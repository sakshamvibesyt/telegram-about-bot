import os
import random
import asyncio
import threading
import sqlite3
from datetime import datetime, timedelta
import time
import json
import html
import urllib.parse
import urllib.request

from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    InlineQueryHandler,
    filters,
)


# ==================================
# CONFIG
# ==================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])

# Apne links yahan change karna
CHANNEL_URL = "https://t.me/sakshamadmin"
YOUTUBE_URL = "https://yt.openinapp.co/wwoez"
INSTAGRAM_URL = "https://insta.openinapp.co/xqhfr"

# Persistent local SQLite storage
DB_FILE = os.environ.get("BOT_DB_FILE", "bot_data.db")

# Optional TMDB API key. If not set, /movie and /series show search buttons
# instead of live metadata. Get a key from TMDB and add it as TMDB_API_KEY.
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_LANGUAGE = os.environ.get("TMDB_LANGUAGE", "en-US").strip()

# Feature toggles / limits
WELCOME_ENABLED_DEFAULT = "1"
# Welcome image: replace welcome.jpg in the bot folder, or set this env variable.
WELCOME_IMAGE_PATH = os.environ.get("WELCOME_IMAGE_PATH", "welcome.jpg").strip()
AUTOMOD_ENABLED_DEFAULT = "0"
REFERRAL_REWARD_DEFAULT = "0"
MAX_WARNINGS_DEFAULT = "3"
FLOOD_LIMIT_DEFAULT = "6"
FLOOD_WINDOW_DEFAULT = "10"



# ==================================
# OWNER ADMIN PANEL
# ==================================


def owner_only(update):
    return bool(update.effective_user and update.effective_user.id == OWNER_ID)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 STATISTICS", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 BROADCAST", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⏰ AUTO PROMO", callback_data="admin_promo")],
        [InlineKeyboardButton("🔗 MANAGE LINKS", callback_data="admin_links")],
        [InlineKeyboardButton("🛡️ MODERATION", callback_data="admin_mod")],
        [InlineKeyboardButton("⚙️ SETTINGS", callback_data="admin_settings")],
        [InlineKeyboardButton("📢 CUSTOM MENTION", callback_data="admin_mention")],
        [InlineKeyboardButton("🚀 MORE FEATURES", callback_data="admin_features")],
    ])


def admin_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")]])


def promo_admin_menu():
    enabled = get_setting("promo_enabled", "1") == "1"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏸️ TURN OFF" if enabled else "▶️ TURN ON", callback_data="promo_toggle")],
        [InlineKeyboardButton("⏱️ SET 5 MIN", callback_data="promo_5"), InlineKeyboardButton("⏱️ SET 10 MIN", callback_data="promo_10")],
        [InlineKeyboardButton("⏱️ SET 30 MIN", callback_data="promo_30")],
        [InlineKeyboardButton("📝 EDIT MESSAGE", callback_data="promo_edit")],
        [InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")],
    ])


def links_admin_menu():
    rows = [[InlineKeyboardButton(f"✏️ {name[:30]}", callback_data=f"link_edit:{link_id}")] for link_id,name,url in load_links()]
    rows += [[InlineKeyboardButton("➕ ADD LINK", callback_data="link_add")], [InlineKeyboardButton("🗑️ DELETE LINK", callback_data="link_delete")], [InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")]]
    return InlineKeyboardMarkup(rows)


def moderation_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 MOD COMMANDS", callback_data="mod_help")],
        [InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")],
    ])


def settings_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 REFRESH", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")],
    ])


async def admin_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    await update.message.reply_text("👑 𝐎𝐖𝐍𝐄𝐑 𝐀𝐃𝐌𝐈𝐍 𝐏𝐀𝐍𝐄𝐋\n\nChoose an option 👇", reply_markup=admin_menu())


async def admin_input(update, context):
    state = context.user_data.get("admin_input")
    if not state or not owner_only(update) or not update.message:
        return False
    value = update.message.text.strip()
    if state == "broadcast":
        context.user_data.pop("admin_input", None)
        with db_connect() as conn:
            ids = [r[0] for r in conn.execute("SELECT user_id FROM users").fetchall()]
        ok = bad = 0
        for uid in ids:
            try:
                await context.bot.send_message(uid, value)
                ok += 1
                await asyncio.sleep(0.05)
            except Exception:
                bad += 1
        await update.message.reply_text(f"📢 Broadcast complete.\n\n✅ Sent: {ok}\n❌ Failed: {bad}", reply_markup=admin_menu())
        return True
    if state == "promo_text":
        set_setting("promo_text", value)
        context.user_data.pop("admin_input", None)
        await update.message.reply_text("✅ Promo message updated.", reply_markup=promo_admin_menu())
        return True
    if state.startswith("add_link:"):
        parts = value.split("|", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip().startswith(("https://", "http://")):
            await update.message.reply_text("❌ Format: Button Name | https://example.com")
            return True
        with db_connect() as conn:
            pos = conn.execute("SELECT COALESCE(MAX(position),-1)+1 FROM links").fetchone()[0]
            conn.execute("INSERT INTO links(name,url,position) VALUES(?,?,?)", (parts[0].strip(), parts[1].strip(), pos))
        context.user_data.pop("admin_input", None)
        await update.message.reply_text("✅ Link added.", reply_markup=links_admin_menu())
        return True
    if state.startswith("edit_link:"):
        link_id = int(state.split(":",1)[1])
        parts = value.split("|", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip().startswith(("https://", "http://")):
            await update.message.reply_text("❌ Format: Button Name | https://example.com")
            return True
        with db_connect() as conn:
            conn.execute("UPDATE links SET name=?, url=? WHERE id=?", (parts[0].strip(), parts[1].strip(), link_id))
        context.user_data.pop("admin_input", None)
        await update.message.reply_text("✅ Link updated.", reply_markup=links_admin_menu())
        return True
    if state == "mention_text":
        set_setting("mention_text", value)
        context.user_data.pop("admin_input", None)
        await update.message.reply_text("✅ Custom mention message saved.", reply_markup=mention_admin_menu())
        return True
    if state == "mention_button":
        parts = value.split("|", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip().startswith(("https://", "http://", "tg://")):
            await update.message.reply_text("❌ Format: Button Name | https://example.com")
            return True
        set_setting("mention_button_name", parts[0].strip())
        set_setting("mention_button_url", parts[1].strip())
        context.user_data.pop("admin_input", None)
        await update.message.reply_text("✅ Custom button saved.", reply_markup=mention_admin_menu())
        return True
    return False


async def mod_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    await update.message.reply_text("🛡️ MODERATION\n\nUse /warn, /mute, /unmute, /ban or /unban as a reply to a user's message.", reply_markup=moderation_menu())


def replied_user(update):
    msg = update.message.reply_to_message if update.message else None
    return msg.from_user if msg else None


async def warn_user(update, context):
    if not owner_only(update): return
    user = replied_user(update)
    if not user:
        await update.message.reply_text("⚠️ Reply to the user's message and use /warn."); return
    with db_connect() as conn:
        conn.execute("INSERT INTO warnings(user_id,count) VALUES(?,1) ON CONFLICT(user_id) DO UPDATE SET count=count+1", (user.id,))
        count = conn.execute("SELECT count FROM warnings WHERE user_id=?", (user.id,)).fetchone()[0]
    await update.message.reply_text(f"⚠️ Warning given to {user.full_name}. Total warnings: {count}")


async def mute_user(update, context):
    if not owner_only(update): return
    user = replied_user(update)
    if not user:
        await update.message.reply_text("⚠️ Reply to the user's message and use /mute."); return
    try:
        from telegram import ChatPermissions
        await context.bot.restrict_chat_member(update.effective_chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"🔇 {user.full_name} muted.")
    except Exception as e:
        await update.message.reply_text(f"❌ Mute failed: {e}")


async def unmute_user(update, context):
    if not owner_only(update): return
    user = replied_user(update)
    if not user:
        await update.message.reply_text("⚠️ Reply to the user's message and use /unmute."); return
    try:
        from telegram import ChatPermissions
        await context.bot.restrict_chat_member(update.effective_chat.id, user.id, permissions=ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
        await update.message.reply_text(f"🔊 {user.full_name} unmuted.")
    except Exception as e:
        await update.message.reply_text(f"❌ Unmute failed: {e}")


async def ban_user(update, context):
    if not owner_only(update): return
    user = replied_user(update)
    if not user:
        await update.message.reply_text("⚠️ Reply to the user's message and use /ban."); return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await update.message.reply_text(f"🚫 {user.full_name} banned.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ban failed: {e}")


async def unban_user(update, context):
    if not owner_only(update): return
    user = replied_user(update)
    if not user:
        await update.message.reply_text("⚠️ Reply to the user's message and use /unban."); return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, user.id, only_if_banned=True)
        await update.message.reply_text(f"✅ {user.full_name} unbanned.")
    except Exception as e:
        await update.message.reply_text(f"❌ Unban failed: {e}")


# ==================================
# GROUP AUTO PROMOTION
# ==================================

AUTO_PROMO_INTERVAL = 60 * 60  # 60 minutes by default
AUTO_PROMO_CHAT_ID = None
AUTO_PROMO_ENABLED = True

PROMO_TEXT = """📢 𝐉𝐎𝐈𝐍 𝐌𝐘 𝐂𝐇𝐀𝐍𝐍𝐄𝐋𝐒

🔥 Stay connected with Saksham Vibes!
👇 Join all our channels/pages:"""

def get_promo_text():
    return get_setting("promo_text", PROMO_TEXT)


def promo_keyboard():
    return build_promo_keyboard()



# ==================================
# USER STATS
# ==================================

users = set()


def db_connect():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL, position INTEGER NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS warnings (user_id INTEGER PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_chats (chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_members (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL, username TEXT, updated_at TEXT NOT NULL, PRIMARY KEY(chat_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS referrals (user_id INTEGER PRIMARY KEY, referred_by INTEGER, joined_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS referral_counts (user_id INTEGER PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS activity (user_id INTEGER NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS welcome_chats (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1)")
        conn.execute("CREATE TABLE IF NOT EXISTS automod_chats (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, max_warnings INTEGER NOT NULL DEFAULT 3, flood_limit INTEGER NOT NULL DEFAULT 6, flood_window INTEGER NOT NULL DEFAULT 10)")
        defaults = {
            "promo_chat_id": "",
            "promo_enabled": "1",
            "promo_interval": str(AUTO_PROMO_INTERVAL),
            "promo_text": PROMO_TEXT,
            "mention_chat_id": "",
            "mention_chat_title": "",
            "mention_text": "",
            "mention_button_name": "",
            "mention_button_url": "",
            "mention_enabled": "1",
            "welcome_enabled": WELCOME_ENABLED_DEFAULT,
            "automod_enabled": AUTOMOD_ENABLED_DEFAULT,
            "max_warnings": MAX_WARNINGS_DEFAULT,
            "flood_limit": FLOOD_LIMIT_DEFAULT,
            "flood_window": FLOOD_WINDOW_DEFAULT,
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
        count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        if count == 0:
            default_links = [
                ("📢 JOIN TELEGRAM", "https://t.me/+6g3B5n2xi2xmNDhl"),
                ("▶️ YOUTUBE", "https://yt.openinapp.co/wwoez"),
                ("📸 INSTAGRAM", "https://insta.openinapp.co/xqhfr"),
                ("❤️ SUPPORT ME", "https://sub4unlock.com/S/u53lm"),
                ("Loader and mods💀", "https://t.me/+OV5fY7y4GA5lZmI1"),
                ("Loader and mods II 🥱", "https://t.me/+e2JbHAluwrU4Yzg1"),
                ("Server Hack💀", "https://t.me/+ZH_BoOkA5foxNTk1"),
                ("👑 OWNER — @sakshamvibesyt", "https://t.me/sakshamvibesyt"),
            ]
            conn.executemany("INSERT INTO links(name,url,position) VALUES(?,?,?)", [(n,u,i) for i,(n,u) in enumerate(default_links)])


def get_setting(key, default=""):
    with db_connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key, value):
    with db_connect() as conn:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def save_user(user_id):
    users.add(user_id)
    with db_connect() as conn:
        conn.execute("INSERT OR IGNORE INTO users(user_id,joined_at) VALUES(?,?)", (user_id, datetime.utcnow().isoformat()))


def load_links():
    with db_connect() as conn:
        return conn.execute("SELECT id,name,url FROM links ORDER BY position,id").fetchall()


def build_promo_keyboard():
    rows = []
    for link_id, name, url in load_links():
        rows.append([InlineKeyboardButton(name, url=url)])
    return InlineKeyboardMarkup(rows)


def get_user_count():
    with db_connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]



# ==================================
# ADVANCED FEATURES HELPERS
# ==================================

def record_activity(user_id, event):
    try:
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO activity(user_id,event,created_at) VALUES(?,?,?)",
                (user_id, event, datetime.utcnow().isoformat())
            )
    except Exception as e:
        print(f"⚠️ Activity log error: {e}")


def tmdb_request(path, params):
    if not TMDB_API_KEY:
        return None, "TMDB_API_KEY is not configured."
    params = dict(params)
    params["api_key"] = TMDB_API_KEY
    params.setdefault("language", TMDB_LANGUAGE)
    url = "https://api.themoviedb.org/3" + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            return json.loads(response.read().decode("utf-8")), None
    except Exception as e:
        return None, str(e)


def format_movie_result(item, media_type="movie"):
    title = item.get("title") or item.get("name") or "Unknown"
    date = item.get("release_date") or item.get("first_air_date") or "N/A"
    rating = item.get("vote_average")
    rating_text = f"{float(rating):.1f}/10" if rating else "N/A"
    overview = (item.get("overview") or "No description available.").strip()
    if len(overview) > 500:
        overview = overview[:497] + "..."
    kind = "🎬 MOVIE" if media_type == "movie" else "📺 SERIES"
    return (
        f"{kind}\n\n"
        f"🎞️ {title}\n"
        f"📅 Release: {date}\n"
        f"⭐ Rating: {rating_text}\n\n"
        f"📝 {overview}"
    )


def movie_search_keyboard(query):
    q = urllib.parse.quote_plus(query)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Google Search", url=f"https://www.google.com/search?q={q}+movie")],
        [InlineKeyboardButton("🎬 TMDB Search", url=f"https://www.themoviedb.org/search/movie?query={q}")],
        [InlineKeyboardButton("▶️ YouTube Search", url=f"https://www.youtube.com/results?search_query={q}+trailer")],
        [InlineKeyboardButton("📺 JustWatch India", url=f"https://www.justwatch.com/in/search?q={q}")],
    ])


def series_search_keyboard(query):
    q = urllib.parse.quote_plus(query)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Google Search", url=f"https://www.google.com/search?q={q}+series")],
        [InlineKeyboardButton("📺 TMDB Search", url=f"https://www.themoviedb.org/search/tv?query={q}")],
        [InlineKeyboardButton("▶️ YouTube Search", url=f"https://www.youtube.com/results?search_query={q}+trailer")],
        [InlineKeyboardButton("📺 JustWatch India", url=f"https://www.justwatch.com/in/search?q={q}")],
    ])


def welcome_enabled(chat_id):
    return get_setting(f"welcome:{chat_id}", get_setting("welcome_enabled", "1")) == "1"


def automod_config(chat_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT enabled,max_warnings,flood_limit,flood_window FROM automod_chats WHERE chat_id=?",
            (chat_id,)
        ).fetchone()
    if row:
        return bool(row[0]), int(row[1]), int(row[2]), int(row[3])
    return (
        get_setting("automod_enabled", AUTOMOD_ENABLED_DEFAULT) == "1",
        int(get_setting("max_warnings", MAX_WARNINGS_DEFAULT)),
        int(get_setting("flood_limit", FLOOD_LIMIT_DEFAULT)),
        int(get_setting("flood_window", FLOOD_WINDOW_DEFAULT)),
    )


def set_automod_config(chat_id, enabled=None, max_warnings=None, flood_limit=None, flood_window=None):
    current = automod_config(chat_id)
    values = [
        int(current[0] if enabled is None else enabled),
        current[1] if max_warnings is None else int(max_warnings),
        current[2] if flood_limit is None else int(flood_limit),
        current[3] if flood_window is None else int(flood_window),
    ]
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO automod_chats(chat_id,enabled,max_warnings,flood_limit,flood_window)
               VALUES(?,?,?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
               enabled=excluded.enabled,max_warnings=excluded.max_warnings,
               flood_limit=excluded.flood_limit,flood_window=excluded.flood_window""",
            (chat_id, *values)
        )


def increment_warning(user_id):
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO warnings(user_id,count) VALUES(?,1) "
            "ON CONFLICT(user_id) DO UPDATE SET count=count+1",
            (user_id,)
        )
        return conn.execute(
            "SELECT count FROM warnings WHERE user_id=?", (user_id,)
        ).fetchone()[0]


def referral_link(bot_username, user_id):
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def register_referral(user_id, referrer_id):
    if not referrer_id or referrer_id == user_id:
        return False
    with db_connect() as conn:
        existing = conn.execute(
            "SELECT referred_by FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO referrals(user_id,referred_by,joined_at) VALUES(?,?,?)",
            (user_id, referrer_id, datetime.utcnow().isoformat())
        )
        conn.execute(
            "INSERT INTO referral_counts(user_id,count) VALUES(?,1) "
            "ON CONFLICT(user_id) DO UPDATE SET count=count+1",
            (referrer_id,)
        )
    return True


def get_referral_count(user_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT count FROM referral_counts WHERE user_id=?", (user_id,)
        ).fetchone()
    return row[0] if row else 0


def top_referrers(limit=10):
    with db_connect() as conn:
        return conn.execute(
            "SELECT user_id,count FROM referral_counts ORDER BY count DESC LIMIT ?",
            (limit,)
        ).fetchall()


def admin_features_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 MOVIE SEARCH", callback_data="feature_movie")],
        [InlineKeyboardButton("📺 SERIES SEARCH", callback_data="feature_series")],
        [InlineKeyboardButton("👋 WELCOME", callback_data="feature_welcome")],
        [InlineKeyboardButton("🛡️ AUTO-MOD", callback_data="feature_automod")],
        [InlineKeyboardButton("🎁 REFERRALS", callback_data="feature_referral")],
        [InlineKeyboardButton("📊 ADVANCED STATS", callback_data="feature_stats")],
        [InlineKeyboardButton("⚙️ SETTINGS", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")],
    ])


# ==================================
# CUSTOM MENTION MESSAGE
# ==================================

def save_group_member(chat, user):
    if not chat or chat.type not in ("group", "supergroup") or not user or user.is_bot:
        return
    now = datetime.utcnow().isoformat()
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO group_chats(chat_id,title,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title,updated_at=excluded.updated_at",
            (chat.id, chat.title or str(chat.id), now),
        )
        conn.execute(
            "INSERT INTO group_members(chat_id,user_id,name,username,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(chat_id,user_id) DO UPDATE SET name=excluded.name,username=excluded.username,updated_at=excluded.updated_at",
            (chat.id, user.id, user.full_name or user.first_name or "User", user.username or "", now),
        )


def known_groups():
    with db_connect() as conn:
        return conn.execute("SELECT chat_id,title FROM group_chats ORDER BY updated_at DESC").fetchall()


def group_members(chat_id):
    with db_connect() as conn:
        return conn.execute("SELECT user_id,name FROM group_members WHERE chat_id=? ORDER BY updated_at DESC", (chat_id,)).fetchall()


def mention_admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 SELECT GROUP", callback_data="mention_groups")],
        [InlineKeyboardButton("📝 SET MESSAGE", callback_data="mention_message")],
        [InlineKeyboardButton("🔘 SET BUTTON", callback_data="mention_button")],
        [InlineKeyboardButton("👥 MENTION: ON", callback_data="mention_toggle")],
        [InlineKeyboardButton("📤 SEND", callback_data="mention_send")],
        [InlineKeyboardButton("🗑️ CLEAR", callback_data="mention_clear")],
        [InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")],
    ])


def mention_status():
    gid = get_setting("mention_chat_id", "")
    title = get_setting("mention_chat_title", "Not selected")
    msg = get_setting("mention_text", "")
    button = get_setting("mention_button_name", "")
    enabled = get_setting("mention_enabled", "1") == "1"
    return title, gid, msg, button, enabled


def mention_groups_menu():
    rows = []
    for chat_id, title in known_groups()[:20]:
        safe_title = (title or str(chat_id))[:35]
        rows.append([InlineKeyboardButton(f"📢 {safe_title}", callback_data=f"mention_group:{chat_id}")])
    if not rows:
        rows.append([InlineKeyboardButton("❌ No group detected yet", callback_data="mention_noop")])
    rows.append([InlineKeyboardButton("🔙 CUSTOM MENTION", callback_data="admin_mention")])
    return InlineKeyboardMarkup(rows)


def mention_panel_text():
    title, gid, msg, button, enabled = mention_status()
    return (
        "📢 𝐂𝐔𝐒𝐓𝐎𝐌 𝐌𝐄𝐍𝐓𝐈𝐎𝐍\n\n"
        f"🎯 Group: {title if gid else 'Not selected'}\n"
        f"📝 Message: {'SET ✅' if msg else 'NOT SET ❌'}\n"
        f"🔘 Button: {button if button else 'NOT SET'}\n"
        f"👥 Mention: {'ON 🟢' if enabled else 'OFF 🔴'}\n\n"
        "Choose an option 👇"
    )


async def track_group_activity(update, context):
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        save_group_member(update.effective_chat, update.effective_user)


async def register_group(update, context):
    """Explicitly register the current group for the Custom Mention selector.
    This works even when Telegram privacy mode prevents ordinary group
    messages from reaching the bot. The owner can run it in the group.
    """
    if not owner_only(update):
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Ye command apne group mein use karo.")
        return
    save_group_member(chat, user)
    await update.message.reply_text(
        f"✅ Group registered!\n\n📢 {chat.title}\n🆔 {chat.id}\n\nAb private chat mein /admin → 📢 CUSTOM MENTION → 🎯 SELECT GROUP kholo."
    )


# ==================================
# RANDOM QUOTES
# ==================================

QUOTES = [
    "😎 Apna vibe hi alag hai.",
    "🔥 Humse jalne wale bhi kamaal karte hain.",
    "👑 Naam yaad rakhna, kaam yaad rahega.",
    "✨ Simple rehna choice hai, weak hona nahi.",
    "🖤 Silence bhi kabhi-kabhi sabse bada answer hota hai.",
    "⚡ Apni duniya, apne rules, apni vibe.",
    "💯 Original raho, copy banne ki zarurat nahi.",
]


# ==================================
# MAIN MENU
# ==================================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "👤 ABOUT ME",
                callback_data="about"
            ),
            InlineKeyboardButton(
                "💌 MESSAGE OWNER",
                callback_data="dm"
            )
        ],
        [
            InlineKeyboardButton(
                "🎲 FUN ZONE",
                callback_data="fun"
            ),
            InlineKeyboardButton(
                "💭 RANDOM QUOTE",
                callback_data="quote"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 BOT STATS",
                callback_data="stats"
            ),
            InlineKeyboardButton(
                "ℹ️ HELP",
                callback_data="help"
            )
        ],
        [
            InlineKeyboardButton("🎬 MOVIE", callback_data="movie_menu"),
            InlineKeyboardButton("📺 SERIES", callback_data="series_menu")
        ],
        [
            InlineKeyboardButton("🎁 REFERRAL", callback_data="referral")
        ],
        [
            InlineKeyboardButton(
                "📢 JOIN CHANNEL",
                url=CHANNEL_URL
            )
        ],
        [
            InlineKeyboardButton(
                "▶️ YOUTUBE",
                url=YOUTUBE_URL
            ),
            InlineKeyboardButton(
                "📸 INSTAGRAM",
                url=INSTAGRAM_URL
            )
        ],        [
            InlineKeyboardButton(
                "❤️ SUPPORT ME",
                url="https://sub4unlock.com/S/u53lm"
            ),
            InlineKeyboardButton(
                "🔗 YOUTUBE SUPPORT",
                url="https://t.me/Sakshamythelp_bot"
            )
        ],
        [
            InlineKeyboardButton(
                "👑 OWNER",
                url="https://t.me/sakshamvibesyt"
            )
        ]
    ])


# ==================================
# ABOUT MESSAGE
# ==================================

ABOUT = """👑 𝐀𝐁𝐎𝐔𝐓 𝐒𝐀𝐊𝐒𝐇𝐀𝐌

╔═════════════════════
╠ 👑 𝐊𝐈𝐍𝐆 𝐎𝐅 𝐕𝐈𝐁𝐄𝐒 ✨
╠ ❤️ 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 ❤️
╚═════════════════════

╔═════════════════════
╠ 🌱 𝙽𝙰𝙼𝙴 ➜ 𝚂𝙰𝙺𝚂𝙷𝙰𝙼
╠ 😎 𝚅𝙸𝙱𝙴 ➜ 𝚄𝙽𝙸𝚀𝚄𝙴
╠ 🔥 𝚂𝚃𝚈𝙻𝙴 ➜ 𝙳𝙸𝙵𝙵𝙴𝚁𝙴𝙽𝚃
╠ ⭐ 𝙰𝙰𝙽𝙳𝙰𝚉 𝙷𝙸 𝙰𝙻𝙰𝙶 𝙷𝙰𝙸
╚═════════════════════

👑 𝗢𝗪𝗡𝗘𝗥
❤️ @sakshamvibesyt
"""



def with_db_movie_count():
    with db_connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM activity WHERE event='movie'").fetchone()[0]


def with_db_series_count():
    with db_connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM activity WHERE event='series'").fetchone()[0]


# ==================================
# START
# ==================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
    record_activity(user.id, "start")

    if context.args:
        payload = context.args[0].strip()
        if payload.startswith("ref_"):
            try:
                referrer_id = int(payload.split("_", 1)[1])
                if register_referral(user.id, referrer_id):
                    try:
                        await context.bot.send_message(
                            referrer_id,
                            f"🎉 New referral!\\n\\n👤 {user.full_name} started the bot using your link.\\n🎁 Total referrals: {get_referral_count(referrer_id)}"
                        )
                    except Exception:
                        pass
            except ValueError:
                pass

    text = f"""✨ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 {user.first_name}! ✨

🤖 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 𝐁𝐎𝐓

👑 Your personal vibe destination.

🎬 Movie & Series Search
🎁 Referral System
🛡️ Smart Group Tools

👇 Choose an option below and explore the bot!

❤️ 𝐓𝐇𝐀𝐍𝐊𝐒 𝐅𝐎𝐑 𝐒𝐓𝐀𝐑𝐓𝐈𝐍𝐆 𝐌𝐘 𝐁𝐎𝐓 ❤️"""

    await update.message.reply_text(text, reply_markup=main_menu())


# ==================================
# BUTTON HANDLER
# ==================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    save_user(user.id)

    if query.data == "admin":
        if not owner_only(update):
            await query.answer("Access denied", show_alert=True); return
        await query.edit_message_text("👑 𝐎𝐖𝐍𝐄𝐑 𝐀𝐃𝐌𝐈𝐍 𝐏𝐀𝐍𝐄𝐋\n\nChoose an option 👇", reply_markup=admin_menu())


    elif query.data == "admin_features":
        if not owner_only(update): return
        await query.edit_message_text(
            "🚀 𝐌𝐎𝐑𝐄 𝐅𝐄𝐀𝐓𝐔𝐑𝐄𝐒\n\nChoose a feature 👇",
            reply_markup=admin_features_menu()
        )

    elif query.data == "feature_movie":
        if not owner_only(update): return
        await query.edit_message_text(
            "🎬 𝐌𝐎𝐕𝐈𝐄 𝐒𝐄𝐀𝐑𝐂𝐇\n\n"
            "Command: /movie <name>\n"
            "With TMDB_API_KEY, the bot returns live title, rating, release date and overview.\n"
            "Without a key, it provides safe search buttons.",
            reply_markup=admin_features_menu()
        )

    elif query.data == "feature_series":
        if not owner_only(update): return
        await query.edit_message_text(
            "📺 𝐒𝐄𝐑𝐈𝐄𝐒 𝐒𝐄𝐀𝐑𝐂𝐇\n\n"
            "Command: /series <name>\n"
            "TMDB_API_KEY enables live metadata.",
            reply_markup=admin_features_menu()
        )

    elif query.data == "feature_welcome":
        if not owner_only(update): return
        await query.edit_message_text(
            "👋 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐒𝐘𝐒𝐓𝐄𝐌\n\n"
            "Use /welcome inside a group to toggle automatic welcome messages.\n"
            "The bot must be able to receive service messages.",
            reply_markup=admin_features_menu()
        )

    elif query.data == "feature_automod":
        if not owner_only(update): return
        await query.edit_message_text(
            "🛡️ 𝐀𝐔𝐓𝐎-𝐌𝐎𝐃\n\n"
            "Use /automod inside a group to toggle smart auto-moderation.\n"
            "It handles configured suspicious phrases and flood warnings.\n"
            "Owner/admin permissions are required for deletion/restriction.",
            reply_markup=admin_features_menu()
        )

    elif query.data == "feature_referral":
        if not owner_only(update): return
        await query.edit_message_text(
            "🎁 𝐑𝐄𝐅𝐄𝐑𝐑𝐀𝐋 𝐒𝐘𝐒𝐓𝐄𝐌\n\n"
            "Users get a unique /start ref_<id> link.\n"
            "Each valid first-time referral is counted once.",
            reply_markup=admin_features_menu()
        )

    elif query.data == "feature_stats":
        if not owner_only(update): return
        with db_connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            movies = conn.execute("SELECT COUNT(*) FROM activity WHERE event='movie'").fetchone()[0]
            series = conn.execute("SELECT COUNT(*) FROM activity WHERE event='series'").fetchone()[0]
            groups = conn.execute("SELECT COUNT(*) FROM group_chats").fetchone()[0]
        await query.edit_message_text(
            f"📊 𝐀𝐃𝐕𝐀𝐍𝐂𝐄𝐃 𝐒𝐓𝐀𝐓𝐒\n\n"
            f"👥 Users: {total}\n🎬 Movies: {movies}\n📺 Series: {series}\n👨‍👩‍👧 Groups: {groups}",
            reply_markup=admin_features_menu()
        )

    elif query.data == "movie_menu":
        await query.edit_message_text(
            "🎬 𝐌𝐎𝐕𝐈𝐄 𝐒𝐄𝐀𝐑𝐂𝐇\n\n"
            "Type:\n/movie <movie name>\n\n"
            "Example:\n/movie Interstellar",
            reply_markup=back_button()
        )

    elif query.data == "series_menu":
        await query.edit_message_text(
            "📺 𝐒𝐄𝐑𝐈𝐄𝐒 𝐒𝐄𝐀𝐑𝐂𝐇\n\n"
            "Type:\n/series <series name>\n\n"
            "Example:\n/series Stranger Things",
            reply_markup=back_button()
        )

    elif query.data == "referral":
        try:
            me = await context.bot.get_me()
            link = referral_link(me.username, user.id)
            await query.edit_message_text(
                f"🎁 𝐘𝐎𝐔𝐑 𝐑𝐄𝐅𝐄𝐑𝐑𝐀𝐋\n\n"
                f"🔗 {link}\n\n"
                f"👥 Referrals: {get_referral_count(user.id)}",
                reply_markup=back_button()
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Referral error: {e}", reply_markup=back_button())

    elif query.data == "admin_stats":
        if not owner_only(update): return
        with db_connect() as conn:
            groups = conn.execute("SELECT COUNT(*) FROM settings WHERE key='promo_chat_id' AND value != ''").fetchone()[0]
        await query.edit_message_text(f"📊 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐒\n\n👥 Users: {get_user_count()}\n📢 Promo group configured: {'YES' if get_setting('promo_chat_id','') else 'NO'}\n⏱️ Promo interval: {int(get_setting('promo_interval',str(AUTO_PROMO_INTERVAL)))//60} min\n🤖 Status: ONLINE ✅", reply_markup=admin_back())

    elif query.data == "admin_broadcast":
        if not owner_only(update): return
        context.user_data["admin_input"] = "broadcast"
        await query.edit_message_text("📢 BROADCAST\n\nApna message type karke bhejo.\n/cancel se cancel karo.", reply_markup=admin_back())

    elif query.data == "admin_promo":
        if not owner_only(update): return
        await query.edit_message_text("⏰ AUTO PROMO\n\nStatus: " + ("ON 🟢" if get_setting("promo_enabled","1")=="1" else "OFF 🔴"), reply_markup=promo_admin_menu())

    elif query.data == "promo_toggle":
        if not owner_only(update): return
        new = "0" if get_setting("promo_enabled","1")=="1" else "1"
        set_setting("promo_enabled", new)
        await query.edit_message_text("⏰ AUTO PROMO\n\nStatus: " + ("ON 🟢" if new=="1" else "OFF 🔴"), reply_markup=promo_admin_menu())

    elif query.data in ("promo_5", "promo_10", "promo_30"):
        if not owner_only(update): return
        mins = int(query.data.split("_")[1])
        set_setting("promo_interval", mins*60)
        await query.edit_message_text(f"✅ Auto-promo interval set to {mins} minutes.", reply_markup=promo_admin_menu())

    elif query.data == "promo_edit":
        if not owner_only(update): return
        context.user_data["admin_input"] = "promo_text"
        await query.edit_message_text("📝 New promo message bhejo:", reply_markup=admin_back())

    elif query.data == "admin_mention":
        if not owner_only(update): return
        await query.edit_message_text(mention_panel_text(), reply_markup=mention_admin_menu())

    elif query.data == "mention_groups":
        if not owner_only(update): return
        await query.edit_message_text("🎯 SELECT GROUP\n\nGroups are shown after the bot receives activity from them.", reply_markup=mention_groups_menu())

    elif query.data.startswith("mention_group:"):
        if not owner_only(update): return
        gid = int(query.data.split(":",1)[1])
        row = next((r for r in known_groups() if r[0] == gid), None)
        if not row:
            await query.edit_message_text("❌ Group not found.", reply_markup=mention_admin_menu()); return
        set_setting("mention_chat_id", str(gid))
        set_setting("mention_chat_title", row[1])
        await query.edit_message_text(f"✅ Selected group: {row[1]}", reply_markup=mention_admin_menu())

    elif query.data == "mention_noop":
        if not owner_only(update): return
        await query.answer("Send a message in the group first so the bot can detect it.", show_alert=True)

    elif query.data == "mention_message":
        if not owner_only(update): return
        context.user_data["admin_input"] = "mention_text"
        await query.edit_message_text("📝 Send the custom message now.\n\nYou can write @everyone in the text; the bot will replace it with clickable mentions of members it has seen in this group.\n/cancel to cancel.", reply_markup=admin_back())

    elif query.data == "mention_button":
        if not owner_only(update): return
        context.user_data["admin_input"] = "mention_button"
        await query.edit_message_text("🔘 Send: Button Name | https://example.com\n\n/cancel to cancel.", reply_markup=admin_back())

    elif query.data == "mention_toggle":
        if not owner_only(update): return
        new = "0" if get_setting("mention_enabled", "1") == "1" else "1"
        set_setting("mention_enabled", new)
        await query.edit_message_text(mention_panel_text(), reply_markup=mention_admin_menu())

    elif query.data == "mention_clear":
        if not owner_only(update): return
        for key in ("mention_chat_id", "mention_chat_title", "mention_text", "mention_button_name", "mention_button_url"):
            set_setting(key, "")
        set_setting("mention_enabled", "1")
        context.user_data.pop("admin_input", None)
        await query.edit_message_text("🗑️ Custom mention settings cleared.", reply_markup=mention_admin_menu())

    elif query.data == "mention_send":
        if not owner_only(update): return
        gid = get_setting("mention_chat_id", "")
        text = get_setting("mention_text", "")
        enabled = get_setting("mention_enabled", "1") == "1"
        if not gid:
            await query.answer("Select a group first.", show_alert=True); return
        if not text:
            await query.answer("Set a message first.", show_alert=True); return
        try:
            gid_int = int(gid)
            members = group_members(gid_int) if enabled else []
            from telegram import MessageEntity, User

            marker = "@everyone"
            if enabled and marker in text:
                if not members:
                    await query.answer("No group members have been detected yet. Send some messages in that group first.", show_alert=True)
                    return
                before, after = text.split(marker, 1)
                mention_parts = []
                entities = []
                out = before
                for i, (uid, name) in enumerate(members):
                    if i:
                        out += " "
                    offset = len(out.encode("utf-16-le")) // 2
                    display_name = name[:64]
                    out += display_name
                    length = len(display_name.encode("utf-16-le")) // 2
                    entities.append(MessageEntity(
                        type="text_mention",
                        offset=offset,
                        length=length,
                        user=User(id=uid, first_name=display_name, is_bot=False),
                    ))
                out += after
                clean = out
            else:
                clean = text.replace(marker, "") if not enabled else text
                entities = []

            kb = None
            bname = get_setting("mention_button_name", "")
            burl = get_setting("mention_button_url", "")
            if bname and burl:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(bname, url=burl)]])

            await context.bot.send_message(
                chat_id=gid_int,
                text=clean,
                entities=entities or None,
                reply_markup=kb,
            )
            await query.edit_message_text("✅ Custom mention message sent successfully.", reply_markup=mention_admin_menu())
        except Exception as e:
            await query.edit_message_text(f"❌ Send failed: {e}", reply_markup=mention_admin_menu())

    elif query.data == "admin_links":
        if not owner_only(update): return
        await query.edit_message_text("🔗 MANAGE LINKS\n\nExisting buttons edit karne ke liye button choose karo.", reply_markup=links_admin_menu())

    elif query.data == "link_add":
        if not owner_only(update): return
        context.user_data["admin_input"] = "add_link:new"
        await query.edit_message_text("➕ Send: Button Name | https://link.com", reply_markup=admin_back())

    elif query.data == "link_delete":
        if not owner_only(update): return
        rows = [[InlineKeyboardButton(f"🗑️ {name[:30]}", callback_data=f"link_del:{link_id}")] for link_id,name,url in load_links()]
        rows.append([InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin_links")])
        await query.edit_message_text("🗑️ Choose a link to delete:", reply_markup=InlineKeyboardMarkup(rows))

    elif query.data.startswith("link_del:"):
        if not owner_only(update): return
        link_id=int(query.data.split(":",1)[1])
        with db_connect() as conn: conn.execute("DELETE FROM links WHERE id=?", (link_id,))
        await query.edit_message_text("✅ Link deleted.", reply_markup=links_admin_menu())

    elif query.data.startswith("link_edit:"):
        if not owner_only(update): return
        link_id=int(query.data.split(":",1)[1])
        row=next((r for r in load_links() if r[0]==link_id), None)
        if not row: await query.edit_message_text("❌ Link not found.", reply_markup=links_admin_menu()); return
        context.user_data["admin_input"] = f"edit_link:{link_id}"
        await query.edit_message_text(f"✏️ Current: {row[1]} | {row[2]}\n\nSend new: Button Name | https://link.com", reply_markup=admin_back())

    elif query.data == "admin_mod":
        if not owner_only(update): return
        await query.edit_message_text("🛡️ MODERATION\n\nUse /warn, /mute, /unmute, /ban, /unban as replies to a user's message.", reply_markup=moderation_menu())

    elif query.data == "mod_help":
        await query.edit_message_text("🛡️ MOD COMMANDS\n\n/warn — warning\n/mute — mute\n/unmute — unmute\n/ban — ban\n/unban — unban", reply_markup=admin_back())

    elif query.data == "admin_settings":
        if not owner_only(update): return
        await query.edit_message_text(f"⚙️ SETTINGS\n\nDatabase: SQLite ✅\nUsers stored: {get_user_count()}\nPromo persistence: {'ON' if get_setting('promo_chat_id','') else 'NOT SET'}", reply_markup=settings_menu())

    elif query.data == "about":

        await query.edit_message_text(
            ABOUT,
            reply_markup=back_button()
        )

    elif query.data == "dm":

        context.user_data["dm_mode"] = True

        await query.edit_message_text(
            """💌 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐎𝐖𝐍𝐄𝐑

✍️ Ab अपना message type karke bhejo.

❌ Cancel karne ke liye /cancel use karo.""",
            reply_markup=back_button()
        )

    elif query.data == "fun":

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❤️ LOVE CALCULATOR",
                    callback_data="love"
                )
            ],
            [
                InlineKeyboardButton(
                    "🎲 ROLL DICE",
                    callback_data="dice"
                )
            ],
            [
                InlineKeyboardButton(
                    "💭 RANDOM QUOTE",
                    callback_data="quote"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 BACK",
                    callback_data="menu"
                )
            ]
        ])

        await query.edit_message_text(
            """🎲 𝐅𝐔𝐍 𝐙𝐎𝐍𝐄

Choose a fun option 👇""",
            reply_markup=keyboard
        )

    elif query.data == "love":

        percentage = random.randint(1, 100)

        await query.edit_message_text(
            f"""❤️ 𝐋𝐎𝐕𝐄 𝐂𝐀𝐋𝐂𝐔𝐋𝐀𝐓𝐎𝐑 ❤️

💘 Your Love Percentage:

🔥 {percentage}% 🔥

😎 Just for fun!""",
            reply_markup=back_fun_button()
        )

    elif query.data == "dice":

        number = random.randint(1, 6)

        await query.edit_message_text(
            f"""🎲 𝐃𝐈𝐂𝐄 𝐑𝐎𝐋𝐋

You rolled:

🔥 {number} 🔥""",
            reply_markup=back_fun_button()
        )

    elif query.data == "quote":

        quote = random.choice(QUOTES)

        await query.edit_message_text(
            f"""💭 𝐕𝐈𝐁𝐄 𝐎𝐅 𝐓𝐇𝐄 𝐌𝐎𝐌𝐄𝐍𝐓

{quote}""",
            reply_markup=back_button()
        )

    elif query.data == "stats":

        await query.edit_message_text(
            f"""📊 𝐁𝐎𝐓 𝐒𝐓𝐀𝐓𝐒

👥 Total users:
{get_user_count()}

🎬 Movie searches:
{with_db_movie_count()}

📺 Series searches:
{with_db_series_count()}

🤖 Bot Status: ONLINE ✅""",
            reply_markup=back_button()
        )

    elif query.data == "help":

        await query.edit_message_text(
            """ℹ️ 𝐁𝐎𝐓 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒

/start — Main menu
/about — About Saksham
/dm — Message owner
/cancel — Cancel DM
/love — Random love percentage
/dice — Roll a dice
/quote — Random vibe quote
/stats — Bot stats
/id — Your Telegram ID
/ping — Bot status

👇 Buttons se bhi bot explore kar sakte ho!""",
            reply_markup=back_button()
        )

    elif query.data == "menu":

        await query.edit_message_text(
            """✨ 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 𝐁𝐎𝐓 ✨

👇 Choose what you want to explore!""",
            reply_markup=main_menu()
        )


# ==================================
# BACK BUTTONS
# ==================================

def back_button():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 MAIN MENU",
                callback_data="menu"
            )
        ]
    ])


def back_fun_button():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎲 FUN ZONE",
                callback_data="fun"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 MAIN MENU",
                callback_data="menu"
            )
        ]
    ])


# ==================================
# COMMANDS
# ==================================

async def about_command(update, context):
    save_user(update.effective_user.id)

    await update.message.reply_text(
        ABOUT,
        reply_markup=back_button()
    )


async def help_command(update, context):

    await update.message.reply_text(
        """ℹ️ 𝐁𝐎𝐓 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒

/start
/about
/dm
/cancel
/love
/dice
/quote
/stats
/id
/ping
/movie <name>
/series <name>
/referral
/advstats
/admin — Owner Admin Panel
/mod — Moderation Panel
/setpromo — Set this group for auto-promo
/autopromo_on — Auto-promo ON
/autopromo_off — Auto-promo OFF
/welcome — Toggle group welcome
/automod — Toggle smart auto-mod
/advstats — Advanced statistics
/inline mode — Search via @YourBot <query> after enabling inline mode in BotFather"""
    )


async def ping(update, context):

    await update.message.reply_text(
        "🏓 𝐏𝐎𝐍𝐆!\n\n"
        "🤖 Bot is ONLINE & WORKING ✅"
    )


async def user_id(update, context):

    await update.message.reply_text(
        f"🆔 Your Telegram ID:\n\n{update.effective_user.id}"
    )



# ==================================
# MOVIE / SERIES SEARCH
# ==================================

async def movie_command(update, context):
    save_user(update.effective_user.id)
    record_activity(update.effective_user.id, "movie")
    if not context.args:
        await update.message.reply_text(
            "🎬 𝐌𝐎𝐕𝐈𝐄 𝐒𝐄𝐀𝐑𝐂𝐇\n\nUse:\n/movie <movie name>\n\nExample:\n/movie Interstellar"
        )
        return

    query = " ".join(context.args).strip()
    data, error = await asyncio.to_thread(
        tmdb_request, "/search/movie", {"query": query, "include_adult": "false"}
    )
    if data and data.get("results"):
        top = data["results"][0]
        text = format_movie_result(top, "movie")
        await update.message.reply_text(text, reply_markup=movie_search_keyboard(query))
    else:
        await update.message.reply_text(
            f"🔎 No live TMDB result found for: {query}\n\n"
            "Try a different spelling or use the search buttons below.",
            reply_markup=movie_search_keyboard(query)
        )


async def series_command(update, context):
    save_user(update.effective_user.id)
    record_activity(update.effective_user.id, "series")
    if not context.args:
        await update.message.reply_text(
            "📺 𝐒𝐄𝐑𝐈𝐄𝐒 𝐒𝐄𝐀𝐑𝐂𝐇\n\nUse:\n/series <series name>\n\nExample:\n/series Stranger Things"
        )
        return

    query = " ".join(context.args).strip()
    data, error = await asyncio.to_thread(
        tmdb_request, "/search/tv", {"query": query, "include_adult": "false"}
    )
    if data and data.get("results"):
        top = data["results"][0]
        text = format_movie_result(top, "tv")
        await update.message.reply_text(text, reply_markup=series_search_keyboard(query))
    else:
        await update.message.reply_text(
            f"🔎 No live TMDB result found for: {query}\n\n"
            "Try a different spelling or use the search buttons below.",
            reply_markup=series_search_keyboard(query)
        )


async def referral_command(update, context):
    save_user(update.effective_user.id)
    record_activity(update.effective_user.id, "referral")
    try:
        me = await context.bot.get_me()
        link = referral_link(me.username, update.effective_user.id)
        count = get_referral_count(update.effective_user.id)
        await update.message.reply_text(
            f"🎁 𝐑𝐄𝐅𝐄𝐑𝐑𝐀𝐋 𝐒𝐘𝐒𝐓𝐄𝐌\n\n"
            f"🔗 Your invite link:\n{link}\n\n"
            f"👥 Successful referrals: {count}\n\n"
            "Share your link with friends to grow your referral count."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Referral error: {e}")


async def advanced_stats_command(update, context):
    save_user(update.effective_user.id)
    with db_connect() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        starts = conn.execute("SELECT COUNT(*) FROM activity WHERE event='start'").fetchone()[0]
        movies = conn.execute("SELECT COUNT(*) FROM activity WHERE event='movie'").fetchone()[0]
        series = conn.execute("SELECT COUNT(*) FROM activity WHERE event='series'").fetchone()[0]
        groups = conn.execute("SELECT COUNT(*) FROM group_chats").fetchone()[0]
        warnings_total = conn.execute("SELECT COALESCE(SUM(count),0) FROM warnings").fetchone()[0]
    await update.message.reply_text(
        f"📊 𝐀𝐃𝐕𝐀𝐍𝐂𝐄𝐃 𝐒𝐓𝐀𝐓𝐒\n\n"
        f"👥 Total users: {total_users}\n"
        f"▶️ Starts logged: {starts}\n"
        f"🎬 Movie searches: {movies}\n"
        f"📺 Series searches: {series}\n"
        f"👨‍👩‍👧 Groups detected: {groups}\n"
        f"⚠️ Total warnings: {warnings_total}\n"
        f"🤖 Status: ONLINE ✅"
    )


async def myref_command(update, context):
    await referral_command(update, context)


# ==================================
# GROUP WELCOME
# ==================================

async def welcome_new_members(update, context):
    """Stylish automatic welcome message for every new group member."""
    if not update.message or not update.message.new_chat_members:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup") or not welcome_enabled(chat.id):
        return

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        save_user(member.id)

        first_name = html.escape(member.first_name or "User")
        full_name = html.escape(member.full_name or member.first_name or "User")
        username = f"@{html.escape(member.username)}" if member.username else "Not set"
        chat_title = html.escape(chat.title or "Our Group")

        welcome_text = (
            f"🌸✨ <b>WELCOME TO THE FAMILY</b> ✨🌸\n"
            f"╭━━━━━━━━━━━━━━━━━━━━╮\n"
            f"│ 💖 <b>{first_name}</b>, glad to have you here!\n"
            f"╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"🎀 <b>GROUP</b>  ➜  {chat_title}\n"
            f"🆔 <b>ID</b>     ➜  <code>{member.id}</code>\n"
            f"👤 <b>USER</b>   ➜  {username}\n"
            f"📝 <b>NAME</b>   ➜  {full_name}\n\n"
            f"╭━━━━━━━ ✦ <b>RULES</b> ✦ ━━━━━━━╮\n"
            f"│ 🌷 No Abuse — Respect everyone\n"
            f"│ 🕊️ No Fight — Keep it calm\n"
            f"│ 🔞 No 18+ Content\n"
            f"│ 🚫 No Spam / Promotions\n"
            f"│ 💌 DM only with permission\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"💫 <b>Stay calm • Stay respectful • Enjoy the vibes</b> 💫\n"
            f"🌙 <i>Have fun and make some good memories!</i>"
        )

        try:
            image_path = Path(WELCOME_IMAGE_PATH)
            if image_path.is_file():
                with image_path.open("rb") as image_file:
                    await context.bot.send_photo(
                        chat_id=chat.id,
                        photo=InputFile(image_file, filename=image_path.name),
                        caption=welcome_text,
                        parse_mode="HTML"
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=welcome_text,
                    parse_mode="HTML"
                )
                print(f"⚠️ Welcome image not found: {image_path}")
        except Exception as e:
            print(f"⚠️ Welcome error: {e}")


async def welcome_toggle_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Is command ko group mein use karo.")
        return
    key = f"welcome:{update.effective_chat.id}"
    new = "0" if get_setting(key, "1") == "1" else "1"
    set_setting(key, new)
    await update.message.reply_text(f"👋 Welcome system: {'ON 🟢' if new == '1' else 'OFF 🔴'}")


# ==================================
# SMART AUTO-MOD
# ==================================

BAD_WORDS = {
    "free nitro scam", "click this link scam", "crypto giveaway scam"
}
flood_cache = {}


async def automod_message(update, context):
    message = update.message
    if not message or not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    user = update.effective_user
    if not user or user.is_bot or user.id == OWNER_ID:
        return

    enabled, max_warnings, flood_limit, flood_window = automod_config(update.effective_chat.id)
    if not enabled:
        return

    text = (message.text or message.caption or "").lower()
    suspicious = any(word in text for word in BAD_WORDS)

    now = time.monotonic()
    key = (update.effective_chat.id, user.id)
    times = [t for t in flood_cache.get(key, []) if now - t <= flood_window]
    times.append(now)
    flood_cache[key] = times

    flood = len(times) >= flood_limit
    if not suspicious and not flood:
        return

    reason = "suspicious text" if suspicious else "flooding"
    try:
        await message.delete()
    except Exception:
        pass

    count = increment_warning(user.id)
    try:
        await message.chat.send_message(
            f"⚠️ {user.mention_html()} warning {count}/{max_warnings}\n"
            f"Reason: {reason}",
            parse_mode="HTML"
        )
    except Exception:
        pass

    if count >= max_warnings:
        try:
            from telegram import ChatPermissions
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            await message.chat.send_message(
                f"🔇 {user.mention_html()} has been muted after {count} warnings.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"⚠️ Auto-mute error: {e}")


async def automod_toggle_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Is command ko group mein use karo.")
        return
    current = automod_config(chat.id)
    set_automod_config(chat.id, enabled=not current[0])
    await update.message.reply_text(
        f"🛡️ Auto-Mod: {'ON 🟢' if not current[0] else 'OFF 🔴'}"
    )


# ==================================
# INLINE SEARCH
# ==================================

async def inline_search(update, context):
    query = (update.inline_query.query or "").strip()
    if not query:
        await update.inline_query.answer([], cache_time=5, is_personal=True)
        return

    data, error = await asyncio.to_thread(
        tmdb_request, "/search/multi", {"query": query, "include_adult": "false"}
    )
    results = []
    if data:
        from telegram import InlineQueryResultArticle, InputTextMessageContent
        from uuid import uuid4
        for item in data.get("results", [])[:10]:
            media_type = item.get("media_type")
            if media_type not in ("movie", "tv"):
                continue
            title = item.get("title") or item.get("name") or "Unknown"
            desc = (item.get("overview") or "No description")[:180]
            text = format_movie_result(item, media_type)
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=title,
                    description=desc,
                    input_message_content=InputTextMessageContent(text),
                    reply_markup=movie_search_keyboard(title) if media_type == "movie" else series_search_keyboard(title)
                )
            )

    await update.inline_query.answer(results, cache_time=30, is_personal=False)


# ==================================
# ADVANCED ADMIN STATS
# ==================================

async def admin_advanced_stats(update, context):
    if not owner_only(update):
        return
    with db_connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        activity_total = conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
        movie_total = conn.execute("SELECT COUNT(*) FROM activity WHERE event='movie'").fetchone()[0]
        series_total = conn.execute("SELECT COUNT(*) FROM activity WHERE event='series'").fetchone()[0]
        groups = conn.execute("SELECT COUNT(*) FROM group_chats").fetchone()[0]
        refs = conn.execute("SELECT COALESCE(SUM(count),0) FROM referral_counts").fetchone()[0]
        warnings_total = conn.execute("SELECT COALESCE(SUM(count),0) FROM warnings").fetchone()[0]

    top = top_referrers(5)
    top_text = "\n".join([f"• {uid}: {count}" for uid, count in top]) or "No referrals yet."
    await update.message.reply_text(
        f"📊 𝐀𝐃𝐕𝐀𝐍𝐂𝐄𝐃 𝐀𝐃𝐌𝐈𝐍 𝐒𝐓𝐀𝐓𝐒\n\n"
        f"👥 Users: {total}\n"
        f"⚡ Activity events: {activity_total}\n"
        f"🎬 Movies: {movie_total}\n"
        f"📺 Series: {series_total}\n"
        f"👨‍👩‍👧 Groups: {groups}\n"
        f"🎁 Referrals: {refs}\n"
        f"⚠️ Warnings: {warnings_total}\n\n"
        f"🏆 Top referrers:\n{top_text}"
    )


# ==================================
# FUN COMMANDS
# ==================================

async def love(update, context):

    percentage = random.randint(1, 100)

    await update.message.reply_text(
        f"❤️ Your Love Percentage: {percentage}%"
    )


async def dice(update, context):

    number = random.randint(1, 6)

    await update.message.reply_text(
        f"🎲 You rolled: {number}"
    )


async def quote(update, context):

    await update.message.reply_text(
        f"💭 {random.choice(QUOTES)}"
    )


# ==================================
# STATS
# ==================================

async def stats(update, context):

    await update.message.reply_text(
        f"""📊 𝐁𝐎𝐓 𝐒𝐓𝐀𝐓𝐒

👥 Current session users: {len(users)}
🤖 Status: ONLINE ✅"""
    )


# ==================================
# DM OWNER
# ==================================

async def dm(update, context):

    save_user(update.effective_user.id)

    if context.args:

        message = " ".join(context.args)

        await send_to_owner(
            update,
            context,
            message
        )

        return

    context.user_data["dm_mode"] = True

    await update.message.reply_text(
        """💌 𝐃𝐌 𝐌𝐎𝐃𝐄 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃

✍️ Ab अपना message type karke bhejo.

❌ Cancel ke liye /cancel."""
    )


async def receive_dm(update, context):

    if not context.user_data.get("dm_mode"):
        return

    message = update.message.text

    await send_to_owner(
        update,
        context,
        message
    )

    context.user_data["dm_mode"] = False


async def send_to_owner(
    update,
    context,
    message
):

    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else "No Username"
    )

    owner_message = f"""💌 𝐍𝐄𝐖 𝐌𝐄𝐒𝐒𝐀𝐆𝐄

👤 Name: {user.full_name}
🆔 ID: {user.id}
🔗 Username: {username}

━━━━━━━━━━━━━━

💬 Message:

{message}

━━━━━━━━━━━━━━
"""

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=owner_message
    )

    await update.message.reply_text(
        """✅ 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐒𝐄𝐍𝐓!

👑 Owner ko tumhara message mil gaya ❤️"""
    )


async def cancel(update, context):

    context.user_data["dm_mode"] = False
    context.user_data.pop("admin_input", None)

    await update.message.reply_text(
        "❌ DM mode cancelled."
    )


# ==================================
# GROUP AUTO PROMOTION
# ==================================

async def send_auto_promo(context: ContextTypes.DEFAULT_TYPE):
    global AUTO_PROMO_CHAT_ID

    if get_setting("promo_enabled", "1") != "1" or not get_setting("promo_chat_id", ""):
        return

    try:
        await context.bot.send_message(
            chat_id=int(get_setting("promo_chat_id", "0")),
            text=get_promo_text(),
            reply_markup=promo_keyboard()
        )
    except Exception as e:
        print(f"⚠️ Auto promo error: {e}")


async def set_promo_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_PROMO_CHAT_ID, AUTO_PROMO_ENABLED

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "⚠️ Is command ko apne target group ke andar use karo."
        )
        return

    AUTO_PROMO_CHAT_ID = update.effective_chat.id
    AUTO_PROMO_ENABLED = True
    set_setting("promo_chat_id", update.effective_chat.id)
    set_setting("promo_enabled", "1")

    await update.message.reply_text(
        "✅ Auto-promo group set ho gaya!\n\n"
        "📢 Auto-promo configured interval par JOIN MY CHANNELS message bhejega."
    )


async def promo_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_PROMO_ENABLED

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return

    AUTO_PROMO_ENABLED = True
    set_setting("promo_enabled", "1")
    await update.message.reply_text("✅ Auto-promo ON hai.")


async def promo_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_PROMO_ENABLED

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return

    AUTO_PROMO_ENABLED = False
    set_setting("promo_enabled", "0")
    await update.message.reply_text("🛑 Auto-promo OFF kar diya gaya hai.")


async def auto_promo_loop(app):
    """Send the promo message at the configured interval."""
    while True:
        try:
            await asyncio.sleep(max(30, int(get_setting("promo_interval", str(AUTO_PROMO_INTERVAL)))))
            await send_auto_promo_from_app(app)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️ Auto promo loop error: {e}")


async def send_auto_promo_from_app(app):
    global AUTO_PROMO_CHAT_ID

    if get_setting("promo_enabled", "1") != "1" or not get_setting("promo_chat_id", ""):
        return

    try:
        await app.bot.send_message(
            chat_id=int(get_setting("promo_chat_id", "0")),
            text=get_promo_text(),
            reply_markup=promo_keyboard()
        )
        print("📢 Auto promo message sent.")
    except Exception as e:
        print(f"⚠️ Auto promo send error: {e}")


# ==================================
# FLASK SERVER FOR RENDER
# ==================================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "SAKSHAM VIBES BOT IS RUNNING! 🤖"


@web_app.route("/health")
def health():
    return "OK"


def run_web_server():

    port = int(
        os.environ.get("PORT", 10000)
    )

    web_app.run(
        host="0.0.0.0",
        port=port
    )


# ==================================
# MAIN
# ==================================

async def run_bot():

    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("id", user_id))
    app.add_handler(CommandHandler("movie", movie_command))
    app.add_handler(CommandHandler("series", series_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("myref", myref_command))
    app.add_handler(CommandHandler("advstats", advanced_stats_command))

    app.add_handler(CommandHandler("dm", dm))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(CommandHandler("love", love))
    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("quote", quote))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("registergroup", register_group))
    app.add_handler(CommandHandler("mod", mod_command))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))

    # Group auto-promotion controls
    app.add_handler(CommandHandler("setpromo", set_promo_group))
    app.add_handler(CommandHandler("autopromo_on", promo_on))
    app.add_handler(CommandHandler("autopromo_off", promo_off))
    app.add_handler(CommandHandler("welcome", welcome_toggle_command))
    app.add_handler(CommandHandler("automod", automod_toggle_command))

    # Start automatic group promotion without requiring
    # python-telegram-bot's optional JobQueue dependency.
    promo_task = asyncio.create_task(auto_promo_loop(app))

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(InlineQueryHandler(inline_search))

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_new_members
        ),
        group=-3
    )

    app.add_handler(
        MessageHandler(
            filters.ALL,
            track_group_activity
        ),
        group=-2
    )

    app.add_handler(
        MessageHandler(
            filters.ALL,
            automod_message
        ),
        group=-1
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_input
        ),
        group=0
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_dm
        ),
        group=1
    )

    print("🤖 SAKSHAM VIBES BOT IS RUNNING...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Event().wait()

    finally:
        promo_task.cancel()
        try:
            await promo_task
        except asyncio.CancelledError:
            pass

        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

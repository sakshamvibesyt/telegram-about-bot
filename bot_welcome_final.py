import os
import random
import asyncio
import threading
import sqlite3
from datetime import datetime

from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)


# ==================================
# CONFIG
# ==================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])

# Apne links yahan change karna
CHANNEL_URL = "https://t.me/+6g3B5n2xi2xmNDhl"
YOUTUBE_URL = "https://yt.openinapp.co/wwoez"
INSTAGRAM_URL = "https://insta.openinapp.co/xqhfr"

# Persistent local SQLite storage
DB_FILE = os.environ.get("BOT_DB_FILE", "bot_data.db")


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
        [InlineKeyboardButton("🔄 AUTO FORWARD", callback_data="admin_forward")],
        [InlineKeyboardButton("🛡️ MODERATION", callback_data="admin_mod")],
        [InlineKeyboardButton("⚙️ SETTINGS", callback_data="admin_settings")],
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


def forward_admin_menu():
    enabled = get_setting("forward_enabled", "1") == "1"
    status = "ON 🟢" if enabled else "OFF 🔴"
    source = get_setting("forward_source", "") or "NOT SET"
    dests = load_forward_destinations()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏸️ TURN OFF" if enabled else "▶️ TURN ON", callback_data="forward_toggle")],
        [InlineKeyboardButton("📍 SET SOURCE", callback_data="forward_source_help")],
        [InlineKeyboardButton("➕ ADD DESTINATION", callback_data="forward_dest_help")],
        [InlineKeyboardButton("📋 DESTINATIONS", callback_data="forward_list")],
        [InlineKeyboardButton("🗑️ REMOVE DESTINATION", callback_data="forward_remove")],
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
# AUTO FORWARD COMMANDS
# ==================================

async def set_forward_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update):
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ Is command ko source group/channel ke andar use karo.")
        return
    set_setting("forward_source", update.effective_chat.id)
    await update.message.reply_text(
        f"✅ Auto-forward source set.\n\n📍 Chat ID: {update.effective_chat.id}\n🔄 Ab is chat ke naye messages configured destinations par forward honge."
    )


async def add_forward_destination_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update):
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ Is command ko destination group/channel ke andar use karo.")
        return
    source = int(get_setting("forward_source", "0") or 0)
    if update.effective_chat.id == source:
        await update.message.reply_text("⚠️ Source chat ko destination banane ki zarurat nahi hai.")
        return
    add_forward_destination(update.effective_chat.id, update.effective_chat.title or str(update.effective_chat.id))
    await update.message.reply_text("✅ Ye chat auto-forward destination list mein add ho gayi.")


async def remove_forward_destination_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update):
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ Is command ko destination group/channel ke andar use karo.")
        return
    remove_forward_destination(update.effective_chat.id)
    await update.message.reply_text("✅ Ye chat destination list se remove ho gayi.")


async def list_forward_destinations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    source = get_setting("forward_source", "") or "NOT SET"
    rows = load_forward_destinations()
    lines = [f"🔄 SOURCE: {source}", "", "📋 DESTINATIONS:"]
    if rows:
        lines += [f"• {title} — {chat_id}" for chat_id, title in rows]
    else:
        lines.append("• None")
    await update.message.reply_text("\n".join(lines))


async def auto_forward_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_setting("forward_enabled", "1") != "1":
        return
    source = int(get_setting("forward_source", "0") or 0)
    if not source or not update.effective_chat or update.effective_chat.id != source:
        return
    message = update.effective_message
    if not message or message.message_id is None:
        return
    # Do not forward bot commands from the source chat.
    if message.text and message.text.startswith("/"):
        return
    destinations = load_forward_destinations()
    for chat_id, _title in destinations:
        if int(chat_id) == source:
            continue
        try:
            await context.bot.forward_message(
                chat_id=int(chat_id),
                from_chat_id=source,
                message_id=message.message_id,
            )
        except Exception as e:
            # Protected/deleted/inaccessible messages or missing permissions
            # should not crash the bot or stop forwarding to other destinations.
            print(f"⚠️ Auto-forward failed for {chat_id}: {e}")


# ==================================
# GROUP AUTO PROMOTION
# ==================================

AUTO_PROMO_INTERVAL = 60 * 60  # 10 minutes
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
        conn.execute("CREATE TABLE IF NOT EXISTS forward_destinations (chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '')")
        defaults = {
            "promo_chat_id": "",
            "promo_enabled": "1",
            "promo_interval": str(AUTO_PROMO_INTERVAL),
            "promo_text": PROMO_TEXT,
            "forward_source": "",
            "forward_enabled": "1",
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
                ("🤖 YOUTUBE SUPPORT", "https://t.me/Sakshamythelp_bot"),
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
# AUTO FORWARD STORAGE
# ==================================

def load_forward_destinations():
    with db_connect() as conn:
        return conn.execute("SELECT chat_id,title FROM forward_destinations ORDER BY chat_id").fetchall()


def add_forward_destination(chat_id, title=""):
    with db_connect() as conn:
        conn.execute("INSERT OR REPLACE INTO forward_destinations(chat_id,title) VALUES(?,?)", (int(chat_id), title or str(chat_id)))


def remove_forward_destination(chat_id):
    with db_connect() as conn:
        conn.execute("DELETE FROM forward_destinations WHERE chat_id=?", (int(chat_id),))


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


# ==================================
# START
# ==================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)

    text = f"""✨ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 {user.first_name}! ✨

🤖 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 𝐁𝐎𝐓

👑 Your personal vibe destination.

👇 Choose an option below and explore the bot!

❤️ 𝐓𝐇𝐀𝐍𝐊𝐒 𝐅𝐎𝐑 𝐒𝐓𝐀𝐑𝐓𝐈𝐍𝐆 𝐌𝐘 𝐁𝐎𝐓 ❤️"""

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


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

    elif query.data == "admin_forward":
        if not owner_only(update): return
        enabled = "ON 🟢" if get_setting("forward_enabled", "1") == "1" else "OFF 🔴"
        source = get_setting("forward_source", "") or "NOT SET"
        dests = len(load_forward_destinations())
        await query.edit_message_text(
            f"🔄 AUTO FORWARD\n\nStatus: {enabled}\n📍 Source: {source}\n📤 Destinations: {dests}",
            reply_markup=forward_admin_menu()
        )

    elif query.data == "forward_toggle":
        if not owner_only(update): return
        new = "0" if get_setting("forward_enabled", "1") == "1" else "1"
        set_setting("forward_enabled", new)
        await query.edit_message_text(
            f"🔄 AUTO FORWARD\n\nStatus: {'ON 🟢' if new == '1' else 'OFF 🔴'}\n📍 Source: {get_setting('forward_source','') or 'NOT SET'}\n📤 Destinations: {len(load_forward_destinations())}",
            reply_markup=forward_admin_menu()
        )

    elif query.data == "forward_source_help":
        if not owner_only(update): return
        await query.edit_message_text(
            "📍 SET SOURCE\n\nSource group/channel ke andar /setforwardsource command bhejo.\n\n⚠️ Bot ko source chat mein messages dekhne ki permission honi chahiye.",
            reply_markup=admin_back()
        )

    elif query.data == "forward_dest_help":
        if not owner_only(update): return
        await query.edit_message_text(
            "➕ ADD DESTINATION\n\nHar destination group/channel ke andar /addforward command ek baar bhejo.\n\nBot ko destination mein message send permission/admin rights chahiye.",
            reply_markup=admin_back()
        )

    elif query.data == "forward_list":
        if not owner_only(update): return
        source = get_setting("forward_source", "") or "NOT SET"
        rows = load_forward_destinations()
        lines = [f"📍 SOURCE: {source}", "", "📤 DESTINATIONS:"]
        lines += ([f"• {title} — {chat_id}" for chat_id, title in rows] if rows else ["• None"])
        await query.edit_message_text("\n".join(lines), reply_markup=forward_admin_menu())

    elif query.data == "forward_remove":
        if not owner_only(update): return
        rows = [[InlineKeyboardButton(f"🗑️ {title[:30]}", callback_data=f"forward_del:{chat_id}")] for chat_id, title in load_forward_destinations()]
        rows.append([InlineKeyboardButton("🔙 AUTO FORWARD", callback_data="admin_forward")])
        await query.edit_message_text("🗑️ Choose destination to remove:", reply_markup=InlineKeyboardMarkup(rows))

    elif query.data.startswith("forward_del:"):
        if not owner_only(update): return
        chat_id = int(query.data.split(":", 1)[1])
        remove_forward_destination(chat_id)
        await query.edit_message_text("✅ Destination removed.", reply_markup=forward_admin_menu())

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

👥 Users in current bot session:
{len(users)}

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
/setforwardsource — Set forwarding source
/addforward — Add forwarding destination
/removeforward — Remove forwarding destination
/listforward — Show forwarding setup

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
/admin — Owner Admin Panel
/mod — Moderation Panel
/setpromo — Set this group for auto-promo
/autopromo_on — Auto-promo ON
/autopromo_off — Auto-promo OFF
/setforwardsource — Set source group/channel
/addforward — Add current group/channel as destination
/removeforward — Remove current destination
/listforward — Show forwarding setup"""
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
        "📢 Ab configured interval par JOIN MY CHANNELS message bheja jayega."
    )


async def promo_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_PROMO_ENABLED

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return

    AUTO_PROMO_ENABLED = True
    await update.message.reply_text("✅ Auto-promo ON hai.")


async def promo_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_PROMO_ENABLED

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner ye command use kar sakta hai.")
        return

    AUTO_PROMO_ENABLED = False
    await update.message.reply_text("🛑 Auto-promo OFF kar diya gaya hai.")


async def auto_promo_loop(app):
    """Send the promo message every 10 minutes."""
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


# ==================================
# AUTOMATIC NEW-MEMBER WELCOME
# ==================================

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.new_chat_members:
        return

    for member in message.new_chat_members:
        # Show the member's Telegram first name (no @mention).
        name = member.first_name or member.full_name or "Friend"

        welcome = f"""╭━━━━━━━━━━━━━━━━━━━━━━╮
  ًَُْ𝅯𝅯۪ؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒؒ
          🦋 𝑾𝑬𝑳𝑪𝑶𝑴𝑬 🦋
╰━━━━━━━━━━━━━━━━━━━━━━╯

✨ 𝑯𝒆𝒚, {name}! 👋

💀 𝑾𝒉𝒐𝒍𝒆 𝑯𝒂𝒄𝒌𝒆𝒓 𝑻𝒆𝒂𝒎 𝒌𝒊 𝒕𝒂𝒓𝒂𝒇 𝒔𝒆
🔥 𝑴𝑶𝑺𝑻 𝑾𝑬𝑳𝑪𝑶𝑴𝑬 𝑻𝑶 𝑻𝑯𝑬 𝑮𝑹𝑶𝑼𝑷! 🖤

💫 𝑾𝒆'𝒓𝒆 𝒈𝒍𝒂𝒅 𝒕𝒐 𝒉𝒂𝒗𝒆 𝒚𝒐𝒖 𝒉𝒆𝒓𝒆! ❤️

📌 𝑺𝒕𝒂𝒚 𝑨𝒄𝒕𝒊𝒗𝒆
🤝 𝑹𝒆𝒔𝒑𝒆𝒄𝒕 𝑬𝒗𝒆𝒓𝒚𝒐𝒏𝒆
🚫 𝑵𝒐 𝑺𝒑𝒂𝒎
✨ 𝑬𝒏𝒋𝒐𝒚 & 𝑺𝒕𝒂𝒚 𝑪𝒐𝒐𝒍 😎

╭━━━━━━━━━━━━━━━━━━━━━━╮
   👑 𝑶𝒘𝒏𝒆𝒓 : @sakshamvibesyt
╰━━━━━━━━━━━━━━━━━━━━━━╯"""

        try:
            await message.reply_text(welcome)
        except Exception as e:
            print(f"⚠️ Welcome message failed: {e}")


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

    app.add_handler(CommandHandler("dm", dm))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(CommandHandler("love", love))
    app.add_handler(CommandHandler("dice", dice))
    app.add_handler(CommandHandler("quote", quote))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("mod", mod_command))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))

    app.add_handler(CommandHandler("setforwardsource", set_forward_source))
    app.add_handler(CommandHandler("addforward", add_forward_destination_command))
    app.add_handler(CommandHandler("removeforward", remove_forward_destination_command))
    app.add_handler(CommandHandler("listforward", list_forward_destinations_command))

    # Group auto-promotion controls
    app.add_handler(CommandHandler("setpromo", set_promo_group))
    app.add_handler(CommandHandler("autopromo_on", promo_on))
    app.add_handler(CommandHandler("autopromo_off", promo_off))

    # Start automatic group promotion without requiring
    # python-telegram-bot's optional JobQueue dependency.
    promo_task = asyncio.create_task(auto_promo_loop(app))

    # Automatic welcome for every new member in groups/channels.
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_new_members
        ),
        group=-2
    )

    # Watch messages/updates from the configured source for auto-forwarding.
    app.add_handler(TypeHandler(Update, auto_forward_update), group=-1)

    app.add_handler(
        CallbackQueryHandler(button_handler)
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

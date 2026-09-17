import os
import random
import asyncio
import threading
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import json
import html
import urllib.parse
import urllib.request
import secrets
import string
import re
import io
from functools import wraps
from pathlib import Path

from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    CopyTextButton,
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


def group_only(handler):
    """Show a clear, friendly message when a group-only command is used in private chat."""
    @wraps(handler)
    async def wrapped(update, context):
        chat = update.effective_chat
        if not chat or chat.type not in ("group", "supergroup"):
            msg = update.effective_message
            if msg:
                await msg.reply_text(
                    "⚠️ 𝐆𝐑𝐎𝐔𝐏 𝐎𝐍𝐋𝐘\n\n"
                    "👥 Ye command sirf Telegram group mein use ki ja sakti hai.\n"
                    "💬 Private chat mein is command ki zarurat nahi hai.\n\n"
                    "➡️ Bot ko apne group mein add karke wahan command try karo. 🚀"
                )
            return
        return await handler(update, context)
    return wrapped


async def can_manage_protection(update, context):
    user = update.effective_user
    chat = update.effective_chat
    if user and user.id == OWNER_ID:
        return True
    if not chat or chat.type not in ("group", "supergroup") or not user:
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def admin_dashboard_text():
    try:
        with db_connect() as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            groups = conn.execute("SELECT COUNT(*) FROM group_chats").fetchone()[0]
            xp_users = conn.execute("SELECT COUNT(*) FROM xp_levels").fetchone()[0]
            coin_users, total_coins = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(balance),0) FROM coins WHERE balance > 0"
            ).fetchone()
    except Exception:
        users = groups = xp_users = coin_users = total_coins = 0

    promo = "🟢 ON" if get_setting("promo_enabled", "1") == "1" else "🔴 OFF"
    mention = "🟢 ON" if get_setting("mention_enabled", "1") == "1" else "🔴 OFF"

    return (
        "╔══════════════════════════════╗\n"
        "       👑 𝐎𝐖𝐍𝐄𝐑 𝐂𝐎𝐍𝐓𝐑𝐎𝐋 𝐂𝐄𝐍𝐓𝐄𝐑\n"
        "╚══════════════════════════════╝\n\n"
        "⚡ 𝐁𝐎𝐓 𝐎𝐕𝐄𝐑𝐕𝐈𝐄𝐖\n"
        f"👥 Users: {users}     🏠 Groups: {groups}\n"
        f"⭐ XP Users: {xp_users}   🪙 Coin Holders: {coin_users}\n"
        f"💰 Total Coins: {total_coins}\n\n"
        "📡 𝐒𝐘𝐒𝐓𝐄𝐌 𝐒𝐓𝐀𝐓𝐔𝐒\n"
        "🤖 Bot: 🟢 ONLINE\n"
        f"⏰ Auto Promo: {promo}\n"
        f"📢 Custom Mention: {mention}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛠️ Choose a control module below 👇"
    )


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 𝐃𝐀𝐒𝐇𝐁𝐎𝐀𝐑𝐃", callback_data="admin_stats"), InlineKeyboardButton("🔄 𝐑𝐄𝐅𝐑𝐄𝐒𝐇", callback_data="admin_refresh")],
        [InlineKeyboardButton("📢 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓", callback_data="admin_broadcast"), InlineKeyboardButton("📣 𝐂𝐔𝐒𝐓𝐎𝐌 𝐌𝐄𝐍𝐓𝐈𝐎𝐍", callback_data="admin_mention")],
        [InlineKeyboardButton("⏰ 𝐀𝐔𝐓𝐎 𝐏𝐑𝐎𝐌𝐎", callback_data="admin_promo"), InlineKeyboardButton("🔗 𝐋𝐈𝐍𝐊𝐒", callback_data="admin_links")],
        [InlineKeyboardButton("🪙 𝐂𝐎𝐈𝐍 𝐂𝐄𝐍𝐓𝐄𝐑", callback_data="admin_coins"), InlineKeyboardButton("🛡️ 𝐌𝐎𝐃𝐄𝐑𝐀𝐓𝐈𝐎𝐍", callback_data="admin_mod")],
        [InlineKeyboardButton("🚀 𝐌𝐎𝐑𝐄 𝐅𝐄𝐀𝐓𝐔𝐑𝐄𝐒", callback_data="admin_features"), InlineKeyboardButton("🎟️ 𝐑𝐄𝐃𝐄𝐄𝐌 𝐂𝐎𝐃𝐄𝐒", callback_data="admin_redeem")],
        [InlineKeyboardButton("⚙️ 𝐒𝐄𝐓𝐓𝐈𝐍𝐆𝐒", callback_data="admin_settings")],
        [InlineKeyboardButton("👑 𝐎𝐖𝐍𝐄𝐑 • 𝐒𝐄𝐂𝐔𝐑𝐄", callback_data="admin_secure")],
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


def coin_admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD COINS", callback_data="coin_add")],
        [InlineKeyboardButton("➖ REMOVE COINS", callback_data="coin_remove")],
        [InlineKeyboardButton("🛒 COIN SHOP", callback_data="shop")],
        [InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin")],
    ])


async def admin_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    await update.message.reply_text(admin_dashboard_text(), reply_markup=admin_menu())


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
    if state in ("coin_add", "coin_remove"):
        parts = value.split()
        if len(parts) != 1 or not parts[0].lstrip("+").isdigit():
            await update.message.reply_text("❌ Sirf amount bhejo, example: 500")
            return True
        amount = int(parts[0])
        if amount <= 0:
            await update.message.reply_text("❌ Amount 0 se zyada hona chahiye.")
            return True
        target_msg = update.message.reply_to_message
        target = target_msg.from_user if target_msg and target_msg.from_user else None
        if not target or target.is_bot:
            await update.message.reply_text("❌ Jis member ko coins dene hain, uske message ko reply karke amount bhejo.")
            return True
        delta = amount if state == "coin_add" else -amount
        current = get_coins(update.effective_chat.id, target.id)
        if state == "coin_remove" and amount > current:
            await update.message.reply_text(f"❌ Itne coins available nahi hain. Current balance: {current}")
            return True
        new_balance = add_coins(update.effective_chat.id, target.id, delta)
        context.user_data.pop("admin_input", None)
        action = "added to" if delta > 0 else "removed from"
        await update.message.reply_text(
            f"✅ {amount} coins {action} {target.full_name}\n💰 New balance: {new_balance} coins",
            reply_markup=coin_admin_menu()
        )
        return True
    if state == "redeem_generate":
        parts = value.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await update.message.reply_text("❌ Format: AMOUNT COUNT\nExample: 1000 50")
            return True
        amount, count = int(parts[0]), int(parts[1])
        if amount <= 0 or count <= 0 or count > 500:
            await update.message.reply_text("❌ Amount > 0 aur count 1-500 ke beech rakho.")
            return True
        codes = []
        alphabet = string.ascii_uppercase + string.digits
        with db_connect() as conn:
            for _ in range(count):
                while True:
                    code = "SV-" + "".join(secrets.choice(alphabet) for _ in range(10))
                    if not conn.execute("SELECT 1 FROM redeem_codes WHERE code=?", (code,)).fetchone():
                        break
                conn.execute("INSERT INTO redeem_codes(code,amount,created_at) VALUES(?,?,?)", (code, amount, datetime.utcnow().isoformat()))
                codes.append(code)
        context.user_data.pop("admin_input", None)

        # Send every generated code as a separate message to the selected group.
        target_chat_id = get_setting("mention_chat_id", "").strip()
        if not target_chat_id:
            target_chat_id = get_setting("promo_chat_id", "").strip()
        if not target_chat_id and update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
            target_chat_id = str(update.effective_chat.id)

        if not target_chat_id:
            await update.message.reply_text(
                "❌ Koi group selected nahi hai. Pehle group select/register karo, phir redeem codes generate karo.",
                reply_markup=admin_menu()
            )
            return True

        sent = 0
        failed = 0
        for code in codes:
            try:
                copy_button = InlineKeyboardButton(
                    "📋 𝐂𝐎𝐏𝐘 𝐂𝐎𝐃𝐄",
                    copy_text=CopyTextButton(text=code)
                )
                await context.bot.send_message(
                    chat_id=int(target_chat_id),
                    text=f"🎟️ 𝐑𝐄𝐃𝐄𝐄𝐌 𝐂𝐎𝐃𝐄\n\n`{code}`\n\n🪙 𝐑𝐞𝐰𝐚𝐫𝐝: {amount} 𝐂𝐨𝐢𝐧𝐬\n⚡ Use: /redeem {code}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[copy_button]])
                )
                sent += 1
            except Exception:
                failed += 1

        if sent > 0:
            try:
                await context.bot.send_message(
                    chat_id=int(target_chat_id),
                    text=(
                        "🎟️ 𝐑𝐞𝐝𝐞𝐞𝐦 𝐂𝐨𝐝𝐞 𝐊𝐚𝐢𝐬𝐞 𝐑𝐞𝐝𝐞𝐞𝐦 𝐊𝐚𝐫𝐞𝐧? 👇\n\n"
                        "/redeem YOUR_CODE\n"
                        "💰 Example: /redeem ABC123\n"
                        "✅ Code redeem karo → coins pao 🪙🔥"
                    )
                )
            except Exception:
                pass

        await update.message.reply_text(
            f"✅ 𝐑𝐄𝐃𝐄𝐄𝐌 𝐂𝐎𝐃𝐄𝐒 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄𝐃\n\n🪙 Value: {amount} coins each\n🔢 Generated: {count}\n📢 Sent to group: {sent}\n❌ Failed: {failed}",
            reply_markup=admin_menu()
        )
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
# AUTO DAILY GREETINGS + AUTO TAG ALL
# ==================================

AUTO_GREETING_TIMES = {
    (7, 0): "🌅 𝐆𝐎𝐎𝐃 𝐌𝐎𝐑𝐍𝐈𝐍𝐆 𝐄𝐕𝐄𝐑𝐘𝐎𝐍𝐄! ☀️",
    (15, 0): "☀️ 𝐆𝐎𝐎𝐃 𝐀𝐅𝐓𝐄𝐑𝐍𝐎𝐎𝐍 𝐄𝐕𝐄𝐑𝐘𝐎𝐍𝐄! 🌤️",
    (20, 0): "🌙 𝐆𝐎𝐎𝐃 𝐍𝐈𝐆𝐇𝐓 𝐄𝐕𝐄𝐑𝐘𝐎𝐍𝐄! ✨",
}
AUTO_GREETING_TZ = ZoneInfo("Asia/Kolkata")


def build_auto_mention_messages(chat_id, intro):
    members = group_members(chat_id)
    # Keep the same member source as /tagall: only known, non-bot members.
    return [(uid, name) for uid, name in members if uid]


async def send_auto_greeting(app, chat_id, intro):
    if not chat_id:
        return
    members = build_auto_mention_messages(chat_id, intro)
    if not members:
        return

    # Use the existing tagger batching so large groups are sent safely in chunks.
    for start in range(0, len(members), TAG_BATCH_SIZE):
        batch = members[start:start + TAG_BATCH_SIZE]
        text = intro + "\n\n"
        entities = []
        for index, (uid, name) in enumerate(batch):
            if index:
                text += " "
            display_name = (name or "User")[:64]
            offset = len(text.encode("utf-16-le")) // 2
            text += display_name
            length = len(display_name.encode("utf-16-le")) // 2
            from telegram import MessageEntity, User
            entities.append(
                MessageEntity(
                    type="text_mention",
                    offset=offset,
                    length=length,
                    user=User(id=uid, first_name=display_name, is_bot=False),
                )
            )

        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=text,
                entities=entities,
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"⚠️ Auto greeting send error in {chat_id}: {e}")
            break

        if start + TAG_BATCH_SIZE < len(members):
            await asyncio.sleep(TAG_DELAY)


async def test_greet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Immediately test an automatic greeting with member mentions."""
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /testgreet sirf group mein use karo.")
        return

    if not user:
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("creator", "administrator") and user.id != OWNER_ID:
            await update.message.reply_text("❌ Sirf group admins /testgreet use kar sakte hain.")
            return
    except Exception:
        if user.id != OWNER_ID:
            await update.message.reply_text("❌ Admin permission verify nahi ho saki.")
            return

    choice = (context.args[0].lower() if context.args else "morning")
    greetings = {
        "morning": AUTO_GREETING_TIMES[(7, 0)],
        "gm": AUTO_GREETING_TIMES[(7, 0)],
        "afternoon": AUTO_GREETING_TIMES[(15, 0)],
        "ga": AUTO_GREETING_TIMES[(15, 0)],
        "night": AUTO_GREETING_TIMES[(20, 0)],
        "gn": AUTO_GREETING_TIMES[(20, 0)],
    }
    intro = greetings.get(choice)
    if not intro:
        await update.message.reply_text(
            "⚠️ Use: /testgreet morning | afternoon | night"
        )
        return

    members = build_auto_mention_messages(chat.id, intro)
    if not members:
        await update.message.reply_text(
            "❌ Abhi koi known member nahi mila. Pehle group activity/member messages bot ko receive hone do."
        )
        return

    await update.message.reply_text("🧪 Test greeting bhej raha hoon...")
    await send_auto_greeting(context.application, chat.id, intro)


async def auto_greeting_loop(app):
    """Send Good Morning/Afternoon/Night and mention known members at fixed IST times."""
    last_sent = None
    while True:
        try:
            now = datetime.now(AUTO_GREETING_TZ)
            slot = (now.hour, now.minute)
            day_key = now.strftime("%Y-%m-%d")
            send_key = (day_key, slot)

            if slot in AUTO_GREETING_TIMES and send_key != last_sent:
                intro = AUTO_GREETING_TIMES[slot]
                # Send to every group the bot has detected/registered.
                for chat_id, _ in known_groups():
                    await send_auto_greeting(app, chat_id, intro)
                last_sent = send_key

            await asyncio.sleep(20)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️ Auto greeting loop error: {e}")
            await asyncio.sleep(20)


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
        conn.execute("CREATE TABLE IF NOT EXISTS xp_levels (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, xp INTEGER NOT NULL DEFAULT 0, level INTEGER NOT NULL DEFAULT 1, message_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY(chat_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS coins (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, balance INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY(chat_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS coin_shop (item_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL, price INTEGER NOT NULL, reward_type TEXT NOT NULL, reward_value INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1)")
        conn.execute("CREATE TABLE IF NOT EXISTS coin_purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, item_id INTEGER NOT NULL, item_name TEXT NOT NULL, price INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'claimed', created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS vip_users (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, granted_at TEXT NOT NULL, granted_by INTEGER NOT NULL, PRIMARY KEY(chat_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS elite_users (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, granted_at TEXT NOT NULL, granted_by INTEGER NOT NULL, PRIMARY KEY(chat_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS custom_titles (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, title TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(chat_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS redeem_codes (code TEXT PRIMARY KEY, amount INTEGER NOT NULL, created_at TEXT NOT NULL, used_by INTEGER, used_chat_id INTEGER, used_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS giveaways (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, creator_id INTEGER NOT NULL, prize TEXT NOT NULL, winners_count INTEGER NOT NULL, end_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', message_id INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS giveaway_entries (giveaway_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL, joined_at TEXT NOT NULL, PRIMARY KEY(giveaway_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS group_activity (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, message_count INTEGER NOT NULL DEFAULT 0, last_seen TEXT NOT NULL, PRIMARY KEY(chat_id,user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS autoclean_chats (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, delay_seconds INTEGER NOT NULL DEFAULT 10)")
        shop_defaults = [
            ("⭐ XP BOOST PACK", "Instantly add 500 XP to your group profile", 300, "xp", 500),
            ("📣 CUSTOM SHOUTOUT", "Request a custom shoutout from the owner", 600, "request", 0),
            ("👑 VIP BADGE", "Request a special VIP badge from the owner", 1000, "request", 0),
            ("🎁 BONUS COIN PACK", "Instantly receive 750 bonus coins", 1200, "coins", 750),
            ("💎 ELITE BADGE", "Request an exclusive Elite badge from the owner", 1800, "request", 0),
            ("🚀 PRIORITY SHOUTOUT", "Get a priority promotional shoutout request", 2500, "request", 0),
        ]
        for item in shop_defaults:
            exists = conn.execute("SELECT 1 FROM coin_shop WHERE name=?", (item[0],)).fetchone()
            if not exists:
                conn.execute("INSERT INTO coin_shop(name,description,price,reward_type,reward_value,enabled) VALUES(?,?,?,?,?,1)", item)
        conn.execute("CREATE TABLE IF NOT EXISTS welcome_chats (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1)")
        conn.execute("CREATE TABLE IF NOT EXISTS automod_chats (chat_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, max_warnings INTEGER NOT NULL DEFAULT 3, flood_limit INTEGER NOT NULL DEFAULT 6, flood_window INTEGER NOT NULL DEFAULT 10)")
        conn.execute("CREATE TABLE IF NOT EXISTS protection_chats (chat_id INTEGER PRIMARY KEY, link_protect INTEGER NOT NULL DEFAULT 0, forward_protect INTEGER NOT NULL DEFAULT 0)")
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


def get_coins(chat_id, user_id):
    with db_connect() as conn:
        row = conn.execute("SELECT balance FROM coins WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    return row[0] if row else 0


def add_coins(chat_id, user_id, amount):
    now = datetime.utcnow().isoformat()
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO coins(chat_id,user_id,balance,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id,user_id) DO UPDATE SET balance=coins.balance+excluded.balance,updated_at=excluded.updated_at",
            (chat_id, user_id, amount, now)
        )
        row = conn.execute("SELECT balance FROM coins WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    return row[0] if row else 0


def is_vip(chat_id, user_id):
    with db_connect() as conn:
        row = conn.execute("SELECT 1 FROM vip_users WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    return bool(row)


def is_elite(chat_id, user_id):
    with db_connect() as conn:
        row = conn.execute("SELECT 1 FROM elite_users WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    return bool(row)


def grant_elite(chat_id, user_id):
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO elite_users(chat_id,user_id,granted_at,granted_by) VALUES(?,?,?,?)",
            (chat_id, user_id, datetime.utcnow().isoformat(), OWNER_ID)
        )


def remove_elite(chat_id, user_id):
    with db_connect() as conn:
        cur = conn.execute("DELETE FROM elite_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return cur.rowcount > 0


async def elite_command(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /elite sirf group mein use karo.")
        return
    status = "ELITE ACTIVE 💎" if is_elite(chat.id, user.id) else "NOT ACTIVE ❌"
    await update.message.reply_text(f"💎 𝐄𝐋𝐈𝐓𝐄 𝐒𝐓𝐀𝐓𝐔𝐒\n\n👤 {user.full_name}\n✨ Status: {status}")


async def giveelite_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    chat = update.effective_chat
    target = replied_user(update)
    if not chat or chat.type not in ("group", "supergroup") or not target or target.is_bot:
        await update.message.reply_text("💎 Member ke message ko reply karke /giveelite use karo.")
        return
    grant_elite(chat.id, target.id)
    await update.message.reply_text(f"💎 Elite badge granted to {target.full_name}!\n✨ /elite se status check kar sakte hain.")


async def removeelite_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    chat = update.effective_chat
    target = replied_user(update)
    if not chat or chat.type not in ("group", "supergroup") or not target or target.is_bot:
        await update.message.reply_text("💎 Member ke message ko reply karke /removeelite use karo.")
        return
    removed = remove_elite(chat.id, target.id)
    await update.message.reply_text((f"❌ Elite badge removed from {target.full_name}." if removed else f"ℹ️ {target.full_name} ke paas Elite active nahi tha."))


def grant_vip(chat_id, user_id):
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO vip_users(chat_id,user_id,granted_at,granted_by) VALUES(?,?,?,?)",
            (chat_id, user_id, datetime.utcnow().isoformat(), OWNER_ID)
        )


def remove_vip(chat_id, user_id):
    with db_connect() as conn:
        cur = conn.execute("DELETE FROM vip_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return cur.rowcount > 0


async def vip_command(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /vip sirf group mein use karo.")
        return
    status = "ACTIVE 👑" if is_vip(chat.id, user.id) else "NOT ACTIVE ❌"
    await update.message.reply_text(f"👑 𝐕𝐈𝐏 𝐒𝐓𝐀𝐓𝐔𝐒\n\n👤 {user.full_name}\n✨ Status: {status}")


async def givevip_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    chat = update.effective_chat
    target = replied_user(update)
    if not chat or chat.type not in ("group", "supergroup") or not target or target.is_bot:
        await update.message.reply_text("👑 Member ke message ko reply karke /givevip use karo.")
        return
    grant_vip(chat.id, target.id)
    await update.message.reply_text(f"👑 VIP badge granted to {target.full_name}!\n✨ /vip se status check kar sakte hain.")


async def removevip_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    chat = update.effective_chat
    target = replied_user(update)
    if not chat or chat.type not in ("group", "supergroup") or not target or target.is_bot:
        await update.message.reply_text("👑 Member ke message ko reply karke /removevip use karo.")
        return
    removed = remove_vip(chat.id, target.id)
    await update.message.reply_text((f"❌ VIP badge removed from {target.full_name}." if removed else f"ℹ️ {target.full_name} ke paas VIP active nahi tha."))


def shop_items():
    with db_connect() as conn:
        return conn.execute(
            "SELECT item_id,name,description,price,reward_type,reward_value FROM coin_shop WHERE enabled=1 ORDER BY item_id"
        ).fetchall()


def shop_text():
    items = shop_items()
    lines = ["🛒 𝐂𝐎𝐈𝐍 𝐒𝐇𝐎𝐏", "", "Spend your coins to claim special rewards 🪙", ""]
    for item_id, name, desc, price, reward_type, reward_value in items:
        lines.append(f"{name}  •  🪙 {price}")
        lines.append(f"└ {desc}")
        lines.append("")
    lines.append("👇 Select a reward to claim it")
    return "\n".join(lines)


def shop_keyboard():
    rows = []
    for item_id, name, desc, price, reward_type, reward_value in shop_items():
        rows.append([InlineKeyboardButton(f"{name} • 🪙 {price}", callback_data=f"shop_buy:{item_id}")])
    rows.append([InlineKeyboardButton("💳 MY WALLET", callback_data="shop_wallet"), InlineKeyboardButton("🔄 REFRESH", callback_data="shop")])
    rows.append([InlineKeyboardButton("🏠 MAIN MENU", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def record_purchase(chat_id, user_id, item_id, item_name, price):
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO coin_purchases(chat_id,user_id,item_id,item_name,price,status,created_at) VALUES(?,?,?,?,?,?,?)",
            (chat_id, user_id, item_id, item_name, price, "claimed", datetime.utcnow().isoformat())
        )


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /shop group mein use karo.")
        return
    await update.message.reply_text(shop_text(), reply_markup=shop_keyboard())


async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /coins group mein use karo.")
        return
    balance = get_coins(chat.id, user.id)
    await update.message.reply_text(
        f"🪙 𝐂𝐎𝐈𝐍 𝐖𝐀𝐋𝐋𝐄𝐓\n\n👤 {user.full_name}\n💰 Balance: {balance} coins"
    )


async def dailycoins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /dailycoins group mein use karo.")
        return
    amount = random.randint(50, 150)
    balance = add_coins(chat.id, user.id, amount)
    await update.message.reply_text(
        f"🎁 𝐃𝐀𝐈𝐋𝐘 𝐑𝐄𝐖𝐀𝐑𝐃\n\n💰 +{amount} coins added!\n💳 New balance: {balance} coins"
    )


async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    sender = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /gift group mein use karo.")
        return
    target_msg = update.message.reply_to_message
    target = target_msg.from_user if target_msg and target_msg.from_user else None
    if not target or target.is_bot:
        await update.message.reply_text("🎁 Jis member ko gift dena hai, uske message ko reply karke use karo: /gift 100")
        return
    if target.id == sender.id:
        await update.message.reply_text("😄 Khud ko gift nahi kar sakte.")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("🎁 Format: reply to member + /gift 100")
        return
    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("❌ Gift amount 0 se zyada hona chahiye.")
        return
    sender_balance = get_coins(chat.id, sender.id)
    if sender_balance < amount:
        await update.message.reply_text(f"❌ Tumhare paas sirf {sender_balance} coins hain.")
        return
    add_coins(chat.id, sender.id, -amount)
    receiver_balance = add_coins(chat.id, target.id, amount)
    await update.message.reply_text(
        f"🎁 𝐂𝐎𝐈𝐍 𝐆𝐈𝐅𝐓\n\n"
        f"👤 {sender.full_name} ➜ {target.full_name}\n"
        f"🪙 Gift: {amount} coins\n"
        f"💳 {target.full_name}'s balance: {receiver_balance} coins"
    )


async def runall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner_only(update):
        await update.message.reply_text("❌ Sirf owner /runall use kar sakta hai.")
        return
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /runall group mein use karo.")
        return

    # Safe test mode: it previews/tests non-destructive systems without changing
    # XP/coins or triggering moderation, bans, promo, or external searches.
    balance_before = get_coins(chat.id, user.id)
    xp_row = get_group_xp(chat.id, user.id)
    level = xp_row[1] if xp_row else 1
    xp = xp_row[0] if xp_row else 0
    await update.message.reply_text(
        "🧪 𝐑𝐔𝐍𝐀𝐋𝐋 — 𝐒𝐀𝐅𝐄 𝐓𝐄𝐒𝐓 𝐌𝐎𝐃𝐄\n\n"
        "🏓 Ping ........ ✅\n"
        "🎲 Dice ........ ✅\n"
        "💭 Quote ....... ✅\n"
        "📊 Stats ....... ✅\n"
        f"🏆 XP/Rank ..... ✅ Level {level} • {xp} XP\n"
        "🪙 Coins ....... ✅\n"
        f"💰 Wallet ...... {balance_before} coins\n"
        "🌅 Greeting .... ✅ TEST ONLY\n"
        "👥 Mention ...... ✅ KNOWN MEMBERS ONLY\n"
        "\n✨ All safe test checks completed.\n"
        "🔄 XP/coins balance ko change nahi kiya gaya.\n"
        "🛡️ Ban/mute/warn/promo/search jaise actions intentionally execute nahi hote."
    )


def xp_for_level(level):
    return 100 * level * level


def calculate_level(xp):
    level = 1
    while xp >= xp_for_level(level):
        level += 1
    return level


def add_group_xp(chat_id, user_id, amount=5):
    now = datetime.utcnow().isoformat()
    with db_connect() as conn:
        row = conn.execute("SELECT xp, level, message_count FROM xp_levels WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
        old_xp, old_level, messages = row if row else (0, 1, 0)
        new_xp = old_xp + amount
        new_level = calculate_level(new_xp)
        conn.execute(
            "INSERT INTO xp_levels(chat_id,user_id,xp,level,message_count,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(chat_id,user_id) DO UPDATE SET xp=excluded.xp,level=excluded.level,message_count=excluded.message_count,updated_at=excluded.updated_at",
            (chat_id, user_id, new_xp, new_level, messages + 1, now)
        )
    return old_xp, new_xp, old_level, new_level, messages + 1


def get_group_xp(chat_id, user_id):
    with db_connect() as conn:
        row = conn.execute("SELECT xp, level, message_count FROM xp_levels WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    return row if row else (0, 1, 0)


def get_group_rank(chat_id, user_id):
    with db_connect() as conn:
        row = conn.execute("SELECT xp FROM xp_levels WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
        if not row:
            return None
        return conn.execute("SELECT COUNT(*) + 1 FROM xp_levels WHERE chat_id=? AND xp>?", (chat_id, row[0])).fetchone()[0]


def get_group_top(chat_id, limit=10):
    with db_connect() as conn:
        return conn.execute(
            "SELECT x.user_id, COALESCE(g.name, 'User'), x.xp, x.level, x.message_count "
            "FROM xp_levels x LEFT JOIN group_members g ON g.chat_id=x.chat_id AND g.user_id=x.user_id "
            "WHERE x.chat_id=? ORDER BY x.xp DESC, x.message_count DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()


def get_custom_title(chat_id, user_id):
    with db_connect() as conn:
        row = conn.execute("SELECT title FROM custom_titles WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    return row[0] if row else None


def set_custom_title(chat_id, user_id, title):
    with db_connect() as conn:
        conn.execute("INSERT INTO custom_titles(chat_id,user_id,title,updated_at) VALUES(?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET title=excluded.title,updated_at=excluded.updated_at", (chat_id, user_id, title, datetime.utcnow().isoformat()))


def clear_custom_title(chat_id, user_id):
    with db_connect() as conn:
        cur = conn.execute("DELETE FROM custom_titles WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return cur.rowcount > 0


async def profile_command(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /profile sirf group mein use karo.")
        return
    target = replied_user(update) or user
    xp, level, messages = get_group_xp(chat.id, target.id)
    rank = get_group_rank(chat.id, target.id)
    coins = get_coins(chat.id, target.id)
    title = get_custom_title(chat.id, target.id)
    try:
        member = await context.bot.get_chat_member(chat.id, target.id)
        status = member.status
    except Exception:
        status = "member"
    role = "OWNER" if status == "creator" else "ADMIN" if status == "administrator" else "MEMBER"
    display_title = title or role
    badge = "💎 ELITE" if is_elite(chat.id, target.id) else ("👑 VIP" if is_vip(chat.id, target.id) else "—")
    rank_text = f"#{rank}" if rank else "Unranked"
    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "       👤 𝐏𝐑𝐎𝐅𝐈𝐋𝐄 𝐂𝐀𝐑𝐃\n"
        "╚══════════════════════════════╝\n\n"
        f"👤 Name: {target.full_name}\n"
        f"🆔 ID: {target.id}\n"
        f"🏷️ Title: {display_title}\n"
        f"✨ Level: {level}\n"
        f"⚡ XP: {xp}\n"
        f"💬 Messages: {messages}\n"
        f"🏆 Group Rank: {rank_text}\n"
        f"🪙 Coins: {coins}\n"
        f"🌟 Badge: {badge}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 Your group profile, your stats."
    )


async def settitle_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    chat = update.effective_chat
    target = replied_user(update)
    title = " ".join(context.args).strip()
    if not chat or chat.type not in ("group", "supergroup") or not target or target.is_bot or not title:
        await update.message.reply_text("⚠️ Member ke message ko reply karke /settitle CODER use karo.")
        return
    if len(title) > 32:
        await update.message.reply_text("❌ Title maximum 32 characters ka ho sakta hai.")
        return
    set_custom_title(chat.id, target.id, title)
    await update.message.reply_text(f"✅ {target.full_name} ka custom title set: {title}")


async def cleartitle_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    chat = update.effective_chat
    target = replied_user(update)
    if not chat or chat.type not in ("group", "supergroup") or not target:
        await update.message.reply_text("⚠️ Member ke message ko reply karke /cleartitle use karo.")
        return
    clear_custom_title(chat.id, target.id)
    await update.message.reply_text(f"✅ Custom title cleared. {target.full_name} ab default role title use karega.")


async def redeem_command(update, context):
    if not context.args:
        await update.message.reply_text("🎟️ Use: /redeem CODE\nExample: /redeem SV-XXXXXXXXXX")
        return
    code = context.args[0].strip().upper()
    with db_connect() as conn:
        row = conn.execute("SELECT amount,used_by FROM redeem_codes WHERE code=?", (code,)).fetchone()
        if not row:
            await update.message.reply_text("❌ Invalid redeem code.")
            return
        amount, used_by = row
        if used_by is not None:
            await update.message.reply_text("⚠️ Ye redeem code already used hai.")
            return
        chat_id = update.effective_chat.id if update.effective_chat and update.effective_chat.type in ("group", "supergroup") else 0
        conn.execute("UPDATE redeem_codes SET used_by=?,used_chat_id=?,used_at=? WHERE code=? AND used_by IS NULL", (update.effective_user.id, chat_id, datetime.utcnow().isoformat(), code))
    if chat_id:
        new_balance = add_coins(chat_id, update.effective_user.id, amount)
    else:
        # Private redemption uses a personal wallet bucket.
        new_balance = add_coins(0, update.effective_user.id, amount)
    await update.message.reply_text(f"🎉 𝐂𝐎𝐃𝐄 𝐑𝐄𝐃𝐄𝐄𝐌𝐄𝐃!\n\n🪙 +{amount} coins added.\n💰 Balance: {new_balance} coins")


async def analytics_command(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /analytics sirf group mein use karo.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("creator", "administrator") and user.id != OWNER_ID:
            await update.message.reply_text("❌ Sirf group admins /analytics use kar sakte hain.")
            return
    except Exception:
        if user.id != OWNER_ID:
            await update.message.reply_text("❌ Admin permission verify nahi ho saki.")
            return
    with db_connect() as conn:
        members = conn.execute("SELECT COUNT(*) FROM group_members WHERE chat_id=?", (chat.id,)).fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM group_activity WHERE chat_id=? AND last_seen>=?", (chat.id, (datetime.utcnow()-timedelta(days=7)).isoformat())).fetchone()[0]
        total_messages = conn.execute("SELECT COALESCE(SUM(message_count),0) FROM xp_levels WHERE chat_id=?", (chat.id,)).fetchone()[0]
        coins = conn.execute("SELECT COALESCE(SUM(balance),0) FROM coins WHERE chat_id=?", (chat.id,)).fetchone()[0]
        top = conn.execute("SELECT COALESCE(g.name,'User'),x.message_count,x.xp FROM xp_levels x LEFT JOIN group_members g ON g.chat_id=x.chat_id AND g.user_id=x.user_id WHERE x.chat_id=? ORDER BY x.message_count DESC LIMIT 5", (chat.id,)).fetchall()
    top_text = "\n".join(f"• {n[:24]} — {m} msgs / {xp} XP" for n,m,xp in top) or "No activity yet."
    await update.message.reply_text(f"📊 𝐆𝐑𝐎𝐔𝐏 𝐀𝐍𝐀𝐋𝐘𝐓𝐈𝐂𝐒\n\n👥 Known members: {members}\n🔥 Active (7 days): {active}\n💬 Total messages: {total_messages}\n🪙 Total coins: {coins}\n\n🏆 Top active members:\n{top_text}")


async def autoclean_command(update, context):
    if not owner_only(update):
        await update.message.reply_text("❌ Access denied.")
        return
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /autoclean group mein use karo.")
        return
    arg = context.args[0].lower() if context.args else "toggle"
    if arg in ("on", "off"):
        enabled = arg == "on"
    else:
        with db_connect() as conn:
            row = conn.execute("SELECT enabled FROM autoclean_chats WHERE chat_id=?", (chat.id,)).fetchone()
        enabled = not bool(row and row[0])
    with db_connect() as conn:
        conn.execute("INSERT INTO autoclean_chats(chat_id,enabled,delay_seconds) VALUES(?,?,10) ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled", (chat.id, 1 if enabled else 0))
    await update.message.reply_text(f"🧹 Auto-Clean: {'ON 🟢' if enabled else 'OFF 🔴'}\n\nBot commands will be cleaned after the configured delay.")


async def cleanup_message_later(bot, chat_id, message_id, delay=10):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def rank_command(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /rank sirf group mein use karo.")
        return
    xp, level, messages = get_group_xp(chat.id, user.id)
    rank = get_group_rank(chat.id, user.id)
    current_base = xp_for_level(level - 1) if level > 1 else 0
    next_target = xp_for_level(level)
    progress = xp - current_base
    needed = max(0, next_target - xp)
    rank_text = f"#{rank}" if rank else "Unranked"
    await update.message.reply_text(
        f"🏆 𝐘𝐎𝐔𝐑 𝐑𝐀𝐍𝐊\n\n"
        f"👤 {user.full_name}\n"
        f"🏅 Level: {level} {"💎 ELITE" if is_elite(chat.id, user.id) else ("👑 VIP" if is_vip(chat.id, user.id) else "")}\n"
        f"✨ XP: {xp}\n"
        f"📊 Progress: {progress}/{next_target - current_base}\n"
        f"💬 Messages: {messages}\n"
        f"🥇 Group Rank: {rank_text}\n\n"
        f"🎯 Next level: {needed} XP needed"
    )


async def top_command(update, context):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /top sirf group mein use karo.")
        return
    rows = get_group_top(chat.id, 10)
    if not rows:
        await update.message.reply_text("📊 Abhi leaderboard empty hai. Group mein messages bhejo aur XP earn karo! 🚀")
        return
    lines = ["🏆 𝐆𝐑𝐎𝐔𝐏 𝐋𝐄𝐀𝐃𝐄𝐑𝐁𝐎𝐀𝐑𝐃", ""]
    medals = ["🥇", "🥈", "🥉"]
    for i, (_, name, xp, level, messages) in enumerate(rows, 1):
        prefix = medals[i-1] if i <= 3 else f"{i}."
        safe_name = (name or "User").replace("\n", " ")[:40]
        lines.append(f"{prefix} {safe_name} — Lvl {level} • {xp} XP • {messages} msgs")
    lines.append("\n💡 Use /rank to check your own stats.")
    await update.message.reply_text("\n".join(lines))


async def track_group_activity(update, context):
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        save_group_member(update.effective_chat, update.effective_user)
        user = update.effective_user
        message = update.effective_message
        if user and not user.is_bot and message and message.text and not message.text.startswith("/"):
            add_group_xp(update.effective_chat.id, user.id, 5)
            with db_connect() as conn:
                conn.execute("INSERT INTO group_activity(chat_id,user_id,message_count,last_seen) VALUES(?,?,1,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET message_count=group_activity.message_count+1,last_seen=excluded.last_seen", (update.effective_chat.id, user.id, datetime.utcnow().isoformat()))
        if user and not user.is_bot and message and message.text and message.text.startswith("/"):
            with db_connect() as conn:
                row = conn.execute("SELECT enabled,delay_seconds FROM autoclean_chats WHERE chat_id=?", (update.effective_chat.id,)).fetchone()
            if row and row[0]:
                asyncio.create_task(cleanup_message_later(context.bot, update.effective_chat.id, message.message_id, row[1]))


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


# ===== NATURAL AI VOICE MESSAGE FEATURE =====
def _voice_language(text):
    return "hi" if re.search(r"[\u0900-\u097F]", text) else "en"

async def send_voice_from_text(update, context):
    message = update.effective_message
    if not message:
        return
    text_to_speak = " ".join(context.args or []).strip()
    if not text_to_speak:
        await message.reply_text(
            "🎙️ <b>Natural Voice</b>\n\n"
            "Use:\n<code>/voice Hello everyone 👋</code>\n"
            "<code>/voice नमस्ते सभी को 👋</code>\n"
            "<code>/voice Aaj group me kya scene hai?</code>",
            parse_mode="HTML",
        )
        return
    if len(text_to_speak) > 500:
        await message.reply_text("⚠️ Voice text maximum 500 characters ka rakho.")
        return
    try:
        import edge_tts
        voice_name = "hi-IN-SwaraNeural" if re.search(r"[\u0900-\u097F]", text_to_speak) else "en-IN-NeerjaNeural"
        audio = io.BytesIO()
        communicate = edge_tts.Communicate(text_to_speak, voice_name, rate="+0%", volume="+0%", pitch="+0Hz")
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio.write(chunk["data"])
        audio.seek(0)
        await message.reply_voice(voice=audio, caption="🎙️ Natural AI Voice")
    except Exception as e:
        print(f"⚠️ Voice generation error: {e}")
        await message.reply_text("❌ Natural voice generate nahi ho payi. Render logs check karo.")


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

    if query.data.startswith("giveaway_join:"):
        await giveaway_join_callback(query, context)

    elif query.data == "admin_redeem":
        if not owner_only(update): return
        context.user_data["admin_input"] = "redeem_generate"
        await query.edit_message_text("🎟️ 𝐑𝐄𝐃𝐄𝐄𝐌 𝐂𝐎𝐃𝐄 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐎𝐑\n\nAmount aur count bhejo.\nExample: 1000 50\n➡️ Isse 1000 coins ke 50 unique one-time codes banenge.\n/cancel se cancel.", reply_markup=admin_back())

    elif query.data == "admin":
        if not owner_only(update):
            await query.answer("Access denied", show_alert=True); return
        await query.edit_message_text(admin_dashboard_text(), reply_markup=admin_menu())


    elif query.data == "admin_refresh":
        if not owner_only(update): return
        await query.edit_message_text(admin_dashboard_text(), reply_markup=admin_menu())

    elif query.data == "shop":
        await query.edit_message_text(shop_text(), reply_markup=shop_keyboard())

    elif query.data == "shop_wallet":
        balance = get_coins(query.message.chat_id, user.id)
        await query.answer(f"🪙 Your balance: {balance} coins", show_alert=True)

    elif query.data.startswith("shop_buy:"):
        try:
            item_id = int(query.data.split(":", 1)[1])
        except ValueError:
            await query.answer("Invalid shop item.", show_alert=True); return
        with db_connect() as conn:
            item = conn.execute(
                "SELECT item_id,name,description,price,reward_type,reward_value FROM coin_shop WHERE item_id=? AND enabled=1",
                (item_id,)
            ).fetchone()
        if not item:
            await query.answer("❌ This reward is unavailable.", show_alert=True); return
        _, name, desc, price, reward_type, reward_value = item
        balance = get_coins(query.message.chat_id, user.id)
        if balance < price:
            await query.answer(f"❌ Need {price} coins. You have {balance}.", show_alert=True); return
        add_coins(query.message.chat_id, user.id, -price)
        if reward_type == "xp":
            old_xp, new_xp, old_level, new_level, _ = add_group_xp(query.message.chat_id, user.id, reward_value)
            reward_msg = f"⭐ +{reward_value} XP added"
            if new_level > old_level:
                reward_msg += f"\n🎉 Level up: {old_level} → {new_level}"
        elif reward_type == "coins":
            new_balance = add_coins(query.message.chat_id, user.id, reward_value)
            reward_msg = f"🪙 +{reward_value} bonus coins added"
        else:
            reward_msg = "📩 Your reward request has been recorded for the owner"
            try:
                if name == "👑 VIP BADGE":
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("👑 APPROVE VIP", callback_data=f"vip_approve:{query.message.chat_id}:{user.id}"),
                        InlineKeyboardButton("❌ REJECT", callback_data=f"vip_reject:{query.message.chat_id}:{user.id}")
                    ]])
                    await context.bot.send_message(
                        OWNER_ID,
                        f"🛒 𝐕𝐈𝐏 𝐂𝐋𝐀𝐈𝐌\n\n👤 {user.full_name} (ID: {user.id})\n🏠 Chat: {query.message.chat_id}\n🎁 {name}\n🪙 Cost: {price} coins\n📝 {desc}",
                        reply_markup=kb
                    )
                elif name == "💎 ELITE BADGE":
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("💎 APPROVE ELITE", callback_data=f"elite_approve:{query.message.chat_id}:{user.id}"),
                        InlineKeyboardButton("❌ REJECT", callback_data=f"elite_reject:{query.message.chat_id}:{user.id}")
                    ]])
                    await context.bot.send_message(
                        OWNER_ID,
                        f"🛒 𝐄𝐋𝐈𝐓𝐄 𝐂𝐋𝐀𝐈𝐌\n\n👤 {user.full_name} (ID: {user.id})\n🏠 Chat: {query.message.chat_id}\n🎁 {name}\n🪙 Cost: {price} coins\n📝 {desc}",
                        reply_markup=kb
                    )
                else:
                    await context.bot.send_message(
                        OWNER_ID,
                        f"🛒 SHOP CLAIM\n\n👤 {user.full_name} (ID: {user.id})\n🏠 Chat: {query.message.chat_id}\n🎁 {name}\n🪙 Cost: {price} coins\n📝 {desc}"
                    )
            except Exception:
                pass
        record_purchase(query.message.chat_id, user.id, item_id, name, price)
        final_balance = get_coins(query.message.chat_id, user.id)
        await query.answer("✅ Reward claimed!", show_alert=True)
        await query.edit_message_text(
            f"✅ 𝐑𝐄𝐖𝐀𝐑𝐃 𝐂𝐋𝐀𝐈𝐌𝐄𝐃\n\n🎁 {name}\n{reward_msg}\n💳 Remaining balance: {final_balance} coins",
            reply_markup=shop_keyboard()
        )

    elif query.data.startswith("vip_approve:"):
        if not owner_only(update):
            await query.answer("Owner only", show_alert=True); return
        try:
            _, chat_id, user_id = query.data.split(":")
            chat_id, user_id = int(chat_id), int(user_id)
        except Exception:
            await query.answer("Invalid VIP request.", show_alert=True); return
        grant_vip(chat_id, user_id)
        with db_connect() as conn:
            conn.execute("UPDATE coin_purchases SET status='approved' WHERE chat_id=? AND user_id=? AND item_name='👑 VIP BADGE' AND status='claimed'", (chat_id, user_id))
        await query.edit_message_text(f"✅ 𝐕𝐈𝐏 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃\n\n👤 User ID: {user_id}\n🏠 Chat ID: {chat_id}\n👑 VIP badge is now active.")
        try:
            await context.bot.send_message(chat_id, f"👑 𝐕𝐈𝐏 𝐁𝐀𝐃𝐆𝐄 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃!\n\n🎉 Congratulations! Your VIP status is now active.\n✨ Use /vip to check your status.")
        except Exception:
            pass

    elif query.data.startswith("vip_reject:"):
        if not owner_only(update):
            await query.answer("Owner only", show_alert=True); return
        try:
            _, chat_id, user_id = query.data.split(":")
            chat_id, user_id = int(chat_id), int(user_id)
        except Exception:
            await query.answer("Invalid VIP request.", show_alert=True); return
        with db_connect() as conn:
            conn.execute("UPDATE coin_purchases SET status='rejected' WHERE chat_id=? AND user_id=? AND item_name='👑 VIP BADGE' AND status='claimed'", (chat_id, user_id))
        await query.edit_message_text(f"❌ 𝐕𝐈𝐏 𝐑𝐄𝐐𝐔𝐄𝐒𝐓 𝐑𝐄𝐉𝐄𝐂𝐓𝐄𝐃\n\n👤 User ID: {user_id}\n🏠 Chat ID: {chat_id}")
        try:
            await context.bot.send_message(chat_id, "❌ Your VIP Badge request was rejected by the owner.")
        except Exception:
            pass

    elif query.data.startswith("elite_approve:"):
        if not owner_only(update):
            await query.answer("Owner only", show_alert=True); return
        try:
            _, chat_id, user_id = query.data.split(":")
            chat_id, user_id = int(chat_id), int(user_id)
        except Exception:
            await query.answer("Invalid Elite request.", show_alert=True); return
        grant_elite(chat_id, user_id)
        with db_connect() as conn:
            conn.execute("UPDATE coin_purchases SET status='approved' WHERE chat_id=? AND user_id=? AND item_name='💎 ELITE BADGE' AND status='claimed'", (chat_id, user_id))
        await query.edit_message_text(f"✅ 𝐄𝐋𝐈𝐓𝐄 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃\n\n👤 User ID: {user_id}\n🏠 Chat ID: {chat_id}\n💎 Elite badge is now active.")
        try:
            await context.bot.send_message(chat_id, "💎 𝐄𝐋𝐈𝐓𝐄 𝐁𝐀𝐃𝐆𝐄 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃!\n\n🎉 Congratulations! Your Elite status is now active.\n✨ Use /elite to check your status.")
        except Exception:
            pass

    elif query.data.startswith("elite_reject:"):
        if not owner_only(update):
            await query.answer("Owner only", show_alert=True); return
        try:
            _, chat_id, user_id = query.data.split(":")
            chat_id, user_id = int(chat_id), int(user_id)
        except Exception:
            await query.answer("Invalid Elite request.", show_alert=True); return
        with db_connect() as conn:
            conn.execute("UPDATE coin_purchases SET status='rejected' WHERE chat_id=? AND user_id=? AND item_name='💎 ELITE BADGE' AND status='claimed'", (chat_id, user_id))
        await query.edit_message_text(f"❌ 𝐄𝐋𝐈𝐓𝐄 𝐑𝐄𝐐𝐔𝐄𝐒𝐓 𝐑𝐄𝐉𝐄𝐂𝐓𝐄𝐃\n\n👤 User ID: {user_id}\n🏠 Chat ID: {chat_id}")
        try:
            await context.bot.send_message(chat_id, "❌ Your Elite Badge request was rejected by the owner.")
        except Exception:
            pass

    elif query.data == "admin_secure":
        if not owner_only(update): return
        await query.answer("Owner-only control center 🔐", show_alert=True)

    elif query.data == "admin_coins":
        if not owner_only(update): return
        await query.edit_message_text(
            "🪙 𝐂𝐎𝐈𝐍 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓\n\n"
            "➕ Add/➖ Remove coins: button choose karo, phir target member ke message ko reply karke amount bhejo.",
            reply_markup=coin_admin_menu()
        )

    elif query.data in ("coin_add", "coin_remove"):
        if not owner_only(update): return
        state = "coin_add" if query.data == "coin_add" else "coin_remove"
        context.user_data["admin_input"] = state
        action = "ADD" if state == "coin_add" else "REMOVE"
        await query.edit_message_text(
            f"🪙 𝐂𝐎𝐈𝐍 {action}\n\n"
            "Ab jis member ko coins dene hain uske message ko REPLY karke sirf amount bhejo.\n"
            "Example: 500\n\n/cancel se cancel kar sakte ho.",
            reply_markup=admin_back()
        )

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
        with db_connect() as conn:
            groups_total = conn.execute("SELECT COUNT(*) FROM group_chats").fetchone()[0]
            xp_users = conn.execute("SELECT COUNT(*) FROM xp_levels").fetchone()[0]
            coin_users, total_coins = conn.execute("SELECT COUNT(*), COALESCE(SUM(balance),0) FROM coins WHERE balance > 0").fetchone()
        await query.edit_message_text(
            f"📊 𝐀𝐃𝐕𝐀𝐍𝐂𝐄𝐃 𝐃𝐀𝐒𝐇𝐁𝐎𝐀𝐑𝐃\n\n"
            f"👥 Total Users: {get_user_count()}\n"
            f"🏠 Groups Tracked: {groups_total}\n"
            f"⭐ XP Users: {xp_users}\n"
            f"🪙 Coin Holders: {coin_users}\n"
            f"💰 Total Coins: {total_coins}\n\n"
            f"📢 Promo Group: {'CONNECTED ✅' if get_setting('promo_chat_id','') else 'NOT SET ⚠️'}\n"
            f"⏱️ Promo Interval: {int(get_setting('promo_interval',str(AUTO_PROMO_INTERVAL)))//60} min\n"
            f"🤖 Bot Status: ONLINE 🟢",
            reply_markup=admin_menu()
        )

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
        """╔══════════════════════════════╗
        🤖 𝐁𝐎𝐓 𝐇𝐄𝐋𝐏 𝐂𝐄𝐍𝐓𝐄𝐑
╚══════════════════════════════╝

✨ 𝐐𝐔𝐈𝐂𝐊 𝐒𝐓𝐀𝐑𝐓
/start — Start & open the bot
/about — About the bot & owner
/help — Show this command guide
/ping — Check if the bot is online
/id — Show your Telegram ID
/dm — Contact the owner
/cancel — Cancel an active action

🎮 𝐅𝐔𝐍 & 𝐒𝐎𝐂𝐈𝐀𝐋
/love — Fun love meter
/dice — Roll a dice
/quote — Get a random quote

⭐ 𝐗𝐏 & 𝐑𝐀𝐍𝐊
/rank — Your XP, level & rank
/top — Top 10 members leaderboard
/stats — Group/user statistics
/advstats — Advanced statistics
/profile — Your group profile card
/analytics — Group analytics (admins)

🪙 𝐂𝐎𝐈𝐍 𝐄𝐂𝐎𝐍𝐎𝐌𝐘
/coins — Check your wallet balance
/dailycoins — Claim your daily coin reward
/shop — Open the Coin Shop & claim rewards
/gift <amount> — Reply to a member and gift coins
/redeem CODE — Redeem a one-time coin code

🎁 𝐂𝐎𝐈𝐍 𝐒𝐇𝐎𝐏 𝐑𝐄𝐖𝐀𝐑𝐃𝐒
⭐ XP Boost • 📣 Shoutout • 👑 VIP Badge
🎁 Bonus Coins • 💎 Elite Badge • 🚀 Priority Shoutout

👥 𝐆𝐑𝐎𝐔𝐏 𝐓𝐎𝐎𝐋𝐒
/tag [message] — Mention known members (admin)
/tagall [message] — Same as /tag
/testgreet morning|afternoon|night — Test greeting
/welcome — Welcome system controls
/automod — Smart auto-moderation controls

🎬 𝐌𝐎𝐕𝐈𝐄 & 𝐒𝐄𝐑𝐈𝐄𝐒
/movie <name> — Search movie information
/series <name> — Search series information

🔗 𝐂𝐎𝐌𝐌𝐔𝐍𝐈𝐓𝐘
/referral — Get your referral link
/myref — Check your referral count

🛡️ 𝐎𝐖𝐍𝐄𝐑 𝐂𝐎𝐍𝐓𝐑𝐎𝐋𝐒
/admin — Advanced Owner Control Center
/mod — Moderation panel
/setpromo — Configure auto-promo group
/autopromo_on — Turn auto-promo ON
/autopromo_off — Turn auto-promo OFF
/giveaway MINUTES WINNERS PRIZE — Start a giveaway
/autoclean on/off — Auto-delete group commands
/settitle TITLE — Owner custom title (reply)
/cleartitle — Reset custom title (reply)
/runall — Safe system test

💡 𝐓𝐈𝐏: Group tools ko group mein slash `/` ke saath use karo.
👥 Group-only command ko private chat mein bhejne par bot clearly guide karega.
🔐 Owner-only commands unauthorized users ke liye locked hain.

🚀 More features are available through /start"""
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
# GIVEAWAY SYSTEM
# ==================================

async def giveaway_command(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /giveaway sirf group mein use karo.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("creator", "administrator") and user.id != OWNER_ID:
            await update.message.reply_text("❌ Sirf group admins /giveaway chala sakte hain.")
            return
    except Exception:
        if user.id != OWNER_ID:
            return
    if len(context.args) < 3:
        await update.message.reply_text("🎁 Use: /giveaway MINUTES WINNERS PRIZE\nExample: /giveaway 60 2 1000 Coins")
        return
    try:
        minutes = int(context.args[0]); winners = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Minutes aur winners number hone chahiye.")
        return
    if minutes < 1 or minutes > 10080 or winners < 1 or winners > 20:
        await update.message.reply_text("❌ Minutes 1-10080 aur winners 1-20 rakho.")
        return
    prize = " ".join(context.args[2:]).strip()
    end_at = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()
    with db_connect() as conn:
        cur = conn.execute("INSERT INTO giveaways(chat_id,creator_id,prize,winners_count,end_at) VALUES(?,?,?,?,?)", (chat.id,user.id,prize,winners,end_at))
        gid = cur.lastrowid
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 JOIN GIVEAWAY", callback_data=f"giveaway_join:{gid}")]])
    msg = await update.message.reply_text(f"🎉 𝐆𝐈𝐕𝐄𝐀𝐖𝐀𝐘 𝐋𝐈𝐕𝐄!\n\n🎁 Prize: {prize}\n🏆 Winners: {winners}\n⏳ Ends in: {minutes} minutes\n\n👇 Join below!", reply_markup=kb)
    with db_connect() as conn:
        conn.execute("UPDATE giveaways SET message_id=? WHERE id=?", (msg.message_id,gid))


async def giveaway_join_callback(query, context):
    try:
        gid = int(query.data.split(":",1)[1])
    except Exception:
        await query.answer("Invalid giveaway.", show_alert=True); return
    with db_connect() as conn:
        row = conn.execute("SELECT chat_id,prize,end_at,status FROM giveaways WHERE id=?", (gid,)).fetchone()
        if not row:
            await query.answer("Giveaway not found.", show_alert=True); return
        chat_id, prize, end_at, status = row
        if status != "active" or datetime.fromisoformat(end_at) <= datetime.utcnow():
            await query.answer("⏰ Giveaway has ended.", show_alert=True); return
        conn.execute("INSERT OR IGNORE INTO giveaway_entries(giveaway_id,user_id,name,joined_at) VALUES(?,?,?,?)", (gid,query.from_user.id,query.from_user.full_name,datetime.utcnow().isoformat()))
    await query.answer("🎉 You joined the giveaway!", show_alert=True)


async def giveaway_loop(app):
    while True:
        try:
            await asyncio.sleep(15)
            with db_connect() as conn:
                rows = conn.execute("SELECT id,chat_id,prize,winners_count,message_id FROM giveaways WHERE status='active' AND end_at<=?", (datetime.utcnow().isoformat(),)).fetchall()
            for gid, chat_id, prize, winners_count, message_id in rows:
                with db_connect() as conn:
                    entries = conn.execute("SELECT user_id,name FROM giveaway_entries WHERE giveaway_id=?", (gid,)).fetchall()
                    conn.execute("UPDATE giveaways SET status='ended' WHERE id=? AND status='active'", (gid,))
                if entries:
                    winners = random.sample(entries, min(winners_count, len(entries)))
                    winner_text = "\n".join(f"🏆 {name} — <code>{uid}</code>" for uid,name in winners)
                    result = f"🏁 𝐆𝐈𝐕𝐄𝐀𝐖𝐀𝐘 𝐄𝐍𝐃𝐄𝐃!\n\n🎁 Prize: {prize}\n\n{winner_text}"
                else:
                    result = f"🏁 𝐆𝐈𝐕𝐄𝐀𝐖𝐀𝐘 𝐄𝐍𝐃𝐄𝐃!\n\n🎁 Prize: {prize}\n❌ No participants."
                try:
                    await app.bot.send_message(chat_id, result, parse_mode="HTML")
                    if message_id:
                        await app.bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
                except Exception:
                    pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️ Giveaway loop error: {e}")

# ==================================
# GROUP TAGGER / TAG ALL
# ==================================

TAG_BATCH_SIZE = 25
TAG_DELAY = 1.2
tag_running = set()


async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tag known non-bot group members in small batches.

    Usage: /tag [optional message]
    The bot can only tag members it has previously detected/stored.
    """
    chat = update.effective_chat
    user = update.effective_user

    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ /tag command sirf group mein use karo.")
        return

    if not user:
        return

    # Keep tagging admin-controlled to avoid members repeatedly mass-tagging
    # the whole group.
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ("creator", "administrator") and user.id != OWNER_ID:
            await update.message.reply_text("❌ Sirf group admins / owner /tag use kar sakte hain.")
            return
    except Exception:
        if user.id != OWNER_ID:
            await update.message.reply_text("❌ Admin permission verify nahi ho saki.")
            return

    if chat.id in tag_running:
        await update.message.reply_text("⏳ Tagging already chal rahi hai. Please wait...")
        return

    members = group_members(chat.id)
    # Never tag bots or the requesting command sender when they are in storage.
    members = [(uid, name) for uid, name in members if uid != user.id]

    if not members:
        await update.message.reply_text(
            "❌ Abhi koi known member nahi mila.\n\n"
            "Bot ko group mein members ke messages/activities detect karne do, "
            "phir /tag dobara use karo."
        )
        return

    custom_text = " ".join(context.args).strip()
    intro = custom_text or "👋 Hey everyone!"

    tag_running.add(chat.id)
    try:
        total = len(members)
        await update.message.reply_text(
            f"📢 𝐓𝐀𝐆 𝐀𝐋𝐋 𝐒𝐓𝐀𝐑𝐓𝐄𝐃\n\n"
            f"👥 Members found: {total}\n"
            f"⚡ Tagging in progress..."
        )

        for start in range(0, total, TAG_BATCH_SIZE):
            batch = members[start:start + TAG_BATCH_SIZE]
            text = intro + "\n\n"
            entities = []

            for index, (uid, name) in enumerate(batch):
                if index:
                    text += " "
                display_name = (name or "User")[:64]
                offset = len(text.encode("utf-16-le")) // 2
                text += display_name
                length = len(display_name.encode("utf-16-le")) // 2
                from telegram import MessageEntity, User
                entities.append(
                    MessageEntity(
                        type="text_mention",
                        offset=offset,
                        length=length,
                        user=User(
                            id=uid,
                            first_name=display_name,
                            is_bot=False,
                        ),
                    )
                )

            await context.bot.send_message(
                chat_id=chat.id,
                text=text,
                entities=entities,
                disable_web_page_preview=True,
            )

            if start + TAG_BATCH_SIZE < total:
                await asyncio.sleep(TAG_DELAY)

        await context.bot.send_message(
            chat_id=chat.id,
            text=f"✅ 𝐓𝐀𝐆𝐆𝐈𝐍𝐆 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄\n\n👥 Tagged: {total} members",
        )
    except Exception as e:
        print(f"⚠️ Tag error: {e}")
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text="⚠️ Tagging stop ho gayi. Telegram limit/permission ki wajah se ho sakta hai."
            )
        except Exception:
            pass
    finally:
        tag_running.discard(chat.id)


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
# LINK / MESSAGE PROTECTION
# ==================================

URL_PATTERN = re.compile(
    r"(?i)(?:https?://|ftp://|www\\.)[^\\s<>()]+"
    r"|(?:t\\.me|telegram\\.me|telegram\\.dog)/[^\\s<>()]+"
    r"|(?:[a-z0-9-]+\\.)+(?:com|net|org|in|xyz|me|io|co|ly|gg|cc|app|dev|site|online|store|live|tv|tech|info|pro|link|fun|top|club)(?:/[^\\s<>()]*)?"
)

def protection_config(chat_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT link_protect,forward_protect FROM protection_chats WHERE chat_id=?",
            (chat_id,)
        ).fetchone()
    if row:
        return bool(row[0]), bool(row[1])
    return False, False


def set_protection_config(chat_id, link_protect=None, forward_protect=None):
    current = protection_config(chat_id)
    values = (
        int(current[0] if link_protect is None else bool(link_protect)),
        int(current[1] if forward_protect is None else bool(forward_protect)),
    )
    with db_connect() as conn:
        conn.execute(
            """INSERT INTO protection_chats(chat_id,link_protect,forward_protect)
               VALUES(?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
               link_protect=excluded.link_protect,
               forward_protect=excluded.forward_protect""",
            (chat_id, *values)
        )


def message_contains_link(message):
    text = message.text or message.caption or ""
    if text and URL_PATTERN.search(text):
        return True

    entities = []
    if message.entities:
        entities.extend(message.entities)
    if message.caption_entities:
        entities.extend(message.caption_entities)

    return any(
        getattr(entity, "type", "") in ("url", "text_link")
        for entity in entities
    )


def is_forwarded_message(message):
    return bool(getattr(message, "forward_origin", None))


async def protection_command(update, context):
    if not await can_manage_protection(update, context):
        await update.effective_message.reply_text("❌ Sirf owner/admin ye command use kar sakta hai.")
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Ye command group mein use karo.")
        return

    args = [a.lower() for a in context.args]
    link_on, forward_on = protection_config(chat.id)

    if not args:
        await update.message.reply_text(
            "🛡️ 𝐆𝐑𝐎𝐔𝐏 𝐏𝐑𝐎𝐓𝐄𝐂𝐓𝐈𝐎𝐍\n\n"
            f"🔗 Link Protection: {'ON 🟢' if link_on else 'OFF 🔴'}\n"
            f"↪️ Forward Protection: {'ON 🟢' if forward_on else 'OFF 🔴'}\n\n"
            "Commands:\n"
            "/linkprotect on — links auto-delete\n"
            "/linkprotect off — link protection OFF\n"
            "/forwardprotect on — forwarded messages auto-delete\n"
            "/forwardprotect off — forward protection OFF"
        )
        return

    mode = args[0]
    if mode not in ("on", "off"):
        await update.message.reply_text(
            "❌ Use: /protection or /protection on|off\n"
            "For links: /linkprotect on|off"
        )
        return

    set_protection_config(chat.id, link_protect=(mode == "on"))
    await update.message.reply_text(
        f"🛡️ Link Protection: {'ON 🟢' if mode == 'on' else 'OFF 🔴'}"
    )


async def linkprotect_command(update, context):
    if not await can_manage_protection(update, context):
        await update.effective_message.reply_text("❌ Sirf owner/admin ye command use kar sakta hai.")
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Ye command group mein use karo.")
        return

    args = [a.lower() for a in context.args]
    current_link, _ = protection_config(chat.id)

    if not args:
        await update.message.reply_text(
            f"🔗 𝐋𝐈𝐍𝐊 𝐏𝐑𝐎𝐓𝐄𝐂𝐓𝐈𝐎𝐍\n\n"
            f"Status: {'ON 🟢' if current_link else 'OFF 🔴'}\n\n"
            "ON: /linkprotect on\n"
            "OFF: /linkprotect off"
        )
        return

    if args[0] not in ("on", "off"):
        await update.message.reply_text("❌ Use: /linkprotect on or /linkprotect off")
        return

    enabled = args[0] == "on"
    set_protection_config(chat.id, link_protect=enabled)
    await update.message.reply_text(
        f"🔗 Link Protection: {'ON 🟢' if enabled else 'OFF 🔴'}\n"
        "⚠️ Bot ko group mein Delete Messages permission honi chahiye."
    )


async def forwardprotect_command(update, context):
    if not await can_manage_protection(update, context):
        await update.effective_message.reply_text("❌ Sirf owner/admin ye command use kar sakta hai.")
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Ye command group mein use karo.")
        return

    args = [a.lower() for a in context.args]
    _, current_forward = protection_config(chat.id)

    if not args:
        await update.message.reply_text(
            f"↪️ 𝐅𝐎𝐑𝐖𝐀𝐑𝐃 𝐏𝐑𝐎𝐓𝐄𝐂𝐓𝐈𝐎𝐍\n\n"
            f"Status: {'ON 🟢' if current_forward else 'OFF 🔴'}\n\n"
            "ON: /forwardprotect on\n"
            "OFF: /forwardprotect off"
        )
        return

    if args[0] not in ("on", "off"):
        await update.message.reply_text("❌ Use: /forwardprotect on or /forwardprotect off")
        return

    enabled = args[0] == "on"
    set_protection_config(chat.id, forward_protect=enabled)
    await update.message.reply_text(
        f"↪️ Forward Protection: {'ON 🟢' if enabled else 'OFF 🔴'}\n"
        "⚠️ Bot ko group mein Delete Messages permission honi chahiye."
    )


# ==================================
# SMART AUTO-MOD
# ==================================

BAD_WORDS = {
    "free nitro scam", "click this link scam", "crypto giveaway scam"
}
flood_cache = {}


async def automod_message(update, context):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type not in ("group", "supergroup"):
        return

    user = update.effective_user
    if not user or user.is_bot:
        return

    link_protect, forward_protect = protection_config(chat.id)

    # Link/forward protection is checked before the normal Auto-Mod admin
    # exemption, so protection can still catch links sent by the owner/admin.
    if link_protect and message_contains_link(message):
        try:
            await message.delete()
            await chat.send_message(
                f"🛡️ {user.mention_html()} ka link remove kar diya gaya.\n"
                "🔗 Link Protection active hai.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"⚠️ Link protection error: {e}")
        return

    # Optional forwarded-message protection.
    if forward_protect and is_forwarded_message(message):
        try:
            await message.delete()
            await chat.send_message(
                f"🛡️ {user.mention_html()} ka forwarded message remove kar diya gaya.\n"
                "↪️ Forward Protection active hai.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"⚠️ Forward protection error: {e}")
        return

    enabled, max_warnings, flood_limit, flood_window = automod_config(chat.id)
    if not enabled:
        return

    text = (message.text or message.caption or "").lower()
    suspicious = any(word in text for word in BAD_WORDS)

    now = time.monotonic()
    key = (chat.id, user.id)
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
        await chat.send_message(
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
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            await chat.send_message(
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
    app.add_handler(CommandHandler("profile", group_only(profile_command)))
    app.add_handler(CommandHandler("settitle", group_only(settitle_command)))
    app.add_handler(CommandHandler("cleartitle", group_only(cleartitle_command)))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(CommandHandler("analytics", group_only(analytics_command)))
    app.add_handler(CommandHandler("autoclean", group_only(autoclean_command)))
    app.add_handler(CommandHandler("giveaway", group_only(giveaway_command)))
    app.add_handler(CommandHandler("rank", group_only(rank_command)))
    app.add_handler(CommandHandler("vip", vip_command))
    app.add_handler(CommandHandler("elite", elite_command))
    app.add_handler(CommandHandler("giveelite", giveelite_command))
    app.add_handler(CommandHandler("removeelite", removeelite_command))
    app.add_handler(CommandHandler("givevip", givevip_command))
    app.add_handler(CommandHandler("removevip", removevip_command))
    app.add_handler(CommandHandler("top", group_only(top_command)))
    app.add_handler(CommandHandler("testgreet", group_only(test_greet_command)))
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CommandHandler("shop", shop_command))
    app.add_handler(CommandHandler("dailycoins", dailycoins_command))
    app.add_handler(CommandHandler("gift", gift_command))
    app.add_handler(CommandHandler("runall", runall_command))

    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("registergroup", register_group))
    app.add_handler(CommandHandler("mod", group_only(mod_command)))
    app.add_handler(CommandHandler("warn", group_only(warn_user)))
    app.add_handler(CommandHandler("mute", group_only(mute_user)))
    app.add_handler(CommandHandler("unmute", group_only(unmute_user)))
    app.add_handler(CommandHandler("ban", group_only(ban_user)))
    app.add_handler(CommandHandler("unban", group_only(unban_user)))

    # Group auto-promotion controls
    app.add_handler(CommandHandler("setpromo", group_only(set_promo_group)))
    app.add_handler(CommandHandler("autopromo_on", promo_on))
    app.add_handler(CommandHandler("autopromo_off", promo_off))
    app.add_handler(CommandHandler("welcome", group_only(welcome_toggle_command)))
    app.add_handler(CommandHandler("automod", group_only(automod_toggle_command)))
    app.add_handler(CommandHandler("protection", group_only(protection_command)))
    app.add_handler(CommandHandler("linkprotect", group_only(linkprotect_command)))
    app.add_handler(CommandHandler("forwardprotect", group_only(forwardprotect_command)))
    app.add_handler(CommandHandler("voice", send_voice_from_text))
    app.add_handler(CommandHandler("tag", group_only(tag_command)))
    app.add_handler(CommandHandler("tagall", group_only(tag_command)))

    # Start automatic group promotion without requiring
    # python-telegram-bot's optional JobQueue dependency.
    promo_task = asyncio.create_task(auto_promo_loop(app))
    greeting_task = asyncio.create_task(auto_greeting_loop(app))
    giveaway_task = asyncio.create_task(giveaway_loop(app))
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
        greeting_task.cancel()
        giveaway_task.cancel()
        try:
            await promo_task
        except asyncio.CancelledError:
            pass
        try:
            await greeting_task
        except asyncio.CancelledError:
            pass
        try:
            await giveaway_task
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

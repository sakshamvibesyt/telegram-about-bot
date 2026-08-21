import os
import asyncio
import threading

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]

# Render Environment Variables me apna numeric Telegram ID daalna
OWNER_ID = int(os.environ["OWNER_ID"])


# =========================
# ABOUT / WELCOME
# =========================

ABOUT = """✨ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 ✨

╔══════════════════════
║ 👑 𝐊𝐈𝐍𝐆 𝐎𝐅 𝐕𝐈𝐁𝐄𝐒
║ ❤️ 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒
╚══════════════════════

🌱 𝙽𝙰𝙼𝙴 ➜ 𝚂𝙰𝙺𝚂𝙷𝙰𝙼
😎 𝚅𝙸𝙱𝙴 ➜ 𝙰𝙻𝚆𝙰𝚈𝚂 𝚄𝙽𝙸𝚀𝚄𝙴
✨ 𝚂𝚃𝚈𝙻𝙴 ➜ 𝙰𝙻𝚆𝙰𝚈𝚂 𝙳𝙸𝙵𝙵𝙴𝚁𝙴𝙽𝚃

👑 𝗢𝗪𝗡𝗘𝗥
♥️ @sakshamvibesyt

👇 𝗨𝗦𝗘 𝗧𝗛𝗘 𝗕𝗨𝗧𝗧𝗢𝗡𝗦 𝗕𝗘𝗟𝗢𝗪 👇

💌 /dm — Owner ko direct message
ℹ️ /help — Bot commands
🏓 /ping — Bot status
🆔 /id — Apni Telegram ID

❤️ 𝐓𝐇𝐀𝐍𝐊𝐒 𝐅𝐎𝐑 𝐒𝐓𝐀𝐑𝐓𝐈𝐍𝐆 𝐌𝐘 𝐁𝐎𝐓 ❤️
"""


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton(
                "📢 JOIN CHANNEL",
                url="https://t.me/+6g3B5n2xi2xmNDhl"
            )
        ],
        [
            InlineKeyboardButton(
                "▶️ YouTube",
                url="https://youtube.com/@sakshamvibesyt"
            ),
            InlineKeyboardButton(
                "👑 Owner",
                url="https://t.me/sakshamvibesyt"
            )
        ],
        [
            InlineKeyboardButton(
                "💌 MESSAGE OWNER",
                callback_data="dm_info"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        ABOUT,
        reply_markup=reply_markup
    )


# =========================
# HELP
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """╔══════════════════════╗
       🤖 𝐁𝐎𝐓 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒
╚══════════════════════╝

✨ /start
➜ Welcome message

💌 /dm
➜ Owner ko direct message

❌ /cancel
➜ DM mode cancel

🏓 /ping
➜ Bot response check

🆔 /id
➜ Apni Telegram ID dekho

ℹ️ /help
➜ Commands ki list

❤️ 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 ❤️
"""

    await update.message.reply_text(text)


# =========================
# PING
# =========================

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🏓 𝐏𝐎𝐍𝐆!\n\n"
        "🤖 Bot is 𝐀𝐋𝐈𝐕𝐄 & 𝐖𝐎𝐑𝐊𝐈𝐍𝐆 ✅\n"
        "⚡ SAKSHAM VIBES"
    )


# =========================
# USER ID
# =========================

async def user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"🆔 𝐘𝐎𝐔𝐑 𝐓𝐄𝐋𝐄𝐆𝐑𝐀𝐌 𝐈𝐃\n\n"
        f"`{update.effective_user.id}`",
        parse_mode="Markdown"
    )


# =========================
# DM COMMAND
# =========================

async def dm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    # Agar /dm ke baad message diya hai
    if context.args:

        message = " ".join(context.args)

        owner_message = f"""💌 𝐍𝐄𝐖 𝐃𝐌 𝐑𝐄𝐂𝐄𝐈𝐕𝐄𝐃

👤 Name: {user.full_name}
🆔 ID: {user.id}
🔗 Username: @{user.username if user.username else "No Username"}

━━━━━━━━━━━━━━━━━━

💬 Message:

{message}

━━━━━━━━━━━━━━━━━━
"""

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=owner_message
        )

        await update.message.reply_text(
            "✅ 𝐘𝐎𝐔𝐑 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐇𝐀𝐒 𝐁𝐄𝐄𝐍 𝐒𝐄𝐍𝐓!\n\n"
            "👑 Owner ko tumhara message mil gaya ❤️"
        )

        return

    # Agar sirf /dm likha
    context.user_data["dm_mode"] = True

    await update.message.reply_text(
        "💌 𝐃𝐌 𝐌𝐎𝐃𝐄 𝐀𝐂𝐓𝐈𝐕𝐀𝐓𝐄𝐃\n\n"
        "✍️ Ab apna message type karke bhejo.\n\n"
        "❌ Cancel karne ke liye /cancel likho."
    )


# =========================
# RECEIVE DM MESSAGE
# =========================

async def receive_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data.get("dm_mode"):
        return

    user = update.effective_user

    message = update.message.text

    owner_message = f"""💌 𝐍𝐄𝐖 𝐌𝐄𝐒𝐒𝐀𝐆𝐄

👤 Name: {user.full_name}
🆔 ID: {user.id}
🔗 Username: @{user.username if user.username else "No Username"}

━━━━━━━━━━━━━━━━━━

💬 {message}

━━━━━━━━━━━━━━━━━━
"""

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=owner_message
    )

    context.user_data["dm_mode"] = False

    await update.message.reply_text(
        "✅ 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐒𝐄𝐍𝐓!\n\n"
        "👑 Tumhara message Saksham tak pahunch gaya ❤️"
    )


# =========================
# CANCEL DM
# =========================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["dm_mode"] = False

    await update.message.reply_text(
        "❌ 𝐃𝐌 𝐌𝐎𝐃𝐄 𝐂𝐀𝐍𝐂𝐄𝐋𝐋𝐄𝐃\n\n"
        "✨ Wapas start karne ke liye /dm use karo."
    )


# =========================
# FLASK WEB SERVER
# =========================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "SAKSHAM VIBES BOT IS RUNNING! 🤖"


@web_app.route("/health")
def health():
    return "OK"


def run_web_server():

    port = int(os.environ.get("PORT", 10000))

    web_app.run(
        host="0.0.0.0",
        port=port
    )


# =========================
# MAIN BOT
# =========================

async def run_bot():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("ping", ping)
    )

    app.add_handler(
        CommandHandler("id", user_id)
    )

    app.add_handler(
        CommandHandler("dm", dm)
    )

    app.add_handler(
        CommandHandler("cancel", cancel)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_dm
        )
    )

    print("🤖 SAKSHAM VIBES BOT IS RUNNING...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


# =========================
# START EVERYTHING
# =========================

def main():

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

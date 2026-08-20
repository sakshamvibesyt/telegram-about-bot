import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# =========================
# BOT TOKEN
# =========================
BOT_TOKEN = os.environ["BOT_TOKEN"]

# =========================
# ABOUT MESSAGE
# =========================
ABOUT = """
╔══════════════════════╗
   💫 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐌𝐘 𝐁𝐎𝐓 💫
╚══════════════════════╝

👑 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 𝐘𝐓

✨ Apni duniya me mast
🖤 Bass dekhte raho
🔥 Andaaz hi alag hai

⭐ 𝐎𝐖𝐍𝐄𝐑 ⭐
❤️ @sakshamvibesyt

💫 Thanks for starting my bot 💫
"""

# =========================
# TELEGRAM START COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton(
                "📢 JOIN → CLICK HERE",
                url="https://t.me/sakshamvibesyt"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        ABOUT,
        reply_markup=reply_markup
    )


# =========================
# RENDER WEB SERVER
# =========================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Telegram Bot is Running!"

@app.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================
# START BOT
# =========================
def main():

    # Start Render web server
    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    # Create Telegram bot
    bot_app = Application.builder().token(BOT_TOKEN).build()

    bot_app.add_handler(
        CommandHandler("start", start)
    )

    print("🤖 BOT IS RUNNING...")

    bot_app.run_polling()


if __name__ == "__main__":
    main()

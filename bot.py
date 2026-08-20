import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]

ABOUT = """𝐖𝐀𝐋𝐂𝐎𝐌𝐄 𝐀𝐁𝐎𝐔𝐓 𝐒𝐀𝐊𝐒𝐇𝐀𝐌
🎇🎇🎇🎇🎇🎇🎇🎇🎇🎇

╔═════════════════════
╠ 👑 𝐊𝐈𝐍𝐆 𝐎𝐅 𝐕𝐈𝐁𝐄𝐒 ✨
╠ ❤️ 𝐒𝐀𝐊𝐒𝐇𝐀𝐌 𝐕𝐈𝐁𝐄𝐒 ❤️
╚═════════════════════

╔═════════════════════
╠ ⭐️ 𝙺𝚈𝙰 𝙳𝙴𝙺𝙷 𝚁𝙷𝙰 𝙷𝙰𝙸 𝙱𝙴? ⭐️
╠ 🌱 𝙽𝙰𝙼𝙴 𝙷𝙰𝙸 𝚂𝙰𝙺𝚂𝙷𝙰𝙼 🌱
╠ 😎 𝙰𝙿𝙽𝙸 𝙷𝙸 𝙳𝚄𝙽𝙸𝚈𝙰 𝙼𝙴 𝙼𝙰𝚂𝚃
╠ 💛 𝙱𝙰𝚂𝚂 𝙳𝙴𝙺𝙷𝚃𝙴 𝚁𝙷𝙾 🧡
╠ ⭐ 𝙰𝙰𝙽𝙳𝙰𝚉 𝙷𝙸 𝙰𝙻𝙰𝙶 𝙷𝙰𝙸 ⭐
╚═════════════════════

                 ⭐️ 𝗢𝗪𝗡𝗘𝗥 ⭐️
╔═════════════════════
╠ ♥️ ᴏᴡɴᴇʀ ➜ @sakshamvibesyt ✅
╚═════════════════════

👇 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 & 𝗟𝗜𝗡𝗞𝗦 👇

❤️ 𝐓𝐇𝐀𝐍𝐊𝐒 𝐅𝐎𝐑 𝐒𝐓𝐀𝐑𝐓𝐈𝐍𝐆 𝐌𝐘 𝐁𝐎𝐓 ❤️
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton(
                "📢 CLICK HERE — JOIN CHANNEL",
                url="https://t.me/+6g3B5n2xi2xmNDhl"
            )
        ],
        [
            InlineKeyboardButton(
                "▶️ YouTube",
                url="https://yt.openinapp.co/wwoez"
            ),
            InlineKeyboardButton(
                "👤 Owner",
                url="https://t.me/sakshamvibesyt"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        ABOUT,
        reply_markup=reply_markup
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("BOT IS RUNNING...")

    app.run_polling()

if __name__ == "__main__":
    main()

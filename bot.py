import os
import random
import asyncio
import threading

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
    filters,
)


# ==================================
# CONFIG
# ==================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])

# Apne links yahan change karna
CHANNEL_URL = "https://t.me/YOUR_CHANNEL_USERNAME"
YOUTUBE_URL = "https://youtube.com/@YOUR_YOUTUBE"
INSTAGRAM_URL = "https://instagram.com/YOUR_INSTAGRAM"


# ==================================
# USER STATS
# ==================================

users = set()


def save_user(user_id):
    users.add(user_id)


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
                url="https://t.me/+6g3B5n2xi2xmNDhl"
            )
        ],
        [
            InlineKeyboardButton(
                "▶️ YOUTUBE",
                url="https://yt.openinapp.co/wwoez"
            ),
            InlineKeyboardButton(
                "📸 INSTAGRAM",
                url="https://insta.openinapp.co/xqhfr"
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

    if query.data == "about":

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
/ping"""
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

    await update.message.reply_text(
        "❌ DM mode cancelled."
    )


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

    app.add_handler(
        CallbackQueryHandler(button_handler)
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


def main():

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

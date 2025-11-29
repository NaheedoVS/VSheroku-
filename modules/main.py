# main.py
# (c) Pglinsan | Updated by GPT-5
# Telegram Video Uploader + Watermark + Compression Bot
# Compatible with Pyrogram v2.x

import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import globals
from vars import API_ID, API_HASH, BOT_TOKEN, OWNER, CREDIT

# Import modules

from features import register_features_handlers
from html_handler import register_html_handlers
from logs import register_logs_handlers
from saini import build_watermark_filter
from settings import register_settings_handlers
from text_handler import register_text_handlers
from upgrade import register_upgrade_handlers
from youtube_handler import register_youtube_handlers

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize Bot
bot = Client(
    "VSherokuUploaderBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ============================================================
# START COMMAND
# ============================================================
@bot.on_message(filters.command(["start", "help"]))
async def start_handler(client, message: Message):
    buttons = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="setttings")],
        [InlineKeyboardButton("📥 DRM Downloader", callback_data="drm_command")],
        [InlineKeyboardButton("📣 Owner", url=f"tg://user?id={OWNER}")],
    ]
    text = (
        f"👋 Hello [{message.from_user.first_name}](tg://user?id={message.from_user.id})!\n\n"
        f"I’m your advanced **Telegram Video Uploader Bot** with:\n"
        f"• Movable watermark (`Pglinsan`)\n"
        f"• Adjustable CRF compression\n"
        f"• Full DRM downloading support\n\n"
        f"Use `/setcrf 18` to adjust compression quality.\n\n"
        f"🧠 Developed by {CREDIT}"
    )
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# ============================================================
# CRF CONTROL COMMAND
# ============================================================
@bot.on_message(filters.command("setcrf"))
async def set_crf_command(client, message: Message):
    """
    Allows users to set CRF (video compression level).
    CRF range: 8-28 (lower = better quality)
    """
    if len(message.command) < 2:
        await message.reply_text(
            f"🎚️ Current CRF: `{globals.crf_value}`\n\n"
            f"Use `/setcrf 18` to change (8–28 recommended).",
            quote=True,
        )
        return
    try:
        value = int(message.command[1])
        if 8 <= value <= 28:
            globals.crf_value = value
            await message.reply_text(
                f"✅ CRF updated to `{value}`.\n"
                f"Lower → higher quality, larger size.\n"
                f"Higher → smaller size, lower quality."
            )
        else:
            await message.reply_text("⚠️ Please choose a CRF between **8 and 28**.")
    except Exception as e:
        await message.reply_text(f"❌ Invalid value.\nExample: `/setcrf 18`\n\nError: `{str(e)}`")

# ============================================================
# MANUAL WATERMARK COMMAND
# ============================================================
@bot.on_message(filters.command("watermark"))
async def manual_watermark(client, message: Message):
    """
    Allows user to manually watermark a replied video with
    the current watermark settings (movement + CRF).
    """
    reply = message.reply_to_message
    if not reply or not reply.video:
        await message.reply_text("🎥 Reply to a video with `/watermark` to apply watermark.")
        return

    input_path = await reply.download()
    out_path = os.path.splitext(input_path)[0] + "_wm.mp4"

    wm = build_watermark_filter(
        text=globals.vidwatermark if globals.vidwatermark != "/d" else "Pglinsan",
        fontfile="vidwater.ttf",
        movement=globals.watermark_movement,
        speed=globals.watermark_speed,
        fontsize_expr="h/18",
    )
    crf = int(getattr(globals, "crf_value", 23))

    cmd = f'ffmpeg -y -i "{input_path}" -vf "{wm}" -c:v libx264 -preset medium -crf {crf} -c:a copy "{out_path}"'
    await message.reply_text("⚙️ Processing watermark... please wait ⏳")

    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        await message.reply_text(f"❌ FFmpeg error:\n```{stderr.decode()}```")
        return

    await message.reply_video(
        video=out_path,
        caption=(
            f"✅ Watermark applied!\n"
            f"CRF `{crf}` | Movement `{globals.watermark_movement}`"
        ),
        supports_streaming=True,
    )

    os.remove(input_path)
    os.remove(out_path)

# ============================================================
# OTHER COMMANDS / ERROR HANDLER
# ============================================================
@bot.on_message(filters.command("about"))
async def about_command(client, message):
    await message.reply_text(
        f"🤖 **About This Bot**\n\n"
        f"• Developer: {CREDIT}\n"
        f"• Owner ID: `{OWNER}`\n"
        f"• Default CRF: `{globals.crf_value}`\n"
        f"• Watermark: `{globals.vidwatermark}`\n"
        f"• Movement: `{globals.watermark_movement}`",
        disable_web_page_preview=True,
    )

@bot.on_message(filters.command("ping"))
async def ping_command(client, message):
    start = time.time()
    msg = await message.reply_text("🏓 Pinging...")
    end = time.time()
    await msg.edit_text(f"🏓 Pong! `{round((end - start) * 1000)}ms`")

# ============================================================
# REGISTER ALL MODULE HANDLERS
# ============================================================
def register_all_handlers():
    register_authorisation_handlers(bot)
    register_broadcast_handlers(bot)
    register_command_handlers(bot)
    register_drm_handlers(bot)
    register_features_handlers(bot)
    register_html_handlers(bot)
    register_logs_handlers(bot)
    register_settings_handlers(bot)
    register_text_handlers(bot)
    register_upgrade_handlers(bot)
    register_youtube_handlers(bot)

# ============================================================
# STARTUP
# ============================================================
async def main():
    register_all_handlers()
    await bot.start()
    print("🚀 Bot started successfully as", (await bot.get_me()).first_name)
    await idle()

if __name__ == "__main__":
    from pyrogram import idle
    asyncio.get_event_loop().run_until_complete(main())
    

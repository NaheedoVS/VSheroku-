# drm_handler.py
# (c) Pglinsan | Updated by GPT-5
# Integrated movable watermark + CRF compression system
# Compatible with Pyrogram 2.x

import os
import asyncio
import globals
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from saini import build_watermark_filter
from utils import progress_bar
import time


def register_drm_handlers(bot: Client):

    @bot.on_message(filters.command(["drm", "download"]))
    async def drm_downloader(client, message: Message):
        user_id = message.from_user.id
        if len(message.command) < 2:
            await message.reply_text("❗ Usage: `/drm <video_url>`", quote=True)
            return

        url = message.command[1]
        await message.reply_text(f"🔗 Processing DRM URL:\n`{url}`", quote=True)

        # Temporary output folder
        output_path = "downloads"
        output_name = f"drm_{int(time.time())}"

        try:
            # Build ffmpeg postprocessor args dynamically
            if globals.vidwatermark != "/d":
                wm = build_watermark_filter(
                    text=globals.vidwatermark,
                    fontfile="vidwater.ttf",
                    movement=globals.watermark_movement,
                    speed=globals.watermark_speed,
                    fontsize_expr="h/18"
                )
                crf = int(getattr(globals, "crf_value", 18))
                postprocessor = f'--postprocessor-args "ffmpeg:-vf \\"{wm}\\" -c:v libx264 -preset medium -crf {crf} -c:a copy"'
            else:
                postprocessor = ""

            # Command (uses yt-dlp for DRM or normal stream)
            cmd = f'yt-dlp -f "bv+ba/b" -o "{output_path}/{output_name}.%(ext)s" {postprocessor} "{url}"'
            await message.reply_text(f"🎬 Downloading with watermark + CRF...\n\n`{cmd}`")

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                await message.reply_text(f"❌ FFmpeg failed:\n```{stderr.decode()}```")
                return

            final_file = None
            for ext in [".mp4", ".mkv", ".webm"]:
                candidate = os.path.join(output_path, f"{output_name}{ext}")
                if os.path.exists(candidate):
                    final_file = candidate
                    break

            if not final_file:
                await message.reply_text("⚠️ Output file not found after processing.")
                return

            await message.reply_video(
                video=final_file,
                caption=f"✅ Done!\n\nWatermark: `{globals.vidwatermark}`\nMovement: `{globals.watermark_movement}`\nCRF: `{globals.crf_value}`",
                supports_streaming=True,
            )

            # Clean up temp
            try:
                os.remove(final_file)
            except:
                pass

        except Exception as e:
            await message.reply_text(f"❌ Error while processing DRM:\n`{str(e)}`")

    # -----------------------------------------------------------
    # Manual watermark + compression command
    # -----------------------------------------------------------
    @bot.on_message(filters.command("watermark"))
    async def manual_watermark(client, message: Message):
        reply = message.reply_to_message
        if not reply or not reply.video:
            await message.reply_text("🎥 Reply to a video with `/watermark` to apply the moving watermark.")
            return

        input_path = await reply.download()
        out_path = os.path.splitext(input_path)[0] + "_wm.mp4"

        wm = build_watermark_filter(
            text=globals.vidwatermark,
            fontfile="vidwater.ttf",
            movement=globals.watermark_movement,
            speed=globals.watermark_speed,
            fontsize_expr="h/18"
        )
        crf = int(getattr(globals, "crf_value", 18))

        cmd = f'ffmpeg -y -i "{input_path}" -vf "{wm}" -c:v libx264 -preset medium -crf {crf} -c:a copy "{out_path}"'
        await message.reply_text("⚙️ Adding watermark... Please wait.")

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            await message.reply_text(f"❌ FFmpeg failed:\n```{stderr.decode()}```")
            return

        await message.reply_video(
            video=out_path,
            caption=f"✅ Watermark applied!\nCRF `{crf}` | Movement `{globals.watermark_movement}`",
            supports_streaming=True,
        )

        os.remove(input_path)
        os.remove(out_path)
        

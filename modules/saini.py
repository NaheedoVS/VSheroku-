# saini.py (updated portions + helper functions)
import os
import re
import time
import mmap
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import tgcrypto
import subprocess
import concurrent.futures
from math import ceil
from utils import progress_bar
from pyrogram import Client, filters
from pyrogram.types import Message
from io import BytesIO
from pathlib import Path  
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode
import globals
import shlex

# ------ helper: build ffmpeg drawtext filter for watermark (movable) ------
def build_watermark_filter(text: str,
                           fontfile: str = "vidwater.ttf",
                           movement: str = "none",
                           speed: int = 100,
                           fontsize_expr: str = "h/18"):
    """
    Returns a ffmpeg drawtext expression string.
    - text: watermark text
    - fontfile: path to TTF file (vidwater.ttf)
    - movement: 'none' | 'lr' (left->right) | 'tb' (top->bottom)
    - speed: movement speed (units affect expression; typical 50-200)
    - fontsize_expr: expression for fontsize (e.g., h/18)
    """

    # escape single quotes in text for ffmpeg
    safe_text = text.replace("'", r"\'")

    # common drawtext parts
    # font color black, fully opaque
    fontcolor = "black"
    # tw/text_w and th/text_h are ffmpeg metadata variables
    # fontsize use fontsize_expr (string)
    base = f"drawtext=fontfile={fontfile}:text='{safe_text}':fontcolor={fontcolor}:fontsize={fontsize_expr}:box=0:shadowcolor=black@0.0:shadowx=0:shadowy=0"

    if movement == "none":
        # place center or bottom-right depending on globals.watermark_position
        if globals.watermark_position == "bottom-right":
            x_expr = "(w-text_w-10)"
            y_expr = "(h-text_h-10)"
        else:
            x_expr = "(w-text_w)/2"
            y_expr = "(h-text_h)/2"
        vf = f"{base}:x={x_expr}:y={y_expr}"
        return vf

    # movement: use mod(t*speed, w+tw) - tw  (left->right), or similar for top->bottom
    # ffmpeg expression uses 'mod(a,b)'
    # speed controls how many pixels per second (approx).
    if movement == "lr":
        # x moves across width, y centered
        # note: tw is text_w, use 'mod(t*{speed}\, w+tw)-tw'
        x_expr = f"mod(t*{speed}\\, w+text_w)-text_w"
        y_expr = "(h-text_h)/2"
        vf = f"{base}:x={x_expr}:y={y_expr}"
        return vf

    if movement == "tb":
        y_expr = f"mod(t*{speed}\\, h+text_h)-text_h"
        x_expr = "(w-text_w)/2"
        vf = f"{base}:x={x_expr}:y={y_expr}"
        return vf

    # fallback stationary
    x_expr = "(w-text_w)/2"
    y_expr = "(h-text_h)/2"
    vf = f"{base}:x={x_expr}:y={y_expr}"
    return vf

# ------ ffmpeg run helper (async) ------
async def run_cmd_async(cmd: str):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode})\nCMD: {cmd}\nSTDOUT:\n{stdout.decode()}\nSTDERR:\n{stderr.decode()}")
    return stdout.decode(), stderr.decode()

# Example: updated decrypt_and_merge_video (maintains original logic but uses new watermark & crf)
async def decrypt_and_merge_video(mpd_url, keys_string, output_path, output_name, quality="720"):
    try:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        cmd1 = f'yt-dlp -f "bv[height<={quality}]+ba/b" -o "{output_path}/file.%(ext)s" --allow-unplayable-format --no-check-certificate --external-downloader aria2c "{mpd_url}"'
        os.system(cmd1)

        avDir = list(output_path.iterdir())

        # find downloaded video and audio
        video_file = None
        audio_file = None
        for data in avDir:
            if data.suffix in [".mp4", ".mkv", ".webm"] and video_file is None:
                video_file = data
            elif data.suffix in [".m4a", ".mp4", ".aac"] and audio_file is None:
                audio_file = data

        # decrypt if keys_string present (original logic kept)
        if keys_string and video_file:
            # mp4decrypt usage here is from your original; we keep it
            os.system(f'mp4decrypt {keys_string} --show-progress "{video_file}" "{output_path}/video.mp4"')
            if (output_path / "video.mp4").exists():
                video_file.unlink()
                video_file = output_path / "video.mp4"
        if keys_string and audio_file:
            os.system(f'mp4decrypt {keys_string} --show-progress "{audio_file}" "{output_path}/audio.m4a"')
            if (output_path / "audio.m4a").exists():
                audio_file.unlink()
                audio_file = output_path / "audio.m4a"

        if not video_file:
            raise FileNotFoundError("Downloaded video not found.")

        # decide final merge command
        needs_reencode = False
        # if watermark enabled -> we must re-encode to overlay drawtext
        if globals.vidwatermark != "/d":
            needs_reencode = True

        out_file = output_path / f"{output_name}.mp4"

        if needs_reencode:
            # build watermark filter
            wm_filter = build_watermark_filter(
                text=globals.vidwatermark,
                fontfile="vidwater.ttf",
                movement=globals.watermark_movement,
                speed=globals.watermark_speed,
                fontsize_expr="h/18"
            )

            # use globals.crf_value for compression
            crf = int(getattr(globals, "crf_value", 23))
            # Compose ffmpeg command:
            # if audio exists, map it and copy; else include only video
            if audio_file:
                cmd4 = f'ffmpeg -y -i "{video_file}" -i "{audio_file}" -filter_complex "{wm_filter}" -map 0:v -map 1:a -c:v libx264 -preset medium -crf {crf} -c:a copy "{out_file}"'
            else:
                cmd4 = f'ffmpeg -y -i "{video_file}" -vf "{wm_filter}" -c:v libx264 -preset medium -crf {crf} -c:a copy "{out_file}"'

            # synchronous fallback: use os.system (keeps same behavior), but we await via run_cmd_async for error checking
            try:
                await run_cmd_async(cmd4)
            except Exception as e:
                # fallback to os.system and log error
                print("FFmpeg re-encode failed:", e)
                os.system(cmd4)
        else:
            # no watermark -> prefer to copy streams to avoid quality loss
            if audio_file:
                cmd_cp = f'ffmpeg -y -i "{video_file}" -i "{audio_file}" -c copy "{out_file}"'
            else:
                # if single file contains audio+video, just copy
                cmd_cp = f'ffmpeg -y -i "{video_file}" -c copy "{out_file}"'
            os.system(cmd_cp)

        # cleanup temporary files (keep out_file)
        try:
            # remove intermediate files if present
            for f in [video_file, audio_file]:
                if f and Path(f).exists():
                    try:
                        Path(f).unlink()
                    except:
                        pass
        except Exception:
            pass

        if not out_file.exists():
            raise FileNotFoundError("Final output not created by ffmpeg.")

        return str(out_file)

    except Exception as e:
        print(f"Error during decrypt_and_merge_video: {e}")
        raise

# Updated send_vid: applies watermark when necessary and uses crf
async def send_vid(bot: Client, m: Message, cc, filename, vidwatermark, thumb, name, prog, channel_id):
    """
    Example send_vid wrapper — this function expects 'filename' is a path to a video file
    It will create a thumbnail, apply watermark if enabled, compress using globals.crf_value, and send to channel.
    """
    send_file = filename

    try:
        if globals.vidwatermark != "/d":
            # build watermark filter and re-encode
            wm_filter = build_watermark_filter(
                text=globals.vidwatermark,
                fontfile="vidwater.ttf",
                movement=globals.watermark_movement,
                speed=globals.watermark_speed,
                fontsize_expr="h/18"
            )
            crf = int(getattr(globals, "crf_value", 23))
            tmp_out = f"{os.path.splitext(filename)[0]}__wm.mp4"
            if os.path.exists(tmp_out):
                os.remove(tmp_out)

            cmd = f'ffmpeg -y -i "{filename}" -vf "{wm_filter}" -c:v libx264 -preset medium -crf {crf} -c:a copy "{tmp_out}"'
            # run and wait
            try:
                await run_cmd_async(cmd)
            except Exception as e:
                print("Warning: ffmpeg failed:", e)
                # fallback to blocking call
                os.system(cmd)

            if os.path.exists(tmp_out):
                send_file = tmp_out
        else:
            # no watermark -> we may rewrap/copy for safety (no quality loss)
            send_file = filename

        # now send send_file to channel
        # create a thumb if required
        thumb_path = None
        if thumb and thumb != "/d":
            # if remote url, download it
            if thumb.startswith("http"):
                thumb_path = "thumb.jpg"
                os.system(f"wget -q '{thumb}' -O {thumb_path}")
            else:
                thumb_path = thumb

        # use pyrogram to send
        # here we assume channel_id and name are set as in your code logic
        await bot.send_video(
            chat_id=channel_id,
            video=send_file,
            caption=cc,
            thumb=thumb_path if thumb_path else None,
            supports_streaming=True
        )

        # cleanup tmp_out if exists
        if send_file.endswith("__wm.mp4"):
            try:
                os.remove(send_file)
            except:
                pass

    except Exception as e:
        print("send_vid error:", e)
        raise
      

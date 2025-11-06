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
            crf = int(getattr(globals, "crf_value", 18))
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
            crf = int(getattr(globals, "crf_value", 18))
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
                    #  mp4,mkv etc ==== f"({i[1]})" 
                    
                    new_info.update({f'{i[2]}':f'{i[0]}'})

            except:
                pass
    return new_info


async def decrypt_and_merge_video(mpd_url, keys_string, output_path, output_name, quality="720"):
    try:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        cmd1 = f'yt-dlp -f "bv[height<={quality}]+ba/b" -o "{output_path}/file.%(ext)s" --allow-unplayable-format --no-check-certificate --external-downloader aria2c "{mpd_url}"'
        print(f"Running command: {cmd1}")
        os.system(cmd1)
        
        avDir = list(output_path.iterdir())
        print(f"Downloaded files: {avDir}")
        print("Decrypting")

        video_decrypted = False
        audio_decrypted = False

        for data in avDir:
            if data.suffix == ".mp4" and not video_decrypted:
                cmd2 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/video.mp4"'
                print(f"Running command: {cmd2}")
                os.system(cmd2)
                if (output_path / "video.mp4").exists():
                    video_decrypted = True
                data.unlink()
            elif data.suffix == ".m4a" and not audio_decrypted:
                cmd3 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/audio.m4a"'
                print(f"Running command: {cmd3}")
                os.system(cmd3)
                if (output_path / "audio.m4a").exists():
                    audio_decrypted = True
                data.unlink()

        if not video_decrypted or not audio_decrypted:
            raise FileNotFoundError("Decryption failed: video or audio file not found.")

        # Merge video and audio with watermark if enabled
        if globals.vidwatermark != "/d":
            watermark_filter = f"drawtext=fontfile=vidwater.ttf:text='{globals.vidwatermark}':fontcolor=black@0.7:fontsize=h/10:x=(w-text_w)/2:y=(h-text_h)/2"
            cmd4 = f'ffmpeg -i "{output_path}/video.mp4" -i "{output_path}/audio.m4a" -vf "{watermark_filter}" -c:v libx264 -preset ultrafast -crf 23 -c:a copy "{output_path}/{output_name}.mp4"'
        else:
            cmd4 = f'ffmpeg -i "{output_path}/video.mp4" -i "{output_path}/audio.m4a" -c copy "{output_path}/{output_name}.mp4"'
        
        print(f"Running command: {cmd4}")
        os.system(cmd4)
        
        if (output_path / "video.mp4").exists():
            (output_path / "video.mp4").unlink()
        if (output_path / "audio.m4a").exists():
            (output_path / "audio.m4a").unlink()
        
        filename = output_path / f"{output_name}.mp4"

        if not filename.exists():
            raise FileNotFoundError("Merged video file not found.")

        cmd5 = f'ffmpeg -i "{filename}" 2>&1 | grep "Duration"'
        duration_info = os.popen(cmd5).read()
        print(f"Duration info: {duration_info}")

        return str(filename)

    except Exception as e:
        print(f"Error during decryption and merging: {str(e)}")
        raise

async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'

    

def old_download(url, file_name, chunk_size = 1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name


def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"


async def download_video(url,cmd, name):
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter
    print(download_cmd)
    logging.info(download_cmd)
    k = subprocess.run(download_cmd, shell=True)
    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        await download_video(url, cmd, name)
    failed_counter = 0
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"

        return name
    except FileNotFoundError as exc:
        return os.path.isfile.splitext[0] + "." + "mp4"


async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name, channel_id):
    reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
    time.sleep(1)
    start_time = time.time()
    await bot.send_document(ka, caption=cc1)
    count+=1
    await reply.delete (True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3) 


def decrypt_file(file_path, key):  
    if not os.path.exists(file_path): 
        return False  

    with open(file_path, "r+b") as f:  
        num_bytes = min(28, os.path.getsize(file_path))  
        with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:  
            for i in range(num_bytes):  
                mmapped_file[i] ^= ord(key[i]) if i < len(key) else i 
    return True  

async def download_and_decrypt_video(url, cmd, name, key):  
    video_path = await download_video(url, cmd, name)  
    
    if video_path:  
        decrypted = decrypt_file(video_path, key)  
        if decrypted:  
            print(f"File {video_path} decrypted successfully.")  
            return video_path  
        else:  
            print(f"Failed to decrypt {video_path}.")  
            return None  

async def send_vid(bot: Client, m: Message, cc, filename, vidwatermark, thumb, name, prog, channel_id):
    subprocess.run(f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 "{filename}.jpg"', shell=True)
    await prog.delete(True)
    reply1 = await bot.send_message(channel_id, f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>")
    reply = await m.reply_text(f"**Generate Thumbnail:**\n<blockquote>**{name}**</blockquote>")
    
    try:
        if thumb == "/d":
            thumbnail = f"{filename}.jpg"
        else:
            thumbnail = thumb  
        
        # Watermark already applied during download for yt-dlp videos
        # For DRM videos, it's applied in decrypt_and_merge_video
        w_filename = filename
            
    except Exception as e:
        await m.reply_text(str(e))

    dur = int(duration(w_filename))
    start_time = time.time()

    try:
        await bot.send_video(channel_id, w_filename, caption=cc, supports_streaming=True, height=720, width=1280, thumb=thumbnail, duration=dur, progress=progress_bar, progress_args=(reply, start_time))
    except Exception:
        await bot.send_document(channel_id, w_filename, caption=cc, progress=progress_bar, progress_args=(reply, start_time))
    
    os.remove(w_filename)
    await reply.delete(True)
    await reply1.delete(True)
    os.remove(f"{filename}.jpg")

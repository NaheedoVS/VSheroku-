# settings.py
import globals
import random
from pyromod import listen
from pyrogram import Client, filters
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto

def register_settings_handlers(bot):

    @bot.on_callback_query(filters.regex("setttings"))
    async def settings_button(client, callback_query):
        caption = "✨ <b>My Premium BOT Settings Panel</b> ✨"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Caption Style", callback_data="caption_style_command"), InlineKeyboardButton("🖋️ File Name", callback_data="file_name_command")],
            [InlineKeyboardButton("🌅 Thumbnail", callback_data="thummbnail_command")],
            [InlineKeyboardButton("✍️ Add Credit", callback_data="add_credit_command"), InlineKeyboardButton("🔏 Set Token", callback_data="set_token_command")],
            [InlineKeyboardButton("💧 Watermark", callback_data="wattermark_command")],
            [InlineKeyboardButton("📽️ Video Quality", callback_data="quality_command"), InlineKeyboardButton("🏷️ Topic", callback_data="topic_command")],
            [InlineKeyboardButton("🎚️ CRF / Compression", callback_data="crf_command"), InlineKeyboardButton("🔁 Watermark Move", callback_data="wm_move_command")],
            [InlineKeyboardButton("🔄 Reset", callback_data="resset_command")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main_menu")]
        ])
        await callback_query.message.edit_media(
            InputMediaPhoto(
              media="https://envs.sh/GVI.jpg",
              caption=caption
            ),
            reply_markup=keyboard
        )

    # ... existing thumbnail / watermark handlers remain unchanged above ...
    # Add or replace the video watermark handler (so UI sets globals.vidwatermark) - we keep your existing implementation

    @bot.on_callback_query(filters.regex("video_wateermark_command"))
    async def video_watermark(client, callback_query):
        user_id = callback_query.from_user.id
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="wattermark_command")]
        ])
        editable = await callback_query.message.edit(f"**Send Video Watermark text or Send /d**\n\nCurrent: `{globals.vidwatermark}`", reply_markup=keyboard)
        input_msg = await bot.listen(editable.chat.id)
        try:
            if input_msg.text.lower() == "/d":
                globals.vidwatermark = "/d"
                await editable.edit(f"**Video Watermark Disabled ✅** !", reply_markup=keyboard)
            else:
                globals.vidwatermark = input_msg.text
                await editable.edit(f"Video Watermark `{globals.vidwatermark}` enabled ✅!", reply_markup=keyboard)
        except Exception as e:
            await editable.edit(f"<b>❌ Failed to set Watermark:</b>\n<blockquote expandable>{str(e)}</blockquote>", reply_markup=keyboard)
        finally:
            await input_msg.delete()

    # CRF setter
    @bot.on_callback_query(filters.regex("crf_command"))
    async def crf_button(client, callback_query):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="setttings")]])
        editable = await callback_query.message.edit(f"**Send CRF value (8-28) or /d to reset to default (18).**\nCurrent CRF: `{globals.crf_value}`", reply_markup=keyboard)
        input_msg = await bot.listen(editable.chat.id)
        try:
            if input_msg.text.lower() == "/d":
                globals.crf_value = 18
                await editable.edit(f"✅ CRF reset to default (`18`) !", reply_markup=keyboard)
            else:
                try:
                    v = int(input_msg.text.strip())
                    if 8 <= v <= 28:
                        globals.crf_value = v
                        await editable.edit(f"✅ CRF set to `{globals.crf_value}` !", reply_markup=keyboard)
                    else:
                        await editable.edit(f"⚠️ Please provide a value between 8 and 28.", reply_markup=keyboard)
                except:
                    await editable.edit(f"⚠️ Invalid input. Send a number like `18`.", reply_markup=keyboard)
        except Exception as e:
            await editable.edit(f"<b>❌ Failed to set CRF:</b>\n<blockquote expandable>{str(e)}</blockquote>", reply_markup=keyboard)
        finally:
            await input_msg.delete()

    # Watermark movement selector
    @bot.on_callback_query(filters.regex("wm_move_command"))
    async def wm_move_button(client, callback_query):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Stationary", callback_data="wm_move_none"), InlineKeyboardButton("Left→Right", callback_data="wm_move_lr")],
            [InlineKeyboardButton("Top→Bottom", callback_data="wm_move_tb")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="setttings")]
        ])
        await callback_query.message.edit("Choose watermark movement:", reply_markup=keyboard)

    @bot.on_callback_query(filters.regex("wm_move_none"))
    async def wm_move_none(client, callback_query):
        globals.watermark_movement = "none"
        await callback_query.answer("Watermark set to stationary.")
        await callback_query.message.edit(f"Watermark movement: `none` (stationary). Current: `{globals.vidwatermark}`")

    @bot.on_callback_query(filters.regex("wm_move_lr"))
    async def wm_move_lr(client, callback_query):
        globals.watermark_movement = "lr"
        await callback_query.answer("Watermark will move left→right.")
        await callback_query.message.edit(f"Watermark movement: `left→right`. Current: `{globals.vidwatermark}`")

    @bot.on_callback_query(filters.regex("wm_move_tb"))
    async def wm_move_tb(client, callback_query):
        globals.watermark_movement = "tb"
        await callback_query.answer("Watermark will move top→bottom.")
        await callback_query.message.edit(f"Watermark movement: `top→bottom`. Current: `{globals.vidwatermark}`")

    # Additional handler: set watermark speed (pixels per second)
    @bot.on_callback_query(filters.regex("wattermark_command"))
    async def cmd(client, callback_query):
        user_id = callback_query.from_user.id
        first_name = callback_query.from_user.first_name
        caption = f"✨ **Welcome [{first_name}](tg://user?id={user_id})\nChoose Button to set Watermark**"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Video (text)", callback_data="video_wateermark_command"), InlineKeyboardButton("📑 PDF", callback_data="pdf_wateermark_command")],
            [InlineKeyboardButton("⚡ Speed", callback_data="wm_speed_command")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="setttings")]
        ])
        await callback_query.message.edit_media(
            InputMediaPhoto(
              media="https://tinypic.host/images/2025/07/14/file_00000000fc2461fbbdd6bc500cecbff8_conversation_id6874702c-9760-800e-b0bf-8e0bcf8a3833message_id964012ce-7ef5-4ad4-88e0-1c41ed240c03-1-1.jpg",
              caption=caption
            ),
            reply_markup=keyboard
        )

    @bot.on_callback_query(filters.regex("wm_speed_command"))
    async def wm_speed_cmd(client, callback_query):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Watermark", callback_data="wattermark_command")]])
        editable = await callback_query.message.edit(f"**Send watermark speed (integer, default {globals.watermark_speed}). Higher = faster.**", reply_markup=keyboard)
        input_msg = await bot.listen(editable.chat.id)
        try:
            try:
                v = int(input_msg.text.strip())
                if v <= 0:
                    await editable.edit("⚠️ Speed must be > 0", reply_markup=keyboard)
                else:
                    globals.watermark_speed = v
                    await editable.edit(f"✅ Watermark speed set to `{v}` !", reply_markup=keyboard)
            except:
                await editable.edit("⚠️ Invalid input. Send an integer like `100`.", reply_markup=keyboard)
        except Exception as e:
            await editable.edit(f"<b>❌ Failed to set speed:</b>\n<blockquote expandable>{str(e)}</blockquote>", reply_markup=keyboard)
        finally:
            await input_msg.delete()

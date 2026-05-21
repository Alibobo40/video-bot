"""
Telegram Video Yuklab Olish Boti â€” YANGILANGAN 
TikTok, YouTube, Instagram, Twitter va boshqa saytlardan video yuklab oladi.
"""

import os
import logging
import asyncio
from pathlib import Path
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB Telegram cheklov


async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not CHANNEL_USERNAME:
        return True
    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_USERNAME, user_id=user_id
        )
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Obuna tekshirishda xato: {e}")
        return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"Assalomu alaykum, {user.first_name}! ðŸ‘‹\n\n"
        "Men video yuklab olish botiman ðŸŽ¬\n\n"
        "ðŸ“± Qo'llab-quvvatlanadi:\n"
        "â€¢ TikTok âœ…\n"
        "â€¢ Instagram (public) âœ…\n"
        "â€¢ YouTube Shorts âœ…\n"
        "â€¢ Twitter / X âœ…\n"
        "â€¢ Facebook âœ…\n\n"
        "âœ¨ Faqat video havolasini (link) yuboring!\n\n"
        "âš ï¸ Eslatma: 50MB dan katta videolar yuborilmaydi (Telegram cheklovi)"
    )
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "ðŸ“– Qanday foydalanish:\n\n"
        "1ï¸âƒ£ Istalgan video havolasini nusxa oling\n"
        "2ï¸âƒ£ Menga yuboring\n"
        "3ï¸âƒ£ Bir necha soniyada videoni olasiz!\n\n"
        "âŒ Agar video yuklanmasa:\n"
        "â€¢ Video 50MB dan katta bo'lishi mumkin\n"
        "â€¢ Yopiq (private) akkauntdan bo'lishi mumkin\n"
        "â€¢ Havola noto'g'ri bo'lishi mumkin"
    )
    await update.message.reply_text(help_text)


def get_ydl_opts(output_path: str, url: str) -> dict:
    """URL turiga qarab moslangan sozlamalar"""
    opts = {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_FILE_SIZE,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        },
        "retries": 3,
        "fragment_retries": 3,
    }

    if "youtube.com" in url or "youtu.be" in url:
        opts["format"] = "best[height<=720][filesize<50M]/best[filesize<50M]/best[height<=480]/worst"
        # YouTube botblok'ini chetlab o'tish uchun Android client
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "web"],
            }
        }
    elif "instagram.com" in url:
        opts["format"] = "best[filesize<50M]/best"
    elif "tiktok.com" in url:
        opts["format"] = "best[filesize<50M]/best"
    else:
        opts["format"] = "best[filesize<50M]/best[height<=720]/best"

    return opts


def _download(url: str, ydl_opts: dict):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info, None
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"yt-dlp DownloadError: {error_msg}")
        return None, error_msg
    except Exception as e:
        logger.error(f"yt-dlp xatosi: {e}")
        return None, str(e)


async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "âŒ Iltimos, to'g'ri havola yuboring.\n"
            "Masalan: https://www.tiktok.com/..."
        )
        return

    is_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("ðŸ“¢ Kanalga obuna bo'lish", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("âœ… Tekshirish", callback_data="check_sub")],
        ]
        await update.message.reply_text(
            "âš ï¸ Botdan foydalanish uchun avval kanalimizga obuna bo'ling!",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    status_message = await update.message.reply_text("â³ Video yuklanmoqda, kuting...")

    output_template = str(DOWNLOAD_DIR / f"{user_id}_{update.message.message_id}.%(ext)s")
    ydl_opts = get_ydl_opts(output_template, url)

    try:
        loop = asyncio.get_event_loop()
        info, error = await loop.run_in_executor(None, lambda: _download(url, ydl_opts))

        if not info:
            error_text = "âŒ Videoni yuklab bo'lmadi.\n\n"
            if error:
                err_lower = error.lower()
                if "private" in err_lower or "login required" in err_lower:
                    error_text += "ðŸ”’ Bu video yopiq (private) akkauntdan."
                elif "not available" in err_lower or "unavailable" in err_lower or "removed" in err_lower:
                    error_text += "ðŸš« Video mavjud emas yoki o'chirilgan."
                elif "filesize" in err_lower or "too large" in err_lower:
                    error_text += "ðŸ“¦ Video 50MB dan katta â€” Telegram qabul qilmaydi."
                elif "sign in" in err_lower or "confirm you" in err_lower:
                    error_text += "ðŸ¤– YouTube vaqtincha cheklab qo'ydi.\nBoshqa video sinab ko'ring."
                else:
                    error_text += "Boshqa video havolasini sinab ko'ring."
            else:
                error_text += "Boshqa video havolasini sinab ko'ring."
            
            await status_message.edit_text(error_text)
            return

        downloaded_file = None
        for file in DOWNLOAD_DIR.glob(f"{user_id}_{update.message.message_id}.*"):
            downloaded_file = file
            break

        if not downloaded_file or not downloaded_file.exists():
            await status_message.edit_text(
                "âŒ Fayl topilmadi.\n"
                "Video juda katta bo'lishi mumkin (50MB dan ortiq).\n"
                "Qisqaroq video sinab ko'ring."
            )
            return

        file_size = downloaded_file.stat().st_size
        size_mb = file_size / (1024 * 1024)
        
        if file_size > MAX_FILE_SIZE:
            await status_message.edit_text(
                f"âŒ Video juda katta ({size_mb:.1f} MB).\n"
                "Telegram 50MB dan katta fayllarni yubora olmaydi."
            )
            downloaded_file.unlink()
            return

        title = info.get("title", "Video")[:100]
        bot_username = context.bot.username
        caption = f"ðŸŽ¬ {title}\n\nðŸ¤– @{bot_username}"

        await status_message.edit_text(f"ðŸ“¤ Yuborilmoqda... ({size_mb:.1f} MB)")
        
        try:
            with open(downloaded_file, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=caption,
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                )
            await status_message.delete()
        except Exception as send_error:
            logger.error(f"Yuborishda xato: {send_error}")
            try:
                with open(downloaded_file, "rb") as doc_file:
                    await update.message.reply_document(
                        document=doc_file,
                        caption=caption,
                    )
                await status_message.delete()
            except Exception as e2:
                logger.error(f"Document sifatida ham yuborib bo'lmadi: {e2}")
                await status_message.edit_text(
                    "âŒ Videoni yuborib bo'lmadi."
                )

        try:
            downloaded_file.unlink()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Yuklab olishda umumiy xato: {e}", exc_info=True)
        await status_message.edit_text(
            "âŒ Xatolik yuz berdi. Havolani tekshiring yoki keyinroq urinib ko'ring."
        )
        for file in DOWNLOAD_DIR.glob(f"{user_id}_{update.message.message_id}.*"):
            try:
                file.unlink()
            except Exception:
                pass


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    is_subscribed = await check_subscription(user_id, context)
    if is_subscribed:
        await query.edit_message_text("âœ… Rahmat! Endi video havolasini yuboring.")
    else:
        await query.answer("âŒ Hali obuna bo'lmagansiz!", show_alert=True)


def main():
    if not BOT_TOKEN:
        print("âŒ XATO: BOT_TOKEN o'rnatilmagan!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="check_sub"))

    print("ðŸ¤– Bot ishga tushdi! (Yangilangan versiya)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

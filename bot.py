"""
Telegram Video Yuklab Olish Boti — INSTAGRAM YAXSHILANGAN VERSIYA
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
        f"Assalomu alaykum, {user.first_name}! 👋\n\n"
        "Men video yuklab olish botiman 🎬\n\n"
        "📱 Qo'llab-quvvatlanadi:\n"
        "• TikTok ✅\n"
        "• YouTube Shorts ✅\n"
        "• Instagram Reels (public) ✅\n"
        "• Twitter / X ✅\n"
        "• Facebook ✅\n\n"
        "✨ Faqat video havolasini (link) yuboring!\n\n"
        "⚠️ Eslatma: 50MB dan katta videolar yuborilmaydi"
    )
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 Qanday foydalanish:\n\n"
        "1️⃣ Istalgan video havolasini nusxa oling\n"
        "2️⃣ Menga yuboring\n"
        "3️⃣ Bir necha soniyada videoni olasiz!"
    )
    await update.message.reply_text(help_text)


def normalize_instagram_url(url: str) -> str:
    """Instagram URL'ini standart formatga keltiradi"""
    # /reels/ ni /reel/ ga o'zgartirish (yt-dlp ba'zan /reel/ ni yaxshiroq tushunadi)
    url = url.replace("/reels/", "/reel/")
    # Tracking parametrlarni olib tashlash
    if "?" in url:
        url = url.split("?")[0]
    return url


def get_ydl_opts(output_path: str, url: str) -> dict:
    """URL turiga qarab moslangan sozlamalar"""
    opts = {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_FILE_SIZE,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
    }

    if "youtube.com" in url or "youtu.be" in url:
        opts["format"] = "best[height<=720][filesize<50M]/best[filesize<50M]/best[height<=480]/worst"
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "web"],
            }
        }
        opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
    elif "instagram.com" in url:
        # Instagram uchun MAXSUS sozlamalar
        opts["format"] = "best[filesize<50M]/best"
        opts["http_headers"] = {
            # Instagram mobil ilovasidek ko'rinish (ko'proq ishlaydi)
            "User-Agent": "Instagram 219.0.0.12.117 Android",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "X-IG-App-ID": "936619743392459",  # Instagram web app ID
        }
        # Instagram uchun maxsus extractor args
        opts["extractor_args"] = {
            "instagram": {
                "include_stories": ["0"],
            }
        }
    elif "tiktok.com" in url:
        opts["format"] = "best[filesize<50M]/best"
        opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
    else:
        opts["format"] = "best[filesize<50M]/best[height<=720]/best"
        opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }

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
        logger.error(f"yt-dlp xatosi: {e}", exc_info=True)
        return None, str(e)


async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ Iltimos, to'g'ri havola yuboring.\n"
            "Masalan: https://www.tiktok.com/..."
        )
        return

    # Instagram URL'ini normalizatsiya qilish
    if "instagram.com" in url:
        url = normalize_instagram_url(url)
        logger.info(f"Instagram URL normalizatsiya qilindi: {url}")

    is_subscribed = await check_subscription(user_id, context)
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")],
        ]
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun avval kanalimizga obuna bo'ling!",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    status_message = await update.message.reply_text("⏳ Video yuklanmoqda, kuting...")

    output_template = str(DOWNLOAD_DIR / f"{user_id}_{update.message.message_id}.%(ext)s")
    ydl_opts = get_ydl_opts(output_template, url)

    try:
        loop = asyncio.get_event_loop()
        info, error = await loop.run_in_executor(None, lambda: _download(url, ydl_opts))

        # Agar Instagram ishlamasa, qayta urinish — boshqacha sozlamalar bilan
        if not info and "instagram.com" in url:
            logger.info("Instagram birinchi urinish muvaffaqiyatsiz, qayta urinish...")
            # Boshqacha User-Agent bilan urinish
            ydl_opts["http_headers"]["User-Agent"] = (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            )
            info, error = await loop.run_in_executor(None, lambda: _download(url, ydl_opts))

        if not info:
            error_text = "❌ Videoni yuklab bo'lmadi.\n\n"
            if error:
                err_lower = error.lower()
                if "instagram" in url.lower() and ("login" in err_lower or "rate" in err_lower or "empty" in err_lower):
                    error_text += (
                        "🔒 Instagram bu videoni berishni rad etdi.\n\n"
                        "Sabablari:\n"
                        "• Akkaunt yopiq bo'lishi mumkin\n"
                        "• Instagram vaqtincha cheklab qo'ydi\n"
                        "• Story yoki Highlight (qo'llab-quvvatlanmaydi)\n\n"
                        "💡 Qayta urinib ko'ring 5-10 daqiqadan keyin."
                    )
                elif "private" in err_lower or "login required" in err_lower:
                    error_text += "🔒 Bu video yopiq (private) akkauntdan."
                elif "not available" in err_lower or "unavailable" in err_lower or "removed" in err_lower:
                    error_text += "🚫 Video mavjud emas yoki o'chirilgan."
                elif "filesize" in err_lower or "too large" in err_lower:
                    error_text += "📦 Video 50MB dan katta."
                elif "sign in" in err_lower or "confirm you" in err_lower:
                    error_text += "🤖 Sayt vaqtincha cheklab qo'ydi.\nBoshqa video sinab ko'ring."
                else:
                    error_text += f"Boshqa video havolasini sinab ko'ring."
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
                "❌ Fayl topilmadi.\n"
                "Video juda katta bo'lishi mumkin."
            )
            return

        file_size = downloaded_file.stat().st_size
        size_mb = file_size / (1024 * 1024)
        
        if file_size > MAX_FILE_SIZE:
            await status_message.edit_text(
                f"❌ Video juda katta ({size_mb:.1f} MB).\n"
                "Telegram 50MB dan katta fayllarni yubora olmaydi."
            )
            downloaded_file.unlink()
            return

        title = info.get("title", "Video")[:100]
        bot_username = context.bot.username
        caption = f"🎬 {title}\n\n🤖 @{bot_username}"

        await status_message.edit_text(f"📤 Yuborilmoqda... ({size_mb:.1f} MB)")
        
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
                await status_message.edit_text("❌ Videoni yuborib bo'lmadi.")

        try:
            downloaded_file.unlink()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Yuklab olishda umumiy xato: {e}", exc_info=True)
        await status_message.edit_text(
            "❌ Xatolik yuz berdi. Keyinroq urinib ko'ring."
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
        await query.edit_message_text("✅ Rahmat! Endi video havolasini yuboring.")
    else:
        await query.answer("❌ Hali obuna bo'lmagansiz!", show_alert=True)


def main():
    if not BOT_TOKEN:
        print("❌ XATO: BOT_TOKEN o'rnatilmagan!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="check_sub"))

    print("🤖 Bot ishga tushdi! (Instagram yaxshilangan versiya)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

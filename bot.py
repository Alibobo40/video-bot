"""
Telegram Video Yuklab Olish Boti â€” APIFY INSTAGRAM bilan
TikTok, YouTube â€” yt-dlp orqali
Instagram â€” Apify Instagram Scraper API orqali
"""

import os
import logging
import asyncio
from pathlib import Path
import yt_dlp
import httpx
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
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")  # Apify token

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
        "â€¢ YouTube Shorts âœ…\n"
        "â€¢ Instagram Reels âœ…\n"
        "â€¢ Twitter / X âœ…\n"
        "â€¢ Facebook âœ…\n\n"
        "âœ¨ Faqat video havolasini (link) yuboring!"
    )
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "ðŸ“– Qanday foydalanish:\n\n"
        "1ï¸âƒ£ Istalgan video havolasini nusxa oling\n"
        "2ï¸âƒ£ Menga yuboring\n"
        "3ï¸âƒ£ Bir necha soniyada videoni olasiz!"
    )
    await update.message.reply_text(help_text)


# ========== INSTAGRAM uchun APIFY ==========
async def download_instagram_via_apify(url: str) -> tuple:
    """Apify Instagram Scraper orqali video URL'ini olish"""
    if not APIFY_TOKEN:
        return None, "Apify token sozlanmagan"
    
    try:
        # Apify Instagram Scraper actor'ni ishga tushirish
        actor_url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={APIFY_TOKEN}"
        
        payload = {
            "directUrls": [url],
            "resultsType": "posts",
            "resultsLimit": 1,
            "addParentData": False,
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(actor_url, json=payload)
            
            if response.status_code != 200 and response.status_code != 201:
                logger.error(f"Apify javob xato: {response.status_code} - {response.text}")
                return None, f"Apify xato: {response.status_code}"
            
            data = response.json()
            
            if not data or len(data) == 0:
                return None, "Video ma'lumoti topilmadi"
            
            post = data[0]
            
            # Video URL'ini topish
            video_url = post.get("videoUrl") or post.get("videoUrlBackup")
            
            if not video_url:
                # Carousel (album) tekshirish
                if "childPosts" in post and post["childPosts"]:
                    for child in post["childPosts"]:
                        if child.get("videoUrl"):
                            video_url = child["videoUrl"]
                            break
            
            if not video_url:
                return None, "Video URL topilmadi (post rasm bo'lishi mumkin)"
            
            return {
                "video_url": video_url,
                "title": post.get("caption", "Instagram Video")[:100] if post.get("caption") else "Instagram Video",
                "owner": post.get("ownerUsername", ""),
            }, None
            
    except httpx.TimeoutException:
        return None, "Apify javob bermadi (timeout)"
    except Exception as e:
        logger.error(f"Apify Instagram xato: {e}", exc_info=True)
        return None, str(e)


async def download_file_from_url(video_url: str, output_path: Path) -> bool:
    """URL'dan video faylni yuklab olish"""
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("GET", video_url) as response:
                if response.status_code != 200:
                    return False
                
                total_size = 0
                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        total_size += len(chunk)
                        if total_size > MAX_FILE_SIZE:
                            logger.warning("Fayl 50MB dan oshdi")
                            return False
                
                return True
    except Exception as e:
        logger.error(f"Fayl yuklashda xato: {e}")
        return False


# ========== TikTok va YouTube uchun yt-dlp ==========
def get_ydl_opts(output_path: str, url: str) -> dict:
    opts = {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_FILE_SIZE,
        "retries": 3,
        "fragment_retries": 3,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        },
    }

    if "youtube.com" in url or "youtu.be" in url:
        opts["format"] = "best[height<=720][filesize<50M]/best[filesize<50M]/best[height<=480]/worst"
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "web"],
            }
        }
    elif "tiktok.com" in url:
        opts["format"] = "best[filesize<50M]/best"
    else:
        opts["format"] = "best[filesize<50M]/best[height<=720]/best"

    return opts


def _download_with_ytdlp(url: str, ydl_opts: dict):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info, None
    except yt_dlp.utils.DownloadError as e:
        return None, str(e)
    except Exception as e:
        logger.error(f"yt-dlp xatosi: {e}")
        return None, str(e)


# ========== ASOSIY VIDEO YUKLASH ==========
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
    
    downloaded_file = None
    info_data = None
    
    try:
        # ===== INSTAGRAM uchun Apify =====
        if "instagram.com" in url:
            await status_message.edit_text("â³ Instagram'dan yuklanmoqda...")
            
            instagram_data, error = await download_instagram_via_apify(url)
            
            if not instagram_data:
                error_text = "âŒ Instagram videoni yuklab bo'lmadi.\n\n"
                if error:
                    if "rasm" in error.lower() or "post rasm" in error.lower():
                        error_text += "ðŸ“· Bu video emas, balki rasm bo'lishi mumkin."
                    elif "timeout" in error.lower():
                        error_text += "â± Vaqt tugadi, qaytadan urinib ko'ring."
                    else:
                        error_text += f"Sabab: {error}"
                await status_message.edit_text(error_text)
                return
            
            # Video URL'ini olib, faylni yuklash
            output_path = DOWNLOAD_DIR / f"{user_id}_{update.message.message_id}.mp4"
            success = await download_file_from_url(instagram_data["video_url"], output_path)
            
            if not success or not output_path.exists():
                await status_message.edit_text(
                    "âŒ Video faylni yuklab bo'lmadi.\n"
                    "Hajmi katta bo'lishi yoki havola eskirgan bo'lishi mumkin."
                )
                if output_path.exists():
                    output_path.unlink()
                return
            
            downloaded_file = output_path
            info_data = {
                "title": instagram_data["title"],
                "owner": instagram_data["owner"],
            }
        
        # ===== TikTok, YouTube va boshqalar uchun yt-dlp =====
        else:
            ydl_opts = get_ydl_opts(output_template, url)
            loop = asyncio.get_event_loop()
            info, error = await loop.run_in_executor(None, lambda: _download_with_ytdlp(url, ydl_opts))
            
            if not info:
                error_text = "âŒ Videoni yuklab bo'lmadi.\n\n"
                if error:
                    err_lower = error.lower()
                    if "private" in err_lower or "login" in err_lower:
                        error_text += "ðŸ”’ Yopiq (private) akkauntdan."
                    elif "unavailable" in err_lower or "removed" in err_lower:
                        error_text += "ðŸš« Video mavjud emas yoki o'chirilgan."
                    elif "sign in" in err_lower:
                        error_text += "ðŸ¤– Sayt vaqtincha cheklab qo'ydi. Keyinroq urinib ko'ring."
                    else:
                        error_text += "Boshqa video havolasini sinab ko'ring."
                await status_message.edit_text(error_text)
                return
            
            # Fayl yo'lini topish
            for file in DOWNLOAD_DIR.glob(f"{user_id}_{update.message.message_id}.*"):
                downloaded_file = file
                break
            
            if not downloaded_file or not downloaded_file.exists():
                await status_message.edit_text("âŒ Fayl topilmadi. Video katta bo'lishi mumkin.")
                return
            
            info_data = {
                "title": info.get("title", "Video"),
                "owner": info.get("uploader", ""),
            }

        # ===== Faylni yuborish (umumiy qism) =====
        file_size = downloaded_file.stat().st_size
        size_mb = file_size / (1024 * 1024)
        
        if file_size > MAX_FILE_SIZE:
            await status_message.edit_text(
                f"âŒ Video juda katta ({size_mb:.1f} MB).\n"
                "Telegram 50MB dan kattani yubora olmaydi."
            )
            downloaded_file.unlink()
            return

        title = info_data["title"][:100] if info_data["title"] else "Video"
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
                    await update.message.reply_document(document=doc_file, caption=caption)
                await status_message.delete()
            except Exception as e2:
                logger.error(f"Document sifatida ham yuborib bo'lmadi: {e2}")
                await status_message.edit_text("âŒ Videoni yuborib bo'lmadi.")

        try:
            downloaded_file.unlink()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Umumiy xato: {e}", exc_info=True)
        await status_message.edit_text("âŒ Xatolik yuz berdi. Qaytadan urinib ko'ring.")
        # Tozalash
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
    
    if not APIFY_TOKEN:
        print("âš ï¸ OGOHLANTIRISH: APIFY_TOKEN o'rnatilmagan! Instagram ishlamaydi.")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="check_sub"))

    print("ðŸ¤– Bot ishga tushdi! (Apify Instagram bilan)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

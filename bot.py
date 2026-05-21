"""
Telegram Video Yuklab Olish Boti
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
)

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment'dan token olish (Railway'da sozlanadi)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "")  # @kanal_nomi - majburiy obuna uchun

# Vaqtinchalik fayllar uchun papka
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Foydalanuvchi kanalga obuna bo'lganmi tekshiradi"""
    if not CHANNEL_USERNAME:
        return True  # Kanal sozlanmagan bo'lsa, tekshirmaymiz
    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_USERNAME, user_id=user_id
        )
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Obuna tekshirishda xato: {e}")
        return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Boshlash buyrug'i"""
    user = update.effective_user
    welcome_text = (
        f"Assalomu alaykum, {user.first_name}! 👋\n\n"
        "Men video yuklab olish botiman 🎬\n\n"
        "📱 Qo'llab-quvvatlanadi:\n"
        "• TikTok\n"
        "• YouTube (video va Shorts)\n"
        "• Instagram (Reels, post)\n"
        "• Twitter / X\n"
        "• Facebook\n\n"
        "✨ Faqat video havolasini (link) yuboring!"
    )
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yordam buyrug'i"""
    help_text = (
        "📖 Qanday foydalanish:\n\n"
        "1️⃣ Istalgan video havolasini nusxa oling\n"
        "2️⃣ Menga yuboring\n"
        "3️⃣ Bir necha soniyada videoni olasiz!\n\n"
        "❓ Muammo bo'lsa: @sizning_username"
    )
    await update.message.reply_text(help_text)


async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy video yuklash funksiyasi"""
    url = update.message.text.strip()
    user_id = update.effective_user.id

    # Havola tekshiruvi
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text(
            "❌ Iltimos, to'g'ri havola yuboring.\n"
            "Masalan: https://www.tiktok.com/..."
        )
        return

    # Kanalga obunani tekshirish
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

    # "Yuklanmoqda..." xabari
    status_message = await update.message.reply_text("⏳ Video yuklanmoqda, kuting...")

    output_path = DOWNLOAD_DIR / f"{user_id}_{update.message.message_id}.%(ext)s"

    ydl_opts = {
        "format": "best[filesize<50M]/best",  # Telegram 50MB cheklov
        "outtmpl": str(output_path),
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 50 * 1024 * 1024,  # 50MB
    }

    try:
        # Videoni yuklash (alohida thread'da, asyncio'ni bloklamaslik uchun)
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: _download(url, ydl_opts))

        if not info:
            await status_message.edit_text("❌ Videoni yuklab bo'lmadi. Boshqa havola sinab ko'ring.")
            return

        # Fayl yo'lini topish
        downloaded_file = None
        for file in DOWNLOAD_DIR.glob(f"{user_id}_{update.message.message_id}.*"):
            downloaded_file = file
            break

        if not downloaded_file or not downloaded_file.exists():
            await status_message.edit_text("❌ Fayl topilmadi. Qaytadan urinib ko'ring.")
            return

        # Fayl hajmini tekshirish
        file_size = downloaded_file.stat().st_size
        if file_size > 50 * 1024 * 1024:
            await status_message.edit_text(
                "❌ Video juda katta (50MB dan ortiq). Telegram cheklovi tufayli yuborib bo'lmaydi."
            )
            downloaded_file.unlink()
            return

        # Sarlavha
        title = info.get("title", "Video")[:100]
        caption = f"🎬 {title}\n\n🤖 @{context.bot.username}"

        # Videoni yuborish
        await status_message.edit_text("📤 Yuborilmoqda...")
        with open(downloaded_file, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=caption,
                supports_streaming=True,
            )

        await status_message.delete()
        downloaded_file.unlink()  # Faylni o'chirish

    except Exception as e:
        logger.error(f"Yuklab olishda xato: {e}")
        await status_message.edit_text(
            f"❌ Xatolik yuz berdi. Havolani tekshiring yoki keyinroq urinib ko'ring."
        )
        # Yarim yuklangan fayllarni tozalash
        for file in DOWNLOAD_DIR.glob(f"{user_id}_{update.message.message_id}.*"):
            try:
                file.unlink()
            except Exception:
                pass


def _download(url: str, ydl_opts: dict):
    """Sinxron yuklash (executor'da ishlaydi)"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info
    except Exception as e:
        logger.error(f"yt-dlp xatosi: {e}")
        return None


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obunani qayta tekshirish tugmasi"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    is_subscribed = await check_subscription(user_id, context)
    if is_subscribed:
        await query.edit_message_text("✅ Rahmat! Endi video havolasini yuboring.")
    else:
        await query.answer("❌ Hali obuna bo'lmagansiz!", show_alert=True)


def main():
    """Botni ishga tushirish"""
    if not BOT_TOKEN:
        print("❌ XATO: BOT_TOKEN o'rnatilmagan!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Buyruqlar
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Havola yuborilganda
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))

    # Callback (obuna tekshirish)
    from telegram.ext import CallbackQueryHandler
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="check_sub"))

    print("🤖 Bot ishga tushdi!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

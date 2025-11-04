"""
Combined Telegram bot for Wildberries Logistics
Integrates both Ostatki PM and Shipment monitoring functionality
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pickle
import os

from utils.config import BOT_TOKEN, accounts, CHANNEL_ID, REPORT_INTERVAL_MINUTES, OSTATKI_PM_CHANNEL
from utils.message_util import update_message, messages
from ostatki.router import router as ostatki_router
from ostatki.router import show_ostatki_menu, send_scheduled_reports, send_reports_to_group
from shipment.router import router as shipment_router
from shipment.router import show_shipment_menu
from shipment.monitor import stop_all_monitoring
from retentions.router import router as retentions_router
from retentions.scheduler import send_retentions_alerts
from defects.router import router as defects_router
from defects.router import send_defects_to_channel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_combined.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize routers
main_router = Router()

# Add routers to dispatcher
dp.include_router(main_router)
dp.include_router(ostatki_router)
dp.include_router(shipment_router)
dp.include_router(retentions_router)
dp.include_router(defects_router)

# Initialize scheduler
scheduler = AsyncIOScheduler()

# User state storage
users_file = "combined_users.pkl"
users: Dict[int, Dict[str, Any]] = {}

def load_users():
    """Load users data from pickle file"""
    global users
    if os.path.exists(users_file):
        try:
            with open(users_file, "rb") as f:
                users = pickle.load(f)
            logger.info(f"Loaded {len(users)} users from file")
        except Exception as e:
            logger.error(f"Error loading users: {e}")
            users = {}
    else:
        logger.info("No users file found, starting with empty users dict")
        users = {}

def save_users():
    """Save users data to pickle file"""
    try:
        with open(users_file, "wb") as f:
            pickle.dump(users, f)
        logger.info(f"Saved {len(users)} users to file")
    except Exception as e:
        logger.error(f"Error saving users: {e}")

# Keyboard creation functions
def get_main_keyboard() -> InlineKeyboardMarkup:
    """Create main menu keyboard with both bot options"""
    keyboard = [
        [
            InlineKeyboardButton(text="📦 Остатки ПМ", callback_data="menu_ostatki"),
            InlineKeyboardButton(text="🚚 Отгрузки", callback_data="menu_shipment")
        ],
        [
            InlineKeyboardButton(text="⚠️ Удержания", callback_data="retentions_menu"),
            InlineKeyboardButton(text="🔍 Браки", callback_data="defects_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_button() -> InlineKeyboardMarkup:
    """Create a keyboard with just a back button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])

# Command handlers
@main_router.message(Command("start"))
async def cmd_start(message: Message):
    """Handler for the /start command - entry point to the bot"""
    user_id = message.from_user.id

    # Save user info
    users[user_id] = {
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_menu": "main"  # Track current menu for back button functionality
    }
    save_users()

    welcome_text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я бот для работы с Wildberries Логистика. У меня есть четыре основных режима:\n\n"
        "📦 *Остатки ПМ* - мониторинг остатков на пунктах маршрута\n"
        "🚚 *Отгрузки* - отслеживание процесса отгрузки товаров\n"
        "⚠️ *Удержания* - контроль удержаний с таймерами 120 часов\n"
        "🔍 *Браки* - мониторинг браков и претензий от WB\n\n"
        "Выберите нужный режим с помощью кнопок ниже:"
    )

    # Use update_message to send a new message and store its ID
    await update_message(
        bot=message.bot,
        user_id=user_id,
        text=welcome_text,
        reply_markup=get_main_keyboard(),
        message_key="main_menu_id",
        parse_mode=ParseMode.MARKDOWN
    )

# Callback query handlers
@main_router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main_menu(callback: CallbackQuery):
    """Handler for back button - returns to main menu"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    if user_id in users:
        users[user_id]["current_menu"] = "main"
        save_users()  # Save updated user state

    welcome_text = (
        f"Выберите режим работы с Wildberries Логистика:\n\n"
        "📦 *Остатки ПМ* - мониторинг остатков на пунктах маршрута\n"
        "🚚 *Отгрузки* - отслеживание процесса отгрузки товаров\n"
        "⚠️ *Удержания* - контроль удержаний с таймерами 120 часов\n"
        "🔍 *Браки* - мониторинг браков и претензий от WB"
    )

    # Use update_message to update the current message
    await update_message(
        bot=callback.bot,
        user_id=user_id,
        text=welcome_text,
        reply_markup=get_main_keyboard(),
        message_id=message_id,
        message_key="main_menu_id",
        parse_mode=ParseMode.MARKDOWN
    )

@main_router.callback_query(lambda c: c.data == "help")
async def show_help(callback: CallbackQuery):
    """Handler for help button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    if user_id in users:
        users[user_id]["current_menu"] = "help"
        save_users()  # Save updated user state

    help_text = (
        "🔍 *Справка по использованию бота*\n\n"
        "*Основные режимы:*\n\n"
        "📦 *Остатки ПМ* - позволяет:\n"
        "- Получать отчеты по остаткам на пунктах маршрута\n"
        "- Скачивать Excel-отчеты\n"
        "- Настраивать автоматическую отправку отчетов\n"
        "- Добавлять информацию о маршрутах\n\n"
        "🚚 *Отгрузки* - позволяет:\n"
        "- Отслеживать отгрузки в реальном времени\n"
        "- Мониторить прогресс по каждой отгрузке\n"
        "- Получать уведомления о новых отгрузках\n"
        "- Настраивать мониторинг по разным аккаунтам\n\n"
        "*Для начала работы* выберите нужный режим из главного меню."
    )

    # Use update_message to update the current message
    await update_message(
        bot=callback.bot,
        user_id=user_id,
        text=help_text,
        reply_markup=get_back_button(),
        message_id=message_id,
        message_key="main_menu_id",
        parse_mode=ParseMode.MARKDOWN
    )

# Menu selection handlers
@main_router.callback_query(lambda c: c.data == "menu_ostatki")
async def open_ostatki_menu(callback: CallbackQuery):
    """Handler for Ostatki PM menu selection"""
    await callback.answer("Переход в меню 'Остатки ПМ'")

    user_id = callback.from_user.id
    message_id = callback.message.message_id

    if user_id in users:
        users[user_id]["current_menu"] = "ostatki"
        save_users()  # Save updated user state

    # Call the module's function to show the menu
    await show_ostatki_menu(callback.bot, user_id, message_id)

@main_router.callback_query(lambda c: c.data == "menu_shipment")
async def open_shipment_menu(callback: CallbackQuery):
    """Handler for Shipment menu selection"""
    await callback.answer("Переход в меню 'Отгрузки'")

    user_id = callback.from_user.id
    message_id = callback.message.message_id

    if user_id in users:
        users[user_id]["current_menu"] = "shipment"
        save_users()  # Save updated user state

    # Call the module's function to show the menu
    await show_shipment_menu(callback.bot, user_id, message_id)

@main_router.callback_query(lambda c: c.data == "defects_menu")
async def open_defects_menu(callback: CallbackQuery):
    """Handler for Defects menu selection"""
    await callback.answer("Переход в меню 'Браки'")

    # Create defects menu keyboard
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 За последние 30 дней", callback_data="defects_30")],
        [InlineKeyboardButton(text="📅 За последние 7 дней", callback_data="defects_7")],
        [InlineKeyboardButton(text="📈 За последние 3 дня", callback_data="defects_3")],
        [InlineKeyboardButton(text="🔄 За сегодня", callback_data="defects_1")],
        [InlineKeyboardButton(text="📄 Экспорт в CSV", callback_data="defects_export")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
    ])

    await callback.message.edit_text(
        "📊 <b>МОНИТОРИНГ БРАКОВ</b>\n"
        "Выберите период для анализа:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

# Main startup function
async def main():
    """Main function to start the bot"""
    # Load user data
    load_users()

    # Setup scheduler tasks with async wrapper
    def schedule_async(coro):
        """Wrapper to schedule async tasks from sync context"""
        loop = asyncio.get_event_loop()
        return loop.create_task(coro)

    scheduler.add_job(
        lambda: schedule_async(send_scheduled_reports(bot)),
        'interval',
        minutes=REPORT_INTERVAL_MINUTES,
        id='ostatki_scheduled_reports'
    )

    scheduler.add_job(
        lambda: schedule_async(send_reports_to_group(bot)),
        'interval',
        minutes=REPORT_INTERVAL_MINUTES * 2,  # Less frequent for group reports
        id='ostatki_group_reports'
    )

    # Add retentions monitoring task (every 60 minutes)
    scheduler.add_job(
        lambda: schedule_async(send_retentions_alerts(bot)),
        'interval',
        minutes=60,  # Check every hour
        id='retentions_alerts'
    )

    # Add defects monitoring task (every 2 hours)
    scheduler.add_job(
        lambda: schedule_async(send_defects_to_channel(bot)),
        'interval',
        minutes=120,  # Check every 2 hours
        id='defects_alerts'
    )

    # Start scheduler
    scheduler.start()
    logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs")

    # Log startup info
    logger.info("Bot started")
    logger.info(f"Loaded {len(accounts)} accounts")

    try:
        # Start polling
        await dp.start_polling(bot)
    finally:
        # Cleanup on shutdown
        logger.info("Shutting down...")

        # Stop all monitoring tasks
        stop_all_monitoring()

        # Shutdown scheduler
        scheduler.shutdown(wait=False)

        # Close bot session
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())
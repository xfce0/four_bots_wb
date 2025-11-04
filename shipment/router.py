"""
Router for Shipment module
Handles all commands and callbacks for the Shipment functionality
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

from shipment.monitor import (
    start_monitoring,
    stop_monitoring,
    stop_all_monitoring,
    is_monitoring_active
)
from utils.config import accounts, account_monitoring

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = Router()

# Message state storage
messages: Dict[int, Dict[str, Any]] = {}

# Keyboard creation functions
def get_shipment_keyboard() -> InlineKeyboardMarkup:
    """Create Shipment main menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Статус", callback_data="shipment_status"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="shipment_help")
        ],
        [
            InlineKeyboardButton(text="▶️ Запустить мониторинг", callback_data="shipment_start_all")
        ],
        [
            InlineKeyboardButton(text="⏸ Остановить мониторинг", callback_data="shipment_stop_all")
        ],
        [
            InlineKeyboardButton(text="⚙️ Выбрать аккаунты", callback_data="shipment_select_accounts")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_to_shipment_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with back button to Shipment menu"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_shipment")]
    ])

def get_account_selection_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for account selection for monitoring"""
    keyboard = []

    # Add toggle buttons for each account
    for account_id, account_data in accounts.items():
        if account_data['enabled']['shipment']:
            is_active = is_monitoring_active(account_id)
            status_text = "🟢 Включен" if is_active else "⚪ Выключен"
            action = "shipment_stop_account" if is_active else "shipment_start_account"

            keyboard.append([
                InlineKeyboardButton(
                    text=f"{account_data['name']} ({status_text})",
                    callback_data=f"{action}_{account_id}"
                )
            ])

    # Add back button
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_shipment")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Main entry point
async def show_shipment_menu(bot: Bot, user_id: int, message_id: int = None):
    """
    Show Shipment main menu

    Args:
        bot: Bot instance
        user_id: User ID
        message_id: Message ID to update (optional)
    """
    menu_text = (
        "🚚 *Режим Отгрузки*\n\n"
        "Выберите действие из меню ниже:\n\n"
        "📊 *Статус* - текущий статус мониторинга отгрузок\n"
        "❓ *Помощь* - информация о работе с отгрузками\n"
        "▶️ *Запустить мониторинг* - запустить мониторинг всех аккаунтов\n"
        "⏸ *Остановить мониторинг* - остановить мониторинг всех аккаунтов\n"
        "⚙️ *Выбрать аккаунты* - включить/выключить отдельные аккаунты\n"
    )

    if message_id:
        # Update existing message
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=menu_text,
                reply_markup=get_shipment_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error updating Shipment menu: {e}")
            # If update fails, send a new message
            sent_message = await bot.send_message(
                chat_id=user_id,
                text=menu_text,
                reply_markup=get_shipment_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
            messages[user_id] = {"shipment_menu_id": sent_message.message_id}
    else:
        # Send a new message
        sent_message = await bot.send_message(
            chat_id=user_id,
            text=menu_text,
            reply_markup=get_shipment_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        messages[user_id] = {"shipment_menu_id": sent_message.message_id}

# Callback handlers
@router.callback_query(lambda c: c.data == "menu_shipment")
async def callback_shipment_menu(callback: CallbackQuery):
    """Handler for Shipment menu selection from main menu"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Store message ID for future updates
    messages[user_id] = {"shipment_menu_id": message_id}

    await show_shipment_menu(callback.bot, user_id, message_id)

@router.callback_query(lambda c: c.data == "back_to_shipment")
async def callback_back_to_shipment(callback: CallbackQuery):
    """Handler for back button to Shipment menu"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    await show_shipment_menu(callback.bot, user_id, message_id)

@router.callback_query(lambda c: c.data == "shipment_status")
async def callback_shipment_status(callback: CallbackQuery):
    """Handler for status button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Build status message
    status_text = "📊 *Статус мониторинга отгрузок*\n\n"

    any_active = False

    for account_id, account_data in accounts.items():
        if account_data['enabled']['shipment']:
            is_active = is_monitoring_active(account_id)
            status = "🟢 Включен" if is_active else "⚪ Выключен"

            if is_active:
                any_active = True

            status_text += f"*{account_data['name']}*: {status}\n"

    if not any_active:
        status_text += "\n⚠️ *Мониторинг не активен ни для одного аккаунта!*\n"
        status_text += "Нажмите на «Запустить мониторинг» или выберите отдельные аккаунты."
    else:
        status_text += "\n✅ *Мониторинг активен*\n"
        status_text += "Сообщения о новых отгрузках будут отправляться в настроенный канал."

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=status_text,
        reply_markup=get_back_to_shipment_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "shipment_help")
async def callback_shipment_help(callback: CallbackQuery):
    """Handler for help button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    help_text = (
        "❓ *Справка по работе с отгрузками*\n\n"
        "*Мониторинг отгрузок* позволяет в реальном времени отслеживать процесс отгрузки товаров на Wildberries.\n\n"
        "*Основные функции:*\n\n"
        "▶️ *Запустить мониторинг* - начать мониторинг всех включенных аккаунтов\n"
        "⏸ *Остановить мониторинг* - прекратить мониторинг всех аккаунтов\n"
        "⚙️ *Выбрать аккаунты* - включить/выключить мониторинг отдельных аккаунтов\n\n"
        "*Как работает мониторинг:*\n\n"
        "1. Бот проверяет новые отгрузки каждые 60 секунд\n"
        "2. При обнаружении новой отгрузки, создается сообщение с информацией\n"
        "3. Статус отгрузки обновляется каждые 10 секунд в реальном времени\n"
        "4. Когда отгрузка завершается, она перемещается в отдельный топик/канал\n\n"
        "*Сообщения отправляются:*\n"
        "- Активные отгрузки - в основной канал/топик\n"
        "- Завершенные отгрузки - в отдельный топик или второй канал\n\n"
        "⚠️ Для работы мониторинга бот должен быть запущен. Если бот был перезапущен, необходимо заново включить мониторинг."
    )

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=help_text,
        reply_markup=get_back_to_shipment_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "shipment_start_all")
async def callback_shipment_start_all(callback: CallbackQuery):
    """Handler for start all monitoring button"""
    await callback.answer("Запуск мониторинга...")
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Update message to show progress
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text="🔄 Запуск мониторинга для всех аккаунтов...\n\nПожалуйста, подождите.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Start monitoring for all enabled accounts
    started = 0
    already_running = 0
    errors = 0

    for account_id, account_data in accounts.items():
        if account_data['enabled']['shipment']:
            if is_monitoring_active(account_id):
                already_running += 1
                continue

            success = start_monitoring(callback.bot, account_id)
            if success:
                started += 1
            else:
                errors += 1

    # Show result
    result_text = f"✅ *Мониторинг отгрузок запущен*\n\n"

    if started > 0:
        result_text += f"Запущено для {started} аккаунтов\n"

    if already_running > 0:
        result_text += f"Уже запущено для {already_running} аккаунтов\n"

    if errors > 0:
        result_text += f"Ошибки при запуске для {errors} аккаунтов\n"

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=result_text,
        reply_markup=get_back_to_shipment_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "shipment_stop_all")
async def callback_shipment_stop_all(callback: CallbackQuery):
    """Handler for stop all monitoring button"""
    await callback.answer("Остановка мониторинга...")
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Update message to show progress
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text="🔄 Остановка мониторинга для всех аккаунтов...\n\nПожалуйста, подождите.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Stop all monitoring
    stop_all_monitoring()

    # Show result
    result_text = "⏹ *Мониторинг отгрузок остановлен*\n\n"
    result_text += "Мониторинг всех аккаунтов успешно остановлен.\n"
    result_text += "Для возобновления мониторинга нажмите «Запустить мониторинг»."

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=result_text,
        reply_markup=get_back_to_shipment_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "shipment_select_accounts")
async def callback_shipment_select_accounts(callback: CallbackQuery):
    """Handler for select accounts button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Show account selection menu
    accounts_text = (
        "⚙️ *Выбор аккаунтов для мониторинга*\n\n"
        "Нажмите на аккаунт, чтобы включить/выключить его мониторинг:\n\n"
        "🟢 Включен - мониторинг активен\n"
        "⚪ Выключен - мониторинг не активен\n"
    )

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=accounts_text,
        reply_markup=get_account_selection_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data.startswith("shipment_start_account_"))
async def callback_shipment_start_account(callback: CallbackQuery):
    """Handler for start monitoring for specific account"""
    await callback.answer("Запуск мониторинга...")
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Extract account ID from callback data
    account_id = callback.data.replace("shipment_start_account_", "")

    if account_id in accounts and accounts[account_id]['enabled']['shipment']:
        # Start monitoring for the account
        success = start_monitoring(callback.bot, account_id)

        # Update account selection menu
        accounts_text = (
            "⚙️ *Выбор аккаунтов для мониторинга*\n\n"
            "Нажмите на аккаунт, чтобы включить/выключить его мониторинг:\n\n"
            "🟢 Включен - мониторинг активен\n"
            "⚪ Выключен - мониторинг не активен\n"
        )

        if success:
            accounts_text += f"\n✅ Мониторинг для аккаунта *{accounts[account_id]['name']}* успешно запущен."
        else:
            accounts_text += f"\n⚠️ Ошибка запуска мониторинга для аккаунта *{accounts[account_id]['name']}*."

        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=accounts_text,
            reply_markup=get_account_selection_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda c: c.data.startswith("shipment_stop_account_"))
async def callback_shipment_stop_account(callback: CallbackQuery):
    """Handler for stop monitoring for specific account"""
    await callback.answer("Остановка мониторинга...")
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Extract account ID from callback data
    account_id = callback.data.replace("shipment_stop_account_", "")

    if account_id in accounts and accounts[account_id]['enabled']['shipment']:
        # Stop monitoring for the account
        success = stop_monitoring(account_id)

        # Update account selection menu
        accounts_text = (
            "⚙️ *Выбор аккаунтов для мониторинга*\n\n"
            "Нажмите на аккаунт, чтобы включить/выключить его мониторинг:\n\n"
            "🟢 Включен - мониторинг активен\n"
            "⚪ Выключен - мониторинг не активен\n"
        )

        if success:
            accounts_text += f"\n⏹ Мониторинг для аккаунта *{accounts[account_id]['name']}* остановлен."
        else:
            accounts_text += f"\n⚠️ Ошибка остановки мониторинга для аккаунта *{accounts[account_id]['name']}*."

        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=accounts_text,
            reply_markup=get_account_selection_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

# Command handlers
@router.message(Command("monitor"))
async def cmd_monitor(message: Message):
    """Handler for /monitor command"""
    user_id = message.from_user.id

    # Start monitoring for all enabled accounts
    started = 0
    already_running = 0
    errors = 0

    for account_id, account_data in accounts.items():
        if account_data['enabled']['shipment']:
            if is_monitoring_active(account_id):
                already_running += 1
                continue

            success = start_monitoring(message.bot, account_id)
            if success:
                started += 1
            else:
                errors += 1

    # Show result
    result_text = f"✅ *Мониторинг отгрузок запущен*\n\n"

    if started > 0:
        result_text += f"Запущено для {started} аккаунтов\n"

    if already_running > 0:
        result_text += f"Уже запущено для {already_running} аккаунтов\n"

    if errors > 0:
        result_text += f"Ошибки при запуске для {errors} аккаунтов\n"

    await message.answer(result_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("stop"))
async def cmd_stop(message: Message):
    """Handler for /stop command"""
    user_id = message.from_user.id

    # Stop all monitoring
    stop_all_monitoring()

    # Show result
    result_text = "⏹ *Мониторинг отгрузок остановлен*\n\n"
    result_text += "Мониторинг всех аккаунтов успешно остановлен.\n"
    result_text += "Для возобновления мониторинга используйте команду /monitor или нажмите «Запустить мониторинг» в меню."

    await message.answer(result_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("status"))
async def cmd_status(message: Message):
    """Handler for /status command"""
    user_id = message.from_user.id

    # Build status message
    status_text = "📊 *Статус мониторинга отгрузок*\n\n"

    any_active = False

    for account_id, account_data in accounts.items():
        if account_data['enabled']['shipment']:
            is_active = is_monitoring_active(account_id)
            status = "🟢 Включен" if is_active else "⚪ Выключен"

            if is_active:
                any_active = True

            status_text += f"*{account_data['name']}*: {status}\n"

    if not any_active:
        status_text += "\n⚠️ *Мониторинг не активен ни для одного аккаунта!*\n"
        status_text += "Используйте команду /monitor для запуска мониторинга."
    else:
        status_text += "\n✅ *Мониторинг активен*\n"
        status_text += "Сообщения о новых отгрузках отправляются в настроенный канал."

    await message.answer(status_text, parse_mode=ParseMode.MARKDOWN)
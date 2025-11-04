"""
Router module for retentions functionality
"""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import Command

from utils.config import accounts
from retentions.api import (
    get_retentions_data,
    merge_retentions_with_drivers,
    get_retention_timers
)
from retentions.formatter import (
    format_retentions_report,
    format_timers_report,
    format_retention_summary
)

logger = logging.getLogger(__name__)
router = Router(name="retentions")


async def get_retentions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """
    Create keyboard for retentions accounts selection

    Args:
        user_id: Telegram user ID

    Returns:
        InlineKeyboardMarkup with account buttons
    """
    buttons = []

    # Add buttons for each account with retentions capability
    for account_id, account_data in accounts.items():
        if account_data.get('retentions', {}).get('enabled'):
            account_name = account_data['name']
            buttons.append([
                InlineKeyboardButton(
                    text=f"📊 {account_name}",
                    callback_data=f"retention_report_{account_id}"
                )
            ])

    # Add check all button
    if len(buttons) > 1:
        buttons.append([
            InlineKeyboardButton(
                text="🔍 Проверить все аккаунты",
                callback_data="retention_check_all"
            )
        ])

    # Add timers button
    buttons.append([
        InlineKeyboardButton(
            text="⏱ Показать таймеры",
            callback_data="retention_timers"
        )
    ])

    # Add back button
    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Назад в главное меню",
            callback_data="back_to_main"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("retentions"))
async def cmd_retentions(message: Message):
    """Handler for /retentions command"""
    try:
        user_id = message.from_user.id
        keyboard = await get_retentions_keyboard(user_id)

        await message.answer(
            "🔍 *Мониторинг удержаний*\n\n"
            "Выберите аккаунт для проверки возможных удержаний:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Error in /retentions command: {e}")
        await message.answer(
            "🚫 Произошла ошибка при открытии меню удержаний",
            parse_mode=ParseMode.MARKDOWN
        )


@router.callback_query(F.data == "retentions_menu")
async def callback_retentions_menu(callback: CallbackQuery):
    """Handler for retentions menu callback"""
    try:
        await callback.answer()
        user_id = callback.from_user.id
        keyboard = await get_retentions_keyboard(user_id)

        await callback.message.edit_text(
            "🔍 *Мониторинг удержаний*\n\n"
            "Выберите аккаунт для проверки возможных удержаний:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Error in retentions menu callback: {e}")
        await callback.answer("Ошибка при открытии меню", show_alert=True)


@router.callback_query(F.data.startswith("retention_report_"))
async def callback_retention_report(callback: CallbackQuery):
    """Handler for single account retention report"""
    try:
        await callback.answer("Загружаю данные об удержаниях...")
        user_id = callback.from_user.id
        message_id = callback.message.message_id

        # Extract account ID from callback data
        account_id = callback.data.replace("retention_report_", "")

        if account_id not in accounts:
            await callback.answer("Аккаунт не найден", show_alert=True)
            return

        account_data = accounts[account_id]

        # Check if retentions are enabled for this account
        if not account_data.get('retentions', {}).get('enabled'):
            await callback.answer("Удержания не настроены для этого аккаунта", show_alert=True)
            return

        retentions_config = account_data['retentions']
        token = retentions_config.get('token')
        supplier_id = retentions_config.get('supplier_id')

        if not token or not supplier_id:
            await callback.answer("Не настроен токен или supplier_id", show_alert=True)
            return

        account_name = account_data['name']

        # Update message to show loading
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=f"🔄 Загрузка данных об удержаниях для *{account_name}*...\n\n"
                 f"Это может занять некоторое время.",
            parse_mode=ParseMode.MARKDOWN
        )

        # Get retentions data
        retentions_data = get_retentions_data(token, supplier_id)

        if not retentions_data:
            await callback.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=f"✅ *{account_name}*\n\n"
                     f"Удержания не найдены!",
                parse_mode=ParseMode.MARKDOWN
            )

            # Add back button
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="retentions_menu"
                )
            ]])

            await callback.bot.edit_message_reply_markup(
                chat_id=user_id,
                message_id=message_id,
                reply_markup=keyboard
            )
            return

        # Update status - getting driver info
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=f"🔄 Получение информации о водителях для *{account_name}*...\n\n"
                 f"Найдено удержаний: {len(retentions_data)}",
            parse_mode=ParseMode.MARKDOWN
        )

        # Merge with driver info
        merged_retentions = merge_retentions_with_drivers(retentions_data, token)

        # Format report
        formatted_text = format_retentions_report(merged_retentions, account_name)

        # Send formatted report as new message (too long for edit)
        await callback.bot.send_message(
            chat_id=user_id,
            text=formatted_text,
            parse_mode=ParseMode.MARKDOWN
        )

        # Update original message
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=f"✅ Отчет об удержаниях для *{account_name}* отправлен выше",
            parse_mode=ParseMode.MARKDOWN
        )

        # Add back button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⬅️ Назад к списку аккаунтов",
                callback_data="retentions_menu"
            )
        ]])

        await callback.bot.edit_message_reply_markup(
            chat_id=user_id,
            message_id=message_id,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error in retention report callback: {e}")
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data == "retention_check_all")
async def callback_retention_check_all(callback: CallbackQuery):
    """Handler for checking all accounts for retentions"""
    try:
        await callback.answer("Проверяю все аккаунты...")
        user_id = callback.from_user.id
        message_id = callback.message.message_id

        # Get all accounts with retentions enabled
        retention_accounts = [
            (acc_id, acc_data)
            for acc_id, acc_data in accounts.items()
            if acc_data.get('retentions', {}).get('enabled')
        ]

        if not retention_accounts:
            await callback.answer("Нет аккаунтов с настроенными удержаниями", show_alert=True)
            return

        # Update message
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=f"🔄 Проверка удержаний по всем аккаунтам...\n\n"
                 f"Аккаунтов для проверки: {len(retention_accounts)}",
            parse_mode=ParseMode.MARKDOWN
        )

        # Check each account
        results = []
        for i, (account_id, account_data) in enumerate(retention_accounts, 1):
            account_name = account_data['name']

            # Update progress
            await callback.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=f"🔄 Проверка удержаний...\n\n"
                     f"Обработка: {account_name} ({i}/{len(retention_accounts)})",
                parse_mode=ParseMode.MARKDOWN
            )

            retentions_config = account_data['retentions']
            token = retentions_config.get('token')
            supplier_id = retentions_config.get('supplier_id')

            if not token or not supplier_id:
                results.append(f"❌ {account_name}: Не настроен")
                continue

            # Get retentions data
            retentions_data = get_retentions_data(token, supplier_id)

            if retentions_data:
                # Count lost tares
                total_lost = sum(
                    len([t for t in item.get('tares', []) if t.get('status') == 'TARE_STATUS_LOST'])
                    for item in retentions_data
                )
                total_amount = sum(
                    t.get('price', 0)
                    for item in retentions_data
                    for t in item.get('tares', [])
                    if t.get('status') == 'TARE_STATUS_LOST'
                )

                results.append(
                    f"⚠️ *{account_name}*:\n"
                    f"   • Путевых листов: {len(retentions_data)}\n"
                    f"   • Потерянных тар: {total_lost}\n"
                    f"   • Сумма: {total_amount} ₽"
                )
            else:
                results.append(f"✅ {account_name}: Удержаний нет")

        # Format summary
        summary = "📊 *Сводка по всем аккаунтам:*\n\n" + "\n\n".join(results)

        # Send summary
        await callback.bot.send_message(
            chat_id=user_id,
            text=summary,
            parse_mode=ParseMode.MARKDOWN
        )

        # Update original message
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="✅ Проверка всех аккаунтов завершена",
            parse_mode=ParseMode.MARKDOWN
        )

        # Add back button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⬅️ Назад к списку аккаунтов",
                callback_data="retentions_menu"
            )
        ]])

        await callback.bot.edit_message_reply_markup(
            chat_id=user_id,
            message_id=message_id,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error in check all callback: {e}")
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data == "retention_timers")
async def callback_retention_timers(callback: CallbackQuery):
    """Handler for showing retention timers"""
    try:
        await callback.answer("Получаю информацию о таймерах...")
        user_id = callback.from_user.id
        message_id = callback.message.message_id

        # Get all accounts with retentions enabled
        retention_accounts = [
            (acc_id, acc_data)
            for acc_id, acc_data in accounts.items()
            if acc_data.get('retentions', {}).get('enabled')
        ]

        if not retention_accounts:
            await callback.answer("Нет аккаунтов с настроенными удержаниями", show_alert=True)
            return

        # Update message
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="🔄 Получение информации о таймерах удержаний...",
            parse_mode=ParseMode.MARKDOWN
        )

        # Collect timers from all accounts
        all_timers = []
        for account_id, account_data in retention_accounts:
            retentions_config = account_data['retentions']
            token = retentions_config.get('token')
            supplier_id = retentions_config.get('supplier_id')

            if token and supplier_id:
                account_timers = get_retention_timers(token, supplier_id)
                if account_timers:
                    all_timers.append({
                        'account_id': account_id,
                        'account_name': account_data['name'],
                        'timers': account_timers
                    })

        if not all_timers:
            await callback.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text="✅ Нет активных таймеров удержаний",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Format timers report
            formatted_text = format_timers_report(all_timers)

            # Send report
            await callback.bot.send_message(
                chat_id=user_id,
                text=formatted_text,
                parse_mode=ParseMode.MARKDOWN
            )

            # Update original message
            await callback.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text="✅ Информация о таймерах отправлена выше",
                parse_mode=ParseMode.MARKDOWN
            )

        # Add back button
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⬅️ Назад к списку аккаунтов",
                callback_data="retentions_menu"
            )
        ]])

        await callback.bot.edit_message_reply_markup(
            chat_id=user_id,
            message_id=message_id,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error in timers callback: {e}")
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


# Scheduled check function (can be called from scheduler)
async def check_retentions_scheduled():
    """
    Scheduled function to check retentions for all accounts
    This can be called from external scheduler
    """
    try:
        logger.info("Starting scheduled retentions check")

        # Get all accounts with retentions enabled
        retention_accounts = [
            (acc_id, acc_data)
            for acc_id, acc_data in accounts.items()
            if acc_data.get('retentions', {}).get('enabled')
        ]

        if not retention_accounts:
            logger.info("No accounts with retentions configured")
            return []

        results = []
        for account_id, account_data in retention_accounts:
            try:
                retentions_config = account_data['retentions']
                token = retentions_config.get('token')
                supplier_id = retentions_config.get('supplier_id')

                if not token or not supplier_id:
                    logger.warning(f"Account {account_id} missing token or supplier_id")
                    continue

                # Get retentions data
                retentions_data = get_retentions_data(token, supplier_id)

                if retentions_data:
                    # Merge with driver info
                    merged_retentions = merge_retentions_with_drivers(retentions_data, token)

                    results.append({
                        'account_id': account_id,
                        'account_name': account_data['name'],
                        'retentions': merged_retentions
                    })

                    logger.info(f"Found {len(retentions_data)} retentions for {account_id}")
                else:
                    logger.info(f"No retentions found for {account_id}")

            except Exception as e:
                logger.error(f"Error checking retentions for {account_id}: {e}")
                continue

        return results

    except Exception as e:
        logger.error(f"Error in scheduled retentions check: {e}")
        return []
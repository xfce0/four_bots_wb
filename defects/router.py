"""Router for defects monitoring functionality"""

import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from .api import get_all_defects_data, get_defects_data
from .formatter import (
    format_defects_summary,
    format_defects_list,
    format_defects_for_channel,
    create_excel_content
)
from utils.config import accounts

logger = logging.getLogger(__name__)

router = Router(name='defects')


@router.message(F.text == "🔍 Браки")
async def handle_defects_menu(message: Message, state: FSMContext):
    """Handle main defects menu"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 За последние 30 дней", callback_data="defects_30")],
        [InlineKeyboardButton(text="📅 За последние 7 дней", callback_data="defects_7")],
        [InlineKeyboardButton(text="📈 За последние 3 дня", callback_data="defects_3")],
        [InlineKeyboardButton(text="🔄 За сегодня", callback_data="defects_1")],
        [InlineKeyboardButton(text="📄 Экспорт в Excel", callback_data="defects_export")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

    await message.answer(
        "📊 <b>МОНИТОРИНГ БРАКОВ</b>\n"
        "Выберите период для анализа:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("defects_"))
async def handle_defects_callback(callback: CallbackQuery, state: FSMContext):
    """Handle defects callback queries"""
    # Parse callback data: can be "defects_3", "defects_export", or "defects_export_3"
    parts = callback.data.split("_")
    action = parts[1]  # "3", "7", "export", etc.

    # Check if there's a days parameter (for "defects_export_3" format)
    if len(parts) > 2:
        try:
            days = int(parts[2])
        except ValueError:
            days = 30  # Default if parsing fails
    else:
        # Determine the period from action
        days_map = {
            "30": 30,
            "7": 7,
            "3": 3,
            "1": 1,
            "export": 30  # Default for export without days parameter
        }
        days = days_map.get(action, 30)

    # Answer callback immediately to prevent timeout
    await callback.answer()

    # Edit message to show initial loading status
    await callback.message.edit_text(
        "⏳ <b>Загрузка данных о браках...</b>\n"
        "Пожалуйста, подождите...",
        parse_mode="HTML"
    )

    # Create progress callback
    last_update_time = [0]  # Use list to make it mutable in nested function

    async def progress_callback(current: int, total: int, account_name: str):
        """Update message with current progress"""
        import time
        # Only update every 2 seconds to avoid rate limits
        current_time = time.time()
        if current_time - last_update_time[0] < 2 and current < total:
            return

        last_update_time[0] = current_time

        try:
            progress_text = (
                "⏳ <b>Загрузка информации о водителях...</b>\n\n"
                f"📦 Кабинет: {account_name}\n"
                f"📊 Обработано: <b>{current}</b> из <b>{total}</b> путевых листов\n"
                f"⚡️ Прогресс: {int(current * 100 / total)}%"
            )
            await callback.message.edit_text(progress_text, parse_mode="HTML")
        except Exception as e:
            logger.debug(f"Failed to update progress message: {e}")

    # Get defects data from all accounts with progress tracking
    all_defects = await get_all_defects_data(days, progress_callback=progress_callback)

    if not all_defects or not any(all_defects.values()):
        await callback.message.edit_text(
            f"📊 <b>Нет данных о браках за последние {days} дней</b>",
            parse_mode="HTML"
        )
        return

    if action == "export":
        # Export to Excel
        await export_defects_excel(callback, all_defects)
    else:
        # Show summary and list
        await show_defects_summary(callback, all_defects, days)


async def show_defects_summary(callback: CallbackQuery, all_defects: Dict[str, List[Dict[str, Any]]], days: int):
    """Show defects summary"""
    # Format summary
    summary = format_defects_summary(all_defects)

    # Add back button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Экспорт в Excel", callback_data=f"defects_export_{days}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="defects_menu")]
    ])

    await callback.message.edit_text(
        summary,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def export_defects_excel(callback: CallbackQuery, all_defects: Dict[str, List[Dict[str, Any]]]):
    """Export defects to Excel file"""
    try:
        # Combine all defects
        all_defects_list = []
        for account_id, defects in all_defects.items():
            all_defects_list.extend(defects)

        if not all_defects_list:
            await callback.answer("Нет данных для экспорта", show_alert=True)
            return

        # Create Excel content
        excel_bytes = create_excel_content(all_defects_list)

        # Create file
        filename = f"defects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        # Send file
        document = BufferedInputFile(excel_bytes, filename=filename)
        await callback.message.answer_document(
            document,
            caption=f"📄 Экспорт браков в Excel\nВсего записей: {len(all_defects_list)}"
        )

        await callback.answer("Файл создан")

    except Exception as e:
        logger.error(f"Error exporting defects: {e}")
        await callback.answer("Ошибка при создании файла", show_alert=True)


@router.callback_query(F.data == "defects_menu")
async def handle_back_to_defects_menu(callback: CallbackQuery, state: FSMContext):
    """Handle back to defects menu"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 За последние 30 дней", callback_data="defects_30")],
        [InlineKeyboardButton(text="📅 За последние 7 дней", callback_data="defects_7")],
        [InlineKeyboardButton(text="📈 За последние 3 дня", callback_data="defects_3")],
        [InlineKeyboardButton(text="🔄 За сегодня", callback_data="defects_1")],
        [InlineKeyboardButton(text="📄 Экспорт в Excel", callback_data="defects_export")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

    await callback.message.edit_text(
        "📊 <b>МОНИТОРИНГ БРАКОВ</b>\n"
        "Выберите период для анализа:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def send_defects_to_channel(bot):
    """Send active defects to channel (scheduled task)"""
    try:
        # Get defects data for last 7 days
        all_defects = await get_all_defects_data(days=7)

        if not all_defects or not any(all_defects.values()):
            logger.info("No defects to send to channel")
            return

        # Format messages for channel
        messages = format_defects_for_channel(all_defects)

        # Get channel ID and topic from config
        channel_id = -1002900008388  # As specified by user
        topic_id = 7  # As specified by user

        # Send messages
        for message_text in messages:
            try:
                await bot.send_message(
                    chat_id=channel_id,
                    text=message_text,
                    parse_mode="HTML",
                    message_thread_id=topic_id  # For forum topics
                )
            except Exception as e:
                # Try without topic if it fails
                logger.warning(f"Failed to send with topic, trying without: {e}")
                try:
                    await bot.send_message(
                        chat_id=channel_id,
                        text=message_text,
                        parse_mode="HTML"
                    )
                except Exception as e2:
                    logger.error(f"Failed to send defects to channel: {e2}")

        logger.info(f"Sent {len(messages)} defects messages to channel")

    except Exception as e:
        logger.error(f"Error in send_defects_to_channel: {e}")


# Export function for scheduler
__all__ = ['router', 'send_defects_to_channel']
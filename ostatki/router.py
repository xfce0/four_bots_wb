"""
Router for Ostatki PM module
Handles all commands and callbacks for the Ostatki PM functionality
"""
import logging
from datetime import datetime
from typing import Dict, Any, List

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.enums import ParseMode

from ostatki.api import get_wb_report, create_excel_from_json
from ostatki.formatter import format_last_mile_text
from ostatki.data import add_route, get_routes, save_routes
from utils.config import accounts, OSTATKI_PM_CHANNEL

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = Router()

# Message state storage
messages: Dict[int, Dict[str, Any]] = {}
subscription_status: Dict[int, bool] = {}

# Keyboard creation functions
def get_ostatki_keyboard() -> InlineKeyboardMarkup:
    """Create Ostatki PM main menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Получить отчет", callback_data="ostatki_get_report"),
            InlineKeyboardButton(text="📎 Скачать Excel", callback_data="ostatki_get_excel"),
        ],
        [
            InlineKeyboardButton(text="🔔 Подписаться", callback_data="ostatki_subscribe"),
            InlineKeyboardButton(text="🔕 Отписаться", callback_data="ostatki_unsubscribe"),
        ],
        [
            InlineKeyboardButton(text="📝 Добавить маршрут", callback_data="ostatki_add_route"),
            InlineKeyboardButton(text="📋 Список маршрутов", callback_data="ostatki_list_routes"),
        ],
        [
            InlineKeyboardButton(text="📤 Отправить в канал", callback_data="ostatki_send_to_group"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_to_ostatki_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard with back button to Ostatki menu"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_ostatki")]
    ])

def get_account_selection_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    """
    Create keyboard for account selection

    Args:
        callback_prefix: Prefix for callback data (e.g., "ostatki_report_")

    Returns:
        Keyboard with account selection buttons
    """
    keyboard = []
    row = []

    # Add enabled accounts
    for i, (account_id, account_data) in enumerate(accounts.items()):
        if account_data['enabled']['ostatki']:
            # Create rows with 2 buttons each
            if i % 2 == 0 and row:
                keyboard.append(row)
                row = []

            row.append(
                InlineKeyboardButton(
                    text=account_data['name'],
                    callback_data=f"{callback_prefix}{account_id}"
                )
            )

    # Add the last row if not empty
    if row:
        keyboard.append(row)

    # Add back button
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_ostatki")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Main entry point
async def show_ostatki_menu(bot: Bot, user_id: int, message_id: int = None):
    """
    Show Ostatki PM main menu

    Args:
        bot: Bot instance
        user_id: User ID
        message_id: Message ID to update (optional)
    """
    menu_text = (
        "📦 *Режим Остатки ПМ*\n\n"
        "Выберите действие из меню ниже:\n\n"
        "📊 *Получить отчет* - текстовый отчет по остаткам\n"
        "📎 *Скачать Excel* - выгрузка в формате Excel\n"
        "🔔 *Подписаться* - автоматическая отправка отчетов\n"
        "🔕 *Отписаться* - отмена подписки\n"
        "📝 *Добавить маршрут* - настройка данных по маршруту\n"
        "📋 *Список маршрутов* - просмотр настроенных маршрутов\n"
        "📤 *Отправить в канал* - отправить отчеты в настроенный канал\n"
    )

    if message_id:
        # Update existing message
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=menu_text,
                reply_markup=get_ostatki_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error updating Ostatki menu: {e}")
            # If update fails, send a new message
            sent_message = await bot.send_message(
                chat_id=user_id,
                text=menu_text,
                reply_markup=get_ostatki_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
            messages[user_id] = {"ostatki_menu_id": sent_message.message_id}
    else:
        # Send a new message
        sent_message = await bot.send_message(
            chat_id=user_id,
            text=menu_text,
            reply_markup=get_ostatki_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        messages[user_id] = {"ostatki_menu_id": sent_message.message_id}

# Callback handlers
@router.callback_query(lambda c: c.data == "menu_ostatki")
async def callback_ostatki_menu(callback: CallbackQuery):
    """Handler for Ostatki PM menu selection from main menu"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Store message ID for future updates
    messages[user_id] = {"ostatki_menu_id": message_id}

    await show_ostatki_menu(callback.bot, user_id, message_id)

@router.callback_query(lambda c: c.data == "back_to_ostatki")
async def callback_back_to_ostatki(callback: CallbackQuery):
    """Handler for back button to Ostatki menu"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    await show_ostatki_menu(callback.bot, user_id, message_id)

@router.callback_query(lambda c: c.data == "ostatki_get_report")
async def callback_ostatki_get_report(callback: CallbackQuery):
    """Handler for get report button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Show account selection keyboard
    account_selection_text = (
        "📊 *Получение отчета Остатки ПМ*\n\n"
        "Выберите аккаунт для получения отчета:"
    )

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=account_selection_text,
        reply_markup=get_account_selection_keyboard("ostatki_report_"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data.startswith("ostatki_report_"))
async def callback_ostatki_report_account(callback: CallbackQuery):
    """Handler for account selection for report"""
    await callback.answer("Загружаю отчет...")
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Extract account ID from callback data
    account_id = callback.data.replace("ostatki_report_", "")

    if account_id in accounts and accounts[account_id]['enabled']['ostatki']:
        account_data = accounts[account_id]
        token = account_data['ostatki']['token']
        account_name = account_data['name']
        office_id = account_data['ostatki']['office_id']

        # Update message to show loading
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=f"🔄 Загрузка отчета для аккаунта *{account_name}*...\n\nПожалуйста, подождите.",
            parse_mode=ParseMode.MARKDOWN
        )

        # Get report data
        report_data = get_wb_report(token, office_id)

        if report_data:
            # Format report
            formatted_text = format_last_mile_text(report_data, account_name, account_id)

            # Send formatted report
            await callback.bot.send_message(
                chat_id=user_id,
                text=formatted_text,
                parse_mode=ParseMode.MARKDOWN
            )

            # Return to Ostatki menu
            await show_ostatki_menu(callback.bot, user_id, message_id)
        else:
            # Show error and return to Ostatki menu
            await callback.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=f"❌ Ошибка при получении отчета для аккаунта *{account_name}*.",
                reply_markup=get_back_to_ostatki_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        # Invalid account, return to Ostatki menu
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ Ошибка: выбран недоступный аккаунт.",
            reply_markup=get_back_to_ostatki_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda c: c.data == "ostatki_get_excel")
async def callback_ostatki_get_excel(callback: CallbackQuery):
    """Handler for get Excel report button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Show account selection keyboard
    account_selection_text = (
        "📎 *Скачать Excel-отчет Остатки ПМ*\n\n"
        "Выберите аккаунт для получения Excel-отчета:"
    )

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=account_selection_text,
        reply_markup=get_account_selection_keyboard("ostatki_excel_"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data.startswith("ostatki_excel_"))
async def callback_ostatki_excel_account(callback: CallbackQuery):
    """Handler for account selection for Excel report"""
    await callback.answer("Загружаю Excel-отчет...")
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Extract account ID from callback data
    account_id = callback.data.replace("ostatki_excel_", "")

    if account_id in accounts and accounts[account_id]['enabled']['ostatki']:
        account_data = accounts[account_id]
        token = account_data['ostatki']['token']
        account_name = account_data['name']

        # Update message to show loading
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=f"🔄 Генерация Excel-отчета для аккаунта *{account_name}*...\n\nПожалуйста, подождите.",
            parse_mode=ParseMode.MARKDOWN
        )

        # Get report data (without office_id filter to get all offices)
        report_data = get_wb_report(token, office_id=None)

        if report_data:
            # Create Excel from JSON data
            excel_data = create_excel_from_json(report_data, account_name, account_id)

            if excel_data:
                # Generate filename
                filename = f"Детали_лог_объекта_{account_name}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

                # Send info message
                await callback.bot.send_message(
                    chat_id=user_id,
                    text=f"📊 *Excel-отчет: Детали лог объекта - {account_name}*\n📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    parse_mode=ParseMode.MARKDOWN
                )

                # Send Excel file
                await callback.bot.send_document(
                    chat_id=user_id,
                    document=BufferedInputFile(excel_data, filename=filename)
                )

                # Return to Ostatki menu
                await show_ostatki_menu(callback.bot, user_id, message_id)
            else:
                # Show error and return to Ostatki menu
                await callback.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=f"❌ Ошибка при создании Excel-отчета для аккаунта *{account_name}*.",
                    reply_markup=get_back_to_ostatki_keyboard(),
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            # Show error and return to Ostatki menu
            await callback.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=f"❌ Ошибка при получении данных для аккаунта *{account_name}*.",
                reply_markup=get_back_to_ostatki_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        # Invalid account, return to Ostatki menu
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ Ошибка: выбран недоступный аккаунт.",
            reply_markup=get_back_to_ostatki_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(lambda c: c.data == "ostatki_subscribe")
async def callback_ostatki_subscribe(callback: CallbackQuery):
    """Handler for subscribe button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Subscribe user
    subscription_status[user_id] = True

    # Confirm subscription
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text="✅ Вы успешно подписались на автоматические отчеты!\n\nВы будете получать отчеты по остаткам ПМ регулярно.",
        reply_markup=get_back_to_ostatki_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "ostatki_unsubscribe")
async def callback_ostatki_unsubscribe(callback: CallbackQuery):
    """Handler for unsubscribe button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Unsubscribe user
    subscription_status[user_id] = False

    # Confirm unsubscription
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text="🔕 Вы отписались от автоматических отчетов.\n\nВы всё равно можете запрашивать отчеты вручную через меню.",
        reply_markup=get_back_to_ostatki_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "ostatki_list_routes")
async def callback_ostatki_list_routes(callback: CallbackQuery):
    """Handler for list routes button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Get all routes
    routes = get_routes()

    if not routes:
        # No routes, show message
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="📋 *Список добавленных маршрутов*\n\nНет добавленных маршрутов.",
            reply_markup=get_back_to_ostatki_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Format routes list
    response = "📋 *Список добавленных маршрутов:*\n\n"

    for account_key, account_routes in routes.items():
        if account_routes:
            account_name = accounts.get(account_key, {}).get('name', account_key)
            response += f"*{account_name}:*\n"

            for route_id, route_info in account_routes.items():
                response += (
                    f"- ID {route_id}, Парковка {route_info['parking']}, "
                    f"Норма ШК {route_info['shk_norm']}"
                )

                if 'fuel_norm' in route_info:
                    response += f", Норма литров {route_info['fuel_norm']:.2f}"

                response += "\n"

            response += "\n"

    # Show routes list
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=response,
        reply_markup=get_back_to_ostatki_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "ostatki_add_route")
async def callback_ostatki_add_route(callback: CallbackQuery):
    """Handler for add route button"""
    await callback.answer()
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    # Show instructions
    instructions = (
        "📝 *Добавление информации о маршруте*\n\n"
        "Для добавления маршрута отправьте команду в формате:\n\n"
        "`/add_route account_id route_id parking shk_norm [fuel_norm]`\n\n"
        "Например:\n"
        "`/add_route account_1 10194 20 1158 4502.31`\n\n"
        "Где:\n"
        "- `account_id` - ID аккаунта (например, account_1)\n"
        "- `route_id` - ID маршрута (число)\n"
        "- `parking` - номер парковки\n"
        "- `shk_norm` - норма ШК (целое число)\n"
        "- `fuel_norm` - норма литров (число с плавающей точкой, опционально)\n\n"
        "*Доступные аккаунты:*\n"
    )

    # Add available accounts
    for account_id, account_data in accounts.items():
        if account_data['enabled']['ostatki']:
            instructions += f"- `{account_id}`: {account_data['name']}\n"

    # Show instructions
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=instructions,
        reply_markup=get_back_to_ostatki_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(lambda c: c.data == "ostatki_send_to_group")
async def callback_ostatki_send_to_group(callback: CallbackQuery):
    """Handler for send to channel button"""
    await callback.answer("Отправляю отчеты в канал...")
    user_id = callback.from_user.id
    message_id = callback.message.message_id

    if not OSTATKI_PM_CHANNEL:
        # No channel configured for Ostatki PM
        await callback.bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ Ошибка: Канал для отчетов остатков ПМ не настроен в конфигурации бота.",
            reply_markup=get_back_to_ostatki_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Update message to show progress
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=f"🔄 Отправка отчетов в канал...\n\nПожалуйста, подождите.",
        parse_mode=ParseMode.MARKDOWN
    )

    # Send reports for all enabled accounts
    success_count = 0
    error_count = 0

    for account_id, account_data in accounts.items():
        if account_data['enabled']['ostatki']:
            token = account_data['ostatki']['token']
            account_name = account_data['name']
            office_id = account_data['ostatki']['office_id']

            try:
                # Get report data
                report_data = get_wb_report(token, office_id)

                if report_data:
                    # Format report
                    formatted_text = format_last_mile_text(report_data, account_name, account_id)

                    # Send to channel
                    await callback.bot.send_message(
                        chat_id=OSTATKI_PM_CHANNEL,
                        text=formatted_text,
                        parse_mode=ParseMode.MARKDOWN
                    )

                    success_count += 1
                else:
                    logger.error(f"Error getting report for {account_name}")
                    error_count += 1
            except Exception as e:
                logger.error(f"Error sending report to channel for {account_name}: {e}", exc_info=True)
                error_count += 1

    # Show result
    result_text = f"✅ Отчеты отправлены в канал!\n\n"

    if success_count > 0:
        result_text += f"Успешно отправлено: {success_count} отчетов\n"

    if error_count > 0:
        result_text += f"Ошибки при отправке: {error_count} отчетов\n"

    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=message_id,
        text=result_text,
        reply_markup=get_back_to_ostatki_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# Command handlers
@router.message(Command("add_route"))
async def cmd_add_route(message: Message):
    """Handler for /add_route command"""
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 5 or len(args) > 6:
        await message.answer(
            'Неверный формат команды.\n'
            'Используйте: /add_route account_id route_id parking shk_norm [fuel_norm]\n'
            'Пример: /add_route account_1 10194 20 1158 4502.31'
        )
        return

    try:
        account_key = args[1]
        route_id = int(args[2])
        parking_val = args[3]
        shk_norm = int(args[4])
        fuel_norm = float(args[5]) if len(args) == 6 else None

        if account_key not in accounts or not accounts[account_key]['enabled']['ostatki']:
            await message.answer(
                f'Ошибка: аккаунт {account_key} не существует или не включен.\n'
                f'Доступные аккаунты: {", ".join([a for a, d in accounts.items() if d["enabled"]["ostatki"]])}'
            )
            return

        # Add route data
        success = add_route(account_key, route_id, parking_val, shk_norm, fuel_norm, user_id)

        if success:
            response = (
                f'✅ Маршрут успешно добавлен:\n'
                f'Аккаунт: {account_key}\n'
                f'ID маршрута: {route_id}\n'
                f'Парковка: {parking_val}\n'
                f'Норма ШК: {shk_norm}'
            )

            if fuel_norm is not None:
                response += f'\nНорма литров: {fuel_norm}'
            else:
                response += '\nНорма литров: будет использоваться значение из API'

            await message.answer(response)
        else:
            await message.answer('❌ Ошибка при сохранении данных о маршруте.')

    except ValueError as e:
        await message.answer(f'Ошибка: неверный формат числовых параметров. {e}')
    except Exception as e:
        logger.error(f"Error adding route: {e}", exc_info=True)
        await message.answer(f'Произошла ошибка: {e}')

# Scheduled task for sending reports to subscribed users
async def send_scheduled_reports(bot: Bot):
    """
    Send scheduled reports to all subscribed users

    Args:
        bot: Bot instance
    """
    logger.info("Sending scheduled reports to subscribed users")

    # Skip if no subscribed users
    if not subscription_status:
        logger.info("No subscribed users")
        return

    # Get subscribed users
    subscribed_users = [user_id for user_id, subscribed in subscription_status.items() if subscribed]

    if not subscribed_users:
        logger.info("No subscribed users")
        return

    logger.info(f"Sending reports to {len(subscribed_users)} subscribed users")

    # Send reports for all enabled accounts
    for account_id, account_data in accounts.items():
        if not account_data['enabled']['ostatki']:
            continue

        token = account_data['ostatki']['token']
        account_name = account_data['name']
        office_id = account_data['ostatki']['office_id']

        try:
            # Get report data
            report_data = get_wb_report(token, office_id)

            if report_data:
                # Format report
                formatted_text = format_last_mile_text(report_data, account_name, account_id)

                # Send to each subscribed user
                for user_id in subscribed_users:
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=formatted_text,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        logger.info(f"Report for {account_name} sent to user {user_id}")
                    except Exception as e:
                        logger.error(f"Error sending report to user {user_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error getting report for {account_name}: {e}", exc_info=True)

# Scheduled task for sending reports to channel
async def send_reports_to_group(bot: Bot):
    """
    Send reports to configured channel

    Args:
        bot: Bot instance
    """
    logger.info(f"Sending scheduled reports to channel {OSTATKI_PM_CHANNEL}")

    if not OSTATKI_PM_CHANNEL:
        logger.error("Ostatki PM channel not configured")
        return

    # Send reports for all enabled accounts
    for account_id, account_data in accounts.items():
        if not account_data['enabled']['ostatki']:
            continue

        token = account_data['ostatki']['token']
        account_name = account_data['name']
        office_id = account_data['ostatki']['office_id']

        try:
            # Get report data
            report_data = get_wb_report(token, office_id)

            if report_data:
                # Format report
                formatted_text = format_last_mile_text(report_data, account_name, account_id)

                # Send to channel
                await bot.send_message(
                    chat_id=OSTATKI_PM_CHANNEL,
                    text=formatted_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Report for {account_name} sent to channel")
            else:
                logger.error(f"Error getting report for {account_name}")
        except Exception as e:
            logger.error(f"Error sending report to channel for {account_name}: {e}", exc_info=True)
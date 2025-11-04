"""
Formatter module for retentions messages
"""

import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def format_retentions_report(data: List[Dict[str, Any]], account_name: str) -> str:
    """
    Format retentions data into readable Telegram message

    Args:
        data: List of retentions
        account_name: Account name

    Returns:
        Formatted message text
    """
    try:
        if not data:
            return f"✅ {account_name}: Нет данных о возможных удержаниях."

        # Count general statistics
        total_waysheets = len(data)

        # Count only LOST tares
        total_tares = sum(
            len([t for t in item.get('tares', []) if t.get('status') == 'TARE_STATUS_LOST'])
            for item in data
        )
        total_lost_amount = sum(
            t.get('price', 0)
            for item in data
            for t in item.get('tares', [])
            if t.get('status') == 'TARE_STATUS_LOST'
        )

        # Format main report text
        formatted_text = f"⚠️ *ОБНАРУЖЕНЫ УДЕРЖАНИЯ!* ⚠️\n"
        formatted_text += f"💰 *{account_name}*\n"
        formatted_text += f"📅 Дата формирования: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"

        # General statistics
        formatted_text += "🌐 *Общая статистика:*\n"
        formatted_text += f"• Путевых листов с удержаниями: {total_waysheets} 📋\n"
        formatted_text += f"• Всего потерянных тар: {total_tares} 📦\n"
        formatted_text += f"• Сумма потенциальных удержаний: {total_lost_amount} ₽ 💸\n\n"

        # Detailed info about waysheets with retentions
        formatted_text += "💸 *Детали удержаний:*\n\n"

        # Sort data by remaining time (ascending)
        sorted_data = sorted(
            data,
            key=lambda x: x.get('total_remaining_hours', float('inf'))
        )

        for i, waysheet in enumerate(sorted_data, 1):
            # Count only lost tares
            lost_tares = [t for t in waysheet.get('tares', []) if t.get('status') == 'TARE_STATUS_LOST']
            if not lost_tares:
                continue  # Skip if no lost tares

            lost_amount = sum(t.get('price', 0) for t in lost_tares)

            formatted_text += f"*🔖 Путевой лист {i}:*\n"

            # Basic fields
            if 'waysheet_id' in waysheet:
                formatted_text += f"🆔 ID: {waysheet['waysheet_id']}\n"

            # Timer info
            if waysheet.get('remaining_hours') is not None:
                hours = waysheet['remaining_hours']
                minutes = waysheet['remaining_minutes']

                formatted_text += f"⏱ Осталось: *{hours} ч {minutes} мин*\n"

                # Add warnings based on remaining time
                if waysheet.get('time_expired', False):
                    formatted_text += "⚠️ *ВРЕМЯ ИСТЕКЛО!* Срочно обработайте удержание\n"
                elif hours < 24:
                    formatted_text += "🚨 *СРОЧНО!* Менее 24 часов\n"
                elif hours < 48:
                    formatted_text += "⚠️ *ВНИМАНИЕ!* Менее 48 часов\n"
            else:
                formatted_text += "⏱ Таймер: Н/Д\n"

            # Source office
            if 'src_office_name' in waysheet:
                formatted_text += f"🏢 Офис отправления: {waysheet['src_office_name']}\n"

            # Open date
            if 'open_dt' in waysheet:
                try:
                    dt = datetime.fromisoformat(waysheet['open_dt'].replace('Z', '+00:00'))
                    formatted_date = dt.strftime('%d.%m.%Y %H:%M')
                    formatted_text += f"📅 Дата: {formatted_date}\n"
                except:
                    formatted_text += f"📅 Дата: {waysheet['open_dt']}\n"

            # Add driver info if available
            if 'driver_name' in waysheet and waysheet['driver_name'] != "Не найдено":
                formatted_text += f"👨‍✈️ Водитель: {waysheet['driver_name']}\n"

            # Lost tares info
            formatted_text += f"❌ Потерянных тар: {len(lost_tares)}\n"
            formatted_text += f"💰 Сумма удержаний: {lost_amount} ₽\n\n"

            formatted_text += "*Детали потерянных тар:*\n"
            for j, tare in enumerate(lost_tares[:5], 1):  # Show up to 5 tares
                formatted_text += f"  • Тара {j}: ID {tare.get('tare_id')}, {tare.get('price')} ₽\n"
                formatted_text += f"    Офис назначения: {tare.get('dst_office_name', 'Не указан')}\n"

            if len(lost_tares) > 5:
                formatted_text += f"  • ... и еще {len(lost_tares) - 5} тар\n"

            formatted_text += "\n"

            # Limit message length to avoid Telegram limits
            if len(formatted_text) > 3500:
                formatted_text += "... (показаны не все удержания)\n"
                break

        # Conclusion
        formatted_text += "\n✅ *Конец отчета* ✅\n"
        formatted_text += "⚠️ *Пожалуйста, примите меры!* ⚠️"

        return formatted_text

    except Exception as e:
        logger.error(f"Error formatting retentions data: {str(e)}")
        traceback.print_exc()
        return f"🚫 Ошибка при форматировании данных о возможных удержаниях: {str(e)}"


def format_timers_report(timers_by_account: List[Dict]) -> str:
    """
    Format retention timers into readable Telegram message

    Args:
        timers_by_account: List of timers grouped by account

    Returns:
        Formatted message text
    """
    try:
        if not timers_by_account:
            return "✅ Нет активных таймеров удержаний."

        # Format message with timers
        response = "⏱ *ТАЙМЕРЫ УДЕРЖАНИЙ* ⏱\n\n"

        for account_info in timers_by_account:
            account_name = account_info['account_name']
            response += f"*{account_name}*:\n"

            total_retentions = len(account_info['timers'])
            response += f"Всего удержаний: {total_retentions}\n\n"

            # Sort by remaining time (ascending)
            sorted_timers = sorted(
                account_info['timers'],
                key=lambda x: x.get('total_remaining_hours', float('inf'))
            )

            # Show up to 5 retentions with least remaining time
            for i, timer in enumerate(sorted_timers[:5], 1):
                waysheet_id = timer.get('waysheet_id', 'Н/Д')
                response += f"⚠️ *Удержание {i}:*\n"
                response += f"🆔 ID: {waysheet_id}\n"

                if timer.get('remaining_hours') is not None:
                    hours = timer['remaining_hours']
                    minutes = timer['remaining_minutes']
                    response += f"⏱ Осталось: *{hours} ч {minutes} мин*\n"

                    # Add emoji based on remaining time
                    if hours < 24:
                        response += "🚨 *СРОЧНО!* Менее 24 часов\n"
                    elif hours < 48:
                        response += "⚠️ *ВНИМАНИЕ!* Менее 48 часов\n"
                    else:
                        response += "📊 Более 48 часов\n"
                else:
                    response += "⏱ Таймер: Н/Д\n"

                # Source office
                if 'src_office_name' in timer:
                    response += f"🏢 Офис: {timer['src_office_name']}\n"

                # Add driver info if available
                if 'driver_name' in timer and timer['driver_name'] != "Не найдено":
                    response += f"👨‍✈️ Водитель: {timer['driver_name']}\n"

                response += "\n"

            # If there are more records
            if len(sorted_timers) > 5:
                response += f"... и ещё {len(sorted_timers) - 5} удержаний\n"

            response += "\n"

        return response

    except Exception as e:
        logger.error(f"Error formatting timers data: {str(e)}")
        traceback.print_exc()
        return f"🚫 Ошибка при форматировании таймеров: {str(e)}"


def format_retention_summary(retention: Dict[str, Any]) -> str:
    """
    Format single retention summary for inline display

    Args:
        retention: Retention data

    Returns:
        Formatted summary text
    """
    try:
        summary = []

        # Add timer if available
        if retention.get('remaining_hours') is not None:
            hours = retention['remaining_hours']
            minutes = retention['remaining_minutes']
            if retention.get('time_expired', False):
                summary.append("⚠️ ВРЕМЯ ИСТЕКЛО!")
            elif hours < 24:
                summary.append(f"🚨 {hours}ч {minutes}м")
            else:
                summary.append(f"⏱ {hours}ч {minutes}м")

        # Add waysheet ID
        if 'waysheet_id' in retention:
            summary.append(f"ID: {retention['waysheet_id']}")

        # Add lost tares count
        lost_tares = [t for t in retention.get('tares', []) if t.get('status') == 'TARE_STATUS_LOST']
        if lost_tares:
            lost_amount = sum(t.get('price', 0) for t in lost_tares)
            summary.append(f"{len(lost_tares)} тар / {lost_amount}₽")

        return " | ".join(summary) if summary else "Нет данных"

    except Exception as e:
        logger.error(f"Error formatting retention summary: {str(e)}")
        return "Ошибка форматирования"
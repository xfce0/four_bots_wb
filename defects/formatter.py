"""Formatters for defects messages"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from .api import extract_driver_from_comment, extract_waysheet_number, is_defect_returned

logger = logging.getLogger(__name__)


def format_defects_summary(all_defects: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format summary of defects from all accounts"""
    if not all_defects:
        return "📊 <b>Нет данных о браках</b>"

    total_defects = 0
    total_returned = 0
    total_amount = 0.0
    messages = []

    for account_id, defects in all_defects.items():
        if not defects:
            continue

        account_name = defects[0].get('account_name', account_id) if defects else account_id
        account_defects = len(defects)
        account_returned = sum(1 for d in defects if is_defect_returned(d))
        account_amount = sum(
            float(d.get('amount', 0) or 0)
            for d in defects if not is_defect_returned(d)
        )

        total_defects += account_defects
        total_returned += account_returned
        total_amount += account_amount

        messages.append(
            f"📦 <b>{account_name}</b>\n"
            f"   • Всего браков: {account_defects}\n"
            f"   • Возвращено: {account_returned}\n"
            f"   • Активных: {account_defects - account_returned}\n"
            f"   • Сумма активных: {account_amount:,.2f} ₽"
        )

    summary = (
        f"📊 <b>СВОДКА ПО БРАКАМ</b>\n"
        f"{'=' * 25}\n\n"
        f"<b>ОБЩАЯ СТАТИСТИКА:</b>\n"
        f"• Всего браков: {total_defects}\n"
        f"• Возвращено: {total_returned}\n"
        f"• Активных: {total_defects - total_returned}\n"
        f"• Общая сумма: {total_amount:,.2f} ₽\n\n"
        f"<b>ПО КАБИНЕТАМ:</b>\n\n" +
        "\n\n".join(messages)
    )

    return summary


def format_defect_details(defect: Dict[str, Any]) -> str:
    """Format detailed information about a single defect"""
    try:
        # Extract basic info
        defect_id = defect.get('pretension_id', defect.get('id', 'Н/Д'))
        created_date = defect.get('created_at', defect.get('create_dt', 'Н/Д'))
        amount = float(defect.get('amount', 0) or 0)
        rop_id = defect.get('rop_id', 'Н/Д')
        transfer_box_id = defect.get('transfer_box_id', 'Н/Д')

        # Extract comment and description
        comment = defect.get('comment', defect.get('description', ''))

        # Extract driver: first try from API data, then from comment
        driver = defect.get('driver_name') or extract_driver_from_comment(comment) or "Н/Д"
        waysheet = extract_waysheet_number(comment)

        # Check if returned
        is_returned = is_defect_returned(defect)
        status_emoji = "✅" if is_returned else "❌"
        status_text = "Возвращен" if is_returned else "Активен"

        # Format created date
        if created_date and created_date != 'Н/Д':
            try:
                if isinstance(created_date, str):
                    dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                    created_str = dt.strftime('%d.%m.%Y %H:%M')
                else:
                    created_str = str(created_date)
            except:
                created_str = str(created_date)
        else:
            created_str = 'Н/Д'

        # Build message
        message = (
            f"{status_emoji} <b>БРАК #{defect_id}</b>\n"
            f"{'=' * 25}\n"
            f"📅 Дата: {created_str}\n"
            f"💰 Сумма: {amount:,.2f} ₽\n"
            f"📦 ROP ID: {rop_id}\n"
            f"📦 Коробка: {transfer_box_id}\n"
            f"🚗 Водитель: {driver}\n"
            f"📋 Путевой: {waysheet}\n"
            f"📊 Статус: {status_text}\n"
        )

        # Add comment if exists
        if comment:
            # Truncate long comments
            if len(comment) > 200:
                comment = comment[:197] + "..."
            message += f"\n💬 Комментарий:\n{comment}"

        return message

    except Exception as e:
        logger.error(f"Error formatting defect details: {e}")
        return f"❌ Ошибка форматирования брака {defect.get('id', 'unknown')}"


def format_defects_list(defects: List[Dict[str, Any]], title: str = "БРАКИ") -> List[str]:
    """Format list of defects for sending as messages (split if too long)"""
    if not defects:
        return [f"📊 <b>{title}</b>\n\nНет данных о браках"]

    messages = []
    current_message = f"📊 <b>{title}</b>\n{'=' * 25}\n\n"

    # Sort defects by date (newest first)
    sorted_defects = sorted(
        defects,
        key=lambda x: x.get('created_at', x.get('create_dt', '')),
        reverse=True
    )

    for defect in sorted_defects:
        defect_text = format_defect_short(defect)

        # Check if adding this defect would exceed Telegram limit
        if len(current_message) + len(defect_text) > 3500:
            messages.append(current_message)
            current_message = f"📊 <b>{title} (продолжение)</b>\n{'=' * 25}\n\n"

        current_message += defect_text + "\n" + "─" * 20 + "\n"

    if current_message.strip():
        messages.append(current_message)

    return messages


def format_defect_short(defect: Dict[str, Any]) -> str:
    """Format short version of defect for lists"""
    try:
        defect_id = defect.get('pretension_id', defect.get('id', 'Н/Д'))
        created_date = defect.get('created_at', defect.get('create_dt', 'Н/Д'))
        amount = float(defect.get('amount', 0) or 0)
        comment = defect.get('comment', defect.get('description', ''))[:100]

        # Extract driver: first try from API data, then from comment
        driver = defect.get('driver_name') or extract_driver_from_comment(defect.get('comment', '')) or "Н/Д"

        # Check if returned
        is_returned = is_defect_returned(defect)
        status_emoji = "✅" if is_returned else "❌"

        # Format date
        if created_date and created_date != 'Н/Д':
            try:
                if isinstance(created_date, str):
                    dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                    date_str = dt.strftime('%d.%m %H:%M')
                else:
                    date_str = str(created_date)[:16]
            except:
                date_str = str(created_date)[:16]
        else:
            date_str = 'Н/Д'

        return (
            f"{status_emoji} <b>#{defect_id}</b> | {date_str}\n"
            f"💰 {amount:,.0f} ₽ | 🚗 {driver}\n"
            f"{comment if comment else 'Без комментария'}"
        )

    except Exception as e:
        logger.error(f"Error formatting defect short: {e}")
        return f"❌ Ошибка форматирования брака"


def format_defects_for_channel(all_defects: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """Format defects for sending to channel (with topic support)"""
    messages = []

    for account_id, defects in all_defects.items():
        if not defects:
            continue

        # Filter only active (non-returned) defects
        active_defects = [d for d in defects if not is_defect_returned(d)]

        if not active_defects:
            continue

        account_name = defects[0].get('account_name', account_id)

        # Create header
        header = (
            f"⚠️ <b>АКТИВНЫЕ БРАКИ - {account_name}</b>\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"{'=' * 25}\n\n"
        )

        # Group defects by driver
        by_driver = {}
        for defect in active_defects:
            driver = defect.get('driver_name') or extract_driver_from_comment(defect.get('comment', '')) or "Неизвестный водитель"
            if driver not in by_driver:
                by_driver[driver] = []
            by_driver[driver].append(defect)

        current_message = header

        for driver, driver_defects in by_driver.items():
            driver_total = sum(float(d.get('amount', 0) or 0) for d in driver_defects)
            driver_section = (
                f"🚗 <b>{driver}</b>\n"
                f"   Браков: {len(driver_defects)} | Сумма: {driver_total:,.2f} ₽\n"
            )

            # Add each defect
            for defect in driver_defects[:5]:  # Limit to 5 per driver to avoid huge messages
                defect_id = defect.get('pretension_id', defect.get('id', 'Н/Д'))
                amount = float(defect.get('amount', 0) or 0)
                driver_section += f"   • #{defect_id}: {amount:,.0f} ₽\n"

            if len(driver_defects) > 5:
                driver_section += f"   ... и еще {len(driver_defects) - 5} браков\n"

            driver_section += "\n"

            # Check message size
            if len(current_message) + len(driver_section) > 3500:
                messages.append(current_message)
                current_message = header + driver_section
            else:
                current_message += driver_section

        # Add summary
        total_amount = sum(float(d.get('amount', 0) or 0) for d in active_defects)
        summary = (
            f"{'=' * 25}\n"
            f"📊 <b>ИТОГО:</b>\n"
            f"• Активных браков: {len(active_defects)}\n"
            f"• Общая сумма: {total_amount:,.2f} ₽\n"
        )

        if len(current_message) + len(summary) <= 4000:
            current_message += summary
        else:
            messages.append(current_message)
            messages.append(summary)
            continue

        messages.append(current_message)

    return messages


def create_excel_content(defects: List[Dict[str, Any]]) -> bytes:
    """Create Excel content from defects data"""
    import pandas as pd
    import io

    # Prepare data for DataFrame
    rows = []
    for defect in defects:
        # Get driver: first from API data, then from comment
        driver = defect.get('driver_name') or extract_driver_from_comment(defect.get('comment', '')) or "Н/Д"
        waysheet = extract_waysheet_number(defect.get('comment', ''))
        is_returned = is_defect_returned(defect)

        # Format created date
        created_date = defect.get('created_at', defect.get('create_dt', ''))
        if created_date:
            try:
                if isinstance(created_date, str):
                    dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                    created_str = dt.strftime('%d.%m.%Y %H:%M')
                else:
                    created_str = str(created_date)
            except:
                created_str = str(created_date)
        else:
            created_str = ''

        rows.append({
            'ID брака': defect.get('pretension_id', defect.get('id', '')),
            'Дата создания': created_str,
            'Тип': defect.get('retention_type', 'БРАК'),
            'Сумма': float(defect.get('amount', 0) or 0),
            'ROP ID': defect.get('rop_id', ''),
            'ID коробки': defect.get('transfer_box_id', ''),
            'Водитель': driver,
            'Путевой лист': waysheet,
            'Статус': 'Возвращен' if is_returned else 'Активен',
            'Комментарий': defect.get('comment', defect.get('description', '')),
            'Кабинет': defect.get('account_name', '')
        })

    # Create DataFrame
    df = pd.DataFrame(rows)

    # Create Excel in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Браки', index=False)

        # Auto-adjust column width
        worksheet = writer.sheets['Браки']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).apply(len).max(),
                len(col)
            )
            # Limit max width to 50 characters
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)

    output.seek(0)
    return output.read()
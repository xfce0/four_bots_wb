"""
Utilities for Shipment module
Provides helper functions for shipment monitoring
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

def is_new_shipment(shipment: Dict, monitoring_start_time: datetime) -> bool:
    """
    Check if shipment is new (created after monitoring started)

    Args:
        shipment: Shipment data
        monitoring_start_time: Time when monitoring started

    Returns:
        True if shipment is new, False otherwise
    """
    if not monitoring_start_time:
        return True

    created_at_str = shipment.get('created_at')
    if not created_at_str:
        return False

    try:
        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        return created_at > monitoring_start_time
    except (ValueError, TypeError):
        logger.error(f"Error parsing shipment creation date: {created_at_str}")
        return False

def calculate_max_stats(shipment: Dict) -> Dict[str, int]:
    """
    Calculate maximum stats (boxes, items) from shipment data

    Args:
        shipment: Shipment data

    Returns:
        Dictionary with max stats
    """
    max_stats = {
        'max_boxes': 0,
        'max_items': 0
    }

    # Calculate from transfers
    transfers = shipment.get('transfers', [])
    for transfer in transfers:
        box_count = transfer.get('box_count', 0)
        item_count = transfer.get('item_count', 0)

        max_stats['max_boxes'] += box_count
        max_stats['max_items'] += item_count

    # Add tares (warehouse boxes)
    tares = shipment.get('tares', [])
    for tare in tares:
        box_count = 1  # Each tare is one box
        item_count = tare.get('item_count', 0)

        max_stats['max_boxes'] += box_count
        max_stats['max_items'] += item_count

    return max_stats

def has_progress_changed(shipment_id: int, current_progress: Dict, last_progress: Dict) -> bool:
    """
    Check if shipment progress has changed significantly

    Args:
        shipment_id: Shipment ID
        current_progress: Current progress data
        last_progress: Previous progress data

    Returns:
        True if progress has changed, False otherwise
    """
    if shipment_id not in last_progress:
        return True

    # Check if state changed
    if current_progress.get('state') != last_progress[shipment_id].get('state'):
        return True

    # Check if scanned boxes count changed
    current_boxes = current_progress.get('scanned_boxes', 0)
    last_boxes = last_progress[shipment_id].get('scanned_boxes', 0)

    if current_boxes != last_boxes:
        return True

    # Check if scanned items count changed
    current_items = current_progress.get('scanned_items', 0)
    last_items = last_progress[shipment_id].get('scanned_items', 0)

    if current_items != last_items:
        return True

    return False

def update_last_progress(shipment_id: int, progress: Dict, last_progress: Dict) -> None:
    """
    Update last progress data

    Args:
        shipment_id: Shipment ID
        progress: Current progress data
        last_progress: Previous progress data dictionary to update
    """
    last_progress[shipment_id] = progress

def get_shipment_grouped_info(shipment: Dict, max_stats: Dict) -> Dict:
    """
    Get grouped information about shipment progress

    Args:
        shipment: Shipment data
        max_stats: Maximum stats

    Returns:
        Dictionary with grouped information
    """
    # Calculate current progress
    scanned_boxes = 0
    scanned_items = 0
    remaining_items = 0

    # Count from transfers
    transfers = shipment.get('transfers', [])
    for transfer in transfers:
        scanned_boxes += transfer.get('box_scanned', 0)
        scanned_items += transfer.get('item_scanned', 0)
        remaining_items += transfer.get('remain_count', 0)

    # Add tares (warehouse boxes)
    tares = shipment.get('tares', [])
    for tare in tares:
        if tare.get('is_scanned', False):
            scanned_boxes += 1
            scanned_items += tare.get('item_count', 0)

    # Calculate percentages
    box_percentage = 0
    item_percentage = 0

    if max_stats['max_boxes'] > 0:
        box_percentage = round((scanned_boxes / max_stats['max_boxes']) * 100, 1)

    if max_stats['max_items'] > 0:
        item_percentage = round((scanned_items / max_stats['max_items']) * 100, 1)

    # Format times
    created_at = None
    created_at_str = shipment.get('created_at')
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            logger.error(f"Error parsing shipment creation date: {created_at_str}")

    closed_at = None
    closed_at_str = shipment.get('closed_at')
    if closed_at_str:
        try:
            closed_at = datetime.fromisoformat(closed_at_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            logger.error(f"Error parsing shipment closing date: {closed_at_str}")

    # Calculate duration if closed
    duration = None
    if created_at and closed_at:
        duration = closed_at - created_at

    # Gather result
    return {
        'shipment_id': shipment.get('id'),
        'state': shipment.get('state'),
        'vehicle': shipment.get('car_number', 'N/A'),
        'responsible': shipment.get('responsible', 'N/A'),
        'created_at': created_at,
        'closed_at': closed_at,
        'duration': duration,
        'max_boxes': max_stats['max_boxes'],
        'max_items': max_stats['max_items'],
        'scanned_boxes': scanned_boxes,
        'scanned_items': scanned_items,
        'remaining_items': remaining_items,
        'box_percentage': box_percentage,
        'item_percentage': item_percentage
    }

def format_progress_message(account_name: str, info: Dict) -> str:
    """
    Format message for active shipment

    Args:
        account_name: Account name
        info: Shipment information

    Returns:
        Formatted message
    """
    # Progress bar (10 blocks)
    progress_blocks = 10
    filled_blocks = round(info['box_percentage'] / 10)
    if filled_blocks > progress_blocks:
        filled_blocks = progress_blocks

    progress_bar = '🟩' * filled_blocks + '⬜' * (progress_blocks - filled_blocks)

    # Format times
    created_at_str = "N/A"
    if info['created_at']:
        created_at_str = info['created_at'].strftime('%d.%m.%Y %H:%M:%S')

    # Build message
    message = (
        f"🟢 [{account_name}] Отгрузка #{info['shipment_id']} - Активная\n\n"
        f"Статус: {info['state']}\n"
        f"Ответственный: {info['responsible']}\n"
        f"Транспорт: {info['vehicle']}\n"
        f"Создана: {created_at_str}\n\n"
        f"📦 ДАННЫЕ ОТГРУЗКИ:\n"
        f"Всего товаров: {info['max_items']} шт.\n"
        f"Всего коробок: {info['max_boxes']} шт.\n"
        f"Отсканировано товаров: {info['scanned_items']}/{info['max_items']}\n"
        f"Отсканировано: {info['scanned_boxes']}/{info['max_boxes']} шт. ({info['box_percentage']}%)\n"
        f"Прогресс: {progress_bar}"
    )

    return message

def format_completed_shipment(account_name: str, info: Dict) -> str:
    """
    Format message for completed shipment

    Args:
        account_name: Account name
        info: Shipment information

    Returns:
        Formatted message
    """
    # Progress bar (always full for completed shipments)
    progress_bar = '🟩' * 10

    # Format times
    created_at_str = "N/A"
    if info['created_at']:
        created_at_str = info['created_at'].strftime('%d.%m.%Y %H:%M:%S')

    closed_at_str = "N/A"
    if info['closed_at']:
        closed_at_str = info['closed_at'].strftime('%d.%m.%Y %H:%M:%S')

    # Format duration
    duration_str = "N/A"
    if info['duration']:
        hours = info['duration'].seconds // 3600
        minutes = (info['duration'].seconds % 3600) // 60
        duration_str = f"{hours} ч. {minutes} мин."

    # Build message
    message = (
        f"🔴 [{account_name}] Отгрузка #{info['shipment_id']} - Завершена\n\n"
        f"Статус: {info['state']}\n"
        f"Ответственный: {info['responsible']}\n"
        f"Транспорт: {info['vehicle']}\n"
        f"Создана: {created_at_str}\n"
        f"Закрыта: {closed_at_str}\n\n"
        f"📦 ДАННЫЕ ОТГРУЗКИ:\n"
        f"Всего товаров: {info['max_items']} шт.\n"
        f"Всего коробок: {info['max_boxes']} шт.\n"
        f"Оставшиеся товары: {info['remaining_items']} шт.\n"
        f"Отсканировано товаров: {info['scanned_items']}/{info['max_items']}\n"
        f"Отсканировано: {info['scanned_boxes']}/{info['max_boxes']} шт. ({info['box_percentage']}%)\n"
        f"Прогресс: {progress_bar}\n"
        f"Время отгрузки: {duration_str}"
    )

    return message
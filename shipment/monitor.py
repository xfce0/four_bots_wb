"""
Monitoring logic for Shipment module
Provides asynchronous monitoring loops for shipment tracking
"""
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from aiogram.enums import ParseMode

from shipment.api import authenticate, get_shipments, get_shipment_details
from shipment.utils import (
    is_new_shipment,
    calculate_max_stats,
    has_progress_changed,
    update_last_progress,
    get_shipment_grouped_info,
    format_progress_message,
    format_completed_shipment
)
from utils.config import CHANNEL_ID, CHANNEL_ID2, LIVE_TOPIC_ID, COMPLETED_TOPIC_ID
from utils.config import CHECK_INTERVAL, REFRESH_INTERVAL, INACTIVITY_TIMEOUT

# Configure logging
logger = logging.getLogger(__name__)

# Global monitoring state
monitoring_tasks: Dict[str, asyncio.Task] = {}

async def check_new_shipments_loop(bot, account_id: str, account_data: Dict, session: aiohttp.ClientSession) -> None:
    """
    Loop for checking new shipments

    Args:
        bot: Bot instance
        account_id: Account ID
        account_data: Account data
        session: aiohttp session
    """
    account_name = account_data['name']
    logger.info(f"Starting check_new_shipments_loop for {account_name}")

    refresh_counter = 0

    while True:
        try:
            # Re-authenticate every 30 iterations to refresh token
            if refresh_counter >= 30:
                logger.info(f"Refreshing authentication for {account_name}")
                auth_success, _ = await authenticate(session, account_id)
                if not auth_success:
                    logger.warning(f"Failed to refresh authentication for {account_name}")
                refresh_counter = 0

            # Get active shipments
            shipments = await get_shipments(session, account_id, account_data)

            if not shipments:
                logger.warning(f"No shipments data for {account_name}, retrying later")
                await asyncio.sleep(REFRESH_INTERVAL)
                refresh_counter += 1
                continue

            logger.info(f"Processing {len(shipments)} shipments for {account_name}")

            # Get monitoring start time
            from utils.config import monitoring_start_times
            monitoring_start_time = monitoring_start_times.get(account_id)

            for shipment in shipments:
                shipment_id = shipment.get('id')
                if not shipment_id:
                    continue

                # Skip already processed shipments
                if shipment_id in account_data['shipment']['processed_shipments']:
                    continue

                # Check if it's a new shipment
                if is_new_shipment(shipment, monitoring_start_time):
                    logger.info(f"New shipment detected: {shipment_id} for {account_name}")

                    # Get shipment details
                    shipment_details = await get_shipment_details(session, account_data, shipment_id)

                    if not shipment_details:
                        logger.error(f"Failed to get details for shipment {shipment_id}")
                        continue

                    # Calculate maximum statistics
                    max_stats = calculate_max_stats(shipment_details)

                    # Get grouped information
                    info = get_shipment_grouped_info(shipment_details, max_stats)

                    # Check if shipment is already completed
                    if shipment_details.get('state') in ['closed', 'terminated', 'canceled']:
                        # Format message for completed shipment
                        message_text = format_completed_shipment(account_name, info)

                        # Send to completed channel/topic
                        await send_to_channel(bot, message_text, account_id, shipment_id, "completed")

                        # Mark as completed and processed
                        account_data['shipment']['completed_shipments'].add(shipment_id)
                        account_data['shipment']['processed_shipments'].add(shipment_id)
                        logger.info(f"Completed shipment {shipment_id} processed for {account_name}")
                    else:
                        # Format message for active shipment
                        message_text = format_progress_message(account_name, info)

                        # Send to live channel/topic
                        message_id = await send_to_channel(bot, message_text, account_id, shipment_id, "live")

                        if message_id:
                            # Store message ID for updates
                            account_data['shipment']['message_ids'][shipment_id] = message_id

                            # Store current progress
                            update_last_progress(shipment_id, info, account_data['shipment']['last_progress'])

                            # Update last activity time
                            account_data['shipment']['last_activity_time'][shipment_id] = datetime.now()

                            # Start monitoring this shipment
                            account_data['shipment']['monitored_shipments'][shipment_id] = shipment_details
                            logger.info(f"Started monitoring shipment {shipment_id} for {account_name}")

            refresh_counter += 1

        except Exception as e:
            logger.error(f"Error in check_new_shipments_loop for {account_name}: {e}", exc_info=True)

        # Sleep until next iteration
        await asyncio.sleep(REFRESH_INTERVAL)

async def update_active_shipments_loop(bot, account_id: str, account_data: Dict, session: aiohttp.ClientSession) -> None:
    """
    Loop for updating active shipments

    Args:
        bot: Bot instance
        account_id: Account ID
        account_data: Account data
        session: aiohttp session
    """
    account_name = account_data['name']
    logger.info(f"Starting update_active_shipments_loop for {account_name}")

    while True:
        try:
            monitored_shipments = list(account_data['shipment']['monitored_shipments'].keys())
            logger.debug(f"Updating {len(monitored_shipments)} monitored shipments for {account_name}")

            for shipment_id in monitored_shipments:
                # Skip completed shipments
                if shipment_id in account_data['shipment']['completed_shipments']:
                    continue

                # Check last activity time
                last_activity = account_data['shipment']['last_activity_time'].get(shipment_id)
                if last_activity:
                    inactive_time = (datetime.now() - last_activity).total_seconds()

                    if inactive_time > INACTIVITY_TIMEOUT:
                        logger.info(f"Shipment {shipment_id} inactive for {inactive_time} seconds, removing from monitoring")
                        del account_data['shipment']['monitored_shipments'][shipment_id]
                        continue

                # Get shipment details
                shipment_details = await get_shipment_details(session, account_data, shipment_id)

                if not shipment_details:
                    logger.error(f"Failed to get details for shipment {shipment_id}")
                    continue

                # Update stored shipment data
                account_data['shipment']['monitored_shipments'][shipment_id] = shipment_details

                # Calculate maximum statistics
                max_stats = calculate_max_stats(shipment_details)

                # Get grouped information
                info = get_shipment_grouped_info(shipment_details, max_stats)

                # Check if shipment is completed
                if shipment_details.get('state') in ['closed', 'terminated', 'canceled']:
                    logger.info(f"Shipment {shipment_id} completed")

                    # Format message for completed shipment
                    message_text = format_completed_shipment(account_name, info)

                    # Send to completed channel/topic
                    await send_to_channel(bot, message_text, account_id, shipment_id, "completed")

                    # Delete original message if exists
                    original_message_id = account_data['shipment']['message_ids'].get(shipment_id)
                    if original_message_id:
                        try:
                            await bot.delete_message(chat_id=CHANNEL_ID, message_id=original_message_id)
                            logger.info(f"Deleted original message for shipment {shipment_id}")
                        except Exception as e:
                            logger.error(f"Error deleting original message: {e}")

                    # Mark as completed
                    account_data['shipment']['completed_shipments'].add(shipment_id)
                    del account_data['shipment']['monitored_shipments'][shipment_id]

                else:
                    # Check if progress has changed
                    if has_progress_changed(shipment_id, info, account_data['shipment']['last_progress']):
                        logger.info(f"Progress changed for shipment {shipment_id}")

                        # Format message for active shipment
                        message_text = format_progress_message(account_name, info)

                        # Update existing message
                        message_id = account_data['shipment']['message_ids'].get(shipment_id)
                        if message_id:
                            try:
                                await bot.edit_message_text(
                                    chat_id=CHANNEL_ID,
                                    message_id=message_id,
                                    text=message_text,
                                    parse_mode=ParseMode.HTML
                                )
                                logger.info(f"Updated message for shipment {shipment_id}")

                                # Update last progress
                                update_last_progress(shipment_id, info, account_data['shipment']['last_progress'])

                                # Update last activity time
                                account_data['shipment']['last_activity_time'][shipment_id] = datetime.now()
                            except Exception as e:
                                logger.error(f"Error updating message: {e}")

        except Exception as e:
            logger.error(f"Error in update_active_shipments_loop for {account_name}: {e}", exc_info=True)

        # Sleep until next iteration
        await asyncio.sleep(CHECK_INTERVAL)

async def send_to_channel(bot, text: str, account_id: str, shipment_id: int,
                          message_type: str = "live") -> Optional[int]:
    """
    Send message to channel with support for dual channel mode or topic mode

    Логика:
    - Если CHANNEL_ID2 указан: отправляет в CHANNEL_ID (live) и CHANNEL_ID2 (completed) без топиков
    - Если топик ID = 1: отправляет в CHANNEL_ID без топика
    - Иначе: отправляет в CHANNEL_ID с указанным топиком

    Args:
        bot: Bot instance
        text: Message text
        account_id: Account ID
        shipment_id: Shipment ID
        message_type: Message type (live or completed)

    Returns:
        Message ID or None on error
    """
    try:
        if CHANNEL_ID2:
            # Режим двух каналов: первый для активных, второй для завершенных
            if message_type == "live":
                message = await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent {message_type} message for shipment {shipment_id} to primary channel (no topic)")
                return message.message_id
            else:  # completed
                message = await bot.send_message(
                    chat_id=CHANNEL_ID2,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent {message_type} message for shipment {shipment_id} to secondary channel (no topic)")
                return message.message_id
        else:
            # Режим одного канала с топиками или без
            topic_id = LIVE_TOPIC_ID if message_type == "live" else COMPLETED_TOPIC_ID

            if topic_id == 1:
                # Отправляем без топика
                message = await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent {message_type} message for shipment {shipment_id} to main channel (no topic)")
                return message.message_id
            else:
                # Отправляем с топиком
                message = await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    message_thread_id=topic_id
                )
                logger.info(f"Sent {message_type} message for shipment {shipment_id} to main channel topic {topic_id}")
                return message.message_id
    except Exception as e:
        logger.error(f"Error sending message to channel: {e}", exc_info=True)
        return None

async def background_monitoring_account(bot, account_id: str) -> None:
    """
    Background monitoring for a specific account

    Args:
        bot: Bot instance
        account_id: Account ID to monitor
    """
    from utils.config import accounts

    account_data = accounts.get(account_id)
    if not account_data or not account_data['enabled']['shipment']:
        logger.error(f"Account {account_id} not found or shipment disabled")
        return

    # Update monitoring start time
    from utils.config import monitoring_start_times
    monitoring_start_times[account_id] = datetime.now()

    # Create aiohttp session
    async with aiohttp.ClientSession() as session:
        # Authenticate
        auth_success, auth_message = await authenticate(session, account_id)

        if not auth_success:
            logger.error(f"Failed to authenticate account {account_id}: {auth_message}")
            return

        # Start monitoring loops
        try:
            # Run both loops in parallel
            await asyncio.gather(
                check_new_shipments_loop(bot, account_id, account_data, session),
                update_active_shipments_loop(bot, account_id, account_data, session)
            )
        except asyncio.CancelledError:
            logger.info(f"Monitoring for account {account_id} cancelled")
        except Exception as e:
            logger.error(f"Error in background monitoring for {account_id}: {e}", exc_info=True)

def start_monitoring(bot, account_id: str) -> bool:
    """
    Start monitoring for a specific account

    Args:
        bot: Bot instance
        account_id: Account ID to monitor

    Returns:
        True if monitoring started, False otherwise
    """
    from utils.config import account_monitoring

    if account_monitoring.get(account_id, False):
        logger.warning(f"Monitoring for account {account_id} already running")
        return False

    # Update monitoring state
    account_monitoring[account_id] = True

    # Create background task
    task = asyncio.create_task(background_monitoring_account(bot, account_id))
    monitoring_tasks[account_id] = task

    logger.info(f"Started monitoring for account {account_id}")
    return True

def stop_monitoring(account_id: str) -> bool:
    """
    Stop monitoring for a specific account

    Args:
        account_id: Account ID to stop monitoring

    Returns:
        True if monitoring stopped, False otherwise
    """
    from utils.config import account_monitoring

    if not account_monitoring.get(account_id, False):
        logger.warning(f"No active monitoring for account {account_id}")
        return False

    # Cancel task
    task = monitoring_tasks.get(account_id)
    if task and not task.done():
        task.cancel()

    # Update monitoring state
    account_monitoring[account_id] = False

    logger.info(f"Stopped monitoring for account {account_id}")
    return True

def stop_all_monitoring() -> None:
    """Stop all active monitoring"""
    from utils.config import account_monitoring

    for account_id in list(monitoring_tasks.keys()):
        stop_monitoring(account_id)

    # Reset monitoring state
    for account_id in account_monitoring:
        account_monitoring[account_id] = False

    logger.info("Stopped all monitoring")

def is_monitoring_active(account_id: str) -> bool:
    """
    Check if monitoring is active for a specific account

    Args:
        account_id: Account ID to check

    Returns:
        True if monitoring is active, False otherwise
    """
    from utils.config import account_monitoring
    return account_monitoring.get(account_id, False)
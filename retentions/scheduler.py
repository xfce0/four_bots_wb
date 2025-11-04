"""
Scheduler functions for retentions monitoring
"""

import logging
from typing import List, Dict, Any
from aiogram import Bot

from utils.config import accounts, RETENTIONS_GROUP, RETENTIONS_TOPIC_ID
from .api import get_retentions_data, merge_retentions_with_drivers
from .formatter import format_retentions_report

logger = logging.getLogger(__name__)


async def send_retentions_alerts(bot: Bot):
    """
    Check for retentions and send alerts if any found
    This function is called by scheduler every hour
    """
    logger.info("Starting scheduled retentions check")

    if not RETENTIONS_GROUP:
        logger.warning("Retentions group not configured, skipping scheduled check")
        return

    # Check all accounts with retentions enabled
    for account_id, account_data in accounts.items():
        if not account_data.get('retentions', {}).get('enabled'):
            continue

        try:
            retentions_config = account_data['retentions']
            token = retentions_config.get('token')
            supplier_id = retentions_config.get('supplier_id')

            if not token or not supplier_id:
                logger.warning(f"Account {account_id} missing token or supplier_id for retentions")
                continue

            account_name = account_data['name']
            logger.info(f"Checking retentions for {account_name}")

            # Get retentions data
            retentions_data = get_retentions_data(token, supplier_id)

            if retentions_data:
                logger.info(f"Found {len(retentions_data)} retentions for {account_name}")

                # Merge with driver info
                merged_retentions = merge_retentions_with_drivers(retentions_data, token)

                # Check for critical retentions (less than 24 hours)
                critical_retentions = [
                    r for r in merged_retentions
                    if r.get('remaining_hours') is not None and r['remaining_hours'] < 24
                ]

                # Format and send report
                if merged_retentions:
                    formatted_text = format_retentions_report(merged_retentions, account_name)

                    # Send to group with topic if configured
                    if RETENTIONS_TOPIC_ID and RETENTIONS_TOPIC_ID > 1:
                        await bot.send_message(
                            chat_id=RETENTIONS_GROUP,
                            text=formatted_text,
                            parse_mode="Markdown",
                            message_thread_id=RETENTIONS_TOPIC_ID
                        )
                    else:
                        await bot.send_message(
                            chat_id=RETENTIONS_GROUP,
                            text=formatted_text,
                            parse_mode="Markdown"
                        )

                    logger.info(f"Sent retentions report for {account_name} to group")

                    # Additional alert for critical retentions
                    if critical_retentions:
                        alert_text = f"🚨 *СРОЧНО!* 🚨\n\n"
                        alert_text += f"Для аккаунта *{account_name}* обнаружено "
                        alert_text += f"*{len(critical_retentions)}* удержаний с критическим сроком (< 24 часов)!\n\n"
                        alert_text += "Требуется срочное вмешательство!"

                        await bot.send_message(
                            chat_id=RETENTIONS_GROUP,
                            text=alert_text,
                            parse_mode="Markdown"
                        )
            else:
                logger.info(f"No retentions found for {account_name}")

        except Exception as e:
            logger.error(f"Error checking retentions for {account_id}: {e}", exc_info=True)
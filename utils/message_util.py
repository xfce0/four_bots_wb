"""
Message utilities for the combined WB bot
Provides helper functions for message updating and management
"""
import logging
from typing import Dict, Any, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.enums import ParseMode

# Configure logging
logger = logging.getLogger(__name__)

# Message state storage - for tracking and updating messages
messages: Dict[int, Dict[str, Any]] = {}

async def update_message(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    message_key: str = None,
    message_id: int = None,
    parse_mode: str = ParseMode.MARKDOWN
) -> int:
    """
    Update an existing message or send a new one

    Args:
        bot: Bot instance
        user_id: User ID
        text: Message text
        reply_markup: Keyboard markup
        message_key: Key for storing the message ID in the messages dict
        message_id: Message ID to update (optional)
        parse_mode: Parse mode for message formatting

    Returns:
        Message ID (either updated or new)
    """
    # Determine message ID to update
    msg_id = message_id

    # If no message_id is provided but we have a message_key, try to get stored message ID
    if not msg_id and message_key and user_id in messages:
        msg_id = messages.get(user_id, {}).get(message_key)

    if msg_id:
        # Try to update existing message
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

            # Store the message ID if message_key is provided
            if message_key:
                if user_id not in messages:
                    messages[user_id] = {}
                messages[user_id][message_key] = msg_id

            return msg_id

        except Exception as e:
            logger.error(f"Error updating message: {e}")
            # Fall through to send new message

    # If update fails or no message ID is provided, send a new message
    try:
        sent_message = await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

        # Store the message ID if message_key is provided
        if message_key:
            if user_id not in messages:
                messages[user_id] = {}
            messages[user_id][message_key] = sent_message.message_id

        return sent_message.message_id

    except Exception as e:
        logger.error(f"Error sending new message: {e}")
        return None
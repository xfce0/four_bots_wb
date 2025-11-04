"""API functions for fetching defects data from Wildberries"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Callable
import re
from utils.config import accounts

logger = logging.getLogger(__name__)


async def get_defects_data(
    account_id: str,
    days: int = 30,
    fetch_drivers: bool = True,
    progress_callback: Optional[Callable[[int, int, str], Any]] = None
) -> Optional[List[Dict[str, Any]]]:
    """Get defects data from WB API for a specific account

    Args:
        account_id: Account ID
        days: Number of days to fetch
        fetch_drivers: If True, fetch driver info for each defect (slower but complete)
        progress_callback: Optional async callback(current, total, account_name) for progress updates
    """
    try:
        account_data = accounts.get(account_id)
        if not account_data:
            logger.error(f"Account {account_id} not found")
            return None

        # Check if defects configuration exists
        defects_config = account_data.get('defects')
        if not defects_config:
            logger.error(f"No defects configuration for account {account_id}")
            return None

        token = defects_config.get('token')
        supplier_id = defects_config.get('supplier_id')

        if not token or not supplier_id:
            logger.error(f"Missing token or supplier_id for account {account_id}")
            return None

        # Define time range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        from_date = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        to_date = end_date.strftime("%Y-%m-%dT%H:%M:%S")

        url = "https://logistics.wb.ru/pretensions/v3/public/pretensions"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        params = {
            "from": from_date,
            "to": to_date,
            "supplier_id": supplier_id,
            "pretension_type": 2  # DEFECTS only
        }

        logger.info(f"Fetching defects for {account_data['name']} for last {days} days")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Extract defects data
                    if isinstance(data, dict) and 'data' in data:
                        defects_data = data['data']
                    elif isinstance(data, list):
                        defects_data = data
                    else:
                        defects_data = []

                    if isinstance(defects_data, list):
                        for item in defects_data:
                            if isinstance(item, dict):
                                item['retention_type'] = 'БРАК'  # Mark as defect
                                item['account_name'] = account_data['name']
                                item['account_id'] = account_id

                    logger.info(f"Got {len(defects_data)} defects for {account_data['name']}")

                    # Fetch driver info for each defect if requested
                    if fetch_drivers and defects_data:
                        logger.info(f"Fetching driver info for {len(defects_data)} defects...")

                        # Collect all transfer_box_ids
                        transfer_box_ids = []
                        for defect in defects_data:
                            transfer_box_id = defect.get('transfer_box_id')
                            if transfer_box_id:
                                transfer_box_ids.append((defect, transfer_box_id))
                            else:
                                defect['driver_name'] = 'Н/Д'

                        # Fetch drivers in parallel batches
                        if transfer_box_ids:
                            batch_size = 20  # Process 20 at a time
                            total_boxes = len(transfer_box_ids)

                            for i in range(0, total_boxes, batch_size):
                                batch = transfer_box_ids[i:i + batch_size]
                                tasks = [get_driver_info(box_id, account_id) for _, box_id in batch]
                                drivers = await asyncio.gather(*tasks, return_exceptions=True)

                                # Assign results
                                for j, (defect, _) in enumerate(batch):
                                    driver = drivers[j]
                                    if isinstance(driver, Exception):
                                        defect['driver_name'] = 'Н/Д'
                                    else:
                                        defect['driver_name'] = driver

                                # Update progress
                                processed = min(i + batch_size, total_boxes)
                                logger.info(f"Processed {processed}/{total_boxes} defects")

                                # Call progress callback if provided
                                if progress_callback:
                                    try:
                                        await progress_callback(processed, total_boxes, account_data['name'])
                                    except Exception as e:
                                        logger.debug(f"Progress callback error: {e}")

                        logger.info("Driver info fetching completed")

                    return defects_data
                else:
                    logger.error(f"API error for {account_data['name']}: {response.status}")
                    text = await response.text()
                    logger.error(f"Response: {text}")
                    return None

    except Exception as e:
        logger.error(f"Error getting defects for {account_id}: {e}")
        return None


async def get_all_defects_data(
    days: int = 30,
    progress_callback: Optional[Callable[[int, int, str], Any]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Get defects data from all configured accounts

    Args:
        days: Number of days to fetch
        progress_callback: Optional async callback(current, total, account_name) for progress updates
    """
    results = {}

    for account_id, account_data in accounts.items():
        if account_data.get('defects', {}).get('enabled', False):
            defects = await get_defects_data(account_id, days, fetch_drivers=True, progress_callback=progress_callback)
            if defects:
                results[account_id] = defects
            else:
                results[account_id] = []

    return results


async def get_driver_info(transfer_box_id: str, account_id: str) -> str:
    """Get driver information by transfer box ID"""
    try:
        account_data = accounts.get(account_id)
        if not account_data:
            return "Н/Д"

        defects_config = account_data.get('defects', {})
        token = defects_config.get('token')

        if not token:
            return "Н/Д"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Try different API endpoints
        api_endpoints = [
            f"https://logistics.wb.ru/transfer-boxes-service/api/v1/transfer-boxes/{transfer_box_id}/shipment-info",
            f"https://logistics.wb.ru/api/v1/transfer-boxes/{transfer_box_id}/details",
            f"https://logistics.wb.ru/pretensions/v3/public/transfer-boxes/{transfer_box_id}/info",
        ]

        async with aiohttp.ClientSession() as session:
            for api_url in api_endpoints:
                try:
                    async with session.get(api_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()

                            # Look for driver name in various fields
                            driver_fields = [
                                ['data', 'driver_name'],
                                ['data', 'driver'],
                                ['data', 'contractor_name'],
                                ['driver_name'],
                                ['driver'],
                                ['contractor_name'],
                            ]

                            for field_path in driver_fields:
                                temp_data = data
                                try:
                                    for field in field_path:
                                        temp_data = temp_data[field]
                                    if temp_data and isinstance(temp_data, str) and temp_data.strip():
                                        return temp_data.strip()
                                except (KeyError, TypeError):
                                    continue

                except Exception as e:
                    logger.debug(f"Error querying {api_url}: {e}")
                    continue

        return "Н/Д"

    except Exception as e:
        logger.error(f"Error getting driver info for box {transfer_box_id}: {e}")
        return "Н/Д"


def extract_driver_from_comment(comment: str) -> Optional[str]:
    """Extract driver name from comment text"""
    if not comment:
        return None

    # Patterns for finding driver name in comments
    patterns = [
        r'[Вв]одитель[:\s]+([А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)*?)(?:\s*\([^)]*\)|[,.\t\n\r]|$)',
        r'[Кк]урьер[:\s]+([А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)*?)(?:[,.\t\n\r]|$)',
        r'[Дд]оставщик[:\s]+([А-Яа-яЁё\.]+(?:\s+[А-Яа-яЁё\.]+)*?)(?:[,.\t\n\r]|$)',
        r'ФИО[:\s]+([А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)*?)(?:[,.\t\n\r]|$)',
        r'[Ии]сполнитель[:\s]+([А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)*?)(?:[,.\t\n\r]|$)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, comment, re.IGNORECASE)
        if matches:
            for match in matches:
                driver_name = match.strip()

                # Validate the name
                invalid_words = [
                    'null', 'none', 'н/д', 'н/а', 'обл', 'ул', 'кра',
                    'коробки', 'путевой', 'лист', 'дата', 'отгрузки'
                ]

                is_valid = (
                    len(driver_name) > 4 and
                    not re.match(r'^\d+$', driver_name) and
                    not any(word in driver_name.lower() for word in invalid_words) and
                    len(driver_name.split()) >= 2
                )

                if is_valid:
                    return driver_name

    return None


def extract_waysheet_number(comment: str) -> str:
    """Extract waysheet number from comment"""
    if not comment:
        return "Н/Д"

    patterns = [
        r'Путевой\s+(\d+)',
        r'путевой\s+(\d+)',
        r'Путевой:\s*(\d+)',
        r'ПЛ\s*(\d+)',
        r'№\s*(\d+)',
        r'waybill\s+(\d+)',
        r'waysheet\s+(\d+)',
        r'\b(\d{4,})\b'  # Any number with 4+ digits
    ]

    for pattern in patterns:
        match = re.search(pattern, comment, re.IGNORECASE)
        if match:
            return match.group(1)

    return "Н/Д"


def is_defect_returned(defect: Dict[str, Any]) -> bool:
    """Check if defect has been returned/refunded"""
    # Check various return indicators
    if defect.get('rop_refund_id') or defect.get('rop_refund_dt'):
        return True

    status_id = defect.get('status_id', 0)
    if status_id == 4:  # Status 4 usually means returned/cancelled
        return True

    refund_status = defect.get('refund_status')
    if refund_status and refund_status.lower() in ['returned', 'refunded', 'cancelled']:
        return True

    refund_amount = defect.get('refund_amount', 0)
    if refund_amount and refund_amount > 0:
        return True

    return False
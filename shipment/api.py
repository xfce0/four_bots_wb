"""
API client for Shipment module
Handles API requests to WB Logistics for shipment monitoring
"""
import logging
import time
import json
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

# Constants
API_BASE_URL = "https://logistics.wb.ru"
AUTH_ENDPOINT = "/news-feed-api/public/v2/feed/status"
SHIPMENTS_ENDPOINT = "/shipments-service/api/v1/shipments"
TRANSFER_BOXES_ENDPOINT = "/logistics-api/api/v1/transfer-boxes/in-transfer"

async def get_with_retry(session: aiohttp.ClientSession, url: str, headers: Dict,
                         params: Dict = None, max_attempts: int = 5) -> Optional[Dict]:
    """
    Send GET request with retry and exponential backoff

    Args:
        session: aiohttp session
        url: API endpoint URL
        headers: Request headers
        params: Request parameters
        max_attempts: Maximum number of retry attempts

    Returns:
        Response data or None on error
    """
    attempt = 0
    while attempt < max_attempts:
        try:
            async with session.get(url, headers=headers, params=params, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401 or response.status == 403:
                    # Authentication error, token expired
                    logger.error(f"Authentication error: {response.status}. Token expired.")
                    return None
                else:
                    logger.warning(f"API error: {response.status}. Attempt {attempt+1}/{max_attempts}")
                    # Exponential backoff
                    await asyncio.sleep(2 ** attempt)
                    attempt += 1
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Request error: {e}. Attempt {attempt+1}/{max_attempts}")
            await asyncio.sleep(2 ** attempt)
            attempt += 1

    logger.error(f"Failed to get {url} after {max_attempts} attempts")
    return None

async def authenticate(session: aiohttp.ClientSession, account_id: str) -> Tuple[bool, str]:
    """
    Authenticate with WB Logistics API and get bearer token

    Args:
        session: aiohttp session
        account_id: Account ID

    Returns:
        Tuple of (success, message)
    """
    from utils.config import accounts

    if account_id not in accounts:
        return False, f"Account {account_id} not found"

    account_data = accounts[account_id]

    try:
        # Use the token from config as bearer token
        token = account_data.get('shipment', {}).get('token')
        if not token:
            logger.error(f"No token configured for account {account_id}")
            return False, "No token configured"

        account_data['shipment']['bearer_token'] = token

        # Verify token with test request
        url = f"{API_BASE_URL}{AUTH_ENDPOINT}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            "Origin": "https://logistics.wildberries.ru",
            "Referer": "https://logistics.wildberries.ru/",
            "sec-ch-ua": '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site"
        }

        logger.info(f"Authenticating account {account_id} with WB API")
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                logger.info(f"Authentication successful for account {account_id}")
                return True, "Token verified successfully"
            else:
                logger.error(f"Authentication failed for account {account_id}: {response.status}")
                return False, f"Authentication failed: {response.status}"
    except Exception as e:
        logger.error(f"Authentication error for account {account_id}: {e}")
        return False, f"Request error: {e}"

async def get_shipments(session: aiohttp.ClientSession, account_id: str, account_data: Dict) -> Optional[List[Dict]]:
    """
    Get active shipments from WB Logistics API

    Args:
        session: aiohttp session
        account_id: Account ID
        account_data: Account data

    Returns:
        List of shipments or None on error
    """
    # Ensure we have bearer token
    if not account_data.get('shipment', {}).get('bearer_token'):
        auth_success, auth_message = await authenticate(session, account_id)
        if not auth_success:
            logger.error(f"Failed to authenticate account {account_id}: {auth_message}")
            return None

    # Set date range (last 3 days)
    now = datetime.now()
    start_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")

    url = f"{API_BASE_URL}{SHIPMENTS_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {account_data['shipment']['bearer_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Origin": "https://logistics.wildberries.ru",
        "Referer": "https://logistics.wildberries.ru/",
        "sec-ch-ua": '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site"
    }

    # Get office_ids list
    office_ids = account_data.get('shipment', {}).get('office_ids', [])
    if not office_ids:
        logger.error(f"No office_ids configured for account {account_id}")
        return []

    # Get supplier_id
    supplier_id = account_data.get('shipment', {}).get('supplier_id')
    if not supplier_id:
        logger.error(f"No supplier_id configured for account {account_id}")
        return []

    all_shipments = []

    # Get shipments for each office_id
    logger.info(f"Getting active shipments for account {account_id}")

    for office_id in office_ids:
        params = {
            "dt_start": start_date,
            "dt_end": end_date,
            "src_office_id": office_id,
            "page_index": 0,
            "limit": 50,
            "supplier_id": supplier_id,
            "show_only_open": "true",
            "direction": -1,
            "sorter": "updated_at"
        }

        response_data = await get_with_retry(session, url, headers, params)

        if not response_data:
            logger.warning(f"Failed to get shipments for office_id {office_id}")
            continue

        # Extract shipments from response
        shipments_data = []
        if isinstance(response_data, dict) and "data" in response_data:
            shipments_data = response_data["data"]
        elif isinstance(response_data, list):
            shipments_data = response_data

        # Process each shipment
        for shipment in shipments_data:
            if isinstance(shipment, dict):
                # Ensure ID field exists
                if "id" not in shipment or shipment["id"] is None:
                    # Try to find ID in other fields
                    if "_id" in shipment:
                        shipment["id"] = shipment["_id"]
                    elif "shipment_id" in shipment:
                        shipment["id"] = shipment["shipment_id"]

                # Add office_id tracking information
                shipment["src_office_id_used"] = office_id
                all_shipments.append(shipment)

        if shipments_data:
            logger.info(f"Got {len(shipments_data)} shipments for office_id {office_id}")

    logger.info(f"Total {len(all_shipments)} shipments for account {account_id}")
    return all_shipments if all_shipments else []

async def get_shipment_details(session: aiohttp.ClientSession, account_data: Dict,
                               shipment_id: int) -> Optional[Dict]:
    """
    Get detailed information about a specific shipment

    Args:
        session: aiohttp session
        account_data: Account data
        shipment_id: Shipment ID

    Returns:
        Shipment details or None on error
    """
    url = f"{API_BASE_URL}{SHIPMENTS_ENDPOINT}/{shipment_id}"
    headers = {
        "Authorization": f"Bearer {account_data['shipment']['bearer_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    logger.info(f"Getting details for shipment {shipment_id}")
    response_data = await get_with_retry(session, url, headers)

    if not response_data:
        logger.error(f"Failed to get details for shipment {shipment_id}")
        return None

    return response_data

async def get_transfer_boxes(session: aiohttp.ClientSession, account_data: Dict,
                             transfer_id: int) -> Optional[List[Dict]]:
    """
    Get information about boxes in a transfer

    Args:
        session: aiohttp session
        account_data: Account data
        transfer_id: Transfer ID

    Returns:
        List of transfer boxes or None on error
    """
    url = f"{API_BASE_URL}{TRANSFER_BOXES_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {account_data['shipment']['bearer_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    params = {
        "transfer_id": transfer_id
    }

    logger.info(f"Getting boxes for transfer {transfer_id}")
    response_data = await get_with_retry(session, url, headers, params)

    if not response_data:
        logger.error(f"Failed to get boxes for transfer {transfer_id}")
        return None

    # Extract boxes from response
    boxes = response_data.get('data', [])
    logger.info(f"Got {len(boxes)} boxes for transfer {transfer_id}")

    return boxes
"""
API module for WB retentions and driver info
"""

import json
import logging
import traceback
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


def api_request_with_retry(url: str, method: str, headers: Dict,
                          data: Optional[Dict] = None,
                          params: Optional[Dict] = None,
                          max_retries: int = 3,
                          timeout: int = 30) -> Optional[requests.Response]:
    """
    Execute API request with retry logic

    Args:
        url: API endpoint URL
        method: HTTP method (GET, POST)
        headers: Request headers
        data: Body data for POST requests
        params: Query parameters for GET requests
        max_retries: Maximum number of retry attempts
        timeout: Request timeout in seconds

    Returns:
        Response object or None if all attempts failed
    """
    for attempt in range(max_retries):
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
            else:  # POST
                response = requests.post(url, headers=headers, json=data, timeout=timeout)

            if response.status_code == 200:
                return response
            elif response.status_code >= 500 and attempt < max_retries - 1:
                logger.warning(f"Server error {response.status_code}, retry {attempt+1}/{max_retries}")
                time.sleep(2)
            else:
                return response

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                logger.warning(f"Connection error: {str(e)}, retry {attempt+1}/{max_retries}")
                time.sleep(2)
            else:
                logger.error(f"All request attempts exhausted: {str(e)}")
                return None

    return None


def get_retentions_data(token: str, supplier_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get retentions data from WB API

    Args:
        token: Bearer token for authentication
        supplier_id: Supplier ID for filtering

    Returns:
        List of retentions or empty list on error
    """
    try:
        logger.info(f"Getting retentions data for supplier {supplier_id}")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        api_url = "https://logistics.wb.ru/lost-and-found-tares/v1/public/lost-and-found"
        params = {"supplier_id": supplier_id}

        response = api_request_with_retry(api_url, 'GET', headers, params=params)

        if response and response.status_code == 200:
            try:
                data = response.json()

                # Check response structure
                if isinstance(data, dict) and 'data' in data:
                    result = data['data']
                elif isinstance(data, list):
                    result = data
                else:
                    result = [data]

                logger.info(f"Received retentions data ({len(result)} records)")
                return result
            except json.JSONDecodeError:
                logger.error("Response is not valid JSON")
                return []
        else:
            status_code = response.status_code if response else "N/A"
            response_text = response.text[:200] if response else "No response"
            logger.error(f"Retentions API error: {status_code} - {response_text}")

            if response:
                if response.status_code == 500:
                    logger.error("Internal server error in retentions API")
                elif response.status_code in [401, 403]:
                    logger.error("Authorization error in retentions API. Check token")

            return []

    except Exception as e:
        logger.error(f"Error getting retentions data: {e}")
        traceback.print_exc()
        return []


def get_driver_info_from_logistics(token: str, tare_ids: List[str]) -> Dict[str, str]:
    """
    Get driver information through API for specified tares

    Args:
        token: Bearer token for authentication
        tare_ids: List of tare IDs

    Returns:
        Dictionary {tare_id: driver_name}
    """
    try:
        logger.info(f"Getting driver info through API for {len(tare_ids)} tares")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        drivers_info = {}

        for tare_id in tare_ids:
            try:
                api_url = f"https://logistics.wb.ru/transfer-boxes-service/api/v1/transfer-boxes/{tare_id}/shipment-info"

                logger.info(f"Requesting info for tare {tare_id}")

                response = api_request_with_retry(api_url, 'GET', headers, timeout=30)

                if response and response.status_code == 200:
                    try:
                        content = response.text
                        logger.debug(f"API response for tare {tare_id}: {content[:200]}...")

                        if content.strip():
                            data = json.loads(content)

                            driver_name = None

                            # Check different possible paths for driver name
                            if 'data' in data and 'driver_name' in data['data']:
                                driver_name = data['data']['driver_name']
                            elif 'driver_name' in data:
                                driver_name = data['driver_name']

                            if driver_name:
                                drivers_info[str(tare_id)] = driver_name
                                logger.info(f"Found driver for tare {tare_id}: {driver_name}")
                            else:
                                logger.warning(f"Response structure doesn't contain driver name for tare {tare_id}")
                        else:
                            logger.warning(f"Empty API response for tare {tare_id}")

                    except json.JSONDecodeError as json_err:
                        logger.error(f"JSON decode error for tare {tare_id}: {json_err}")
                        logger.error(f"Response start: {response.text[:100]}")
                else:
                    status_code = response.status_code if response else "N/A"
                    logger.error(f"API error for tare {tare_id}: {status_code}")
                    if response:
                        logger.error(f"Response: {response.text[:100]}")

            except Exception as e:
                logger.error(f"Error processing tare {tare_id}: {e}")

            # Small pause between requests to avoid overloading API
            time.sleep(0.5)

        logger.info(f"Got driver info for {len(drivers_info)}/{len(tare_ids)} tares")
        return drivers_info

    except Exception as e:
        logger.error(f"Error getting driver info: {e}")
        traceback.print_exc()
        return {}


def merge_retentions_with_drivers(retentions_data: List[Dict], token: str) -> List[Dict]:
    """
    Merge retentions data with driver information and add timers

    Args:
        retentions_data: List of retentions
        token: Bearer token for authentication

    Returns:
        List of retentions with added driver info and timers
    """
    try:
        if not retentions_data:
            logger.error("No retentions data to merge with drivers")
            return []

        # Collect all tare IDs from retentions
        tare_ids = []
        tare_map = {}  # To link tares with retentions

        for retention_idx, retention in enumerate(retentions_data):
            # Get waysheet ID for logging
            waysheet_id = None
            for field in ['waysheet_id', '№', 'id', 'waybillId', 'waysheetId']:
                if field in retention and retention[field]:
                    waysheet_id = str(retention[field])
                    break

            logger.info(f"Processing retention with waysheet ID: {waysheet_id}")

            # Process tares
            for tare in retention.get('tares', []):
                if 'tare_id' in tare and tare['tare_id']:
                    tare_id = str(tare['tare_id'])
                    tare_ids.append(tare_id)
                    # Save connection between tare ID and retention index
                    tare_map[tare_id] = retention_idx
                    logger.debug(f"Added tare {tare_id} for retention with waysheet ID {waysheet_id}")

        logger.info(f"Total collected {len(tare_ids)} tare IDs for driver info")

        # Get driver info by tares
        drivers_info = get_driver_info_from_logistics(token, tare_ids)

        # Add timer info to all retentions
        add_timer_info_to_retentions(retentions_data)

        # Now add driver info for corresponding retentions
        for tare_id, driver_name in drivers_info.items():
            if tare_id in tare_map:
                retention_idx = tare_map[tare_id]
                retention = retentions_data[retention_idx]
                # Add driver only if not already present
                if 'driver_name' not in retention or not retention['driver_name'] or retention['driver_name'] == "Не найдено":
                    retention['driver_name'] = driver_name
                    retention['has_driver_data'] = True
                    logger.info(f"Added driver {driver_name} for retention with tare {tare_id}")

        # Set "Not found" status for retentions without drivers
        for retention in retentions_data:
            if 'driver_name' not in retention or not retention.get('driver_name'):
                retention['driver_name'] = "Не найдено"
                retention['has_driver_data'] = False

        # Count statistics
        matched_count = sum(1 for r in retentions_data if r.get('has_driver_data', False))
        logger.info(f"Total retentions: {len(retentions_data)}, matched with driver data: {matched_count}")

        return retentions_data

    except Exception as e:
        logger.error(f"Error merging retentions with driver data: {e}")
        traceback.print_exc()

        # In case of error, add empty driver info
        for retention in retentions_data:
            retention['driver_name'] = "Ошибка сопоставления"
            retention['has_driver_data'] = False

        return retentions_data


def add_timer_info_to_retentions(retentions_data: List[Dict]) -> None:
    """
    Add timer information to retentions

    Args:
        retentions_data: List of retentions
    """
    for retention in retentions_data:
        created_dt = None
        if 'open_dt' in retention:
            created_dt = retention['open_dt']
        elif 'created_dt' in retention:
            created_dt = retention['created_dt']

        if created_dt:
            try:
                # Convert date string to datetime object
                created_datetime = datetime.fromisoformat(created_dt.replace('Z', '+00:00'))

                # Calculate remaining time (120 hours from creation)
                deadline = created_datetime + timedelta(hours=120)
                now = datetime.now(timezone.utc)
                remaining_time = deadline - now

                # If time hasn't expired yet
                if remaining_time.total_seconds() > 0:
                    hours, remainder = divmod(remaining_time.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)

                    # Add time information
                    retention['remaining_hours'] = int(hours)
                    retention['remaining_minutes'] = int(minutes)
                    retention['remaining_seconds'] = int(seconds)
                    retention['total_remaining_hours'] = round(remaining_time.total_seconds() / 3600, 1)
                    retention['deadline_dt'] = deadline.isoformat()
                else:
                    # Time expired
                    retention['remaining_hours'] = 0
                    retention['remaining_minutes'] = 0
                    retention['remaining_seconds'] = 0
                    retention['total_remaining_hours'] = 0
                    retention['deadline_dt'] = deadline.isoformat()
                    retention['time_expired'] = True
            except Exception as e:
                logger.error(f"Error calculating time for retention: {e}")
                retention['remaining_hours'] = None
                retention['remaining_minutes'] = None
        else:
            # No creation time info
            retention['remaining_hours'] = None
            retention['remaining_minutes'] = None


def get_retention_timers(token: str, supplier_id: str) -> List[Dict[str, Any]]:
    """
    Get retention timers information

    Args:
        token: Bearer token for authentication
        supplier_id: Supplier ID for filtering

    Returns:
        List of retentions with timer info or empty list
    """
    try:
        logger.info(f"Getting retention timers data")

        # Get retentions data
        retentions_data = get_retentions_data(token, supplier_id)

        if not retentions_data:
            logger.info("No retentions data available")
            return []

        # Add timer information
        add_timer_info_to_retentions(retentions_data)

        # Filter only active retentions (with time remaining)
        active_retentions = [
            r for r in retentions_data
            if r.get('remaining_hours') is not None and not r.get('time_expired', False)
        ]

        return active_retentions

    except Exception as e:
        logger.error(f"Error getting retention timers: {e}")
        traceback.print_exc()
        return []
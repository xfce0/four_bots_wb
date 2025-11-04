"""
API client for Ostatki PM module
Handles API requests to WB Logistics for last-mile reports
"""
import requests
import logging
import io
from typing import Dict, Optional, Any, List
import pandas as pd

# Configure logging
logger = logging.getLogger(__name__)

# Constants
WB_API_BASE_URL = 'https://logistics.wb.ru/reports-service/api/v1'

def get_offices_from_api(token: str) -> List[int]:
    """
    Get list of available offices from API

    Args:
        token: Bearer token for authentication

    Returns:
        List of office IDs
    """
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    url = f"{WB_API_BASE_URL}/last-mile"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                office_ids = [office.get('office_id') for office in data['data']]
                return office_ids
    except Exception as e:
        logger.warning(f"Error getting offices from API: {e}")

    return []

def get_wb_report(token: str, office_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Get last-mile report from WB Logistics API

    Args:
        token: Bearer token for authentication
        office_id: Office ID to filter by (optional)

    Returns:
        Report data or None on error
    """
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    url = f"{WB_API_BASE_URL}/last-mile"

    try:
        logger.info(f"🌐 API request to: {url}")
        logger.debug(f"🔑 Using token: {token[:20]}...")

        response = requests.get(url, headers=headers, timeout=30)
        logger.info(f"📈 Response status code: {response.status_code}")

        response.raise_for_status()
        data = response.json()

        logger.debug(f"✅ Response structure: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")

        if data.get('data'):
            total_routes = sum(len(office.get('routes', [])) for office in data['data'])
            logger.info(f"📊 Total routes in response: {total_routes}")

        # Filter by office_id if specified
        if office_id and data.get('data'):
            logger.info(f"🔍 Filtering by office_id: {office_id}")
            data['data'] = [
                office for office in data['data']
                if office.get('office_id') == office_id
            ]
            logger.info(f"   Found offices: {len(data['data'])}")
        else:
            logger.info(f"ℹ️ No office filtering applied (office_id={office_id})")

        return data

    except requests.exceptions.HTTPError as e:
        logger.error(f"❌ HTTP error: {e}")
        if response:
            logger.error(f"📝 Server response: {response.text[:500]}")
        return None
    except Exception as e:
        logger.error(f"❌ Error getting report: {e}", exc_info=True)
        return None

def create_excel_from_json(report_data: dict, account_name: str, account_key: str) -> Optional[bytes]:
    """
    Create Excel file from JSON report data

    Args:
        report_data: Report data from API
        account_name: Account name
        account_key: Account key

    Returns:
        Excel file content as bytes or None on error
    """
    from ostatki.data import get_routes
    from utils.config import SHK_NORMS, FUEL_NORMS, FIXED_PARKING

    if not report_data or not report_data.get('data'):
        return None

    try:
        # Copy norms
        shk_norms = SHK_NORMS.copy()
        fuel_norms = FUEL_NORMS.copy()
        parking = FIXED_PARKING.copy()

        # Add custom route data
        custom_routes = get_routes(account_key)
        if custom_routes:
            for route_id, route_info in custom_routes.items():
                if 'shk_norm' in route_info:
                    shk_norms[route_id] = route_info['shk_norm']
                if 'fuel_norm' in route_info:
                    fuel_norms[route_id] = route_info['fuel_norm']
                if 'parking' in route_info:
                    parking[route_id] = route_info['parking']

        # Create Excel in memory
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for office in report_data['data']:
                office_id = office.get('office_id', 'Unknown')
                office_name = office.get('office_name', 'Unknown')
                routes = office.get('routes', [])

                if not routes:
                    continue

                # Prepare data for DataFrame
                rows = []
                for route in routes:
                    route_id = route.get('route_car_id', 'N/A')
                    count_shk = route.get('count_shk', 0)
                    count_tares = route.get('count_tares', 0)
                    volume_ml = route.get('volume_ml_by_content', 0)
                    volume_liters = volume_ml / 1000
                    fuel = route.get('normative_liters', 0)

                    # SHK norm
                    fixed_shk_norm = shk_norms.get(route_id, 0)

                    # Fuel norm
                    if fuel > 0:
                        fixed_fuel_norm = fuel
                    elif route_id in fuel_norms:
                        fixed_fuel_norm = fuel_norms[route_id]
                    else:
                        fixed_fuel_norm = volume_liters

                    # Parking
                    parking_value = parking.get(route_id, '')
                    if not parking_value:
                        api_parking = route.get('parking', [])
                        if api_parking and len(api_parking) > 0:
                            parking_value = str(api_parking[0])

                    rows.append({
                        'Парковка': parking_value,
                        'ID маршрута': route_id,
                        'Кол-во ШК': count_shk,
                        'Норма ШК': fixed_shk_norm,
                        'Кол-во мест': count_tares,
                        'Кол-во литров': round(volume_liters, 2),
                        'Норма литров': round(fixed_fuel_norm, 2)
                    })

                # Create DataFrame and write to sheet
                df = pd.DataFrame(rows)
                # Limit sheet name length (Excel max 31 chars)
                sheet_name = f"{office_name[:20]}_{office_id}"
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        output.seek(0)
        return output.read()

    except Exception as e:
        logger.error(f"Error creating Excel: {e}", exc_info=True)
        return None
"""
Formatter for Ostatki PM module
Formats last-mile report data into text format
"""
from datetime import datetime
import logging
from typing import Dict, Any

from ostatki.data import get_routes
from utils.config import SHK_NORMS, FUEL_NORMS, FIXED_PARKING

# Configure logging
logger = logging.getLogger(__name__)

def format_last_mile_text(report_data: Dict[str, Any], account_name: str, account_key: str) -> str:
    """
    Format last-mile report data into text with color indicators

    Args:
        report_data: Report data from API
        account_name: Account name
        account_key: Account key

    Returns:
        Formatted text report
    """
    if not report_data:
        return f"Отчет для {account_name} пуст или произошла ошибка при получении данных."

    try:
        # Copy base norms
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

        # Special rules for certain routes
        special_day_routes = ['13', '78', '9']
        current_hour = datetime.now().hour

        formatted_text = ""

        logger.info(f"📝 Formatting report for {account_name}")
        logger.info(f"📊 Offices in data: {len(report_data.get('data', []))}")

        for office in report_data.get('data', []):
            office_id = office.get('office_id', 'Unknown')
            office_name = office.get('office_name', 'Unknown')

            formatted_text += f"{office_name} ({office_id})\n"
            formatted_text += f"По состоянию на {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            routes = office.get('routes', [])
            logger.info(f"   Office {office_id}: {len(routes)} routes")

            if routes:
                for route in routes:
                    route_id = route.get('route_car_id', 'N/A')
                    fuel = route.get('normative_liters', 0)
                    count_shk = route.get('count_shk', 0)
                    count_tares = route.get('count_tares', 0)
                    volume = route.get('volume_ml_by_content', 0)

                    fixed_shk_norm = shk_norms.get(route_id, 0)

                    # Determine fuel norm
                    if fuel > 0:
                        fixed_fuel_norm = fuel
                    elif route_id in fuel_norms:
                        fixed_fuel_norm = fuel_norms[route_id]
                    else:
                        fixed_fuel_norm = volume / 1000

                    # Get parking: priority: custom data > FIXED_PARKING > API
                    parking_value = parking.get(route_id, '')

                    # If parking not in manual data, try API
                    if not parking_value:
                        api_parking = route.get('parking', [])
                        if api_parking and len(api_parking) > 0:
                            parking_value = str(api_parking[0])
                            logger.debug(f"      Parking {parking_value} for route {route_id} from API")
                        else:
                            parking_value = ''
                            logger.debug(f"      Parking for route {route_id} not found")
                    else:
                        logger.debug(f"      Parking {parking_value} for route {route_id} from manual data")

                    # Color indicator logic (commented out as in the original code)
                    color_indicator = ""

                    # Uncomment this section to enable color indicators based on specific rules
                    # Color logic can be customized here

                    formatted_text += f"{color_indicator}*Парковка {parking_value}*, *ID {route_id}*, "
                    formatted_text += f"Кол-ва ШК {count_shk}, "

                    # Add SHK norm only if it's not 0
                    if fixed_shk_norm > 0:
                        formatted_text += f"норма ШК {fixed_shk_norm}, "

                    formatted_text += f"Кол-ва мест {count_tares}, "
                    formatted_text += f"Кол-ва литров {volume/1000:.2f}, "
                    formatted_text += f"Норма литров {fixed_fuel_norm:.2f}\n\n\n"
            else:
                formatted_text += "🚫 Нет данных о маршрутах\n"

        return formatted_text

    except Exception as e:
        logger.error(f"Error formatting report: {e}", exc_info=True)
        return f"Ошибка при форматировании отчета для {account_name}: {e}"
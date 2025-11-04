"""
Data management for Ostatki PM module
Handles loading and saving custom route data
"""
import os
import pickle
import logging
from typing import Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

# Constants
ROUTES_FILE = 'routes_data.pkl'

# Global storage
routes_data: Dict[str, Dict[int, Dict[str, Any]]] = {}

def load_routes() -> Dict[str, Dict[int, Dict[str, Any]]]:
    """
    Load routes data from pickle file

    Returns:
        Dictionary with custom route data
    """
    global routes_data
    if os.path.exists(ROUTES_FILE):
        try:
            with open(ROUTES_FILE, 'rb') as f:
                routes_data = pickle.load(f)
            logger.info(f"Loaded route data: {len(routes_data)} accounts with custom routes")
            return routes_data
        except Exception as e:
            logger.error(f"Error loading routes data: {e}", exc_info=True)
            routes_data = {}
            return {}
    else:
        logger.info("No routes file found, starting with empty routes dict")
        routes_data = {}
        return {}

def save_routes() -> bool:
    """
    Save routes data to pickle file

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        with open(ROUTES_FILE, 'wb') as f:
            pickle.dump(routes_data, f)
        logger.info(f"Saved routes data: {len(routes_data)} accounts with custom routes")
        return True
    except Exception as e:
        logger.error(f"Error saving routes data: {e}", exc_info=True)
        return False

def add_route(account_key: str, route_id: int, parking: str, shk_norm: int,
              fuel_norm: float = None, user_id: int = None) -> bool:
    """
    Add custom route data

    Args:
        account_key: Account identifier
        route_id: Route ID
        parking: Parking number
        shk_norm: SHK norm value
        fuel_norm: Fuel norm value (optional)
        user_id: User ID who added the route (optional)

    Returns:
        True if added successfully, False otherwise
    """
    from datetime import datetime

    try:
        if account_key not in routes_data:
            routes_data[account_key] = {}

        route_data = {
            'parking': parking,
            'shk_norm': shk_norm,
            'added_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        if fuel_norm is not None:
            route_data['fuel_norm'] = fuel_norm

        if user_id is not None:
            route_data['added_by'] = user_id

        routes_data[account_key][route_id] = route_data
        return save_routes()
    except Exception as e:
        logger.error(f"Error adding route: {e}", exc_info=True)
        return False

def get_routes(account_key: str = None) -> Dict:
    """
    Get all routes data or routes for specific account

    Args:
        account_key: Account identifier (optional)

    Returns:
        Dictionary with routes data
    """
    if account_key is None:
        return routes_data
    else:
        return routes_data.get(account_key, {})

# Load routes data on module import
load_routes()
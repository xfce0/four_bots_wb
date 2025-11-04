"""
Unified configuration and account management for the combined WB bot
Loads data from .env file and manages accounts for both Ostatki PM and Shipment functionality
"""
import os
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in .env file")

# Group/Channel Configuration
GROUP_ID = os.getenv("GROUP_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")
LIVE_TOPIC_ID = int(os.getenv("LIVE_TOPIC_ID", "1"))
COMPLETED_TOPIC_ID = int(os.getenv("COMPLETED_TOPIC_ID", "1"))

# Additional channels for specific purposes
COMPLETED_SHIPMENTS_CHANNEL = os.getenv("COMPLETED_SHIPMENTS_CHANNEL")
ACTIVE_SHIPMENTS_CHANNEL = os.getenv("ACTIVE_SHIPMENTS_CHANNEL")
RETENTIONS_GROUP = os.getenv("RETENTIONS_GROUP")
RETENTIONS_TOPIC_ID = int(os.getenv("RETENTIONS_TOPIC_ID", "1"))

# Secondary channel configuration (optional)
CHANNEL_ID2 = os.getenv("CHANNEL_ID2")
if CHANNEL_ID2:
    CHANNEL_ID2 = int(CHANNEL_ID2)

# Ostatki PM Configuration
REPORT_INTERVAL_MINUTES = int(os.getenv("REPORT_INTERVAL_MINUTES", "10"))
OSTATKI_PM_CHANNEL = os.getenv("OSTATKI_PM_CHANNEL")  # Канал для отчетов остатков ПМ

# Shipment Monitoring Configuration
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "60"))
INACTIVITY_TIMEOUT = int(os.getenv("INACTIVITY_TIMEOUT", "300"))

def load_accounts() -> Dict[str, Dict[str, Any]]:
    """
    Load account configuration from .env file
    Each account can be used by both bots (Ostatki PM and Shipment)
    Format:
        ACCOUNT1_NAME="Account Name"
        ACCOUNT1=bearer_token_for_ostatki_pm
        ACCOUNT1_TOKEN=bearer_token_for_shipment
        ACCOUNT1_OFFICE_ID=123456,654321
        ACCOUNT1_SUPPLIER_ID=1234567

    Returns:
        Dict with account configurations
    """
    accounts = {}
    account_num = 1

    while True:
        account_key = f"account_{account_num}"
        name = os.getenv(f"ACCOUNT{account_num}_NAME")

        # Tokens for both bots
        ostatki_token = os.getenv(f"ACCOUNT{account_num}")
        shipment_token = os.getenv(f"ACCOUNT{account_num}_TOKEN")
        retentions_token = os.getenv(f"ACCOUNT{account_num}_RETENTIONS_TOKEN")
        defects_token = os.getenv(f"ACCOUNT{account_num}_DEFECTS_TOKEN")

        # Office IDs (can be multiple, comma-separated)
        office_id_str = os.getenv(f"ACCOUNT{account_num}_OFFICE_ID")
        supplier_id = os.getenv(f"ACCOUNT{account_num}_SUPPLIER_ID")
        retentions_supplier_id = os.getenv(f"ACCOUNT{account_num}_RETENTIONS_SUPPLIER_ID")
        defects_supplier_id = os.getenv(f"ACCOUNT{account_num}_DEFECTS_SUPPLIER_ID")

        # If no name or no tokens are found, we've reached the end of accounts
        if not name or (not ostatki_token and not shipment_token and not retentions_token and not defects_token):
            break

        # Parse office IDs
        office_ids = []
        if office_id_str:
            office_ids = [int(oid.strip()) for oid in office_id_str.split(",") if oid.strip()]

        # Create account structure
        accounts[account_key] = {
            "name": name,
            "ostatki": {
                "token": ostatki_token,
                "office_id": office_ids[0] if office_ids else None  # Ostatki PM uses single office ID
            },
            "shipment": {
                "token": shipment_token,
                "bearer_token": None,  # Will be filled after authentication
                "office_ids": office_ids,  # Shipment uses multiple office IDs
                "supplier_id": int(supplier_id) if supplier_id else None,
                "monitored_shipments": {},
                "last_progress": {},
                "message_ids": {},
                "completed_shipments": set(),
                "processed_shipments": set(),
                "last_activity_time": {}
            },
            "retentions": {
                "token": retentions_token,
                "supplier_id": retentions_supplier_id,
                "enabled": retentions_token is not None and retentions_supplier_id is not None
            },
            "defects": {
                "token": defects_token,
                "supplier_id": defects_supplier_id,
                "enabled": defects_token is not None and defects_supplier_id is not None
            },
            "enabled": {
                "ostatki": ostatki_token is not None,
                "shipment": all([shipment_token, supplier_id, office_ids]),
                "retentions": retentions_token is not None and retentions_supplier_id is not None,
                "defects": defects_token is not None and defects_supplier_id is not None
            }
        }

        account_num += 1

    return accounts

# Load all accounts
accounts = load_accounts()

# Monitoring state for shipment bot
account_monitoring = {account_id: False for account_id in accounts.keys()}
monitoring_start_times = {account_id: None for account_id in accounts.keys()}

# Print loaded accounts info
print(f"Loaded {len(accounts)} accounts:")
for account_id, account_data in accounts.items():
    print(f"  - {account_id}: {account_data['name']}")
    print(f"    Ostatki PM enabled: {account_data['enabled']['ostatki']}")
    print(f"    Shipment enabled: {account_data['enabled']['shipment']}")

# Check if we have any accounts
if not accounts:
    raise ValueError("No accounts found in .env file. Check format: ACCOUNT1_*, ACCOUNT2_*, ...")

# Fixed data for Ostatki PM
# Словарь с фиксированными значениями нормы количества ШК для каждого маршрута
SHK_NORMS = {
    10194: 1158,
    20359: 1186,
    25025: 1123,
    25321: 1112,
    30449: 1147
}

# Словарь с фиксированными значениями нормы литров для каждого маршрута
FUEL_NORMS = {
    10194: 4502.31,
    20359: 4676.61,
    25025: 4258.41,
    25321: 4269.49,
    30449: 4425.83
}

# Фиксированные значения для парковок по маршрутам
FIXED_PARKING = {
    10194: '20',
    20359: '13',
    25025: '36',
    25321: '74',
    28616: '35',
    28751: '135',
    29484: '122',
    29612: '22',
    29738: '120',
    29767: '20',
    30449: '73'
}
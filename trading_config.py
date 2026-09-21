#!/usr/bin/env python3
"""
Trading Configuration Module
=============================
Handles bot configuration for money allocation, timeframe, and risk settings.
Persists configuration to JSON for state recovery.
"""

import json
import eel
from pathlib import Path
from ml.config import settings

CONFIG_FILE = Path("trading_config.json")
AUTOMATION_STATE_FILE = Path("automation_state.json")

# Default configuration
DEFAULT_CONFIG = {
    "riskPercent": 2.0,
    "maxPositionPercent": 10.0,
    "minTradeAmount": 1.0,
    "timeframe": "1m",
    "minTimeBetweenTrades": 5,
    "maxTradesPerDay": 100,
    "startHour": 0,
    "endHour": 23,
    "minConfidence": 50,
    "targetReturn": 2.5,
    "dailyLossLimit": 500,
    "maxDrawdown": 20,
    "selectedPairs": []
}

# Global configuration - loaded from disk or defaults
TRADING_CONFIG = DEFAULT_CONFIG.copy()

def load_config():
    """Load trading configuration from disk if available."""
    global TRADING_CONFIG

    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                loaded = json.load(f)
                TRADING_CONFIG.update(loaded)
                print(f"✅ Trading configuration loaded from {CONFIG_FILE}")
                return TRADING_CONFIG
    except Exception as e:
        print(f"⚠️ Error loading trading config: {e}")

    print(f"📝 Using default trading configuration")
    return TRADING_CONFIG

def persist_config(config):
    """Save configuration to disk."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"💾 Trading configuration persisted to {CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"❌ Error persisting config: {e}")
        return False

def load_automation_state():
    """Load automation enabled/disabled state from disk."""
    try:
        if AUTOMATION_STATE_FILE.exists():
            with open(AUTOMATION_STATE_FILE, 'r') as f:
                state = json.load(f)
                print(f"✅ Automation state loaded: {state}")
                return state.get('enabled', False)
    except Exception as e:
        print(f"⚠️ Error loading automation state: {e}")

    return False

def persist_automation_state(enabled):
    """Save automation enabled/disabled state to disk."""
    try:
        state = {'enabled': enabled, 'timestamp': str(__import__('datetime').datetime.now())}
        with open(AUTOMATION_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"💾 Automation state persisted: {state}")
        return True
    except Exception as e:
        print(f"❌ Error persisting automation state: {e}")
        return False

# Load configuration on module import
load_config()

@eel.expose
def get_trading_config():
    """Get current trading configuration.

    Returns:
        Dict with all trading settings
    """
    global TRADING_CONFIG

    try:
        return TRADING_CONFIG.copy()
    except Exception as e:
        print(f"⚠️ Error getting trading config: {e}")
        return TRADING_CONFIG

@eel.expose
def save_trading_config(config):
    """Save trading configuration and apply to live trader.

    Args:
        config: Dict with trading configuration

    Returns:
        Dict with success status
    """
    global TRADING_CONFIG

    try:
        # Validate config
        if config.get("riskPercent", 0) > 50:
            return {"success": False, "error": "Risk per trade cannot exceed 50%"}

        if config.get("startHour", 0) > config.get("endHour", 23):
            return {"success": False, "error": "Start hour must be before end hour"}

        # Save configuration to memory
        TRADING_CONFIG.update(config)

        # Persist to disk
        if not persist_config(TRADING_CONFIG):
            return {"success": False, "error": "Failed to persist configuration to disk"}

        # Apply to settings module
        settings.min_time_between_trades_sec = config.get("minTimeBetweenTrades", 5)
        settings.max_trades_per_day = config.get("maxTradesPerDay", 100)
        settings.risk_per_trade_percent = config.get("riskPercent", 2.0)
        settings.max_position_size_percent = config.get("maxPositionPercent", 10.0)
        settings.automation_start_hour = config.get("startHour", 0)
        settings.automation_end_hour = config.get("endHour", 23)

        print(f"✅ Trading configuration updated:")
        print(f"   Risk: {config.get('riskPercent')}%")
        print(f"   Timeframe: {config.get('timeframe')}")
        print(f"   Max Trades/Day: {config.get('maxTradesPerDay')}")
        print(f"   Daily Loss Limit: ${config.get('dailyLossLimit')}")
        print(f"   Selected Pairs: {len(config.get('selectedPairs', []))}")

        return {"success": True, "message": "Configuration saved and persisted to disk"}
    except Exception as e:
        print(f"❌ Error saving trading config: {e}")
        return {"success": False, "error": str(e)}

@eel.expose
def get_available_pairs():
    """Get all available trading pairs for configuration.

    Returns:
        List of trading pair names
    """
    try:
        return [
            "USD/INR (OTC)",
            "CHF/JPY (OTC)",
            "CAD/JPY (OTC)",
            "USD/PKR (OTC)",
            "CAD/CHF (OTC)",
            "CHF/JPY",
            "NZD/JPY (OTC)",
            "EUR/USD (OTC)",
            "GBP/USD (OTC)",
            "AUD/CAD (OTC)"
        ]
    except Exception as e:
        print(f"⚠️ Error getting available pairs: {e}")
        return []

def apply_config_to_trader(trader, config):
    """Apply configuration to an automated trader instance.

    Args:
        trader: AutomatedTrader instance
        config: Configuration dict
    """
    if trader:
        trader.min_time_between_trades = config.get("minTimeBetweenTrades", 5)
        trader.max_trades_per_day = config.get("maxTradesPerDay", 100)
        trader.risk_per_trade_percent = config.get("riskPercent", 2.0)
        trader.max_position_size_percent = config.get("maxPositionPercent", 10.0)
        trader.automation_start_hour = config.get("startHour", 0)
        trader.automation_end_hour = config.get("endHour", 23)

def get_config_summary():
    """Get a human-readable summary of current configuration.

    Returns:
        Formatted string with current settings
    """
    global TRADING_CONFIG

    summary = f"""
    ⚙️ TRADING CONFIGURATION SUMMARY
    {'='*50}
    💰 Risk Management:
       - Risk Per Trade: {TRADING_CONFIG.get('riskPercent')}%
       - Max Position: {TRADING_CONFIG.get('maxPositionPercent')}%
       - Minimum Trade: ${TRADING_CONFIG.get('minTradeAmount')}

    ⏱️ Trading Frequency:
       - Timeframe: {TRADING_CONFIG.get('timeframe')}
       - Min Time Between Trades: {TRADING_CONFIG.get('minTimeBetweenTrades')}s
       - Max Trades/Day: {TRADING_CONFIG.get('maxTradesPerDay')}

    🕐 Trading Hours:
       - Start: {TRADING_CONFIG.get('startHour')}:00
       - End: {TRADING_CONFIG.get('endHour')}:00

    📊 Signal Confidence:
       - Minimum: {TRADING_CONFIG.get('minConfidence')}%
       - Expected Return: {TRADING_CONFIG.get('targetReturn')}%

    ⛔ Loss Limits:
       - Daily Loss Limit: ${TRADING_CONFIG.get('dailyLossLimit')}
       - Max Drawdown: {TRADING_CONFIG.get('maxDrawdown')}%

    📈 Selected Pairs: {len(TRADING_CONFIG.get('selectedPairs', []))}
       {', '.join(TRADING_CONFIG.get('selectedPairs', []))}
    """

    return summary

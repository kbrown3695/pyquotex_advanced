#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quotex Pro Trader — EEL + ASYNCIO STABLE v3.3 (COUNTDOWN FIX)
✅ Hard Ping (get_balance) كل 60 ثانية
✅ Timeout على get_realtime_price (5 ثوانٍ)
✅ كشف "zombie connection" بعد 30 ثانية
✅ Forced resubscription دورية كل 60 ثانية
✅ أوقات استجابة أسرع: idle=30s, ping=60s
✅ [جديد] SERVER_TIME_OFFSET بـ EMA smoothing — يمنع flutter
✅ [جديد] Rate-limit على send_to_ui (max كل 500ms) — يمنع تعارض العدّاد
✅ [جديد] candle_start_time ثابت في الـ payload — JS يحسب countdown محلياً
✅ [جديد] asyncio.sleep(0.05) بدل 0.2 — أقل jitter
"""
import warnings
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.*")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning)  # Suppress all UserWarnings from dependencies

import asyncio
import threading
import time
import json
import os
import sys
import eel
import certifi
from pathlib import Path
from queue import Queue, Full
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# ✅ Load .env file
load_dotenv()

# ✅ Auto-login credentials from .env
QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")

if QUOTEX_EMAIL and QUOTEX_PASSWORD:
    print(f"[OK] .env loaded: {QUOTEX_EMAIL}")
else:
    print("[WARN] No .env credentials found")

# ✅ SSL Setup
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['WEBSOCKET_CLIENT_CA_BUNDLE'] = certifi.where()

try:
    from pyquotex.stable_api import Quotex
    from pyquotex.utils.processor import process_candles
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("Run: pip install git+https://github.com/cleitonleonel/pyquotex.git@master")
    sys.exit(1)

try:
    from ml_signals import EnsembleSignalGenerator
except ImportError as e:
    print(f"⚠️ ML signals not available: {e}")
    EnsembleSignalGenerator = None

try:
    from ml.serving.signal_service import MLSignalService
except ImportError as e:
    print(f"⚠️ ML signal service not available: {e}")
    MLSignalService = None

try:
    from ml.trading.trading_session import BinaryOptionsTradingSession
except ImportError as e:
    print(f"⚠️ Trading session not available: {e}")
    BinaryOptionsTradingSession = None

# ✅ Critical imports with detailed error handling
CandleStore = None
TimeframeAggregator = None

try:
    from ml.data.candle_store import CandleStore
    print("[OK] ✅ CandleStore imported successfully")
except Exception as e:
    print(f"⚠️ CandleStore import failed: {type(e).__name__}: {e}")
    print(f"   → Falling back to in-memory candle aggregation")
    CandleStore = None

try:
    from ml.data.timeframe_aggregator import TimeframeAggregator
    print("[OK] ✅ TimeframeAggregator imported successfully")
except Exception as e:
    print(f"⚠️ TimeframeAggregator import failed: {type(e).__name__}: {e}")
    TimeframeAggregator = None

try:
    from ml.serving.async_signal_manager import AsyncSignalManager
except ImportError as e:
    print(f"⚠️ Async signal manager not available: {e}")
    AsyncSignalManager = None

try:
    from ml.data.candle_aggregator_bg import BackgroundCandleAggregator
    print("[OK] ✅ BackgroundCandleAggregator imported successfully")
except Exception as e:
    print(f"⚠️ BackgroundCandleAggregator import failed: {type(e).__name__}: {e}")
    BackgroundCandleAggregator = None

# ✅ Phase H: Constraint Tracking & Automation
try:
    from ml.trading.account_constraint_tracker import AccountConstraintTracker
    print("[OK] ✅ AccountConstraintTracker imported successfully")
except ImportError as e:
    print(f"⚠️ AccountConstraintTracker import failed: {e}")
    AccountConstraintTracker = None

try:
    from ml.serving.websocket_health_monitor import WebSocketHealthMonitor
    print("[OK] ✅ WebSocketHealthMonitor imported successfully")
except ImportError as e:
    print(f"⚠️ WebSocketHealthMonitor import failed: {e}")
    WebSocketHealthMonitor = None

try:
    from ml.trading.automated_trader import AutomatedTrader
    print("[OK] ✅ AutomatedTrader imported successfully")
except ImportError as e:
    print(f"⚠️ AutomatedTrader import failed: {e}")
    AutomatedTrader = None

try:
    from ml.serving.auto_trading_manager import AutoTradingManager
    print("[OK] ✅ AutoTradingManager imported successfully")
except ImportError as e:
    print(f"⚠️ AutoTradingManager import failed: {e}")
    AutoTradingManager = None

try:
    from ml.trading.order_executor import OrderExecutor
    print("[OK] ✅ OrderExecutor imported successfully")
except ImportError as e:
    print(f"⚠️ OrderExecutor import failed: {e}")
    OrderExecutor = None

try:
    from ml.trading.position_tracker import PositionTracker
    print("[OK] ✅ PositionTracker imported successfully")
except ImportError as e:
    print(f"⚠️ PositionTracker import failed: {e}")
    PositionTracker = None

# ======================
# ⚙️ CONFIG & LOGGING
# ======================
CONSOLE_LEVEL = 1  # 0=Silent, 1=Minimal, 2=Verbose
def log(msg: str, level: int = 1):
    if level <= CONSOLE_LEVEL:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

# ======================
# Async Loop Manager
# ======================
ASYNC_LOOP = None

def start_async_engine():
    global ASYNC_LOOP
    ASYNC_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(ASYNC_LOOP)
    log("🔄 Async engine started", level=2)
    ASYNC_LOOP.run_forever()

async_thread = threading.Thread(target=start_async_engine, daemon=True, name="AsyncEngine")
async_thread.start()
time.sleep(0.3)
if ASYNC_LOOP is None:
    print("❌ Failed to initialize Async Loop")
    sys.exit(1)

# ======================
# UI Update Queue
# ======================
UI_QUEUE = Queue(maxsize=100)  # ✅ Increased from 50 to 100
QUEUE_OVERFLOW_COUNT = 0
QUEUE_LAST_OVERFLOW_LOG = 0

def ui_loop():
    global QUEUE_OVERFLOW_COUNT, QUEUE_LAST_OVERFLOW_LOG
    last_log_time = time.time()
    update_count = 0

    while True:
        try:
            payload = UI_QUEUE.get()
            if payload is None:
                break

            update_count += 1
            # ✅ Log every 10th update to avoid spam
            if update_count % 10 == 0:
                log(f"📨 UI_LOOP: Sending update #{update_count} ({payload['mode']}) to frontend", 2)

            result = eel.updateChart(payload)()

            UI_QUEUE.task_done()
            QUEUE_OVERFLOW_COUNT = 0  # Reset on successful send

        except Exception as e:
            log(f"❌ [UI_LOOP ERROR] Failed to send update: {type(e).__name__}: {e}", 1)
            time.sleep(0.1)
threading.Thread(target=ui_loop, daemon=True, name="UIUpdater").start()

# ======================
# Global State
# ======================
LAST_TICK_TIME = time.time()
LAST_SUBSCRIPTION_TIME = time.time()
SAVED_EMAIL = None
SAVED_PASSWORD = None
IS_RECONNECTING = False
RECONNECT_COOLDOWN = 30
LAST_RECONNECT_TIME = 0

# ML Signal Generators
ENSEMBLE_GENERATOR = EnsembleSignalGenerator() if EnsembleSignalGenerator else None

# Phase 2: Initialize trading session for money/risk management
TRADING_SESSION = None
if BinaryOptionsTradingSession:
    try:
        TRADING_SESSION = BinaryOptionsTradingSession(starting_balance=1000)
        print(f"✅ Trading session initialized: $1000 account")
    except Exception as e:
        print(f"⚠️ Failed to initialize trading session: {e}")

ML_SERVICE = MLSignalService(trading_session=TRADING_SESSION) if MLSignalService else None
# ML_SERVICE now includes:
# - Phase A: Ensemble, Kalman, ExpectedReturn, Probability (4 models)
# - Phase B: GradientBoosting Directional/Return, Volatility, Quantile (5 models)
# - Phase D: RL Agent (1 model)
# - Phase E: LSTM, Transformer (2 models)
# - Phase 1.5: Binary Options features enrichment
# - Phase 2: Money/Risk management with Kelly Criterion sizing
# - Binary Options: ReversalPredictorModel (1 model) - timing for position sizing
# Total: 15 models + position sizing recommendations + reversal timing

# Initialize SIGNAL_MANAGER eagerly (not lazily) so it's ready when frontend polls
SIGNAL_MANAGER = None
try:
    if ML_SERVICE and AsyncSignalManager:
        SIGNAL_MANAGER = AsyncSignalManager(ML_SERVICE)
        print(f"✅ SIGNAL_MANAGER initialized: {SIGNAL_MANAGER}")
        log("🔗 AsyncSignalManager initialized at module load", 1)
    else:
        print(f"⚠️ Cannot init: ML_SERVICE={ML_SERVICE is not None}, AsyncSignalManager={AsyncSignalManager is not None}")
        log(f"⚠️ Cannot initialize AsyncSignalManager: ML_SERVICE={ML_SERVICE is not None}, AsyncSignalManager={AsyncSignalManager is not None}", 1)
except Exception as e:
    print(f"❌ SIGNAL_MANAGER init failed: {e}")
    import traceback
    traceback.print_exc()
    SIGNAL_MANAGER = None

# ✅ Phase H: Initialize Constraint Tracking & Health Monitoring
CONSTRAINT_TRACKER = None
HEALTH_MONITOR = None
ORDER_EXECUTOR = None
POSITION_TRACKER = None
AUTOMATED_TRADER = None

if AccountConstraintTracker:
    try:
        CONSTRAINT_TRACKER = AccountConstraintTracker()
        print(f"✅ AccountConstraintTracker initialized")
    except Exception as e:
        print(f"⚠️ AccountConstraintTracker init failed: {e}")

if WebSocketHealthMonitor:
    try:
        HEALTH_MONITOR = WebSocketHealthMonitor()
        print(f"✅ WebSocketHealthMonitor initialized")
    except Exception as e:
        print(f"⚠️ WebSocketHealthMonitor init failed: {e}")

if OrderExecutor:
    try:
        ORDER_EXECUTOR = OrderExecutor()
        print(f"✅ OrderExecutor initialized")
    except Exception as e:
        print(f"⚠️ OrderExecutor init failed: {e}")

if PositionTracker:
    try:
        POSITION_TRACKER = PositionTracker()
        print(f"✅ PositionTracker initialized")
    except Exception as e:
        print(f"⚠️ PositionTracker init failed: {e}")

if AutomatedTrader and CONSTRAINT_TRACKER and HEALTH_MONITOR:
    try:
        AUTOMATED_TRADER = AutomatedTrader(
            constraint_tracker=CONSTRAINT_TRACKER,
            health_monitor=HEALTH_MONITOR,
            order_executor=ORDER_EXECUTOR,
            position_tracker=POSITION_TRACKER
        )
        print(f"✅ AutomatedTrader initialized (demo mode enabled)")
    except Exception as e:
        print(f"⚠️ AutomatedTrader init failed: {e}")

# ✅ Phase H: Initialize Auto Trading Manager (loads selected pairs)
AUTO_TRADING_MANAGER = None
if AutoTradingManager and AUTOMATED_TRADER and CONSTRAINT_TRACKER and HEALTH_MONITOR:
    try:
        AUTO_TRADING_MANAGER = AutoTradingManager(
            constraint_tracker=CONSTRAINT_TRACKER,
            health_monitor=HEALTH_MONITOR,
            automated_trader=AUTOMATED_TRADER,
            pairs_file="selected_signal_pairs.json"
        )
        print(f"✅ AutoTradingManager initialized with selected pairs")
    except Exception as e:
        print(f"⚠️ AutoTradingManager init failed: {e}")
        AUTO_TRADING_MANAGER = None

# ✅ تحسين #5: أوقات محسّنة للاستقرار
TICK_IDLE_THRESHOLD   = 90   # ✅ Increased from 30s to reduce false reconnects
PING_INTERVAL         = 90   # ✅ Increased from 60s
RESUB_INTERVAL        = 60   # ✅ Increased from 30s
HARD_PING_INTERVAL    = 60   # ✅ Kept stable
EMPTY_TICK_RESUB_THRESHOLD = 30  # ✅ Increased from 12
MAX_CONSECUTIVE_EMPTY = 100  # ✅ Increased from 50

ASSET_DISPLAY_MAP: Dict[str, str] = {}
forex_assets = {
    "AUDCAD": "AUD/CAD", "AUDCAD_otc": "AUD/CAD (OTC)", "AUDCHF": "AUD/CHF", "AUDCHF_otc": "AUD/CHF (OTC)",
    "AUDJPY": "AUD/JPY", "AUDJPY_otc": "AUD/JPY (OTC)", "AUDNZD_otc": "AUD/NZD (OTC)", "AUDUSD": "AUD/USD",
    "AUDUSD_otc": "AUD/USD (OTC)", "CADJPY": "CAD/JPY", "CADJPY_otc": "CAD/JPY (OTC)", "CADCHF_otc": "CAD/CHF (OTC)",
    "CHFJPY": "CHF/JPY", "CHFJPY_otc": "CHF/JPY (OTC)", "EURAUD": "EUR/AUD", "EURAUD_otc": "EUR/AUD (OTC)",
    "EURCAD": "EUR/CAD", "EURCAD_otc": "EUR/CAD (OTC)", "EURCHF": "EUR/CHF", "EURCHF_otc": "EUR/CHF (OTC)",
    "EURGBP": "EUR/GBP", "EURGBP_otc": "EUR/GBP (OTC)", "EURJPY": "EUR/JPY", "EURJPY_otc": "EUR/JPY (OTC)",
    "EURNZD_otc": "EUR/NZD (OTC)", "EURSGD_otc": "EUR/SGD (OTC)", "EURUSD": "EUR/USD", "EURUSD_otc": "EUR/USD (OTC)",
    "GBPAUD": "GBP/AUD", "GBPAUD_otc": "GBP/AUD (OTC)", "GBPCAD": "GBP/CAD", "GBPCAD_otc": "GBP/CAD (OTC)",
    "GBPCHF": "GBP/CHF", "GBPCHF_otc": "GBP/CHF (OTC)", "GBPJPY": "GBP/JPY", "GBPJPY_otc": "GBP/JPY (OTC)",
    "GBPNZD_otc": "GBP/NZD (OTC)", "GBPUSD": "GBP/USD", "GBPUSD_otc": "GBP/USD (OTC)", "NZDCAD_otc": "NZD/CAD (OTC)",
    "NZDCHF_otc": "NZD/CHF (OTC)", "NZDJPY_otc": "NZD/JPY (OTC)", "NZDUSD_otc": "NZD/USD (OTC)", "USDCAD": "USD/CAD",
    "USDCAD_otc": "USD/CAD (OTC)", "USDCHF": "USD/CHF", "USDCHF_otc": "USD/CHF (OTC)", "USDJPY": "USD/JPY",
    "USDJPY_otc": "USD/JPY (OTC)", "USDARS_otc": "USD/ARS (OTC)", "USDBDT_otc": "USD/BDT (OTC)", "USDCOP_otc": "USD/COP (OTC)",
    "USDDZD_otc": "USD/DZD (OTC)", "USDEGP_otc": "USD/EGP (OTC)", "USDIDR_otc": "USD/IDR (OTC)", "USDINR_otc": "USD/INR (OTC)",
    "USDMXN_otc": "USD/MXN (OTC)", "USDNGN_otc": "USD/NGN (OTC)", "USDPHP_otc": "USD/PHP (OTC)", "USDPKR_otc": "USD/PKR (OTC)",
    "USDTRY_otc": "USD/TRY (OTC)", "USDZAR_otc": "USD/ZAR (OTC)",
}
ASSET_DISPLAY_MAP.update(forex_assets)

crypto_assets = {
    "ADAUSD_otc": "Cardano (OTC)", "APTUSD_otc": "Aptos (OTC)", "ARBUSD_otc": "Arbitrum (OTC)", "ATOUSD_otc": "ATO (OTC)",
    "AVAUSD_otc": "Avalanche (OTC)", "AXSUSD_otc": "Axie Infinity (OTC)", "BCHUSD_otc": "Bitcoin Cash (OTC)",
    "BNBUSD_otc": "Binance Coin (OTC)", "BONUSD_otc": "Bonk (OTC)", "BTCUSD_otc": "Bitcoin (OTC)", "DASUSD_otc": "Dash (OTC)",
    "DOGUSD_otc": "Dogecoin (OTC)", "DOTUSD_otc": "Polkadot (OTC)", "ETCUSD_otc": "Ethereum Classic (OTC)",
    "ETHUSD_otc": "Ethereum (OTC)", "FLOUSD_otc": "Floki (OTC)", "GALUSD_otc": "Gala (OTC)", "HMSUSD_otc": "Hamster Kombat (OTC)",
    "LINUSD_otc": "Chainlink (OTC)", "LTCUSD_otc": "Litecoin (OTC)", "MELUSD_otc": "Melania Meme (OTC)",
    "SHIBUSD_otc": "Shiba Inu (OTC)", "SOLUSD_otc": "Solana (OTC)", "TIAUSD_otc": "Celestia (OTC)", "TONUSD_otc": "Toncoin (OTC)",
    "TRUUSD_otc": "TrueFi (OTC)", "TRXUSD_otc": "TRON (OTC)", "WIFUSD_otc": "Dogwifhat (OTC)", "XRPUSD_otc": "Ripple (OTC)",
    "ZECUSD_otc": "Zcash (OTC)",
}
ASSET_DISPLAY_MAP.update(crypto_assets)

commodities_assets = {
    "XAUUSD": "Gold", "XAUUSD_otc": "Gold (OTC)", "XAGUSD": "Silver", "XAGUSD_otc": "Silver (OTC)",
    "UKBrent_otc": "UK Brent (OTC)", "USCrude_otc": "US Crude (OTC)",
}
ASSET_DISPLAY_MAP.update(commodities_assets)

stocks_assets = {
    "AXP_otc": "American Express (OTC)", "BA_otc": "Boeing Company (OTC)", "FB_otc": "Facebook (OTC)",
    "INTC_otc": "Intel (OTC)", "JNJ_otc": "Johnson & Johnson (OTC)", "MCD_otc": "McDonald's (OTC)",
    "MSFT_otc": "Microsoft (OTC)", "PFE_otc": "Pfizer Inc (OTC)", "PEPUSD_otc": "PepsiCo (OTC)",
}
ASSET_DISPLAY_MAP.update(stocks_assets)

indices_assets = {
    "DJIUSD": "Dow Jones", "NDXUSD": "NASDAQ 100", "F40EUR": "CAC 40", "FTSGBP": "FTSE 100",
    "HSIHKD": "Hong Kong 50", "IBXEUR": "IBEX 35", "JPXJPY": "Nikkei 225", "CHIA50": "China A50",
    "STXEUR": "EURO STOXX 50",
}
ASSET_DISPLAY_MAP.update(indices_assets)

DISPLAY_TO_INTERNAL = {v: k for k, v in ASSET_DISPLAY_MAP.items()}
ASSET_CATEGORIES = {
    "💱 Forex": list(forex_assets.values()),
    "₿ Crypto": list(crypto_assets.values()),
    "🛢️ Commodities": list(commodities_assets.values()),
    "🏦 Stocks": list(stocks_assets.values()),
    "📊 Indices": list(indices_assets.values()),
}

# Flat list of all available assets for pair selector
ASSETS_LIST = list(ASSET_DISPLAY_MAP.values())

TIMEFRAMES = {
    "5s": 5, "10s": 10, "15s": 15, "30s": 30,
    "1m": 60, "2m": 120, "3m": 180, "5m": 300,
    "10m": 600, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400
}

CLIENT: Optional[Quotex] = None
CURRENT_ASSET = "AUD/CAD (OTC)"
CURRENT_TIMEFRAME = "1m"
# Guards CURRENT_ASSET / CURRENT_TIMEFRAME against cross-thread races:
# they are written from Eel endpoint threads and read by the async loop.
STATE_LOCK = threading.Lock()
CANDLES: Dict[str, Dict[str, List[dict]]] = {}
CURRENT_CANDLE: Dict[str, Dict[str, dict]] = {}
SERVER_TIME_OFFSET = 0.0
LAST_UI_SEND = 0.0
CANDLE_COLORS = {
    "upColor": "#00C510", "downColor": "#ff0000",
    "borderUpColor": "#00C510", "borderDownColor": "#ff0000",
    "wickUpColor": "#00C510", "wickDownColor": "#ff0000"
}
ASSETS_LOADED = False
LOGIN_SUCCESS = False
CHART_OPENED = False
ACTIVE_TASKS: Dict[str, asyncio.Task] = {}
BACKGROUND_TASKS: Dict[str, asyncio.Task] = {}
BACKGROUND_LOADER_TASK = None

# ======================
# Fallback In-Memory Aggregator (for when CandleStore is unavailable)
# ======================
class InMemoryAggregator:
    """Aggregate 1m candles into multiple timeframes in memory."""

    def __init__(self):
        self.aggregated = {}  # {asset: {timeframe: [candles]}}

    def aggregate_1m_to_timeframes(self, asset: str, candle: dict, target_tfs: set = None):
        """Aggregate 1m candle into 5s/10s/15s/30s/4h."""
        if target_tfs is None:
            target_tfs = {"5s", "10s", "15s", "30s", "4h"}

        if asset not in self.aggregated:
            self.aggregated[asset] = {}

        # For sub-minute TFs, we store the 1m candle as-is (simplified aggregation)
        for tf in target_tfs:
            if tf not in self.aggregated[asset]:
                self.aggregated[asset][tf] = []
            # Use 1m data directly for now (proper aggregation would create bars)
            self.aggregated[asset][tf].append(candle)
            # Keep only last 200
            if len(self.aggregated[asset][tf]) > 200:
                self.aggregated[asset][tf] = self.aggregated[asset][tf][-200:]

    def get_candles(self, asset: str, timeframe: str, limit: int = 200) -> List[dict]:
        """Get aggregated candles."""
        candles = self.aggregated.get(asset, {}).get(timeframe, [])
        return candles[-limit:] if candles else []

# ======================
# Phase B: Database & Async Signals
# ======================
CANDLE_STORE = CandleStore("quotex_candles.db") if CandleStore else None
TIMEFRAME_AGGREGATOR = TimeframeAggregator(CANDLE_STORE) if (TimeframeAggregator and CANDLE_STORE) else None
FALLBACK_AGGREGATOR = InMemoryAggregator()  # Always available as fallback
BG_AGGREGATOR = None  # Will be initialized after login
# SIGNAL_MANAGER already initialized at module load (line ~140)

# Default pairs for multi-asset signal generation
DEFAULT_SIGNAL_PAIRS = ["AUD/CAD (OTC)", "EUR/USD (OTC)", "USD/PKR (OTC)", "USD/INR (OTC)"]
SELECTED_PAIRS_FILE = "selected_signal_pairs.json"

def load_selected_pairs() -> List[str]:
    """Load previously selected signal pairs from file."""
    try:
        abs_path = os.path.abspath(SELECTED_PAIRS_FILE)
        print(f"🔍 Looking for pairs file at: {abs_path}")

        if os.path.exists(SELECTED_PAIRS_FILE):
            with open(SELECTED_PAIRS_FILE, 'r', encoding='utf-8') as f:
                pairs = json.load(f)
                if isinstance(pairs, list) and pairs:
                    print(f"✅ Loaded {len(pairs)} saved signal pairs: {pairs}")
                    return pairs
                else:
                    print(f"⚠️ File exists but is empty or invalid JSON")
        else:
            print(f"⚠️ File not found: {abs_path}")
    except Exception as e:
        print(f"⚠️ Failed to load selected pairs: {e}")
        import traceback
        traceback.print_exc()
    print(f"ℹ️ Using default {len(DEFAULT_SIGNAL_PAIRS)} pairs: {DEFAULT_SIGNAL_PAIRS}")
    return DEFAULT_SIGNAL_PAIRS

def save_selected_pairs(pairs: List[str]) -> bool:
    """Save selected signal pairs to file."""
    try:
        with open(SELECTED_PAIRS_FILE, 'w', encoding='utf-8') as f:
            json.dump(pairs, f, indent=2)
        print(f"✅ Saved {len(pairs)} signal pairs to {SELECTED_PAIRS_FILE}: {pairs}")
        log(f"✅ Saved {len(pairs)} signal pairs", 2)
        return True
    except Exception as e:
        print(f"❌ Failed to save selected pairs: {e}")
        log(f"⚠️ Failed to save selected pairs: {e}", 2)
        return False

SIGNAL_PAIRS = load_selected_pairs()

# ======================
# Helpers & Reconnection
# ======================
def is_websocket_connected() -> bool:
    try:
        if not CLIENT or not CLIENT.api:
            return False
        if hasattr(CLIENT.api, '_is_connected'):
            return bool(CLIENT.api._is_connected)
        if hasattr(CLIENT.api, 'check_connect'):
            return CLIENT.api.check_connect()
        return True
    except Exception:
        return False

def update_tick_time():
    global LAST_TICK_TIME
    LAST_TICK_TIME = time.time()

def update_subscription_time():
    global LAST_SUBSCRIPTION_TIME
    LAST_SUBSCRIPTION_TIME = time.time()

def start_background_task(name: str, coro) -> asyncio.Task:
    """Spawn a named background task, replacing any previous instance.

    Prevents duplicate heartbeat/ping loops from accumulating across
    reconnects and repeated logins.
    """
    old = BACKGROUND_TASKS.get(name)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(coro, name=name)
    BACKGROUND_TASKS[name] = task
    return task

async def stop_background_tasks():
    """Cancel all named background tasks and wait for them to settle."""
    tasks = list(BACKGROUND_TASKS.values())
    BACKGROUND_TASKS.clear()
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

def can_reconnect() -> bool:
    """True if enough time has passed since the last reconnect attempt.

    Note: does NOT stamp LAST_RECONNECT_TIME — the caller stamps it only
    when an attempt actually begins, so a blocked/aborted call never burns
    the cooldown.
    """
    return (time.time() - LAST_RECONNECT_TIME) >= RECONNECT_COOLDOWN

async def full_reconnect():
    global CLIENT, IS_RECONNECTING, LOGIN_SUCCESS, ASSETS_LOADED, LAST_RECONNECT_TIME
    if not SAVED_EMAIL or not SAVED_PASSWORD:
        return False
    if IS_RECONNECTING or not can_reconnect():
        return False

    LAST_RECONNECT_TIME = time.time()
    IS_RECONNECTING = True
    log("🔄 Full re-login initiated...", 1)

    for task in list(ACTIVE_TASKS.values()):
        if not task.done():
            task.cancel()
    ACTIVE_TASKS.clear()
    await stop_background_tasks()

    try:
        if CLIENT and CLIENT.api:
            try:
                await asyncio.wait_for(CLIENT.api.close(), timeout=2)
            except Exception:
                pass
        CLIENT = None
        await asyncio.sleep(1.5)

        CLIENT = Quotex(email=SAVED_EMAIL, password=SAVED_PASSWORD, host="qxbroker.com", lang="en")
        check, reason = await CLIENT.connect()
        if not check:
            log(f"❌ Re-login failed: {reason}", 1)
            return False

        try:
            await CLIENT.change_account("PRACTICE")
        except Exception as e:
            log(f"⚠️ Failed to switch account on reconnect: {e}", 1)

        try:
            await CLIENT.get_all_assets()
        except Exception as e:
            log(f"⚠️ Failed to load assets on reconnect: {e}", 1)

        ASSETS_LOADED = True
        LOGIN_SUCCESS = True
        update_tick_time()
        update_subscription_time()

        start_background_task("heartbeat", realtime_heartbeat())
        start_background_task("market_ping", market_activity_ping())
        start_background_task("hard_ping", hard_ping_loop())
        start_background_task("forced_resub", forced_resubscription())

        # Restart background candle aggregator for selected pairs
        global BG_AGGREGATOR
        if BackgroundCandleAggregator and CANDLE_STORE and not BG_AGGREGATOR:
            BG_AGGREGATOR = BackgroundCandleAggregator(CANDLE_STORE)
            start_background_task("bg_candle_aggregator", BG_AGGREGATOR.start())
            log("✅ Background candle aggregator restarted", 1)

        log("✅ Re-login successful", 1)
        return True
    except Exception as e:
        log(f"❌ Reconnection error: {e}", 1)
        return False
    finally:
        IS_RECONNECTING = False
        # ✅ Restart streaming AFTER clearing IS_RECONNECTING flag
        if CHART_OPENED:
            try:
                await start_streaming(CURRENT_ASSET)
            except Exception as e:
                log(f"⚠️ Failed to restart streaming after reconnect: {e}", 1)

# ======================
# ✅ تحسين #1: Hard Ping بـ get_balance
# ======================
async def get_account_balances() -> Dict[str, float]:
    """Get both real and demo account balances from Quotex API.

    Returns:
        Dict with keys: 'real', 'demo', 'current_mode'
        current_mode: 'REAL' or 'PRACTICE'
    """
    try:
        if not CLIENT or not CLIENT.api:
            return {
                'real': 0.0, 'demo': 0.0, 'current_mode': 'UNKNOWN',
                'error': 'Client not ready'
            }

        # Try to get balances from cached account_balance dict (fast path)
        account_balance = getattr(CLIENT.api, 'account_balance', None)
        if account_balance and isinstance(account_balance, dict):
            real_balance = float(account_balance.get('liveBalance', 0.0))
            demo_balance = float(account_balance.get('demoBalance', 0.0))

            current_mode = "REAL" if CLIENT.account_is_demo == 0 else "PRACTICE"

            result = {
                'real': real_balance,
                'demo': demo_balance,
                'current_mode': current_mode,
                'timestamp': time.time()
            }

            log(f"💰 Balances (cached): Real=${real_balance:.2f} Demo=${demo_balance:.2f} Mode={current_mode}", 2)
            return result

        # Fallback: Try get_balance() if account_balance not available
        log("⚠️ account_balance not ready, trying get_balance() fallback", 2)
        try:
            current_balance = await asyncio.wait_for(CLIENT.get_balance(), timeout=2)
        except Exception as e:
            log(f"⚠️ get_balance() fallback failed: {e}", 2)
            current_balance = 0.0

        current_mode = "REAL" if CLIENT.account_is_demo == 0 else "PRACTICE"

        if current_mode == 'REAL':
            result = {'real': float(current_balance) if current_balance else 0.0, 'demo': 0.0}
        else:
            result = {'real': 0.0, 'demo': float(current_balance) if current_balance else 0.0}

        result['current_mode'] = current_mode
        result['timestamp'] = time.time()

        log(f"💰 Balances (fallback): {current_mode}=${result.get(current_mode.lower(), 0):.2f}", 2)
        return result

    except Exception as e:
        import traceback
        log(f"⚠️ Failed to get account balances: {type(e).__name__}: {e}", 1)
        traceback.print_exc()
        return {
            'real': 0.0, 'demo': 0.0, 'current_mode': 'UNKNOWN',
            'error': str(e)
        }


# ✅ Phase H: Update constraints with latest account data
async def update_constraints():
    """Update constraint tracker with latest WebSocket account data."""
    if not CONSTRAINT_TRACKER or not CLIENT or not CLIENT.api:
        return

    try:
        account_balance = getattr(CLIENT.api, 'account_balance', None)
        profile_data = getattr(CLIENT.api, 'profile', None)
        account_is_demo = getattr(CLIENT, 'account_is_demo', 1)

        if account_balance:
            CONSTRAINT_TRACKER.update_from_websocket(
                account_balance=account_balance,
                profile_data=profile_data.__dict__ if profile_data else None,
                account_is_demo=account_is_demo
            )
    except Exception as e:
        log(f"⚠️ Failed to update constraints: {e}", 2)


async def hard_ping_loop():
    while True:
        await asyncio.sleep(HARD_PING_INTERVAL)
        try:
            if CLIENT and CLIENT.api:
                balances = await get_account_balances()
                log(f"💓 Hard ping OK — Real: ${balances['real']:.2f} Demo: ${balances['demo']:.2f} ({balances['current_mode']})", 2)
                update_tick_time()

                # ✅ Phase H: Update constraints and health monitoring
                await update_constraints()

                # Log constraint status periodically
                if CONSTRAINT_TRACKER:
                    status = CONSTRAINT_TRACKER.get_status()
                    if status.get('constraint_status') != 'OK':
                        log(f"⚠️  Constraint Alert: {status.get('halt_reason', 'Unknown')}", 1)
        except asyncio.CancelledError:
            break
        except asyncio.TimeoutError:
            log("⚠️ Hard ping timeout — triggering reconnect", 1)
            if HEALTH_MONITOR:
                HEALTH_MONITOR.record_disconnection()
            asyncio.create_task(full_reconnect())
        except (ConnectionError, OSError) as e:
            log(f"⚠️ Hard ping connection error: {e}", 1)
            if HEALTH_MONITOR:
                HEALTH_MONITOR.record_disconnection()
            asyncio.create_task(full_reconnect())
        except Exception as e:
            log(f"⚠️ Hard ping unexpected error: {type(e).__name__}: {e}", 2)

# ======================
# ✅ تحسين #4: Forced Resubscription دورية
# ======================
async def forced_resubscription():
    while True:
        await asyncio.sleep(RESUB_INTERVAL)
        try:
            if not CLIENT or not CLIENT.api or not CURRENT_ASSET:
                continue
            internal = DISPLAY_TO_INTERNAL.get(CURRENT_ASSET)
            if not internal:
                continue
            period = TIMEFRAMES.get(CURRENT_TIMEFRAME, 60)
            await CLIENT.start_realtime_price(internal, period)
            update_subscription_time()
            log(f"🔁 Forced resub: {CURRENT_ASSET} [{CURRENT_TIMEFRAME}]", 2)
        except asyncio.CancelledError:
            break
        except (ConnectionError, OSError, TimeoutError) as e:
            log(f"⚠️ Resub error: {type(e).__name__}: {e}", 1)
        except Exception as e:
            log(f"⚠️ Resub error: {type(e).__name__}: {e}", 2)

# ======================
# Background Tasks
# ======================
async def realtime_heartbeat():
    """Monitor connection health - detect dead connections by checking if data flows"""
    while True:
        await asyncio.sleep(90)  # ✅ Check every 90 seconds (increased to reduce false disconnects)
        try:
            if CLIENT:
                # ✅ CRITICAL FIX: Check if data is actually flowing
                time_since_tick = time.time() - LAST_TICK_TIME

                # If no data for 35+ seconds, connection is definitely dead
                if time_since_tick > 35:
                    log(f"💀 CRITICAL: No data for {time_since_tick:.0f}s — data stream frozen!", 1)
                    log(f"🔄 Forcing full reconnection NOW", 1)
                    asyncio.create_task(full_reconnect())
                elif not is_websocket_connected():
                    log("⚠️ Heartbeat: WebSocket disconnected, reconnecting...", 1)
                    asyncio.create_task(full_reconnect())
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"⚠️ Heartbeat error: {type(e).__name__}", 2)

async def market_activity_ping():
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            if not CLIENT or not CLIENT.api or not CURRENT_ASSET:
                continue
            internal = DISPLAY_TO_INTERNAL.get(CURRENT_ASSET, "AUDCAD_otc")
            period = TIMEFRAMES.get(CURRENT_TIMEFRAME, 60)
            candles = await CLIENT.get_candles(internal, time.time(), period * 2, period)
            log(f"📡 Market ping: {len(candles) if candles else 0} candles", 2)
        except asyncio.CancelledError:
            break
        except (ConnectionError, OSError) as e:
            log(f"⚠️ Market ping connection error: {type(e).__name__}", 2)
        except Exception as e:
            log(f"⚠️ Market ping error: {type(e).__name__}", 2)

def price_sleep_watcher():
    while True:
        time.sleep(15)
        idle = time.time() - LAST_TICK_TIME
        if idle > TICK_IDLE_THRESHOLD and not IS_RECONNECTING:
            log(f"♻️ Stream idle {idle:.0f}s > {TICK_IDLE_THRESHOLD}s — reconnecting", 1)
            asyncio.run_coroutine_threadsafe(full_reconnect(), ASYNC_LOOP)
threading.Thread(target=price_sleep_watcher, daemon=True, name="PriceWatcher").start()

# ======================
# Candle Processing & UI
# ======================
def process_candle_data(raw_candles: List[dict], period: int) -> List[dict]:
    if not raw_candles:
        return []
    formatted = []
    for c in raw_candles:
        if not isinstance(c, dict):
            continue
        try:
            if not all(k in c for k in ("time", "open", "high", "low", "close")):
                continue
            ts = int(float(c["time"]))
            o = float(c["open"])
            h = float(c["high"])
            l = float(c["low"])
            cl = float(c["close"])

            # ✅ Validation checks to prevent corrupted candles
            if not (o > 0 and h > 0 and l > 0 and cl > 0):
                log(f"⚠️ Candle has non-positive price: {c}", 2)
                continue
            if h < l:
                log(f"⚠️ Candle inverted: high ({h}) < low ({l})", 2)
                continue
            if o > h or o < l or cl > h or cl < l:
                log(f"⚠️ Candle OHLC out of bounds: O={o} H={h} L={l} C={cl}", 2)
                continue
            if ts <= 0:
                continue

            aligned = (ts // period) * period
            formatted.append({
                "time": aligned, "open": o, "high": h,
                "low": l, "close": cl
            })
        except (ValueError, TypeError) as e:
            log(f"⚠️ Candle parse error: {e}", 2)
            continue
    formatted.sort(key=lambda x: x["time"])
    return formatted

def update_candle(asset: str, frame: str, price: float, ts_sec: int, volume: float = 0.0):
    global CANDLES, CURRENT_CANDLE, CANDLE_STORE, TIMEFRAME_AGGREGATOR, FALLBACK_AGGREGATOR
    duration = TIMEFRAMES.get(frame, 60)
    start = (ts_sec // duration) * duration
    curr = CURRENT_CANDLE.get(asset, {}).get(frame, {})
    if not curr or curr.get("time") != start:
        if curr:
            candle_copy = curr.copy()
            CANDLES.setdefault(asset, {}).setdefault(frame, []).append(candle_copy)

            # Save completed candle to database (Phase B)
            if CANDLE_STORE:
                CANDLE_STORE.save_candle(asset, frame, candle_copy)
                # Aggregate 1m candles into other timeframes
                if frame == "1m" and TIMEFRAME_AGGREGATOR:
                    TIMEFRAME_AGGREGATOR.aggregate_to_timeframes(asset, candle_copy)

            # ✅ Also populate fallback in-memory aggregator
            if frame == "1m":
                FALLBACK_AGGREGATOR.aggregate_1m_to_timeframes(asset, candle_copy)

            if len(CANDLES[asset][frame]) > 200:
                CANDLES[asset][frame] = CANDLES[asset][frame][-200:]

        CURRENT_CANDLE.setdefault(asset, {})[frame] = {
            "time": start, "open": price, "high": price, "low": price, "close": price, "volume": volume
        }
    else:
        if price > curr["high"]: curr["high"] = price
        if price < curr["low"]:  curr["low"] = price
        curr["close"] = price
        curr["volume"] = curr.get("volume", 0) + volume

def prune_candle_cache(keep_asset: str):
    """Drop cached candles for all assets except those with active signals.

    Bounds memory while preserving candles for assets with signal generation.
    """
    global SIGNAL_MANAGER
    # Always keep candles for assets with active signal threads
    keep_assets = {keep_asset}
    if SIGNAL_MANAGER and hasattr(SIGNAL_MANAGER, 'threads'):
        for key in SIGNAL_MANAGER.threads.keys():
            # Key format: "ASSET_DISPLAY_NAME_TIMEFRAME", extract asset
            parts = key.rsplit('_', 1)  # Split from right to separate timeframe
            if len(parts) == 2:
                asset = parts[0]
                keep_assets.add(asset)

    # Remove only assets that aren't in keep_assets
    for asset in list(CANDLES.keys()):
        if asset not in keep_assets:
            CANDLES.pop(asset, None)
    for asset in list(CURRENT_CANDLE.keys()):
        if asset != keep_asset:
            CURRENT_CANDLE.pop(asset, None)

def is_cache_fresh(asset: str, tf: str) -> bool:
    """True if the cached last candle covers the currently forming period."""
    candles = CANDLES.get(asset, {}).get(tf)
    if not candles:
        return False
    period = TIMEFRAMES.get(tf, 60)
    server_now = time.time() + SERVER_TIME_OFFSET
    expected_start = (int(server_now) // period) * period
    return candles[-1]["time"] >= expected_start

def send_to_ui(asset: str, timeframe: str, force: bool = False, full: bool = False) -> bool:
    """Push candles to the browser.

    full=True  → complete snapshot; bypasses the rate limit (used on load
                 and asset/timeframe switches, so a snapshot is never dropped).
    full=False → incremental: only the currently forming candle; the JS side
                 merges it via candleSeries.update(). Cuts payload size from
                 ~200 candles to 1 per tick.
    """
    global LAST_UI_SEND, QUEUE_OVERFLOW_COUNT, QUEUE_LAST_OVERFLOW_LOG
    now = time.time()
    # ✅ FIXED: Reduced rate limit from 0.5s to 0.3s to avoid false connection timeouts
    # Frontend timeout is 10s, so we need updates at least every 5-8s
    # With 0.3s rate limit: 10s / 0.3s = ~33 potential updates, very safe margin
    if not (full or force) and (now - LAST_UI_SEND) < 0.3:
        return False
    LAST_UI_SEND = now

    duration = TIMEFRAMES.get(timeframe, 60)
    server_now = now + SERVER_TIME_OFFSET
    candle_start = (int(server_now) // duration) * duration

    if full:
        all_c = CANDLES.get(asset, {}).get(timeframe, []).copy()
        curr = CURRENT_CANDLE.get(asset, {}).get(timeframe)
        if curr:
            if all_c and all_c[-1]["time"] == curr["time"]:
                all_c[-1] = curr
            else:
                all_c.append(curr)
        all_c.sort(key=lambda x: x["time"])
        candles, mode = all_c, "full"
    else:
        curr = CURRENT_CANDLE.get(asset, {}).get(timeframe)
        if not curr:
            return False
        candles, mode = [curr], "update"

    payload = {
        "mode"             : mode,
        "candles"          : candles,
        "asset"            : asset,
        "timeframe"        : timeframe,
        "timeframe_seconds": duration,
        "server_time"      : server_now,
        "candle_start_time": candle_start,
    }
    try:
        UI_QUEUE.put_nowait(payload)
        QUEUE_OVERFLOW_COUNT = 0

        # ✅ Log every 10 successful sends to avoid spam
        if int(time.time() * 10) % 10 == 0:  # ~Every 10th call
            price = payload["candles"][-1]["close"] if payload["candles"] else 0
            log(f"✅ SEND_TO_UI: Queued {mode} for {asset}/{timeframe} @ {price}", 2)

        return True
    except Full:
        QUEUE_OVERFLOW_COUNT += 1
        if now - QUEUE_LAST_OVERFLOW_LOG > 5:  # Log at most once per 5 seconds
            log(f"🚨 UI Queue OVERFLOW — {QUEUE_OVERFLOW_COUNT} updates dropped! Queue full.", 1)
            QUEUE_LAST_OVERFLOW_LOG = now
        return False

# ======================
# 🔥 Realtime Loop
# ======================
async def realtime_price_loop(asset_display: str):
    internal = DISPLAY_TO_INTERNAL.get(asset_display)
    if not internal or not CLIENT:
        return
    log(f"🔄 Loop started: {asset_display}", 1)
    errs = 0
    consecutive_empty = 0
    last_resub_time = 0

    try:
        while True:
            idle_secs = time.time() - LAST_TICK_TIME
            if idle_secs > TICK_IDLE_THRESHOLD and is_websocket_connected():
                log(f"🧟 Zombie detected — connected but idle {idle_secs:.0f}s, resubscribing...", 1)
                try:
                    period = TIMEFRAMES.get(CURRENT_TIMEFRAME, 60)
                    await CLIENT.start_realtime_price(internal, period)
                    update_subscription_time()
                    log("✅ Zombie cured via resubscription", 1)
                    last_resub_time = time.time()
                except Exception as ze:
                    log(f"⚠️ Zombie resub failed: {ze}", 2)
                    asyncio.create_task(full_reconnect())
                    break

            if errs >= 5 and not is_websocket_connected():
                log(f"⚠️ WebSocket disconnected after {errs} errors, attempting recovery...", 1)
                await CLIENT.start_realtime_price(internal, TIMEFRAMES.get(CURRENT_TIMEFRAME, 60))
                update_subscription_time()
                last_resub_time = time.time()
                errs = 0

            try:
                data = await asyncio.wait_for(
                    CLIENT.get_realtime_price(internal),
                    timeout=5
                )
            except asyncio.TimeoutError:
                log(f"⏱️ get_realtime_price timeout ({asset_display})", 2)
                errs += 1
                consecutive_empty += 1
                # FIXED: More aggressive recovery - try resub after just 3-4 timeouts (2 seconds)
                if consecutive_empty >= 3 and (time.time() - last_resub_time) > 2:
                    log(f"⚠️ {consecutive_empty} timeouts detected — attempting immediate recovery", 1)
                    try:
                        period = TIMEFRAMES.get(CURRENT_TIMEFRAME, 60)
                        await CLIENT.start_realtime_price(internal, period)
                        update_subscription_time()
                        last_resub_time = time.time()
                        consecutive_empty = 0
                        errs = 0
                    except Exception as resub_err:
                        log(f"❌ Recovery failed: {resub_err}, triggering full reconnect", 1)
                        asyncio.create_task(full_reconnect())
                        break
                await asyncio.sleep(0.1)  # FIXED: Reduced from 0.5s for faster retries
                continue

            update_tick_time()

            if data and len(data) > 0:
                latest = data[-1]
                price = float(latest.get("price", latest.get("close", 0)))
                ts = int(float(latest.get("time", time.time())))
                if price > 0 and ts > 0:
                    global SERVER_TIME_OFFSET
                    raw_offset = ts - time.time()
                    if SERVER_TIME_OFFSET == 0.0:
                        SERVER_TIME_OFFSET = raw_offset
                    else:
                        SERVER_TIME_OFFSET = SERVER_TIME_OFFSET * 0.9 + raw_offset * 0.1
                    with STATE_LOCK:
                        active = asset_display == CURRENT_ASSET
                        frame = CURRENT_TIMEFRAME
                    # Always update candles (not just for active asset) so background pairs accumulate data
                    update_candle(asset_display, frame, price, ts)
                    # Only send UI updates for the active/viewed asset
                    if active:
                        send_to_ui(asset_display, frame)
                        # ✅ FIXED: Log every successful update for debugging
                        if errs > 0 or consecutive_empty > 0:
                            log(f"✅ {asset_display}: Data flowing (recovered from {errs}e/{consecutive_empty}empty)", 2)
                    errs = 0
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
                    log(f"⚠️ {asset_display}: Invalid price/ts ({price}/{ts})", 2)
            else:
                consecutive_empty += 1
                log(f"⚠️ {asset_display}: Empty data received", 2)

            if consecutive_empty >= EMPTY_TICK_RESUB_THRESHOLD:
                if (time.time() - last_resub_time) > 15:  # ✅ Exponential backoff: wait 15s before resub
                    log(f"⚠️ {consecutive_empty} empty ticks — forcing resub (backoff applied)", 1)
                    try:
                        period = TIMEFRAMES.get(CURRENT_TIMEFRAME, 60)
                        await CLIENT.start_realtime_price(internal, period)
                        update_subscription_time()
                        last_resub_time = time.time()
                        consecutive_empty = 0
                    except Exception:
                        asyncio.create_task(full_reconnect())
                        break
                elif consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                    log(f"❌ {consecutive_empty} empty ticks (max reached) — full reconnect", 1)
                    asyncio.create_task(full_reconnect())
                    break

            await asyncio.sleep(0.05)

    except asyncio.CancelledError:
        log(f"⏹️ Loop stopped: {asset_display}", 2)
    except Exception as e:
        errs += 1
        log(f"⚠️ Loop error ({asset_display}): {e}", 1)
        if errs >= 15:
            asyncio.create_task(full_reconnect())
    finally:
        ACTIVE_TASKS.pop(asset_display, None)

# ======================
# Data Loading & Streaming
# ======================
async def load_timeframe_data(asset: str, tf: str, period: int) -> List[dict]:
    if not CLIENT or not CLIENT.api:
        return []

    # For aggregated timeframes, try database or fallback first
    aggregated_tfs = {"5s", "10s", "15s", "30s", "4h"}
    if tf in aggregated_tfs:
        # Try database first
        if CANDLE_STORE:
            try:
                db_candles = CANDLE_STORE.get_candles(asset, tf, limit=199)
                if db_candles and len(db_candles) > 10:
                    CANDLES.setdefault(asset, {})[tf] = db_candles
                    return db_candles
            except Exception as e:
                log(f"⚠️ Database query failed for {asset}/{tf}: {e}", 2)

        # Try fallback in-memory aggregator
        fallback_candles = FALLBACK_AGGREGATOR.get_candles(asset, tf, limit=199)
        if fallback_candles and len(fallback_candles) > 10:
            CANDLES.setdefault(asset, {})[tf] = fallback_candles
            return fallback_candles

        # If no aggregated data available yet, return empty (will stream real-time)
        log(f"⚠️ No aggregated data for {asset}/{tf}, waiting for real-time stream", 2)
        return []

    # For standard API timeframes, hit Quotex
    internal = DISPLAY_TO_INTERNAL.get(asset, "AUDCAD_otc")
    try:
        hist = await CLIENT.get_candles(internal, time.time(), 199 * period, period)
        loaded = process_candle_data(hist, period)
        CANDLES.setdefault(asset, {})[tf] = loaded[-199:]
        return loaded[-199:]
    except Exception as e:
        log(f"⚠️ Failed to load {tf} data for {asset}: {e}", 2)
        return []

async def chart_opened_loader(asset: str):
    global CHART_OPENED, BACKGROUND_LOADER_TASK
    if CHART_OPENED:
        return
    CHART_OPENED = True
    log("📊 Chart opened", 1)
    await load_timeframe_data(asset, "1m", 60)
    send_to_ui(asset, "1m", force=True, full=True)
    internal = DISPLAY_TO_INTERNAL.get(asset)
    if internal:
        for _ in range(3):
            try:
                await CLIENT.start_realtime_price(internal, 60)
                update_subscription_time()
                break
            except Exception:
                await asyncio.sleep(2)
    task = asyncio.create_task(realtime_price_loop(asset))
    ACTIVE_TASKS[asset] = task
    BACKGROUND_LOADER_TASK = asyncio.create_task(smart_background_loader(asset))

    # Phase B: Pre-load candles from database for all saved pairs, then start signal generation
    global CANDLES, CANDLE_STORE, SIGNAL_PAIRS
    for pair_display in SIGNAL_PAIRS:
        if pair_display not in CANDLES or "1m" not in CANDLES[pair_display]:
            if CANDLE_STORE:
                try:
                    db_candles = CANDLE_STORE.get_candles(pair_display, "1m", limit=200)
                    if db_candles:
                        if pair_display not in CANDLES:
                            CANDLES[pair_display] = {}
                        CANDLES[pair_display]["1m"] = db_candles
                except Exception:
                    pass

    log(f"🔗 Starting signal generation for {len(SIGNAL_PAIRS)} pairs in parallel...", 2)

    # Start signal generation for all pairs FIRST (they'll wait for candles)
    for pair_display in SIGNAL_PAIRS:
        _start_signal_generation(pair_display, "1m")

    # Start background polling for non-active pairs to accumulate candles
    async def poll_background_pairs():
        """Periodically fetch candles for background pairs to feed signal generation."""
        while True:
            try:
                await asyncio.sleep(30)  # Poll every 30 seconds
                for pair in SIGNAL_PAIRS:
                    if pair == CURRENT_ASSET:
                        continue  # Skip the active asset (uses realtime)
                    try:
                        internal = DISPLAY_TO_INTERNAL.get(pair)
                        if internal:
                            # Fetch last 50 candles to backfill
                            candles = await CLIENT.get_candles(internal, time.time(), 50*60, 60)
                            if candles:
                                processed = process_candle_data(candles, 60)
                                if processed:
                                    if pair not in CANDLES:
                                        CANDLES[pair] = {}
                                    CANDLES[pair]["1m"] = processed[-200:]
                                    if CANDLE_STORE:
                                        for c in processed:
                                            CANDLE_STORE.save_candle(pair, "1m", c)
                                    log(f"📊 Backfilled {len(processed)} candles for {pair}", 2)
                    except Exception as e:
                        log(f"⚠️ Failed to poll {pair}: {e}", 2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log(f"⚠️ Background polling error: {e}", 2)
                await asyncio.sleep(10)

    start_background_task("poll_background_pairs", poll_background_pairs())

async def smart_background_loader(asset: str):
    for tf in ["5m", "15m", "30m", "1h", "10s", "30s", "2m", "3m", "10m", "4h", "5s", "15s"]:
        if CURRENT_ASSET != asset:
            break
        if tf == CURRENT_TIMEFRAME or tf in CANDLES.get(asset, {}):
            continue
        try:
            await load_timeframe_data(asset, tf, TIMEFRAMES[tf])
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(2)

# ======================
# Connection & Login
# ======================
async def connect_with_retry(attempts=5) -> Tuple[bool, str]:
    for i in range(1, attempts + 1):
        if not SAVED_EMAIL or not SAVED_PASSWORD:
            await asyncio.sleep(2)
            continue
        try:
            global CLIENT
            CLIENT = Quotex(email=SAVED_EMAIL, password=SAVED_PASSWORD, host="qxbroker.com", lang="en")
            check, reason = await CLIENT.connect()
            if check:
                return True, reason
            if Path("session.json").exists():
                Path("session.json").unlink()
            if i < attempts:
                await asyncio.sleep(2)
        except Exception as e:
            log(f"⚠️ Attempt {i} failed: {e}", 2)
            if i < attempts:
                await asyncio.sleep(2)
    return False, "Connection failed"

async def connect_to_quotex(email: str, password: str) -> Tuple[bool, str]:
    global CLIENT, ASSETS_LOADED, LOGIN_SUCCESS, SAVED_EMAIL, SAVED_PASSWORD
    log("🔐 Connecting...", 1)
    SAVED_EMAIL, SAVED_PASSWORD = email, password
    success, reason = await connect_with_retry()
    if not success:
        return False, reason

    try:
        await CLIENT.change_account("PRACTICE")
    except Exception as e:
        log(f"❌ Failed to switch to PRACTICE account: {e}", 1)
        return False, f"Account switch failed: {e}"

    # Explicitly fetch balance after account switch to initialize account_balance dict
    try:
        await asyncio.sleep(0.5)  # Brief wait for WebSocket update
        _ = await asyncio.wait_for(CLIENT.get_balance(), timeout=2.0)
        log("✅ Demo balance fetched and initialized", 1)
    except Exception as e:
        log(f"⚠️ Failed to fetch initial balance (non-fatal): {e}", 1)

    try:
        await CLIENT.get_all_assets()
    except Exception as e:
        log(f"⚠️ Failed to load assets (non-fatal): {e}", 1)
        # Continue anyway; assets may load later

    ASSETS_LOADED = LOGIN_SUCCESS = True
    update_subscription_time()
    start_background_task("heartbeat", realtime_heartbeat())
    start_background_task("market_ping", market_activity_ping())
    start_background_task("hard_ping", hard_ping_loop())
    start_background_task("forced_resub", forced_resubscription())

    # Wire Quotex client to OrderExecutor for trade execution
    global ORDER_EXECUTOR
    if ORDER_EXECUTOR and CLIENT:
        ORDER_EXECUTOR.client = CLIENT
        log("✅ OrderExecutor wired to Quotex client", 1)

    # Initialize background candle aggregator for selected pairs
    global BG_AGGREGATOR
    if BackgroundCandleAggregator and CANDLE_STORE and not BG_AGGREGATOR:
        BG_AGGREGATOR = BackgroundCandleAggregator(CANDLE_STORE)
        start_background_task("bg_candle_aggregator", BG_AGGREGATOR.start())
        log("✅ Background candle aggregator started", 1)

    log("✅ Login successful", 1)
    return True, ""

async def start_streaming(asset: str):
    global CURRENT_ASSET, BACKGROUND_LOADER_TASK
    if not CLIENT or not CLIENT.api:
        log(f"⚠️ Cannot start streaming: CLIENT not ready", 1)
        return

    try:
        old = CURRENT_ASSET
        if old and old != asset:
            task = ACTIVE_TASKS.pop(old, None)
            if task and not task.done():
                task.cancel()
            try:
                await CLIENT.stop_realtime_price(DISPLAY_TO_INTERNAL.get(old))
            except Exception:
                pass

        if BACKGROUND_LOADER_TASK and not BACKGROUND_LOADER_TASK.done():
            BACKGROUND_LOADER_TASK.cancel()

        with STATE_LOCK:
            CURRENT_ASSET = asset
            tf = CURRENT_TIMEFRAME
        prune_candle_cache(asset)
        period = TIMEFRAMES.get(tf, 60)
        await load_timeframe_data(asset, tf, period)
        send_to_ui(asset, tf, force=True, full=True)
        await asyncio.sleep(0.5)

        internal = DISPLAY_TO_INTERNAL.get(asset)
        if internal:
            for attempt in range(3):
                try:
                    await CLIENT.start_realtime_price(internal, period)
                    update_subscription_time()
                    log(f"✅ Streaming started: {asset}", 1)
                    break
                except Exception as e:
                    log(f"⚠️ start_realtime_price attempt {attempt+1}/3 failed: {e}", 1)
                    if attempt < 2:
                        await asyncio.sleep(1)

        log(f"🔄 Creating realtime_price_loop for {asset}", 1)
        task = asyncio.create_task(realtime_price_loop(asset))
        ACTIVE_TASKS[asset] = task
        BACKGROUND_LOADER_TASK = asyncio.create_task(smart_background_loader(asset))

        # Start signal generation for this asset
        log(f"📊 Starting signal generation for {asset}...", 1)
        _start_signal_generation(asset, CURRENT_TIMEFRAME)
        log(f"✅ Streaming fully initialized for {asset}", 1)
    except Exception as e:
        log(f"❌ start_streaming error: {e}", 1)
        raise

# ======================
# Input Validation
# ======================
def validate_email(email: str) -> Tuple[bool, str]:
    if not email or not isinstance(email, str):
        return False, "Email is required"
    email = email.strip()
    if len(email) < 5 or "@" not in email or "." not in email:
        return False, "Invalid email format"
    return True, ""

def validate_password(password: str) -> Tuple[bool, str]:
    if not password or not isinstance(password, str):
        return False, "Password is required"
    if len(password) < 3:
        return False, "Password must be at least 3 characters"
    return True, ""

# ======================
# Eel Endpoints
# ======================
@eel.expose
def login(email, password):
    def run():
        try:
            ok, err = validate_email(email)
            if not ok:
                eel.onLoginError(err)()
                return
            ok, err = validate_password(password)
            if not ok:
                eel.onLoginError(err)()
                return

            fut = asyncio.run_coroutine_threadsafe(connect_to_quotex(email, password), ASYNC_LOOP)
            ok, err = fut.result(timeout=60)
            if ok:
                eel.onLoginSuccess()()
            else:
                eel.onLoginError(err)()
        except Exception as e:
            eel.onLoginError(str(e))()
    threading.Thread(target=run, daemon=True).start()

@eel.expose
def on_chart_opened():
    if not LOGIN_SUCCESS:
        return
    def run():
        try:
            asyncio.run_coroutine_threadsafe(chart_opened_loader(CURRENT_ASSET), ASYNC_LOOP).result(timeout=30)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()

def _start_signal_generation(asset: str, timeframe: str = "1m") -> None:
    """Start async signal generation for an asset (Phase B).

    Called when an asset is selected. Creates a background thread
    that generates signals every 10 seconds.
    """
    global SIGNAL_MANAGER, CANDLE_STORE

    if not SIGNAL_MANAGER:
        log(f"⚠️ Cannot start signals for {asset}: SIGNAL_MANAGER not initialized", 1)
        return

    # Check if signal thread already running for this asset
    key = f"{asset}_{timeframe}"
    if hasattr(SIGNAL_MANAGER, 'threads') and key in SIGNAL_MANAGER.threads:
        if SIGNAL_MANAGER.threads[key].is_alive():
            log(f"Signal generation already running for {asset} {timeframe}", 2)
            return

    try:
        def get_candles_for_asset():
            candles = CANDLES.get(asset, {}).get(timeframe, [])
            if not candles:
                # Try loading from database as fallback
                if CANDLE_STORE:
                    try:
                        candles = CANDLE_STORE.get_candles(asset, timeframe, limit=200)
                    except Exception:
                        pass
            return candles

        SIGNAL_MANAGER.add_asset(asset, timeframe, get_candles_for_asset, interval_seconds=10.0)
        log(f"🔗 Signal generation started for {asset} {timeframe}", 1)
    except Exception as e:
        log(f"⚠️ Failed to start signals for {asset}: {e}", 1)

@eel.expose
def change_asset(asset):
    if not asset or not isinstance(asset, str):
        log(f"❌ Invalid asset: {asset}", 1)
        return
    if asset not in ASSET_DISPLAY_MAP.values():
        log(f"❌ Unknown asset: {asset}", 1)
        return
    def run():
        try:
            asyncio.run_coroutine_threadsafe(start_streaming(asset), ASYNC_LOOP).result(timeout=15)
            # Start signal generation for this asset (Phase B)
            _start_signal_generation(asset, "1m")
        except Exception as e:
            log(f"⚠️ Asset change failed: {e}", 1)
    threading.Thread(target=run, daemon=True).start()

@eel.expose
def change_timeframe(tf):
    global CURRENT_TIMEFRAME
    if not tf or tf not in TIMEFRAMES:
        log(f"❌ Invalid timeframe: {tf}", 1)
        return
    with STATE_LOCK:
        CURRENT_TIMEFRAME = tf
        asset = CURRENT_ASSET
        fresh = is_cache_fresh(asset, tf)
    if fresh:
        send_to_ui(asset, tf, force=True, full=True)
        return

    def run():
        try:
            asyncio.run_coroutine_threadsafe(
                load_timeframe_data(asset, tf, TIMEFRAMES[tf]), ASYNC_LOOP
            ).result(timeout=15)
            send_to_ui(asset, tf, force=True, full=True)
        except Exception as e:
            log(f"⚠️ Timeframe change failed: {e}", 1)
    threading.Thread(target=run, daemon=True).start()

@eel.expose
def get_asset_categories():
    return ASSET_CATEGORIES

@eel.expose
def get_timeframes():
    return list(TIMEFRAMES.keys())

@eel.expose
def apply_candle_colors(c):
    global CANDLE_COLORS
    CANDLE_COLORS = c

@eel.expose
def get_candle_colors():
    return CANDLE_COLORS

@eel.expose
def get_connection_status():
    if CLIENT and CLIENT.api:
        return {
            "connected": is_websocket_connected(),
            "assets_loaded": ASSETS_LOADED,
            "login_success": LOGIN_SUCCESS,
            "current_asset": CURRENT_ASSET,
            "current_timeframe": CURRENT_TIMEFRAME,
            "is_reconnecting": IS_RECONNECTING,
            "last_tick_age": round(time.time() - LAST_TICK_TIME, 1),
            "last_sub_age": round(time.time() - LAST_SUBSCRIPTION_TIME, 1)
        }
    return {"connected": False}

@eel.expose
def reconnect_realtime():
    """Force reconnection of realtime data stream - called by frontend when connection lost."""
    global CURRENT_ASSET, CURRENT_TIMEFRAME
    if not CLIENT:
        return {"status": "error", "message": "Client not initialized"}

    try:
        # Get current asset/timeframe
        with STATE_LOCK:
            asset = CURRENT_ASSET
            timeframe = CURRENT_TIMEFRAME

        internal = DISPLAY_TO_INTERNAL.get(asset, "AUDCAD_otc")
        period = TIMEFRAMES.get(timeframe, 60)

        log(f"🔄 Frontend triggered reconnect for {asset}/{timeframe}", 1)

        # Force full chart refresh on next data update
        global CHART_OPENED
        CHART_OPENED = False

        # Trigger resubscription
        def async_reconnect():
            async def _reconnect():
                try:
                    await CLIENT.start_realtime_price(internal, period)
                    update_subscription_time()
                    send_to_ui(asset, timeframe, force=True, full=True)
                    log(f"✅ Reconnection successful: {asset}/{timeframe}", 1)
                except Exception as e:
                    log(f"❌ Reconnection failed: {e}", 1)
                    await full_reconnect()

            asyncio.run_coroutine_threadsafe(_reconnect(), ASYNC_LOOP)

        async_reconnect()
        return {"status": "reconnecting", "asset": asset, "timeframe": timeframe}
    except Exception as e:
        log(f"❌ Reconnect failed: {e}", 1)
        return {"status": "error", "message": str(e)}

# ======================
# 🤖 Async ML Signal Methods
# ======================

async def _train_ml_signals_async():
    """Async ML model training (non-blocking via thread pool)."""
    # Try ML_SERVICE first (Phase A+), fall back to ENSEMBLE_GENERATOR (legacy)
    if not ML_SERVICE and not ENSEMBLE_GENERATOR:
        return {'error': 'ML signals not available'}

    try:
        with STATE_LOCK:
            asset = CURRENT_ASSET
            tf = CURRENT_TIMEFRAME
            candles = CANDLES.get(asset, {}).get(tf, [])

        if len(candles) < 100:
            return {'error': f'Need at least 100 candles, have {len(candles)}'}

        # Run synchronous training in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        if ML_SERVICE:
            result = await loop.run_in_executor(
                None, ML_SERVICE.train_all, asset, tf, candles
            )
        else:
            # Fallback to legacy ensemble generator
            result = await loop.run_in_executor(
                None, ENSEMBLE_GENERATOR.ml.train, candles
            )

        log(f"🤖 ML training done: {result.get('accuracy', 'N/A')} accuracy", 1)
        return result
    except Exception as e:
        log(f"❌ ML training error: {e}", 1)
        return {'error': str(e)}

async def _get_ml_signal_async():
    """Async ML signal generation (non-blocking via thread pool)."""
    # Try ML_SERVICE first (Phase A+), fall back to ENSEMBLE_GENERATOR (legacy)
    if not ML_SERVICE and not ENSEMBLE_GENERATOR:
        return None

    try:
        with STATE_LOCK:
            asset = CURRENT_ASSET
            tf = CURRENT_TIMEFRAME
            candles = CANDLES.get(asset, {}).get(tf, [])

        if not candles or len(candles) < 26:
            return None

        # Run signal generation in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        try:
            # Try new ML service first
            if ML_SERVICE:
                signal = await loop.run_in_executor(
                    None, ML_SERVICE.generate_signal, asset, tf, candles
                )
                if signal:
                    return signal.to_dict()
            else:
                # Fallback to legacy ensemble generator
                signal = await loop.run_in_executor(
                    None, ENSEMBLE_GENERATOR.generate_signal, candles
                )
                if signal:
                    return signal.to_dict()
        except Exception as inner_e:
            log(f"⚠️ ML signal inner error: {inner_e}", 2)

        return None
    except Exception as e:
        log(f"⚠️ ML signal error: {e}", 1)
        return None

# Global cache for ML results
ML_TRAINING_RESULT = None
LAST_ML_SIGNAL = None
ML_MODELS_FILE = "ml_signals_model.json"

def save_ml_models(training_result: Dict) -> bool:
    """Save trained ML models to persistent storage with detailed status."""
    try:
        # Extract models status from result
        models_trained = training_result.get('models_trained', [])
        model_errors = {k: v for k, v in training_result.items() if k.endswith('_error')}

        # Build detailed model status
        model_status = {}
        all_models = [
            'ensemble', 'kalman', 'expected_return', 'probability',  # Phase A
            'gradient_boosting_directional', 'gradient_boosting_return',  # Phase B
            'volatility', 'quantile_upper', 'quantile_lower',  # Phase B
            'regime_classifier', 'hmm_regime',  # Phase C
            'rl_agent',  # Phase D
            'lstm', 'transformer' , # Phase E
            'reversal_predictor'  # Phase 1.5
        ]

        for model in all_models:
            if model in models_trained:
                model_status[model] = "✅ trained"
            elif f"{model}_error" in training_result:
                model_status[model] = f"❌ {training_result[f'{model}_error'][:50]}"
            else:
                model_status[model] = "❌ not trained"

        model_data = {
            "timestamp": time.time(),
            "training_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "result": training_result,
            "model_status": model_status,
            "summary": {
                "total_models": len(all_models),
                "trained": len(models_trained),
                "failed": len(model_errors)
            }
        }

        with open(ML_MODELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(model_data, f, indent=2)

        print(f"✅ Saved ML models: {len(models_trained)}/{len(all_models)} trained")
        for model, status in model_status.items():
            print(f"  {status}: {model}")
        return True
    except Exception as e:
        print(f"❌ Failed to save ML models: {e}")
        return False

def load_ml_models() -> Dict:
    """Load trained ML models from persistent storage."""
    try:
        if os.path.exists(ML_MODELS_FILE):
            with open(ML_MODELS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"✅ Loaded ML models from {ML_MODELS_FILE} (trained: {data.get('training_date')})")
                return data.get('result', {})
    except Exception as e:
        print(f"⚠️ Failed to load ML models: {e}")
    return {}

@eel.expose
def train_ml_signals():
    """Async wrapper: Train ML model on recent candles (all assets)."""
    global ML_TRAINING_RESULT

    def run():
        global ML_TRAINING_RESULT
        try:
            fut = asyncio.run_coroutine_threadsafe(
                _train_ml_signals_async(), ASYNC_LOOP
            )
            ML_TRAINING_RESULT = fut.result(timeout=300)
            log(f"🤖 ML training cached: {ML_TRAINING_RESULT.get('accuracy', 'N/A')}", 1)

            # Save trained models to file
            if 'error' not in ML_TRAINING_RESULT:
                save_ml_models(ML_TRAINING_RESULT)
        except Exception as e:
            log(f"❌ Async training error: {e}", 1)
            ML_TRAINING_RESULT = {'error': str(e)}

    threading.Thread(target=run, daemon=True).start()

@eel.expose
def get_ml_training_result():
    """Get cached training result (non-blocking)."""
    global ML_TRAINING_RESULT
    if ML_TRAINING_RESULT:
        result = ML_TRAINING_RESULT
        ML_TRAINING_RESULT = None  # Clear after retrieval
        return result
    return None

@eel.expose
def get_ml_signal():
    """Async wrapper: Get current ML signal (non-blocking poll)."""
    global LAST_ML_SIGNAL

    def run():
        global LAST_ML_SIGNAL
        try:
            fut = asyncio.run_coroutine_threadsafe(
                _get_ml_signal_async(), ASYNC_LOOP
            )
            LAST_ML_SIGNAL = fut.result(timeout=5)
        except Exception as e:
            log(f"⚠️ Async signal fetch error: {e}", 2)
            LAST_ML_SIGNAL = None

    threading.Thread(target=run, daemon=True).start()

@eel.expose
def get_last_ml_signal():
    """Get cached ML signal (non-blocking)."""
    global LAST_ML_SIGNAL
    if LAST_ML_SIGNAL:
        signal = LAST_ML_SIGNAL
        LAST_ML_SIGNAL = None  # Clear after retrieval
        return signal
    return None

@eel.expose
def get_saved_ml_models():
    """Get previously saved ML models from file."""
    return load_ml_models()

@eel.expose
def clear_ml_models():
    """Clear saved ML models."""
    try:
        if os.path.exists(ML_MODELS_FILE):
            os.remove(ML_MODELS_FILE)
            log(f"✅ Cleared ML models file", 1)
            return {"success": True, "message": "ML models cleared"}
    except Exception as e:
        log(f"⚠️ Failed to clear ML models: {e}", 1)
        return {"success": False, "error": str(e)}

# ======================
# Phase B: Multi-Asset Signal Management
# ======================
@eel.expose
def get_signal_for_asset(asset: str, timeframe: str = "1m"):
    """Get latest cached signal for a specific asset (Phase B).

    Args:
        asset: Asset symbol (e.g. "AUD/CAD (OTC)")
        timeframe: Timeframe (default "1m")

    Returns:
        Signal dict or None if not available
    """
    global SIGNAL_MANAGER
    if not SIGNAL_MANAGER:
        log(f"⚠️ get_signal_for_asset({asset}): SIGNAL_MANAGER is None", 1)
        return None

    signal = SIGNAL_MANAGER.get_signal(asset, timeframe)
    key = f"{asset}_{timeframe}"

    if signal:
        log(f"✅ get_signal_for_asset({asset}): returning {signal.get('side')} @ {signal.get('confidence', 0):.2f}", 1)
        return signal

    # Debug: show what's actually cached
    if SIGNAL_MANAGER.signal_cache:
        cached_keys = list(SIGNAL_MANAGER.signal_cache.keys())
        log(f"⚠️ get_signal_for_asset({asset}): key '{key}' not found. Cached: {cached_keys}", 1)
    else:
        log(f"⚠️ get_signal_for_asset({asset}): cache empty", 1)

    return None

@eel.expose
def get_all_asset_signals():
    """Get all cached signals for all assets (Phase B).

    Returns:
        Dict mapping "asset_timeframe" → signal_dict
    """
    global SIGNAL_MANAGER
    if SIGNAL_MANAGER:
        return SIGNAL_MANAGER.get_all_signals()
    return {}

@eel.expose
def get_candles_from_store(asset: str, timeframe: str, limit: int = 200):
    """Get historical candles from persistent storage (Phase B).

    Args:
        asset: Asset symbol
        timeframe: Timeframe
        limit: Max candles to return (default 200)

    Returns:
        List of candle dicts with OHLCV data
    """
    global CANDLE_STORE
    if CANDLE_STORE:
        return CANDLE_STORE.get_candles(asset, timeframe, limit=limit)
    return []

@eel.expose
def get_account_balances_sync():
    """Get real and demo account balances synchronously.

    Returns:
        Dict with keys: 'real', 'demo', 'current_mode', 'timestamp'
        Example: {
            'real': 5000.50,
            'demo': 1000.00,
            'current_mode': 'PRACTICE',
            'timestamp': 1234567890.123
        }
    """
    def run():
        try:
            # First check if client/api is available without async call
            if not CLIENT or not CLIENT.api:
                log("⚠️ get_account_balances_sync: CLIENT not available for sync call", 2)
                return {'real': 0.0, 'demo': 0.0, 'current_mode': 'UNKNOWN', 'error': 'Client not ready'}

            fut = asyncio.run_coroutine_threadsafe(get_account_balances(), ASYNC_LOOP)
            result = fut.result(timeout=5)  # Shorter timeout for sync wrapper
            log(f"💰 Account balances: Real=${result['real']:.2f} Demo=${result['demo']:.2f} Mode={result['current_mode']}", 2)
            return result
        except asyncio.TimeoutError:
            log("⚠️ Timeout getting account balances (>5s)", 1)
            return {'real': 0.0, 'demo': 0.0, 'current_mode': 'UNKNOWN', 'error': 'Timeout'}
        except Exception as e:
            log(f"⚠️ Error in get_account_balances_sync: {type(e).__name__}: {e}", 1)
            return {'real': 0.0, 'demo': 0.0, 'current_mode': 'UNKNOWN', 'error': str(e)}

    # Run in thread to avoid blocking
    result = [None]
    thread = threading.Thread(target=lambda: result.__setitem__(0, run()), daemon=True)
    thread.start()
    thread.join(timeout=15)

    if result[0] is None:
        log("⚠️ Balance fetch thread timeout", 1)
        return {'real': 0.0, 'demo': 0.0, 'current_mode': 'UNKNOWN', 'error': 'Thread timeout'}

    if result[0]:
        log(f"✅ Returning balance: {result[0]}", 2)
    return result[0]

@eel.expose
def switch_account_mode(mode: str):
    """Switch between REAL and PRACTICE (DEMO) account modes.

    Args:
        mode: 'REAL' for real account, 'PRACTICE' for demo account

    Returns:
        Dict with success status and new balance info
        Example: {
            'success': True,
            'message': 'Switched to PRACTICE mode',
            'real': 5000.50,
            'demo': 1000.00,
            'current_mode': 'PRACTICE'
        }
    """
    def run():
        try:
            mode_upper = mode.upper()
            if mode_upper not in ['REAL', 'PRACTICE']:
                return {'success': False, 'error': f"Invalid mode '{mode}'. Use 'REAL' or 'PRACTICE'"}

            # Execute the account switch
            fut = asyncio.run_coroutine_threadsafe(CLIENT.change_account(mode_upper), ASYNC_LOOP)
            fut.result(timeout=10)

            # Get updated balances
            balances = asyncio.run_coroutine_threadsafe(get_account_balances(), ASYNC_LOOP).result(timeout=10)

            log(f"✅ Switched to {mode_upper} mode", 1)

            return {
                'success': True,
                'message': f"Switched to {mode_upper} mode",
                'real': balances['real'],
                'demo': balances['demo'],
                'current_mode': balances['current_mode']
            }
        except asyncio.TimeoutError:
            log(f"⚠️ Timeout switching to {mode} account", 1)
            return {'success': False, 'error': 'Timeout switching account'}
        except Exception as e:
            log(f"⚠️ Failed to switch account: {e}", 1)
            return {'success': False, 'error': str(e)}

    result = [None]
    thread = threading.Thread(target=lambda: result.__setitem__(0, run()), daemon=True)
    thread.start()
    thread.join(timeout=15)
    return result[0] or {'success': False, 'error': 'Thread timeout'}

@eel.expose
def get_candle_count(asset: str, timeframe: str):
    """Get total count of historical candles (Phase B).

    Args:
        asset: Asset symbol
        timeframe: Timeframe

    Returns:
        Count of candles in database
    """
    global CANDLE_STORE
    if CANDLE_STORE:
        return CANDLE_STORE.count_candles(asset, timeframe)
    return 0

@eel.expose
def get_available_assets():
    """Get list of all available assets (for pair selector).

    Returns:
        List of asset symbols available for trading
    """
    global ASSETS_LIST
    return ASSETS_LIST if ASSETS_LIST else []

@eel.expose
def start_signals_for_asset(asset: str, timeframe: str = "1m"):
    """Start signal generation for a specific asset (user enabled).

    Automatically loads initial candles from database or WebSocket stream.
    Persists the pair to the saved list ONLY if added by user (not during startup).

    Args:
        asset: Asset symbol
        timeframe: Timeframe (default "1m")

    Returns:
        Success status dict
    """
    global SIGNAL_MANAGER, CANDLE_STORE, ASYNC_LOOP, CURRENT_TIMEFRAME, SIGNAL_PAIRS
    if not SIGNAL_MANAGER:
        return {"success": False, "error": "SIGNAL_MANAGER not initialized"}

    try:
        # Get candles getter for this asset (same logic as _start_signal_generation)
        def get_candles_fn():
            # First try in-memory CANDLES (fed by real-time stream)
            candles = CANDLES.get(asset, {}).get(timeframe, [])
            if not candles:
                # Fall back to database
                if CANDLE_STORE:
                    try:
                        candles = CANDLE_STORE.get_candles(asset, timeframe, limit=200)
                    except Exception:
                        pass
            return candles

        # Start signal generation thread
        SIGNAL_MANAGER.add_asset(asset, timeframe, get_candles_fn)
        log(f"✅ Started signal generation for {asset} {timeframe}", 1)

        # Subscribe to real-time price stream to feed candles
        async def subscribe_to_realtime():
            try:
                if not CLIENT:
                    return
                internal = DISPLAY_TO_INTERNAL.get(asset)
                if not internal:
                    log(f"⚠️ No internal symbol for {asset}", 1)
                    return

                # Use current or default timeframe for subscription
                tf = CURRENT_TIMEFRAME if CURRENT_TIMEFRAME else "1m"
                period = TIMEFRAMES.get(tf, 60)

                log(f"📡 Subscribing {asset} to real-time stream ({tf})...", 1)
                await CLIENT.start_realtime_price(internal, period)
                log(f"✅ Subscribed {asset} to real-time price stream", 1)
            except Exception as e:
                log(f"⚠️ Failed to subscribe {asset} to real-time: {e}", 1)

        asyncio.run_coroutine_threadsafe(subscribe_to_realtime(), ASYNC_LOOP)

        # Add to signal pairs list and persist ONLY on user action (not during startup)
        # Check if this is a user-initiated call (via UI) vs auto-startup call
        if asset not in SIGNAL_PAIRS:
            SIGNAL_PAIRS.append(asset)
            # Only save if it's not during the initial chart_opened_loader startup
            # (startup signals are loaded from file, not auto-saved)
            if CHART_OPENED:  # True only after initial load
                save_selected_pairs(SIGNAL_PAIRS)
                log(f"💾 Saved {asset} to signal pairs", 2)

        return {"success": True, "asset": asset, "timeframe": timeframe}
    except Exception as e:
        log(f"❌ Failed to start signals for {asset}: {e}", 1)
        return {"success": False, "error": str(e)}

@eel.expose
def stop_signals_for_asset(asset: str, timeframe: str = "1m"):
    """Stop signal generation for a specific asset (user disabled).

    Removes the pair from the saved list ONLY on user action (not during startup).

    Args:
        asset: Asset symbol
        timeframe: Timeframe (default "1m")

    Returns:
        Success status dict
    """
    global SIGNAL_MANAGER, SIGNAL_PAIRS
    if not SIGNAL_MANAGER:
        return {"success": False, "error": "SIGNAL_MANAGER not initialized"}

    try:
        SIGNAL_MANAGER.remove_asset(asset, timeframe)
        log(f"⏹️ Stopped signal generation for {asset} {timeframe}", 1)

        # Remove from signal pairs list and persist ONLY on user action
        if asset in SIGNAL_PAIRS:
            SIGNAL_PAIRS.remove(asset)
            # Only save if it's not during startup
            if CHART_OPENED:  # True only after initial load
                save_selected_pairs(SIGNAL_PAIRS)
                log(f"💾 Removed {asset} from signal pairs", 2)

        return {"success": True, "asset": asset, "timeframe": timeframe}
    except Exception as e:
        log(f"❌ Failed to stop signals for {asset}: {e}", 1)
        return {"success": False, "error": str(e)}

@eel.expose
def get_signal_pairs():
    """Get list of pairs currently configured for signal generation.

    Returns:
        List of asset symbols
    """
    global SIGNAL_PAIRS
    return SIGNAL_PAIRS

@eel.expose
def set_signal_pairs(pairs: List[str]):
    """Set which pairs to generate signals for and persist to storage.

    Args:
        pairs: List of asset symbols (e.g. ["AUD/CAD (OTC)", "EUR/USD (OTC)"])

    Returns:
        Success status dict
    """
    global SIGNAL_PAIRS
    if not pairs or not isinstance(pairs, list):
        return {"success": False, "error": "Invalid pairs list"}

    # Validate all pairs exist
    valid_pairs = []
    for pair in pairs:
        if pair in ASSET_DISPLAY_MAP.values():
            valid_pairs.append(pair)
        else:
            log(f"⚠️ Invalid asset pair: {pair}", 1)

    if not valid_pairs:
        return {"success": False, "error": "No valid pairs provided"}

    SIGNAL_PAIRS = valid_pairs
    if save_selected_pairs(valid_pairs):
        log(f"✅ Signal pairs updated: {valid_pairs}", 1)
        return {"success": True, "pairs": valid_pairs}
    else:
        return {"success": False, "error": "Failed to save pairs"}

@eel.expose
def get_signal_status():
    """Get diagnostic status of signal generation (Phase B).

    Returns:
        Dict with signal manager status and active threads
    """
    global SIGNAL_MANAGER, ML_SERVICE, CANDLE_STORE, SIGNAL_PAIRS
    status = {
        "ml_service_ready": ML_SERVICE is not None,
        "signal_manager_ready": SIGNAL_MANAGER is not None,
        "candle_store_ready": CANDLE_STORE is not None,
        "current_asset": CURRENT_ASSET,
        "current_timeframe": CURRENT_TIMEFRAME,
        "signal_pairs": SIGNAL_PAIRS,
    }

    if SIGNAL_MANAGER:
        status["active_signals"] = SIGNAL_MANAGER.get_all_signals()
        status["cached_count"] = len(SIGNAL_MANAGER.signal_cache)
        status["thread_count"] = len(SIGNAL_MANAGER.threads)

    # Add CANDLES info
    if CURRENT_ASSET in CANDLES:
        for tf in CANDLES[CURRENT_ASSET]:
            status[f"candles_{tf}"] = len(CANDLES[CURRENT_ASSET].get(tf, []))

    return status

@eel.expose
def report_trade_outcome(profit: float, components: dict, side: str, entry: float, exit: float):
	"""Phase G3: Report a completed trade for online learning.

	Called by the UI or trading bot when a trade closes. Updates the online learning
	optimizer to track which models contributed to winning/losing trades.

	Args:
		profit: Trade P&L (positive = win, negative/zero = loss)
		components: Model predictions from the signal (dict)
		side: Trade side ("BUY" or "SELL")
		entry: Entry price
		exit: Exit price

	Returns:
		Dict with status and G3 stats
	"""
	global ML_SERVICE
	if not ML_SERVICE:
		return {"success": False, "error": "ML service not initialized"}

	try:
		trade_result = {
			"profit": profit,
			"components": components,
			"side": side,
			"entry": entry,
			"exit": exit,
			"timestamp": time.time(),
		}

		# Update G3 online learning
		ML_SERVICE.process_trade_outcome(trade_result)

		# Return updated stats
		stats = ML_SERVICE.get_g3_stats()
		return {
			"success": True,
			"profit": profit,
			"trades_evaluated": stats.get("trades_evaluated", 0),
			"win_rates": stats.get("win_rates", {}),
			"current_weights": stats.get("current_weights", {}),
		}
	except Exception as e:
		log(f"⚠️ Error reporting trade outcome: {e}", 2)
		return {"success": False, "error": str(e)}

# ======================
# Phase H: Automated Trading Endpoints
# ======================
@eel.expose
def get_automation_status():
	"""Get current automation status and selected pairs.

	Returns:
		Dict with automation state, selected pairs, and real-time metrics
	"""
	global AUTO_TRADING_MANAGER, CONSTRAINT_TRACKER, HEALTH_MONITOR

	if not AUTO_TRADING_MANAGER:
		return {"error": "Auto trading manager not initialized"}

	try:
		status = AUTO_TRADING_MANAGER.get_automation_status()

		# Add real-time balance
		balances = asyncio.run_coroutine_threadsafe(
			get_account_balances(), ASYNC_LOOP
		).result(timeout=3)

		status['balances'] = balances
		status['trading_mode'] = "DEMO" if settings.prefer_demo_mode else "LIVE"

		return status
	except Exception as e:
		log(f"⚠️ Error getting automation status: {e}", 2)
		return {"error": str(e)}

@eel.expose
def enable_automation():
	"""Enable automated trading for selected pairs.

	Returns:
		Dict with success status
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return {"success": False, "error": "Auto trading manager not initialized"}

	try:
		success = AUTO_TRADING_MANAGER.enable_automation()
		if success:
			log("🚀 AUTOMATION ENABLED for selected pairs", 1)
			return {"success": True, "message": "Automation enabled"}
		else:
			return {"success": False, "error": "Failed to enable automation"}
	except Exception as e:
		log(f"❌ Error enabling automation: {e}", 1)
		return {"success": False, "error": str(e)}

@eel.expose
def disable_automation():
	"""Disable automated trading.

	Returns:
		Dict with success status
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return {"success": False, "error": "Auto trading manager not initialized"}

	try:
		AUTO_TRADING_MANAGER.disable_automation()
		log("⏹️  AUTOMATION DISABLED", 1)
		return {"success": True, "message": "Automation disabled"}
	except Exception as e:
		log(f"❌ Error disabling automation: {e}", 1)
		return {"success": False, "error": str(e)}

@eel.expose
def get_selected_pairs():
	"""Get list of selected pairs for automated trading.

	Returns:
		List of pair display names
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return []

	return AUTO_TRADING_MANAGER.selected_pairs

@eel.expose
def get_pair_statuses():
	"""Get real-time status of each selected pair.

	Returns:
		Dict mapping pair names to status info
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return {}

	return AUTO_TRADING_MANAGER.get_pair_statuses()

@eel.expose
def get_real_time_balance():
	"""Get real-time account balance (updated every 60s from hard ping).

	Returns:
		Dict with current balances
	"""
	global CONSTRAINT_TRACKER

	try:
		# Get from constraint tracker (already updated by hard ping every 60s)
		if CONSTRAINT_TRACKER and CONSTRAINT_TRACKER.current_constraints:
			c = CONSTRAINT_TRACKER.current_constraints
			return {
				'real_balance': c.live_balance,
				'demo_balance': c.demo_balance,
				'day_limit': c.day_limit,
				'day_balance': c.day_balance,
				'minimum_amount': c.minimum_amount,
				'account_mode': c.account_mode,
				'timestamp': c.timestamp
			}
		else:
			# Fallback: get from async call
			balances = asyncio.run_coroutine_threadsafe(
				get_account_balances(), ASYNC_LOOP
			).result(timeout=2)
			return balances
	except Exception as e:
		log(f"⚠️ Error getting real-time balance: {e}", 2)
		return {}

# ======================
# Phase H: Individual Pair Activation/Deactivation
# ======================
@eel.expose
def activate_pair(pair_name: str):
	"""Activate a specific pair for trading.

	Args:
		pair_name: Display name (e.g., "CHF/JPY")

	Returns:
		Dict with success status
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return {"success": False, "error": "Auto trading manager not initialized"}

	try:
		success = AUTO_TRADING_MANAGER.activate_pair(pair_name)
		if success:
			log(f"✅ PAIR ACTIVATED: {pair_name}", 1)
			return {"success": True, "message": f"Activated {pair_name}"}
		else:
			return {"success": False, "error": f"Pair not found: {pair_name}"}
	except Exception as e:
		log(f"❌ Error activating pair: {e}", 1)
		return {"success": False, "error": str(e)}

@eel.expose
def deactivate_pair(pair_name: str):
	"""Deactivate a specific pair (won't execute trades).

	Args:
		pair_name: Display name (e.g., "CHF/JPY")

	Returns:
		Dict with success status
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return {"success": False, "error": "Auto trading manager not initialized"}

	try:
		success = AUTO_TRADING_MANAGER.deactivate_pair(pair_name)
		if success:
			log(f"⏸️  PAIR DEACTIVATED: {pair_name}", 1)
			return {"success": True, "message": f"Deactivated {pair_name}"}
		else:
			return {"success": False, "error": f"Pair not found: {pair_name}"}
	except Exception as e:
		log(f"❌ Error deactivating pair: {e}", 1)
		return {"success": False, "error": str(e)}

@eel.expose
def activate_all_pairs():
	"""Activate all selected pairs.

	Returns:
		Dict with count of activated pairs
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return {"success": False, "error": "Auto trading manager not initialized"}

	try:
		count = AUTO_TRADING_MANAGER.activate_all_pairs()
		log(f"✅ Activated all {count} pairs", 1)
		return {"success": True, "activated_count": count}
	except Exception as e:
		log(f"❌ Error activating all pairs: {e}", 1)
		return {"success": False, "error": str(e)}

@eel.expose
def deactivate_all_pairs():
	"""Deactivate all selected pairs.

	Returns:
		Dict with count of deactivated pairs
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return {"success": False, "error": "Auto trading manager not initialized"}

	try:
		count = AUTO_TRADING_MANAGER.deactivate_all_pairs()
		log(f"⏸️  Deactivated all {count} pairs", 1)
		return {"success": True, "deactivated_count": count}
	except Exception as e:
		log(f"❌ Error deactivating all pairs: {e}", 1)
		return {"success": False, "error": str(e)}

@eel.expose
def get_active_pairs():
	"""Get list of currently active pairs.

	Returns:
		List of active pair names
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return []

	return AUTO_TRADING_MANAGER.get_active_pairs()

@eel.expose
def get_inactive_pairs():
	"""Get list of currently inactive (deactivated) pairs.

	Returns:
		List of inactive pair names
	"""
	global AUTO_TRADING_MANAGER

	if not AUTO_TRADING_MANAGER:
		return []

	return AUTO_TRADING_MANAGER.get_inactive_pairs()

# ======================
# Phase H: Order Execution & Position Tracking
# ======================

@eel.expose
def get_open_positions():
	"""Get all currently open trading positions.

	Returns:
		Dict with position details by asset
	"""
	global POSITION_TRACKER

	if not POSITION_TRACKER:
		return {}

	return POSITION_TRACKER.get_position_summary_by_asset()

@eel.expose
def get_recent_trades(limit=20):
	"""Get recent closed trades.

	Args:
		limit: Number of recent trades to return

	Returns:
		List of recent trade records with P&L
	"""
	global POSITION_TRACKER

	if not POSITION_TRACKER:
		return []

	return POSITION_TRACKER.get_recent_trades(limit)

@eel.expose
def get_position_statistics():
	"""Get position and trade statistics.

	Returns:
		Dict with:
		- open_positions: count of open trades
		- total_trades: total executed trades
		- winning_trades: count of winners
		- losing_trades: count of losers
		- win_rate_percent: win rate %
		- total_profit_loss_usd: total P&L
		- avg_profit_loss_per_trade: average P&L per trade
	"""
	global POSITION_TRACKER

	if not POSITION_TRACKER:
		return {
			'open_positions': 0,
			'total_trades': 0,
			'winning_trades': 0,
			'losing_trades': 0,
			'win_rate_percent': 0,
			'total_profit_loss_usd': 0,
			'avg_profit_loss_per_trade': 0
		}

	return POSITION_TRACKER.get_statistics()

@eel.expose
def get_order_execution_stats():
	"""Get order execution statistics.

	Returns:
		Dict with:
		- orders_placed: total orders sent
		- orders_executed: successful orders
		- orders_failed: failed orders
		- execution_rate_percent: success rate
		- total_traded_usd: total USD traded
		- avg_order_size: average order size
	"""
	global ORDER_EXECUTOR

	if not ORDER_EXECUTOR:
		return {
			'orders_placed': 0,
			'orders_executed': 0,
			'orders_failed': 0,
			'execution_rate_percent': 0,
			'total_traded_usd': 0,
			'avg_order_size': 0
		}

	return ORDER_EXECUTOR.get_execution_stats()

@eel.expose
def get_recent_orders(limit=10):
	"""Get recent order execution history.

	Args:
		limit: Number of recent orders to return

	Returns:
		List of recent order records
	"""
	global ORDER_EXECUTOR

	if not ORDER_EXECUTOR:
		return []

	return ORDER_EXECUTOR.get_recent_orders(limit)

@eel.expose
def close_position(position_id, asset, exit_price=0.0, exit_reason=""):
	"""Close an open trading position.

	Args:
		position_id: Position identifier
		asset: Asset symbol
		exit_price: Exit price (optional)
		exit_reason: Reason for closing (e.g., "manual_close", "stop_loss")

	Returns:
		Dict with {success: bool, message: str, pnl_pct: float, pnl_usd: float}
	"""
	global POSITION_TRACKER

	if not POSITION_TRACKER:
		return {
			'success': False,
			'message': 'Position tracker not available'
		}

	try:
		position = POSITION_TRACKER.close_position(
			position_id=position_id,
			asset=asset,
			exit_price=exit_price,
			exit_reason=exit_reason
		)

		if position:
			return {
				'success': True,
				'message': f'Position closed: {exit_reason}',
				'pnl_pct': position.profit_loss_pct,
				'pnl_usd': position.profit_loss_usd,
				'status': position.status
			}
		else:
			return {
				'success': False,
				'message': f'Position {position_id} not found'
			}

	except Exception as e:
		return {
			'success': False,
			'message': f'Error closing position: {str(e)}'
		}

@eel.expose
def export_position_history(filepath="position_history.json"):
	"""Export complete position history to JSON.

	Args:
		filepath: Output file path

	Returns:
		Dict with {success: bool, message: str, filepath: str}
	"""
	global POSITION_TRACKER

	if not POSITION_TRACKER:
		return {
			'success': False,
			'message': 'Position tracker not available'
		}

	try:
		POSITION_TRACKER.export_positions_log(filepath)
		return {
			'success': True,
			'message': 'Position history exported',
			'filepath': filepath
		}
	except Exception as e:
		return {
			'success': False,
			'message': f'Export failed: {str(e)}'
		}

@eel.expose
def export_order_history(filepath="order_history.json"):
	"""Export complete order execution history to JSON.

	Args:
		filepath: Output file path

	Returns:
		Dict with {success: bool, message: str, filepath: str}
	"""
	global ORDER_EXECUTOR

	if not ORDER_EXECUTOR:
		return {
			'success': False,
			'message': 'Order executor not available'
		}

	try:
		ORDER_EXECUTOR.export_order_log(filepath)
		return {
			'success': True,
			'message': 'Order history exported',
			'filepath': filepath
		}
	except Exception as e:
		return {
			'success': False,
			'message': f'Export failed: {str(e)}'
		}

# ======================
# Main Entry - FIXED with Type Safety
# ======================
if __name__ == "__main__":
    print("🚀 Quotex Pro Trader — EEL COMPATIBLE v3.3 (COUNTDOWN FIX)")
    print(
        "✅ EMA Offset | Rate-limited UI | Stable candle_start | Fast sleep | Anti-Sleep"
    )

    os.makedirs("frontend", exist_ok=True)
    if not os.path.exists("frontend/login/login.html"):
        print("❌ Missing frontend/login/login.html")
        sys.exit(1)

    # ✅ Auto-Login from .env with type safety
    if QUOTEX_EMAIL and QUOTEX_PASSWORD:
        # Type-safe: ensure we have strings
        email = str(QUOTEX_EMAIL)
        password = str(QUOTEX_PASSWORD)

        print(f"🔐 Auto-login with: {email}")

        def auto_login():
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    connect_to_quotex(email, password), ASYNC_LOOP
                )
                ok, err = fut.result(timeout=60)
                if ok:
                    print("✅ Auto-login successful!")
                    eel.onLoginSuccess()()
                else:
                    print(f"❌ Auto-login failed: {err}")
                    eel.start(
                        "login/login.html", size=(1280, 720), port=0, mode="chrome"
                    )
            except Exception as e:
                print(f"❌ Auto-login error: {e}")
                eel.start("login/login.html", size=(1280, 720), port=0, mode="chrome")

        threading.Thread(target=auto_login, daemon=True).start()

        try:
            eel.init("frontend")
            eel.start("login/login.html", size=(1280, 720), port=0, mode="chrome")
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Startup failed: {e}")
            sys.exit(1)
    else:
        print("⚠️ No .env credentials found. Please login manually.")
        try:
            eel.init("frontend")
            eel.start("login/login.html", size=(1280, 720), port=0, mode="chrome")
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Startup failed: {e}")
            sys.exit(1)

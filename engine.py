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
    print(f"✅ .env loaded: {QUOTEX_EMAIL}")
else:
    print("⚠️ No .env credentials found")

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
    from ml.data.candle_store import CandleStore
except ImportError as e:
    print(f"⚠️ Candle store not available: {e}")
    CandleStore = None

try:
    from ml.serving.async_signal_manager import AsyncSignalManager
except ImportError as e:
    print(f"⚠️ Async signal manager not available: {e}")
    AsyncSignalManager = None

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
    while True:
        try:
            payload = UI_QUEUE.get()
            if payload is None:
                break
            eel.updateChart(payload)()
            UI_QUEUE.task_done()
            QUEUE_OVERFLOW_COUNT = 0  # Reset on successful send
        except Exception as e:
            log(f"⚠️ [UI Error] {e}", 1)
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
ML_SERVICE = MLSignalService() if MLSignalService else None
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

# ✅ تحسين #5: أوقات مخفضة
TICK_IDLE_THRESHOLD   = 30   # ثانية — كان 90
PING_INTERVAL         = 60   # ثانية — كان 180
RESUB_INTERVAL        = 60   # ✅ جديد: إعادة اشتراك دورية
HARD_PING_INTERVAL    = 60   # ✅ جديد: ping بـ get_balance
EMPTY_TICK_RESUB_THRESHOLD = 20  # ✅ Increased from 15, more conservative
MAX_CONSECUTIVE_EMPTY = 50   # ✅ Max before giving up on asset switch

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
# Phase B: Database & Async Signals
# ======================
CANDLE_STORE = CandleStore("quotex_candles.db") if CandleStore else None
# SIGNAL_MANAGER already initialized at module load (line ~140)

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
        if CHART_OPENED:
            await start_streaming(CURRENT_ASSET)

        log("✅ Re-login successful", 1)
        return True
    except Exception as e:
        log(f"❌ Reconnection error: {e}", 1)
        return False
    finally:
        IS_RECONNECTING = False

# ======================
# ✅ تحسين #1: Hard Ping بـ get_balance
# ======================
async def hard_ping_loop():
    while True:
        await asyncio.sleep(HARD_PING_INTERVAL)
        try:
            if CLIENT and CLIENT.api:
                balance = await asyncio.wait_for(CLIENT.get_balance(), timeout=8)
                log(f"💓 Hard ping OK — balance: {balance}", 2)
                update_tick_time()
        except asyncio.CancelledError:
            break
        except asyncio.TimeoutError:
            log("⚠️ Hard ping timeout — triggering reconnect", 1)
            asyncio.create_task(full_reconnect())
        except (ConnectionError, OSError) as e:
            log(f"⚠️ Hard ping connection error: {e}", 1)
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
    while True:
        await asyncio.sleep(45)
        try:
            if CLIENT:
                if not is_websocket_connected():
                    log("⚠️ Heartbeat: Connection lost, reconnecting...", 1)
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

def update_candle(asset: str, frame: str, price: float, ts_sec: int):
    global CANDLES, CURRENT_CANDLE, CANDLE_STORE
    duration = TIMEFRAMES.get(frame, 60)
    start = (ts_sec // duration) * duration
    curr = CURRENT_CANDLE.get(asset, {}).get(frame, {})
    if not curr or curr.get("time") != start:
        if curr:
            CANDLES.setdefault(asset, {}).setdefault(frame, []).append(curr.copy())
            # Save completed candle to database (Phase B)
            if CANDLE_STORE:
                CANDLE_STORE.save_candle(asset, frame, curr.copy())
            if len(CANDLES[asset][frame]) > 200:
                CANDLES[asset][frame] = CANDLES[asset][frame][-200:]
        CURRENT_CANDLE.setdefault(asset, {})[frame] = {
            "time": start, "open": price, "high": price, "low": price, "close": price
        }
    else:
        if price > curr["high"]: curr["high"] = price
        if price < curr["low"]:  curr["low"] = price
        curr["close"] = price

def prune_candle_cache(keep_asset: str):
    """Drop cached candles for all assets except `keep_asset`.

    Bounds memory to a single asset (200 candles x 14 timeframes) instead
    of growing with every asset ever viewed.
    """
    for asset in list(CANDLES.keys()):
        if asset != keep_asset:
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
    if not (full or force) and (now - LAST_UI_SEND) < 0.5:
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
        return True
    except Full:
        QUEUE_OVERFLOW_COUNT += 1
        if now - QUEUE_LAST_OVERFLOW_LOG > 5:  # Log at most once per 5 seconds
            log(f"🚨 UI Queue overflow (dropped {QUEUE_OVERFLOW_COUNT} updates)", 1)
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

            if errs >= 10 and not is_websocket_connected():
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
                if consecutive_empty >= 8 and (time.time() - last_resub_time) > 10:
                    log(f"⚠️ {consecutive_empty} timeouts — trying resub (with backoff)", 1)
                    try:
                        period = TIMEFRAMES.get(CURRENT_TIMEFRAME, 60)
                        await CLIENT.start_realtime_price(internal, period)
                        update_subscription_time()
                        last_resub_time = time.time()
                        consecutive_empty = 0
                    except Exception:
                        asyncio.create_task(full_reconnect())
                        break
                await asyncio.sleep(0.5)
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
                    if active:
                        update_candle(asset_display, frame, price, ts)
                        send_to_ui(asset_display, frame)
                    errs = 0
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
            else:
                consecutive_empty += 1

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
    internal = DISPLAY_TO_INTERNAL.get(asset, "AUDCAD_otc")
    try:
        hist = await CLIENT.get_candles(internal, time.time(), 199 * period, period)
        loaded = process_candle_data(hist, period)
        CANDLES.setdefault(asset, {})[tf] = loaded[-199:]
        return loaded[-199:]
    except Exception:
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

    # Phase B: Pre-load candles from database for all 4 pairs, then start signal generation
    global CANDLES, CANDLE_STORE
    for pair_display in ["AUD/CAD (OTC)", "EUR/USD (OTC)", "USD/PKR (OTC)", "GBP/USD (OTC)"]:
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

    log("🔗 Starting signal generation for all 4 pairs in parallel...", 2)
    for pair_display in ["AUD/CAD (OTC)", "EUR/USD (OTC)", "USD/PKR (OTC)", "GBP/USD (OTC)"]:
        _start_signal_generation(pair_display, "1m")

    # Phase B: Start background streaming for other 3 pairs so they accumulate candles
    async def load_other_pairs():
        other_pairs = ["EUR/USD (OTC)", "USD/PKR (OTC)", "GBP/USD (OTC)"]
        for pair in other_pairs:
            try:
                await load_timeframe_data(pair, "1m", 60)
            except Exception:
                pass

    asyncio.create_task(load_other_pairs())

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
    log("✅ Login successful", 1)
    return True, ""

async def start_streaming(asset: str):
    global CURRENT_ASSET, BACKGROUND_LOADER_TASK
    if IS_RECONNECTING or not CLIENT or not CLIENT.api:
        return

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
        for _ in range(3):
            try:
                await CLIENT.start_realtime_price(internal, period)
                update_subscription_time()
                break
            except Exception:
                await asyncio.sleep(1)
    print(f"[start_streaming] About to create realtime_price_loop for {asset}", file=sys.stderr)
    task = asyncio.create_task(realtime_price_loop(asset))
    ACTIVE_TASKS[asset] = task
    print(f"[start_streaming] Realtime task created", file=sys.stderr)
    BACKGROUND_LOADER_TASK = asyncio.create_task(smart_background_loader(asset))
    print(f"[start_streaming] Background loader created", file=sys.stderr)

    # Phase B: Start signal generation for this asset
    print(f"[start_streaming] About to start signal generation for {asset}...", file=sys.stderr)
    log(f"Starting signal generation for {asset}...", 2)
    _start_signal_generation(asset, CURRENT_TIMEFRAME)
    print(f"[start_streaming] Signal generation call completed", file=sys.stderr)

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

# ======================
# 🤖 Async ML Signal Methods
# ======================

async def _train_ml_signals_async():
    """Async ML model training (non-blocking)."""
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

        # Try new ML service first
        if ML_SERVICE:
            result = ML_SERVICE.train_all(asset, tf, candles, lookahead=1)
        else:
            # Fallback to legacy ensemble generator
            result = ENSEMBLE_GENERATOR.ml.train(candles, lookback=100)

        log(f"🤖 ML training done: {result.get('accuracy', 'N/A')} accuracy", 1)
        return result
    except Exception as e:
        log(f"❌ ML training error: {e}", 1)
        return {'error': str(e)}

async def _get_ml_signal_async():
    """Async ML signal generation (non-blocking)."""
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

        # Try new ML service first
        if ML_SERVICE:
            signal = ML_SERVICE.generate_signal(asset, tf, candles)
            if signal:
                return signal.to_dict()
        else:
            # Fallback to legacy ensemble generator
            signal = ENSEMBLE_GENERATOR.generate_signal(candles)
            if signal:
                return signal.to_dict()

        return None
    except Exception as e:
        log(f"⚠️ ML signal error: {e}", 1)
        return None

# Global cache for ML results
ML_TRAINING_RESULT = None
LAST_ML_SIGNAL = None

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
            ML_TRAINING_RESULT = fut.result(timeout=120)
            log(f"🤖 ML training cached: {ML_TRAINING_RESULT.get('accuracy', 'N/A')}", 1)
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
def get_signal_status():
    """Get diagnostic status of signal generation (Phase B).

    Returns:
        Dict with signal manager status and active threads
    """
    global SIGNAL_MANAGER, ML_SERVICE, CANDLE_STORE
    status = {
        "ml_service_ready": ML_SERVICE is not None,
        "signal_manager_ready": SIGNAL_MANAGER is not None,
        "candle_store_ready": CANDLE_STORE is not None,
        "current_asset": CURRENT_ASSET,
        "current_timeframe": CURRENT_TIMEFRAME,
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

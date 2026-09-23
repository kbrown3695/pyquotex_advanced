"""Configuration stub for ML module (replaces dollar's src.config.settings)."""


class _Settings:
    """Settings configuration for ML features."""

    # ==================== ML Signals ====================
    enable_ml_signals: bool = True
    ml_history_days: int = 30
    ml_model_dir: str = "models"

    # ==================== Phase H: Account Constraints ====================
    # Daily trading limits
    enable_constraint_tracking: bool = True
    constraint_violation_halt: bool = True  # Stop trading on violation

    # Minimum trade validation (from profile)
    enable_minimum_amount_validation: bool = True
    fallback_minimum_amount: float = 1.0  # USD fallback if profile not available

    # Day limit enforcement
    enable_day_limit_enforcement: bool = True
    day_limit_warning_threshold: float = 0.2  # Warn when 20% balance remaining

    # ==================== Phase H: WebSocket Health ====================
    enable_health_monitoring: bool = True
    health_check_interval_sec: float = 5.0  # Check health every 5 seconds

    # Latency thresholds (milliseconds)
    latency_warning_ms: float = 500.0
    latency_critical_ms: float = 1000.0

    # Staleness detection (multiple of candle period)
    stale_threshold_multiplier: float = 1.5  # 1.5x expected interval
    consecutive_stale_max: int = 10  # Alert after 10 consecutive stale events

    # ==================== Phase H: Automation ====================
    enable_automated_trading: bool = True  # ✅ ENABLED: Auto-trading active
    automation_start_hour: int = 0  # 24-hour format (0-23)
    automation_end_hour: int = 23

    # Signal confidence threshold (configurable minimum)
    min_signal_confidence: float = 0.05  # Require 30% confidence minimum

    # ==================== Data Accumulation Phase (Phase I) ====================
    # Automatic warm-up period to collect training data before trading
    enable_data_accumulation_phase: bool = True
    data_accumulation_min_candles: int = 500  # Collect 500+ candles per asset before trading
    data_accumulation_timeout_minutes: int = 120  # Max 2 hours to collect data

    # During accumulation, show progress but don't execute trades
    data_accumulation_show_signals: bool = True  # Display signals even during warmup
    data_accumulation_allow_trades: bool = False  # But don't execute them yet

    # Position sizing
    risk_per_trade_percent: float = 2.0  # Risk 2% of balance per trade
    max_position_size_percent: float = 10.0  # Max 10% of balance per trade

    # Trade execution
    max_trades_per_day: int = 100
    min_time_between_trades_sec: float = 5.0
    position_duration_seconds: int = 300  # Binary option duration (5 minutes)

    # ==================== Phase H: Timezone & Localization ====================
    # Server timezone offset (from Quotex profile)
    server_timezone_offset: int = 0  # Will be updated from profile.offset
    use_server_timezone: bool = True  # Use Quotex server time vs local time

    # ==================== Phase H: Account Management ====================
    # Auto-switch accounts based on balance
    enable_account_auto_switch: bool = True
    live_account_min_balance: float = 100.0  # Switch to demo if live balance < $100

    # Demo/Live mode preferences
    prefer_demo_mode: bool = True  # Start in demo mode
    demo_balance_target: float = 10000.0  # Target demo balance for testing

    # ==================== Phase H: Compliance & Logging ====================
    # Compliance tracking
    enable_compliance_logging: bool = True
    compliance_log_file: str = "logs/compliance.log"

    # Constraint history
    export_constraint_history: bool = True
    constraint_history_file: str = "data/constraint_history.json"

    # Health monitoring exports
    export_health_logs: bool = True
    health_log_file: str = "logs/websocket_health.json"


settings = _Settings()

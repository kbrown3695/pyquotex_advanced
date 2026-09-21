# Trading Bot Training Guide: Using Quotex Data

## Overview
How to leverage the Quotex data structures for developing, training, and deploying an automated trading bot.

---

## 1. FEATURE ENGINEERING FROM RAW DATA

### 1.1 Price Features (from `wss_message` candle data)

**Raw Data Source:**
```python
candle = {
  "asset": "EURUSD_otc",
  "period": 60,  # 1-minute candle
  "history": [[timestamp, open, high, low, close, volume], ...]
}
```

**Derived Features for ML Model:**

#### Technical Indicators
```python
features = {
    # Trend Indicators
    "SMA_10": simple_moving_average(closes, 10),
    "SMA_20": simple_moving_average(closes, 20),
    "EMA_12": exponential_moving_average(closes, 12),
    
    # Momentum Indicators
    "RSI_14": relative_strength_index(closes, 14),
    "MACD": moving_average_convergence_divergence(closes),
    "ROC": rate_of_change(closes, 12),
    
    # Volatility Indicators
    "Bollinger_Bands": bollinger_bands(closes, 20),
    "ATR_14": average_true_range(closes, 14),
    "Std_Dev": standard_deviation(closes, 20),
    
    # Volatility Measures
    "high_low_ratio": (high - low) / close,
    "close_open_ratio": (close - open) / open,
    
    # Volume Indicators
    "Volume_SMA": simple_moving_average(volumes, 10),
    "Volume_Ratio": volume / volume_SMA,
    
    # Price Action
    "Higher_High": high > previous_high,
    "Lower_Low": low < previous_low,
    "Close_Above_Open": close > open,
    "Gap": open - previous_close,
    
    # Multi-timeframe (aggregate different periods)
    "Trend_1m": trend_from_1min_candles,
    "Trend_5m": trend_from_5min_candles,
    "Trend_15m": trend_from_15min_candles,
}
```

### 1.2 Account State Features (from `account_balance`)

**Raw Data:**
```python
{
  "liveBalance": 5000,
  "demoBalance": 10000,
  "dayLimit": 1000,
  "dayBalance": 9000
}
```

**Derived Features:**
```python
account_features = {
    "cash_available": account_balance['demoBalance'],
    "daily_remaining": account_balance['dayLimit'] - abs(account_balance['dayBalance']),
    "leverage_ratio": total_position_value / cash_available,
    "risk_per_trade": cash_available * 0.02,  # 2% risk rule
    "account_heat": trades_last_hour / max_trades_per_hour,
    "profit_factor": wins_profit / losses_lost,
    "win_rate": winning_trades / total_trades,
}
```

### 1.3 Session/Market Context Features (from `session_data` + timestamp)

```python
context_features = {
    "market_session": get_market_session(timestamp),  # US/EU/Asia
    "volatility_regime": "high" if ATR > threshold else "low",
    "liquidity_score": volume_ratio,
    "time_to_market_close": minutes_remaining,
    "day_of_week": timestamp.weekday(),
    "hour_of_day": timestamp.hour,
    "is_news_event": check_economic_calendar(timestamp),
}
```

---

## 2. TRAINING DATA PIPELINE

### 2.1 Data Collection Strategy

**Stage 1: Historical Data Collection**
```python
async def collect_training_data():
    """Collect 3-6 months of historical data"""
    
    for asset in TRADING_ASSETS:  # ["EURUSD_otc", "GBPUSD_otc", ...]
        for period in [60, 300, 900]:  # 1min, 5min, 15min
            
            # Fetch all candles for asset/period
            candles = await client.get_candle_data(
                asset=asset,
                period=period,
                count=10000  # Maximum historical candles
            )
            
            # Store raw data
            save_to_database({
                'asset': asset,
                'period': period,
                'candles': candles,  # [[timestamp, o, h, l, c, v], ...]
                'timestamp': datetime.now()
            })
```

**Stage 2: Real-time Data Streaming**
```python
async def stream_realtime_data():
    """Continuously collect live candles during trading hours"""
    
    while trading_active:
        # Subscribe to multiple assets
        await client.subscribe_realtime_candle("EURUSD_otc", 60)
        
        # Collect wss_message updates
        latest_candle = client.api.wss_message
        
        # Store for training
        log_candle_to_database(latest_candle)
        
        # Update model features in real-time
        await update_feature_cache(latest_candle)
        
        await asyncio.sleep(1)
```

### 2.2 Data Organization for ML

```
trading_bot_data/
├── raw_candles/
│   ├── EURUSD_otc_60s.csv     # timestamp, open, high, low, close, volume
│   ├── GBPUSD_otc_60s.csv
│   └── ...
├── features/
│   ├── EURUSD_otc_features.csv # All technical indicators
│   └── ...
├── labels/
│   ├── EURUSD_otc_labels.csv   # Future price movement: UP/DOWN/HOLD
│   └── ...
├── account_states/
│   ├── balance_history.csv      # Balance changes over time
│   └── ...
└── trades/
    ├── executed_trades.csv      # Entry, exit, P&L
    └── signals_generated.csv    # Model signals before execution
```

---

## 3. TRAINING THE ML MODEL

### 3.1 Classification Problem Setup

**Question:** "Will price go UP or DOWN in the next N candles?"

```python
# Create training dataset
X_train = pd.DataFrame([
    {
        # Price features
        'SMA_10': 1.0850,
        'RSI_14': 65.2,
        'MACD': 0.0012,
        'close_open_ratio': 0.0005,
        'volume_ratio': 1.2,
        
        # Account features
        'account_heat': 0.3,
        'risk_per_trade': 200,
        'win_rate': 0.58,
        
        # Context
        'volatility_regime': 'high',
        'hour_of_day': 14,
        'day_of_week': 2,
    },
    # ... thousands more samples
])

# Create labels (target variable)
y_train = [
    1,  # Price went UP in next 5 candles
    0,  # Price went DOWN
    1,  # UP
    0,  # DOWN
    # ...
]

# Train multiple models
models = {
    'random_forest': RandomForestClassifier(n_estimators=100),
    'xgboost': XGBClassifier(max_depth=6, learning_rate=0.1),
    'neural_network': MLPClassifier(hidden_layer_sizes=(64, 32)),
}

for model_name, model in models.items():
    model.fit(X_train, y_train)
    accuracy = model.score(X_test, y_test)
    print(f"{model_name}: {accuracy:.2%}")
```

### 3.2 Regression Problem (Optional)

**Question:** "What will the exact price be in N candles?"

```python
from sklearn.ensemble import GradientBoostingRegressor

# Target: exact future close price
y_train = [1.0852, 1.0849, 1.0855, ...]  # Future prices

model = GradientBoostingRegressor()
model.fit(X_train, y_train)

# Predict price movements in basis points
predictions = model.predict(X_test)
# Output: [1.0851, 1.0850, 1.0853, ...]
```

---

## 4. FEATURE IMPORTANCE & MODEL INTERPRETATION

### 4.1 Understanding What Drives Predictions

```python
# Get feature importance from trained model
feature_importance = model.feature_importances_

# Rank by importance
importance_df = pd.DataFrame({
    'feature': X_train.columns,
    'importance': feature_importance
}).sort_values('importance', ascending=False)

print(importance_df)
# Output:
#              feature  importance
# 0            RSI_14       0.285   ← Most important
# 1          MACD       0.195
# 2       volume_ratio       0.156
# 3         SMA_10       0.142
# 4      account_heat       0.098
# 5      hour_of_day       0.065
# ...

# Visualization
plt.barh(importance_df['feature'], importance_df['importance'])
plt.xlabel('Feature Importance')
plt.title('What matters most for price prediction?')
plt.show()
```

---

## 5. BACKTESTING: VALIDATING THE BOT

### 5.1 Walk-Forward Backtesting

```python
async def backtest_trading_bot():
    """Test bot on historical data without real money"""
    
    # Historical candles from database
    candles = load_historical_candles("EURUSD_otc", "2024-01-01", "2024-06-30")
    
    # Simulation state
    portfolio = {
        'balance': 10000,
        'positions': [],
        'trades': [],
    }
    
    for i, candle in enumerate(candles):
        timestamp, open_price, high, low, close, volume = candle
        
        # 1. Extract features from recent candles
        recent_candles = candles[max(0, i-50):i+1]
        features = calculate_features(recent_candles)
        
        # 2. Generate signal from trained model
        signal = model.predict([features])[0]  # 0=DOWN, 1=UP
        
        # 3. Execute trade based on signal
        if signal == 1 and len(portfolio['positions']) == 0:
            # BUY signal
            position = {
                'entry_price': close,
                'entry_time': timestamp,
                'size': portfolio['balance'] * 0.1,
                'type': 'BUY'
            }
            portfolio['positions'].append(position)
        
        # 4. Exit strategy (stop loss / take profit)
        for position in portfolio['positions']:
            pnl = (close - position['entry_price']) / position['entry_price']
            
            if pnl > 0.02:  # Take profit at 2%
                portfolio['balance'] += position['size'] * pnl
                portfolio['trades'].append(position)
                portfolio['positions'].remove(position)
            elif pnl < -0.01:  # Stop loss at -1%
                portfolio['balance'] += position['size'] * pnl
                portfolio['trades'].append(position)
                portfolio['positions'].remove(position)
    
    # 6. Calculate performance metrics
    metrics = calculate_metrics(portfolio['trades'])
    return metrics
```

### 5.2 Performance Metrics

```python
def calculate_metrics(trades):
    """Analyze bot performance"""
    
    profits = [t['pnl'] for t in trades if t['pnl'] > 0]
    losses = [t['pnl'] for t in trades if t['pnl'] < 0]
    
    return {
        'total_trades': len(trades),
        'win_rate': len(profits) / len(trades) * 100,
        'average_win': np.mean(profits) if profits else 0,
        'average_loss': np.mean(losses) if losses else 0,
        'profit_factor': sum(profits) / abs(sum(losses)) if losses else 0,
        'total_pnl': sum([t['pnl'] for t in trades]),
        'max_drawdown': calculate_max_drawdown(trades),
        'sharpe_ratio': calculate_sharpe_ratio(trades),
    }
```

---

## 6. LIVE TRADING BOT IMPLEMENTATION

### 6.1 Real-time Decision Loop

```python
async def run_trading_bot():
    """Deploy bot for live trading"""
    
    client = Quotex(email=EMAIL, password=PASSWORD)
    await client.connect()
    
    # Asset allocation
    assets = ["EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc"]
    
    while True:
        try:
            # 1. Get current account state
            balance = await client.get_balance()
            account_state = client.api.account_balance
            
            # 2. Subscribe to real-time data
            for asset in assets:
                await client.subscribe_realtime_candle(asset, 60)
            
            # Wait for WebSocket to update
            await asyncio.sleep(1)
            
            # 3. For each asset, make decision
            for asset in assets:
                # Get latest candle
                latest_candle = client.api.wss_message
                
                if latest_candle['asset'] != asset:
                    continue
                
                # Calculate features
                candles = latest_candle['history']
                features = calculate_features(candles)
                
                # Get prediction from trained model
                signal_probability = model.predict_proba([features])[0]
                
                up_probability = signal_probability[1]  # Probability of UP
                confidence = abs(up_probability - 0.5)
                
                # 4. Only trade if high confidence
                if confidence > 0.15:  # 65%+ confidence
                    
                    # Risk management
                    risk_amount = account_state['demoBalance'] * 0.02
                    trade_amount = risk_amount
                    
                    # Execute trade
                    if up_probability > 0.5:
                        await client.buy(asset, 300, trade_amount)
                        log_trade('BUY', asset, up_probability)
                    else:
                        await client.sell_option()  # Sell (if position exists)
                        log_trade('SELL', asset, up_probability)
            
            # 5. Monitor positions
            await monitor_positions()
            
            # Sleep until next candle close (59 seconds for 1-min candles)
            await asyncio.sleep(59)
            
        except Exception as e:
            logger.error(f"Bot error: {e}")
            await asyncio.sleep(5)
    
    await client.close()
```

---

## 7. USING ACCOUNT DATA FOR RISK MANAGEMENT

### 7.1 Position Sizing Based on Account State

```python
def calculate_position_size(client, risk_percent=0.02):
    """Size positions based on current account balance"""
    
    account = client.api.account_balance
    daily_limit = account['dayLimit']
    daily_used = account['dayBalance']
    
    # Calculate available capital
    available_daily = daily_limit - daily_used
    available_balance = account['demoBalance']
    
    # Position size = % of balance, but respect daily limit
    position_size = min(
        available_balance * risk_percent,  # 2% of balance
        available_daily * 0.5               # Max 50% of daily allowance
    )
    
    return position_size
```

### 7.2 Adaptive Stop Loss

```python
def calculate_stop_loss(account, entry_price, asset_volatility):
    """Adjust stops based on market conditions"""
    
    account = client.api.account_balance
    daily_remaining = account['dayLimit'] - abs(account['dayBalance'])
    
    # If low on daily allowance, use tighter stops
    if daily_remaining < account['dayLimit'] * 0.2:
        stop_loss_pips = 20  # Tighter
    else:
        stop_loss_pips = 50  # Wider
    
    # Adjust for asset volatility
    if asset_volatility > 1.5:
        stop_loss_pips *= 1.5  # More volatile = wider stops
    
    return entry_price - (stop_loss_pips * 0.0001)
```

---

## 8. MULTI-ASSET TRAINING STRATEGY

### 8.1 Asset Correlation

```python
# Train bot on multiple correlated assets
assets = ["EURUSD_otc", "GBPUSD_otc", "AUDUSD_otc"]

# Check if movements are correlated
correlation_matrix = calculate_correlation(assets)
print(correlation_matrix)
#           EURUSD  GBPUSD  AUDUSD
# EURUSD    1.00    0.92    0.78
# GBPUSD    0.92    1.00    0.85
# AUDUSD    0.78    0.85    1.00

# Strategy: Trade highest confidence signal
# Don't over-expose to correlated assets
```

---

## 9. DATA VALIDATION & QUALITY

### 9.1 Checking for Data Issues

```python
def validate_data_quality(candles):
    """Detect anomalies in candle data"""
    
    issues = []
    
    for i, candle in enumerate(candles):
        timestamp, open_p, high, low, close, volume = candle
        
        # Check OHLC relationships
        if high < max(open_p, close):
            issues.append(f"Invalid high at {timestamp}")
        
        if low > min(open_p, close):
            issues.append(f"Invalid low at {timestamp}")
        
        # Check for gaps (market closure)
        if i > 0:
            prev_close = candles[i-1][4]
            gap = abs(open_p - prev_close) / prev_close
            if gap > 0.05:  # 5% gap = suspicious
                issues.append(f"Large gap at {timestamp}")
        
        # Check volume
        if volume == 0:
            issues.append(f"Zero volume at {timestamp}")
    
    return issues
```

---

## 10. FEEDBACK LOOP: CONTINUOUS IMPROVEMENT

### 10.1 Retraining Schedule

```python
async def continuous_learning_loop():
    """Retrain model periodically with new data"""
    
    last_retrain = datetime.now()
    retrain_interval = timedelta(days=7)  # Weekly retraining
    
    while True:
        # Run trading bot
        signal = await run_trading_bot_once()
        
        # Every week, retrain
        if datetime.now() - last_retrain > retrain_interval:
            print("Retraining model with 1 week of new data...")
            
            # Collect recent data
            recent_data = load_data(
                start=datetime.now() - timedelta(weeks=4),
                end=datetime.now()
            )
            
            # Recalculate labels (what actually happened)
            labels = calculate_actual_outcomes(recent_data)
            
            # Retrain model
            X, y = prepare_features(recent_data), labels
            model.fit(X, y)
            
            # Evaluate on holdout set
            accuracy = model.score(X_val, y_val)
            print(f"New model accuracy: {accuracy:.2%}")
            
            last_retrain = datetime.now()
        
        await asyncio.sleep(60)
```

---

## 11. MONITORING & ALERTING

### 11.1 Track Key Metrics

```python
async def monitor_bot_health():
    """Track bot performance in real-time"""
    
    metrics = {
        'signals_generated': 0,
        'trades_executed': 0,
        'win_rate': 0,
        'daily_pnl': 0,
        'model_accuracy': 0,
    }
    
    while True:
        # Update metrics
        trades_today = count_trades_since_session_start()
        wins = count_winning_trades()
        
        metrics['win_rate'] = wins / trades_today if trades_today > 0 else 0
        metrics['daily_pnl'] = calculate_daily_pnl()
        
        # Alert if something's wrong
        if metrics['win_rate'] < 0.45:
            alert("Win rate dropped below 45%! Check model.")
        
        if metrics['daily_pnl'] < -500:
            alert("Daily loss exceeds -500. Pausing trading.")
        
        # Log metrics
        logger.info(f"Daily Stats: {metrics}")
        
        await asyncio.sleep(300)  # Check every 5 minutes
```

---

## SUMMARY: Data → Bot Pipeline

```
Quotex Data
    ↓
[1] Feature Engineering
    - Price: SMA, RSI, MACD, Bollinger Bands
    - Account: Balance, Heat, Win Rate
    - Context: Time, Volatility, Session
    ↓
[2] Collect Training Data
    - 3-6 months historical candles
    - Real-time WebSocket stream
    - Account state snapshots
    ↓
[3] Train ML Models
    - Classification: UP/DOWN prediction
    - XGBoost, Neural Networks, Random Forest
    - Cross-validation & hyperparameter tuning
    ↓
[4] Backtest Strategy
    - Test on historical data
    - Calculate Sharpe, Win Rate, Drawdown
    - Optimize entry/exit rules
    ↓
[5] Deploy Live Bot
    - Real-time predictions from wss_message
    - Risk management using account_balance
    - Position sizing based on daily limits
    ↓
[6] Monitor & Retrain
    - Track daily P&L and win rate
    - Retrain weekly with new data
    - Adapt to changing market conditions
```

This complete pipeline transforms raw Quotex data into an intelligent trading bot!

# 🐢 Turtle Trader + Forex Scalping System

A multi-strategy trading signal scanner with Telegram integration, featuring:
- **Turtle Trading** strategy
- **1-Minute Scalping** (EMA + Stochastic)
- **MA Ribbon Entry** 
- **Bollinger Band Scalping**

## Architecture

The system consists of two Streamlit apps:

### 1. Main Scanner App (`app.py`)
- **Auto-starts scanning** immediately when accessed
- Loads all configuration from `config.csv`
- Displays real-time charts and signals
- Sends signals to Telegram automatically
- **No user controls** - runs continuously

### 2. Control Panel (`control_panel.py`)
- Web interface to configure bot parameters
- Updates `config.csv` when settings are saved
- Changes take effect on next app access

### 3. Configuration File (`config.csv`)
Stores all bot parameters:
- Strategy selection
- Market (Gold/Crypto) and symbol
- Timeframe
- Entry/Exit periods
- Risk/Reward ratio
- Scan interval
- Telegram credentials
- TradingView credentials (optional)

## How to Use

### Step 1: Configure Your Bot
Run the control panel:
```bash
streamlit run control_panel.py
```

1. Choose your strategy
2. Select market and timeframe
3. Set risk/reward ratio
4. Configure scan interval
5. Enter Telegram bot credentials
6. Click **"💾 Save Configuration"**

### Step 2: Run the Scanner
Run the main app:
```bash
streamlit run app.py
```

The app will:
- Automatically load your configuration
- Start scanning immediately
- Display live charts
- Send signals to Telegram when opportunities are detected

## Files

```
/workspace/
├── app.py                 # Main scanner app (auto-starts)
├── control_panel.py       # Configuration interface
├── config.csv             # Bot configuration (auto-created)
├── core/
│   ├── data_fetcher.py    # Market data retrieval
│   ├── turtle_logic.py    # Turtle Trading signals
│   └── scalping_strategies.py  # Forex scalping strategies
└── utils/
    └── notifier.py        # Telegram notifications
```

## Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| strategy_choice | Trading strategy | Turtle Trading |
| mode | Asset type (gold/crypto) | gold |
| symbol | Crypto pair | BTC/USDT |
| interval | Timeframe | 1h |
| entry_period | Entry lookback period | 20 |
| exit_period | Exit lookback period | 10 |
| scan_interval | Seconds between scans | 60 |
| risk_reward_ratio | R:R ratio for TP calculation | 2.5 |
| tg_token | Telegram bot token | (required) |
| tg_chat | Telegram chat ID | (required) |
| tv_username | TradingView username | (optional) |
| tv_password | TradingView password | (optional) |

## Deployment

### Local Development
```bash
pip install -r requirements.txt
streamlit run control_panel.py  # Configure first
streamlit run app.py            # Then run scanner
```

### Streamlit Cloud
1. Connect your GitHub repository
2. Set main file to `app.py`
3. The app will auto-start on every visit
4. Use `control_panel.py` to update settings

## Features

✅ **Automatic Scanning** - No manual start required  
✅ **Configurable Strategies** - 4 different trading strategies  
✅ **Risk Management** - Customizable R:R ratios  
✅ **Telegram Integration** - Real-time signal notifications  
✅ **Live Charts** - Interactive Plotly charts with signal markers  
✅ **Signal History** - Track all generated signals  
✅ **Trade Tracking** - Monitor active trades and status  

## Notes

- The main app (`app.py`) has **no controls** - it's designed to run continuously
- All configuration changes must be made through `control_panel.py`
- The app will create a default `config.csv` if none exists
- Daily trade limit guardrail: 50 trades per day (configurable in code)

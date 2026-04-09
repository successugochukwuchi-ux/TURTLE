# 🐢 Turtle Trader - Streamlit Edition

Real-time Turtle Trading Channel scanner with confidence levels, stop loss & take profit suggestions. Built for deployment on Streamlit Community Cloud.

## Features

- **Real-time Scanning**: Continuously monitors XAUUSD (Gold) or Crypto markets
- **Turtle Trading Strategy**: Implements the classic Turtle Trading Channel breakout system
- **Confidence Levels**: Each signal includes a 0-100% confidence score based on:
  - Breakout strength
  - Channel width (narrower = stronger)
  - Trend consistency
- **Risk Management**: Automatic calculation of:
  - Suggested Stop Loss (based on channel boundaries & ATR)
  - Take Profit targets (2:1 and 3:1 risk-reward ratios)
  - Risk-reward ratios displayed for each target
- **Interactive Charts**: Plotly candlestick charts with Turtle channels overlay
- **Telegram Alerts**: Optional real-time notifications to your Telegram
- **Signal History**: Track all signals with full details, exportable to CSV

## Deployment on Streamlit Community Cloud

1. **Push to GitHub**: Upload this repository to your GitHub account

2. **Deploy on Streamlit Cloud**:
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Click "New app"
   - Select your repository and branch
   - Set Main file path: `app.py`
   - Click "Deploy!"

3. **Configure Settings** (in the app sidebar):
   - Select asset type (Gold or Crypto)
   - Choose timeframe and Turtle parameters
   - Add Telegram Bot token and Chat ID for alerts (optional)
   - Add TradingView credentials for premium data (optional)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## Configuration

### Turtle Parameters
- **Entry Period** (default: 20): Lookback period for entry channel
- **Exit Period** (default: 10): Lookback period for exit channel

### Scanner Settings
- **Scan Interval**: How often to check for new signals (10-300 seconds)

### Telegram Integration
1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Get your bot token
3. Get your chat ID (use [@userinfobot](https://t.me/userinfobot))
4. Enter both in the sidebar

## Signal Types

- 🟢 **ENTER_LONG**: Buy signal - price broke above entry channel
- 🔴 **ENTER_SHORT**: Sell signal - price broke below entry channel  
- 🟡 **EXIT_LONG**: Close long position - price broke below exit channel
- 🟡 **EXIT_SHORT**: Close short position - price broke above exit channel

## How Confidence is Calculated

The confidence score (0-100%) is based on three factors:

1. **Breakout Strength** (0-40 points): How far price moved beyond the channel
2. **Channel Width** (0-30 points): Narrower channels indicate stronger breakouts
3. **Trend Consistency** (0-30 points): Recent price action alignment with signal direction

## Disclaimer

This tool is for educational and informational purposes only. Trading involves substantial risk of loss. Past performance does not guarantee future results. Always do your own research and consider consulting with a qualified financial advisor.

## License

MIT License

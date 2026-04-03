# Turtle Trader Discord Bot

A Discord bot for multi-strategy trading signals with confidence levels, designed for Kata Bump hosting.

## Features

- **Multiple Trading Strategies**: Donchian Channels, RSI+MACD, SuperTrend, ZigZag, Bollinger Bands, EMA Crossover
- **Real-time Signal Detection**: Automatically scans markets and sends alerts
- **Confidence Levels**: Each signal includes a confidence score (0-100%)
- **Stop Loss & Take Profit**: Automatic calculation of risk management levels
- **Admin Commands**: Full control via Discord slash commands

## Slash Commands

| Command | Description |
|---------|-------------|
| `/tf` | Set the timeframe (e.g., 1m, 5m, 15m, 1h, 4h, 1d) |
| `/scan` | Start the scanning service |
| `/inst` | Choose what instrument to trade (gold or crypto symbol) |
| `/strat` | Choose from available strategies with parameters |
| `/end` | Stop the bot |
| `/int` | Set the check interval in seconds |
| `/status` | Show current bot status |
| `/history` | Show recent signal history |

## Setup

### 1. Create Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and name it
3. Go to "Bot" section and click "Add Bot"
4. Copy your **Bot Token**
5. Under "Privileged Gateway Intents", enable:
   - Message Content Intent
6. Go to "OAuth2" → "URL Generator"
7. Select scopes: `bot`, `applications.commands`
8. Select permissions: `Send Messages`, `Embed Links`
9. Use the generated URL to invite the bot to your server

### 2. Configure Bot Token

Edit `bot.py` and replace the token:

```python
BOT_TOKEN = "YOUR_ACTUAL_BOT_TOKEN_HERE"
```

The Application ID and Public Key are already configured:
- Application ID: `1489598877425205328`
- Public Key: `1ba152b1466018193d26eda90a5cd547ecd952d50e28f60486927b48c874f448`

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Deploy to Kata Bump

1. Zip all files in this directory
2. Upload the zip file to Kata Bump
3. Configure the start command: `python bot.py`

## Usage

Once deployed and running:

1. **Set Timeframe**: `/tf 1h` (or any valid timeframe)
2. **Set Instrument**: `/inst gold` or `/inst BTCUSDT`
3. **Set Strategy**: `/strat donchian entry_period:20 exit_period:10`
4. **Set Check Interval**: `/int 60` (minimum 10 seconds)
5. **Start Scanning**: `/scan`
6. **Stop**: `/end`

## Available Strategies

### Donchian Channels (Turtle)
- Parameters: `entry_period`, `exit_period`
- Breakout strategy based on channel highs/lows

### RSI + MACD
- Parameters: `rsi_period`, `macd_fast`, `macd_slow`, `macd_signal_period`
- Momentum + Trend convergence strategy

### SuperTrend
- Parameters: `st_period`, `st_multiplier`
- Volatility-based trend following

### ZigZag
- Parameters: `threshold`
- Price reversal pattern detection

### Bollinger Bands
- Parameters: `bb_period`, `bb_std_dev`
- Mean reversion strategy

### EMA Crossover
- Parameters: `ema_fast`, `ema_slow`
- Moving average trend strategy

## File Structure

```
├── bot.py              # Main Discord bot code
├── core/
│   ├── strategies.py   # Trading strategy implementations
│   └── data_fetcher.py # Market data fetching
├── utils/
│   └── notifier.py     # Notification utilities
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## Notes

- The bot runs continuously once started with `/scan`
- Signals are posted as rich embeds in the channel where `/scan` was executed
- Signal history is limited to the last 50 signals
- Minimum check interval is 10 seconds to prevent rate limiting

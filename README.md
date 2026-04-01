# 🐢 Turtle Trader — TUTCI Dashboard

A production-ready Streamlit dashboard implementing **Richard Dennis & Bill Eckhardt's Turtle Trading Rules** (TUTCI variant) for **XAUUSD (Gold)** and **BTC/USDT (Crypto)**.

---

## Features

| Feature | Details |
|---|---|
| **Entry Signal** | 20-period Donchian Channel breakout (configurable) |
| **Exit Signal** | 10-period Donchian Channel breakout (configurable) |
| **Signals** | `ENTER_LONG`, `ENTER_SHORT`, `EXIT_LONG`, `EXIT_SHORT` |
| **Data Sources** | `yfinance` for Gold · `ccxt` (Binance) for Crypto |
| **Alerts** | Telegram Bot API |
| **Dashboard** | Streamlit — real-time price + channel chart, signal log |
| **Headless Mode** | `run_loop.py` — `while True` scanner for VPS/cron |

---

## Pine Script → Python Translation

```pine
// Pine Script (TUTCI)
entryHigh = ta.highest(high, 20)
entryLow  = ta.lowest(low,  20)
exitHigh  = ta.highest(high, 10)
exitLow   = ta.lowest(low,  10)

enterLong  = ta.crossover(close, entryHigh[1])
enterShort = ta.crossunder(close, entryLow[1])
exitLong   = ta.crossunder(close, exitLow[1])
exitShort  = ta.crossover(close, exitHigh[1])
```

The `[1]` offset (previous bar's channel) is replicated via `.shift(1)` in pandas.

---

## Quickstart

```bash
# 1. Clone / unzip the repo
cd turtle-trader

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the Streamlit dashboard
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

---

## Headless Loop (VPS)

```bash
python run_loop.py \
  --mode gold \
  --interval 1h \
  --entry 20 \
  --exit 10 \
  --tg-token "YOUR_BOT_TOKEN" \
  --tg-chat  "YOUR_CHAT_ID" \
  --sleep 60
```

Signals are saved to `signals.json` and printed to stdout.

---

## Telegram Setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy token
2. Add bot to your group or get your personal chat ID via `@userinfobot`
3. Enter token + chat ID in the **sidebar** of the dashboard, or pass as CLI args

---

## Project Structure

```
turtle-trader/
├── app.py                  # Streamlit dashboard (main entry)
├── run_loop.py             # Headless while-True scanner
├── requirements.txt
├── .streamlit/
│   └── config.toml         # Dark theme config
├── core/
│   ├── data_fetcher.py     # yfinance + ccxt data fetchers
│   └── turtle_logic.py     # Donchian channel + signal logic
└── utils/
    ├── notifier.py         # Telegram Bot API wrapper
    └── signal_log.py       # In-memory + JSON signal log
```

---

## Disclaimer

This tool is for **educational purposes only**. It does not constitute financial advice. Past signals do not guarantee future performance. Always manage risk appropriately.

---

## License

MIT

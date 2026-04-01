"""
Background Loop Runner
=======================
Standalone script that runs the Turtle Trading signal scanner in a
`while True` loop, printing signals to stdout and optionally sending
Telegram alerts. Useful for running headlessly (e.g. on a VPS / cron).

Usage:
    python run_loop.py --mode gold --interval 1h --entry 20 --exit 10 \
        --tg-token "123:ABC" --tg-chat "-100xxx" --sleep 60
"""

import argparse
import time
import logging
from datetime import datetime, timezone

from core.data_fetcher import fetch_gold, fetch_crypto
from core.turtle_logic import compute_turtle_signals, get_latest_signal
from utils.notifier import TelegramNotifier, NullNotifier
from utils.signal_log import SignalLog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="Turtle Trader — headless loop")
    p.add_argument("--mode",      choices=["gold", "crypto"], default="gold")
    p.add_argument("--symbol",    default="BTC/USDT",         help="Crypto symbol")
    p.add_argument("--interval",  default="1h",               help="Timeframe")
    p.add_argument("--entry",     type=int, default=20,       help="Entry channel period")
    p.add_argument("--exit",      type=int, default=10,       help="Exit channel period")
    p.add_argument("--sleep",     type=int, default=60,       help="Seconds between checks")
    p.add_argument("--tg-token",  default="",                 help="Telegram bot token")
    p.add_argument("--tg-chat",   default="",                 help="Telegram chat ID")
    p.add_argument("--log-file",  default="signals.json",     help="Signal log JSON path")
    return p.parse_args()


def main():
    args    = parse_args()
    sig_log = SignalLog(max_entries=200, persist_path=args.log_file)

    # Notifier
    if args.tg_token and args.tg_chat:
        notifier = TelegramNotifier(args.tg_token, args.tg_chat)
        log.info("Telegram notifier active → chat %s", args.tg_chat)
        notifier.test()
    else:
        notifier = NullNotifier()
        log.info("No Telegram credentials provided — running without alerts.")

    log.info(
        "Starting loop | mode=%s interval=%s entry=%d exit=%d sleep=%ds",
        args.mode, args.interval, args.entry, args.exit, args.sleep,
    )

    last_signal = None   # avoid re-alerting the same candle

    while True:
        try:
            # Fetch data
            if args.mode == "gold":
                df = fetch_gold(interval=args.interval, lookback_bars=max(args.entry, args.exit) * 10)
                asset_label = "XAUUSD"
            else:
                df = fetch_crypto(args.symbol, interval=args.interval,
                                  lookback_bars=max(args.entry, args.exit) * 10)
                asset_label = args.symbol

            df = compute_turtle_signals(df, entry_period=args.entry, exit_period=args.exit)
            info = get_latest_signal(df)

            price  = info["close"]
            signal = info["signal"]
            ts     = info["timestamp"]

            # Deduplicate: only log/alert if signal is new or on a new bar
            sig_key = (signal, str(ts))
            if signal and sig_key != last_signal:
                last_signal = sig_key
                log.info(
                    "SIGNAL %-14s | %s | price=%.4f",
                    signal, asset_label, price,
                )
                sig_log.add(signal, price, asset_label, args.interval, ts)

                msg = TelegramNotifier.format_signal(signal, asset_label, price, args.interval)
                notifier.send(msg)
            else:
                log.info("no signal | %s | price=%.4f | bar=%s", asset_label, price, ts)

        except KeyboardInterrupt:
            log.info("Interrupted — stopping.")
            break
        except Exception as exc:
            log.error("Loop error: %s", exc, exc_info=True)

        time.sleep(args.sleep)


if __name__ == "__main__":
    main()

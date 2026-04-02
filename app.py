"""
Turtle Trader — Flask Control Panel
Runs the scanner in a background thread. GUI accessible via browser (Railway subdomain).
"""

import threading
import time
import logging
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request

from core.data_fetcher import fetch_gold, fetch_crypto
from core.turtle_logic import compute_turtle_signals, get_latest_signal
from utils.notifier import TelegramNotifier, NullNotifier
from utils.signal_log import SignalLog

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Hardcoded credentials (edit here) ────────────────────────────────────────
TG_TOKEN = "8639500812:AAG2cLSiKyRVwazanOlN--PInxu4-m58ES0"
TV_USERNAME = ""  # your TradingView username
TV_PASSWORD = ""  # your TradingView password
TG_CHAT  = "8739979073"

# ── Shared state (thread-safe via lock) ──────────────────────────────────────
lock = threading.Lock()

state = {
    "running":      False,
    "mode":         "gold",         # "gold" | "crypto"
    "symbol":       "BTC/USDT",
    "interval":     "1h",
    "entry":        20,
    "exit":         10,
    "sleep":        60,
    "last_price":   None,
    "last_signal":  None,
    "last_check":   None,
    "error":        None,
    "checks_done":  0,
    "tg_token":     TG_TOKEN,
    "tg_chat":      TG_CHAT,
    "tv_username":  TV_USERNAME,
    "tv_password":  TV_PASSWORD,
}

sig_log  = SignalLog(max_entries=200, persist_path="signals.json")
_thread  = None
_stop_ev = threading.Event()


# ── Scanner thread ────────────────────────────────────────────────────────────

def scanner_loop():
    log.info("Scanner started")
    last_sig_key = None

    while not _stop_ev.is_set():
        try:
            with lock:
                mode     = state["mode"]
                symbol   = state["symbol"]
                interval = state["interval"]
                entry    = state["entry"]
                exit_p   = state["exit"]
                tg_token    = state["tg_token"]
                tg_chat     = state["tg_chat"]
                tv_username = state["tv_username"]
                tv_password = state["tv_password"]
                sleep_s     = state["sleep"]

            notifier = TelegramNotifier(tg_token, tg_chat) if (tg_token and tg_chat) else NullNotifier()

            # Inject TV credentials into the data_fetcher module at runtime
            import core.data_fetcher as _df_mod
            _df_mod.TV_USERNAME = tv_username
            _df_mod.TV_PASSWORD = tv_password

            lookback = max(entry, exit_p) * 10
            if mode == "gold":
                df = fetch_gold(interval=interval, lookback_bars=lookback)
                asset_label = "XAUUSD"
            else:
                df = fetch_crypto(symbol, interval=interval, lookback_bars=lookback)
                asset_label = symbol

            df   = compute_turtle_signals(df, entry_period=entry, exit_period=exit_p)
            info = get_latest_signal(df)

            price  = info["close"]
            signal = info["signal"]
            ts     = info["timestamp"]
            sig_key = (signal, str(ts))

            with lock:
                state["last_price"]  = price
                state["last_signal"] = signal or "—"
                state["last_check"]  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                state["error"]       = None
                state["checks_done"] += 1

            if signal and sig_key != last_sig_key:
                last_sig_key = sig_key
                sig_log.add(signal, price, asset_label, interval, ts)
                msg = TelegramNotifier.format_signal(signal, asset_label, price, interval)
                notifier.send(msg)
                log.info("SIGNAL %s | %s | %.4f", signal, asset_label, price)
            else:
                log.info("no signal | %s | price=%.4f", asset_label, price)

        except Exception as exc:
            log.error("Scanner error: %s", exc)
            with lock:
                state["error"] = str(exc)

        _stop_ev.wait(timeout=sleep_s)

    log.info("Scanner stopped")


def start_scanner():
    global _thread, _stop_ev
    if _thread and _thread.is_alive():
        return
    _stop_ev.clear()
    _thread = threading.Thread(target=scanner_loop, daemon=True)
    _thread.start()
    with lock:
        state["running"] = True


def stop_scanner():
    global _stop_ev
    _stop_ev.set()
    with lock:
        state["running"] = False


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with lock:
        tg_token = state["tg_token"]
        tg_chat  = state["tg_chat"]
    return render_template("index.html", tg_token=tg_token, tg_chat=tg_chat)


@app.route("/api/status")
def api_status():
    with lock:
        s = dict(state)
    s["log"] = sig_log.as_dataframe().head(10).to_dict(orient="records")
    return jsonify(s)


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.json or {}
    with lock:
        state["mode"]     = data.get("mode",     state["mode"])
        state["symbol"]   = data.get("symbol",   state["symbol"])
        state["interval"] = data.get("interval", state["interval"])
        state["entry"]    = int(data.get("entry",  state["entry"]))
        state["exit"]     = int(data.get("exit",   state["exit"]))
        state["sleep"]    = int(data.get("sleep",  state["sleep"]))
    start_scanner()
    return jsonify({"ok": True, "message": "Scanner started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop_scanner()
    return jsonify({"ok": True, "message": "Scanner stopped"})


@app.route("/api/test_telegram", methods=["POST"])
def api_test_telegram():
    with lock:
        token = state["tg_token"]
        chat  = state["tg_chat"]
    try:
        n  = TelegramNotifier(token, chat)
        ok = n.test()
        return jsonify({"ok": ok, "message": "Message sent ✓" if ok else "Telegram returned an error"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route("/api/update_config", methods=["POST"])
def api_update_config():
    data = request.json or {}
    with lock:
        for key in ("mode", "symbol", "interval"):
            if key in data:
                state[key] = data[key]
        for key in ("entry", "exit", "sleep"):
            if key in data:
                state[key] = int(data[key])
        if "tg_token" in data:
            state["tg_token"] = data["tg_token"]
        if "tg_chat" in data:
            state["tg_chat"] = data["tg_chat"]
        if "tv_username" in data:
            state["tv_username"] = data["tv_username"]
        if "tv_password" in data:
            state["tv_password"] = data["tv_password"]
    return jsonify({"ok": True})


@app.route("/api/clear_log", methods=["POST"])
def api_clear_log():
    sig_log.clear()
    return jsonify({"ok": True})


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

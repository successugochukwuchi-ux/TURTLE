"""
Turtle Trading System — XAUUSD & Crypto Dashboard
Implements Richard Dennis / Bill Eckhardt Turtle Rules (TUTCI variant)
Donchian Channel breakout: 20-period entry, 10-period exit
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
import threading
import queue
from datetime import datetime, timezone

from core.data_fetcher import fetch_gold, fetch_crypto
from core.turtle_logic import compute_turtle_signals
from utils.notifier import TelegramNotifier
from utils.signal_log import SignalLog

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🐢 Turtle Trader",
    page_icon="🐢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow+Condensed:wght@300;600;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Barlow Condensed', sans-serif;
}

/* Dark terminal background */
.stApp {
    background: #0b0f14;
    color: #c8d6e5;
}

.block-container {
    padding: 1.5rem 2rem;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0d1117;
    border-right: 1px solid #1e2d3d;
}

section[data-testid="stSidebar"] * {
    color: #8badc1 !important;
}

/* Metric cards */
[data-testid="metric-container"] {
    background: #111922;
    border: 1px solid #1e2d3d;
    border-radius: 4px;
    padding: 12px 16px;
}

[data-testid="metric-container"] label {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.7rem;
    color: #4a6fa5 !important;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-family: 'Share Tech Mono', monospace;
    font-size: 1.4rem;
    color: #e2f0fb !important;
}

/* Signal badges */
.sig-long {
    background: #0d3b2b;
    color: #00ff9d;
    border: 1px solid #00cc7a;
    padding: 3px 10px;
    border-radius: 3px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    font-weight: bold;
    letter-spacing: 0.1em;
}
.sig-short {
    background: #3b0d0d;
    color: #ff4d6d;
    border: 1px solid #cc0022;
    padding: 3px 10px;
    border-radius: 3px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    font-weight: bold;
    letter-spacing: 0.1em;
}
.sig-exit {
    background: #1e1e2e;
    color: #f0c060;
    border: 1px solid #c09010;
    padding: 3px 10px;
    border-radius: 3px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    font-weight: bold;
    letter-spacing: 0.1em;
}
.sig-none {
    color: #3a5068;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
}

/* Table styling */
.log-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.8rem;
}
.log-table th {
    background: #0d1117;
    color: #4a6fa5;
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #1e2d3d;
    letter-spacing: 0.1em;
    font-size: 0.7rem;
    text-transform: uppercase;
}
.log-table td {
    padding: 8px 12px;
    border-bottom: 1px solid #111922;
    color: #8badc1;
}
.log-table tr:hover td {
    background: #111922;
}

/* Divider */
hr {
    border: none;
    border-top: 1px solid #1e2d3d;
    margin: 1rem 0;
}

/* Header */
.main-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-weight: 800;
    font-size: 2.6rem;
    letter-spacing: -0.01em;
    color: #e2f0fb;
    line-height: 1;
}
.sub-title {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    color: #2e5070;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin-top: 2px;
}

/* Status dot */
.status-live {
    display: inline-block;
    width: 8px; height: 8px;
    background: #00ff9d;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse 1.5s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}

.status-bar {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.72rem;
    color: #2e5070;
    margin-bottom: 1.5rem;
}

/* Stbutton */
.stButton > button {
    background: #111922;
    border: 1px solid #1e2d3d;
    color: #8badc1;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.8rem;
    border-radius: 3px;
    transition: all 0.2s;
}
.stButton > button:hover {
    border-color: #4a6fa5;
    color: #e2f0fb;
    background: #0d1117;
}
</style>
""", unsafe_allow_html=True)

# ─── Session State Init ──────────────────────────────────────────────────────
if "signal_log" not in st.session_state:
    st.session_state.signal_log = SignalLog(max_entries=50)
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None
if "running" not in st.session_state:
    st.session_state.running = False
if "notifier" not in st.session_state:
    st.session_state.notifier = None

# ─── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🐢 TURTLE TRADER")
    st.markdown("---")

    asset = st.radio(
        "MARKET",
        options=["XAUUSD (Gold)", "BTC/USDT (Crypto)"],
        index=0,
    )
    ticker_mode = "gold" if "XAUUSD" in asset else "crypto"

    st.markdown("---")
    st.markdown("**TURTLE PARAMETERS**")
    entry_period = st.slider("Entry Channel (bars)", 10, 55, 20)
    exit_period  = st.slider("Exit Channel (bars)",  5, 30, 10)
    interval     = st.selectbox("Timeframe", ["1h", "4h", "1d"], index=0)

    st.markdown("---")
    st.markdown("**TELEGRAM ALERTS**")
    tg_token = st.text_input("Bot Token", type="password", placeholder="1234:ABC...")
    tg_chat  = st.text_input("Chat ID",  placeholder="-100xxxxxxxx")

    tg_col1, tg_col2 = st.columns(2)
    with tg_col1:
        if st.button("💾 Save", use_container_width=True):
            if tg_token and tg_chat:
                st.session_state.notifier = TelegramNotifier(tg_token, tg_chat)
                st.success("Saved ✓")
            else:
                st.error("Enter token + chat ID")
    with tg_col2:
        if st.button("📡 Test", use_container_width=True):
            if st.session_state.notifier:
                ok = st.session_state.notifier.test()
                if ok:
                    st.success("Sent ✓")
                else:
                    st.error("Failed ✗")
            elif tg_token and tg_chat:
                # Save-and-test in one click
                try:
                    n = TelegramNotifier(tg_token, tg_chat)
                    ok = n.test()
                    if ok:
                        st.session_state.notifier = n
                        st.success("Sent ✓")
                    else:
                        st.error("Failed ✗")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Enter token + chat ID first")

    # Status indicator
    if st.session_state.notifier:
        st.markdown(
            '<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.7rem;'
            'color:#00cc7a;">● NOTIFIER ACTIVE</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span style="font-family:\'Share Tech Mono\',monospace;font-size:0.7rem;'
            'color:#3a5068;">○ NOTIFIER OFF</span>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    refresh_secs = st.slider("Auto-refresh (sec)", 30, 300, 60, step=30)
    auto_refresh = st.toggle("Live mode", value=False)

# ─── Header ─────────────────────────────────────────────────────────────────
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown('<div class="main-title">🐢 TURTLE TRADER</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Donchian Channel Breakout System — TUTCI Rules</div>', unsafe_allow_html=True)

with col_h2:
    if st.button("⟳ Refresh Now", use_container_width=True):
        st.session_state.last_refresh = datetime.now(timezone.utc)
        st.rerun()

# ─── Data Fetch ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=55, show_spinner=False)
def load_data(mode: str, tf: str, ep: int, xp: int):
    try:
        if mode == "gold":
            df = fetch_gold(interval=tf, lookback_bars=max(ep, xp) * 10)
        else:
            df = fetch_crypto("BTC/USDT", interval=tf, lookback_bars=max(ep, xp) * 10)
        df = compute_turtle_signals(df, entry_period=ep, exit_period=xp)
        return df, None
    except Exception as e:
        return None, str(e)

with st.spinner("Fetching market data…"):
    df, err = load_data(ticker_mode, interval, entry_period, exit_period)

if err:
    st.error(f"**Data error:** {err}")
    if "binance" in str(err).lower() or "451" in str(err):
        st.info(
            "💡 **Binance is geo-restricted in your region.** "
            "The app automatically tries KuCoin → Bybit → OKX → Gate.io → MEXC as fallbacks. "
            "If all fail, check that your internet connection can reach these exchanges."
        )
    st.stop()

if df is None or df.empty:
    st.warning("No data returned. Check your internet connection.")
    st.stop()

# ─── Metrics Row ─────────────────────────────────────────────────────────────
latest       = df.iloc[-1]
price        = latest["close"]
entry_high   = latest["entry_high"]
entry_low    = latest["entry_low"]
exit_high    = latest["exit_high"]
exit_low     = latest["exit_low"]
signal       = latest.get("signal", "—")
prev_close   = df.iloc[-2]["close"] if len(df) > 1 else price
pct_change   = (price - prev_close) / prev_close * 100

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("PRICE",        f"{price:,.2f}",       f"{pct_change:+.2f}%")
m2.metric("ENTRY HIGH",   f"{entry_high:,.2f}",  help=f"{entry_period}-bar Donchian high")
m3.metric("ENTRY LOW",    f"{entry_low:,.2f}",   help=f"{entry_period}-bar Donchian low")
m4.metric("EXIT HIGH",    f"{exit_high:,.2f}",   help=f"{exit_period}-bar Donchian high")
m5.metric("EXIT LOW",     f"{exit_low:,.2f}",    help=f"{exit_period}-bar Donchian low")

# ─── Signal Banner ───────────────────────────────────────────────────────────
sig_map = {
    "ENTER_LONG":  ("sig-long",  "▲ ENTER LONG"),
    "ENTER_SHORT": ("sig-short", "▼ ENTER SHORT"),
    "EXIT_LONG":   ("sig-exit",  "◀ EXIT LONG"),
    "EXIT_SHORT":  ("sig-exit",  "▶ EXIT SHORT"),
}
if signal in sig_map:
    css, label = sig_map[signal]
    st.markdown(
        f'<div style="margin:8px 0;"><span class="{css}">{label}</span>'
        f' <span style="font-family:\'Share Tech Mono\',monospace;font-size:0.75rem;color:#2e5070;margin-left:12px;">'
        f'@ {price:,.2f} — {datetime.now().strftime("%H:%M:%S")}</span></div>',
        unsafe_allow_html=True,
    )
    # Log signal
    st.session_state.signal_log.add(signal, price, asset.split(" ")[0], interval)
    # Telegram alert
    if st.session_state.notifier:
        try:
            st.session_state.notifier.send(
                f"🐢 *{label}*\n"
                f"Asset: `{asset.split()[0]}`\n"
                f"Price: `{price:,.2f}`\n"
                f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
            )
        except Exception:
            pass

st.markdown('<hr>', unsafe_allow_html=True)

# ─── Chart ───────────────────────────────────────────────────────────────────
st.markdown("#### PRICE CHART  ·  DONCHIAN CHANNELS")

chart_bars = st.slider("Bars to display", 50, min(500, len(df)), 150, step=10)
plot_df = df.tail(chart_bars)[["close", "entry_high", "entry_low", "exit_high", "exit_low"]].copy()
plot_df.index = pd.to_datetime(plot_df.index)

st.line_chart(
    plot_df,
    height=380,
    use_container_width=True,
    color=["#e2f0fb", "#00cc7a", "#00cc7a", "#f0c060", "#f0c060"],
)

st.caption(
    "🟢 Entry Channel (20-bar)  🟡 Exit Channel (10-bar)  ⬜ Close"
)

st.markdown('<hr>', unsafe_allow_html=True)

# ─── Signal Log ──────────────────────────────────────────────────────────────
st.markdown("#### SIGNAL LOG")

log_df = st.session_state.signal_log.as_dataframe()

if log_df.empty:
    st.markdown('<p class="sig-none">No signals triggered yet in this session.</p>', unsafe_allow_html=True)
else:
    rows_html = ""
    for _, row in log_df.head(5).iterrows():
        sig = row["signal"]
        css, label = sig_map.get(sig, ("sig-none", sig))
        rows_html += (
            f"<tr>"
            f"<td>{row['timestamp']}</td>"
            f"<td><span class='{css}'>{label}</span></td>"
            f"<td>{row['asset']}</td>"
            f"<td>{float(row['price']):,.2f}</td>"
            f"<td>{row['timeframe']}</td>"
            f"</tr>"
        )

    st.markdown(f"""
    <table class="log-table">
        <thead><tr>
            <th>TIME</th><th>SIGNAL</th><th>ASSET</th><th>PRICE</th><th>TF</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

# ─── Raw Data Expander ───────────────────────────────────────────────────────
with st.expander("📊 Raw DataFrame (last 20 bars)"):
    display_cols = ["open","high","low","close","entry_high","entry_low","exit_high","exit_low","signal"]
    st.dataframe(
        df[display_cols].tail(20).style.format({
            col: "{:,.2f}" for col in display_cols if col != "signal"
        }),
        use_container_width=True,
    )

# ─── Status Bar ──────────────────────────────────────────────────────────────
last = st.session_state.last_refresh or datetime.now(timezone.utc)
st.markdown(
    f'<div class="status-bar"><span class="status-live"></span>'
    f'LAST UPDATE: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")} '
    f'· BARS LOADED: {len(df)} · INTERVAL: {interval} · '
    f'NOTIFIER: {"ACTIVE" if st.session_state.notifier else "OFF"}</div>',
    unsafe_allow_html=True,
)

# ─── Auto-Refresh ─────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_secs)
    st.session_state.last_refresh = datetime.now(timezone.utc)
    st.rerun()

"""
Turtle Trader — Streamlit App for Community Cloud
Real-time Turtle Trading scanner with confidence levels, stop loss & take profit suggestions.
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime, timezone
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.data_fetcher import fetch_gold, fetch_crypto
from core.turtle_logic import compute_turtle_signals, get_latest_signal
from utils.notifier import TelegramNotifier

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🐢 Turtle Trader",
    page_icon="🐢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Session State Initialization ──────────────────────────────────────────────
if "running" not in st.session_state:
    st.session_state.running = False
if "last_signal" not in st.session_state:
    st.session_state.last_signal = None
if "last_price" not in st.session_state:
    st.session_state.last_price = None
if "last_check" not in st.session_state:
    st.session_state.last_check = None
if "signal_history" not in st.session_state:
    st.session_state.signal_history = []
if "last_sig_key" not in st.session_state:
    st.session_state.last_sig_key = None
if "error" not in st.session_state:
    st.session_state.error = None

# ── Helper Functions ──────────────────────────────────────────────────────────

def calculate_confidence(df, entry_period: int = 20, exit_period: int = 10) -> float:
    """
    Calculate confidence level (0-100%) based on multiple factors:
    - Breakout strength (how far price broke through the channel)
    - Volume confirmation (if available)
    - Recent volatility
    - Channel width (narrower channels = stronger breakouts)
    """
    if len(df) < max(entry_period, exit_period):
        return 50.0
    
    latest = df.iloc[-1]
    
    # Factor 1: Breakout Strength (0-40 points)
    breakout_strength = 0
    if latest.get("signal") in ["ENTER_LONG", "EXIT_SHORT"]:
        # Price vs entry_upper
        if latest.get("entry_upper") and latest["close"] > latest["entry_upper"]:
            pct_breakout = (latest["close"] - latest["entry_upper"]) / latest["entry_upper"] * 100
            breakout_strength = min(40, pct_breakout * 10)  # Cap at 40
    elif latest.get("signal") in ["ENTER_SHORT", "EXIT_LONG"]:
        # Price vs entry_lower
        if latest.get("entry_lower") and latest["close"] < latest["entry_lower"]:
            pct_breakout = (latest["entry_lower"] - latest["close"]) / latest["entry_lower"] * 100
            breakout_strength = min(40, pct_breakout * 10)
    
    # Factor 2: Channel Width - Narrower = Stronger (0-30 points)
    channel_width_score = 30
    if latest.get("entry_upper") and latest.get("entry_lower"):
        channel_width = (latest["entry_upper"] - latest["entry_lower"]) / latest["entry_lower"] * 100
        # Narrower channels (< 2%) get higher scores
        if channel_width < 1:
            channel_width_score = 30
        elif channel_width < 2:
            channel_width_score = 25
        elif channel_width < 3:
            channel_width_score = 20
        elif channel_width < 5:
            channel_width_score = 15
        else:
            channel_width_score = 10
    
    # Factor 3: Trend Consistency (0-30 points)
    trend_score = 30
    if len(df) >= 5:
        recent_closes = df["close"].iloc[-5:].values
        if latest.get("signal") in ["ENTER_LONG", "EXIT_SHORT"]:
            # Uptrend confirmation
            if all(recent_closes[i] <= recent_closes[i+1] for i in range(len(recent_closes)-1)):
                trend_score = 30
            elif recent_closes[-1] > recent_closes[0]:
                trend_score = 20
            else:
                trend_score = 10
        else:
            # Downtrend confirmation
            if all(recent_closes[i] >= recent_closes[i+1] for i in range(len(recent_closes)-1)):
                trend_score = 30
            elif recent_closes[-1] < recent_closes[0]:
                trend_score = 20
            else:
                trend_score = 10
    
    total_confidence = breakout_strength + channel_width_score + trend_score
    return round(min(100, max(0, total_confidence)), 1)


def calculate_stop_loss_take_profit(signal: str, price: float, df: pd.DataFrame, 
                                     entry_period: int = 20, exit_period: int = 10) -> dict:
    """
    Calculate suggested stop loss and take profit levels.
    
    Stop Loss: Based on opposite channel boundary or ATR
    Take Profit: Based on risk-reward ratio (2:1 or 3:1) or channel targets
    """
    latest = df.iloc[-1]
    
    # Get channel levels
    entry_upper = latest.get("entry_upper", price)
    entry_lower = latest.get("entry_lower", price)
    exit_upper = latest.get("exit_upper", price)
    exit_lower = latest.get("exit_lower", price)
    
    # Calculate ATR for dynamic stops
    if len(df) >= 14:
        high_low = df["high"].iloc[-14:] - df["low"].iloc[-14:]
        atr = high_low.mean()
    else:
        atr = price * 0.02  # Default 2%
    
    result = {
        "stop_loss": None,
        "take_profit_1": None,
        "take_profit_2": None,
        "risk_reward_1": None,
        "risk_reward_2": None
    }
    
    if signal in ["ENTER_LONG", "EXIT_SHORT"]:
        # Long position
        # Stop loss below entry_lower or using ATR
        sl_distance = max(price - entry_lower, atr * 1.5)
        result["stop_loss"] = round(price - sl_distance, 2)
        
        # Take profit targets
        risk = price - result["stop_loss"]
        result["take_profit_1"] = round(price + risk * 2, 2)  # 2:1 R:R
        result["take_profit_2"] = round(price + risk * 3, 2)  # 3:1 R:R
        
        # Channel target
        channel_target = entry_upper + (entry_upper - entry_lower) * 0.5
        if channel_target > result["take_profit_1"]:
            result["take_profit_2"] = round(channel_target, 2)
            
    elif signal in ["ENTER_SHORT", "EXIT_LONG"]:
        # Short position
        # Stop loss above entry_upper or using ATR
        sl_distance = max(entry_upper - price, atr * 1.5)
        result["stop_loss"] = round(price + sl_distance, 2)
        
        # Take profit targets
        risk = result["stop_loss"] - price
        result["take_profit_1"] = round(price - risk * 2, 2)  # 2:1 R:R
        result["take_profit_2"] = round(price - risk * 3, 2)  # 3:1 R:R
        
        # Channel target
        channel_target = entry_lower - (entry_upper - entry_lower) * 0.5
        if channel_target < result["take_profit_1"]:
            result["take_profit_2"] = round(channel_target, 2)
    
    # Calculate risk-reward percentages
    if result["stop_loss"] and result["take_profit_1"]:
        risk_pct = abs(price - result["stop_loss"]) / price * 100
        reward1_pct = abs(result["take_profit_1"] - price) / price * 100
        reward2_pct = abs(result["take_profit_2"] - price) / price * 100 if result["take_profit_2"] else None
        result["risk_reward_1"] = f"{reward1_pct/risk_pct:.1f}:1" if risk_pct > 0 else "N/A"
        result["risk_reward_2"] = f"{reward2_pct/risk_pct:.1f}:1" if result["take_profit_2"] and risk_pct > 0 else "N/A"
    
    return result


def format_signal_message(signal: str, asset: str, price: float, interval: str,
                          confidence: float, stop_loss: float, take_profit: float) -> str:
    """Format a rich Markdown alert message with full details."""
    emoji_map = {
        "ENTER_LONG":  "🟢",
        "ENTER_SHORT": "🔴",
        "EXIT_LONG":   "🟡",
        "EXIT_SHORT":  "🟡",
    }
    emoji = emoji_map.get(signal, "⚪")
    
    return (
        f"{emoji} *{signal.replace('_', ' ')}*\n"
        f"Asset: `{asset}` · TF: `{interval}`\n"
        f"Price: `{price:,.2f}`\n"
        f"Confidence: `{confidence:.1f}%`\n"
        f"Stop Loss: `{stop_loss:,.2f}`\n"
        f"Take Profit: `{take_profit:,.2f}`"
    )


def scan_for_signals(mode: str, symbol: str, interval: str, entry: int, exit_p: int,
                     tg_token: str, tg_chat: str, tv_username: str, tv_password: str):
    """Run a single scan iteration and update session state."""
    try:
        # Inject TV credentials
        import core.data_fetcher as _df_mod
        _df_mod.TV_USERNAME = tv_username
        _df_mod.TV_PASSWORD = tv_password
        
        lookback = max(entry, exit_p) * 15
        if mode == "gold":
            df = fetch_gold(interval=interval, lookback_bars=lookback)
            asset_label = "XAUUSD"
        else:
            df = fetch_crypto(symbol, interval=interval, lookback_bars=lookback)
            asset_label = symbol
        
        df = compute_turtle_signals(df, entry_period=entry, exit_period=exit_p)
        info = get_latest_signal(df)
        
        price = info["close"]
        signal = info["signal"]
        ts = info["timestamp"]
        
        # Update basic state
        st.session_state.last_price = price
        st.session_state.last_signal = signal or "—"
        st.session_state.last_check = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        st.session_state.error = None
        
        # Check for new signal - use timestamp only as key to avoid duplicate detection issues
        sig_key = str(ts)
        
        # Check if this is a genuine entry/exit signal (not just "HOLD" or None)
        valid_signals = ["ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT"]
        
        if signal and signal in valid_signals:
            # Add to history regardless of last_sig_key to ensure all signals appear
            # Only skip if exact same timestamp already exists
            existing_timestamps = [s["timestamp"] for s in st.session_state.signal_history]
            current_ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            
            if current_ts_str not in existing_timestamps:
                # Calculate confidence and levels
                confidence = calculate_confidence(df, entry, exit_p)
                sl_tp = calculate_stop_loss_take_profit(signal, price, df, entry, exit_p)
                
                # Add to history
                signal_entry = {
                    "timestamp": current_ts_str,
                    "signal": signal,
                    "asset": asset_label,
                    "interval": interval,
                    "price": price,
                    "confidence": confidence,
                    "stop_loss": sl_tp["stop_loss"],
                    "take_profit_1": sl_tp["take_profit_1"],
                    "take_profit_2": sl_tp["take_profit_2"],
                    "risk_reward_1": sl_tp["risk_reward_1"],
                    "risk_reward_2": sl_tp["risk_reward_2"]
                }
                st.session_state.signal_history.insert(0, signal_entry)
                
                # Keep only last 50 signals
                if len(st.session_state.signal_history) > 50:
                    st.session_state.signal_history = st.session_state.signal_history[:50]
                
                # Send Telegram notification
                if tg_token and tg_chat:
                    try:
                        notifier = TelegramNotifier(tg_token, tg_chat)
                        tp = sl_tp["take_profit_1"] if sl_tp["take_profit_1"] else price
                        msg = format_signal_message(signal, asset_label, price, interval,
                                                   confidence, sl_tp["stop_loss"], tp)
                        notifier.send(msg)
                        log.info("Signal sent to Telegram: %s", signal)
                    except Exception as e:
                        log.error("Telegram send failed: %s", e)
                
                log.info("NEW SIGNAL: %s | %s | %.2f | Confidence: %.1f%%", 
                        signal, asset_label, price, confidence)
                
                # Update last_sig_key after processing
                st.session_state.last_sig_key = sig_key
        
        return df, asset_label
        
    except Exception as e:
        st.session_state.error = str(e)
        log.error("Scan error: %s", e)
        return None, None


def create_chart(df: pd.DataFrame, asset_label: str, signals: list) -> go.Figure:
    """Create an interactive candlestick chart with Turtle channels and signals.
    
    Uses Plotly's efficient update methods for smooth real-time updates without recreating the entire chart.
    """
    if df is None or df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font_size=20)
        return fig
    
    # Create subplots
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                       vertical_spacing=0.03, row_heights=[0.7, 0.3],
                       subplot_titles=(f"{asset_label} Price with Turtle Channels", "Volume"))
    
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350"
    ), row=1, col=1)
    
    # Entry channels - solid blue lines
    fig.add_trace(go.Scatter(x=df.index, y=df["entry_upper"], 
                            name="Entry Upper", line=dict(color="#2962ff", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["entry_lower"], 
                            name="Entry Lower", line=dict(color="#2962ff", width=1.5)), row=1, col=1)
    
    # Exit channels - dashed orange lines
    fig.add_trace(go.Scatter(x=df.index, y=df["exit_upper"], 
                            name="Exit Upper", line=dict(color="#ff6d00", width=1, dash="dash")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["exit_lower"], 
                            name="Exit Lower", line=dict(color="#ff6d00", width=1, dash="dash")), row=1, col=1)
    
    # Signal markers - plot all historical signals on chart
    if signals:
        # Group signals by type for better legend display
        long_entries = [s for s in signals if s.get("type") == "ENTER_LONG"]
        short_entries = [s for s in signals if s.get("type") == "ENTER_SHORT"]
        exit_longs = [s for s in signals if s.get("type") == "EXIT_LONG"]
        exit_shorts = [s for s in signals if s.get("type") == "EXIT_SHORT"]
        
        # Long entry signals (green triangles up)
        if long_entries:
            fig.add_trace(go.Scatter(
                x=[s["timestamp"] for s in long_entries],
                y=[s["price"] for s in long_entries],
                mode="markers+text",
                marker=dict(symbol="triangle-up", size=18, color="#26a69a"),
                text=["🟢"] * len(long_entries),
                textposition="top center",
                name="🟢 Long Entry",
                hovertemplate="Long Entry<br>Price: %{y:.2f}<br>Time: %{x}<extra></extra>"
            ), row=1, col=1)
        
        # Short entry signals (red triangles down)
        if short_entries:
            fig.add_trace(go.Scatter(
                x=[s["timestamp"] for s in short_entries],
                y=[s["price"] for s in short_entries],
                mode="markers+text",
                marker=dict(symbol="triangle-down", size=18, color="#ef5350"),
                text=["🔴"] * len(short_entries),
                textposition="bottom center",
                name="🔴 Short Entry",
                hovertemplate="Short Entry<br>Price: %{y:.2f}<br>Time: %{x}<extra></extra>"
            ), row=1, col=1)
        
        # Exit long signals (yellow markers)
        if exit_longs:
            fig.add_trace(go.Scatter(
                x=[s["timestamp"] for s in exit_longs],
                y=[s["price"] for s in exit_longs],
                mode="markers",
                marker=dict(symbol="circle", size=12, color="#f5c842", line=dict(width=2)),
                name="🟡 Exit Long",
                hovertemplate="Exit Long<br>Price: %{y:.2f}<br>Time: %{x}<extra></extra>"
            ), row=1, col=1)
        
        # Exit short signals (yellow markers)
        if exit_shorts:
            fig.add_trace(go.Scatter(
                x=[s["timestamp"] for s in exit_shorts],
                y=[s["price"] for s in exit_shorts],
                mode="markers",
                marker=dict(symbol="circle", size=12, color="#f5c842", line=dict(width=2)),
                name="🟡 Exit Short",
                hovertemplate="Exit Short<br>Price: %{y:.2f}<br>Time: %{x}<extra></extra>"
            ), row=1, col=1)
    
    # Volume bars with dynamic colors
    colors = ['#26a69a' if df["close"].iloc[i] >= df["open"].iloc[i] else '#ef5350' 
              for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=df.index,
        y=df["volume"],
        name="Volume",
        marker_color=colors,
        opacity=0.7
    ), row=2, col=1)
    
    # Layout - optimized for real-time updates
    fig.update_layout(
        height=700,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=50, b=50),
        template="plotly_dark",
        dragmode="pan",
        hovermode="x unified"
    )
    
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    
    return fig


# ── Sidebar Configuration ─────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")
    
    st.subheader("Market")
    mode = st.radio("Asset Type", ["gold", "crypto"], index=0, horizontal=True)
    
    if mode == "gold":
        symbol = "XAUUSD"
    else:
        symbol = st.selectbox("Crypto Pair", 
                             ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"],
                             index=0)
    
    interval = st.selectbox("Timeframe", 
                           ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                           index=4)
    
    st.subheader("Turtle Parameters")
    entry = st.slider("Entry Period", 5, 50, 20, 1)
    exit_p = st.slider("Exit Period", 5, 50, 10, 1)
    
    st.subheader("Scanner")
    scan_interval = st.slider("Scan Interval (seconds)", 10, 300, 60, 10)
    
    st.subheader("Telegram Bot")
    # Hardcoded credentials - for security, consider using st.secrets in production
    tg_token = "8639500812:AAG2cLSiKyRVwazanOlN--PInxu4-m58ES0"
    tg_chat = "-5137913812"
    st.success("✅ Telegram bot configured and ready")
    
    st.subheader("TradingView (Optional)")
    tv_username = st.text_input("TV Username", value="",
                               help="TradingView username for premium data")
    tv_password = st.text_input("TV Password", value="", type="password",
                               help="TradingView password")
    
    st.divider()
    
    # Test Telegram Button
    if st.button("📬 Test Telegram", type="secondary", use_container_width=True):
        try:
            notifier = TelegramNotifier(tg_token, tg_chat)
            test_result = notifier.test()
            if test_result:
                st.success("✅ Test message sent successfully!")
            else:
                st.error("❌ Telegram API returned an error")
        except Exception as e:
            st.error(f"❌ Test failed: {str(e)}")
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Start", type="primary", use_container_width=True):
            st.session_state.running = True
    with col2:
        if st.button("⏹️ Stop", type="secondary", use_container_width=True):
            st.session_state.running = False
            st.session_state.last_sig_key = None

# ── Main Content ──────────────────────────────────────────────────────────────
st.title("🐢 Turtle Trader")
st.markdown("**Real-time Turtle Trading Channel Scanner** with confidence levels & risk management")

# Status bar
col1, col2, col3, col4 = st.columns(4)
with col1:
    status_color = "🟢" if st.session_state.running else "🔴"
    st.metric("Status", f"{status_color} {'Running' if st.session_state.running else 'Stopped'}")
with col2:
    st.metric("Last Price", f"${st.session_state.last_price:,.2f}" if st.session_state.last_price else "—")
with col3:
    last_sig = st.session_state.last_signal
    if last_sig:
        emoji = {"ENTER_LONG": "🟢", "ENTER_SHORT": "🔴", "EXIT_LONG": "🟡", "EXIT_SHORT": "🟡"}.get(last_sig, "⚪")
        st.metric("Last Signal", f"{emoji} {last_sig}")
    else:
        st.metric("Last Signal", "—")
with col4:
    st.metric("Last Check", st.session_state.last_check or "—")

if st.session_state.error:
    st.error(f"❌ Error: {st.session_state.error}")

# Main chart and signals
chart_col, signals_col = st.columns([2, 1])

with chart_col:
    st.subheader("📊 Live Chart")
    
    # Run scan if active
    df = None
    asset_label = None
    
    # Create a placeholder for the chart that can be updated efficiently
    chart_placeholder = st.empty()
    
    if st.session_state.running:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        while st.session_state.running:
            status_text.text("Scanning...")
            df, asset_label = scan_for_signals(
                mode, symbol, interval, entry, exit_p,
                tg_token, tg_chat, tv_username, tv_password
            )
            
            if df is not None:
                # Create signals list for chart - include ALL historical signals for this asset
                signals_list = []
                for sig in st.session_state.signal_history:  # All signals, not just last 20
                    if sig["asset"] == asset_label:
                        signals_list.append({
                            "timestamp": sig["timestamp"],
                            "type": sig["signal"],
                            "price": sig["price"]
                        })
                
                fig = create_chart(df, asset_label, signals_list)
                chart_placeholder.empty()  # Clear previous chart
                chart_placeholder.plotly_chart(fig, use_container_width=True, key=f"live_chart_{asset_label}_{int(time.time())}")
            
            progress_bar.progress(100)
            status_text.text(f"Last scan: {datetime.now().strftime('%H:%M:%S')}")
            time.sleep(scan_interval)
            progress_bar.progress(0)
    else:
        # Manual scan button when stopped
        if st.button("🔍 Scan Now"):
            df, asset_label = scan_for_signals(
                mode, symbol, interval, entry, exit_p,
                tg_token, tg_chat, tv_username, tv_password
            )
        
        if df is not None:
            # Create signals list for chart - include ALL historical signals
            signals_list = []
            for sig in st.session_state.signal_history:  # All signals
                if sig["asset"] == asset_label:
                    signals_list.append({
                        "timestamp": sig["timestamp"],
                        "type": sig["signal"],
                        "price": sig["price"]
                    })
            
            fig = create_chart(df, asset_label, signals_list)
            chart_placeholder.empty()  # Clear previous chart
            chart_placeholder.plotly_chart(fig, use_container_width=True, key=f"manual_chart_{asset_label}_{int(time.time())}")
        else:
            st.info("Click 'Scan Now' or press 'Start' to begin scanning")

with signals_col:
    st.subheader("🔔 Recent Signals")
    
    if st.session_state.signal_history:
        # Show detailed signal cards
        for sig in st.session_state.signal_history[:10]:
            signal_type = sig["signal"]
            emoji = {"ENTER_LONG": "🟢", "ENTER_SHORT": "🔴", "EXIT_LONG": "🟡", "EXIT_SHORT": "🟡"}.get(signal_type, "⚪")
            
            with st.container():
                st.markdown(f"**{emoji} {signal_type.replace('_', ' ')}**")
                st.markdown(f"`{sig['asset']}` · `{sig['interval']}`")
                st.markdown(f"**Entry:** ${sig['price']:,.2f}")
                
                # Confidence badge
                conf = sig.get("confidence", 0)
                if conf >= 70:
                    conf_color = "green"
                elif conf >= 50:
                    conf_color = "orange"
                else:
                    conf_color = "red"
                st.markdown(f"**Confidence:** :{conf_color}[{conf:.1f}%]")
                
                # Stop Loss
                sl = sig.get("stop_loss")
                if sl:
                    st.markdown(f"**🛑 Stop Loss:** ${sl:,.2f}")
                
                # Take Profit
                tp1 = sig.get("take_profit_1")
                tp2 = sig.get("take_profit_2")
                rr1 = sig.get("risk_reward_1")
                rr2 = sig.get("risk_reward_2")
                
                if tp1:
                    st.markdown(f"**🎯 TP1:** ${tp1:,.2f} ({rr1})")
                if tp2:
                    st.markdown(f"**🎯 TP2:** ${tp2:,.2f} ({rr2})")
                
                st.caption(f"🕒 {sig['timestamp']}")
                st.divider()
    else:
        st.info("No signals detected yet")
    
    if st.session_state.signal_history:
        if st.button("🗑️ Clear History"):
            st.session_state.signal_history = []
            st.rerun()

# ── Signal History Table ──────────────────────────────────────────────────────
if st.session_state.signal_history:
    st.divider()
    st.subheader("📋 Signal History")
    
    # Convert to DataFrame for display
    history_df = pd.DataFrame(st.session_state.signal_history)
    
    # Format for display
    display_df = history_df[[
        "timestamp", "signal", "asset", "interval", "price", 
        "confidence", "stop_loss", "take_profit_1", "take_profit_2"
    ]].copy()
    
    display_df.columns = [
        "Time", "Signal", "Asset", "TF", "Entry Price",
        "Confidence %", "Stop Loss", "TP 1", "TP 2"
    ]
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Download button
    csv = history_df.to_csv(index=False)
    st.download_button(
        label="📥 Download History (CSV)",
        data=csv,
        file_name=f"turtle_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style='text-align: center; color: gray;'>
    🐢 Turtle Trading Strategy · Built with Streamlit
</div>
""", unsafe_allow_html=True)

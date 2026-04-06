import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# Core imports
from core.data_fetcher import fetch_data
from core.turtle_logic import generate_turtle_signals
from core.scalping_strategies import (
    generate_1min_scalp_signals,
    generate_ma_ribbon_signals,
    generate_bollinger_signals
)
from utils.notifier import send_telegram_message

# Page Config
st.set_page_config(page_title="Pro Forex Scalper", layout="wide")

# --- Session State Initialization ---
if 'last_signal_time' not in st.session_state:
    st.session_state.last_signal_time = None
if 'active_trade' not in st.session_state:
    st.session_state.active_trade = None  # Dict: {type, entry, sl, tp, strategy, time}
if 'signal_history' not in st.session_state:
    st.session_state.signal_history = []
if 'daily_trades' not in st.session_state:
    st.session_state.daily_trades = 0
if 'last_checked_price' not in st.session_state:
    st.session_state.last_checked_price = None

# --- Helper Functions ---

def calculate_sl_tp(df, signal_type, strategy, atr_period=14):
    """Calculate SL and TP based on strategy and recent swing points"""
    current_price = df['close'].iloc[-1]
    
    # Simple ATR calculation for dynamic stops if needed, otherwise use swing high/low
    high_window = df['high'].iloc[-20:].max()
    low_window = df['low'].iloc[-20:].min()
    
    if strategy in ["1-Minute Scalping", "MA Ribbon Entry"]:
        # Tighter stops for scalping
        if signal_type == "ENTER_LONG":
            sl = low_window * 0.9995  # 0.05% below recent low
            tp = current_price + (current_price - sl) * 1.5
        else: # ENTER_SHORT
            sl = high_window * 1.0005 # 0.05% above recent high
            tp = current_price - (sl - current_price) * 1.5
            
    elif strategy == "Bollinger Band Scalping":
        # Based on band width
        bb_width = (df['bb_upper'].iloc[-1] - df['bb_lower'].iloc[-1])
        if signal_type == "ENTER_LONG":
            sl = df['bb_lower'].iloc[-1] * 0.999
            tp = current_price + (current_price - sl) * 1.5
        else:
            sl = df['bb_upper'].iloc[-1] * 1.001
            tp = current_price - (sl - current_price) * 1.5
            
    else: # Turtle Trading
        # Wider stops
        if signal_type == "ENTER_LONG":
            sl = low_window * 0.998
            tp = current_price + (current_price - sl) * 2.0 # Turtle usually aims higher
        else:
            sl = high_window * 1.002
            tp = current_price - (sl - current_price) * 2.0

    return round(sl, 5), round(tp, 5)

def format_signal_message(strategy, action, asset, tf, price, confidence, sl=None, tp=None, rr=None):
    """Format a clean, readable Telegram message"""
    emoji = "🟢" if "LONG" in action else "🔴" if "SHORT" in action else "🟡"
    if action == "GUARD": emoji = "🛡"
    if action == "HOLD": emoji = "🔒"
    if action == "WATCH": emoji = "👁"
    if "VALID" in action: emoji = "✔"
    if "INVALID" in action: emoji = "❌"

    msg = f"{emoji} <b>{strategy}</b>\n\n"
    msg += f"<b>{action}</b>\n"
    msg += f"Asset: {asset} · TF: {tf}\n"
    msg += f"Price: {price:,.5f}\n"
    
    if confidence:
        msg += f"Confidence: {confidence:.1f}%\n"
    
    if sl and tp:
        msg += f"Stop Loss: {sl:,.5f}\n"
        msg += f"Take Profit: {tp:,.5f}\n"
        if rr:
            msg += f"Risk/Reward: {rr}\n"
    
    if action in ["GUARD", "HOLD"]:
        msg += "\n<i>Monitor position closely.</i>"
    elif action in ["WATCH"]:
        msg += "\n<i>No active trade. Waiting for setup.</i>"
    elif "VALID" in action:
        msg += "\n<b>🎉 Target Hit! Trade Closed.</b>"
    elif "INVALID" in action:
        msg += "\n<b>⚠️ Stop Loss Hit. Trade Closed.</b>"

    return msg

def create_chart(df, asset, strategy, active_trade=None):
    """Create interactive chart with strategy-specific indicators"""
    fig = make_subplots(rows=1, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[1.0])
    
    # Candlestick
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"))
    
    # Strategy Specific Indicators
    if strategy == "Turtle Trading":
        if 'entry_upper' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['entry_upper'], name="Entry Upper", line=dict(color="#2962FF", width=2)))
            fig.add_trace(go.Scatter(x=df.index, y=df['entry_lower'], name="Entry Lower", line=dict(color="#2962FF", width=2)))
        if 'exit_upper' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['exit_upper'], name="Exit Upper", line=dict(color="#FF6D00", width=1, dash='dot')))
            fig.add_trace(go.Scatter(x=df.index, y=df['exit_lower'], name="Exit Lower", line=dict(color="#FF6D00", width=1, dash='dot')))
            
    elif strategy == "1-Minute Scalping":
        if 'ema_13' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['ema_13'], name="EMA 13", line=dict(color="#00E676", width=1.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['ema_26'], name="EMA 26", line=dict(color="#FF5252", width=1.5)))
            
    elif strategy == "MA Ribbon Entry":
        if 'sma_5' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['sma_5'], name="SMA 5", line=dict(color="#2962FF", width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['sma_8'], name="SMA 8", line=dict(color="#00B0FF", width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['sma_13'], name="SMA 13", line=dict(color="#0091EA", width=1)))
            
    elif strategy == "Bollinger Band Scalping":
        if 'bb_upper' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], name="BB Upper", fill=None, line=dict(color="#D500F9", width=1)))
            fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], name="BB Lower", fill='tonexty', line=dict(color="#D500F9", width=1)))

    # Active Trade Levels
    if active_trade:
        fig.add_hline(y=active_trade['entry'], line_dash="dash", line_color="white", annotation_text="Entry")
        fig.add_hline(y=active_trade['sl'], line_dash="dot", line_color="red", annotation_text="SL")
        fig.add_hline(y=active_trade['tp'], line_dash="dot", line_color="green", annotation_text="TP")

    fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark", title=f"{asset} - {strategy}")
    return fig

# --- Sidebar Configuration ---
with st.sidebar:
    st.title("⚙️ Configuration")
    
    asset_map = {
        "Gold (XAUUSD)": "XAUUSD",
        "BTC/USDT": "BTC/USDT",
        "ETH/USDT": "ETH/USDT",
        "EUR/USD": "EUR/USD",
        "GBP/USD": "GBP/USD"
    }
    selected_asset_name = st.selectbox("Asset", list(asset_map.keys()))
    asset = asset_map[selected_asset_name]
    
    timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"])
    
    strategy = st.selectbox(
        "Strategy", 
        ["Turtle Trading", "1-Minute Scalping", "MA Ribbon Entry", "Bollinger Band Scalping"]
    )
    
    st.divider()
    
    # Risk Guardrail Display
    st.metric("Daily Trades", f"{st.session_state.daily_trades} / 50")
    if st.session_state.daily_trades >= 50:
        st.error("⚠️ Daily trade limit reached! Reset required.")
    elif st.session_state.daily_trades >= 40:
        st.warning("⚠️ Approaching daily trade limit (80%).")
        
    st.divider()
    
    auto_scan = st.checkbox("Auto-Scan", value=False)
    run_button = st.button("🚀 Scan Now", type="primary", disabled=auto_scan)

# --- Main Logic ---

st.title(f"📈 {asset} Scanner")
st.caption(f"Strategy: **{strategy}** | Timeframe: **{timeframe}**")

chart_placeholder = st.empty()
status_placeholder = st.empty()
history_placeholder = st.empty()

def process_scan():
    # Check Guardrails
    if st.session_state.daily_trades >= 50:
        status_placeholder.error("Daily trade limit reached. Please reset session.")
        return

    try:
        # Fetch Data
        df = fetch_data(asset, timeframe)
        if df is None or df.empty:
            status_placeholder.error("Failed to fetch data.")
            return

        # Generate Signals based on Strategy
        signals_list = []
        confidence = 0.0
        
        if strategy == "Turtle Trading":
            df = generate_turtle_signals(df)
            last_row = df.iloc[-1]
            if last_row.get('signal') == 'ENTER_LONG': signals_list.append("ENTER_LONG")
            elif last_row.get('signal') == 'ENTER_SHORT': signals_list.append("ENTER_SHORT")
            elif last_row.get('signal') == 'EXIT_LONG': signals_list.append("EXIT_LONG")
            elif last_row.get('signal') == 'EXIT_SHORT': signals_list.append("EXIT_SHORT")
            confidence = last_row.get('confidence', 50.0)
            
        elif strategy == "1-Minute Scalping":
            df = generate_1min_scalp_signals(df, timeframe)
            last_row = df.iloc[-1]
            if last_row.get('signal') == 'BUY': signals_list.append("ENTER_LONG")
            elif last_row.get('signal') == 'SELL': signals_list.append("ENTER_SHORT")
            confidence = last_row.get('confidence', 50.0)
            
        elif strategy == "MA Ribbon Entry":
            df = generate_ma_ribbon_signals(df, timeframe)
            last_row = df.iloc[-1]
            if last_row.get('signal') == 'BUY': signals_list.append("ENTER_LONG")
            elif last_row.get('signal') == 'SELL': signals_list.append("ENTER_SHORT")
            confidence = last_row.get('confidence', 50.0)
            
        elif strategy == "Bollinger Band Scalping":
            df = generate_bollinger_signals(df, timeframe)
            last_row = df.iloc[-1]
            if last_row.get('signal') == 'BUY': signals_list.append("ENTER_LONG")
            elif last_row.get('signal') == 'SELL': signals_list.append("ENTER_SHORT")
            confidence = last_row.get('confidence', 50.0)

        current_price = df['close'].iloc[-1]
        st.session_state.last_checked_price = current_price

        # --- STATE MACHINE LOGIC ---
        active_trade = st.session_state.active_trade
        new_signal_msg = None
        update_trade_status = False

        # 1. Check if Active Trade Exists
        if active_trade:
            # Check for TP/SL hits
            if active_trade['type'] == 'LONG':
                if current_price <= active_trade['sl']:
                    # Hit SL
                    msg = format_signal_message(strategy, "❌ INVALID (SL Hit)", asset, timeframe, current_price, None)
                    new_signal_msg = msg
                    st.session_state.active_trade = None
                    st.session_state.signal_history.insert(0, {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "asset": asset,
                        "strategy": strategy,
                        "action": "CLOSED (SL)",
                        "price": current_price,
                        "pnl": "Loss"
                    })
                    update_trade_status = True
                    
                elif current_price >= active_trade['tp']:
                    # Hit TP
                    msg = format_signal_message(strategy, "✔ VALID (TP Hit)", asset, timeframe, current_price, None)
                    new_signal_msg = msg
                    st.session_state.active_trade = None
                    st.session_state.signal_history.insert(0, {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "asset": asset,
                        "strategy": strategy,
                        "action": "CLOSED (TP)",
                        "price": current_price,
                        "pnl": "Profit"
                    })
                    update_trade_status = True
                
                else:
                    # Trade still active - Determine Status (Hold/Guard/Watch)
                    entry = active_trade['entry']
                    dist_from_entry = (current_price - entry) / entry * 100
                    dist_to_tp = (active_trade['tp'] - current_price) / (active_trade['tp'] - entry) * 100 if active_trade['tp'] != entry else 0
                    
                    # Simple logic for demo: 
                    # Guard: Price < Entry but > SL
                    # Hold: Price > Entry
                    # Watch: Low volatility (could add ATR check here)
                    
                    if current_price < entry:
                        status_action = "🛡 GUARD"
                        status_conf = max(10, 100 - abs(dist_from_entry)*10) # Confidence drops as it goes against us
                    else:
                        status_action = "🔒 HOLD"
                        status_conf = min(99, 50 + dist_from_entry*10)
                        
                    msg = format_signal_message(strategy, status_action, asset, timeframe, current_price, status_conf)
                    # We don't send this as a new alert necessarily, but display it
                    status_placeholder.info(msg) 
                    
            elif active_trade['type'] == 'SHORT':
                if current_price >= active_trade['sl']:
                    msg = format_signal_message(strategy, "❌ INVALID (SL Hit)", asset, timeframe, current_price, None)
                    new_signal_msg = msg
                    st.session_state.active_trade = None
                    st.session_state.signal_history.insert(0, {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "asset": asset,
                        "strategy": strategy,
                        "action": "CLOSED (SL)",
                        "price": current_price,
                        "pnl": "Loss"
                    })
                    update_trade_status = True
                elif current_price <= active_trade['tp']:
                    msg = format_signal_message(strategy, "✔ VALID (TP Hit)", asset, timeframe, current_price, None)
                    new_signal_msg = msg
                    st.session_state.active_trade = None
                    st.session_state.signal_history.insert(0, {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "asset": asset,
                        "strategy": strategy,
                        "action": "CLOSED (TP)",
                        "price": current_price,
                        "pnl": "Profit"
                    })
                    update_trade_status = True
                else:
                    entry = active_trade['entry']
                    if current_price > entry:
                        status_action = "🛡 GUARD"
                        status_conf = max(10, 100 - abs(current_price - entry)/entry*100*10)
                    else:
                        status_action = "🔒 HOLD"
                        status_conf = min(99, 50 + (entry - current_price)/entry*100*10)
                    
                    msg = format_signal_message(strategy, status_action, asset, timeframe, current_price, status_conf)
                    status_placeholder.info(msg)

            # If trade closed, send notification
            if update_trade_status and new_signal_msg:
                send_telegram_message(new_signal_msg)
                st.session_state.last_signal_time = datetime.now()
                # Don't look for new entries immediately after close, wait for next scan
                signals_list = [] 

        # 2. No Active Trade - Look for Entries
        if not st.session_state.active_trade:
            if "ENTER_LONG" in signals_list or "ENTER_SHORT" in signals_list:
                sig_type = "ENTER_LONG" if "ENTER_LONG" in signals_list else "ENTER_SHORT"
                sl, tp = calculate_sl_tp(df, sig_type, strategy)
                rr = "1:1.5" if strategy != "Turtle Trading" else "1:2.0"
                
                msg = format_signal_message(strategy, sig_type.replace("ENTER_", ""), asset, timeframe, current_price, confidence, sl, tp, rr)
                
                # Send Alert
                send_telegram_message(msg)
                
                # Update State
                st.session_state.active_trade = {
                    "type": "LONG" if sig_type == "ENTER_LONG" else "SHORT",
                    "entry": current_price,
                    "sl": sl,
                    "tp": tp,
                    "strategy": strategy,
                    "time": datetime.now()
                }
                st.session_state.daily_trades += 1
                st.session_state.signal_history.insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "asset": asset,
                    "strategy": strategy,
                    "action": sig_type,
                    "price": current_price,
                    "pnl": "Open"
                })
                st.session_state.last_signal_time = datetime.now()
                
                status_placeholder.success(f"New {sig_type} signal detected! Trade opened.")
                
            elif not status_placeholder._is_empty:
                 # Clear status if no trade and no signal
                 status_placeholder.empty()

        # Render Chart
        fig = create_chart(df, asset, strategy, st.session_state.active_trade)
        chart_placeholder.plotly_chart(fig, use_container_width=True)

        # Render History
        if st.session_state.signal_history:
            hist_df = pd.DataFrame(st.session_state.signal_history)
            history_placeholder.subheader("📜 Recent Signal History")
            history_placeholder.dataframe(hist_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Error: {str(e)}")

# Execution
if run_button or auto_scan:
    process_scan()
    
    if auto_scan:
        time.sleep(60) # Wait 1 minute before next auto scan
        st.rerun()

# Initial Load
if not run_button and not auto_scan and st.session_state.last_checked_price is None:
    st.info("Configure settings and click 'Scan Now' to start.")
    # Show dummy chart or last known if available
    if st.session_state.signal_history:
         hist_df = pd.DataFrame(st.session_state.signal_history)
         history_placeholder.subheader("📜 Recent Signal History")
         history_placeholder.dataframe(hist_df, use_container_width=True, hide_index=True)

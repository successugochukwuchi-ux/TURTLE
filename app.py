"""
Turtle Trader — Streamlit App for Community Cloud
Real-time Turtle Trading scanner with confidence levels, stop loss & take profit suggestions.
Now includes Forex Scalping Strategies: 1-Minute, MA Ribbon, Bollinger Bands
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
from core.scalping_strategies import ScalpingStrategies
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
    page_title="🐢 Turtle Trader + Forex Scalping",
    page_icon="📈",
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
# NEW: Daily trade counter for risk guardrail
if "daily_trades" not in st.session_state:
    st.session_state.daily_trades = 0
if "session_date" not in st.session_state:
    st.session_state.session_date = datetime.now().date()
# NEW: Active trade tracking
if "active_trade" not in st.session_state:
    st.session_state.active_trade = None  # Dict with entry info when trade is open
if "trade_status" not in st.session_state:
    st.session_state.trade_status = "NO_TRADE"  # NO_TRADE, IN_TRADE, GUARD, HOLD, WATCH
if "last_market_update" not in st.session_state:
    st.session_state.last_market_update = None
# NEW: User-configurable risk/reward ratio
if "user_rr_ratio" not in st.session_state:
    st.session_state.user_rr_ratio = 1.5  # Default 1:1.5

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


def assess_market_status(active_trade: dict, current_price: float, df: pd.DataFrame) -> tuple:
    """
    Assess the current market status relative to an active trade.
    
    Returns:
        tuple: (status, confidence) where status is one of:
            - "GUARD": Market moving against entry (filter noise, stay vigilant)
            - "HOLD": Market following prediction (hold position)
            - "WATCH": Market shaky/unclear (crosshair candles, no clear movement)
    """
    if not active_trade:
        return "NO_TRADE", 0
    
    entry_price = active_trade["entry_price"]
    entry_type = active_trade["entry_type"]  # ENTER_LONG or ENTER_SHORT
    stop_loss = active_trade["stop_loss"]
    take_profit = active_trade["take_profit"]
    
    # Calculate distance from entry
    if entry_type == "ENTER_LONG":
        price_change_pct = (current_price - entry_price) / entry_price * 100
        is_in_profit = current_price > entry_price
        sl_distance_pct = (entry_price - stop_loss) / entry_price * 100 if stop_loss else 2
        tp_distance_pct = (take_profit - entry_price) / entry_price * 100 if take_profit else 4
    else:  # ENTER_SHORT
        price_change_pct = (entry_price - current_price) / entry_price * 100
        is_in_profit = current_price < entry_price
        sl_distance_pct = (stop_loss - entry_price) / entry_price * 100 if stop_loss else 2
        tp_distance_pct = (entry_price - take_profit) / entry_price * 100 if take_profit else 4
    
    # Check for crosshair/doji candles (indecision)
    if len(df) >= 3:
        recent_candles = df.iloc[-3:]
        body_sizes = abs(recent_candles["close"] - recent_candles["open"])
        candle_ranges = recent_candles["high"] - recent_candles["low"]
        
        # Crosshair detection: small bodies relative to range
        avg_body_ratio = (body_sizes / candle_ranges.replace(0, 0.0001)).mean()
        is_crosshair = avg_body_ratio < 0.3  # Bodies are less than 30% of candle range
    else:
        is_crosshair = False
    
    # Calculate confidence based on price action
    if is_in_profit:
        # In profit - check if trending well
        if price_change_pct >= tp_distance_pct * 0.5:
            confidence = min(95, 70 + (price_change_pct / tp_distance_pct) * 30)
        else:
            confidence = min(85, 60 + (price_change_pct / tp_distance_pct) * 30)
        status = "HOLD"
    else:
        # Against us - check severity
        loss_ratio = abs(price_change_pct) / sl_distance_pct if sl_distance_pct > 0 else 0
        
        if loss_ratio > 0.7:
            # Close to stop loss - high alert
            confidence = max(40, 80 - loss_ratio * 40)
            status = "GUARD"
        elif loss_ratio > 0.3:
            # Moderate move against
            confidence = max(50, 70 - loss_ratio * 30)
            status = "GUARD"
        else:
            # Small pullback - could be noise
            confidence = max(55, 65 - loss_ratio * 20)
            status = "GUARD"
    
    # Override with WATCH if market is indecisive
    if is_crosshair and not is_in_profit:
        status = "WATCH"
        confidence = 50
    
    return status, round(confidence, 1)


def check_trade_exit(active_trade: dict, current_price: float) -> str:
    """
    Check if current price hits TP or SL.
    
    Returns:
        str: "TP_HIT", "SL_HIT", or "NONE"
    """
    if not active_trade:
        return "NONE"
    
    entry_type = active_trade["entry_type"]
    stop_loss = active_trade["stop_loss"]
    take_profit = active_trade["take_profit"]
    
    if entry_type == "ENTER_LONG":
        if take_profit and current_price >= take_profit:
            return "TP_HIT"
        if stop_loss and current_price <= stop_loss:
            return "SL_HIT"
    else:  # ENTER_SHORT
        if take_profit and current_price <= take_profit:
            return "TP_HIT"
        if stop_loss and current_price >= stop_loss:
            return "SL_HIT"
    
    return "NONE"


def calculate_stop_loss_take_profit(signal: str, price: float, df: pd.DataFrame, 
                                     entry_period: int = 20, exit_period: int = 10,
                                     rr_ratio: float = 1.5) -> dict:
    """
    Calculate suggested stop loss and take profit levels.
    
    Stop Loss: Based on opposite channel boundary or ATR
    Take Profit: Based on risk-reward ratio (user-defined or default) or channel targets
    
    Args:
        signal: Entry signal type
        price: Current entry price
        df: DataFrame with OHLC data
        entry_period: Turtle entry period
        exit_period: Turtle exit period
        rr_ratio: Risk/reward ratio multiplier (e.g., 1.5 for 1:1.5, 2.0 for 1:2)
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
        
        # Take profit targets based on user's RR ratio
        risk = price - result["stop_loss"]
        result["take_profit_1"] = round(price + risk * rr_ratio, 2)  # User-defined R:R
        result["take_profit_2"] = round(price + risk * (rr_ratio + 1), 2)  # Higher R:R
        
        # Channel target
        channel_target = entry_upper + (entry_upper - entry_lower) * 0.5
        if channel_target > result["take_profit_1"]:
            result["take_profit_2"] = round(channel_target, 2)
            
    elif signal in ["ENTER_SHORT", "EXIT_LONG"]:
        # Short position
        # Stop loss above entry_upper or using ATR
        sl_distance = max(entry_upper - price, atr * 1.5)
        result["stop_loss"] = round(price + sl_distance, 2)
        
        # Take profit targets based on user's RR ratio
        risk = result["stop_loss"] - price
        result["take_profit_1"] = round(price - risk * rr_ratio, 2)  # User-defined R:R
        result["take_profit_2"] = round(price - risk * (rr_ratio + 1), 2)  # Higher R:R
        
        # Channel target
        channel_target = entry_lower - (entry_upper - entry_lower) * 0.5
        if channel_target < result["take_profit_1"]:
            result["take_profit_2"] = round(channel_target, 2)
    
    # Calculate risk-reward percentages
    if result["stop_loss"] and result["take_profit_1"]:
        risk_pct = abs(price - result["stop_loss"]) / price * 100
        reward1_pct = abs(result["take_profit_1"] - price) / price * 100
        reward2_pct = abs(result["take_profit_2"] - price) / price * 100 if result["take_profit_2"] else None
        result["risk_reward_1"] = f"1:{rr_ratio:.1f}"
        result["risk_reward_2"] = f"1:{rr_ratio + 1:.1f}" if result["take_profit_2"] else "N/A"
    
    return result


def format_signal_message(signal: str, asset: str, price: float, interval: str,
                          confidence: float, stop_loss: float, take_profit: float,
                          rr_ratio: float = 1.5) -> str:
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
        f"Take Profit: `{take_profit:,.2f}`\n"
        f"Risk/Reward: `1:{rr_ratio:.1f}`"
    )


def scan_for_signals(mode: str, symbol: str, interval: str, entry: int, exit_p: int,
                     tg_token: str, tg_chat: str, tv_username: str, tv_password: str,
                     strategy_choice: str = "Turtle Trading"):
    """Run a single scan iteration and update session state.
    
    Supports both Turtle Trading and Forex Scalping strategies.
    Implements proper trade lifecycle management:
    - No new entry if active trade exists
    - Monitor for TP/SL hits
    - Print GUARD/HOLD/WATCH status updates
    """
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
        
        # Run appropriate strategy
        if strategy_choice == "Turtle Trading":
            df = compute_turtle_signals(df, entry_period=entry, exit_period=exit_p)
        else:
            # Use Forex scalping strategies
            df = ScalpingStrategies.run_strategy(df, strategy_choice, interval)
        
        info = get_latest_signal(df)
        
        price = info["close"]
        signal = info["signal"]
        ts = info["timestamp"]
        
        # Update basic state
        st.session_state.last_price = price
        st.session_state.last_check = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        st.session_state.error = None
        
        # ── TRADE MANAGEMENT LOGIC ─────────────────────────────────────────────
        
        # Check if we have an active trade
        active_trade = st.session_state.active_trade
        
        if active_trade:
            # We have an active trade - check for exit conditions first
            exit_result = check_trade_exit(active_trade, price)
            
            if exit_result == "TP_HIT":
                # Take Profit hit - successful trade
                st.session_state.trade_status = "TP_HIT"
                st.session_state.last_market_update = {
                    "type": "TP_HIT",
                    "message": "✔VALID, Congrats",
                    "price": price,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_reason": "Take Profit"
                }
                
                # Update the active trade in history with exit info
                for hist_entry in reversed(st.session_state.signal_history):
                    if (hist_entry.get("entry_price") == active_trade["entry_price"] and 
                        hist_entry.get("status") == "OPEN"):
                        hist_entry["status"] = "CLOSED"
                        hist_entry["exit_price"] = price
                        hist_entry["exit_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        hist_entry["exit_reason"] = "Take Profit"
                        hist_entry["pnl"] = (price - active_trade["entry_price"]) / active_trade["entry_price"] * 100
                        if active_trade["entry_type"] == "ENTER_SHORT":
                            hist_entry["pnl"] = -hist_entry["pnl"]
                        break
                
                # Clear active trade
                st.session_state.active_trade = None
                log.info(f"TP HIT for {active_trade['entry_type']} at {price}. Profit!")
                
            elif exit_result == "SL_HIT":
                # Stop Loss hit - failed trade
                st.session_state.trade_status = "SL_HIT"
                st.session_state.last_market_update = {
                    "type": "SL_HIT",
                    "message": "❌INVALID, Sorry for that",
                    "price": price,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_reason": "Stop Loss"
                }
                
                # Update the active trade in history with exit info
                for hist_entry in reversed(st.session_state.signal_history):
                    if (hist_entry.get("entry_price") == active_trade["entry_price"] and 
                        hist_entry.get("status") == "OPEN"):
                        hist_entry["status"] = "CLOSED"
                        hist_entry["exit_price"] = price
                        hist_entry["exit_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        hist_entry["exit_reason"] = "Stop Loss"
                        hist_entry["pnl"] = (price - active_trade["entry_price"]) / active_trade["entry_price"] * 100
                        if active_trade["entry_type"] == "ENTER_SHORT":
                            hist_entry["pnl"] = -hist_entry["pnl"]
                        break
                
                # Clear active trade
                st.session_state.active_trade = None
                log.info(f"SL HIT for {active_trade['entry_type']} at {price}. Loss.")
                
            else:
                # No exit - assess market status (GUARD/HOLD/WATCH)
                status, confidence = assess_market_status(active_trade, price, df)
                st.session_state.trade_status = status
                
                emoji_map = {"GUARD": "🛡", "HOLD": "🔒", "WATCH": "👁"}
                st.session_state.last_market_update = {
                    "type": status,
                    "message": f"{emoji_map.get(status, '•')} {status}",
                    "confidence": confidence,
                    "price": price,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "unrealized_pnl": calculate_unrealized_pnl(active_trade, price)
                }
            
            # NO NEW ENTRY SIGNALS while trade is active
            st.session_state.last_signal = f"Holding {active_trade['entry_type']}"
            
        else:
            # No active trade - check for new entry signals
            st.session_state.trade_status = "NO_TRADE"
            st.session_state.last_market_update = None
            
            valid_entry_signals = ["ENTER_LONG", "ENTER_SHORT"]
            
            if signal and signal in valid_entry_signals:
                # New entry signal detected!
                existing_timestamps = [s.get("timestamp") for s in st.session_state.signal_history]
                current_ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
                
                # Only process if not already recorded
                if current_ts_str not in existing_timestamps:
                    # Get user's RR ratio from session state
                    user_rr = st.session_state.user_rr_ratio
                    
                    # Calculate confidence and levels based on strategy
                    if strategy_choice == "Turtle Trading":
                        confidence = calculate_confidence(df, entry, exit_p)
                        sl_tp = calculate_stop_loss_take_profit(signal, price, df, entry, exit_p, rr_ratio=user_rr)
                    else:
                        confidence = 75.0
                        sl_tp = ScalpingStrategies.calculate_stop_loss_take_profit(
                            signal, price, df, strategy_choice, rr_ratio=user_rr
                        )
                    
                    # Get TP and SL values
                    stop_loss = sl_tp.get("stop_loss")
                    take_profit = sl_tp.get("take_profit_1") or sl_tp.get("take_profit")
                    risk_reward = sl_tp.get("risk_reward_1") or sl_tp.get("risk_reward", f"1:{user_rr:.1f}")
                    
                    # Create active trade record
                    st.session_state.active_trade = {
                        "entry_type": signal,
                        "entry_price": price,
                        "entry_time": current_ts_str,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "strategy": strategy_choice,
                        "asset": asset_label,
                        "interval": interval,
                        "initial_confidence": confidence
                    }
                    
                    st.session_state.trade_status = "IN_TRADE"
                    st.session_state.last_signal = signal
                    
                    # Add to signal history
                    signal_entry = {
                        "timestamp": current_ts_str,
                        "signal": signal,
                        "asset": asset_label,
                        "interval": interval,
                        "price": price,
                        "entry_price": price,
                        "confidence": confidence,
                        "strategy": strategy_choice,
                        "stop_loss": stop_loss,
                        "take_profit_1": take_profit,
                        "take_profit_2": sl_tp.get("take_profit_2"),
                        "risk_reward_1": risk_reward,
                        "risk_reward_2": sl_tp.get("risk_reward_2"),
                        "status": "OPEN",
                        "exit_price": None,
                        "exit_time": None,
                        "exit_reason": None,
                        "pnl": None
                    }
                    st.session_state.signal_history.insert(0, signal_entry)
                    
                    # Keep only last 50 signals
                    if len(st.session_state.signal_history) > 50:
                        st.session_state.signal_history = st.session_state.signal_history[:50]
                    
                    # Increment daily trade counter
                    st.session_state.daily_trades += 1
                    
                    # Send Telegram notification
                    if tg_token and tg_chat:
                        try:
                            notifier = TelegramNotifier(tg_token, tg_chat)
                            msg = format_scalping_signal_message(
                                strategy_choice, signal, asset_label, price, interval,
                                confidence, stop_loss or price * 0.99, take_profit or price * 1.02,
                                rr_ratio=user_rr
                            )
                            notifier.send(msg)
                            log.info("Entry signal sent to Telegram: %s | %s", strategy_choice, signal)
                        except Exception as e:
                            log.error("Telegram send failed: %s", e)
                    
                    log.info("NEW ENTRY: %s | %s | %s | %.2f | Confidence: %.1f%%", 
                            strategy_choice, signal, asset_label, price, confidence)
            
            elif signal and signal in ["EXIT_LONG", "EXIT_SHORT"]:
                # Exit signal without entry - just log it, don't create trade
                st.session_state.last_signal = f"{signal} (no active position)"
        
        return df, asset_label
        
    except Exception as e:
        st.session_state.error = str(e)
        log.error("Scan error: %s", e)
        return None, None


def calculate_unrealized_pnl(active_trade: dict, current_price: float) -> float:
    """Calculate unrealized PnL percentage for active trade."""
    if not active_trade:
        return 0.0
    
    entry_price = active_trade["entry_price"]
    entry_type = active_trade["entry_type"]
    
    if entry_type == "ENTER_LONG":
        pnl = (current_price - entry_price) / entry_price * 100
    else:
        pnl = (entry_price - current_price) / entry_price * 100
    
    return round(pnl, 2)


def format_scalping_signal_message(strategy: str, signal: str, asset: str, price: float, 
                                   interval: str, confidence: float, stop_loss: float, 
                                   take_profit: float, rr_ratio: float = 1.5) -> str:
    """Format a rich Markdown alert message for scalping strategies with full details."""
    emoji_map = {
        "ENTER_LONG":  "🟢",
        "ENTER_SHORT": "🔴",
        "EXIT_LONG":   "🟡",
        "EXIT_SHORT":  "🟡",
    }
    emoji = emoji_map.get(signal, "⚪")
    
    # Strategy icon
    strategy_icon = {
        "1-Minute Scalping": "⚡",
        "MA Ribbon Entry": "🎗️",
        "Bollinger Band Scalping": "📊",
        "Turtle Trading": "🐢",
    }.get(strategy, "📈")
    
    return (
        f"{emoji} {strategy_icon} *{strategy}*\n\n"
        f"{emoji} *{signal.replace('_', ' ')}*\n"
        f"Asset: `{asset}` · TF: `{interval}`\n"
        f"Price: `{price:,.5f}`\n"
        f"Confidence: `{confidence:.1f}%`\n"
        f"Stop Loss: `{stop_loss:,.5f}`\n"
        f"Take Profit: `{take_profit:,.5f}`\n"
        f"Risk/Reward: `1:{rr_ratio:.1f}`"
    )


def create_chart(df: pd.DataFrame, asset_label: str, signals: list, strategy_name: str = "Turtle Trading") -> go.Figure:
    """Create an interactive candlestick chart with channels and signals.
    
    Uses Plotly's efficient update methods for smooth real-time updates without recreating the entire chart.
    Adapts visualization based on the selected strategy.
    """
    if df is None or df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font_size=20)
        return fig
    
    # Create subplots
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                       vertical_spacing=0.03, row_heights=[0.7, 0.3],
                       subplot_titles=(f"{asset_label} Price Chart", "Volume"))
    
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
    
    # Add strategy-specific indicators
    if strategy_name == "Turtle Trading":
        # Entry channels - solid blue lines
        if "entry_upper" in df.columns and "entry_lower" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["entry_upper"], 
                                    name="Entry Upper", line=dict(color="#2962ff", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["entry_lower"], 
                                    name="Entry Lower", line=dict(color="#2962ff", width=1.5)), row=1, col=1)
            
            # Exit channels - dashed orange lines
            if "exit_upper" in df.columns and "exit_lower" in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df["exit_upper"], 
                                        name="Exit Upper", line=dict(color="#ff6d00", width=1, dash="dash")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df["exit_lower"], 
                                        name="Exit Lower", line=dict(color="#ff6d00", width=1, dash="dash")), row=1, col=1)
    elif strategy_name == "1-Minute Scalping":
        # EMA lines
        if "ema_13" in df.columns and "ema_26" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["ema_13"], 
                                    name="EMA 13", line=dict(color="#2962ff", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["ema_26"], 
                                    name="EMA 26", line=dict(color="#ff6d00", width=1.5)), row=1, col=1)
    elif strategy_name == "MA Ribbon Entry":
        # SMA ribbon
        if "sma_5" in df.columns and "sma_8" in df.columns and "sma_13" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["sma_5"], 
                                    name="SMA 5", line=dict(color="#2962ff", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["sma_8"], 
                                    name="SMA 8", line=dict(color="#ff6d00", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["sma_13"], 
                                    name="SMA 13", line=dict(color="#00c853", width=1.5)), row=1, col=1)
    elif strategy_name == "Bollinger Band Scalping":
        # Bollinger Bands
        if "bb_upper" in df.columns and "bb_lower" in df.columns and "bb_middle" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], 
                                    name="BB Upper", line=dict(color="#ff5252", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_middle"], 
                                    name="BB Middle", line=dict(color="#bdbdbd", width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], 
                                    name="BB Lower", line=dict(color="#448aff", width=1.5)), row=1, col=1)
    
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
    
    # NEW: Strategy Selection
    st.subheader("📊 Strategy Selection")
    strategy_choice = st.selectbox(
        "Choose Strategy",
        ["Turtle Trading", "1-Minute Scalping", "MA Ribbon Entry", "Bollinger Band Scalping"],
        index=0,
        help="Select your trading strategy. Each has optimized parameters for different timeframes."
    )
    
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
    
    # Show strategy-specific parameters
    if strategy_choice == "Turtle Trading":
        st.subheader("Turtle Parameters")
        entry = st.slider("Entry Period", 5, 50, 20, 1)
        exit_p = st.slider("Exit Period", 5, 50, 10, 1)
    elif strategy_choice == "1-Minute Scalping":
        st.subheader("EMA + Stochastic Parameters")
        st.info("Uses 13 & 26 EMA + Stochastic (14,3,3)\n\nOptimized levels for timeframe:")
        if interval in ['5m', '15m']:
            st.success("Stochastic levels: 25/75 (tightened)")
        elif interval in ['30m', '1h']:
            st.success("Stochastic levels: 30/70 (tightened)")
        elif interval in ['4h', '1d']:
            st.success("Stochastic levels: 35/65 (tightened)")
        entry = 20  # Default for lookback
        exit_p = 10
    elif strategy_choice == "MA Ribbon Entry":
        st.subheader("MA Ribbon Parameters")
        st.info("Uses 5, 8, 13 SMA ribbon\n\nBuy when ribbon fans bullish + pullback to 5/8 SMA")
        entry = 15
        exit_p = 10
    elif strategy_choice == "Bollinger Band Scalping":
        st.subheader("Bollinger Band Parameters")
        st.info("Uses 20 SMA ± 2 StdDev\n\nBuy when price pierces band & closes back inside")
        if interval in ['30m', '1h']:
            st.success("Band width: 2.2 StdDev (wider)")
        elif interval in ['4h', '1d']:
            st.success("Band width: 2.5 StdDev (wider)")
        entry = 20
        exit_p = 10
    
    # Risk/Reward Ratio Configuration
    st.subheader("💰 Risk Management")
    
    # Define optimal RR ratios for each strategy/timeframe combination
    optimal_rr_map = {
        "Turtle Trading": {"1m": 1.5, "5m": 2.0, "15m": 2.0, "30m": 2.5, "1h": 2.5, "4h": 3.0, "1d": 3.0},
        "1-Minute Scalping": {"1m": 1.5, "5m": 1.5, "15m": 2.0, "30m": 2.0, "1h": 2.5, "4h": 2.5, "1d": 3.0},
        "MA Ribbon Entry": {"1m": 1.5, "5m": 2.0, "15m": 2.0, "30m": 2.5, "1h": 2.5, "4h": 3.0, "1d": 3.0},
        "Bollinger Band Scalping": {"1m": 1.5, "5m": 1.5, "15m": 2.0, "30m": 2.0, "1h": 2.5, "4h": 2.5, "1d": 3.0}
    }
    
    default_rr = optimal_rr_map.get(strategy_choice, {}).get(interval, 2.0)
    
    st.caption(f"📊 Optimal R:R for {strategy_choice} on {interval}: **1:{default_rr:.1f}**")
    
    user_rr_ratio = st.number_input(
        "Risk/Reward Ratio (1:X)",
        min_value=1.0,
        max_value=5.0,
        value=st.session_state.user_rr_ratio,
        step=0.1,
        help="Set your desired risk/reward ratio. The optimal ratio for your strategy and timeframe is shown above."
    )
    
    # Update session state with user's RR ratio
    st.session_state.user_rr_ratio = user_rr_ratio
    
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
    
    # Test Signal Button - generates a fake signal with user's settings
    if st.button("🧪 Test Signal", type="secondary", use_container_width=True):
        try:
            # Generate a fake signal with all user settings
            fake_price = 2000.00 if mode == "gold" else 50000.00
            fake_sl = fake_price * 0.98
            fake_tp = fake_price + (fake_price - fake_sl) * st.session_state.user_rr_ratio
            fake_confidence = 75.0
            
            # Create fake signal message
            if strategy_choice == "Turtle Trading":
                msg = format_signal_message(
                    "ENTER_LONG", 
                    symbol if mode == "crypto" else "XAUUSD", 
                    fake_price, 
                    interval,
                    fake_confidence,
                    fake_sl,
                    fake_tp,
                    rr_ratio=st.session_state.user_rr_ratio
                )
            else:
                msg = format_scalping_signal_message(
                    strategy_choice,
                    "ENTER_LONG",
                    symbol if mode == "crypto" else "XAUUSD",
                    fake_price,
                    interval,
                    fake_confidence,
                    fake_sl,
                    fake_tp,
                    rr_ratio=st.session_state.user_rr_ratio
                )
            
            # Send via Telegram
            notifier = TelegramNotifier(tg_token, tg_chat)
            send_result = notifier.send(msg)
            
            if send_result:
                st.success(f"✅ Test signal sent to Telegram!\n\n**Signal Details:**\n- Type: ENTER_LONG\n- Price: {fake_price:.2f}\n- SL: {fake_sl:.2f}\n- TP: {fake_tp:.2f}\n- R:R: 1:{st.session_state.user_rr_ratio:.1f}\n- Strategy: {strategy_choice}")
            else:
                st.error("❌ Failed to send test signal")
        except Exception as e:
            st.error(f"❌ Test signal failed: {str(e)}")
    
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
st.title("🐢 Turtle Trader + Forex Scalping")
st.markdown(f"**Multi-Strategy Scanner**: {strategy_choice} | Real-time signals with confidence levels & risk management")

# NEW: Daily Trade Counter Warning (Risk Guardrail)
today = datetime.now().date()
if st.session_state.session_date != today:
    st.session_state.session_date = today
    st.session_state.daily_trades = 0

MAX_DAILY_TRADES = 50
if st.session_state.daily_trades >= MAX_DAILY_TRADES:
    st.error(f"⚠️ **DAILY TRADE LIMIT REACHED**: You've executed {st.session_state.daily_trades} trades today. Consider stopping to avoid overtrading.")
elif st.session_state.daily_trades >= MAX_DAILY_TRADES * 0.8:
    st.warning(f"⚠️ **Approaching Daily Limit**: {st.session_state.daily_trades}/{MAX_DAILY_TRADES} trades today. Use caution.")
else:
    st.info(f"📊 **Daily Trades**: {st.session_state.daily_trades}/{MAX_DAILY_TRADES}")

# Status bar
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    status_color = "🟢" if st.session_state.running else "🔴"
    st.metric("Status", f"{status_color} {'Running' if st.session_state.running else 'Stopped'}")
with col2:
    st.metric("Last Price", f"${st.session_state.last_price:,.2f}" if st.session_state.last_price else "—")
with col3:
    last_sig = st.session_state.last_signal
    if last_sig:
        # Handle different signal types including holding states
        if "Holding" in last_sig:
            emoji = "🔒"
        else:
            emoji = {"ENTER_LONG": "🟢", "ENTER_SHORT": "🔴", "EXIT_LONG": "🟡", "EXIT_SHORT": "🟡"}.get(last_sig.split()[0], "⚪")
        st.metric("Last Signal", f"{emoji} {last_sig}")
    else:
        st.metric("Last Signal", "—")
with col4:
    st.metric("Last Check", st.session_state.last_check or "—")
with col5:
    # Show trade status instead of just strategy
    trade_status = st.session_state.trade_status
    if trade_status == "NO_TRADE":
        st.metric("Trade Status", "No Trade")
    elif trade_status == "IN_TRADE":
        st.metric("Trade Status", "🔵 In Trade")
    elif trade_status in ["GUARD", "HOLD", "WATCH"]:
        emoji_map = {"GUARD": "🛡", "HOLD": "🔒", "WATCH": "👁"}
        st.metric("Trade Status", f"{emoji_map.get(trade_status)} {trade_status}")
    elif trade_status == "TP_HIT":
        st.metric("Trade Status", "✔ TP Hit")
    elif trade_status == "SL_HIT":
        st.metric("Trade Status", "❌ SL Hit")
    else:
        st.metric("Strategy", strategy_choice.split()[0])

if st.session_state.error:
    st.error(f"❌ Error: {st.session_state.error}")

# ── MARKET STATUS ALERT BOX ────────────────────────────────────────────────────
# Display real-time market status updates (GUARD/HOLD/WATCH/TP/SL)
if st.session_state.last_market_update:
    update = st.session_state.last_market_update
    update_type = update.get("type")
    
    if update_type == "TP_HIT":
        st.success(f"## ✔VALID, Congrats! Take Profit hit at ${update['price']:,.2f}")
        st.json({
            "Exit Reason": update.get("exit_reason"),
            "Exit Time": update.get("timestamp"),
            "Exit Price": f"${update['price']:,.2f}"
        })
    elif update_type == "SL_HIT":
        st.error(f"## ❌INVALID, Sorry for that. Stop Loss hit at ${update['price']:,.2f}")
        st.json({
            "Exit Reason": update.get("exit_reason"),
            "Exit Time": update.get("timestamp"),
            "Exit Price": f"${update['price']:,.2f}"
        })
    elif update_type in ["GUARD", "HOLD", "WATCH"]:
        emoji_map = {"GUARD": "🛡", "HOLD": "🔒", "WATCH": "👁"}
        color_map = {"GUARD": "warning", "HOLD": "info", "WATCH": "secondary"}
        
        with st.container():
            if update_type == "GUARD":
                st.warning(f"### 🛡GUARD - Market moving against entry. Stay vigilant!")
            elif update_type == "HOLD":
                st.info(f"### 🔒HOLD - Market following prediction. Hold position.")
            else:  # WATCH
                st.markdown(f"### 👁WATCH - Market indecisive. No clear movement.")
            
            # Show confidence and PnL
            col_conf, col_pnl = st.columns(2)
            with col_conf:
                conf = update.get("confidence", 0)
                if conf >= 70:
                    st.success(f"**Confidence:** {conf:.1f}%")
                elif conf >= 50:
                    st.warning(f"**Confidence:** {conf:.1f}%")
                else:
                    st.error(f"**Confidence:** {conf:.1f}%")
            with col_pnl:
                pnl = update.get("unrealized_pnl", 0)
                if pnl > 0:
                    st.success(f"**Unrealized PnL:** +{pnl:.2f}%")
                elif pnl < 0:
                    st.error(f"**Unrealized PnL:** {pnl:.2f}%")
                else:
                    st.info(f"**Unrealized PnL:** {pnl:.2f}%")
            
            st.caption(f"Last update: {update.get('timestamp')} | Price: ${update.get('price', 0):,.2f}")

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
                tg_token, tg_chat, tv_username, tv_password,
                strategy_choice
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
                
                fig = create_chart(df, asset_label, signals_list, strategy_choice)
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
                tg_token, tg_chat, tv_username, tv_password,
                strategy_choice
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
            
            fig = create_chart(df, asset_label, signals_list, strategy_choice)
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
    
    # Format for display - include status and exit info
    display_cols = [
        "timestamp", "signal", "asset", "interval", "price", 
        "confidence", "stop_loss", "take_profit_1", "status"
    ]
    
    # Only show columns that exist
    available_cols = [col for col in display_cols if col in history_df.columns]
    display_df = history_df[available_cols].copy()
    
    new_columns = {
        "timestamp": "Time", 
        "signal": "Signal", 
        "asset": "Asset", 
        "interval": "TF", 
        "price": "Entry Price",
        "confidence": "Confidence %", 
        "stop_loss": "Stop Loss", 
        "take_profit_1": "TP 1",
        "status": "Status"
    }
    display_df.rename(columns=new_columns, inplace=True)
    
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

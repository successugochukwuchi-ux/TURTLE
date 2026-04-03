"""
Turtle Trader Discord Bot
A Discord bot for multi-strategy trading signals with confidence levels.
Designed for Kata Bump hosting platform.
"""

import discord
from discord import app_commands
from discord.ext import tasks, commands
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
import asyncio
import io
import zipfile

from core.data_fetcher import fetch_gold, fetch_crypto
from core.strategies import (
    compute_strategy_signals, 
    get_latest_signal, 
    STRATEGIES, 
    get_strategy_params
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Bot Credentials (Hardcoded) ──────────────────────────────────────────────
APPLICATION_ID = 1489598877425205328
PUBLIC_KEY = "1ba152b1466018193d26eda90a5cd547ecd952d50e28f60486927b48c874f448"
# IMPORTANT: Replace with your actual bot token from Discord Developer Portal
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# ── Bot Configuration ────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ── Global State ─────────────────────────────────────────────────────────────
class BotState:
    def __init__(self):
        self.running = False
        self.timeframe = "1h"
        self.instrument = "gold"  # gold or crypto symbol
        self.strategy = "donchian"
        self.strategy_params = {}
        self.check_interval = 60  # seconds
        self.scan_task = None
        self.last_signal = None
        self.last_price = None
        self.signal_history = []
        
state = BotState()

# ── Helper Functions ─────────────────────────────────────────────────────────

def calculate_confidence(df, entry_period: int = 20, exit_period: int = 10) -> float:
    """Calculate confidence level (0-100%) based on multiple factors."""
    if len(df) < max(entry_period, exit_period):
        return 50.0
    
    latest = df.iloc[-1]
    
    # Factor 1: Breakout Strength (0-40 points)
    breakout_strength = 0
    if latest.get("signal") in ["ENTER_LONG", "EXIT_SHORT"]:
        if latest.get("entry_upper") and latest["close"] > latest["entry_upper"]:
            pct_breakout = (latest["close"] - latest["entry_upper"]) / latest["entry_upper"] * 100
            breakout_strength = min(40, pct_breakout * 10)
    elif latest.get("signal") in ["ENTER_SHORT", "EXIT_LONG"]:
        if latest.get("entry_lower") and latest["close"] < latest["entry_lower"]:
            pct_breakout = (latest["entry_lower"] - latest["close"]) / latest["entry_lower"] * 100
            breakout_strength = min(40, pct_breakout * 10)
    
    # Factor 2: Channel Width (0-30 points)
    channel_width_score = 30
    if latest.get("entry_upper") and latest.get("entry_lower"):
        channel_width = (latest["entry_upper"] - latest["entry_lower"]) / latest["entry_lower"] * 100
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
            if all(recent_closes[i] <= recent_closes[i+1] for i in range(len(recent_closes)-1)):
                trend_score = 30
            elif recent_closes[-1] > recent_closes[0]:
                trend_score = 20
            else:
                trend_score = 10
        else:
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
    """Calculate suggested stop loss and take profit levels."""
    latest = df.iloc[-1]
    
    # Exit signals don't need stop loss or take profit
    if signal in ["EXIT_LONG", "EXIT_SHORT"]:
        return {
            "stop_loss": None,
            "take_profit_1": None,
            "take_profit_2": None,
        }
    
    entry_upper = latest.get("entry_upper", price)
    entry_lower = latest.get("entry_lower", price)
    
    if len(df) >= 14:
        high_low = df["high"].iloc[-14:] - df["low"].iloc[-14:]
        atr = high_low.mean()
    else:
        atr = price * 0.02
    
    result = {
        "stop_loss": None,
        "take_profit_1": None,
        "take_profit_2": None,
    }
    
    if signal == "ENTER_LONG":
        sl_distance = max(price - entry_lower, atr * 1.5)
        result["stop_loss"] = round(price - sl_distance, 2)
        risk = price - result["stop_loss"]
        result["take_profit_1"] = round(price + risk * 2, 2)
        result["take_profit_2"] = round(price + risk * 3, 2)
            
    elif signal == "ENTER_SHORT":
        sl_distance = max(entry_upper - price, atr * 1.5)
        result["stop_loss"] = round(price + sl_distance, 2)
        risk = result["stop_loss"] - price
        result["take_profit_1"] = round(price - risk * 2, 2)
        result["take_profit_2"] = round(price - risk * 3, 2)
    
    return result


def format_signal_embed(signal: str, asset: str, price: float, interval: str,
                        confidence: float, sl_tp: dict, strategy_name: str = "") -> discord.Embed:
    """Format a rich embed for signal alerts."""
    emoji_map = {
        "ENTER_LONG": "🟢",
        "ENTER_SHORT": "🔴",
        "EXIT_LONG": "🟡",
        "EXIT_SHORT": "🟡",
    }
    emoji = emoji_map.get(signal, "⚪")
    
    embed = discord.Embed(
        title=f"{emoji} {signal.replace('_', ' ')}",
        color=discord.Color.green() if "LONG" in signal else discord.Color.red() if "SHORT" in signal else discord.Color.yellow()
    )
    
    embed.add_field(name="Strategy", value=f"`{strategy_name}`", inline=True)
    embed.add_field(name="Asset", value=f"`{asset}`", inline=True)
    embed.add_field(name="Timeframe", value=f"`{interval}`", inline=True)
    embed.add_field(name="Price", value=f"`{price:,.2f}`", inline=True)
    embed.add_field(name="Confidence", value=f"`{confidence:.1f}%`", inline=True)
    
    if signal in ["ENTER_LONG", "ENTER_SHORT"]:
        if sl_tp.get("stop_loss"):
            embed.add_field(name="Stop Loss", value=f"`{sl_tp['stop_loss']:,.2f}`", inline=True)
        if sl_tp.get("take_profit_1"):
            embed.add_field(name="Take Profit", value=f"`{sl_tp['take_profit_1']:,.2f}`", inline=True)
    
    embed.set_footer(text=f"Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    return embed


async def scan_loop():
    """Background task to continuously scan for signals."""
    while state.running:
        try:
            await perform_scan()
            await asyncio.sleep(state.check_interval)
        except Exception as e:
            log.error(f"Scan loop error: {e}")
            await asyncio.sleep(state.check_interval)


async def perform_scan(channel=None):
    """Run a single scan iteration."""
    try:
        numeric_params = [v for v in state.strategy_params.values() if isinstance(v, (int, float))]
        max_period = max(numeric_params) if numeric_params else 50
        if max_period < 1:
            max_period = int(50 / max_period) if max_period > 0 else 50
        lookback = int(max_period * 25)
        
        if state.instrument == "gold":
            df = fetch_gold(interval=state.timeframe, lookback_bars=lookback)
            asset_label = "XAUUSD"
        else:
            df = fetch_crypto(state.instrument, interval=state.timeframe, lookback_bars=lookback)
            asset_label = state.instrument
        
        df = compute_strategy_signals(df, strategy=state.strategy, **state.strategy_params)
        info = get_latest_signal(df)
        
        price = info["close"]
        signal = info["signal"]
        
        state.last_price = price
        
        valid_signals = ["ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT"]
        
        if signal and signal in valid_signals:
            # Check if this is a new signal
            current_ts_str = info["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            existing_timestamps = [s["timestamp"] for s in state.signal_history]
            
            if current_ts_str not in existing_timestamps:
                confidence = calculate_confidence(df)
                sl_tp = calculate_stop_loss_take_profit(signal, price, df)
                
                signal_entry = {
                    "timestamp": current_ts_str,
                    "signal": signal,
                    "strategy": STRATEGIES.get(state.strategy, state.strategy),
                    "asset": asset_label,
                    "interval": state.timeframe,
                    "price": price,
                    "confidence": confidence,
                    "stop_loss": sl_tp.get("stop_loss"),
                    "take_profit": sl_tp.get("take_profit_1")
                }
                state.signal_history.insert(0, signal_entry)
                
                # Keep only last 50 signals
                if len(state.signal_history) > 50:
                    state.signal_history = state.signal_history[:50]
                
                # Send notification if channel is provided
                if channel:
                    embed = format_signal_embed(
                        signal, asset_label, price, state.timeframe,
                        confidence, sl_tp, STRATEGIES.get(state.strategy, state.strategy)
                    )
                    await channel.send(embed=embed)
                
                log.info(f"NEW SIGNAL: {signal} | {asset_label} | {price:.2f} | Confidence: {confidence:.1f}%")
        
        return df, asset_label
        
    except Exception as e:
        log.error(f"Scan error: {e}")
        return None, None


# ── Slash Commands ───────────────────────────────────────────────────────────

@bot.tree.command(name="tf", description="Set the timeframe for scanning")
@app_commands.describe(timeframe="Timeframe (e.g., 1m, 5m, 15m, 1h, 4h, 1d)")
async def set_timeframe(interaction: discord.Interaction, timeframe: str):
    """Set the timeframe for scanning."""
    valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1W", "1M"]
    if timeframe not in valid_timeframes:
        await interaction.response.send_message(
            f"Invalid timeframe. Valid options: {', '.join(valid_timeframes)}",
            ephemeral=True
        )
        return
    
    state.timeframe = timeframe
    await interaction.response.send_message(
        f"✅ Timeframe set to `{timeframe}`",
        ephemeral=True
    )


@bot.tree.command(name="scan", description="Start the scanning service")
async def start_scan(interaction: discord.Interaction):
    """Start the clock round service."""
    if state.running:
        await interaction.response.send_message(
            "⚠️ Scanner is already running!",
            ephemeral=True
        )
        return
    
    state.running = True
    channel = interaction.channel
    state.scan_task = bot.loop.create_task(scan_loop())
    
    await interaction.response.send_message(
        f"✅ Scanner started!\n"
        f"Timeframe: `{state.timeframe}`\n"
        f"Instrument: `{state.instrument}`\n"
        f"Strategy: `{STRATEGIES.get(state.strategy, state.strategy)}`\n"
        f"Check Interval: `{state.check_interval}s`",
        ephemeral=False
    )


@bot.tree.command(name="inst", description="Choose what instrument to trade")
@app_commands.describe(instrument="Instrument (gold or crypto symbol like BTCUSDT)")
async def set_instrument(interaction: discord.Interaction, instrument: str):
    """Choose what's being traded."""
    state.instrument = instrument.lower()
    await interaction.response.send_message(
        f"✅ Instrument set to `{instrument}`",
        ephemeral=True
    )


@bot.tree.command(name="strat", description="Choose from available strategies")
@app_commands.describe(
    strategy="Strategy name",
    entry_period="Entry period (for Donchian)",
    exit_period="Exit period (for Donchian)",
    rsi_period="RSI period (for RSI+MACD)",
    macd_fast="MACD fast period",
    macd_slow="MACD slow period",
    macd_signal_period="MACD signal period",
    st_period="SuperTrend period",
    st_multiplier="SuperTrend multiplier",
    threshold="ZigZag threshold",
    bb_period="Bollinger Bands period",
    bb_std_dev="Bollinger Bands std dev",
    ema_fast="Fast EMA period",
    ema_slow="Slow EMA period"
)
async def set_strategy(interaction: discord.Interaction, 
                       strategy: str = "donchian",
                       entry_period: int = 20,
                       exit_period: int = 10,
                       rsi_period: int = 14,
                       macd_fast: int = 12,
                       macd_slow: int = 26,
                       macd_signal_period: int = 9,
                       st_period: int = 10,
                       st_multiplier: float = 3.0,
                       threshold: float = 0.05,
                       bb_period: int = 20,
                       bb_std_dev: float = 2.0,
                       ema_fast: int = 9,
                       ema_slow: int = 21):
    """Choose from available strategies with parameters."""
    valid_strategies = list(STRATEGIES.keys())
    
    if strategy not in valid_strategies:
        await interaction.response.send_message(
            f"Invalid strategy. Valid options: {', '.join(valid_strategies)}",
            ephemeral=True
        )
        return
    
    state.strategy = strategy
    
    # Set strategy parameters based on strategy type
    params = get_strategy_params(strategy)
    state.strategy_params = {}
    
    for param_name, default_value in params.items():
        # Map command arguments to strategy parameters
        if strategy == "donchian":
            state.strategy_params = {"entry_period": entry_period, "exit_period": exit_period}
        elif strategy == "rsi_macd":
            state.strategy_params = {
                "rsi_period": rsi_period,
                "macd_fast": macd_fast,
                "macd_slow": macd_slow,
                "macd_signal": macd_signal_period
            }
        elif strategy == "supertrend":
            state.strategy_params = {"period": st_period, "multiplier": st_multiplier}
        elif strategy == "zigzag":
            state.strategy_params = {"threshold": threshold}
        elif strategy == "bollinger":
            state.strategy_params = {"period": bb_period, "std_dev": bb_std_dev}
        elif strategy == "ema_cross":
            state.strategy_params = {"fast_period": ema_fast, "slow_period": ema_slow}
    
    strategy_display = STRATEGIES.get(strategy, strategy)
    params_str = ", ".join([f"{k}={v}" for k, v in state.strategy_params.items()])
    
    await interaction.response.send_message(
        f"✅ Strategy set to `{strategy_display}`\n"
        f"Parameters: `{params_str}`",
        ephemeral=True
    )


@bot.tree.command(name="end", description="Stop the bot")
async def stop_bot(interaction: discord.Interaction):
    """Stop the bot."""
    if not state.running:
        await interaction.response.send_message(
            "⚠️ Scanner is not running!",
            ephemeral=True
        )
        return
    
    state.running = False
    if state.scan_task:
        state.scan_task.cancel()
        try:
            await state.scan_task
        except asyncio.CancelledError:
            pass
        state.scan_task = None
    
    await interaction.response.send_message(
        "🛑 Scanner stopped!",
        ephemeral=False
    )


@bot.tree.command(name="int", description="Choose the check interval in seconds")
@app_commands.describe(seconds="Check interval in seconds")
async def set_interval(interaction: discord.Interaction, seconds: int):
    """Choose the check interval in seconds."""
    if seconds < 10:
        await interaction.response.send_message(
            "⚠️ Minimum interval is 10 seconds!",
            ephemeral=True
        )
        return
    
    state.check_interval = seconds
    await interaction.response.send_message(
        f"✅ Check interval set to `{seconds}` seconds",
        ephemeral=True
    )


@bot.tree.command(name="status", description="Show current bot status")
async def show_status(interaction: discord.Interaction):
    """Show current bot configuration and status."""
    status = f"""
**🐢 Turtle Trader Status**

Running: `{'✅ Yes' if state.running else '❌ No'}`
Timeframe: `{state.timeframe}`
Instrument: `{state.instrument}`
Strategy: `{STRATEGIES.get(state.strategy, state.strategy)}`
Parameters: `{state.strategy_params}`
Check Interval: `{state.check_interval}s`
Last Price: `{state.last_price}`
Signals Found: `{len(state.signal_history)}`
    """.strip()
    
    await interaction.response.send_message(status, ephemeral=True)


@bot.tree.command(name="history", description="Show recent signal history")
@app_commands.describe(count="Number of signals to show (max 10)")
async def show_history(interaction: discord.Interaction, count: int = 5):
    """Show recent signal history."""
    if not state.signal_history:
        await interaction.response.send_message("No signals found yet.", ephemeral=True)
        return
    
    count = min(count, 10)
    history = state.signal_history[:count]
    
    embed = discord.Embed(title="📊 Recent Signal History", color=discord.Color.blue())
    
    for i, sig in enumerate(history, 1):
        embed.add_field(
            name=f"{i}. {sig['signal']} - {sig['asset']}",
            value=f"Price: `{sig['price']:,.2f}` | TF: `{sig['interval']}`\n"
                  f"Confidence: `{sig['confidence']:.1f}%` | Strat: `{sig['strategy']}`",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        log.error(f"Failed to sync commands: {e}")


# ── Main Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run the bot with the hardcoded token
    # IMPORTANT: Replace BOT_TOKEN with your actual bot token
    bot.run(BOT_TOKEN)

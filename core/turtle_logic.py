"""
Turtle Trading Logic — TUTCI Variant (OKX Signal Bot Compatible)
=================================================================
Translated from Pine Script by KivancOzbilgic - Turtle Trading Channels Indicator

Core Logic:
  Entry Channel (entryLength=20):
    upper = highest(high, entryLength)
    lower = lowest(low, entryLength)
    
  Exit Channel (exitLength=10):
    sup = highest(high, exitLength)
    sdown = lowest(low, exitLength)
  
  Raw Signals:
    buySignal  = high >= upper[1] (breakout above entry channel)
    sellSignal = low <= lower[1]  (breakdown below entry channel)
    buyExit    = low <= sdown[1]  (breakdown below exit channel)
    sellExit   = high >= sup[1]   (breakout above exit channel)
  
  State Machine Filter (critical!):
    ENTER_LONG  = buySignal  AND (barsSince(buyExit) < barsSince(buySignal)[1])
    ENTER_SHORT = sellSignal AND (barsSince(sellExit) < barsSince(sellSignal)[1])
    EXIT_LONG   = buyExit    AND (barsSince(buySignal) < barsSince(buyExit)[1])
    EXIT_SHORT  = sellExit   AND (barsSince(sellSignal) < barsSince(sellExit)[1])
  
  This ensures:
    - Can only ENTER_LONG after an EXIT_LONG occurred more recently than last ENTER_LONG
    - Can only ENTER_SHORT after an EXIT_SHORT occurred more recently than last ENTER_SHORT
    - Can only EXIT_LONG after an ENTER_LONG occurred more recently than last EXIT_LONG
    - Can only EXIT_SHORT after an ENTER_SHORT occurred more recently than last EXIT_SHORT
"""

import pandas as pd
import numpy as np

_SIGNALS = ["ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT"]


def compute_turtle_signals(
    df: pd.DataFrame,
    entry_period: int = 20,
    exit_period: int = 10,
) -> pd.DataFrame:
    """
    Add Turtle Trading channel columns and signal column to `df`.
    
    Implements the exact logic from the Pine Script TUTCI indicator.

    New columns:
        entry_upper     — entry_period highest high
        entry_lower     — entry_period lowest low
        exit_upper      — exit_period highest high
        exit_lower      — exit_period lowest low
        entry_upper_1   — previous bar's entry_upper (for signal comparison)
        entry_lower_1   — previous bar's entry_lower
        exit_upper_1    — previous bar's exit_upper
        exit_lower_1    — previous bar's exit_lower
        signal          — one of SIGNALS or ""
    """
    df = df.copy()

    # Rolling channel values (use high/low of each candle)
    # Entry channel
    df["entry_upper"] = df["high"].rolling(entry_period).max()
    df["entry_lower"] = df["low"].rolling(entry_period).min()
    
    # Exit channel
    df["exit_upper"] = df["high"].rolling(exit_period).max()
    df["exit_lower"] = df["low"].rolling(exit_period).min()

    # Shifted by 1 (previous bar's channel — mirrors Pine's [1] offset)
    df["entry_upper_1"] = df["entry_upper"].shift(1)
    df["entry_lower_1"] = df["entry_lower"].shift(1)
    df["exit_upper_1"] = df["exit_upper"].shift(1)
    df["exit_lower_1"] = df["exit_lower"].shift(1)

    # Raw signal conditions (Pine Script logic):
    # buySignal = high == upper[1] or ta.crossover(high, upper[1])
    #           = high >= upper[1]
    # sellSignal = low == lower[1] or ta.crossover(lower[1], low)
    #            = low <= lower[1]
    # buyExit = low == sdown[1] or ta.crossover(sdown[1], low)
    #         = low <= sdown[1]
    # sellExit = high == sup[1] or ta.crossover(high, sup[1])
    #          = high >= sup[1]
    
    df["buy_signal_raw"] = df["high"] >= df["entry_upper_1"]
    df["sell_signal_raw"] = df["low"] <= df["entry_lower_1"]
    df["buy_exit_raw"] = df["low"] <= df["exit_lower_1"]
    df["sell_exit_raw"] = df["high"] >= df["exit_upper_1"]

    # Calculate bars since each signal type
    # ta.barssince(condition) returns how many bars ago the condition was true
    # We need to track this cumulatively
    
    def bars_since(series: pd.Series) -> pd.Series:
        """
        Calculate bars since condition was True.
        Returns 0 when condition is True, increments otherwise.
        """
        result = pd.Series(np.nan, index=series.index)
        count = float('inf')
        for idx, val in series.items():
            if val:
                count = 0
            else:
                count += 1
            result[idx] = count
        return result

    df["bars_since_buy_signal"] = bars_since(df["buy_signal_raw"])
    df["bars_since_sell_signal"] = bars_since(df["sell_signal_raw"])
    df["bars_since_buy_exit"] = bars_since(df["buy_exit_raw"])
    df["bars_since_sell_exit"] = bars_since(df["sell_exit_raw"])
    
    # Shift by 1 to get previous bar's bars_since values
    df["bars_since_buy_signal_1"] = df["bars_since_buy_signal"].shift(1)
    df["bars_since_sell_signal_1"] = df["bars_since_sell_signal"].shift(1)
    df["bars_since_buy_exit_1"] = df["bars_since_buy_exit"].shift(1)
    df["bars_since_sell_exit_1"] = df["bars_since_sell_exit"].shift(1)

    # State machine filter conditions:
    # ENTER_LONG: buySignal AND exitBarssince1 < entryBarssince1[1]
    # ENTER_SHORT: sellSignal AND exitBarssince2 < entryBarssince2[1]
    # EXIT_LONG: buyExit AND entryBarssince1 < exitBarssince1[1]
    # EXIT_SHORT: sellExit AND entryBarssince2 < exitBarssince2[1]
    
    df["enter_long_cond"] = (
        df["buy_signal_raw"] & 
        (df["bars_since_buy_exit"] < df["bars_since_buy_signal_1"])
    )
    
    df["enter_short_cond"] = (
        df["sell_signal_raw"] & 
        (df["bars_since_sell_exit"] < df["bars_since_sell_signal_1"])
    )
    
    df["exit_long_cond"] = (
        df["buy_exit_raw"] & 
        (df["bars_since_buy_signal"] < df["bars_since_buy_exit_1"])
    )
    
    df["exit_short_cond"] = (
        df["sell_exit_raw"] & 
        (df["bars_since_sell_signal"] < df["bars_since_sell_exit_1"])
    )

    # Assign signals with priority (only one signal per bar)
    # Priority order from Pine Script: ENTER_LONG > ENTER_SHORT > EXIT_LONG > EXIT_SHORT
    df["signal"] = ""
    df.loc[df["exit_short_cond"], "signal"] = "EXIT_SHORT"
    df.loc[df["exit_long_cond"], "signal"] = "EXIT_LONG"
    df.loc[df["enter_short_cond"], "signal"] = "ENTER_SHORT"
    df.loc[df["enter_long_cond"], "signal"] = "ENTER_LONG"

    # Drop rows where channels aren't yet formed
    df = df.dropna(subset=["entry_upper", "entry_lower", "exit_upper", "exit_lower"])

    return df


def get_latest_signal(df: pd.DataFrame) -> dict:
    """Return a dict with the latest bar's signal info."""
    row = df.iloc[-1]
    return {
        "signal":       row.get("signal", ""),
        "close":        float(row["close"]),
        "entry_upper":  float(row.get("entry_upper", np.nan)),
        "entry_lower":  float(row.get("entry_lower", np.nan)),
        "exit_upper":   float(row.get("exit_upper", np.nan)),
        "exit_lower":   float(row.get("exit_lower", np.nan)),
        "timestamp":    df.index[-1],
    }


def signal_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Count signal occurrences across the full history."""
    counts = df["signal"].value_counts().reindex(_SIGNALS, fill_value=0)
    return counts.to_frame(name="count")

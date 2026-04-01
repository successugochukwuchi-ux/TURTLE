"""
Turtle Trading Logic — TUTCI Variant
=====================================
Translated from Pine Script Donchian Channel breakout:

  // Entry channel
  entryHigh = ta.highest(high, 20)
  entryLow  = ta.lowest(low,  20)

  // Exit channel
  exitHigh  = ta.highest(high, 10)
  exitLow   = ta.lowest(low,  10)

  // Signals
  enterLong  = ta.crossover(close, entryHigh[1])
  enterShort = ta.crossunder(close, entryLow[1])
  exitLong   = ta.crossunder(close, exitLow[1])
  exitShort  = ta.crossover(close, exitHigh[1])

Signals (mutually exclusive, priority order):
  ENTER_LONG  > ENTER_SHORT > EXIT_LONG > EXIT_SHORT
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

    New columns:
        entry_high   — entry_period highest high (shifted 1 for signal comparison)
        entry_low    — entry_period lowest low   (shifted 1)
        exit_high    — exit_period highest high  (shifted 1)
        exit_low     — exit_period lowest low    (shifted 1)
        raw_entry_h  — unshifted entry high
        raw_entry_l  — unshifted entry low
        signal       — one of SIGNALS or ""
    """
    df = df.copy()

    # Rolling channel values (use high/low of each candle)
    df["raw_entry_h"] = df["high"].rolling(entry_period).max()
    df["raw_entry_l"] = df["low"].rolling(entry_period).min()
    df["raw_exit_h"]  = df["high"].rolling(exit_period).max()
    df["raw_exit_l"]  = df["low"].rolling(exit_period).min()

    # Shifted by 1 (previous bar's channel — mirrors Pine's [1] offset)
    df["entry_high"] = df["raw_entry_h"].shift(1)
    df["entry_low"]  = df["raw_entry_l"].shift(1)
    df["exit_high"]  = df["raw_exit_h"].shift(1)
    df["exit_low"]   = df["raw_exit_l"].shift(1)

    # Previous close for crossover detection
    prev_close = df["close"].shift(1)

    # Crossover: close crosses ABOVE a level  (prev <= level, current > level)
    enter_long  = (prev_close <= df["entry_high"]) & (df["close"] > df["entry_high"])
    # Crossunder: close crosses BELOW a level
    enter_short = (prev_close >= df["entry_low"])  & (df["close"] < df["entry_low"])
    exit_long   = (prev_close >= df["exit_low"])   & (df["close"] < df["exit_low"])
    exit_short  = (prev_close <= df["exit_high"])  & (df["close"] > df["exit_high"])

    # Assign signals with priority
    df["signal"] = ""
    df.loc[exit_short,  "signal"] = "EXIT_SHORT"
    df.loc[exit_long,   "signal"] = "EXIT_LONG"
    df.loc[enter_short, "signal"] = "ENTER_SHORT"
    df.loc[enter_long,  "signal"] = "ENTER_LONG"

    # Drop rows where channels aren't yet formed
    df = df.dropna(subset=["entry_high", "entry_low", "exit_high", "exit_low"])

    return df


def get_latest_signal(df: pd.DataFrame) -> dict:
    """Return a dict with the latest bar's signal info."""
    row = df.iloc[-1]
    return {
        "signal":      row.get("signal", ""),
        "close":       float(row["close"]),
        "entry_high":  float(row["entry_high"]),
        "entry_low":   float(row["entry_low"]),
        "exit_high":   float(row["exit_high"]),
        "exit_low":    float(row["exit_low"]),
        "timestamp":   df.index[-1],
    }


def signal_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Count signal occurrences across the full history."""
    counts = df["signal"].value_counts().reindex(_SIGNALS, fill_value=0)
    return counts.to_frame(name="count")

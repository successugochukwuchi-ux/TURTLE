"""
Trading Strategies Module
=========================
Multiple trading strategies for signal generation.

Available Strategies:
- Donchian Channels (Turtle Trading) - Breakout strategy
- RSI + MACD - Momentum + Trend convergence
- SuperTrend - Volatility-based trend following
- ZigZag - Price reversal pattern detection
- Bollinger Bands - Mean reversion strategy
- EMA Crossover - Moving average trend strategy
"""

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Compute Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.inf)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """Compute MACD line, Signal line, and Histogram."""
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr


def compute_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> tuple:
    """
    Compute SuperTrend indicator.
    Returns: (supertrend_values, supertrend_direction, buy_signals, sell_signals)
    """
    atr = compute_atr(df, period)
    hl2 = (df['high'] + df['low']) / 2
    
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr
    
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)  # 1 = uptrend, -1 = downtrend
    
    supertrend.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = 1
    
    for i in range(1, len(df)):
        if direction.iloc[i-1] == 1:
            if df['close'].iloc[i] < lower_band.iloc[i]:
                direction.iloc[i] = -1
                supertrend.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = 1
                supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1])
        else:
            if df['close'].iloc[i] > upper_band.iloc[i]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                direction.iloc[i] = -1
                supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1])
    
    # Generate signals
    buy_signals = (direction.shift(1) == -1) & (direction == 1)
    sell_signals = (direction.shift(1) == 1) & (direction == -1)
    
    return supertrend, direction, buy_signals, sell_signals


def find_zigzag_peaks(df: pd.DataFrame, threshold: float = 0.05) -> tuple:
    """
    Find ZigZag peaks and troughs.
    threshold: minimum price movement to consider a reversal (as decimal, e.g., 0.05 = 5%)
    Returns: (zigzag_values, peak_indices, trough_indices)
    """
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    
    zigzag = pd.Series(np.nan, index=df.index)
    peaks = []
    troughs = []
    
    # Find initial extreme
    last_pivot_high = highs[0]
    last_pivot_low = lows[0]
    pivot_high_idx = 0
    pivot_low_idx = 0
    is_last_pivot_high = None  # True = last was high, False = last was low, None = undetermined
    
    for i in range(1, n):
        if highs[i] > last_pivot_high:
            last_pivot_high = highs[i]
            pivot_high_idx = i
        if lows[i] < last_pivot_low:
            last_pivot_low = lows[i]
            pivot_low_idx = i
        
        # Check for reversal from low
        if is_last_pivot_high == False or is_last_pivot_high is None:
            if highs[i] > last_pivot_low * (1 + threshold):
                if is_last_pivot_high is not None:  # Not the first pivot
                    zigzag.iloc[pivot_low_idx] = last_pivot_low
                    troughs.append(pivot_low_idx)
                is_last_pivot_high = False
                last_pivot_high = highs[i]
                pivot_high_idx = i
                last_pivot_low = lows[i]
                pivot_low_idx = i
        
        # Check for reversal from high
        if is_last_pivot_high == True or is_last_pivot_high is None:
            if lows[i] < last_pivot_high * (1 - threshold):
                if is_last_pivot_high is not None:  # Not the first pivot
                    zigzag.iloc[pivot_high_idx] = last_pivot_high
                    peaks.append(pivot_high_idx)
                is_last_pivot_high = True
                last_pivot_low = lows[i]
                pivot_low_idx = i
                last_pivot_high = highs[i]
                pivot_high_idx = i
    
    # Set the last pivot
    if is_last_pivot_high == True and pivot_low_idx > 0:
        zigzag.iloc[pivot_low_idx] = last_pivot_low
        troughs.append(pivot_low_idx)
    elif is_last_pivot_high == False and pivot_high_idx > 0:
        zigzag.iloc[pivot_high_idx] = last_pivot_high
        peaks.append(pivot_high_idx)
    
    return zigzag, peaks, troughs


def compute_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple:
    """Compute Bollinger Bands."""
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Implementations
# ─────────────────────────────────────────────────────────────────────────────

STRATEGIES = {
    "donchian": "Donchian Channels (Turtle)",
    "rsi_macd": "RSI + MACD",
    "supertrend": "SuperTrend",
    "zigzag": "ZigZag",
    "bollinger": "Bollinger Bands",
    "ema_cross": "EMA Crossover"
}


def compute_donchian_signals(df: pd.DataFrame, entry_period: int = 20, exit_period: int = 10) -> pd.DataFrame:
    """
    Donchian Channels (Turtle Trading) Strategy.
    Entry: Breakout above/below entry channel
    Exit: Breakout below/above exit channel
    """
    df = df.copy()
    
    # Entry channel
    df["entry_upper"] = df["high"].rolling(entry_period).max()
    df["entry_lower"] = df["low"].rolling(entry_period).min()
    
    # Exit channel
    df["exit_upper"] = df["high"].rolling(exit_period).max()
    df["exit_lower"] = df["low"].rolling(exit_period).min()
    
    # Shifted values
    df["entry_upper_1"] = df["entry_upper"].shift(1)
    df["entry_lower_1"] = df["entry_lower"].shift(1)
    df["exit_upper_1"] = df["exit_upper"].shift(1)
    df["exit_lower_1"] = df["exit_lower"].shift(1)
    
    # Raw signals
    df["buy_signal_raw"] = df["high"] >= df["entry_upper_1"]
    df["sell_signal_raw"] = df["low"] <= df["entry_lower_1"]
    df["buy_exit_raw"] = df["low"] <= df["exit_lower_1"]
    df["sell_exit_raw"] = df["high"] >= df["exit_upper_1"]
    
    def bars_since(series: pd.Series) -> pd.Series:
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
    
    df["bars_since_buy_signal_1"] = df["bars_since_buy_signal"].shift(1)
    df["bars_since_sell_signal_1"] = df["bars_since_sell_signal"].shift(1)
    df["bars_since_buy_exit_1"] = df["bars_since_buy_exit"].shift(1)
    df["bars_since_sell_exit_1"] = df["bars_since_sell_exit"].shift(1)
    
    # State machine filter
    df["enter_long_cond"] = df["buy_signal_raw"] & (df["bars_since_buy_exit"] < df["bars_since_buy_signal_1"])
    df["enter_short_cond"] = df["sell_signal_raw"] & (df["bars_since_sell_exit"] < df["bars_since_sell_signal_1"])
    df["exit_long_cond"] = df["buy_exit_raw"] & (df["bars_since_buy_signal"] < df["bars_since_buy_exit_1"])
    df["exit_short_cond"] = df["sell_exit_raw"] & (df["bars_since_sell_signal"] < df["bars_since_sell_exit_1"])
    
    df["signal"] = ""
    df.loc[df["exit_short_cond"], "signal"] = "EXIT_SHORT"
    df.loc[df["exit_long_cond"], "signal"] = "EXIT_LONG"
    df.loc[df["enter_short_cond"], "signal"] = "ENTER_SHORT"
    df.loc[df["enter_long_cond"], "signal"] = "ENTER_LONG"
    
    df = df.dropna(subset=["entry_upper", "entry_lower", "exit_upper", "exit_lower"])
    
    return df


def compute_rsi_macd_signals(df: pd.DataFrame, rsi_period: int = 14, 
                              macd_fast: int = 12, macd_slow: int = 26,
                              macd_signal: int = 9,
                              rsi_oversold: float = 30, rsi_overbought: float = 70) -> pd.DataFrame:
    """
    RSI + MACD Strategy.
    Long Entry: RSI crosses above oversold AND MACD crosses above signal line
    Short Entry: RSI crosses below overbought AND MACD crosses below signal line
    Exit: Opposite crossover or RSI reaches opposite extreme
    """
    df = df.copy()
    
    # Compute indicators
    df["rsi"] = compute_rsi(df["close"], rsi_period)
    macd_line, signal_line, histogram = compute_macd(df["close"], macd_fast, macd_slow, macd_signal)
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = histogram
    
    # Crossover conditions
    df["macd_cross_up"] = (df["macd"].shift(1) < df["macd_signal"].shift(1)) & (df["macd"] > df["macd_signal"])
    df["macd_cross_down"] = (df["macd"].shift(1) > df["macd_signal"].shift(1)) & (df["macd"] < df["macd_signal"])
    
    # RSI conditions
    df["rsi_oversold"] = df["rsi"] < rsi_oversold
    df["rsi_overbought"] = df["rsi"] > rsi_overbought
    df["rsi_cross_above_oversold"] = (df["rsi"].shift(1) < rsi_oversold) & (df["rsi"] >= rsi_oversold)
    df["rsi_cross_below_overbought"] = (df["rsi"].shift(1) > rsi_overbought) & (df["rsi"] <= rsi_overbought)
    
    # Generate signals
    df["signal"] = ""
    
    # Long entry: MACD bullish cross + RSI coming out of oversold
    long_entry = df["macd_cross_up"] & ((df["rsi_oversold"]) | df["rsi_cross_above_oversold"])
    df.loc[long_entry, "signal"] = "ENTER_LONG"
    
    # Short entry: MACD bearish cross + RSI coming from overbought
    short_entry = df["macd_cross_down"] & ((df["rsi_overbought"]) | df["rsi_cross_below_overbought"])
    df.loc[short_entry, "signal"] = "ENTER_SHORT"
    
    # Exit long: MACD bearish cross OR RSI overbought
    exit_long = df["macd_cross_down"] | df["rsi_overbought"]
    df.loc[exit_long & (df["signal"] == ""), "signal"] = "EXIT_LONG"
    
    # Exit short: MACD bullish cross OR RSI oversold
    exit_short = df["macd_cross_up"] | df["rsi_oversold"]
    df.loc[exit_short & (df["signal"] == ""), "signal"] = "EXIT_SHORT"
    
    # Add reference levels for charting
    df["entry_upper"] = df["close"]  # Placeholder for compatibility
    df["entry_lower"] = df["close"]
    df["exit_upper"] = df["close"]
    df["exit_lower"] = df["close"]
    
    return df


def compute_supertrend_signals(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    SuperTrend Strategy.
    Long Entry: SuperTrend flips to uptrend
    Short Entry: SuperTrend flips to downtrend
    Exit: Opposite flip
    """
    df = df.copy()
    
    supertrend, direction, buy_signals, sell_signals = compute_supertrend(df, period, multiplier)
    
    df["supertrend"] = supertrend
    df["supertrend_direction"] = direction
    
    # Use supertrend as dynamic support/resistance
    df["entry_upper"] = df.apply(lambda x: x["supertrend"] if x["supertrend_direction"] == -1 else x["high"], axis=1)
    df["entry_lower"] = df.apply(lambda x: x["supertrend"] if x["supertrend_direction"] == 1 else x["low"], axis=1)
    df["exit_upper"] = df["entry_upper"]
    df["exit_lower"] = df["entry_lower"]
    
    df["signal"] = ""
    df.loc[buy_signals, "signal"] = "ENTER_LONG"
    df.loc[sell_signals, "signal"] = "ENTER_SHORT"
    
    # Add exit signals (opposite entries act as exits)
    df.loc[buy_signals & (direction.shift(1) == -1), "signal"] = "EXIT_SHORT"
    df.loc[sell_signals & (direction.shift(1) == 1), "signal"] = "EXIT_LONG"
    
    return df


def compute_zigzag_signals(df: pd.DataFrame, threshold: float = 0.05) -> pd.DataFrame:
    """
    ZigZag Strategy.
    Long Entry: New trough confirmed after previous peak (price reversal up)
    Short Entry: New peak confirmed after previous trough (price reversal down)
    """
    df = df.copy()
    
    zigzag, peaks, troughs = find_zigzag_peaks(df, threshold)
    
    df["zigzag"] = zigzag
    
    # Create signal array
    df["signal"] = ""
    
    # Mark peaks and troughs
    for idx in peaks:
        if idx < len(df) - 1:
            df.iloc[idx, df.columns.get_loc("signal")] = "ENTER_SHORT"
    
    for idx in troughs:
        if idx < len(df) - 1:
            df.iloc[idx, df.columns.get_loc("signal")] = "ENTER_LONG"
    
    # Add reference levels
    df["entry_upper"] = df["high"].rolling(20).max()
    df["entry_lower"] = df["low"].rolling(20).min()
    df["exit_upper"] = df["entry_upper"]
    df["exit_lower"] = df["entry_lower"]
    
    return df


def compute_bollinger_signals(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """
    Bollinger Bands Strategy (Mean Reversion).
    Long Entry: Price touches lower band + confirmation candle
    Short Entry: Price touches upper band + confirmation candle
    Exit: Price reaches middle band or opposite band
    """
    df = df.copy()
    
    upper, middle, lower = compute_bollinger_bands(df["close"], period, std_dev)
    
    df["bb_upper"] = upper
    df["bb_middle"] = middle
    df["bb_lower"] = lower
    
    # Price touching bands
    df["touch_lower"] = (df["low"] <= lower) & (df["close"] > lower)
    df["touch_upper"] = (df["high"] >= upper) & (df["close"] < upper)
    
    # Confirmation: next candle closes back inside
    df["confirm_long"] = df["touch_lower"].shift(1) & (df["close"] > df["open"])
    df["confirm_short"] = df["touch_upper"].shift(1) & (df["close"] < df["open"])
    
    # Exit conditions
    df["exit_long_cond"] = df["close"] >= middle
    df["exit_short_cond"] = df["close"] <= middle
    
    df["signal"] = ""
    df.loc[df["confirm_long"], "signal"] = "ENTER_LONG"
    df.loc[df["confirm_short"], "signal"] = "ENTER_SHORT"
    df.loc[df["exit_long_cond"] & (df["signal"] == ""), "signal"] = "EXIT_LONG"
    df.loc[df["exit_short_cond"] & (df["signal"] == ""), "signal"] = "EXIT_SHORT"
    
    # Use BB levels for charting
    df["entry_upper"] = upper
    df["entry_lower"] = lower
    df["exit_upper"] = middle
    df["exit_lower"] = middle
    
    return df


def compute_ema_cross_signals(df: pd.DataFrame, fast_period: int = 9, slow_period: int = 21) -> pd.DataFrame:
    """
    EMA Crossover Strategy.
    Long Entry: Fast EMA crosses above Slow EMA
    Short Entry: Fast EMA crosses below Slow EMA
    Exit: Opposite crossover
    """
    df = df.copy()
    
    df["ema_fast"] = compute_ema(df["close"], fast_period)
    df["ema_slow"] = compute_ema(df["close"], slow_period)
    
    # Crossover conditions
    df["golden_cross"] = (df["ema_fast"].shift(1) <= df["ema_slow"].shift(1)) & (df["ema_fast"] > df["ema_slow"])
    df["death_cross"] = (df["ema_fast"].shift(1) >= df["ema_slow"].shift(1)) & (df["ema_fast"] < df["ema_slow"])
    
    df["signal"] = ""
    df.loc[df["golden_cross"], "signal"] = "ENTER_LONG"
    df.loc[df["death_cross"], "signal"] = "ENTER_SHORT"
    
    # Exits are the opposite crossovers
    df.loc[df["death_cross"] & (df["signal"] == ""), "signal"] = "EXIT_LONG"
    df.loc[df["golden_cross"] & (df["signal"] == ""), "signal"] = "EXIT_SHORT"
    
    # Use EMAs as reference levels
    df["entry_upper"] = df["ema_slow"]
    df["entry_lower"] = df["ema_fast"]
    df["exit_upper"] = df["ema_slow"]
    df["exit_lower"] = df["ema_fast"]
    
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main Strategy Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def compute_strategy_signals(df: pd.DataFrame, strategy: str = "donchian", **kwargs) -> pd.DataFrame:
    """
    Compute signals based on selected strategy.
    
    Args:
        df: DataFrame with OHLCV data
        strategy: Strategy name from STRATEGIES dict
        **kwargs: Strategy-specific parameters
    
    Returns:
        DataFrame with signal column and strategy-specific columns
    """
    strategy_functions = {
        "donchian": compute_donchian_signals,
        "rsi_macd": compute_rsi_macd_signals,
        "supertrend": compute_supertrend_signals,
        "zigzag": compute_zigzag_signals,
        "bollinger": compute_bollinger_signals,
        "ema_cross": compute_ema_cross_signals
    }
    
    if strategy not in strategy_functions:
        raise ValueError(f"Unknown strategy: {strategy}. Available: {list(STRATEGIES.keys())}")
    
    func = strategy_functions[strategy]
    return func(df, **kwargs)


def get_strategy_params(strategy: str) -> dict:
    """Get default parameters for a strategy."""
    params = {
        "donchian": {
            "entry_period": 20,
            "exit_period": 10,
            "labels": {"entry_period": "Entry Period", "exit_period": "Exit Period"}
        },
        "rsi_macd": {
            "rsi_period": 14,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "labels": {
                "rsi_period": "RSI Period",
                "macd_fast": "MACD Fast",
                "macd_slow": "MACD Slow",
                "macd_signal": "MACD Signal",
                "rsi_oversold": "RSI Oversold",
                "rsi_overbought": "RSI Overbought"
            }
        },
        "supertrend": {
            "period": 10,
            "multiplier": 3.0,
            "labels": {"period": "ATR Period", "multiplier": "Multiplier"}
        },
        "zigzag": {
            "threshold": 0.05,
            "labels": {"threshold": "Reversal Threshold (%)"}
        },
        "bollinger": {
            "period": 20,
            "std_dev": 2.0,
            "labels": {"period": "Period", "std_dev": "Std Dev"}
        },
        "ema_cross": {
            "fast_period": 9,
            "slow_period": 21,
            "labels": {"fast_period": "Fast EMA", "slow_period": "Slow EMA"}
        }
    }
    return params.get(strategy, {})


def get_latest_signal(df: pd.DataFrame) -> dict:
    """Return a dict with the latest bar's signal info."""
    row = df.iloc[-1]
    return {
        "signal": row.get("signal", ""),
        "close": float(row["close"]),
        "entry_upper": float(row.get("entry_upper", np.nan)),
        "entry_lower": float(row.get("entry_lower", np.nan)),
        "exit_upper": float(row.get("exit_upper", np.nan)),
        "exit_lower": float(row.get("exit_lower", np.nan)),
        "timestamp": df.index[-1],
    }

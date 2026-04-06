"""
Forex Scalping Strategies Module
================================
Implements three optimized scalping strategies for Forex trading:
1. 1-Minute Scalping (EMA + Stochastic)
2. MA Ribbon Entry (5/8/13 SMA fanning)
3. Bollinger Band Scalping (mean reversion)

All strategies include timeframe-optimized parameters and risk management.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple


class ScalpingStrategies:
    """Container for all scalping strategy implementations."""
    
    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_sma(series: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average."""
        return series.rolling(period).mean()
    
    @staticmethod
    def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Stochastic Oscillator (%K and %D).
        Returns: (%K line, %D signal line)
        """
        lowest_low = df['low'].rolling(window=k_period).min()
        highest_high = df['high'].rolling(window=k_period).max()
        
        k_percent = 100 * (df['close'] - lowest_low) / (highest_high - lowest_low)
        d_percent = k_percent.rolling(window=d_period).mean()
        
        return k_percent, d_percent
    
    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """
        Calculate Bollinger Bands.
        Returns dict with 'upper', 'middle', 'lower' bands.
        """
        middle = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'bandwidth': (upper - lower) / middle * 100  # Bandwidth percentage
        }
    
    @staticmethod
    def get_timeframe_optimized_params(timeframe: str) -> Dict[str, any]:
        """
        Return optimized parameters based on selected timeframe.
        Higher timeframes need slightly adjusted thresholds.
        """
        # Default parameters for 1-minute
        params = {
            'stoch_overbought': 20,
            'stoch_oversold': 20,
            'stoch_k_period': 14,
            'stoch_d_period': 3,
            'bb_std_dev': 2.0,
            'bb_period': 20,
        }
        
        # Adjust for higher timeframes - tighten levels to capture momentum faster
        if timeframe in ['5m', '15m']:
            params['stoch_overbought'] = 25
            params['stoch_oversold'] = 25
        elif timeframe in ['30m', '1h']:
            params['stoch_overbought'] = 30
            params['stoch_oversold'] = 30
            params['bb_std_dev'] = 2.2  # Wider bands for higher TF
        elif timeframe in ['4h', '1d']:
            params['stoch_overbought'] = 35
            params['stoch_oversold'] = 35
            params['bb_std_dev'] = 2.5
        
        return params
    
    @staticmethod
    def strategy_1min_scalping(df: pd.DataFrame, timeframe: str = '1m') -> pd.DataFrame:
        """
        1-Minute Scalping Strategy
        ===========================
        Indicators: 13 EMA, 26 EMA, Stochastic (14, 3, 3)
        
        Buy Signal:
          - Price > both EMAs
          - 13 EMA > 26 EMA (bullish alignment)
          - Stochastic < 20 (or optimized level) and moving up
        
        Sell Signal:
          - Price < both EMAs
          - 13 EMA < 26 EMA (bearish alignment)
          - Stochastic > 80 (or 100-optimized) and moving down
        """
        df = df.copy()
        params = ScalpingStrategies.get_timeframe_optimized_params(timeframe)
        
        # Calculate EMAs
        df['ema_13'] = ScalpingStrategies.calculate_ema(df['close'], 13)
        df['ema_26'] = ScalpingStrategies.calculate_ema(df['close'], 26)
        
        # Calculate Stochastic
        stoch_k, stoch_d = ScalpingStrategies.calculate_stochastic(
            df, 
            k_period=params['stoch_k_period'],
            d_period=params['stoch_d_period']
        )
        df['stoch_k'] = stoch_k
        df['stoch_d'] = stoch_d
        
        # Previous values for comparison
        df['stoch_k_prev'] = df['stoch_k'].shift(1)
        df['stoch_d_prev'] = df['stoch_d'].shift(1)
        
        # Bullish conditions
        price_above_emas = (df['close'] > df['ema_13']) & (df['close'] > df['ema_26'])
        ema_bullish = df['ema_13'] > df['ema_26']
        stoch_oversold = df['stoch_k'] < params['stoch_oversold']
        stoch_rising = df['stoch_k'] > df['stoch_k_prev']
        
        # Bearish conditions
        price_below_emas = (df['close'] < df['ema_13']) & (df['close'] < df['ema_26'])
        ema_bearish = df['ema_13'] < df['ema_26']
        stoch_overbought = df['stoch_k'] > (100 - params['stoch_overbought'])
        stoch_falling = df['stoch_k'] < df['stoch_k_prev']
        
        # Generate signals
        df['signal'] = ''
        df.loc[price_above_emas & ema_bullish & stoch_oversold & stoch_rising, 'signal'] = 'ENTER_LONG'
        df.loc[price_below_emas & ema_bearish & stoch_overbought & stoch_falling, 'signal'] = 'ENTER_SHORT'
        
        # Exit signals (opposite conditions or EMA cross against position)
        df.loc[(df['ema_13'] < df['ema_26']) & (df['signal'] == ''), 'signal'] = 'EXIT_LONG'
        df.loc[(df['ema_13'] > df['ema_26']) & (df['signal'] == ''), 'signal'] = 'EXIT_SHORT'
        
        return df
    
    @staticmethod
    def strategy_ma_ribbon(df: pd.DataFrame, timeframe: str = '1m') -> pd.DataFrame:
        """
        MA Ribbon Entry Strategy
        ========================
        Indicators: 5 SMA, 8 SMA, 13 SMA
        
        Buy Signal:
          - 5 SMA > 8 SMA > 13 SMA (fanning out bullish)
          - Price pulls back to touch 5 or 8 SMA (not breaking below 13)
        
        Sell Signal:
          - 5 SMA < 8 SMA < 13 SMA (fanning out bearish)
          - Price pulls back to touch 5 or 8 SMA (not breaking above 13)
        """
        df = df.copy()
        
        # Calculate SMAs
        df['sma_5'] = ScalpingStrategies.calculate_sma(df['close'], 5)
        df['sma_8'] = ScalpingStrategies.calculate_sma(df['close'], 8)
        df['sma_13'] = ScalpingStrategies.calculate_sma(df['close'], 13)
        
        # Bullish ribbon: 5 > 8 > 13
        ribbon_bullish = (df['sma_5'] > df['sma_8']) & (df['sma_8'] > df['sma_13'])
        
        # Bearish ribbon: 5 < 8 < 13
        ribbon_bearish = (df['sma_5'] < df['sma_8']) & (df['sma_8'] < df['sma_13'])
        
        # Price touching/pulling back to 5 or 8 SMA (within 0.1% tolerance)
        tolerance = 0.001  # 0.1%
        touch_sma_5_long = abs(df['low'] - df['sma_5']) / df['sma_5'] < tolerance
        touch_sma_8_long = abs(df['low'] - df['sma_8']) / df['sma_8'] < tolerance
        touch_sma_5_short = abs(df['high'] - df['sma_5']) / df['sma_5'] < tolerance
        touch_sma_8_short = abs(df['high'] - df['sma_8']) / df['sma_8'] < tolerance
        
        # Ensure price hasn't broken below/above the 13 SMA
        above_sma_13 = df['low'] > df['sma_13']
        below_sma_13 = df['high'] < df['sma_13']
        
        # Pullback detection (previous candle was further from SMA)
        prev_distance_long = (df['close'].shift(1) - df['sma_5'].shift(1)) > (df['close'] - df['sma_5'])
        prev_distance_short = (df['sma_5'].shift(1) - df['close'].shift(1)) > (df['sma_5'] - df['close'])
        
        # Generate signals
        df['signal'] = ''
        
        # Long entry: bullish ribbon + pullback to 5 or 8 + holding above 13
        long_condition = (
            ribbon_bullish & 
            (touch_sma_5_long | touch_sma_8_long) & 
            above_sma_13 &
            prev_distance_long
        )
        df.loc[long_condition, 'signal'] = 'ENTER_LONG'
        
        # Short entry: bearish ribbon + pullback to 5 or 8 + holding below 13
        short_condition = (
            ribbon_bearish & 
            (touch_sma_5_short | touch_sma_8_short) & 
            below_sma_13 &
            prev_distance_short
        )
        df.loc[short_condition, 'signal'] = 'ENTER_SHORT'
        
        # Exit when ribbon flattens or reverses
        df.loc[~ribbon_bullish & (df['signal'] == ''), 'signal'] = 'EXIT_LONG'
        df.loc[~ribbon_bearish & (df['signal'] == ''), 'signal'] = 'EXIT_SHORT'
        
        return df
    
    @staticmethod
    def strategy_bollinger_bands(df: pd.DataFrame, timeframe: str = '1m') -> pd.DataFrame:
        """
        Bollinger Band Scalping Strategy
        =================================
        Indicators: 20 SMA, 2 Standard Deviation bands
        
        Buy Signal:
          - Price pierces Lower Band (goes below it)
          - Price closes back inside the band (bullish reversal)
        
        Sell Signal:
          - Price pierces Upper Band (goes above it)
          - Price closes back inside the band (bearish reversal)
        """
        df = df.copy()
        params = ScalpingStrategies.get_timeframe_optimized_params(timeframe)
        
        # Calculate Bollinger Bands
        bb = ScalpingStrategies.calculate_bollinger_bands(
            df,
            period=params['bb_period'],
            std_dev=params['bb_std_dev']
        )
        df['bb_upper'] = bb['upper']
        df['bb_middle'] = bb['middle']
        df['bb_lower'] = bb['lower']
        
        # Previous close for comparison
        df['close_prev'] = df['close'].shift(1)
        df['bb_lower_prev'] = df['bb_lower'].shift(1)
        df['bb_upper_prev'] = df['bb_upper'].shift(1)
        
        # Long setup: price pierced lower band and closed back inside
        pierced_lower = df['low'] < df['bb_lower_prev']
        closed_inside_long = (df['close'] > df['bb_lower_prev']) & (df['close_prev'] < df['bb_lower_prev'])
        
        # Short setup: price pierced upper band and closed back inside
        pierced_upper = df['high'] > df['bb_upper_prev']
        closed_inside_short = (df['close'] < df['bb_upper_prev']) & (df['close_prev'] > df['bb_upper_prev'])
        
        # Additional confirmation: volume spike (optional, if volume available)
        # For now, we'll use price momentum confirmation
        momentum_long = df['close'] > df['open']  # Green candle
        momentum_short = df['close'] < df['open']  # Red candle
        
        # Generate signals
        df['signal'] = ''
        
        # Long entry
        df.loc[pierced_lower & closed_inside_long & momentum_long, 'signal'] = 'ENTER_LONG'
        
        # Short entry
        df.loc[pierced_upper & closed_inside_short & momentum_short, 'signal'] = 'ENTER_SHORT'
        
        # Exit signals: price reaches middle band or opposite band
        exit_long = df['close'] >= df['bb_middle']
        exit_short = df['close'] <= df['bb_middle']
        
        df.loc[exit_long & (df['signal'] == ''), 'signal'] = 'EXIT_LONG'
        df.loc[exit_short & (df['signal'] == ''), 'signal'] = 'EXIT_SHORT'
        
        return df
    
    @staticmethod
    def run_strategy(df: pd.DataFrame, strategy_name: str, timeframe: str = '1m') -> pd.DataFrame:
        """
        Run the specified strategy on the dataframe.
        
        Args:
            df: OHLCV dataframe with columns [open, high, low, close, volume]
            strategy_name: One of '1-Minute Scalping', 'MA Ribbon Entry', 'Bollinger Band Scalping'
            timeframe: Chart timeframe for parameter optimization
        
        Returns:
            DataFrame with added indicator columns and 'signal' column
        """
        strategy_map = {
            '1-Minute Scalping': ScalpingStrategies.strategy_1min_scalping,
            'MA Ribbon Entry': ScalpingStrategies.strategy_ma_ribbon,
            'Bollinger Band Scalping': ScalpingStrategies.strategy_bollinger_bands,
        }
        
        if strategy_name not in strategy_map:
            raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(strategy_map.keys())}")
        
        return strategy_map[strategy_name](df, timeframe)
    
    @staticmethod
    def calculate_stop_loss_take_profit(
        signal: str,
        price: float,
        df: pd.DataFrame,
        strategy_name: str,
        atr_period: int = 14,
        rr_ratio: float = 1.5
    ) -> Dict[str, Optional[float]]:
        """
        Calculate Stop Loss and Take Profit based on strategy and recent swing points.
        
        Uses ATR for dynamic stops and user-defined risk-reward ratio for targets.
        
        Args:
            signal: Entry signal type
            price: Current entry price
            df: DataFrame with OHLC data
            strategy_name: Name of the strategy
            atr_period: ATR calculation period
            rr_ratio: Risk/reward ratio multiplier (e.g., 1.5 for 1:1.5, 2.0 for 1:2)
        
        Returns dict with:
            - stop_loss: SL price level
            - take_profit: TP price level (based on rr_ratio)
            - risk_reward: Risk-reward ratio string
        """
        if len(df) < atr_period:
            atr = price * 0.01  # Default 1% if not enough data
        else:
            high_low = df['high'].iloc[-atr_period:] - df['low'].iloc[-atr_period:]
            atr = high_low.mean()
        
        result = {
            'stop_loss': None,
            'take_profit': None,
            'risk_reward': f'1:{rr_ratio:.1f}',
            'sl_distance': None,
            'tp_distance': None,
        }
        
        if signal == 'ENTER_LONG':
            # Find recent swing low (lowest low in last N bars)
            lookback = min(20, len(df))
            swing_low = df['low'].iloc[-lookback:].min()
            
            # Use wider of: swing low or ATR-based stop
            sl_distance = max(price - swing_low, atr * 1.5)
            result['stop_loss'] = round(price - sl_distance, 5)
            result['sl_distance'] = sl_distance
            
            # Take profit at user-defined R:R
            tp_distance = sl_distance * rr_ratio
            result['take_profit'] = round(price + tp_distance, 5)
            result['tp_distance'] = tp_distance
            
        elif signal == 'ENTER_SHORT':
            # Find recent swing high (highest high in last N bars)
            lookback = min(20, len(df))
            swing_high = df['high'].iloc[-lookback:].max()
            
            # Use wider of: swing high or ATR-based stop
            sl_distance = max(swing_high - price, atr * 1.5)
            result['stop_loss'] = round(price + sl_distance, 5)
            result['sl_distance'] = sl_distance
            
            # Take profit at user-defined R:R
            tp_distance = sl_distance * rr_ratio
            result['take_profit'] = round(price - tp_distance, 5)
            result['tp_distance'] = tp_distance
        
        return result
    
    @staticmethod
    def get_latest_signal_info(df: pd.DataFrame) -> Dict:
        """Extract latest bar information including signal."""
        row = df.iloc[-1]
        return {
            'signal': row.get('signal', ''),
            'close': float(row['close']),
            'timestamp': df.index[-1],
            'open': float(row.get('open', row['close'])),
            'high': float(row.get('high', row['close'])),
            'low': float(row.get('low', row['close'])),
        }

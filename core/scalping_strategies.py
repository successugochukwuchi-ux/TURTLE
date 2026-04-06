import pandas as pd
import numpy as np

def calculate_indicators(df, timeframe):
    """Calculate common indicators with timeframe optimization"""
    # EMA
    df['ema_13'] = df['close'].ewm(span=13, adjust=False).mean()
    df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
    
    # SMA
    df['sma_5'] = df['close'].rolling(window=5).mean()
    df['sma_8'] = df['close'].rolling(window=8).mean()
    df['sma_13'] = df['close'].rolling(window=13).mean()
    df['sma_20'] = df['close'].rolling(window=20).mean()
    
    # Bollinger Bands
    multiplier = 2.0
    if timeframe in ['30m', '1h']: multiplier = 2.2
    if timeframe in ['4h', '1d']: multiplier = 2.5
    
    std_dev = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['sma_20'] + (std_dev * multiplier)
    df['bb_lower'] = df['sma_20'] - (std_dev * multiplier)
    
    # Stochastic
    k_period = 14
    d_period = 3
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    df['stoch_k'] = 100 * (df['close'] - low_min) / (high_max - low_min)
    df['stoch_d'] = df['stoch_k'].rolling(window=d_period).mean()
    
    return df

def generate_1min_scalp_signals(df, timeframe):
    """
    1-Minute Scalping Strategy
    Buy: Price > EMAs, 13 EMA > 26 EMA, Stochastic < 20 (rising)
    Sell: Price < EMAs, 13 EMA < 26 EMA, Stochastic > 80 (falling)
    """
    df = calculate_indicators(df, timeframe)
    
    # Timeframe Optimization for Stochastic Levels
    oversold = 20
    overbought = 80
    if timeframe in ['5m', '15m']:
        oversold, overbought = 25, 75
    elif timeframe in ['30m', '1h']:
        oversold, overbought = 30, 70
        
    df['signal'] = None
    df['confidence'] = 0.0
    
    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Long Condition
        if (curr['close'] > curr['ema_13'] > curr['ema_26']) and \
           (prev['stoch_k'] < oversold and curr['stoch_k'] > prev['stoch_k']) and \
           (curr['stoch_k'] < oversold + 10): # Still relatively low
            df.at[df.index[i], 'signal'] = 'BUY'
            # Confidence based on how deep in oversold and EMA separation
            conf = 50 + (oversold - curr['stoch_k']) * 2
            df.at[df.index[i], 'confidence'] = min(conf, 95)
            
        # Short Condition
        elif (curr['close'] < curr['ema_13'] < curr['ema_26']) and \
             (prev['stoch_k'] > overbought and curr['stoch_k'] < prev['stoch_k']) and \
             (curr['stoch_k'] > overbought - 10):
            df.at[df.index[i], 'signal'] = 'SELL'
            conf = 50 + (curr['stoch_k'] - overbought) * 2
            df.at[df.index[i], 'confidence'] = min(conf, 95)
            
    return df

def generate_ma_ribbon_signals(df, timeframe):
    """
    MA Ribbon Entry
    Buy: 5 > 8 > 13 (fanning out) and price touches/pulls back to 5 or 8 SMA
    Sell: 5 < 8 < 13 and price touches 5 or 8
    """
    df = calculate_indicators(df, timeframe)
    df['signal'] = None
    df['confidence'] = 0.0
    
    for i in range(2, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Bullish Fan: 5>8>13
        bullish_fan = (curr['sma_5'] > curr['sma_8'] > curr['sma_13'])
        bearish_fan = (curr['sma_5'] < curr['sma_8'] < curr['sma_13'])
        
        # Pullback logic: Price near SMA 5 or 8 but not below/above SMA 13
        long_pullback = (bullish_fan) and (curr['low'] <= curr['sma_8'] * 1.001) and (curr['close'] > curr['sma_13'])
        short_pullback = (bearish_fan) and (curr['high'] >= curr['sma_8'] * 0.999) and (curr['close'] < curr['sma_13'])
        
        if long_pullback:
            df.at[df.index[i], 'signal'] = 'BUY'
            # Confidence based on fan width
            spread = (curr['sma_5'] - curr['sma_13']) / curr['close'] * 100
            df.at[df.index[i], 'confidence'] = min(50 + spread * 100, 90)
            
        elif short_pullback:
            df.at[df.index[i], 'signal'] = 'SELL'
            spread = (curr['sma_13'] - curr['sma_5']) / curr['close'] * 100
            df.at[df.index[i], 'confidence'] = min(50 + spread * 100, 90)
            
    return df

def generate_bollinger_signals(df, timeframe):
    """
    Bollinger Band Scalping
    Buy: Price pierces Lower Band and closes back inside
    Sell: Price pierces Upper Band and closes back inside
    """
    df = calculate_indicators(df, timeframe)
    df['signal'] = None
    df['confidence'] = 0.0
    
    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Long: Previous low broke lower band, current close is inside
        if (prev['low'] < prev['bb_lower']) and (curr['close'] > curr['bb_lower']):
            df.at[df.index[i], 'signal'] = 'BUY'
            # Confidence based on band width (volatility)
            width = (curr['bb_upper'] - curr['bb_lower']) / curr['sma_20']
            df.at[df.index[i], 'confidence'] = min(50 + width * 50, 90)
            
        # Short: Previous high broke upper band, current close is inside
        elif (prev['high'] > prev['bb_upper']) and (curr['close'] < curr['bb_upper']):
            df.at[df.index[i], 'signal'] = 'SELL'
            width = (curr['bb_upper'] - curr['bb_lower']) / curr['sma_20']
            df.at[df.index[i], 'confidence'] = min(50 + width * 50, 90)
            
    return df

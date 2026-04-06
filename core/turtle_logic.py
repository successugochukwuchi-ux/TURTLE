import pandas as pd
import numpy as np

def generate_turtle_signals(df):
    """
    Classic Turtle Trading Strategy
    Entry: Breakout of 20-day high (Long) or 20-day low (Short)
    Exit: Breakout of 10-day low (Long) or 10-day high (Short)
    """
    df = df.copy()
    
    # Donchian Channels
    df['entry_upper'] = df['high'].rolling(window=20).max()
    df['entry_lower'] = df['low'].rolling(window=20).min()
    df['exit_upper'] = df['high'].rolling(window=10).max()
    df['exit_lower'] = df['low'].rolling(window=10).min()
    
    df['signal'] = None
    df['confidence'] = 0.0
    
    for i in range(20, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Long Entry: Close breaks above 20-day high
        if curr['close'] > prev['entry_upper']:
            df.at[df.index[i], 'signal'] = 'ENTER_LONG'
            # Confidence based on how far above the breakout
            strength = (curr['close'] - prev['entry_upper']) / prev['entry_upper'] * 100
            df.at[df.index[i], 'confidence'] = min(50 + strength * 10, 95)
            
        # Short Entry: Close breaks below 20-day low
        elif curr['close'] < prev['entry_lower']:
            df.at[df.index[i], 'signal'] = 'ENTER_SHORT'
            strength = (prev['entry_lower'] - curr['close']) / prev['entry_lower'] * 100
            df.at[df.index[i], 'confidence'] = min(50 + strength * 10, 95)
            
        # Exit Long: Close breaks below 10-day low
        elif curr['close'] < prev['exit_lower']:
            df.at[df.index[i], 'signal'] = 'EXIT_LONG'
            df.at[df.index[i], 'confidence'] = 80.0
            
        # Exit Short: Close breaks above 10-day high
        elif curr['close'] > prev['exit_upper']:
            df.at[df.index[i], 'signal'] = 'EXIT_SHORT'
            df.at[df.index[i], 'confidence'] = 80.0
            
    return df

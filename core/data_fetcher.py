import pandas as pd
import yfinance as yf
import ccxt
from datetime import datetime, timedelta

def fetch_gold(timeframe):
    """Fetch Gold data from Yahoo Finance"""
    try:
        ticker = yf.Ticker("GC=F") # Gold Futures
        # Map timeframe to yfinance interval
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "60m", "4h": "1d", "1d": "1d"
        }
        interval = interval_map.get(timeframe, "1h")
        
        df = ticker.history(period="5d" if timeframe in ["1m", "5m"] else "1mo", interval=interval)
        if df.empty:
            return None
            
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        if 'date' in df.columns:
            df['datetime'] = pd.to_datetime(df['date'])
            df.set_index('datetime', inplace=True)
        elif 'index' in df.columns: # Sometimes index is the date
             df.set_index('index', inplace=True)
             
        # Rename to standard OHLCV
        final_df = pd.DataFrame()
        final_df['open'] = df['open']
        final_df['high'] = df['high']
        final_df['low'] = df['low']
        final_df['close'] = df['close']
        final_df['volume'] = df['volume']
        
        return final_df
    except Exception as e:
        print(f"Error fetching Gold: {e}")
        return None

def fetch_crypto(symbol, timeframe):
    """Fetch Crypto data using CCXT"""
    try:
        exchange = ccxt.binance()
        # Normalize symbol
        if '/' not in symbol:
            symbol = f"{symbol.replace('USDT', '')}/USDT"
            
        limit = 100
        if timeframe == "1m": limit = 200
        
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        
        if not ohlcv:
            return None
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching Crypto: {e}")
        return None

def fetch_data(asset, timeframe):
    """Main dispatcher to fetch data based on asset type"""
    asset = asset.upper()
    
    if "XAU" in asset or "GOLD" in asset:
        return fetch_gold(timeframe)
    elif "BTC" in asset or "ETH" in asset or "SOL" in asset or "USDT" in asset:
        return fetch_crypto(asset, timeframe)
    else:
        # Fallback for Forex pairs via yfinance (e.g., EURUSD=X)
        try:
            ticker_str = f"{asset.replace('/', '')}=X"
            ticker = yf.Ticker(ticker_str)
            df = ticker.history(period="1mo", interval="1h") # Defaulting to 1h for forex fallback
            if df.empty: return None
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            df.columns = ['open', 'high', 'low', 'close', 'volume']
            return df
        except:
            # Return dummy data if all else fails (for testing UI)
            dates = pd.date_range(start=datetime.now()-timedelta(hours=100), periods=100, freq='H')
            df = pd.DataFrame({
                'open': 100 + range(100),
                'high': 105 + range(100),
                'low': 95 + range(100),
                'close': 102 + range(100),
                'volume': 1000 + range(100)
            }, index=dates)
            return df

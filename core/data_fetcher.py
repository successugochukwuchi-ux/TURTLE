"""
Data fetchers for XAUUSD (via yfinance) and Crypto (via ccxt).
Returns a clean OHLCV DataFrame indexed by datetime.
"""

import pandas as pd
import yfinance as yf


# ─── GOLD / XAUUSD ──────────────────────────────────────────────────────────

_GOLD_TICKERS = ["GC=F", "XAUUSD=X"]   # try in order

_INTERVAL_MAP_YF = {
    "1m": "1m",  "5m": "5m",  "15m": "15m",
    "30m": "30m", "1h": "1h",  "4h": "1h",   # yfinance has no 4h; use 1h
    "1d": "1d",  "1wk": "1wk",
}

_PERIOD_MAP = {
    "1m": "7d",  "5m": "60d", "15m": "60d",
    "30m": "60d", "1h": "730d", "4h": "730d",
    "1d": "5y",  "1wk": "10y",
}


def fetch_gold(interval: str = "1h", lookback_bars: int = 500) -> pd.DataFrame:
    """Fetch XAUUSD OHLCV data via yfinance."""
    yf_interval = _INTERVAL_MAP_YF.get(interval, "1h")
    period = _PERIOD_MAP.get(interval, "730d")

    last_err = None
    for ticker in _GOLD_TICKERS:
        try:
            raw = yf.download(
                ticker,
                period=period,
                interval=yf_interval,
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                continue
            df = _clean_yf(raw)
            return df.tail(lookback_bars)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Could not fetch gold data. Last error: {last_err}")


def _clean_yf(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index)
    df.index.name = "datetime"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


# ─── CRYPTO via ccxt ────────────────────────────────────────────────────────

def fetch_crypto(
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    lookback_bars: int = 500,
    exchange_id: str = "binance",
) -> pd.DataFrame:
    """Fetch crypto OHLCV data via ccxt (default: Binance)."""
    try:
        import ccxt
    except ImportError:
        raise ImportError("ccxt is not installed. Run: pip install ccxt")

    _ccxt_interval_map = {
        "1m": "1m", "5m": "5m", "15m": "15m",
        "30m": "30m", "1h": "1h", "4h": "4h",
        "1d": "1d", "1wk": "1w",
    }
    tf = _ccxt_interval_map.get(interval, "1h")

    exchange_cls = getattr(ccxt, exchange_id)
    exchange = exchange_cls({"enableRateLimit": True})

    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=lookback_bars)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("datetime").drop(columns=["timestamp"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


# ─── Fallback: synthetic data for demo/testing ──────────────────────────────

def synthetic_gold(bars: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for offline testing."""
    import numpy as np
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.005, bars)
    close = 2000.0 * np.cumprod(1 + returns)
    high  = close * (1 + rng.uniform(0, 0.01, bars))
    low   = close * (1 - rng.uniform(0, 0.01, bars))
    open_ = close * (1 + rng.normal(0, 0.003, bars))
    idx   = pd.date_range(end=pd.Timestamp.utcnow(), periods=bars, freq="1h", tz="UTC")
    df    = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": rng.integers(1000, 50000, bars)}, index=idx)
    df.index.name = "datetime"
    return df

"""
Data fetchers for XAUUSD (via yfinance) and Crypto (via ccxt).
Returns a clean OHLCV DataFrame indexed by datetime.

Gold:   yfinance — tries GC=F then XAUUSD=X
Crypto: ccxt — tries kucoin → bybit → okx → gateio → mexc (Binance is geo-blocked
        in Nigeria and several other regions; these exchanges have no such restriction)
"""

import pandas as pd
import numpy as np
import yfinance as yf

# ─── GOLD / XAUUSD ──────────────────────────────────────────────────────────

# yfinance ≥0.2 returns a MultiIndex (field, ticker); ≥0.2.40 also has
# multi_level_index kwarg.  We handle both layouts in _clean_yf().
_GOLD_TICKERS = ["GC=F", "XAUUSD=X"]

_INTERVAL_MAP_YF = {
    "1m": "1m",  "5m": "5m",  "15m": "15m",
    "30m": "30m", "1h": "1h",  "4h": "1h",   # yfinance has no native 4h
    "1d": "1d",  "1wk": "1wk",
}

_PERIOD_MAP = {
    "1m": "7d",  "5m": "60d", "15m": "60d",
    "30m": "60d", "1h": "730d", "4h": "730d",
    "1d": "10y", "1wk": "10y",
}


def fetch_gold(interval: str = "1h", lookback_bars: int = 500) -> pd.DataFrame:
    """Fetch XAUUSD OHLCV data via yfinance."""
    yf_interval = _INTERVAL_MAP_YF.get(interval, "1h")
    period      = _PERIOD_MAP.get(interval, "730d")

    last_err = None
    for ticker in _GOLD_TICKERS:
        try:
            # multi_level_index=False flattens the column MultiIndex introduced
            # in yfinance ≥0.2.18 when downloading a single ticker.
            try:
                raw = yf.download(
                    ticker,
                    period=period,
                    interval=yf_interval,
                    progress=False,
                    auto_adjust=True,
                    multi_level_index=False,   # yfinance ≥0.2.18
                )
            except TypeError:
                # Older yfinance that doesn't support the kwarg
                raw = yf.download(
                    ticker,
                    period=period,
                    interval=yf_interval,
                    progress=False,
                    auto_adjust=True,
                )

            if raw is None or raw.empty:
                continue

            df = _clean_yf(raw, ticker)
            if df.empty:
                continue
            return df.tail(lookback_bars)

        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(
        f"Could not fetch gold data from yfinance. Last error: {last_err}\n"
        "Check your internet connection or try again shortly."
    )


def _clean_yf(raw: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    """
    Normalise a yfinance DataFrame to lowercase OHLCV columns.

    yfinance column layouts we handle:
      A) MultiIndex: (FieldName, TickerSymbol)  e.g. ('Close', 'GC=F')
      B) Flat:       FieldName                  e.g. 'Close'
    """
    df = raw.copy()

    # Flatten MultiIndex columns → take the first level (field name)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    # Lowercase everything
    df.columns = [c.lower() for c in df.columns]

    # 'adj close' → drop it if present (we use auto_adjust=True so 'close' is already adjusted)
    df = df.drop(columns=[c for c in df.columns if "adj" in c], errors="ignore")

    # Keep only OHLCV
    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns after cleaning: {missing}. Got: {df.columns.tolist()}")

    df = df[needed].dropna(subset=["close"])
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "datetime"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


# ─── CRYPTO via ccxt ────────────────────────────────────────────────────────

# Ordered list of exchanges to try — Binance is first only if not geo-blocked.
# KuCoin, Bybit, OKX, Gate.io, MEXC are all accessible from Nigeria.
_CRYPTO_EXCHANGES = ["kucoin", "bybit", "okx", "gateio", "mexc", "binance"]

_CCXT_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "4h": "4h",
    "1d": "1d", "1wk": "1w",
}


def fetch_crypto(
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    lookback_bars: int = 500,
    preferred_exchange: str | None = None,
) -> pd.DataFrame:
    """
    Fetch crypto OHLCV data via ccxt.

    Tries exchanges in order: kucoin → bybit → okx → gateio → mexc → binance.
    Binance is geo-blocked in Nigeria; the others work fine.
    """
    try:
        import ccxt
    except ImportError:
        raise ImportError("ccxt is not installed.  Run: pip install ccxt")

    tf = _CCXT_INTERVAL_MAP.get(interval, "1h")

    order = ([preferred_exchange] if preferred_exchange else []) + _CRYPTO_EXCHANGES
    # de-duplicate while preserving order
    seen, order = set(), [x for x in order if not (x in seen or seen.add(x))]

    last_err = None
    for ex_id in order:
        try:
            exchange_cls = getattr(ccxt, ex_id)
            exchange = exchange_cls({"enableRateLimit": True})
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=lookback_bars)
            if not ohlcv:
                continue
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.set_index("datetime").drop(columns=["timestamp"])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.index.name = "datetime"
            return df

        except Exception as e:
            last_err = e
            # If geo-blocked (451) or similar, try next exchange
            continue

    raise RuntimeError(
        f"Could not fetch {symbol} from any exchange.\n"
        f"Tried: {', '.join(order)}\n"
        f"Last error: {last_err}"
    )


# ─── Fallback: synthetic data for demo/testing ──────────────────────────────

def synthetic_ohlcv(
    bars: int = 500,
    base_price: float = 3300.0,
    volatility: float = 0.005,
    seed: int = 42,
    freq: str = "1h",
) -> pd.DataFrame:
    """Generate synthetic OHLCV data for offline testing."""
    rng     = np.random.default_rng(seed)
    returns = rng.normal(0, volatility, bars)
    close   = base_price * np.cumprod(1 + returns)
    high    = close * (1 + rng.uniform(0, 0.01, bars))
    low     = close * (1 - rng.uniform(0, 0.01, bars))
    open_   = close * (1 + rng.normal(0, 0.003, bars))
    idx     = pd.date_range(end=pd.Timestamp.utcnow(), periods=bars, freq=freq, tz="UTC")
    df      = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(1000, 50000, bars)},
        index=idx,
    )
    df.index.name = "datetime"
    return df


# Keep old name for backward compat
def synthetic_gold(bars: int = 500, seed: int = 42) -> pd.DataFrame:
    return synthetic_ohlcv(bars=bars, base_price=3300.0, seed=seed)

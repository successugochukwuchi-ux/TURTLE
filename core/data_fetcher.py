"""
Data fetchers for XAUUSD and Crypto.

Gold priority chain:
  1. tvdatafeed-enhanced  — TradingView data (OANDA:XAUUSD), most accurate
  2. yfinance             — fallback if TV credentials missing or unavailable
  3. gold-api.com         — patches the latest close with real-time spot price

Crypto: ccxt — kucoin → bybit → okx → gateio → mexc → binance
"""

import logging
import requests
import pandas as pd
import numpy as np
import yfinance as yf

log = logging.getLogger(__name__)

# ─── TradingView credentials (set these) ─────────────────────────────────────
TV_USERNAME = ""   # your TradingView username
TV_PASSWORD = ""   # your TradingView password

# ─── Interval maps ───────────────────────────────────────────────────────────

_TV_INTERVAL_MAP = {
    "1m":  "in_1_minute",
    "5m":  "in_5_minute",
    "15m": "in_15_minute",
    "30m": "in_30_minute",
    "1h":  "in_1_hour",
    "4h":  "in_4_hour",
    "1d":  "in_daily",
    "1wk": "in_weekly",
}

_INTERVAL_MAP_YF = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "4h": "1h",
    "1d": "1d", "1wk": "1wk",
}

_PERIOD_MAP_YF = {
    "1m": "7d", "5m": "60d", "15m": "60d",
    "30m": "60d", "1h": "730d", "4h": "730d",
    "1d": "10y", "1wk": "10y",
}

# ─── Real-time spot gold price ────────────────────────────────────────────────

def fetch_spot_gold_price() -> float | None:
    sources = [
        ("gold-api.com",  "https://www.gold-api.com/price/XAU",
         lambda r: float(r.json()["price"])),
        ("metals.live",   "https://metals.live/api/spot/gold",
         lambda r: float(r.json()["price"])),
        ("goldprice.org", "https://data-asg.goldprice.org/dbXRates/USD",
         lambda r: float(r.json()["items"][0]["xauPrice"])),
    ]
    for name, url, parser in sources:
        try:
            r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                price = parser(r)
                log.info("Spot gold from %s: %.2f", name, price)
                return price
        except Exception as e:
            log.debug("Spot source %s failed: %s", name, e)
    return None


# ─── TradingView fetch ────────────────────────────────────────────────────────

def fetch_gold_tv(interval: str = "1h", lookback_bars: int = 500) -> pd.DataFrame:
    """Fetch XAUUSD from TradingView via tvdatafeed-enhanced."""
    from tvDatafeed import TvDatafeed, Interval as TvInterval

    tf_name = _TV_INTERVAL_MAP.get(interval, "in_1_hour")
    tf      = getattr(TvInterval, tf_name)

    if TV_USERNAME and TV_PASSWORD:
        tv = TvDatafeed(TV_USERNAME, TV_PASSWORD)
    else:
        tv = TvDatafeed()   # no-login (limited but works)

    # OANDA:XAUUSD is the cleanest spot gold feed on TradingView
    for symbol, exchange in [("XAUUSD", "OANDA"), ("XAUUSD", "FX_IDC"), ("GOLD", "TVC")]:
        try:
            df = tv.get_hist(symbol, exchange, interval=tf, n_bars=lookback_bars)
            if df is not None and not df.empty:
                df = df.rename(columns={"open":"open","high":"high","low":"low",
                                        "close":"close","volume":"volume"})
                df.index = pd.to_datetime(df.index, utc=True)
                df.index.name = "datetime"
                df = df[["open","high","low","close","volume"]].dropna(subset=["close"])
                log.info("TV gold data: %d bars from %s:%s", len(df), exchange, symbol)
                return df
        except Exception as e:
            log.debug("TV %s:%s failed: %s", exchange, symbol, e)

    raise RuntimeError("tvdatafeed could not fetch XAUUSD from any TradingView exchange")


# ─── yfinance fetch ───────────────────────────────────────────────────────────

def fetch_gold_yf(interval: str = "1h", lookback_bars: int = 500) -> pd.DataFrame:
    """Fetch gold OHLCV from yfinance as fallback."""
    yf_interval = _INTERVAL_MAP_YF.get(interval, "1h")
    period      = _PERIOD_MAP_YF.get(interval, "730d")
    last_err    = None

    for ticker in ["GC=F", "XAUUSD=X"]:
        try:
            try:
                raw = yf.download(ticker, period=period, interval=yf_interval,
                                  progress=False, auto_adjust=True, multi_level_index=False)
            except TypeError:
                raw = yf.download(ticker, period=period, interval=yf_interval,
                                  progress=False, auto_adjust=True)
            if raw is None or raw.empty:
                continue
            df = _clean_yf(raw)
            if not df.empty:
                return df.tail(lookback_bars)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"yfinance gold fetch failed. Last error: {last_err}")


def _clean_yf(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df.columns = [c.lower() for c in df.columns]
    df = df.drop(columns=[c for c in df.columns if "adj" in c], errors="ignore")
    needed = ["open", "high", "low", "close", "volume"]
    df = df[needed].dropna(subset=["close"])
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "datetime"
    return df[~df.index.duplicated(keep="last")].sort_index()


# ─── Main gold entry point ────────────────────────────────────────────────────

def fetch_gold(interval: str = "1h", lookback_bars: int = 500) -> pd.DataFrame:
    """
    Fetch XAUUSD OHLCV.
    Tries TradingView first, falls back to yfinance.
    Patches the latest close with real-time spot price.
    """
    df = None

    # 1. Try TradingView
    try:
        df = fetch_gold_tv(interval=interval, lookback_bars=lookback_bars)
        log.info("Using TradingView gold data")
    except Exception as e:
        log.warning("TradingView fetch failed (%s), falling back to yfinance", e)

    # 2. Fall back to yfinance
    if df is None or df.empty:
        df = fetch_gold_yf(interval=interval, lookback_bars=lookback_bars)
        log.info("Using yfinance gold data")

    # 3. Patch latest close with real-time spot price
    spot = fetch_spot_gold_price()
    if spot and spot > 0:
        df.iloc[-1, df.columns.get_loc("close")] = spot
        df.iloc[-1, df.columns.get_loc("high")]  = max(df.iloc[-1]["high"], spot)
        df.iloc[-1, df.columns.get_loc("low")]   = min(df.iloc[-1]["low"],  spot)
        log.info("Patched latest close with spot price: %.2f", spot)

    return df


# ─── Crypto via ccxt ─────────────────────────────────────────────────────────

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
    try:
        import ccxt
    except ImportError:
        raise ImportError("ccxt is not installed. Run: pip install ccxt")

    tf    = _CCXT_INTERVAL_MAP.get(interval, "1h")
    order_list = ([preferred_exchange] if preferred_exchange else []) + _CRYPTO_EXCHANGES
    seen, order = set(), []
    for x in order_list:
        if x not in seen:
            seen.add(x)
            order.append(x)

    last_err = None
    for ex_id in order:
        try:
            exchange = getattr(ccxt, ex_id)({"enableRateLimit": True})
            ohlcv    = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=lookback_bars)
            if not ohlcv:
                continue
            df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.set_index("datetime").drop(columns=["timestamp"])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.index.name = "datetime"
            return df
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(
        f"Could not fetch {symbol} from any exchange.\n"
        f"Tried: {', '.join(order)}\nLast error: {last_err}"
    )


# ─── Synthetic fallback ───────────────────────────────────────────────────────

def synthetic_ohlcv(bars=500, base_price=3300.0, volatility=0.005, seed=42, freq="1h"):
    rng     = np.random.default_rng(seed)
    returns = rng.normal(0, volatility, bars)
    close   = base_price * np.cumprod(1 + returns)
    high    = close * (1 + rng.uniform(0, 0.01, bars))
    low     = close * (1 - rng.uniform(0, 0.01, bars))
    open_   = close * (1 + rng.normal(0, 0.003, bars))
    idx     = pd.date_range(end=pd.Timestamp.utcnow(), periods=bars, freq=freq, tz="UTC")
    df      = pd.DataFrame({"open":open_,"high":high,"low":low,"close":close,
                             "volume":rng.integers(1000,50000,bars)}, index=idx)
    df.index.name = "datetime"
    return df

def synthetic_gold(bars=500, seed=42):
    return synthetic_ohlcv(bars=bars, base_price=3300.0, seed=seed)

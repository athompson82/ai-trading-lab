"""Market data: download, cache, validate.

Sources
- US ETFs: Tiingo end-of-day API (dividend- and split-adjusted OHLC).
- Crypto: Coinbase Exchange public candles (no key needed).

Every price frame has columns open, high, low, close, volume indexed by a
timezone-naive daily DatetimeIndex. "close" for ETFs is the adjusted close
(total return), so buy-and-hold comparisons include dividends.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
COLS = ["open", "high", "low", "close", "volume"]
_session = requests.Session()
_session.headers["User-Agent"] = "ai-trading-lab/0.1 (research)"


class DataError(RuntimeError):
    pass


def _get(url: str, params: dict | None = None, headers: dict | None = None, tries: int = 4):
    for attempt in range(tries):
        try:
            r = _session.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                raise DataError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, DataError) as exc:  # pragma: no cover - network
            if attempt == tries - 1:
                raise DataError(f"GET {url} failed: {exc}") from exc
            time.sleep(2 ** attempt)


# --------------------------------------------------------------------------- ETFs
def fetch_tiingo(ticker: str, start: str) -> pd.DataFrame:
    # In GitHub Actions the key comes from a repository secret. In cloud
    # sessions a network proxy injects it, so a placeholder is fine.
    key = os.environ.get("TIINGO_API_KEY", "proxy-injected")
    rows = _get(
        f"https://api.tiingo.com/tiingo/daily/{ticker}/prices",
        params={"startDate": start, "format": "json"},
        headers={"Authorization": f"Token {key}"},
    )
    if not rows:
        raise DataError(f"Tiingo returned no rows for {ticker}")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    out = df.set_index("date")[["adjOpen", "adjHigh", "adjLow", "adjClose", "adjVolume"]]
    out.columns = COLS
    return out.sort_index()


# --------------------------------------------------------------------------- crypto
def fetch_coinbase(product: str, start: str) -> pd.DataFrame:
    """Daily candles; Coinbase returns at most 300 per request, so page."""
    t0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    frames = []
    while t0 < now:
        t1 = min(t0 + timedelta(days=299), now)
        rows = _get(
            f"https://api.exchange.coinbase.com/products/{product}/candles",
            params={"granularity": 86400, "start": t0.isoformat(), "end": t1.isoformat()},
        )
        if rows:
            frames.append(pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"]))
        t0 = t1 + timedelta(days=1)
        time.sleep(0.35)  # stay well inside public rate limits
    if not frames:
        raise DataError(f"Coinbase returned no candles for {product}")
    df = pd.concat(frames)
    df["date"] = pd.to_datetime(df["time"], unit="s")
    df = df.drop_duplicates("date").set_index("date").sort_index()
    # Drop today's still-forming candle: it is not a completed day.
    today = pd.Timestamp(now.date())
    df = df[df.index < today]
    return df[COLS].astype(float)


# --------------------------------------------------------------------------- cache
def _path(symbol: str) -> Path:
    return DATA_DIR / f"{symbol.replace('/', '_')}.csv"


def load(symbol: str) -> pd.DataFrame:
    p = _path(symbol)
    if not p.exists():
        raise DataError(f"No cached data for {symbol}; run `python -m lab.cli fetch`")
    return pd.read_csv(p, index_col=0, parse_dates=True)


def refresh(symbol: str, start: str) -> pd.DataFrame:
    """Download full history and cache it.

    We re-download the full history rather than appending, because adjusted
    ETF prices are restated whenever a dividend is paid.
    """
    df = fetch_coinbase(symbol, start) if symbol.endswith("-USD") else fetch_tiingo(symbol, start)
    problems = validate(df)
    if problems:
        raise DataError(f"{symbol}: " + "; ".join(problems))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_path(symbol))
    return df


def validate(df: pd.DataFrame, max_abs_daily_move: float = 0.6) -> list[str]:
    """Sanity checks. Failures block trading (risk control), they don't get patched over."""
    problems = []
    if df[COLS[:4]].isna().any().any():
        problems.append("missing prices")
    if (df[COLS[:4]] <= 0).any().any():
        problems.append("non-positive prices")
    if (df["high"] < df[["open", "close"]].max(axis=1) * 0.999).any():
        problems.append("high below open/close")
    if (df["low"] > df[["open", "close"]].min(axis=1) * 1.001).any():
        problems.append("low above open/close")
    moves = df["close"].pct_change().abs()
    if (moves > max_abs_daily_move).any():
        problems.append(f"daily move > {max_abs_daily_move:.0%} on {moves.idxmax().date()}")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        problems.append("index not sorted/unique")
    return problems


def panel(symbols, field: str = "close") -> pd.DataFrame:
    """Wide frame of one field for several symbols (outer-joined on dates)."""
    return pd.concat({s: load(s)[field] for s in symbols}, axis=1).sort_index()

"""Signal generation: prices in, desired portfolio weights out.

Pure functions, identical in backtest and live trading. Row t of every output
uses only data up to and including the close of day t (tests/test_no_lookahead.py
checks this by truncating the data and comparing).

The strategy is time-series momentum with volatility targeting, long-or-cash:
  1. Trend score per asset = fraction of lookbacks (1, 3, 6, 12 months) with a
     positive return. 0 = all down (hold none), 1 = all up (full allocation).
  2. Scale each asset by 1/volatility so each contributes similar risk.
  3. Scale the whole portfolio so its estimated volatility (from the recent
     covariance matrix) equals the target. Never exceed 100% gross exposure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SleeveConfig


def trend_score(close: pd.DataFrame, lookbacks: tuple[int, ...]) -> pd.DataFrame:
    votes = [(close / close.shift(lb) - 1.0 > 0).astype(float).where(close.shift(lb).notna())
             for lb in lookbacks]
    # Require all lookbacks to be available (asset old enough).
    score = sum(votes) / len(votes)
    return score


def trend_weights(close: pd.DataFrame, cfg: SleeveConfig) -> pd.DataFrame:
    rets = close.pct_change(fill_method=None)
    score = trend_score(close, cfg.lookbacks_days)
    vol = rets.rolling(cfg.vol_lookback, min_periods=cfg.vol_lookback).std() * np.sqrt(cfg.periods_per_year)
    raw = (score / vol).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    out = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    cov_window = cfg.cov_lookback
    rv = rets.values
    for i in range(len(close)):
        w = raw.iloc[i].values.copy()
        if w.sum() <= 0 or i < cov_window:
            continue
        w = w / w.sum()                                   # relative risk-parity mix
        window = rv[i - cov_window + 1: i + 1]
        live = w > 0
        sub = window[:, live]
        sub = sub[~np.isnan(sub).any(axis=1)]
        if len(sub) < cov_window // 2:
            continue
        cov = np.cov(sub, rowvar=False) * cfg.periods_per_year
        port_vol = float(np.sqrt(np.atleast_2d(cov).dot(w[live]).dot(w[live]))) if live.sum() > 1 \
            else float(np.sqrt(cov) * w[live][0])
        if port_vol <= 0:
            continue
        w = w * (cfg.target_vol / port_vol)
        w = np.minimum(w, cfg.max_weight)
        gross = w.sum()
        if gross > cfg.max_gross:
            w = w * (cfg.max_gross / gross)
        out.iloc[i] = w
    return out


# --------------------------------------------------------------------------- benchmarks
def constant_weights(close: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    """Static-allocation benchmark (e.g. 100% SPY, or 60/40 SPY/AGG)."""
    out = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for sym, w in weights.items():
        out[sym] = w
    # Can't hold an asset before it has a price.
    return out.where(close.notna(), 0.0)

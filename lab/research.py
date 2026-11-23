"""Run strategies and benchmarks for a sleeve over a period.

`run_sleeve(..., period="development")` stops before HOLDOUT_START and is what
research uses. The holdout is only reachable through lab/holdout.py.
"""
from __future__ import annotations

import pandas as pd

from . import data, metrics
from .config import HOLDOUT_START, SleeveConfig, SLEEVES
from .engine import BacktestResult, run_backtest
from .strategies import constant_weights, trend_weights


def benchmark_specs(cfg: SleeveConfig) -> dict[str, dict[str, float]]:
    if cfg.name == "etf_trend":
        return {"bench_spy": {"SPY": 1.0}, "bench_60_40": {"SPY": 0.6, "AGG": 0.4}}
    return {"bench_btc": {"BTC-USD": 1.0}, "bench_btc_eth_50_50": {"BTC-USD": 0.5, "ETH-USD": 0.5}}


def load_prices(cfg: SleeveConfig):
    syms = sorted(set(cfg.assets) | {a for spec in benchmark_specs(cfg).values() for a in spec})
    opens, closes = data.panel(syms, "open"), data.panel(syms, "close")
    cash = None
    if cfg.cash_proxy:
        cash = data.load(cfg.cash_proxy)["close"].pct_change(fill_method=None).reindex(closes.index).fillna(0.0)
    return opens, closes, cash


def _bench_cfg(cfg: SleeveConfig, spec: dict[str, float]) -> SleeveConfig:
    from dataclasses import replace
    # Benchmarks rebalance monthly-ish via a wide band and are not subject to
    # the strategy's risk caps; they are what a passive investor would hold.
    return replace(cfg, assets=tuple(spec), max_weight=1.0, rebalance="daily", rebalance_band=0.10,
                   drawdown_brake=10.0)


def run_sleeve(name: str, period: str = "development", overlay=None) -> dict[str, BacktestResult]:
    cfg = SLEEVES[name]
    opens, closes, cash = load_prices(cfg)
    if period == "development":
        start, end = None, HOLDOUT_START
    elif period == "holdout":  # only call via lab.holdout
        start, end = None, None
    else:
        raise ValueError(period)

    strat_closes = closes[list(cfg.assets)]
    weights = trend_weights(strat_closes, cfg)
    # Start everything on the same date: the first day the strategy is able
    # to hold positions (enough history for the 12-month lookback).
    first = weights.index[(weights.sum(axis=1) > 0).argmax()]
    results = {cfg.name: run_backtest(cfg.name, opens[list(cfg.assets)], strat_closes, weights, cfg,
                                      cash_returns=cash, start=str(first.date()), end=end)}
    for bname, spec in benchmark_specs(cfg).items():
        bcfg = _bench_cfg(cfg, spec)
        cols = list(spec)
        bw = constant_weights(closes[cols], spec)
        results[bname] = run_backtest(bname, opens[cols], closes[cols], bw, bcfg, use_risk=False,
                                      start=str(first.date()), end=end)
    if period == "holdout":
        for k, r in results.items():
            results[k] = _slice(r, HOLDOUT_START)
    return results


def _slice(r: BacktestResult, start: str) -> BacktestResult:
    """Evaluate only the holdout window, but with positions carried in from
    before it (as a live system would have them)."""
    eq = r.equity[r.equity.index >= pd.Timestamp(start)]
    fills = r.fills[r.fills["date"] >= pd.Timestamp(start)] if len(r.fills) else r.fills
    return BacktestResult(r.name, eq, eq.pct_change().fillna(0.0), r.weights.loc[eq.index], fills,
                          [n for n in r.risk_notes if n[0] >= pd.Timestamp(start)], r.cfg)


def report(results: dict[str, BacktestResult]) -> pd.DataFrame:
    rows = []
    for name, r in results.items():
        ppy = r.cfg.periods_per_year
        traded = r.fills.eval("abs(units * price)").sum() if len(r.fills) else 0.0
        years = (len(r.equity) - 1) / ppy
        turnover = traded / r.equity.mean() / years if years > 0 else None
        rows.append(metrics.summary(name, r.equity, ppy, r.total_costs, turnover))
    return pd.DataFrame(rows).set_index("name")


def vol_matched(strategy: BacktestResult, bench: BacktestResult) -> pd.Series:
    """Benchmark returns scaled (ex post, cost-free) to the strategy's volatility,
    so we compare at equal risk."""
    s, b = strategy.returns.iloc[1:], bench.returns.reindex(strategy.returns.index).iloc[1:]
    return b * (s.std() / b.std())

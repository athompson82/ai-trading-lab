"""Performance and statistical-evidence metrics.

References
- Probabilistic Sharpe Ratio (PSR) and Deflated Sharpe Ratio (DSR):
  Bailey & Lopez de Prado (2012, 2014). DSR corrects for the number of
  strategy variants tried, which is how most backtests mislead.
- Stationary bootstrap (Politis & Romano 1994) for confidence intervals that
  respect autocorrelation and volatility clustering.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from statistics import NormalDist

_N = NormalDist()
EULER_GAMMA = 0.5772156649


def sharpe(r: pd.Series, ppy: int) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(ppy)) if sd > 0 else float("nan")


def sortino(r: pd.Series, ppy: int) -> float:
    downside = np.sqrt((np.minimum(r, 0) ** 2).mean())
    return float(r.mean() / downside * math.sqrt(ppy)) if downside > 0 else float("nan")


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min())


def cagr(equity: pd.Series, ppy: int) -> float:
    years = (len(equity) - 1) / ppy
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) if years > 0 else float("nan")


def psr(r: pd.Series, benchmark_sr: float = 0.0) -> float:
    """P(true per-period Sharpe > benchmark_sr) given sample size, skew, kurtosis."""
    r = r.dropna()
    n = len(r)
    if n < 10 or r.std() == 0:
        return float("nan")
    sr = r.mean() / r.std(ddof=1)
    g3, g4 = float(r.skew()), float(r.kurt()) + 3.0
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    return float(_N.cdf((sr - benchmark_sr) * math.sqrt(n - 1) / denom))


def expected_max_sharpe(n_trials: int, var_trials_sr: float) -> float:
    """Expected maximum per-period Sharpe among n_trials skill-less strategies."""
    if n_trials <= 1:
        return 0.0
    z1 = _N.inv_cdf(1 - 1 / n_trials)
    z2 = _N.inv_cdf(1 - 1 / (n_trials * math.e))
    return math.sqrt(var_trials_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)


def dsr(r: pd.Series, n_trials: int, var_trials_sr: float) -> float:
    """Deflated Sharpe: PSR against the Sharpe that luck alone would produce."""
    return psr(r, expected_max_sharpe(n_trials, var_trials_sr))


def stationary_bootstrap_idx(n: int, mean_block: int, rng: np.random.Generator) -> np.ndarray:
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    p = 1.0 / mean_block
    for i in range(1, n):
        idx[i] = rng.integers(n) if rng.random() < p else (idx[i - 1] + 1) % n
    return idx


def bootstrap_sharpe_ci(r: pd.Series, ppy: int, bench: pd.Series | None = None,
                        n_boot: int = 2000, mean_block: int = 20, seed: int = 7,
                        alpha: float = 0.05) -> dict:
    """CI for the annualised Sharpe and (optionally) the Sharpe difference vs a benchmark.

    The same resampled dates are used for both series so their correlation is kept.
    """
    rng = np.random.default_rng(seed)
    a = r.values
    b = bench.reindex(r.index).fillna(0.0).values if bench is not None else None
    n = len(a)
    s_list, d_list, g_list = [], [], []
    for _ in range(n_boot):
        ix = stationary_bootstrap_idx(n, mean_block, rng)
        sa = a[ix]
        g_list.append(float(np.prod(1 + sa) ** (ppy / n) - 1))
        s = sa.mean() / sa.std(ddof=1) * math.sqrt(ppy) if sa.std() > 0 else 0.0
        s_list.append(s)
        if b is not None:
            sb = b[ix]
            sbv = sb.mean() / sb.std(ddof=1) * math.sqrt(ppy) if sb.std() > 0 else 0.0
            d_list.append(s - sbv)
    lo, hi = alpha / 2 * 100, (1 - alpha / 2) * 100
    out = {"sharpe_ci": (float(np.percentile(s_list, lo)), float(np.percentile(s_list, hi))),
           "cagr_ci": (float(np.percentile(g_list, lo)), float(np.percentile(g_list, hi)))}
    if b is not None:
        d = np.array(d_list)
        out["sharpe_diff_ci"] = (float(np.percentile(d, lo)), float(np.percentile(d, hi)))
        out["p_strategy_better"] = float((d > 0).mean())
    return out


def concentration(r: pd.Series, equity: pd.Series) -> dict:
    """How much of the result came from a handful of days? (Question 3.)"""
    pnl = equity.diff().dropna()
    total = pnl.sum()
    top = pnl.sort_values(ascending=False)
    k = max(1, int(len(pnl) * 0.01))
    # Consecutive 12-month blocks from the start (a final block shorter than
    # 6 months is ignored), so a 3-year holdout gives exactly 3 "years".
    blocks, t0 = [], equity.index[0]
    while t0 < equity.index[-1]:
        t1 = t0 + pd.DateOffset(years=1)
        seg = equity[(equity.index >= t0) & (equity.index <= t1)]
        if len(seg) > 1 and (seg.index[-1] - t0).days >= 182:
            blocks.append(float(seg.iloc[-1] / seg.iloc[0] - 1))
        t0 = t1
    return {
        "yearly_block_returns": blocks,
        "best_1pct_days_share_of_pnl": float(top.iloc[:k].sum() / total) if total else float("nan"),
        "pnl_without_best_10_days": float(total - top.iloc[:10].sum()),
        "hit_rate_days": float((r[r != 0] > 0).mean()),
        "positive_years": int(sum(b > 0 for b in blocks)),
        "n_years": len(blocks),
    }


def summary(name: str, equity: pd.Series, ppy: int, costs: float = 0.0,
            turnover: float | None = None) -> dict:
    r = equity.pct_change().dropna()
    return {
        "name": name,
        "start": str(equity.index[0].date()),
        "end": str(equity.index[-1].date()),
        "final_equity": round(float(equity.iloc[-1]), 2),
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "cagr": cagr(equity, ppy),
        "vol": float(r.std() * math.sqrt(ppy)),
        "sharpe": sharpe(r, ppy),
        "sortino": sortino(r, ppy),
        "max_drawdown": max_drawdown(equity),
        "calmar": cagr(equity, ppy) / abs(max_drawdown(equity)) if max_drawdown(equity) < 0 else float("nan"),
        "psr_vs_0": psr(r),
        "costs_usd": round(costs, 2),
        "annual_turnover": turnover,
    }

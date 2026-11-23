"""Report-only comparisons (addendum A1, section 6). They never affect trading.

1. Pure-AI shadow: replays the AI trader's raw choices (as logged in the
   ledger) with only the hard limits (per-asset caps, no leverage) and the same
   costs and timing, but without the drawdown brake. This shows what the AI's
   own judgement was worth.

2. Random-guessing baseline: 1,000 portfolios that pick random weights on the
   same assets, rebalance weekly under the same band, caps and costs. Each
   real portfolio is ranked against them: a result inside the random spread is
   indistinguishable from luck.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .config import CostModel, SLEEVES, SleeveConfig
from .engine import Portfolio, apply_risk, is_rebalance_day, step

N_RANDOM = 1000
# Report-only extra data (not part of the frozen config): managed-futures ETFs,
# i.e. professionally run, diversified trend following you can simply buy.
REPORT_ONLY_ETFS = ("DBMF", "KMLM")

# Cost scenarios for re-pricing the SAME decisions (per side, all-in).
COST_SCENARIOS = {
    "etf_trend": {"modelled (0.08%)": 0.0008, "low-cost broker (0.03%)": 0.0003},
    "crypto_trend": {"modelled: Coinbase taker (0.75%)": 0.0075, "Coinbase limit order (~0.45%)": 0.0045,
                     "Kraken maker (~0.30%)": 0.0030, "spot crypto ETF (~0.10%)": 0.0010},
}
SEED = 20261123  # fixed so the baseline is reproducible


def _prices(cfg: SleeveConfig, start: str):
    assets = list(cfg.assets)
    opens, closes = data.panel(assets, "open"), data.panel(assets, "close")
    m = closes.index >= pd.Timestamp(start)
    cash = None
    if cfg.cash_proxy:
        cash = data.load(cfg.cash_proxy)["close"].pct_change(fill_method=None).reindex(closes.index).fillna(0.0)
    return opens[m], closes[m], closes.ffill().fillna(0.0)[m], (cash[m] if cash is not None else None)


def _simulate(cfg, opens, closes, marks, cash, decisions: dict[pd.Timestamp, tuple[dict, pd.Timestamp]]):
    """decisions: {decision_date: (weights, first_execution_date)}. Returns an equity Series."""
    pf = Portfolio(cash=cfg.capital, peak_equity=cfg.capital)
    eq_hist, pending, not_before = [], None, None
    idx = closes.index
    for i, d in enumerate(idx):
        executable = pending is not None and (not_before is None or d >= not_before)
        res = step(pf, pending if executable else None, d, opens.iloc[i].to_dict(),
                   marks.iloc[i - 1].to_dict() if i else {}, marks.iloc[i].to_dict(), closes.iloc[i].to_dict(),
                   {}, float(cash.iloc[i]) if cash is not None else 0.0, cfg, eq_hist, decide=False)
        if executable:
            pending = None
        if d in decisions:
            w, nb = decisions[d]
            pending, not_before = w, nb
    return pd.Series(eq_hist, index=idx)


# --------------------------------------------------------------------------- 1. pure-AI shadow
def pure_ai_shadow(events: list[dict], arm: str) -> pd.Series | None:
    sleeve = "etf_trend" if arm.startswith("etf") else "crypto_trend"
    cfg = SLEEVES[sleeve]
    decs = [e["data"] for e in events if e["type"] == "decision" and e["data"]["arm"] == arm]
    timing = {e["data"]["date"]: e["data"]["executes_from"] for e in events
              if e["type"] == "decision_timing" and e["data"]["arm"] == arm}
    if not decs:
        return None
    opens, closes, marks, cash = _prices(cfg, decs[0]["date"])
    decisions = {}
    for x in decs:
        raw = {k: float(v) for k, v in x["signal"].items()}          # the AI's own choice, pre-risk-manager
        hard = apply_risk(raw, cfg, drawdown=0.0, data_ok={a: True for a in raw}).weights  # caps + no leverage only
        nb = timing.get(x["date"])
        decisions[pd.Timestamp(x["date"])] = (hard, pd.Timestamp(nb) if nb else None)
    return _simulate(cfg, opens, closes, marks, cash, decisions)


# --------------------------------------------------------------------------- 2. random baseline
def random_baseline(sleeve: str, start: str, n: int = N_RANDOM) -> pd.DataFrame:
    """Final return and Sharpe for n random-weight portfolios from `start` to the latest data."""
    cfg = SLEEVES[sleeve]
    opens, closes, marks, cash = _prices(cfg, start)
    if len(closes) < 3:
        return pd.DataFrame(columns=["return", "sharpe"])
    rng = np.random.default_rng(SEED)
    k = len(cfg.assets)
    idx = closes.index
    rows = []
    for _ in range(n):
        decisions = {}
        for i, d in enumerate(idx[:-1]):
            if i == 0 or is_rebalance_day(idx, i, "weekly"):
                w = rng.dirichlet(np.ones(k + 1))[:k]               # uniform over assets + cash
                w = np.minimum(w, cfg.max_weight)
                decisions[d] = (dict(zip(cfg.assets, w)), None)
        eq = _simulate(cfg, opens, closes, marks, cash, decisions)
        r = eq.pct_change().dropna()
        sharpe = float(r.mean() / r.std() * np.sqrt(cfg.periods_per_year)) if r.std() > 0 else 0.0
        rows.append({"return": eq.iloc[-1] / eq.iloc[0] - 1, "sharpe": sharpe})
    return pd.DataFrame(rows)


def percentile_rank(baseline: pd.DataFrame, value: float, col: str = "return") -> float:
    """Share of random portfolios this result beat (0-100)."""
    if baseline.empty or not np.isfinite(value):
        return float("nan")
    return float((baseline[col] < value).mean() * 100)


# --------------------------------------------------------------------------- 3. cost sensitivity
def _cfg_with_cost(cfg: SleeveConfig, per_side: float) -> SleeveConfig:
    return replace(cfg, costs=CostModel(fee=per_side, half_spread=0.0, slippage=0.0,
                                        min_trade_usd=cfg.costs.min_trade_usd))


def replay(events: list[dict], arm: str, per_side: float | None = None, start: str | None = None):
    """Re-run an arm's logged decisions (post-risk targets, same timing) under another cost level.
    With per_side=None it uses the modelled costs and should reproduce the live equity (sanity check)."""
    sleeve = "etf_trend" if arm.startswith("etf") else "crypto_trend"
    cfg = SLEEVES[sleeve]
    if arm.split("_", 1)[1].startswith("bench"):
        return None  # benchmarks barely trade; not informative
    decs = [e["data"] for e in events if e["type"] == "decision" and e["data"]["arm"] == arm]
    if not decs:
        return None
    timing = {e["data"]["date"]: e["data"]["executes_from"] for e in events
              if e["type"] == "decision_timing" and e["data"]["arm"] == arm}
    if per_side is not None:
        cfg = _cfg_with_cost(cfg, per_side)
    opens, closes, marks, cash = _prices(cfg, start or decs[0]["date"])
    decisions = {pd.Timestamp(x["date"]): ({k: (np.nan if v is None else v) for k, v in x["target"].items()},
                                           pd.Timestamp(timing[x["date"]]) if x["date"] in timing else None)
                 for x in decs}
    return _simulate(cfg, opens, closes, marks, cash, decisions)


def cost_sensitivity(events: list[dict]) -> dict:
    out = {}
    arms = sorted({e["data"]["arm"] for e in events if e["type"] == "decision"})
    for arm in arms:
        sleeve = "etf_trend" if arm.startswith("etf") else "crypto_trend"
        rows = {}
        for label, c in COST_SCENARIOS[sleeve].items():
            eq = replay(events, arm, c)
            if eq is None or len(eq) < 2:
                break
            rows[label] = float(eq.iloc[-1] / eq.iloc[0] - 1)
        if rows:
            out[arm] = rows
    return out


# --------------------------------------------------------------------------- 4. buy-the-pros benchmark
def managed_futures(start: str) -> dict:
    """Buy-and-hold return of each managed-futures ETF since `start`, after one ETF-cost purchase."""
    out = {}
    for sym in REPORT_ONLY_ETFS:
        try:
            px = data.load(sym)["close"]
        except data.DataError:
            continue
        px = px[px.index >= pd.Timestamp(start)]
        if len(px) > 1:
            out[sym] = float(px.iloc[-1] / px.iloc[0] * (1 - SLEEVES["etf_trend"].costs.per_side) - 1)
    return out


def build(ledger_path: Path, state_dir: Path, start: str | None) -> dict:
    """Everything the dashboard/report needs, as plain JSON-able data."""
    events = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()] if ledger_path.exists() else []
    out = {"shadow": {}, "random": {}}
    for arm in ("etf_ai_trader", "crypto_ai_trader"):
        s = pure_ai_shadow(events, arm)
        if s is not None and len(s) > 1:
            out["shadow"][arm] = [[str(d.date()), float(v)] for d, v in s.items()]
    out["costs"] = cost_sensitivity(events)
    if not start:
        return out
    for sleeve in SLEEVES:
        base = random_baseline(sleeve, start)
        if base.empty:
            continue
        ranks = {}
        prefix = sleeve.split("_")[0]
        for f in sorted(state_dir.glob(f"{prefix}_*.json")):
            st = json.loads(f.read_text())
            eq = pd.Series([v for _, v in st["equity"]], index=pd.to_datetime([d for d, _ in st["equity"]]))
            eq = eq[eq.index >= pd.Timestamp(start)]
            if len(eq) < 2:
                continue
            ret = eq.iloc[-1] / eq.iloc[0] - 1
            ranks[st["arm"]] = {"return": float(ret), "beats_pct_of_random": percentile_rank(base, ret)}
        shadow = out["shadow"].get(f"{prefix}_ai_trader")
        if shadow:
            ret = shadow[-1][1] / shadow[0][1] - 1
            ranks[f"{prefix}_ai_trader_pure"] = {"return": ret, "beats_pct_of_random": percentile_rank(base, ret)}
        if sleeve == "etf_trend":
            for sym, ret in managed_futures(start).items():
                ranks[f"mf_{sym}"] = {"return": ret, "beats_pct_of_random": percentile_rank(base, ret)}
        out["random"][sleeve] = {
            "n": len(base), "start": start,
            "pct": {str(p): float(np.percentile(base["return"], p)) for p in (5, 25, 50, 75, 95)},
            "ranks": ranks,
        }
    return out

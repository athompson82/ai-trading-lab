"""Risk manager, execution simulator and portfolio accounting.

The same Portfolio/step logic drives both the historical backtest and the
daily live paper-trading run, so live results are directly comparable to the
backtest.

Timing convention (prevents look-ahead):
  - Decisions are made after the close of day t, using data <= t.
  - Orders fill at the OPEN of the next trading day t+1, plus costs.
  - The portfolio is marked to market at each close.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import SleeveConfig


# --------------------------------------------------------------------------- risk
@dataclass
class RiskDecision:
    weights: dict[str, float]
    notes: list[str] = field(default_factory=list)
    halted: bool = False


def apply_risk(desired: dict[str, float], cfg: SleeveConfig, drawdown: float,
               data_ok: dict[str, bool], overlay: dict[str, float] | None = None) -> RiskDecision:
    """Independent risk layer. It can only reduce exposure, never add to it."""
    notes: list[str] = []
    w = {a: max(0.0, float(desired.get(a, 0.0))) for a in cfg.assets}

    # AI/other overlays may only scale positions DOWN (multiplier in [0, 1]).
    if overlay:
        for a, m in overlay.items():
            m = min(1.0, max(0.0, float(m)))
            if a in w and m < 1.0:
                notes.append(f"overlay scaled {a} by {m:.2f}")
                w[a] *= m

    for a in w:
        if w[a] > cfg.max_weight:
            notes.append(f"capped {a} {w[a]:.2f}->{cfg.max_weight:.2f}")
            w[a] = cfg.max_weight
        if not data_ok.get(a, True) and w[a] > 0:
            notes.append(f"data check failed for {a}: freeze position")
            w[a] = np.nan  # NaN means "do not trade this asset today"

    if drawdown > cfg.drawdown_brake:
        notes.append(f"drawdown brake: dd={drawdown:.1%} > {cfg.drawdown_brake:.0%}, exposure halved")
        w = {a: (v * 0.5 if not np.isnan(v) else v) for a, v in w.items()}

    gross = sum(v for v in w.values() if not np.isnan(v))
    if gross > cfg.max_gross + 1e-9:
        notes.append(f"gross {gross:.2f} scaled to {cfg.max_gross:.2f}")
        w = {a: (v * cfg.max_gross / gross if not np.isnan(v) else v) for a, v in w.items()}
    return RiskDecision(weights=w, notes=notes)


# --------------------------------------------------------------------------- portfolio
@dataclass
class Fill:
    date: pd.Timestamp
    asset: str
    units: float        # signed: + buy, - sell
    price: float        # market open price
    fill_price: float   # price after spread/slippage
    fee: float          # commission in USD
    cost_usd: float     # total cost vs. market price (spread + slippage + fee)


@dataclass
class Portfolio:
    cash: float
    units: dict[str, float] = field(default_factory=dict)
    peak_equity: float = 0.0

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(u * prices[a] for a, u in self.units.items() if u)

    def weights(self, prices: dict[str, float]) -> dict[str, float]:
        eq = self.equity(prices)
        return {a: (u * prices[a] / eq if eq > 0 else 0.0) for a, u in self.units.items()}

    def to_dict(self) -> dict:
        return {"cash": self.cash, "units": dict(self.units), "peak_equity": self.peak_equity}

    @classmethod
    def from_dict(cls, d: dict) -> "Portfolio":
        return cls(cash=d["cash"], units=dict(d["units"]), peak_equity=d.get("peak_equity", 0.0))


def execute(pf: Portfolio, target: dict[str, float], opens: dict[str, float], date,
            cfg: SleeveConfig, ref_prices: dict[str, float] | None = None) -> list[Fill]:
    """Move the portfolio toward target weights at today's open, paying costs.

    Sells execute before buys so we never need to borrow cash. Weight changes
    smaller than the rebalance band, or trades below the minimum size, are
    skipped. Target NaN means "leave this asset alone".
    """
    c = cfg.costs
    tradable = {a: p for a, p in opens.items() if p is not None and np.isfinite(p) and p > 0}
    # Value positions at today's open; if an asset has no open (holiday gap),
    # fall back to its last known price. It just can't be traded today.
    ref = ref_prices or {}
    vals = {a: tradable.get(a, ref.get(a, 0.0)) for a in pf.units}
    eq = pf.equity(vals)
    if eq <= 0:
        return []
    current = pf.weights(vals)
    orders = []
    for a, tw in target.items():
        if a not in tradable or tw is None or np.isnan(tw):
            continue
        cw = current.get(a, 0.0)
        diff = tw - cw
        # Always allow a full exit; otherwise respect the band.
        if abs(diff) < cfg.rebalance_band and not (tw == 0.0 and cw > 0):
            continue
        notional = diff * eq
        if abs(notional) < c.min_trade_usd:
            continue
        orders.append((a, notional))

    fills: list[Fill] = []
    for a, notional in sorted(orders, key=lambda x: x[1]):  # sells (negative) first
        p = tradable[a]
        slip = c.half_spread + c.slippage
        if notional > 0:
            fill_price = p * (1 + slip)
            # Cannot spend more cash than we have (no leverage, no margin).
            spend = min(notional, pf.cash / (1 + c.fee))
            if spend < c.min_trade_usd:
                continue
            units = spend / fill_price
            fee = spend * c.fee
            pf.cash -= spend + fee
        else:
            fill_price = p * (1 - slip)
            units = notional / p                      # negative
            units = max(units, -pf.units.get(a, 0.0))  # cannot sell what we don't own
            proceeds = -units * fill_price
            fee = proceeds * c.fee
            pf.cash += proceeds - fee
        pf.units[a] = pf.units.get(a, 0.0) + units
        if abs(pf.units[a]) < 1e-12:
            pf.units[a] = 0.0
        cost = abs(units) * abs(fill_price - p) + fee
        fills.append(Fill(date, a, units, p, fill_price, fee, cost))
    return fills


# --------------------------------------------------------------------------- backtest
@dataclass
class BacktestResult:
    name: str
    equity: pd.Series
    returns: pd.Series
    weights: pd.DataFrame
    fills: pd.DataFrame
    risk_notes: list[tuple]
    cfg: SleeveConfig

    @property
    def total_costs(self) -> float:
        return float(self.fills["cost_usd"].sum()) if len(self.fills) else 0.0


def is_rebalance_day(dates: pd.DatetimeIndex, i: int, mode: str) -> bool:
    if mode == "daily":
        return True
    if mode == "weekly":
        # First trading day of each ISO week. (Not the last: live, we can't know
        # a day is the week's last trading day until the next one arrives.)
        return i == 0 or dates[i].isocalendar()[:2] != dates[i - 1].isocalendar()[:2]
    raise ValueError(mode)


@dataclass
class StepResult:
    fills: list[Fill]
    equity: float
    weights: dict[str, float]
    decision: dict[str, float] | None
    notes: list[str]


def step(pf: Portfolio, pending: dict[str, float] | None, d: pd.Timestamp,
         open_row: dict, prev_marks: dict, marks: dict, close_row: dict, target_row: dict,
         cash_ret: float, cfg: SleeveConfig, eq_hist: list[float], decide: bool,
         use_risk: bool = True, overlay: dict[str, float] | None = None) -> StepResult:
    """One trading day. Shared by the backtest and the live paper-trading run.

    open_row/close_row: today's raw prices (NaN if the asset didn't trade);
    prev_marks/marks: last known prices for valuation; target_row: strategy
    weights computed at today's close; eq_hist: prior closing equities (mutated).
    """
    fills = []
    # 1) Execute the previous decision at today's open.
    if pending is not None:
        fills = execute(pf, pending, open_row, d, cfg, ref_prices=prev_marks)
    # 2) Idle cash earns the cash proxy's return.
    if cash_ret and pf.cash > 0:
        pf.cash *= 1 + cash_ret
    # 3) Mark to market at the close.
    eq = pf.equity(marks)
    pf.peak_equity = max(pf.peak_equity, eq)
    eq_hist.append(eq)
    weights = pf.weights(marks)
    # 4) Decide for the next open.
    decision, notes = None, []
    if decide:
        desired = {a: float(v) for a, v in target_row.items()}
        if use_risk:
            dd = 1 - eq / max(eq_hist[-cfg.brake_window:])
            ok = {a: bool(np.isfinite(close_row.get(a, np.nan))) or desired.get(a, 0) == 0
                  for a in desired}
            rd = apply_risk(desired, cfg, dd, ok, overlay)
            decision, notes = rd.weights, rd.notes
        else:
            decision = desired
    return StepResult(fills, eq, weights, decision, notes)


def run_backtest(name: str, opens: pd.DataFrame, closes: pd.DataFrame, target: pd.DataFrame,
                 cfg: SleeveConfig, cash_returns: pd.Series | None = None,
                 use_risk: bool = True, start: str | None = None, end: str | None = None
                 ) -> BacktestResult:
    """Simulate a strategy given a frame of desired weights (row t = decision at close t)."""
    idx = closes.index
    if start:
        idx = idx[idx >= pd.Timestamp(start)]
    if end:
        idx = idx[idx < pd.Timestamp(end)]
    opens, closes, target = opens.reindex(idx), closes.reindex(idx), target.reindex(idx).fillna(0.0)
    last_close = closes.ffill().fillna(0.0)
    cash_r = cash_returns.reindex(idx).fillna(0.0) if cash_returns is not None else None

    pf = Portfolio(cash=cfg.capital, peak_equity=cfg.capital)
    pending: dict[str, float] | None = None
    eq_hist, w_hist, fills, notes = [], [], [], []
    for i, d in enumerate(idx):
        res = step(pf, pending, d, opens.iloc[i].to_dict(),
                   last_close.iloc[i - 1].to_dict() if i else {}, last_close.iloc[i].to_dict(),
                   closes.iloc[i].to_dict(), target.iloc[i].to_dict(),
                   float(cash_r.iloc[i]) if cash_r is not None else 0.0, cfg, eq_hist,
                   decide=i < len(idx) - 1 and is_rebalance_day(idx, i, cfg.rebalance),
                   use_risk=use_risk)
        fills += res.fills
        w_hist.append(res.weights)
        if res.notes:
            notes.append((d, res.notes))
        pending = res.decision
    equity = pd.Series(eq_hist, index=idx, name=name)
    fills_df = pd.DataFrame([f.__dict__ for f in fills])
    return BacktestResult(name, equity, equity.pct_change().fillna(0.0),
                          pd.DataFrame(w_hist, index=idx).fillna(0.0), fills_df, notes, cfg)

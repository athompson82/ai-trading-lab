"""The two AI arms' decision logic.

1. Risk overlay (`*_trend_ai` arms, pre-registered): on the trend strategy's
   rebalance days, Claude reviews current news and may scale each position
   DOWN (multiplier 0-1). It can never add exposure; engine.apply_risk also
   clamps multipliers to [0, 1].

2. AI trader (`*_ai_trader` arms, addendum docs/PREREGISTRATION_ADDENDUM_AI.md):
   every day Claude reads current news plus the price-trend data below and
   chooses target weights itself, long or cash only, inside the same risk
   limits and costs as every other arm.

Both are forward-test only, and both fail safe: if the AI is unavailable the
overlay applies no change and the AI trader keeps its current positions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import ai
from .config import SleeveConfig

DISCLAIMER = ("This is a simulated, paper-trading research experiment; no real money or orders are involved. "
              "Base every judgement on information you find via web search now, cite nothing you did not find, "
              "and say so plainly when news is thin or ambiguous.")


def market_brief(closes: pd.DataFrame, cfg: SleeveConfig, holdings: dict[str, float] | None = None) -> str:
    """Plain-text trend facts as of the latest close, from our own price data."""
    ppy = cfg.periods_per_year
    month = 30 if ppy == 365 else 21
    lines = [f"As-of close: {closes.index[-1].date()} (prices adjusted for dividends/splits where applicable)",
             "asset | last close | 1-week | 1-month | 3-month | 12-month | annualised vol (3m) | current weight"]
    for a in cfg.assets:
        s = closes[a].dropna()
        if len(s) < 13 * month:
            continue
        r = s.pct_change()
        def ret(n):
            return f"{s.iloc[-1] / s.iloc[-1 - n] - 1:+.1%}"
        vol = r.iloc[-3 * month:].std() * np.sqrt(ppy)
        w = (holdings or {}).get(a, 0.0)
        lines.append(f"{a} | {s.iloc[-1]:,.2f} | {ret(7 if ppy == 365 else 5)} | {ret(month)} | {ret(3 * month)} "
                     f"| {ret(12 * month)} | {vol:.0%} | {w:.0%}")
    return "\n".join(lines)


def _weights_schema(assets, key_desc: str) -> dict:
    return {
        "type": "object",
        "properties": {
            key_desc: {"type": "object", "properties": {a: {"type": "number"} for a in assets},
                       "required": list(assets), "additionalProperties": False},
            "rationale": {"type": "string"},
            "key_news": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": [key_desc, "rationale", "key_news", "confidence"],
        "additionalProperties": False,
    }


def _clean(values: dict, assets, cap: float) -> dict[str, float]:
    out = {}
    for a in assets:
        try:
            v = float(values.get(a, 0.0))
        except (TypeError, ValueError):
            v = 0.0
        out[a] = min(cap, max(0.0, v if np.isfinite(v) else 0.0))
    return out


# --------------------------------------------------------------------------- 1. overlay
def risk_overlay(cfg: SleeveConfig, closes: pd.DataFrame, proposed: dict[str, float], ledger, client=None):
    """Returns (multipliers or None, metadata)."""
    held = {a: w for a, w in proposed.items() if w and w > 0}
    if not held:
        return None, {"status": "no_positions"}
    system = ("You are the risk officer for a systematic, long-only trend-following portfolio. "
              "Your only power is to REDUCE positions ahead of identifiable, material event risk "
              "(e.g. a pending regulatory action, exchange failure, sanctions, scheduled binary events). "
              "You cannot add exposure. Most days the right answer is 1.0 for every asset: reduce only with a "
              "specific, current, verifiable reason. " + DISCLAIMER)
    prompt = (f"The strategy intends to hold these weights from the next market open: "
              f"{ {a: round(w, 3) for a, w in held.items()} }.\n\n{market_brief(closes, cfg, held)}\n\n"
              f"Search for current news relevant to these holdings (at most {ai.MAX_SEARCHES} searches). "
              "For each asset return a multiplier between 0 and 1 (1 = keep as proposed, 0.5 = halve, 0 = exit). "
              "Assets not held should get 1.")
    try:
        res = ai.decide(system, prompt, _weights_schema(cfg.assets, "multipliers"), ledger,
                        purpose=f"overlay:{cfg.name}", client=client)
    except ai.AIUnavailable as exc:
        return None, {"status": str(exc)}
    mult = _clean(res.output["multipliers"], cfg.assets, 1.0)
    return mult, {"status": "ok", "rationale": res.output["rationale"][:2000],
                  "key_news": res.output["key_news"][:10], "confidence": res.output["confidence"],
                  "cost_usd": res.meta["cost_usd"]}


# --------------------------------------------------------------------------- 2. AI trader
def ai_trader(cfg: SleeveConfig, closes: pd.DataFrame, holdings: dict[str, float], ledger, client=None):
    """Returns (target weights or None, metadata)."""
    c = cfg.costs
    system = ("You are an autonomous portfolio manager in a research experiment testing whether an AI that reads "
              "current news and market trends can beat simple rules and passive investing after costs. "
              f"Rules: long or cash only (no shorting, no leverage); weights are fractions of the portfolio; each "
              f"asset at most {cfg.max_weight:.0%}; total at most 100% (the rest is cash). "
              f"Every trade costs about {c.per_side:.2%} of the amount traded each way, and weight changes under "
              f"{cfg.rebalance_band:.0%} are ignored, so avoid churning on noise. "
              "Your goal is the best risk-adjusted return over months, not today's move. " + DISCLAIMER)
    prompt = (f"Universe: {', '.join(cfg.assets)}.\n\n{market_brief(closes, cfg, holdings)}\n\n"
              f"Search for the most important current news, research and macro developments for these assets "
              f"(at most {ai.MAX_SEARCHES} searches). Then choose target weights to hold from the next market open.")
    try:
        res = ai.decide(system, prompt, _weights_schema(cfg.assets, "weights"), ledger,
                        purpose=f"trader:{cfg.name}", client=client)
    except ai.AIUnavailable as exc:
        return None, {"status": str(exc)}
    w = _clean(res.output["weights"], cfg.assets, cfg.max_weight)
    return w, {"status": "ok", "rationale": res.output["rationale"][:2000],
               "key_news": res.output["key_news"][:10], "confidence": res.output["confidence"],
               "cost_usd": res.meta["cost_usd"]}

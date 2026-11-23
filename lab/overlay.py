"""AI risk overlay (experimental arm).

Once a day, before the rebalance decision, an LLM reviews current news for the
assets in each sleeve and may recommend REDUCING exposure to any of them
(multiplier between 0 and 1). It can never increase exposure, and the risk
manager enforces that independently (engine.apply_risk clamps to [0, 1]).

The `_ai` arms use this; the plain arms don't. The difference between them is
the measured value of the AI. The overlay is forward-test only: an LLM's
training data includes the historical period, so a backtest would be
contaminated by hindsight.

Status: not yet enabled. Until an API key is configured, every multiplier is
1.0, the `_ai` arms behave exactly like the plain arms, and each decision is
logged with status "not_configured" so that period can be excluded from the
A/B comparison.
"""
from __future__ import annotations

import os


def today_overlays() -> dict[str, tuple[dict | None, dict]]:
    """Return {sleeve: (multipliers or None, metadata)}."""
    from .config import SLEEVES
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {s: (None, {"status": "not_configured"}) for s in SLEEVES}
    raise NotImplementedError("AI overlay is implemented in a later milestone (see docs/STATUS.md)")

"""Forward-test report built only from the ledger state (never from strategy code)."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import metrics
from .live import LEDGER_DIR, ROOT

REPORT = ROOT / "reports" / "latest.md"


def _equity(arm_file: Path) -> pd.Series:
    st = json.loads(arm_file.read_text())
    if not st["equity"]:
        return pd.Series(dtype=float)
    d, e = zip(*st["equity"])
    return pd.Series(e, index=pd.to_datetime(d), name=st["arm"])


def write_report() -> str:
    rows = []
    for f in sorted((LEDGER_DIR / "state").glob("*.json")):
        eq = _equity(f)
        if len(eq) < 2:
            continue
        ppy = 365 if f.stem.startswith("crypto") else 252
        r = eq.pct_change().dropna()
        rows.append({
            "arm": f.stem, "days": len(eq), "equity": eq.iloc[-1],
            "return": eq.iloc[-1] / eq.iloc[0] - 1 if eq.iloc[0] else math.nan,
            "vol": r.std() * math.sqrt(ppy), "sharpe": metrics.sharpe(r, ppy),
            "max_dd": metrics.max_drawdown(eq),
        })
    lines = [f"# Forward paper-trading report",
             f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from the ledger._", ""]
    if not rows:
        lines.append("No forward data yet.")
    else:
        df = pd.DataFrame(rows).set_index("arm")
        lines += ["| arm | days | equity (USD) | return | vol (ann.) | Sharpe (ann.) | max drawdown |",
                  "|---|---|---|---|---|---|---|"]
        for arm, x in df.iterrows():
            lines.append(f"| {arm} | {int(x.days)} | {x.equity:,.2f} | {x['return']:+.2%} | {x.vol:.1%} | "
                         f"{x.sharpe:.2f} | {x.max_dd:.1%} |")
        lines += ["", "Short-window Sharpe ratios are extremely noisy (see docs/PREREGISTRATION.md, section 3); "
                      "do not read them as evidence of skill on their own."]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    return str(REPORT)

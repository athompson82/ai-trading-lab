"""Data snapshot for the private "Ask the Lab" Q&A page (qa/ask.html).

The page runs inside the owner's Claude account and cannot reach the internet,
so it answers from this JSON, published alongside it. Claude's weekly check-in
regenerates and republishes it. Read-only: built from the ledger and docs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import analysis
from .dashboard import LABELS, collect, phase, reliability

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "qa" / "data.json"


def _doc(rel: str, limit: int = 30000) -> str:
    p = ROOT / rel
    return p.read_text()[:limit] if p.exists() else ""


def build() -> Path:
    d = collect()
    now = datetime.now(timezone.utc)
    ph, ph_detail = phase(now.date(), d["start"])
    an = analysis.build(ROOT / "ledger" / "events.jsonl", ROOT / "ledger" / "state", d["start"])

    portfolios = []
    for arm, eq in sorted(d["series"].items()):
        if not eq:
            continue
        vals = [v for _, v in eq]
        peak, mdd = vals[0], 0.0
        for v in vals:
            peak = max(peak, v)
            mdd = min(mdd, v / peak - 1)
        m = d["marks"].get(arm, {})
        portfolios.append({"id": arm, "name": LABELS.get(arm, arm), "value": round(vals[-1], 2),
                           "return_since_start": round(vals[-1] / 5000 - 1, 4), "worst_drop": round(mdd, 4),
                           "days": len(vals), "holdings_now": {k: round(v, 3) for k, v in m.get("weights", {}).items()
                                                               if v > 0.001},
                           "next_target": d["positions"].get(arm, {}).get("pending"),
                           "trades": sum(1 for f in d["fills"] if f["arm"] == arm),
                           "costs_paid": round(sum(f["cost_usd"] for f in d["fills"] if f["arm"] == arm), 2),
                           "equity_history": [[x, round(v, 2)] for x, v in eq[-120:]]})

    decisions = []
    for x in d["decisions"]:
        if "_bench" in x["arm"]:
            continue
        meta = x.get("overlay_meta") or {}
        decisions.append({"date": x["date"], "portfolio": x["arm"], "target": x.get("target"),
                          "risk_notes": x.get("risk_notes"), "ai_status": meta.get("status"),
                          "ai_rationale": meta.get("rationale"), "ai_key_news": meta.get("key_news"),
                          "ai_confidence": meta.get("confidence")})
    trades = [{"date": str(f["date"])[:10], "portfolio": f["arm"], "asset": f["asset"],
               "side": "buy" if f["units"] > 0 else "sell", "amount_usd": round(abs(f["units"]) * f["fill_price"], 2),
               "market_price": round(f["price"], 4), "cost_usd": round(f["cost_usd"], 2)} for f in d["fills"]]
    ai_spend = round(sum(e["data"].get("cost_usd", 0) for e in d["events"] if e["type"] == "ai_call"), 2)
    weekly = sorted((ROOT / "reports" / "weekly").glob("*.md"))

    snap = {
        "generated_utc": now.strftime("%Y-%m-%d %H:%M"),
        "phase": ph, "phase_detail": ph_detail, "forward_start": d["start"],
        "reliability": reliability(d["runs"], d["start"]) | {"ledger_check": d["chain_msg"], "ledger_ok": d["chain_ok"]},
        "ai_spend_total_usd": ai_spend,
        "portfolios": portfolios,
        "luck_ranking": an.get("random", {}),
        "cost_sensitivity": an.get("costs", {}),
        "canadian_mirror": {k: v for k, v in (an.get("cad") or {}).items() if k != "series"} or None,
        "holdout": d["holdout"]["sleeves"] if d["holdout"] else None,
        "decisions": decisions[-150:],
        "trades": trades[-300:],
        "documents": {
            "plan_v1": _doc("docs/PREREGISTRATION.md"),
            "plan_addendum_ai": _doc("docs/PREREGISTRATION_ADDENDUM_AI.md"),
            "decisions_log": _doc("docs/DECISIONS.md", 40000),
            "status": _doc("docs/STATUS.md"),
            "candidate_improvements": _doc("docs/IMPROVEMENTS.md"),
            "live_pilot_plan": _doc("docs/LIVE_PILOT_PLAN.md"),
            "plan_addendum_canadian_mirror": _doc("docs/PREREGISTRATION_ADDENDUM_CAD.md"),
            "latest_weekly_report": weekly[-1].read_text()[:20000] if weekly else "",
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(snap, default=str, separators=(",", ":")))
    return OUT


if __name__ == "__main__":
    p = build()
    print(p, p.stat().st_size, "bytes")

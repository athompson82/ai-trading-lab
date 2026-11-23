"""Weekly progress report: numbers from the ledger, an AI analyst's review, and
candidate improvements.

Improvements are PROPOSED here, never applied: changing the rules of a
portfolio mid-test would make its results unverifiable. Candidates are
collected in docs/IMPROVEMENTS.md and reviewed with the owner at the day-60
interim; chosen ones launch as pre-registered "version 2" portfolios running
alongside version 1 (docs/PREREGISTRATION.md §5).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import ai, analysis
from .dashboard import LABELS, collect, phase, reliability
from .ledger import Ledger

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "ledger" / "events.jsonl"
STATE = ROOT / "ledger" / "state"
OUT_DIR = ROOT / "reports" / "weekly"
IMPROVEMENTS = ROOT / "docs" / "IMPROVEMENTS.md"


def _label(arm: str) -> str:
    return f"{LABELS.get(arm, arm)} ({arm.split('_')[0].upper()})"


def _stats(d: dict, week_start: date) -> list[dict]:
    rows = []
    for arm, eq in sorted(d["series"].items()):
        if not eq:
            continue
        s = pd.Series([v for _, v in eq], index=pd.to_datetime([x for x, _ in eq]))
        before = s[s.index < pd.Timestamp(week_start)]
        base_w = before.iloc[-1] if len(before) else s.iloc[0]
        fills = [f for f in d["fills"] if f["arm"] == arm and str(f["date"])[:10] >= str(week_start)]
        rows.append({"arm": arm, "value": s.iloc[-1], "week": s.iloc[-1] / base_w - 1,
                     "total": s.iloc[-1] / 5000.0 - 1, "max_dd": float((s / s.cummax() - 1).min()),
                     "trades_week": len(fills), "costs_week": sum(f["cost_usd"] for f in fills)})
    return rows


def build(use_ai: bool = True, client=None) -> tuple[str, Path]:
    d = collect()
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=7)
    ph, ph_detail = phase(today, d["start"])
    rel = reliability(d["runs"], d["start"])
    an = analysis.build(LEDGER, STATE, d["start"])
    rows = _stats(d, week_start)
    events = d["events"]
    wk = [e for e in events if e["ts"][:10] >= str(week_start)]
    ai_calls = [e["data"] for e in wk if e["type"] == "ai_call"]
    month_cost = ai.month_to_date_cost(events)
    risk_notes = [(e["data"]["arm"], e["data"]["date"], n) for e in wk if e["type"] == "decision"
                  for n in (e["data"].get("risk_notes") or [])]
    ai_decisions = [e["data"] for e in wk if e["type"] == "decision" and e["data"]["arm"].endswith("_ai_trader")]

    L = [f"# Weekly report: week ending {today:%Y-%m-%d}", "",
         f"**{ph}.** {ph_detail}", "",
         "> Simulated money only. One week of results is mostly noise; the questions this report answers are "
         "*is it working as designed*, *what is it costing*, and *is anything better than luck yet*.", "",
         "## Performance", "",
         "| Portfolio | Value | This week | Since start | Worst drop | Trades (week) | Costs (week) |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    if not rows:
        L.append("| _All portfolios_ | $5,000.00 each | n/a | n/a | n/a | 0 | $0.00 |")
        L += ["", "_No completed trading days yet. Every portfolio starts at US$5,000 in cash; the first decisions "
                  "are made at the first nightly run after the forward start date._"]
    for r in rows:
        L.append(f"| {_label(r['arm'])} | ${r['value']:,.2f} | {r['week']:+.2%} | {r['total']:+.2%} | "
                 f"{r['max_dd']:.1%} | {r['trades_week']} | ${r['costs_week']:,.2f} |")
    L += ["", "## Better than luck?", ""]
    if not an.get("random"):
        L += ["_Not computed yet: needs at least a few trading days since the forward start._", ""]
    for sleeve, rb in an.get("random", {}).items():
        L.append(f"**{'ETF' if sleeve.startswith('etf') else 'Crypto'}**: 1,000 random portfolios returned "
                 f"{rb['pct']['5']:+.1%} to {rb['pct']['95']:+.1%} (middle 90%).")
        for a, v in sorted(rb["ranks"].items(), key=lambda kv: -kv[1]["beats_pct_of_random"]):
            name = "AI trader, pure AI choices (shadow)" if a.endswith("_pure") else LABELS.get(a, a)
            L.append(f"- {name}: {v['return']:+.2%}, beat {v['beats_pct_of_random']:.0f}% of random")
        L.append("")
    if an.get("costs"):
        L += ["## Cost sensitivity (same decisions, cheaper trading)", ""]
        for arm, sc in an["costs"].items():
            L.append(f"- {_label(arm)}: " + "; ".join(f"{k}: {v:+.2%}" for k, v in sc.items()))
        L.append("")
    cad = an.get("cad")
    if cad and cad.get("series"):
        L += ["## Canadian mirror (CAD, report-only)", "",
              f"- ETF Trend Follower held as Canadian-listed equivalents: {cad['return']:+.2%} in CAD "
              f"(costs C${cad['costs_cad']:.2f}; US dollar vs CAD over the period {cad['usdcad_change']:+.2%}).", ""]
    L += ["## AI activity", "",
          f"- AI calls this week: {len(ai_calls)} ({sum(1 for c in ai_calls if c.get('ok'))} succeeded); "
          f"API spend this month: ${month_cost:.2f} of the $50 stop.",
          f"- AI trader decisions this week: {len(ai_decisions)}."]
    for x in ai_decisions[-4:]:
        meta = x.get("overlay_meta") or {}
        L.append(f"  - {x['date']} {_label(x['arm'])}: "
                 + ", ".join(f"{k} {v:.0%}" for k, v in (x.get("target") or {}).items() if v)
                 + f" (confidence {meta.get('confidence', '?')})")
    L += ["", "## Reliability", "",
          f"- Nightly runs completed: {rel['completed']} of {rel['expected']}; missed: "
          f"{', '.join(rel['missed'][-7:]) or 'none'}; data errors: {rel['errors']}.",
          f"- Ledger tamper check: {'passed' if d['chain_ok'] else 'FAILED'} ({d['chain_msg']}; entries: "
          + ", ".join(f"{k} {v}" for k, v in sorted(pd.Series([e['type'] for e in events]).value_counts().items()))
          + ").",
          f"- Risk-manager actions this week: {len(risk_notes)}."]
    for arm, dt, n in risk_notes[:10]:
        L.append(f"  - {dt} {_label(arm)}: {n}")

    facts = "\n".join(L)
    review = None
    if use_ai:
        review = _ai_review(facts, client)
    L += ["", "## Analyst review (AI-written, based only on the figures above)", ""]
    if review is None:
        L.append("_Not available this week (AI not configured, over budget, or the call failed)._")
    else:
        L += [review["summary"], "", "**Strengths**", *[f"- {x}" for x in review["strengths"]], "",
              "**Weaknesses**", *[f"- {x}" for x in review["weaknesses"]], "",
              "**Room for growth: candidate improvements (proposed only, not applied)**"]
        for c in review["candidate_improvements"]:
            L.append(f"- **{c['idea']}**. Evidence: {c['evidence']} How to test: {c['how_to_test']}")
        L += ["", f"_Caveats: {review['caveats']}_"]
        _log_candidates(today, review["candidate_improvements"])
    L += ["", "---", "Dashboard: https://athompson82.github.io/ai-trading-lab/ · "
          "Plan: docs/PREREGISTRATION.md · Candidate improvements: docs/IMPROVEMENTS.md"]
    if review is not None:  # plain-English box goes near the top, after the phase line
        L[4:4] = ["## In plain English", "", review["plain_english"], ""]
    text = "\n".join(L) + "\n"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{today:%Y-%m-%d}.md"
    path.write_text(text)
    return text, path


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "plain_english": {"type": "string"},
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "candidate_improvements": {"type": "array", "items": {
            "type": "object",
            "properties": {"idea": {"type": "string"}, "evidence": {"type": "string"},
                           "how_to_test": {"type": "string"}},
            "required": ["idea", "evidence", "how_to_test"], "additionalProperties": False}},
        "caveats": {"type": "string"},
    },
    "required": ["plain_english", "summary", "strengths", "weaknesses", "candidate_improvements", "caveats"],
    "additionalProperties": False,
}


def _ai_review(facts: str, client=None) -> dict | None:
    system = ("You are an independent quantitative analyst reviewing a pre-registered paper-trading experiment "
              "for its owner, a non-specialist. Be candid and specific. Use only the figures provided; do not "
              "invent numbers. Short samples are noisy: never present one week's result as evidence of skill. "
              "Improvement ideas must be testable without touching the running portfolios (they would run as "
              "separate 'version 2' portfolios with rules fixed in advance), must not use leverage, and must "
              "say what evidence would show they work. Prefer ideas that cut costs or risk over ideas that "
              "chase returns. Write in plain English.")
    prompt = ("Weekly figures:\n\n" + facts + "\n\nWrite: 'plain_english': 4-6 short sentences for an owner "
              "with no trading background, explaining what happened this week and why, defining any term you use "
              "(e.g. 'drawdown means the drop from the highest value'), and saying whether anything needs their "
              "attention; a 3-5 sentence summary; 2-4 strengths; 2-4 "
              "weaknesses; 0-3 candidate improvements (only where the figures give a reason); and caveats.")
    try:
        res = ai.decide(system, prompt, REVIEW_SCHEMA, Ledger(LEDGER), purpose="weekly_review",
                        client=client, web_search=False)
    except ai.AIUnavailable:
        return None
    return res.output


def _log_candidates(day: date, cands: list[dict]) -> None:
    if not cands:
        return
    if not IMPROVEMENTS.exists():
        IMPROVEMENTS.write_text(
            "# Candidate improvements\n\nProposed by the weekly review; none are applied to running portfolios. "
            "Reviewed with the owner at the day-60 interim (2027-02-12). Chosen ideas become pre-registered "
            "version-2 portfolios that run alongside version 1.\n\n"
            "| Proposed | Idea | Evidence | How to test | Status |\n|---|---|---|---|---|\n")
    with IMPROVEMENTS.open("a") as f:
        for c in cands:
            cells = [str(day), c["idea"], c["evidence"], c["how_to_test"], "proposed"]
            f.write("| " + " | ".join(x.replace("|", "/").replace("\n", " ") for x in cells) + " |\n")


if __name__ == "__main__":
    text, path = build(use_ai=bool(os.environ.get("ANTHROPIC_API_KEY")))
    print(path)

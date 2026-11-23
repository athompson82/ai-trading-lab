"""Build the public dashboard (site/index.html) from the ledger only.

Read-only with respect to trading: it imports nothing from strategy, risk or
execution code, and it never writes to the ledger.
"""
from __future__ import annotations

import html
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "ledger" / "events.jsonl"
STATE_DIR = ROOT / "ledger" / "state"
OUT = ROOT / "site" / "index.html"
REPO_URL = "https://github.com/athompson82/ai-trading-lab"

# Pre-registered schedule (docs/STATUS.md). Changing these does not change scoring.
SHAKEDOWN_END = date(2026, 12, 13)
SCORED_START = date(2026, 12, 14)
INTERIM = date(2027, 2, 12)
SCORED_END = date(2027, 3, 14)

SLEEVES = {
    "etf": {"title": "ETF sleeve", "arms": ["etf_trend", "etf_trend_ai", "etf_bench_spy", "etf_bench_60_40", "etf_ai_trader"]},
    "crypto": {"title": "Crypto sleeve", "arms": ["crypto_trend", "crypto_trend_ai", "crypto_bench_btc",
                                                  "crypto_bench_btc_eth_50_50", "crypto_ai_trader"]},
}
LABELS = {
    "etf_trend": "Trend Follower", "etf_trend_ai": "Trend Follower + News Guard", "etf_ai_trader": "News-Driven AI",
    "etf_bench_spy": "Buy & Hold: S&P 500", "etf_bench_60_40": "Buy & Hold: 60/40 stocks/bonds",
    "crypto_trend": "Trend Follower", "crypto_trend_ai": "Trend Follower + News Guard",
    "crypto_ai_trader": "News-Driven AI", "crypto_bench_btc": "Buy & Hold: Bitcoin",
    "crypto_bench_btc_eth_50_50": "Buy & Hold: 50/50 Bitcoin/Ether",
    "mf_DBMF": "Managed-futures fund DBMF (buy & hold)", "mf_KMLM": "Managed-futures fund KMLM (buy & hold)",
}


def _verify_chain(events: list[dict]) -> tuple[bool, str]:
    import hashlib
    prev = "0" * 64
    for i, ev in enumerate(events, start=1):
        body = {k: v for k, v in ev.items() if k != "hash"}
        h = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if ev.get("seq") != i or ev.get("prev_hash") != prev or h != ev.get("hash"):
            return False, f"problem at entry {i}"
        prev = ev["hash"]
    return True, f"{len(events)} entries verified"


def collect() -> dict:
    events = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()] if LEDGER.exists() else []
    ok, msg = _verify_chain(events)
    series, positions = {}, {}
    for f in sorted(STATE_DIR.glob("*.json")) if STATE_DIR.exists() else []:
        st = json.loads(f.read_text())
        series[st["arm"]] = st["equity"]
        positions[st["arm"]] = {"pending": st.get("pending"), "cash": st["portfolio"]["cash"],
                                "start": st.get("start")}
    marks = {}
    for e in events:
        if e["type"] == "mark":
            marks[e["data"]["arm"]] = e["data"]
    fills = [e["data"] | {"seq": e["seq"]} for e in events if e["type"] == "fill"]
    decisions = [e["data"] | {"seq": e["seq"]} for e in events if e["type"] == "decision"]
    runs = [e for e in events if e["type"] in ("run_start", "run_end", "data_error")]
    holdout = next((e["data"] for e in reversed(events) if e["type"] == "holdout_evaluation"), None)
    start = os.environ.get("FORWARD_START") or next(
        (e["data"].get("start") for e in events if e["type"] == "run_start"), None)
    return {"events": events, "chain_ok": ok, "chain_msg": msg, "series": series, "positions": positions,
            "marks": marks, "fills": fills, "decisions": decisions, "runs": runs, "holdout": holdout,
            "start": start}


def reliability(runs: list[dict], start: str | None) -> dict:
    """Expected one completed run per UTC day from the day after the forward start."""
    if not start:
        return {"expected": 0, "completed": 0, "missed": [], "errors": 0}
    first = date.fromisoformat(start) + timedelta(days=1)
    today = datetime.now(timezone.utc).date()
    done = {e["ts"][:10] for e in runs if e["type"] == "run_end"}
    expected = [first + timedelta(days=i) for i in range((today - first).days + 1)] if today >= first else []
    # Today's run counts as expected only once its scheduled time (01:17 UTC) has passed.
    if expected and expected[-1] == today and datetime.now(timezone.utc).hour < 2 and str(today) not in done:
        expected = expected[:-1]
    missed = [str(d) for d in expected if str(d) not in done]
    return {"expected": len(expected), "completed": len(expected) - len(missed), "missed": missed,
            "errors": sum(1 for e in runs if e["type"] == "data_error")}


def phase(today: date, start: str | None) -> tuple[str, str]:
    if not start:
        return "Not started", "The forward test has not started."
    s = date.fromisoformat(start)
    if today <= SHAKEDOWN_END:
        return "Shakedown (not scored)", f"Day {(today - s).days + 1} of shakedown. Scoring begins {SCORED_START:%-d %B %Y}."
    if today <= SCORED_END:
        d = (today - SCORED_START).days + 1
        return "Scored window", f"Day {d} of 90. Interim report {INTERIM:%-d %B %Y}; final {SCORED_END:%-d %B %Y}."
    return "Scored window complete", "Final evaluation due (or optional extension to 6 months)."


def _esc(x) -> str:
    return html.escape(str(x))


# The four systems, with names that say what they do (D-030).
SYSTEMS = [
    {"key": "trend", "name": "Trend Follower", "color": "s1",
     "what": "Fixed rules: holds what has been rising, steps aside from what is falling. Rebalances weekly."},
    {"key": "guard", "name": "Trend Follower + News Guard", "color": "s2",
     "what": "The same rules, plus an AI that reads the news weekly and can only make it more careful."},
    {"key": "ai", "name": "News-Driven AI", "color": "s3",
     "what": "An AI that reads the news and price trends every night and decides what to hold."},
    {"key": "hold", "name": "Buy & Hold", "color": "s4",
     "what": "Buy once, never trade. The benchmark every system has to beat to be worth the effort."},
]
MARKETS = {
    "etf": {"title": "US ETFs", "arms": {"trend": "etf_trend", "guard": "etf_trend_ai", "ai": "etf_ai_trader",
                                          "hold": "etf_bench_spy", "hold2": "etf_bench_60_40"},
            "hold_names": {"etf_bench_spy": "Buy & Hold: S&P 500", "etf_bench_60_40": "Buy & Hold: 60/40 stocks/bonds"}},
    "crypto": {"title": "Crypto", "arms": {"trend": "crypto_trend", "guard": "crypto_trend_ai", "ai": "crypto_ai_trader",
                                            "hold": "crypto_bench_btc", "hold2": "crypto_bench_btc_eth_50_50"},
               "hold_names": {"crypto_bench_btc": "Buy & Hold: Bitcoin",
                              "crypto_bench_btc_eth_50_50": "Buy & Hold: 50/50 Bitcoin/Ether"}},
}
SYS_NAME = {s["key"]: s["name"] for s in SYSTEMS}


def _arm_meta(arm: str) -> tuple[str, str, str]:
    """(market, system key, display name)."""
    for mk, m in MARKETS.items():
        for sk, a in m["arms"].items():
            if a == arm:
                key = "hold" if sk.startswith("hold") else sk
                return mk, key, m["hold_names"].get(arm, SYS_NAME[key])
    return "", "", arm


def _stats(eq: list, ppy: int) -> dict:
    import math
    vals = [v for _, v in eq]
    if not vals:
        return {}
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
    vol = sharpe = None
    if len(rets) > 2:
        mu = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
        vol = sd * math.sqrt(ppy)
        sharpe = mu / sd * math.sqrt(ppy) if sd > 0 else None
    wk = 5 if ppy == 252 else 7
    week = vals[-1] / vals[-1 - wk] - 1 if len(vals) > wk else vals[-1] / 5000 - 1
    return {"value": vals[-1], "ret": vals[-1] / 5000 - 1, "week": week, "mdd": mdd, "vol": vol, "sharpe": sharpe}


def _headline(ports: dict) -> str:
    parts = []
    for mk, m in MARKETS.items():
        live = {a: p for a, p in ports.items() if p["market"] == mk and p.get("ret") is not None}
        if not live:
            continue
        lead = max(live.values(), key=lambda p: p["ret"])
        hold = live.get(m["arms"]["hold"])
        txt = f"In {m['title']}, {lead['name']} leads ({lead['ret']:+.1%} since the start)"
        if hold and hold is not lead:
            txt += f"; {hold['name']} is at {hold['ret']:+.1%}"
        parts.append(txt + ".")
    if not parts:
        return "No trading days completed yet. Every portfolio starts with US$5,000 in cash; the first trades happen after the first nightly run."
    return " ".join(parts) + " Over days and weeks this is mostly luck: see “Better than luck?”."


def _feed(d: dict) -> list[dict]:
    items = []
    for x in d["decisions"]:
        arm = x["arm"]
        if "_bench" in arm:
            continue
        mk, sk, name = _arm_meta(arm)
        meta = x.get("overlay_meta") or {}
        tgt = {k: v for k, v in (x.get("target") or {}).items() if v}
        hold = ", ".join(f"{k} {v:.0%}" for k, v in sorted(tgt.items(), key=lambda kv: -kv[1])) or "all cash"
        text = f"Target: {hold}."
        if meta.get("status") == "ok" and meta.get("rationale"):
            r = meta["rationale"]
            text += " Reason: “" + (r[:260] + ("…" if len(r) > 260 else "")) + "”"
        for n in x.get("risk_notes") or []:
            items.append({"date": x["date"], "market": mk, "system": sk, "who": "Risk manager", "kind": "risk",
                          "text": f"{name}: {n}"})
        items.append({"date": x["date"], "market": mk, "system": sk, "who": name, "kind": "decision", "text": text})
    for e in d["events"]:
        if e["type"] == "decision_skipped":
            mk, sk, name = _arm_meta(e["data"]["arm"])
            items.append({"date": e["data"]["date"], "market": mk, "system": sk, "who": name, "kind": "warn",
                          "text": "No AI decision today; kept current positions (" + str((e["data"].get("reason") or {}).get("status", "")) + ")."})
        elif e["type"] == "data_error":
            items.append({"date": e["ts"][:10], "market": "", "system": "", "who": "System", "kind": "warn",
                          "text": "Market data problem; no trading that night. It catches up on the next run."})
    items.sort(key=lambda i: i["date"])
    return items[-60:]


def payload() -> dict:
    d = collect()
    now = datetime.now(timezone.utc)
    ph, ph_detail = phase(now.date(), d["start"])
    rel = reliability(d["runs"], d["start"])
    try:
        from . import analysis
        an = analysis.build(LEDGER, STATE_DIR, d["start"])
    except Exception as exc:
        an = {"shadow": {}, "random": {}, "costs": {}, "error": f"{type(exc).__name__}: {exc}"}
    luck = {}
    for sleeve, rb in an.get("random", {}).items():
        for arm, v in rb["ranks"].items():
            luck[arm] = v["beats_pct_of_random"]
    ports = {}
    for mk, m in MARKETS.items():
        ppy = 252 if mk == "etf" else 365
        for sk, arm in m["arms"].items():
            _, key, name = _arm_meta(arm)
            eq = d["series"].get(arm, [])
            mark = d["marks"].get(arm, {})
            hold = {k: v for k, v in mark.get("weights", {}).items() if v > 0.0005}
            ports[arm] = {"id": arm, "market": mk, "system": key, "name": name, "secondary": sk == "hold2",
                          "series": eq[-400:], **_stats(eq, ppy),
                          "holdings": hold, "cash": max(0.0, 1 - sum(hold.values())) if mark else 1.0,
                          "target": d["positions"].get(arm, {}).get("pending"),
                          "trades": sum(1 for f in d["fills"] if f["arm"] == arm),
                          "costs": sum(f["cost_usd"] for f in d["fills"] if f["arm"] == arm),
                          "luck": luck.get(arm)}
    ai_month = sum(e["data"].get("cost_usd", 0) for e in d["events"]
                   if e["type"] == "ai_call" and e["ts"][:7] == now.strftime("%Y-%m"))
    last_run = next((e["ts"] for e in reversed(d["runs"]) if e["type"] == "run_end"), None)
    holdout = None
    if d["holdout"]:
        holdout = {k: {"verdict": v["verdict"], "table": v["table"]} for k, v in d["holdout"]["sleeves"].items()}
    return {
        "generated": now.strftime("%Y-%m-%d %H:%M"), "phase": ph, "phase_detail": ph_detail, "start": d["start"],
        "headline": _headline(ports), "systems": SYSTEMS,
        "markets": {k: {"title": v["title"], "arms": v["arms"]} for k, v in MARKETS.items()},
        "portfolios": ports, "shadow": an.get("shadow", {}), "random": an.get("random", {}),
        "costs": an.get("costs", {}), "feed": _feed(d), "holdout": holdout,
        "health": {"last_run": last_run, "completed": rel["completed"], "expected": rel["expected"],
                   "missed": rel["missed"][-10:], "errors": rel["errors"], "ledger_ok": d["chain_ok"],
                   "ledger_msg": d["chain_msg"], "ai_month": ai_month, "ai_cap": 50},
        "links": {"repo": REPO_URL, "ask": "https://claude.ai/artifact/FndLCFizNc6Y7xAzXkJ4Z2"},
    }


def build() -> str:
    data = payload()
    page = (Path(__file__).parent / "dashboard.html").read_text()
    page = page.replace("{{DATA}}", json.dumps(data, default=str).replace("</", "<\\/"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page)
    return str(OUT)


if __name__ == "__main__":
    print(build())

"""Daily forward paper-trading run.

Run once a day after the US close / UTC midnight (GitHub Actions does this).
For every arm it processes each completed trading day since the last run
(so a missed run catches up rather than skipping days):
  - fill the previous decision at that day's open (with costs),
  - mark to market at the close,
  - on rebalance days, compute and record a new decision.
All of it goes to the hash-chained ledger; per-arm state is saved as JSON.

The simulator never touches a broker or real money. There is deliberately no
code path that can place a real order.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, overlay as overlay_mod
from .config import CRYPTO_DATA_START, ETF_DATA_START, SLEEVES, SleeveConfig
from .engine import Portfolio, is_rebalance_day, step
from .ledger import Ledger
from .research import _bench_cfg, benchmark_specs
from .strategies import constant_weights, trend_weights

ROOT = Path(__file__).resolve().parent.parent
LEDGER_DIR = ROOT / "ledger"


@dataclass(frozen=True)
class Arm:
    name: str
    sleeve: str
    kind: str                 # "trend", "benchmark" or "ai_trader"
    use_overlay: bool = False
    bench_spec: tuple = ()

    def cfg(self) -> SleeveConfig:
        base = SLEEVES[self.sleeve]
        return _bench_cfg(base, dict(self.bench_spec)) if self.kind == "benchmark" else base


def arms() -> list[Arm]:
    out = []
    for sleeve in SLEEVES:
        out.append(Arm(sleeve, sleeve, "trend"))
        out.append(Arm(f"{sleeve}_ai", sleeve, "trend", use_overlay=True))
        # Added by addendum (docs/PREREGISTRATION_ADDENDUM_AI.md); forward-only.
        out.append(Arm(f"{sleeve.split('_')[0]}_ai_trader", sleeve, "ai_trader"))
        for bname, spec in benchmark_specs(SLEEVES[sleeve]).items():
            out.append(Arm(f"{sleeve.split('_')[0]}_{bname}", sleeve, "benchmark",
                           bench_spec=tuple(spec.items())))
    return out


def code_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:  # pragma: no cover
        return "unknown"


def _state_path(arm: str) -> Path:
    return LEDGER_DIR / "state" / f"{arm}.json"


def load_state(arm: Arm, start: str) -> dict:
    p = _state_path(arm.name)
    if p.exists():
        return json.loads(p.read_text())
    cfg = arm.cfg()
    if arm.kind == "ai_trader":
        # Added mid-experiment: it starts from the day it is first switched on,
        # not from the forward-test start (it can't make decisions for the past).
        start = max(start, str(datetime.now(timezone.utc).date() - timedelta(days=1)))
    return {"arm": arm.name, "start": start, "last_date": None, "pending": None,
            "portfolio": Portfolio(cash=cfg.capital, peak_equity=cfg.capital).to_dict(),
            "equity": []}


def save_state(state: dict) -> None:
    p = _state_path(state["arm"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1, default=str))


def refresh_all() -> list[str]:
    """Download fresh data. Returns a list of problems (empty if fine)."""
    from .config import BENCHMARK_ETFS
    problems = []
    syms = {}
    for s in SLEEVES.values():
        for a in s.assets:
            syms[a] = CRYPTO_DATA_START if a.endswith("-USD") else ETF_DATA_START
    from .analysis import REPORT_ONLY_ETFS
    for a in BENCHMARK_ETFS + REPORT_ONLY_ETFS:
        syms[a] = ETF_DATA_START
    syms["FX_USDCAD"] = "2020-01-01"  # report-only Canadian mirror (addendum A2)
    for sym, start in syms.items():
        try:
            data.refresh(sym, start)
        except Exception as exc:
            problems.append(f"{sym}: {exc}")
    return problems


def _first_executable_day(cfg: SleeveConfig, decided_at: datetime) -> str:
    """First trading day whose OPEN is after the moment an AI decision was made.

    Rule-based decisions use only the close, so they fill at the next open. AI
    decisions also read news up to the moment of the call (about 01:17 UTC),
    which is after the crypto day's 00:00 UTC open, so they must wait one more
    day; otherwise the AI would see news published after the price it trades at.
    """
    d = decided_at.date()
    if cfg.periods_per_year == 365:          # crypto: day opens 00:00 UTC
        return str(d + timedelta(days=1))
    # US ETFs open 13:30/14:30 UTC: today's open is still ahead at 01:17 UTC.
    return str(d if decided_at.hour < 13 else d + timedelta(days=1))


def run_arm(arm: Arm, ledger: Ledger, start: str, ai_client=None, now: datetime | None = None) -> dict:
    cfg = arm.cfg()
    assets = list(cfg.assets)
    opens, closes = data.panel(assets, "open"), data.panel(assets, "close")
    if arm.kind == "trend":
        target = trend_weights(closes, cfg)
    elif arm.kind == "benchmark":
        target = constant_weights(closes, dict(arm.bench_spec))
    else:  # ai_trader: no historical signal; decisions come from the AI on the latest day only
        target = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    cash = None
    if cfg.cash_proxy:
        cash = data.load(cfg.cash_proxy)["close"].pct_change(fill_method=None)
    last_close = closes.ffill().fillna(0.0)
    idx = closes.index
    now = now or datetime.now(timezone.utc)

    st = load_state(arm, start)
    pf = Portfolio.from_dict(st["portfolio"])
    eq_hist = [e for _, e in st["equity"]]
    last = pd.Timestamp(st["last_date"]) if st["last_date"] else None
    todo = [i for i, d in enumerate(idx) if d >= pd.Timestamp(st["start"]) and (last is None or d > last)]
    latest_i = len(idx) - 1
    for i in todo:
        d = idx[i]
        first_day = st["last_date"] is None
        is_latest = i == latest_i
        if arm.kind == "ai_trader":
            decide = is_latest            # a missed day can't be re-assessed with today's news
        else:
            decide = first_day or is_rebalance_day(idx, i, cfg.rebalance)

        # Pending orders wait for their first executable day (AI timing rule).
        pending = st["pending"]
        not_before = st.get("pending_not_before")
        executable = pending is not None and (not_before is None or str(d.date()) >= not_before)

        row = target.iloc[i].fillna(0.0).to_dict()
        ov, ai_meta, uses_ai = None, None, False
        if decide and arm.kind == "ai_trader":
            holdings = pf.weights(last_close.iloc[i].to_dict())
            w, ai_meta = overlay_mod.ai_trader(cfg, closes.iloc[: i + 1], holdings, ledger, client=ai_client)
            if w is None:
                decide = False            # AI unavailable: keep current positions, logged below
                ledger.append("decision_skipped", {"arm": arm.name, "date": str(d.date()), "reason": ai_meta})
            else:
                row, uses_ai = w, True
        elif decide and arm.use_overlay:
            if is_latest:
                ov, ai_meta = overlay_mod.risk_overlay(cfg, closes.iloc[: i + 1], row, ledger, client=ai_client)
                uses_ai = ov is not None
            else:
                ai_meta = {"status": "skipped_catchup_day"}

        res = step(pf, pending if executable else None, d, opens.iloc[i].to_dict(),
                   last_close.iloc[i - 1].to_dict() if i else {}, last_close.iloc[i].to_dict(),
                   closes.iloc[i].to_dict(), row,
                   float(cash.get(d, 0.0)) if cash is not None and np.isfinite(cash.get(d, 0.0)) else 0.0,
                   cfg, eq_hist, decide=decide, use_risk=arm.kind != "benchmark", overlay=ov)
        for f in res.fills:
            ledger.append("fill", {"arm": arm.name, **{k: (str(v) if k == "date" else v)
                                                       for k, v in f.__dict__.items()}})
        if decide:
            ledger.append("decision", {"arm": arm.name, "date": str(d.date()),
                                       "signal": {k: round(float(v), 6) for k, v in row.items()},
                                       "target": {k: (None if np.isnan(v) else round(v, 6))
                                                  for k, v in res.decision.items()},
                                       "risk_notes": res.notes, "overlay": ov, "overlay_meta": ai_meta})
            st["pending"] = res.decision
            st["pending_not_before"] = _first_executable_day(cfg, now) if uses_ai else None
            if st["pending_not_before"]:
                ledger.append("decision_timing", {"arm": arm.name, "date": str(d.date()),
                                                  "executes_from": st["pending_not_before"]})
        elif executable:
            st["pending"], st["pending_not_before"] = None, None
        ledger.append("mark", {"arm": arm.name, "date": str(d.date()), "equity": round(res.equity, 4),
                               "cash": round(pf.cash, 4),
                               "weights": {k: round(v, 6) for k, v in res.weights.items()}})
        st["equity"].append([str(d.date()), res.equity])
        st["last_date"] = str(d.date())
        st["portfolio"] = pf.to_dict()
    save_state(st)
    return {"arm": arm.name, "days_processed": len(todo), "last_date": st["last_date"],
            "equity": st["equity"][-1][1] if st["equity"] else cfg.capital}


def run_daily(start: str, use_network: bool = True) -> dict:
    ledger = Ledger(LEDGER_DIR / "events.jsonl")
    ok, msg = ledger.verify()
    if not ok:
        raise RuntimeError(f"Ledger integrity check failed: {msg}. Refusing to trade.")
    run = {"code_version": code_version(), "start": start}
    if use_network:
        problems = refresh_all()
        if problems:
            ledger.append("data_error", {"problems": problems})
            raise RuntimeError("Data refresh failed; no trading today: " + "; ".join(problems))
    # Fingerprint the exact data used, so any run can be reproduced and audited.
    import hashlib
    run["data_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                          for p in sorted(data.DATA_DIR.glob("*.csv"))}
    ledger.append("run_start", run)
    import os
    ai_on = bool(os.environ.get("ANTHROPIC_API_KEY"))
    # AI trader arms only exist once the AI is configured (see the addendum).
    results = [run_arm(a, ledger, start) for a in arms() if a.kind != "ai_trader" or ai_on]
    ledger.append("run_end", {"arms": results})
    return {"results": results}

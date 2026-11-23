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
    kind: str                 # "trend" or "benchmark"
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
    for a in BENCHMARK_ETFS:
        syms[a] = ETF_DATA_START
    for sym, start in syms.items():
        try:
            data.refresh(sym, start)
        except Exception as exc:
            problems.append(f"{sym}: {exc}")
    return problems


def run_arm(arm: Arm, ledger: Ledger, start: str, today_overlay: dict | None) -> dict:
    cfg = arm.cfg()
    assets = list(cfg.assets)
    opens, closes = data.panel(assets, "open"), data.panel(assets, "close")
    if arm.kind == "trend":
        target = trend_weights(closes, cfg)
    else:
        target = constant_weights(closes, dict(arm.bench_spec))
    cash = None
    if cfg.cash_proxy:
        cash = data.load(cfg.cash_proxy)["close"].pct_change(fill_method=None)
    last_close = closes.ffill().fillna(0.0)
    idx = closes.index

    st = load_state(arm, start)
    pf = Portfolio.from_dict(st["portfolio"])
    eq_hist = [e for _, e in st["equity"]]
    last = pd.Timestamp(st["last_date"]) if st["last_date"] else None
    todo = [i for i, d in enumerate(idx) if d >= pd.Timestamp(st["start"]) and (last is None or d > last)]
    latest_i = len(idx) - 1
    for i in todo:
        d = idx[i]
        first_day = st["last_date"] is None
        decide = first_day or is_rebalance_day(idx, i, cfg.rebalance)
        ov, ov_meta = None, None
        if decide and arm.use_overlay:
            if i == latest_i and today_overlay is not None:
                ov, ov_meta = today_overlay.get(arm.sleeve, (None, None))
            else:
                # A missed day can't be re-assessed honestly with today's news.
                ov_meta = {"status": "skipped_catchup_day"}
        res = step(pf, st["pending"], d, opens.iloc[i].to_dict(),
                   last_close.iloc[i - 1].to_dict() if i else {}, last_close.iloc[i].to_dict(),
                   closes.iloc[i].to_dict(), target.iloc[i].fillna(0.0).to_dict(),
                   float(cash.get(d, 0.0)) if cash is not None and np.isfinite(cash.get(d, 0.0)) else 0.0,
                   cfg, eq_hist, decide=decide, use_risk=arm.kind == "trend", overlay=ov)
        for f in res.fills:
            ledger.append("fill", {"arm": arm.name, **{k: (str(v) if k == "date" else v)
                                                       for k, v in f.__dict__.items()}})
        if decide:
            ledger.append("decision", {"arm": arm.name, "date": str(d.date()),
                                       "signal": {k: round(float(v), 6) for k, v in target.iloc[i].fillna(0).items()},
                                       "target": {k: (None if np.isnan(v) else round(v, 6))
                                                  for k, v in res.decision.items()},
                                       "risk_notes": res.notes, "overlay": ov, "overlay_meta": ov_meta})
        ledger.append("mark", {"arm": arm.name, "date": str(d.date()), "equity": round(res.equity, 4),
                               "cash": round(pf.cash, 4),
                               "weights": {k: round(v, 6) for k, v in res.weights.items()}})
        st["pending"] = res.decision
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
    overlays = overlay_mod.today_overlays() if any(a.use_overlay for a in arms()) else {}
    ledger.append("run_start", {**run, "overlay_status": {k: v[1] for k, v in overlays.items()}})
    results = [run_arm(a, ledger, start, overlays) for a in arms()]
    ledger.append("run_end", {"arms": results})
    return {"results": results}

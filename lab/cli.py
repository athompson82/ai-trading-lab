"""Command line entry point.

  python -m lab.cli fetch                 download/refresh all market data
  python -m lab.cli backtest              development-period backtest (holdout excluded)
  python -m lab.cli run --start DATE      daily forward paper-trading run
  python -m lab.cli verify                check ledger integrity
  python -m lab.cli report                write reports/latest.md from the ledger
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lab")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("backtest")
    r = sub.add_parser("run")
    r.add_argument("--start", required=True, help="forward test start date (YYYY-MM-DD)")
    r.add_argument("--offline", action="store_true", help="use cached data (testing only)")
    sub.add_parser("verify")
    sub.add_parser("report")
    sub.add_parser("ai-check", help="one real AI trader call per sleeve into a throwaway ledger")
    a = p.parse_args(argv)

    if a.cmd == "fetch":
        from .live import refresh_all
        problems = refresh_all()
        print("\n".join(problems) or "all data refreshed and validated")
        return 1 if problems else 0
    if a.cmd == "backtest":
        from .research import report, run_sleeve
        from .config import SLEEVES
        pd.set_option("display.width", 200)
        for s in SLEEVES:
            print(report(run_sleeve(s, "development")).round(3).T, "\n")
        return 0
    if a.cmd == "run":
        from .live import run_daily
        out = run_daily(a.start, use_network=not a.offline)
        for r_ in out["results"]:
            print(f"{r_['arm']:<34} days={r_['days_processed']:<4} last={r_['last_date']}  equity={r_['equity']:,.2f}")
        return 0
    if a.cmd == "verify":
        from .ledger import Ledger
        from .live import LEDGER_DIR
        ok, msg = Ledger(LEDGER_DIR / "events.jsonl").verify()
        print(msg)
        return 0 if ok else 1
    if a.cmd == "ai-check":
        import json
        import tempfile
        from pathlib import Path
        from .config import SLEEVES
        from .ledger import Ledger
        from .overlay import ai_trader
        from .research import load_prices
        lg = Ledger(Path(tempfile.mkdtemp()) / "check.jsonl")   # never touches the real ledger
        ok = True
        for name, cfg in SLEEVES.items():
            closes = load_prices(cfg)[1][list(cfg.assets)]
            w, meta = ai_trader(cfg, closes, {}, lg)
            print(f"== {name}: status={meta['status']}")
            print(json.dumps({"weights": w, **meta}, indent=1)[:3000])
            ok = ok and w is not None
        for e in lg.events():
            if e["type"] == "ai_call":
                print("call:", {k: e["data"].get(k) for k in ("purpose", "ok", "model", "cost_usd", "error",
                                                               "web_search_requests", "searches", "usage")})
        return 0 if ok else 1
    if a.cmd == "report":
        from .report import write_report
        print(write_report())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

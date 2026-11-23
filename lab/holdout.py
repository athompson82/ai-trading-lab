"""One-time evaluation of the locked holdout period (HOLDOUT_START onward).

Rules (docs/PREREGISTRATION.md):
  - Runs only once the pre-registration is signed off: a git tag `prereg-v1`
    must exist and the working tree must be clean, so the exact code and
    config evaluated are on record.
  - Runs once per configuration. The result is written to the ledger and to
    reports/holdout.md. A second run refuses unless --force is given with a
    reason, and that reason is itself logged permanently.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import subprocess
import sys

import pandas as pd

from . import config, metrics, research
from .ledger import Ledger
from .live import LEDGER_DIR, ROOT

TRIALS_FILE = ROOT / "docs" / "trials.json"


def config_hash() -> str:
    src = inspect.getsource(config) + inspect.getsource(__import__("lab.strategies", fromlist=["x"])) \
        + inspect.getsource(__import__("lab.engine", fromlist=["x"]))
    return hashlib.sha256(src.encode()).hexdigest()


def _git(*args) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def evaluate(force_reason: str | None = None) -> str:
    if "prereg-v1" not in _git("tag", "--list").split():
        raise SystemExit("Refusing: pre-registration tag `prereg-v1` not found. Freeze the plan first.")
    if _git("status", "--porcelain", "--", "lab", "docs"):
        raise SystemExit("Refusing: uncommitted changes in lab/ or docs/.")
    lg = Ledger(LEDGER_DIR / "events.jsonl")
    chash = config_hash()
    prior = [e for e in lg.events() if e["type"] == "holdout_evaluation" and e["data"]["config_hash"] == chash]
    if prior and not force_reason:
        raise SystemExit(f"Refusing: holdout already evaluated for this config (seq {prior[0]['seq']}).")

    trials = json.loads(TRIALS_FILE.read_text())
    out = ["# Holdout evaluation (one-time)", "",
           f"Period: {config.HOLDOUT_START} to latest data. Code: {_git('rev-parse', 'HEAD')}.", ""]
    record = {"config_hash": chash, "commit": _git("rev-parse", "HEAD"), "force_reason": force_reason,
              "sleeves": {}}
    for name, cfg in config.SLEEVES.items():
        res = research.run_sleeve(name, "holdout")
        table = research.report(res)
        strat = res[name]
        r = strat.returns.iloc[1:]
        t = trials[name]
        n_trials = len(t["dev_sharpes_per_period"])
        var_sr = float(pd.Series(t["dev_sharpes_per_period"]).var(ddof=1)) if n_trials > 1 else 0.0
        benches = [b for b in res if b != name]
        boot = {b: metrics.bootstrap_sharpe_ci(r, cfg.periods_per_year, res[b].returns.iloc[1:]) for b in benches}
        evidence = {"psr_vs_0": metrics.psr(r), "dsr": metrics.dsr(r, n_trials, var_sr),
                    "n_trials": n_trials, "bootstrap": boot,
                    "concentration": metrics.concentration(r, strat.equity)}
        record["sleeves"][name] = {"table": json.loads(table.to_json(orient="index")), "evidence": evidence}
        out += [f"## {name}", "", table.round(4).T.to_markdown(), "",
                "```", json.dumps(evidence, indent=2, default=float), "```", ""]
    lg.append("holdout_evaluation", record)
    path = ROOT / "reports" / "holdout.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(out))
    return str(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", metavar="REASON")
    a = ap.parse_args()
    print(evaluate(a.force))
    sys.exit(0)

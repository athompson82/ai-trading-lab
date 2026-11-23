"""Hourly early-warning watcher. ALERTS ONLY: it never trades or changes any state.

Checks live prices and the health of the nightly run, and opens a GitHub issue
(which emails the repository owner) with a plain-English note when:
  - BTC or ETH moves 10% or more over the last 24 hours,
  - SPY (the S&P 500) is down 4% or more on the day,
  - the nightly run hasn't completed for more than 30 hours.
Each alert is raised at most once per UTC day.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "ledger" / "state"
LEDGER = ROOT / "ledger" / "events.jsonl"
CRYPTO_MOVE, SPY_DROP, STALE_HOURS = 0.10, -0.04, 30
DASH = "https://athompson82.github.io/ai-trading-lab/"


def _crypto_24h(product: str) -> float:
    s = requests.get(f"https://api.exchange.coinbase.com/products/{product}/stats", timeout=20).json()
    return float(s["last"]) / float(s["open"]) - 1


def _spy_day() -> float | None:
    key = os.environ.get("TIINGO_API_KEY", "proxy-injected")
    q = requests.get("https://api.tiingo.com/iex/SPY", headers={"Authorization": f"Token {key}"}, timeout=20).json()[0]
    last = q.get("tngoLast") or q.get("last")
    return (float(last) / float(q["prevClose"]) - 1) if last and q.get("prevClose") else None


def _last_marks() -> dict[str, dict]:
    marks = {}
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            e = json.loads(line)
            if e["type"] == "mark":
                marks[e["data"]["arm"]] = e["data"]
    return marks


def _holders(asset: str, marks: dict) -> str:
    rows = [(arm, m["weights"].get(asset, 0.0)) for arm, m in marks.items() if m["weights"].get(asset, 0.0) > 0.005]
    if not rows:
        return "None of our portfolios currently hold it, so this move doesn't affect them."
    parts = [f"{arm} holds {w:.0%}" for arm, w in sorted(rows, key=lambda r: -r[1])]
    return ("Exposure at the last close: " + "; ".join(parts) + ". A portfolio's move is roughly "
            "its holding share times the asset's move.")


def _last_run_age_hours() -> float | None:
    if not LEDGER.exists():
        return None
    last = None
    for line in LEDGER.read_text().splitlines():
        e = json.loads(line)
        if e["type"] == "run_end":
            last = e["ts"]
    if last is None:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 3600


def check() -> list[tuple[str, str]]:
    """Returns [(title, body)] for every alert condition currently true."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    marks = _last_marks()
    alerts = []
    for product, name in (("BTC-USD", "Bitcoin"), ("ETH-USD", "Ether")):
        try:
            mv = _crypto_24h(product)
        except Exception as exc:
            alerts.append((f"Alert {today}: live crypto prices unavailable",
                           f"Couldn't read {product} from Coinbase ({type(exc).__name__}). Usually temporary."))
            break
        if abs(mv) >= CRYPTO_MOVE:
            direction = "rose" if mv > 0 else "fell"
            alerts.append((f"Alert {today}: {name} {direction} {abs(mv):.0%} in 24 hours",
                           f"{name} {direction} {abs(mv):.1%} over the last 24 hours. {_holders(product, marks)}\n\n"
                           "**No action is needed.** The portfolios follow their fixed rules: the risk manager "
                           "and tonight's run handle it, including the drawdown brake if losses get large. "
                           "Large crypto moves happen several times a year."))
    try:
        spy = _spy_day()
    except Exception:
        spy = None
    if spy is not None and spy <= SPY_DROP:
        alerts.append((f"Alert {today}: S&P 500 down {abs(spy):.0%} today",
                       f"SPY is down {abs(spy):.1%} versus yesterday's close. {_holders('SPY', marks)}\n\n"
                       "**No action is needed.** Days like this are when diversification and trend rules are "
                       "meant to help; the nightly run applies the rules as usual."))
    age = _last_run_age_hours()
    if age is not None and age > STALE_HOURS:
        alerts.append((f"Alert {today}: nightly run overdue ({age:.0f} hours since last)",
                       "The nightly trading run hasn't completed recently. Check the Actions tab on GitHub; "
                       "missed days are caught up automatically on the next successful run, and Claude's weekly "
                       "check-in will investigate."))
    return [(t, b + f"\n\nDashboard: {DASH}\n\n_Automatic alert. Alerts never change any trade._") for t, b in alerts]


def post(alerts: list[tuple[str, str]]) -> None:
    for title, body in alerts:
        existing = subprocess.run(["gh", "issue", "list", "--state", "all", "--search", f'in:title "{title}"',
                                   "--json", "title"], capture_output=True, text=True, check=True).stdout
        if any(i["title"] == title for i in json.loads(existing or "[]")):
            continue  # already alerted today
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], check=True)


if __name__ == "__main__":
    found = check()
    for t, _ in found:
        print(t)
    if os.environ.get("GH_TOKEN"):
        post(found)
    print(f"{len(found)} alert condition(s)")

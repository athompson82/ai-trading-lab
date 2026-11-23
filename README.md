# AI Trading Lab

An autonomous **paper-trading** experiment to test, with honest statistics,
whether a systematic strategy (with or without AI assistance) beats passive
investing after realistic costs. Simulated capital only: there is no code
path that can place a real order.

- Plan and success criteria: [docs/PREREGISTRATION.md](docs/PREREGISTRATION.md)
- Why things are the way they are: [docs/DECISIONS.md](docs/DECISIONS.md)
- Current progress and next steps: [docs/STATUS.md](docs/STATUS.md)

## Layout

```
lab/config.py      all experiment parameters (sleeves, costs, holdout date)
lab/data.py        download + validate market data (Tiingo, Coinbase)
lab/strategies.py  signals: prices -> desired weights (pure functions)
lab/engine.py      risk manager, execution simulator, shared daily step, backtest
lab/live.py        daily forward paper-trading run over all arms
lab/overlay.py     AI risk overlay (reduce-only), forward-test only
lab/ledger.py      append-only hash-chained event ledger
lab/metrics.py     Sharpe, PSR, Deflated Sharpe, bootstrap, concentration
lab/holdout.py     one-time, logged evaluation of the locked holdout
lab/report.py      forward-test report from the ledger
ledger/            events.jsonl (audit trail) + per-arm state
data/raw/          cached market data used by each run (hash-logged)
```

## Usage

```
pip install -r requirements.txt
export TIINGO_API_KEY=...            # free key from tiingo.com
python -m lab.cli fetch              # refresh data
python -m lab.cli backtest           # development period only
python -m pytest -q                  # tests
python -m lab.cli run --start YYYY-MM-DD   # daily forward run (normally via GitHub Actions)
python -m lab.cli verify             # ledger integrity
python -m lab.cli report
```

## Dashboard

Published nightly to GitHub Pages: https://athompson82.github.io/ai-trading-lab/
(built by `lab/dashboard.py` from the ledger only).

## Automation

`.github/workflows/daily.yml` runs at 01:17 UTC every day. It needs the
repository secret `TIINGO_API_KEY` (and later `ANTHROPIC_API_KEY`) and the
repository variable `FORWARD_START`. It does nothing until `FORWARD_START`
is set. A failed run makes GitHub email the repository owner.

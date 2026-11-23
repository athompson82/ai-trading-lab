# Project status

_Last updated: 2026-11-23 (evening)_

## Where we are

Phase 1 (build) is mostly done. Development-period backtests are complete.
The holdout has **not** been looked at.

## Done

- Data pipeline: Tiingo ETFs (2006→), Coinbase BTC (2015→) and ETH (2016→), with validation checks.
- Strategy (trend + volatility targeting), independent risk manager, pessimistic execution simulator.
- Backtest engine and live daily runner sharing one step function (proven identical by test).
- Hash-chained ledger, catch-up after missed runs, run fingerprints (code commit + data hashes).
- Metrics: Sharpe, Sortino, drawdown, PSR, Deflated Sharpe, stationary bootstrap, concentration.
- Locked-holdout guard; trial registry (docs/trials.json: 5 ETF trials, 6 crypto trials).
- GitHub Actions: daily run (inactive until `FORWARD_START` is set) and tests on push.
- 14 automated tests passing.

## Development-period results (not the evidence; for sanity only)

| Sleeve | CAGR | Vol | Sharpe | Max DD | Benchmark Sharpe / Max DD |
|---|---|---|---|---|---|
| ETF trend (2007–2023) | 4.1% | 7.6% | 0.57 | −16% | SPY 0.54 / −55%; 60/40 0.63 / −34% |
| Crypto trend (2016–2023) | 42.6% | 36% | 1.17 | −52% | BTC 1.11 / −84%; 50/50 1.26 / −88% |

Reading: as the literature predicts, much smaller drawdowns at a similar
risk-adjusted return. No sign of a large edge, and none expected.

## Holdout results (2023-11-23 → 2026-11-20, evaluated once)

| | ETF trend | Crypto trend |
|---|---|---|
| Net CAGR (95% CI) | 10.3% (1.2% to 20.2%) | 11.0% (−27% to +71%) |
| Sharpe vs benchmarks | 1.08 vs SPY 1.05, 60/40 1.13 | 0.47 vs BTC 0.58, 50/50 0.41 |
| Max drawdown vs benchmarks | −8.9% vs −18.8% / −12.7% | −50% vs −53% / −61% |
| Q1 positive net return | Met | Met (CI includes large losses) |
| Q2 risk-adjusted edge | Not met: lower risk, no proven edge | Not met |
| Q3 consistency | Met | Not met (1 of 3 years positive; loss without best 10 days) |

Interpretation: the ETF sleeve does what trend following is known for: similar
risk-adjusted return to passive, with about half the drawdown. The crypto
sleeve showed no advantage after its ~0.75%/side costs. Under the
pre-registered rules, neither sleeve qualifies for a real-money pilot on
backtest evidence (Q2 fails for both). The forward test continues unchanged
to answer Q4 and the AI A/B question.

## Forward test schedule (proposed)

- Shakedown (unscored): 2026-11-24 → 2026-12-13
- Scored window: 2026-12-14 → 2027-03-14 (90 days); interim report 2027-02-12
- Optional extension to 6 months: 2027-06-14

## Next

1. ~~Move the code into the dedicated GitHub repository.~~ Done 2026-11-23 (public repo, `main`).
2. ~~Owner sign-off; tag `prereg-v1`.~~ Done 2026-11-23 (commit 55505a7). The tag exists locally; the session's git proxy refused to push tags, so the commit timestamp is the public record.
3. ~~One-time holdout evaluation.~~ Done 2026-11-23 → reports/holdout.md, ledger seq 1.
4. ~~AI overlay + AI trader arms.~~ Built 2026-11-23 (addendum A1). Waiting on a successful `ai-check` run with the owner's `ANTHROPIC_API_KEY` secret.
5. ~~Repository secret `TIINGO_API_KEY`.~~ Added by owner 2026-11-23; checked with the `data-check` workflow.
   Later: `ANTHROPIC_API_KEY`; set the `FORWARD_START` variable to begin the shakedown.

## Reporting

- Daily: dashboard (https://athompson82.github.io/ai-trading-lab/), rebuilt after every nightly run.
- Weekly (Mondays): `reports/weekly/`, also posted as a GitHub issue; candidate improvements are collected in `docs/IMPROVEMENTS.md`.
- Day 60 (2027-02-12): interim report, plus selection of version-2 candidates with the owner.

## Blocked on owner

- Set repository variable `FORWARD_START=2026-11-24` to start the shakedown.

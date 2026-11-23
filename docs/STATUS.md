# Project status

_Last updated: 2026-11-23_

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

## Next

1. Move the code into the dedicated GitHub repository (waiting on owner).
2. Owner sign-off of docs/PREREGISTRATION.md, then tag `prereg-v1`.
3. Run the one-time holdout evaluation.
4. AI overlay implementation (needs an Anthropic API key).
5. Repository secrets `TIINGO_API_KEY` (and later `ANTHROPIC_API_KEY`); set `FORWARD_START` to begin the shakedown.

## Blocked on owner

- Create a private GitHub repo `ai-trading-lab` and add it to the session.
- Sign off the pre-registration.
- Anthropic API key (for the AI arm). Spend cap about $30/month, as approved.

# Pre-registration: AI Trading Lab forward experiment

**Status: DRAFT, awaiting owner sign-off.** When signed off, this file and the
code are frozen with git tag `prereg-v1`. After that, any change to strategy,
risk, cost model, metrics or criteria is recorded in docs/DECISIONS.md and
starts a new version with its own evaluation clock. Results under the old
version are never re-scored under new rules.

## 1. What is being tested

| Arm | Description |
|---|---|
| `etf_trend` | Multi-asset ETF trend following with volatility targeting (SPY, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ), long or cash, US$5,000 |
| `etf_trend_ai` | Same, plus the AI risk overlay (may only reduce exposure) |
| `etf_bench_spy` | Passive: 100% SPY |
| `etf_bench_60_40` | Passive: 60% SPY / 40% AGG |
| `crypto_trend` | BTC/ETH trend following with volatility targeting, long or cash, US$5,000 |
| `crypto_trend_ai` | Same, plus the AI risk overlay |
| `crypto_bench_btc` | Passive: 100% BTC |
| `crypto_bench_btc_eth_50_50` | Passive: 50% BTC / 50% ETH |

Rules, parameters and costs are exactly as in `lab/config.py`, `lab/strategies.py`
and `lab/engine.py` at tag `prereg-v1`. No leverage, no short selling, no real money.

## 2. Evidence sources and their roles

1. **Holdout backtest** (2023-11-23 to tag date, about 3 years, never seen during development; run once): the main statistical evidence for questions 1–3.
2. **Forward paper test**: questions 4–5, plus a consistency check against the backtest.
   - Shakedown: 2 weeks from the first scheduled run. Not scored.
   - Scored window: 90 calendar days starting the Monday after shakedown (about 62 US trading days, 90 crypto days).
   - Interim report at day 60, final report at day 90.
   - Default: continue to 6 months unless the owner stops it.

## 3. Why short windows can't prove skill

The standard error of an annualised Sharpe ratio over 90 days is about ±2. The
forward test is therefore judged on consistency with the backtest and on
reliability, not on whether it happened to make money.

## 4. Success criteria (fixed now, applied as written)

**Q1. Positive returns after costs?**
Holdout net CAGR > 0, reported with a 95% stationary-bootstrap confidence
interval. Forward net return is reported but is not decisive on its own.

**Q2. Better than passive on a risk-adjusted basis?** Met for a sleeve only if all three hold:
- (a) Holdout Deflated Sharpe Ratio ≥ 0.95. This corrects for every trial in docs/trials.json.
- (b) Bootstrap probability that the strategy's holdout Sharpe beats each benchmark's ≥ 0.90.
- (c) Holdout maximum drawdown smaller than each benchmark's.

If only (c) holds, the finding is "lower risk, no proven risk-adjusted edge."

**Q3. Consistent rather than lucky?** Met if, in the holdout:
- the best 1% of days account for less than 50% of total profit,
- profit remains positive after removing the best 10 days, and
- at least 2 of the 3 holdout years are positive.

**Q4. Reliable and autonomous?** Met if, during the scored forward window:
- at least 99% of scheduled daily runs complete (catch-up runs are logged separately),
- zero ledger integrity failures,
- zero manual changes to positions or state,
- zero breaches of risk limits (gross ≤ 100%, per-asset caps), and
- replaying the backtest over the forward period from the same data reproduces the live equity to within 0.1%.

**Q5. Enough evidence for a small real-money pilot?** "Go" only if all of these hold:
- Q2 is met for that sleeve,
- Q3 and Q4 are met,
- the forward return is not below the 5th percentile of 90-day returns implied by block-bootstrapping that sleeve's development + holdout returns, and
- realised costs per trade are within the modelled cost assumptions.

Anything else is "no-go," and the report states which criterion failed and why.
A "go" is a recommendation only. Live trading needs separate authorisation and
security controls.

**AI overlay value.** Measured as the difference between each `_ai` arm and its
plain arm, over decisions made while the overlay was enabled (decisions logged
`not_configured` or `skipped_catchup_day` are excluded). The AI "adds value"
only if the `_ai` arm shows lower drawdown or volatility without lower return,
with bootstrap probability ≥ 0.90. With about 13 weekly decisions per sleeve,
the expected honest result is "insufficient evidence" unless the effect is large.

## 5. Change control during the scored window

- No changes to strategy, parameters, risk limits or cost model.
- Bug fixes are allowed only if they don't change any decision. A fix that
  would have changed decisions ends the scored window for that version, and
  the report says so.
- Data outages: no trading that day (logged); the next run catches up.

## 6. Sign-off

Owner: ____________________  Date: __________

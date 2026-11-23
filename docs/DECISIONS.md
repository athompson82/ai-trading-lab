# Decisions log

Every material decision, with its reason. Newest at the bottom. "Owner" says
who made it; decisions affecting cost, risk, scope, security or the agreed
objectives need the project owner's approval.

| ID | Date | Decision | Reason | Owner |
|---|---|---|---|---|
| D-001 | 2026-11-20 | Three-layer evidence design: historical backtest with a locked holdout → pre-registration → forward paper test (2-week unscored shakedown, 90-day scored window, 60-day interim, optional extension to 6 months). Replaces a single 60-day test. | A 60-day Sharpe ratio has a standard error of about ±2.5, so it can't separate skill from luck. The backtest carries the statistical weight; the forward test checks reliability and backtest-to-live consistency. | Approved by owner |
| D-002 | 2026-11-20 | Two sleeves: US ETFs and crypto (BTC, ETH), long or cash only. | Liquid, cheap to trade (ETFs), strong documented trend effects, uncorrelated markets. Forex, futures and options need leverage, which is excluded. | Approved by owner |
| D-003 | 2026-11-20 | Rules-based core. AI used as a risk-reduce-only overlay, tested as an A/B arm, forward-only. LLM spend ≤ ~$30/month. | No credible evidence that LLM price prediction gives a durable edge. Historical LLM backtests are contaminated because the model has seen the period. The A/B arm measures AI value directly. | Approved by owner |
| D-004 | 2026-11-20 | Simulated capital US$5,000 per sleeve (US$10,000 total). | Owner's choice (reduced from the proposed $25k). Costs are modelled at this size; minimum trade size $25. | Owner |
| D-005 | 2026-11-20 | Dedicated private repo; daily run on GitHub Actions; infrastructure budget ≤ $50/month. | Free at daily frequency; git history gives a second audit trail. | Approved by owner |
| D-006 | 2026-11-20 | Data: Tiingo (adjusted ETF prices, free key) and Coinbase public candles. | Stooq blocks automated access; Yahoo is unofficial and unreliable. Both chosen sources need no paid plan. | Claude (routine) |
| D-007 | 2026-11-23 | Canonical, untuned parameters: 1/3/6/12-month trend lookbacks, 3-month volatility, 6-month covariance, 10% (ETF) / 40% (crypto) volatility targets, per-asset caps 30% / 70%. | Parameter tuning is the main source of backtest overfitting. Textbook values keep the number of trials small and honest. | Claude (routine) |
| D-008 | 2026-11-23 | Fills at the next open after a decision, with pessimistic costs: ETF 8 bp per side, crypto 75 bp per side (Coinbase lowest-tier taker 0.60% + spread + slippage). Own simulator rather than broker paper fills. | Prevents look-ahead and avoids the optimistic fills of broker paper accounts. | Claude (routine) |
| D-009 | 2026-11-23 | Rebalance weekly (first trading day of the ISO week) with a 10% per-asset no-trade band, both sleeves. | Development testing showed daily re-sizing turnover of 8–13× per year; at crypto costs that drag outweighed any benefit. All variants tried are in docs/trials.json and count toward the Deflated Sharpe penalty. First (not last) trading day because a live system can't know in advance that a day is the week's last. | Claude (routine; logged as trials) |
| D-010 | 2026-11-23 | Drawdown brake measured from the trailing 12-month peak, not the all-time high. | The all-time-high version kept the crypto sleeve half-throttled for years after 2018, which defeats the purpose of a temporary brake. Logged as a trial. | Claude (routine; logged as trials) |
| D-011 | 2026-11-23 | Idle ETF-sleeve cash earns the T-bill ETF (BIL) return; idle crypto cash earns 0. | Benchmarks are fully invested. Ignoring cash yield would unfairly penalise a strategy that is often in cash. Crypto exchange USD balances typically earn nothing. | Claude (routine) |
| D-012 | 2026-11-23 | Holdout period = 2023-11-23 onward (3 years), evaluated once, only after the pre-registration is tagged `prereg-v1`. | Enforced in code (lab/holdout.py); repeat runs are refused or permanently logged. | Claude (routine) |
| D-013 | 2026-11-23 | The live runner shares the backtest's daily step function; a test asserts that replaying live over history equals the backtest exactly. | Removes the most common class of "backtest vs live" bugs. | Claude (routine) |
| D-014 | 2026-11-23 | Q3a amended before the plan was tagged: "best 1% of days < 50% of profit" becomes "no more reliant on the best 1% of days than the primary passive benchmark (SPY / BTC)". | The original rule failed for every portfolio in development data, including buy-and-hold SPY (128%) and BTC (288%), so it couldn't discriminate. Changed before anyone saw holdout data, so no bias. | Approved by owner |
| D-015 | 2026-11-23 | Pre-registration signed off and frozen as tag `prereg-v1`. | Owner approval. | Owner |
| D-016 | 2026-11-23 | Public dashboard on GitHub Pages, rebuilt nightly from the ledger only (read-only; imports no trading code). | Owner asked for visibility; free; no new services. Contains simulated trades only. | Approved by owner |

## Observations worth remembering

- **Rebalance-day sensitivity (2026-11-23).** Crypto's development Sharpe was 1.36 with Sunday rebalancing and 1.17 with Monday rebalancing, everything else identical. A single backtest number is fragile, which is why the Deflated Sharpe and bootstrap intervals are the evidence standard, not point estimates.

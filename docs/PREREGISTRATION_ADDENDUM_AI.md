# Pre-registration addendum A1: AI trader portfolios

**Status: approved by the project owner on 2026-11-23, written before the AI trader's first decision.**
It adds two arms. It changes nothing in `docs/PREREGISTRATION.md` (v1): the
eight original arms, their rules and their criteria stay exactly as frozen.

## 1. Question

Can an AI that reads current news, research and price trends every day make
better trading decisions than simple rules and passive investing, after costs?

## 2. Arms added

| Arm | Description |
|---|---|
| `etf_ai_trader` | US$5,000. Same 9 ETFs as `etf_trend`. |
| `crypto_ai_trader` | US$5,000. BTC and ETH, as `crypto_trend`. |

## 3. Rules

- **Decision.** Once a day, after the close, Claude (`claude-opus-5-5`, medium
  effort, web search capped at 10 calls with 4–6 distinct searches requested) receives:
  - the price-trend facts (1-week, 1-month, 3-month and 12-month returns, and volatility),
  - its current weights, and
  - the rules: long or cash only, per-asset caps (30% ETF / 70% crypto), total ≤ 100%, and the cost per trade.

  It returns target weights plus its rationale and the news it relied on. All of this is logged.
- **Same constraints as every arm.** The same risk manager (caps, no leverage,
  drawdown brake, data checks), the same 10% no-trade band and the same
  pessimistic cost model.
- **Timing (no peeking).** Decisions fill at the first market open after the
  moment of the AI call:
  - ETFs: the same day's US open.
  - Crypto: the following day's 00:00 UTC open. The current day's open has
    already passed when the call happens at about 01:17 UTC.
- **Fail-safe.** If the AI is unavailable, refuses, or returns an invalid
  answer, the arm keeps its current positions and the ledger records why. It
  never trades on a guess.
- **Budget.** AI calls stop when month-to-date AI spend reaches US$50,
  leaving headroom under the owner's US$60/month cap. The rest of the
  experiment is unaffected.
- **No tuning during the test.** The prompts, model and effort level in
  `lab/overlay.py` and `lab/ai.py` at the commit that introduces this file are
  fixed for the scored window. As with v1, any change starts a new version.

## 4. When it runs

- Starts on the first nightly run after the `ANTHROPIC_API_KEY` repository secret is configured.
- Shakedown and scored windows are the same as v1: scored 2026-12-14 → 2027-03-14, interim 2027-02-12.
- If the AI trader starts after 2026-12-14, its scored window is its first 90 days instead. The report states which applies.

## 5. How it will be judged

This is exploratory: about 60–90 trading decisions over 90 days cannot prove
skill, and no backtest is possible. Reported for each AI trader arm:

1. Net return, volatility, Sharpe ratio and maximum drawdown, against:
   - the plain trend arm,
   - the trend arm with the AI overlay, and
   - the passive benchmarks.
2. The bootstrap probability that its Sharpe ratio beats each comparator.
3. Turnover and costs paid. Cost drag is a known risk for a daily decision-maker.
4. Reliability: share of days with a valid AI decision, and API cost per month.

"The AI trader shows evidence of an advantage" is claimed only if **both** hold:

- its Sharpe ratio beats both the plain trend arm and the primary passive
  benchmark with bootstrap probability ≥ 0.90, and
- its maximum drawdown is no worse than the primary benchmark's.

Otherwise the result is reported as "no evidence of an advantage", with the
numbers. In no case is the AI trader on its own grounds for a real-money pilot
without a longer test.

**Expectation, stated in advance:** the research literature predicts no
reliable advantage and higher costs from more frequent trading. Claims of
multiplying money daily are not achievable and are explicitly not a goal
(D-018).

## 6. Report-only comparisons (added before the first AI decision, owner-approved)

These change nothing about how any portfolio trades. They are computed from
the ledger and price data by `lab/analysis.py`.

1. **Pure-AI shadow.** The AI trader's raw daily choices, replayed with the
   same timing and costs and only the hard limits (per-asset caps, no
   leverage). There is no drawdown brake. This shows the value of the AI's
   judgement on its own, alongside the real arm (AI inside the safe system).
2. **Random-guessing baseline.** 1,000 portfolios per sleeve that draw random
   weights over the same assets plus cash every week (uniform over the
   simplex, capped per asset). They use the same band and costs, with a fixed
   random seed (20261123). Every arm, and the pure-AI shadow, is reported with
   the share of random portfolios its return beat.

   Reading the result:
   - ≥ 95% is a suggestive sign of skill. Over 90 days it is not proof.
   - Around 50% is indistinguishable from luck.

## 7. Further report-only additions and the improvement process (2026-11-23, before the scored window)

3. **Cost sensitivity.** Each active arm's logged decisions are re-priced at
   lower trading costs, using the same decisions and timing:
   - Crypto: 0.45%, 0.30% and 0.10% per side.
   - ETF: 0.03% per side.

   Replaying at the modelled cost reproduces the live results to within $0.001,
   which validates the replay. The portfolios themselves always pay the
   modelled, pessimistic cost.
4. **"Buy the professionals" benchmark.** Buy-and-hold returns of the
   managed-futures ETFs DBMF and KMLM over the same period are ranked against
   the random baseline beside the ETF sleeve.
5. **Weekly review and improvement pipeline.**
   - Every Monday a report with figures, an AI analyst review, and candidate
     improvements is committed and posted as a GitHub issue.
   - Candidates are logged in `docs/IMPROVEMENTS.md` and are **never applied**
     to running portfolios.
   - At the day-60 interim the owner chooses which candidates become
     version-2 portfolios. Their rules and criteria are pre-registered before
     they start, and they run alongside version 1 on live data.

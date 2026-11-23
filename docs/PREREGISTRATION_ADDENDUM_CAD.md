# Pre-registration addendum A2: Canadian mirror (report-only)

**Approved by the owner on 2026-11-23, before the mirror had any data.**
It changes nothing about how any portfolio trades.

## Purpose
To show what the US ETF Trend Follower would deliver to a Canadian investor
holding Canadian-listed equivalents in CAD. This is the version a real pilot
would trade (docs/LIVE_PILOT_PLAN.md).

## Method (`lab/analysis.py`, `cad_mirror`)
- **Decisions.** The `etf_trend` arm's logged target weights and timing,
  unchanged.
- **Prices.** Each US fund's daily open and close × the USD/CAD rate (Tiingo
  FX). This assumes unhedged Canadian-listed funds that track the same index.
  The category mapping and example funds are listed in `CAD_MAP`.
- **Costs.**
  - 0.10% per side (commission-free Canadian discount broker plus wider
    spreads).
  - Broad commodities (DBC) have no close Canadian equivalent, so they carry
    an extra 1.5% per side for currency conversion.
- **Capital.** C$5,000. Idle cash earns the same T-bill proxy as the US arm,
  an approximation.
- **Comparison.** Buy & Hold S&P 500 and 60/40, both converted to CAD with
  the same costs.

## Limits
- Fund fees, US dividend withholding tax, and tracking differences between
  the Canadian and US funds are not modelled.
- Real Toronto-exchange prices were not available from our data provider.
  Before any real trade, verify each fund and compare against actual quotes.

## How it is used
It is reported on the dashboard, in the weekly report and in the Q&A page.
At the February interim and the final review, it informs the decision on a
real-money pilot. It is not a pass/fail criterion of plan v1.

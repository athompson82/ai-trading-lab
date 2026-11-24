# Signal Lab: public-information strategies (plan)

Approved by the owner 2026-11-23. Separate from the running experiment;
nothing here changes plan v1 or its addenda.

## Question
Can a strategy built on free public information beat passive investing
after realistic costs?

## Constraints
- US$0 extra monthly spend: SEC EDGAR (free), Tiingo free tier, GitHub
  Actions, existing API credits.
- Once-a-day, end-of-day timing. The target effects last weeks, so
  minute-level speed isn't needed.
- Paid data or an always-on server are proposed only if a signal proves
  itself, and only what that signal needs.

## Phase 1: insider buying (starts mid-December 2026, after the shakedown)
1. Data: SEC Form 4 open-market purchases by officers and directors.
   Universe: the stocks the Tiingo free tier allows (about the S&P 500).
2. Development test on pre-holdout history only, with costs and a trial
   registry. Then a one-time locked holdout test, as in plan v1.
3. Report survivorship-bias exposure from the free data.
4. If it survives: pre-register and run a US$5,000 paper portfolio of US
   stocks from the February interim, scored against Buy & Hold, the Trend
   Follower and the random baseline. If it fails: report it and stop or
   move on.

## Later phases (only if phase 1 justifies them)
- Post-earnings drift: EDGAR XBRL earnings data.
- AI reading 8-K filings (forward-only).
- Combine surviving signals.

## Needed from the owner at start
- Approval to add sec.gov hosts to the environment's network allowlist.
- A contact email for the SEC's required User-Agent (personal or
  dedicated; the owner's choice).

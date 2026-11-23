# Candidate improvements

Proposed by the weekly review; none are applied to running portfolios. Reviewed with the owner at the day-60 interim (2027-02-12). Chosen ideas become pre-registered version-2 portfolios that run alongside version 1.

| Proposed | Idea | Evidence | How to test | Status |
|---|---|---|---|---|
| 2026-11-23 | Make the report fill in every section even when there is no activity: list each portfolio with its starting value, 0 trades and 0 costs, and print 'not computed (n too small)' in the luck test. | The Performance table and the 'Better than luck?' section are both empty. An empty section looks the same whether nothing happened or the reporting is broken. | Generate next week's report and check that every portfolio from the pre-registration appears with a starting value, and that blank sections show an explicit status message. This needs no change to the portfolios themselves. | proposed |
| 2026-11-23 | Add a reconciliation line comparing ledger entry count with expected entries (setup records + runs + trades + AI decisions), and flag any mismatch. | The ledger holds 7 entries while runs, trades and AI decisions are all 0. Their origin is unexplained. | During shakedown, check that the reconciliation balances every week. Deliberately inject a test entry in a sandbox copy and confirm it gets flagged. | proposed |

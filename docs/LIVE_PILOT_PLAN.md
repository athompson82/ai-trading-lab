# Real-money pilot: outline for the end-of-test decision (not authorised)

Recorded 2026-11-23 at the owner's request. Nothing here is built or switched
on. Any real-money trading needs the owner's separate authorisation and the
security controls below (original brief; PREREGISTRATION.md §4 Q5).

## Gate
Proceed only if the pre-registered go/no-go criteria are met for that system.

If the outcome is "lower risk, no proven edge" (as the holdout showed for the
ETF trend follower), the simpler real-money option is a low-cost balanced or
managed-futures ETF held in a TFSA, with no system at all.

## Execution options (safest first)
1. **Manual.** Each week the system sends an order ticket in Canadian-listed
   funds, sized to the real account. The owner places the orders and records
   the fills. Start here.
2. **One-click approval.** Orders are pre-staged at a broker with an API
   (e.g. Interactive Brokers) and the owner approves them. Only after about 3
   months of option 1 working.
3. **Fully automatic.** Only after months of option 2, with all the controls
   below.

## Pilot design
- A separate account holding only money the owner can afford to lose
  (e.g. C$1,000–5,000).
- A TFSA where possible. Check with a tax professional: very frequent trading
  in a TFSA can be treated as business income. Weekly rebalancing carries
  less of this risk than daily.
- Canadian-listed equivalents (e.g. VFV for SPY; Canadian spot Bitcoin/Ether
  ETFs for crypto) to avoid 1–2% currency-conversion costs. Re-test the
  strategy with the substitutes before going live.
- Paper portfolios keep running as the control group. Real fills are
  compared with simulated fills (implementation shortfall).
- Kill switches: per-order size cap, a daily loss limit that pauses trading,
  and an owner-controlled stop.
- Options 2 and 3 only: API key can trade but never withdraw; it is stored in
  encrypted secrets; broker two-factor authentication on; security review
  before enabling.

## Timeline if results justify it
1. Mid-March 2027: final report; go/no-go decision.
2. Then 3–6 months of option 1 with a small amount.
3. Review real-vs-paper results.
4. Add money only after 6–12 months of real results.

## To build (start near the day-60 interim)
- Weekly order ticket in Canadian funds, at real account size.
- A simple way to record fills.
- Real-vs-paper tracking.

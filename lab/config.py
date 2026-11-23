"""Experiment configuration.

Everything that defines the experiment lives here, in one place, so it can be
frozen (pre-registered) and hashed. Parameters are canonical choices from the
published literature, NOT values tuned on our data: tuning is the main source
of overfitting, and fixed textbook parameters keep the number of strategies we
"tried" honest (see docs/DECISIONS.md, D-007).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Evaluation periods
# ---------------------------------------------------------------------------
# Data on/after HOLDOUT_START is the locked holdout. Research code cannot see it;
# it is evaluated exactly once (see lab/holdout.py).
HOLDOUT_START = "2023-11-23"
ETF_DATA_START = "2006-01-01"
CRYPTO_DATA_START = "2015-07-20"


@dataclass(frozen=True)
class CostModel:
    """Per-side trading costs, as fractions of traded notional.

    Deliberately pessimistic. A simulator that is too kind is the most common
    way paper trading misleads.
    """

    fee: float          # exchange / broker commission
    half_spread: float  # paying half the bid/ask spread
    slippage: float     # price moving against us while executing
    min_trade_usd: float  # skip trades smaller than this (would be noise + fees)

    @property
    def per_side(self) -> float:
        return self.fee + self.half_spread + self.slippage


# US ETFs: commission-free at retail brokers; the liquid ETFs below trade at
# ~1 bp spreads. We charge 2 bp half-spread + 5 bp slippage + 1 bp for
# regulatory fees on sells (applied to both sides for simplicity) = 8 bp/side.
ETF_COSTS = CostModel(fee=0.0001, half_spread=0.0002, slippage=0.0005, min_trade_usd=25.0)

# Crypto: Coinbase Advanced lowest-volume tier taker fee 0.60%. Plus 5 bp
# half-spread and 10 bp slippage = 0.75% per side. Kraken/maker orders are
# cheaper; we assume the worst realistic retail case.
CRYPTO_COSTS = CostModel(fee=0.0060, half_spread=0.0005, slippage=0.0010, min_trade_usd=25.0)


@dataclass(frozen=True)
class SleeveConfig:
    name: str
    assets: tuple[str, ...]
    capital: float
    costs: CostModel
    target_vol: float          # annualised portfolio volatility target
    max_weight: float          # per-asset cap
    max_gross: float = 1.0     # NO LEVERAGE: total exposure <= 100%
    drawdown_brake: float = 0.20   # if sleeve drawdown exceeds this, halve exposure
    brake_window: int = 252        # drawdown measured from the trailing 12-month peak
    rebalance_band: float = 0.10   # ignore weight changes smaller than this (cost control, D-009)
    periods_per_year: int = 252
    rebalance: str = "daily"     # "daily" or "weekly" (last trading day of the week)
    lookbacks_days: tuple[int, ...] = (21, 63, 126, 252)  # 1, 3, 6, 12 months
    vol_lookback: int = 63         # 3 months
    cov_lookback: int = 126        # 6 months
    cash_proxy: str | None = None  # instrument whose return idle cash earns
    extra: dict = field(default_factory=dict)


ETF_SLEEVE = SleeveConfig(
    name="etf_trend",
    # Diversified multi-asset universe: US large/small caps, developed and
    # emerging international, long and intermediate Treasuries, gold,
    # broad commodities, real estate.
    assets=("SPY", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"),
    capital=5_000.0,
    costs=ETF_COSTS,
    target_vol=0.10,
    max_weight=0.30,
    drawdown_brake=0.15,
    periods_per_year=252,
    rebalance="weekly",
    lookbacks_days=(21, 63, 126, 252),
    vol_lookback=63,
    cov_lookback=126,
    # Idle cash in a brokerage account can sit in a T-bill ETF. Benchmarks are
    # fully invested, so ignoring this would unfairly penalise a strategy that
    # is often partly in cash. BIL starts 2007-05; before that cash earns 0.
    cash_proxy="BIL",
)

CRYPTO_SLEEVE = SleeveConfig(
    name="crypto_trend",
    assets=("BTC-USD", "ETH-USD"),
    capital=5_000.0,
    costs=CRYPTO_COSTS,
    target_vol=0.40,
    max_weight=0.70,
    drawdown_brake=0.30,
    periods_per_year=365,
    brake_window=365,
    # Weekly, not daily: at ~0.75%/side crypto costs, daily re-sizing cost
    # more than it earned in development testing (D-009).
    rebalance="weekly",
    # Same rule as the ETF sleeve in calendar time (1, 3, 6, 12 months);
    # crypto trades 365 days a year.
    lookbacks_days=(30, 91, 182, 365),
    vol_lookback=91,
    cov_lookback=182,
    cash_proxy=None,  # assume USD cash on the exchange earns nothing
)

SLEEVES = {s.name: s for s in (ETF_SLEEVE, CRYPTO_SLEEVE)}

# Benchmark assets that must also be downloaded.
BENCHMARK_ETFS = ("SPY", "AGG", "BIL")

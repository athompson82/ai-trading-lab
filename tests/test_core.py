import json

import numpy as np
import pandas as pd
import pytest

from lab import config, research
from lab.config import CRYPTO_SLEEVE, ETF_SLEEVE, HOLDOUT_START
from lab.engine import Portfolio, apply_risk, execute, run_backtest
from lab.ledger import Ledger
from lab.strategies import trend_weights


@pytest.fixture(scope="module")
def etf_prices():
    return research.load_prices(ETF_SLEEVE)


# ----------------------------------------------------------------- look-ahead
@pytest.mark.parametrize("cfg", [ETF_SLEEVE, CRYPTO_SLEEVE])
def test_signals_use_no_future_data(cfg):
    _, closes, _ = research.load_prices(cfg)
    c = closes[list(cfg.assets)]
    full = trend_weights(c, cfg)
    for cut in (len(c) // 2, len(c) - 300, len(c) - 7):
        part = trend_weights(c.iloc[:cut], cfg)
        pd.testing.assert_frame_equal(part, full.iloc[:cut], check_freq=False)


def test_development_run_never_sees_holdout():
    res = research.run_sleeve("etf_trend", "development")
    for r in res.values():
        assert r.equity.index.max() < pd.Timestamp(HOLDOUT_START)


# ----------------------------------------------------------------- costs and risk
def test_round_trip_costs_match_model():
    cfg = CRYPTO_SLEEVE
    pf = Portfolio(cash=1000.0)
    execute(pf, {"BTC-USD": 0.5}, {"BTC-USD": 100.0}, pd.Timestamp("2024-01-01"), cfg)
    execute(pf, {"BTC-USD": 0.0}, {"BTC-USD": 100.0}, pd.Timestamp("2024-01-02"), cfg)
    lost = 1000.0 - pf.cash
    expected = 500 * cfg.costs.per_side * 2
    assert lost == pytest.approx(expected, rel=0.02)


def test_cannot_spend_more_than_cash():
    pf = Portfolio(cash=100.0)
    execute(pf, {"SPY": 1.0, "TLT": 1.0}, {"SPY": 10.0, "TLT": 10.0}, pd.Timestamp("2024-01-01"), ETF_SLEEVE)
    assert pf.cash >= -1e-9


def test_risk_layer_limits():
    d = apply_risk({a: 0.9 for a in ETF_SLEEVE.assets}, ETF_SLEEVE, drawdown=0.0,
                   data_ok={a: True for a in ETF_SLEEVE.assets})
    assert all(v <= ETF_SLEEVE.max_weight + 1e-12 for v in d.weights.values())
    assert sum(d.weights.values()) <= 1.0 + 1e-9


def test_overlay_can_only_reduce():
    base = {"BTC-USD": 0.5, "ETH-USD": 0.3}
    ok = {a: True for a in base}
    up = apply_risk(base, CRYPTO_SLEEVE, 0.0, ok, overlay={"BTC-USD": 3.0, "ETH-USD": 0.5})
    assert up.weights["BTC-USD"] == pytest.approx(0.5)
    assert up.weights["ETH-USD"] == pytest.approx(0.15)


def test_bad_data_freezes_asset():
    d = apply_risk({"BTC-USD": 0.5}, CRYPTO_SLEEVE, 0.0, {"BTC-USD": False})
    assert np.isnan(d.weights["BTC-USD"])


def test_drawdown_brake_halves_exposure():
    ok = {"BTC-USD": True, "ETH-USD": True}
    d = apply_risk({"BTC-USD": 0.4, "ETH-USD": 0.4}, CRYPTO_SLEEVE, 0.5, ok)
    assert sum(d.weights.values()) == pytest.approx(0.4)


@pytest.mark.parametrize("name", ["etf_trend", "crypto_trend"])
def test_backtest_no_leverage_no_negative_cash(name):
    r = research.run_sleeve(name, "development")[name]
    assert (r.weights.sum(axis=1) <= 1.0 + 0.02).all()  # small drift between rebalances allowed
    assert (r.equity > 0).all()


# ----------------------------------------------------------------- ledger
def test_ledger_detects_tampering(tmp_path):
    lg = Ledger(tmp_path / "e.jsonl")
    for i in range(5):
        lg.append("mark", {"equity": 100 + i})
    assert lg.verify() == (True, "ok")
    lines = (tmp_path / "e.jsonl").read_text().splitlines()
    ev = json.loads(lines[2])
    ev["data"]["equity"] = 999
    lines[2] = json.dumps(ev, sort_keys=True, separators=(",", ":"))
    (tmp_path / "e.jsonl").write_text("\n".join(lines) + "\n")
    ok, msg = lg.verify()
    assert not ok and "seq 3" in msg


# ----------------------------------------------------------------- live == backtest
@pytest.mark.parametrize("sleeve", ["etf_trend", "crypto_trend"])
def test_live_runner_reproduces_backtest(tmp_path, monkeypatch, sleeve):
    """The daily live run, replayed over history, must equal the backtest exactly."""
    from lab import live
    monkeypatch.setattr(live, "LEDGER_DIR", tmp_path)
    start = "2022-01-03"
    arm = next(a for a in live.arms() if a.name == sleeve)
    lg = Ledger(tmp_path / "events.jsonl")
    live.run_arm(arm, lg, start, {})
    st = json.loads((tmp_path / "state" / f"{sleeve}.json").read_text())
    live_eq = pd.Series([e for _, e in st["equity"]], index=pd.to_datetime([d for d, _ in st["equity"]]))

    cfg = config.SLEEVES[sleeve]
    opens, closes, cash = research.load_prices(cfg)
    cols = list(cfg.assets)
    w = trend_weights(closes[cols], cfg)
    bt = run_backtest(sleeve, opens[cols], closes[cols], w, cfg, cash_returns=cash, start=start)
    pd.testing.assert_series_equal(live_eq, bt.equity.reindex(live_eq.index), check_names=False,
                                   check_freq=False, rtol=1e-9)
    assert lg.verify()[0]

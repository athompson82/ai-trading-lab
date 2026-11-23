from lab import alerts


def test_alert_conditions(monkeypatch):
    monkeypatch.setattr(alerts, "_crypto_24h", lambda p: -0.12 if p == "BTC-USD" else 0.02)
    monkeypatch.setattr(alerts, "_spy_day", lambda: -0.05)
    monkeypatch.setattr(alerts, "_last_run_age_hours", lambda: 40.0)
    monkeypatch.setattr(alerts, "_last_marks", lambda: {"crypto_trend": {"weights": {"BTC-USD": 0.4}}})
    titles = [t for t, _ in alerts.check()]
    assert any("Bitcoin fell 12%" in t for t in titles)
    assert not any("Ether" in t for t in titles)
    assert any("S&P 500 down 5%" in t for t in titles)
    assert any("overdue" in t for t in titles)
    body = dict(alerts.check())[next(t for t in titles if "Bitcoin" in t)]
    assert "crypto_trend holds 40%" in body and "No action is needed" in body


def test_quiet_market_no_alerts(monkeypatch):
    monkeypatch.setattr(alerts, "_crypto_24h", lambda p: 0.03)
    monkeypatch.setattr(alerts, "_spy_day", lambda: -0.01)
    monkeypatch.setattr(alerts, "_last_run_age_hours", lambda: 5.0)
    assert alerts.check() == []

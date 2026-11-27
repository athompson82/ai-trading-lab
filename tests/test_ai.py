"""Tests of OUR handling of AI answers, using a stand-in client.

These never call Claude and never judge the AI's quality; they check clamping,
fail-safe behaviour, budget enforcement, logging and the timing rule.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from lab import ai, live, overlay, research
from lab.config import CRYPTO_SLEEVE, ETF_SLEEVE
from lab.ledger import Ledger


class FakeClient:
    def __init__(self, payload=None, stop_reason="end_turn", raise_exc=None):
        self.calls = 0
        self.payload, self.stop_reason, self.raise_exc = payload, stop_reason, raise_exc
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        assert kw["model"] == ai.MODEL
        assert kw["output_config"]["format"]["type"] == "json_schema"
        if self.raise_exc:
            raise self.raise_exc
        usage = NS(input_tokens=10_000, output_tokens=1_000, server_tool_use=NS(web_search_requests=3))
        content = [NS(type="text", text=json.dumps(self.payload))]
        return NS(content=content, stop_reason=self.stop_reason, usage=usage, model=ai.MODEL)


@pytest.fixture
def closes():
    return research.load_prices(CRYPTO_SLEEVE)[1][list(CRYPTO_SLEEVE.assets)]


def test_trader_weights_are_clamped_and_logged(tmp_path, closes):
    lg = Ledger(tmp_path / "e.jsonl")
    fake = FakeClient({"weights": {"BTC-USD": 5.0, "ETH-USD": -1}, "rationale": "x", "key_news": [],
                       "confidence": "low"})
    w, meta = overlay.ai_trader(CRYPTO_SLEEVE, closes, {}, lg, client=fake)
    assert w == {"BTC-USD": CRYPTO_SLEEVE.max_weight, "ETH-USD": 0.0}
    call = [e for e in lg.events() if e["type"] == "ai_call"][0]["data"]
    assert call["ok"] and call["cost_usd"] == pytest.approx(10_000 * 4 / 1e6 + 1_000 * 20 / 1e6 + 3 * 0.01)


def test_overlay_never_above_one(tmp_path, closes):
    lg = Ledger(tmp_path / "e.jsonl")
    fake = FakeClient({"multipliers": {"BTC-USD": 2.0, "ETH-USD": 0.25}, "rationale": "x", "key_news": [],
                       "confidence": "medium"})
    m, _ = overlay.risk_overlay(CRYPTO_SLEEVE, closes, {"BTC-USD": 0.4, "ETH-USD": 0.3}, lg, client=fake)
    assert m == {"BTC-USD": 1.0, "ETH-USD": 0.25}


@pytest.mark.parametrize("fake", [FakeClient(stop_reason="refusal", payload={}),
                                  FakeClient(raise_exc=RuntimeError("boom"))])
def test_failures_fail_safe(tmp_path, closes, fake):
    lg = Ledger(tmp_path / "e.jsonl")
    w, meta = overlay.ai_trader(CRYPTO_SLEEVE, closes, {}, lg, client=fake)
    assert w is None and meta["status"]
    assert lg.events()[-1]["data"]["ok"] is False


def test_no_key_means_not_configured(tmp_path, closes, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    w, meta = overlay.ai_trader(CRYPTO_SLEEVE, closes, {}, Ledger(tmp_path / "e.jsonl"))
    assert w is None and meta["status"] == "not_configured"


def test_budget_guard_blocks_calls(tmp_path, closes):
    lg = Ledger(tmp_path / "e.jsonl")
    lg.append("ai_call", {"ok": True, "cost_usd": ai.MONTHLY_BUDGET_USD + 1})
    fake = FakeClient({"weights": {}, "rationale": "", "key_news": [], "confidence": "low"})
    w, meta = overlay.ai_trader(CRYPTO_SLEEVE, closes, {}, lg, client=fake)
    assert w is None and "budget_exhausted" in meta["status"] and fake.calls == 0


def test_ai_timing_rule():
    at = datetime(2026, 11, 25, 1, 17, tzinfo=timezone.utc)
    assert live._first_executable_day(CRYPTO_SLEEVE, at) == "2026-11-26"   # 00:00 open already passed
    assert live._first_executable_day(ETF_SLEEVE, at) == "2026-11-25"      # US open still ahead


def test_ai_trader_arm_end_to_end(tmp_path, monkeypatch):
    """Decision on the latest day, executed no earlier than the timing rule allows."""
    monkeypatch.setattr(live, "LEDGER_DIR", tmp_path)
    arm = next(a for a in live.arms() if a.name == "crypto_ai_trader")
    lg = Ledger(tmp_path / "events.jsonl")
    fake = FakeClient({"weights": {"BTC-USD": 0.5, "ETH-USD": 0.2}, "rationale": "r", "key_news": ["n"],
                       "confidence": "medium"})
    _, closes = None, research.load_prices(CRYPTO_SLEEVE)[1]
    last = closes.index[-1]
    start = str((last - pd.Timedelta(days=2)).date())
    now = datetime.combine((last + pd.Timedelta(days=1)).date(), datetime.min.time(), timezone.utc).replace(hour=1)
    live.run_arm(arm, lg, start, ai_client=fake, now=now)
    st = json.loads((tmp_path / "state" / "crypto_ai_trader.json").read_text())
    assert fake.calls == 1                       # only the latest day decides
    assert st["pending"]["BTC-USD"] == pytest.approx(0.5)
    assert st["pending_not_before"] == str((last + pd.Timedelta(days=2)).date())
    assert not [e for e in lg.events() if e["type"] == "fill"]
    assert lg.verify()[0]


def test_weekly_report_builds_and_logs_candidates(tmp_path, monkeypatch):
    """Weekly report from a replayed ledger; AI review via stand-in client; candidates only logged."""
    from lab import dashboard, weekly
    monkeypatch.setattr(live, "LEDGER_DIR", tmp_path)
    lg = Ledger(tmp_path / "events.jsonl")
    for a in live.arms():
        if a.kind != "ai_trader":
            live.run_arm(a, lg, "2026-10-01")
    for mod in (dashboard, weekly):
        monkeypatch.setattr(mod, "LEDGER", tmp_path / "events.jsonl")
    monkeypatch.setattr(dashboard, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(weekly, "STATE", tmp_path / "state")
    monkeypatch.setattr(weekly, "OUT_DIR", tmp_path / "weekly")
    monkeypatch.setattr(weekly, "IMPROVEMENTS", tmp_path / "IMPROVEMENTS.md")
    monkeypatch.setenv("FORWARD_START", "2026-10-01")
    review = {"plain_english": "pe", "summary": "s", "strengths": ["a"], "weaknesses": ["b"], "caveats": "c",
              "candidate_improvements": [{"idea": "cheaper crypto execution", "evidence": "e", "how_to_test": "t"}]}
    text, path = weekly.build(use_ai=True, client=FakeClient(review))
    assert path.exists() and "Better than luck?" in text and "cheaper crypto execution" in text
    assert "## In plain English" in text
    assert "| proposed |" in (tmp_path / "IMPROVEMENTS.md").read_text()
    assert Ledger(tmp_path / "events.jsonl").verify()[0]


def test_ai_trader_sees_post_fill_holdings(tmp_path, monkeypatch):
    """D-035: on day 2 the AI must be told what it bought at that day's open, not 'all cash'."""
    monkeypatch.setattr(live, "LEDGER_DIR", tmp_path)
    arm = next(a for a in live.arms() if a.name == "etf_ai_trader")
    lg = Ledger(tmp_path / "events.jsonl")
    prompts = []

    class Capturing(FakeClient):
        def _create(self, **kw):
            prompts.append(kw["messages"][0]["content"])
            return super()._create(**kw)

    fake = Capturing({"weights": {"SPY": 0.3, "IEF": 0.3}, "rationale": "r", "key_news": [], "confidence": "low"})
    closes = research.load_prices(ETF_SLEEVE)[1]
    d1, d2 = closes.index[-3], closes.index[-2]
    # Day 1: decide (decision executes at day 2's open). Day 2: AI decides again.
    live.run_arm(arm, lg, str(d1.date()), ai_client=fake,
                 now=datetime.combine((d1 + pd.Timedelta(days=1)).date(), datetime.min.time(), timezone.utc).replace(hour=1))
    st = json.loads((tmp_path / "state" / "etf_ai_trader.json").read_text())
    st["equity"] = st["equity"][:1]; st["last_date"] = str(d1.date())
    (tmp_path / "state" / "etf_ai_trader.json").write_text(json.dumps(st))
    import lab.data as data_mod
    real_panel = data_mod.panel
    monkeypatch.setattr(data_mod, "panel", lambda syms, field="close": real_panel(syms, field).loc[:d2])
    live.run_arm(arm, lg, str(d1.date()), ai_client=fake,
                 now=datetime.combine((d2 + pd.Timedelta(days=1)).date(), datetime.min.time(), timezone.utc).replace(hour=1))
    assert len(prompts) == 2
    spy_line = next(l for l in prompts[1].splitlines() if l.startswith("SPY |"))
    assert not spy_line.rstrip().endswith("| 0%"), spy_line   # holds ~30% SPY after day-2 open fills

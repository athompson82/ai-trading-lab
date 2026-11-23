"""Claude API access for the AI arms: the risk overlay and the AI trader.

One function, `decide()`, sends a prompt with live web search and receives a
strictly structured JSON answer. Every call is logged to the ledger with its
token usage and estimated cost; a month-to-date budget guard stops AI calls
before the agreed cap is reached (the AI arms then keep their previous
positions, and the ledger says why).

Forward-test only: an LLM has read about the past, so any historical test of
these arms would be contaminated by hindsight.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_SEARCHES = 5
# US$ per million tokens / per search for MODEL (platform pricing, 2026-11).
PRICE_IN, PRICE_OUT, PRICE_SEARCH = 4.00, 20.00, 0.01
# Owner-approved AI cap is $60/month (D-017). Stop at $50 to leave headroom.
MONTHLY_BUDGET_USD = 50.0


class AIUnavailable(RuntimeError):
    """The AI could not produce a usable decision; callers fall back safely."""


@dataclass
class AIResult:
    output: dict
    meta: dict


def month_to_date_cost(events: list[dict]) -> float:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return sum(e["data"].get("cost_usd", 0.0) for e in events
               if e["type"] == "ai_call" and e["ts"].startswith(month))


def _estimate_cost(usage) -> float:
    searches = 0
    stu = getattr(usage, "server_tool_use", None)
    if stu is not None:
        searches = getattr(stu, "web_search_requests", 0) or 0
    return (usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1e6 + searches * PRICE_SEARCH


def decide(system: str, prompt: str, schema: dict, ledger, purpose: str, client=None) -> AIResult:
    """Ask Claude for a structured decision, using web search for current news.

    Raises AIUnavailable (never returns a made-up answer) when there is no key,
    the budget is spent, the request fails or the answer doesn't validate.
    """
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise AIUnavailable("not_configured")
        import anthropic
        client = anthropic.Anthropic(max_retries=3, timeout=600)
    spent = month_to_date_cost(ledger.events())
    if spent >= MONTHLY_BUDGET_USD:
        raise AIUnavailable(f"budget_exhausted (${spent:.2f} this month)")

    messages = [{"role": "user", "content": prompt}]
    cost, usage_log, response = 0.0, [], None
    try:
        for _ in range(4):  # resume server-tool pauses a few times at most
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=system,
                messages=messages,
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES}],
                output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            c = _estimate_cost(response.usage)
            cost += c
            usage_log.append({"in": response.usage.input_tokens, "out": response.usage.output_tokens,
                              "cost_usd": round(c, 4)})
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            break
    except Exception as exc:  # network/API errors: fail safe, record, don't guess
        ledger.append("ai_call", {"purpose": purpose, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:500],
                                  "cost_usd": round(cost, 4), "usage": usage_log})
        raise AIUnavailable(f"api_error: {type(exc).__name__}") from exc

    meta = {"purpose": purpose, "model": getattr(response, "model", MODEL), "stop_reason": response.stop_reason,
            "cost_usd": round(cost, 4), "usage": usage_log}
    if response.stop_reason != "end_turn":
        ledger.append("ai_call", {**meta, "ok": False, "error": f"stop_reason={response.stop_reason}"})
        raise AIUnavailable(f"stop_reason={response.stop_reason}")
    text = next((b.text for b in reversed(response.content) if b.type == "text"), None)
    try:
        output = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        ledger.append("ai_call", {**meta, "ok": False, "error": "invalid_json"})
        raise AIUnavailable("invalid_json") from exc
    sources = []
    for b in response.content:
        if b.type == "web_search_tool_result" and isinstance(b.content, list):
            sources += [{"title": r.title, "url": r.url} for r in b.content[:5]]
    meta["sources"] = sources[:15]
    ledger.append("ai_call", {**meta, "ok": True, "output": output})
    return AIResult(output, meta)

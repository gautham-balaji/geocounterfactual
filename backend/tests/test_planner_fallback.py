"""Planner fail-fast: an LLM outage must not stall the pipeline.

During a Gemini 503 storm the planner made four calls of ~12 s each and held
the whole run for 51 s before falling back to keyword parsing, with nothing in
the UI terminal. An availability error must now end the LLM stage after one
call, while a schema rejection must still reach the raw-JSON path, which is
what that path exists for.

Offline: the client is replaced with a fake, so this needs no API key and
cannot be flaky against the live service.

Run:  python -m backend.tests.test_planner_fallback
"""

from __future__ import annotations

import sys

import langchain_google_genai

from backend.agents import planner
from backend.config import settings

GOOD_JSON = ('{"structure_type": "check_dam", "count": 3, '
             '"placement_strategy": "stream_channel", "buffer_radius_m": 200, '
             '"impound_height_m": 2.0, "reasoning": "test"}')


class _Reply:
    def __init__(self, content):
        self.content = content


def _fake_client(structured_error=None, raw_error=None, raw_content=GOOD_JSON):
    """A ChatGoogleGenerativeAI stand-in that counts every call made."""
    calls = {"n": 0, "kwargs": None}

    class FakeLLM:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        def with_structured_output(self, _schema):
            class Structured:
                def invoke(self, _prompt):
                    calls["n"] += 1
                    raise structured_error
            return Structured()

        def invoke(self, _prompt):
            calls["n"] += 1
            if raw_error is not None:
                raise raw_error
            return _Reply(raw_content)

    return FakeLLM, calls


def _run_with(fake_cls):
    original = langchain_google_genai.ChatGoogleGenerativeAI
    original_key = settings.gemini_api_key
    langchain_google_genai.ChatGoogleGenerativeAI = fake_cls
    settings.gemini_api_key = "test-key"
    try:
        return planner.parse_intent_with_gemini("Build 3 check-dams", 5)
    finally:
        langchain_google_genai.ChatGoogleGenerativeAI = original
        settings.gemini_api_key = original_key


def test_outage_fails_fast():
    outage = RuntimeError("503 UNAVAILABLE. This model is currently "
                          "experiencing high demand.")
    fake, calls = _fake_client(structured_error=outage, raw_error=outage)
    plan, err = _run_with(fake)
    print(f"  503 outage      : {calls['n']} call(s), plan={plan}, "
          f"err={err[:40]}...")
    assert plan is None, "An outage must hand over to the keyword fallback"
    assert calls["n"] == 1, (f"An outage must end the LLM stage after one "
                             f"call, made {calls['n']}")


def test_rate_limit_fails_fast():
    limited = RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
    fake, calls = _fake_client(structured_error=limited, raw_error=limited)
    plan, _ = _run_with(fake)
    print(f"  429 rate limit  : {calls['n']} call(s), plan={plan}")
    assert plan is None and calls["n"] == 1


def test_schema_rejection_still_tries_raw_json():
    # Not an outage: the model rejected the schema. The raw-JSON path is
    # exactly for this, and must still run and succeed.
    rejected = ValueError("Invalid JSON schema for response_schema")
    fake, calls = _fake_client(structured_error=rejected)
    plan, err = _run_with(fake)
    print(f"  schema rejection: {calls['n']} call(s), "
          f"plan={plan.structure_type if plan else None}")
    assert plan is not None and err is None, \
        "A schema rejection must fall through to the raw-JSON path"
    assert calls["n"] == 2


def test_client_is_bounded():
    fake, calls = _fake_client(structured_error=RuntimeError("503"))
    _run_with(fake)
    kw = calls["kwargs"]
    print(f"  client config   : timeout={kw.get('timeout')} "
          f"max_retries={kw.get('max_retries')}")
    assert kw.get("timeout") == 20
    assert kw.get("max_retries") == 1


def run() -> int:
    print("=" * 70)
    print("PLANNER FAIL-FAST: an LLM outage must not stall the pipeline")
    print("=" * 70)
    test_outage_fails_fast()
    test_rate_limit_fails_fast()
    test_schema_rejection_still_tries_raw_json()
    test_client_is_bounded()
    print("-" * 70)
    print("Outages end after one call; schema rejections still reach raw JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(run())

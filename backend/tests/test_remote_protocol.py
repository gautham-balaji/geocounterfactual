"""Remote generator protocol 2: adapter control, seeding, feedback.

The ablation's base arms run on the Colab T4 with the adapter switched off
per request. Every way that can silently go wrong is checked here:

  * an outdated server drops use_lora (pydantic ignores unknown fields) and
    runs the adapter anyway -- the base arm becomes a LoRA arm;
  * the server runs a different adapter state than requested;
  * critic rejections are sent one pass at a time, so water retracted
    earlier reappears and the gating arms oscillate instead of converging.

Offline: HTTP and the diffusion pipeline are both faked.

Run:  python -m backend.tests.test_remote_protocol
"""

from __future__ import annotations

import sys

import numpy as np

import backend.generator.remote_client as rc
from backend.generator.base import GenerationRequest

SHAPE = (16, 16)


def _request(iteration=0, feedback=None):
    return GenerationRequest(
        baseline_rgb=np.zeros((*SHAPE, 3), np.float32),
        conditioning_map=np.zeros((*SHAPE, 5), np.float32),
        change_mask=np.ones(SHAPE, np.float32),
        dynamics_guidance={}, prompt="p", iteration=iteration,
        feedback_mask=feedback)


class _Response:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def _fake_server(reply_extra):
    """Patch requests.post; return the list every payload is recorded in."""
    sent = []

    def post(url, json=None, timeout=None, headers=None):
        sent.append(json)
        body = {"rgb": rc.encode_array(np.zeros((*SHAPE, 3), np.float32)),
                "ndvi": None, "notes": [], "device": "cuda"}
        body.update(reply_extra(json))
        return _Response(body)

    rc.requests.post = post
    return sent


def _client(**kw):
    return rc.RemoteGenerator(url="http://fake", **kw)


def test_payload_carries_adapter_and_seed():
    sent = _fake_server(lambda p: {"adapter_active": p.get("use_lora")})
    _client(use_lora=False, seed=7).generate(_request())
    assert sent[0]["use_lora"] is False and sent[0]["seed"] == 7
    print("  payload        : use_lora and seed sent")


def test_outdated_server_is_refused_without_retry():
    # Protocol-1 server: no adapter_active in the reply, adapter ran anyway.
    sent = _fake_server(lambda p: {})
    try:
        _client(use_lora=False).generate(_request())
    except rc.AdapterMismatchError as exc:
        print(f"  outdated server: refused after {len(sent)} call(s)")
        assert len(sent) == 1, "a deterministic mismatch must not be retried"
        assert "protocol" in str(exc)
        return
    raise AssertionError("an outdated server's reply was accepted for a "
                         "base-model request")


def test_wrong_adapter_state_is_refused():
    _fake_server(lambda p: {"adapter_active": True})
    try:
        _client(use_lora=False).generate(_request())
    except rc.AdapterMismatchError:
        print("  wrong state    : refused")
        return
    raise AssertionError("a reply that ran the adapter was accepted for a "
                         "base-model request")


def test_demo_path_unaffected():
    # use_lora=None is the normal app path: an old server must still work.
    sent = _fake_server(lambda p: {})
    _client().generate(_request())
    assert "use_lora" not in sent[0] and "seed" not in sent[0]
    print("  demo path      : old server still accepted when unpinned")


def test_feedback_accumulates_and_resets():
    sent = _fake_server(lambda p: {"adapter_active": True})
    client = _client(use_lora=True)
    a = np.zeros(SHAPE, bool); a[0, 0] = True
    b = np.zeros(SHAPE, bool); b[5, 5] = True

    client.generate(_request(0))
    client.generate(_request(1, a))
    client.generate(_request(2, b))
    client.generate(_request(0))                  # a new run

    def mask(i):
        payload = sent[i]["feedback_mask"]
        return None if payload is None else rc.decode_array(payload) > 0

    assert mask(0) is None
    assert mask(1).sum() == 1 and mask(1)[0, 0]
    assert mask(2).sum() == 2 and mask(2)[0, 0] and mask(2)[5, 5], \
        "the second rejection must include the first"
    assert mask(3) is None, "a new run must not inherit old rejections"
    print("  feedback       : cumulative within a run, reset between runs")


def test_server_toggles_and_echoes():
    import backend.generator.colab_server as cs

    calls = []

    class FakePipe:
        def enable_lora(self): calls.append("enable")
        def disable_lora(self): calls.append("disable")
        def set_adapters(self, names, adapter_weights): calls.append("scale")

    original = (cs.get_pipeline, cs._generate, cs._LORA_LOADED)
    cs.get_pipeline = lambda: FakePipe()
    cs._generate = lambda req: {"rgb": None}
    try:
        def req(use_lora):
            return cs.GenerateRequest(
                prompt="p", use_lora=use_lora, seed=9,
                baseline_rgb=cs.ArrayPayload(dtype="float32", shape=[1],
                                             data=""),
                conditioning_map=cs.ArrayPayload(dtype="float32", shape=[1],
                                                 data=""),
                change_mask=cs.ArrayPayload(dtype="float32", shape=[1],
                                            data=""))

        cs._LORA_LOADED = True
        off = cs.generate(req(False))
        on = cs.generate(req(True))
        default = cs.generate(req(None))
        assert off["adapter_active"] is False and calls[0] == "disable"
        assert on["adapter_active"] is True and calls[1:3] == ["enable", "scale"]
        assert default["adapter_active"] is True
        assert off["seed"] == 9 and off["protocol"] == cs.PROTOCOL

        cs._LORA_LOADED = False
        try:
            cs.generate(req(True))
        except cs.HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("use_lora=True without an adapter must 409")
        assert cs.generate(req(None))["adapter_active"] is False
        print("  colab server   : toggles adapter, echoes state, 409s on "
              "a missing adapter")
    finally:
        cs.get_pipeline, cs._generate, cs._LORA_LOADED = original


def run() -> int:
    original_post = rc.requests.post
    print("=" * 70)
    print("REMOTE PROTOCOL 2: per-request adapter, seed, cumulative feedback")
    print("=" * 70)
    try:
        test_payload_carries_adapter_and_seed()
        test_outdated_server_is_refused_without_retry()
        test_wrong_adapter_state_is_refused()
        test_demo_path_unaffected()
        test_feedback_accumulates_and_resets()
        test_server_toggles_and_echoes()
    finally:
        rc.requests.post = original_post
    print("-" * 70)
    print("A base arm cannot silently run the adapter.")
    return 0


if __name__ == "__main__":
    sys.exit(run())

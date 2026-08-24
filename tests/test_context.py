from __future__ import annotations

from wizards_pick.context import (
    budget_messages,
    estimate_tokens,
    truncate_to_tokens,
)


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("x" * 400) == 100


def test_truncate_keeps_head_and_tail_with_marker():
    text = "HEAD" + ("m" * 5000) + "TAIL"
    trimmed = truncate_to_tokens(text, 50)
    assert trimmed.startswith("HEAD")
    assert trimmed.endswith("TAIL")
    assert "omitted" in trimmed
    assert len(trimmed) < len(text)


def test_truncate_noop_when_within_budget():
    assert truncate_to_tokens("short", 100) == "short"


def test_truncate_zero_budget_is_empty():
    assert truncate_to_tokens("anything", 0) == ""


def _msgs(prefix, n, size=100):
    return [{"role": "user", "content": f"{prefix}{i}-" + "x" * size} for i in range(n)]


def test_budget_always_keeps_leading_and_trailing():
    leading = [{"role": "system", "content": "system"}]
    trailing = [{"role": "user", "content": "current turn"}]
    out = budget_messages(
        leading,
        _msgs("h", 100),
        trailing,
        context_window_tokens=200,
        response_reserve_tokens=20,
        per_message_cap_tokens=40,
    )
    assert out[0] == {"role": "system", "content": "system"}
    assert out[-1] == {"role": "user", "content": "current turn"}
    assert len(out) < 102  # history was trimmed


def test_budget_keeps_the_most_recent_history():
    leading = [{"role": "system", "content": "s"}]
    history = _msgs("h", 40, size=40)
    out = budget_messages(
        leading,
        history,
        context_window_tokens=300,
        response_reserve_tokens=20,
    )
    kept = [m for m in out if m["content"].startswith("h")]
    # The kept window must be a contiguous suffix ending at the newest message.
    assert kept[-1] == history[-1]
    assert kept == history[len(history) - len(kept) :]


def test_budget_truncates_a_single_oversized_message():
    leading = [{"role": "system", "content": "s"}]
    huge = [{"role": "user", "content": "Z" * 100_000}]
    out = budget_messages(
        leading,
        huge,
        context_window_tokens=2000,
        response_reserve_tokens=100,
    )
    assert len(out) == 2
    assert len(out[1]["content"]) < 100_000
    assert "omitted" in out[1]["content"]


def test_budget_does_not_mutate_inputs():
    history = [{"role": "user", "content": "Q" * 50_000}]
    original = history[0]["content"]
    budget_messages([], history, context_window_tokens=500, response_reserve_tokens=50)
    assert history[0]["content"] == original

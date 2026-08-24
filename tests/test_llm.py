from __future__ import annotations

import json

from wizards_pick import llm
from wizards_pick.llm import (
    SYSTEM_PROMPT,
    LLMClient,
    build_messages,
    extract_command_proposal,
    extract_findings,
    extract_json_payloads,
    scope_context,
)
from wizards_pick.models import Scope
from wizards_pick.paths import RESPONSE_RESERVE_TOKENS


class _FakeResponse:
    """Minimal stand-in for an HTTP response: a context manager over byte lines."""

    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def __iter__(self):
        return iter(self._lines)


def test_extract_json_payloads_from_fence_and_bare_and_dedup():
    text = (
        'prose\n```json\n{"type":"command_proposal","commands":["id"]}\n```\n'
        'and inline {"type":"finding","title":"X"} plus dup '
        '{"type":"command_proposal","commands":["id"]}'
    )
    payloads = extract_json_payloads(text)
    types = sorted(p.get("type") for p in payloads)
    assert types == ["command_proposal", "finding"]  # duplicate collapsed


def test_extract_json_payloads_ignores_non_objects():
    assert extract_json_payloads("no json here, just [1,2,3] and 42") == []


def test_extract_command_proposal_prefers_json_block():
    text = (
        '```json\n{"type":"command_proposal","phase":"Scanning",'
        '"commands":["nmap -sV 10.0.0.5"],"risk_level":"low"}\n```'
    )
    proposal = extract_command_proposal(text)
    assert proposal is not None
    assert proposal.phase == "Scanning"
    assert proposal.commands == ["nmap -sV 10.0.0.5"]


def test_extract_command_proposal_accepts_string_command_field():
    proposal = extract_command_proposal('{"type":"command_proposal","command":"whoami"}')
    assert proposal is not None
    assert proposal.commands == ["whoami"]


def test_extract_command_proposal_falls_back_to_shell_fence():
    text = "Let's map the host.\n```bash\n# enumerate\nnmap -sV \\\n  -p- 10.0.0.5\n```\n"
    proposal = extract_command_proposal(text)
    assert proposal is not None
    assert proposal.commands == ["nmap -sV -p- 10.0.0.5"]


def test_fenced_fallback_skips_prose_lines():
    text = (
        "```sh\n"
        "This is a full sentence describing the plan in detail.\n"
        "gobuster dir -u http://10.0.0.5 -w list.txt\n"
        "```"
    )
    proposal = extract_command_proposal(text)
    assert proposal is not None
    assert proposal.commands == ["gobuster dir -u http://10.0.0.5 -w list.txt"]


def test_fenced_fallback_reads_markdown_headings_for_metadata():
    text = "# Phase: Recon\n```bash\nwhoami\n```"
    proposal = extract_command_proposal(text)
    assert proposal is not None
    assert proposal.phase == "Recon"


def test_extract_command_proposal_returns_none_without_commands():
    assert extract_command_proposal("Just some analysis, no commands or fences.") is None


def test_non_shell_fence_is_not_a_command():
    assert extract_command_proposal("```python\nprint('hi')\n```") is None


def test_extract_findings():
    text = (
        '```json\n{"type":"finding","title":"SQL Injection","severity":"high",'
        '"evidence":"UNION works"}\n```'
    )
    findings = extract_findings(text)
    assert len(findings) == 1
    assert findings[0].title == "SQL Injection"
    assert findings[0].severity.value == "high"


def test_scope_context_lists_scope_fields(scope: Scope):
    context = scope_context(scope)
    assert "10.0.0.5" in context
    assert "SOW-2026-014" in context
    assert "recon" in context


def test_build_messages_structure_and_current_turn(scope: Scope):
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    messages = build_messages(scope, history, user_text="next?")
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["content"] == scope_context(scope)
    assert messages[-1] == {"role": "user", "content": "next?"}


def test_build_messages_without_budget_keeps_everything(scope: Scope):
    history = [{"role": "user", "content": "x" * 500_000}]
    messages = build_messages(scope, history, budget=False)
    assert len(messages) == 3  # 2 system + 1 history, untrimmed
    assert len(messages[2]["content"]) == 500_000


def test_build_messages_with_budget_trims_oversized_history(scope: Scope):
    history = [{"role": "user", "content": "x" * 5_000_000}]
    messages = build_messages(scope, history)
    assert len(messages[-1]["content"]) < 5_000_000


def test_build_messages_skips_unknown_roles(scope: Scope):
    history = [{"role": "tool", "content": "ignored"}, {"role": "user", "content": "kept"}]
    messages = build_messages(scope, history)
    contents = [m["content"] for m in messages]
    assert "ignored" not in contents
    assert "kept" in contents


def test_llmclient_default_max_tokens_tracks_reserve():
    assert LLMClient().max_tokens == RESPONSE_RESERVE_TOKENS


def test_llmclient_streams_content_and_sends_configured_max_tokens(monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            [
                b'data: {"choices":[{"delta":{"content":"nmap "}}]}\n',
                b'data: {"choices":[{"delta":{"content":"-sV"}}]}\n',
                b"data: [DONE]\n",
            ]
        )

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    client = LLMClient(timeout=7, max_tokens=321)
    out = "".join(client.chat([{"role": "user", "content": "hi"}]))

    assert out == "nmap -sV"
    assert captured["timeout"] == 7
    assert captured["body"]["max_tokens"] == 321
    assert captured["body"]["stream"] is True
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_llmclient_raises_llmerror_on_connection_failure(monkeypatch):
    import urllib.error

    def boom(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    try:
        list(LLMClient().chat([{"role": "user", "content": "hi"}]))
    except llm.LLMError as exc:
        assert "Could not reach local LLM server" in str(exc)
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("expected LLMError")

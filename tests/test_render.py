from __future__ import annotations

import pytest
from rich.console import Console
from rich.errors import MarkupError

from wizards_pick import render
from wizards_pick.methodology import ToolStatus
from wizards_pick.models import (
    CommandProposal,
    ExecutionMode,
    Finding,
    RiskLevel,
    Scope,
    Session,
)

# Sequences that Rich's markup parser would choke on: a stray closing tag, an
# unclosed tag, and the bracket noise every scanner emits.
HOSTILE = "[+] host up [*] [1-1000] [/red] [bold] unclosed [not_a_tag"


@pytest.fixture
def recording(monkeypatch):
    console = Console(record=True, width=120)
    monkeypatch.setattr(render, "console", console)
    return console


def test_plain_console_would_crash_on_stray_closing_tag():
    # Documents the bug these helpers exist to avoid.
    with pytest.raises(MarkupError):
        Console().print("[/red]")


def test_stream_chunk_renders_hostile_text_verbatim(recording):
    render.stream_chunk(HOSTILE)
    assert HOSTILE in recording.export_text()


def test_print_status_renders_hostile_value(recording):
    render.print_status("[green]Finding recorded:[/green]", HOSTILE)
    out = recording.export_text()
    assert "Finding recorded:" in out
    assert "[not_a_tag" in out


def test_display_proposal_survives_hostile_fields(recording):
    proposal = CommandProposal(
        phase=HOSTILE,
        technique=HOSTILE,
        commands=[HOSTILE, "sqlmap -u 'http://x?id=[1]'"],
        risk_level=RiskLevel.LOW,
        scope_check="",
        expected_outcome=HOSTILE,
        next_steps=HOSTILE,
    )
    render.display_proposal(proposal)
    assert "Command proposal" in recording.export_text()


def test_print_findings_survives_hostile_title(recording):
    render.print_findings(
        [Finding(title=HOSTILE, severity=RiskLevel.HIGH, evidence="e", classification=HOSTILE)]
    )
    assert "Findings" in recording.export_text()


def test_print_sessions_survives_hostile_name(recording):
    scope = Scope(authorized_targets=[HOSTILE])
    render.print_sessions([Session(id="id", name=HOSTILE, mode=ExecutionMode.MANUAL, scope=scope)])
    assert "Sessions" in recording.export_text()


def test_print_tools_survives_hostile_path(recording):
    render.print_tools(
        [ToolStatus(name="nmap", category="scanning", installed=True, path="/opt/[x]/nmap")]
    )
    out = recording.export_text()
    assert "installed" in out


def test_literal_panel_shows_content(recording):
    recording.print(render.literal_panel(HOSTILE, title="cmd"))
    assert "[not_a_tag" in recording.export_text()

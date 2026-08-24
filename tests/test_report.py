from __future__ import annotations

from wizards_pick.models import CommandProposal, CommandResult, Finding, RiskLevel, Session
from wizards_pick.report import export_markdown
from wizards_pick.storage import Storage


def test_export_markdown_empty_session(storage: Storage, session: Session, tmp_path):
    path = export_markdown(storage, session, tmp_path / "report.md")
    text = path.read_text(encoding="utf-8")
    assert "# Assessment Report: Example" in text
    assert "No findings have been recorded yet." in text
    assert "No commands have been executed through the assistant." in text
    # Session context is always rendered.
    assert "SOW-2026-014" in text
    assert "soc@example.com" in text


def test_export_markdown_with_findings_commands_events(
    storage: Storage, session: Session, tmp_path
):
    storage.add_finding(
        session.id,
        Finding(
            title="Auth bypass",
            severity=RiskLevel.CRITICAL,
            evidence="cookie forgery",
            business_impact="full account takeover",
            remediation="sign the cookie",
        ),
    )
    proposal = CommandProposal.from_payload(
        {"technique": "service scan", "commands": ["nmap -sV 10.0.0.5"], "risk_level": "low"}
    )
    result = CommandResult(
        command="nmap -sV 10.0.0.5",
        exit_code=0,
        stdout="22/tcp open ssh",
        stderr="",
        started_at="t0",
        completed_at="t1",
    )
    storage.add_command_run(session.id, proposal.to_dict(), result.to_dict(), "exit_0")
    storage.add_event(session.id, "command_executed", {"command": "nmap -sV 10.0.0.5"})

    path = export_markdown(
        storage, session, tmp_path / "r.md", executive_summary="Overall high risk."
    )
    text = path.read_text(encoding="utf-8")

    assert "## Executive Summary" in text
    assert "Overall high risk." in text
    assert "### 1. Auth bypass" in text
    assert "full account takeover" in text
    assert "## Command Timeline" in text
    assert "nmap -sV 10.0.0.5" in text
    assert "22/tcp open ssh" in text
    assert "## Audit Events" in text
    assert "command_executed" in text


def test_export_markdown_creates_parent_dirs(storage: Storage, session: Session, tmp_path):
    nested = tmp_path / "deep" / "nested" / "out.md"
    path = export_markdown(storage, session, nested)
    assert path.exists()


def test_export_markdown_omits_summary_section_when_absent(
    storage: Storage, session: Session, tmp_path
):
    text = export_markdown(storage, session, tmp_path / "r.md").read_text(encoding="utf-8")
    assert "## Executive Summary" not in text

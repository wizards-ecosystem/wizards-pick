from __future__ import annotations

import pytest

from wizards_pick.models import (
    CommandProposal,
    CommandResult,
    ExecutionMode,
    Finding,
    RiskLevel,
    Scope,
    Session,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("info", RiskLevel.INFORMATIONAL),
        ("INFORMATIONAL", RiskLevel.INFORMATIONAL),
        ("low", RiskLevel.LOW),
        ("Medium", RiskLevel.MEDIUM),
        ("med", RiskLevel.MEDIUM),
        ("HIGH", RiskLevel.HIGH),
        ("crit", RiskLevel.CRITICAL),
        ("critical", RiskLevel.CRITICAL),
        ("nonsense", RiskLevel.MEDIUM),
        (None, RiskLevel.MEDIUM),
        ("", RiskLevel.MEDIUM),
    ],
)
def test_risklevel_from_text(raw, expected):
    assert RiskLevel.from_text(raw) is expected


def test_scope_round_trip_default():
    scope = Scope()
    assert Scope.from_dict(scope.to_dict()) == scope


def test_scope_round_trip_populated(scope: Scope):
    assert Scope.from_dict(scope.to_dict()) == scope


def test_scope_from_dict_missing_keys_uses_field_defaults():
    scope = Scope.from_dict({})
    assert scope.target_type == "web app"
    assert scope.testing_window == ""
    assert scope.emergency_contact == ""
    assert scope.allowed_categories == ["recon", "scanning", "exploitation"]


def test_scope_from_dict_preserves_explicit_empty_categories():
    scope = Scope.from_dict({"allowed_categories": []})
    assert scope.allowed_categories == []


def test_scope_summary_includes_optional_fields(scope: Scope):
    summary = scope.summary()
    assert "SOW-2026-014" in summary
    assert "soc@example.com" in summary
    assert "staging only" in summary


def test_session_to_dict_serializes_mode(scope: Scope):
    session = Session(id="abc", name="s", mode=ExecutionMode.ASSISTED, scope=scope)
    data = session.to_dict()
    assert data["mode"] == "assisted"
    assert data["scope"]["target_type"] == "web app"


def test_command_proposal_from_payload_normalizes_commands():
    proposal = CommandProposal.from_payload(
        {"phase": "Recon", "command": "nmap 10.0.0.5", "risk_level": "low"}
    )
    assert proposal.commands == ["nmap 10.0.0.5"]
    assert proposal.risk_level is RiskLevel.LOW
    assert proposal.category == "recon"


def test_command_proposal_from_payload_filters_blanks_and_defaults():
    proposal = CommandProposal.from_payload({"commands": ["  ", "id", ""]})
    assert proposal.commands == ["id"]
    assert proposal.phase == "Recon"
    assert proposal.risk_level is RiskLevel.MEDIUM
    assert proposal.raw["commands"] == ["  ", "id", ""]


def test_command_proposal_to_dict_serializes_risk():
    proposal = CommandProposal.from_payload({"commands": ["id"], "risk_level": "high"})
    assert proposal.to_dict()["risk_level"] == "high"


def test_finding_from_payload_supports_severity_aliases():
    finding = Finding.from_payload({"title": "SQLi", "risk_level": "crit", "evidence": "boom"})
    assert finding.severity is RiskLevel.CRITICAL
    assert finding.title == "SQLi"
    assert finding.to_dict()["severity"] == "critical"


def test_command_result_combined_output_merges_streams():
    result = CommandResult(
        command="id",
        exit_code=0,
        stdout="uid=0\n",
        stderr=" warning \n",
        started_at="t0",
        completed_at="t1",
    )
    assert result.combined_output() == "uid=0\nwarning"


def test_command_result_combined_output_empty():
    result = CommandResult(
        command="true", exit_code=0, stdout="", stderr="", started_at="t0", completed_at="t1"
    )
    assert result.combined_output() == ""

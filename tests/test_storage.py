from __future__ import annotations

from wizards_pick.models import (
    CommandProposal,
    CommandResult,
    ExecutionMode,
    Finding,
    RiskLevel,
    Scope,
    Session,
)
from wizards_pick.storage import Storage


def test_create_and_get_session(storage: Storage, session: Session):
    fetched = storage.get_session(session.id)
    assert fetched is not None
    assert fetched.id == session.id
    assert fetched.name == "Example"
    assert fetched.mode is ExecutionMode.MANUAL
    assert fetched.scope.authorized_targets == ["10.0.0.5", "app.example.com"]


def test_get_missing_session_returns_none(storage: Storage):
    assert storage.get_session("nope") is None


def test_update_session_persists_mode_and_bumps_timestamp(storage: Storage, session: Session):
    original_updated = session.updated_at
    session.mode = ExecutionMode.AUTOMATED
    storage.update_session(session)
    reloaded = storage.get_session(session.id)
    assert reloaded is not None
    assert reloaded.mode is ExecutionMode.AUTOMATED
    assert reloaded.updated_at >= original_updated


def test_latest_session_tracks_updates(storage: Storage, scope: Scope):
    first = storage.create_session("first", ExecutionMode.MANUAL, scope)
    second = storage.create_session("second", ExecutionMode.MANUAL, scope)
    assert storage.latest_session().id == second.id
    storage.update_session(first)
    assert storage.latest_session().id == first.id


def test_list_sessions_returns_all(storage: Storage, scope: Scope):
    storage.create_session("a", ExecutionMode.MANUAL, scope)
    storage.create_session("b", ExecutionMode.MANUAL, scope)
    assert {s.name for s in storage.list_sessions()} == {"a", "b"}


def test_messages_round_trip_in_chronological_order(storage: Storage, session: Session):
    storage.add_message(session.id, "user", "first")
    storage.add_message(session.id, "assistant", "second")
    storage.add_message(session.id, "user", "third")
    messages = storage.list_messages(session.id)
    assert [m["content"] for m in messages] == ["first", "second", "third"]


def test_messages_limit_keeps_most_recent(storage: Storage, session: Session):
    for i in range(10):
        storage.add_message(session.id, "user", f"m{i}")
    recent = storage.list_messages(session.id, limit=3)
    assert [m["content"] for m in recent] == ["m7", "m8", "m9"]


def test_events_round_trip(storage: Storage, session: Session):
    storage.add_event(session.id, "mode_changed", {"mode": "assisted"})
    events = storage.list_events(session.id)
    assert events[-1]["kind"] == "mode_changed"
    assert events[-1]["data"] == {"mode": "assisted"}


def test_command_runs_round_trip(storage: Storage, session: Session):
    proposal = CommandProposal.from_payload({"commands": ["id"], "risk_level": "low"})
    result = CommandResult(
        command="id", exit_code=0, stdout="uid=0", stderr="", started_at="t0", completed_at="t1"
    )
    storage.add_command_run(session.id, proposal.to_dict(), result.to_dict(), "exit_0")
    runs = storage.list_command_runs(session.id)
    assert len(runs) == 1
    assert runs[0]["status"] == "exit_0"
    assert runs[0]["result"]["stdout"] == "uid=0"
    assert runs[0]["proposal"]["commands"] == ["id"]


def test_findings_round_trip(storage: Storage, session: Session):
    storage.add_finding(
        session.id,
        Finding(title="XSS", severity=RiskLevel.MEDIUM, evidence="alert(1)"),
    )
    findings = storage.list_findings(session.id)
    assert len(findings) == 1
    assert findings[0].title == "XSS"
    assert findings[0].severity is RiskLevel.MEDIUM


def test_storage_isolates_by_session(storage: Storage, scope: Scope):
    a = storage.create_session("a", ExecutionMode.MANUAL, scope)
    b = storage.create_session("b", ExecutionMode.MANUAL, scope)
    storage.add_message(a.id, "user", "for-a")
    assert storage.list_messages(b.id) == []

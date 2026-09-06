from __future__ import annotations

import pytest

from wizards_pick import cli
from wizards_pick.executor import CommandExecutor
from wizards_pick.models import CommandResult, ExecutionMode, Scope
from wizards_pick.storage import Storage


class _RecordingExecutor(CommandExecutor):
    def __init__(self):
        super().__init__()
        self.commands: list[str] = []

    def run(self, command: str) -> CommandResult:
        self.commands.append(command)
        return CommandResult(
            command=command,
            exit_code=0,
            stdout="ok",
            stderr="",
            started_at="t0",
            completed_at="t1",
        )


def test_automated_mode_executes_model_proposal(storage: Storage, monkeypatch):
    session = storage.create_session("automated", ExecutionMode.AUTOMATED, Scope())
    executor = _RecordingExecutor()
    monkeypatch.setattr(cli, "display_proposal", lambda proposal: None)
    response = '{"type":"command_proposal","commands":["printf ok"]}'

    cli.process_model_response(storage, session, executor, response)

    assert executor.commands == ["printf ok"]
    assert storage.list_command_runs(session.id)[0]["status"] == "exit_0"


def test_report_slug_cannot_escape_report_directory():
    assert cli._report_slug("../../ Client / Root") == "client-root"
    assert cli._report_slug("...") == "session"


def test_operator_can_set_long_positive_timeout(storage: Storage):
    session = storage.create_session("timeout", ExecutionMode.MANUAL, Scope())
    executor = CommandExecutor()
    cli._handle_timeout("7200", storage, session, executor)
    assert executor.timeout == 7200


def test_version_flag_does_not_initialize_storage(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "wizards-pick 0.2.0" in capsys.readouterr().out
    assert not (tmp_path / ".wizards-pick").exists()

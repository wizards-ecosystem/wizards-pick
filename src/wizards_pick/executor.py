from __future__ import annotations

import subprocess

from .models import CommandResult, utc_now


class CommandExecutor:
    """Runs a shell command and captures its output, with a wall-clock timeout.

    Execution is intentionally unsandboxed — governed only by the session's mode
    and the operator's own authorization (see the project's "lean by design"
    stance). ``timeout`` bounds a single command so a hung scan can't wedge the
    session; a timed-out run is returned with ``timed_out=True`` and whatever
    partial output was captured.
    """

    def __init__(self, timeout: int = 300):
        self.timeout = timeout

    def run(self, command: str) -> CommandResult:
        started_at = utc_now()
        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return CommandResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                started_at=started_at,
                completed_at=utc_now(),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                exit_code=None,
                stdout=exc.stdout if isinstance(exc.stdout, str) else "",
                stderr=exc.stderr if isinstance(exc.stderr, str) else "",
                started_at=started_at,
                completed_at=utc_now(),
                timed_out=True,
            )

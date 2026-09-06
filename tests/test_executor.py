from __future__ import annotations

import os
import shlex
import sys
import time
from pathlib import Path

from wizards_pick.executor import CommandExecutor


def _python_command(source: str) -> str:
    return shlex.join([sys.executable, "-c", source])


def test_executor_captures_stdout_and_stderr():
    result = CommandExecutor(timeout=5).run(
        _python_command("import sys; print('out'); print('err', file=sys.stderr)")
    )
    assert result.exit_code == 0
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    assert not result.timed_out
    assert not result.output_truncated


def test_executor_bounds_captured_output():
    result = CommandExecutor(timeout=5, output_limit=512).run(
        _python_command("import sys; sys.stdout.write('x' * 100_000); sys.stdout.flush()")
    )
    assert result.output_truncated
    assert len(result.stdout.encode()) <= 512
    assert "output truncated" in result.stderr


def test_executor_timeout_returns_promptly():
    started = time.monotonic()
    result = CommandExecutor(timeout=1).run(_python_command("import time; time.sleep(30)"))
    elapsed = time.monotonic() - started
    assert result.timed_out
    assert result.exit_code is None
    assert elapsed < 4


def test_executor_timeout_stops_descendants():
    if not (sys.platform.startswith("linux") and os.path.isdir("/proc")):
        return
    source = (
        "import subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "print(child.pid, flush=True); time.sleep(30)"
    )
    result = CommandExecutor(timeout=1).run(_python_command(source))
    child_pid = int(result.stdout.strip())

    deadline = time.monotonic() + 2
    while _linux_process_is_running(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _linux_process_is_running(child_pid)


def _linux_process_is_running(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2]
    except FileNotFoundError:
        return False
    return state != "Z"

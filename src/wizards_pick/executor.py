from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

from .models import CommandResult, utc_now


class CommandExecutor:
    """Runs a shell command and captures its output, with a wall-clock timeout.

    Execution is unsandboxed and governed by the operator's authorization.
    ``timeout`` bounds wall time and ``output_limit`` bounds combined captured
    stdout and stderr. On POSIX systems, the whole command process group is
    terminated when either bound is reached.
    """

    def __init__(self, timeout: int = 300, output_limit: int = 1_000_000):
        self.timeout = timeout
        self.output_limit = output_limit

    def run(self, command: str) -> CommandResult:
        started_at = utc_now()
        collector = _OutputCollector(self.output_limit)
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
        assert process.stdout is not None
        assert process.stderr is not None
        readers = [
            threading.Thread(
                target=_drain, args=(process.stdout, collector, "stdout"), daemon=True
            ),
            threading.Thread(
                target=_drain, args=(process.stderr, collector, "stderr"), daemon=True
            ),
        ]
        for reader in readers:
            reader.start()

        timed_out = False
        deadline = time.monotonic() + self.timeout
        while process.poll() is None:
            if collector.limit_reached.wait(timeout=0.05):
                _terminate_process_tree(process)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                _terminate_process_tree(process)
                break

        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process, force=True)
            process.wait()

        for reader in readers:
            reader.join(timeout=0.2)
        if any(reader.is_alive() for reader in readers):
            _terminate_process_tree(process, force=True)
            process.stdout.close()
            process.stderr.close()
            for reader in readers:
                reader.join(timeout=0.2)

        stdout, stderr = collector.text()
        return CommandResult(
            command=command,
            exit_code=None if timed_out else process.returncode,
            stdout=stdout,
            stderr=stderr,
            started_at=started_at,
            completed_at=utc_now(),
            timed_out=timed_out,
            output_truncated=collector.truncated,
        )


class _OutputCollector:
    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("output_limit must be at least 1 byte")
        self.limit = limit
        self.used = 0
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.truncated = False
        self.lock = threading.Lock()
        self.limit_reached = threading.Event()

    def add(self, stream: str, chunk: bytes) -> None:
        with self.lock:
            remaining = self.limit - self.used
            kept = chunk[:remaining]
            getattr(self, stream).extend(kept)
            self.used += len(kept)
            if len(kept) < len(chunk):
                self.truncated = True
                self.limit_reached.set()

    def text(self) -> tuple[str, str]:
        marker = "\n[output truncated: command exceeded capture limit]\n"
        stdout = self.stdout.decode("utf-8", errors="replace")
        stderr = self.stderr.decode("utf-8", errors="replace")
        if self.truncated:
            stderr += marker
        return stdout, stderr


def _drain(pipe, collector: _OutputCollector, stream: str) -> None:
    try:
        while chunk := pipe.read(65_536):
            collector.add(stream, chunk)
    except (OSError, ValueError):
        return


def _terminate_process_tree(process: subprocess.Popen, *, force: bool = False) -> None:
    if os.name == "posix":
        signum = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            return
        return
    if process.poll() is None:
        if force:
            process.kill()
        else:
            process.terminate()

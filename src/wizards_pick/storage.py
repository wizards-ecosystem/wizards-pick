from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import ExecutionMode, Finding, Scope, Session, utc_now
from .paths import DB_PATH

DEFAULT_DB_PATH = DB_PATH


class Storage:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    authorization_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS command_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                """
            )

    def create_session(
        self,
        name: str,
        mode: ExecutionMode,
        scope: Scope,
    ) -> Session:
        session = Session(
            id=str(uuid.uuid4()),
            name=name,
            mode=mode,
            scope=scope,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, name, mode, scope_json, authorization_hash,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.name,
                    session.mode.value,
                    json.dumps(scope.to_dict(), sort_keys=True),
                    scope.authorization_hash,
                    session.created_at,
                    session.updated_at,
                ),
            )
        return session

    def update_session(self, session: Session) -> None:
        session.updated_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET name = ?, mode = ?, scope_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    session.name,
                    session.mode.value,
                    json.dumps(session.scope.to_dict(), sort_keys=True),
                    session.updated_at,
                    session.id,
                ),
            )

    def get_session(self, session_id: str) -> Session | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._row_to_session(row) if row else None

    def latest_session(self) -> Session | None:
        # Order by the raw ISO timestamp (sub-second precise as text; SQLite's
        # datetime() would truncate to whole seconds), with rowid as a final
        # deterministic tiebreak for identical timestamps.
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self) -> list[Session]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, utc_now()),
            )

    def list_messages(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        messages = [dict(row) for row in rows]
        messages.reverse()
        return messages

    def add_event(self, session_id: str, kind: str, data: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO events (session_id, kind, data_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, kind, json.dumps(data, sort_keys=True), utc_now()),
            )

    def list_events(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT kind, data_json, created_at
                FROM events
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "kind": row["kind"],
                "data": json.loads(row["data_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def add_command_run(
        self,
        session_id: str,
        proposal: dict[str, Any],
        result: dict[str, Any],
        status: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO command_runs (session_id, proposal_json, result_json, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    json.dumps(proposal, sort_keys=True),
                    json.dumps(result, sort_keys=True),
                    status,
                    utc_now(),
                ),
            )

    def list_command_runs(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT proposal_json, result_json, status, created_at
                FROM command_runs
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "proposal": json.loads(row["proposal_json"]),
                "result": json.loads(row["result_json"]),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def add_finding(self, session_id: str, finding: Finding) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO findings (session_id, data_json, created_at)
                VALUES (?, ?, ?)
                """,
                (session_id, json.dumps(finding.to_dict(), sort_keys=True), utc_now()),
            )

    def list_findings(self, session_id: str) -> list[Finding]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT data_json
                FROM findings
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        return [Finding.from_payload(json.loads(row["data_json"])) for row in rows]

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            name=row["name"],
            mode=ExecutionMode(row["mode"]),
            scope=Scope.from_dict(json.loads(row["scope_json"])),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

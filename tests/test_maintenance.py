from __future__ import annotations

import io
import json
import sqlite3

import pytest

from wizards_pick import storage as storage_module
from wizards_pick.excerpts import excerpt
from wizards_pick.llm import LLMClient, LLMError, extract_json_payloads
from wizards_pick.storage import Storage


def test_excerpt_keeps_verdict():
    text = "HEAD\n" + "noise\n" * 10000 + "TAIL failure"
    for budget in (4000, 6000, 32000):
        result = excerpt(text, budget)
        assert result.startswith("HEAD") and result.endswith("TAIL failure")
        assert "characters omitted" in result and len(result) <= budget


def test_continuation_completes_payload_and_is_bounded():
    def frame(content, finish):
        return (
            "data: "
            + json.dumps({"choices": [{"delta": {"content": content}, "finish_reason": finish}]})
            + "\n"
        ).encode()

    class Opener:
        def __init__(self, frames):
            self.frames = iter(frames)
            self.requests = []

        def open(self, request, timeout=None):
            self.requests.append(json.loads(request.data))
            return io.BytesIO(next(self.frames))

    opener = Opener(
        [frame('```json\n{"type":"finding","title":"X', "length"), frame('SS"}\n```', "stop")]
    )
    client = LLMClient(opener=opener)
    text = "".join(client.chat([{"role": "user", "content": "summarize"}]))
    assert extract_json_payloads(text)[0]["title"] == "XSS"
    assert len(opener.requests) == 2
    assert opener.requests[0]["max_tokens"] == opener.requests[1]["max_tokens"]
    opener = Opener([frame("x", "length")] * 3)
    with pytest.raises(LLMError, match="three requests"):
        list(LLMClient(opener=opener).chat([]))
    assert len(opener.requests) == 3


def test_migration_preserves_legacy_data_and_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite"
    store = Storage(path)
    store.add_message("legacy", "user", "retained")
    with store.connect() as conn:
        conn.execute("PRAGMA user_version = 0")
    store = Storage(path)
    assert store.list_messages("legacy")[0]["content"] == "retained"
    monkeypatch.setattr(
        storage_module,
        "MIGRATIONS",
        (*storage_module.MIGRATIONS, ("ALTER TABLE messages ADD COLUMN extra TEXT",)),
    )
    Storage(path)
    Storage(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("SELECT content FROM messages").fetchone()[0] == "retained"
    monkeypatch.setattr(storage_module, "MIGRATIONS", storage_module.MIGRATIONS[:1])
    with pytest.raises(RuntimeError, match="newer"):
        Storage(path)


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "rollback.sqlite"
    Storage(path)
    monkeypatch.setattr(
        storage_module,
        "MIGRATIONS",
        (*storage_module.MIGRATIONS, ("CREATE TABLE temporary_step (id INTEGER)", "INVALID SQL")),
    )
    with pytest.raises(sqlite3.OperationalError):
        Storage(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='temporary_step'").fetchone()
            is None
        )

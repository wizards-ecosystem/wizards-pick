from __future__ import annotations

import pytest

from wizards_pick.models import ExecutionMode, Scope, Session
from wizards_pick.storage import Storage


@pytest.fixture
def scope() -> Scope:
    return Scope(
        target_type="web app",
        authorized_targets=["10.0.0.5", "app.example.com"],
        allowed_categories=["recon", "scanning"],
        excluded_targets=["10.0.0.1"],
        testing_window="Mon-Fri 09:00-17:00 UTC",
        authorization_label="SOW-2026-014",
        emergency_contact="soc@example.com",
        notes="staging only",
    )


@pytest.fixture
def storage(tmp_path) -> Storage:
    return Storage(tmp_path / "sessions.sqlite")


@pytest.fixture
def session(storage: Storage, scope: Scope) -> Session:
    return storage.create_session(name="Example", mode=ExecutionMode.MANUAL, scope=scope)

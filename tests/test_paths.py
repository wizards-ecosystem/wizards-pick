from __future__ import annotations

import json
import os
import subprocess
import sys

from wizards_pick.paths import PROJECT_DATA_DIR


def test_project_data_dir_uses_branded_name() -> None:
    assert PROJECT_DATA_DIR.name == ".wizards-pick"


def test_branded_environment_overrides() -> None:
    env = os.environ.copy()
    env.update(
        {
            "WIZARDS_PICK_MODEL": "test-model",
            "WIZARDS_PICK_OLLAMA_HOST": "127.0.0.1:4242",
            "WIZARDS_PICK_URL": "http://127.0.0.1:4242/custom",
            "WIZARDS_PICK_CONTEXT_TOKENS": "4096",
            "WIZARDS_PICK_RESPONSE_TOKENS": "512",
        }
    )
    script = """
import json
from wizards_pick import paths

print(json.dumps({
    "model": paths.LOCAL_LLM_MODEL,
    "host": paths.LOCAL_OLLAMA_HOST,
    "url": paths.LOCAL_LLM_URL,
    "context": paths.CONTEXT_WINDOW_TOKENS,
    "response": paths.RESPONSE_RESERVE_TOKENS,
}))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "model": "test-model",
        "host": "127.0.0.1:4242",
        "url": "http://127.0.0.1:4242/custom",
        "context": 4096,
        "response": 512,
    }

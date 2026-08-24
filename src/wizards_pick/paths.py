from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back on bad input."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DATA_DIR = PROJECT_ROOT / ".wizards-pick"

# Local security-tuned model (DeepHat-V1-7B, built from the in-repo Modelfile).
# Override per-session for one-off tasks, e.g. WIZARDS_PICK_MODEL=qwen2.5-coder:7b.
LOCAL_LLM_MODEL = os.environ.get("WIZARDS_PICK_MODEL", "deephat")
# Project-local Ollama listens on loopback; override host/port for non-default setups.
LOCAL_OLLAMA_HOST = os.environ.get("WIZARDS_PICK_OLLAMA_HOST", "127.0.0.1:11435")
LOCAL_LLM_URL = os.environ.get(
    "WIZARDS_PICK_URL", f"http://{LOCAL_OLLAMA_HOST}/v1/chat/completions"
)

# Context window the model was built with (Modelfile pins num_ctx 32768). History is
# budgeted to fit this so long engagements never silently overflow the window.
CONTEXT_WINDOW_TOKENS = _env_int("WIZARDS_PICK_CONTEXT_TOKENS", 32768)
# Tokens reserved for the model's reply; mirrors max_tokens/num_predict (1024).
RESPONSE_RESERVE_TOKENS = _env_int("WIZARDS_PICK_RESPONSE_TOKENS", 1024)

DB_PATH = PROJECT_DATA_DIR / "sessions.sqlite"
REPORTS_DIR = PROJECT_DATA_DIR / "reports"
OLLAMA_HOME = PROJECT_DATA_DIR / "home"
OLLAMA_MODELS_DIR = PROJECT_DATA_DIR / "ollama" / "models"
OLLAMA_RUNTIME_DIR = PROJECT_DATA_DIR / "runtime"

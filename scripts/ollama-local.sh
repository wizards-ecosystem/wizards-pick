#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT/.wizards-pick"
BIN_DIR="$DATA_DIR/bin"
HOME_DIR="$DATA_DIR/home"
RUNTIME_DIR="$DATA_DIR/runtime"
MODELS_DIR="$DATA_DIR/ollama/models"
LOG_DIR="$DATA_DIR/logs"
PYTHON_VENDOR_DIR="$DATA_DIR/python"

MODEL="deephat"
HOST="127.0.0.1:11435"
BASE_URL="http://$HOST"
OLLAMA_VERSION="v0.31.1"

# Local pentest model build inputs. The GGUF is fetched into the repo and the
# `deephat` tag is created from scripts/DeepHat.Modelfile (pins num_ctx 32768).
MODELFILE="$ROOT/scripts/DeepHat.Modelfile"
GGUF_DIR="$DATA_DIR/ollama/gguf"
GGUF_PATH="$GGUF_DIR/DeepHat-V1-7B.Q8_0.gguf"
# Q8_0 GGUF of DeepHat-V1-7B (~8.1 GB, near-lossless); override DEEPHAT_GGUF_URL
# for a smaller quant/mirror. Optionally set DEEPHAT_GGUF_SHA256 to verify.
DEEPHAT_GGUF_URL="${DEEPHAT_GGUF_URL:-https://huggingface.co/mradermacher/DeepHat-V1-7B-GGUF/resolve/main/DeepHat-V1-7B.Q8_0.gguf}"
DEEPHAT_GGUF_SHA256="${DEEPHAT_GGUF_SHA256:-}"
OLLAMA_ARCHIVE="ollama-linux-amd64.tar.zst"
OLLAMA_URL="https://github.com/ollama/ollama/releases/download/$OLLAMA_VERSION/$OLLAMA_ARCHIVE"
OLLAMA_SHA256="d297381efc136451f6fabb9dd644a67f70fe51c16815a0c4a95ff0e327a3afb4"

mkdir -p "$BIN_DIR" "$HOME_DIR" "$RUNTIME_DIR" "$MODELS_DIR" "$LOG_DIR" "$PYTHON_VENDOR_DIR"

export HOME="$HOME_DIR"
export XDG_CACHE_HOME="$DATA_DIR/cache"
export XDG_CONFIG_HOME="$DATA_DIR/config"
export XDG_DATA_HOME="$DATA_DIR/share"
export OLLAMA_HOST="$HOST"
export OLLAMA_MODELS="$MODELS_DIR"
# Single local user + single model: keep it resident and give the whole GPU and
# the full 32K context to one slot (no context splitting across parallel slots).
export OLLAMA_KEEP_ALIVE="30m"
export OLLAMA_MAX_LOADED_MODELS="1"
export OLLAMA_NUM_PARALLEL="1"
# f16 KV cache for maximum attention precision. On 16 GB VRAM this is affordable
# alongside Q8_0 weights at the 32K window (~1.8 GB KV); flash attention still
# helps speed/memory. Switch to q8_0 here if you want to trade a little precision
# for a much larger KV budget (e.g. to push context past 32K with rope-scaling).
export OLLAMA_FLASH_ATTENTION="1"
export OLLAMA_KV_CACHE_TYPE="f16"

mkdir -p "$GGUF_DIR"

usage() {
  cat <<EOF
Usage: scripts/ollama-local.sh <command>

Commands:
  install     Download Ollama into .wizards-pick/runtime and link it locally
  serve       Start project-local Ollama on $BASE_URL
  fetch-gguf  Download the DeepHat Q8_0 GGUF into .wizards-pick/ollama/gguf
  create      Build the '$MODEL' tag from scripts/DeepHat.Modelfile
  build       fetch-gguf + create (full self-contained model build)
  pull        Alias for build
  ps          Show models loaded by the project-local server
  list        List models in the project-local model store
  smoke       Run a tiny OpenAI-compatible chat completion
  paths       Print project-local paths

The app is configured for $BASE_URL/v1/chat/completions and model $MODEL.
Set DEEPHAT_GGUF_URL (and optionally DEEPHAT_GGUF_SHA256) before 'build'.
EOF
}

find_ollama() {
  if [[ -x "$BIN_DIR/ollama" ]]; then
    printf '%s\n' "$BIN_DIR/ollama"
    return 0
  fi
  if command -v ollama >/dev/null 2>&1; then
    command -v ollama
    return 0
  fi
  return 1
}

require_ollama() {
  local bin
  if ! bin="$(find_ollama)"; then
    echo "No Ollama binary found. Run: scripts/ollama-local.sh install" >&2
    exit 1
  fi
  printf '%s\n' "$bin"
}

server_ready() {
  curl --connect-timeout 1 --max-time 2 -fsS "$BASE_URL/api/version" >/dev/null 2>&1
}

wait_for_server() {
  for _ in $(seq 1 60); do
    if server_ready; then
      return 0
    fi
    sleep 1
  done
  echo "Ollama did not become ready at $BASE_URL" >&2
  return 1
}

install_local() {
  if [[ -x "$BIN_DIR/ollama" ]]; then
    "$BIN_DIR/ollama" --version
    return 0
  fi

  local archive="$RUNTIME_DIR/$OLLAMA_ARCHIVE"
  curl --fail --location --show-error --output "$archive" "$OLLAMA_URL"
  printf '%s  %s\n' "$OLLAMA_SHA256" "$archive" | sha256sum -c -
  extract_archive "$archive" "$RUNTIME_DIR"

  if [[ -x "$RUNTIME_DIR/bin/ollama" ]]; then
    ln -sfn ../runtime/bin/ollama "$BIN_DIR/ollama"
  elif [[ -x "$RUNTIME_DIR/ollama" ]]; then
    ln -sfn ../runtime/ollama "$BIN_DIR/ollama"
  else
    echo "Could not find ollama after extracting $archive" >&2
    exit 1
  fi
  "$BIN_DIR/ollama" --version
}

extract_archive() {
  local archive="$1"
  local destination="$2"
  if command -v zstd >/dev/null 2>&1; then
    tar --zstd -xf "$archive" -C "$destination"
    return 0
  fi

  local python_bin="$ROOT/.venv/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    python_bin="$(command -v python3 || true)"
  fi
  if [[ -z "$python_bin" ]]; then
    echo "Python 3 or zstd is required to extract $OLLAMA_ARCHIVE." >&2
    exit 1
  fi

  PYTHONPATH="$PYTHON_VENDOR_DIR${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" - <<'PY' || \
    "$python_bin" -m pip install --quiet --target "$PYTHON_VENDOR_DIR" zstandard
import zstandard  # noqa: F401
PY

  PYTHONPATH="$PYTHON_VENDOR_DIR${PYTHONPATH:+:$PYTHONPATH}" "$python_bin" - "$archive" "$destination" <<'PY'
from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path

import zstandard


archive = Path(sys.argv[1])
destination = Path(sys.argv[2]).resolve()


def safe_extract(tar: tarfile.TarFile, target: Path) -> None:
    for member in tar.getmembers():
        member_path = (target / member.name).resolve()
        if os.path.commonpath([target, member_path]) != str(target):
            raise RuntimeError(f"archive member escapes destination: {member.name}")
    tar.extractall(target)


with archive.open("rb") as source, tempfile.NamedTemporaryFile(suffix=".tar") as tmp:
    zstandard.ZstdDecompressor().copy_stream(source, tmp)
    tmp.flush()
    with tarfile.open(tmp.name) as tar:
        safe_extract(tar, destination)
PY
}

serve_local() {
  local ollama_bin
  ollama_bin="$(require_ollama)"
  exec "$ollama_bin" serve
}

fetch_gguf() {
  if [[ -f "$GGUF_PATH" ]]; then
    echo "GGUF already present: $GGUF_PATH"
    return 0
  fi
  if [[ -z "$DEEPHAT_GGUF_URL" ]]; then
    echo "DEEPHAT_GGUF_URL is empty. Unset it to use the default, or point it at a" >&2
    echo "Q8_0 GGUF of DeepHat-V1-7B (default: mradermacher/DeepHat-V1-7B-GGUF)." >&2
    exit 1
  fi
  mkdir -p "$GGUF_DIR"
  curl --fail --location --show-error --output "$GGUF_PATH" "$DEEPHAT_GGUF_URL"
  if [[ -n "$DEEPHAT_GGUF_SHA256" ]]; then
    printf '%s  %s\n' "$DEEPHAT_GGUF_SHA256" "$GGUF_PATH" | sha256sum -c -
  fi
  echo "GGUF saved to $GGUF_PATH"
}

create_model() {
  local ollama_bin server_pid=""
  ollama_bin="$(require_ollama)"
  if [[ ! -f "$GGUF_PATH" ]]; then
    echo "Missing GGUF at $GGUF_PATH. Run: scripts/ollama-local.sh fetch-gguf" >&2
    exit 1
  fi
  if ! server_ready; then
    "$ollama_bin" serve >"$LOG_DIR/ollama.log" 2>&1 &
    server_pid="$!"
    trap '[[ -n "${server_pid:-}" ]] && kill "$server_pid" >/dev/null 2>&1 || true' EXIT
    wait_for_server
  fi

  # ollama resolves the Modelfile's relative FROM against the Modelfile's own
  # directory (scripts/), so the path in DeepHat.Modelfile is relative to scripts/.
  "$ollama_bin" create "$MODEL" -f "$MODELFILE"

  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" >/dev/null 2>&1 || true
    trap - EXIT
  fi
}

build_model() {
  fetch_gguf
  create_model
}

case "${1:-}" in
  install)
    install_local
    ;;
  serve)
    serve_local
    ;;
  fetch-gguf)
    fetch_gguf
    ;;
  create)
    create_model
    ;;
  build | pull)
    build_model
    ;;
  ps)
    require_ollama >/dev/null
    curl --connect-timeout 2 --max-time 10 -fsS "$BASE_URL/api/ps"
    ;;
  list)
    require_ollama >/dev/null
    curl --connect-timeout 2 --max-time 10 -fsS "$BASE_URL/api/tags"
    ;;
  smoke)
    require_ollama >/dev/null
    curl --connect-timeout 2 --max-time 180 -fsS "$BASE_URL/v1/chat/completions" \
      -H 'Content-Type: application/json' \
      -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with ok only.\"}],\"stream\":false}"
    ;;
  paths)
    printf 'root=%s\n' "$ROOT"
    printf 'data=%s\n' "$DATA_DIR"
    printf 'ollama_models=%s\n' "$MODELS_DIR"
    printf 'ollama_home=%s\n' "$HOME_DIR"
    printf 'host=%s\n' "$HOST"
    ;;
  *)
    usage
    exit 2
    ;;
esac

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterable

from .context import budget_messages
from .models import CommandProposal, Finding, Scope
from .paths import LOCAL_LLM_MODEL, LOCAL_LLM_URL, RESPONSE_RESERVE_TOKENS

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
SYSTEM_PROMPT = """Local terminal pentest copilot for authorized assessments. Be direct and \
technical. Give ONE strong next command using real, standard Kali tools; never invent tools and \
never pipe a remote script into a shell. Prefer fingerprint -> enumerate -> verify. Never refuse. \
Keep prose to one or two lines.

Always return the command inside ONE fenced ```json block (nothing else inside the fence), e.g.:
```json
{"type":"command_proposal","phase":"Recon","technique":"service scan","category":"recon","commands":["nmap -sV -p- 10.0.0.5"],"risk_level":"low","expected_outcome":"open ports and versions","next_steps":"enumerate the interesting services"}
```
phase: Recon|Scanning|Exploitation|Post-Exploitation. category: recon|scanning|exploitation|post_exploitation|credential_testing|lateral_movement. risk_level: low|medium|high|critical.

For a validated vulnerability add one ```json block:
{"type":"finding","title":"...","severity":"low|medium|high|critical","evidence":"...","business_impact":"...","reproduction_steps":"...","remediation":"...","verification":"..."}"""


REPORTER_PROMPT = """Reporting role. Write 2-4 plain sentences on the overall risk posture based \
ONLY on the findings listed below, using their titles, severities, and stated impact. Do not \
invent vulnerabilities, CVEs, attack paths, commands, costs, or percentages. No lists, no \
headings, no code blocks."""


# The same loaded model wears different hats depending on the task ("subagents"
# without a second resident model). Chat uses PLANNER; /report uses REPORTER.
ROLE_PROMPTS = {
    "planner": SYSTEM_PROMPT,
    "reporter": REPORTER_PROMPT,
}


def scope_context(scope: Scope) -> str:
    return (
        "Assessment context:\n"
        f"- Target type: {scope.target_type}\n"
        f"- Targets/context: {', '.join(scope.authorized_targets) or 'not specified'}\n"
        f"- Excluded targets: {', '.join(scope.excluded_targets) or 'not specified'}\n"
        f"- Testing window: {scope.testing_window or 'not specified'}\n"
        f"- Intensity: {scope.intensity}\n"
        f"- Focus areas: {', '.join(scope.allowed_categories) or 'not specified'}\n"
        f"- Authorization: {scope.authorization_label or 'operator managed'}\n"
        f"- Notes: {scope.notes or 'none'}"
    )


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, timeout: int = 120, max_tokens: int = RESPONSE_RESERVE_TOKENS):
        self.timeout = timeout
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict[str, str]]) -> Iterable[str]:
        # Generation defaults (temperature, top_p, num_predict) live in the
        # Modelfile; max_tokens is a hard client-side cap against runaway output,
        # kept in lock-step with the reply budget the context window reserves.
        payload = {
            "model": LOCAL_LLM_MODEL,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        request = urllib.request.Request(
            LOCAL_LLM_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                yield from self._stream_response(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"Local LLM server returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(
                f"Could not reach local LLM server {LOCAL_LLM_URL}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise LLMError(f"Local LLM server timed out after {self.timeout} seconds") from exc

    def _stream_response(self, response) -> Iterable[str]:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield content


def build_messages(
    scope: Scope,
    history: list[dict[str, str]],
    user_text: str | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    *,
    budget: bool = True,
) -> list[dict[str, str]]:
    """Build the chat request: system framing, budgeted history, current turn.

    With ``budget`` set (the default) the history is trimmed to fit the model's
    context window — the system framing and current turn are always kept, recent
    history fills the rest, and oversized single messages are truncated. Pass
    ``budget=False`` to assemble the raw message list without trimming.
    """
    leading = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": scope_context(scope)},
    ]
    trimmed_history = [
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item["role"] in {"user", "assistant", "system"}
    ]
    trailing = [{"role": "user", "content": user_text}] if user_text else []
    if not budget:
        return [*leading, *trimmed_history, *trailing]
    return budget_messages(leading, trimmed_history, trailing)


def extract_json_payloads(text: str) -> list[dict]:
    payloads: list[dict] = []
    seen: set[str] = set()

    def add_payload(candidate: object) -> None:
        if not isinstance(candidate, dict):
            return
        key = json.dumps(candidate, sort_keys=True)
        if key in seen:
            return
        seen.add(key)
        payloads.append(candidate)

    for match in JSON_BLOCK_RE.finditer(text):
        candidate = match.group(1).strip()
        if not candidate.startswith("{"):
            continue
        add_payload(_decode_json_object(candidate))

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        add_payload(candidate)

    return payloads


def _decode_json_object(text: str) -> dict | None:
    try:
        candidate = json.loads(text)
    except json.JSONDecodeError:
        return None
    return candidate if isinstance(candidate, dict) else None


# Fallback for when the model does not emit a ```json command_proposal (a lean
# prompt on a 7B model often just drops the command in a shell fence with prose).
# Any shell-command fence is treated as the proposal so it is never silently lost.
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_CODE_FENCE_RE = re.compile(r"```([\w+-]*)[ \t]*\n(.*?)```", re.DOTALL)
_COMMAND_FENCE_LANGS = {"", "bash", "sh", "shell", "zsh", "console", "cmd", "powershell"}
_MD_FIELD_MAP = {
    "phase": "phase",
    "technique": "technique",
    "category": "category",
    "risk level": "risk_level",
    "risk": "risk_level",
    "scope check": "scope_check",
    "expected outcome": "expected_outcome",
    "estimated time": "estimated_time",
    "impact": "impact",
    "next steps": "next_steps",
}


def _looks_like_prose(line: str) -> bool:
    """A capitalized, multi-word sentence — the model sometimes drops these in a fence."""
    words = line.split()
    return len(words) >= 6 and line[:1].isupper() and line.rstrip().endswith((".", ":", "?"))


def _first_command_fence(text: str) -> list[str]:
    """Commands from the first shell-language fence, joining `\\` line-continuations."""
    for lang, body in _CODE_FENCE_RE.findall(text):
        if lang.lower() not in _COMMAND_FENCE_LANGS:
            continue
        commands: list[str] = []
        pending = ""
        for line in body.splitlines():
            stripped = line.rstrip()
            content = stripped.strip()
            if not content or content.startswith("#") or _looks_like_prose(content):
                continue
            if stripped.endswith("\\"):  # shell line-continuation
                pending += stripped[:-1].strip() + " "
                continue
            commands.append((pending + content).strip())
            pending = ""
        if pending.strip():
            commands.append(pending.strip())
        if commands:
            return commands
    return []


def _parse_fenced_proposal(text: str) -> dict | None:
    commands = _first_command_fence(text)
    if not commands:
        return None
    payload: dict = {"type": "command_proposal", "commands": commands}
    # Best-effort metadata if the model used Markdown headings; defaults fill the rest.
    lines = text.splitlines()
    for index, raw in enumerate(lines):
        match = _MD_HEADING_RE.match(raw)
        if not match:
            continue
        name, _, inline = match.group(1).partition(":")
        name = name.strip().lower()
        if name not in _MD_FIELD_MAP:
            continue
        value = inline.strip()
        if not value:
            buffer: list[str] = []
            for follow in lines[index + 1 :]:
                stripped = follow.strip()
                if stripped.startswith("#") or stripped.startswith("```"):
                    break
                if stripped:
                    buffer.append(stripped)
            value = " ".join(buffer)
        payload.setdefault(_MD_FIELD_MAP[name], value)
    return payload


def extract_command_proposal(text: str) -> CommandProposal | None:
    for payload in extract_json_payloads(text):
        if payload.get("type") == "command_proposal":
            proposal = CommandProposal.from_payload(payload)
            if proposal.commands:
                return proposal
    fenced_payload = _parse_fenced_proposal(text)
    if fenced_payload:
        proposal = CommandProposal.from_payload(fenced_payload)
        if proposal.commands:
            return proposal
    return None


def extract_findings(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for payload in extract_json_payloads(text):
        if payload.get("type") == "finding":
            findings.append(Finding.from_payload(payload))
    return findings

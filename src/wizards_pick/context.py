"""Context-window budgeting for the local model.

The model is built with a fixed context window (the Modelfile pins ``num_ctx``).
A long engagement — large pasted scan dumps, ``/exec`` output, multi-step chains —
can accumulate far more chat history than that window holds. Rather than blindly
sending everything and letting the server silently drop the *oldest* system framing
(or truncate mid-message), we budget the history here: system framing and the
current turn are always kept, recent history is filled in newest-first until the
window is full, and any single oversized message is trimmed head-and-tail so one
giant blob can't evict the entire conversation.
"""

from __future__ import annotations

from collections.abc import Sequence

from .paths import CONTEXT_WINDOW_TOKENS, RESPONSE_RESERVE_TOKENS

Message = dict[str, str]

# Rough heuristic. Real tokenization is model-specific, but ~4 chars/token is a
# stable, slightly conservative estimate for English + shell/command text, which
# is all we need to keep the request comfortably inside the window.
CHARS_PER_TOKEN = 4
_PER_MESSAGE_OVERHEAD_TOKENS = 4  # role/formatting framing per message
_TRUNCATION_NOTICE = "\n... [{omitted} characters omitted to fit the context window] ...\n"


def estimate_tokens(text: str) -> int:
    """Cheap, slightly conservative estimate of the tokens in ``text``."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def _message_tokens(message: Message) -> int:
    return estimate_tokens(message.get("content", "")) + _PER_MESSAGE_OVERHEAD_TOKENS


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Trim ``text`` to roughly ``max_tokens``, keeping the head and tail.

    Command output tends to matter most at the top (open ports, banners, the
    first errors) and the bottom (summaries, final state), so the middle is what
    gets dropped, with a marker recording how much was removed.
    """
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    notice_room = len(_TRUNCATION_NOTICE.format(omitted=len(text)))
    body = max(0, max_chars - notice_room)
    head = (body * 3) // 5
    tail = body - head
    omitted = len(text) - head - tail
    tail_text = text[len(text) - tail :] if tail else ""
    return text[:head] + _TRUNCATION_NOTICE.format(omitted=omitted) + tail_text


def budget_messages(
    leading: Sequence[Message],
    history: Sequence[Message],
    trailing: Sequence[Message] = (),
    *,
    context_window_tokens: int = CONTEXT_WINDOW_TOKENS,
    response_reserve_tokens: int = RESPONSE_RESERVE_TOKENS,
    per_message_cap_tokens: int | None = None,
) -> list[Message]:
    """Assemble ``leading + recent(history) + trailing`` within the context window.

    ``leading`` (system framing) and ``trailing`` (the current turn) are always
    kept; ``history`` is filled in newest-first until the remaining budget is
    exhausted, dropping the oldest messages. Any single message larger than
    ``per_message_cap_tokens`` is truncated head-and-tail first, so one huge dump
    is shortened rather than allowed to evict everything else.
    """
    budget = max(0, context_window_tokens - response_reserve_tokens)
    if per_message_cap_tokens is None:
        per_message_cap_tokens = max(budget // 4, 512)

    def clamp(message: Message) -> Message:
        content = message.get("content", "")
        if estimate_tokens(content) <= per_message_cap_tokens:
            return dict(message)
        return {**message, "content": truncate_to_tokens(content, per_message_cap_tokens)}

    kept_leading = [clamp(message) for message in leading]
    kept_trailing = [clamp(message) for message in trailing]
    used = sum(_message_tokens(message) for message in (*kept_leading, *kept_trailing))

    selected: list[Message] = []
    for message in reversed(history):
        candidate = clamp(message)
        cost = _message_tokens(candidate)
        if used + cost > budget:
            break
        selected.append(candidate)
        used += cost
    selected.reverse()

    return [*kept_leading, *selected, *kept_trailing]

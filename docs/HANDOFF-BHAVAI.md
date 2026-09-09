# Handoff: two changes taken from a BhavAI review, 2026-09-06

Status: **reviewed, nothing implemented.** This file is the whole output of the review. Every
gap described below was checked against the source at the time of writing rather than assumed,
but no code has been changed.

## Where this came from

BhavAI Terminal Edition is a third-party terminal agent in Python: a Reason-Act-Observe loop,
a tool set, and a Sarvam or Groq backend. It was cloned into the ecosystem's investigation tree,
read for technique, and deleted. It is a coding agent rather than an assessment tool, so most of
it does not apply to The Wizard's Pick. Two things do, and one of its mistakes is worth recording
because it argues for a position Pick already holds.

| | |
| --- | --- |
| Upstream | https://github.com/BhavneeshBanga/BhavAI-Terminal-Edition |
| Reviewed at | `67e329da154afc0722c080ae6af9b79e2fdf3b94` |

**Its licence forbids reuse of its code.** `LICENSE.md` is "BhavAI Community License v1.0, All
Rights Reserved", and section 3 prohibits derivative works and using the source in another
project. Its `pyproject.toml` separately claims MIT; the licence file governs, and the
contradiction is a reason for caution rather than a loophole. Nothing below is a copy. Each item
is a technique described so it can be written from scratch, which is how it has to be done.

Both items are stdlib-only and neither touches the execution model, the scope of what Pick
controls, or the SQLite schema. Per [CONTRIBUTING.md](../CONTRIBUTING.md), both need tests, and
both can be tested offline with no Ollama server.

---

## 1. Keep the tail when truncating command output

**The gap is real, in three places.** Pick truncates command output head-only at every layer:

| Where | What | Why it matters |
| --- | --- | --- |
| [cli.py:373](../src/wizards_pick/cli.py#L373) | `output[:MODEL_OUTPUT_CONTEXT_CHARS]`, 32,000 chars | The excerpt the model reasons over |
| [report.py:93](../src/wizards_pick/report.py#L93) | `output[:4000]` | The excerpt that lands in the deliverable |
| [executor.py:21](../src/wizards_pick/executor.py#L21) | `output_limit=1_000_000` capture bound | Stops reading at the limit |

For assessment work this is the wrong half. A long scan, an enumeration sweep, a fuzzing run, or
a failing exploit attempt puts the banner and the argument echo at the start and the finding at
the end. Truncating head-only reliably discards the result and keeps the preamble — in the model
context, where it costs a wrong next step, and in the report, where it costs the evidence.

The technique, which BhavAI applies at its own much smaller scale: split the budget, keep the
first half and the last half, and put an explicit `... [N lines omitted] ...` marker between them
so the reader and the model both know the gap is there instead of inferring a contradiction.

The two excerpt sites are straightforward — the whole string is already in hand, so this is a
small helper applied twice. The capture bound is different: it is a streaming bound that stops
reading, so keeping a tail there means a bounded head buffer plus a ring buffer for the tail
(`collections.deque` with `maxlen`), which holds memory flat while letting the end survive. Do
the two excerpt sites first; the capture bound is only worth changing if commands are actually
hitting the 1,000,000-byte limit in practice.

One property to preserve: the existing marker wording says the capture limit was exceeded, and
`output_truncated` is recorded on the row. Whatever replaces it should stay explicit that output
was dropped and where, because a report excerpt that silently omits its middle is worse than one
that says so.

**Tests:** an over-long output whose first and last lines both survive, and whose marker is
present; one case per site.

## 2. Continue a completion that stopped at the token cap

**The gap is real.** `LLMClient.chat` ([llm.py:80-95](../src/wizards_pick/llm.py#L80-L95)) sends
`max_tokens` as a hard client-side cap and the streaming reader never inspects a finish reason.
A reply cut off at the cap is handled as though it were complete. The comment at
[llm.py:82](../src/wizards_pick/llm.py#L82) is honest that this is a runaway guard kept in
lock-step with the reply budget, which is the right design — but the consequence is that a long
legitimate reply is silently amputated.

Where it bites in Pick specifically: a methodology walk-through, a multi-step command rationale,
or a findings write-up is exactly the kind of long reply that reaches the cap. A truncated one
loses the trailing `json` block, so the command proposal or finding never gets extracted and the
turn appears to produce nothing.

The technique: when the reply stops for length rather than a natural stop, append what came back
as an assistant turn, append a short user turn instructing the model to resume exactly where it
stopped, emit only the continuation, and repeat nothing already written. Then call again and
concatenate, bounded to a few rounds.

Take the flaw out while implementing it. BhavAI concatenates blindly and parses afterwards, so a
join that does not stitch cleanly corrupts the whole payload with nothing to detect it. Pick is
better placed here than BhavAI is: `extract_json_payloads` already tolerates partial and messy
output, so validate the joined result through the existing extractor and fall back to the first
fragment if the join produces nothing usable.

Keep `max_tokens` as it is. The continuation is a way to finish a legitimate long reply, not a
reason to raise the cap, and the round bound is what keeps the runaway guard meaningful.

**Tests:** a fake opener returning a length-stop on the first response and a natural stop on the
second, asserting the fragments join and the payload extracts.

---

## Deliberately not taken

**Pick's JSON handling is already better than BhavAI's — do not "fix" it.** BhavAI parses
strictly and, on failure, feeds the parse error back and retries, aborting after three
consecutive failures. Pick's [extract_json_payloads](../src/wizards_pick/llm.py#L181) does
tolerant extraction instead: fenced-block matching, a `raw_decode` scan for unfenced objects,
de-duplication by sorted-key JSON, and an explicit fallback for lean models that never emit a
`command_proposal` block. That is the stronger design for a local 7B, and it costs no round
trips. Recorded here so a future reader who sees BhavAI's retry loop does not mistake it for an
improvement.

**Its safety model is theatre, and it argues for the position Pick already documents.** BhavAI
advertises a "Zero-Deletion Policy" and a "Sandboxed Scope". In practice `BLOCKED_COMMANDS` is
nine substrings matched by regex against a string then handed to `subprocess.Popen(shell=True)`.
`find . -delete`, `truncate -s 0`, `git clean -xdf`, `dd`, and a bare `> file` all pass. The
literal `format` is blocked, so harmless commands are rejected too. It is wrong in both
directions at once, and it sits beside a genuine path sandbox on the file tools, which makes the
README's safety claim look supported when it is not.

Pick's README states plainly that it ships no scope matcher, denylist, sandbox, approval service,
or output redaction, and that containment belongs to the account, container, VM, network, and
engagement process. That is the more defensible position, and it is worth keeping precisely
because a partial denylist would create the impression of a control that does not exist — for a
tool pointed at authorized targets by an operator who is relying on the documented boundary,
that impression is the dangerous part.

**Everything else does not apply.** Its AST code-editing tools, git auto-staging, chunked file
writes, `.bhavai/skills` manifest, and FastAPI settings backend all belong to a coding agent.
Pick does not edit code and should not start. For the record, that FastAPI backend is dead code
upstream — `fastapi` is not a declared dependency there, and the router's own docstring says it
is not wired to anything.

## Suggested order

Item 1 first, at the two excerpt sites. It is small, it is a verified gap, and it improves both
the model's next step and the deliverable. Item 2 after, since it needs care in the streaming
reader.

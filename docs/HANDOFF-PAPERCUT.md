# Handoff: three changes taken from a Papercut review, 2026-09-06

Status: **three things to investigate later.** Each was checked against
`src/wizards_pick/` at the time of writing, so the gaps described are real rather than assumed,
but no code has been changed. Temporary file: delete it once they are picked up.

## Where this came from

Papercut is a third-party CLI that gives coding agents a local SQLite memory of "development
friction". It was cloned into the scratch tree, read for technique, and deleted. It solves a
different problem than Pick does, but it stores the same *kind* of thing — model-written records
in a local SQLite file that outlives the session — so its storage discipline is worth knowing.

| | |
| --- | --- |
| Upstream | https://github.com/Tbsheff/papercut |
| Reviewed at | `b9570df` (v0.1.0, 2026-09-06) |
| Licence | MIT, Tbsheff |
| Size | 1,132 lines of TypeScript, Node 22.13+ |
| Traction | Created 2026-08-27. 0 stars, one author, no releases |

The licence is MIT, so reuse would be permitted, but the code is TypeScript and there is nothing
to vendor. Every item below is a technique described so it can be written from scratch in Python
with no new dependency. Of the four projects reviewed, Pick is the only one with anything to do.

Per `CONTRIBUTING.md`, each item names the regression it needs under `tests/`.

---

## 1. A migration ladder instead of `CREATE TABLE IF NOT EXISTS`

**The gap is real.** `storage.py:44` `_init_db()` runs one `executescript` of four
`CREATE TABLE IF NOT EXISTS` statements. There is no schema version recorded anywhere. Adding a
column today means either a hand-written `ALTER TABLE` guarded by a `PRAGMA table_info` probe, or
silently doing nothing to databases that already exist — and `DB_PATH` is
`~/.wizards-pick/sessions.sqlite`, which holds engagement data an operator cannot simply delete
and recreate.

Papercut's version is about twenty lines. An ordered list of SQL strings *is* the schema history,
and `PRAGMA user_version` is the pointer into it:

- If `user_version >= len(migrations)`, return without opening a write transaction. This is the
  common path on every start, and it costs one read.
- Otherwise loop: `BEGIN IMMEDIATE`, **re-read `user_version` after taking the write lock**,
  apply `migrations[current]`, set `user_version = current + 1`, `COMMIT`. Roll back and re-raise
  on any error.

The re-read inside the transaction is the part worth copying rather than reinventing: it is what
stops two processes that start together from both applying step *n*.

Migration 0 is the current schema exactly as `_init_db` writes it, so existing databases need a
one-time stamp: if the tables already exist and `user_version` is 0, set it to 1 rather than
re-running step 0. Note that `sqlite3` will not accept `PRAGMA user_version = ?` as a bound
parameter; the value has to be interpolated, which is safe here because it is a loop counter and
never input.

**Test:** `tests/test_storage.py` — open a database at version 0, add a throwaway migration,
reopen, assert the column exists and `user_version` advanced; and assert that reopening twice is
a no-op.

## 2. Deduplicate findings by fingerprint, and count occurrences

**The gap is real.** `storage.py:86`, the `findings` table, is `id / session_id / data_json /
created_at` with no uniqueness of any kind. `Finding` (`models.py:186`) carries a `title` and
`evidence`, and the model rewrites both in slightly different words every time it re-observes the
same thing. Today an operator who re-runs a phase, or scans a second host in the same engagement,
gets N rows for one issue, and `report.py` renders all of them.

Papercut's shape:

- A `fingerprint` column with a `UNIQUE` constraint, holding a SHA-256 hex digest over a scope
  key and a normalized message joined by a newline.
- Normalization is the whole trick: NFKC, casefold, replace every run of non-alphanumeric
  characters with a single space, strip. If normalization empties the string, fall back to the
  NFKC-lowercased original so the digest is never taken over an empty message.
- `INSERT OR IGNORE` against that column, then **always** insert a row into a separate
  `finding_occurrences` table recording the session, the target, and the time of *this*
  observation.
- Reads `LEFT JOIN` the occurrences, `GROUP BY` the parent, and return the count beside it.
- The write returns whether it created a record or added an occurrence, so the caller never needs
  a second query to find out which happened.

For Pick the scope key should be the target rather than the session — the same finding on the
same host across two sessions of one engagement is one finding — and `Finding` has no target
field today, so this needs a small model change first. Occurrence count then earns a column in
the report, which is real assessment signal: "observed on four hosts" is not the same finding as
"observed once".

**Test:** `tests/test_storage.py` — record the same finding twice with cosmetically different
wording, assert one row and two occurrences; record it against a second target, assert two rows.

## 3. Refuse a data directory inside a Git work tree

**Cheap and small.** Papercut resolves its home directory, then walks the ancestor chain looking
for a `.git` entry and refuses to start if it finds one, so a misconfigured home can never drop
its database into somebody's checkout. Pick already has the stronger half of this —
`private_io.py` hardens the database and its `-wal` and `-shm` sidecars, which Papercut does not
do — but no check on *where* the directory is.

`PROJECT_DATA_DIR` is fixed today, so this only bites if the path ever becomes configurable.
Worth adding at the same time it does, not before.

**Test:** `tests/test_paths.py` — a temporary directory containing `.git` is rejected.

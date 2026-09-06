# Contributing to The Wizard's Pick

Pick accepts focused bug fixes, tests, documentation corrections, and features that preserve its
small terminal workflow. Open an issue before a broad redesign so maintainers and contributors can
agree on scope.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
make check
```

The quality gate runs Ruff linting and formatting checks, mypy, and pytest. Tests must remain
offline and must not require an Ollama server or assessment target.

## Pull requests

- Keep each change reviewable and explain its user-visible effect.
- Add or update tests for behavior changes.
- Update the README and changelog when the public interface changes.
- Do not include target data, credentials, model files, runtime state, or generated reports.
- Use Pick only against systems covered by your authorization while developing or testing it.

By submitting a contribution, you agree that it may be distributed under the repository's
[MIT License](LICENSE).

Report vulnerabilities through the private process in [SECURITY.md](SECURITY.md).

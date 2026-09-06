# Releasing The Wizard's Pick

Releases are built from a GitHub release and published to PyPI with OpenID Connect. The workflow
does not use a long-lived PyPI token.

## One-time PyPI setup

Before the first release, create a pending trusted publisher on PyPI with these values:

| Field | Value |
|---|---|
| PyPI project name | `wizards-pick` |
| GitHub owner | `wizards-ecosystem` |
| GitHub repository | `wizards-pick` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

Create a GitHub environment named `pypi`. Add protection rules if the project needs a second
release approval. The package name was unregistered when checked on 2026-09-05; confirm it again
immediately before the first release.

## Release checklist

1. Update `src/wizards_pick/__init__.py` and `CHANGELOG.md` with the release version.
2. Run `make release-check` in a clean checkout.
3. Install the wheel from `dist/` in a fresh virtual environment and run `wizards-pick --help`.
4. Commit the release changes and wait for CI and CodeQL to pass on `main`.
5. Create a GitHub release whose tag is exactly `v<version>`, for example `v0.2.0`.
6. Confirm the `Publish to PyPI` workflow passes and the PyPI project shows both distributions.

The publish workflow rejects a tag that does not match the package version. It validates the
distributions before requesting PyPI credentials.

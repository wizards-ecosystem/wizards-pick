# Security policy for The Wizard's Pick

## Supported versions

Security fixes are applied to the latest release and the `main` branch. Older releases may be used
to reproduce a report, but do not receive separate fixes.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/wizards-ecosystem/wizards-pick/security/advisories/new).
Do not open a public issue for an undisclosed vulnerability.

Include the affected version or commit, operating environment, reproduction steps, impact, and any
suggested fix. Remove credentials, target data, command output, and other engagement-sensitive
material unless it is essential to reproduce the issue.

## Intended trust model

Pick is an operator-controlled command execution tool. These behaviors are part of its public
contract:

- `automated` mode executes parsed model proposals without confirmation.
- `/exec` executes the supplied shell command regardless of the current mode.
- Recorded scope and exclusions guide the model but are not enforced against commands.
- Pasted and captured target output becomes model context and can influence later proposals.
- Commands run without a sandbox, scope matcher, command denylist, or output redaction.
- Local state and generated reports can contain unredacted assessment data.

The operating-system account and host are trust boundaries. A process running as the same user may
be able to read assessment data or impersonate the loopback model endpoint. Operators who require
stronger isolation should supply it through their account, container, virtual machine, network,
and engagement controls.

Reports about bypassing an explicit mode confirmation, unintended execution outside `automated`
mode or `/exec`, unsafe archive or model handling, exposure across the stated trust boundary, or
other behavior that contradicts this policy are in scope.

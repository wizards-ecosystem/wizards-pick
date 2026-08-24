from __future__ import annotations

from pathlib import Path

from .models import Finding, Session
from .storage import Storage


def export_markdown(
    storage: Storage,
    session: Session,
    path: str | Path,
    executive_summary: str | None = None,
) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    commands = storage.list_command_runs(session.id)
    events = storage.list_events(session.id)
    findings = storage.list_findings(session.id)

    lines: list[str] = [
        f"# Assessment Report: {session.name}",
        "",
    ]

    if executive_summary:
        lines.extend(["## Executive Summary", "", executive_summary.strip(), ""])

    lines.extend(
        [
            "## Assessment Context",
            "",
            f"- Session ID: `{session.id}`",
            f"- Created: {session.created_at}",
            f"- Updated: {session.updated_at}",
            f"- Mode: {session.mode.value}",
            f"- Target type: {session.scope.target_type}",
            f"- Targets/context: {', '.join(session.scope.authorized_targets) or 'none'}",
            f"- Excluded targets: {', '.join(session.scope.excluded_targets) or 'none'}",
            f"- Testing window: {session.scope.testing_window or 'not specified'}",
            f"- Intensity: {session.scope.intensity}",
            f"- Focus areas: {', '.join(session.scope.allowed_categories) or 'none'}",
            f"- Authorization: {session.scope.authorization_label or 'operator managed'}",
            f"- Emergency contact: {session.scope.emergency_contact or 'not specified'}",
            f"- Notes: {session.scope.notes or 'none'}",
            "",
            "## Findings",
            "",
        ]
    )

    if findings:
        for index, finding in enumerate(findings, start=1):
            lines.extend(_finding_lines(index, finding))
    else:
        lines.append("No findings have been recorded yet.")
        lines.append("")

    lines.extend(["## Command Timeline", ""])
    if commands:
        for index, item in enumerate(commands, start=1):
            proposal = item["proposal"]
            result = item["result"]
            lines.extend(
                [
                    f"### {index}. {proposal.get('technique', 'Command')}",
                    "",
                    f"- Status: {item['status']}",
                    f"- Risk: {proposal.get('risk_level', 'unknown')}",
                    f"- Created: {item['created_at']}",
                    "",
                    "```bash",
                    str(result.get("command", "")),
                    "```",
                    "",
                ]
            )
            output = "\n".join(
                part.strip()
                for part in (result.get("stdout", ""), result.get("stderr", ""))
                if part.strip()
            ).strip()
            if output:
                lines.extend(["Output excerpt:", "", "```text", output[:4000], "```", ""])
    else:
        lines.append("No commands have been executed through the assistant.")
        lines.append("")

    lines.extend(["## Audit Events", ""])
    if events:
        for event in events:
            lines.append(f"- {event['created_at']} `{event['kind']}`: `{event['data']}`")
    else:
        lines.append("No audit events have been recorded.")
    lines.append("")

    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def _finding_lines(index: int, finding: Finding) -> list[str]:
    return [
        f"### {index}. {finding.title}",
        "",
        f"- Severity: {finding.severity.value}",
        f"- Classification: {finding.classification or 'not specified'}",
        f"- Difficulty: {finding.difficulty or 'not specified'}",
        "",
        "**Evidence**",
        "",
        finding.evidence or "No evidence recorded.",
        "",
        "**Business Impact**",
        "",
        finding.business_impact or "Not specified.",
        "",
        "**Reproduction Steps**",
        "",
        finding.reproduction_steps or "Not specified.",
        "",
        "**Remediation**",
        "",
        finding.remediation or "Not specified.",
        "",
        "**Verification**",
        "",
        finding.verification or "Not specified.",
        "",
    ]

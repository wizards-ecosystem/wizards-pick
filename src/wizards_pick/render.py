"""Terminal rendering helpers built on Rich.

Everything the model or a command emits is *untrusted text* for Rich's markup
parser: pentest output is full of sequences like ``[+]``, ``[*]``, and
``[1-1000]`` that Rich would try to read as markup tags and reject with a
``MarkupError`` mid-session. These helpers render all dynamic content literally
(via :class:`rich.text.Text`), so only the static labels we author ever carry
markup. Keeping every renderer here also keeps ``cli.py`` focused on flow.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .methodology import ToolStatus
from .models import CommandProposal, Finding, Session

console = Console()


def literal_panel(
    content: str,
    *,
    title: str | None = None,
    border_style: str = "cyan",
    expand: bool = True,
) -> Panel:
    """A panel whose body is rendered literally — never parsed as Rich markup."""
    return Panel(Text(content), title=title, border_style=border_style, expand=expand)


def stream_chunk(chunk: str) -> None:
    """Write a streamed model chunk verbatim — no markup, no syntax highlighting."""
    console.print(chunk, end="", markup=False, highlight=False, soft_wrap=True)


def print_status(prefix_markup: str, value: str) -> None:
    """Print a styled prefix followed by an untrusted, literal value."""
    console.print(prefix_markup, Text(value))


def display_proposal(proposal: CommandProposal) -> None:
    table = Table(title="Command Proposal")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Phase", Text(proposal.phase))
    table.add_row("Technique", Text(proposal.technique))
    table.add_row("Category", Text(proposal.category))
    table.add_row("Risk", Text(proposal.risk_level.value))
    table.add_row("Estimated time", Text(proposal.estimated_time))
    table.add_row("Impact", Text(proposal.impact))
    table.add_row("Expected", Text(proposal.expected_outcome))
    table.add_row("Next", Text(proposal.next_steps))
    console.print(table)
    for index, command in enumerate(proposal.commands, start=1):
        console.print(literal_panel(command, title=f"Command {index}"))


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        console.print("No findings recorded yet.")
        return
    table = Table(title="Findings")
    table.add_column("Title")
    table.add_column("Severity")
    table.add_column("Classification")
    for finding in findings:
        table.add_row(
            Text(finding.title),
            Text(finding.severity.value),
            Text(finding.classification or "n/a"),
        )
    console.print(table)


def print_sessions(sessions: list[Session]) -> None:
    if not sessions:
        console.print("No sessions saved yet.")
        return
    table = Table(title="Sessions")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Mode")
    table.add_column("Updated")
    table.add_column("Targets")
    for item in sessions:
        table.add_row(
            Text(item.id),
            Text(item.name),
            Text(item.mode.value),
            Text(item.updated_at),
            Text(", ".join(item.scope.authorized_targets) or "none"),
        )
    console.print(table)


def print_tools(statuses: list[ToolStatus]) -> None:
    table = Table(title="Local Tool Inventory")
    table.add_column("Category", style="cyan")
    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("Path")
    for item in statuses:
        status = "[green]installed[/green]" if item.installed else "[yellow]missing[/yellow]"
        table.add_row(Text(item.category), Text(item.name), status, Text(item.path or "n/a"))
    console.print(table)


def read_multiline(prompt: str) -> str:
    """Read lines from stdin until a line containing only ``EOF``."""
    console.print(prompt)
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "EOF":
            break
        lines.append(line)
    return "\n".join(lines)

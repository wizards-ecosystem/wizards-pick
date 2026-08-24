from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
except ImportError:  # pragma: no cover - exercised only without optional dependency.
    print("Rich is required. Install with: python -m pip install -e .", file=sys.stderr)
    raise

from .executor import CommandExecutor
from .llm import (
    ROLE_PROMPTS,
    LLMClient,
    LLMError,
    build_messages,
    extract_command_proposal,
    extract_findings,
)
from .methodology import format_methodology, tool_inventory
from .models import CommandProposal, ExecutionMode, RiskLevel, Scope, Session
from .paths import REPORTS_DIR
from .render import (
    console,
    display_proposal,
    literal_panel,
    print_findings,
    print_sessions,
    print_status,
    print_tools,
    read_multiline,
    stream_chunk,
)
from .report import export_markdown
from .storage import Storage

HISTORY_FETCH_LIMIT = 200

HELP_TEXT = """Available commands:

`/help` - show this help
`/context` or `/scope` - show session context
`/sessions` - list saved sessions
`/plan [phase|all]` - show an offline assessment plan for the current scope
`/tools` - check common local pentest tool availability
`/mode manual|assisted|automated` - change execution mode
`/timeout [seconds]` - show or update local command timeout
`/paste` - paste command output until a line containing only EOF
`/exec <command>` - run a local command and store the output
`/report [path]` - export a Markdown report
`/findings` - list recorded findings
`/exit` - quit
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wizards-pick",
        description="Local-first terminal assistant for authorized security testing.",
    )
    parser.add_argument("--session", help="Resume a specific session id.")
    parser.add_argument("--new", action="store_true", help="Create a new session.")
    args = parser.parse_args(argv)

    storage = Storage()
    if args.session:
        session = storage.get_session(args.session)
        if not session:
            console.print(f"[red]No session found with id {args.session}[/red]")
            return 2
    elif args.new:
        session = create_session_wizard(storage)
    else:
        session = storage.latest_session()
        if not session or not Confirm.ask(f"Resume latest session '{session.name}'?", default=True):
            session = create_session_wizard(storage)

    chat_loop(storage, session)
    return 0


def create_session_wizard(storage: Storage) -> Session:
    console.print(Panel.fit("wizards-pick security session", border_style="cyan"))
    name = Prompt.ask("Session name", default="Pentest session")
    mode = _prompt_mode(default=ExecutionMode.MANUAL)

    target_type = Prompt.ask("Target type", default="web app")
    targets = _split_csv(Prompt.ask("Targets/context", default=""))
    categories = _split_csv(Prompt.ask("Focus areas", default="recon,scanning,exploitation"))
    intensity = Prompt.ask("Intensity", default="standard")
    excluded_targets = _split_csv(Prompt.ask("Excluded targets (optional)", default=""))
    testing_window = Prompt.ask("Testing window (optional)", default="")
    authorization_label = Prompt.ask(
        "Authorization label/reference", default="provided during wizard"
    )
    emergency_contact = Prompt.ask("Emergency contact (optional)", default="")
    notes = Prompt.ask("Notes", default="")

    scope = Scope(
        target_type=target_type,
        authorized_targets=targets,
        allowed_categories=categories,
        intensity=intensity,
        excluded_targets=excluded_targets,
        testing_window=testing_window,
        authorization_label=authorization_label,
        emergency_contact=emergency_contact,
        notes=notes,
    )
    session = storage.create_session(name=name, mode=mode, scope=scope)
    storage.add_event(session.id, "session_created", {"mode": mode.value})
    console.print("[green]Session created.[/green]")
    console.print(literal_panel(scope.summary(), title="Context", border_style="green"))
    return session


def chat_loop(storage: Storage, session: Session) -> None:
    executor = CommandExecutor()
    client = LLMClient()

    console.print(
        literal_panel(
            f"{session.name}\nMode: {session.mode.value}", border_style="green", expand=False
        )
    )
    console.print(Markdown("Type `/help` for commands."))

    while True:
        try:
            text = Prompt.ask("[bold cyan]you[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return
        if not text:
            continue
        if text.startswith("/"):
            if handle_command(text, storage, session, executor, client):
                return
            continue

        storage.add_message(session.id, "user", text)
        response = ask_model(storage, session, client)
        if response:
            process_model_response(storage, session, executor, response)


def handle_command(
    text: str,
    storage: Storage,
    session: Session,
    executor: CommandExecutor,
    client: LLMClient,
) -> bool:
    command, _, arg = text.partition(" ")
    command = command.lower()

    if command in {"/exit", "/quit"}:
        return True
    if command == "/help":
        console.print(Markdown(HELP_TEXT))
        return False
    if command in {"/context", "/scope"}:
        console.print(literal_panel(session.scope.summary(), title="Context", border_style="green"))
        return False
    if command == "/sessions":
        print_sessions(storage.list_sessions())
        return False
    if command == "/plan":
        console.print(Markdown(format_methodology(session.scope, arg.strip() or None)))
        return False
    if command == "/tools":
        print_tools(tool_inventory())
        return False
    if command == "/timeout":
        _handle_timeout(arg, storage, session, executor)
        return False
    if command == "/mode":
        _handle_mode(arg, storage, session)
        return False
    if command == "/paste":
        pasted = read_multiline("Paste command output. End with a line containing only EOF.")
        prompt = (
            "Interpret this command output, update assessment state, and propose a useful next step.\n\n"
            "```text\n"
            f"{pasted}\n"
            "```"
        )
        storage.add_message(session.id, "user", prompt)
        response = ask_model(storage, session, client)
        if response:
            process_model_response(storage, session, executor, response)
        return False
    if command == "/exec":
        if not arg.strip():
            console.print("[red]Usage: /exec <command>[/red]")
            return False
        proposal = CommandProposal(
            phase="Execution",
            technique="User command",
            commands=[arg.strip()],
            risk_level=RiskLevel.MEDIUM,
            scope_check="User-managed.",
            expected_outcome="Capture command output.",
            next_steps="Review output and continue.",
            category="user_command",
        )
        run_proposal(storage, session, executor, proposal, confirm=False)
        return False
    if command == "/report":
        default_path = REPORTS_DIR / f"{session.name.lower().replace(' ', '-')}-{session.id[:8]}.md"
        destination = Path(arg.strip()) if arg.strip() else default_path
        summary = generate_executive_summary(storage, session, client)
        report_path = export_markdown(storage, session, destination, executive_summary=summary)
        console.print(f"[green]Report exported to {report_path}[/green]")
        return False
    if command == "/findings":
        print_findings(storage.list_findings(session.id))
        return False

    console.print("[red]Unknown command. Type /help.[/red]")
    return False


def _handle_timeout(
    arg: str, storage: Storage, session: Session, executor: CommandExecutor
) -> None:
    if not arg.strip():
        console.print(f"Current command timeout: [cyan]{executor.timeout} seconds[/cyan]")
        return
    try:
        timeout = int(arg.strip())
    except ValueError:
        console.print("[red]Timeout must be an integer number of seconds.[/red]")
        return
    if timeout < 1:
        console.print("[red]Timeout must be at least 1 second.[/red]")
        return
    executor.timeout = timeout
    storage.add_event(session.id, "timeout_changed", {"timeout": timeout})
    console.print(f"[green]Command timeout set to {timeout} seconds.[/green]")


def _handle_mode(arg: str, storage: Storage, session: Session) -> None:
    if not arg:
        session.mode = _prompt_mode(default=session.mode)
    else:
        try:
            session.mode = ExecutionMode(arg.strip().lower())
        except ValueError:
            console.print("[red]Mode must be manual, assisted, or automated.[/red]")
            return
    storage.update_session(session)
    storage.add_event(session.id, "mode_changed", {"mode": session.mode.value})
    console.print(f"[green]Mode set to {session.mode.value}.[/green]")


def ask_model(storage: Storage, session: Session, client: LLMClient) -> str:
    # The model runs a 32K context window; history is budgeted to fit it (see
    # context.py), so long engagements stay in-window instead of overflowing.
    history = storage.list_messages(session.id, limit=HISTORY_FETCH_LIMIT)
    messages = build_messages(session.scope, history)
    console.print("[bold magenta]assistant[/bold magenta]")
    chunks: list[str] = []
    try:
        for chunk in client.chat(messages):
            chunks.append(chunk)
            stream_chunk(chunk)
        console.print()
    except LLMError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print(
            "Check that your local model server is running and exposes /chat/completions."
        )
        return ""

    response = "".join(chunks).strip()
    if response:
        storage.add_message(session.id, "assistant", response)
    return response


def generate_executive_summary(storage: Storage, session: Session, client: LLMClient) -> str | None:
    """Run the same model in its REPORTER role over the recorded findings."""
    findings = storage.list_findings(session.id)
    if not findings:
        return None  # nothing validated to summarize; template report still exports.

    # Findings-only digest: feeding the command timeline invites the model to
    # invent commands/output, so the faithful timeline is left to the template.
    digest_lines = ["Findings:"]
    for finding in findings:
        digest_lines.append(
            f"- [{finding.severity.value}] {finding.title}: {finding.evidence or 'no evidence'} "
            f"| impact: {finding.business_impact or 'n/a'}"
        )

    messages = build_messages(
        session.scope, [], user_text="\n".join(digest_lines), system_prompt=ROLE_PROMPTS["reporter"]
    )
    chunks: list[str] = []
    try:
        for chunk in client.chat(messages):
            chunks.append(chunk)
    except LLMError as exc:
        console.print(f"[yellow]Executive summary skipped: {exc}[/yellow]")
        return None
    return "".join(chunks).strip() or None


def process_model_response(
    storage: Storage,
    session: Session,
    executor: CommandExecutor,
    response: str,
) -> None:
    for finding in extract_findings(response):
        storage.add_finding(session.id, finding)
        storage.add_event(
            session.id,
            "finding_recorded",
            {"title": finding.title, "severity": finding.severity.value},
        )
        print_status("[green]Finding recorded:[/green]", finding.title)

    proposal = extract_command_proposal(response)
    if not proposal:
        return

    display_proposal(proposal)
    if session.mode == ExecutionMode.MANUAL:
        console.print("[cyan]Manual mode:[/cyan] run externally, then use `/paste` for output.")
        return
    if session.mode == ExecutionMode.ASSISTED:
        run_proposal(storage, session, executor, proposal, confirm=True)
        return
    run_proposal(storage, session, executor, proposal, confirm=False)


def run_proposal(
    storage: Storage,
    session: Session,
    executor: CommandExecutor,
    proposal: CommandProposal,
    confirm: bool,
) -> None:
    if confirm and not Confirm.ask("Execute command(s)?", default=False):
        console.print("[yellow]Execution cancelled.[/yellow]")
        return

    for command in proposal.commands:
        console.print(literal_panel(command, title="Executing", border_style="yellow"))
        result = executor.run(command)
        status = "timeout" if result.timed_out else f"exit_{result.exit_code}"
        storage.add_command_run(session.id, proposal.to_dict(), result.to_dict(), status)
        storage.add_event(session.id, "command_executed", {"command": command, "status": status})
        output = result.combined_output()
        if output:
            console.print(literal_panel(output[:6000], title=status, border_style="blue"))
        else:
            console.print(f"[blue]{status}: no output[/blue]")

        prompt = (
            "Command output for assessment context.\n\n"
            f"Command: `{command}`\n"
            f"Status: `{status}`\n\n"
            "```text\n"
            f"{output}\n"
            "```"
        )
        storage.add_message(session.id, "user", prompt)


def _prompt_mode(default: ExecutionMode) -> ExecutionMode:
    mode = Prompt.ask(
        "Execution mode",
        choices=[item.value for item in ExecutionMode],
        default=default.value,
    )
    return ExecutionMode(mode)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())

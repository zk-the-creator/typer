from __future__ import annotations

import json
import shlex
from pathlib import Path

from . import _click
from ._click.termui import prompt
from .exceptions import Abort
from .inspection import (
    ApplicationContract,
    InspectionFailure,
    InspectionResult,
    get_application_contract,
    inspect_invocation,
)


def _display_value(value: object) -> str:
    return repr(value)


def _show_commands(contract: ApplicationContract) -> None:
    _click.echo("\nCommands:")
    commands = [command for command in contract.commands if command.path]
    if not commands:
        _click.echo("  (none)")
    for command in commands:
        annotations = []
        if command.hidden:
            annotations.append("hidden")
        if command.deprecated:
            annotations.append("deprecated")
        suffix = f" ({', '.join(annotations)})" if annotations else ""
        _click.echo(f"  {command.path}{suffix}")
    _click.echo()


def _show_contract(contract: ApplicationContract) -> None:
    _click.echo("\nApplication contract:")
    for command in contract.commands:
        path = command.path or "<root>"
        labels = ["group" if command.is_group else "command"]
        if command.hidden:
            labels.append("hidden")
        if command.deprecated:
            labels.append("deprecated")
        _click.echo(f"\n  {path} [{', '.join(labels)}]")
        if command.parent_path is not None:
            _click.echo(f"    Parent: {command.parent_path or '<root>'}")
        if command.help:
            _click.echo(f"    Help: {command.help}")
        _click.echo("    Parameters:")
        if not command.parameters:
            _click.echo("      (none)")
        for parameter in command.parameters:
            _click.echo(f"      {parameter.name} ({parameter.kind})")
            _click.echo(f"        Python type: {parameter.python_type}")
            _click.echo(f"        Required: {parameter.required}")
            _click.echo(f"        Default: {_display_value(parameter.default)}")
            if parameter.option_names:
                _click.echo(f"        Options: {', '.join(parameter.option_names)}")
            if parameter.secondary_option_names:
                _click.echo(
                    "        Boolean pair: "
                    + ", ".join(parameter.secondary_option_names)
                )
            if parameter.envvar:
                envvars = (
                    ", ".join(parameter.envvar)
                    if isinstance(parameter.envvar, tuple)
                    else parameter.envvar
                )
                _click.echo(f"        Environment: {envvars}")
            if parameter.multiple or parameter.nargs != 1 or parameter.count:
                _click.echo(
                    "        Arity: "
                    f"multiple={parameter.multiple}, nargs={parameter.nargs}, "
                    f"count={parameter.count}"
                )
            if parameter.constraints:
                _click.echo(f"        Constraints: {dict(parameter.constraints)!r}")
            if parameter.sensitive:
                _click.echo("        Sensitive: True (values redacted)")
    _click.echo()


def _show_inspection(result: InspectionResult) -> None:
    status = "successful" if result.success else "failed"
    _click.echo(f"\nInspection: {status}")
    _click.echo(f"Resolved command: {result.command_path or '(unresolved)'}")
    _click.echo("Parameters:")
    if not result.parameters:
        _click.echo("  (none)")
    for parameter in result.parameters:
        _click.echo(f"  {parameter.name}")
        _click.echo(f"    Command: {parameter.command_path}")
        _click.echo(f"    Raw value: {_display_value(parameter.raw_value)}")
        _click.echo(f"    Resolved value: {_display_value(parameter.value)}")
        _click.echo(f"    Type: {parameter.python_type or '(unresolved)'}")
        source = (
            parameter.source.name.lower().replace("_", " ")
            if parameter.source is not None
            else "unknown"
        )
        _click.echo(f"    Source: {source}")
    if result.failure:
        _show_failure(result.failure)
    _click.echo()


def _show_failure(failure: InspectionFailure) -> None:
    _click.echo(f"Inspection error: {failure.message}", err=True)
    _click.echo(f"  Stage: {failure.stage}", err=True)
    if failure.parameter:
        _click.echo(f"  Parameter: {failure.parameter}", err=True)
        _click.echo(f"  Raw value: {_display_value(failure.raw_value)}", err=True)
    if failure.expected_type:
        _click.echo(f"  Expected type: {failure.expected_type}", err=True)


def _inspect_text(command: _click.Command, invocation: str) -> InspectionResult:
    try:
        args = shlex.split(invocation)
    except ValueError as exc:
        return InspectionResult(
            command_path="",
            parameters=(),
            success=False,
            failure=InspectionFailure(
                stage="tokenization", message=str(exc), command_path=""
            ),
        )
    return inspect_invocation(command, args)


def _export_json(
    data: ApplicationContract | InspectionResult,
    output_path: Path,
    *,
    source_path: Path | None,
) -> bool:
    try:
        resolved_output = output_path.expanduser().resolve()
        if source_path is not None and resolved_output == source_path.resolve():
            raise ValueError(
                "The discovered application's source file cannot be replaced."
            )
        payload = json.dumps(
            data.to_dict(), indent=2, ensure_ascii=False, allow_nan=False
        )
        resolved_output.write_text(f"{payload}\n", encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        _click.echo(f"Export error: {exc}", err=True)
        return False
    _click.echo(f"Exported JSON to {resolved_output}")
    return True


def _prompt_path(label: str, default: str) -> Path | None:
    try:
        value = prompt(label, default=default, type=str).strip()
    except (EOFError, Abort):
        _click.echo("\nExport cancelled.")
        return None
    return Path(value)


def run_menu(command: _click.Command, *, source_path: Path | None = None) -> None:
    contract = get_application_contract(command)
    latest_inspection: InspectionResult | None = None
    _click.echo("Typer Application Menu")
    while True:
        _click.echo("1. Explore commands")
        _click.echo("2. Inspect invocation")
        _click.echo("3. View application contract")
        _click.echo("4. Export application contract as JSON")
        _click.echo("5. Export latest inspection as JSON")
        _click.echo("6. Exit")
        try:
            choice = prompt("Select an option", type=str).strip().lower()
        except (EOFError, Abort):
            _click.echo("\nLeaving menu.")
            return

        if choice in {"1", "explore", "commands"}:
            _show_commands(contract)
        elif choice in {"2", "inspect"}:
            try:
                invocation = prompt("Invocation", type=str, hide_input=True)
            except (EOFError, Abort):
                _click.echo("\nLeaving menu.")
                return
            latest_inspection = _inspect_text(command, invocation)
            _show_inspection(latest_inspection)
        elif choice in {"3", "contract", "view"}:
            _show_contract(contract)
        elif choice in {"4", "export contract"}:
            output = _prompt_path("JSON path", "typer-contract.json")
            if output is not None:
                _export_json(contract, output, source_path=source_path)
        elif choice in {"5", "export inspection"}:
            if latest_inspection is None:
                _click.echo("Inspect an invocation before exporting its result.")
                continue
            output = _prompt_path("JSON path", "typer-inspection.json")
            if output is not None:
                _export_json(latest_inspection, output, source_path=source_path)
        elif choice in {"6", "exit", "quit", "q"}:
            _click.echo("Leaving menu.")
            return
        else:
            _click.echo("Please choose an option from 1 through 6.")

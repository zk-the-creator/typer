from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from . import _click
from ._click.core import ParameterSource
from ._click.termui import prompt
from .core import TyperGroup
from .exceptions import Abort


@dataclass
class InspectedParameter:
    name: str
    raw_value: Any
    value: Any
    source: ParameterSource | None


@dataclass
class InspectedInvocation:
    command_path: str
    parameters: list[InspectedParameter]


_missing = object()


def _make_bare_context(
    command: _click.Command,
    *,
    info_name: str,
    parent: _click.Context | None = None,
) -> _click.Context:
    return command.context_class(command, info_name=info_name, parent=parent)


def _command_paths(command: _click.Command) -> list[str]:
    if not isinstance(command, TyperGroup):
        return [command.name or "<command>"]

    paths: list[str] = []

    def visit(
        current: TyperGroup,
        prefix: tuple[str, ...],
        parent: _click.Context | None,
    ) -> None:
        info_name = prefix[-1] if prefix else current.name or "app"
        ctx = _make_bare_context(current, info_name=info_name, parent=parent)
        try:
            for command_name in current.list_commands(ctx):
                child = current.get_command(ctx, command_name)
                if child is None or child.hidden:
                    continue
                path = (*prefix, command_name)
                paths.append(" ".join(path))
                if isinstance(child, TyperGroup):
                    visit(child, path, ctx)
        finally:
            ctx.close()

    visit(command, (), None)
    return paths


def _raw_parameter_values(
    command: _click.Command,
    args: list[str],
    *,
    info_name: str,
    parent: _click.Context | None,
) -> dict[str, Any]:
    ctx = _make_bare_context(command, info_name=info_name, parent=parent)
    try:
        values, _, _ = command.make_parser(ctx).parse_args(args=list(args))
        return values
    finally:
        ctx.close()


def _parameters_from_context(
    command: _click.Command,
    ctx: _click.Context,
    raw_values: dict[str, Any],
) -> list[InspectedParameter]:
    parameters: list[InspectedParameter] = []
    convertors = getattr(command.callback, "__typer_convertors__", {})
    for parameter in command.get_params(ctx):
        if parameter.name is None or parameter.name not in ctx.params:
            continue
        source = ctx.get_parameter_source(parameter.name)
        raw_value = raw_values.get(parameter.name, _missing)
        if source is not ParameterSource.COMMANDLINE:
            raw_value = _missing
        value = ctx.params[parameter.name]
        if parameter.name in convertors:
            value = convertors[parameter.name](value)
            ctx.params[parameter.name] = value
        parameters.append(
            InspectedParameter(
                name=parameter.name,
                raw_value=raw_value,
                value=value,
                source=source,
            )
        )
    return parameters


def inspect_invocation(command: _click.Command, args: list[str]) -> InspectedInvocation:
    current = command
    current_args = list(args)
    parent: _click.Context | None = None
    contexts: list[_click.Context] = []
    command_path: list[str] = []
    parameters: list[InspectedParameter] = []

    try:
        while True:
            info_name = command_path[-1] if command_path else current.name or "app"
            raw_values = _raw_parameter_values(
                current,
                current_args,
                info_name=info_name,
                parent=parent,
            )
            ctx = current.make_context(info_name, current_args, parent=parent)
            contexts.append(ctx)
            parameters.extend(_parameters_from_context(current, ctx, raw_values))

            if not isinstance(current, TyperGroup):
                if not command_path:
                    command_path.append(current.name or "<command>")
                break

            remaining_args = [*ctx._protected_args, *ctx.args]
            if not remaining_args:
                if current.invoke_without_command:
                    if not command_path:
                        command_path.append(current.name or "<command>")
                    break
                ctx.fail("Missing command.")

            command_name, next_command, next_args = current.resolve_command(
                ctx, remaining_args
            )
            if next_command is None:  # pragma: no cover - resolve_command raises
                ctx.fail(f"No such command {command_name!r}.")
            assert command_name is not None
            command_path.append(command_name)
            parent = ctx
            current = next_command
            current_args = next_args

        return InspectedInvocation(
            command_path=" ".join(command_path), parameters=parameters
        )
    finally:
        for ctx in reversed(contexts):
            ctx.close()


def _type_name(value: Any) -> str:
    value_type = type(value)
    if value_type.__module__ == "builtins":
        return value_type.__qualname__
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _source_name(source: ParameterSource | None) -> str:
    if source is None:
        return "unknown"
    return source.name.lower().replace("_", " ")


def _show_commands(command: _click.Command) -> None:
    paths = _command_paths(command)
    _click.echo("\nCommands:")
    if not paths:
        _click.echo("  (none)")
    for path in paths:
        _click.echo(f"  {path}")
    _click.echo()


def _show_inspection(command: _click.Command, invocation: str) -> None:
    try:
        args = shlex.split(invocation)
    except ValueError as exc:
        _click.echo(f"Invalid invocation: {exc}", err=True)
        return

    try:
        inspected = inspect_invocation(command, args)
    except _click.ClickException as exc:
        _click.echo(f"Inspection error: {exc.format_message()}", err=True)
        return

    _click.echo(f"\nResolved command: {inspected.command_path}")
    _click.echo("Parameters:")
    if not inspected.parameters:
        _click.echo("  (none)")
    for parameter in inspected.parameters:
        _click.echo(f"  {parameter.name}")
        raw = (
            "(not provided)"
            if parameter.raw_value is _missing
            else repr(parameter.raw_value)
        )
        _click.echo(f"    Raw value: {raw}")
        _click.echo(f"    Resolved value: {parameter.value!r}")
        _click.echo(f"    Type: {_type_name(parameter.value)}")
        _click.echo(f"    Source: {_source_name(parameter.source)}")
    _click.echo()


def run_menu(command: _click.Command) -> None:
    _click.echo("Typer Application Menu")
    while True:
        _click.echo("1. Explore commands")
        _click.echo("2. Inspect invocation")
        _click.echo("3. Exit")
        try:
            choice = prompt("Select an option", type=str).strip().lower()
        except (EOFError, Abort):
            _click.echo("\nLeaving menu.")
            return

        if choice in {"1", "explore", "commands"}:
            _show_commands(command)
        elif choice in {"2", "inspect"}:
            try:
                invocation = prompt("Invocation", type=str)
            except (EOFError, Abort):
                _click.echo("\nLeaving menu.")
                return
            _show_inspection(command, invocation)
        elif choice in {"3", "exit", "quit", "q"}:
            _click.echo("Leaving menu.")
            return
        else:
            _click.echo("Please choose Explore (1), Inspect (2), or Exit (3).")

"""Structured, callback-free inspection of Typer applications."""

from __future__ import annotations

import inspect
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from . import _click
from ._click import types
from ._click.core import ParameterSource
from ._types import TyperChoice
from .core import TyperGroup, TyperOption
from .models import TyperPath

if TYPE_CHECKING:
    from .main import Typer


class _MissingValue:
    def __repr__(self) -> str:
        return "(not provided)"


class _RedactedValue:
    def __repr__(self) -> str:
        return "[REDACTED]"


MISSING = _MissingValue()
REDACTED = _RedactedValue()


def type_name(value: Any) -> str:
    value_type = type(value)
    if value_type.__module__ == "builtins":
        return value_type.__qualname__
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _safe_display(value: Any) -> str:
    if value is MISSING or value is REDACTED:
        return repr(value)
    if inspect.isroutine(value) or inspect.isclass(value):
        module = getattr(value, "__module__", "")
        qualname = getattr(value, "__qualname__", type_name(value))
        return f"{module}.{qualname}" if module else qualname
    try:
        return repr(value)
    except Exception:
        return f"<{type_name(value)}>"


def json_safe(value: Any) -> Any:
    """Return a JSON-compatible representation without requiring custom objects."""
    if value is MISSING:
        return {"state": "not_provided"}
    if value is REDACTED:
        return {"redacted": True, "display": "[REDACTED]"}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return {
            "python_type": type_name(value),
            "display": _safe_display(value),
            "items": [json_safe(item) for item in value],
        }
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, Enum):
        return {
            "python_type": type_name(value),
            "display": _safe_display(value),
            "value": json_safe(value.value),
        }
    return {
        "python_type": type_name(value),
        "display": _safe_display(value),
    }


def _source_name(source: ParameterSource | None) -> str:
    if source is None:
        return "unknown"
    return source.name.lower().replace("_", " ")


@dataclass(frozen=True)
class ParameterContract:
    name: str
    kind: str
    python_type: str
    click_type: str
    required: bool
    default: Any
    option_names: tuple[str, ...] = ()
    secondary_option_names: tuple[str, ...] = ()
    envvar: str | tuple[str, ...] | None = None
    multiple: bool = False
    nargs: int = 1
    count: bool = False
    hidden: bool = False
    sensitive: bool = False
    help: str | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "python_type": self.python_type,
            "click_type": self.click_type,
            "required": self.required,
            "default": json_safe(self.default),
            "option_names": list(self.option_names),
            "secondary_option_names": list(self.secondary_option_names),
            "envvar": self.envvar,
            "multiple": self.multiple,
            "nargs": self.nargs,
            "count": self.count,
            "hidden": self.hidden,
            "sensitive": self.sensitive,
            "help": self.help,
            "constraints": json_safe(dict(self.constraints)),
        }


@dataclass(frozen=True)
class CommandContract:
    path: str
    name: str
    parent_path: str | None
    help: str | None
    short_help: str | None
    hidden: bool
    deprecated: bool | str
    is_group: bool
    parameters: tuple[ParameterContract, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "parent_path": self.parent_path,
            "help": self.help,
            "short_help": self.short_help,
            "hidden": self.hidden,
            "deprecated": self.deprecated,
            "is_group": self.is_group,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }


@dataclass(frozen=True)
class ApplicationContract:
    root_name: str
    commands: tuple[CommandContract, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "typer_application_contract",
            "root_name": self.root_name,
            "commands": [command.to_dict() for command in self.commands],
        }


@dataclass(frozen=True)
class InspectedParameter:
    command_path: str
    name: str
    raw_value: Any
    value: Any
    python_type: str | None
    source: ParameterSource | None
    resolved: bool
    sensitive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_path": self.command_path,
            "name": self.name,
            "raw_value": json_safe(self.raw_value),
            "resolved_value": json_safe(self.value),
            "python_type": self.python_type,
            "source": _source_name(self.source),
            "resolved": self.resolved,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True)
class InspectionFailure:
    stage: str
    message: str
    command_path: str
    parameter: str | None = None
    raw_value: Any = MISSING
    expected_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "message": self.message,
            "command_path": self.command_path,
            "parameter": self.parameter,
            "raw_value": json_safe(self.raw_value),
            "expected_type": self.expected_type,
        }


@dataclass(frozen=True)
class InspectionResult:
    command_path: str
    parameters: tuple[InspectedParameter, ...]
    success: bool
    failure: InspectionFailure | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "typer_invocation_inspection",
            "success": self.success,
            "resolved_command": self.command_path,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "failure": self.failure.to_dict() if self.failure else None,
        }


def _as_command(app: Typer | _click.Command) -> _click.Command:
    if isinstance(app, _click.Command):
        return app
    from .main import Typer, get_command

    if not isinstance(app, Typer):
        raise TypeError("Expected a Typer application or Click command.")
    return get_command(app)


def _make_bare_context(
    command: _click.Command,
    *,
    info_name: str,
    parent: _click.Context | None = None,
) -> _click.Context:
    return command.context_class(command, info_name=info_name, parent=parent)


def _annotation_names(command: _click.Command) -> dict[str, str]:
    if command.callback is None:
        return {}
    try:
        signature = inspect.signature(command.callback)
    except (TypeError, ValueError):
        return {}
    result: dict[str, str] = {}
    for name, parameter in signature.parameters.items():
        annotation = parameter.annotation
        if annotation is inspect.Parameter.empty:
            continue
        if isinstance(annotation, type):
            result[name] = (
                annotation.__qualname__
                if annotation.__module__ == "builtins"
                else f"{annotation.__module__}.{annotation.__qualname__}"
            )
        else:
            result[name] = str(annotation)
    return result


def _type_constraints(param_type: types.ParamType) -> dict[str, Any]:
    if isinstance(param_type, (types.IntRange, types.FloatRange)):
        return {
            "numeric_range": {
                "minimum": param_type.min,
                "maximum": param_type.max,
                "minimum_open": param_type.min_open,
                "maximum_open": param_type.max_open,
                "clamp": param_type.clamp,
            }
        }
    if isinstance(param_type, TyperChoice):
        return {
            "choices": list(param_type.choices),
            "case_sensitive": param_type.case_sensitive,
        }
    if isinstance(param_type, TyperPath):
        return {
            "path": {
                "exists": param_type.exists,
                "file_okay": param_type.file_okay,
                "directory_okay": param_type.dir_okay,
                "readable": param_type.readable,
                "writable": param_type.writable,
                "resolve_path": param_type.resolve_path,
                "allow_dash": param_type.allow_dash,
            }
        }
    if isinstance(param_type, types.Tuple):
        return {
            "tuple_types": [
                {"type": item.name, "constraints": _type_constraints(item)}
                for item in param_type.types
            ]
        }
    return {}


def _parameter_contracts(
    command: _click.Command, ctx: _click.Context
) -> tuple[ParameterContract, ...]:
    annotation_names = _annotation_names(command)
    result: list[ParameterContract] = []
    for parameter in command.get_params(ctx):
        if parameter.name is None:
            continue
        option = parameter if isinstance(parameter, TyperOption) else None
        sensitive = bool(option and option.hide_input)
        envvar = parameter.envvar
        if envvar is not None and not isinstance(envvar, str):
            envvar = tuple(envvar)
        result.append(
            ParameterContract(
                name=parameter.name,
                kind=parameter.param_type_name,
                python_type=annotation_names.get(parameter.name, parameter.type.name),
                click_type=parameter.type.name,
                required=parameter.required,
                default=REDACTED if sensitive else parameter.default,
                option_names=tuple(option.opts) if option else (),
                secondary_option_names=(tuple(option.secondary_opts) if option else ()),
                envvar=envvar,
                multiple=parameter.multiple,
                nargs=parameter.nargs,
                count=bool(option and option.count),
                hidden=bool(getattr(parameter, "hidden", False)),
                sensitive=sensitive,
                help=getattr(parameter, "help", None),
                constraints=MappingProxyType(_type_constraints(parameter.type)),
            )
        )
    return tuple(result)


def get_application_contract(app: Typer | _click.Command) -> ApplicationContract:
    """Build a reusable contract without invoking registered callbacks."""
    root = _as_command(app)
    contracts: list[CommandContract] = []

    def visit(
        command: _click.Command,
        path_parts: tuple[str, ...],
        parent: _click.Context | None,
    ) -> None:
        name = path_parts[-1] if path_parts else command.name or "app"
        path = " ".join(path_parts)
        parent_path = " ".join(path_parts[:-1]) if path_parts else None
        ctx = _make_bare_context(command, info_name=name, parent=parent)
        try:
            contracts.append(
                CommandContract(
                    path=path,
                    name=name,
                    parent_path=parent_path,
                    help=command.help,
                    short_help=command.short_help,
                    hidden=command.hidden,
                    deprecated=command.deprecated,
                    is_group=isinstance(command, TyperGroup),
                    parameters=_parameter_contracts(command, ctx),
                )
            )
            if isinstance(command, TyperGroup):
                for child_name in command.list_commands(ctx):
                    child = command.get_command(ctx, child_name)
                    if child is not None:
                        visit(child, (*path_parts, child_name), ctx)
        finally:
            ctx.close()

    visit(root, () if isinstance(root, TyperGroup) else (root.name or "command",), None)
    return ApplicationContract(root_name=root.name or "app", commands=tuple(contracts))


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


def _is_sensitive(parameter: _click.Parameter) -> bool:
    return isinstance(parameter, TyperOption) and parameter.hide_input


def _parameter_type_name(parameter: _click.Parameter) -> str:
    return parameter.type.name


def _parameters_from_context(
    command: _click.Command,
    ctx: _click.Context,
    raw_values: dict[str, Any],
    command_path: str,
) -> tuple[list[InspectedParameter], InspectionFailure | None]:
    parameters: list[InspectedParameter] = []
    convertors = getattr(command.callback, "__typer_convertors__", {})
    for parameter in command.get_params(ctx):
        if parameter.name is None:
            continue
        has_value = parameter.name in ctx.params
        has_raw = parameter.name in raw_values
        if not has_value and not has_raw:
            continue
        sensitive = _is_sensitive(parameter)
        source = ctx.get_parameter_source(parameter.name) if has_value else None
        raw_value = raw_values.get(parameter.name, MISSING)
        if source is not ParameterSource.COMMANDLINE:
            raw_value = MISSING
        value = ctx.params.get(parameter.name, MISSING)
        resolved = has_value
        if has_value and parameter.name in convertors:
            try:
                value = convertors[parameter.name](value)
                ctx.params[parameter.name] = value
            except Exception as exc:
                parameters.append(
                    InspectedParameter(
                        command_path=command_path,
                        name=parameter.name,
                        raw_value=REDACTED if sensitive else raw_value,
                        value=REDACTED if sensitive else MISSING,
                        python_type=None,
                        source=source,
                        resolved=False,
                        sensitive=sensitive,
                    )
                )
                return parameters, InspectionFailure(
                    stage="typer conversion",
                    message=(
                        "Conversion failed for a sensitive parameter."
                        if sensitive
                        else str(exc)
                    ),
                    command_path=command_path,
                    parameter=parameter.name,
                    raw_value=REDACTED if sensitive else raw_value,
                    expected_type=_parameter_type_name(parameter),
                )
        stored_value = REDACTED if sensitive else value
        parameters.append(
            InspectedParameter(
                command_path=command_path,
                name=parameter.name,
                raw_value=REDACTED if sensitive else raw_value,
                value=stored_value,
                python_type=type_name(stored_value)
                if resolved and not sensitive
                else None,
                source=source,
                resolved=resolved,
                sensitive=sensitive,
            )
        )
    return parameters, None


def _failure_from_exception(
    exc: _click.ClickException,
    command_path: str,
    raw_values: dict[str, Any],
) -> InspectionFailure:
    parameter = getattr(exc, "param", None)
    parameter_name = parameter.name if parameter is not None else None
    sensitive = parameter is not None and _is_sensitive(parameter)
    return InspectionFailure(
        stage="parameter conversion" if parameter is not None else "command parsing",
        message=(
            "Invalid value for a sensitive parameter."
            if sensitive
            else exc.format_message()
        ),
        command_path=command_path,
        parameter=parameter_name,
        raw_value=(
            REDACTED
            if sensitive
            else raw_values.get(parameter_name, MISSING)
            if parameter_name is not None
            else MISSING
        ),
        expected_type=(
            _parameter_type_name(parameter) if parameter is not None else None
        ),
    )


def inspect_invocation(
    app: Typer | _click.Command, args: Sequence[str]
) -> InspectionResult:
    """Parse an invocation with Typer's runtime model without invoking callbacks."""
    current = _as_command(app)
    current_args = list(args)
    parent: _click.Context | None = None
    contexts: list[_click.Context] = []
    command_path: list[str] = []
    parameters: list[InspectedParameter] = []

    try:
        while True:
            info_name = command_path[-1] if command_path else current.name or "app"
            path = " ".join(command_path) or current.name or "<command>"
            try:
                raw_values = _raw_parameter_values(
                    current, current_args, info_name=info_name, parent=parent
                )
            except _click.ClickException as exc:
                return InspectionResult(
                    command_path=path,
                    parameters=tuple(parameters),
                    success=False,
                    failure=_failure_from_exception(exc, path, {}),
                )

            try:
                ctx = current.make_context(info_name, current_args, parent=parent)
            except _click.ClickException as exc:
                failed_ctx = getattr(exc, "ctx", None)
                if failed_ctx is not None and failed_ctx not in contexts:
                    contexts.append(failed_ctx)
                    partial, _ = _parameters_from_context(
                        current, failed_ctx, raw_values, path
                    )
                    parameters.extend(partial)
                return InspectionResult(
                    command_path=path,
                    parameters=tuple(parameters),
                    success=False,
                    failure=_failure_from_exception(exc, path, raw_values),
                )

            contexts.append(ctx)
            inspected, conversion_failure = _parameters_from_context(
                current, ctx, raw_values, path
            )
            parameters.extend(inspected)
            if conversion_failure:
                return InspectionResult(
                    command_path=path,
                    parameters=tuple(parameters),
                    success=False,
                    failure=conversion_failure,
                )

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
                failure = InspectionFailure(
                    stage="command resolution",
                    message="Missing command.",
                    command_path=" ".join(command_path),
                )
                return InspectionResult(
                    command_path=" ".join(command_path),
                    parameters=tuple(parameters),
                    success=False,
                    failure=failure,
                )

            try:
                command_name, next_command, next_args = current.resolve_command(
                    ctx, remaining_args
                )
            except _click.ClickException as exc:
                return InspectionResult(
                    command_path=" ".join(command_path),
                    parameters=tuple(parameters),
                    success=False,
                    failure=_failure_from_exception(exc, " ".join(command_path), {}),
                )
            if next_command is None:
                return InspectionResult(
                    command_path=" ".join(command_path),
                    parameters=tuple(parameters),
                    success=False,
                    failure=InspectionFailure(
                        stage="command resolution",
                        message=f"No such command {command_name!r}.",
                        command_path=" ".join(command_path),
                    ),
                )
            assert command_name is not None
            command_path.append(command_name)
            parent = ctx
            current = next_command
            current_args = next_args

        return InspectionResult(
            command_path=" ".join(command_path),
            parameters=tuple(parameters),
            success=True,
        )
    finally:
        for ctx in reversed(contexts):
            ctx.close()

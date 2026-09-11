from io import StringIO
from typing import IO, Any

from . import _click
from ._click.globals import get_current_context
from .core import HAS_RICH

DEVELOPER_MODE_KEY = "typer.developer_mode"


def is_developer_mode() -> bool:
    """Return whether developer mode is active for the current invocation."""
    ctx = get_current_context(silent=True)
    if ctx is None:
        return False
    return bool(ctx.meta.get(DEVELOPER_MODE_KEY, False))


def _qualified_type_name(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _safe_str(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return "<str unavailable>"


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return "<repr unavailable>"


def _render_plain(message: Any) -> str:
    return "\n".join(
        (
            "Value",
            f"type: {_qualified_type_name(message)}",
            f"value: {_safe_str(message)}",
            f"repr: {_safe_repr(message)}",
        )
    )


def _render_rich(message: Any) -> str:
    from rich.console import Console, Group
    from rich.text import Text

    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, color_system="auto")
    renderable = Group(
        Text("Value", style="bold"),
        Text.assemble(("type: ", "bold cyan"), _qualified_type_name(message)),
        Text.assemble(("value: ", "bold green"), _safe_str(message)),
        Text.assemble(("repr: ", "bold magenta"), _safe_repr(message)),
    )
    console.print(renderable, end="")
    return buffer.getvalue()


def _render_structured(message: Any) -> str:
    if HAS_RICH:
        return _render_rich(message)
    return _render_plain(message)


def echo(
    message: Any | None = None,
    file: IO[Any] | None = None,
    nl: bool = True,
    err: bool = False,
    color: bool | None = None,
) -> None:
    """Print output using Click semantics, with structured developer rendering.

    Outside developer mode this delegates directly to Click's ``echo``. When
    developer mode is active, the original Python object is inspected before
    string conversion and rendered with type, value, and repr information.
    """
    if not is_developer_mode():
        return _click.echo(message, file=file, nl=nl, err=err, color=color)

    rendered = _render_structured(message)
    _click.echo(rendered, file=file, nl=nl, err=err, color=color)

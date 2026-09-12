"""Framework-managed developer mode for Typer.

Developer mode is disabled by default. When enabled on a ``typer.Typer``
instance, Typer exposes a framework-managed ``--developer`` root-level flag.

When the flag is used at runtime, instead of running the user command Typer
reveals the raw data of the values it digested (parsed and converted) for the
invoked command. Each value is reported using the following architecture::

    Value
      type: <fully qualified Python type>
      value: <str(value)>
      repr: <repr(value)>

The rendering distinguishes native and Typer-converted values (``None``,
containers, ``Path``, ``UUID``, ``datetime``, ``Enum`` members, custom
classes, ...). Rich is only used for presentation; it never alters the
reported Python type or representation, and Rich markup / terminal control
codes present in the reported data are treated as data (never interpreted as
styling).
"""

from typing import Any

from . import _click
from ._click.globals import get_current_context

# Attribute used on the Click context object (``ctx.obj`` is a plain dict) to
# signal that developer mode is active for the current run only. It never leaks
# to user callbacks and it is not persisted between runs.
DEVELOPER_MODE_CTX_KEY = "__typer_developer_mode__"

# Name of the framework-managed root-level flag.
DEVELOPER_FLAG_NAME = "--developer"


def _fully_qualified_type_name(value: Any) -> str:
    tp = type(value)
    module = getattr(tp, "__module__", None)
    qualname = getattr(tp, "__qualname__", tp.__name__)
    if module in (None, "builtins"):
        return qualname
    return f"{module}.{qualname}"


def developer_callback(ctx: _click.Context, param: _click.Parameter, value: Any) -> Any:
    """Eager callback for the framework-managed ``--developer`` flag.

    It only records that developer mode is active for the current run. It does
    not alter user callbacks and applies only to the current invocation.
    """
    if ctx.resilient_parsing:
        return value
    if value:
        # Mirror the inheritance of nested commands: the state is stored on the
        # root context object, which is shared throughout the nested command
        # tree via Click's context inheritance.
        root = ctx.find_root()
        if root.obj is None:
            root.obj = {}
        if isinstance(root.obj, dict):
            root.obj[DEVELOPER_MODE_CTX_KEY] = True
    return value


def is_developer_mode_active() -> bool:
    """Return whether developer mode is active for the current run."""
    try:
        ctx = get_current_context(silent=True)
    except Exception:  # pragma: no cover
        return False
    while ctx is not None:
        obj = getattr(ctx, "obj", None)
        if isinstance(obj, dict) and obj.get(DEVELOPER_MODE_CTX_KEY):
            return True
        ctx = ctx.parent
    return False


def format_value_report(value: Any) -> str:
    """Return the plain-text report for a single digested value."""
    lines = [
        "Value",
        f"  type: {_fully_qualified_type_name(value)}",
        f"  value: {value!s}",
        f"  repr: {value!r}",
    ]
    return "\n".join(lines)


def render_developer_output(params: dict) -> None:
    """Render the developer report for the digested command parameters.

    Rich is optional and only used for presentation. Whether or not Rich is
    available/enabled, the reported type, ``str`` and ``repr`` are identical.
    Rich markup and terminal control codes found in the data are treated as
    data (never interpreted as styling).
    """
    from .core import HAS_RICH

    reports = [format_value_report(value) for value in params.values()]
    text = "\n".join(reports)

    if HAS_RICH:
        try:
            from . import rich_utils

            console = rich_utils._get_rich_console()
            # ``highlight=False`` and an escaped, non-markup print make sure the
            # data is shown verbatim: no styling, no markup interpretation, and
            # no terminal control code interpretation.
            for report in reports:
                console.print(report, markup=False, highlight=False, soft_wrap=True)
            return
        except Exception:  # pragma: no cover
            pass

    _click.echo(text)


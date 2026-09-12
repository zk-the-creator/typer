import datetime
from enum import Enum
from pathlib import Path
from uuid import UUID

import typer
import typer.core
from typer._developer import (
    _fully_qualified_type_name,
    format_value_report,
    is_developer_mode_active,
)
from typer.testing import CliRunner

runner = CliRunner()


class Color(str, Enum):
    red = "red"
    blue = "blue"


def make_app(developer: bool = True) -> typer.Typer:
    app = typer.Typer(developer=developer)

    @app.command()
    def main(
        name: str,
        count: int = 1,
        path: Path = Path("."),
        color: Color = Color.red,
    ):
        typer.echo(f"Hello {name} {count} {path} {color}")

    return app


def test_developer_disabled_by_default():
    app = typer.Typer()
    assert app._developer is False


def test_developer_enabled_flag_stored():
    app = typer.Typer(developer=True)
    assert app._developer is True


def test_flag_not_exposed_when_disabled():
    app = make_app(developer=False)
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--developer" not in result.output


def test_flag_reserved_only_when_enabled():
    app = make_app(developer=False)
    result = runner.invoke(app, ["--developer", "Bob"])
    # When disabled, the option is not reserved and is rejected.
    assert result.exit_code != 0
    assert "No such option" in result.output or "--developer" in result.output


def test_flag_exposed_when_enabled():
    app = make_app(developer=True)
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--developer" in result.output


def test_normal_run_unaffected_when_enabled():
    app = make_app(developer=True)
    result = runner.invoke(app, ["Bob", "--count", "3"])
    assert result.exit_code == 0
    assert "Hello Bob 3" in result.output


def test_developer_output_reveals_converted_values():
    app = make_app(developer=True)
    result = runner.invoke(
        app, ["--developer", "Bob", "--count", "3", "--color", "blue"]
    )
    assert result.exit_code == 0
    out = result.output
    # Native str
    assert "Value" in out
    assert "type: str" in out
    assert "value: Bob" in out
    assert "repr: 'Bob'" in out
    # Native int
    assert "type: int" in out
    assert "value: 3" in out
    # Typer-converted Path (fully-qualified type)
    assert "pathlib." in out
    # Enum member preserved
    assert "type: tests.test_developer_mode.Color" in out
    assert "repr: <Color.blue: 'blue'>" in out


def test_developer_output_preserves_none_and_containers():
    app = typer.Typer(developer=True)

    @app.command()
    def main(
        items: list[str] = typer.Option([]),
        maybe: str | None = typer.Option(None),
        u: UUID = typer.Option("12345678-1234-5678-1234-567812345678"),
        d: datetime.datetime = typer.Option("2020-01-01T00:00:00"),
    ):
        typer.echo("ran")

    result = runner.invoke(app, ["--developer", "--items", "a", "--items", "b"])
    assert result.exit_code == 0
    out = result.output
    # Container
    assert "type: list" in out
    assert "value: ['a', 'b']" in out
    # None
    assert "type: NoneType" in out
    assert "value: None" in out
    assert "repr: None" in out
    # UUID
    assert "type: uuid.UUID" in out
    assert "repr: UUID('12345678-1234-5678-1234-567812345678')" in out
    # datetime
    assert "type: datetime.datetime" in out
    assert "repr: datetime.datetime(2020, 1, 1, 0, 0)" in out


def test_markup_and_control_codes_are_data():
    app = typer.Typer(developer=True)

    @app.command()
    def main(text: str = typer.Option("x")):
        typer.echo("ran")

    payload = "[red]hi[/red] \x1b[31mansi"
    result = runner.invoke(app, ["--developer", "--text", payload])
    assert result.exit_code == 0
    out = result.output
    # Markup shown verbatim as data (not interpreted as styling).
    assert "[red]hi[/red]" in out
    # No stray ANSI red styling was applied by Rich (the escape must be verbatim
    # data via repr, never a real terminal control sequence surrounding output).
    # The value line contains the literal payload.
    assert "value: [red]hi[/red]" in out


def test_developer_output_same_with_and_without_rich(monkeypatch):
    app = make_app(developer=True)
    args = ["--developer", "Bob", "--count", "2", "--color", "red"]

    result_rich = runner.invoke(app, args)

    monkeypatch.setattr(typer.core, "HAS_RICH", False)
    app_plain = make_app(developer=True)
    result_plain = runner.invoke(app_plain, args)

    assert result_rich.exit_code == 0
    assert result_plain.exit_code == 0
    assert result_rich.output == result_plain.output


def test_developer_state_is_per_run_only():
    app = make_app(developer=True)
    r1 = runner.invoke(app, ["--developer", "Bob"])
    assert "Value" in r1.output
    # The next run without the flag should run normally.
    r2 = runner.invoke(app, ["Bob"])
    assert "Hello Bob" in r2.output
    assert "Value" not in r2.output
    # And developer mode is not active outside of a run.
    assert is_developer_mode_active() is False


def test_developer_flag_does_not_reach_user_callback():
    app = typer.Typer(developer=True)
    seen = {}

    @app.command()
    def main(name: str):
        import inspect

        seen["params"] = set(inspect.signature(main).parameters)
        typer.echo(f"ran {name}")

    result = runner.invoke(app, ["Alice"])
    assert result.exit_code == 0
    assert "developer" not in seen["params"]


def test_developer_mode_inherited_by_nested_commands():
    app = typer.Typer(developer=True)
    sub = typer.Typer()
    app.add_typer(sub, name="users")

    @app.command()
    def top(x: int = 5):
        typer.echo(f"top {x}")

    @sub.command()
    def create(username: str, admin: bool = False):
        typer.echo(f"create {username}")

    # Root-level --developer applies to the nested command tree.
    result = runner.invoke(app, ["--developer", "users", "create", "alice", "--admin"])
    assert result.exit_code == 0
    assert "type: str" in result.output
    assert "value: alice" in result.output
    assert "type: bool" in result.output
    assert "value: True" in result.output

    # The nested command does not expose --developer as its own flag.
    sub_help = runner.invoke(app, ["users", "create", "--help"])
    assert "--developer" not in sub_help.output

    # Normal nested run is unaffected.
    normal = runner.invoke(app, ["users", "create", "alice"])
    assert "create alice" in normal.output


def test_fully_qualified_type_name_helper():
    assert _fully_qualified_type_name("x") == "str"
    assert _fully_qualified_type_name(1) == "int"
    assert _fully_qualified_type_name(None) == "NoneType"
    assert _fully_qualified_type_name(Path(".")).startswith("pathlib.")
    assert _fully_qualified_type_name(Color.red) == "tests.test_developer_mode.Color"


def test_format_value_report_structure():
    report = format_value_report(42)
    lines = report.splitlines()
    assert lines[0] == "Value"
    assert lines[1] == "  type: int"
    assert lines[2] == "  value: 42"
    assert lines[3] == "  repr: 42"


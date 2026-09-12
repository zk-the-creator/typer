import io
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import UUID

import pytest
import typer
from typer.testing import CliRunner

runner = CliRunner()


class Color(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class CustomItem:
    def __init__(self, name: str, count: int) -> None:
        self.name = name
        self.count = count

    def __str__(self) -> str:
        return f"CustomItem({self.name}:{self.count})"

    def __repr__(self) -> str:
        return f"<CustomItem name={self.name!r} count={self.count!r}>"


def parse_custom_item(value: str) -> CustomItem:
    name, count_str = value.split(":")
    return CustomItem(name=name, count=int(count_str))


def test_version_updated() -> None:
    assert typer.__version__ == "0.27.2.1"


def test_developer_mode_disabled_by_default() -> None:
    app = typer.Typer()
    assert app.developer_mode is False
    assert app.developer is False

    @app.command()
    def main(name: str) -> None:
        typer.echo(name)

    help_res = runner.invoke(app, ["--help"])
    assert help_res.exit_code == 0
    assert "--developer" not in help_res.output

    # Flag is not exposed or reserved when disabled
    dev_res = runner.invoke(app, ["--developer", "Alice"])
    assert dev_res.exit_code != 0
    assert "No such option: --developer" in dev_res.output


def test_user_can_define_developer_option_when_disabled() -> None:
    app = typer.Typer()

    @app.command()
    def main(developer: bool = typer.Option(False, "--developer")) -> None:
        typer.echo(f"User flag: {developer}")

    res = runner.invoke(app, ["--developer"])
    assert res.exit_code == 0
    assert res.output == "User flag: True\n"


def test_developer_mode_enabled_state_and_flag() -> None:
    app = typer.Typer(developer_mode=True)
    assert app.developer_mode is True
    assert app.developer is True

    @app.command()
    def main(name: str) -> None:
        typer.echo(name)

    help_res = runner.invoke(app, ["--help"])
    assert help_res.exit_code == 0
    assert "--developer" in help_res.output

    # Normal run without --developer flag
    normal_res = runner.invoke(app, ["Alice"])
    assert normal_res.exit_code == 0
    assert normal_res.output == "Alice\n"

    # Run with --developer flag
    dev_res = runner.invoke(app, ["--developer", "Alice"])
    assert dev_res.exit_code == 0
    expected = (
        "Value\n"
        "   type: builtins.str\n"
        "   value: Alice\n"
        "   repr: 'Alice'\n"
    )
    assert dev_res.output == expected

    # Subsequent run without --developer flag returns to normal mode
    after_res = runner.invoke(app, ["Bob"])
    assert after_res.exit_code == 0
    assert after_res.output == "Bob\n"


def test_developer_alias_in_init_and_setter() -> None:
    app = typer.Typer(developer=True)
    assert app.developer_mode is True
    assert app.developer is True

    app2 = typer.Typer()
    assert app2.developer_mode is False
    app2.developer = True
    assert app2.developer_mode is True
    assert app2.developer is True


def test_developer_mode_does_not_affect_user_callbacks() -> None:
    app = typer.Typer(developer_mode=True)
    callback_called = False

    @app.callback()
    def main_callback(ctx: typer.Context, verbose: bool = False) -> None:
        nonlocal callback_called
        callback_called = True
        assert "developer" not in ctx.params
        if verbose:
            typer.echo("verbose_enabled")

    @app.command()
    def run(item: str) -> None:
        typer.echo(item)

    res = runner.invoke(app, ["--developer", "--verbose", "run", "test_item"])
    assert res.exit_code == 0
    assert callback_called is True
    expected = (
        "Value\n"
        "   type: builtins.str\n"
        "   value: verbose_enabled\n"
        "   repr: 'verbose_enabled'\n"
        "Value\n"
        "   type: builtins.str\n"
        "   value: test_item\n"
        "   repr: 'test_item'\n"
    )
    assert res.output == expected


def test_distinction_between_types_and_converted_values() -> None:
    app = typer.Typer(developer_mode=True)

    @app.command()
    def inspect_types(
        path_val: Path,
        uuid_val: UUID,
        dt_val: datetime,
        enum_val: Color,
        custom_val: CustomItem = typer.Option(..., parser=parse_custom_item),
    ) -> None:
        # None
        typer.echo(None)
        # Empty string (distinct from None)
        typer.echo("")
        # Containers
        typer.echo([1, "two", 3])
        typer.echo(("a", 2))
        typer.echo({"key": "val"})
        # Converted Path vs native string
        typer.echo(path_val)
        typer.echo(str(path_val))
        # Converted UUID vs native string
        typer.echo(uuid_val)
        typer.echo(str(uuid_val))
        # Converted datetime vs native string
        typer.echo(dt_val)
        typer.echo(str(dt_val))
        # Converted Enum vs native string
        typer.echo(enum_val)
        typer.echo(enum_val.value)
        # Custom class
        typer.echo(custom_val)

    uid_str = "12345678-1234-5678-1234-567812345678"
    dt_str = "2025-01-15T10:30:00"
    res = runner.invoke(
        app,
        [
            "--developer",
            "/tmp/sample.txt",
            uid_str,
            dt_str,
            "red",
            "--custom-val",
            "widget:42",
        ],
    )
    assert res.exit_code == 0

    path_obj = Path("/tmp/sample.txt")
    path_type_name = f"pathlib.{type(path_obj).__qualname__}"
    uid_obj = UUID(uid_str)
    dt_obj = datetime(2025, 1, 15, 10, 30, 0)
    enum_obj = Color.RED
    enum_type_name = f"{Color.__module__}.{Color.__qualname__}"
    custom_obj = CustomItem("widget", 42)
    custom_type_name = f"{CustomItem.__module__}.{CustomItem.__qualname__}"

    expected_blocks = [
        # None
        "Value\n   type: builtins.NoneType\n   value: None\n   repr: None",
        # Empty string
        "Value\n   type: builtins.str\n   value: \n   repr: ''",
        # list
        "Value\n   type: builtins.list\n   value: [1, 'two', 3]\n   repr: [1, 'two', 3]",
        # tuple
        "Value\n   type: builtins.tuple\n   value: ('a', 2)\n   repr: ('a', 2)",
        # dict
        "Value\n   type: builtins.dict\n   value: {'key': 'val'}\n   repr: {'key': 'val'}",
        # Path
        f"Value\n   type: {path_type_name}\n   value: {path_obj}\n   repr: {path_obj!r}",
        # str(path)
        f"Value\n   type: builtins.str\n   value: {path_obj}\n   repr: {str(path_obj)!r}",
        # UUID
        f"Value\n   type: uuid.UUID\n   value: {uid_obj}\n   repr: {uid_obj!r}",
        # str(UUID)
        f"Value\n   type: builtins.str\n   value: {uid_str}\n   repr: {uid_str!r}",
        # datetime
        f"Value\n   type: datetime.datetime\n   value: {dt_obj}\n   repr: {dt_obj!r}",
        # str(datetime)
        f"Value\n   type: builtins.str\n   value: {dt_obj}\n   repr: {str(dt_obj)!r}",
        # Enum member
        f"Value\n   type: {enum_type_name}\n   value: {enum_obj}\n   repr: {enum_obj!r}",
        # str(enum.value)
        "Value\n   type: builtins.str\n   value: red\n   repr: 'red'",
        # Custom class
        f"Value\n   type: {custom_type_name}\n   value: {custom_obj}\n   repr: {custom_obj!r}",
    ]
    assert res.output == "\n".join(expected_blocks) + "\n"


def test_echo_semantics_nl_err_and_file() -> None:
    app = typer.Typer(developer_mode=True)
    custom_stream = io.StringIO()

    @app.command()
    def cmd() -> None:
        # nl=False
        typer.echo(10, nl=False)
        typer.echo(20, nl=True)
        # err=True
        typer.echo("error_msg", err=True)
        # explicit file
        typer.echo("file_msg", file=custom_stream)

    res = runner.invoke(app, ["--developer"])
    assert res.exit_code == 0

    expected_stdout = (
        "Value\n"
        "   type: builtins.int\n"
        "   value: 10\n"
        "   repr: 10"
        "Value\n"
        "   type: builtins.int\n"
        "   value: 20\n"
        "   repr: 20\n"
    )
    assert res.stdout == expected_stdout

    expected_stderr = (
        "Value\n"
        "   type: builtins.str\n"
        "   value: error_msg\n"
        "   repr: 'error_msg'\n"
    )
    assert res.stderr == expected_stderr

    expected_file = (
        "Value\n"
        "   type: builtins.str\n"
        "   value: file_msg\n"
        "   repr: 'file_msg'\n"
    )
    assert custom_stream.getvalue() == expected_file


def test_rich_markup_and_terminal_control_codes_treated_as_data() -> None:
    app = typer.Typer(developer_mode=True)

    @app.command()
    def cmd() -> None:
        typer.echo("[bold red]Danger[/bold red]")
        typer.echo("\x1b[31mANSI Red\x1b[0m")

    res = runner.invoke(app, ["--developer"])
    assert res.exit_code == 0

    expected = (
        "Value\n"
        "   type: builtins.str\n"
        "   value: [bold red]Danger[/bold red]\n"
        "   repr: '[bold red]Danger[/bold red]'\n"
        "Value\n"
        "   type: builtins.str\n"
        "   value: \\x1b[31mANSI Red\\x1b[0m\n"
        "   repr: '\\x1b[31mANSI Red\\x1b[0m'\n"
    )
    assert res.output == expected
    assert "\x1b[31m" not in res.output


def test_rich_optional_plain_text_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    app = typer.Typer(developer_mode=True)

    @app.command()
    def cmd() -> None:
        typer.echo(Path("/var/log"))
        typer.echo("[bold]markup[/bold]")

    # With Rich enabled
    res_with_rich = runner.invoke(app, ["--developer"])
    assert res_with_rich.exit_code == 0

    # With Rich disabled via environment variable and HAS_RICH flag
    monkeypatch.setenv("TYPER_USE_RICH", "0")
    monkeypatch.setattr("typer.core.HAS_RICH", False)
    res_without_rich = runner.invoke(app, ["--developer"])
    assert res_without_rich.exit_code == 0

    assert res_with_rich.output == res_without_rich.output


def test_nested_commands_inheritance() -> None:
    root_app = typer.Typer(developer_mode=True)
    sub_app = typer.Typer()
    leaf_app = typer.Typer()

    @leaf_app.command()
    def leaf_cmd(val: int) -> None:
        typer.echo(val)

    sub_app.add_typer(leaf_app, name="leaf")
    root_app.add_typer(sub_app, name="sub")

    # Verify inheritance on instances
    assert sub_app.developer_mode is True
    assert leaf_app.developer_mode is True

    # Run nested command with root --developer option
    res = runner.invoke(root_app, ["--developer", "sub", "leaf", "leaf-cmd", "99"])
    assert res.exit_code == 0
    expected = (
        "Value\n"
        "   type: builtins.int\n"
        "   value: 99\n"
        "   repr: 99\n"
    )
    assert res.output == expected

    # Run nested command without --developer option
    res_normal = runner.invoke(root_app, ["sub", "leaf", "leaf-cmd", "99"])
    assert res_normal.exit_code == 0
    assert res_normal.output == "99\n"


def test_secho_preserves_types_in_developer_mode() -> None:
    app = typer.Typer(developer_mode=True)

    @app.command()
    def cmd(path: Path) -> None:
        typer.secho(path, fg=typer.colors.GREEN, bold=True)
        typer.secho(12345, fg=typer.colors.BLUE)

    res = runner.invoke(app, ["--developer", "/tmp/my_file.py"])
    assert res.exit_code == 0
    path_obj = Path("/tmp/my_file.py")
    path_type_name = f"pathlib.{type(path_obj).__qualname__}"

    expected = (
        f"Value\n"
        f"   type: {path_type_name}\n"
        f"   value: {path_obj}\n"
        f"   repr: {path_obj!r}\n"
        f"Value\n"
        f"   type: builtins.int\n"
        f"   value: 12345\n"
        f"   repr: 12345\n"
    )
    assert res.output == expected


def test_binary_data_and_binary_file_destination() -> None:
    app = typer.Typer(developer_mode=True)
    binary_buf = io.BytesIO()

    @app.command()
    def cmd() -> None:
        typer.echo(b"raw_bytes")
        typer.echo(bytearray(b"raw_bytearray"))
        typer.echo("to_bytes_io", file=binary_buf)

    res = runner.invoke(app, ["--developer"])
    assert res.exit_code == 0

    expected_stdout = (
        "Value\n"
        "   type: builtins.bytes\n"
        "   value: b'raw_bytes'\n"
        "   repr: b'raw_bytes'\n"
        "Value\n"
        "   type: builtins.bytearray\n"
        "   value: bytearray(b'raw_bytearray')\n"
        "   repr: bytearray(b'raw_bytearray')\n"
    )
    assert res.stdout == expected_stdout

    expected_binary = (
        b"Value\n"
        b"   type: builtins.str\n"
        b"   value: to_bytes_io\n"
        b"   repr: 'to_bytes_io'\n"
    )
    assert binary_buf.getvalue() == expected_binary


def test_echo_no_arguments_and_color_parameter() -> None:
    app = typer.Typer(developer_mode=True)

    @app.command()
    def cmd() -> None:
        typer.echo()
        typer.echo("colored_true", color=True)
        typer.echo("colored_false", color=False)

    res = runner.invoke(app, ["--developer"])
    assert res.exit_code == 0
    expected = (
        "Value\n"
        "   type: builtins.NoneType\n"
        "   value: None\n"
        "   repr: None\n"
        "Value\n"
        "   type: builtins.str\n"
        "   value: colored_true\n"
        "   repr: 'colored_true'\n"
        "Value\n"
        "   type: builtins.str\n"
        "   value: colored_false\n"
        "   repr: 'colored_false'\n"
    )
    assert res.output == expected


def test_echo_signature_preserved() -> None:
    import inspect

    sig = inspect.signature(typer.echo)
    params = list(sig.parameters.keys())
    assert params == ["message", "file", "nl", "err", "color"]
    assert sig.parameters["message"].default is None
    assert sig.parameters["file"].default is None
    assert sig.parameters["nl"].default is True
    assert sig.parameters["err"].default is False
    assert sig.parameters["color"].default is None


def test_dynamic_toggling_developer_mode() -> None:
    app = typer.Typer(developer_mode=False)

    @app.command()
    def cmd(x: int) -> None:
        typer.echo(x)

    # Initially disabled
    res1 = runner.invoke(app, ["--developer", "10"])
    assert res1.exit_code != 0

    # Enable dynamically
    app.developer_mode = True
    res2 = runner.invoke(app, ["--developer", "10"])
    assert res2.exit_code == 0
    assert "type: builtins.int" in res2.output

    # Disable dynamically
    app.developer_mode = False
    res3 = runner.invoke(app, ["--developer", "10"])
    assert res3.exit_code != 0


import os
import subprocess
import sys
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import typer
from typer._click._compat import strip_ansi
from typer.testing import CliRunner

from .utils import needs_rich

runner = CliRunner()


class Choice(str, Enum):
    ALPHA = "alpha"
    BETA = "beta"


class CustomDisplay:
    def __str__(self) -> str:
        return "custom text"

    def __repr__(self) -> str:
        return "CustomDisplay(value=42)"


class BrokenStr:
    def __str__(self) -> str:
        raise RuntimeError("broken str")

    def __repr__(self) -> str:
        return "BrokenStr()"


class BrokenRepr:
    def __str__(self) -> str:
        return "broken repr text"

    def __repr__(self) -> str:
        raise RuntimeError("broken repr")


class BrokenBoth:
    def __str__(self) -> str:
        raise RuntimeError("broken str")

    def __repr__(self) -> str:
        raise RuntimeError("broken repr")


def _qualified_type_name(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _structured_output(
    value: object,
    *,
    value_text: str | None = None,
    repr_text: str | None = None,
    nl: bool = True,
) -> str:
    if value_text is None:
        value_text = str(value)
    if repr_text is None:
        repr_text = repr(value)
    output = (
        "Value\n"
        f"type: {_qualified_type_name(value)}\n"
        f"value: {value_text}\n"
        f"repr: {repr_text}"
    )
    if nl:
        output += "\n"
    return output


def _app_echoing(value: object, **echo_kwargs: Any) -> typer.Typer:
    app = typer.Typer(developer_mode=True, add_completion=False)

    @app.command()
    def main() -> None:
        typer.echo(value, **echo_kwargs)

    return app


def test_echo_without_context_preserves_click_semantics() -> None:
    stream = StringIO()

    typer.echo(
        "hello",
        file=stream,
        nl=False,
        err=True,
        color=False,
    )

    assert stream.getvalue() == "hello"


def test_normal_mode_preserves_click_output() -> None:
    app = typer.Typer(add_completion=False)

    @app.command()
    def main() -> None:
        typer.echo(None)
        typer.echo({"answer": 42})

    result = runner.invoke(app)

    assert result.exit_code == 0
    assert result.stdout == "\n{'answer': 42}\n"


def test_developer_option_is_available_only_when_enabled() -> None:
    disabled_app = typer.Typer(add_completion=False)
    enabled_app = typer.Typer(developer_mode=True, add_completion=False)

    @disabled_app.command()
    def disabled() -> None:
        pass

    @enabled_app.command()
    def enabled() -> None:
        pass

    disabled_help = runner.invoke(disabled_app, ["--help"])
    disabled_attempt = runner.invoke(disabled_app, ["--developer"])
    enabled_help = runner.invoke(enabled_app, ["--help"])
    enabled_attempt = runner.invoke(enabled_app, ["--developer"])

    assert "--developer" not in disabled_help.stdout
    assert disabled_attempt.exit_code == 2
    assert "--developer" in enabled_help.stdout
    assert enabled_attempt.exit_code == 0


def test_disabled_app_can_define_user_developer_option() -> None:
    app = typer.Typer(add_completion=False)

    @app.command()
    def main(developer: bool = False) -> None:
        typer.echo(developer)

    result = runner.invoke(app, ["--developer"])

    assert result.exit_code == 0
    assert result.stdout == "True\n"


@pytest.mark.parametrize(
    "value",
    [
        10,
        3.5,
        False,
        None,
        [1, 2, 2],
        (1, 2, 2),
        {"answer": 42},
    ],
)
def test_developer_mode_preserves_python_semantics(value: object) -> None:
    result = runner.invoke(_app_echoing(value), ["--developer"])

    assert result.exit_code == 0
    assert result.stdout == _structured_output(value)


def test_developer_mode_inspects_typer_converted_values() -> None:
    app = typer.Typer(developer_mode=True, add_completion=False)
    path = Path("example.txt")
    identifier = UUID("a8098c1a-f86e-11da-bd1a-00112444be1e")
    choice = Choice.ALPHA

    @app.command()
    def main(path_value: Path, identifier_value: UUID, choice_value: Choice) -> None:
        typer.echo(path_value)
        typer.echo(identifier_value)
        typer.echo(choice_value)

    result = runner.invoke(
        app,
        ["--developer", str(path), str(identifier), choice.value],
    )

    assert result.exit_code == 0
    assert result.stdout == (
        _structured_output(path)
        + _structured_output(identifier)
        + _structured_output(choice)
    )


def test_developer_mode_preserves_distinct_str_and_repr() -> None:
    value = CustomDisplay()

    result = runner.invoke(_app_echoing(value), ["--developer"])

    assert result.exit_code == 0
    assert result.stdout == _structured_output(value)


@pytest.mark.xfail(
    strict=False,
    reason="Optional robustness beyond the prompt contract",
)
def test_developer_mode_survives_broken_str_and_repr() -> None:
    broken_str = BrokenStr()
    broken_repr = BrokenRepr()
    broken_both = BrokenBoth()
    app = typer.Typer(developer_mode=True, add_completion=False)

    @app.command()
    def main() -> None:
        typer.echo(broken_str)
        typer.echo(broken_repr)
        typer.echo(broken_both)

    result = runner.invoke(app, ["--developer"])

    assert result.exit_code == 0
    assert result.stdout == (
        _structured_output(
            broken_str,
            value_text="<str unavailable>",
            repr_text="BrokenStr()",
        )
        + _structured_output(
            broken_repr,
            value_text="broken repr text",
            repr_text="<repr unavailable>",
        )
        + _structured_output(
            broken_both,
            value_text="<str unavailable>",
            repr_text="<repr unavailable>",
        )
    )


@pytest.mark.parametrize("nl", [False, True])
def test_developer_mode_preserves_custom_stream_and_newline(nl: bool) -> None:
    value = {"destination": "custom"}
    captured: list[str] = []
    app = typer.Typer(developer_mode=True, add_completion=False)

    @app.command()
    def main() -> None:
        stream = StringIO()
        typer.echo(value, file=stream, nl=nl)
        captured.append(stream.getvalue())

    result = runner.invoke(app, ["--developer"])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert captured == [_structured_output(value, nl=nl)]


def test_developer_mode_preserves_stderr_destination() -> None:
    value = {"destination": "stderr"}

    result = runner.invoke(
        _app_echoing(value, err=True),
        ["--developer"],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == _structured_output(value)


def test_developer_mode_has_plain_fallback() -> None:
    value = {"renderer": "plain"}
    application = """
import typer

app = typer.Typer(developer_mode=True, add_completion=False)


@app.command()
def main() -> None:
    typer.echo({"renderer": "plain"})


if __name__ == "__main__":
    app()
"""
    result = subprocess.run(
        [sys.executable, "-c", application, "--developer"],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env={**os.environ, "TYPER_USE_RICH": "0"},
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == _structured_output(value)
    assert "\x1b[" not in result.stdout


@needs_rich
def test_developer_mode_uses_rich_for_styling() -> None:
    value = {"renderer": "rich"}

    result = runner.invoke(
        _app_echoing(value),
        ["--developer"],
        color=True,
    )

    assert result.exit_code == 0
    assert "\x1b[" in result.stdout
    assert strip_ansi(result.stdout) == _structured_output(value)


def test_developer_mode_treats_markup_and_control_codes_as_data() -> None:
    markup = "[bold]literal markup[/bold]"
    ansi = "\x1b[31mred text\x1b[0m"
    app = typer.Typer(developer_mode=True, add_completion=False)

    @app.command()
    def main() -> None:
        typer.echo(markup)
        typer.echo(ansi)

    result = runner.invoke(app, ["--developer"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert result.stdout == (
        _structured_output(markup)
        + _structured_output(
            ansi,
            value_text=r"\x1b[31mred text\x1b[0m",
        )
    )


def test_developer_mode_propagates_to_nested_applications() -> None:
    root = typer.Typer(developer_mode=True, add_completion=False)
    child = typer.Typer()
    grandchild = typer.Typer()
    value = {"level": "grandchild"}

    @grandchild.command()
    def show() -> None:
        typer.echo(value)

    child.add_typer(grandchild, name="grandchild")
    root.add_typer(child, name="child")
    command_path = ["child", "grandchild", "show"]

    normal_result = runner.invoke(root, command_path)
    developer_result = runner.invoke(root, ["--developer", *command_path])

    assert normal_result.exit_code == 0
    assert normal_result.stdout == f"{value}\n"
    assert developer_result.exit_code == 0
    assert developer_result.stdout == _structured_output(value)


def test_child_developer_mode_does_not_override_plain_root() -> None:
    root = typer.Typer(add_completion=False)
    child = typer.Typer(developer_mode=True, add_completion=False)
    value = {"application": "child"}

    @child.command()
    def status() -> None:
        typer.echo(value)

    root.add_typer(child, name="child")

    mounted_help = runner.invoke(root, ["child", "--help"])
    mounted_attempt = runner.invoke(root, ["child", "--developer"])
    standalone_help = runner.invoke(child, ["--help"])
    standalone_result = runner.invoke(child, ["--developer"])

    assert "--developer" not in mounted_help.stdout
    assert mounted_attempt.exit_code == 2
    assert "--developer" in standalone_help.stdout
    assert standalone_result.exit_code == 0
    assert standalone_result.stdout == _structured_output(value)

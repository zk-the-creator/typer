from pathlib import Path

from typer.cli import app as typer_cli_app
from typer.testing import CliRunner

runner = CliRunner()
menu_app = "tests/assets/cli/menu_app.py"


def test_menu_explores_and_inspects_without_callback(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input=("1\n2\nprocess data.json --count 5 --verbose --output-format json\n3\n"),
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "process" in result.output
    assert "admin deploy" in result.output
    assert "Resolved command: process" in result.output
    assert "Raw value: '5'" in result.output
    assert "Resolved value: 5" in result.output
    assert "Type: int" in result.output
    assert "Resolved value: True" in result.output
    assert "Type: bool" in result.output
    assert "Type: pathlib." in result.output
    assert "OutputFormat" in result.output
    assert not sentinel.exists()


def test_menu_displays_defaults_and_nested_command(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    result = runner.invoke(
        typer_cli_app,
        ["--menu", menu_app],
        input="2\nadmin deploy production --force\n3\n",
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Resolved command: admin deploy" in result.output
    assert "Resolved value: 'production'" in result.output
    assert "Resolved value: True" in result.output
    assert not sentinel.exists()


def test_menu_displays_default_values_without_flattening_types() -> None:
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input="2\nprocess data.json\n3\n",
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Raw value: (not provided)" in result.output
    assert "Resolved value: 1" in result.output
    assert "Resolved value: False" in result.output
    assert "Type: pathlib." in result.output
    assert "OutputFormat.text" in result.output


def test_menu_recovers_after_invalid_inspection(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input="2\nprocess data.json --count nope\n1\n3\n",
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Inspection error:" in result.output
    assert "not a valid int" in result.output
    assert "Commands:" in result.output
    assert "Leaving menu." in result.output
    assert not sentinel.exists()


def test_menu_supports_single_command_app() -> None:
    result = runner.invoke(
        typer_cli_app,
        ["tests/assets/cli/rich_formatted_app.py", "--menu"],
        input="2\nNeo --force\n3\n",
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Resolved command: hello" in result.output
    assert "Resolved value: 'Neo'" in result.output
    assert "Resolved value: True" in result.output
    assert "Hello Neo" not in result.output


def test_normal_execution_is_unchanged(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "run", "process", "data.json", "--count", "2"],
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "process:data.json:2:False:text" in result.output
    assert sentinel.read_text() == "process:data.json:2:False:text"

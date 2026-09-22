import json
from pathlib import Path

import pytest
from typer.cli import app as typer_cli_app
from typer.inspection import get_application_contract, inspect_invocation
from typer.testing import CliRunner

from tests.assets.cli import menu_app as menu_module

runner = CliRunner()
menu_app = "tests/assets/cli/menu_app.py"


def test_menu_explores_and_inspects_without_callback(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input=("1\n2\nprocess data.json --count 5 --verbose --output-format json\n6\n"),
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "process" in result.output
    assert "admin deploy" in result.output
    assert "admin legacy-deploy (hidden, deprecated)" in result.output
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
        input="2\nadmin deploy production --force\n6\n",
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
        input="2\nprocess data.json\n6\n",
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
        input="2\nprocess data.json --count nope\n1\n6\n",
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Inspection error:" in result.output
    assert "not a valid int" in result.output
    assert "Inspection: failed" in result.output
    assert "Raw value: 'nope'" in result.output
    assert "Commands:" in result.output
    assert "Leaving menu." in result.output
    assert not sentinel.exists()


def test_menu_supports_single_command_app() -> None:
    result = runner.invoke(
        typer_cli_app,
        ["tests/assets/cli/rich_formatted_app.py", "--menu"],
        input="2\nNeo --force\n6\n",
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


def test_contract_is_reusable_and_covers_hidden_commands() -> None:
    menu_module.app._add_completion = False
    contract = get_application_contract(menu_module.app)
    data = contract.to_dict()

    commands = {command["path"]: command for command in data["commands"]}
    assert "admin legacy-deploy" in commands
    assert commands["admin legacy-deploy"]["hidden"] is True
    process = commands["process"]
    parameters = {parameter["name"]: parameter for parameter in process["parameters"]}
    assert parameters["verbose"]["option_names"] == ["--verbose"]
    assert parameters["verbose"]["secondary_option_names"] == ["--quiet"]
    assert parameters["count"]["envvar"] == "PROCESS_COUNT"
    assert parameters["count"]["constraints"]["numeric_range"] == {
        "minimum": 1,
        "maximum": 10,
        "minimum_open": False,
        "maximum_open": False,
        "clamp": False,
    }
    assert parameters["source"]["constraints"]["path"]["file_okay"] is True
    assert parameters["source"]["constraints"]["path"]["directory_okay"] is False
    assert parameters["output_format"]["constraints"]["choices"] == [
        "text",
        "json",
    ]
    assert parameters["secret"]["default"] == {
        "redacted": True,
        "display": "[REDACTED]",
    }
    assert "classified" not in json.dumps(data)


def test_contract_menu_rendering_and_json_export(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "callback-ran"
    output_path = tmp_path / "contract.json"
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input=f"3\n4\n{output_path}\n6\n",
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Application contract:" in result.output
    assert "admin legacy-deploy [command, hidden, deprecated]" in result.output
    assert "numeric_range" in result.output
    assert "Sensitive: True (values redacted)" in result.output
    assert "classified" not in result.output
    exported = json.loads(output_path.read_text())
    assert exported["kind"] == "typer_application_contract"
    assert "classified" not in output_path.read_text()
    assert not sentinel.exists()


def test_successful_inspection_json_preserves_python_types(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "callback-ran"
    output_path = tmp_path / "inspection.json"
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input=(
            f"2\nprocess data.json --count 5 --secret revealed\n5\n{output_path}\n6\n"
        ),
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Enter a complete command path" in result.output
    assert "process data.json --count 5 --secret revealed" in result.output
    assert "[REDACTED]" in result.output
    exported_text = output_path.read_text()
    exported = json.loads(exported_text)
    assert exported["success"] is True
    parameters = {parameter["name"]: parameter for parameter in exported["parameters"]}
    assert parameters["count"]["raw_value"] == "5"
    assert parameters["count"]["resolved_value"] == 5
    assert parameters["count"]["python_type"] == "int"
    assert parameters["source"]["resolved_value"]["python_type"] == "pathlib.PosixPath"
    assert parameters["secret"]["raw_value"]["redacted"] is True
    assert "revealed" not in exported_text
    assert not sentinel.exists()


def test_failed_inspection_is_partial_and_exportable(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    output_path = tmp_path / "failed-inspection.json"
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input=f"2\nprocess data.json --count nope\n5\n{output_path}\n6\n",
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    exported = json.loads(output_path.read_text())
    assert exported["success"] is False
    assert exported["resolved_command"] == "process"
    assert exported["failure"]["stage"] == "parameter conversion"
    assert exported["failure"]["parameter"] == "count"
    assert exported["failure"]["raw_value"] == "nope"
    assert exported["parameters"]
    assert not sentinel.exists()


def test_public_inspection_api_never_invokes_registered_callbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "callback-ran"
    monkeypatch.setenv("TYPER_MENU_SENTINEL", str(sentinel))
    menu_module.app._add_completion = False

    result = inspect_invocation(
        menu_module.app, ["admin", "deploy", "production", "--force"]
    )

    assert result.success is True
    assert result.command_path == "admin deploy"
    assert not sentinel.exists()


def test_export_refuses_to_replace_discovered_source() -> None:
    original = Path(menu_app).read_text()
    result = runner.invoke(
        typer_cli_app,
        [menu_app, "--menu"],
        input=f"4\n{menu_app}\n6\n",
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "source file cannot be replaced" in result.output
    assert Path(menu_app).read_text() == original


def test_no_registered_callback_kind_can_run_through_menu() -> None:
    result = runner.invoke(
        typer_cli_app,
        ["tests/assets/cli/menu_callbacks_app.py", "--menu"],
        input="1\n3\n2\nhello Neo\n6\n",
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "Resolved command: hello" in result.output
    assert "callback executed" not in result.output

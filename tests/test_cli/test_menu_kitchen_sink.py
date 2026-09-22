import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.cli import app as typer_cli_app
from typer.testing import CliRunner

from tests.assets.cli import menu_invalid_apps
from tests.assets.cli import menu_kitchen_sink_app as kitchen_sink

runner = CliRunner()
kitchen_sink_path = "tests/assets/cli/menu_kitchen_sink_app.py"


def _commands_by_path() -> dict[str, dict[str, Any]]:
    kitchen_sink.app._add_completion = False
    contract = typer.get_application_contract(kitchen_sink.app).to_dict()
    return {command["path"]: command for command in contract["commands"]}


def _parameters_by_name(command: dict[str, Any]) -> dict[str, dict[str, Any]]:
    parameters = command["parameters"]
    assert isinstance(parameters, list)
    return {parameter["name"]: parameter for parameter in parameters}


def test_kitchen_sink_contract_covers_the_runtime_surface(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    commands = _commands_by_path()

    assert set(commands) == {
        "",
        "typed",
        "defaults",
        "admin",
        "admin deploy",
        "admin legacy",
        "admin users",
        "admin users create",
        "admin users purge",
    }
    assert commands["admin legacy"]["hidden"] is True
    assert commands["admin legacy"]["deprecated"] is True
    assert commands["admin users purge"]["hidden"] is True
    assert commands["admin users create"]["parent_path"] == "admin users"

    root_parameters = _parameters_by_name(commands[""])
    assert root_parameters["profile"]["option_names"] == ["--profile", "-p"]
    assert root_parameters["profile"]["envvar"] == (
        "TYPER_TEST_PROFILE",
        "PROFILE",
    )

    parameters = _parameters_by_name(commands["typed"])
    assert parameters["coordinates"]["nargs"] == 2
    assert parameters["coordinates"]["constraints"]["tuple_types"] == [
        {"type": "int", "constraints": {}},
        {"type": "float", "constraints": {}},
    ]
    assert parameters["count"]["constraints"]["numeric_range"]["minimum"] == 1
    assert parameters["count"]["constraints"]["numeric_range"]["maximum"] == 10
    assert parameters["ratio"]["constraints"]["numeric_range"]["clamp"] is True
    assert parameters["mode"]["constraints"] == {
        "choices": ["fast", "careful"],
        "case_sensitive": False,
    }
    assert parameters["source"]["constraints"]["path"] == {
        "exists": True,
        "file_okay": True,
        "directory_okay": False,
        "readable": True,
        "writable": False,
        "resolve_path": True,
        "allow_dash": False,
    }
    assert parameters["verbose"]["secondary_option_names"] == ["--quiet"]
    assert parameters["retry"]["count"] is True
    assert parameters["tags"]["multiple"] is True
    assert parameters["internal_note"]["hidden"] is True
    assert parameters["secret"]["sensitive"] is True
    assert parameters["secret"]["default"] == {
        "redacted": True,
        "display": "[REDACTED]",
    }
    assert "fixture-secret-default" not in json.dumps(commands)
    assert not sentinel.exists()


def test_kitchen_sink_inspection_preserves_types_sources_and_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "callback-ran"
    monkeypatch.setenv("TYPER_MENU_SENTINEL", str(sentinel))
    monkeypatch.setenv("PROFILE", "qa")
    monkeypatch.setenv("TYPER_TEST_COUNT", "8")
    kitchen_sink.app._add_completion = False

    result = typer.inspect_invocation(
        kitchen_sink.app,
        [
            "typed",
            "report",
            "7",
            "2.5",
            "--source",
            "pyproject.toml",
            "--ratio",
            "2.0",
            "--mode",
            "CAREFUL",
            "--format",
            "json",
            "--tag",
            "alpha",
            "--tag",
            "beta",
            "--verbose",
            "--retry",
            "--retry",
            "--request-id",
            "12345678-1234-5678-1234-567812345678",
            "--scheduled-at",
            "2026-09-22T14:30",
            "--artifact",
            "build:42",
            "--secret",
            "do-not-export",
        ],
    )

    assert result.success is True
    assert result.command_path == "typed"
    parameters = {parameter.name: parameter.to_dict() for parameter in result.parameters}
    assert parameters["profile"]["resolved_value"] == "qa"
    assert parameters["profile"]["source"] == "environment"
    assert parameters["coordinates"]["python_type"] == "tuple"
    assert parameters["coordinates"]["resolved_value"]["items"] == [7, 2.5]
    assert parameters["source"]["resolved_value"]["python_type"].startswith(
        "pathlib."
    )
    assert parameters["count"]["resolved_value"] == 8
    assert parameters["count"]["source"] == "environment"
    assert parameters["ratio"]["resolved_value"] == 1.0
    assert parameters["mode"]["resolved_value"] == "careful"
    assert parameters["mode"]["python_type"].endswith(".RunMode")
    assert parameters["tags"]["resolved_value"] == ["alpha", "beta"]
    assert parameters["verbose"]["resolved_value"] is True
    assert parameters["retry"]["resolved_value"] == 2
    assert parameters["request_id"]["resolved_value"]["python_type"] == "uuid.UUID"
    assert (
        parameters["scheduled_at"]["resolved_value"]["python_type"]
        == "datetime.datetime"
    )
    assert parameters["artifact"]["resolved_value"]["python_type"].endswith(
        ".ArtifactRef"
    )
    assert parameters["secret"]["raw_value"]["redacted"] is True
    assert parameters["secret"]["resolved_value"]["redacted"] is True
    assert "do-not-export" not in json.dumps(result.to_dict())
    assert not sentinel.exists()


def test_kitchen_sink_menu_black_box_session(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    contract_path = tmp_path / "contract.json"
    success_path = tmp_path / "success.json"
    failure_path = tmp_path / "failure.json"
    success_invocation = (
        "typed report 7 2.5 --source pyproject.toml --mode careful "
        "--format json --tag alpha --verbose --retry "
        "--artifact build:42 --secret never-serialize"
    )
    failed_invocation = (
        "typed report 7 2.5 --source pyproject.toml --count nope"
    )
    result = runner.invoke(
        typer_cli_app,
        [kitchen_sink_path, "--menu"],
        input=(
            f"1\n3\n4\n{contract_path}\n"
            f"2\n{success_invocation}\n5\n{success_path}\n"
            f"2\n{failed_invocation}\n5\n{failure_path}\n"
            "2\nadmin users missing-command\n6\n"
        ),
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
        prog_name="typer",
    )

    assert result.exit_code == 0
    assert "admin users create" in result.output
    assert "admin legacy (hidden, deprecated)" in result.output
    assert "Application contract:" in result.output
    assert "Inspection: successful" in result.output
    assert "Inspection: failed" in result.output
    assert "not a valid int" in result.output
    assert "No such command 'missing-command'" in result.output
    assert "Leaving menu." in result.output
    assert success_invocation in result.output
    assert "Resolved value: [REDACTED]" in result.output
    assert "fixture-secret-default" not in result.output

    contract = json.loads(contract_path.read_text())
    success = json.loads(success_path.read_text())
    failure = json.loads(failure_path.read_text())
    assert contract["kind"] == "typer_application_contract"
    assert success["success"] is True
    assert failure["success"] is False
    assert failure["failure"]["parameter"] == "count"
    assert "never-serialize" not in success_path.read_text()
    assert "fixture-secret-default" not in contract_path.read_text()
    assert not sentinel.exists()


def test_intentionally_invalid_app_structures_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "callback-ran"
    monkeypatch.setenv("TYPER_MENU_SENTINEL", str(sentinel))

    with pytest.raises(RuntimeError, match="Could not get a command"):
        typer.get_application_contract(menu_invalid_apps.empty_app)
    with pytest.raises(RuntimeError, match="Type not yet supported"):
        typer.get_application_contract(menu_invalid_apps.unsupported_type_app)
    with pytest.raises(AssertionError, match="doesn't support Union types"):
        typer.get_application_contract(menu_invalid_apps.ambiguous_union_app)

    result = typer.inspect_invocation(menu_invalid_apps.invalid_default_app, [])
    assert result.success is False
    assert result.failure is not None
    assert result.failure.stage == "parameter conversion"
    assert result.failure.parameter == "count"
    assert "not a valid int" in result.failure.message
    assert not sentinel.exists()

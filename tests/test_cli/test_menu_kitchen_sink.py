"""Prompt-level acceptance tests for ``typer --menu`` implementations.

These tests intentionally avoid importing an implementation-specific inspection or
contract API. Menu choices are discovered from their displayed labels, JSON is
validated by meaning rather than an exact schema, and assertions cover only behavior
required by the feature prompt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer import _click
from typer.cli import app as typer_cli_app
from typer.main import get_command
from typer.testing import CliRunner

from tests.assets.cli import menu_invalid_apps

runner = CliRunner()
kitchen_sink_path = "tests/assets/cli/menu_kitchen_sink_app.py"

public_paths = (
    "typed",
    "defaults",
    "admin",
    "admin deploy",
    "admin users",
    "admin users create",
)
all_contract_paths = (*public_paths, "admin legacy", "admin users purge")


def _invoke_menu(
    input_text: str,
    *,
    env: dict[str, str] | None = None,
) -> Any:
    return runner.invoke(
        typer_cli_app,
        [kitchen_sink_path, "--menu"],
        input=input_text,
        env=env,
        prog_name="typer",
    )


def _choice_entries(output: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    patterns = (
        re.compile(r"^\s*\[(?P<token>[^\]]+)\]\s*(?P<label>.+?)\s*$"),
        re.compile(
            r"^\s*(?P<token>[A-Za-z0-9]+)\s*[.):]\s*(?P<label>.+?)\s*$"
        ),
    )
    for line in output.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                entries.append((match.group("token"), match.group("label").lower()))
                break
    return entries


def _menu_choices() -> dict[str, str]:
    probe = _invoke_menu("")
    entries = _choice_entries(probe.output)
    choices: dict[str, str] = {}
    for token, label in entries:
        if "export" in label and "contract" in label:
            choices["export_contract"] = token
        elif "export" in label and any(
            word in label for word in ("inspect", "invocation", "result")
        ):
            choices["export_inspection"] = token
        elif "contract" in label:
            choices["contract"] = token
        elif any(word in label for word in ("inspect", "invocation")):
            choices["inspect"] = token
        elif any(word in label for word in ("explore", "command")):
            choices["explore"] = token
        elif any(word in label for word in ("exit", "quit", "leave")):
            choices["exit"] = token

    required = {
        "explore",
        "inspect",
        "contract",
        "export_contract",
        "export_inspection",
        "exit",
    }
    assert required <= choices.keys(), (
        "The menu must expose labeled choices for exploration, inspection, contract "
        "view/export, inspection export, and exit. Displayed entries were: "
        f"{entries!r}"
    )
    return choices


def _walk_json(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()


def _contains_redaction(value: Any) -> bool:
    text = _json_text(value)
    return any(
        marker in text
        for marker in ("redact", "censor", "masked", "hidden", "********")
    )


def _named_nodes(value: Any, parameter_name: str) -> list[Any]:
    """Find parameter records in either list-of-records or name-keyed schemas."""
    matches: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if normalized_key == parameter_name:
                matches.append(child)
            if (
                parameter_name.lower() == str(child).lower()
                and any(word in normalized_key for word in ("name", "parameter", "param"))
            ):
                matches.append(value)
            matches.extend(_named_nodes(child, parameter_name))
    elif isinstance(value, list):
        for child in value:
            matches.extend(_named_nodes(child, parameter_name))
    return matches


def test_menu_exposes_every_required_operation_and_can_exit(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "callback-ran"
    choices = _menu_choices()

    result = _invoke_menu(
        f"{choices['exit']}\n",
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
    )

    assert result.exit_code == 0
    assert not sentinel.exists()


def test_exploration_lists_complete_public_command_paths(tmp_path: Path) -> None:
    sentinel = tmp_path / "callback-ran"
    choices = _menu_choices()

    result = _invoke_menu(
        f"{choices['explore']}\n{choices['exit']}\n",
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
    )

    assert result.exit_code == 0
    for command_path in public_paths:
        assert command_path in result.output
    assert not sentinel.exists()


def test_contract_render_and_export_preserve_prompt_required_semantics(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "callback-ran"
    contract_path = tmp_path / "contract.json"
    choices = _menu_choices()

    result = _invoke_menu(
        (
            f"{choices['contract']}\n"
            f"{choices['export_contract']}\n{contract_path}\n"
            f"{choices['exit']}\n"
        ),
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
    )

    assert result.exit_code == 0
    assert contract_path.exists()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    terminal_text = result.output.lower()
    exported_text = _json_text(contract)

    for command_path in all_contract_paths:
        assert command_path in result.output
        assert command_path in exported_text
    for metadata in ("hidden", "deprecated", "parent"):
        assert metadata in terminal_text
        assert metadata in exported_text
    for parameter in (
        "profile",
        "coordinates",
        "source",
        "count",
        "ratio",
        "mode",
        "output_format",
        "tags",
        "verbose",
        "retry",
        "request_id",
        "scheduled_at",
        "artifact",
        "secret",
        "internal_note",
    ):
        assert parameter in terminal_text
        assert parameter in exported_text
    for option_spelling in (
        "--profile",
        "-p",
        "--source",
        "-s",
        "--verbose",
        "--quiet",
        "--retry",
        "-r",
    ):
        assert option_spelling in result.output
        assert option_spelling in exported_text
    for constraint in (
        "minimum",
        "maximum",
        "choices",
        "exists",
        "readable",
        "file_okay",
        "directory_okay",
    ):
        assert constraint in exported_text

    secret_nodes = _named_nodes(contract, "secret")
    assert secret_nodes
    assert any(_contains_redaction(node) for node in secret_nodes)
    assert "fixture-secret-default" not in exported_text
    assert "legacy-secret" not in exported_text
    assert not sentinel.exists()


def test_successful_inspection_uses_typer_conversion_and_exports_json(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "callback-ran"
    inspection_path = tmp_path / "successful-inspection.json"
    choices = _menu_choices()
    supplied_secret = "do-not-retain-this-secret"
    invocation = (
        "typed report 7 2.5 --source pyproject.toml --count 5 --ratio 2.0 "
        "--mode CAREFUL --format json --tag alpha --tag beta --verbose "
        "--retry --retry --request-id 12345678-1234-5678-1234-567812345678 "
        "--scheduled-at 2026-09-22T14:30 --artifact build:42 "
        f"--secret {supplied_secret}"
    )

    result = _invoke_menu(
        (
            f"{choices['inspect']}\n{invocation}\n"
            f"{choices['export_inspection']}\n{inspection_path}\n"
            f"{choices['exit']}\n"
        ),
        env={
            "TYPER_MENU_SENTINEL": str(sentinel),
            "PROFILE": "quality-assurance",
        },
    )

    assert result.exit_code == 0
    assert inspection_path.exists()
    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    exported_text = _json_text(inspection)
    terminal_text = result.output.lower()

    assert "typed" in terminal_text
    assert "typed" in exported_text
    for parameter in (
        "label",
        "coordinates",
        "source",
        "count",
        "ratio",
        "mode",
        "output_format",
        "tags",
        "verbose",
        "retry",
        "request_id",
        "scheduled_at",
        "artifact",
        "secret",
    ):
        assert parameter in terminal_text
        assert parameter in exported_text

    count_nodes = _named_nodes(inspection, "count")
    assert count_nodes
    count_text = " ".join(_json_text(node) for node in count_nodes)
    assert "raw" in count_text
    assert "resolved" in count_text or "converted" in count_text
    assert "int" in count_text
    assert "5" in count_text

    for expected_type in (
        "tuple",
        "path",
        "runmode",
        "uuid",
        "datetime",
        "artifactref",
    ):
        assert expected_type in exported_text
    assert "build:42" in exported_text or (
        "namespace" in exported_text and "identifier" in exported_text
    )

    secret_nodes = _named_nodes(inspection, "secret")
    assert secret_nodes
    assert any(_contains_redaction(node) for node in secret_nodes)
    assert supplied_secret.lower() not in exported_text
    assert not sentinel.exists()


def test_failed_conversion_exports_partial_structured_result_and_recovers(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "callback-ran"
    failure_path = tmp_path / "failed-inspection.json"
    choices = _menu_choices()
    invocation = "typed report 7 2.5 --source pyproject.toml --count nope"

    result = _invoke_menu(
        (
            f"{choices['inspect']}\n{invocation}\n"
            f"{choices['export_inspection']}\n{failure_path}\n"
            f"{choices['explore']}\n{choices['exit']}\n"
        ),
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
    )

    assert result.exit_code == 0
    assert failure_path.exists()
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    exported_text = _json_text(failure)
    terminal_text = result.output.lower()

    assert "count" in terminal_text
    assert "int" in terminal_text
    assert "nope" in terminal_text
    assert "count" in exported_text
    assert "int" in exported_text
    assert "nope" in exported_text
    assert any(word in exported_text for word in ("error", "failure", "failed"))
    assert "typed" in exported_text
    assert any(value in exported_text for value in ("report", "coordinates", "source"))
    assert "admin users create" in result.output
    assert not sentinel.exists()


def test_invalid_nested_command_is_useful_and_menu_remains_exitable(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "callback-ran"
    choices = _menu_choices()

    result = _invoke_menu(
        (
            f"{choices['inspect']}\nadmin users missing-command\n"
            f"{choices['exit']}\n"
        ),
        env={"TYPER_MENU_SENTINEL": str(sentinel)},
    )

    assert result.exit_code == 0
    assert "missing-command" in result.output
    assert any(
        word in result.output.lower()
        for word in ("invalid", "unknown", "no such", "not found", "error")
    )
    assert not sentinel.exists()


def test_invalid_application_fixtures_are_separate_and_genuinely_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fixture validation only; malformed-app handling is not imposed on agents."""
    sentinel = tmp_path / "callback-ran"
    monkeypatch.setenv("TYPER_MENU_SENTINEL", str(sentinel))

    for app in (
        menu_invalid_apps.empty_app,
        menu_invalid_apps.unsupported_type_app,
        menu_invalid_apps.ambiguous_union_app,
    ):
        with pytest.raises((RuntimeError, AssertionError)):
            get_command(app)

    invalid_default_command = get_command(menu_invalid_apps.invalid_default_app)
    with pytest.raises(_click.ClickException):
        invalid_default_command.make_context("invalid-default", [])
    assert not sentinel.exists()

"""A deliberately broad application for manually exercising ``typer --menu``.

Suggested successful inspection:

    typed report 7 2.5 --source pyproject.toml --mode careful \
        --format json --tag alpha --tag beta --verbose --retry \
        --artifact build:42 --secret do-not-export

Suggested failures:

    typed report 7 2.5 --source missing.txt --count nope
    admin users missing-command

Set ``TYPER_MENU_SENTINEL`` to a file path. Any command, group, or result callback
that runs will create that file and raise, making callback leakage unmistakable.
Set ``TYPER_MENU_ALLOW_CALLBACKS=1`` only when testing ordinary, non-menu execution.
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import typer


class RunMode(str, Enum):
    fast = "fast"
    careful = "careful"


class ArtifactRef:
    def __init__(self, namespace: str, identifier: str) -> None:
        self.namespace = namespace
        self.identifier = identifier

    def __repr__(self) -> str:
        return (
            f"ArtifactRef(namespace={self.namespace!r}, "
            f"identifier={self.identifier!r})"
        )


def parse_artifact(value: str) -> ArtifactRef:
    try:
        namespace, identifier = value.split(":", 1)
    except ValueError:
        raise typer.BadParameter("must use NAMESPACE:IDENTIFIER") from None
    if not namespace or not identifier:
        raise typer.BadParameter("must use NAMESPACE:IDENTIFIER")
    return ArtifactRef(namespace=namespace, identifier=identifier)


def _forbid_callback(kind: str) -> None:
    sentinel = os.environ.get("TYPER_MENU_SENTINEL")
    if sentinel:
        Path(sentinel).write_text(kind, encoding="utf-8")
    if os.environ.get("TYPER_MENU_ALLOW_CALLBACKS") == "1":
        typer.echo(f"CALLBACK EXECUTED: {kind}")
        return
    raise RuntimeError(f"{kind} callback executed through --menu")


def root_callback(
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            "-p",
            envvar=["TYPER_TEST_PROFILE", "PROFILE"],
            help="A root-group option.",
        ),
    ] = "development",
) -> None:
    _forbid_callback(f"root group ({profile})")


def result_callback(result: object, profile: str) -> None:
    _forbid_callback(f"result ({result!r}, {profile})")


app = typer.Typer(
    callback=root_callback,
    result_callback=result_callback,
    help="Kitchen-sink application for testing the inspection menu.",
)
admin_app = typer.Typer(help="Administrative command tree.")
users_app = typer.Typer(help="Three-level nesting fixture.")


@app.command(help="Exercise most supported parameter forms in one invocation.")
def typed(
    label: Annotated[str, typer.Argument(help="A required scalar argument.")],
    coordinates: Annotated[
        tuple[int, float], typer.Argument(help="A fixed-arity tuple argument.")
    ],
    source: Annotated[
        Path,
        typer.Option(
            "--source",
            "-s",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    count: Annotated[
        int,
        typer.Option(
            "--count", min=1, max=10, envvar="TYPER_TEST_COUNT"
        ),
    ] = 3,
    ratio: Annotated[
        float, typer.Option("--ratio", min=0.0, max=1.0, clamp=True)
    ] = 0.5,
    mode: Annotated[
        RunMode, typer.Option("--mode", case_sensitive=False)
    ] = RunMode.fast,
    output_format: Annotated[
        Literal["text", "json", "yaml"], typer.Option("--format")
    ] = "text",
    tags: Annotated[list[str] | None, typer.Option("--tag", "-t")] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose/--quiet", help="A Boolean flag pair.")
    ] = False,
    retry: Annotated[
        int, typer.Option("--retry", "-r", count=True, help="A count option.")
    ] = 0,
    request_id: Annotated[UUID | None, typer.Option("--request-id")] = None,
    scheduled_at: Annotated[
        datetime | None,
        typer.Option("--scheduled-at", formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M"]),
    ] = None,
    artifact: Annotated[
        ArtifactRef | None,
        typer.Option("--artifact", parser=parse_artifact),
    ] = None,
    secret: Annotated[
        str,
        typer.Option(
            "--secret",
            hide_input=True,
            help="Sensitive input that must always be censored.",
        ),
    ] = "fixture-secret-default",
    internal_note: Annotated[
        str, typer.Option("--internal-note", hidden=True)
    ] = "hidden-default",
) -> None:
    _forbid_callback(
        f"typed command ({label}, {coordinates}, {source}, {count}, {ratio}, "
        f"{mode}, {output_format}, {tags}, {verbose}, {retry}, {request_id}, "
        f"{scheduled_at}, {artifact}, {secret}, {internal_note})"
    )


@app.command(help="Exercise defaults and environment-value sources.")
def defaults(
    message: str = "hello",
    enabled: bool = True,
    optional_count: int | None = None,
) -> None:
    _forbid_callback(
        f"defaults command ({message}, {enabled}, {optional_count})"
    )


def admin_callback(
    region: Annotated[str, typer.Option("--region", envvar="ADMIN_REGION")] = "west"
) -> None:
    _forbid_callback(f"admin group ({region})")


admin_app.callback()(admin_callback)


@admin_app.command()
def deploy(
    environment: Annotated[
        Literal["development", "staging", "production"], typer.Argument()
    ],
    force: Annotated[bool, typer.Option("--force/--no-force")] = False,
) -> None:
    _forbid_callback(f"deploy command ({environment}, {force})")


@admin_app.command(hidden=True, deprecated=True)
def legacy(token: Annotated[str, typer.Option(hide_input=True)] = "legacy-secret") -> None:
    _forbid_callback(f"legacy command ({token})")


@users_app.command()
def create(
    username: str,
    roles: Annotated[list[str] | None, typer.Option("--role")] = None,
    active: Annotated[bool, typer.Option("--active/--inactive")] = True,
) -> None:
    _forbid_callback(f"create command ({username}, {roles}, {active})")


@users_app.command(hidden=True)
def purge(username: str) -> None:
    _forbid_callback(f"purge command ({username})")


admin_app.add_typer(users_app, name="users")
app.add_typer(admin_app, name="admin")

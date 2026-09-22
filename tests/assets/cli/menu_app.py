import os
from enum import Enum
from pathlib import Path

import typer


class OutputFormat(str, Enum):
    text = "text"
    json = "json"


admin_app = typer.Typer()


@admin_app.callback()
def admin_callback() -> None:
    _record_callback("admin-group")


@admin_app.command()
def deploy(environment: str, force: bool = False) -> None:
    _record_callback(f"deploy:{environment}:{force}")


@admin_app.command(hidden=True, deprecated=True)
def legacy_deploy(environment: str) -> None:
    _record_callback(f"legacy:{environment}")


app = typer.Typer()
app.add_typer(admin_app, name="admin")


@app.command()
def process(
    source: Path = typer.Argument(..., exists=False, file_okay=True, dir_okay=False),
    count: int = typer.Option(1, min=1, max=10, envvar="PROCESS_COUNT"),
    verbose: bool = typer.Option(False, "--verbose/--quiet"),
    output_format: OutputFormat = OutputFormat.text,
    secret: str = typer.Option(
        "classified", "--secret", hide_input=True, help="A sensitive value."
    ),
) -> None:
    _record_callback(f"process:{source}:{count}:{verbose}:{output_format.value}")


def _record_callback(value: str) -> None:
    sentinel = os.environ.get("TYPER_MENU_SENTINEL")
    if sentinel:
        Path(sentinel).write_text(value)
    typer.echo(value)

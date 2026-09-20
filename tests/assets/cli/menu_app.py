import os
from enum import Enum
from pathlib import Path

import typer


class OutputFormat(str, Enum):
    text = "text"
    json = "json"


admin_app = typer.Typer()


@admin_app.command()
def deploy(environment: str, force: bool = False) -> None:
    _record_callback(f"deploy:{environment}:{force}")


app = typer.Typer()
app.add_typer(admin_app, name="admin")


@app.command()
def process(
    source: Path,
    count: int = 1,
    verbose: bool = False,
    output_format: OutputFormat = OutputFormat.text,
) -> None:
    _record_callback(f"process:{source}:{count}:{verbose}:{output_format.value}")


def _record_callback(value: str) -> None:
    sentinel = os.environ.get("TYPER_MENU_SENTINEL")
    if sentinel:
        Path(sentinel).write_text(value)
    typer.echo(value)

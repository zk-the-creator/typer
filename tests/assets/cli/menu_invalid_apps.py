"""Intentionally invalid applications for testing discovery/build failures.

Select one explicitly with ``--app``; keeping them separate prevents a malformed
application from blocking the valid kitchen-sink fixture.

    typer tests/assets/cli/menu_invalid_apps.py --app empty_app --menu
    typer tests/assets/cli/menu_invalid_apps.py --app unsupported_type_app --menu
    typer tests/assets/cli/menu_invalid_apps.py --app ambiguous_union_app --menu
    typer tests/assets/cli/menu_invalid_apps.py --app invalid_default_app --menu
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import typer


def _forbid_callback(name: str) -> None:
    sentinel = os.environ.get("TYPER_MENU_SENTINEL")
    if sentinel:
        Path(sentinel).write_text(name, encoding="utf-8")
    raise RuntimeError(f"{name} callback executed")


empty_app = typer.Typer()


unsupported_type_app = typer.Typer()


@unsupported_type_app.command()
def unsupported(mapping: dict[str, str]) -> None:
    _forbid_callback(f"unsupported ({mapping})")


ambiguous_union_app = typer.Typer()


@ambiguous_union_app.command()
def ambiguous(value: int | str) -> None:
    _forbid_callback(f"ambiguous ({value})")


invalid_default_app = typer.Typer()


@invalid_default_app.command()
def invalid_default(count: int = cast(int, "not-an-integer")) -> None:
    _forbid_callback(f"invalid default ({count})")

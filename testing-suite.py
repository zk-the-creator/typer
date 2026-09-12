from datetime import datetime
from enum import Enum
from io import StringIO
import os
from pathlib import Path
from uuid import UUID

import typer
from typer.core import HAS_RICH
from typer.testing import CliRunner


class SomeEnum(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class CustomDisplay:
    def __str__(self) -> str:
        return "CustomDisplay as text"

    def __repr__(self) -> str:
        return "CustomDisplay(value=42)"


class BrokenStr:
    def __str__(self) -> str:
        raise RuntimeError("intentional __str__ failure")

    def __repr__(self) -> str:
        return "BrokenStr()"


class BrokenRepr:
    def __str__(self) -> str:
        return "BrokenRepr as text"

    def __repr__(self) -> str:
        raise RuntimeError("intentional __repr__ failure")


class BrokenBoth:
    def __str__(self) -> str:
        raise RuntimeError("intentional __str__ failure")

    def __repr__(self) -> str:
        raise RuntimeError("intentional __repr__ failure")


print("version:", typer.__version__)
print("loaded from:", typer.__file__)

app = typer.Typer(developer_mode=True, add_completion=False)


@app.command()
def main(
    suite_num: int = typer.Argument(..., help="The testing suite number to run."),
    some_path: Path = typer.Option(
        Path("typer/testing.py"),
        help="Path value used by suite 2.",
    ),
    some_uuid: UUID = typer.Option(
        UUID("a8098c1a-f86e-11da-bd1a-00112444be1e"),
        help="UUID value used by suite 2.",
    ),
    some_datetime: datetime = typer.Option(
        datetime(2026, 9, 12, 12, 34, 56),
        help="Datetime value used by suite 2.",
    ),
    some_enum: SomeEnum = typer.Option(
        SomeEnum.A,
        help="Enum value used by suite 2.",
    ),
) -> None:
    match suite_num:
        case 1:
            # Testing Suite 1: Primitive and container types
            values = (
                10,
                3.141589763,
                "neat",
                False,
                None,
                [1, 2, 2, 4, 6],
                (1, 2, 3, 3),
                {1, 2, 3},
                {"A": 1, "B": 2, "C": 3},
            )

            print(
                "\n|==============[SUITE 1: PRIMITIVES / CONTAINERS]==============|"
            )
            for value in values:
                typer.echo(value)

        case 2:
            # Testing Suite 2: Values converted by Typer from CLI text
            print(
                "\n|==============[SUITE 2: TYPER-CONVERTED CLI VALUES]==============|"
            )
            typer.echo(some_path)
            typer.echo(some_uuid)
            typer.echo(some_datetime)
            typer.echo(some_enum)

        case 3:
            # Testing Suite 3: An object with distinct __str__ and __repr__
            print("\n|==============[SUITE 3: CUSTOM CLASS]==============|")
            typer.echo(CustomDisplay())

        case 4:
            # Testing Suite 4: Defensive rendering and Click echo arguments
            print(
                "\n|==============[SUITE 4: FAILURES / ECHO SEMANTICS]==============|"
            )

            print("\n-- Explicit StringIO destination --")
            stream = StringIO()
            typer.echo({"destination": "StringIO"}, file=stream)
            print(repr(stream.getvalue()))

            print("\n-- nl=False (the marker should touch the output) --")
            typer.echo("no trailing newline", nl=False)
            print("<-- marker")

            print("\n-- color=False (rendered output should contain no ANSI codes) --")
            color_stream = StringIO()
            typer.echo({"color": False}, file=color_stream, color=False)
            color_output = color_stream.getvalue()
            print(repr(color_output))
            print("contains ANSI escape:", "\x1b[" in color_output)

            print("\n-- err=True (this section is written to stderr) --")
            typer.echo({"destination": "stderr"}, err=True)

            hostile_values = (
                ("Broken __str__", BrokenStr()),
                ("Broken __repr__", BrokenRepr()),
                ("Broken __str__ and __repr__", BrokenBoth()),
            )
            for label, value in hostile_values:
                print(f"\n-- {label} --")
                try:
                    typer.echo(value)
                except Exception as exception:
                    print(
                        "caught expected normal-mode exception:",
                        f"{type(exception).__name__}: {exception}",
                    )

        case 5:
            # Root developer mode should propagate through child contexts
            print(
                "\n|==============[SUITE 5: NESTED ROOT INHERITANCE]==============|"
            )

            nested_root = typer.Typer(developer_mode=True, add_completion=False)
            child = typer.Typer()
            grandchild = typer.Typer()

            @grandchild.command("show")
            def nested_show() -> None:
                typer.echo({"level": "grandchild"})

            child.add_typer(grandchild, name="grandchild")
            nested_root.add_typer(child, name="child")

            command_path = ["child", "grandchild", "show"]
            runner = CliRunner()
            normal_result = runner.invoke(nested_root, command_path)
            developer_result = runner.invoke(
                nested_root,
                ["--developer", *command_path],
            )

            print("\n-- Nested invocation without --developer --")
            print("exit code:", normal_result.exit_code)
            print(normal_result.output, end="")
            if normal_result.exception:
                print("exception:", repr(normal_result.exception))

            print("\n-- Nested invocation with --developer --")
            print("exit code:", developer_result.exit_code)
            print(developer_result.output, end="")
            if developer_result.exception:
                print("exception:", repr(developer_result.exception))

        case 6:
            # A mounted child cannot introduce developer mode to a plain root
            print(
                "\n|==============[SUITE 6: CHILD CAPABILITY BOUNDARY]==============|"
            )

            plain_root = typer.Typer(add_completion=False)
            enabled_child = typer.Typer(
                developer_mode=True,
                add_completion=False,
            )

            @enabled_child.command()
            def status() -> None:
                typer.echo({"application": "child"})

            plain_root.add_typer(enabled_child, name="child")
            runner = CliRunner()

            mounted_help = runner.invoke(plain_root, ["child", "--help"])
            mounted_attempt = runner.invoke(
                plain_root,
                ["child", "--developer"],
            )
            standalone_help = runner.invoke(enabled_child, ["--help"])
            standalone_run = runner.invoke(enabled_child, ["--developer"])

            print(
                "mounted child help exposes --developer:",
                "--developer" in mounted_help.output,
            )
            print("mounted --developer exit code:", mounted_attempt.exit_code)
            print(
                "standalone child help exposes --developer:",
                "--developer" in standalone_help.output,
            )
            print("standalone --developer exit code:", standalone_run.exit_code)
            print(standalone_run.output, end="")

        case 7:
            # TYPER_USE_RICH is read when Typer is imported, before this case runs
            print("\n|==============[SUITE 7: RICH DISABLED]==============|")
            print("TYPER_USE_RICH:", os.getenv("TYPER_USE_RICH"))
            print("typer.core.HAS_RICH:", HAS_RICH)
            typer.echo({"renderer": "plain", "rich_enabled": HAS_RICH})

        case 8:
            # Values that could be misinterpreted or formatted by Rich
            print("\n|==============[SUITE 8: RICH-SENSITIVE VALUES]==============|")
            rich_sensitive_values = (
                "[bold]this is data, not markup[/bold]",
                "<angle brackets & symbols>",
                "Unicode: café — 東京 — 🐍",
                "first line\nsecond line\nthird line",
                "\x1b[31mraw ANSI-looking text\x1b[0m",
            )
            for value in rich_sensitive_values:
                typer.echo(value)

        case _:
            raise typer.BadParameter(
                "Invalid testing suite number. Choose a number from 1 through 8."
            )


if __name__ == "__main__":
    app()

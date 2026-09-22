import typer


def forbidden_group_callback() -> None:
    raise RuntimeError("group callback executed")


def forbidden_result_callback(value: object) -> None:
    raise RuntimeError("result callback executed")


app = typer.Typer(
    callback=forbidden_group_callback,
    result_callback=forbidden_result_callback,
)


@app.command()
def hello(name: str) -> None:
    raise RuntimeError(f"command callback executed for {name}")

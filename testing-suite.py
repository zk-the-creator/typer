from unittest import case

import typer
from pathlib import Path
from uuid import UUID
from datetime import datetime
from enum import Enum

print("version:", typer.__version__)
print("loaded from:", typer.__file__)

app = typer.Typer(developer_mode=True, add_completion=False)

@app.command()
def main(suite_num : int = typer.Argument(..., help="The testing suite number to run.")):

  match suite_num:
    case 1:
      # Testing Suite 1: Primitives/container types
      some_int = 10
      some_float = 3.141589763
      some_str = "neat"
      some_bool = False
      some_none = None
      some_list = [1,2,2,4,6] # ordered, mutable (elements as well), allows duplicates
      some_tuple = (1,2,3,3) # ordered, immutable, allows duplicates
      some_set = {1,2,3} # unordered, mutable (elements must be immutable), automatically removes duplicates
      some_dict = {"A":1, "B":2, "C":3} # unordered, mutable (elements must be immutable), keys must be unique

      typer.echo("\n|==============[TESTING SUITE 1: PRIMITIVES/CONTAINER TYPES]==============|")
      typer.echo(some_int)
      typer.echo(some_float)
      typer.echo(some_str)
      typer.echo(some_bool)
      typer.echo(some_none)
      typer.echo(some_list)
      typer.echo(some_tuple)
      typer.echo(some_set)
      typer.echo(some_dict)

    case 2:
      # Testing Suite 2: Typer-converted CLI values
      some_path = Path("typer/testing.py")
      some_uuid = UUID('a8098c1a-f86e-11da-bd1a-00112444be1e')
      some_datetime = datetime.now()
      some_enum = Enum("SomeEnum", "A B C")

      typer.echo("\n|==============[TESTING SUITE 2: TYPER-CONVERTED CLI VALUES]==============|")
      typer.echo(some_path)
      typer.echo(some_uuid)
      typer.echo(some_datetime)
      typer.echo(some_enum)

    case 3:
      # Testing Suite 3: Custom classes
      typer.echo("\n|==============[TESTING SUITE 3: CUSTOM CLASSES]==============|")

    case 4:
      # Testing Suite 4: Error handling
      typer.echo("\n|==============[TESTING SUITE 4: ERROR HANDLING]==============|")

    case 5:
      # Testing Suite 5: Nested apps with root inheritance from developer_mode=True
      typer.echo("\n|==============[TESTING SUITE 5: NESTED APPS]==============|")

    case 6:
      # Testing Suite 6: Root without Developer mode, child with it, child should not expose --developer
      typer.echo("\n|==============[TESTING SUITE 6: ROOT WITHOUT DEVELOPER MODE]==============|")

    case 7:
      # Testing Suite 7: TYPER_USE_RICH=0 
      typer.echo("\n|==============[TESTING SUITE 7: TYPER_USE_RICH=0]==============|")

    case 8:
      # Testing Suite 8: Rich-looking markup, Multiline strings, and other rich features.
      typer.echo("\n|==============[TESTING SUITE 8: RICH FEATURES]==============|")

    case _:
      typer.echo("Invalid testing suite number. Please provide a valid suite number (1-8).")

if __name__ == "__main__":
 app()

"""Allow `python -m ghg ...` without installing the console script.

Kept thin on purpose: the argument parsing and exit codes live in `cli.main`, so
`python -m ghg` and the installed `ghg` entry point cannot diverge.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())

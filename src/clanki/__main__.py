"""Clanki CLI entrypoint.

This module allows running clanki as a Python module:
    python3 -m clanki
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())

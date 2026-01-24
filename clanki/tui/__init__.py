"""Textual TUI for Clanki."""

# Import textual_image.renderable early for terminal capability detection.
# This must happen BEFORE the Textual app starts, as per textual-image docs.
# Importing at module load time ensures detection happens before App.run().
import textual_image.renderable  # noqa: F401

from .app import ClankiApp, run_tui

__all__ = ["ClankiApp", "run_tui"]

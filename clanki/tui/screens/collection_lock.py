"""Collection lock error screen for Clanki TUI.

This screen displays a friendly error message when Anki Desktop
has the collection locked, and exits on any key press.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Static


class CollectionLockScreen(Screen[None]):
    """Screen displayed when collection is locked by Anki Desktop."""

    def compose(self) -> ComposeResult:
        yield Center(
            Vertical(
                Static(
                    "[bold red]Collection Locked[/bold red]",
                    id="error-title",
                    markup=True,
                ),
                Static(""),
                Static("Anki Desktop is currently open."),
                Static("Please close Anki and try again."),
                Static(""),
                Static("[dim]Press any key to exit.[/dim]", markup=True),
                classes="done-stats",
            ),
            classes="done-container",
        )

    def on_key(self) -> None:
        """Exit on any key press."""
        self.app.exit(1)

"""Done screen for Clanki TUI.

This screen displays session statistics after completing a review
and allows returning to the deck picker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Static

if TYPE_CHECKING:
    from ..app import ClankiApp


class DoneScreen(Screen[None]):
    """Screen displayed when a review session is complete."""

    BINDINGS = [
        Binding("escape", "back_to_picker", "Back to Decks"),
        Binding("enter", "back_to_picker", "Continue", show=False),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, deck_name: str) -> None:
        super().__init__()
        self._deck_name = deck_name

    @property
    def clanki_app(self) -> "ClankiApp":
        """Get the typed app instance."""
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        stats = self.clanki_app.state.stats

        # Build color-coded ratings breakdown
        ratings_line = (
            f"  [bold #e96c6c]Again[/bold #e96c6c] {stats.again_count}    "
            f"[bold #e0c55a]Hard[/bold #e0c55a] {stats.hard_count}    "
            f"[bold #6cd97e]Good[/bold #6cd97e] {stats.good_count}    "
            f"[bold #5eb5f7]Easy[/bold #5eb5f7] {stats.easy_count}"
        )

        yield Center(
            Vertical(
                Static(
                    "[bold #6cd97e]\u2714 Review Complete[/bold #6cd97e]",
                    id="done-title",
                    markup=True,
                ),
                Static(""),
                Static(f"  [bold]{self._deck_name}[/bold]", markup=True),
                Static(""),
                Static(
                    f"  Cards reviewed: [bold]{stats.reviewed}[/bold]",
                    markup=True,
                ),
                Static(""),
                Static(ratings_line, markup=True),
                Static(""),
                Static(
                    "  [dim]Esc[/dim] Back to Decks    [dim]q[/dim] Quit",
                    markup=True,
                ),
                classes="done-stats",
            ),
            classes="done-container",
        )

    async def action_back_to_picker(self) -> None:
        """Return to the deck picker."""
        # Reset stats for next session
        self.clanki_app.state.stats.reset()

        # Pop back to the existing deck picker on the stack
        self.app.pop_screen()

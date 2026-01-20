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
from textual.widgets import Button, Static

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

        yield Center(
            Vertical(
                Static(
                    "[bold green]Review Complete![/bold green]",
                    id="done-title",
                    markup=True,
                ),
                Static(""),
                Static(f"[bold]{self._deck_name}[/bold]", markup=True),
                Static(""),
                Static(f"Cards reviewed: [bold]{stats.reviewed}[/bold]", markup=True),
                Static(""),
                Static("[dim]Ratings breakdown:[/dim]", markup=True),
                Static(f"  Again (1): {stats.again_count}"),
                Static(f"  Hard  (2): {stats.hard_count}"),
                Static(f"  Good  (3): {stats.good_count}"),
                Static(f"  Easy  (4): {stats.easy_count}"),
                Static(""),
                Button("Back to Decks", id="back-button", variant="primary"),
                classes="done-stats",
            ),
            classes="done-container",
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "back-button":
            await self.action_back_to_picker()

    async def action_back_to_picker(self) -> None:
        """Return to the deck picker."""
        from .deck_picker import DeckPickerScreen

        # Reset stats for next session
        self.clanki_app.state.stats.reset()

        # Switch to deck picker (replace done screen)
        await self.app.switch_screen(DeckPickerScreen())

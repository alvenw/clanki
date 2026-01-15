"""Deck picker screen for Clanki TUI.

This screen displays a filterable list of decks with their due counts,
allowing users to select a deck to start a review session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Input, ListItem, ListView, Static

from ..widgets import AsciiLogo

if TYPE_CHECKING:
    from ..app import ClankiApp


@dataclass
class DeckInfo:
    """Information about a deck for display."""

    deck_id: int
    name: str
    new_count: int
    learn_count: int
    review_count: int

    @property
    def total_due(self) -> int:
        """Total number of cards due."""
        return self.new_count + self.learn_count + self.review_count

    @property
    def display_name(self) -> str:
        """Format deck name for display (show only leaf name with indent)."""
        parts = self.name.split("::")
        indent = "  " * (len(parts) - 1)
        return f"{indent}{parts[-1]}"

    def format_counts(self) -> str:
        """Format counts as new/learn/review string."""
        return f"{self.new_count}/{self.learn_count}/{self.review_count}"


class DeckListItem(ListItem):
    """A list item representing a deck."""

    def __init__(self, deck: DeckInfo) -> None:
        super().__init__()
        self.deck = deck

    def compose(self) -> ComposeResult:
        counts = self.deck.format_counts()
        yield Static(
            f"{self.deck.display_name}  [dim]({counts})[/dim]",
            markup=True,
        )


class DeckPickerScreen(Screen[str]):
    """Screen for selecting a deck to review."""

    BINDINGS = [
        Binding("escape", "app.quit", "Quit"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "select_deck", "Select"),
        Binding("/", "focus_filter", "Filter", show=False),
    ]

    class DeckSelected(Message):
        """Message sent when a deck is selected."""

        def __init__(self, deck_name: str) -> None:
            super().__init__()
            self.deck_name = deck_name

    def __init__(self) -> None:
        super().__init__()
        self._decks: list[DeckInfo] = []
        self._filtered_decks: list[DeckInfo] = []

    @property
    def clanki_app(self) -> "ClankiApp":
        """Get the typed app instance."""
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        yield Vertical(
            AsciiLogo(id="logo"),
            Input(placeholder="Filter decks...", id="filter-input"),
            ListView(id="deck-list"),
            Static(
                "[dim]j/k[/dim] navigate  [dim]Enter[/dim] select  [dim]q[/dim] quit",
                classes="help-text",
                markup=True,
            ),
        )

    async def on_mount(self) -> None:
        """Load decks when screen mounts."""
        self._load_decks()
        self._update_list()
        # Focus the list
        self.query_one("#deck-list", ListView).focus()

    def _load_decks(self) -> None:
        """Load deck information from collection."""
        col = self.clanki_app.state.col
        if col is None:
            return

        tree = col.sched.deck_due_tree()
        self._decks = []
        self._flatten_tree(tree)
        self._filtered_decks = self._decks.copy()

    def _flatten_tree(self, node: Any, depth: int = 0) -> None:
        """Flatten deck tree into a list."""
        # Skip the root node (has no meaningful name)
        if depth > 0 or node.name:
            deck = DeckInfo(
                deck_id=node.deck_id,
                name=node.name,
                new_count=node.new_count,
                learn_count=node.learn_count,
                review_count=node.review_count,
            )
            self._decks.append(deck)

        for child in node.children:
            self._flatten_tree(child, depth + 1)

    def _update_list(self, filter_text: str = "") -> None:
        """Update the deck list with optional filtering."""
        list_view = self.query_one("#deck-list", ListView)
        list_view.clear()

        filter_lower = filter_text.lower()
        self._filtered_decks = [
            deck
            for deck in self._decks
            if not filter_text or filter_lower in deck.name.lower()
        ]

        for deck in self._filtered_decks:
            list_view.append(DeckListItem(deck))

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter-input":
            self._update_list(event.value)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle deck selection from list."""
        if isinstance(event.item, DeckListItem):
            await self._select_deck(event.item.deck)

    async def action_cursor_down(self) -> None:
        """Move cursor down in the list."""
        list_view = self.query_one("#deck-list", ListView)
        list_view.action_cursor_down()

    async def action_cursor_up(self) -> None:
        """Move cursor up in the list."""
        list_view = self.query_one("#deck-list", ListView)
        list_view.action_cursor_up()

    async def action_select_deck(self) -> None:
        """Select the currently highlighted deck."""
        list_view = self.query_one("#deck-list", ListView)
        if list_view.highlighted_child is not None:
            if isinstance(list_view.highlighted_child, DeckListItem):
                await self._select_deck(list_view.highlighted_child.deck)

    async def action_focus_filter(self) -> None:
        """Focus the filter input."""
        self.query_one("#filter-input", Input).focus()

    async def _select_deck(self, deck: DeckInfo) -> None:
        """Select a deck and push the review screen."""
        if deck.total_due == 0:
            # No cards due - show notification
            self.notify(f"No cards due in {deck.name}", severity="warning")
            return

        # Reset session stats
        self.clanki_app.state.stats.reset()

        # Push review screen
        from .review import ReviewScreen

        await self.app.push_screen(ReviewScreen(deck.name))

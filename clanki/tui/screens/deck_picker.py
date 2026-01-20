"""Deck picker screen for Clanki TUI.

This screen displays a hierarchical list of decks with their due counts,
allowing users to select a deck to start a review session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import ListItem, ListView, Static

from ... import __version__

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


@dataclass
class DeckNode:
    """A node in the deck hierarchy tree."""

    deck_id: int
    name: str
    new_count: int
    learn_count: int
    review_count: int
    depth: int
    children: list["DeckNode"]

    @property
    def has_children(self) -> bool:
        """Check if this node has children."""
        return len(self.children) > 0

    @property
    def total_due(self) -> int:
        """Total number of cards due."""
        return self.new_count + self.learn_count + self.review_count

    @property
    def leaf_name(self) -> str:
        """Get the leaf part of the deck name."""
        parts = self.name.split("::")
        return parts[-1] if parts else self.name

    def format_counts(self) -> str:
        """Format counts as new/learn/review string."""
        return f"{self.new_count}/{self.learn_count}/{self.review_count}"


class DeckListItem(ListItem):
    """A list item representing a deck."""

    def __init__(self, node: DeckNode, is_expanded: bool = False) -> None:
        super().__init__()
        self.node = node
        self.is_expanded = is_expanded

    def compose(self) -> ComposeResult:
        counts = self.node.format_counts()
        indent = "  " * self.node.depth

        # Toggle indicator for parent decks
        if self.node.has_children:
            indicator = "▼ " if self.is_expanded else "▶ "
        else:
            indicator = "  "

        yield Static(
            f"{indent}{indicator}{self.node.leaf_name}  [dim]({counts})[/dim]",
            markup=True,
        )


class DeckPickerScreen(Screen[str]):
    """Screen for selecting a deck to review."""

    BINDINGS = [
        Binding("escape", "app.quit", "Quit"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "select_deck", "Select"),
        Binding("space", "toggle_expand", "Expand/Collapse", show=False),
    ]

    class DeckSelected(Message):
        """Message sent when a deck is selected."""

        def __init__(self, deck_name: str) -> None:
            super().__init__()
            self.deck_name = deck_name

    def __init__(self) -> None:
        super().__init__()
        self._deck_tree: list[DeckNode] = []
        self._visible_nodes: list[DeckNode] = []

    @property
    def clanki_app(self) -> "ClankiApp":
        """Get the typed app instance."""
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        # Footer - full width, docked to bottom
        yield Static(
            "[dim]j/k[/dim] navigate  [dim]Space[/dim] expand/collapse  "
            "[dim]Enter[/dim] select  [dim]q[/dim] quit",
            classes="help-text footer-bar",
            markup=True,
        )
        # Main content - centered with max-width
        yield Container(
            Vertical(
                Static(f"clanki v{__version__}", classes="header-bar"),
                ListView(id="deck-list"),
                classes="content-column",
            ),
            classes="centered-screen",
        )

    async def on_mount(self) -> None:
        """Load decks and initialize UI when screen mounts."""
        self._load_decks()
        self._update_list()
        self.call_after_refresh(self._update_list_height)

        # Focus the list and highlight first item
        list_view = self.query_one("#deck-list", ListView)
        list_view.focus()

        if self._visible_nodes:
            def init_highlight() -> None:
                list_view.index = 0

            list_view.call_after_refresh(init_highlight)

    def on_screen_resume(self) -> None:
        """Refresh deck data when screen becomes active again after another screen is popped."""
        # Reload decks to get updated counts after review
        self._load_decks()
        self._update_list()
        self.call_after_refresh(self._update_list_height)

        # Re-focus the list
        list_view = self.query_one("#deck-list", ListView)
        list_view.focus()

    def on_resize(self) -> None:
        """Handle terminal resize."""
        self.call_after_refresh(self._update_list_height)

    def _update_list_height(self) -> None:
        """Set list height to min(content, available space)."""
        list_view = self.query_one("#deck-list", ListView)
        column = self.query_one(".content-column", Vertical)
        header = self.query_one(".header-bar", Static)

        # Available space inside the column after header
        available = column.size.height - header.outer_size.height

        # List border adds 2 rows (top + bottom)
        border_height = 2 if list_view.styles.border else 0

        content_height = len(self._visible_nodes)
        target = max(1, min(content_height + border_height, available))
        list_view.styles.height = target

    @property
    def _expanded_decks(self) -> set[int]:
        """Get the expanded deck IDs from app state."""
        return self.clanki_app.state.expanded_decks

    def _load_decks(self) -> None:
        """Load deck information from collection."""
        col = self.clanki_app.state.col
        if col is None:
            return

        tree = col.sched.deck_due_tree()
        self._deck_tree = self._build_tree(tree)

        # Initialize expanded state for top-level decks on first load
        if not self._expanded_decks:
            for node in self._deck_tree:
                if node.has_children:
                    self._expanded_decks.add(node.deck_id)

    def _build_node(self, node: Any, depth: int) -> DeckNode:
        """Build a single DeckNode with its direct children only."""
        children = [self._build_node(child, depth + 1) for child in node.children]
        return DeckNode(
            deck_id=node.deck_id,
            name=node.name,
            new_count=node.new_count,
            learn_count=node.learn_count,
            review_count=node.review_count,
            depth=depth,
            children=children,
        )

    def _build_tree(self, root: Any) -> list[DeckNode]:
        """Build tree structure from Anki's deck_due_tree root."""
        # Root node is special (has no meaningful name), process its children at depth 0
        if not root.name:
            return [self._build_node(child, 0) for child in root.children]
        # If root has a name, it's a real node
        return [self._build_node(root, 0)]

    def _get_visible_nodes(self, nodes: list[DeckNode]) -> list[DeckNode]:
        """Get the list of visible nodes based on expanded state."""
        result: list[DeckNode] = []

        def walk(node_list: list[DeckNode]) -> None:
            for node in node_list:
                result.append(node)
                if node.deck_id in self._expanded_decks:
                    walk(node.children)

        walk(nodes)
        return result

    def _update_list(self, restore_deck_id: int | None = None) -> None:
        """Update the deck list.

        Args:
            restore_deck_id: If provided, restore highlight to this deck after rebuild.
        """
        list_view = self.query_one("#deck-list", ListView)

        # Remember current selection if not explicitly provided
        if restore_deck_id is None and list_view.highlighted_child is not None:
            if isinstance(list_view.highlighted_child, DeckListItem):
                restore_deck_id = list_view.highlighted_child.node.deck_id

        list_view.clear()

        self._visible_nodes = self._get_visible_nodes(self._deck_tree)

        for node in self._visible_nodes:
            is_expanded = node.deck_id in self._expanded_decks
            list_view.append(DeckListItem(node, is_expanded))

        # Restore highlight after rebuild - use list_view.call_after_refresh
        # so it runs after ListView processes its children
        if restore_deck_id is not None and self._visible_nodes:
            new_index = 0
            for i, node in enumerate(self._visible_nodes):
                if node.deck_id == restore_deck_id:
                    new_index = i
                    break

            def restore_highlight() -> None:
                list_view.index = new_index

            list_view.call_after_refresh(restore_highlight)

        # Update height after list content changes (after layout runs)
        self.call_after_refresh(self._update_list_height)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle deck selection from list."""
        if isinstance(event.item, DeckListItem):
            await self._select_deck(event.item.node)

    async def action_cursor_down(self) -> None:
        """Move cursor down in the list, wrapping to top at the end."""
        list_view = self.query_one("#deck-list", ListView)
        if list_view.index is not None and list_view.index >= len(self._visible_nodes) - 1:
            list_view.index = 0
        else:
            list_view.action_cursor_down()

    async def action_cursor_up(self) -> None:
        """Move cursor up in the list, wrapping to bottom at the start."""
        list_view = self.query_one("#deck-list", ListView)
        if list_view.index is not None and list_view.index <= 0:
            list_view.index = len(self._visible_nodes) - 1
        else:
            list_view.action_cursor_up()

    async def action_select_deck(self) -> None:
        """Select the currently highlighted deck."""
        list_view = self.query_one("#deck-list", ListView)
        if list_view.highlighted_child is not None:
            if isinstance(list_view.highlighted_child, DeckListItem):
                await self._select_deck(list_view.highlighted_child.node)

    async def action_toggle_expand(self) -> None:
        """Toggle expand/collapse for the highlighted deck."""
        list_view = self.query_one("#deck-list", ListView)
        if list_view.highlighted_child is None:
            return

        if not isinstance(list_view.highlighted_child, DeckListItem):
            return

        node = list_view.highlighted_child.node
        if not node.has_children:
            return

        # Toggle expanded state
        if node.deck_id in self._expanded_decks:
            self._expanded_decks.discard(node.deck_id)
        else:
            self._expanded_decks.add(node.deck_id)

        # Refresh the list - _update_list handles highlight restoration
        self._update_list()

    async def _select_deck(self, node: DeckNode) -> None:
        """Select a deck and push the review screen."""
        if node.total_due == 0:
            # No cards due - show notification
            self.notify(f"No cards due in {node.name}", severity="warning")
            return

        # Resolve canonical deck name from ID
        # deck_due_tree().name may be decorated for display, but ReviewSession
        # needs the canonical name that matches col.decks.all_names_and_ids()
        col = self.clanki_app.state.col
        if col is None:
            self.notify("Collection not open", severity="error")
            return

        deck_dict = col.decks.get(node.deck_id)
        if deck_dict is None:
            self.notify(f"Deck not found: {node.name}", severity="error")
            return

        canonical_name = deck_dict["name"]

        # Reset session stats
        self.clanki_app.state.stats.reset()

        # Push review screen
        from .review import ReviewScreen

        await self.app.push_screen(ReviewScreen(canonical_name))

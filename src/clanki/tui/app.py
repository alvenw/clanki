"""Textual TUI application for Clanki.

This module provides the main Textual App that manages:
- Collection lifecycle (open on mount, close on exit)
- Screen navigation (deck picker, review, done)
- Session statistics tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App

if TYPE_CHECKING:
    from anki.collection import Collection


@dataclass
class SessionStats:
    """Statistics for the current review session."""

    reviewed: int = 0
    again_count: int = 0
    hard_count: int = 0
    good_count: int = 0
    easy_count: int = 0

    def record_answer(self, rating: int) -> None:
        """Record an answer with the given rating (1-4)."""
        self.reviewed += 1
        if rating == 1:
            self.again_count += 1
        elif rating == 2:
            self.hard_count += 1
        elif rating == 3:
            self.good_count += 1
        elif rating == 4:
            self.easy_count += 1

    def reset(self) -> None:
        """Reset all statistics."""
        self.reviewed = 0
        self.again_count = 0
        self.hard_count = 0
        self.good_count = 0
        self.easy_count = 0


@dataclass
class AppState:
    """Shared application state."""

    col: Collection | None = None
    media_dir: Path | None = None
    stats: SessionStats = field(default_factory=SessionStats)
    initial_deck: str | None = None
    images_enabled: bool = True
    audio_enabled: bool = True
    audio_autoplay: bool = True
    expanded_decks: set[int] = field(default_factory=set)


class ClankiApp(App[None]):
    """Main Textual application for Clanki."""

    TITLE = "Clanki"
    CSS = """
    Screen {
        background: $surface;
    }

    /* Footer bar - full width, docked to bottom */
    .footer-bar {
        dock: bottom;
        width: 100%;
    }

    /* Centered layout - outer container centers the inner column */
    .centered-screen {
        width: 100%;
        height: 1fr;
        align-horizontal: center;
    }

    /* Inner content column with max-width */
    .content-column {
        max-width: 96;
        width: 100%;
        height: 1fr;
        min-height: 0;
    }

    #deck-list {
        border: solid $primary;
    }

    /* Card container - fills available space with scrolling */
    .card-container {
        height: 1fr;
        min-height: 0;
        margin-top: 1;
    }

    .card-content {
        padding: 0 2 1 2;
        height: auto;
    }

    .question-panel {
        border: solid $primary;
        height: auto;
    }

    .answer-panel {
        border: solid $success;
        height: auto;
    }

    .stats-bar {
        height: 3;
        background: $surface-darken-1;
        padding: 0 1;
    }

    .rating-bar {
        height: 3;
        background: $surface-darken-2;
        layout: horizontal;
    }

    .rating-button {
        width: 1fr;
        margin: 0 1;
    }

    .done-container {
        align: center middle;
        height: 1fr;
    }

    .done-stats {
        width: 60;
        height: auto;
        border: solid $success;
        padding: 2;
    }

    .help-text {
        height: 1;
        background: $surface-darken-1;
        text-align: center;
    }

    DeckCountsBar {
        height: auto;
    }

    /* Header bar with version */
    .header-bar {
        height: 1;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        collection_path: Path,
        initial_deck: str | None = None,
        images_enabled: bool = True,
        audio_enabled: bool = True,
        audio_autoplay: bool = True,
    ) -> None:
        """Initialize the Clanki app.

        Args:
            collection_path: Path to the Anki collection file.
            initial_deck: Optional deck name to start reviewing immediately.
            images_enabled: Whether to render images in card views.
            audio_enabled: Whether audio playback is enabled.
            audio_autoplay: Whether to auto-play audio on card display/reveal.
        """
        super().__init__()
        self._collection_path = collection_path

        # Load expanded_decks from persistent config
        from ..config_store import load_config

        config = load_config()

        self._state = AppState(
            initial_deck=initial_deck,
            images_enabled=images_enabled,
            audio_enabled=audio_enabled,
            audio_autoplay=audio_autoplay,
            expanded_decks=config.expanded_decks.copy(),
        )

    @property
    def state(self) -> AppState:
        """Get the shared application state."""
        return self._state

    async def on_mount(self) -> None:
        """Open collection and push initial screen on mount."""
        from ..collection import CollectionLockError, open_collection

        # Open collection
        try:
            self._state.col = open_collection(self._collection_path)
            self._state.media_dir = Path(self._state.col.media.dir())
        except CollectionLockError:
            from .screens.collection_lock import CollectionLockScreen

            await self.push_screen(CollectionLockScreen())
            return

        # Push appropriate screen
        if self._state.initial_deck:
            from .screens.review import ReviewScreen

            await self.push_screen(ReviewScreen(self._state.initial_deck))
        else:
            from .screens.deck_picker import DeckPickerScreen

            await self.push_screen(DeckPickerScreen())

    async def action_quit(self) -> None:
        """Quit the application."""
        self._close_collection()
        self.exit()

    def _close_collection(self) -> None:
        """Close the collection safely."""
        from ..collection import close_collection

        if self._state.col is not None:
            close_collection(self._state.col)
            self._state.col = None

    def on_unmount(self) -> None:
        """Ensure collection is closed and config is saved on unmount."""
        self._close_collection()
        self._save_config()

    def _save_config(self) -> None:
        """Save expanded_decks state to persistent config."""
        from ..config_store import load_config, save_config

        config = load_config()
        config.expanded_decks = self._state.expanded_decks.copy()
        save_config(config)


def run_tui(
    collection_path: Path,
    initial_deck: str | None = None,
    images_enabled: bool = True,
    audio_enabled: bool = True,
    audio_autoplay: bool = True,
) -> None:
    """Run the Clanki TUI.

    Args:
        collection_path: Path to the Anki collection file.
        initial_deck: Optional deck name to start reviewing immediately.
        images_enabled: Whether to render images in card views.
        audio_enabled: Whether audio playback is enabled.
        audio_autoplay: Whether to auto-play audio on card display/reveal.
    """
    app = ClankiApp(
        collection_path=collection_path,
        initial_deck=initial_deck,
        images_enabled=images_enabled,
        audio_enabled=audio_enabled,
        audio_autoplay=audio_autoplay,
    )
    app.run()

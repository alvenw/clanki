"""Review screen for Clanki TUI.

This screen handles the card review flow:
- Show question, reveal answer on space/enter
- If answer visible, space submits Good rating
- Support 1-4 ratings, undo, and back to picker
- Audio playback with auto-play and replay support
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ...audio import (
    is_audio_playback_available,
    play_audio_by_index,
    play_audio_for_side,
    stop_audio,
)
from ...config_store import Config, load_config, save_config
from ...render import render_html_to_text
from ...review import CardView, DeckNotFoundError, Rating, ReviewSession, UndoError
from ..widgets.card_view import CardViewWidget
from ..widgets.stats_bar import DeckCountsBar, StatsBar

if TYPE_CHECKING:
    from ..app import ClankiApp


class ReviewScreen(Screen[None]):
    """Screen for reviewing cards in a deck."""

    BINDINGS = [
        Binding("escape", "back_to_picker", "Back"),
        Binding("q", "app.quit", "Quit"),
        Binding("space", "space_action", "Reveal/Good", show=True),
        Binding("enter", "reveal", "Reveal", show=False),
        Binding("1", "rate_again", "Again", show=False),
        Binding("2", "rate_hard", "Hard", show=False),
        Binding("3", "rate_good", "Good", show=False),
        Binding("4", "rate_easy", "Easy", show=False),
        Binding("5", "play_audio_1", "Audio1", show=False),
        Binding("6", "play_audio_2", "Audio2", show=False),
        Binding("7", "play_audio_3", "Audio3", show=False),
        Binding("8", "play_audio_4", "Audio4", show=False),
        Binding("9", "play_audio_5", "Audio5", show=False),
        Binding("u", "undo", "Undo", show=False),
        Binding("i", "toggle_images", "Images", show=False),
        Binding("a", "replay_audio", "Audio", show=False),
        Binding("s", "toggle_audio", "Sound", show=False),
    ]

    def __init__(self, deck_name: str) -> None:
        super().__init__()
        self._deck_name = deck_name
        self._session: ReviewSession | None = None
        self._current_card: CardView | None = None
        self._answer_revealed = False
        self._processing_action = False  # Guard against rapid key presses

    @property
    def clanki_app(self) -> ClankiApp:
        """Get the typed app instance."""
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        # Get initial settings from app state
        media_dir = self.clanki_app.state.media_dir
        images_enabled = self.clanki_app.state.images_enabled

        # Footer - full width, docked to bottom
        yield Static(
            self._get_help_text(),
            id="help-bar",
            classes="help-text footer-bar",
            markup=True,
        )
        # Main content - centered with max-width
        yield Container(
            Vertical(
                Static(
                    f"[bold]{self._deck_name}[/bold]",
                    id="deck-title",
                    markup=True,
                ),
                StatsBar(id="stats-bar"),
                VerticalScroll(
                    CardViewWidget(
                        id="card-view",
                        media_dir=media_dir,
                        images_enabled=images_enabled,
                    ),
                    id="card-scroll",
                    classes="card-container",
                ),
                DeckCountsBar(id="deck-counts-bar"),
                classes="content-column",
            ),
            classes="centered-screen",
        )

    def _current_side_has_audio(self) -> bool:
        """Check if the current side (question or answer) has audio files."""
        if self._current_card is None:
            return False
        if self._answer_revealed:
            return bool(self._current_card.answer_audio)
        return bool(self._current_card.question_audio)

    def _get_help_text(self) -> str:
        """Get context-appropriate help text with action prompts."""
        state = self.clanki_app.state
        img_status = "on" if state.images_enabled else "off"
        snd_status = "on" if state.audio_enabled else "off"

        # Only show replay hint if current side has audio and audio is enabled
        replay_hint = ""
        if state.audio_enabled and self._current_side_has_audio():
            replay_hint = "[dim]a[/dim] replay  "

        # Check if undo is available
        undo_hint = ""
        if self._session is not None and self._session.can_undo:
            undo_hint = "[dim]u[/dim] undo  "

        if not self._answer_revealed:
            # Question side: Show Answer prompt
            return (
                "[bold reverse] Show Answer [/bold reverse] [dim](Space/Enter)[/dim]  "
                f"{undo_hint}{replay_hint}"
                f"[dim]s[/dim] snd:{snd_status}  [dim]i[/dim] img:{img_status}  "
                "[dim]Esc[/dim] back"
            )
        # Answer side: Rating bar with timestamps
        labels = (
            self._current_card.rating_labels
            if self._current_card is not None and len(self._current_card.rating_labels) == 4
            else None
        )
        if labels:
            again, hard, good, easy = labels
            return (
                f"[bold red]1[/bold red] Again [dim]{again}[/dim]  "
                f"[bold yellow]2[/bold yellow] Hard [dim]{hard}[/dim]  "
                f"[bold green]3[/bold green] Good [dim]{good}[/dim]  "
                f"[bold blue]4[/bold blue] Easy [dim]{easy}[/dim]  "
                f"{undo_hint}{replay_hint}"
            )
        return (
            "[bold red]1[/bold red] Again  "
            "[bold yellow]2[/bold yellow] Hard  "
            "[bold green]3[/bold green] Good  "
            "[bold blue]4[/bold blue] Easy  "
            f"{undo_hint}{replay_hint}"
        )

    async def on_mount(self) -> None:
        """Initialize review session and load first card."""
        col = self.clanki_app.state.col
        if col is None:
            self.notify("Collection not open", severity="error")
            self.app.pop_screen()
            return

        try:
            self._session = ReviewSession(col, self._deck_name)
        except DeckNotFoundError as exc:
            self.notify(str(exc), severity="error")
            self.app.pop_screen()
            return

        self._update_stats()
        await self._load_next_card()

    def on_unmount(self) -> None:
        """Stop audio when leaving the screen."""
        stop_audio()

    def _update_stats(self) -> None:
        """Update all stats displays with current counts."""
        if self._session is None:
            return

        counts = self._session.get_counts()

        # Update top stats bar (session summary: due/reviewed)
        stats_bar = self.query_one("#stats-bar", StatsBar)
        stats_bar.update_counts(
            new=counts.new_count,
            learn=counts.learn_count,
            review=counts.review_count,
        )
        session_stats = self.clanki_app.state.stats
        stats_bar.update_session(reviewed=session_stats.reviewed)

        # Update bottom deck counts bar (new/learn/review)
        deck_counts_bar = self.query_one("#deck-counts-bar", DeckCountsBar)
        deck_counts_bar.update_counts(
            new=counts.new_count,
            learn=counts.learn_count,
            review=counts.review_count,
        )

    async def _load_next_card(self) -> None:
        """Load the next card or show done screen."""
        if self._session is None:
            return

        self._current_card = self._session.next_card()
        self._answer_revealed = False

        if self._current_card is None:
            # No more cards - show done screen
            from .done import DoneScreen

            await self.app.switch_screen(DoneScreen(self._deck_name))
            return

        self._display_card()

    def _display_card(self, play_audio: bool = True) -> None:
        """Display the current card content.

        Args:
            play_audio: Whether to auto-play audio for this display update.
        """
        if self._current_card is None:
            return

        card_view = self.query_one("#card-view", CardViewWidget)

        # Pass raw HTML to the card view - it handles styled rendering internally
        if self._answer_revealed:
            card_view.show_answer(
                self._current_card.question_html,
                self._current_card.answer_html,
            )
        else:
            card_view.show_question(self._current_card.question_html)

        # Reset scroll to top AFTER content update so scrollbar visual syncs correctly
        scroll_container = self.query_one("#card-scroll", VerticalScroll)
        scroll_container.scroll_home(animate=False)

        # Update help text (includes Show Answer prompt or Rating bar)
        help_bar = self.query_one("#help-bar", Static)
        help_bar.update(self._get_help_text())

        # Auto-play audio if enabled
        if play_audio:
            self._maybe_play_audio()

    def _maybe_play_audio(self) -> None:
        """Play audio for the current side if audio is enabled and autoplay is on."""
        state = self.clanki_app.state
        if not state.audio_enabled or not state.audio_autoplay:
            return
        self._play_current_side_audio()

    def _play_current_side_audio(self) -> None:
        """Play audio for the current card side (question or answer)."""
        if self._current_card is None:
            return

        state = self.clanki_app.state
        if not state.audio_enabled:
            return

        media_dir = state.media_dir

        # Determine which side to play
        if self._answer_revealed:
            # Play answer audio
            text = render_html_to_text(
                self._current_card.answer_html,
                media_dir=media_dir,
            )
            audio_files = self._current_card.answer_audio
        else:
            # Play question audio
            text = render_html_to_text(
                self._current_card.question_html,
                media_dir=media_dir,
            )
            audio_files = self._current_card.question_audio

        # Play audio
        play_audio_for_side(
            text=text,
            audio_files=audio_files,
            media_dir=media_dir,
            on_error=lambda msg: self.notify(msg, severity="warning"),
        )

    async def action_space_action(self) -> None:
        """Handle space key - reveal answer or rate Good."""
        # Guard against rapid key presses causing double actions
        if self._processing_action:
            return
        self._processing_action = True
        try:
            if not self._answer_revealed:
                self._reveal_answer()
            else:
                await self._rate(Rating.GOOD)
        finally:
            self._processing_action = False

    async def action_reveal(self) -> None:
        """Reveal the answer."""
        if not self._answer_revealed:
            self._reveal_answer()

    def _reveal_answer(self) -> None:
        """Reveal the answer for the current card."""
        import contextlib

        if self._current_card is None:
            return

        self._answer_revealed = True
        try:
            self._display_card()
        except Exception as exc:
            # If display fails, disable images and retry
            self.clanki_app.state.images_enabled = False
            card_view = self.query_one("#card-view", CardViewWidget)
            card_view.set_images_enabled(False)
            self.notify(f"Image rendering error: {exc}", severity="warning")
            with contextlib.suppress(Exception):
                self._display_card()

    async def action_rate_again(self) -> None:
        """Rate the card as Again (1)."""
        if self._answer_revealed:
            await self._rate(Rating.AGAIN)

    async def action_rate_hard(self) -> None:
        """Rate the card as Hard (2)."""
        if self._answer_revealed:
            await self._rate(Rating.HARD)

    async def action_rate_good(self) -> None:
        """Rate the card as Good (3)."""
        if self._answer_revealed:
            await self._rate(Rating.GOOD)

    async def action_rate_easy(self) -> None:
        """Rate the card as Easy (4)."""
        if self._answer_revealed:
            await self._rate(Rating.EASY)

    def _play_indexed_audio(self, index: int) -> None:
        """Play a specific audio file by index.

        Args:
            index: 1-based audio index (matches 🔊1, 🔊2, etc. in display).
        """
        if self._current_card is None:
            return

        state = self.clanki_app.state
        if not state.audio_enabled:
            self.notify("Audio is disabled (press 's' to enable)", severity="warning")
            return

        if not is_audio_playback_available():
            self.notify(
                "Audio playback is only supported on macOS",
                severity="warning",
            )
            return

        media_dir = state.media_dir

        # Determine which side's audio to play
        if self._answer_revealed:
            text = render_html_to_text(
                self._current_card.answer_html,
                media_dir=media_dir,
            )
            audio_files = self._current_card.answer_audio
        else:
            text = render_html_to_text(
                self._current_card.question_html,
                media_dir=media_dir,
            )
            audio_files = self._current_card.question_audio

        play_audio_by_index(
            text=text,
            audio_files=audio_files,
            media_dir=media_dir,
            index=index,
            on_error=lambda msg: self.notify(msg, severity="warning"),
        )

    async def action_play_audio_1(self) -> None:
        """Play audio file 1 (key 5)."""
        self._play_indexed_audio(1)

    async def action_play_audio_2(self) -> None:
        """Play audio file 2 (key 6)."""
        self._play_indexed_audio(2)

    async def action_play_audio_3(self) -> None:
        """Play audio file 3 (key 7)."""
        self._play_indexed_audio(3)

    async def action_play_audio_4(self) -> None:
        """Play audio file 4 (key 8)."""
        self._play_indexed_audio(4)

    async def action_play_audio_5(self) -> None:
        """Play audio file 5 (key 9)."""
        self._play_indexed_audio(5)

    async def _rate(self, rating: Rating) -> None:
        """Submit a rating for the current card."""
        if self._session is None or self._current_card is None:
            return

        try:
            self._session.answer(rating)
            self.clanki_app.state.stats.record_answer(int(rating))
            self._update_stats()
            await self._load_next_card()
        except Exception as exc:
            self.notify(f"Error rating card: {exc}", severity="error")

    async def action_undo(self) -> None:
        """Undo the last answer."""
        if self._session is None:
            return

        try:
            self._current_card = self._session.undo()
            self._answer_revealed = False  # Show front side after undo

            # Update stats (decrement reviewed count)
            stats = self.clanki_app.state.stats
            if stats.reviewed > 0:
                stats.reviewed -= 1

            self._update_stats()
            self._display_card(play_audio=False)  # Don't auto-play after undo
            self.notify("Undone", severity="information")
        except UndoError as exc:
            self.notify(str(exc), severity="warning")

    async def action_back_to_picker(self) -> None:
        """Return to the deck picker."""
        stop_audio()
        self.app.pop_screen()

    async def action_toggle_images(self) -> None:
        """Toggle image rendering on/off and persist to config."""
        state = self.clanki_app.state

        # Toggle the state
        state.images_enabled = not state.images_enabled

        # Update the card view widget
        card_view = self.query_one("#card-view", CardViewWidget)
        card_view.set_images_enabled(state.images_enabled)

        # Re-display current card (don't re-play audio)
        self._display_card(play_audio=False)

        # Update help text to show new image status
        help_bar = self.query_one("#help-bar", Static)
        help_bar.update(self._get_help_text())

        # Persist to config
        config = Config(
            images_enabled=state.images_enabled,
            audio_enabled=state.audio_enabled,
            audio_autoplay=state.audio_autoplay,
        )
        save_config(config)

        # Show notification
        status = "enabled" if state.images_enabled else "disabled"
        self.notify(f"Images {status}", severity="information")

    async def action_replay_audio(self) -> None:
        """Replay audio for the current card side."""
        state = self.clanki_app.state
        if not state.audio_enabled:
            self.notify("Audio is disabled (press 's' to enable)", severity="warning")
            return

        if not is_audio_playback_available():
            self.notify(
                "Audio playback is only supported on macOS",
                severity="warning",
            )
            return

        self._play_current_side_audio()

    async def action_toggle_audio(self) -> None:
        """Toggle audio playback on/off and persist to config."""
        import clanki.audio as audio_module

        state = self.clanki_app.state

        # Reset the cache to ensure fresh detection
        audio_module.reset_audio_cache()

        # If trying to enable audio, check if it's available
        if not state.audio_enabled and not is_audio_playback_available():
            self.notify(
                "Audio playback is only supported on macOS",
                title="Audio not available",
                severity="warning",
                timeout=5,
            )
            return

        # Toggle the state
        state.audio_enabled = not state.audio_enabled

        # Stop any playing audio when disabling
        if not state.audio_enabled:
            stop_audio()

        # Update help text to show new audio status
        help_bar = self.query_one("#help-bar", Static)
        help_bar.update(self._get_help_text())

        # Persist to config
        config = Config(
            images_enabled=state.images_enabled,
            audio_enabled=state.audio_enabled,
            audio_autoplay=state.audio_autoplay,
        )
        save_config(config)

        # Show notification
        status = "enabled" if state.audio_enabled else "disabled"
        self.notify(f"Audio {status}", severity="information")

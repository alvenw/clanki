"""Review screen for Clanki TUI.

This screen handles the card review flow:
- Show question, reveal answer on space/enter
- If answer visible, space submits Good rating
- Support 1-4 ratings, undo, and back to picker
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ...render import render_html_to_text
from ...review import CardView, DeckNotFoundError, Rating, ReviewSession, UndoError
from ..widgets.card_view import CardViewWidget
from ..widgets.stats_bar import StatsBar

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
        Binding("u", "undo", "Undo", show=False),
    ]

    def __init__(self, deck_name: str) -> None:
        super().__init__()
        self._deck_name = deck_name
        self._session: ReviewSession | None = None
        self._current_card: CardView | None = None
        self._answer_revealed = False

    @property
    def clanki_app(self) -> "ClankiApp":
        """Get the typed app instance."""
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(f"[bold]{self._deck_name}[/bold]", id="deck-title", markup=True),
            StatsBar(id="stats-bar"),
            VerticalScroll(
                CardViewWidget(id="card-view"),
            ),
            Static(
                self._get_help_text(),
                id="help-bar",
                classes="help-text",
                markup=True,
            ),
        )

    def _get_help_text(self) -> str:
        """Get context-appropriate help text."""
        if not self._answer_revealed:
            return "[dim]Space[/dim] reveal  [dim]Esc[/dim] back  [dim]q[/dim] quit"
        return (
            "[dim]1[/dim] Again  [dim]2[/dim] Hard  "
            "[dim]3/Space[/dim] Good  [dim]4[/dim] Easy  "
            "[dim]u[/dim] undo  [dim]Esc[/dim] back"
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

    def _update_stats(self) -> None:
        """Update the stats bar with current deck counts."""
        if self._session is None:
            return

        counts = self._session.get_counts()
        stats_bar = self.query_one("#stats-bar", StatsBar)
        stats_bar.update_counts(
            new=counts.new_count,
            learn=counts.learn_count,
            review=counts.review_count,
        )

        session_stats = self.clanki_app.state.stats
        stats_bar.update_session(reviewed=session_stats.reviewed)

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

    def _display_card(self) -> None:
        """Display the current card content."""
        if self._current_card is None:
            return

        media_dir = self.clanki_app.state.media_dir
        card_view = self.query_one("#card-view", CardViewWidget)

        question = render_html_to_text(
            self._current_card.question_html,
            media_dir=media_dir,
        )

        if self._answer_revealed:
            answer = render_html_to_text(
                self._current_card.answer_html,
                media_dir=media_dir,
            )
            card_view.show_answer(question, answer)
        else:
            card_view.show_question(question)

        # Update help text
        help_bar = self.query_one("#help-bar", Static)
        help_bar.update(self._get_help_text())

    async def action_space_action(self) -> None:
        """Handle space key - reveal answer or rate Good."""
        if not self._answer_revealed:
            self._reveal_answer()
        else:
            await self._rate(Rating.GOOD)

    async def action_reveal(self) -> None:
        """Reveal the answer."""
        if not self._answer_revealed:
            self._reveal_answer()

    def _reveal_answer(self) -> None:
        """Reveal the answer for the current card."""
        if self._current_card is None:
            return

        self._answer_revealed = True
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
            self._answer_revealed = True  # Show answer after undo

            # Update stats (decrement reviewed count)
            stats = self.clanki_app.state.stats
            if stats.reviewed > 0:
                stats.reviewed -= 1

            self._update_stats()
            self._display_card()
            self.notify("Undone", severity="information")
        except UndoError as exc:
            self.notify(str(exc), severity="warning")

    async def action_back_to_picker(self) -> None:
        """Return to the deck picker."""
        self.app.pop_screen()

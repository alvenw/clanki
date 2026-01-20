"""Review session wrapper around Anki scheduler.

This module provides a clean interface for deck selection, card retrieval,
answering, and undo operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anki.cards import Card
    from anki.collection import Collection


class Rating(IntEnum):
    """Card answer ratings matching Anki's scheduler."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class UndoError(Exception):
    """Raised when undo operation fails or nothing to undo."""

    pass


class DeckNotFoundError(Exception):
    """Raised when the specified deck cannot be found."""

    pass


@dataclass
class DeckCounts:
    """Due counts for a deck."""

    new_count: int
    learn_count: int
    review_count: int

    @property
    def total(self) -> int:
        """Total number of cards due."""
        return self.new_count + self.learn_count + self.review_count


def _extract_audio_filenames(av_tags: list[Any]) -> list[str]:
    """Extract audio filenames from Anki AV tags.

    Args:
        av_tags: List of AV tags from render_output (SoundOrVideoTag or TTSTag).

    Returns:
        List of audio filenames (sound files only, not TTS).
    """
    filenames = []
    for tag in av_tags:
        # Tags can be SoundOrVideoTag (has filename attr) or TTSTag
        # We only handle sound/video files, not TTS
        if hasattr(tag, "filename") and tag.filename:
            filenames.append(tag.filename)
    return filenames


@dataclass
class CardView:
    """View of a card for review.

    Contains both the rendered HTML and internal state needed for answering.
    """

    card_id: int
    question_html: str
    answer_html: str
    card: "Card"
    states: Any  # SchedulingStates protobuf
    question_audio: list[str] = field(default_factory=list)  # Audio filenames for question
    answer_audio: list[str] = field(default_factory=list)  # Audio filenames for answer
    rating_labels: list[str] = field(default_factory=list)  # GUI-style interval labels (again, hard, good, easy)


class ReviewSession:
    """Review session wrapper around Anki scheduler.

    Provides deck selection, card retrieval, answer flow, and undo support.
    """

    def __init__(self, col: "Collection", deck_name: str) -> None:
        """Initialize a review session for a specific deck.

        Args:
            col: Open Anki collection.
            deck_name: Name of the deck to review.

        Raises:
            DeckNotFoundError: If the deck cannot be found.
        """
        self._col = col
        self._deck_name = deck_name
        self._deck_id: int | None = None
        self._current_card: CardView | None = None
        self._answered_card_ids: list[int] = []

        # Resolve and select deck
        self._resolve_deck(deck_name)

    def _resolve_deck(self, deck_name: str) -> None:
        """Resolve deck by name and select it.

        Args:
            deck_name: Name of the deck to find.

        Raises:
            DeckNotFoundError: If deck not found.
        """
        for deck in self._col.decks.all_names_and_ids():
            if deck.name == deck_name:
                self._deck_id = deck.id
                self._col.decks.select(deck.id)
                return

        # Build helpful error message
        available = [d.name for d in self._col.decks.all_names_and_ids()]
        raise DeckNotFoundError(
            f"Deck '{deck_name}' not found.\n"
            f"Available decks: {', '.join(available) if available else 'none'}"
        )

    @property
    def deck_id(self) -> int:
        """Get the current deck ID."""
        if self._deck_id is None:
            raise RuntimeError("Deck not selected")
        return self._deck_id

    @property
    def deck_name(self) -> str:
        """Get the current deck name."""
        return self._deck_name

    @property
    def can_undo(self) -> bool:
        """Check if undo is available.

        Returns:
            True if there is a previous answer to undo.
        """
        return len(self._answered_card_ids) > 0

    def get_counts(self) -> DeckCounts:
        """Get due counts for the current deck.

        Returns:
            DeckCounts with new, learn, and review counts.
        """
        tree = self._col.sched.deck_due_tree()
        return self._find_deck_counts(tree, self.deck_id)

    def _find_deck_counts(self, node: Any, target_id: int) -> DeckCounts:
        """Recursively search deck tree for counts.

        Args:
            node: Current tree node.
            target_id: Deck ID to find.

        Returns:
            DeckCounts for the target deck, or zeros if not found.
        """
        if node.deck_id == target_id:
            return DeckCounts(
                new_count=node.new_count,
                learn_count=node.learn_count,
                review_count=node.review_count,
            )

        for child in node.children:
            result = self._find_deck_counts(child, target_id)
            if result.total > 0 or child.deck_id == target_id:
                return result

        return DeckCounts(new_count=0, learn_count=0, review_count=0)

    def next_card(self) -> CardView | None:
        """Get the next card for review.

        Returns:
            CardView with card data and states, or None if no cards due.
        """
        # Ensure deck is selected
        self._col.decks.select(self.deck_id)

        # Get queued cards
        queued = self._col.sched.get_queued_cards(fetch_limit=1)

        if not queued.cards:
            self._current_card = None
            return None

        queued_card = queued.cards[0]

        # Get full card object
        card = self._col.get_card(queued_card.card.id)

        # Render the card
        render_output = card.render_output()

        # Get GUI-style interval labels (again, hard, good, easy)
        rating_labels = list(self._col.sched.describe_next_states(queued_card.states))

        # Create CardView
        card_view = CardView(
            card_id=card.id,
            question_html=render_output.question_text,
            answer_html=render_output.answer_text,
            card=card,
            states=queued_card.states,
            question_audio=_extract_audio_filenames(render_output.question_av_tags),
            answer_audio=_extract_audio_filenames(render_output.answer_av_tags),
            rating_labels=rating_labels,
        )

        self._current_card = card_view
        return card_view

    def answer(self, rating: Rating) -> None:
        """Answer the current card with the given rating.

        Args:
            rating: Rating for the answer (AGAIN, HARD, GOOD, EASY).

        Raises:
            RuntimeError: If no card is currently being reviewed.
        """
        from anki.scheduler.v3 import CardAnswer

        if self._current_card is None:
            raise RuntimeError(
                "No card to answer. Call next_card() first."
            )

        card = self._current_card.card
        states = self._current_card.states

        # Map our Rating enum to Anki's protobuf enum
        rating_map = {
            Rating.AGAIN: CardAnswer.Rating.AGAIN,
            Rating.HARD: CardAnswer.Rating.HARD,
            Rating.GOOD: CardAnswer.Rating.GOOD,
            Rating.EASY: CardAnswer.Rating.EASY,
        }

        # CRITICAL: Start timer before answering
        # This sets card.timer_started which is required for build_answer
        card.start_timer()

        # Build and submit answer
        answer = self._col.sched.build_answer(
            card=card,
            states=states,
            rating=rating_map[rating],
        )
        self._col.sched.answer_card(answer)

        # Track for undo
        self._answered_card_ids.append(self._current_card.card_id)
        self._current_card = None

    def undo(self) -> CardView:
        """Undo the last answer and return the card.

        Returns:
            CardView for the previously answered card.

        Raises:
            UndoError: If there's nothing to undo or undo fails.
        """
        if not self._answered_card_ids:
            raise UndoError("Nothing to undo.")

        try:
            # Perform undo
            self._col.undo()
        except Exception as exc:
            raise UndoError(f"Undo failed: {exc}") from exc

        # Re-fetch the card
        card_id = self._answered_card_ids.pop()

        try:
            card = self._col.get_card(card_id)
        except Exception as exc:
            raise UndoError(f"Failed to retrieve card after undo: {exc}") from exc

        # Re-select deck (undo may have changed selection)
        self._col.decks.select(self.deck_id)

        # Get fresh queued state for the card
        # We need to get the states from the queue again
        queued = self._col.sched.get_queued_cards(fetch_limit=1)

        if not queued.cards:
            raise UndoError("Card not in queue after undo.")

        queued_card = queued.cards[0]

        # Verify it's the same card
        if queued_card.card.id != card_id:
            # The queued card is different - this shouldn't happen after undo
            # but handle it gracefully
            card = self._col.get_card(queued_card.card.id)

        # Render the card
        render_output = card.render_output()

        # Get GUI-style interval labels (again, hard, good, easy)
        rating_labels = list(self._col.sched.describe_next_states(queued_card.states))

        card_view = CardView(
            card_id=card.id,
            question_html=render_output.question_text,
            answer_html=render_output.answer_text,
            card=card,
            states=queued_card.states,
            question_audio=_extract_audio_filenames(render_output.question_av_tags),
            answer_audio=_extract_audio_filenames(render_output.answer_av_tags),
            rating_labels=rating_labels,
        )

        self._current_card = card_view
        return card_view

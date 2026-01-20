"""Fixture-backed integration tests for ReviewSession flow.

These tests use lightweight fake Collection/Scheduler/Card/Deck classes
to exercise the full review flow without requiring a real Anki database.

Covers:
- Deck resolution → next_card() → answer() → undo()
- Error branches (nothing to undo, queued card mismatch)
"""

import sys
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest


# Lightweight fake classes that mimic Anki's API


@dataclass
class FakeDeckInfo:
    """Fake Anki DeckNameId."""

    name: str
    id: int


@dataclass
class FakeTreeNode:
    """Fake deck_due_tree node."""

    deck_id: int
    name: str
    new_count: int
    learn_count: int
    review_count: int
    children: list = field(default_factory=list)


@dataclass
class FakeCard:
    """Fake Anki Card with essential methods."""

    id: int
    question_html: str = "<div>Question</div>"
    answer_html: str = "<div>Answer</div>"
    question_audio: list = field(default_factory=list)
    answer_audio: list = field(default_factory=list)
    timer_started: bool = False

    def start_timer(self) -> None:
        """Mark timer as started."""
        self.timer_started = True

    def render_output(self) -> "FakeRenderOutput":
        """Return fake render output."""
        return FakeRenderOutput(
            question_text=self.question_html,
            answer_text=self.answer_html,
            question_av_tags=self.question_audio,
            answer_av_tags=self.answer_audio,
        )


@dataclass
class FakeRenderOutput:
    """Fake card render output."""

    question_text: str
    answer_text: str
    question_av_tags: list = field(default_factory=list)
    answer_av_tags: list = field(default_factory=list)


@dataclass
class FakeQueuedCard:
    """Fake QueuedCard protobuf."""

    card: Any  # Has .id attribute
    states: Any  # Scheduling states


@dataclass
class FakeQueuedCards:
    """Fake QueuedCards protobuf response."""

    cards: list


class FakeScheduler:
    """Fake Anki scheduler with in-memory state."""

    def __init__(self, deck_tree: FakeTreeNode, cards: list[FakeCard]):
        self._deck_tree = deck_tree
        self._cards = list(cards)  # Queue of cards
        self._answered_cards: list[tuple[FakeCard, Any]] = []  # (card, states) for undo

    def deck_due_tree(self) -> FakeTreeNode:
        """Return the deck tree."""
        return self._deck_tree

    def get_queued_cards(self, fetch_limit: int = 1) -> FakeQueuedCards:
        """Return next queued cards."""
        if not self._cards:
            return FakeQueuedCards(cards=[])

        # Return the first card without removing it
        card = self._cards[0]
        queued = FakeQueuedCard(
            card=Mock(id=card.id),
            states=Mock(),  # Fake scheduling states
        )
        return FakeQueuedCards(cards=[queued])

    def describe_next_states(self, states: Any) -> list[str]:
        """Return fake interval labels for buttons."""
        return ["<1m", "10m", "1d", "4d"]

    def build_answer(self, card: FakeCard, states: Any, rating: Any) -> dict:
        """Build an answer object."""
        return {"card_id": card.id, "rating": rating, "states": states}

    def answer_card(self, answer: dict) -> None:
        """Process the answer - removes card from queue."""
        if self._cards:
            answered = self._cards.pop(0)
            self._answered_cards.append((answered, answer["states"]))


class FakeDecks:
    """Fake Anki decks manager."""

    def __init__(self, decks: list[FakeDeckInfo]):
        self._decks = decks
        self._selected_id: int | None = None

    def all_names_and_ids(self) -> list[FakeDeckInfo]:
        """Return all deck names and IDs."""
        return self._decks

    def select(self, deck_id: int) -> None:
        """Select a deck."""
        self._selected_id = deck_id


class FakeCollection:
    """Fake Anki Collection with scheduler and decks."""

    def __init__(
        self,
        decks: list[FakeDeckInfo],
        deck_tree: FakeTreeNode,
        cards: list[FakeCard],
    ):
        self.decks = FakeDecks(decks)
        self.sched = FakeScheduler(deck_tree, cards)
        self._cards_by_id = {c.id: c for c in cards}
        self._undo_stack: list[FakeCard] = []

    def get_card(self, card_id: int) -> FakeCard:
        """Get a card by ID."""
        if card_id not in self._cards_by_id:
            raise ValueError(f"Card {card_id} not found")
        return self._cards_by_id[card_id]

    def undo(self) -> None:
        """Undo the last operation - restores answered card to queue."""
        if self.sched._answered_cards:
            card, states = self.sched._answered_cards.pop()
            self.sched._cards.insert(0, card)
        else:
            raise RuntimeError("Nothing to undo")


# Test fixtures


@pytest.fixture
def mock_anki_scheduler():
    """Mock anki.scheduler.v3 module."""
    mock_module = MagicMock()
    mock_module.CardAnswer.Rating.AGAIN = 1
    mock_module.CardAnswer.Rating.HARD = 2
    mock_module.CardAnswer.Rating.GOOD = 3
    mock_module.CardAnswer.Rating.EASY = 4

    original = sys.modules.get("anki.scheduler.v3")
    sys.modules["anki.scheduler.v3"] = mock_module
    yield mock_module

    if original is not None:
        sys.modules["anki.scheduler.v3"] = original
    else:
        sys.modules.pop("anki.scheduler.v3", None)


@pytest.fixture
def basic_collection():
    """Create a basic fake collection with one deck and cards."""
    deck_id = 1001
    decks = [FakeDeckInfo(name="Test Deck", id=deck_id)]
    deck_tree = FakeTreeNode(
        deck_id=deck_id,
        name="Test Deck",
        new_count=2,
        learn_count=1,
        review_count=3,
    )
    cards = [
        FakeCard(id=101, question_html="<b>Q1</b>", answer_html="<i>A1</i>"),
        FakeCard(id=102, question_html="<b>Q2</b>", answer_html="<i>A2</i>"),
        FakeCard(id=103, question_html="<b>Q3</b>", answer_html="<i>A3</i>"),
    ]
    return FakeCollection(decks=decks, deck_tree=deck_tree, cards=cards)


@pytest.fixture
def empty_collection():
    """Create a collection with no cards due."""
    deck_id = 2001
    decks = [FakeDeckInfo(name="Empty Deck", id=deck_id)]
    deck_tree = FakeTreeNode(
        deck_id=deck_id,
        name="Empty Deck",
        new_count=0,
        learn_count=0,
        review_count=0,
    )
    return FakeCollection(decks=decks, deck_tree=deck_tree, cards=[])


@pytest.fixture
def nested_deck_collection():
    """Create a collection with nested decks."""
    parent_id = 3001
    child_id = 3002

    decks = [
        FakeDeckInfo(name="Parent", id=parent_id),
        FakeDeckInfo(name="Parent::Child", id=child_id),
    ]

    child_tree = FakeTreeNode(
        deck_id=child_id,
        name="Child",
        new_count=5,
        learn_count=2,
        review_count=8,
    )
    parent_tree = FakeTreeNode(
        deck_id=parent_id,
        name="Parent",
        new_count=0,
        learn_count=0,
        review_count=0,
        children=[child_tree],
    )

    cards = [
        FakeCard(id=301, question_html="Child Q1", answer_html="Child A1"),
    ]

    return FakeCollection(decks=decks, deck_tree=parent_tree, cards=cards)


# Integration test classes


class TestDeckResolution:
    """Tests for deck name resolution in ReviewSession."""

    def test_resolves_deck_by_exact_name(self, basic_collection):
        """ReviewSession should resolve deck by exact name match."""
        from clanki.review.session import ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")

        assert session.deck_id == 1001
        assert session.deck_name == "Test Deck"
        assert basic_collection.decks._selected_id == 1001

    def test_raises_deck_not_found_for_unknown_deck(self, basic_collection):
        """ReviewSession should raise DeckNotFoundError for unknown deck."""
        from clanki.review.session import DeckNotFoundError, ReviewSession

        with pytest.raises(DeckNotFoundError) as exc_info:
            ReviewSession(basic_collection, "Unknown Deck")

        error_msg = str(exc_info.value)
        assert "Unknown Deck" in error_msg
        assert "not found" in error_msg.lower()
        assert "Test Deck" in error_msg  # Available decks should be listed

    def test_resolves_nested_deck(self, nested_deck_collection):
        """ReviewSession should resolve nested deck names."""
        from clanki.review.session import ReviewSession

        session = ReviewSession(nested_deck_collection, "Parent::Child")

        assert session.deck_id == 3002
        assert session.deck_name == "Parent::Child"


class TestNextCardFlow:
    """Tests for next_card() retrieval."""

    def test_next_card_returns_card_view(self, basic_collection):
        """next_card() should return CardView with card data."""
        from clanki.review.session import CardView, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        card_view = session.next_card()

        assert card_view is not None
        assert isinstance(card_view, CardView)
        assert card_view.card_id == 101
        assert "<b>Q1</b>" in card_view.question_html
        assert "<i>A1</i>" in card_view.answer_html

    def test_next_card_returns_none_when_empty(self, empty_collection):
        """next_card() should return None when no cards due."""
        from clanki.review.session import ReviewSession

        session = ReviewSession(empty_collection, "Empty Deck")
        card_view = session.next_card()

        assert card_view is None

    def test_next_card_tracks_current_card(self, basic_collection):
        """next_card() should track current card internally."""
        from clanki.review.session import ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")

        assert session._current_card is None
        card_view = session.next_card()
        assert session._current_card is card_view


class TestAnswerFlow:
    """Tests for answer() submission."""

    def test_answer_starts_card_timer(self, basic_collection, mock_anki_scheduler):
        """answer() should call card.start_timer() before submitting."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        card_view = session.next_card()

        # Get the underlying fake card
        fake_card = basic_collection.get_card(card_view.card_id)
        assert not fake_card.timer_started

        session.answer(Rating.GOOD)

        assert fake_card.timer_started

    def test_answer_clears_current_card(self, basic_collection, mock_anki_scheduler):
        """answer() should clear current card after submission."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        session.next_card()

        assert session._current_card is not None

        session.answer(Rating.HARD)

        assert session._current_card is None

    def test_answer_without_card_raises_error(self, basic_collection, mock_anki_scheduler):
        """answer() should raise RuntimeError if no card is current."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        # Don't call next_card()

        with pytest.raises(RuntimeError) as exc_info:
            session.answer(Rating.GOOD)

        assert "No card to answer" in str(exc_info.value)

    def test_answer_tracks_for_undo(self, basic_collection, mock_anki_scheduler):
        """answer() should track card ID for undo."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        card_view = session.next_card()
        original_card_id = card_view.card_id

        session.answer(Rating.EASY)

        assert original_card_id in session._answered_card_ids


class TestUndoFlow:
    """Tests for undo() operation."""

    def test_undo_restores_previous_card(self, basic_collection, mock_anki_scheduler):
        """undo() should restore the previously answered card."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        first_card = session.next_card()
        original_id = first_card.card_id

        session.answer(Rating.AGAIN)

        # Undo should restore the card
        restored_card = session.undo()

        assert restored_card.card_id == original_id

    def test_undo_without_previous_answer_raises_error(self, basic_collection):
        """undo() should raise UndoError if nothing to undo."""
        from clanki.review.session import ReviewSession, UndoError

        session = ReviewSession(basic_collection, "Test Deck")

        with pytest.raises(UndoError) as exc_info:
            session.undo()

        assert "Nothing to undo" in str(exc_info.value)

    def test_undo_sets_current_card(self, basic_collection, mock_anki_scheduler):
        """undo() should set the restored card as current."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        session.next_card()
        session.answer(Rating.GOOD)

        assert session._current_card is None

        session.undo()

        assert session._current_card is not None

    def test_undo_pops_from_stack(self, basic_collection, mock_anki_scheduler):
        """undo() should pop the last answered card ID from the stack."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        session.next_card()
        session.answer(Rating.HARD)

        assert len(session._answered_card_ids) == 1

        session.undo()

        assert len(session._answered_card_ids) == 0

    def test_can_undo_reflects_stack_size(self, basic_collection, mock_anki_scheduler):
        """can_undo should reflect whether the undo stack has entries."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")

        # Initially no undo available
        assert session.can_undo is False

        # Answer first card
        session.next_card()
        session.answer(Rating.GOOD)
        assert session.can_undo is True

        # Answer second card
        session.next_card()
        session.answer(Rating.HARD)
        assert session.can_undo is True

        # Undo once - still one card on stack
        session.undo()
        assert session.can_undo is True

        # Undo again - stack is empty
        session.undo()
        assert session.can_undo is False

    def test_undo_handles_queued_card_mismatch(self, mock_anki_scheduler):
        """undo() should handle gracefully when queued card differs from undone card.

        This tests the branch in session.py:299-303 where after undo, the card
        at the front of the queue has a different ID than the last answered card.
        The implementation gracefully uses the queued card instead.
        """
        from clanki.review.session import Rating, ReviewSession

        # Create a collection with custom undo behavior that simulates mismatch
        deck_id = 4001
        decks = [FakeDeckInfo(name="Mismatch Deck", id=deck_id)]
        deck_tree = FakeTreeNode(
            deck_id=deck_id,
            name="Mismatch Deck",
            new_count=2,
            learn_count=0,
            review_count=0,
        )
        cards = [
            FakeCard(id=401, question_html="Q1", answer_html="A1"),
            FakeCard(id=402, question_html="Q2", answer_html="A2"),
        ]
        col = FakeCollection(decks=decks, deck_tree=deck_tree, cards=cards)

        # Override undo to return a different card at the front of queue
        original_undo = col.undo

        def undo_with_mismatch():
            """Undo that restores a different card to the queue."""
            original_undo()
            # After undo, put card 402 at front instead of 401
            col.sched._cards = [
                FakeCard(id=402, question_html="Mismatched Q", answer_html="Mismatched A"),
            ]
            col._cards_by_id[402] = col.sched._cards[0]

        col.undo = undo_with_mismatch

        session = ReviewSession(col, "Mismatch Deck")
        card1 = session.next_card()
        assert card1.card_id == 401

        session.answer(Rating.AGAIN)

        # Undo - but collection returns card 402 at front of queue instead of 401
        restored = session.undo()

        # The session should gracefully use the queued card (402) not the original (401)
        assert restored.card_id == 402
        assert "Mismatched" in restored.question_html


class TestFullReviewCycle:
    """Integration tests for complete review cycles."""

    def test_review_multiple_cards_in_sequence(self, basic_collection, mock_anki_scheduler):
        """Should be able to review multiple cards in sequence."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")

        # Review first card
        card1 = session.next_card()
        assert card1 is not None
        assert card1.card_id == 101
        session.answer(Rating.GOOD)

        # Review second card
        card2 = session.next_card()
        assert card2 is not None
        assert card2.card_id == 102
        session.answer(Rating.EASY)

        # Review third card
        card3 = session.next_card()
        assert card3 is not None
        assert card3.card_id == 103
        session.answer(Rating.AGAIN)

        # Queue should be empty now
        card4 = session.next_card()
        assert card4 is None

    def test_answer_undo_answer_cycle(self, basic_collection, mock_anki_scheduler):
        """Should be able to answer, undo, then answer again."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")

        # Get and answer first card
        card1 = session.next_card()
        session.answer(Rating.AGAIN)

        # Undo
        restored = session.undo()
        assert restored.card_id == card1.card_id

        # Answer again with different rating
        session.answer(Rating.EASY)

        # Should move to next card
        card2 = session.next_card()
        assert card2.card_id == 102

    def test_get_counts_reflects_deck_state(self, basic_collection):
        """get_counts() should return current deck due counts."""
        from clanki.review.session import DeckCounts, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")
        counts = session.get_counts()

        assert isinstance(counts, DeckCounts)
        assert counts.new_count == 2
        assert counts.learn_count == 1
        assert counts.review_count == 3
        assert counts.total == 6


class TestErrorBranches:
    """Tests for error handling branches."""

    def test_answer_with_no_card_fetched_raises(self, empty_collection, mock_anki_scheduler):
        """answer() after next_card() returns None should raise."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(empty_collection, "Empty Deck")
        card = session.next_card()  # Returns None

        assert card is None

        with pytest.raises(RuntimeError) as exc_info:
            session.answer(Rating.GOOD)

        assert "No card to answer" in str(exc_info.value)
        assert "next_card()" in str(exc_info.value)

    def test_multi_level_undo(self, basic_collection, mock_anki_scheduler):
        """Undo should work multiple times in LIFO order."""
        from clanki.review.session import Rating, ReviewSession, UndoError

        session = ReviewSession(basic_collection, "Test Deck")

        # Answer 3 cards in sequence
        card1 = session.next_card()
        assert card1.card_id == 101
        session.answer(Rating.GOOD)

        card2 = session.next_card()
        assert card2.card_id == 102
        session.answer(Rating.HARD)

        card3 = session.next_card()
        assert card3.card_id == 103
        session.answer(Rating.EASY)

        # Undo 3 times in LIFO order
        restored3 = session.undo()
        assert restored3.card_id == 103

        restored2 = session.undo()
        assert restored2.card_id == 102

        restored1 = session.undo()
        assert restored1.card_id == 101

        # Fourth undo should fail (nothing left to undo)
        with pytest.raises(UndoError) as exc_info:
            session.undo()

        assert "Nothing to undo" in str(exc_info.value)

    def test_deck_id_property_raises_if_not_resolved(self):
        """deck_id property should raise if deck not properly resolved."""
        from clanki.review.session import ReviewSession

        # Create a session with valid deck
        deck_id = 999
        decks = [FakeDeckInfo(name="ValidDeck", id=deck_id)]
        deck_tree = FakeTreeNode(
            deck_id=deck_id,
            name="ValidDeck",
            new_count=0,
            learn_count=0,
            review_count=0,
        )
        col = FakeCollection(decks=decks, deck_tree=deck_tree, cards=[])

        session = ReviewSession(col, "ValidDeck")

        # Manually break the state (this wouldn't happen in normal use)
        session._deck_id = None

        with pytest.raises(RuntimeError) as exc_info:
            _ = session.deck_id

        assert "not selected" in str(exc_info.value).lower()


class TestRatingEnum:
    """Integration tests for Rating enum usage."""

    def test_all_ratings_work_in_answer(self, basic_collection, mock_anki_scheduler):
        """All Rating values should work in answer()."""
        from clanki.review.session import Rating, ReviewSession

        session = ReviewSession(basic_collection, "Test Deck")

        # Test each rating
        for rating in [Rating.AGAIN, Rating.HARD, Rating.GOOD, Rating.EASY]:
            # Reset the collection for each test
            basic_collection.sched._cards = [
                FakeCard(id=100 + rating.value, question_html="Q", answer_html="A"),
            ]
            basic_collection._cards_by_id[100 + rating.value] = basic_collection.sched._cards[0]

            session.next_card()
            session.answer(rating)  # Should not raise

            # Verify card was removed from queue
            assert len(basic_collection.sched._cards) == 0

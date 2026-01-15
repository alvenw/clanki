"""Tests for review/session.py - review session wrapper with mocked Anki components."""

import sys
from dataclasses import dataclass, field
from unittest.mock import MagicMock, Mock, patch

import pytest

from clanki.review.session import (
    DeckCounts,
    DeckNotFoundError,
    Rating,
    ReviewSession,
    UndoError,
)


@pytest.fixture
def mock_anki_scheduler():
    """Mock anki.scheduler.v3 module to avoid circular import issues."""
    mock_module = MagicMock()
    mock_module.CardAnswer.Rating.AGAIN = 1
    mock_module.CardAnswer.Rating.HARD = 2
    mock_module.CardAnswer.Rating.GOOD = 3
    mock_module.CardAnswer.Rating.EASY = 4

    # Store original if exists
    original = sys.modules.get("anki.scheduler.v3")

    sys.modules["anki.scheduler.v3"] = mock_module
    yield mock_module

    # Restore original
    if original is not None:
        sys.modules["anki.scheduler.v3"] = original
    else:
        sys.modules.pop("anki.scheduler.v3", None)


@dataclass
class MockDeckInfo:
    """Mock for Anki's DeckNameId."""

    name: str
    id: int


@dataclass
class MockTreeNode:
    """Mock for deck_due_tree node."""

    deck_id: int
    new_count: int
    learn_count: int
    review_count: int
    children: list


@dataclass
class MockQueuedCard:
    """Mock for QueuedCard protobuf."""

    card: Mock  # has .id attribute
    states: Mock  # scheduling states


@dataclass
class MockQueuedCards:
    """Mock for QueuedCards protobuf response."""

    cards: list


@dataclass
class MockRenderOutput:
    """Mock for card render output."""

    question_text: str
    answer_text: str
    question_av_tags: list = field(default_factory=list)
    answer_av_tags: list = field(default_factory=list)


def create_mock_collection(deck_name: str = "Test Deck", deck_id: int = 1234):
    """Create a mock Anki collection with standard test data."""
    col = MagicMock()

    # Mock decks
    mock_deck_info = MockDeckInfo(name=deck_name, id=deck_id)
    col.decks.all_names_and_ids.return_value = [mock_deck_info]
    col.decks.select = MagicMock()

    # Mock scheduler with due tree
    tree = MockTreeNode(
        deck_id=deck_id,
        new_count=5,
        learn_count=3,
        review_count=10,
        children=[],
    )
    col.sched.deck_due_tree.return_value = tree

    return col


def create_mock_card(card_id: int = 100):
    """Create a mock Card object."""
    card = MagicMock()
    card.id = card_id
    card.start_timer = MagicMock()
    card.render_output.return_value = MockRenderOutput(
        question_text="<div>Question HTML</div>",
        answer_text="<div>Answer HTML</div>",
    )
    return card


def create_mock_queued_cards(card_id: int = 100):
    """Create mock QueuedCards response."""
    queued_card = MockQueuedCard(
        card=Mock(id=card_id),
        states=Mock(),  # SchedulingStates protobuf
    )
    return MockQueuedCards(cards=[queued_card])


class TestReviewSessionInit:
    """Tests for ReviewSession initialization."""

    def test_init_resolves_deck_by_name(self):
        """ReviewSession should resolve deck by name on init."""
        col = create_mock_collection(deck_name="My Deck", deck_id=5678)

        session = ReviewSession(col, "My Deck")

        assert session.deck_id == 5678
        assert session.deck_name == "My Deck"
        col.decks.select.assert_called_with(5678)

    def test_init_raises_deck_not_found(self):
        """ReviewSession should raise DeckNotFoundError for unknown deck."""
        col = create_mock_collection(deck_name="Other Deck", deck_id=1)

        with pytest.raises(DeckNotFoundError) as exc_info:
            ReviewSession(col, "NonExistent Deck")

        assert "NonExistent Deck" in str(exc_info.value)
        assert "Available decks:" in str(exc_info.value)


class TestGetCounts:
    """Tests for get_counts method."""

    def test_get_counts_returns_deck_counts(self):
        """get_counts should return DeckCounts from deck_due_tree."""
        col = create_mock_collection()
        session = ReviewSession(col, "Test Deck")

        counts = session.get_counts()

        assert isinstance(counts, DeckCounts)
        assert counts.new_count == 5
        assert counts.learn_count == 3
        assert counts.review_count == 10
        assert counts.total == 18

    def test_get_counts_searches_tree_recursively(self):
        """get_counts should find deck in nested tree."""
        col = create_mock_collection(deck_id=999)

        # Create nested tree structure
        target_node = MockTreeNode(
            deck_id=999,
            new_count=2,
            learn_count=1,
            review_count=4,
            children=[],
        )
        root = MockTreeNode(
            deck_id=1,
            new_count=0,
            learn_count=0,
            review_count=0,
            children=[target_node],
        )
        col.sched.deck_due_tree.return_value = root

        session = ReviewSession(col, "Test Deck")
        counts = session.get_counts()

        assert counts.new_count == 2
        assert counts.learn_count == 1
        assert counts.review_count == 4


class TestNextCard:
    """Tests for next_card method."""

    def test_next_card_returns_card_view(self):
        """next_card should return CardView with card data."""
        col = create_mock_collection()
        card = create_mock_card(card_id=42)
        queued = create_mock_queued_cards(card_id=42)

        col.sched.get_queued_cards.return_value = queued
        col.get_card.return_value = card

        session = ReviewSession(col, "Test Deck")
        card_view = session.next_card()

        assert card_view is not None
        assert card_view.card_id == 42
        assert "Question HTML" in card_view.question_html
        assert "Answer HTML" in card_view.answer_html

    def test_next_card_returns_none_when_no_cards(self):
        """next_card should return None when no cards due."""
        col = create_mock_collection()
        col.sched.get_queued_cards.return_value = MockQueuedCards(cards=[])

        session = ReviewSession(col, "Test Deck")
        card_view = session.next_card()

        assert card_view is None

    def test_next_card_selects_deck_first(self):
        """next_card should ensure deck is selected before fetching."""
        col = create_mock_collection(deck_id=777)
        col.sched.get_queued_cards.return_value = MockQueuedCards(cards=[])

        session = ReviewSession(col, "Test Deck")
        session.next_card()

        # Should be called on init and again on next_card
        calls = col.decks.select.call_args_list
        assert any(call[0][0] == 777 for call in calls)


class TestAnswer:
    """Tests for answer method."""

    def test_answer_starts_timer(self, mock_anki_scheduler):
        """answer should call card.start_timer() before answering."""
        col = create_mock_collection()
        card = create_mock_card()
        queued = create_mock_queued_cards()

        col.sched.get_queued_cards.return_value = queued
        col.get_card.return_value = card
        col.sched.build_answer.return_value = Mock()

        session = ReviewSession(col, "Test Deck")
        session.next_card()

        session.answer(Rating.GOOD)

        card.start_timer.assert_called_once()

    def test_answer_maps_rating_correctly(self, mock_anki_scheduler):
        """answer should map Rating enum to Anki's protobuf rating."""
        col = create_mock_collection()
        card = create_mock_card()
        queued = create_mock_queued_cards()

        col.sched.get_queued_cards.return_value = queued
        col.get_card.return_value = card

        session = ReviewSession(col, "Test Deck")
        session.next_card()

        session.answer(Rating.GOOD)

        # Verify build_answer was called with correct rating (GOOD = 3)
        call_kwargs = col.sched.build_answer.call_args[1]
        assert call_kwargs["rating"] == 3  # GOOD

    def test_answer_calls_answer_card(self, mock_anki_scheduler):
        """answer should call sched.answer_card with built answer."""
        col = create_mock_collection()
        card = create_mock_card()
        queued = create_mock_queued_cards()

        col.sched.get_queued_cards.return_value = queued
        col.get_card.return_value = card
        mock_answer = Mock()
        col.sched.build_answer.return_value = mock_answer

        session = ReviewSession(col, "Test Deck")
        session.next_card()

        session.answer(Rating.GOOD)

        col.sched.answer_card.assert_called_once_with(mock_answer)

    def test_answer_raises_if_no_current_card(self, mock_anki_scheduler):
        """answer should raise RuntimeError if no card is being reviewed."""
        col = create_mock_collection()
        col.sched.get_queued_cards.return_value = MockQueuedCards(cards=[])

        session = ReviewSession(col, "Test Deck")
        session.next_card()  # Returns None

        with pytest.raises(RuntimeError) as exc_info:
            session.answer(Rating.GOOD)

        assert "No card to answer" in str(exc_info.value)

    def test_answer_clears_current_card(self, mock_anki_scheduler):
        """answer should clear current card after answering."""
        col = create_mock_collection()
        card = create_mock_card()
        queued = create_mock_queued_cards()

        col.sched.get_queued_cards.return_value = queued
        col.get_card.return_value = card

        session = ReviewSession(col, "Test Deck")
        session.next_card()

        session.answer(Rating.AGAIN)

        # Current card should be cleared
        assert session._current_card is None


class TestRatingEnum:
    """Tests for Rating enum values."""

    def test_rating_values(self):
        """Rating enum should have correct integer values."""
        assert Rating.AGAIN == 1
        assert Rating.HARD == 2
        assert Rating.GOOD == 3
        assert Rating.EASY == 4


class TestDeckCounts:
    """Tests for DeckCounts dataclass."""

    def test_total_property(self):
        """total should sum new, learn, and review counts."""
        counts = DeckCounts(new_count=5, learn_count=3, review_count=12)

        assert counts.total == 20

    def test_total_with_zeros(self):
        """total should work correctly with zero values."""
        counts = DeckCounts(new_count=0, learn_count=0, review_count=0)

        assert counts.total == 0

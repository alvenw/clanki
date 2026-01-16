"""Fake Anki environment stubs for CLI subprocess tests.

This module provides controlled stubs for Anki dependencies, allowing
deterministic CLI tests without requiring a real Anki installation.

Usage in tests:
    Import and call setup_fake_env() before running subprocess tests,
    or use the module as a sitecustomize replacement via PYTHONPATH.

Environment variables for control:
    CLANKI_FAKE_PROFILE: Profile name to return (default: "FakeProfile")
    CLANKI_FAKE_SYNC_RESULT: "success", "no_changes", or "error"
    CLANKI_FAKE_DECK_COUNT: Number of due cards (default: 0 for empty deck)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


# Fake data classes


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
    new_count: int = 0
    learn_count: int = 0
    review_count: int = 0
    children: list = field(default_factory=list)


@dataclass
class FakeRenderOutput:
    """Fake card render output."""

    question_text: str = "<div>Fake Question</div>"
    answer_text: str = "<div>Fake Answer</div>"
    question_av_tags: list = field(default_factory=list)
    answer_av_tags: list = field(default_factory=list)


@dataclass
class FakeSyncOutcome:
    """Fake sync outcome."""

    result: Any
    message: str
    server_message: str | None = None


class FakeCard:
    """Fake Anki Card."""

    def __init__(self, card_id: int = 1):
        self.id = card_id
        self.timer_started = False

    def start_timer(self) -> None:
        self.timer_started = True

    def render_output(self) -> FakeRenderOutput:
        return FakeRenderOutput()


class FakeQueuedCard:
    """Fake QueuedCard protobuf."""

    def __init__(self, card_id: int = 1):
        self.card = MagicMock(id=card_id)
        self.states = MagicMock()


class FakeQueuedCards:
    """Fake QueuedCards response."""

    def __init__(self, cards: list | None = None):
        self.cards = cards or []


class FakeScheduler:
    """Fake Anki scheduler."""

    def __init__(self, deck_tree: FakeTreeNode, cards: list | None = None):
        self._deck_tree = deck_tree
        self._cards = list(cards) if cards else []

    def deck_due_tree(self) -> FakeTreeNode:
        return self._deck_tree

    def get_queued_cards(self, fetch_limit: int = 1) -> FakeQueuedCards:
        if not self._cards:
            return FakeQueuedCards([])
        queued = [FakeQueuedCard(c.id) for c in self._cards[:fetch_limit]]
        return FakeQueuedCards(queued)

    def build_answer(self, card: Any, states: Any, rating: Any) -> dict:
        return {"card_id": card.id, "rating": rating}

    def answer_card(self, answer: dict) -> None:
        if self._cards:
            self._cards.pop(0)


class FakeDecks:
    """Fake Anki decks manager."""

    def __init__(self, decks: list[FakeDeckInfo]):
        self._decks = decks
        self._selected_id: int | None = None

    def all_names_and_ids(self) -> list[FakeDeckInfo]:
        return self._decks

    def select(self, deck_id: int) -> None:
        self._selected_id = deck_id


class FakeMedia:
    """Fake Anki media manager."""

    def __init__(self, media_dir: str = "/fake/media"):
        self._media_dir = media_dir

    def dir(self) -> str:
        return self._media_dir


class FakeCollection:
    """Fake Anki Collection for testing."""

    def __init__(
        self,
        profile: str = "FakeProfile",
        deck_count: int = 0,
    ):
        self._profile = profile
        deck_id = 1001
        decks = [FakeDeckInfo(name="Default", id=deck_id)]
        cards = [FakeCard(i) for i in range(deck_count)]
        deck_tree = FakeTreeNode(
            deck_id=deck_id,
            name="Default",
            new_count=deck_count,
            learn_count=0,
            review_count=0,
        )
        self.decks = FakeDecks(decks)
        self.sched = FakeScheduler(deck_tree, cards)
        self.media = FakeMedia()
        self._cards_by_id = {c.id: c for c in cards}

    def get_card(self, card_id: int) -> FakeCard:
        if card_id in self._cards_by_id:
            return self._cards_by_id[card_id]
        return FakeCard(card_id)

    def undo(self) -> None:
        pass

    def close(self) -> None:
        pass


def get_fake_profile() -> str:
    """Get the fake profile name from environment or default."""
    return os.environ.get("CLANKI_FAKE_PROFILE", "FakeProfile")


def get_fake_deck_count() -> int:
    """Get the fake deck count from environment or default."""
    return int(os.environ.get("CLANKI_FAKE_DECK_COUNT", "0"))


def get_fake_sync_result() -> str:
    """Get the fake sync result from environment or default."""
    return os.environ.get("CLANKI_FAKE_SYNC_RESULT", "no_changes")


def create_fake_collection(path: Path | None = None) -> FakeCollection:
    """Create a fake collection with environment-controlled settings."""
    return FakeCollection(
        profile=get_fake_profile(),
        deck_count=get_fake_deck_count(),
    )


def create_patches() -> list:
    """Create all patches needed for fake CLI environment.

    Returns a list of patch context managers that should be started.
    """
    from clanki.sync import SyncResult

    fake_profile = get_fake_profile()
    fake_sync_result = get_fake_sync_result()

    # Determine sync outcome based on env var
    if fake_sync_result == "success":
        sync_outcome = FakeSyncOutcome(
            result=SyncResult.SUCCESS,
            message="Sync completed successfully.",
        )
    elif fake_sync_result == "error":
        sync_outcome = FakeSyncOutcome(
            result=SyncResult.AUTH_FAILED,
            message="Sync failed: fake error",
        )
    else:  # no_changes
        sync_outcome = FakeSyncOutcome(
            result=SyncResult.NO_CHANGES,
            message="Collection is already in sync.",
        )

    patches = [
        patch("clanki.cli.resolve_anki_base", return_value=Path("/fake/anki")),
        patch("clanki.cli.default_profile", return_value=fake_profile),
        patch(
            "clanki.cli.resolve_collection_path",
            return_value=Path("/fake/anki") / fake_profile / "collection.anki2",
        ),
        patch("clanki.cli.open_collection", side_effect=create_fake_collection),
        patch("clanki.cli.close_collection"),
        patch("clanki.cli.run_sync", return_value=sync_outcome),
        patch("clanki.cli._check_tui_available", return_value=False),
    ]

    return patches


def setup_fake_env():
    """Set up the fake environment by starting all patches.

    Returns:
        List of started patch objects (call stop() on each to clean up).
    """
    patches = create_patches()
    started = []
    for p in patches:
        started.append(p.start())
    return patches, started


def teardown_fake_env(patches: list):
    """Tear down the fake environment by stopping all patches."""
    for p in patches:
        p.stop()

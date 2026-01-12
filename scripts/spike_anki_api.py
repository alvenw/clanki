#!/usr/bin/env python3
"""
ANKI-1 Spike: Validate Anki Python backend API for local collection access.

This script is temporary and should NOT be committed.

Requirements:
    pip install anki>=25.9

Usage:
    # Make sure Anki Desktop is NOT running (avoids DB lock)
    python3 scripts/spike_anki_api.py
    python3 scripts/spike_anki_api.py --profile "User 1"
    python3 scripts/spike_anki_api.py --collection "/path/to/collection.anki2"
    python3 scripts/spike_anki_api.py --deck "My Deck" --review

Notes:
    - Tested with anki==25.9 (matching apy baseline)
    - macOS only for auto-profile detection
    - Collection is opened in read/write mode
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Optional

# Check anki package is available
try:
    import anki
    from anki.collection import Collection
    from anki.scheduler.v3 import CardAnswer
    ANKI_VERSION = pkg_version("anki")
except ImportError:
    print("Error: anki package not installed. Install with:")
    print("  pip install anki>=25.9")
    sys.exit(1)


# =============================================================================
# HTML Cleanup (adapted from anki_tui_poc.py)
# =============================================================================

class _HTMLStripper(HTMLParser):
    """Strip HTML tags and extract text content."""

    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip_depth = 0
        self._skip_tags = {"style", "script"}

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if data:
            self._chunks.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
            return
        if tag in {"br", "div", "p", "li", "tr"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in {"p", "div", "li", "tr"}:
            self._chunks.append("\n")

    def get_text(self):
        return "".join(self._chunks)


def html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    stripper = _HTMLStripper()
    stripper.feed(html or "")
    text = unescape(stripper.get_text())
    lines = [line.strip() for line in text.splitlines()]
    cleaned = []
    for line in lines:
        if line:
            cleaned.append(line)
        elif cleaned and cleaned[-1] != "":
            cleaned.append("")
    return "\n".join(cleaned).strip()


# =============================================================================
# Profile / Collection Path Resolution (macOS)
# =============================================================================

def get_anki_base_path() -> Path:
    """Get the Anki base directory (macOS only)."""
    return Path.home() / "Library" / "Application Support" / "Anki2"


def get_profiles() -> list[str]:
    """List available profiles from the Anki2 directory."""
    base = get_anki_base_path()
    if not base.exists():
        return []

    profiles = []
    for item in base.iterdir():
        if item.is_dir() and (item / "collection.anki2").exists():
            profiles.append(item.name)
    return sorted(profiles)


def get_last_used_profile() -> Optional[str]:
    """
    Get the last-used profile name.

    The prefs21.db database stores profile data in a 'profiles' table with
    binary blobs. Since extracting the active profile from blob data is complex,
    we fall back to checking file modification times.
    """
    base = get_anki_base_path()
    profiles = get_profiles()

    if not profiles:
        return None

    # Use the most recently modified collection as a heuristic for last-used
    latest_profile = None
    latest_mtime = 0

    for profile in profiles:
        col_path = base / profile / "collection.anki2"
        if col_path.exists():
            mtime = col_path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_profile = profile

    return latest_profile


def resolve_collection_path(profile: Optional[str] = None,
                            collection: Optional[str] = None) -> Path:
    """
    Resolve the collection path.

    Priority:
    1. Explicit --collection path
    2. Explicit --profile name
    3. Last-used profile from prefs21.db
    4. First available profile
    """
    if collection:
        path = Path(collection)
        if not path.exists():
            raise FileNotFoundError(f"Collection not found: {collection}")
        return path

    base = get_anki_base_path()

    if profile:
        path = base / profile / "collection.anki2"
        if not path.exists():
            raise FileNotFoundError(f"Profile collection not found: {path}")
        return path

    # Try last-used profile
    last_profile = get_last_used_profile()
    if last_profile:
        path = base / last_profile / "collection.anki2"
        if path.exists():
            print(f"Using last-used profile: {last_profile}")
            return path

    # Fallback to first available profile
    profiles = get_profiles()
    if not profiles:
        raise FileNotFoundError(
            f"No Anki profiles found in {base}. "
            "Please run Anki at least once to create a profile."
        )

    print(f"Using first available profile: {profiles[0]}")
    return base / profiles[0] / "collection.anki2"


# =============================================================================
# Collection Management
# =============================================================================

@dataclass
class DeckCounts:
    """Due counts for a deck."""
    new_count: int
    learn_count: int
    review_count: int

    @property
    def total_due(self) -> int:
        return self.new_count + self.learn_count + self.review_count


def open_collection(collection_path: Path) -> Collection:
    """
    Open an Anki collection.

    The collection is opened in read/write mode. Make sure Anki Desktop
    is NOT running to avoid database lock issues.
    """
    print(f"Opening collection: {collection_path}")

    if not collection_path.exists():
        raise FileNotFoundError(f"Collection not found: {collection_path}")

    # Check if the database is locked
    try:
        col = Collection(str(collection_path))
        print(f"  Anki backend version: {ANKI_VERSION}")
        return col
    except Exception as e:
        if "locked" in str(e).lower():
            raise RuntimeError(
                "Collection is locked. Make sure Anki Desktop is not running."
            ) from e
        raise


def close_collection(col: Collection) -> None:
    """Close the collection cleanly."""
    print("Closing collection...")
    col.close()
    print("  Collection closed successfully.")


# =============================================================================
# Deck Listing and Counts
# =============================================================================

def list_decks(col: Collection) -> list[dict]:
    """
    List all decks with their IDs and names.

    Returns a list of dicts with 'id' and 'name' keys.
    """
    decks = []
    for deck in col.decks.all_names_and_ids():
        decks.append({
            "id": deck.id,
            "name": deck.name,
        })
    return decks


def get_deck_due_counts(col: Collection, deck_id: int) -> DeckCounts:
    """
    Get due counts for a specific deck.

    Uses the scheduler's deck_due_tree() to get accurate counts.
    """
    # Get the deck tree which includes counts
    tree = col.sched.deck_due_tree()

    def find_deck_counts(node, target_id: int) -> Optional[DeckCounts]:
        """Recursively search the deck tree for the target deck."""
        if node.deck_id == target_id:
            return DeckCounts(
                new_count=node.new_count,
                learn_count=node.learn_count,
                review_count=node.review_count,
            )
        for child in node.children:
            result = find_deck_counts(child, target_id)
            if result:
                return result
        return None

    result = find_deck_counts(tree, deck_id)
    if result:
        return result

    # Fallback if deck not found in tree
    return DeckCounts(new_count=0, learn_count=0, review_count=0)


def print_deck_tree(col: Collection) -> None:
    """Print the deck tree with due counts."""
    tree = col.sched.deck_due_tree()

    def print_node(node, indent: int = 0):
        prefix = "  " * indent
        total = node.new_count + node.learn_count + node.review_count
        print(f"{prefix}{node.name}")
        print(f"{prefix}  ID: {node.deck_id}")
        print(f"{prefix}  New: {node.new_count}, Learn: {node.learn_count}, "
              f"Review: {node.review_count}, Total: {total}")
        for child in node.children:
            print_node(child, indent + 1)

    print_node(tree)


# =============================================================================
# Headless Review Flow
# =============================================================================

def select_deck(col: Collection, deck_id: int) -> None:
    """Select a deck for review."""
    col.decks.select(deck_id)
    print(f"Selected deck ID: {deck_id}")


def get_queued_cards(col: Collection, limit: int = 10) -> list:
    """
    Get queued cards for review.

    Uses col.sched.get_queued_cards() which returns cards in review order.
    """
    try:
        # get_queued_cards returns a QueuedCards protobuf message
        queued = col.sched.get_queued_cards(fetch_limit=limit)
        return queued.cards
    except Exception as e:
        print(f"Warning: get_queued_cards failed: {e}")
        return []


def render_card(col: Collection, card_id: int) -> tuple[str, str]:
    """
    Render a card's question and answer.

    Returns (question_html, answer_html).
    """
    card = col.get_card(card_id)
    note = card.note()

    # Render the card using the template
    result = card.render_output()

    return result.question_text, result.answer_text


def answer_card(col: Collection, card, states, rating: int) -> None:
    """
    Answer a card with a rating.

    Args:
        col: The collection
        card: The Card object
        states: SchedulingStates from the QueuedCard
        rating: Rating value (1=Again, 2=Hard, 3=Good, 4=Easy)

    This uses the v3 scheduler's answer_card method.
    """
    # Map rating int to CardAnswer.Rating enum
    rating_map = {
        1: CardAnswer.Rating.AGAIN,
        2: CardAnswer.Rating.HARD,
        3: CardAnswer.Rating.GOOD,
        4: CardAnswer.Rating.EASY,
    }

    if rating not in rating_map:
        raise ValueError(f"Invalid rating: {rating}. Must be 1-4.")

    # Ensure the card timer is started (required for time_taken calculation)
    if card.timer_started is None:
        card.start_timer()

    # Build the answer using states from QueuedCard
    answer = col.sched.build_answer(
        card=card,
        states=states,
        rating=rating_map[rating],
    )

    # Submit the answer
    col.sched.answer_card(answer)
    print(f"  Answered card {card.id} with rating {rating}")


def headless_review(col: Collection, deck_name: str, limit: int = 5) -> None:
    """
    Perform a headless review session.

    This demonstrates the full review flow:
    1. Select deck
    2. Get queued cards
    3. Display question/answer
    4. Answer card
    """
    # Find deck by name
    deck = None
    for d in col.decks.all_names_and_ids():
        if d.name == deck_name:
            deck = d
            break

    if not deck:
        print(f"Deck not found: {deck_name}")
        return

    print(f"\n{'='*60}")
    print(f"Starting headless review for: {deck_name}")
    print(f"{'='*60}\n")

    # Select the deck
    select_deck(col, deck.id)

    # Get counts before review
    counts = get_deck_due_counts(col, deck.id)
    print(f"Due counts - New: {counts.new_count}, Learn: {counts.learn_count}, "
          f"Review: {counts.review_count}, Total: {counts.total_due}\n")

    # Get queued cards
    queued = get_queued_cards(col, limit)

    if not queued:
        print("No cards due for review.")
        return

    print(f"Got {len(queued)} cards to review\n")

    for i, queued_card in enumerate(queued, 1):
        card = col.get_card(queued_card.card.id)
        states = queued_card.states

        print(f"--- Card {i}/{len(queued)} (ID: {card.id}) ---")

        # Render the card
        question_html, answer_html = render_card(col, card.id)
        question = html_to_text(question_html)
        answer = html_to_text(answer_html)

        print(f"\nQuestion:\n{question}")
        print(f"\nAnswer:\n{answer}")

        # In a real app, we'd prompt for rating
        # For the spike, just auto-answer with "Good" (3)
        print("\n[Auto-answering with 'Good' (3)]")
        answer_card(col, card, states, rating=3)
        print()

    # Get counts after review
    counts_after = get_deck_due_counts(col, deck.id)
    print(f"\nDue counts after review - New: {counts_after.new_count}, "
          f"Learn: {counts_after.learn_count}, "
          f"Review: {counts_after.review_count}, Total: {counts_after.total_due}")


# =============================================================================
# Interactive Review (for testing)
# =============================================================================

def interactive_review(col: Collection, deck_name: str, limit: int = 10) -> None:
    """
    Interactive review session with manual rating input.
    """
    # Find deck by name
    deck = None
    for d in col.decks.all_names_and_ids():
        if d.name == deck_name:
            deck = d
            break

    if not deck:
        print(f"Deck not found: {deck_name}")
        return

    print(f"\n{'='*60}")
    print(f"Interactive review for: {deck_name}")
    print("Commands: 1=Again, 2=Hard, 3=Good, 4=Easy, s=Skip, q=Quit")
    print(f"{'='*60}\n")

    select_deck(col, deck.id)

    reviewed = 0
    while reviewed < limit:
        counts = get_deck_due_counts(col, deck.id)
        print(f"\nDue: New {counts.new_count} | Learn {counts.learn_count} | "
              f"Review {counts.review_count}")

        queued = get_queued_cards(col, 1)
        if not queued:
            print("No more cards due.")
            break

        queued_card = queued[0]
        card = col.get_card(queued_card.card.id)
        states = queued_card.states

        question_html, answer_html = render_card(col, card.id)
        question = html_to_text(question_html)
        answer = html_to_text(answer_html)

        print(f"\n{'─'*40}")
        print(f"Card {reviewed + 1}/{limit}")
        print(f"{'─'*40}")
        print(f"\nQuestion:\n{question}")

        input("\nPress Enter to show answer...")

        print(f"\nAnswer:\n{answer}")

        while True:
            choice = input("\nRating (1-4), s=skip, q=quit: ").strip().lower()
            if choice == 'q':
                print("Exiting review.")
                return
            if choice == 's':
                print("Skipping card.")
                break
            if choice in {'1', '2', '3', '4'}:
                answer_card(col, card, states, int(choice))
                reviewed += 1
                break
            print("Invalid input. Use 1-4, s, or q.")

    print(f"\nReviewed {reviewed} cards.")


# =============================================================================
# Main / CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Spike: Anki Python backend API validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--profile",
        help="Anki profile name (e.g., 'User 1')"
    )
    parser.add_argument(
        "--collection",
        help="Direct path to collection.anki2 file"
    )
    parser.add_argument(
        "--deck",
        help="Deck name for review (required with --review)"
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Run interactive review session"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless review (auto-answers with 'Good')"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum cards to review (default: 5)"
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit"
    )
    args = parser.parse_args()

    # Print version info
    print(f"Anki package version: {ANKI_VERSION}")
    print()

    # List profiles mode
    if args.list_profiles:
        print("Available profiles:")
        profiles = get_profiles()
        if not profiles:
            print("  (none found)")
        else:
            for p in profiles:
                print(f"  - {p}")
        last = get_last_used_profile()
        if last:
            print(f"\nLast used: {last}")
        return 0

    # Resolve collection path
    try:
        collection_path = resolve_collection_path(args.profile, args.collection)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    # Open collection
    try:
        col = open_collection(collection_path)
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error opening collection: {e}")
        return 1

    try:
        # List decks
        print("\n" + "="*60)
        print("DECK TREE WITH DUE COUNTS")
        print("="*60 + "\n")
        print_deck_tree(col)

        # Review mode
        if args.review or args.headless:
            if not args.deck:
                print("\nError: --deck is required with --review or --headless")
                return 1

            if args.headless:
                headless_review(col, args.deck, args.limit)
            else:
                interactive_review(col, args.deck, args.limit)

        print("\n" + "="*60)
        print("SPIKE COMPLETED SUCCESSFULLY")
        print("="*60)

    finally:
        close_collection(col)

    return 0


# =============================================================================
# API Surface Notes (for wrapper design)
# =============================================================================

"""
WORKING API CALLS (anki==25.9.2)
================================

Tested with: anki==25.9.2

1. Collection Management:
   - Collection(path: str) - Open collection (read/write mode)
   - col.close() - Close collection cleanly

2. Deck Operations:
   - col.decks.all_names_and_ids() -> list[DeckNameId]
     - Returns deck objects with .id and .name attributes
   - col.decks.select(deck_id: int) -> None
     - Selects deck for review
   - col.sched.deck_due_tree() -> DeckTreeNode
     - Returns tree with .new_count, .learn_count, .review_count
     - Recurse .children for sub-decks

3. Card Retrieval:
   - col.sched.get_queued_cards(fetch_limit: int) -> QueuedCards
     - Returns protobuf with .cards list of QueuedCard
     - Each QueuedCard has .card (card info), .states (SchedulingStates)
   - col.get_card(card_id: int) -> Card
     - Returns full Card object for manipulation

4. Card Rendering:
   - card.render_output() -> RenderOutput
     - Has .question_text and .answer_text (HTML)

5. Answer Flow:
   - card.start_timer() - REQUIRED before answering (sets timer_started)
   - col.sched.build_answer(card, states, rating) -> CardAnswer
     - states: from QueuedCard.states
     - rating: CardAnswer.Rating.{AGAIN,HARD,GOOD,EASY}
   - col.sched.answer_card(answer) -> OpChanges
     - Persists the answer to the database

6. Profile Detection (macOS):
   - Base path: ~/Library/Application Support/Anki2/
   - Collection: {base}/{profile}/collection.anki2
   - prefs21.db stores profile data as binary blobs


SUGGESTED WRAPPER API
=====================

class AnkiCollection:
    def __init__(self, path: str): ...
    def close(self): ...

    # Deck operations
    def list_decks(self) -> list[Deck]: ...
    def select_deck(self, deck_id: int): ...
    def get_deck_counts(self, deck_id: int) -> DeckCounts: ...

    # Review operations
    def get_next_card(self) -> Optional[ReviewCard]: ...
    def answer_card(self, card_id: int, rating: Rating): ...

@dataclass
class Deck:
    id: int
    name: str
    new_count: int
    learn_count: int
    review_count: int

@dataclass
class ReviewCard:
    id: int
    question: str      # plain text (HTML stripped)
    answer: str        # plain text (HTML stripped)
    _card: Card        # internal: actual Card object
    _states: States    # internal: SchedulingStates for answering

class Rating(Enum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


VERSION CAVEATS
===============

- anki>=25.9 uses v3 scheduler exclusively (no v1/v2)
- get_queued_cards() returns a QueuedCards protobuf message
  - Access cards via .cards (list of QueuedCard)
  - Each QueuedCard has .card and .states
- CardAnswer.Rating is an enum from anki.scheduler.v3
- card.start_timer() MUST be called before build_answer()
- render_output() returns RenderOutput with question_text/answer_text
- DB locking: collection cannot be opened if Anki Desktop is running
- Profile prefs stored as binary blobs (not plain JSON)
"""


if __name__ == "__main__":
    sys.exit(main())

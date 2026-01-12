"""CLI command routing for Clanki.

This module provides the command-line interface with support for:
- TUI mode (default, with fallback to plain if unavailable)
- Plain terminal mode
- Review mode with deck selection
- Sync mode
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .collection import (
    CollectionLockError,
    CollectionNotFoundError,
    close_collection,
    open_collection,
)
from .config import default_profile, resolve_anki_base, resolve_collection_path
from .render import render_html_to_text
from .sync import SyncResult, run_sync


def _check_tui_available() -> bool:
    """Check if TUI dependencies are available."""
    try:
        import textual  # noqa: F401

        return True
    except ImportError:
        return False


def _cmd_sync(args: argparse.Namespace) -> int:
    """Handle sync command."""
    try:
        anki_base = resolve_anki_base()
        profile = default_profile(anki_base)

        if profile is None:
            print("Error: No Anki profiles found.", file=sys.stderr)
            return 1

        collection_path = resolve_collection_path(anki_base, profile)

        print(f"Syncing profile: {profile}")

        outcome = run_sync(
            collection_path=collection_path,
            anki_base=anki_base,
            profile=profile,
            log=lambda msg: print(f"  {msg}"),
        )

        if outcome.result == SyncResult.SUCCESS:
            print(outcome.message)
            if outcome.server_message:
                print(f"Server message: {outcome.server_message}")
            return 0
        elif outcome.result == SyncResult.NO_CHANGES:
            print(outcome.message)
            return 0
        else:
            print(f"Error: {outcome.message}", file=sys.stderr)
            return 1

    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except CollectionLockError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


def _cmd_review(args: argparse.Namespace) -> int:
    """Handle review command."""
    from .review import DeckNotFoundError, Rating, ReviewSession

    deck_name = args.deck
    use_plain = args.plain

    # Use TUI if available and not explicitly disabled
    if not use_plain and _check_tui_available():
        try:
            from .tui import run_tui

            anki_base = resolve_anki_base()
            profile = default_profile(anki_base)

            if profile is None:
                print("Error: No Anki profiles found.", file=sys.stderr)
                return 1

            collection_path = resolve_collection_path(anki_base, profile)
            run_tui(collection_path=collection_path, initial_deck=deck_name)
            return 0
        except CollectionLockError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except CollectionNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

    # Plain mode fallback
    try:
        anki_base = resolve_anki_base()
        profile = default_profile(anki_base)

        if profile is None:
            print("Error: No Anki profiles found.", file=sys.stderr)
            return 1

        collection_path = resolve_collection_path(anki_base, profile)

        print(f"Opening collection for profile: {profile}")
        col = open_collection(collection_path)

        try:
            session = ReviewSession(col, deck_name)
            counts = session.get_counts()

            print(f"\nReviewing: {deck_name}")
            print(
                f"Due: {counts.new_count} new, "
                f"{counts.learn_count} learning, "
                f"{counts.review_count} review"
            )
            print()

            if counts.total == 0:
                print("No cards due for review.")
                return 0

            # Get media directory for rendering
            media_dir = col.media.dir()

            # Plain review loop
            reviewed = 0
            while True:
                card = session.next_card()
                if card is None:
                    break

                # Show question
                question = render_html_to_text(card.question_html, media_dir=media_dir)
                print("-" * 40)
                print(f"Card {reviewed + 1}")
                print("-" * 40)
                print(f"\nQuestion:\n{question}\n")

                # Wait for user to reveal answer
                try:
                    input("Press Enter to show answer...")
                except (EOFError, KeyboardInterrupt):
                    print("\nExiting review.")
                    break

                # Show answer
                answer = render_html_to_text(card.answer_html, media_dir=media_dir)
                print(f"\nAnswer:\n{answer}\n")

                # Get rating
                print("Rate: (1) Again  (2) Hard  (3) Good  (4) Easy  (u) Undo  (q) Quit")
                while True:
                    try:
                        choice = input("> ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        print("\nExiting review.")
                        close_collection(col)
                        return 0

                    if choice == "q":
                        print("Exiting review.")
                        close_collection(col)
                        return 0

                    if choice == "u":
                        try:
                            card = session.undo()
                            print("Undone. Showing previous card.")
                            # Re-display the card
                            question = render_html_to_text(card.question_html, media_dir=media_dir)
                            answer = render_html_to_text(card.answer_html, media_dir=media_dir)
                            print(f"\nQuestion:\n{question}\n")
                            print(f"Answer:\n{answer}\n")
                            print(
                                "Rate: (1) Again  (2) Hard  (3) Good  (4) Easy  (u) Undo  (q) Quit"
                            )
                            continue
                        except Exception as exc:
                            print(f"Cannot undo: {exc}")
                            continue

                    if choice in {"1", "2", "3", "4"}:
                        rating_map = {
                            "1": Rating.AGAIN,
                            "2": Rating.HARD,
                            "3": Rating.GOOD,
                            "4": Rating.EASY,
                        }
                        session.answer(rating_map[choice])
                        reviewed += 1
                        break

                    print("Invalid choice. Use 1-4, u, or q.")

                print()

            # Show summary
            final_counts = session.get_counts()
            print("-" * 40)
            print(f"Session complete. Reviewed {reviewed} cards.")
            print(
                f"Remaining: {final_counts.new_count} new, "
                f"{final_counts.learn_count} learning, "
                f"{final_counts.review_count} review"
            )

        finally:
            close_collection(col)

        return 0

    except DeckNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except CollectionLockError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except CollectionNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


def _cmd_default(args: argparse.Namespace) -> int:
    """Handle default command (TUI or plain mode)."""
    use_plain = args.plain

    # Use TUI if available and not explicitly disabled
    if not use_plain and _check_tui_available():
        try:
            from .tui import run_tui

            anki_base = resolve_anki_base()
            profile = default_profile(anki_base)

            if profile is None:
                print("Error: No Anki profiles found.", file=sys.stderr)
                return 1

            collection_path = resolve_collection_path(anki_base, profile)
            run_tui(collection_path=collection_path)
            return 0
        except CollectionLockError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except CollectionNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

    # Plain mode fallback
    if use_plain or not _check_tui_available():
        # Plain mode: show deck list
        try:
            anki_base = resolve_anki_base()
            profile = default_profile(anki_base)

            if profile is None:
                print("Error: No Anki profiles found.", file=sys.stderr)
                return 1

            collection_path = resolve_collection_path(anki_base, profile)

            print(f"Opening collection for profile: {profile}")
            col = open_collection(collection_path)

            try:
                print("\nAvailable decks:")
                print("-" * 40)

                # Get deck tree for counts
                tree = col.sched.deck_due_tree()

                def print_deck(node: object, indent: int = 0) -> None:
                    prefix = "  " * indent
                    total = node.new_count + node.learn_count + node.review_count  # type: ignore
                    if total > 0 or indent == 0:
                        print(
                            f"{prefix}{node.name}  "  # type: ignore
                            f"({node.new_count}/{node.learn_count}/{node.review_count})"  # type: ignore
                        )
                    for child in node.children:  # type: ignore
                        print_deck(child, indent + 1)

                print_deck(tree)

                print()
                print("Run 'clanki review \"Deck Name\"' to start reviewing.")

            finally:
                close_collection(col)

            return 0

        except CollectionLockError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except CollectionNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

    # This should not be reached since TUI is handled above
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = argparse.ArgumentParser(
        prog="clanki",
        description="Terminal-based Anki review client",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Force plain terminal mode (no TUI)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # sync command
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync collection with AnkiWeb",
    )
    sync_parser.set_defaults(func=_cmd_sync)

    # review command
    review_parser = subparsers.add_parser(
        "review",
        help="Start a review session for a deck",
    )
    review_parser.add_argument(
        "deck",
        help="Name of the deck to review",
    )
    review_parser.add_argument(
        "--plain",
        action="store_true",
        help="Force plain terminal mode (no TUI)",
    )
    review_parser.set_defaults(func=_cmd_review)

    args = parser.parse_args(argv)

    # Route to appropriate handler
    if args.command is None:
        return _cmd_default(args)

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

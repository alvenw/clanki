"""CLI command routing for Clanki.

This module provides the command-line interface with support for:
- TUI mode (default, with fallback to plain if unavailable)
- Plain terminal mode
- Review mode with deck selection
- Sync mode
- Audio playback support (macOS only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .audio import (
    is_audio_playback_available,
    play_audio_for_side,
    substitute_audio_icons,
)
from .collection import (
    CollectionLockError,
    CollectionNotFoundError,
    close_collection,
    open_collection,
)
from .config import default_profile, resolve_anki_base, resolve_collection_path
from .config_store import load_config
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


def _resolve_images_enabled(args: argparse.Namespace) -> bool:
    """Resolve images_enabled from CLI flags or config.

    CLI flags take precedence over stored config.
    """
    # CLI override takes precedence
    if getattr(args, "images", None) is True:
        return True
    if getattr(args, "no_images", None) is True:
        return False

    # Fall back to config
    config = load_config()
    return config.images_enabled


def _resolve_audio_enabled(args: argparse.Namespace) -> bool:
    """Resolve audio_enabled from CLI flags or config.

    CLI flags take precedence over stored config.
    Returns False if audio playback is not available.
    """
    # If audio not available, can't be enabled
    if not is_audio_playback_available():
        return False

    # CLI override takes precedence
    if getattr(args, "audio", None) is True:
        return True
    if getattr(args, "no_audio", None) is True:
        return False

    # Fall back to config
    config = load_config()
    return config.audio_enabled


def _resolve_audio_autoplay(args: argparse.Namespace) -> bool:
    """Resolve audio_autoplay from CLI flags or config.

    CLI flags take precedence over stored config.
    """
    # CLI override takes precedence
    if getattr(args, "audio_autoplay", None) is True:
        return True
    if getattr(args, "no_audio_autoplay", None) is True:
        return False

    # Fall back to config
    config = load_config()
    return config.audio_autoplay


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
            images_enabled = _resolve_images_enabled(args)
            audio_enabled = _resolve_audio_enabled(args)
            audio_autoplay = _resolve_audio_autoplay(args)
            run_tui(
                collection_path=collection_path,
                initial_deck=deck_name,
                images_enabled=images_enabled,
                audio_enabled=audio_enabled,
                audio_autoplay=audio_autoplay,
            )
            return 0
        except CollectionNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # Plain mode fallback
    audio_enabled = _resolve_audio_enabled(args)
    audio_autoplay = _resolve_audio_autoplay(args)
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
            media_dir_path = Path(media_dir) if media_dir else None

            # Helper function to play audio for a side
            def play_audio(text: str, audio_files: list[str]) -> None:
                if audio_enabled and media_dir_path:
                    play_audio_for_side(
                        text=text,
                        audio_files=audio_files,
                        media_dir=media_dir_path,
                        on_error=lambda msg: print(f"Audio: {msg}"),
                    )

            # Plain review loop
            reviewed = 0
            answer_revealed = False

            while True:
                card = session.next_card()
                if card is None:
                    break

                answer_revealed = False

                # Show question
                question = render_html_to_text(card.question_html, media_dir=media_dir)
                # Substitute audio placeholders with icons for display
                question_display = substitute_audio_icons(question)
                print("-" * 40)
                print(f"Card {reviewed + 1}")
                print("-" * 40)
                print(f"\nQuestion:\n{question_display}\n")

                # Auto-play question audio
                if audio_autoplay:
                    play_audio(question, card.question_audio)

                # Get prompt text (includes audio replay option if audio present)
                reveal_prompt = "Press Enter to show answer"
                if audio_enabled and card.question_audio:
                    reveal_prompt += " (a=replay audio)"
                reveal_prompt += "..."

                # Wait for user to reveal answer
                while not answer_revealed:
                    try:
                        user_input = input(reveal_prompt).strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        print("\nExiting review.")
                        close_collection(col)
                        return 0

                    if user_input == "a" and audio_enabled:
                        play_audio(question, card.question_audio)
                        continue
                    else:
                        answer_revealed = True

                # Show answer
                answer = render_html_to_text(card.answer_html, media_dir=media_dir)
                answer_display = substitute_audio_icons(answer)
                print(f"\nAnswer:\n{answer_display}\n")

                # Auto-play answer audio
                if audio_autoplay:
                    play_audio(answer, card.answer_audio)

                # Get rating prompt with interval labels if available
                labels = card.rating_labels if len(card.rating_labels) == 4 else None
                if labels:
                    again, hard, good, easy = labels
                    rating_prompt = (
                        f"Rate: (1) Again {again}  (2) Hard {hard}  "
                        f"(3) Good {good}  (4) Easy {easy}  (u) Undo"
                    )
                else:
                    rating_prompt = "Rate: (1) Again  (2) Hard  (3) Good  (4) Easy  (u) Undo"
                if audio_enabled and card.answer_audio:
                    rating_prompt += "  (a) Replay"
                rating_prompt += "  (q) Quit"
                print(rating_prompt)

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

                    if choice == "a" and audio_enabled:
                        play_audio(answer, card.answer_audio)
                        continue

                    if choice == "u":
                        try:
                            card = session.undo()
                            print("Undone. Showing previous card.")
                            # Re-display the card
                            question = render_html_to_text(card.question_html, media_dir=media_dir)
                            answer = render_html_to_text(card.answer_html, media_dir=media_dir)
                            question_display = substitute_audio_icons(question)
                            answer_display = substitute_audio_icons(answer)
                            print(f"\nQuestion:\n{question_display}\n")
                            print(f"Answer:\n{answer_display}\n")
                            # Rebuild rating prompt with new card's labels
                            labels = card.rating_labels if len(card.rating_labels) == 4 else None
                            if labels:
                                again, hard, good, easy = labels
                                rating_prompt = (
                                    f"Rate: (1) Again {again}  (2) Hard {hard}  "
                                    f"(3) Good {good}  (4) Easy {easy}  (u) Undo"
                                )
                            else:
                                rating_prompt = "Rate: (1) Again  (2) Hard  (3) Good  (4) Easy  (u) Undo"
                            if audio_enabled and card.answer_audio:
                                rating_prompt += "  (a) Replay"
                            rating_prompt += "  (q) Quit"
                            print(rating_prompt)
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

                    print("Invalid choice. Use 1-4, u, a, or q.")

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
            images_enabled = _resolve_images_enabled(args)
            audio_enabled = _resolve_audio_enabled(args)
            audio_autoplay = _resolve_audio_autoplay(args)
            run_tui(
                collection_path=collection_path,
                images_enabled=images_enabled,
                audio_enabled=audio_enabled,
                audio_autoplay=audio_autoplay,
            )
            return 0
        except CollectionNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
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

    # Image rendering options (mutually exclusive)
    images_group = parser.add_mutually_exclusive_group()
    images_group.add_argument(
        "--images",
        action="store_true",
        help="Enable image rendering in TUI (overrides config)",
    )
    images_group.add_argument(
        "--no-images",
        action="store_true",
        dest="no_images",
        help="Disable image rendering in TUI (overrides config)",
    )

    # Audio playback options (mutually exclusive)
    audio_group = parser.add_mutually_exclusive_group()
    audio_group.add_argument(
        "--audio",
        action="store_true",
        help="Enable audio playback (overrides config, macOS only)",
    )
    audio_group.add_argument(
        "--no-audio",
        action="store_true",
        dest="no_audio",
        help="Disable audio playback (overrides config)",
    )

    # Audio autoplay options (mutually exclusive)
    autoplay_group = parser.add_mutually_exclusive_group()
    autoplay_group.add_argument(
        "--audio-autoplay",
        action="store_true",
        dest="audio_autoplay",
        help="Enable auto-play of audio on card display (overrides config)",
    )
    autoplay_group.add_argument(
        "--no-audio-autoplay",
        action="store_true",
        dest="no_audio_autoplay",
        help="Disable auto-play of audio (overrides config)",
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

    # Image rendering options for review command
    review_images_group = review_parser.add_mutually_exclusive_group()
    review_images_group.add_argument(
        "--images",
        action="store_true",
        help="Enable image rendering in TUI (overrides config)",
    )
    review_images_group.add_argument(
        "--no-images",
        action="store_true",
        dest="no_images",
        help="Disable image rendering in TUI (overrides config)",
    )

    # Audio playback options for review command
    review_audio_group = review_parser.add_mutually_exclusive_group()
    review_audio_group.add_argument(
        "--audio",
        action="store_true",
        help="Enable audio playback (overrides config, macOS only)",
    )
    review_audio_group.add_argument(
        "--no-audio",
        action="store_true",
        dest="no_audio",
        help="Disable audio playback (overrides config)",
    )

    # Audio autoplay options for review command
    review_autoplay_group = review_parser.add_mutually_exclusive_group()
    review_autoplay_group.add_argument(
        "--audio-autoplay",
        action="store_true",
        dest="audio_autoplay",
        help="Enable auto-play of audio on card display (overrides config)",
    )
    review_autoplay_group.add_argument(
        "--no-audio-autoplay",
        action="store_true",
        dest="no_audio_autoplay",
        help="Disable auto-play of audio (overrides config)",
    )

    review_parser.set_defaults(func=_cmd_review)

    args = parser.parse_args(argv)

    # Route to appropriate handler
    if args.command is None:
        return _cmd_default(args)

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

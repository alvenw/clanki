"""Black-box CLI smoke tests for Clanki.

These tests run the CLI via subprocess and validate:
- Exit codes
- Key stdout/stderr fragments
- Basic argument handling

Tests are designed to be hermetic (no real Anki DB, no network).
Uses tests/helpers/sitecustomize.py for controlled environment stubs
activated via CLANKI_TEST_MODE=fake.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def get_test_pythonpath() -> str:
    """Get PYTHONPATH that includes tests/helpers for sitecustomize."""
    # Get project root (contains tests/ and src/)
    project_root = Path(__file__).parent.parent.parent
    helpers_path = project_root / "tests" / "helpers"
    src_path = project_root / "src"

    # Build PYTHONPATH with:
    # 1. helpers first (for sitecustomize auto-import)
    # 2. project root (so tests.helpers.fake_cli_env can be imported)
    # 3. src (for clanki package)
    paths = [str(helpers_path), str(project_root), str(src_path)]
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        paths.append(existing)
    return os.pathsep.join(paths)


def run_cli_fake(
    args: list[str],
    *,
    sync_result: str = "no_changes",
    deck_count: int = 0,
    profile: str = "FakeProfile",
    timeout: int = 10,
) -> subprocess.CompletedProcess:
    """Run CLI with fake environment via subprocess.

    Args:
        args: CLI arguments (e.g., ["review", "--plain", "Default"])
        sync_result: "success", "no_changes", or "error"
        deck_count: Number of due cards in fake deck
        profile: Fake profile name
        timeout: Subprocess timeout in seconds

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = get_test_pythonpath()
    env["CLANKI_TEST_MODE"] = "fake"
    env["CLANKI_FAKE_PROFILE"] = profile
    env["CLANKI_FAKE_SYNC_RESULT"] = sync_result
    env["CLANKI_FAKE_DECK_COUNT"] = str(deck_count)

    return subprocess.run(
        [sys.executable, "-m", "clanki"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


class TestCliHelp:
    """Tests for --help and --version flags."""

    def test_help_flag_shows_usage(self):
        """--help should show usage information and exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "usage:" in result.stdout.lower() or "clanki" in result.stdout.lower()
        assert "review" in result.stdout.lower()
        assert "sync" in result.stdout.lower()

    def test_version_flag_shows_version(self):
        """--version should show version string and exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        # Version should contain a version number pattern
        assert "clanki" in result.stdout.lower() or "." in result.stdout


class TestCliReviewCommand:
    """Tests for review command exit behavior."""

    def test_review_missing_deck_arg_exits_error(self):
        """review without deck argument should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "review"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should fail because deck argument is required
        assert result.returncode != 0
        # argparse prints error to stderr
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_review_help_shows_deck_arg(self):
        """review --help should show deck argument."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "review", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "deck" in result.stdout.lower()
        assert "--plain" in result.stdout


class TestCliSyncCommand:
    """Tests for sync command structure."""

    def test_sync_help_shows_description(self):
        """sync --help should show sync description."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "sync", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        # Should have some sync-related text
        assert "sync" in result.stdout.lower()


class TestCliReviewPlainModeSuccess:
    """Tests for review command in plain mode with fake environment (subprocess)."""

    def test_review_plain_empty_deck_success(self):
        """review --plain with empty deck should exit 0 with 'No cards due'."""
        result = run_cli_fake(
            ["review", "--plain", "Default"],
            deck_count=0,
        )

        assert result.returncode == 0
        assert "No cards due for review." in result.stdout

    def test_review_plain_deck_not_found_exits_error(self):
        """review --plain with nonexistent deck should exit 1."""
        result = run_cli_fake(
            ["review", "--plain", "NonExistentDeck"],
            deck_count=0,
        )

        assert result.returncode == 1
        assert "error" in result.stderr.lower() or "not found" in result.stderr.lower()


class TestCliSyncSuccess:
    """Tests for sync command with fake environment (subprocess)."""

    def test_sync_no_changes_success(self):
        """sync with no changes should exit 0 and show 'already in sync'."""
        result = run_cli_fake(
            ["sync"],
            sync_result="no_changes",
        )

        assert result.returncode == 0
        assert "Collection is already in sync." in result.stdout

    def test_sync_success_with_changes(self):
        """sync with changes should exit 0 and show success message."""
        result = run_cli_fake(
            ["sync"],
            sync_result="success",
        )

        assert result.returncode == 0
        assert "Sync completed successfully." in result.stdout

    def test_sync_auth_failed_exits_error(self):
        """sync with auth failure should exit 1."""
        result = run_cli_fake(
            ["sync"],
            sync_result="error",
        )

        assert result.returncode == 1
        assert "error" in result.stderr.lower()


class TestCliMainFunction:
    """Tests for CLI main function behavior."""

    def test_main_with_unknown_command(self):
        """main() with unknown subcommand should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "unknown_command"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0

    def test_main_default_command_shows_decks(self):
        """Default command --plain should show deck list and exit 0."""
        result = run_cli_fake(
            ["--plain"],
            deck_count=0,
        )

        assert result.returncode == 0
        # Should show the fake deck
        assert "Default" in result.stdout
        # Should show the available decks header
        assert "Available decks" in result.stdout


class TestCliImageAndAudioFlags:
    """Tests for --images, --no-images, --audio, --no-audio flags."""

    def test_images_flag_in_help(self):
        """--images and --no-images should appear in help."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "--images" in result.stdout
        assert "--no-images" in result.stdout

    def test_audio_flags_in_help(self):
        """--audio and --no-audio should appear in help."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "--audio" in result.stdout
        assert "--no-audio" in result.stdout

    def test_audio_autoplay_flags_in_help(self):
        """--audio-autoplay and --no-audio-autoplay should appear in help."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "--audio-autoplay" in result.stdout
        assert "--no-audio-autoplay" in result.stdout

    def test_mutually_exclusive_images_flags(self):
        """--images and --no-images should be mutually exclusive."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "--images", "--no-images"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # argparse should reject mutually exclusive flags
        assert result.returncode != 0
        assert "not allowed" in result.stderr.lower() or "mutually exclusive" in result.stderr.lower()

    def test_mutually_exclusive_audio_flags(self):
        """--audio and --no-audio should be mutually exclusive."""
        result = subprocess.run(
            [sys.executable, "-m", "clanki", "--audio", "--no-audio"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # argparse should reject mutually exclusive flags
        assert result.returncode != 0
        assert "not allowed" in result.stderr.lower() or "mutually exclusive" in result.stderr.lower()

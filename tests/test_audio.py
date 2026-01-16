"""Tests for audio.py - Audio playback support."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clanki.audio import (
    AUDIO_ICON,
    AudioPlaceholder,
    _check_afplay_available,
    is_audio_playback_available,
    parse_audio_placeholders,
    play_audio_by_index,
    play_audio_files,
    play_audio_for_side,
    reset_audio_cache,
    resolve_audio_files,
    substitute_audio_icons,
)


def setup_function():
    """Reset cache before each test."""
    reset_audio_cache()


def teardown_function():
    """Reset cache after each test."""
    reset_audio_cache()


class TestParseAudioPlaceholders:
    """Tests for parse_audio_placeholders function."""

    def test_empty_string(self):
        """Empty string should return empty list."""
        result = parse_audio_placeholders("")
        assert result == []

    def test_no_placeholders(self):
        """Text without placeholders should return empty list."""
        result = parse_audio_placeholders("Hello world, no audio here.")
        assert result == []

    def test_single_index_placeholder(self):
        """Single index placeholder should be found."""
        result = parse_audio_placeholders("Here is [audio: 0] the sound.")
        assert len(result) == 1
        assert result[0].value == "0"
        assert result[0].is_index is True
        assert result[0].index == 0

    def test_single_filename_placeholder(self):
        """Single filename placeholder should be found."""
        result = parse_audio_placeholders("Here is [audio: sound.mp3] the sound.")
        assert len(result) == 1
        assert result[0].value == "sound.mp3"
        assert result[0].is_index is False
        assert result[0].index is None

    def test_multiple_placeholders(self):
        """Multiple placeholders should all be found."""
        text = "[audio: 0] text [audio: word.mp3]"
        result = parse_audio_placeholders(text)
        assert len(result) == 2
        assert result[0].value == "0"
        assert result[1].value == "word.mp3"

    def test_placeholder_with_spaces(self):
        """Placeholder with extra spaces should be parsed."""
        result = parse_audio_placeholders("[audio:   spacy.mp3  ]")
        assert len(result) == 1
        assert result[0].value == "spacy.mp3"

    def test_positions_are_correct(self):
        """Placeholder positions should match the text."""
        text = "before [audio: test.mp3] after"
        result = parse_audio_placeholders(text)
        assert len(result) == 1
        assert text[result[0].start : result[0].end] == "[audio: test.mp3]"


class TestSubstituteAudioIcons:
    """Tests for substitute_audio_icons function."""

    def test_no_placeholders(self):
        """Text without placeholders should be unchanged."""
        text = "Hello world"
        result = substitute_audio_icons(text)
        assert result == text

    def test_single_placeholder(self):
        """Single placeholder should show key to press."""
        text = "Here is [audio: sound.mp3] the sound."
        result = substitute_audio_icons(text)
        # First audio maps to key 5
        assert result == f"Here is {AUDIO_ICON}[5] the sound."

    def test_multiple_placeholders(self):
        """Multiple placeholders should show sequential keys 5-9."""
        text = "[audio: 0] and [audio: 1] and [audio: word.mp3]"
        result = substitute_audio_icons(text)
        # Keys 5, 6, 7 for audio 1, 2, 3
        assert result == f"{AUDIO_ICON}[5] and {AUDIO_ICON}[6] and {AUDIO_ICON}[7]"

    def test_more_than_five_placeholders(self):
        """Audio beyond 5 should show plain icon (no key binding)."""
        text = "[audio: 1] [audio: 2] [audio: 3] [audio: 4] [audio: 5] [audio: 6]"
        result = substitute_audio_icons(text)
        # First 5 have keys 5-9, 6th has no key
        assert result == f"{AUDIO_ICON}[5] {AUDIO_ICON}[6] {AUDIO_ICON}[7] {AUDIO_ICON}[8] {AUDIO_ICON}[9] {AUDIO_ICON}"

    def test_icon_value(self):
        """AUDIO_ICON should be a speaker emoji."""
        assert AUDIO_ICON == "🔊"


class TestResolveAudioFiles:
    """Tests for resolve_audio_files function."""

    def test_no_media_dir(self):
        """Without media dir, should return empty list."""
        result = resolve_audio_files("[audio: 0]", ["sound.mp3"], None)
        assert result == []

    def test_no_placeholders(self):
        """Text without placeholders should return empty list."""
        with patch("pathlib.Path.exists", return_value=True):
            result = resolve_audio_files("Hello", ["sound.mp3"], Path("/media"))
        assert result == []

    def test_index_placeholder_resolves(self, tmp_path):
        """Index placeholder should resolve to file from audio_files list."""
        audio_file = tmp_path / "sound.mp3"
        audio_file.touch()

        result = resolve_audio_files("[audio: 0]", ["sound.mp3"], tmp_path)
        assert len(result) == 1
        assert result[0] == audio_file

    def test_index_out_of_range(self, tmp_path):
        """Out of range index should be skipped."""
        result = resolve_audio_files("[audio: 5]", ["sound.mp3"], tmp_path)
        assert result == []

    def test_filename_placeholder_resolves(self, tmp_path):
        """Filename placeholder should resolve directly."""
        audio_file = tmp_path / "word.mp3"
        audio_file.touch()

        result = resolve_audio_files("[audio: word.mp3]", [], tmp_path)
        assert len(result) == 1
        assert result[0] == audio_file

    def test_missing_file_skipped(self, tmp_path):
        """Missing files should be skipped."""
        result = resolve_audio_files("[audio: missing.mp3]", [], tmp_path)
        assert result == []

    def test_multiple_files(self, tmp_path):
        """Multiple placeholders should resolve to multiple files."""
        file1 = tmp_path / "a.mp3"
        file2 = tmp_path / "b.mp3"
        file1.touch()
        file2.touch()

        result = resolve_audio_files(
            "[audio: 0] [audio: b.mp3]", ["a.mp3"], tmp_path
        )
        assert len(result) == 2
        assert result[0] == file1
        assert result[1] == file2


class TestAfplayAvailability:
    """Tests for afplay availability checking."""

    def test_available_on_macos(self):
        """afplay should be detected on macOS when available."""
        reset_audio_cache()

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/afplay"),
        ):
            result = _check_afplay_available()
            assert result is True

        reset_audio_cache()

    def test_unavailable_on_non_macos(self):
        """afplay should not be available on non-macOS."""
        reset_audio_cache()

        with patch("sys.platform", "linux"):
            result = _check_afplay_available()
            assert result is False

        reset_audio_cache()

    def test_unavailable_when_not_found(self):
        """afplay should not be available when not in PATH."""
        reset_audio_cache()

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value=None),
        ):
            result = _check_afplay_available()
            assert result is False

        reset_audio_cache()

    def test_is_audio_playback_available_delegates(self):
        """is_audio_playback_available should delegate to _check_afplay_available."""
        reset_audio_cache()

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/afplay"),
        ):
            result = is_audio_playback_available()
            assert result is True

        reset_audio_cache()


class TestPlayAudioFiles:
    """Tests for play_audio_files function."""

    def test_empty_list(self):
        """Empty file list should return True."""
        result = play_audio_files([])
        assert result is True

    def test_unavailable_returns_false(self, tmp_path):
        """Should return False when afplay unavailable."""
        reset_audio_cache()

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with patch("sys.platform", "linux"):
            errors = []
            result = play_audio_files([audio_file], on_error=errors.append)
            assert result is False
            assert len(errors) == 1

        reset_audio_cache()

    def test_plays_existing_files(self, tmp_path):
        """Should play existing files when afplay available."""
        reset_audio_cache()

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/afplay"),
            patch("subprocess.Popen") as mock_popen,
        ):
            mock_popen.return_value = MagicMock()
            result = play_audio_files([audio_file])
            assert result is True
            mock_popen.assert_called_once()

        reset_audio_cache()

    def test_skips_missing_files(self, tmp_path):
        """Should skip files that don't exist."""
        reset_audio_cache()

        missing_file = tmp_path / "missing.mp3"

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/afplay"),
            patch("subprocess.Popen") as mock_popen,
        ):
            # File doesn't exist, so subprocess should not be called
            result = play_audio_files([missing_file])
            # Returns True because no error, just nothing to play
            assert result is True
            # Verify subprocess was never called for missing file
            mock_popen.assert_not_called()

        reset_audio_cache()


class TestPlayAudioForSide:
    """Tests for play_audio_for_side function."""

    def test_no_audio_files(self, tmp_path):
        """Should return True when no audio files to play."""
        result = play_audio_for_side(
            text="Hello",
            audio_files=[],
            media_dir=tmp_path,
        )
        assert result is True

    def test_no_media_dir(self):
        """Should return True when no media dir."""
        result = play_audio_for_side(
            text="[audio: 0]",
            audio_files=["test.mp3"],
            media_dir=None,
        )
        assert result is True

    def test_plays_resolved_files(self, tmp_path):
        """Should play resolved audio files."""
        reset_audio_cache()

        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/afplay"),
            patch("subprocess.Popen") as mock_popen,
        ):
            mock_popen.return_value = MagicMock()
            result = play_audio_for_side(
                text="[audio: 0]",
                audio_files=["test.mp3"],
                media_dir=tmp_path,
            )
            assert result is True
            mock_popen.assert_called_once()

        reset_audio_cache()


class TestAudioPlaceholderDataclass:
    """Tests for AudioPlaceholder dataclass."""

    def test_index_placeholder(self):
        """Index placeholder should have correct properties."""
        placeholder = AudioPlaceholder(value="0", start=0, end=10)
        assert placeholder.is_index is True
        assert placeholder.index == 0

    def test_filename_placeholder(self):
        """Filename placeholder should have correct properties."""
        placeholder = AudioPlaceholder(value="sound.mp3", start=0, end=20)
        assert placeholder.is_index is False
        assert placeholder.index is None

    def test_multi_digit_index(self):
        """Multi-digit index should work."""
        placeholder = AudioPlaceholder(value="123", start=0, end=10)
        assert placeholder.is_index is True
        assert placeholder.index == 123


class TestPlayAudioByIndex:
    """Tests for play_audio_by_index function."""

    def test_no_audio_files(self, tmp_path):
        """Should return False when no audio files."""
        errors = []
        result = play_audio_by_index(
            text="Hello",
            audio_files=[],
            media_dir=tmp_path,
            index=1,
            on_error=errors.append,
        )
        assert result is False
        assert len(errors) == 1
        assert "No audio files" in errors[0]

    def test_invalid_index_too_high(self, tmp_path):
        """Should return False for index beyond available files."""
        audio_file = tmp_path / "test.mp3"
        audio_file.touch()

        errors = []
        result = play_audio_by_index(
            text="[audio: 0]",
            audio_files=["test.mp3"],
            media_dir=tmp_path,
            index=5,  # Only 1 file available
            on_error=errors.append,
        )
        assert result is False
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_valid_index_plays_file(self, tmp_path):
        """Valid index should play the correct file."""
        reset_audio_cache()

        file1 = tmp_path / "a.mp3"
        file2 = tmp_path / "b.mp3"
        file1.touch()
        file2.touch()

        with (
            patch("sys.platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/afplay"),
            patch("subprocess.Popen") as mock_popen,
        ):
            mock_popen.return_value = MagicMock()
            result = play_audio_by_index(
                text="[audio: 0] [audio: 1]",
                audio_files=["a.mp3", "b.mp3"],
                media_dir=tmp_path,
                index=2,  # Should play b.mp3
            )
            assert result is True
            mock_popen.assert_called_once()
            # Verify the command contains b.mp3
            call_args = mock_popen.call_args[0][0]
            assert "b.mp3" in call_args
            assert "a.mp3" not in call_args

        reset_audio_cache()

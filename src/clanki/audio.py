"""Audio playback support for Clanki.

This module provides:
- Audio placeholder parsing and icon substitution
- macOS audio playback via afplay
- Playback availability detection
"""

from __future__ import annotations

import os
import re
import signal
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Audio icon used to replace [audio: ...] placeholders
# Using Unicode speaker emoji for better visual representation
AUDIO_ICON = "🔊"

# Pattern to match [audio: N] (index) or [audio: filename] placeholders
AUDIO_PLACEHOLDER_PATTERN = re.compile(r"\[audio:\s*([^\]]+)\]")


@dataclass
class AudioPlaceholder:
    """Represents an audio placeholder found in card text."""

    value: str  # Either index (as string) or filename
    start: int
    end: int

    @property
    def is_index(self) -> bool:
        """Check if this placeholder uses an index reference."""
        return self.value.isdigit()

    @property
    def index(self) -> int | None:
        """Get the index if this is an index placeholder."""
        return int(self.value) if self.is_index else None


def parse_audio_placeholders(text: str) -> list[AudioPlaceholder]:
    """Parse text for [audio: ...] placeholders.

    Args:
        text: Card text content.

    Returns:
        List of AudioPlaceholder objects with value and position.
    """
    placeholders = []
    for match in AUDIO_PLACEHOLDER_PATTERN.finditer(text):
        placeholders.append(
            AudioPlaceholder(
                value=match.group(1).strip(),
                start=match.start(),
                end=match.end(),
            )
        )
    return placeholders


def substitute_audio_icons(text: str) -> str:
    """Replace [audio: ...] placeholders with audio icons showing key to press.

    Args:
        text: Card text containing audio placeholders.

    Returns:
        Text with placeholders replaced by 🔊[5], 🔊[6], etc.
        Keys 5-9 map to audio 1-5.
    """
    counter = [0]  # Use list to allow mutation in nested function

    def replace_with_key(match: re.Match[str]) -> str:
        counter[0] += 1
        # Keys 5-9 play audio 1-5
        key = counter[0] + 4
        if key <= 9:
            return f"{AUDIO_ICON}[{key}]"
        # For audio 6+, just show the icon (no key binding)
        return AUDIO_ICON

    return AUDIO_PLACEHOLDER_PATTERN.sub(replace_with_key, text)


def resolve_audio_files(
    text: str,
    audio_files: list[str],
    media_dir: Path | None,
) -> list[Path]:
    """Resolve audio placeholders to file paths.

    Handles both index-based [audio: N] and filename-based [audio: file.mp3]
    placeholders. Index N refers to the Nth audio tag in the audio_files list.

    Args:
        text: Card text containing audio placeholders.
        audio_files: List of audio filenames from CardView (question_audio or answer_audio).
        media_dir: Path to Anki media directory.

    Returns:
        List of resolved file paths (only includes existing files).
    """
    if media_dir is None:
        return []

    placeholders = parse_audio_placeholders(text)
    resolved: list[Path] = []

    for placeholder in placeholders:
        filepath: Path | None = None

        if placeholder.is_index:
            # Index-based: [audio: 0] refers to audio_files[0]
            idx = placeholder.index
            if idx is not None and 0 <= idx < len(audio_files):
                filepath = media_dir / audio_files[idx]
        else:
            # Filename-based: [audio: sound.mp3]
            filepath = media_dir / placeholder.value

        if filepath is not None and filepath.exists():
            resolved.append(filepath)

    return resolved


# Module-level cache for afplay availability
_afplay_available: bool | None = None


def _check_afplay_available() -> bool:
    """Check if afplay binary is available (macOS only)."""
    global _afplay_available
    if _afplay_available is not None:
        return _afplay_available

    # afplay is only available on macOS
    if sys.platform != "darwin":
        _afplay_available = False
        return False

    _afplay_available = shutil.which("afplay") is not None
    return _afplay_available


def is_audio_playback_available() -> bool:
    """Check if audio playback is available.

    Returns:
        True if afplay is available on macOS.
    """
    return _check_afplay_available()


def get_audio_unavailable_message() -> str:
    """Get a user-friendly message explaining why audio is unavailable.

    Returns:
        Message explaining the situation.
    """
    if sys.platform != "darwin":
        return "Audio playback is only supported on macOS"
    return "afplay not found (should be included with macOS)"


# Track running audio process for stopping (only one at a time)
_running_process: subprocess.Popen[bytes] | None = None


def stop_audio() -> None:
    """Stop any currently playing audio.

    Uses process group kill to ensure all child processes (afplay) are terminated.
    """
    global _running_process
    if _running_process is None:
        return

    try:
        # Kill the entire process group to stop shell and all child processes
        os.killpg(os.getpgid(_running_process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        # Process already terminated
        pass

    _running_process = None


def play_audio_files(
    files: list[Path],
    on_error: Callable[[str], None] | None = None,
) -> bool:
    """Play a list of audio files sequentially (non-blocking).

    Uses afplay on macOS. Each file plays in sequence via subprocess.
    Calling this function while audio is playing will stop the current
    audio and start the new playback (interruptible).

    Args:
        files: List of audio file paths to play.
        on_error: Optional callback for error messages.

    Returns:
        True if playback started successfully, False otherwise.
    """
    global _running_process

    if not files:
        return True

    if not _check_afplay_available():
        if on_error:
            on_error(get_audio_unavailable_message())
        return False

    # Stop any currently playing audio (makes playback interruptible)
    stop_audio()

    # Filter to existing files only
    existing_files = [f for f in files if f.exists()]
    if not existing_files:
        return True

    # For simplicity, we play files sequentially using a shell command
    # This is non-blocking as we don't wait for the process
    try:
        # Build command to play all files sequentially
        # Using shell to chain commands: afplay f1 && afplay f2 && ...
        cmds = [f'afplay "{f}"' for f in existing_files]
        full_cmd = " && ".join(cmds)

        # Use start_new_session=True to create a new process group
        # This allows us to kill the shell and all child processes together
        proc = subprocess.Popen(
            full_cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _running_process = proc
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        if on_error:
            on_error(f"Failed to play audio: {exc}")
        return False


def play_audio_for_side(
    text: str,
    audio_files: list[str],
    media_dir: Path | None,
    on_error: Callable[[str], None] | None = None,
) -> bool:
    """Convenience function to play all audio for a card side.

    Args:
        text: Rendered card text (may contain audio placeholders).
        audio_files: Audio filenames from CardView for this side.
        media_dir: Path to Anki media directory.
        on_error: Optional callback for error messages.

    Returns:
        True if playback started (or no audio to play), False on error.
    """
    resolved = resolve_audio_files(text, audio_files, media_dir)
    if not resolved:
        # No audio files to play - not an error
        return True
    return play_audio_files(resolved, on_error)


def play_audio_by_index(
    text: str,
    audio_files: list[str],
    media_dir: Path | None,
    index: int,
    on_error: Callable[[str], None] | None = None,
) -> bool:
    """Play a specific audio file by its display index (1-based).

    Args:
        text: Rendered card text (may contain audio placeholders).
        audio_files: Audio filenames from CardView for this side.
        media_dir: Path to Anki media directory.
        index: 1-based index of the audio to play (matches 🔊1, 🔊2, etc.).
        on_error: Optional callback for error messages.

    Returns:
        True if playback started, False on error or invalid index.
    """
    resolved = resolve_audio_files(text, audio_files, media_dir)
    if not resolved:
        if on_error:
            on_error("No audio files available")
        return False

    # Convert 1-based display index to 0-based list index
    zero_index = index - 1
    if zero_index < 0 or zero_index >= len(resolved):
        if on_error:
            on_error(f"Audio {index} not found (have {len(resolved)} audio files)")
        return False

    return play_audio_files([resolved[zero_index]], on_error)


def reset_audio_cache() -> None:
    """Reset the module-level cache (useful for testing)."""
    global _afplay_available, _running_process
    _afplay_available = None
    _running_process = None

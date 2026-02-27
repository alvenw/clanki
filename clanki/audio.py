"""Audio playback support for Clanki.

This module provides:
- Audio placeholder parsing and icon substitution
- Cross-platform audio playback via system backends
- Playback availability detection
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
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


@dataclass(frozen=True)
class _AudioBackend:
    """Represents a supported audio playback backend."""

    name: str
    binary: str
    base_args: tuple[str, ...]


# Module-level cache for backend availability
_backend_checked = False
_audio_backend: _AudioBackend | None = None


def _backend_candidates() -> tuple[_AudioBackend, ...]:
    """Return backend candidates in preferred order for this platform."""
    afplay = _AudioBackend(
        name="afplay",
        binary="afplay",
        base_args=("afplay",),
    )
    ffplay = _AudioBackend(
        name="ffplay",
        binary="ffplay",
        base_args=("ffplay", "-nodisp", "-autoexit", "-nostdin", "-loglevel", "quiet"),
    )

    if sys.platform == "darwin":
        return (afplay, ffplay)
    return (ffplay,)


def _detect_audio_backend() -> _AudioBackend | None:
    """Detect and cache the first available supported backend."""
    global _backend_checked, _audio_backend
    if _backend_checked:
        return _audio_backend

    for backend in _backend_candidates():
        if shutil.which(backend.binary) is not None:
            _audio_backend = backend
            _backend_checked = True
            return backend

    _audio_backend = None
    _backend_checked = True
    return None


def is_audio_playback_available() -> bool:
    """Check if audio playback is available.

    Returns:
        True if a supported backend is available.
    """
    return _detect_audio_backend() is not None


def get_audio_unavailable_message() -> str:
    """Get a user-friendly message explaining why audio is unavailable.

    Returns:
        Message explaining the situation.
    """
    if _detect_audio_backend() is not None:
        return ""
    if sys.platform == "darwin":
        return "No supported audio player found (need afplay or ffplay)"
    if sys.platform == "win32":
        return "No supported audio player found (install ffmpeg and add ffplay to PATH)"
    if sys.platform.startswith("linux"):
        return "No supported audio player found (install ffmpeg for ffplay)"
    return "No supported audio player found (need ffplay on PATH)"


# Track running audio process for stopping (only one at a time)
_running_process: subprocess.Popen[bytes] | None = None
_playback_thread: threading.Thread | None = None
_playback_stop_event: threading.Event | None = None
_process_lock = threading.Lock()


def _build_play_command(backend: _AudioBackend, audio_file: Path) -> list[str]:
    """Build the command to play one audio file with the selected backend."""
    return [*backend.base_args, str(audio_file)]


def _emit_on_error(on_error: Callable[[str], None] | None, message: str) -> None:
    """Best-effort error callback invocation."""
    if on_error is None:
        return
    try:
        on_error(message)
    except Exception:
        # Avoid letting callback errors break playback worker cleanup.
        pass


def stop_audio() -> None:
    """Stop any currently playing audio."""
    global _running_process, _playback_stop_event, _playback_thread

    with _process_lock:
        stop_event = _playback_stop_event
        if stop_event is not None:
            stop_event.set()
        proc = _running_process
        thread = _playback_thread

    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
        except OSError:
            pass

    if thread is not None and thread.is_alive():
        thread.join(timeout=0.2)

    with _process_lock:
        if _running_process is proc:
            _running_process = None
        if _playback_thread is thread and (thread is None or not thread.is_alive()):
            _playback_thread = None
            _playback_stop_event = None


def play_audio_files(
    files: list[Path],
    on_error: Callable[[str], None] | None = None,
) -> bool:
    """Play a list of audio files sequentially (non-blocking).

    Uses the selected backend (afplay/ffplay) via subprocess.
    Calling this function while audio is playing will stop the current
    audio and start the new playback (interruptible).

    Args:
        files: List of audio file paths to play.
        on_error: Optional callback for error messages.

    Returns:
        True if playback started successfully, False otherwise.
    """
    global _playback_stop_event, _playback_thread

    if not files:
        return True

    backend = _detect_audio_backend()
    if backend is None:
        _emit_on_error(on_error, get_audio_unavailable_message())
        return False

    # Stop any currently playing audio (interruptible behavior)
    stop_audio()

    # Filter to existing files only
    existing_files = [f for f in files if f.exists()]
    if not existing_files:
        return True

    stop_event = threading.Event()
    worker_thread: threading.Thread | None = None

    def _worker() -> None:
        global _running_process, _playback_stop_event, _playback_thread
        try:
            for audio_file in existing_files:
                if stop_event.is_set():
                    break

                command = _build_play_command(backend, audio_file)
                launch_error: Exception | None = None
                proc: subprocess.Popen[bytes] | None = None
                with _process_lock:
                    # Re-check stop/ownership immediately before launching.
                    if stop_event.is_set() or _playback_thread is not worker_thread:
                        break
                    try:
                        proc = subprocess.Popen(
                            command,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except (OSError, subprocess.SubprocessError) as exc:
                        launch_error = exc
                    else:
                        _running_process = proc

                if launch_error is not None:
                    _emit_on_error(
                        on_error,
                        f"Failed to start audio playback ({backend.binary}): {launch_error}",
                    )
                    break

                assert proc is not None

                try:
                    return_code = proc.wait()
                    if return_code != 0 and not stop_event.is_set():
                        _emit_on_error(
                            on_error,
                            f"Audio playback exited with status {return_code} ({backend.binary})",
                        )
                        break
                finally:
                    with _process_lock:
                        if _running_process is proc:
                            _running_process = None
        finally:
            with _process_lock:
                if _playback_thread is worker_thread:
                    _running_process = None
                    _playback_thread = None
                    _playback_stop_event = None

    thread = threading.Thread(
        target=_worker,
        name="clanki-audio",
        daemon=True,
    )
    worker_thread = thread
    with _process_lock:
        _playback_thread = thread
        _playback_stop_event = stop_event
    try:
        thread.start()
    except RuntimeError as exc:
        with _process_lock:
            if _playback_thread is thread:
                _playback_thread = None
                _playback_stop_event = None
        _emit_on_error(on_error, f"Failed to start audio playback: {exc}")
        return False
    return True


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
    global _backend_checked, _audio_backend, _running_process, _playback_stop_event, _playback_thread
    stop_audio()
    _backend_checked = False
    _audio_backend = None
    with _process_lock:
        _running_process = None
        _playback_stop_event = None
    _playback_thread = None

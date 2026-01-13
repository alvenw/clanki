"""TUI-specific rendering helpers for card content.

This module parses card text for [image: filename] placeholders and
renders them using chafa when available and enabled.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.console import RenderableType
from rich.text import Text

# Pattern to match [image: filename] placeholders
IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[image:\s*([^\]]+)\]")


@dataclass
class ImagePlaceholder:
    """Represents an image placeholder found in card text."""

    filename: str
    start: int
    end: int


def parse_image_placeholders(text: str) -> list[ImagePlaceholder]:
    """Parse text for [image: filename] placeholders.

    Args:
        text: Card text content.

    Returns:
        List of ImagePlaceholder objects with filename and position.
    """
    placeholders = []
    for match in IMAGE_PLACEHOLDER_PATTERN.finditer(text):
        placeholders.append(
            ImagePlaceholder(
                filename=match.group(1).strip(),
                start=match.start(),
                end=match.end(),
            )
        )
    return placeholders


_chafa_available: bool | None = None


def _check_chafa_available() -> bool:
    """Check if chafa binary is available in PATH."""
    global _chafa_available
    if _chafa_available is not None:
        return _chafa_available

    _chafa_available = shutil.which("chafa") is not None
    return _chafa_available


def is_image_support_available() -> bool:
    """Public API to check if image rendering is available.

    Returns:
        True if chafa is installed and can render images.
    """
    return _check_chafa_available()


def _render_image_to_string(
    image_path: Path,
    max_width: int | None = None,
    max_height: int | None = None,
) -> str | None:
    """Render an image to text using chafa.

    Uses block characters with colors for good visual quality.

    Args:
        image_path: Path to the image file.
        max_width: Maximum width in terminal cells.
        max_height: Maximum height in terminal cells.

    Returns:
        ANSI-colored text representation of the image, or None on failure.
    """
    if not _check_chafa_available():
        return None

    if not image_path.exists():
        return None

    try:
        # Build chafa command with block symbols and colors
        cmd = ["chafa"]
        cmd.extend(["--format", "symbols"])
        cmd.extend(["--symbols", "block"])

        # Set size constraints
        if max_width is not None and max_height is not None:
            cmd.extend(["--size", f"{max_width}x{max_height}"])
        elif max_width is not None:
            cmd.extend(["--size", f"{max_width}x"])
        elif max_height is not None:
            cmd.extend(["--size", f"x{max_height}"])

        # Add image path
        cmd.append(str(image_path))

        # Run chafa and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return None

        output = result.stdout
        if not output or not output.strip():
            return None

        return output.rstrip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return None


def render_content_with_images(
    text: str,
    media_dir: Path | None,
    images_enabled: bool,
    max_width: int | None = None,
    max_height: int | None = None,
) -> list[RenderableType]:
    """Render card content, replacing image placeholders with actual images.

    Args:
        text: Card text content with [image: filename] placeholders.
        media_dir: Path to Anki media directory.
        images_enabled: Whether to attempt image rendering.
        max_width: Maximum width for images in terminal cells.
        max_height: Maximum height for images in terminal cells.

    Returns:
        List of Rich renderables (Text objects).
        Falls back to placeholder text on any failure.
    """
    if not text:
        return []

    placeholders = parse_image_placeholders(text)

    # If no placeholders or images disabled, return text as-is
    if not placeholders or not images_enabled:
        return [Text(text)]

    # Check if chafa is available
    if not _check_chafa_available():
        return [Text(text)]

    # Build list of renderables
    renderables: list[RenderableType] = []
    last_end = 0

    for placeholder in placeholders:
        # Add text before this placeholder
        if placeholder.start > last_end:
            text_before = text[last_end : placeholder.start]
            if text_before.strip():
                renderables.append(Text(text_before.rstrip()))

        # Try to render the image to a string
        image_rendered = False
        if media_dir is not None:
            image_path = media_dir / placeholder.filename
            img_str = _render_image_to_string(image_path, max_width, max_height)
            if img_str is not None:
                # Use Text.from_ansi to properly handle ANSI escape sequences
                renderables.append(Text.from_ansi(img_str))
                image_rendered = True

        # Fall back to placeholder text if image rendering failed
        if not image_rendered:
            renderables.append(Text(f"[image: {placeholder.filename}]"))

        last_end = placeholder.end

    # Add remaining text after last placeholder
    if last_end < len(text):
        text_after = text[last_end:]
        if text_after.strip():
            renderables.append(Text(text_after.lstrip()))

    return renderables if renderables else [Text(text)]

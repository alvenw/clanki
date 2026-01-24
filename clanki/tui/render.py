"""TUI-specific rendering helpers for card content.

This module parses card text for [image: filename] placeholders and
renders them using textual-image when available and enabled. It also handles
audio placeholder icon substitution and styled text rendering.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import RenderableType
from rich.style import Style
from rich.text import Text
from textual_image.renderable import (
    SixelImage,
    TGPImage,
    UnicodeImage,
)

if TYPE_CHECKING:
    from textual_image.renderable import Image

from ..audio import substitute_audio_icons
from ..render import RenderMode, StyledSegment, render_html_to_styled_segments


def _detect_image_class() -> type:
    """Detect the best image class based on terminal type.

    textual-image's auto-detection doesn't always work correctly,
    so we detect the terminal ourselves and use the appropriate class.

    Returns:
        The Image class to use (TGPImage, SixelImage, or UnicodeImage).
    """
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()
    lc_terminal = os.environ.get("LC_TERMINAL", "").lower()

    # Kitty and Ghostty support the Kitty graphics protocol (TGP)
    if "kitty" in term or "kitty" in term_program:
        return TGPImage
    if "ghostty" in term or "ghostty" in term_program:
        return TGPImage

    # iTerm2 and WezTerm support Sixel
    if "iterm" in term_program or "iterm" in lc_terminal:
        return SixelImage
    if "wezterm" in term_program:
        return SixelImage

    # Terminals that commonly support Sixel
    if any(x in term for x in ["xterm", "mlterm", "contour", "foot"]):
        return SixelImage

    # Fallback to Unicode half-block characters
    return UnicodeImage


# Cache the detected image class at module load time
_ImageClass: type = _detect_image_class()

# Log the detected protocol for debugging
import logging as _logging

_logger = _logging.getLogger(__name__)
_logger.debug("Detected terminal image protocol: %s", _ImageClass.__module__.split(".")[-1])

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


def is_image_support_available() -> bool:
    """Public API to check if image rendering is available.

    Returns:
        True - textual-image is always available as a dependency.
    """
    return True


def _create_image_renderable(
    image_path: Path,
    max_width: int | None = None,
    max_height: int | None = None,
) -> "Image | None":
    """Create a textual-image Image renderable for an image file.

    Uses terminal-specific image class detected at module load time:
    - TGPImage for Kitty/Ghostty (Kitty graphics protocol)
    - SixelImage for iTerm2/WezTerm/xterm
    - UnicodeImage as fallback

    Args:
        image_path: Path to the image file.
        max_width: Maximum width in terminal cells.
        max_height: Maximum height in terminal cells.

    Returns:
        Image renderable, or None if the file doesn't exist.
    """
    if not image_path.exists():
        return None

    try:
        # Use the terminal-specific image class
        return _ImageClass(image_path, width=max_width, height=max_height)
    except Exception:
        return None


def render_content_with_images(
    text: str,
    media_dir: Path | None,
    images_enabled: bool,
    max_width: int | None = None,
    max_height: int | None = None,
) -> list[RenderableType]:
    """Render card content, replacing image placeholders with actual images.

    Also substitutes audio placeholders with an audio icon.

    Args:
        text: Card text content with [image: filename] and [audio: ...] placeholders.
        media_dir: Path to Anki media directory.
        images_enabled: Whether to attempt image rendering.
        max_width: Maximum width for images in terminal cells.
        max_height: Maximum height for images in terminal cells.

    Returns:
        List of Rich renderables (Text objects and Image renderables).
        Falls back to placeholder text on any failure.
    """
    if not text:
        return []

    # First, substitute audio placeholders with icons
    text = substitute_audio_icons(text)

    placeholders = parse_image_placeholders(text)

    # If no placeholders or images disabled, return text as-is
    if not placeholders or not images_enabled:
        return [Text(text)]

    # Build list of renderables, preserving whitespace
    renderables: list[RenderableType] = []
    last_end = 0

    for placeholder in placeholders:
        # Add text before this placeholder (preserve whitespace)
        if placeholder.start > last_end:
            text_before = text[last_end : placeholder.start]
            if text_before:
                renderables.append(Text(text_before))

        # Try to render the image
        image_rendered = False
        if media_dir is not None:
            image_path = media_dir / placeholder.filename
            img = _create_image_renderable(image_path, max_width, max_height)
            if img is not None:
                renderables.append(img)
                image_rendered = True

        # Fall back to placeholder text if image rendering failed
        if not image_rendered:
            renderables.append(Text(f"[image: {placeholder.filename}]"))

        last_end = placeholder.end

    # Add remaining text after last placeholder (preserve whitespace)
    if last_end < len(text):
        text_after = text[last_end:]
        if text_after:
            renderables.append(Text(text_after))

    return renderables if renderables else [Text(text)]


def _segment_to_rich_style(segment: StyledSegment) -> Style:
    """Convert a StyledSegment's style to a Rich Style object."""
    style_kwargs: dict[str, object] = {}

    if segment.style.bold:
        style_kwargs["bold"] = True

    if segment.style.italic:
        style_kwargs["italic"] = True

    if segment.style.underline:
        style_kwargs["underline"] = True

    if segment.style.strikethrough:
        style_kwargs["strike"] = True

    if segment.style.color:
        style_kwargs["color"] = segment.style.color

    if segment.style.bgcolor:
        style_kwargs["bgcolor"] = segment.style.bgcolor

    # Special cloze styling: bold + reverse for visibility
    if segment.style.is_cloze:
        style_kwargs["bold"] = True
        style_kwargs["reverse"] = True

    return Style(**style_kwargs) if style_kwargs else Style()


def segments_to_rich_text(segments: list[StyledSegment]) -> Text:
    """Convert a list of StyledSegments to a Rich Text object.

    Args:
        segments: List of StyledSegment objects from render_html_to_styled_segments.

    Returns:
        Rich Text object with appropriate styling applied.
    """
    text = Text()
    for segment in segments:
        style = _segment_to_rich_style(segment)
        text.append(segment.text, style=style)
    return text


def render_styled_content_with_images(
    html: str,
    media_dir: Path | None,
    images_enabled: bool,
    mode: RenderMode = RenderMode.ANSWER,
    max_width: int | None = None,
    max_height: int | None = None,
) -> list[RenderableType]:
    """Render HTML card content with styling and image support.

    This is the main entry point for TUI rendering with full styling support.

    Args:
        html: HTML content from Anki card rendering.
        media_dir: Path to Anki media directory.
        images_enabled: Whether to attempt image rendering.
        mode: Render mode for cloze handling (QUESTION shows [...], ANSWER shows styled text).
        max_width: Maximum width for images in terminal cells.
        max_height: Maximum height for images in terminal cells.

    Returns:
        List of Rich renderables (Text objects, possibly with Image renderables).
    """
    if not html:
        return []

    # Get styled segments
    segments = render_html_to_styled_segments(html, media_dir, mode)

    if not segments:
        return []

    # Convert segments to Rich Text
    styled_text = segments_to_rich_text(segments)

    # Apply audio icon substitution to the plain text representation
    plain_text = str(styled_text)
    plain_with_audio = substitute_audio_icons(plain_text)

    # If audio icons were substituted, we need to rebuild the text
    # For simplicity, if there are audio placeholders, apply substitution
    if plain_with_audio != plain_text:
        # Rebuild by applying audio substitution to each segment's text
        new_segments: list[StyledSegment] = []
        for seg in segments:
            new_text = substitute_audio_icons(seg.text)
            new_segments.append(StyledSegment(text=new_text, style=seg.style))
        styled_text = segments_to_rich_text(new_segments)
        plain_text = str(styled_text)

    # Parse image placeholders from the text
    placeholders = parse_image_placeholders(plain_text)

    # If no image placeholders or images disabled, return styled text as-is
    if not placeholders or not images_enabled:
        return [styled_text]

    # Build list of renderables, replacing image placeholders with rendered images
    renderables: list[RenderableType] = []
    last_end = 0

    # We need to slice the Rich Text object at placeholder positions
    for placeholder in placeholders:
        # Add styled text before this placeholder
        if placeholder.start > last_end:
            text_slice = styled_text[last_end:placeholder.start]
            if len(text_slice) > 0:
                renderables.append(text_slice)

        # Try to render the image
        image_rendered = False
        if media_dir is not None:
            image_path = media_dir / placeholder.filename
            img = _create_image_renderable(image_path, max_width, max_height)
            if img is not None:
                renderables.append(img)
                image_rendered = True

        # Fall back to placeholder text if image rendering failed
        if not image_rendered:
            renderables.append(Text(f"[image: {placeholder.filename}]"))

        last_end = placeholder.end

    # Add remaining styled text after last placeholder
    if last_end < len(plain_text):
        text_slice = styled_text[last_end:]
        if len(text_slice) > 0:
            renderables.append(text_slice)

    return renderables if renderables else [styled_text]

"""HTML to terminal text renderer.

This module provides HTML-to-text conversion for Anki card content,
with support for:
- List formatting with indentation and bullets
- Media placeholders (audio, images)
- Block element handling (br, p, div, tr)
- Script/style stripping
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote


class _HTMLToTextRenderer(HTMLParser):
    """HTMLParser-based renderer for terminal output."""

    # Block-level tags that should produce newlines
    BLOCK_TAGS = {"br", "p", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    # Tags whose content should be skipped entirely
    SKIP_TAGS = {"style", "script"}

    def __init__(self, media_dir: str | Path | None = None) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._list_depth = 0
        self._in_list_item = False
        self._media_dir = Path(media_dir) if media_dir else None
        # Ruby/furigana state tracking
        self._in_ruby = False
        self._ruby_base = ""
        self._in_rt = False
        self._rt_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        # List handling
        if tag in {"ul", "ol"}:
            self._list_depth += 1
            return

        if tag == "li":
            self._in_list_item = True
            # Add newline, indentation, and bullet
            indent = "  " * (self._list_depth - 1) if self._list_depth > 0 else ""
            self._chunks.append(f"\n{indent}- ")
            return

        # Ruby/furigana handling
        if tag == "ruby":
            self._in_ruby = True
            self._ruby_base = ""
            self._rt_text = ""
            return

        if tag == "rt":
            self._in_rt = True
            return

        # Image handling
        if tag == "img":
            attrs_dict = dict(attrs)
            src = attrs_dict.get("src", "")
            if src:
                filename = self._extract_filename(src)
                self._chunks.append(f"[image: {filename}]")
            return

        # Block tags produce newlines
        if tag in self.BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if self._skip_depth > 0:
            return

        # Ruby/furigana end handling
        if tag == "rt":
            self._in_rt = False
            return

        if tag == "ruby":
            # Output combined format: base(reading)
            if self._ruby_base and self._rt_text:
                self._chunks.append(f"{self._ruby_base}({self._rt_text})")
            elif self._ruby_base:
                self._chunks.append(self._ruby_base)
            self._in_ruby = False
            self._ruby_base = ""
            self._rt_text = ""
            return

        # List handling
        if tag in {"ul", "ol"}:
            if self._list_depth > 0:
                self._list_depth -= 1
            return

        if tag == "li":
            self._in_list_item = False
            self._chunks.append("\n")
            return

        # Block tags produce trailing newlines
        if tag in {"p", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if not data:
            return

        # Handle ruby/furigana text accumulation
        if self._in_rt:
            self._rt_text += data
            return

        if self._in_ruby:
            self._ruby_base += data
            return

        self._chunks.append(data)

    def _extract_filename(self, src: str) -> str:
        """Extract filename from a src attribute."""
        # URL-decode the path
        decoded = unquote(src)
        # Get basename
        filename = Path(decoded).name
        return filename

    def get_text(self) -> str:
        """Get the rendered text output."""
        return "".join(self._chunks)


def _process_media_tags(text: str) -> str:
    """Process Anki media tags in text.

    Handles:
    - [anki:play:a:N] -> [audio: N]
    - [sound:filename] -> [audio: filename]
    """
    # Handle [anki:play:a:N] format
    text = re.sub(
        r"\[anki:play:[aq]:(\d+)\]",
        r"[audio: \1]",
        text,
    )

    # Handle [sound:filename] format
    text = re.sub(
        r"\[sound:([^\]]+)\]",
        r"[audio: \1]",
        text,
    )

    return text


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace while preserving paragraph breaks and indentation.

    - Collapses multiple spaces into one (preserving leading indent)
    - Collapses 3+ newlines into 2 (paragraph break)
    - Strips trailing whitespace from lines
    """
    # Split into lines
    lines = text.splitlines()

    # Process each line, preserving leading indentation
    cleaned: list[str] = []
    for line in lines:
        # Capture leading whitespace (for list indentation)
        match = re.match(r"^(\s*)", line)
        leading = match.group(1) if match else ""
        # Only preserve leading spaces that look like indentation (multiples of 2)
        # This avoids preserving random whitespace from HTML
        if leading and leading.replace(" ", "") == "":
            # Keep indentation that's a multiple of 2 spaces
            indent_level = len(leading) // 2
            leading = "  " * indent_level
        else:
            leading = ""
        # Collapse internal whitespace
        content = " ".join(line.split())
        if content:
            cleaned.append(leading + content)
        elif cleaned and cleaned[-1] != "":
            # Preserve one empty line for paragraph breaks
            cleaned.append("")

    # Remove trailing empty lines
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    # Remove leading empty lines
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)

    return "\n".join(cleaned)


def render_html_to_text(html: str, media_dir: str | Path | None = None) -> str:
    """Convert HTML to plain text suitable for terminal display.

    Args:
        html: HTML content from Anki card rendering.
        media_dir: Optional path to Anki media directory (from col.media.dir()).
            Currently used for context but filenames are extracted from src attrs.

    Returns:
        Plain text with:
        - List items formatted with "- " bullets and indentation
        - Media placeholders: [image: filename], [audio: filename/index]
        - Block elements converted to newlines
        - Script/style content removed
        - Whitespace normalized
    """
    if not html:
        return ""

    # Parse HTML and extract text
    renderer = _HTMLToTextRenderer(media_dir=media_dir)
    renderer.feed(html)
    text = renderer.get_text()

    # Decode HTML entities
    text = unescape(text)

    # Process media tags (Anki-specific formats)
    text = _process_media_tags(text)

    # Normalize whitespace
    text = _normalize_whitespace(text)

    return text

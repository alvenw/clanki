"""HTML to terminal text renderer.

This module provides HTML-to-text conversion for Anki card content,
with support for:
- List formatting with indentation and bullets
- Media placeholders (audio, images)
- Block element handling (br, p, div, tr)
- Script/style stripping
- Cloze deletion handling (question/answer modes)
- Rich text styling (bold, italic, underline, colors)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote


class RenderMode(Enum):
    """Mode for rendering card content."""

    QUESTION = "question"  # Show cloze as [...] placeholder
    ANSWER = "answer"  # Show cloze content with highlighting


# Pattern to detect cloze span in HTML
CLOZE_PATTERN = re.compile(r'<span[^>]*class="[^"]*cloze[^"]*"[^>]*>', re.IGNORECASE)

# Pattern for raw cloze syntax: {{c1::answer}} or {{c1::answer::hint}}
# The answer and hint may contain HTML tags, so we use a more permissive pattern.
# Groups: (1) cloze number, (2) answer text (may contain HTML), (3) optional hint
# Uses non-greedy matching to handle nested content properly.
RAW_CLOZE_PATTERN = re.compile(
    r'\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}',
    re.DOTALL  # Allow . to match newlines
)


def is_cloze_card(html: str) -> bool:
    """Check if HTML contains cloze deletion markers.

    Args:
        html: HTML content from Anki card rendering.

    Returns:
        True if the HTML contains cloze span markers or raw cloze syntax.
    """
    if not html:
        return False
    return bool(CLOZE_PATTERN.search(html)) or bool(RAW_CLOZE_PATTERN.search(html))


def _process_raw_cloze_in_html(html: str, mode: RenderMode) -> str:
    """Process raw cloze syntax {{cN::answer::hint}} in HTML before parsing.

    This must be called BEFORE HTML parsing because the cloze syntax may contain
    HTML tags that would split the syntax across text nodes.

    Args:
        html: Raw HTML that may contain raw cloze syntax.
        mode: Render mode - QUESTION shows [...] or hint, ANSWER shows answer.

    Returns:
        HTML with raw cloze syntax replaced appropriately.
    """

    def replace_cloze(match: re.Match[str]) -> str:
        # cloze_num = match.group(1)  # Not used currently, but could filter by card
        answer = match.group(2)
        hint = match.group(3)  # May be None

        if mode == RenderMode.QUESTION:
            # In question mode, show hint if available, otherwise [...]
            # Strip HTML from hint for cleaner display
            hint_text = re.sub(r'<[^>]+>', '', hint) if hint else None
            if hint_text:
                return f"[{hint_text}]"
            return "[...]"
        else:
            # In answer mode, return the answer (with any HTML tags intact)
            return answer

    return RAW_CLOZE_PATTERN.sub(replace_cloze, html)


# Patterns for Cloze Overlapping card templates
# These cards use hidden divs to store content that JavaScript renders at runtime
# Answer side: <div id="cloze-is-back" hidden="">...</div>
# Question side: <div id="cloze-anki-rendered" hidden="">...</div>
# We need to "unhide" the relevant div while keeping the rest of the HTML intact
CLOZE_BACK_TAG_PATTERN = re.compile(
    r'(<div[^>]*id=["\']cloze-is-back["\'][^>]*)\s+hidden(?:="[^"]*")?([^>]*>)',
    re.IGNORECASE
)
CLOZE_RENDERED_TAG_PATTERN = re.compile(
    r'(<div[^>]*id=["\']cloze-anki-rendered["\'][^>]*)\s+hidden(?:="[^"]*")?([^>]*>)',
    re.IGNORECASE
)


def _process_cloze_overlapping_html(html: str, mode: RenderMode) -> str:
    """Process Cloze Overlapping card HTML to unhide the relevant content div.

    Cloze Overlapping cards use JavaScript to render content at runtime.
    The actual card content is stored in hidden divs:
    - cloze-is-back: Contains the answer with revealed cloze spans
    - cloze-anki-rendered: Contains the question with [...] placeholders

    This function removes the 'hidden' attribute from the relevant div so it
    gets rendered, while keeping the rest of the HTML intact (preserving any
    extra info, images, etc. that should be shown).

    Args:
        html: HTML content from Anki card rendering.
        mode: Render mode - ANSWER unhides cloze-is-back, QUESTION unhides cloze-anki-rendered.

    Returns:
        Modified HTML with the relevant div unhidden, or original HTML if not a Cloze Overlapping card.
    """
    if mode == RenderMode.ANSWER:
        # Unhide cloze-is-back div (answer content)
        result = CLOZE_BACK_TAG_PATTERN.sub(r'\1\2', html)
        if result != html:
            return result
    else:
        # Unhide cloze-anki-rendered div (question content)
        result = CLOZE_RENDERED_TAG_PATTERN.sub(r'\1\2', html)
        if result != html:
            return result
    return html


@dataclass
class TextStyle:
    """Style attributes for a text segment."""

    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    color: str | None = None
    bgcolor: str | None = None
    is_cloze: bool = False  # Special flag for cloze answer highlighting

    def copy(self) -> "TextStyle":
        """Create a copy of this style."""
        return TextStyle(
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            strikethrough=self.strikethrough,
            color=self.color,
            bgcolor=self.bgcolor,
            is_cloze=self.is_cloze,
        )

    def is_default(self) -> bool:
        """Check if this is the default (unstyled) style."""
        return (
            not self.bold
            and not self.italic
            and not self.underline
            and not self.strikethrough
            and self.color is None
            and self.bgcolor is None
            and not self.is_cloze
        )


@dataclass
class StyledSegment:
    """A text segment with associated style."""

    text: str
    style: TextStyle = field(default_factory=TextStyle)


class _HTMLToTextRenderer(HTMLParser):
    """HTMLParser-based renderer for terminal output."""

    # Block-level tags that should produce newlines
    BLOCK_TAGS = {"br", "p", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    # Tags whose content should be skipped entirely
    SKIP_TAGS = {"style", "script", "button"}

    # Void elements (self-closing) that should be ignored
    # These don't have closing tags, so we just skip them without tracking depth
    VOID_SKIP_TAGS = {"input"}

    # Tags that can have hidden attribute and should skip content when hidden
    HIDEABLE_TAGS = {"div", "span", "p"}

    # Tags that apply text styling
    BOLD_TAGS = {"b", "strong"}
    ITALIC_TAGS = {"i", "em"}
    UNDERLINE_TAGS = {"u", "ins"}
    STRIKETHROUGH_TAGS = {"s", "del", "strike"}

    def __init__(
        self,
        media_dir: str | Path | None = None,
        mode: RenderMode = RenderMode.ANSWER,
        styled: bool = False,
    ) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._hidden_depth = 0  # Track nested hidden elements
        self._list_depth = 0
        self._in_list_item = False
        self._media_dir = Path(media_dir) if media_dir else None
        self._mode = mode
        self._styled = styled
        # Ruby/furigana state tracking
        self._in_ruby = False
        self._ruby_base = ""
        self._in_rt = False
        self._rt_text = ""
        # Cloze state tracking
        self._in_cloze = False
        self._cloze_content = ""
        # Style tracking (for styled output)
        self._segments: list[StyledSegment] = []
        self._style_stack: list[TextStyle] = [TextStyle()]  # Current style at top
        # Track tags that were hidden (for proper closing)
        self._hidden_tag_stack: list[str] = []

    def _current_style(self) -> TextStyle:
        """Get the current style from the stack."""
        return self._style_stack[-1] if self._style_stack else TextStyle()

    def _push_style(self, **changes: Any) -> None:
        """Push a new style with the given changes onto the stack."""
        new_style = self._current_style().copy()
        for key, value in changes.items():
            setattr(new_style, key, value)
        self._style_stack.append(new_style)

    def _pop_style(self) -> None:
        """Pop the current style from the stack."""
        if len(self._style_stack) > 1:
            self._style_stack.pop()

    def _append_styled(self, text: str) -> None:
        """Append text with current style (for styled mode)."""
        if not text:
            return
        if self._styled:
            self._segments.append(StyledSegment(text=text, style=self._current_style().copy()))
        self._chunks.append(text)

    def _is_cloze_span(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        """Check if this is a cloze deletion span."""
        if tag != "span":
            return False
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        return "cloze" in class_attr.split()

    def _has_hidden_attr(self, attrs: list[tuple[str, str | None]]) -> bool:
        """Check if element has hidden attribute."""
        for name, _ in attrs:
            if name.lower() == "hidden":
                return True
        return False

    def _parse_inline_style(self, style_str: str) -> dict[str, str]:
        """Parse inline CSS style attribute into a dict."""
        styles: dict[str, str] = {}
        if not style_str:
            return styles
        for part in style_str.split(";"):
            if ":" in part:
                key, value = part.split(":", 1)
                styles[key.strip().lower()] = value.strip()
        return styles

    def _apply_inline_styles(self, attrs: list[tuple[str, str | None]]) -> dict[str, Any]:
        """Extract style changes from inline CSS."""
        attrs_dict = dict(attrs)
        style_str = attrs_dict.get("style", "") or ""
        styles = self._parse_inline_style(style_str)

        changes: dict[str, Any] = {}

        # font-weight
        if styles.get("font-weight") in ("bold", "700", "800", "900"):
            changes["bold"] = True

        # font-style
        if styles.get("font-style") == "italic":
            changes["italic"] = True

        # text-decoration
        text_dec = styles.get("text-decoration", "")
        if "underline" in text_dec:
            changes["underline"] = True
        if "line-through" in text_dec:
            changes["strikethrough"] = True

        # color
        color = styles.get("color")
        if color:
            changes["color"] = color

        # background-color
        bgcolor = styles.get("background-color") or styles.get("background")
        if bgcolor:
            changes["bgcolor"] = bgcolor

        return changes

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Skip void elements entirely (no depth tracking needed)
        if tag in self.VOID_SKIP_TAGS:
            return

        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        # Check for hidden attribute on hideable tags
        if tag in self.HIDEABLE_TAGS and self._has_hidden_attr(attrs):
            self._hidden_depth += 1
            self._hidden_tag_stack.append(tag)
            return

        if self._hidden_depth > 0:
            return

        # Cloze span handling - must come before general span handling
        if self._is_cloze_span(tag, attrs):
            self._in_cloze = True
            self._cloze_content = ""
            if self._styled:
                # Push cloze style for answer mode
                self._push_style(is_cloze=True, bold=True)
            return

        # Style tag handling
        if tag in self.BOLD_TAGS:
            self._push_style(bold=True)
            return

        if tag in self.ITALIC_TAGS:
            self._push_style(italic=True)
            return

        if tag in self.UNDERLINE_TAGS:
            self._push_style(underline=True)
            return

        if tag in self.STRIKETHROUGH_TAGS:
            self._push_style(strikethrough=True)
            return

        # Span with inline styles
        if tag == "span":
            style_changes = self._apply_inline_styles(attrs)
            if style_changes:
                self._push_style(**style_changes)
            else:
                self._push_style()  # Push unchanged to maintain stack balance
            return

        # List handling
        if tag in {"ul", "ol"}:
            self._list_depth += 1
            return

        if tag == "li":
            self._in_list_item = True
            # Add newline, indentation, and bullet
            indent = "  " * (self._list_depth - 1) if self._list_depth > 0 else ""
            self._append_styled(f"\n{indent}- ")
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
            # Check for display: none in style attribute
            style_str = attrs_dict.get("style", "") or ""
            styles = self._parse_inline_style(style_str)
            if styles.get("display") == "none":
                return  # Skip hidden images
            src = attrs_dict.get("src", "")
            if src:
                filename = self._extract_filename(src)
                self._append_styled(f"[image: {filename}]")
            return

        # Block tags produce newlines
        if tag in self.BLOCK_TAGS:
            self._append_styled("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if self._skip_depth > 0:
            return

        # Check if we're closing a hidden element
        if self._hidden_depth > 0:
            if self._hidden_tag_stack and self._hidden_tag_stack[-1] == tag:
                self._hidden_depth -= 1
                self._hidden_tag_stack.pop()
            return

        # Cloze span end handling - must come before general span handling
        if tag == "span" and self._in_cloze:
            self._in_cloze = False
            if self._mode == RenderMode.QUESTION:
                # In question mode, show placeholder
                self._append_styled("[...]")
            else:
                # In answer mode, show the cloze content (already accumulated)
                self._append_styled(self._cloze_content)
            self._cloze_content = ""
            if self._styled:
                self._pop_style()
            return

        # Style tag end handling
        if tag in self.BOLD_TAGS:
            self._pop_style()
            return

        if tag in self.ITALIC_TAGS:
            self._pop_style()
            return

        if tag in self.UNDERLINE_TAGS:
            self._pop_style()
            return

        if tag in self.STRIKETHROUGH_TAGS:
            self._pop_style()
            return

        # Span end (for inline styles)
        if tag == "span":
            self._pop_style()
            return

        # Ruby/furigana end handling
        if tag == "rt":
            self._in_rt = False
            return

        if tag == "ruby":
            # Output combined format: base(reading)
            if self._ruby_base and self._rt_text:
                self._append_styled(f"{self._ruby_base}({self._rt_text})")
            elif self._ruby_base:
                self._append_styled(self._ruby_base)
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
            self._append_styled("\n")
            return

        # Block tags produce trailing newlines
        if tag in {"p", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._append_styled("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._hidden_depth > 0:
            return
        if not data:
            return

        # Handle cloze content accumulation
        if self._in_cloze:
            self._cloze_content += data
            return

        # Handle ruby/furigana text accumulation
        if self._in_rt:
            self._rt_text += data
            return

        if self._in_ruby:
            self._ruby_base += data
            return

        self._append_styled(data)

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

    def get_segments(self) -> list[StyledSegment]:
        """Get the styled segments (for styled output mode)."""
        return self._segments


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


def _is_anki_tag_line(line: str) -> bool:
    """Check if a line appears to be Anki card tags.

    Anki tags use :: as hierarchical separators and appear as lines like:
    "MileDown::Behavioral::Biology_and_Behavior"
    "chapter1::section2"

    Args:
        line: A single line of text.

    Returns:
        True if the line looks like Anki tags (contains :: separators).
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Tags contain :: and typically don't have spaces (or have underscores)
    # A tag line is one where the content is primarily tag-like
    if "::" not in stripped:
        return False
    # Check if the line is primarily tags (words separated by ::)
    # Real content would have more prose around it
    parts = stripped.split()
    # If it's a single "word" with :: in it, it's likely a tag
    if len(parts) == 1:
        return True
    # If multiple space-separated parts all contain ::, likely all tags
    tag_parts = sum(1 for p in parts if "::" in p)
    return tag_parts == len(parts)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace while preserving paragraph breaks and indentation.

    - Collapses multiple spaces into one (preserving leading indent)
    - Collapses 3+ newlines into 2 (paragraph break)
    - Strips trailing whitespace from lines
    - Filters out Anki tag lines
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
            # Skip lines that are just Anki tags
            if _is_anki_tag_line(content):
                continue
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


def render_html_to_text(
    html: str,
    media_dir: str | Path | None = None,
    mode: RenderMode = RenderMode.ANSWER,
) -> str:
    """Convert HTML to plain text suitable for terminal display.

    Args:
        html: HTML content from Anki card rendering.
        media_dir: Optional path to Anki media directory (from col.media.dir()).
            Currently used for context but filenames are extracted from src attrs.
        mode: Render mode for cloze handling. QUESTION shows [...] placeholder,
            ANSWER shows the actual cloze content.

    Returns:
        Plain text with:
        - List items formatted with "- " bullets and indentation
        - Media placeholders: [image: filename], [audio: filename/index]
        - Block elements converted to newlines
        - Script/style content removed
        - Whitespace normalized
        - Cloze deletions as [...] (question) or actual text (answer)
    """
    if not html:
        return ""

    # Process Cloze Overlapping cards by unhiding the relevant content div
    # This must happen BEFORE other processing since the content is in hidden divs
    html = _process_cloze_overlapping_html(html, mode)

    # Process raw cloze syntax BEFORE HTML parsing
    # This is necessary because cloze syntax may contain HTML tags
    html = _process_raw_cloze_in_html(html, mode)

    # Parse HTML and extract text
    renderer = _HTMLToTextRenderer(media_dir=media_dir, mode=mode, styled=False)
    renderer.feed(html)
    text = renderer.get_text()

    # Decode HTML entities
    text = unescape(text)

    # Process media tags (Anki-specific formats)
    text = _process_media_tags(text)

    # Normalize whitespace
    text = _normalize_whitespace(text)

    return text


def _needs_space_between(prev_text: str, next_text: str) -> bool:
    """Check if a space is needed between two text segments.

    Returns True if prev ends with a letter/digit and next starts with a letter/digit,
    which would cause words to run together without a space.
    """
    if not prev_text or not next_text:
        return False
    prev_char = prev_text[-1]
    next_char = next_text[0]
    # Need space if both are word characters (letter or digit)
    return prev_char.isalnum() and next_char.isalnum()


def _normalize_segments(segments: list[StyledSegment]) -> list[StyledSegment]:
    """Normalize whitespace in styled segments while preserving styles.

    Intelligently adds spaces between styled segments when words would
    otherwise run together (e.g., "<b>bold</b>next" becomes "bold next").
    """
    if not segments:
        return []

    result: list[StyledSegment] = []

    for seg in segments:
        text = seg.text

        # Check for boundary whitespace before normalizing
        has_leading_space = text and text[0] in " \t"
        has_trailing_space = text and text[-1] in " \t"

        # Handle pure newlines specially
        if text == "\n":
            if result and result[-1].style == seg.style:
                result[-1] = StyledSegment(
                    text=result[-1].text + "\n", style=seg.style
                )
            else:
                result.append(StyledSegment(text="\n", style=seg.style))
            continue

        # Collapse internal whitespace
        normalized = " ".join(text.split())

        if not normalized:
            # Segment was whitespace-only; preserve as single space if needed
            if text.strip() == "" and text:
                # Add space to previous segment
                if result:
                    result[-1] = StyledSegment(
                        text=result[-1].text + " ", style=result[-1].style
                    )
            continue

        # Determine if we need to add a leading space
        need_leading_space = False
        if result:
            prev_text = result[-1].text
            prev_ends_with_space = prev_text.endswith((" ", "\n"))

            if has_leading_space and not prev_ends_with_space:
                # Original had leading space, preserve it
                need_leading_space = True
            elif not prev_ends_with_space and _needs_space_between(prev_text, normalized):
                # Words would run together, add space
                need_leading_space = True

        if need_leading_space:
            normalized = " " + normalized

        # Preserve trailing space if original had it
        if has_trailing_space:
            normalized = normalized + " "

        # Merge with previous segment if same style
        if result and result[-1].style == seg.style:
            result[-1] = StyledSegment(
                text=result[-1].text + normalized, style=seg.style
            )
        else:
            result.append(StyledSegment(text=normalized, style=seg.style))

    # Final cleanup: collapse multiple spaces and newlines
    final: list[StyledSegment] = []
    for seg in result:
        # Collapse multiple consecutive spaces to single space
        text = re.sub(r" +", " ", seg.text)
        # Collapse 3+ newlines to 2 (one paragraph break)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove lines that are just whitespace
        text = re.sub(r"\n[ \t]+\n", "\n\n", text)
        if text:
            final.append(StyledSegment(text=text, style=seg.style))

    # Strip leading/trailing whitespace from the combined result
    if final:
        # Strip leading newlines/whitespace from first segment
        first = final[0]
        final[0] = StyledSegment(text=first.text.lstrip(), style=first.style)
        if not final[0].text:
            final.pop(0)

    if final:
        # Strip trailing newlines/whitespace from last segment
        last = final[-1]
        final[-1] = StyledSegment(text=last.text.rstrip(), style=last.style)
        if not final[-1].text:
            final.pop()

    return [s for s in final if s.text]


def _collapse_segment_newlines(segments: list[StyledSegment]) -> list[StyledSegment]:
    """Collapse excessive newlines across segment boundaries.

    This handles the case where multiple segments each end/start with newlines,
    resulting in too many consecutive newlines in the final output.

    Args:
        segments: List of styled segments.

    Returns:
        Segments with excessive newlines collapsed to max 2 (one paragraph break).
    """
    if not segments:
        return []

    # Join all text, collapse newlines, then rebuild
    full_text = "".join(s.text for s in segments)

    # Collapse 3+ newlines to 2
    collapsed_text = re.sub(r"\n{3,}", "\n\n", full_text)

    # If no change, return original
    if collapsed_text == full_text:
        return segments

    # Rebuild segments by mapping positions
    result: list[StyledSegment] = []
    orig_pos = 0
    collapsed_pos = 0

    for seg in segments:
        seg_text = seg.text
        new_chars = []

        for char in seg_text:
            # Find where this char maps to in collapsed text
            if orig_pos < len(full_text) and collapsed_pos < len(collapsed_text):
                # Check if this position was kept
                if full_text[orig_pos] == collapsed_text[collapsed_pos]:
                    new_chars.append(char)
                    collapsed_pos += 1
            orig_pos += 1

        if new_chars:
            result.append(StyledSegment(text="".join(new_chars), style=seg.style))

    # Merge consecutive segments with same style
    merged: list[StyledSegment] = []
    for seg in result:
        if merged and merged[-1].style == seg.style:
            merged[-1] = StyledSegment(text=merged[-1].text + seg.text, style=seg.style)
        else:
            merged.append(seg)

    return [s for s in merged if s.text]


def _filter_tag_segments(segments: list[StyledSegment]) -> list[StyledSegment]:
    """Filter out Anki tag lines from styled segments.

    Removes segments or parts of segments that are purely Anki tags.
    Tags are detected by the :: hierarchical separator pattern.

    Args:
        segments: List of styled segments to filter.

    Returns:
        Filtered list with tag lines removed.
    """
    if not segments:
        return []

    # Join all text and split by newlines to filter tag lines
    full_text = "".join(s.text for s in segments)
    lines = full_text.split("\n")

    # Filter out tag lines
    filtered_lines = [line for line in lines if not _is_anki_tag_line(line)]
    filtered_text = "\n".join(filtered_lines)

    # If nothing was filtered, return original
    if filtered_text == full_text:
        return segments

    # Rebuild segments with filtered text
    # This is a simplified approach - we map character positions
    result: list[StyledSegment] = []
    text_pos = 0
    filtered_pos = 0

    for seg in segments:
        seg_len = len(seg.text)
        seg_end = text_pos + seg_len

        # Find how much of this segment's text survives filtering
        new_text_parts = []
        for i, char in enumerate(seg.text):
            orig_pos = text_pos + i
            # Check if this character is in filtered output
            # by checking if we're in a removed line
            line_start = full_text.rfind("\n", 0, orig_pos + 1) + 1
            line_end = full_text.find("\n", orig_pos)
            if line_end == -1:
                line_end = len(full_text)
            line = full_text[line_start:line_end]

            if not _is_anki_tag_line(line):
                new_text_parts.append(char)

        new_text = "".join(new_text_parts)
        if new_text:
            result.append(StyledSegment(text=new_text, style=seg.style))

        text_pos = seg_end

    # Clean up: merge adjacent segments with same style, remove empty
    cleaned: list[StyledSegment] = []
    for seg in result:
        if not seg.text:
            continue
        if cleaned and cleaned[-1].style == seg.style:
            cleaned[-1] = StyledSegment(
                text=cleaned[-1].text + seg.text, style=seg.style
            )
        else:
            cleaned.append(seg)

    # Remove leading/trailing newlines from result
    if cleaned:
        first = cleaned[0]
        cleaned[0] = StyledSegment(text=first.text.lstrip("\n"), style=first.style)
        if cleaned:
            last = cleaned[-1]
            cleaned[-1] = StyledSegment(text=last.text.rstrip("\n"), style=last.style)

    # Filter out now-empty segments
    return [s for s in cleaned if s.text]


def render_html_to_styled_segments(
    html: str,
    media_dir: str | Path | None = None,
    mode: RenderMode = RenderMode.ANSWER,
) -> list[StyledSegment]:
    """Convert HTML to styled text segments for rich TUI display.

    Args:
        html: HTML content from Anki card rendering.
        media_dir: Optional path to Anki media directory.
        mode: Render mode for cloze handling. QUESTION shows [...] placeholder,
            ANSWER shows the actual cloze content with cloze styling.

    Returns:
        List of StyledSegment objects with text and style information.
        Styles include: bold, italic, underline, strikethrough, color, bgcolor, is_cloze.
    """
    if not html:
        return []

    # Process Cloze Overlapping cards by unhiding the relevant content div
    # This must happen BEFORE other processing since the content is in hidden divs
    html = _process_cloze_overlapping_html(html, mode)

    # Process raw cloze syntax BEFORE HTML parsing
    # This is necessary because cloze syntax may contain HTML tags
    html = _process_raw_cloze_in_html(html, mode)

    # Parse HTML and extract styled segments
    renderer = _HTMLToTextRenderer(media_dir=media_dir, mode=mode, styled=True)
    renderer.feed(html)
    segments = renderer.get_segments()

    # Process media tags in each segment
    processed: list[StyledSegment] = []
    for seg in segments:
        text = unescape(seg.text)
        text = _process_media_tags(text)
        if text:
            processed.append(StyledSegment(text=text, style=seg.style))

    # Normalize segments
    normalized = _normalize_segments(processed)

    # Filter out Anki tag segments
    filtered = _filter_tag_segments(normalized)

    # Final pass: collapse excessive newlines across segment boundaries
    return _collapse_segment_newlines(filtered)

"""TUI-specific rendering helpers for card content.

This module parses card text for [image: filename] placeholders and
renders them using textual-image when available and enabled. It also handles
audio placeholder icon substitution and styled text rendering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from rich.color import Color, ColorParseError
from rich.console import RenderableType
from rich.style import Style
from rich.text import Text

from ..audio import substitute_audio_icons
from ..render import RenderMode, StyledSegment, render_html_to_styled_segments

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


@dataclass
class ImageMarker:
    """Marker for an image that should be rendered by the widget layer.

    The render layer resolves the image path; the widget layer creates
    the actual textual-image widget so that terminal-specific image
    protocols (Sixel, Kitty/TGP) go through Textual's rendering pipeline.
    """

    path: Path


def _create_image_renderable(
    image_path: Path,
    max_width: int | None = None,
    max_height: int | None = None,
) -> ImageMarker | None:
    """Create an image marker for a verified image file.

    Args:
        image_path: Path to the image file.
        max_width: Maximum width in terminal cells (unused, kept for API compat).
        max_height: Maximum height in terminal cells (unused, kept for API compat).

    Returns:
        ImageMarker if the file exists, None otherwise.
    """
    if not image_path.exists():
        return None
    return ImageMarker(path=image_path)


def render_content_with_images(
    text: str,
    media_dir: Path | None,
    images_enabled: bool,
    max_width: int | None = None,
    max_height: int | None = None,
) -> list[RenderableType | ImageMarker]:
    """Render card content, replacing image placeholders with ImageMarkers.

    Also substitutes audio placeholders with an audio icon.

    Args:
        text: Card text content with [image: filename] and [audio: ...] placeholders.
        media_dir: Path to Anki media directory.
        images_enabled: Whether to attempt image rendering.
        max_width: Maximum width for images in terminal cells.
        max_height: Maximum height for images in terminal cells.

    Returns:
        List of Rich renderables (Text objects) and ImageMarker objects.
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
    renderables: list[RenderableType | ImageMarker] = []
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



_CSS_COLOR_MAP: dict[str, str] = {
    "aliceblue": "#f0f8ff",
    "antiquewhite": "#faebd7",
    "aqua": "#00ffff",
    "aquamarine": "#7fffd4",
    "azure": "#f0ffff",
    "beige": "#f5f5dc",
    "bisque": "#ffe4c4",
    "black": "#000000",
    "blanchedalmond": "#ffebcd",
    "blue": "#0000ff",
    "blueviolet": "#8a2be2",
    "brown": "#a52a2a",
    "burlywood": "#deb887",
    "cadetblue": "#5f9ea0",
    "chartreuse": "#7fff00",
    "chocolate": "#d2691e",
    "coral": "#ff7f50",
    "cornflowerblue": "#6495ed",
    "cornsilk": "#fff8dc",
    "crimson": "#dc143c",
    "cyan": "#00ffff",
    "darkblue": "#00008b",
    "darkcyan": "#008b8b",
    "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9",
    "darkgreen": "#006400",
    "darkgrey": "#a9a9a9",
    "darkkhaki": "#bdb76b",
    "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f",
    "darkorange": "#ff8c00",
    "darkorchid": "#9932cc",
    "darkred": "#8b0000",
    "darksalmon": "#e9967a",
    "darkseagreen": "#8fbc8f",
    "darkslateblue": "#483d8b",
    "darkslategray": "#2f4f4f",
    "darkslategrey": "#2f4f4f",
    "darkturquoise": "#00ced1",
    "darkviolet": "#9400d3",
    "deeppink": "#ff1493",
    "deepskyblue": "#00bfff",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "dodgerblue": "#1e90ff",
    "firebrick": "#b22222",
    "floralwhite": "#fffaf0",
    "forestgreen": "#228b22",
    "fuchsia": "#ff00ff",
    "gainsboro": "#dcdcdc",
    "ghostwhite": "#f8f8ff",
    "gold": "#ffd700",
    "goldenrod": "#daa520",
    "gray": "#808080",
    "green": "#008000",
    "greenyellow": "#adff2f",
    "grey": "#808080",
    "honeydew": "#f0fff0",
    "hotpink": "#ff69b4",
    "indianred": "#cd5c5c",
    "indigo": "#4b0082",
    "ivory": "#fffff0",
    "khaki": "#f0e68c",
    "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5",
    "lawngreen": "#7cfc00",
    "lemonchiffon": "#fffacd",
    "lightblue": "#add8e6",
    "lightcoral": "#f08080",
    "lightcyan": "#e0ffff",
    "lightgoldenrodyellow": "#fafad2",
    "lightgray": "#d3d3d3",
    "lightgreen": "#90ee90",
    "lightgrey": "#d3d3d3",
    "lightpink": "#ffb6c1",
    "lightsalmon": "#ffa07a",
    "lightseagreen": "#20b2aa",
    "lightskyblue": "#87cefa",
    "lightslategray": "#778899",
    "lightslategrey": "#778899",
    "lightsteelblue": "#b0c4de",
    "lightyellow": "#ffffe0",
    "lime": "#00ff00",
    "limegreen": "#32cd32",
    "linen": "#faf0e6",
    "magenta": "#ff00ff",
    "maroon": "#800000",
    "mediumaquamarine": "#66cdaa",
    "mediumblue": "#0000cd",
    "mediumorchid": "#ba55d3",
    "mediumpurple": "#9370db",
    "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee",
    "mediumspringgreen": "#00fa9a",
    "mediumturquoise": "#48d1cc",
    "mediumvioletred": "#c71585",
    "midnightblue": "#191970",
    "mintcream": "#f5fffa",
    "mistyrose": "#ffe4e1",
    "moccasin": "#ffe4b5",
    "navajowhite": "#ffdead",
    "navy": "#000080",
    "oldlace": "#fdf5e6",
    "olive": "#808000",
    "olivedrab": "#6b8e23",
    "orange": "#ffa500",
    "orangered": "#ff4500",
    "orchid": "#da70d6",
    "palegoldenrod": "#eee8aa",
    "palegreen": "#98fb98",
    "paleturquoise": "#afeeee",
    "palevioletred": "#db7093",
    "papayawhip": "#ffefd5",
    "peachpuff": "#ffdab9",
    "peru": "#cd853f",
    "pink": "#ffc0cb",
    "plum": "#dda0dd",
    "powderblue": "#b0e0e6",
    "purple": "#800080",
    "rebeccapurple": "#663399",
    "red": "#ff0000",
    "rosybrown": "#bc8f8f",
    "royalblue": "#4169e1",
    "saddlebrown": "#8b4513",
    "salmon": "#fa8072",
    "sandybrown": "#f4a460",
    "seagreen": "#2e8b57",
    "seashell": "#fff5ee",
    "sienna": "#a0522d",
    "silver": "#c0c0c0",
    "skyblue": "#87ceeb",
    "slateblue": "#6a5acd",
    "slategray": "#708090",
    "slategrey": "#708090",
    "snow": "#fffafa",
    "springgreen": "#00ff7f",
    "steelblue": "#4682b4",
    "tan": "#d2b48c",
    "teal": "#008080",
    "thistle": "#d8bfd8",
    "tomato": "#ff6347",
    "turquoise": "#40e0d0",
    "violet": "#ee82ee",
    "wheat": "#f5deb3",
    "white": "#ffffff",
    "whitesmoke": "#f5f5f5",
    "yellow": "#ffff00",
    "yellowgreen": "#9acd32",
}


def _parse_rich_color(css_color: str) -> str | None:
    """Try to parse a CSS color into a Rich-compatible color string.

    Rich uses underscore-separated names (e.g. ``dark_green``) while CSS uses
    camelCase or single words (e.g. ``darkgreen``).  This helper tries the
    original value first, then falls back to inserting underscores at
    common word boundaries.  Returns *None* when the color is unparseable
    (e.g. ``transparent``, ``inherit``).
    """
    if not css_color:
        return None
    # Skip CSS keywords that have no color equivalent
    if css_color in ("transparent", "inherit", "initial", "unset", "currentcolor"):
        return None
    # Try the color as-is first (hex, rgb, or already-valid name)
    try:
        Color.parse(css_color)
        return css_color
    except ColorParseError:
        pass
    # Try inserting underscores at camelCase / compound boundaries
    # e.g. "lightblue" -> "light_blue", "darkgreen" -> "dark_green"
    import re as _re

    underscored = _re.sub(
        r"(light|dark|medium|pale|deep)(.*)",
        lambda m: m.group(1) + "_" + m.group(2),
        css_color,
    )
    if underscored != css_color:
        try:
            Color.parse(underscored)
            return underscored
        except ColorParseError:
            pass
    # Fall back to the CSS named color map
    hex_val = _CSS_COLOR_MAP.get(css_color.lower())
    if hex_val:
        return hex_val
    return None


def _color_to_rgb(color_str: str) -> tuple[int, int, int] | None:
    """Parse a hex or rgb() color string to an (R, G, B) tuple.

    Supports ``#rrggbb``, ``#rgb``, and ``rgb(r, g, b)`` formats.
    Returns *None* for anything unparseable.
    """
    color_str = color_str.strip()
    if color_str.startswith("#"):
        hexval = color_str[1:]
        if len(hexval) == 3:
            r = int(hexval[0] * 2, 16)
            g = int(hexval[1] * 2, 16)
            b = int(hexval[2] * 2, 16)
            return (r, g, b)
        if len(hexval) == 6:
            r = int(hexval[0:2], 16)
            g = int(hexval[2:4], 16)
            b = int(hexval[4:6], 16)
            return (r, g, b)
        return None
    rgb_match = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color_str)
    if rgb_match:
        return (int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3)))
    return None


def _adjust_for_contrast(color_hex: str, *, is_bg: bool) -> str | None:
    """Adjust a color for readability on a dark terminal background.

    For foreground colors: if the luminance is below 140, lighten it to ~190
    while preserving the hue so that e.g. navy stays blue-ish but is clearly
    visible.

    For background colors: if the luminance is above 130, drop it (return
    None) because mid-to-light backgrounds wash out text on dark terminals.

    Returns a ``#rrggbb`` hex string or *None* (meaning "drop this color").
    """
    rgb = _color_to_rgb(color_hex)
    if rgb is None:
        return None
    r, g, b = rgb
    luminance = 0.299 * r + 0.587 * g + 0.114 * b

    if is_bg:
        # Drop backgrounds that aren't clearly dark — they hurt readability
        if luminance > 130:
            return None
        return color_hex

    # Foreground: lighten anything that isn't already bright
    if luminance < 140:
        # Scale RGB up so luminance ≈ 190 (comfortably readable on dark bg)
        max_component = max(r, g, b)
        if max_component == 0:
            # Pure black — make it light gray
            return "#b0b0b0"
        scale = 190.0 / luminance if luminance > 0 else 1.0
        r = min(255, int(r * scale))
        g = min(255, int(g * scale))
        b = min(255, int(b * scale))
        return f"#{r:02x}{g:02x}{b:02x}"

    return color_hex


def _segment_to_rich_style(
    segment: StyledSegment, *, high_contrast: bool = False
) -> Style:
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
        parsed = _parse_rich_color(segment.style.color)
        if parsed is not None:
            if high_contrast:
                adjusted = _adjust_for_contrast(parsed, is_bg=False)
                if adjusted:
                    style_kwargs["color"] = adjusted
                style_kwargs["bold"] = True
            else:
                style_kwargs["color"] = parsed

    if segment.style.bgcolor:
        parsed = _parse_rich_color(segment.style.bgcolor)
        if parsed is not None:
            if high_contrast:
                adjusted = _adjust_for_contrast(parsed, is_bg=True)
                if adjusted:
                    style_kwargs["bgcolor"] = adjusted
                else:
                    style_kwargs["underline"] = True
            else:
                style_kwargs["bgcolor"] = parsed

    # Special cloze styling: bold + reverse for visibility
    if segment.style.is_cloze:
        style_kwargs["bold"] = True
        style_kwargs["reverse"] = True

    return Style(**style_kwargs) if style_kwargs else Style()


def segments_to_rich_text(
    segments: list[StyledSegment], *, high_contrast: bool = False
) -> Text:
    """Convert a list of StyledSegments to a Rich Text object.

    Args:
        segments: List of StyledSegment objects from render_html_to_styled_segments.
        high_contrast: When True, strip foreground/background colors from styles.

    Returns:
        Rich Text object with appropriate styling applied.
    """
    text = Text()
    for segment in segments:
        style = _segment_to_rich_style(segment, high_contrast=high_contrast)
        text.append(segment.text, style=style)
    return text


def render_styled_content_with_images(
    html: str,
    media_dir: Path | None,
    images_enabled: bool,
    mode: RenderMode = RenderMode.ANSWER,
    max_width: int | None = None,
    max_height: int | None = None,
    high_contrast: bool = False,
) -> list[RenderableType | ImageMarker]:
    """Render HTML card content with styling and image support.

    This is the main entry point for TUI rendering with full styling support.

    Args:
        html: HTML content from Anki card rendering.
        media_dir: Path to Anki media directory.
        images_enabled: Whether to attempt image rendering.
        mode: Render mode for cloze handling (QUESTION shows [...], ANSWER shows styled text).
        max_width: Maximum width for images in terminal cells.
        max_height: Maximum height for images in terminal cells.
        high_contrast: When True, strip foreground/background colors from styles.

    Returns:
        List of Rich renderables (Text objects) and ImageMarker objects for images.
    """
    if not html:
        return []

    # Get styled segments
    segments = render_html_to_styled_segments(html, media_dir, mode)

    if not segments:
        return []

    # Convert segments to Rich Text
    styled_text = segments_to_rich_text(segments, high_contrast=high_contrast)

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
        styled_text = segments_to_rich_text(new_segments, high_contrast=high_contrast)
        plain_text = str(styled_text)

    # Parse image placeholders from the text
    placeholders = parse_image_placeholders(plain_text)

    # If no image placeholders or images disabled, return styled text as-is
    if not placeholders or not images_enabled:
        return [styled_text]

    # Build list of renderables, replacing image placeholders with ImageMarkers
    renderables: list[RenderableType | ImageMarker] = []
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

"""iTerm2 Inline Image Protocol Widget for Textual.

This module provides a Textual Widget that renders images using the iTerm2
Inline Image Protocol, which is supported by Warp terminal.

Credit: Pluto4o4 (https://github.com/alvenw/clanki/pull/2)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, NamedTuple

from PIL import Image as PILImage
from rich.control import Control
from rich.segment import ControlType, Segment
from rich.style import Style
from textual.dom import NoScreen
from textual.geometry import Region, Size
from textual.strip import Strip
from textual.widget import Widget

logger = logging.getLogger(__name__)

_NULL_STYLE = Style()


class _CellSize(NamedTuple):
    """Terminal cell size in pixels."""

    width: int
    height: int


def _get_cell_size() -> _CellSize:
    """Get terminal cell size. Returns default if detection fails."""
    try:
        from textual_image._terminal import get_cell_size

        size = get_cell_size()
        return _CellSize(size.width, size.height)
    except Exception:
        return _CellSize(10, 20)  # Default fallback


class _CachedImage(NamedTuple):
    """Cached iTerm2 image data."""

    image_path: Path
    content_crop: Region
    content_size: Size
    terminal_sizes: _CellSize
    iterm2_data: str

    def is_hit(
        self,
        image_path: Path,
        content_crop: Region,
        content_size: Size,
        terminal_sizes: _CellSize,
    ) -> bool:
        return (
            image_path == self.image_path
            and content_crop == self.content_crop
            and content_size == self.content_size
            and terminal_sizes == self.terminal_sizes
        )


class ITerm2Image(Widget):
    """Textual Widget to render images via iTerm2 Inline Image Protocol."""

    DEFAULT_CSS = """
    ITerm2Image {
        width: auto;
        height: auto;
    }
    """

    def __init__(
        self,
        image_path: Path,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the ITerm2Image widget."""
        super().__init__(name=name, id=id, classes=classes)
        self._image_path = image_path
        self._cached: _CachedImage | None = None
        self._image_width = 0
        self._image_height = 0
        self._load_image_meta()

    def _load_image_meta(self) -> None:
        """Load image dimensions."""
        try:
            with PILImage.open(self._image_path) as img:
                self._image_width = img.width
                self._image_height = img.height
        except Exception:
            self._image_width = 0
            self._image_height = 0

    def render_lines(self, crop: Region) -> list[Strip]:
        """Render the image using iTerm2 protocol."""
        try:
            if not self._image_path.exists() or not self.screen.is_active:
                return []
        except NoScreen:
            return []

        terminal_sizes = _get_cell_size()

        if self._cached and self._cached.is_hit(
            self._image_path, crop, self.content_size, terminal_sizes
        ):
            iterm2_data = self._cached.iterm2_data
        else:
            iterm2_data = self._encode_image(crop, terminal_sizes)
            self._cached = _CachedImage(
                self._image_path, crop, self.content_size, terminal_sizes, iterm2_data
            )

        segments = self._get_segments(iterm2_data)
        lines = [Strip([])] * (crop.height - 1) + [
            Strip(segments, cell_length=crop.width)
        ]
        return lines

    def _encode_image(self, crop: Region, terminal_sizes: _CellSize) -> str:
        """Encode image to iTerm2 format."""
        import base64
        import io

        # Calculate pixel dimensions
        pixel_width = crop.width * terminal_sizes.width
        pixel_height = crop.height * terminal_sizes.height

        # Load and resize image
        with PILImage.open(self._image_path) as img:
            img = img.convert("RGBA")
            img = img.resize(
                (pixel_width, pixel_height), PILImage.Resampling.LANCZOS
            )

            # Encode to PNG base64
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            base64_data = base64.b64encode(buffer.getvalue()).decode("ascii")

        # Build iTerm2 escape sequence
        args = f"inline=1;width={crop.width};height={crop.height}"
        return f"\x1b]1337;File={args}:{base64_data}\x07"

    def _get_segments(self, iterm2_data: str) -> Iterable[Segment]:
        """Get Rich segments for rendering."""
        visible_region = self.screen.find_widget(self).visible_region
        return [
            Segment(
                Control.move_to(visible_region.x, visible_region.y).segment.text,
                style=_NULL_STYLE,
            ),
            Segment(
                iterm2_data,
                style=_NULL_STYLE,
                control=((ControlType.CURSOR_FORWARD, 0),),
            ),
            Segment(
                Control.move_to(
                    visible_region.right, visible_region.bottom
                ).segment.text,
                style=_NULL_STYLE,
            ),
        ]

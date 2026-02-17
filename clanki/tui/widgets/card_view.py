"""Card view widget for displaying question and answer content."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from textual import events
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from textual_image.widget import Image as ImageWidget

from ...render import RenderMode
from ..render import ImageMarker, render_styled_content_with_images
from .iterm2_image import ITerm2Image

logger = logging.getLogger(__name__)


def _is_warp_terminal() -> bool:
    """Check if running in Warp terminal."""
    return "warp" in os.environ.get("TERM_PROGRAM", "").lower()


class CardViewWidget(Vertical):
    """Widget for displaying card content (question and optionally answer)."""

    DEFAULT_CSS = """
    CardViewWidget {
        height: auto;
        width: 100%;
        max-width: 96;
        padding: 0;
    }

    CardViewWidget .card-section {
        border: solid $primary;
        padding: 1 2;
        height: auto;
    }

    CardViewWidget .content {
        height: auto;
    }

    CardViewWidget .card-image {
        height: auto;
    }
    """

    # Caps for image display size (in terminal cells).
    # Flashcard images should complement text, not dominate the card.
    MAX_IMAGE_WIDTH = 50
    MAX_IMAGE_HEIGHT = 15

    def __init__(
        self,
        id: str | None = None,
        media_dir: Path | None = None,
        images_enabled: bool = True,
        high_contrast: bool = False,
    ) -> None:
        super().__init__(id=id)
        self._question_html: str = ""
        self._answer_html: str | None = None
        self._media_dir = media_dir
        self._images_enabled = images_enabled
        self._high_contrast = high_contrast
        self._last_width: int = 0  # Track width to avoid unnecessary re-renders

    def set_media_dir(self, media_dir: Path | None) -> None:
        """Set the media directory for image loading."""
        self._media_dir = media_dir

    def set_images_enabled(self, enabled: bool) -> None:
        """Set whether images should be rendered."""
        self._images_enabled = enabled
        self._refresh_content()

    def set_high_contrast(self, enabled: bool) -> None:
        """Set whether high contrast mode is active."""
        self._high_contrast = enabled
        self._refresh_content()

    def show_question(self, question_html: str) -> None:
        """Display only the question.

        Args:
            question_html: Raw HTML content for the question side.
        """
        self._question_html = question_html
        self._answer_html = None
        self._refresh_content()

    def show_answer(self, question_html: str, answer_html: str) -> None:
        """Display both question and answer.

        Args:
            question_html: Raw HTML content for the question side.
            answer_html: Raw HTML content for the answer side.
        """
        self._question_html = question_html
        self._answer_html = answer_html
        self._refresh_content()

    def _get_max_image_size(self) -> tuple[int | None, int | None]:
        """Calculate maximum image size based on available width.

        Uses a fixed max height to prevent resize feedback loops where:
        1. Image renders and increases widget height
        2. Resize triggers re-render with larger max_height
        3. Image grows, increasing height further (infinite loop)

        Returns:
            Tuple of (max_width, max_height) in terminal cells.
        """
        try:
            # content_region accounts for widget's own padding
            region = self.content_region

            # If size isn't known yet (pre-layout), use defaults
            if region.width <= 0:
                return (None, self.MAX_IMAGE_HEIGHT)

            # Subtract card-section chrome: border (1 each side) + padding (2h each side)
            width = region.width - 6

            if width <= 0:
                return (None, self.MAX_IMAGE_HEIGHT)

            return (max(10, width), self.MAX_IMAGE_HEIGHT)
        except Exception:
            return (None, self.MAX_IMAGE_HEIGHT)

    def _make_image_widget(
        self, path: Path, max_width: int | None, max_height: int | None
    ) -> Widget:
        """Create an image widget with fixed, aspect-ratio-correct dimensions.

        Reads the image's real pixel size, calculates the best fit within
        the card area (accounting for the ~2:1 terminal cell aspect ratio),
        and sets a *fixed* width + height on the widget so the layout never
        oscillates.

        Warp terminal uses the iTerm2 widget; others use textual-image.
        """
        from PIL import Image as PILImage

        # Read real image dimensions
        try:
            with PILImage.open(path) as img:
                img_w, img_h = img.size
        except Exception:
            img_w, img_h = 1, 1

        avail_w = min(max_width or self.MAX_IMAGE_WIDTH, self.MAX_IMAGE_WIDTH)
        avail_h = min(max_height or self.MAX_IMAGE_HEIGHT, self.MAX_IMAGE_HEIGHT)

        # Terminal cells are roughly twice as tall as they are wide,
        # so 1 row of cells ≈ 2 columns in visual height.
        img_aspect = img_w / max(img_h, 1)

        # Fit to available width, derive height from aspect ratio
        display_w = avail_w
        display_h = round(display_w / img_aspect / 2)

        # If too tall, fit to height instead
        if display_h > avail_h:
            display_h = avail_h
            display_w = round(display_h * img_aspect * 2)

        display_w = max(display_w, 4)
        display_h = max(display_h, 2)

        if _is_warp_terminal():
            widget: Widget = ITerm2Image(path, classes="card-image")
        else:
            widget = ImageWidget(path, classes="card-image")

        # Fixed dimensions prevent layout oscillation / scroll jitter
        widget.styles.width = display_w
        widget.styles.height = display_h
        return widget

    def _render_section_content(
        self, html: str, mode: RenderMode = RenderMode.ANSWER
    ) -> list[Widget]:
        """Render section content with styling and image support.

        Args:
            html: HTML content from Anki card rendering.
            mode: Render mode - QUESTION shows [...] for cloze, ANSWER shows styled cloze text.

        Returns:
            List of widgets (Static for text, image widgets for images) to mount.
        """
        try:
            max_width, max_height = self._get_max_image_size()

            renderables = render_styled_content_with_images(
                html=html,
                media_dir=self._media_dir,
                images_enabled=self._images_enabled,
                mode=mode,
                max_width=max_width,
                max_height=max_height,
                high_contrast=self._high_contrast,
            )

            widgets: list[Widget] = []
            for renderable in renderables:
                if isinstance(renderable, ImageMarker):
                    widgets.append(
                        self._make_image_widget(
                            renderable.path, max_width, max_height
                        )
                    )
                else:
                    widgets.append(Static(renderable, classes="content"))

            return widgets if widgets else [Static(html, classes="content")]
        except Exception as exc:
            # Fall back to plain text on any rendering error
            logger.warning("Styled rendering failed, using plain text: %s", exc)
            return [Static(html, classes="content")]

    def _refresh_content(self) -> None:
        """Refresh the widget content."""
        try:
            self.remove_children()  # Remove from self, not #card-content

            if self._answer_html is not None:
                content_widgets = self._render_section_content(
                    self._answer_html, mode=RenderMode.ANSWER
                )
            else:
                content_widgets = self._render_section_content(
                    self._question_html, mode=RenderMode.QUESTION
                )

            content_section = Vertical(
                *content_widgets,
                classes="card-section",
            )
            self.mount(content_section)  # Mount directly to self
        except Exception as exc:
            logger.warning("Card content mounting failed, trying fallback: %s", exc)
            try:
                self.remove_children()
                html = self._answer_html if self._answer_html else self._question_html
                self.mount(Static(html, classes="content"))
            except Exception as fallback_exc:
                logger.error("Fallback mounting also failed: %s", fallback_exc)

    def on_resize(self, event: events.Resize) -> None:
        """Re-render content when widget width changes significantly.

        Uses a threshold of 4 columns to avoid feedback loops where
        small layout adjustments from image rendering trigger more resizes.
        """
        current_width = event.size.width
        if abs(current_width - self._last_width) >= 4:
            self._last_width = current_width
            if self._images_enabled and (self._question_html or self._answer_html):
                self._refresh_content()

"""Card view widget for displaying question and answer content."""

from __future__ import annotations

import logging
from pathlib import Path

from textual import events
from textual.containers import Vertical
from textual.widgets import Static

from ...render import RenderMode
from ..render import render_styled_content_with_images

logger = logging.getLogger(__name__)


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
    """

    # Fixed max height for images to prevent resize feedback loops
    MAX_IMAGE_HEIGHT = 20

    def __init__(
        self,
        id: str | None = None,
        media_dir: Path | None = None,
        images_enabled: bool = True,
    ) -> None:
        super().__init__(id=id)
        self._question_html: str = ""
        self._answer_html: str | None = None
        self._media_dir = media_dir
        self._images_enabled = images_enabled
        self._last_width: int = 0  # Track width to avoid unnecessary re-renders

    def set_media_dir(self, media_dir: Path | None) -> None:
        """Set the media directory for image loading."""
        self._media_dir = media_dir

    def set_images_enabled(self, enabled: bool) -> None:
        """Set whether images should be rendered."""
        self._images_enabled = enabled
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

    def _render_section_content(
        self, html: str, mode: RenderMode = RenderMode.ANSWER
    ) -> list[Static]:
        """Render section content with styling and image support.

        Args:
            html: HTML content from Anki card rendering.
            mode: Render mode - QUESTION shows [...] for cloze, ANSWER shows styled cloze text.

        Returns:
            List of Static widgets to mount.
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
            )

            widgets: list[Static] = []
            for renderable in renderables:
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
        """Re-render content when widget width changes to fix image scaling.

        Only re-renders on width changes to prevent feedback loops where
        height changes from image rendering trigger more resizes.
        """
        current_width = event.size.width
        if current_width != self._last_width:
            self._last_width = current_width
            if self._images_enabled and (self._question_html or self._answer_html):
                self._refresh_content()

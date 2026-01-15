"""Card view widget for displaying question and answer content."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ...render import RenderMode
from ..render import render_styled_content_with_images

logger = logging.getLogger(__name__)


class CardViewWidget(Static):
    """Widget for displaying card content (question and optionally answer)."""

    DEFAULT_CSS = """
    CardViewWidget {
        height: 1fr;
        padding: 1 2;
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

    def compose(self) -> ComposeResult:
        yield Vertical(id="card-content")

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
        """Calculate maximum image size based on available viewport.

        Returns:
            Tuple of (max_width, max_height) in terminal cells.
        """
        try:
            # Get container size, accounting for padding and borders
            # Widget padding: 1 2 (top/bottom, left/right) = 4 horizontal, 2 vertical
            # Section border: 1 each side = 2 horizontal, 2 vertical
            # Section padding: 1 2 = 4 horizontal, 2 vertical
            container_width = self.size.width - 12  # Total horizontal padding/borders
            container_height = self.size.height - 8  # Vertical space minus chrome

            return (
                max(10, container_width) if container_width > 0 else None,
                max(5, container_height) if container_height > 0 else None,
            )
        except Exception:
            # If we can't determine size, let term-image decide
            return (None, None)

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
        """Refresh the widget content.

        Always renders a single card section (Anki-style):
        - Question state: shows question_html with QUESTION mode (cloze shows [...])
        - Answer revealed: shows only answer_html with ANSWER mode
          (answer HTML typically includes front via {{FrontSide}})
        """
        try:
            container = self.query_one("#card-content", Vertical)
            container.remove_children()

            if self._answer_html is not None:
                # Answer revealed: render answer HTML only
                content_widgets = self._render_section_content(
                    self._answer_html, mode=RenderMode.ANSWER
                )
            else:
                # Question only: render with QUESTION mode for cloze handling
                content_widgets = self._render_section_content(
                    self._question_html, mode=RenderMode.QUESTION
                )

            content_section = Vertical(
                *content_widgets,
                classes="card-section",
            )
            container.mount(content_section)
        except Exception as exc:
            # If mounting fails, try to show plain text fallback
            logger.warning("Card content mounting failed, trying fallback: %s", exc)
            try:
                container = self.query_one("#card-content", Vertical)
                container.remove_children()
                html = self._answer_html if self._answer_html else self._question_html
                container.mount(Static(html, classes="content"))
            except Exception as fallback_exc:
                logger.error("Fallback mounting also failed: %s", fallback_exc)

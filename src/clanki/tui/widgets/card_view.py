"""Card view widget for displaying question and answer content."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ...render import RenderMode, is_cloze_card
from ..render import render_styled_content_with_images

logger = logging.getLogger(__name__)


class CardViewWidget(Static):
    """Widget for displaying card content (question and optionally answer)."""

    DEFAULT_CSS = """
    CardViewWidget {
        height: 1fr;
        padding: 1 2;
    }

    CardViewWidget .question-section {
        border: solid $primary;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    CardViewWidget .answer-section {
        border: solid $success;
        padding: 1 2;
        height: auto;
    }

    CardViewWidget .section-label {
        color: $text-muted;
        text-style: bold;
        margin-bottom: 1;
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
            # Section label: 1 line + 1 margin
            container_width = self.size.width - 12  # Total horizontal padding/borders
            container_height = self.size.height - 10  # Vertical space minus chrome

            # If showing both question and answer (non-cloze card), halve the height
            # Cloze cards use single section, so they get full height
            is_cloze = is_cloze_card(self._answer_html or self._question_html)
            if self._answer_html is not None and not is_cloze:
                container_height = container_height // 2 - 2

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
        """Refresh the widget content."""
        try:
            container = self.query_one("#card-content", Vertical)
            container.remove_children()

            # Check if this is a cloze card
            is_cloze = is_cloze_card(self._answer_html or self._question_html)

            if is_cloze and self._answer_html is not None:
                # Cloze card with answer revealed: single section with answer HTML
                # The answer HTML contains the full card with cloze revealed
                content_widgets = self._render_section_content(
                    self._answer_html, mode=RenderMode.ANSWER
                )
                content_section = Vertical(
                    Static("[bold]Card[/bold]", classes="section-label", markup=True),
                    *content_widgets,
                    classes="question-section",  # Use question styling for main content
                )
                container.mount(content_section)
            elif is_cloze:
                # Cloze card, question only: show with [...] placeholder
                question_widgets = self._render_section_content(
                    self._question_html, mode=RenderMode.QUESTION
                )
                question_section = Vertical(
                    Static("[bold]Card[/bold]", classes="section-label", markup=True),
                    *question_widgets,
                    classes="question-section",
                )
                container.mount(question_section)
            else:
                # Non-cloze card: show Question + Answer sections
                # Question section
                question_widgets = self._render_section_content(
                    self._question_html, mode=RenderMode.ANSWER
                )
                question_section = Vertical(
                    Static("[bold]Question[/bold]", classes="section-label", markup=True),
                    *question_widgets,
                    classes="question-section",
                )
                container.mount(question_section)

                # Answer section (if revealed)
                if self._answer_html is not None:
                    answer_widgets = self._render_section_content(
                        self._answer_html, mode=RenderMode.ANSWER
                    )
                    answer_section = Vertical(
                        Static("[bold]Answer[/bold]", classes="section-label", markup=True),
                        *answer_widgets,
                        classes="answer-section",
                    )
                    container.mount(answer_section)
        except Exception as exc:
            # If mounting fails, try to show plain text fallback
            logger.warning("Card content mounting failed, trying fallback: %s", exc)
            try:
                container = self.query_one("#card-content", Vertical)
                container.remove_children()
                container.mount(Static(self._question_html, classes="content"))
                if self._answer_html is not None:
                    container.mount(Static(self._answer_html, classes="content"))
            except Exception as fallback_exc:
                logger.error("Fallback mounting also failed: %s", fallback_exc)

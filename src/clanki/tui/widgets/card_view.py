"""Card view widget for displaying question and answer content."""

from __future__ import annotations

from pathlib import Path

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ..render import render_content_with_images


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
        self._question: str = ""
        self._answer: str | None = None
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

    def show_question(self, question: str) -> None:
        """Display only the question."""
        self._question = question
        self._answer = None
        self._refresh_content()

    def show_answer(self, question: str, answer: str) -> None:
        """Display both question and answer."""
        self._question = question
        self._answer = answer
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

            # If showing both question and answer, halve the height
            if self._answer is not None:
                container_height = container_height // 2 - 2

            return (
                max(10, container_width) if container_width > 0 else None,
                max(5, container_height) if container_height > 0 else None,
            )
        except Exception:
            # If we can't determine size, let term-image decide
            return (None, None)

    def _render_section_content(self, text: str) -> list[Static]:
        """Render section content, handling images if enabled.

        Args:
            text: Text content possibly containing [image: ...] placeholders.

        Returns:
            List of Static widgets to mount.
        """
        try:
            max_width, max_height = self._get_max_image_size()

            renderables = render_content_with_images(
                text=text,
                media_dir=self._media_dir,
                images_enabled=self._images_enabled,
                max_width=max_width,
                max_height=max_height,
            )

            widgets: list[Static] = []
            for renderable in renderables:
                widgets.append(Static(renderable, classes="content"))

            return widgets if widgets else [Static(text, classes="content")]
        except Exception:
            # Fall back to plain text on any rendering error
            return [Static(text, classes="content")]

    def _refresh_content(self) -> None:
        """Refresh the widget content."""
        try:
            container = self.query_one("#card-content", Vertical)
            container.remove_children()

            # Question section
            question_widgets = self._render_section_content(self._question)
            question_section = Vertical(
                Static("[bold]Question[/bold]", classes="section-label", markup=True),
                *question_widgets,
                classes="question-section",
            )
            container.mount(question_section)

            # Answer section (if revealed)
            if self._answer is not None:
                answer_widgets = self._render_section_content(self._answer)
                answer_section = Vertical(
                    Static("[bold]Answer[/bold]", classes="section-label", markup=True),
                    *answer_widgets,
                    classes="answer-section",
                )
                container.mount(answer_section)
        except Exception:
            # If mounting fails, try to show plain text fallback
            try:
                container = self.query_one("#card-content", Vertical)
                container.remove_children()
                container.mount(Static(self._question, classes="content"))
                if self._answer is not None:
                    container.mount(Static(self._answer, classes="content"))
            except Exception:
                pass  # Give up if fallback also fails

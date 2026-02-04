"""Card view widget for displaying question and answer content."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from textual import events
from textual.containers import Vertical
from textual.widgets import Static

from ...render import RenderMode
from ..render import render_styled_content_with_images, parse_image_placeholders

logger = logging.getLogger(__name__)


def _is_warp_terminal() -> bool:
    """Check if running in Warp terminal."""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    return "warp" in term_program


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
    ) -> list[Static | "Widget"]:
        """Render section content with styling and image support."""
        from textual.widget import Widget

        # Check if we should use iTerm2 Widget for Warp terminal
        use_iterm2_widget = _is_warp_terminal() and self._images_enabled

        try:
            max_width, max_height = self._get_max_image_size()

            if use_iterm2_widget:
                return self._render_with_iterm2_widget(html, mode, max_width, max_height)

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
            logger.warning("Styled rendering failed, using plain text: %s", exc)
            return [Static(html, classes="content")]

    def _render_with_iterm2_widget(
        self,
        html: str,
        mode: RenderMode,
        max_width: int | None,
        max_height: int | None,
    ) -> list[Static | "Widget"]:
        """Render content using iTerm2 Widget for Warp terminal."""
        from textual.widget import Widget
        from .iterm2_image import ITerm2Image
        from rich.text import Text

        from ..render import segments_to_rich_text
        from ...render import render_html_to_styled_segments as base_render
        from ..render import parse_image_placeholders
        from ...audio import substitute_audio_icons

        # Get styled segments
        segments = base_render(html, self._media_dir, mode)
        if not segments:
            return [Static(html, classes="content")]

        styled_text = segments_to_rich_text(segments)
        plain_text = str(styled_text)
        plain_text = substitute_audio_icons(plain_text)

        # Parse image placeholders
        placeholders = parse_image_placeholders(plain_text)

        if not placeholders or not self._media_dir:
            return [Static(styled_text, classes="content")]

        # Build widgets list
        widgets: list[Static | Widget] = []
        last_end = 0

        for placeholder in placeholders:
            # Add text before image
            if placeholder.start > last_end:
                text_before = plain_text[last_end:placeholder.start]
                if text_before.strip():
                    widgets.append(Static(Text(text_before), classes="content"))

            # Add iTerm2 image widget
            image_path = self._media_dir / placeholder.filename
            if image_path.exists():
                img_widget = ITerm2Image(image_path)
                img_widget.styles.width = max_width or 40
                img_widget.styles.height = max_height or 20
                widgets.append(img_widget)
            else:
                widgets.append(Static(f"[image: {placeholder.filename}]", classes="content"))

            last_end = placeholder.end

        # Add remaining text
        if last_end < len(plain_text):
            text_after = plain_text[last_end:]
            if text_after.strip():
                widgets.append(Static(Text(text_after), classes="content"))

        return widgets if widgets else [Static(html, classes="content")]

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

"""Card view widget for displaying question and answer content."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


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

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._question: str = ""
        self._answer: str | None = None

    def compose(self) -> ComposeResult:
        yield Vertical(id="card-content")

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

    def _refresh_content(self) -> None:
        """Refresh the widget content."""
        container = self.query_one("#card-content", Vertical)
        container.remove_children()

        # Question section
        question_section = Vertical(
            Static("[bold]Question[/bold]", classes="section-label", markup=True),
            Static(self._question, classes="content"),
            classes="question-section",
        )
        container.mount(question_section)

        # Answer section (if revealed)
        if self._answer is not None:
            answer_section = Vertical(
                Static("[bold]Answer[/bold]", classes="section-label", markup=True),
                Static(self._answer, classes="content"),
                classes="answer-section",
            )
            container.mount(answer_section)

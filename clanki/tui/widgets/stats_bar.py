"""Stats bar widgets for displaying deck and session statistics."""

from __future__ import annotations

from textual.widgets import Static


class StatsBar(Static):
    """Widget displaying session progress (due/reviewed) at the top."""

    DEFAULT_CSS = """
    StatsBar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._due = 0
        self._reviewed = 0

    def update_counts(self, new: int, learn: int, review: int) -> None:
        """Update the deck due counts (calculates total due)."""
        self._due = new + learn + review
        self._refresh_display()

    def update_session(self, reviewed: int) -> None:
        """Update the session reviewed count."""
        self._reviewed = reviewed
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the displayed statistics."""
        text = f"Session stats  Due: {self._due}  Reviewed: {self._reviewed}"
        self.update(text)


class DeckCountsBar(Static):
    """Widget displaying deck counts (new/learn/review) at the bottom."""

    DEFAULT_CSS = """
    DeckCountsBar {
        height: 1;
        text-align: center;
    }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._new = 0
        self._learn = 0
        self._review = 0

    def update_counts(self, new: int, learn: int, review: int) -> None:
        """Update the deck due counts."""
        self._new = new
        self._learn = learn
        self._review = review
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the displayed statistics."""
        # Colors matched to Anki's dark mode UI
        text = (
            f"[bold #5eb5f7]{self._new}[/bold #5eb5f7] New  "
            f"[bold #e96c6c]{self._learn}[/bold #e96c6c] Learning  "
            f"[bold #6cd97e]{self._review}[/bold #6cd97e] Review"
        )
        self.update(text)

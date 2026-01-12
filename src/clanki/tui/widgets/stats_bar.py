"""Stats bar widget for displaying deck and session statistics."""

from __future__ import annotations

from textual.widgets import Static


class StatsBar(Static):
    """Widget displaying current deck counts and session progress."""

    DEFAULT_CSS = """
    StatsBar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._new = 0
        self._learn = 0
        self._review = 0
        self._reviewed = 0

    def update_counts(self, new: int, learn: int, review: int) -> None:
        """Update the deck due counts."""
        self._new = new
        self._learn = learn
        self._review = review
        self._refresh_display()

    def update_session(self, reviewed: int) -> None:
        """Update the session reviewed count."""
        self._reviewed = reviewed
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the displayed statistics."""
        total_due = self._new + self._learn + self._review
        text = (
            f"[bold blue]{self._new}[/bold blue] new  "
            f"[bold red]{self._learn}[/bold red] learning  "
            f"[bold green]{self._review}[/bold green] review  "
            f"[dim]|[/dim]  "
            f"Due: {total_due}  "
            f"Reviewed: {self._reviewed}"
        )
        self.update(text)

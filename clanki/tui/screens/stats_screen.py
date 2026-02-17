"""Statistics screen for Clanki TUI.

Shows today's review count, study time, and session breakdown,
using the same layout as the deck picker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Static

if TYPE_CHECKING:
    from ..app import ClankiApp


class StatsScreen(Screen[None]):
    """Screen displaying today's review statistics."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "app.quit", "Quit"),
    ]

    @property
    def clanki_app(self) -> "ClankiApp":
        """Get the typed app instance."""
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        col = self.clanki_app.state.col
        session_stats = self.clanki_app.state.stats

        # Query today's stats from the collection
        today_count = 0
        today_time_secs = 0

        if col is not None:
            try:
                cutoff = col.sched.day_cutoff
                row = col.db.first(
                    "SELECT COUNT(), SUM(time) FROM revlog WHERE id > ?",
                    cutoff * 1000,
                )
                if row:
                    today_count = row[0] or 0
                    today_time_secs = (row[1] or 0) // 1000
            except Exception:
                pass

        # Format study time
        if today_time_secs >= 3600:
            hours = today_time_secs // 3600
            mins = (today_time_secs % 3600) // 60
            time_str = f"{hours}h {mins}m"
        elif today_time_secs >= 60:
            mins = today_time_secs // 60
            secs = today_time_secs % 60
            time_str = f"{mins}m {secs}s"
        else:
            time_str = f"{today_time_secs}s"

        # Footer - full width, docked to bottom
        yield Static(
            "[dim]Esc[/dim] back  [dim]q[/dim] quit",
            classes="help-text footer-bar",
            markup=True,
        )
        # Main content - centered with max-width (matches deck picker layout)
        yield Container(
            Vertical(
                Static("Statistics", classes="header-bar"),
                Static(""),
                Static("[bold]Today[/bold]", markup=True),
                Static(
                    f"  Reviews:    [bold]{today_count}[/bold]",
                    markup=True,
                ),
                Static(
                    f"  Study time: [bold]{time_str}[/bold]",
                    markup=True,
                ),
                Static(""),
                Static("[bold]Session[/bold]", markup=True),
                Static(f"  Reviewed: {session_stats.reviewed}"),
                Static(
                    f"  Again: {session_stats.again_count}  "
                    f"Hard: {session_stats.hard_count}  "
                    f"Good: {session_stats.good_count}  "
                    f"Easy: {session_stats.easy_count}"
                ),
                classes="content-column",
            ),
            classes="centered-screen",
        )

    async def action_back(self) -> None:
        """Return to the previous screen."""
        self.app.pop_screen()

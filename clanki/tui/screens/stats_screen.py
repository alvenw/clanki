"""Statistics screen for Clanki TUI.

Shows detailed review statistics with rich color-coded display including
today's reviews, session stats, streaks, due breakdown, card states,
retention, forecast, 28-day review heatmap, and growth metrics.
Supports per-deck and collection-wide views.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from anki.collection import Collection
    from textual import events

    from ..app import ClankiApp

# ── Color palette ────────────────────────────────────────────────
# Semantic colors that read well on both dark and light terminals.
# These are softer/brighter than pure primaries and avoid clashing.
C_ACCENT = "#6c9fd4"  # Muted blue for section headers
C_NEW = "#5eb5f7"  # Blue - new cards
C_LEARN = "#e9a55c"  # Warm orange - learning
C_REVIEW = "#6cd97e"  # Green - review
C_RELEARN = "#e96c6c"  # Red - relearning / again
C_HARD = "#e0c55a"  # Yellow-gold - hard
C_GOOD = "#6cd97e"  # Green - good
C_EASY = "#5eb5f7"  # Blue - easy
C_MATURE = "#9b8ec4"  # Purple - mature
C_SUSPEND = "#888888"  # Gray - suspended
C_BURIED = "#666666"  # Dim gray - buried
C_YOUNG = "#6cd97e"  # Green - young
C_STREAK = "#e9a55c"  # Warm orange for streaks
C_ADDED = "#5eb5f7"  # Blue for added
C_MATURED = "#9b8ec4"  # Purple for matured
C_DIM = "#777777"  # Dim text
C_BRIGHT = "#e0e0e0"  # Bright text for values
# Bar gradient: 8 colors from dim blue to bright cyan
BAR_GRADIENT = [
    "#2a4a6a",
    "#3a5f8a",
    "#4a74a5",
    "#5a8ac0",
    "#6a9fd5",
    "#7ab4e5",
    "#8ac9f0",
    "#9adeff",
]

# Heatmap color gradient: empty → low → high
HEAT_COLORS = [
    "#222233",  # 0 reviews - empty
    "#2a4a6a",  # low
    "#3a6a9a",  # medium-low
    "#5a8ac0",  # medium
    "#7ab4e5",  # high
    "#9adeff",  # very high
]
C_FUTURE = "#1a1a24"  # Darker than empty — day hasn't happened yet


def _section(title: str, width: int = 44) -> str:
    """Build a colored section header with horizontal rule."""
    rule = "\u2500"
    prefix = f"{rule}{rule} {title} "
    fill = rule * max(0, width - len(prefix))
    return f"[bold {C_ACCENT}]{prefix}{fill}[/bold {C_ACCENT}]"


def _val(n: int | float | str, color: str = C_BRIGHT) -> str:
    """Format a numeric value with color."""
    return f"[bold {color}]{n}[/bold {color}]"


def _label(text: str) -> str:
    """Format a label in dim color."""
    return f"[{C_DIM}]{text}[/{C_DIM}]"


def _format_time(seconds: int) -> str:
    """Format seconds into a human-readable time string."""
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"
    if seconds >= 60:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s"
    return f"{seconds}s"


def _pct_color(pct: float) -> str:
    """Pick a color for a retention percentage."""
    if pct >= 90:
        return C_GOOD
    if pct >= 80:
        return "#a8d86e"  # yellow-green
    if pct >= 70:
        return C_HARD
    return C_RELEARN


def _retention_meter(pct: float) -> str:
    """Render a visual retention meter."""
    width = 20
    filled = max(0, min(width, int(pct / 100 * width)))
    empty = width - filled
    color = _pct_color(pct)
    block = "\u2588"
    shade = "\u2591"
    return f"[{color}]{block * filled}[/{color}][{C_DIM}]{shade * empty}[/{C_DIM}]"


def _get_deck_ids(col: "Collection", deck_name: str) -> list[int]:
    """Get all deck IDs for a deck and its children."""
    prefix = deck_name + "::"
    ids: list[int] = []
    for d in col.decks.all_names_and_ids():
        if d.name == deck_name or d.name.startswith(prefix):
            ids.append(d.id)
    return ids


def _did_filter(deck_ids: list[int] | None, card_alias: str = "c") -> str:
    """Build SQL WHERE clause for deck filtering."""
    if deck_ids is None:
        return ""
    id_list = ",".join(str(d) for d in deck_ids)
    return f" AND {card_alias}.did IN ({id_list})"


# ── Heatmap Widget ──────────────────────────────────────────────


class ReviewHeatmap(Widget):
    """28-day review heatmap — vertical layout (7 rows × 4 cols).

    Rows = days of the week, columns = weeks.
    Reads top-to-bottom within each column, then left-to-right.
    """

    DEFAULT_CSS = """
    ReviewHeatmap {
        height: auto;
    }
    """

    ROWS = 7  # days of week
    COLS = 4  # weeks
    CELL_W = 2  # "██" display width per cell (no gap)
    LABEL_W = 8  # "    Mon " prefix width (4 spaces + 3 char name + 1 space)

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._data: dict[int, int] = {}
        self._max_count: int = 0
        self._hover_info: str = ""

    def set_data(self, data: dict[int, int]) -> None:
        """Set the review data (day_offset -> review count)."""
        self._data = data
        self._max_count = max(data.values(), default=0)
        self._hover_info = ""
        self.refresh(layout=True)

    def _color_for(self, count: int) -> str:
        """Map a review count to a heatmap color."""
        if count == 0:
            return HEAT_COLORS[0]
        if self._max_count <= 0:
            return HEAT_COLORS[1]
        ratio = count / self._max_count
        if ratio > 0.75:
            return HEAT_COLORS[5]
        if ratio > 0.50:
            return HEAT_COLORS[4]
        if ratio > 0.25:
            return HEAT_COLORS[3]
        if ratio > 0.10:
            return HEAT_COLORS[2]
        return HEAT_COLORS[1]

    def _grid_start_offset(self) -> int:
        """Offset from today to the Monday of 3 weeks ago (grid origin)."""
        return -(datetime.now().weekday() + 21)

    def _offset(self, row: int, col: int) -> int:
        """Day offset (relative to today) for a given grid position."""
        return self._grid_start_offset() + col * 7 + row

    def render(self) -> str:
        """Render the 7x4 vertical heatmap grid.

        Rows are always Mon-Sun.  Columns are weeks (oldest left,
        newest right).  Today lands at (today_weekday, 3).  Days after
        today in the last column render as empty.
        """
        block = "\u2588\u2588"
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        lines: list[str] = []

        for row in range(self.ROWS):
            line = f"    [{C_DIM}]{day_names[row]}[/{C_DIM}] "
            for col in range(self.COLS):
                offset = self._offset(row, col)
                if offset > 0:
                    # Future day — visually distinct from "0 reviews"
                    line += f"[{C_FUTURE}]{block}[/{C_FUTURE}]"
                else:
                    count = self._data.get(offset, 0)
                    color = self._color_for(count)
                    line += f"[{color}]{block}[/{color}]"
            lines.append(line)

        # Hover info (always present to keep height stable)
        if self._hover_info:
            lines.append(f"    {self._hover_info}")
        else:
            lines.append(f"    [{C_DIM}]hover for details[/{C_DIM}]")

        return "\n".join(lines)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Show review count for the hovered cell."""
        row = event.y
        if row < 0 or row >= self.ROWS:
            if self._hover_info:
                self._hover_info = ""
                self.refresh()
            return

        col = (event.x - self.LABEL_W) // self.CELL_W
        if col < 0 or col >= self.COLS:
            if self._hover_info:
                self._hover_info = ""
                self.refresh()
            return

        offset = self._offset(row, col)
        if offset > 0:
            # Future day — no info to show
            if self._hover_info:
                self._hover_info = ""
                self.refresh()
            return

        count = self._data.get(offset, 0)
        dt = datetime.now() + timedelta(days=offset)
        date_str = dt.strftime("%a %b %d")

        new_info = (
            f"[{C_DIM}]{date_str}[/{C_DIM}]  "
            f"[bold {C_BRIGHT}]{count}[/bold {C_BRIGHT}] "
            f"[{C_DIM}]reviews[/{C_DIM}]"
        )
        if new_info != self._hover_info:
            self._hover_info = new_info
            self.refresh()

    def on_leave(self, event: events.Leave) -> None:
        """Clear hover info when mouse leaves."""
        if self._hover_info:
            self._hover_info = ""
            self.refresh()


# ── Forecast Chart Widget ──────────────────────────────────────


class ForecastChart(Widget):
    """7-day forecast bar chart with day labels and hover details."""

    DEFAULT_CSS = """
    ForecastChart {
        height: auto;
    }
    """

    # Bar height in rows (excluding label row and hover row)
    BAR_HEIGHT = 6
    COL_W = 7  # width per column: "Thu 18 " = 7 chars
    INDENT = 4  # leading spaces (visual indent in rendered content)

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._counts: list[int] = [0] * 7
        self._labels: list[str] = [""] * 7  # "Thu 18" style
        self._max_count: int = 0
        self._hover_info: str = ""

    def set_data(self, counts: list[int], labels: list[str]) -> None:
        """Set forecast data.

        Args:
            counts: List of 7 due counts (day+1 through day+7).
            labels: List of 7 labels like "Thu 18".
        """
        self._counts = counts
        self._labels = labels
        self._max_count = max(counts, default=0)
        self._hover_info = ""
        self.refresh(layout=True)

    def render(self) -> str:
        """Render vertical bar chart with labels and hover."""
        lines: list[str] = []
        block = "\u2588\u2588"

        indent = " " * self.INDENT

        if self._max_count == 0:
            # No data — show placeholder
            lines.append(f"{indent}[{C_DIM}]No upcoming reviews[/{C_DIM}]")
            lines.append("")
            return "\n".join(lines)

        # Center bars within each column
        bar_w = 2  # "██" display width
        pad_l = (self.COL_W - bar_w) // 2
        pad_r = self.COL_W - bar_w - pad_l

        # Build bar columns (bottom-up, rendered top-down)
        for row in range(self.BAR_HEIGHT, 0, -1):
            line = indent
            threshold = row / self.BAR_HEIGHT
            for i in range(7):
                ratio = self._counts[i] / self._max_count if self._max_count > 0 else 0
                if ratio >= threshold:
                    # Color based on bar height at this position
                    level = min(
                        len(BAR_GRADIENT) - 1,
                        int(ratio * (len(BAR_GRADIENT) - 1)),
                    )
                    color = BAR_GRADIENT[level]
                    line += " " * pad_l + f"[{color}]{block}[/{color}]" + " " * pad_r
                else:
                    line += " " * self.COL_W
            lines.append(line)

        # Count labels under each bar
        count_line = indent
        for i in range(7):
            cnt_str = str(self._counts[i])
            padded = cnt_str.center(self.COL_W)
            count_line += f"[{C_BRIGHT}]{padded}[/{C_BRIGHT}]"
        lines.append(count_line)

        # Day labels: "Thu 18" style
        label_line = indent
        for i in range(7):
            padded = self._labels[i].center(self.COL_W)
            label_line += f"[{C_DIM}]{padded}[/{C_DIM}]"
        lines.append(label_line)

        # Hover info
        if self._hover_info:
            lines.append(f"{indent}{self._hover_info}")
        else:
            lines.append(f"{indent}[{C_DIM}]hover for details[/{C_DIM}]")

        return "\n".join(lines)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Show count details for the hovered column."""
        col_idx = (event.x - self.INDENT) // self.COL_W
        if col_idx < 0 or col_idx > 6:
            if self._hover_info:
                self._hover_info = ""
                self.refresh()
            return

        cnt = self._counts[col_idx]
        label = self._labels[col_idx]
        new_info = (
            f"[{C_DIM}]{label}[/{C_DIM}]  "
            f"[bold {C_BRIGHT}]{cnt}[/bold {C_BRIGHT}] "
            f"[{C_DIM}]cards due[/{C_DIM}]"
        )
        if new_info != self._hover_info:
            self._hover_info = new_info
            self.refresh()

    def on_leave(self, event: events.Leave) -> None:
        """Clear hover info when mouse leaves."""
        if self._hover_info:
            self._hover_info = ""
            self.refresh()


# ── Stats Screen ────────────────────────────────────────────────


class StatsScreen(Screen[None]):
    """Screen displaying detailed review statistics."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "app.quit", "Quit"),
        Binding("d", "toggle_deck", "Toggle Deck/All"),
    ]

    def __init__(
        self,
        deck_id: int | None = None,
        deck_name: str | None = None,
    ) -> None:
        super().__init__()
        self._deck_id = deck_id
        self._deck_name = deck_name
        # Default to All Decks; restore remembered preference if a deck is available
        self._show_all = True

    @property
    def clanki_app(self) -> "ClankiApp":
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        scope_text = self._scope_label()

        yield Static(
            "[dim]d[/dim] toggle deck/all  [dim]Esc[/dim] back  [dim]q[/dim] quit",
            classes="help-text footer-bar",
            markup=True,
        )
        yield Container(
            Vertical(
                Static(
                    scope_text,
                    id="stats-header",
                    classes="header-bar",
                    markup=True,
                ),
                VerticalScroll(
                    Static(id="stats-content", markup=True),
                    ForecastChart(id="forecast-chart"),
                    Static(id="stats-mid", markup=True),
                    ReviewHeatmap(id="review-heatmap"),
                    Static(id="stats-bottom", markup=True),
                    id="stats-scroll",
                ),
                classes="content-column",
            ),
            classes="centered-screen",
        )

    def _scope_label(self) -> str:
        scope = "All Decks" if self._show_all else (self._deck_name or "Unknown")
        hint = ""
        if self._deck_name:
            hint = f"  [{C_DIM}]d to toggle[/{C_DIM}]"
        return f"[bold]Statistics[/bold]  [{C_ACCENT}]{scope}[/{C_ACCENT}]{hint}"

    async def on_mount(self) -> None:
        # Restore remembered all/deck preference
        if self._deck_name is not None:
            self._show_all = self.clanki_app.state.stats_show_all
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        col = self.clanki_app.state.col
        if col is None:
            try:
                self.query_one("#stats-content", Static).update(
                    f"[{C_DIM}]Collection not open.[/{C_DIM}]"
                )
            except Exception:
                pass
            return

        deck_ids: list[int] | None = None
        if not self._show_all and self._deck_name is not None:
            deck_ids = _get_deck_ids(col, self._deck_name)
            if not deck_ids:
                deck_ids = None

        did = _did_filter(deck_ids)

        try:
            cutoff = col.sched.day_cutoff
            today = col.sched.today
        except Exception:
            cutoff = int(time.time())
            today = 0

        # Each section is independently error-handled so one failure
        # doesn't prevent the rest of the screen from updating.

        try:
            top_lines = self._build_top_stats(col, deck_ids, did, cutoff, today)
            w = self.query_one("#stats-content", Static)
            w.update("\n".join(top_lines))
            w.refresh(layout=True)
        except Exception:
            pass

        try:
            forecast_counts, forecast_labels = self._build_forecast_data(col, today, deck_ids)
            self.query_one("#forecast-chart", ForecastChart).set_data(
                forecast_counts, forecast_labels
            )
        except Exception:
            pass

        try:
            mid_lines = self._build_bottom_stats()
            w = self.query_one("#stats-mid", Static)
            w.update("\n".join(mid_lines))
            w.refresh(layout=True)
        except Exception:
            pass

        try:
            heatmap_data = self._build_heatmap_data(col, cutoff, did)
            self.query_one("#review-heatmap", ReviewHeatmap).set_data(heatmap_data)
        except Exception:
            pass

        try:
            growth_lines = self._build_after_heatmap_stats(col, did, deck_ids)
            w = self.query_one("#stats-bottom", Static)
            w.update("\n".join(growth_lines))
            w.refresh(layout=True)
        except Exception:
            pass

        try:
            self.query_one("#stats-header", Static).update(self._scope_label())
        except Exception:
            pass

    def _build_top_stats(
        self,
        col: "Collection",
        deck_ids: list[int] | None,
        did: str,
        cutoff: int,
        today: int,
    ) -> list[str]:
        """Build stat lines for sections above the heatmap."""
        lines: list[str] = []

        lines.append("")
        lines.append(_section("Today"))
        lines.extend(self._today_stats(col, cutoff, did))

        lines.append("")
        lines.append(_section("Session"))
        lines.extend(self._session_stats())

        lines.append("")
        lines.append(_section("Streaks"))
        lines.extend(self._streak_stats(col, cutoff, did))

        lines.append("")
        lines.append(_section("Due"))
        lines.extend(self._due_stats(col, today, deck_ids))

        lines.append("")
        lines.append(_section("Card States"))
        lines.extend(self._card_state_stats(col, deck_ids))

        lines.append("")
        lines.append(_section("Retention"))
        lines.extend(self._retention_stats(col, did))

        lines.append("")
        lines.append(_section("Forecast"))

        return lines

    def _build_heatmap_data(self, col: "Collection", cutoff: int, did: str) -> dict[int, int]:
        """Query review counts per day for the last 28 days."""
        try:
            # Use a reference 28 days before the start of today so that
            # all timestamp differences are positive.  This avoids the
            # SQLite CAST-truncates-toward-zero bug that miscounts days
            # for negative offsets (yesterday's reviews counted as today).
            day_start = cutoff - 86400
            ref = day_start - 28 * 86400
            rows = col.db.all(
                "SELECT"
                " CAST((r.id/1000-?)/86400 AS INTEGER) as d,"
                " COUNT(*)"
                " FROM revlog r"
                " JOIN cards c ON r.cid=c.id"
                f" WHERE r.id>?{did}"
                " GROUP BY d",
                ref,
                (int(time.time()) - 28 * 86400) * 1000,
            )
            # d values are 0..28 (ref-relative); convert to -27..0
            return {d - 28: count for d, count in rows if d <= 28}
        except Exception:
            return {}

    def _build_forecast_data(
        self,
        col: "Collection",
        today: int,
        deck_ids: list[int] | None,
    ) -> tuple[list[int], list[str]]:
        """Query forecast counts and build labels for next 7 days."""
        counts = [0] * 7
        labels: list[str] = []
        now = datetime.now()

        for i in range(7):
            dt = now + timedelta(days=i + 1)
            labels.append(dt.strftime("%a %d"))

        try:
            dc = ""
            if deck_ids:
                dc = " AND did IN (" + ",".join(str(d) for d in deck_ids) + ")"

            rows = col.db.all(
                "SELECT due-?, COUNT(*) FROM cards"
                f" WHERE queue=2 AND due>? AND due<=?{dc}"
                " GROUP BY due-?",
                today,
                today,
                today + 7,
                today,
            )
            for offset, cnt in rows:
                if 1 <= offset <= 7:
                    counts[offset - 1] = cnt
        except Exception:
            pass

        return counts, labels

    def _build_bottom_stats(self) -> list[str]:
        """Build the Reviews section header above the heatmap."""
        return ["", _section("Reviews (28 days)")]

    def _build_after_heatmap_stats(
        self,
        col: "Collection",
        did: str,
        deck_ids: list[int] | None,
    ) -> list[str]:
        """Build stat lines that appear after the heatmap."""
        lines: list[str] = []

        lines.append("")
        lines.append(_section("Growth (30 days)"))
        lines.extend(self._growth_stats(col, did, deck_ids))
        lines.append("")

        return lines

    # ── Today ────────────────────────────────────────────────────

    def _today_stats(self, col: "Collection", cutoff: int, did: str) -> list[str]:
        lines: list[str] = []
        try:
            rows = col.db.all(
                "SELECT r.type, COUNT(*), SUM(r.time)"
                " FROM revlog r"
                " JOIN cards c ON r.cid = c.id"
                f" WHERE r.id > ?{did}"
                " GROUP BY r.type",
                cutoff * 1000,
            )
            tc: dict[int, int] = {}
            tt: dict[int, int] = {}
            for rtype, cnt, ms in rows:
                tc[rtype] = cnt
                tt[rtype] = ms or 0

            new = tc.get(0, 0)
            rev = tc.get(1, 0)
            rel = tc.get(2, 0)
            lrn = tc.get(3, 0)
            total = sum(tc.values())
            secs = sum(tt.values()) // 1000
            avg = secs / total if total > 0 else 0

            lines.append(
                f"  {_label('Reviews')}  {_val(total)}    "
                f"{_label('New')} {_val(new, C_NEW)}  "
                f"{_label('Learn')} {_val(lrn, C_LEARN)}  "
                f"{_label('Review')} {_val(rev, C_REVIEW)}  "
                f"{_label('Relearn')} {_val(rel, C_RELEARN)}"
            )
            lines.append(
                f"  {_label('Time')}  "
                f"{_val(_format_time(secs))}    "
                f"{_label('Avg')} {_val(f'{avg:.1f}s', C_DIM)}"
                f"{_label('/card')}"
            )
        except Exception:
            lines.append(f"  {_label('Reviews')}  {_val(0)}    {_label('Time')}  {_val('0s')}")
        return lines

    # ── Session ──────────────────────────────────────────────────

    def _session_stats(self) -> list[str]:
        s = self.clanki_app.state.stats
        if s.reviewed == 0:
            return [f"  {_label('No cards reviewed this session')}"]
        return [
            f"  {_label('Reviewed')}  {_val(s.reviewed)}    "
            f"{_label('Again')} {_val(s.again_count, C_RELEARN)}  "
            f"{_label('Hard')} {_val(s.hard_count, C_HARD)}  "
            f"{_label('Good')} {_val(s.good_count, C_GOOD)}  "
            f"{_label('Easy')} {_val(s.easy_count, C_EASY)}"
        ]

    # ── Streaks ──────────────────────────────────────────────────

    def _streak_stats(self, col: "Collection", cutoff: int, did: str) -> list[str]:
        lines: list[str] = []
        try:
            base = cutoff - 86400
            rows = col.db.all(
                "SELECT DISTINCT"
                " CAST((r.id / 1000 - ?) / 86400 AS INTEGER)"
                " as d FROM revlog r"
                " JOIN cards c ON r.cid = c.id"
                f" WHERE 1=1{did}"
                " ORDER BY d DESC",
                base,
            )
            offsets = {r[0] for r in rows}

            if not offsets:
                lines.append(f"  {_label('Current')}  {_val(0)}    {_label('Longest')}  {_val(0)}")
                return lines

            # Current streak
            cur = 0
            start = 0 if 0 in offsets else (-1 if -1 in offsets else None)
            if start is not None:
                d = start
                while d in offsets:
                    cur += 1
                    d -= 1

            # Longest streak
            sd = sorted(offsets)
            longest = run = 1
            for i in range(1, len(sd)):
                if sd[i] == sd[i - 1] + 1:
                    run += 1
                else:
                    longest = max(longest, run)
                    run = 1
            longest = max(longest, run)

            lines.append(
                f"  {_label('Current')}  "
                f"{_val(f'{cur} days', C_STREAK)}    "
                f"{_label('Longest')}  {_val(f'{longest} days')}"
            )

            # Visual streak bar (last 14 days, filled = reviewed)
            streak_bar = "  "
            for i in range(-13, 1):
                if i in offsets:
                    streak_bar += f"[{C_STREAK}]\u2588[/{C_STREAK}]"
                else:
                    streak_bar += f"[{C_DIM}]\u2591[/{C_DIM}]"
            streak_bar += f"  [{C_DIM}]last 14d[/{C_DIM}]"
            lines.append(streak_bar)
        except Exception:
            lines.append(
                f"  {_label('Current')}  {_val('0 days')}    {_label('Longest')}  {_val('0 days')}"
            )
        return lines

    # ── Due ───────────────────────────────────────────────────────

    def _due_stats(
        self,
        col: "Collection",
        today: int,
        deck_ids: list[int] | None,
    ) -> list[str]:
        lines: list[str] = []
        try:
            dc = ""
            if deck_ids:
                dc = f" AND did IN ({','.join(str(d) for d in deck_ids)})"

            r = col.db.first(f"SELECT COUNT(*) FROM cards WHERE queue=1{dc}")
            learn_now = (r[0] if r else 0) or 0

            r = col.db.first(
                f"SELECT COUNT(*) FROM cards WHERE queue=2 AND due<=?{dc}",
                today,
            )
            rev_now = (r[0] if r else 0) or 0

            r = col.db.first(
                f"SELECT COUNT(*) FROM cards WHERE queue=2 AND due=?{dc}",
                today + 1,
            )
            tmrw = (r[0] if r else 0) or 0

            r = col.db.first(
                f"SELECT COUNT(*) FROM cards WHERE queue=2 AND due>? AND due<=?{dc}",
                today,
                today + 7,
            )
            wk = (r[0] if r else 0) or 0

            r = col.db.first(f"SELECT COUNT(*) FROM cards WHERE queue=0{dc}")
            new_cnt = (r[0] if r else 0) or 0

            now = learn_now + rev_now
            now_c = C_RELEARN if now > 0 else C_DIM

            lines.append(
                f"  {_label('Due now')}  {_val(now, now_c)}    "
                f"{_label('Tomorrow')}  {_val(tmrw)}    "
                f"{_label('Next 7d')}  {_val(wk)}"
            )
            lines.append(f"  {_label('New available')}  {_val(new_cnt, C_NEW)}")
        except Exception:
            lines.append(
                f"  {_label('Due now')}  {_val(0)}    "
                f"{_label('Tomorrow')}  {_val(0)}    "
                f"{_label('Next 7d')}  {_val(0)}"
            )
        return lines

    # ── Card States ──────────────────────────────────────────────

    def _card_state_stats(
        self,
        col: "Collection",
        deck_ids: list[int] | None,
    ) -> list[str]:
        lines: list[str] = []
        try:
            dc = ""
            if deck_ids:
                dc = f" AND did IN ({','.join(str(d) for d in deck_ids)})"

            rows = col.db.all(
                "SELECT"
                "  CASE"
                "    WHEN queue=-2 THEN 'buried'"
                "    WHEN queue=-1 THEN 'suspended'"
                "    WHEN queue=0 THEN 'new'"
                "    WHEN queue=1 THEN 'learning'"
                "    WHEN queue=2 AND ivl<21 THEN 'young'"
                "    WHEN queue=2 AND ivl>=21 THEN 'mature'"
                "    ELSE 'other'"
                "  END as state,"
                "  COUNT(*)"
                f" FROM cards WHERE 1=1{dc}"
                " GROUP BY state"
            )
            sm: dict[str, int] = {s: c for s, c in rows}

            new = sm.get("new", 0)
            learning = sm.get("learning", 0)
            young = sm.get("young", 0)
            mature = sm.get("mature", 0)
            susp = sm.get("suspended", 0)
            buried = sm.get("buried", 0)
            total = new + learning + young + mature + susp + buried

            lines.append(
                f"  {_label('New')} {_val(new, C_NEW)}   "
                f"{_label('Learning')} {_val(learning, C_LEARN)}   "
                f"{_label('Young')} {_val(young, C_YOUNG)}   "
                f"{_label('Mature')} {_val(mature, C_MATURE)}"
            )

            # Distribution bar
            if total > 0:
                w = 40
                parts = [
                    (new, C_NEW),
                    (learning, C_LEARN),
                    (young, C_YOUNG),
                    (mature, C_MATURE),
                ]
                bar_str = "  "
                block = "\u2588"
                for count, color in parts:
                    cols = max(
                        1 if count > 0 else 0,
                        round(count / total * w),
                    )
                    bar_str += f"[{color}]{block * cols}[/{color}]"
                lines.append(bar_str)

            if susp > 0 or buried > 0:
                extras = []
                if susp > 0:
                    extras.append(f"{_label('Suspended')} {_val(susp, C_SUSPEND)}")
                if buried > 0:
                    extras.append(f"{_label('Buried')} {_val(buried, C_BURIED)}")
                lines.append(f"  {'   '.join(extras)}")

        except Exception:
            lines.append(f"  {_label('No card data available')}")
        return lines

    # ── Retention ────────────────────────────────────────────────

    def _retention_stats(self, col: "Collection", did: str) -> list[str]:
        lines: list[str] = []
        try:
            ago = (int(time.time()) - 30 * 86400) * 1000
            row = col.db.first(
                "SELECT"
                "  COUNT(CASE WHEN r.ease>=2 THEN 1 END),"
                "  COUNT(*)"
                " FROM revlog r"
                " JOIN cards c ON r.cid=c.id"
                f" WHERE r.type=1 AND r.id>?{did}",
                ago,
            )
            if row and row[1] and row[1] > 0:
                passed = row[0] or 0
                total = row[1]
                pct = (passed / total) * 100
                color = _pct_color(pct)
                lines.append(
                    f"  {_label('30-day pass rate')}  "
                    f"{_val(f'{pct:.1f}%', color)}"
                    f"  {_label(f'({passed}/{total} reviews)')}"
                )
                lines.append(f"  {_retention_meter(pct)}")
            else:
                lines.append(f"  {_label('No review data in last 30 days')}")
        except Exception:
            lines.append(f"  {_label('No data')}")
        return lines

    # ── Growth ───────────────────────────────────────────────────

    def _growth_stats(
        self,
        col: "Collection",
        did: str,
        deck_ids: list[int] | None,
    ) -> list[str]:
        lines: list[str] = []
        try:
            ago = (int(time.time()) - 30 * 86400) * 1000

            dc = ""
            if deck_ids:
                dc = f" AND did IN ({','.join(str(d) for d in deck_ids)})"

            r = col.db.first(
                f"SELECT COUNT(*) FROM cards WHERE id>?{dc}",
                ago,
            )
            added = (r[0] if r else 0) or 0

            r = col.db.first(
                "SELECT COUNT(*) FROM revlog r"
                " JOIN cards c ON r.cid=c.id"
                f" WHERE r.ivl>=21 AND r.lastIvl<21 AND r.id>?{did}",
                ago,
            )
            matured = (r[0] if r else 0) or 0

            lines.append(
                f"  {_label('Added')}  "
                f"{_val(f'{added} cards', C_ADDED)}    "
                f"{_label('Matured')}  "
                f"{_val(f'{matured} cards', C_MATURED)}"
            )
        except Exception:
            lines.append(
                f"  {_label('Added')}  {_val('0 cards')}    {_label('Matured')}  {_val('0 cards')}"
            )
        return lines

    # ── Actions ──────────────────────────────────────────────────

    async def action_toggle_deck(self) -> None:
        if self._deck_name is None:
            return
        self._show_all = not self._show_all
        # Remember the preference for next time
        self.clanki_app.state.stats_show_all = self._show_all
        self._refresh_stats()

    async def action_back(self) -> None:
        self.app.pop_screen()

"""Animated ASCII logo widget for Clanki TUI.

Renders the Anki logo as colored ASCII art with a diagonal shimmer animation.
"""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static
from rich.style import Style
from rich.text import Text

from .logo_data import LOGO_DATA

# Animation constants
ANIMATION_INTERVAL = 0.02  # Seconds between animation frames (10ms)
SHIMMER_WIDTH = 12  # Width of the shimmer band (wider coverage)
PAUSE_FRAMES = 40  # Frames to pause between shimmer cycles (~5 seconds)


class AsciiLogo(Static):
    """Widget displaying an animated ASCII logo with diagonal shimmer."""

    DEFAULT_CSS = """
    AsciiLogo {
        width: auto;
        height: auto;
    }
    """

    # Reactive variable - changes trigger watch method
    shimmer_pos = reactive(-SHIMMER_WIDTH)

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._height = len(LOGO_DATA)
        self._width = len(LOGO_DATA[0]) if LOGO_DATA else 0
        # Shimmer starts off-screen and exits off-screen for smooth looping
        self._start_pos = -SHIMMER_WIDTH
        self._end_pos = self._width + self._height + SHIMMER_WIDTH
        self._pause_counter = 0

    def on_mount(self) -> None:
        """Start the shimmer animation when mounted."""
        self._render_frame()
        self.set_interval(ANIMATION_INTERVAL, self._advance_shimmer)

    def _advance_shimmer(self) -> None:
        """Move the shimmer diagonally with pause between cycles."""
        if self._pause_counter > 0:
            self._pause_counter -= 1
            return

        next_pos = self.shimmer_pos + 1
        if next_pos >= self._end_pos:
            # Start pause before next cycle
            self._pause_counter = PAUSE_FRAMES
            self.shimmer_pos = self._start_pos
        else:
            self.shimmer_pos = next_pos

    def watch_shimmer_pos(self, new_value: int) -> None:
        """React to shimmer position changes."""
        self._render_frame()

    def _render_frame(self) -> None:
        """Render the current animation frame."""
        text = Text()

        for y, row in enumerate(LOGO_DATA):
            for x, (char, r, g, b) in enumerate(row):
                # Diagonal position: x + y gives the diagonal line
                diag = x + y
                distance = abs(diag - self.shimmer_pos)

                if distance < SHIMMER_WIDTH:
                    # Shimmer intensity falls off with distance
                    intensity = 1.0 - (distance / SHIMMER_WIDTH)
                    boost = int(120 * intensity)
                    r = min(255, r + boost)
                    g = min(255, g + boost)
                    b = min(255, b + boost)

                style = Style(color=f"rgb({r},{g},{b})")
                text.append(char, style=style)

            if y < self._height - 1:
                text.append("\n")

        self.update(text)

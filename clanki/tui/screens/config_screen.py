"""Configuration screen for Clanki TUI.

This screen displays toggle settings for images, audio, autoplay,
and high contrast mode, using the same layout as the deck picker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ...config_store import load_config, save_config

if TYPE_CHECKING:
    from ..app import ClankiApp


class ConfigScreen(Screen[None]):
    """Screen for adjusting application settings."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("1", "toggle_images", "Images", show=False),
        Binding("2", "toggle_audio", "Audio", show=False),
        Binding("3", "toggle_autoplay", "Autoplay", show=False),
        Binding("4", "toggle_high_contrast", "High Contrast", show=False),
    ]

    @property
    def clanki_app(self) -> "ClankiApp":
        """Get the typed app instance."""
        from ..app import ClankiApp

        assert isinstance(self.app, ClankiApp)
        return self.app

    def compose(self) -> ComposeResult:
        state = self.clanki_app.state

        # Footer - full width, docked to bottom
        yield Static(
            "[dim]1-4[/dim] toggle  [dim]Esc[/dim] back",
            classes="help-text footer-bar",
            markup=True,
        )
        # Main content - centered with max-width (matches deck picker layout)
        yield Container(
            Vertical(
                Static("Settings", classes="header-bar"),
                Static(""),
                Static(
                    self._format_toggle("1", "Images", state.images_enabled),
                    id="opt-images",
                    markup=True,
                ),
                Static(
                    self._format_toggle("2", "Audio", state.audio_enabled),
                    id="opt-audio",
                    markup=True,
                ),
                Static(
                    self._format_toggle("3", "Autoplay", state.audio_autoplay),
                    id="opt-autoplay",
                    markup=True,
                ),
                Static(
                    self._format_toggle("4", "High Contrast", state.high_contrast),
                    id="opt-high-contrast",
                    markup=True,
                ),
                classes="content-column",
            ),
            classes="centered-screen",
        )

    @staticmethod
    def _format_toggle(key: str, label: str, enabled: bool) -> str:
        """Format a toggle line."""
        status = "[bold green]on[/bold green]" if enabled else "[bold red]off[/bold red]"
        return f"  [dim]{key}[/dim]  {label:<16s} {status}"

    def _save_and_refresh(self) -> None:
        """Persist current state to config and refresh displayed toggles."""
        state = self.clanki_app.state
        config = load_config()
        config.images_enabled = state.images_enabled
        config.audio_enabled = state.audio_enabled
        config.audio_autoplay = state.audio_autoplay
        config.high_contrast = state.high_contrast
        save_config(config)

        # Update toggle labels
        self.query_one("#opt-images", Static).update(
            self._format_toggle("1", "Images", state.images_enabled)
        )
        self.query_one("#opt-audio", Static).update(
            self._format_toggle("2", "Audio", state.audio_enabled)
        )
        self.query_one("#opt-autoplay", Static).update(
            self._format_toggle("3", "Autoplay", state.audio_autoplay)
        )
        self.query_one("#opt-high-contrast", Static).update(
            self._format_toggle("4", "High Contrast", state.high_contrast)
        )

    async def action_toggle_images(self) -> None:
        """Toggle image rendering."""
        self.clanki_app.state.images_enabled = not self.clanki_app.state.images_enabled
        self._save_and_refresh()

    async def action_toggle_audio(self) -> None:
        """Toggle audio playback."""
        self.clanki_app.state.audio_enabled = not self.clanki_app.state.audio_enabled
        self._save_and_refresh()

    async def action_toggle_autoplay(self) -> None:
        """Toggle audio autoplay."""
        self.clanki_app.state.audio_autoplay = not self.clanki_app.state.audio_autoplay
        self._save_and_refresh()

    async def action_toggle_high_contrast(self) -> None:
        """Toggle high contrast mode."""
        self.clanki_app.state.high_contrast = not self.clanki_app.state.high_contrast
        self._save_and_refresh()

    async def action_back(self) -> None:
        """Return to the previous screen."""
        self.app.pop_screen()

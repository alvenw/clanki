"""Configuration screen for Clanki TUI.

This screen displays toggle settings for images, audio, autoplay,
and high contrast mode, using the same layout as the deck picker.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ...config_store import load_config, save_config

if TYPE_CHECKING:
    from ..app import ClankiApp

# Descriptions for each option
_DESCS: dict[str, str] = {
    "images": "Render images inline in card views",
    "audio": "Enable audio playback for cards with sound",
    "autoplay": "Automatically play audio when a card is shown",
    "high_contrast": "Use higher contrast colors for readability",
}


class ConfigScreen(Screen[None]):
    """Screen for adjusting application settings."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("1", "toggle_images", "Images", show=False),
        Binding("2", "toggle_audio", "Audio", show=False),
        Binding("3", "toggle_autoplay", "Autoplay", show=False),
        Binding("4", "toggle_high_contrast", "High Contrast", show=False),
        Binding("5", "sync", "Sync", show=False),
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
            "[dim]1-4[/dim] toggle  [dim]5[/dim] sync  [dim]Esc[/dim] back",
            classes="help-text footer-bar",
            markup=True,
        )
        # Main content - centered with max-width (matches deck picker layout)
        yield Container(
            Vertical(
                Static("Settings", classes="header-bar"),
                Static(""),
                Static(
                    _format_option(
                        "1", "Images", state.images_enabled, _DESCS["images"]
                    ),
                    id="opt-images",
                    markup=True,
                ),
                Static(""),
                Static(
                    _format_option(
                        "2", "Audio", state.audio_enabled, _DESCS["audio"]
                    ),
                    id="opt-audio",
                    markup=True,
                ),
                Static(""),
                Static(
                    _format_option(
                        "3", "Autoplay", state.audio_autoplay, _DESCS["autoplay"]
                    ),
                    id="opt-autoplay",
                    markup=True,
                ),
                Static(""),
                Static(
                    _format_option(
                        "4",
                        "High Contrast",
                        state.high_contrast,
                        _DESCS["high_contrast"],
                    ),
                    id="opt-high-contrast",
                    markup=True,
                ),
                Static(""),
                Static(
                    "  [dim]5[/dim]  Sync with AnkiWeb  "
                    "[dim]\u21bb[/dim]\n"
                    "     [dim]Synchronize your collection with AnkiWeb[/dim]",
                    id="opt-sync",
                    markup=True,
                ),
                classes="content-column",
            ),
            classes="centered-screen",
        )

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
            _format_option("1", "Images", state.images_enabled, _DESCS["images"])
        )
        self.query_one("#opt-audio", Static).update(
            _format_option("2", "Audio", state.audio_enabled, _DESCS["audio"])
        )
        self.query_one("#opt-autoplay", Static).update(
            _format_option(
                "3", "Autoplay", state.audio_autoplay, _DESCS["autoplay"]
            )
        )
        self.query_one("#opt-high-contrast", Static).update(
            _format_option(
                "4",
                "High Contrast",
                state.high_contrast,
                _DESCS["high_contrast"],
            )
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

    async def action_sync(self) -> None:
        """Sync collection with AnkiWeb."""
        self.notify("Syncing...", severity="information")
        self.run_worker(self._sync_worker(), exclusive=True)

    async def _sync_worker(self) -> None:
        """Worker coroutine that performs sync in background."""
        from ...collection import close_collection, open_collection
        from ...config import default_profile, resolve_anki_base
        from ...sync import SyncResult, run_sync

        app = self.clanki_app
        collection_path = app.collection_path

        # Close the current collection
        if app.state.col is not None:
            close_collection(app.state.col)
            app.state.col = None

        try:
            anki_base = resolve_anki_base()
            profile = default_profile(anki_base)

            if profile is None:
                self.notify("No Anki profiles found", severity="error")
                return

            outcome = run_sync(
                collection_path=collection_path,
                anki_base=anki_base,
                profile=profile,
            )

            if outcome.result == SyncResult.SUCCESS:
                self.notify("Sync complete", severity="information")
            elif outcome.result == SyncResult.NO_CHANGES:
                self.notify("Already in sync", severity="information")
            else:
                self.notify(f"Sync: {outcome.message}", severity="error")
        except Exception as exc:
            self.notify(f"Sync failed: {exc}", severity="error")
        finally:
            # Reopen collection
            try:
                app.state.col = open_collection(collection_path)
                app.state.media_dir = Path(app.state.col.media.dir())
            except Exception as exc:
                self.notify(f"Failed to reopen collection: {exc}", severity="error")

    async def action_back(self) -> None:
        """Return to the previous screen."""
        self.app.pop_screen()


def _format_option(key: str, label: str, enabled: bool, desc: str) -> str:
    """Format a toggle option with status indicator and description."""
    if enabled:
        status = "[bold #6cd97e]\u25cf on[/bold #6cd97e]"
    else:
        status = "[bold #e96c6c]\u25cb off[/bold #e96c6c]"
    toggle = f"  [dim]{key}[/dim]  {label:<16s} {status}"
    return f"{toggle}\n     [dim]{desc}[/dim]"

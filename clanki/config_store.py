"""Persistent configuration storage for Clanki.

This module provides a simple JSON-based config store with platform-aware
paths (XDG on Linux/macOS, %APPDATA% on Windows).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _get_config_dir() -> Path:
    """Get the platform-appropriate config directory.

    Returns:
        - Linux: $XDG_CONFIG_HOME/clanki or ~/.config/clanki
        - macOS: ~/Library/Application Support/clanki
        - Windows: %APPDATA%/clanki
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        # Linux and other Unix-like systems: use XDG
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            base = Path(xdg_config)
        else:
            base = Path.home() / ".config"

    return base / "clanki"


def _get_config_path() -> Path:
    """Get the path to the config file."""
    return _get_config_dir() / "config.json"


@dataclass
class Config:
    """Application configuration settings."""

    images_enabled: bool = True
    audio_enabled: bool = True
    audio_autoplay: bool = True
    expanded_decks: set[int] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "images_enabled": self.images_enabled,
            "audio_enabled": self.audio_enabled,
            "audio_autoplay": self.audio_autoplay,
            "expanded_decks": list(self.expanded_decks),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create config from dictionary."""
        expanded = data.get("expanded_decks", [])
        return cls(
            images_enabled=data.get("images_enabled", True),
            audio_enabled=data.get("audio_enabled", True),
            audio_autoplay=data.get("audio_autoplay", True),
            expanded_decks=set(expanded) if isinstance(expanded, list) else set(),
        )


_cached_config: Config | None = None


def load_config() -> Config:
    """Load configuration from disk.

    Returns:
        Config object with settings. Returns defaults if file doesn't exist
        or is invalid.
    """
    global _cached_config

    if _cached_config is not None:
        return _cached_config

    config_path = _get_config_path()

    if not config_path.exists():
        _cached_config = Config()
        return _cached_config

    try:
        with open(config_path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise TypeError("Config data must be a dictionary")
        _cached_config = Config.from_dict(data)
        return _cached_config
    except (json.JSONDecodeError, OSError, TypeError, KeyError, AttributeError):
        # Return defaults on any error
        _cached_config = Config()
        return _cached_config


def save_config(config: Config) -> bool:
    """Save configuration to disk.

    Args:
        config: Config object to save.

    Returns:
        True if save succeeded, False otherwise.
    """
    global _cached_config

    config_path = _get_config_path()

    try:
        # Create config directory if needed
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(config.to_dict(), f, indent=2)

        _cached_config = config
        return True
    except OSError:
        return False


def clear_config_cache() -> None:
    """Clear the cached config (useful for testing)."""
    global _cached_config
    _cached_config = None

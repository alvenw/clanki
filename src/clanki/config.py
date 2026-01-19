"""Profile discovery and collection path resolution for Clanki.

This module provides platform-aware path resolution for Anki profiles and
collections, supporting CLI overrides for flexible configuration.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_anki_base(override: str | Path | None = None) -> Path:
    """Resolve the Anki base directory for the current platform.

    Resolution priority:
    1. Explicit override parameter if provided
    2. ANKI_BASE environment variable if set
    3. Platform-specific default path

    Args:
        override: Optional explicit path to use instead of platform default.

    Returns:
        Path to the Anki2 base directory.

    Raises:
        ValueError: If the resolved path does not exist.
    """
    if override is not None:
        base = Path(override).expanduser()
        if not base.exists():
            raise ValueError(f"Anki base directory does not exist: {base}")
        return base

    # Check ANKI_BASE environment variable
    env_base = os.environ.get("ANKI_BASE")
    if env_base:
        base = Path(env_base).expanduser()
        if not base.exists():
            raise ValueError(f"ANKI_BASE directory does not exist: {base}")
        return base

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Anki2"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata) / "Anki2"
        else:
            base = Path.home() / "AppData" / "Roaming" / "Anki2"
    else:
        # Linux and other Unix-like systems
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            base = Path(xdg_data) / "Anki2"
        else:
            base = Path.home() / ".local" / "share" / "Anki2"

    if not base.exists():
        raise ValueError(f"Anki base directory does not exist: {base}")
    return base


# Special Anki folders that should not be treated as profiles
_EXCLUDED_FOLDERS = {"addons21", "logs", "crash.log", "prefs21.db"}


def list_profiles(anki_base: Path | None = None) -> list[str]:
    """List all available Anki profiles.

    Profiles are detected by scanning subdirectories for collection.anki2 files,
    excluding special Anki folders (addons21, logs, etc.).

    Args:
        anki_base: Optional explicit Anki base directory.

    Returns:
        List of profile names (directory names containing collection.anki2).
    """
    base = resolve_anki_base(anki_base)
    profiles = []

    for entry in base.iterdir():
        if entry.is_dir() and entry.name not in _EXCLUDED_FOLDERS:
            collection_path = entry / "collection.anki2"
            if collection_path.exists():
                profiles.append(entry.name)

    return sorted(profiles)


def default_profile(anki_base: Path | None = None) -> str | None:
    """Get the default (most recently used) profile.

    Uses the modification time of collection.anki2 files to determine
    which profile was most recently used.

    Args:
        anki_base: Optional explicit Anki base directory.

    Returns:
        Name of the most recently used profile, or None if no profiles exist.
    """
    base = resolve_anki_base(anki_base)
    profiles = list_profiles(base)

    if not profiles:
        return None

    if len(profiles) == 1:
        return profiles[0]

    # Find most recently modified collection.anki2
    most_recent = None
    most_recent_mtime = 0.0

    for profile in profiles:
        collection_path = base / profile / "collection.anki2"
        try:
            mtime = collection_path.stat().st_mtime
            if mtime > most_recent_mtime:
                most_recent_mtime = mtime
                most_recent = profile
        except OSError:
            continue

    return most_recent


def resolve_collection_path(
    anki_base: str | Path | None = None,
    profile: str | None = None,
    collection_path: str | Path | None = None,
) -> Path:
    """Resolve the path to an Anki collection database.

    Resolution priority:
    1. Explicit collection_path if provided
    2. Profile-based path if profile is provided
    3. Default profile (most recently used)

    Args:
        anki_base: Optional explicit Anki base directory.
        profile: Optional profile name to use.
        collection_path: Optional explicit path to collection.anki2 file.

    Returns:
        Resolved path to collection.anki2 file.

    Raises:
        ValueError: If no collection can be resolved (no profiles found,
            specified profile doesn't exist, etc.).
    """
    # Priority 1: Explicit collection path
    if collection_path is not None:
        path = Path(collection_path).expanduser()
        if not path.exists():
            raise ValueError(f"Collection file does not exist: {path}")
        return path

    # Resolve base for profile-based resolution
    base = resolve_anki_base(anki_base)

    # Priority 2: Specified profile
    if profile is not None:
        path = base / profile / "collection.anki2"
        if not path.exists():
            raise ValueError(f"Collection not found for profile '{profile}': {path}")
        return path

    # Priority 3: Default profile
    default = default_profile(base)
    if default is None:
        raise ValueError(f"No Anki profiles found in {base}")

    path = base / default / "collection.anki2"
    if not path.exists():
        raise ValueError(f"Collection not found for default profile '{default}': {path}")

    return path

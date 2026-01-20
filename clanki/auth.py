"""Sync authentication extraction from prefs21.db for Clanki.

This module provides functions to read sync credentials from Anki's
prefs21.db database, matching Anki Desktop behavior.
"""

from __future__ import annotations

import pickle
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Default sync endpoint base URL
DEFAULT_SYNC_BASE = "https://sync.ankiweb.net/"


@dataclass
class SyncAuth:
    """Sync authentication credentials extracted from prefs21.db."""

    hkey: str
    endpoint: str


class AuthNotFoundError(Exception):
    """Raised when sync auth cannot be found or extracted."""

    pass


def _get_prefs_path(anki_base: Path) -> Path:
    """Get the path to prefs21.db."""
    return anki_base / "prefs21.db"


def load_profiles(anki_base: Path) -> dict[str, dict]:
    """Load all profile data from prefs21.db.

    Args:
        anki_base: Path to the Anki2 base directory.

    Returns:
        Dictionary mapping profile name to profile data (pickled dict).
        The '_global' profile is excluded.

    Raises:
        AuthNotFoundError: If prefs21.db is missing or corrupt.
    """
    prefs_path = _get_prefs_path(anki_base)

    if not prefs_path.exists():
        raise AuthNotFoundError(
            f"prefs21.db not found: {prefs_path}\n"
            "Open Anki Desktop and sync once to create credentials."
        )

    profiles = {}
    try:
        conn = sqlite3.connect(str(prefs_path))
        try:
            cursor = conn.execute("SELECT name, data FROM profiles")
            for name, data in cursor:
                if name == "_global":
                    continue
                try:
                    profiles[name] = pickle.loads(data)
                except (pickle.UnpicklingError, Exception):
                    # Skip corrupt profile data
                    continue
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise AuthNotFoundError(
            f"Failed to read prefs21.db: {exc}\n"
            "The database may be corrupt. Try syncing from Anki Desktop."
        ) from exc

    return profiles


def _resolve_endpoint(profile_data: dict) -> str:
    """Resolve sync endpoint URL from profile data.

    Priority:
    1. currentSyncUrl if present and non-empty
    2. customSyncUrl if present and non-empty
    3. Build from hostNum if present
    4. Default sync endpoint

    Args:
        profile_data: Decoded profile data dictionary.

    Returns:
        Sync endpoint URL.
    """
    # Priority 1: currentSyncUrl (modern Anki behavior)
    current_url = profile_data.get("currentSyncUrl")
    if current_url:
        return current_url.rstrip("/") + "/"

    # Priority 2: customSyncUrl (self-hosted servers)
    custom_url = profile_data.get("customSyncUrl")
    if custom_url:
        return custom_url.rstrip("/") + "/"

    # Priority 3: hostNum fallback (legacy)
    host_num = profile_data.get("hostNum")
    if host_num is not None:
        return f"https://sync{host_num}.ankiweb.net/sync/"

    # Priority 4: Default endpoint
    return DEFAULT_SYNC_BASE


def get_sync_auth(anki_base: Path, profile: str) -> SyncAuth | None:
    """Get sync authentication for a specific profile.

    Args:
        anki_base: Path to the Anki2 base directory.
        profile: Profile name to extract auth for.

    Returns:
        SyncAuth with hkey and endpoint, or None if auth is missing.

    Raises:
        AuthNotFoundError: If prefs21.db is missing/corrupt or profile not found.
    """
    profiles = load_profiles(anki_base)

    if profile not in profiles:
        available = ", ".join(profiles.keys()) or "none"
        raise AuthNotFoundError(
            f"Profile '{profile}' not found in prefs21.db.\n"
            f"Available profiles: {available}"
        )

    profile_data = profiles[profile]

    # Extract sync key
    sync_key = profile_data.get("syncKey")
    if not sync_key:
        # syncKey is missing - user hasn't synced yet
        return None

    # Resolve endpoint
    endpoint = _resolve_endpoint(profile_data)

    return SyncAuth(hkey=sync_key, endpoint=endpoint)


def get_sync_auth_or_raise(anki_base: Path, profile: str) -> SyncAuth:
    """Get sync authentication, raising if not available.

    This is a convenience wrapper around get_sync_auth that raises
    an AuthNotFoundError with guidance if auth is missing.

    Args:
        anki_base: Path to the Anki2 base directory.
        profile: Profile name to extract auth for.

    Returns:
        SyncAuth with hkey and endpoint.

    Raises:
        AuthNotFoundError: If auth is missing or unavailable.
    """
    auth = get_sync_auth(anki_base, profile)

    if auth is None:
        raise AuthNotFoundError(
            f"Sync credentials not found for profile '{profile}'.\n"
            "Open Anki Desktop and sync once to create credentials."
        )

    return auth

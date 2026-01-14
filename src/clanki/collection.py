"""Collection management for Clanki.

This module provides functions to open, close, and validate Anki collections
with proper lock handling and actionable error messages.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki.collection import Collection


class CollectionLockError(Exception):
    """Raised when the collection is locked by another process (usually Anki Desktop)."""

    pass


class CollectionNotFoundError(Exception):
    """Raised when the collection file does not exist."""

    pass


def validate_collection_path(path: str | Path) -> Path:
    """Validate that a collection path exists and is accessible.

    Args:
        path: Path to the collection.anki2 file.

    Returns:
        Validated Path object.

    Raises:
        CollectionNotFoundError: If the collection file does not exist.
        ValueError: If the path is not a file.
    """
    collection_path = Path(path).expanduser()

    if not collection_path.exists():
        raise CollectionNotFoundError(f"Collection file not found: {collection_path}")

    if not collection_path.is_file():
        raise ValueError(f"Collection path is not a file: {collection_path}")

    return collection_path


def open_collection(path: str | Path) -> Collection:
    """Open an Anki collection with lock-aware error handling.

    Args:
        path: Path to the collection.anki2 file.

    Returns:
        Open Collection object. Caller is responsible for calling close_collection().

    Raises:
        CollectionNotFoundError: If the collection file does not exist.
        CollectionLockError: If the collection is locked (Anki Desktop is running).
        RuntimeError: For other collection open failures.
    """
    from anki.collection import Collection as AnkiCollection

    validated_path = validate_collection_path(path)

    try:
        # Anki Collection requires a string path
        return AnkiCollection(str(validated_path))
    except Exception as exc:
        error_msg = str(exc).lower()

        # Check for lock-related errors
        # Anki Desktop shows: "Anki already open, or media currently syncing."
        if (
            "locked" in error_msg
            or "lock" in error_msg
            or "anki already open" in error_msg
        ):
            raise CollectionLockError(
                "Anki Desktop is currently open. Please close Anki and try again."
            ) from exc

        # Re-raise with context
        raise RuntimeError(
            f"Failed to open collection: {exc}\nPath: {validated_path}"
        ) from exc


def close_collection(col: Collection) -> None:
    """Close an Anki collection safely.

    Args:
        col: Collection object to close. Can be None (no-op).
    """
    if col is not None:
        with contextlib.suppress(Exception):
            col.close()

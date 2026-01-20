"""Sync orchestration for Clanki.

This module provides sync functionality matching Anki Desktop behavior,
using in-memory endpoint updates only (no prefs DB writes).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from anki.errors import Interrupted, SyncError, SyncErrorKind
from anki.sync_pb2 import SyncAuth as PbSyncAuth
from anki.sync_pb2 import SyncCollectionResponse, SyncStatusResponse

from .auth import AuthNotFoundError, SyncAuth, get_sync_auth_or_raise
from .collection import close_collection, open_collection

if TYPE_CHECKING:
    from anki.collection import Collection


class SyncResult(Enum):
    """Result of a sync operation."""

    SUCCESS = "success"
    NO_CHANGES = "no_changes"
    AUTH_FAILED = "auth_failed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class SyncOutcome:
    """Detailed outcome of a sync operation."""

    result: SyncResult
    message: str
    server_message: str | None = None


def _build_pb_auth(auth: SyncAuth) -> PbSyncAuth:
    """Convert local SyncAuth to protobuf SyncAuth.

    Args:
        auth: Local SyncAuth dataclass.

    Returns:
        Protobuf SyncAuth for Anki backend calls.
    """
    pb_auth = PbSyncAuth()
    pb_auth.hkey = auth.hkey
    pb_auth.endpoint = auth.endpoint
    return pb_auth


def _update_endpoint(auth: SyncAuth, new_endpoint: str) -> SyncAuth:
    """Create a new SyncAuth with updated endpoint.

    Args:
        auth: Original SyncAuth.
        new_endpoint: New endpoint URL from server.

    Returns:
        New SyncAuth with updated endpoint.
    """
    if new_endpoint:
        # Ensure trailing slash for consistency
        endpoint = new_endpoint.rstrip("/") + "/"
        return SyncAuth(hkey=auth.hkey, endpoint=endpoint)
    return auth


def run_sync(
    collection_path: str | Path,
    anki_base: Path,
    profile: str,
    log: Callable[[str], None] | None = None,
) -> SyncOutcome:
    """Run full sync orchestration matching Anki Desktop flow.

    This implements the sync flow:
    1. Check sync status and update endpoint if needed
    2. Run normal sync
    3. If full sync required, close and do full upload/download
    4. Sync media

    Args:
        collection_path: Path to collection.anki2 file.
        anki_base: Path to Anki2 base directory (for auth extraction).
        profile: Profile name to sync.
        log: Optional callback for progress logging.

    Returns:
        SyncOutcome with result and message.
    """
    if log is None:
        log = lambda msg: None  # noqa: E731

    col: Collection | None = None

    try:
        # Get sync auth from prefs21.db
        log("Retrieving sync credentials...")
        auth = get_sync_auth_or_raise(anki_base, profile)

        # Open collection
        log("Opening collection...")
        col = open_collection(collection_path)

        # Build protobuf auth
        pb_auth = _build_pb_auth(auth)

        # Step 1: Check sync status
        log("Checking sync status...")
        status = col.sync_status(pb_auth)

        # Update endpoint if server provides a new one
        if status.new_endpoint:
            log(f"Updating endpoint to: {status.new_endpoint}")
            auth = _update_endpoint(auth, status.new_endpoint)
            pb_auth = _build_pb_auth(auth)

        # Check if any sync is needed
        if status.required == SyncStatusResponse.Required.NO_CHANGES:
            log("No changes to sync.")
            close_collection(col)
            return SyncOutcome(
                result=SyncResult.NO_CHANGES,
                message="Collection is already in sync.",
            )

        # Step 2: Run collection sync
        log("Syncing collection...")
        output = col.sync_collection(pb_auth, sync_media=False)

        # Update endpoint again if server provides a new one
        if output.new_endpoint:
            log(f"Updating endpoint to: {output.new_endpoint}")
            auth = _update_endpoint(auth, output.new_endpoint)
            pb_auth = _build_pb_auth(auth)

        server_message = output.server_message if output.server_message else None

        # Step 3: Handle full sync if required
        if output.required in (
            SyncCollectionResponse.FULL_DOWNLOAD,
            SyncCollectionResponse.FULL_UPLOAD,
        ):
            upload = output.required == SyncCollectionResponse.FULL_UPLOAD
            action = "upload" if upload else "download"
            log(f"Full sync required: {action}...")

            # Close collection for full sync
            col.close_for_full_sync()

            # Perform full upload or download
            col.full_upload_or_download(
                auth=pb_auth,
                server_usn=output.server_media_usn,
                upload=upload,
            )

            # Reopen collection after full sync
            log("Reopening collection after full sync...")
            col.reopen(after_full_sync=True)

        # Step 4: Sync media
        log("Syncing media...")
        col.sync_media(pb_auth)

        log("Sync complete.")
        close_collection(col)
        col = None

        return SyncOutcome(
            result=SyncResult.SUCCESS,
            message="Sync completed successfully.",
            server_message=server_message,
        )

    except AuthNotFoundError as exc:
        return SyncOutcome(
            result=SyncResult.AUTH_FAILED,
            message=str(exc),
        )

    except SyncError as exc:
        if exc.kind == SyncErrorKind.AUTH:
            return SyncOutcome(
                result=SyncResult.AUTH_FAILED,
                message=(
                    "Sync authentication failed.\n"
                    "Please open Anki Desktop and sync to refresh credentials."
                ),
            )
        return SyncOutcome(
            result=SyncResult.ERROR,
            message=f"Sync error: {exc.message}",
        )

    except Interrupted:
        return SyncOutcome(
            result=SyncResult.CANCELLED,
            message="Sync was cancelled.",
        )

    except Exception as exc:
        return SyncOutcome(
            result=SyncResult.ERROR,
            message=f"Unexpected error during sync: {exc}",
        )

    finally:
        # Ensure collection is closed
        if col is not None:
            close_collection(col)

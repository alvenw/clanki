"""Auto-patch Anki dependencies when running subprocess tests.

This module is automatically imported when Python starts if tests/helpers
is in PYTHONPATH. It activates only when CLANKI_TEST_MODE=fake is set.

Environment variables for control:
    CLANKI_TEST_MODE: Set to "fake" to enable patching
    CLANKI_FAKE_PROFILE: Profile name to return (default: "FakeProfile")
    CLANKI_FAKE_SYNC_RESULT: "success", "no_changes", or "error"
    CLANKI_FAKE_DECK_COUNT: Number of due cards (default: 0 for empty deck)
"""

from __future__ import annotations

import os
import sys


def _apply_fake_env() -> None:
    """Apply fake environment patches if CLANKI_TEST_MODE=fake."""
    if os.environ.get("CLANKI_TEST_MODE") != "fake":
        return

    # Get environment settings
    fake_profile = os.environ.get("CLANKI_FAKE_PROFILE", "FakeProfile")
    fake_sync_result_str = os.environ.get("CLANKI_FAKE_SYNC_RESULT", "no_changes")
    fake_deck_count = int(os.environ.get("CLANKI_FAKE_DECK_COUNT", "0"))

    # We need to intercept clanki imports and patch them
    # Use a meta path finder to do this
    import importlib.abc
    import importlib.machinery
    from pathlib import Path
    from types import ModuleType
    from unittest.mock import MagicMock

    class FakeClankiLoader(importlib.abc.Loader):
        """Loader that patches clanki modules on load."""

        def __init__(self, original_spec):
            self.original_spec = original_spec

        def create_module(self, spec):
            return None  # Use default module creation

        def exec_module(self, module):
            # Let the original module execute first
            if self.original_spec.loader:
                self.original_spec.loader.exec_module(module)

            # Apply patches based on module name
            if module.__name__ == "clanki.config":
                _patch_config_module(module, fake_profile)
            elif module.__name__ == "clanki.collection":
                _patch_collection_module(module, fake_profile, fake_deck_count)
            elif module.__name__ == "clanki.sync":
                _patch_sync_module(module, fake_sync_result_str)
            elif module.__name__ == "clanki.cli":
                _patch_cli_module(module)

    class FakeClankiFinder(importlib.abc.MetaPathFinder):
        """Meta path finder that intercepts clanki module imports."""

        PATCHED_MODULES = {"clanki.config", "clanki.collection", "clanki.sync", "clanki.cli"}

        def find_spec(self, fullname, path, target=None):
            if fullname not in self.PATCHED_MODULES:
                return None

            # Find the original spec using the remaining finders
            for finder in sys.meta_path:
                if finder is self:
                    continue
                try:
                    spec = finder.find_spec(fullname, path, target)
                    if spec is not None:
                        # Wrap the loader to apply patches after loading
                        return importlib.machinery.ModuleSpec(
                            fullname,
                            FakeClankiLoader(spec),
                            origin=spec.origin,
                            is_package=spec.submodule_search_locations is not None,
                        )
                except (AttributeError, TypeError):
                    pass
            return None

    # Install the meta path finder at the beginning
    sys.meta_path.insert(0, FakeClankiFinder())


def _patch_config_module(module, fake_profile):
    """Patch clanki.config module."""
    from pathlib import Path

    original_resolve_anki_base = module.resolve_anki_base
    original_default_profile = module.default_profile
    original_resolve_collection_path = module.resolve_collection_path

    def fake_resolve_anki_base():
        return Path("/fake/anki")

    def fake_default_profile(anki_base=None):
        return fake_profile

    def fake_resolve_collection_path(anki_base, profile):
        return Path("/fake/anki") / profile / "collection.anki2"

    module.resolve_anki_base = fake_resolve_anki_base
    module.default_profile = fake_default_profile
    module.resolve_collection_path = fake_resolve_collection_path


def _patch_collection_module(module, fake_profile, fake_deck_count):
    """Patch clanki.collection module."""
    from tests.helpers.fake_cli_env import FakeCollection

    def fake_open_collection(path):
        return FakeCollection(profile=fake_profile, deck_count=fake_deck_count)

    def fake_close_collection(col):
        pass

    module.open_collection = fake_open_collection
    module.close_collection = fake_close_collection


def _patch_sync_module(module, fake_sync_result_str):
    """Patch clanki.sync module."""
    from tests.helpers.fake_cli_env import FakeSyncOutcome

    SyncResult = module.SyncResult

    def fake_run_sync(**kwargs):
        if fake_sync_result_str == "success":
            return FakeSyncOutcome(
                result=SyncResult.SUCCESS,
                message="Sync completed successfully.",
            )
        elif fake_sync_result_str == "error":
            return FakeSyncOutcome(
                result=SyncResult.AUTH_FAILED,
                message="Sync failed: authentication error",
            )
        else:  # no_changes (default)
            return FakeSyncOutcome(
                result=SyncResult.NO_CHANGES,
                message="Collection is already in sync.",
            )

    module.run_sync = fake_run_sync


def _patch_cli_module(module):
    """Patch clanki.cli module."""
    module._check_tui_available = lambda: False


# Auto-apply when this module is imported
_apply_fake_env()

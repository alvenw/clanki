"""Tests for auth.py - sync authentication extraction from prefs21.db."""

from pathlib import Path

import pytest

from clanki.auth import (
    AuthNotFoundError,
    SyncAuth,
    get_sync_auth,
    get_sync_auth_or_raise,
    load_profiles,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestLoadProfiles:
    """Tests for load_profiles function."""

    def test_load_profiles_excludes_global(self):
        """load_profiles should exclude the _global row."""
        profiles = load_profiles(FIXTURES_DIR)

        assert "_global" not in profiles
        assert "TestProfile" in profiles
        assert "CustomSyncProfile" in profiles
        assert "NoSyncProfile" in profiles

    def test_load_profiles_returns_dict_data(self):
        """load_profiles should return unpickled dict data for each profile."""
        profiles = load_profiles(FIXTURES_DIR)

        # TestProfile should have syncKey
        assert profiles["TestProfile"]["syncKey"] == "test_hkey_12345"
        assert profiles["TestProfile"]["hostNum"] == 3
        assert profiles["TestProfile"]["syncMedia"] is True

    def test_load_profiles_missing_db_raises_error(self, tmp_path):
        """load_profiles should raise AuthNotFoundError if prefs21.db is missing."""
        with pytest.raises(AuthNotFoundError) as exc_info:
            load_profiles(tmp_path)

        assert "prefs21.db not found" in str(exc_info.value)
        assert "Open Anki Desktop and sync once" in str(exc_info.value)


class TestGetSyncAuth:
    """Tests for get_sync_auth function."""

    def test_get_sync_auth_with_hostnum(self):
        """get_sync_auth should build endpoint from hostNum."""
        auth = get_sync_auth(FIXTURES_DIR, "TestProfile")

        assert auth is not None
        assert auth.hkey == "test_hkey_12345"
        assert auth.endpoint == "https://sync3.ankiweb.net/sync/"

    def test_get_sync_auth_current_url_takes_precedence(self):
        """currentSyncUrl should take precedence over hostNum."""
        auth = get_sync_auth(FIXTURES_DIR, "CustomSyncProfile")

        assert auth is not None
        assert auth.hkey == "url_profile_key"
        assert auth.endpoint == "https://custom.sync.server/sync/"

    def test_get_sync_auth_returns_none_when_no_sync_key(self):
        """get_sync_auth should return None if profile has no syncKey."""
        auth = get_sync_auth(FIXTURES_DIR, "NoSyncProfile")

        assert auth is None

    def test_get_sync_auth_profile_not_found(self):
        """get_sync_auth should raise AuthNotFoundError for unknown profile."""
        with pytest.raises(AuthNotFoundError) as exc_info:
            get_sync_auth(FIXTURES_DIR, "NonExistentProfile")

        assert "Profile 'NonExistentProfile' not found" in str(exc_info.value)
        assert "Available profiles:" in str(exc_info.value)


class TestGetSyncAuthOrRaise:
    """Tests for get_sync_auth_or_raise function."""

    def test_get_sync_auth_or_raise_returns_auth(self):
        """get_sync_auth_or_raise should return SyncAuth for valid profile."""
        auth = get_sync_auth_or_raise(FIXTURES_DIR, "TestProfile")

        assert isinstance(auth, SyncAuth)
        assert auth.hkey == "test_hkey_12345"

    def test_get_sync_auth_or_raise_raises_when_no_sync_key(self):
        """get_sync_auth_or_raise should raise with guidance when syncKey missing."""
        with pytest.raises(AuthNotFoundError) as exc_info:
            get_sync_auth_or_raise(FIXTURES_DIR, "NoSyncProfile")

        error_msg = str(exc_info.value)
        assert "Sync credentials not found for profile 'NoSyncProfile'" in error_msg
        assert "Open Anki Desktop and sync once" in error_msg

    def test_get_sync_auth_or_raise_propagates_profile_not_found(self):
        """get_sync_auth_or_raise should propagate AuthNotFoundError for unknown profile."""
        with pytest.raises(AuthNotFoundError) as exc_info:
            get_sync_auth_or_raise(FIXTURES_DIR, "NonExistentProfile")

        assert "Profile 'NonExistentProfile' not found" in str(exc_info.value)

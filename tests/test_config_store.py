"""Tests for config_store.py - persistent configuration storage."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from clanki.config_store import (
    Config,
    _get_config_dir,
    clear_config_cache,
    load_config,
    save_config,
)


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = Config()
        assert config.images_enabled is True
        assert config.audio_enabled is True
        assert config.audio_autoplay is True
        assert config.expanded_decks == set()

    def test_to_dict(self):
        """Config should serialize to dict."""
        config = Config(
            images_enabled=False,
            audio_enabled=False,
            audio_autoplay=False,
            expanded_decks={1, 2, 3},
        )
        data = config.to_dict()
        assert data["images_enabled"] is False
        assert data["audio_enabled"] is False
        assert data["audio_autoplay"] is False
        assert set(data["expanded_decks"]) == {1, 2, 3}

    def test_from_dict(self):
        """Config should deserialize from dict."""
        data = {
            "images_enabled": False,
            "audio_enabled": False,
            "audio_autoplay": False,
            "expanded_decks": [1, 2, 3],
        }
        config = Config.from_dict(data)
        assert config.images_enabled is False
        assert config.audio_enabled is False
        assert config.audio_autoplay is False
        assert config.expanded_decks == {1, 2, 3}

    def test_from_dict_missing_key(self):
        """Config should use defaults for missing keys."""
        data = {}
        config = Config.from_dict(data)
        assert config.images_enabled is True
        assert config.audio_enabled is True
        assert config.audio_autoplay is True
        assert config.expanded_decks == set()

    def test_from_dict_extra_keys(self):
        """Config should ignore extra keys."""
        data = {"images_enabled": False, "unknown_key": "value"}
        config = Config.from_dict(data)
        assert config.images_enabled is False
        # Audio settings should still be defaults
        assert config.audio_enabled is True
        assert config.audio_autoplay is True
        assert config.expanded_decks == set()

    def test_expanded_decks_roundtrip(self):
        """expanded_decks should survive serialization roundtrip."""
        original = Config(expanded_decks={100, 200, 300})
        data = original.to_dict()
        restored = Config.from_dict(data)
        assert restored.expanded_decks == {100, 200, 300}


class TestConfigDir:
    """Tests for config directory resolution."""

    def test_returns_path(self):
        """_get_config_dir should return a Path."""
        config_dir = _get_config_dir()
        assert isinstance(config_dir, Path)
        assert config_dir.name == "clanki"


class TestLoadSaveConfig:
    """Tests for load_config and save_config."""

    @pytest.fixture(autouse=True)
    def setup_temp_config(self, monkeypatch, tmp_path):
        """Set up a temporary config directory for each test."""
        # Clear cache before each test
        clear_config_cache()

        # Create temp config dir
        config_dir = tmp_path / "clanki"

        # Monkeypatch _get_config_dir to return our temp dir
        import clanki.config_store as config_module

        monkeypatch.setattr(config_module, "_get_config_dir", lambda: config_dir)

        yield config_dir

        # Clear cache after test
        clear_config_cache()

    def test_load_returns_defaults_when_no_file(self):
        """load_config should return defaults when config file doesn't exist."""
        config = load_config()
        assert config.images_enabled is True

    def test_save_creates_config_file(self, setup_temp_config):
        """save_config should create the config file and directory."""
        config = Config(images_enabled=False)
        result = save_config(config)
        assert result is True

        config_file = setup_temp_config / "config.json"
        assert config_file.exists()

    def test_save_and_load_roundtrip(self):
        """Saved config should be loadable."""
        # Clear cache to force re-read
        clear_config_cache()

        # Save config
        original = Config(images_enabled=False)
        save_config(original)

        # Clear cache to force re-read
        clear_config_cache()

        # Load config
        loaded = load_config()
        assert loaded.images_enabled is False

    def test_load_handles_invalid_json(self, setup_temp_config):
        """load_config should return defaults for invalid JSON."""
        config_file = setup_temp_config / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("not valid json {{{")

        clear_config_cache()
        config = load_config()
        assert config.images_enabled is True

    def test_load_handles_invalid_data(self, setup_temp_config):
        """load_config should return defaults for invalid data structure."""
        config_file = setup_temp_config / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('"just a string"')

        clear_config_cache()
        config = load_config()
        assert config.images_enabled is True

    def test_load_caches_config(self):
        """load_config should cache the result."""
        config1 = load_config()
        config2 = load_config()
        # Should be the same object due to caching
        assert config1 is config2

    def test_save_updates_cache(self):
        """save_config should update the cache."""
        # Initial load
        config1 = load_config()
        assert config1.images_enabled is True

        # Save new config
        new_config = Config(images_enabled=False)
        save_config(new_config)

        # Load again - should get cached version
        config2 = load_config()
        assert config2.images_enabled is False

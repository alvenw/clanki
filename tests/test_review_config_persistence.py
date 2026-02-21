"""Regression tests for review-screen config persistence.

The review screen toggles (images/audio) persist settings during a session.
These saves must not drop unrelated settings like high_contrast.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import clanki.config_store as config_store
from clanki.config_store import Config, clear_config_cache, load_config, save_config
from clanki.tui.screens.review import _persist_config_from_state


@dataclass
class _FakeState:
    images_enabled: bool = True
    audio_enabled: bool = True
    audio_autoplay: bool = True
    high_contrast: bool = False
    expanded_decks: set[int] = field(default_factory=set)


@pytest.fixture(autouse=True)
def _temp_config_dir(monkeypatch, tmp_path):
    clear_config_cache()
    config_dir = tmp_path / "clanki"
    monkeypatch.setattr(config_store, "_get_config_dir", lambda: config_dir)
    yield config_dir
    clear_config_cache()


def test_review_persist_keeps_high_contrast_and_expanded_decks():
    save_config(Config(high_contrast=True, expanded_decks={123}))
    clear_config_cache()

    state = _FakeState(
        images_enabled=False,
        audio_enabled=True,
        audio_autoplay=False,
        high_contrast=True,
        expanded_decks={123, 456},
    )
    _persist_config_from_state(state)
    clear_config_cache()

    config = load_config()
    assert config.images_enabled is False
    assert config.audio_enabled is True
    assert config.audio_autoplay is False
    assert config.high_contrast is True
    assert config.expanded_decks == {123, 456}


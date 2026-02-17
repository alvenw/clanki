"""TUI screens for Clanki."""

from .collection_lock import CollectionLockScreen
from .config_screen import ConfigScreen
from .deck_picker import DeckPickerScreen
from .done import DoneScreen
from .review import ReviewScreen
from .stats_screen import StatsScreen

__all__ = [
    "CollectionLockScreen",
    "ConfigScreen",
    "DeckPickerScreen",
    "DoneScreen",
    "ReviewScreen",
    "StatsScreen",
]

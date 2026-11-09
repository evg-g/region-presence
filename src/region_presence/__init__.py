"""Real-time region-presence classification (In A / In B / Outside)."""

from importlib.metadata import PackageNotFoundError, version

from .classifier import (
    Classification,
    ClassifierConfig,
    InvalidReadingError,
    Presence,
    PresenceClassifier,
)
from .config import ConfigError, SimConfig, load_config
from .simulation import Frame, Simulation

__all__ = [
    "Classification", "ClassifierConfig", "ConfigError", "Frame", "InvalidReadingError", "Presence",
    "PresenceClassifier", "SimConfig", "Simulation", "load_config",
]
try:
    __version__ = version("region-presence")
except PackageNotFoundError:  # running from a source tree that was not installed
    __version__ = "0+unknown"

"""Real-time region-presence classification (In A / In B / Outside)."""

from .classifier import Classification, ClassifierConfig, Presence, PresenceClassifier
from .config import ConfigError, SimConfig, load_config
from .simulation import Frame, Simulation

__all__ = [
    "Classification", "ClassifierConfig", "ConfigError", "Frame", "Presence",
    "PresenceClassifier", "SimConfig", "Simulation", "load_config",
]
__version__ = "1.0.0"

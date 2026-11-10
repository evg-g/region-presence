"""Every mistake in a config file is a ConfigError naming the section, key and value."""

import copy
import tomllib

import pytest

from region_presence import ConfigError, load_config
from region_presence.config import DEFAULT_CONFIG, from_dict


@pytest.fixture
def data():
    with DEFAULT_CONFIG.open("rb") as fh:
        return tomllib.load(fh)


def test_default_config_is_valid(data):
    cfg = from_dict(data)
    assert cfg.regions["A"]["center"] == (20.0, 20.0)
    assert cfg.path["closed"] is True


# (section, key, bad value, text expected in the message)
BAD_VALUES = [
    ("regions.A", "center", 5, "[regions.A] center = 5: expected [x, y]"),
    ("regions.A", "center", [1, 2, 3], "expected [x, y]"),
    ("regions.A", "center", [1, "2"], "[regions.A] center = '2': expected a number"),
    ("regions.A", "width", "20", "[regions.A] width = '20': expected a number"),
    ("regions.A", "width", float("nan"), "[regions.A] width = nan: must be a finite number"),
    ("regions.A", "width", 0, "[regions.A] width = 0: must be > 0"),
    ("regions.B", "rotation_deg", True, "[regions.B] rotation_deg = True: expected a number"),
    ("simulation", "dt", "0.1", "[simulation] dt = '0.1': expected a number"),
    ("simulation", "dt", 0, "[simulation] dt = 0.0: must be a finite number > 0"),
    ("simulation", "duration_s", float("inf"), "[simulation] duration_s = inf"),
    ("simulation", "duration_s", 0.05, "shorter than one sample"),
    ("simulation", "seed", "x", "[simulation] seed = 'x': expected a whole number"),
    ("simulation", "initial_state", "middle", "[simulation] initial_state = 'middle'"),
    ("sensor", "noise_std", float("nan"), "[sensor] noise_std = nan"),
    ("sensor", "sigma_multiplier", -1, "[sensor] sigma_multiplier = -1.0"),
    ("motion", "mean_speed", "1", "[motion] mean_speed = '1': expected a number"),
    ("motion", "speed_std", float("inf"), "[motion] speed_std = inf: must be a finite number"),
    ("motion", "max_speed", 1.0, "max_speed = 1.0"),
    ("path", "closed", "false", "[path] closed = 'false': expected true or false"),
    ("path", "points", 5, "[path] points = 5"),
    ("path", "points", [[0, 0], [1]], "[path] points[1] = [1]: expected [x, y]"),
]


@pytest.mark.parametrize(("section", "key", "value", "message"), BAD_VALUES,
                         ids=[f"{s}.{k}={v!r}" for s, k, v, _ in BAD_VALUES])
def test_bad_value_is_reported_by_section_key_and_value(data, section, key, value, message):
    bad = copy.deepcopy(data)
    table = bad
    for part in section.split("."):
        table = table[part]
    table[key] = value
    with pytest.raises(ConfigError) as info:
        from_dict(bad)
    assert message in str(info.value)


@pytest.mark.parametrize("section", ["simulation", "motion", "path", "regions"])
def test_section_that_is_not_a_table(data, section):
    data[section] = 5
    with pytest.raises(ConfigError, match=rf"\[{section}\] must be a table"):
        from_dict(data)


def test_missing_region_key(data):
    del data["regions"]["B"]["height"]
    with pytest.raises(ConfigError, match=r"\[regions.B\] missing key 'height'"):
        from_dict(data)


def test_error_from_a_file_names_the_file(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(DEFAULT_CONFIG.read_text().replace("width = 20", 'width = "20"'))
    with pytest.raises(ConfigError, match=r"bad\.toml: \[regions\.A\] width"):
        load_config(bad)


def test_directory_instead_of_a_file(tmp_path):
    with pytest.raises(ConfigError, match="cannot read config file"):
        load_config(tmp_path)

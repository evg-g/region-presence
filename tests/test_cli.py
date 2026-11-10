import sys

import pytest

from region_presence.cli import main
from region_presence.config import DEFAULT_CONFIG


def test_headless_run(capsys):
    assert main(["--headless", "--speedup", "0", "--duration", "60"]) == 0
    out = capsys.readouterr().out
    assert "In A" in out and "matches ground truth" in out


def test_bad_config_returns_error(capsys, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[simulation]\ndt = -1\n")
    assert main(["--headless", "-c", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("args", [
    ["--duration", "nan"], ["--duration", "inf"], ["--duration", "0"], ["--duration", "abc"],
    ["--speedup", "-1"], ["--speedup", "nan"],
])
def test_bad_arguments_are_rejected_before_running(capsys, args):
    with pytest.raises(SystemExit) as info:
        main(["--headless", *args])
    assert info.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_config_that_is_a_directory(capsys, tmp_path):
    assert main(["--headless", "-c", str(tmp_path)]) == 2
    assert "cannot read config file" in capsys.readouterr().err


def test_config_with_a_wrong_type(capsys, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(DEFAULT_CONFIG.read_text().replace("center = [20, 20]", "center = 5"))
    assert main(["--headless", "-c", str(bad)]) == 2
    assert "[regions.A] center = 5" in capsys.readouterr().err


@pytest.mark.filterwarnings("ignore")  # Agg cannot show a window and says so
def test_live_view_starts(monkeypatch):
    pytest.importorskip("matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # instead of opening a window, draw once: that runs the first animation step
    monkeypatch.setattr(plt, "show", lambda: plt.gcf().canvas.draw())
    assert main(["--duration", "5"]) == 0


def test_live_view_without_matplotlib(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)  # makes `import matplotlib` fail
    monkeypatch.delitem(sys.modules, "region_presence.live_view", raising=False)
    assert main(["--duration", "1"]) == 2
    err = capsys.readouterr().err
    assert "needs matplotlib" in err and "--headless" in err


def test_output_piped_into_a_command_that_stops_reading():
    """`region-presence --headless -v | head -1` must not print a traceback."""
    import subprocess

    proc = subprocess.Popen(
        [sys.executable, "-m", "region_presence", "--headless", "--verbose", "--speedup", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    proc.stdout.readline()
    proc.stdout.close()  # like `head` exiting after one line
    stderr = proc.stderr.read().decode()
    assert proc.wait(timeout=60) == 0
    assert "Traceback" not in stderr

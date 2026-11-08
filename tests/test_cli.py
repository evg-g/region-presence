from regionpresence.cli import main


def test_headless_run(capsys):
    assert main(["--headless", "--speedup", "0", "--duration", "60"]) == 0
    out = capsys.readouterr().out
    assert "In A" in out and "matches ground truth" in out


def test_bad_config_returns_error(capsys, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[simulation]\ndt = -1\n")
    assert main(["--headless", "-c", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


def test_save_animation(tmp_path):
    import pytest
    pytest.importorskip("matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    out = tmp_path / "demo.gif"
    assert main(["--save", str(out), "--duration", "5", "--speedup", "5"]) == 0
    assert out.stat().st_size > 0

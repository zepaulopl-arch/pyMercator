import subprocess


def test_cli_cfg_prints_header():
    out = subprocess.run(["python", "-m", "pymercator.cli", "cfg"], capture_output=True, text=True)
    assert "PYMERCATOR CFG" in out.stdout

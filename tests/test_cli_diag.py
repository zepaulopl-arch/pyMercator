import subprocess


def test_cli_diag_runs():
    out = subprocess.run(["python", "-m", "pymercator.cli", "diag"], capture_output=True, text=True)
    assert "PYMERCATOR DIAG" in out.stdout

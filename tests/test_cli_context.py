import json
from pathlib import Path

from pymercator.cli import main
from pymercator.market_context_sources import collect_external_source


def test_context_template_and_check_commands(tmp_path: Path, capsys):
    output = tmp_path / "market_context.json"

    template_exit = main(
        [
            "context",
            "template",
            "--output",
            str(output),
        ]
    )

    assert template_exit == 0
    assert output.exists()

    check_exit = main(
        [
            "context",
            "check",
            "--file",
            str(output),
        ]
    )

    assert check_exit == 0

    captured = capsys.readouterr()
    assert "Market context template written to:" in captured.out
    assert "PYMERCATOR MARKET CONTEXT CHECK" in captured.out
    assert "VALID" in captured.out
    assert "True" in captured.out


def test_context_sources_command_renders_source_diagnostics(tmp_path: Path, capsys):
    context = tmp_path / "latest_market_context.json"
    context.write_text(
        json.dumps(
            {
                "schema_version": "market_context.v2",
                "source_diagnostics": {
                    "auto": {
                        "source": "AUTO",
                        "status": "OK",
                        "last_update": "2026-06-04",
                        "items": 3,
                        "error": "",
                    },
                    "market": {
                        "source": "MARKET",
                        "status": "OK",
                        "last_update": "2026-06-04",
                        "items": 5,
                        "error": "",
                    },
                    "bcb": {
                        "source": "BCB",
                        "status": "FAIL",
                        "last_update": "",
                        "items": 0,
                        "error": "timeout",
                    },
                    "b3": {
                        "source": "B3",
                        "status": "OK",
                        "last_update": "2026-06-04",
                        "items": 79,
                        "error": "",
                    },
                    "cvm": {
                        "source": "CVM",
                        "status": "OK",
                        "last_update": "2026-06-04",
                        "items": 1,
                        "error": "",
                    },
                    "manual": {
                        "source": "MANUAL",
                        "status": "OK",
                        "last_update": "2026-06-04",
                        "items": 1,
                        "error": "",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["context", "sources", "--file", str(context)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "CONTEXT SOURCES" in output
    assert "SOURCE" in output
    assert "BCB" in output
    assert "FAIL" in output
    assert "timeout" in output


def test_context_refresh_updates_source_diagnostics(tmp_path: Path, monkeypatch, capsys):
    import pymercator.cli_context as context_mod

    context = tmp_path / "latest_market_context.json"
    context.write_text(
        json.dumps({"schema_version": "market_context.v2", "context_sources": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        context_mod,
        "collect_market_context_sources",
        lambda **kwargs: (
            {
                "bcb": {
                    "source": "BCB",
                    "status": "OK",
                    "last_update": "2026-06-04",
                    "items": 3,
                    "error": "",
                }
            },
            {},
        ),
    )

    exit_code = main(["context", "refresh", "--source", "BCB", "--file", str(context)])

    output = capsys.readouterr().out
    payload = json.loads(context.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "BCB" in output
    assert payload["source_diagnostics"]["bcb"]["status"] == "OK"
    assert payload["context_sources"]["bcb"] == "OK"


def test_not_implemented_source_is_explicit():
    diagnostic, data = collect_external_source("demo")

    assert diagnostic["status"] == "NOT_IMPLEMENTED"
    assert diagnostic["error"] == "connector not implemented"
    assert data == {}

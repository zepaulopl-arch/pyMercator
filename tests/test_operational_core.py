from __future__ import annotations

import json
from pathlib import Path

import pytest

import aurum.core as core
from aurum.cli import main


ROOT = Path(__file__).resolve().parents[1]


def _raw_payload() -> dict:
    signal_ts = "2026-06-05T12:00:00Z"
    return {
        "status": "OK",
        "profile": "CON",
        "list": "IBOV",
        "report": {
            "decisions": [
                {
                    "asset": {"ticker": "LONG1", "last_close": 100.0},
                    "permission": {"status": "READY"},
                    "ranking": {"context_score": 88.0},
                    "ref_price": 100.0,
                    "ref_date": "2026-06-05",
                    "ref_ts": signal_ts,
                    "reason": "ready long",
                },
                {
                    "asset": {"ticker": "OBS1", "last_close": 50.0},
                    "permission": {"status": "BLOCKED"},
                    "ranking": {"context_score": 74.0},
                    "ref_price": 50.0,
                    "ref_date": "2026-06-05",
                    "ref_ts": signal_ts,
                    "blocker_reasons": ["MODEL_WEAK"],
                },
            ]
        },
        "observation_candidates": [
            {
                "ticker": "OBS2",
                "score": 71.0,
                "class": "OBS_FAVORABLE",
                "reason": "watch long",
                "ref_price": 20.0,
                "ref_date": "2026-06-05",
                "ref_ts": signal_ts,
            }
        ],
        "short_candidates": [
            {
                "ticker": "SHORT1",
                "score": 91.0,
                "short_permission": "SHORT_READY",
                "executable": True,
                "reason": "ready short",
                "ref_price": 40.0,
                "ref_date": "2026-06-05",
                "ref_ts": signal_ts,
            },
            {
                "ticker": "SOBS1",
                "score": 66.0,
                "short_permission": "SHORT_BLOCKED",
                "executable": False,
                "reason": "borrow missing",
                "ref_price": 30.0,
                "ref_date": "2026-06-05",
                "ref_ts": signal_ts,
            },
        ],
        "short_observation_candidates": [
            {
                "ticker": "SOBS2",
                "score": 70.0,
                "short_permission": "SHORT_BLOCKED",
                "executable": False,
                "reason": "watch short",
                "ref_price": 10.0,
                "ref_date": "2026-06-05",
                "ref_ts": signal_ts,
            }
        ],
    }


def _many_obs_payload(count: int = 12) -> dict:
    decisions = []
    for index in range(count):
        score = 100 - index
        decisions.append(
            {
                "asset": {"ticker": f"OBS{index:02d}", "last_close": 10.0 + index},
                "permission": {"status": "BLOCKED"},
                "ranking": {"context_score": score},
                "ref_price": 10.0 + index,
                "ref_date": "2026-06-05",
                "reason": "ranking test",
            }
        )
    return {"status": "OK", "report": {"decisions": decisions}}


def _write_price(prices_dir: Path, ticker: str, latest: float) -> None:
    prices_dir.mkdir(parents=True, exist_ok=True)
    (prices_dir / f"{ticker}.SA.csv").write_text(
        "\n".join(
            [
                "date,open,high,low,close,volume",
                f"2026-06-05,{latest},{latest},{latest},{latest},1000",
                f"2026-06-08,{latest},{latest},{latest},{latest},1000",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _daily(tmp_path: Path) -> dict:
    return core.run_daily(
        profile="CON",
        list_name="IBOV",
        capital=100000.0,
        slots=10,
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        update=False,
        force=False,
        raw_payload=_raw_payload(),
    )


def _review(tmp_path: Path) -> dict:
    _daily(tmp_path)
    prices_dir = tmp_path / "prices"
    _write_price(prices_dir, "LONG1", 110.0)
    _write_price(prices_dir, "OBS1", 55.0)
    _write_price(prices_dir, "OBS2", 22.0)
    _write_price(prices_dir, "SHORT1", 36.0)
    _write_price(prices_dir, "SOBS1", 33.0)
    _write_price(prices_dir, "SOBS2", 9.0)
    return core.run_review(
        profile="CON",
        list_name="IBOV",
        review_date="2026-06-08",
        signals_dir=tmp_path / "signals",
        prices_dir=prices_dir,
    )


def test_daily_always_prints_four_tables(tmp_path: Path) -> None:
    snapshot = _daily(tmp_path)

    assert set(snapshot["tables"]) == set(core.TABLE_KEYS)
    assert [row["ticker"] for row in snapshot["tables"]["real_long"]] == ["LONG1"]
    assert [row["ticker"] for row in snapshot["tables"]["real_short"]] == ["SHORT1"]
    assert {row["ticker"] for row in snapshot["tables"]["obs_long"]} == {"OBS1", "OBS2"}
    assert {row["ticker"] for row in snapshot["tables"]["obs_short"]} == {"SOBS1", "SOBS2"}
    for title in core.TABLE_TITLES.values():
        assert title in snapshot["text"]


def test_daily_tables_are_aligned(tmp_path: Path) -> None:
    snapshot = _daily(tmp_path)

    header = core._daily_table_header()
    assert snapshot["text"].count(header) == 4
    assert "score=" not in snapshot["text"]
    assert "entry=" not in snapshot["text"]
    assert "notional=" not in snapshot["text"]


def test_daily_shown_items_not_confused_with_total_items(tmp_path: Path) -> None:
    snapshot = core.run_daily(
        profile="CON",
        list_name="IBOV",
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        update=False,
        display_limit=10,
        raw_payload=_many_obs_payload(),
    )

    rows = snapshot["tables"]["obs_long"]
    assert len(rows) == 12
    assert [row["ticker"] for row in rows[:10]] == [f"OBS{index:02d}" for index in range(10)]
    assert snapshot["counts"]["obs_long"] == 12
    assert snapshot["raw_counts"]["obs_long"] == 12
    assert snapshot["shown_counts"]["obs_long"] == 10
    assert "OBS LONG: shown_items=10 total_items=12 review_scope=FULL_SNAPSHOT" in snapshot["text"]
    assert "OBS LONG | TOP 10 OF 12" in snapshot["text"]
    assert "Full list saved in snapshot." in snapshot["text"]
    assert "snapshot_json=" in snapshot["text"]


def test_daily_saves_immutable_snapshot(tmp_path: Path) -> None:
    snapshot = _daily(tmp_path)
    path = Path(snapshot["files"]["snapshot_json"])

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "aurum_signal_snapshot.v1"
    with pytest.raises(FileExistsError):
        _daily(tmp_path)


def test_review_loads_previous_market_day_snapshot(tmp_path: Path) -> None:
    review = _review(tmp_path)

    assert review["signal_date"] == "2026-06-05"
    assert review["review_date"] == "2026-06-08"
    assert review["signal_source_file"].endswith("CON_IBOV_signal.json")


def test_review_always_prints_four_tables(tmp_path: Path) -> None:
    core.run_daily(
        profile="CON",
        list_name="IBOV",
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        update=False,
        raw_payload={"status": "OK", "report": {"decisions": []}},
    )

    review = core.run_review(
        profile="CON",
        list_name="IBOV",
        review_date="2026-06-08",
        signals_dir=tmp_path / "signals",
        prices_dir=tmp_path / "prices",
    )

    for title in core.REVIEW_TITLES.values():
        assert title in review["text"]
    assert review["text"].count("NO ITEMS") == 4


def test_review_uses_snapshot_total_items(tmp_path: Path) -> None:
    snapshot = core.run_daily(
        profile="CON",
        list_name="IBOV",
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        update=False,
        display_limit=10,
        raw_payload=_many_obs_payload(),
    )
    prices_dir = tmp_path / "prices"
    for index in range(12):
        _write_price(prices_dir, f"OBS{index:02d}", 11.0 + index)

    review = core.run_review(
        profile="CON",
        list_name="IBOV",
        review_date="2026-06-08",
        signals_dir=tmp_path / "signals",
        prices_dir=prices_dir,
        review_limit=10,
    )

    assert len(snapshot["tables"]["obs_long"]) == 12
    assert len(review["tables"]["obs_long"]) == 12
    assert review["summary"]["obs_long"]["total_items"] == 12
    assert review["summary"]["obs_long"]["shown_items"] == 10
    assert "OBS LONG REVIEW | TOP 10 OF 12" in review["text"]


def test_review_does_not_count_obs_as_final_operational_pnl(tmp_path: Path) -> None:
    core.run_daily(
        profile="CON",
        list_name="IBOV",
        capital=100000.0,
        slots=10,
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        update=False,
        raw_payload={
            "status": "OK",
            "observation_candidates": [
                {
                    "ticker": "OBS_ONLY",
                    "score": 90.0,
                    "class": "OBS_FAVORABLE",
                    "reason": "study setup",
                    "ref_price": 10.0,
                    "ref_date": "2026-06-05",
                }
            ],
        },
    )
    prices_dir = tmp_path / "prices"
    _write_price(prices_dir, "OBS_ONLY", 11.0)

    review = core.run_review(
        profile="CON",
        list_name="IBOV",
        review_date="2026-06-08",
        signals_dir=tmp_path / "signals",
        prices_dir=prices_dir,
    )

    assert review["observation_result"]["obs_total_pnl"] == 1000.0
    assert review["final"]["operational_pnl"] == 0.0
    assert review["final"]["paper_pnl"] == 1000.0
    assert review["final"]["final_verdict"] == "NO_REAL_TRADES"
    assert "FINAL TOTAL" not in review["text"]


def test_review_no_real_trades_final_verdict(tmp_path: Path) -> None:
    core.run_daily(
        profile="CON",
        list_name="IBOV",
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        update=False,
        raw_payload={"status": "OK", "report": {"decisions": []}},
    )

    review = core.run_review(
        profile="CON",
        list_name="IBOV",
        review_date="2026-06-08",
        signals_dir=tmp_path / "signals",
        prices_dir=tmp_path / "prices",
    )

    assert review["operational_result"]["real_trades"] == 0
    assert review["final"]["operational_pnl"] == 0.0
    assert review["final"]["final_verdict"] == "NO_REAL_TRADES"


def test_review_reviews_real_long(tmp_path: Path) -> None:
    review = _review(tmp_path)
    row = review["tables"]["real_long"][0]

    assert row["ticker"] == "LONG1"
    assert row["pnl"] == 1000.0
    assert row["would_pnl"] is None


def test_review_reviews_real_short(tmp_path: Path) -> None:
    review = _review(tmp_path)
    row = review["tables"]["real_short"][0]

    assert row["ticker"] == "SHORT1"
    assert row["pnl"] == 1000.0
    assert row["would_pnl"] is None


def test_review_reviews_obs_long(tmp_path: Path) -> None:
    review = _review(tmp_path)
    rows = {row["ticker"]: row for row in review["tables"]["obs_long"]}

    assert rows["OBS2"]["would_pnl"] == 1000.0
    assert rows["OBS2"]["pnl"] is None


def test_review_reviews_obs_short(tmp_path: Path) -> None:
    review = _review(tmp_path)
    rows = {row["ticker"]: row for row in review["tables"]["obs_short"]}

    assert rows["SOBS2"]["would_pnl"] == 1000.0
    assert rows["SOBS2"]["pnl"] is None


def test_obs_short_with_missing_entry_is_not_reviewable(tmp_path: Path) -> None:
    snapshot = core.run_daily(
        profile="CON",
        list_name="IBOV",
        capital=100000.0,
        slots=10,
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        prices_dir=tmp_path / "prices",
        update=False,
        raw_payload={
            "status": "OK",
            "short_observation_candidates": [
                {
                    "ticker": "MISSENTRY",
                    "score": 80.0,
                    "short_permission": "SHORT_BLOCKED",
                    "executable": False,
                    "reason": "watch short without price",
                }
            ],
        },
    )

    daily_row = snapshot["tables"]["obs_short"][0]
    assert daily_row["status"] == "NOT_REVIEWABLE"
    assert daily_row["quantity"] is None
    assert "missing entry price" in daily_row["reason"]

    review = core.run_review(
        profile="CON",
        list_name="IBOV",
        review_date="2026-06-08",
        signals_dir=tmp_path / "signals",
        prices_dir=tmp_path / "prices",
    )
    row = review["tables"]["obs_short"][0]

    assert row["review_status"] == "NOT_REVIEWABLE"
    assert row["return_pct"] is None
    assert row["would_pnl"] is None
    assert "missing entry price" in row["reason"]


def test_obs_short_with_entry_has_return_and_pnl(tmp_path: Path) -> None:
    review = _review(tmp_path)
    row = {item["ticker"]: item for item in review["tables"]["obs_short"]}["SOBS2"]

    assert row["entry_price"] == 10.0
    assert row["return_pct"] == 10.0
    assert row["would_pnl"] == 1000.0
    assert row["review_status"] == "GAIN"


def test_review_does_not_mix_real_and_obs(tmp_path: Path) -> None:
    review = _review(tmp_path)

    assert review["summary"]["real_long"]["real_pnl"] == 1000.0
    assert review["summary"]["obs_long"]["real_pnl"] == 0.0
    assert review["summary"]["real_short"]["would_pnl"] == 0.0
    assert review["summary"]["obs_short"]["would_pnl"] == 0.0


def test_summary_separates_real_and_observation(tmp_path: Path) -> None:
    review = _review(tmp_path)

    assert review["operational_result"]["real_long_pnl"] == 1000.0
    assert review["operational_result"]["real_short_pnl"] == 1000.0
    assert review["operational_result"]["real_total_pnl"] == 2000.0
    assert review["operational_result"]["real_trades"] == 2
    assert review["observation_result"]["obs_total_pnl"] == 2000.0
    assert review["observation_result"]["obs_verdict"] == "STUDY_ONLY"
    assert review["final"]["operational_pnl"] == 2000.0
    assert review["final"]["paper_pnl"] == 2000.0


def test_review_uses_per_slot_sizing(tmp_path: Path) -> None:
    review = _review(tmp_path)

    for rows in review["tables"].values():
        for row in rows:
            assert row["notional"] == 10000.0
            assert row["sizing_mode"] == "per_slot"


def test_review_shows_empty_tables_explicitly(tmp_path: Path) -> None:
    snapshot = core.run_daily(
        profile="CON",
        list_name="IBOV",
        signal_date="2026-06-05",
        signals_dir=tmp_path / "signals",
        update=False,
        raw_payload={"status": "OK", "report": {"decisions": []}},
    )

    assert snapshot["text"].count("NO ITEMS") == 4
    for title in core.TABLE_TITLES.values():
        assert title in snapshot["text"]


def test_weekly_evaluates_features(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "update_data", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(core, "build_features", lambda payload: {"status": "OK", "rows": 10})
    monkeypatch.setattr(core, "train_models", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(core, "evaluate_features", lambda record=False: {"status": "OPERABLE", "verdict": "BETTER"})
    monkeypatch.setattr(core, "evaluate_engines", lambda: {"best_engine": "ridge", "most_reliable_horizon": "D20"})

    payload = core.run_weekly(output=tmp_path / "weekly.txt")

    assert payload["feature_audit"]["status"] == "OPERABLE"
    assert "FEATURE AUDIT" in payload["text"]


def test_weekly_evaluates_engines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "update_data", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(core, "build_features", lambda payload: {"status": "OK", "rows": 10})
    monkeypatch.setattr(core, "train_models", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(core, "evaluate_features", lambda record=False: {"status": "OPERABLE", "verdict": "BETTER"})
    monkeypatch.setattr(core, "evaluate_engines", lambda: {"best_engine": "extratrees", "most_reliable_horizon": "D5"})

    payload = core.run_weekly(output=tmp_path / "weekly.txt")

    assert payload["engine_audit"]["best_engine"] == "extratrees"
    assert "ENGINE AUDIT" in payload["text"]


def test_commands_call_core_functions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    calls: dict[str, dict] = {}

    def fake_daily(**kwargs):
        calls["daily"] = kwargs
        return {"text": "CORE DAILY\n"}

    def fake_review(**kwargs):
        calls["review"] = kwargs
        return {"text": "CORE REVIEW\n"}

    def fake_weekly(**kwargs):
        calls["weekly"] = kwargs
        return {"text": "CORE WEEKLY\n"}

    monkeypatch.setattr(core, "run_daily", fake_daily)
    monkeypatch.setattr(core, "run_review", fake_review)
    monkeypatch.setattr(core, "run_weekly", fake_weekly)

    assert main(["daily", "--no-update", "--signals-dir", str(tmp_path / "signals")]) == 0
    assert main(["review", "--signals-dir", str(tmp_path / "signals")]) == 0
    assert main(["weekly", "--no-update", "--no-train", "--output", str(tmp_path / "weekly.txt")]) == 0

    output = capsys.readouterr().out
    assert "CORE DAILY" in output
    assert "CORE REVIEW" in output
    assert "CORE WEEKLY" in output
    assert calls["daily"]["update"] is False
    assert calls["daily"]["display_limit"] == 10
    assert "limit" not in calls["daily"]
    assert calls["review"]["signals_dir"] == str(tmp_path / "signals")
    assert calls["review"]["review_limit"] == 10
    assert calls["weekly"]["train"] is False

    for script in ("daily_signal.ps1", "daily_review.ps1", "weekly_train.ps1"):
        text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "from aurum.core import" in text
        assert "python -m aurum" not in text
        assert "-m aurum" not in text

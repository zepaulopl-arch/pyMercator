from datetime import date

from pymercator.pipeline import run_daily_pipeline
from pymercator.reports.json_report import daily_report_to_dict
from pymercator.update_freshness import build_data_freshness


def test_freshness_warns_for_stale_asset():
    freshness = build_data_freshness(
        [
            {
                "step": "prices_check",
                "status": "OK",
                "payload": {
                    "results": [
                        {"path": "data/prices/PETR4.SA.csv", "end_date": "2026-06-01"},
                        {"path": "data/prices/VALE3.SA.csv", "end_date": "2026-05-30"},
                    ]
                },
            },
            {
                "step": "indices_check",
                "status": "OK",
                "payload": {
                    "results": [
                        {"path": "data/indices/^BVSP.csv", "end_date": "2026-06-04"}
                    ]
                },
            },
        ],
        today=date(2026, 6, 4),
    )

    assert freshness["freshness_status"] == "WARNING"
    assert freshness["stale_assets"] == 1
    assert freshness["max_staleness_days"] == 5
    assert 0 <= freshness["data_quality_score"] <= 100


def test_stale_required_index_generates_fail_freshness():
    freshness = build_data_freshness(
        [
            {
                "step": "indices",
                "status": "OK",
                "payload": {
                    "results": [
                        {
                            "symbol": "^BVSP",
                            "required": True,
                            "path": "data/indices/^BVSP.csv",
                        }
                    ]
                },
            },
            {
                "step": "indices_check",
                "status": "OK",
                "payload": {
                    "results": [
                        {"path": "data/indices/^BVSP.csv", "end_date": "2026-05-25"}
                    ]
                },
            },
        ],
        today=date(2026, 6, 4),
    )

    assert freshness["freshness_status"] == "FAIL"
    assert freshness["stale_indices"] == 1


def test_daily_report_can_embed_update_freshness():
    report = run_daily_pipeline(
        universe_path="data/universes/ibov_sample.csv",
        universe_name="IBOV",
        profile="CON",
        headline_risk="OFF",
        headline_tags=[],
        market_trend="UP",
        market_volatility="NORMAL",
    )
    freshness = build_data_freshness([], today=date(2026, 6, 4))
    payload = daily_report_to_dict(
        report,
        update_status={
            "schema_version": "update_status.v1",
            "status": "OK",
            "freshness": freshness,
        },
    )

    assert payload["update_status"]["freshness"]["freshness_status"] == "OK"
    assert payload["update_status"]["freshness"]["data_quality_score"] == 100.0

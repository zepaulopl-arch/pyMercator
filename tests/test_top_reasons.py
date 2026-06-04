from pymercator.top_reasons import format_top_reason_legend, format_top_reasons


def test_top_reason_abbreviations_and_legend_are_screen_scoped():
    display, legend_codes = format_top_reasons(
        {
            "blockers": [
                "MODEL_WEAK",
                "RISK_OFF",
                "BEHAVIOR_AVOID",
                "VOL_HIGH",
                "ATR_HIGH",
                "TREND_CONFIRM",
            ]
        }
    )

    assert display == "MW+RO+AVOID+VOL+2"
    legend = format_top_reason_legend(legend_codes)
    assert "MW=model weak" in legend
    assert "RO=risk off" in legend
    assert "AVOID=behavior avoid" in legend
    assert "VOL=volatility high" in legend
    assert "ATR=ATR high" not in legend


def test_top_reasons_never_truncate_mid_token():
    display, _legend_codes = format_top_reasons(
        {
            "blockers": [
                "MODEL_WEAK",
                "RISK_OFF",
                "BEHAVIOR_AVOID",
                "VOL_HIGH",
            ]
        },
        width=12,
    )

    assert display == "MW+RO+2"
    assert "AV" not in display

import sys
from types import SimpleNamespace

import pandas as pd

from pymercator.data.prices_yahoo import fetch_yahoo_prices
from pymercator.indices_prices import _download_yfinance


def test_indices_yfinance_download_suppresses_provider_terminal_noise(
    monkeypatch,
    capsys,
):
    def noisy_download(*_args, **_kwargs):
        print("provider stdout noise")
        print("provider stderr noise", file=sys.stderr)
        return pd.DataFrame()

    monkeypatch.setitem(
        sys.modules,
        "yfinance",
        SimpleNamespace(download=noisy_download),
    )

    rows = _download_yfinance("^IEE", start="2000-01-01")

    captured = capsys.readouterr()
    assert rows.empty
    assert captured.out == ""
    assert captured.err == ""


def test_price_yfinance_download_suppresses_provider_terminal_noise(
    monkeypatch,
    capsys,
):
    def noisy_download(*_args, **_kwargs):
        print("provider stdout noise")
        print("provider stderr noise", file=sys.stderr)
        return pd.DataFrame()

    monkeypatch.setitem(
        sys.modules,
        "yfinance",
        SimpleNamespace(download=noisy_download),
    )

    try:
        fetch_yahoo_prices(ticker="PRIO3.SA", start="2000-01-01")
    except ValueError as exc:
        assert "No price data returned" in str(exc)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

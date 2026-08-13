"""Tests for ticker_util — to_yf_ticker, from_yf_ticker, get_currency, get_suffix."""

from __future__ import annotations

from market.data.ticker_util import (
    _needs_suffix,
    from_yf_ticker,
    get_currency,
    get_suffix,
    to_yf_ticker,
)


# ── to_yf_ticker ────────────────────────────────────────────────────────


def test_to_yf_ticker_bare_xidx():
    assert to_yf_ticker("BBCA", "XIDX") == "BBCA.JK"


def test_to_yf_ticker_already_suffixed():
    assert to_yf_ticker("BBCA.JK", "XIDX") == "BBCA.JK"


def test_to_yf_ticker_index_no_suffix():
    assert to_yf_ticker("^GSPC", "XNYS") == "^GSPC"


def test_to_yf_ticker_jkse_index():
    assert to_yf_ticker("^JKSE", "XIDX") == "^JKSE"


def test_to_yf_ticker_futures_no_suffix():
    assert to_yf_ticker("GC=F", "XCEC") == "GC=F"


def test_to_yf_ticker_fx_pair_no_suffix():
    assert to_yf_ticker("IDR=X", "XFXS") == "IDR=X"


def test_to_yf_ticker_us_market_no_suffix():
    assert to_yf_ticker("AAPL", "XNYS") == "AAPL"


def test_to_yf_ticker_nasdaq_no_suffix():
    assert to_yf_ticker("MSFT", "XNAS") == "MSFT"


def test_to_yf_ticker_shanghai_suffix():
    assert to_yf_ticker("000001", "XSHG") == "000001.SS"


def test_to_yf_ticker_strips_wrong_suffix():
    assert to_yf_ticker("BBCA.T", "XIDX") == "BBCA.JK"


def test_to_yf_ticker_german_market():
    assert to_yf_ticker("SAP", "XFRA") == "SAP.DE"


def test_to_yf_ticker_hk_market():
    assert to_yf_ticker("0700", "XHKG") == "0700.HK"


def test_to_yf_ticker_unknown_mic_no_suffix():
    assert to_yf_ticker("FOO", "UNKNOWN") == "FOO"


# ── from_yf_ticker ──────────────────────────────────────────────────────


def test_from_yf_ticker_jk():
    bare, mic = from_yf_ticker("BBCA.JK")
    assert bare == "BBCA"
    assert mic == "XIDX"


def test_from_yf_ticker_index_gspc():
    bare, mic = from_yf_ticker("^GSPC")
    assert bare == "^GSPC"
    assert mic == "XNYS"


def test_from_yf_ticker_jkse_index():
    bare, mic = from_yf_ticker("^JKSE")
    assert bare == "^JKSE"
    assert mic == "XIDX"


def test_from_yf_ticker_fx():
    bare, mic = from_yf_ticker("IDR=X")
    assert bare == "IDR=X"
    assert mic == "XFXS"


def test_from_yf_ticker_futures():
    bare, mic = from_yf_ticker("GC=F")
    assert bare == "GC=F"
    assert mic == "XCEC"


def test_from_yf_ticker_us_market():
    bare, mic = from_yf_ticker("AAPL")
    assert bare == "AAPL"
    assert mic == "XNYS"


def test_from_yf_ticker_german():
    bare, mic = from_yf_ticker("SAP.DE")
    assert bare == "SAP"
    assert mic == "XFRA"


def test_from_yf_ticker_hk():
    bare, mic = from_yf_ticker("0700.HK")
    assert bare == "0700"
    assert mic == "XHKG"


# ── get_currency ────────────────────────────────────────────────────────


def test_get_currency_xidx():
    assert get_currency("BBCA.JK", "XIDX") == "IDR"


def test_get_currency_xnys():
    assert get_currency("AAPL", "XNYS") == "USD"


def test_get_currency_xnas():
    assert get_currency("MSFT", "XNAS") == "USD"


def test_get_currency_xfra():
    assert get_currency("SAP.DE", "XFRA") == "EUR"


def test_get_currency_xhkg():
    assert get_currency("0700.HK", "XHKG") == "HKD"


def test_get_currency_unknown_mic_defaults_usd():
    assert get_currency("FOO", "UNKNOWN") == "USD"


# ── get_suffix ──────────────────────────────────────────────────────────


def test_get_suffix_xidx():
    assert get_suffix("XIDX") == ".JK"


def test_get_suffix_xnys_none():
    assert get_suffix("XNYS") is None


def test_get_suffix_xfra():
    assert get_suffix("XFRA") == ".DE"


def test_get_suffix_unknown():
    assert get_suffix("UNKNOWN") is None


# ── _needs_suffix ───────────────────────────────────────────────────────


def test_needs_suffix_jk():
    assert _needs_suffix("BBCA.JK") is True


def test_needs_suffix_de():
    assert _needs_suffix("SAP.DE") is True


def test_needs_suffix_bare():
    assert _needs_suffix("BBCA") is False


def test_needs_suffix_index():
    assert _needs_suffix("^GSPC") is False


# ── Round-trip: to_yf_ticker → from_yf_ticker ───────────────────────────


def test_roundtrip_xidx():
    yf = to_yf_ticker("BBCA", "XIDX")
    bare, mic = from_yf_ticker(yf)
    assert bare == "BBCA"
    assert mic == "XIDX"


def test_roundtrip_xnys():
    yf = to_yf_ticker("AAPL", "XNYS")
    bare, mic = from_yf_ticker(yf)
    assert bare == "AAPL"
    assert mic == "XNYS"

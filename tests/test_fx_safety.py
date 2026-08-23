from datetime import datetime, timedelta, timezone

from roman_arb.fx import FXBook


def test_foreign_fx_without_timestamp_is_fail_closed():
    book = FXBook({"EUR": 1.0, "USD": 1.20}, asof="")
    assert not book.is_fresh()
    assert book.to_eur(120.0, "USD") is None
    # Native EUR does not depend on an FX book.
    assert book.to_eur(120.0, "EUR") == 120.0


def test_fresh_foreign_fx_is_usable():
    asof = datetime.now(timezone.utc).isoformat()
    book = FXBook({"EUR": 1.0, "USD": 1.20}, asof=asof)
    assert book.is_fresh()
    assert abs(book.to_eur(120.0, "USD") - 100.0) < 1e-12


def test_materially_future_dated_fx_is_rejected():
    asof = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    book = FXBook({"EUR": 1.0, "USD": 1.20}, asof=asof)
    assert book.age_hours() is None
    assert not book.is_fresh()
    assert book.to_eur(120.0, "USD") is None

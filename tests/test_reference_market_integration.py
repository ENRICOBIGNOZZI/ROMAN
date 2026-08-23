import json
import sqlite3
from pathlib import Path

import pytest

from roman_arb.feeds.base import RawListing
from roman_arb.production import ShadowLiveEngine


class _FX:
    def to_eur(self, value, currency, executable=False):
        return float(value)

    def acquisition_eur(self, value, currency):
        return float(value)


class _FakeReferenceFeed:
    def available(self):
        return True

    def fetch(self, query, limit=50):
        return [
            RawListing(
                source="cardmarket_public_reference",
                external_id="ref-1",
                title="Pokemon 151 booster box",
                price=125.0,
                currency="EUR",
                product_key="cardmarket:1",
                extra={
                    "query": "Pokemon 151 booster box",
                    "reference_only": True,
                    "reference_kind": "test",
                },
            )
        ]


def _engine(tmp_path):
    return ShadowLiveEngine(
        capital=10_000,
        snapshot_db=str(tmp_path / "market.sqlite"),
        reference_snapshot_db=str(tmp_path / "reference.sqlite"),
        tracking_db=str(tmp_path / "tracking.sqlite"),
        shadow_db=str(tmp_path / "shadow.sqlite"),
        dashboard_path=str(tmp_path / "dashboard.json"),
        queries_per_source=1,
        rows_per_query=10,
    )


def test_reference_update_is_bounded_and_does_not_create_route(tmp_path):
    engine = _engine(tmp_path)
    try:
        candidate = {
            "entity_key": "g:gtin:123",
            "sector": "retro_games",
            "family": "",
            "product": "g:gtin:123",
            "title": "EarthBound Super Nintendo",
            "buy_query": "EarthBound Super Nintendo",
            "buy_price": 80.0,
            "base_fair_value": 100.0,
            "target_exit_price": 100.0,
            "exit_source": "ebay",
            "exit_fee_rate": 0.10,
            "model_sigma_roi": 0.02,
            "comparables_net": [],
        }
        reference = {
            "source": "pricecharting_reference",
            "external_id": "r1",
            "title": "EarthBound Super Nintendo",
            "price": 120.0,
            "currency": "EUR",
            "observed_at": "2026-08-23T10:00:00+00:00",
            "extra": {
                "reference_only": True,
                "query": "EarthBound Super Nintendo",
                "global_product_key": "gtin:123",
            },
            "extra_json": json.dumps(
                {
                    "reference_only": True,
                    "query": "EarthBound Super Nintendo",
                    "global_product_key": "gtin:123",
                }
            ),
        }
        engine._apply_reference_update(candidate, [reference], _FX())
        assert candidate["market_base_fair_value"] == pytest.approx(100.0)
        assert candidate["reference_fair_value"] == pytest.approx(120.0)
        assert 0.0 < candidate["reference_weight"] <= 0.20
        assert candidate["base_fair_value"] == pytest.approx(103.0)
        assert candidate["model_sigma_roi"] > 0.02
        assert candidate["exit_source"] == "ebay"
        assert candidate["reference_values"][0]["source"] == "pricecharting_reference"
    finally:
        engine.close()


def test_extreme_reference_mismatch_is_archived_but_not_used(tmp_path):
    engine = _engine(tmp_path)
    try:
        candidate = {
            "entity_key": "g:gtin:123",
            "title": "EarthBound Super Nintendo",
            "buy_query": "EarthBound Super Nintendo",
            "base_fair_value": 100.0,
        }
        reference = {
            "source": "pricecharting_reference",
            "title": "EarthBound Super Nintendo",
            "price": 500.0,
            "currency": "EUR",
            "extra": {"reference_only": True, "global_product_key": "gtin:123"},
            "extra_json": json.dumps(
                {"reference_only": True, "global_product_key": "gtin:123"}
            ),
        }
        assert engine._reference_values(candidate, [reference], _FX()) == []
    finally:
        engine.close()


def test_reference_collection_uses_separate_database(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.reference_every_cycles = 1
        engine.reference_adapters = {
            "cardmarket_public_reference": _FakeReferenceFeed()
        }
        counts = engine.collect_reference_cycle()
        assert counts["cardmarket_public_reference"] == 1
        assert Path(engine.reference_snapshot_db).exists()
        assert not Path(engine.snapshot_db).exists()
        db = sqlite3.connect(engine.reference_snapshot_db)
        try:
            assert db.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 1
            row = db.execute("SELECT extra_json FROM listings").fetchone()[0]
            assert json.loads(row)["reference_only"] is True
        finally:
            db.close()
    finally:
        engine.close()


def test_reference_database_alone_cannot_create_candidate(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    try:
        engine.reference_every_cycles = 1
        engine.reference_adapters = {
            "cardmarket_public_reference": _FakeReferenceFeed()
        }
        engine.collect_reference_cycle()
        monkeypatch.setattr(engine, "refresh_fx", lambda: _FX())
        assert engine.build_candidates() == []
    finally:
        engine.close()


def test_pricecharting_rows_are_mapped_to_video_game_sectors(tmp_path):
    engine = _engine(tmp_path)
    try:
        game = {
            "source": "pricecharting",
            "title": "EarthBound Super Nintendo",
            "extra": {"genre": "RPG"},
        }
        system = {
            "source": "pricecharting",
            "title": "Nintendo Switch OLED console",
            "extra": {"genre": "Systems"},
        }
        assert engine._sector(game)[0] == "retro_games"
        assert engine._sector(system)[0] == "consoles"
        assert "pricecharting" in engine.plan
        assert "ricardo" in engine.plan
        assert any("EarthBound" in q for q in engine.plan["ebay"])
    finally:
        engine.close()

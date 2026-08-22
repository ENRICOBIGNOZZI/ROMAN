from __future__ import annotations
import json
from pathlib import Path
from .models import Venue, Sector


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "markets.json"


def load_config(path: str | Path | None = None):
    p = Path(path) if path else default_config_path()
    raw = json.loads(p.read_text())
    venues = {
        k: Venue(key=k, **v) for k, v in raw["venues"].items()
    }
    sectors = {}
    for s in raw["sectors"]:
        d = dict(s)
        d["exit_venues"] = tuple(d["exit_venues"])
        sector = Sector(**d)
        sectors[sector.key] = sector
    return raw["assumptions"], venues, sectors

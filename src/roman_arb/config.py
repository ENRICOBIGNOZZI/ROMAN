from __future__ import annotations
import json
from pathlib import Path
from .models import Venue, Sector


def config_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


def default_config_path() -> Path:
    maximal = config_dir() / "maximal_catalog.json"
    packed = config_dir() / "maximal_catalog.json.z64"
    if maximal.exists():
        return maximal
    if packed.exists():
        return packed
    return config_dir() / "markets.json"


def _expand_catalog(raw: dict) -> list[dict]:
    templates = raw["templates"]
    out = []
    for row in raw["sectors"]:
        key, name, avg_ticket, family, source_venues, buy_venues, template_id = row
        d = dict(templates[int(template_id)])
        d.update({
            "key": key,
            "name": name,
            "avg_ticket": avg_ticket,
            "family": family,
            "source_venues": source_venues,
            "buy_venues": buy_venues,
        })
        out.append(d)
    return out


def load_config(path: str | Path | None = None):
    p = Path(path) if path else default_config_path()
    if p.name.endswith(".z64"):
        import base64, zlib
        raw = json.loads(zlib.decompress(base64.b64decode(p.read_text().strip())).decode("utf-8"))
    else:
        raw = json.loads(p.read_text())
    venues = {k: Venue(key=k, **v) for k, v in raw["venues"].items()}
    sectors = {}
    sector_rows = _expand_catalog(raw) if "templates" in raw else raw["sectors"]
    for s in sector_rows:
        d = dict(s)
        d["exit_venues"] = tuple(d["exit_venues"])
        d["source_venues"] = tuple(d.get("source_venues", ()))
        d["buy_venues"] = tuple(d.get("buy_venues", ()))
        sector = Sector(**d)
        sectors[sector.key] = sector
    return raw["assumptions"], venues, sectors

from __future__ import annotations
import json
from pathlib import Path
from .models import Venue, Sector


def config_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


def policy_config_path() -> Path:
    return config_dir() / "markets.json"


def default_config_path() -> Path:
    maximal = config_dir() / "maximal_catalog.json"
    packed = config_dir() / "maximal_catalog.json.z64"
    if maximal.exists():
        return maximal
    if packed.exists():
        return packed
    return policy_config_path()


def _read_json_or_z64(p: Path) -> dict:
    if p.name.endswith(".z64"):
        import base64, zlib
        return json.loads(
            zlib.decompress(base64.b64decode(p.read_text().strip())).decode("utf-8")
        )
    return json.loads(p.read_text())


def _expand_catalog(raw: dict) -> list[dict]:
    templates = raw["templates"]
    out = []
    for row in raw["sectors"]:
        key, name, avg_ticket, family, source_venues, buy_venues, template_id = row
        d = dict(templates[int(template_id)])
        d.update(
            {
                "key": key,
                "name": name,
                "avg_ticket": avg_ticket,
                "family": family,
                "source_venues": source_venues,
                "buy_venues": buy_venues,
            }
        )
        out.append(d)
    return out


def load_config(path: str | Path | None = None):
    p = Path(path) if path else default_config_path()
    # Backward compatibility with earlier expanded-catalog filenames used by
    # scripts/tests. The maximal packed catalog is now the canonical superset.
    if (
        path is not None
        and not p.exists()
        and p.name in {"markets_expanded.json", "markets_maximal.json"}
    ):
        p = default_config_path()

    raw = _read_json_or_z64(p)

    # Catalog breadth and live risk policy are different concerns. The packed
    # catalog can be regenerated to add markets, but it must not resurrect stale
    # capital assumptions OR stale fee schedules. For the default load,
    # markets.json is authoritative for every policy venue it names while extra
    # catalog-only venues are preserved.
    if path is None and p != policy_config_path() and policy_config_path().exists():
        policy = _read_json_or_z64(policy_config_path())
        raw["assumptions"] = {
            **dict(raw.get("assumptions", {})),
            **dict(policy.get("assumptions", {})),
        }
        raw["venues"] = {
            **dict(raw.get("venues", {})),
            **dict(policy.get("venues", {})),
        }

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

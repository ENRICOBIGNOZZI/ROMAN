from __future__ import annotations

import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ECB_DAILY_XML = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


@dataclass
class FXBook:
    """Point-in-time EUR conversion book.

    `foreign_per_eur[USD]=1.17` means EUR 1 = USD 1.17. Conversion to EUR is
    therefore amount / rate. An explicit friction is charged in addition to the mid.
    """
    foreign_per_eur: dict[str, float]
    asof: str = ""
    source: str = ""
    friction_pct: float = 0.004
    max_age_hours: float = 96.0

    @classmethod
    def load(cls, path: str = "data/fx_rates.json") -> "FXBook":
        p = Path(path)
        if not p.exists():
            return cls({"EUR": 1.0}, source="missing")
        raw = json.loads(p.read_text())
        rates = {str(k).upper(): float(v) for k, v in raw.get("foreign_per_eur", raw.get("rates", {})).items()}
        rates["EUR"] = 1.0
        return cls(rates, str(raw.get("asof", "")), str(raw.get("source", "")),
                   float(raw.get("friction_pct", os.getenv("ROMAN_FX_FRICTION", "0.004"))),
                   float(raw.get("max_age_hours", 96.0)))

    def age_hours(self) -> float | None:
        if not self.asof:
            return None
        try:
            dt = datetime.fromisoformat(self.asof.replace("Z", "+00:00"))
            if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
        except Exception:
            return None

    def is_fresh(self) -> bool:
        age = self.age_hours()
        return age is None or age <= self.max_age_hours

    def to_eur(self, amount: float, currency: str, charge_friction: bool = False) -> float | None:
        c = (currency or "").upper()
        if c == "EUR":
            value = float(amount)
        else:
            rate = self.foreign_per_eur.get(c)
            if not rate or rate <= 0 or not self.is_fresh():
                return None
            value = float(amount) / rate
        if charge_friction and c != "EUR":
            value *= (1.0 - self.friction_pct)
        return value

    def acquisition_eur(self, amount: float, currency: str) -> float | None:
        value = self.to_eur(amount, currency, False)
        if value is None: return None
        if (currency or "").upper() != "EUR": value *= (1.0 + self.friction_pct)
        return value


def refresh_ecb(path: str = "data/fx_rates.json", timeout: float = 20.0, friction_pct: float = 0.004) -> dict:
    req = urllib.request.Request(ECB_DAILY_XML, headers={"User-Agent": "ROMAN-paper-research/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        root = ET.fromstring(r.read())
    rates = {"EUR": 1.0}; asof = ""
    for elem in root.iter():
        time_value = elem.attrib.get("time")
        if time_value: asof = time_value
        c = elem.attrib.get("currency"); rate = elem.attrib.get("rate")
        if c and rate:
            rates[c.upper()] = float(rate)
    if not asof or len(rates) <= 1:
        raise RuntimeError("ECB FX response did not contain daily rates")
    payload = {
        "base": "EUR", "asof": f"{asof}T16:00:00+02:00", "source": "ECB euro foreign exchange reference rates",
        "foreign_per_eur": rates, "friction_pct": float(friction_pct), "max_age_hours": 96.0,
        "warning": "reference mid only; ROMAN adds FX friction and does not treat this as an executable transaction quote",
    }
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload

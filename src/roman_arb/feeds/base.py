from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable, Protocol


@dataclass
class RawListing:
    source: str
    external_id: str
    title: str
    price: float
    currency: str
    url: str = ""
    condition: str = ""
    seller: str = ""
    category: str = ""
    product_key: str = ""
    observed_at: str = ""
    extra: dict | None = None

    def __post_init__(self):
        if not self.observed_at:
            self.observed_at = datetime.now(timezone.utc).isoformat()
        if self.extra is None:
            self.extra = {}

    def to_dict(self) -> dict:
        return asdict(self)


class FeedAdapter(Protocol):
    name: str
    def available(self) -> bool: ...
    def fetch(self, query: str, limit: int = 50) -> Iterable[RawListing]: ...

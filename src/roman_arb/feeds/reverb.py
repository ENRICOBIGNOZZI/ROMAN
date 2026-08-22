from __future__ import annotations
import os
from urllib.parse import quote_plus
from .base import RawListing
from .http_utils import get_json


class ReverbFeed:
    name="reverb"
    def __init__(self): self.token=os.getenv("REVERB_TOKEN", "")
    def available(self): return bool(self.token)
    def fetch(self, query: str, limit: int=50):
        url=f"https://reverb.com/api/listings?query={quote_plus(query)}&per_page={min(limit,50)}"
        data=get_json(url,{"Accept":"application/hal+json","X-Auth-Token":self.token})
        items=(data.get("_embedded") or {}).get("listings") or data.get("listings") or []
        out=[]
        for x in items:
            price=x.get("price") or {}
            amount=price.get("amount") if isinstance(price,dict) else price
            currency=price.get("currency") if isinstance(price,dict) else "USD"
            links=x.get("_links") or {}
            web=(links.get("web") or links.get("self") or {}).get("href","") if isinstance(links,dict) else ""
            out.append(RawListing(source=self.name,external_id=str(x.get("id","")),title=x.get("title","") or f"{x.get('make','')} {x.get('model','')}",price=float(amount or 0),currency=currency or "USD",url=web,condition=(x.get("condition") or {}).get("display_name","") if isinstance(x.get("condition"),dict) else str(x.get("condition") or ""),category=str(x.get("product_type") or ""),extra=x))
        return out

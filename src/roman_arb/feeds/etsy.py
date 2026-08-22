from __future__ import annotations
import os
from urllib.parse import quote_plus
from .base import RawListing
from .http_utils import get_json


class EtsyFeed:
    name="etsy"
    def __init__(self):
        self.api_key=os.getenv("ETSY_API_KEY", "")
        self.oauth=os.getenv("ETSY_OAUTH_TOKEN", "")
    def available(self): return bool(self.api_key)
    def fetch(self, query: str, limit: int=50):
        url=f"https://api.etsy.com/v3/application/listings/active?keywords={quote_plus(query)}&limit={min(limit,100)}"
        h={"x-api-key":self.api_key}
        if self.oauth: h["Authorization"]=f"Bearer {self.oauth}"
        data=get_json(url,h)
        out=[]
        for x in data.get("results",[]):
            p=x.get("price") or {}
            divisor=float(p.get("divisor",100) or 100)
            amount=float(p.get("amount",0) or 0)/divisor
            out.append(RawListing(source=self.name,external_id=str(x.get("listing_id","")),title=x.get("title",""),price=amount,currency=p.get("currency_code",""),url=x.get("url",""),category=str(x.get("taxonomy_id") or ""),extra=x))
        return out

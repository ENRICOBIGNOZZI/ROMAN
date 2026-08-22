from __future__ import annotations
import os
from urllib.parse import quote_plus
from .base import RawListing
from .http_utils import get_json


class MercadoLibreFeed:
    name="mercadolibre"
    def __init__(self, site_id: str="MLM"):
        self.token=os.getenv("MELI_ACCESS_TOKEN", "")
        self.site_id=os.getenv("MELI_SITE_ID", site_id)
    def available(self): return bool(self.token)
    def fetch(self, query: str, limit: int=50):
        url=f"https://api.mercadolibre.com/sites/{self.site_id}/search?q={quote_plus(query)}&limit={min(limit,50)}"
        data=get_json(url,{"Authorization":f"Bearer {self.token}"})
        return [RawListing(source=self.name,external_id=str(x.get("id","")),title=x.get("title",""),price=float(x.get("price",0) or 0),currency=x.get("currency_id",""),url=x.get("permalink",""),condition=x.get("condition",""),seller=str(x.get("seller",{}).get("nickname","") if isinstance(x.get("seller"),dict) else ""),category=x.get("category_id",""),extra=x) for x in data.get("results",[])]

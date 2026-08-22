from __future__ import annotations
import os
from urllib.parse import quote_plus
from .base import RawListing
from .http_utils import get_json


class StockXMarketFeed:
    """StockX catalog/market-data adapter. Requires approved developer access.

    Each returned row represents a product variant with current lowest ask as price;
    highest bid is retained in extra for locked-spread screening.
    """
    name="stockx"
    def __init__(self, currency: str="EUR", max_products: int=8):
        self.api_key=os.getenv("STOCKX_API_KEY", "")
        self.token=os.getenv("STOCKX_ACCESS_TOKEN", "")
        self.currency=currency
        self.max_products=max_products

    def available(self): return bool(self.api_key and self.token)
    def _headers(self): return {"Authorization":f"Bearer {self.token}","x-api-key":self.api_key,"Content-Type":"application/json"}

    def fetch(self, query: str, limit: int=50):
        search=get_json(f"https://api.stockx.com/v2/catalog/search?query={quote_plus(query)}&pageNumber=1&pageSize={min(self.max_products,20)}",self._headers())
        products=search.get("products") or search.get("results") or []
        out=[]
        for p in products[:self.max_products]:
            pid=p.get("productId") or p.get("id")
            if not pid: continue
            try:
                md=get_json(f"https://api.stockx.com/v2/catalog/products/{pid}/market-data?currencyCode={self.currency}",self._headers())
            except Exception:
                continue
            rows=md if isinstance(md,list) else md.get("marketData",[]) if isinstance(md,dict) else []
            for row in rows:
                ask=row.get("lowestAskAmount")
                if ask in (None,""): continue
                out.append(RawListing(
                    source=self.name, external_id=f"{pid}:{row.get('variantId','')}",
                    title=f"{p.get('title') or p.get('name') or query} {row.get('variantName') or row.get('variantValue') or ''}".strip(),
                    price=float(ask), currency=row.get("currencyCode",self.currency),
                    category=p.get("productType", ""), product_key=str(row.get("variantId") or pid),
                    extra={"highest_bid":row.get("highestBidAmount"),"sell_faster":row.get("sellFasterAmount"),"earn_more":row.get("earnMoreAmount"),"product":p},
                ))
                if len(out)>=limit: return out
        return out

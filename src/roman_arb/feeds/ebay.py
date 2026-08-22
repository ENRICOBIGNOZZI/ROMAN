from __future__ import annotations
import os
from urllib.parse import quote_plus
from .base import RawListing
from .http_utils import get_json, post_form_json, basic_auth


class EbayBrowseFeed:
    name="ebay"
    def __init__(self, marketplace: str = "EBAY_CH"):
        self.client_id=os.getenv("EBAY_CLIENT_ID", "")
        self.secret=os.getenv("EBAY_CLIENT_SECRET", "")
        self.marketplace=marketplace
        self._token=""

    def available(self):
        return bool(self.client_id and self.secret)

    def _access_token(self):
        if self._token: return self._token
        data=post_form_json(
            "https://api.ebay.com/identity/v1/oauth2/token",
            {"grant_type":"client_credentials","scope":"https://api.ebay.com/oauth/api_scope"},
            {"Authorization": basic_auth(self.client_id,self.secret)},
        )
        self._token=data["access_token"]
        return self._token

    def fetch(self, query: str, limit: int=50):
        token=self._access_token()
        url=f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={quote_plus(query)}&limit={min(limit,200)}"
        data=get_json(url,{"Authorization":f"Bearer {token}","X-EBAY-C-MARKETPLACE-ID":self.marketplace})
        out=[]
        for x in data.get("itemSummaries",[]):
            price=x.get("price") or {}
            out.append(RawListing(
                source=self.name, external_id=str(x.get("itemId","")), title=x.get("title", ""),
                price=float(price.get("value",0) or 0), currency=price.get("currency",""), url=x.get("itemWebUrl",""),
                condition=x.get("condition",""), seller=(x.get("seller") or {}).get("username", ""),
                category=((x.get("categories") or [{}])[0]).get("categoryName", ""), extra=x,
            ))
        return out

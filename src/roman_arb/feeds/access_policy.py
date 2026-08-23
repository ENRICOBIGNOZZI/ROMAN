from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketAccessPolicy:
    source: str
    domain: str
    access_mode: str
    automated_collection: bool
    data_role: str
    credential_env: tuple[str, ...] = ()
    notes: str = ""


# This registry is intentionally conservative.  A source marked
# ``permission_required`` remains strategically relevant to ROMAN, but the live
# collector must not scrape it unless written/platform authorization is obtained.
MARKET_ACCESS_POLICIES: dict[str, MarketAccessPolicy] = {
    "ebay": MarketAccessPolicy(
        "ebay", "ebay.com", "official_api", True, "market_listings",
        ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"),
    ),
    "stockx": MarketAccessPolicy(
        "stockx", "stockx.com", "official_api", True, "market_listings+bids",
        ("STOCKX_API_KEY", "STOCKX_ACCESS_TOKEN"),
    ),
    "reverb": MarketAccessPolicy(
        "reverb", "reverb.com", "official_api", True, "market_listings",
        ("REVERB_TOKEN",),
    ),
    "etsy": MarketAccessPolicy(
        "etsy", "etsy.com", "official_api", True, "market_listings",
        ("ETSY_API_KEY", "ETSY_OAUTH_TOKEN"),
    ),
    "mercadolibre": MarketAccessPolicy(
        "mercadolibre", "mercadolibre.com", "official_api", True, "market_listings",
        ("MELI_ACCESS_TOKEN",),
    ),
    "rakuten_ichiba": MarketAccessPolicy(
        "rakuten_ichiba", "rakuten.co.jp", "official_api", True, "retail_listings",
        ("RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY"),
    ),
    "ricardo": MarketAccessPolicy(
        "ricardo", "ricardo.ch", "partner_api", True, "market_listings",
        ("RICARDO_TOKEN",),
        "Ricardo search/article services require a partnership/token credential.",
    ),
    "pricecharting": MarketAccessPolicy(
        "pricecharting", "pricecharting.com", "licensed_api", True,
        "video_game_market+reference_prices", ("PRICECHARTING_TOKEN",),
        "Paid API; includes videogame price guide and marketplace endpoints.",
    ),
    "bricklink": MarketAccessPolicy(
        "bricklink", "bricklink.com", "official_api", True, "lego_reference_prices",
        (
            "BRICKLINK_CONSUMER_KEY",
            "BRICKLINK_CONSUMER_SECRET",
            "BRICKLINK_TOKEN",
            "BRICKLINK_TOKEN_SECRET",
        ),
        "OAuth credentials and registered source IP are required.",
    ),
    "discogs": MarketAccessPolicy(
        "discogs", "discogs.com", "official_api", True, "vinyl_reference_prices",
        ("DISCOGS_TOKEN",),
    ),
    "tcgapi": MarketAccessPolicy(
        "tcgapi", "tcgapi.dev", "licensed_api", True, "sealed_tcg_reference_prices",
        ("TCGAPI_KEY",),
        "Commercial deployment requires a commercial-use tier/license.",
    ),
    "tcgplayer": MarketAccessPolicy(
        "tcgplayer", "tcgplayer.com", "official_api_existing_keys", True,
        "tcg_reference_prices", ("TCGPLAYER_PUBLIC_KEY", "TCGPLAYER_PRIVATE_KEY"),
        "TCGplayer currently documents that new API keys are not being granted.",
    ),
    "vinted": MarketAccessPolicy(
        "vinted", "vinted.com", "permission_required", False, "market_listings",
        (),
        "Public-market scraping/crawling is prohibited by current user terms. "
        "Vinted Pro Integrations is allowlisted and primarily manages the caller's own inventory/orders.",
    ),
    "tutti": MarketAccessPolicy(
        "tutti", "tutti.ch", "permission_required", False, "market_listings", (),
        "Third-party duplication/takeover of listings is expressly prohibited on the site.",
    ),
    "subito": MarketAccessPolicy(
        "subito", "subito.it", "permission_required", False, "market_listings", (),
        "Current terms expressly prohibit robots/spiders/scrapers and unauthorized aggregators.",
    ),
    "wallapop": MarketAccessPolicy(
        "wallapop", "wallapop.com", "permission_required", False, "market_listings", (),
        "Current terms prohibit systematic extraction, robots and external bots unless authorized.",
    ),
    "kleinanzeigen": MarketAccessPolicy(
        "kleinanzeigen", "kleinanzeigen.de", "permission_required", False, "market_listings", (),
        "Current terms prohibit crawlers/spiders/scrapers without express written permission.",
    ),
    "leboncoin": MarketAccessPolicy(
        "leboncoin", "leboncoin.fr", "permission_required", False, "market_listings", (),
        "Current terms prohibit extraction/indexing by robots without prior express authorization.",
    ),
    "facebook_marketplace": MarketAccessPolicy(
        "facebook_marketplace", "facebook.com", "permission_required", False,
        "market_listings", (), "No general authorized public-market search feed is wired into ROMAN.",
    ),
    "mercari": MarketAccessPolicy(
        "mercari", "mercari.com", "permission_required", False, "market_listings", (),
        "Keep disabled until an official/contracted data route is available.",
    ),
    "catawiki": MarketAccessPolicy(
        "catawiki", "catawiki.com", "permission_required", False, "auction_listings", (),
        "Keep disabled until an official/contracted data route is available.",
    ),
}


def market_access_registry() -> dict[str, MarketAccessPolicy]:
    return dict(MARKET_ACCESS_POLICIES)


def automated_sources() -> tuple[str, ...]:
    return tuple(
        sorted(k for k, v in MARKET_ACCESS_POLICIES.items() if v.automated_collection)
    )


def permission_required_sources() -> tuple[str, ...]:
    return tuple(
        sorted(k for k, v in MARKET_ACCESS_POLICIES.items() if not v.automated_collection)
    )

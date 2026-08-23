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


# Conservative source-of-truth for discovery access. A market can be strategically
# important while remaining disabled for automated discovery. ROMAN never turns a
# public webpage into a scraper merely because the site is visible in a browser.
MARKET_ACCESS_POLICIES: dict[str, MarketAccessPolicy] = {
    # Concrete authorized listing feeds already wired into ROMAN.
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
        "Search/article services require a Ricardo partnership/token credential.",
    ),
    "pricecharting": MarketAccessPolicy(
        "pricecharting", "pricecharting.com", "licensed_api", True,
        "video_game_market+reference_prices", ("PRICECHARTING_TOKEN",),
        "Paid API; marketplace offers and videogame guide prices are available.",
    ),
    "cardtrader": MarketAccessPolicy(
        "cardtrader", "cardtrader.com", "official_api", True,
        "tcg_marketplace_listings", ("CARDTRADER_TOKEN",),
        "Official Bearer-token API exposes marketplace products and purchase/cart endpoints; ROMAN is read-only.",
    ),

    # Authorized/public valuation sources. They never become execution routes.
    "cardmarket_public": MarketAccessPolicy(
        "cardmarket_public", "cardmarket.com", "public_official_download", True,
        "tcg_reference_prices", (),
        "Official daily price-guide and product-catalogue downloads are public for all users.",
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
    "watchcharts": MarketAccessPolicy(
        "watchcharts", "watchcharts.com", "official_api", True, "watch_reference_prices",
        ("WATCHCHARTS_API_KEY",),
        "Official API maps brand+reference to market/dealer/median asking prices; internal-use licensing applies by default.",
    ),
    "keepa": MarketAccessPolicy(
        "keepa", "keepa.com", "official_api", True, "amazon_reference_prices",
        ("KEEPA_API_KEY",),
        "Official paid API provides Amazon product search, current prices, offers and histories; ROMAN initially uses reference prices only.",
    ),
    "tcgplayer": MarketAccessPolicy(
        "tcgplayer", "tcgplayer.com", "official_api_existing_keys", False,
        "tcg_reference_prices", ("TCGPLAYER_PUBLIC_KEY", "TCGPLAYER_PRIVATE_KEY"),
        "New API keys are currently not being granted; enable only for an existing approved account.",
    ),
    "cardmarket_api": MarketAccessPolicy(
        "cardmarket_api", "cardmarket.com", "official_api_existing_keys", False,
        "tcg_market_data", (),
        "New API applications are currently closed. Public price-guide downloads are used instead.",
    ),
    "tcgdex": MarketAccessPolicy(
        "tcgdex", "tcgdex.net", "public_api", False, "pokemon_reference_prices", (),
        "Public no-auth API is tracked but not auto-applied to graded/sealed sectors because raw-card condition semantics differ.",
    ),

    # Seller/inventory APIs that do not provide general market discovery.
    "whatnot": MarketAccessPolicy(
        "whatnot", "whatnot.com", "seller_api_existing_access", False,
        "own_inventory_orders", (),
        "Seller API is in preview, currently not onboarding new applicants, and scopes seller inventory rather than global discovery.",
    ),
    "vinted_pro": MarketAccessPolicy(
        "vinted_pro", "vinted.com", "allowlisted_seller_api", False,
        "own_inventory_orders", (),
        "Pro Integrations is allowlisted and is not a general public-market search feed.",
    ),
    "vestiaire_pro": MarketAccessPolicy(
        "vestiaire_pro", "vestiairecollective.com", "seller_partner_api", False,
        "own_inventory", (),
        "Professional sellers may receive CSV/API integration; no general discovery feed is wired.",
    ),

    # High-value markets retained as partnership targets. No unapproved scraping.
    "vinted": MarketAccessPolicy(
        "vinted", "vinted.com", "permission_required", False, "market_listings", (),
        "Current user terms prohibit public-market scraping/crawling without authorization.",
    ),
    "tutti": MarketAccessPolicy(
        "tutti", "tutti.ch", "permission_required", False, "market_listings", (),
        "Keep disabled until an approved/contracted data route exists.",
    ),
    "subito": MarketAccessPolicy(
        "subito", "subito.it", "permission_required", False, "market_listings", (),
        "Current terms prohibit robots/spiders/scrapers and unauthorized aggregators.",
    ),
    "wallapop": MarketAccessPolicy(
        "wallapop", "wallapop.com", "permission_required", False, "market_listings", (),
        "Current terms prohibit systematic extraction and external bots unless authorized.",
    ),
    "kleinanzeigen": MarketAccessPolicy(
        "kleinanzeigen", "kleinanzeigen.de", "permission_required", False, "market_listings", (),
        "Current terms prohibit crawlers/spiders/scrapers without express written permission.",
    ),
    "leboncoin": MarketAccessPolicy(
        "leboncoin", "leboncoin.fr", "permission_required", False, "market_listings", (),
        "Current terms prohibit extraction/indexing by robots without prior express authorization.",
    ),
    "chrono24": MarketAccessPolicy(
        "chrono24", "chrono24.com", "partner_required", False, "watch_market_listings", (),
        "Professional dealer/partner program exists; no general public discovery API is wired. WatchCharts supplies authorized market-value references instead.",
    ),
    "goat": MarketAccessPolicy(
        "goat", "goat.com", "permission_required", False, "sneaker_market_listings", (),
        "Keep disabled until an official/contracted discovery route is available.",
    ),
    "grailed": MarketAccessPolicy(
        "grailed", "grailed.com", "permission_required", False, "fashion_market_listings", (),
        "Keep disabled until an official/contracted discovery route is available.",
    ),
    "depop": MarketAccessPolicy(
        "depop", "depop.com", "permission_required", False, "fashion_market_listings", (),
        "Keep disabled until an official/contracted discovery route is available.",
    ),
    "poshmark": MarketAccessPolicy(
        "poshmark", "poshmark.com", "permission_required", False, "fashion_market_listings", (),
        "Keep disabled until an official/contracted discovery route is available.",
    ),
    "vestiaire_collective": MarketAccessPolicy(
        "vestiaire_collective", "vestiairecollective.com", "partner_required", False,
        "luxury_market_listings", (), "Professional integration does not imply global discovery access.",
    ),
    "back_market": MarketAccessPolicy(
        "back_market", "backmarket.com", "partner_required", False,
        "refurbished_electronics", (), "Marketplace is strategically useful; no approved global search API is wired.",
    ),
    "swappa": MarketAccessPolicy(
        "swappa", "swappa.com", "permission_required", False, "used_electronics", (),
        "Power/enterprise seller tooling exists; no approved global discovery API is wired.",
    ),
    "mpb": MarketAccessPolicy(
        "mpb", "mpb.com", "permission_required", False, "used_camera_market", (),
        "Keep disabled until an official/contracted discovery route is available.",
    ),
    "keh": MarketAccessPolicy(
        "keh", "keh.com", "permission_required", False, "used_camera_market", (),
        "Keep disabled until an official/contracted discovery route is available.",
    ),
    "cex": MarketAccessPolicy(
        "cex", "webuy.com", "permission_required", False, "games_electronics_retail", (),
        "Keep disabled until an official/contracted machine-readable feed is available.",
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
    "delcampe": MarketAccessPolicy(
        "delcampe", "delcampe.net", "permission_required", False, "collectibles_market", (),
        "Keep disabled until an official/contracted data route is available.",
    ),
    "abebooks": MarketAccessPolicy(
        "abebooks", "abebooks.com", "partner_required", False, "rare_books", (),
        "Retained as a rare-book market target; no general discovery adapter is currently wired.",
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

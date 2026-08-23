# ROMAN market-data universe

ROMAN separates **market discovery** from **valuation reference data** and from **markets that require permission/partnership**. A webpage being publicly visible does not make automated extraction an approved data source.

## 1. Concrete listing feeds wired into the live collector

| Source | Coverage | Access | ROMAN role |
|---|---|---|---|
| eBay | broad global resale | official API | listings / cross-market bridge |
| StockX | sneakers / collectibles | approved API | listings + executable bid evidence |
| Reverb | instruments / music gear | official API | listings |
| Etsy | vintage / collectibles | official API | listings |
| Mercado Libre | LatAm broad resale | authorized API | listings |
| Rakuten Ichiba | Japan retail/secondary opportunities | official API | listings |
| Ricardo | Switzerland broad second-hand | partner API/token | listings |
| PriceCharting Marketplace | videogames / consoles | licensed API | concrete available offers |
| CardTrader | Pokémon / MTG / One Piece / Lorcana / other TCG | official Bearer API | concrete marketplace products |

A source without its required credential remains `NO_CREDENTIALS`; the live engine continues with the other feeds. CardTrader is read-only in ROMAN: the API also exposes purchase/cart actions, but the engine never calls them.

## 2. Reference-only data wired into a separate database

Reference feeds are stored in `data/roman_reference.sqlite`, not in the market-listing database. They can make a bounded update to fair value but **cannot create an acquisition or exit route**.

| Source | Coverage | Access | ROMAN role |
|---|---|---|---|
| Cardmarket public downloads | Pokémon, MTG, Yu-Gi-Oh!, One Piece, Lorcana, etc. | official public download, no key | daily TCG catalogue / price guide |
| PriceCharting guide | videogames | licensed API | guide prices |
| BrickLink | LEGO | official API | stock price guide |
| Discogs | vinyl / music | official API | marketplace lowest-price statistics |
| TCG API | sealed TCG / broad TCG | licensed API | price references |
| WatchCharts | watches | official API | market / dealer / asking-price references |
| Keepa | Amazon products across electronics, games, LEGO, cameras, etc. | official paid API | Amazon retail/current-price reference |

Reference influence is deliberately conservative: entity matching must be exact or high confidence, extreme mismatches are ignored, and the aggregate reference weight on the market-derived base fair value is capped at 20%. Disagreement also increases predictive uncertainty.

TCGdex is tracked as an additional public no-auth Pokémon data source, but it is not automatically applied to graded/sealed inventory because raw-card price semantics are not equivalent to PSA/BGS/sealed-product prices.

## 3. Markets retained but not automatically collected without permission

These markets remain in ROMAN's strategic universe but are **not** backed by scraper adapters:

- Vinted
- Tutti
- Subito
- Wallapop
- Kleinanzeigen
- Leboncoin
- Facebook Marketplace
- Mercari
- Catawiki
- GOAT
- Grailed
- Depop
- Poshmark
- Swappa
- Back Market
- MPB / KEH
- CeX
- Delcampe
- AbeBooks
- Chrono24
- Vestiaire Collective

For these, ROMAN accepts future official APIs, licensed/partner feeds, or user-owned CSV/export data. It does not bypass CAPTCHA, robots controls, login restrictions, or anti-bot systems.

## 4. Restricted/existing-access APIs

Some platforms expose APIs but that does not imply general market discovery is currently obtainable:

- Whatnot Seller API is seller/inventory scoped and current documentation states new applicants are not being onboarded.
- TCGplayer documents that new API access is not currently being granted; ROMAN retains variables for already-approved credentials.
- Cardmarket's legacy API remains relevant to existing approved users, but new API applications are currently closed; ROMAN instead uses the official public download files.
- Vinted Pro integrations and Vestiaire professional integrations primarily solve seller inventory/order integration, not unrestricted public-market discovery.

## 5. Vertical coverage

### Videogames
Videogames are first-class ROMAN sectors. The live search plan includes retro games and systems such as EarthBound/SNES, Chrono Trigger, Pokémon GBA/Game Boy, Nintendo 64, Switch and PlayStation. PriceCharting marketplace offers are concrete listings; PriceCharting guide data and Keepa prices are reference-only. UPC/ePID identifiers are propagated on both PriceCharting and eBay when available so the same physical game can be resolved cross-market without aggressive fuzzy title matching.

### TCG
CardTrader supplies concrete marketplace products, while Cardmarket public downloads and optional TCG reference APIs provide price evidence. CardTrader normalized titles preserve the game name plus product/expansion so `Pokemon Booster Box 151` is not collapsed to a generic `Booster Box 151`.

### Watches
eBay/Ricardo can supply concrete listings while WatchCharts provides brand+reference market/dealer/asking-price evidence. Chrono24 remains a partnership target rather than an unapproved scraper source.

### LEGO, vinyl and electronics
BrickLink provides LEGO reference guides; Discogs provides vinyl marketplace statistics; Keepa provides Amazon reference prices for standardized retail goods. These remain separate from executable resale routes.

## 6. Operational inspection

Run:

```bash
python scripts/market_access_report.py
```

Each market is classified as one of:

- `READY_PUBLIC`
- `READY_CREDENTIALS`
- `NEEDS_CREDENTIALS`
- `EXISTING_ACCESS_ONLY`
- `PARTNER_REQUIRED`
- `PERMISSION_REQUIRED`

This registry is the source of truth for whether ROMAN may instantiate automated market discovery for a venue.

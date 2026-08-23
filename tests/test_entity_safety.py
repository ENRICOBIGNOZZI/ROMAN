from roman_arb.entity import entity_key, match_confidence, structured_codes


def _row(title: str, source: str = "x") -> dict:
    return {"title": title, "source": source, "condition": "", "extra_json": {}}


def test_storage_capacity_is_not_a_product_code():
    assert "256gb" not in structured_codes("iPhone 15 Pro 256GB")
    assert "512gb" not in structured_codes("MacBook Pro M3 14 512GB")


def test_same_storage_does_not_merge_unrelated_phones():
    iphone = entity_key(_row("Apple iPhone 15 Pro 256GB"))
    samsung = entity_key(_row("Samsung S24 Ultra 256GB"))
    assert iphone
    assert samsung
    assert iphone != samsung


def test_focal_length_is_not_a_cross_market_identity():
    assert "24-70" not in structured_codes("Sony FE 24-70 GM II")
    sony = entity_key(_row("Sony FE 24-70 GM II"))
    canon = entity_key(_row("Canon RF 24-70 F2.8 L IS USM"))
    assert sony != canon


def test_brand_anchored_numeric_reference_matches_same_object():
    a = entity_key(_row("LEGO Star Wars Millennium Falcon 75192 sealed"))
    b = entity_key(_row("LEGO 75192 UCS Millennium Falcon new"))
    assert a == b
    assert a.startswith("id:lego:75192")


def test_same_numeric_reference_with_different_brand_does_not_match():
    a = entity_key(_row("Rolex Explorer 124270"))
    b = entity_key(_row("Omega custom part 124270"))
    assert a != b
    assert match_confidence(_row("Rolex Explorer 124270"), _row("Omega custom part 124270")) <= 0.01


def test_alphanumeric_model_code_keeps_brand_anchor():
    a = entity_key(_row("Boss CE-2W Chorus Waza Craft"))
    assert a.startswith("id:boss:ce-2w")

from __future__ import annotations

import re
import json
from collections import Counter
from .feeds.base import RawListing

STOP = {
    "new", "used", "mint", "excellent", "rare", "authentic", "original", "sale",
    "free", "shipping", "the", "a", "an", "with", "box", "full", "set", "watch",
    "card", "cards", "shoe", "shoes", "sealed", "unopened", "genuine", "men", "women",
}

_CODE_RE = re.compile(r"\b[A-Z0-9][A-Z0-9._/-]{3,}\b", re.I)
_WORD_RE = re.compile(r"[a-z0-9]+", re.I)
_GRADE_RE = re.compile(r"\b(PSA|BGS|CGC|SGC)\s*([0-9]+(?:\.[0-9]+)?)\b", re.I)
_STORAGE_RE = re.compile(r"\b(64|128|256|512|1024|2048)\s*(GB|TB)\b", re.I)
_SIZE_RE = re.compile(r"\b(?:US|UK|EU|SIZE|SZ)\s*([0-9]{1,2}(?:\.[05])?)\b", re.I)
_TRAILING_SHOE_SIZE_RE = re.compile(r"(?:^|\s)([3-9]|1[0-8])(?:\.([05]))?$", re.I)
_YEAR_RE = re.compile(r"\b(19[5-9][0-9]|20[0-3][0-9])\b")
_MM_RE = re.compile(r"\b([0-9]{2,3})\s*MM\b", re.I)


def _tokens(title: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(title or "") if t.lower() not in STOP]


def structured_codes(title: str) -> tuple[str, ...]:
    out: list[str] = []
    for raw in _CODE_RE.findall(title or ""):
        t = raw.lower().strip("-_/. ")
        if len(t) < 4:
            continue
        has_digit = any(c.isdigit() for c in t)
        has_alpha = any(c.isalpha() for c in t)
        if has_digit and (has_alpha or len(t) >= 5):
            if t.isdigit() and 1950 <= int(t) <= 2039:
                continue
            out.append(t)
    return tuple(dict.fromkeys(out))


def structured_attributes(title: str, condition: str = "") -> dict[str, str]:
    text = f"{title or ''} {condition or ''}"
    attrs: dict[str, str] = {}
    m = _GRADE_RE.search(text)
    if m: attrs["grade"] = f"{m.group(1).lower()}:{m.group(2)}"
    m = _STORAGE_RE.search(text)
    if m: attrs["storage"] = f"{m.group(1)}{m.group(2).lower()}"
    m = _SIZE_RE.search(text)
    if m: attrs["size"] = m.group(1)
    elif any(k in text.lower() for k in ("jordan", "nike", "adidas", "yeezy", "new balance", "asics", "sneaker", "dunk", "air force")):
        m2 = _TRAILING_SHOE_SIZE_RE.search((title or "").strip())
        if m2: attrs["size"] = m2.group(1) + (("." + m2.group(2)) if m2.group(2) else "")
    m = _MM_RE.search(text)
    if m: attrs["mm"] = m.group(1)
    years = _YEAR_RE.findall(text)
    if years: attrs["year"] = years[0]
    low = text.lower()
    if any(x in low for x in ("sealed", "new in box", "new with tags", "deadstock", "unopened")):
        attrs["condition_class"] = "new"
    elif any(x in low for x in ("used", "pre-owned", "preowned", "worn", "opened")):
        attrs["condition_class"] = "used"
    return attrs


def canonical_title(title: str) -> str:
    toks = _tokens(title)
    return " ".join(toks[:18])


def canonical_fingerprint(title: str) -> str:
    toks = _tokens(title)
    if len(toks) < 3 or not any(any(c.isdigit() for c in t) for t in toks):
        return ""
    counts = Counter(toks)
    unique = sorted(counts)
    return "fp:" + " ".join(unique[:16])


def _row_fields(row: RawListing | dict):
    if isinstance(row, dict):
        extra = row.get("extra_json")
        if not isinstance(extra, dict):
            try: extra = json.loads(extra or "{}")
            except Exception: extra = {}
        global_key = str(row.get("global_product_key") or extra.get("global_product_key") or "").strip()
        return global_key, str(row.get("product_key") or "").strip(), str(row.get("title") or ""), str(row.get("source") or ""), str(row.get("condition") or "")
    extra = row.extra or {}
    return str(extra.get("global_product_key") or "").strip(), (row.product_key or "").strip(), row.title, row.source, row.condition


def entity_key(row: RawListing | dict) -> str:
    global_key, pk, title, source, _condition = _row_fields(row)
    if global_key:
        return "g:" + global_key.lower()
    codes = structured_codes(title)
    if codes:
        code = max(codes, key=lambda x: (sum(c.isdigit() for c in x), len(x)))
        attrs = structured_attributes(title)
        suffix = "|".join(f"{k}={v}" for k, v in sorted(attrs.items()) if k in {"grade", "size", "storage"})
        return "id:" + code + ("|" + suffix if suffix else "")
    if pk:
        return f"src:{source}:{pk.lower()}"
    return canonical_fingerprint(title)


def match_confidence(a: RawListing | dict, b: RawListing | dict) -> float:
    """High-precision entity resolution; conflicting structured attributes are vetoes."""
    ga, pka, ta, sa_source, ca_cond = _row_fields(a)
    gb, pkb, tb, sb_source, cb_cond = _row_fields(b)
    if ga and gb:
        return 1.0 if ga.lower() == gb.lower() else 0.0

    ca, cb = set(structured_codes(ta)), set(structured_codes(tb))
    attrs_a, attrs_b = structured_attributes(ta, ca_cond), structured_attributes(tb, cb_cond)
    for key in ("grade", "size", "storage", "mm"):
        if key in attrs_a and key in attrs_b and attrs_a[key] != attrs_b[key]:
            return 0.01
    if "condition_class" in attrs_a and "condition_class" in attrs_b and attrs_a["condition_class"] != attrs_b["condition_class"]:
        return 0.10

    if ca and cb:
        if ca & cb:
            base = 0.985
            shared_attrs = sum(attrs_a.get(k) == attrs_b.get(k) for k in attrs_a.keys() & attrs_b.keys())
            return min(0.999, base + 0.004 * shared_attrs)
        return 0.01

    if sa_source == sb_source and pka and pkb:
        return 0.995 if pka.lower() == pkb.lower() else 0.01

    wa, wb = set(_tokens(ta)), set(_tokens(tb))
    if not wa or not wb:
        return 0.0
    j = len(wa & wb) / max(len(wa | wb), 1)
    nums_a = {t for t in wa if any(c.isdigit() for c in t)}
    nums_b = {t for t in wb if any(c.isdigit() for c in t)}
    if nums_a and nums_b and not (nums_a & nums_b):
        return min(0.10, j)
    return max(0.0, min(0.90, 0.05 + 0.95 * j))

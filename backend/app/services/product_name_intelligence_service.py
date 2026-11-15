"""Conservative product-name normalization and alias matching."""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable


def normalize_product_name(value: str) -> str:
    """Normalize whitespace, punctuation and case while preserving Unicode letters."""
    if not isinstance(value, str):
        raise ValueError("Product name must be text.")
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def match_product_name(query: str, candidates: Iterable[dict], threshold: float = 0.88) -> dict:
    """Return exact/near alias candidates; never auto-merge product records.

    Candidate dicts require product_id and canonical_name; alias is optional.
    A fuzzy result is explicitly marked for human confirmation.
    """
    normalized = normalize_product_name(query)
    if not normalized:
        raise ValueError("Product name cannot be empty.")
    if not 0.5 <= threshold <= 1:
        raise ValueError("Threshold must be between 0.5 and 1.")

    best_by_product = {}
    for candidate in candidates:
        names = [candidate.get("canonical_name", ""), candidate.get("alias", "")]
        best = max(
            (SequenceMatcher(None, normalized, normalize_product_name(n)).ratio()
             for n in names if n),
            default=0.0,
        )
        if best >= threshold:
            product_id = candidate["product_id"]
            match = {
                "product_id": product_id,
                "canonical_name": candidate["canonical_name"],
                "confidence": round(best, 4),
                "match_type": "exact" if best == 1 else "fuzzy",
                "requires_confirmation": best != 1,
            }
            previous = best_by_product.get(product_id)
            if previous is None or match["confidence"] > previous["confidence"]:
                best_by_product[product_id] = match
    ranked = sorted(
        best_by_product.values(),
        key=lambda item: (-item["confidence"], item["product_id"]),
    )
    return {
        "query": query,
        "normalized_query": normalized,
        "matches": ranked[:5],
        "matched": bool(ranked),
    }

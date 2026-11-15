import pytest

from app.services.product_name_intelligence_service import (
    match_product_name,
    normalize_product_name,
)


def test_normalize_product_name_handles_case_punctuation_and_spaces():
    assert normalize_product_name("  Aashirvaad  Atta- 5KG ") == "aashirvaad atta 5kg"


def test_exact_alias_match_is_not_ambiguous():
    result = match_product_name("godhumai maavu", [
        {"product_id": 7, "canonical_name": "Wheat Flour", "alias": "Godhumai Maavu"},
    ])
    assert result["matched"] is True
    assert result["matches"][0]["product_id"] == 7
    assert result["matches"][0]["confidence"] == 1
    assert result["matches"][0]["requires_confirmation"] is False


def test_fuzzy_match_requires_human_confirmation():
    result = match_product_name("aashirvad atta", [
        {"product_id": 2, "canonical_name": "Aashirvaad Atta", "alias": ""},
    ], threshold=0.8)
    assert result["matched"] is True
    assert result["matches"][0]["requires_confirmation"] is True


def test_unrelated_product_does_not_match():
    result = match_product_name("toor dal", [
        {"product_id": 1, "canonical_name": "Bath Soap", "alias": "Soap"},
    ])
    assert result["matched"] is False
    assert result["matches"] == []


def test_blank_name_and_invalid_threshold_are_rejected():
    with pytest.raises(ValueError):
        match_product_name("   ", [])
    with pytest.raises(ValueError):
        match_product_name("rice", [], threshold=0.2)

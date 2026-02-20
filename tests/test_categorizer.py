"""Tests for the auto-categorization engine."""

import pytest

from src.core.categorizer import Categorizer


@pytest.fixture
def categorizer(tmp_path):
    """Categorizer backed by a temp file."""
    return Categorizer(mappings_file=str(tmp_path / "mappings.json"))


class TestLearnAndSuggest:
    def test_learn_single_transaction(self, categorizer):
        categorizer.learn_from_transactions([
            {"payee_name": "HEB", "category_id": "cat1", "category_name": "Groceries"},
        ])
        result = categorizer.suggest_category("HEB")
        assert result is not None
        assert result["category_id"] == "cat1"

    def test_case_insensitive_suggest(self, categorizer):
        categorizer.learn_from_transactions([
            {"payee_name": "Starbucks", "category_id": "cat2", "category_name": "Dining"},
        ])
        assert categorizer.suggest_category("starbucks") is not None
        assert categorizer.suggest_category("STARBUCKS") is not None

    def test_partial_match_payee_contains_key(self, categorizer):
        categorizer.learn_from_transactions([
            {"payee_name": "Amazon", "category_id": "cat3", "category_name": "Shopping"},
        ])
        result = categorizer.suggest_category("Amazon Prime")
        assert result is not None
        assert result["category_id"] == "cat3"

    def test_partial_match_key_contains_payee(self, categorizer):
        categorizer.learn_from_transactions([
            {"payee_name": "Amazon Prime", "category_id": "cat3", "category_name": "Shopping"},
        ])
        result = categorizer.suggest_category("Amazon")
        assert result is not None
        assert result["category_id"] == "cat3"

    def test_count_decay_overrides_mapping(self, categorizer):
        # Learn HEB -> Groceries (count=2)
        categorizer.learn_from_transactions([
            {"payee_name": "HEB", "category_id": "cat1", "category_name": "Groceries"},
            {"payee_name": "HEB", "category_id": "cat1", "category_name": "Groceries"},
        ])
        # Now learn HEB -> Dining 3 times (decays count to 0, then switches)
        categorizer.learn_from_transactions([
            {"payee_name": "HEB", "category_id": "cat2", "category_name": "Dining"},
            {"payee_name": "HEB", "category_id": "cat2", "category_name": "Dining"},
            {"payee_name": "HEB", "category_id": "cat2", "category_name": "Dining"},
        ])
        assert categorizer.suggest_category("HEB")["category_id"] == "cat2"

    def test_no_match_returns_none(self, categorizer):
        assert categorizer.suggest_category("Unknown Store") is None

    def test_empty_payee_returns_none(self, categorizer):
        assert categorizer.suggest_category("") is None

    def test_skips_transactions_without_payee(self, categorizer):
        categorizer.learn_from_transactions([
            {"payee_name": None, "category_id": "cat1", "category_name": "Groceries"},
            {"payee_name": "", "category_id": "cat1", "category_name": "Groceries"},
        ])
        assert categorizer.get_all_mappings() == {}


class TestPersistence:
    def test_persists_to_disk(self, tmp_path):
        path = str(tmp_path / "mappings.json")
        c1 = Categorizer(mappings_file=path)
        c1.learn_from_transactions([
            {"payee_name": "Target", "category_id": "cat5", "category_name": "Shopping"},
        ])
        # New instance, same file
        c2 = Categorizer(mappings_file=path)
        assert c2.suggest_category("Target")["category_id"] == "cat5"


class TestManualMapping:
    def test_add_mapping_overrides(self, categorizer):
        categorizer.learn_from_transactions([
            {"payee_name": "HEB", "category_id": "cat1", "category_name": "Groceries"},
        ])
        categorizer.add_mapping("HEB", "cat99", "Manual Category")
        assert categorizer.suggest_category("HEB")["category_id"] == "cat99"

    def test_clear_removes_all(self, categorizer):
        categorizer.learn_from_transactions([
            {"payee_name": "HEB", "category_id": "cat1", "category_name": "Groceries"},
        ])
        categorizer.clear()
        assert categorizer.suggest_category("HEB") is None
        assert categorizer.get_all_mappings() == {}

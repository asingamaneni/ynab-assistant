"""Tests for entity resolution helpers."""

import pytest

from tests.conftest import make_account, make_category, make_category_group, make_payee
from src.core.resolvers import ResolverError, resolve_account, resolve_category, resolve_category_or_inflow, resolve_payee


class TestResolveAccount:
    def test_exact_name_match(self):
        accounts = [make_account("Checking"), make_account("Savings", type_="savings")]
        assert resolve_account(accounts, "Checking").name == "Checking"

    def test_partial_case_insensitive_match(self):
        accounts = [make_account("My Checking Account")]
        assert resolve_account(accounts, "check").name == "My Checking Account"

    def test_default_prefers_checking(self):
        accounts = [
            make_account("Savings", type_="savings"),
            make_account("Checking"),
        ]
        assert resolve_account(accounts).name == "Checking"

    def test_default_falls_back_to_on_budget(self):
        accounts = [make_account("Savings", type_="savings")]
        assert resolve_account(accounts).name == "Savings"

    def test_skips_closed_accounts(self):
        accounts = [
            make_account("Old Checking", closed=True),
            make_account("New Savings", type_="savings"),
        ]
        with pytest.raises(ResolverError):
            resolve_account(accounts, "Old Checking")

    def test_no_match_raises_with_available(self):
        accounts = [make_account("Checking")]
        with pytest.raises(ResolverError) as exc_info:
            resolve_account(accounts, "Credit Card")
        assert "Checking" in str(exc_info.value)

    def test_no_accounts_raises(self):
        with pytest.raises(ResolverError):
            resolve_account([])

    def test_skips_off_budget_for_default(self):
        accounts = [make_account("Tracking", type_="savings", on_budget=False)]
        with pytest.raises(ResolverError):
            resolve_account(accounts)


class TestResolveCategory:
    def test_finds_category_across_groups(self):
        groups = [
            make_category_group("Bills", categories=[make_category("Rent")]),
            make_category_group("Food", categories=[make_category("Groceries")]),
        ]
        assert resolve_category(groups, "Groceries").name == "Groceries"

    def test_partial_case_insensitive_match(self):
        groups = [
            make_category_group("Food", categories=[make_category("Dining Out")]),
        ]
        assert resolve_category(groups, "dining").name == "Dining Out"

    def test_skips_hidden_categories(self):
        groups = [
            make_category_group(
                "Food",
                categories=[make_category("Old Groceries", hidden=True)],
            ),
        ]
        with pytest.raises(ResolverError):
            resolve_category(groups, "Groceries")

    def test_no_match_raises(self):
        groups = [
            make_category_group("Food", categories=[make_category("Groceries")]),
        ]
        with pytest.raises(ResolverError):
            resolve_category(groups, "Entertainment")


class TestResolveCategoryOrInflow:
    def _make_groups_with_inflow(self):
        inflow_cat = make_category("Inflow: Ready to Assign", group_id="grp-internal")
        return [
            make_category_group(
                "Internal Master Category",
                categories=[inflow_cat],
            ),
            make_category_group("Food", categories=[make_category("Groceries")]),
        ]

    def test_resolves_inflow_category(self):
        groups = self._make_groups_with_inflow()
        result = resolve_category_or_inflow(groups, "Inflow: Ready to Assign")
        assert result.name == "Inflow: Ready to Assign"

    def test_resolves_inflow_partial_match(self):
        groups = self._make_groups_with_inflow()
        result = resolve_category_or_inflow(groups, "inflow")
        assert result.name == "Inflow: Ready to Assign"

    def test_resolves_inflow_case_insensitive(self):
        groups = self._make_groups_with_inflow()
        result = resolve_category_or_inflow(groups, "INFLOW")
        assert result.name == "Inflow: Ready to Assign"

    def test_ready_to_assign_alias_resolves_inflow(self):
        """'ready to assign' is an explicit inflow alias."""
        groups = self._make_groups_with_inflow()
        result = resolve_category_or_inflow(groups, "ready to assign")
        assert result.name == "Inflow: Ready to Assign"

    def test_substring_inflow_falls_through(self):
        """'cashflow' contains 'inflow' as a substring but should NOT match the inflow category."""
        groups = self._make_groups_with_inflow()
        with pytest.raises(ResolverError):
            resolve_category_or_inflow(groups, "cashflow")

    def test_falls_back_to_regular_category(self):
        groups = self._make_groups_with_inflow()
        result = resolve_category_or_inflow(groups, "Groceries")
        assert result.name == "Groceries"

    def test_no_match_raises(self):
        groups = self._make_groups_with_inflow()
        with pytest.raises(ResolverError):
            resolve_category_or_inflow(groups, "Entertainment")


class TestResolvePayee:
    def test_exact_name_match(self):
        payees = [make_payee("HEB"), make_payee("Costco")]
        assert resolve_payee(payees, "HEB").name == "HEB"

    def test_partial_case_insensitive(self):
        payees = [make_payee("HEB"), make_payee("Costco")]
        assert resolve_payee(payees, "he").name == "HEB"

    def test_skips_deleted_payees(self):
        payees = [make_payee("HEB", deleted=True)]
        with pytest.raises(ResolverError):
            resolve_payee(payees, "HEB")

    def test_no_match_raises(self):
        payees = [make_payee("HEB"), make_payee("Costco")]
        with pytest.raises(ResolverError) as exc_info:
            resolve_payee(payees, "Walmart")
        assert "HEB" in str(exc_info.value)
        assert "Costco" in str(exc_info.value)

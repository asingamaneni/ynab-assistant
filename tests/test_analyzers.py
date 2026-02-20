"""Tests for src/core/analyzers.py."""

from datetime import date

import pytest

from tests.conftest import make_account, make_category, make_category_group, make_transaction
from src.core.analyzers import (
    analyze_credit_cards,
    analyze_overspending,
    analyze_spending_trends,
    build_subtransactions,
    check_affordability,
    compute_budget_assignments,
    filter_transactions,
    find_uncategorized_transactions,
    forecast_spending,
    validate_split_amounts,
)
from src.models.results import SplitItem
from src.models.schemas import dollars_to_milliunits


# --- Spending Trend Analysis ---


class TestAnalyzeSpendingTrends:
    def test_groups_by_month_and_category(self):
        txns = [
            make_transaction(payee_name="HEB", amount=-50000, category_name="Groceries", date="2025-01-10"),
            make_transaction(payee_name="HEB", amount=-60000, category_name="Groceries", date="2025-02-10"),
            make_transaction(payee_name="HEB", amount=-55000, category_name="Groceries", date="2025-03-10"),
        ]
        result = analyze_spending_trends(txns, num_months=3, reference_date=date(2025, 3, 15))
        assert "2025-01" in result.monthly_totals
        assert "2025-02" in result.monthly_totals
        assert "2025-03" in result.monthly_totals
        assert result.monthly_totals["2025-01"]["Groceries"] == 50.0
        assert result.monthly_totals["2025-02"]["Groceries"] == 60.0
        assert result.monthly_totals["2025-03"]["Groceries"] == 55.0

    def test_category_filter(self):
        txns = [
            make_transaction(payee_name="HEB", amount=-50000, category_name="Groceries", date="2025-03-10"),
            make_transaction(payee_name="Uber", amount=-20000, category_name="Transport", date="2025-03-10"),
        ]
        result = analyze_spending_trends(txns, num_months=1, category_name="Groceries", reference_date=date(2025, 3, 15))
        assert "Groceries" in result.monthly_totals["2025-03"]
        assert "Transport" not in result.monthly_totals["2025-03"]

    def test_anomaly_detection(self):
        txns = [
            make_transaction(payee_name="HEB", amount=-50000, category_name="Groceries", date="2025-01-10"),
            make_transaction(payee_name="HEB", amount=-50000, category_name="Groceries", date="2025-02-10"),
            # Huge spike in March
            make_transaction(payee_name="HEB", amount=-150000, category_name="Groceries", date="2025-03-10"),
        ]
        result = analyze_spending_trends(txns, num_months=3, reference_date=date(2025, 3, 15))
        assert len(result.anomalies) == 1
        assert result.anomalies[0].category_name == "Groceries"
        assert result.anomalies[0].pct_above_average > 50

    def test_no_anomaly_when_within_threshold(self):
        txns = [
            make_transaction(payee_name="HEB", amount=-50000, category_name="Groceries", date="2025-01-10"),
            make_transaction(payee_name="HEB", amount=-50000, category_name="Groceries", date="2025-02-10"),
            make_transaction(payee_name="HEB", amount=-55000, category_name="Groceries", date="2025-03-10"),
        ]
        result = analyze_spending_trends(txns, num_months=3, reference_date=date(2025, 3, 15))
        assert len(result.anomalies) == 0

    def test_excludes_inflows(self):
        txns = [
            make_transaction(payee_name="Refund", amount=50000, category_name="Groceries", date="2025-03-10"),
            make_transaction(payee_name="HEB", amount=-20000, category_name="Groceries", date="2025-03-10"),
        ]
        result = analyze_spending_trends(txns, num_months=1, reference_date=date(2025, 3, 15))
        assert result.monthly_totals["2025-03"]["Groceries"] == 20.0

    def test_excludes_deleted(self):
        txns = [
            make_transaction(payee_name="HEB", amount=-50000, category_name="Groceries", date="2025-03-10", deleted=True),
        ]
        result = analyze_spending_trends(txns, num_months=1, reference_date=date(2025, 3, 15))
        assert "Groceries" not in result.monthly_totals.get("2025-03", {})

    def test_empty_transactions(self):
        result = analyze_spending_trends([], num_months=3, reference_date=date(2025, 3, 15))
        assert all(not cats for cats in result.monthly_totals.values())
        assert len(result.anomalies) == 0


# --- Uncategorized Transaction Review ---


class TestFindUncategorizedTransactions:
    def test_finds_uncategorized(self):
        txns = [
            make_transaction(category_id=None, category_name=None),
            make_transaction(category_id="cat-1", category_name="Groceries"),
        ]
        result = find_uncategorized_transactions(txns)
        assert len(result) == 1
        assert result[0].category_id is None

    def test_excludes_deleted(self):
        txns = [
            make_transaction(category_id=None, category_name=None, deleted=True),
        ]
        result = find_uncategorized_transactions(txns)
        assert len(result) == 0

    def test_empty_list(self):
        assert find_uncategorized_transactions([]) == []


# --- Cover Overspending ---


class TestAnalyzeOverspending:
    def test_identifies_overspent_and_sources(self):
        groups = [
            make_category_group("Bills", categories=[
                make_category("Rent", balance=-50000),
                make_category("Electric", balance=20000),
            ]),
            make_category_group("Fun", categories=[
                make_category("Dining", balance=100000),
            ]),
        ]
        result = analyze_overspending(groups)
        assert len(result.overspent) == 1
        assert result.overspent[0].name == "Rent"
        assert len(result.sources) == 2
        assert result.total_overspent == 50.0

    def test_suggests_moves(self):
        groups = [
            make_category_group("Bills", categories=[
                make_category("Rent", balance=-50000),
            ]),
            make_category_group("Fun", categories=[
                make_category("Dining", balance=100000),
            ]),
        ]
        result = analyze_overspending(groups)
        assert len(result.suggestions) == 1
        assert result.suggestions[0].from_category == "Dining"
        assert result.suggestions[0].to_category == "Rent"
        assert result.suggestions[0].amount == 50.0

    def test_skips_internal_groups(self):
        groups = [
            make_category_group("Internal Master Category", categories=[
                make_category("Inflow", balance=-999000),
            ]),
            make_category_group("Fun", categories=[
                make_category("Dining", balance=100000),
            ]),
        ]
        result = analyze_overspending(groups)
        assert len(result.overspent) == 0

    def test_skips_hidden_categories(self):
        groups = [
            make_category_group("Bills", categories=[
                make_category("Old Bill", balance=-50000, hidden=True),
            ]),
        ]
        result = analyze_overspending(groups)
        assert len(result.overspent) == 0

    def test_no_overspending(self):
        groups = [
            make_category_group("Fun", categories=[
                make_category("Dining", balance=100000),
            ]),
        ]
        result = analyze_overspending(groups)
        assert len(result.overspent) == 0
        assert result.total_overspent == 0.0

    def test_suggestion_respects_source_capacity(self):
        groups = [
            make_category_group("Bills", categories=[
                make_category("Rent", balance=-100000),
                make_category("Electric", balance=-30000),
            ]),
            make_category_group("Fun", categories=[
                make_category("Dining", balance=80000),
            ]),
        ]
        result = analyze_overspending(groups)
        # Dining has $80 but needs to cover $100 + $30 = $130
        total_suggested = sum(s.amount for s in result.suggestions)
        assert total_suggested <= 80.0


# --- Affordability Check ---


class TestCheckAffordability:
    def test_can_afford(self):
        cat = make_category("Dining", budgeted=200000, activity=-80000, balance=120000)
        result = check_affordability(cat, 50.0)
        assert result.can_afford is True
        assert result.remaining_after == 70.0

    def test_cannot_afford(self):
        cat = make_category("Dining", budgeted=200000, activity=-180000, balance=20000)
        result = check_affordability(cat, 50.0)
        assert result.can_afford is False
        assert result.remaining_after == -30.0

    def test_exact_match(self):
        cat = make_category("Dining", budgeted=100000, activity=-50000, balance=50000)
        result = check_affordability(cat, 50.0)
        assert result.can_afford is True
        assert result.remaining_after == 0.0

    def test_zero_budget_no_division_error(self):
        cat = make_category("Dining", budgeted=0, activity=0, balance=0)
        result = check_affordability(cat, 10.0)
        assert result.utilization_pct == 0.0

    def test_utilization_percentage(self):
        cat = make_category("Dining", budgeted=200000, activity=-100000, balance=100000)
        result = check_affordability(cat, 10.0)
        assert result.utilization_pct == 50.0


# --- Enhanced Transaction Search ---


class TestFilterTransactions:
    def _make_txns(self):
        return [
            make_transaction(payee_name="Amazon", amount=-50000, category_name="Shopping",
                             account_name="Checking", memo="Prime order", date="2025-03-10"),
            make_transaction(payee_name="HEB", amount=-30000, category_name="Groceries",
                             account_name="Checking", date="2025-03-11"),
            make_transaction(payee_name="Starbucks", amount=-5000, category_name="Dining",
                             account_name="Credit Card", date="2025-03-12"),
            make_transaction(payee_name="Unknown", amount=-75000, category_id=None,
                             category_name=None, account_name="Checking", date="2025-03-13"),
        ]

    def test_filter_by_payee(self):
        result = filter_transactions(self._make_txns(), payee_name="amazon")
        assert len(result) == 1
        assert result[0].payee_name == "Amazon"

    def test_filter_by_amount_range(self):
        result = filter_transactions(self._make_txns(), min_amount=20, max_amount=60)
        assert len(result) == 2  # Amazon ($50) and HEB ($30)

    def test_filter_by_memo(self):
        result = filter_transactions(self._make_txns(), memo_contains="prime")
        assert len(result) == 1
        assert result[0].payee_name == "Amazon"

    def test_filter_by_category(self):
        result = filter_transactions(self._make_txns(), category_name="dining")
        assert len(result) == 1
        assert result[0].payee_name == "Starbucks"

    def test_filter_by_account(self):
        result = filter_transactions(self._make_txns(), account_name="credit")
        assert len(result) == 1
        assert result[0].payee_name == "Starbucks"

    def test_uncategorized_only(self):
        result = filter_transactions(self._make_txns(), uncategorized_only=True)
        assert len(result) == 1
        assert result[0].payee_name == "Unknown"

    def test_combined_filters(self):
        result = filter_transactions(self._make_txns(), account_name="checking", min_amount=40)
        assert len(result) == 2  # Amazon ($50) and Unknown ($75)

    def test_excludes_deleted(self):
        txns = [make_transaction(deleted=True)]
        result = filter_transactions(txns)
        assert len(result) == 0


# --- Split Transaction Helpers ---


class TestSplitTransactions:
    def test_validate_amounts_match(self):
        splits = [SplitItem("Groceries", 120.0), SplitItem("Household", 80.0)]
        validate_split_amounts(200.0, splits)  # Should not raise

    def test_validate_amounts_mismatch(self):
        splits = [SplitItem("Groceries", 120.0), SplitItem("Household", 50.0)]
        with pytest.raises(ValueError, match="Split amounts sum to"):
            validate_split_amounts(200.0, splits)

    def test_validate_amounts_rounding_tolerance(self):
        splits = [SplitItem("A", 33.33), SplitItem("B", 33.33), SplitItem("C", 33.34)]
        validate_split_amounts(100.0, splits)  # Should not raise

    def test_build_subtransactions(self):
        splits = [SplitItem("Groceries", 120.0, "food"), SplitItem("Household", 80.0)]
        resolved = {
            "Groceries": ("cat-1", "Groceries"),
            "Household": ("cat-2", "Household"),
        }
        result = build_subtransactions(splits, resolved)
        assert len(result) == 2
        assert result[0]["category_id"] == "cat-1"
        assert result[0]["amount"] == dollars_to_milliunits(-120.0)
        assert result[0]["memo"] == "food"
        assert result[1]["memo"] is None


# --- Monthly Budget Setup ---


class TestComputeBudgetAssignments:
    def test_last_month_budget_strategy(self):
        cats = [
            make_category("Groceries", budgeted=500000, activity=-450000),
            make_category("Dining", budgeted=200000, activity=-180000),
        ]
        result = compute_budget_assignments(cats, "last_month_budget")
        assert len(result) == 2
        assert result[0].proposed_budgeted == 500.0
        assert result[1].proposed_budgeted == 200.0

    def test_last_month_actual_strategy(self):
        cats = [
            make_category("Groceries", budgeted=500000, activity=-450000),
            make_category("Dining", budgeted=200000, activity=-180000),
        ]
        result = compute_budget_assignments(cats, "last_month_actual")
        assert result[0].proposed_budgeted == 450.0
        assert result[1].proposed_budgeted == 180.0

    def test_skips_hidden_categories(self):
        cats = [
            make_category("Groceries", budgeted=500000),
            make_category("Old", budgeted=100000, hidden=True),
        ]
        result = compute_budget_assignments(cats, "last_month_budget")
        assert len(result) == 1


# --- Credit Card Analysis ---


class TestAnalyzeCreditCards:
    def test_matches_cc_to_payment_category(self):
        accounts = [
            make_account("Chase Sapphire", type_="creditCard", balance=-500000),
        ]
        groups = [
            make_category_group("Credit Card Payments", categories=[
                make_category("Chase Sapphire", balance=500000),
            ]),
        ]
        result = analyze_credit_cards(accounts, groups)
        assert len(result.cards) == 1
        assert result.cards[0].payment_available == 500.0
        assert result.cards[0].discrepancy == 0.0
        assert result.total_owed == 500.0

    def test_detects_underfunded(self):
        accounts = [
            make_account("Chase", type_="creditCard", balance=-500000),
        ]
        groups = [
            make_category_group("Credit Card Payments", categories=[
                make_category("Chase", balance=300000),
            ]),
        ]
        result = analyze_credit_cards(accounts, groups)
        assert result.cards[0].discrepancy == -200.0

    def test_skips_closed_accounts(self):
        accounts = [
            make_account("Old Card", type_="creditCard", closed=True, balance=-100000),
        ]
        groups = []
        result = analyze_credit_cards(accounts, groups)
        assert len(result.cards) == 0

    def test_no_matching_payment_category(self):
        accounts = [
            make_account("New Card", type_="creditCard", balance=-200000),
        ]
        groups = [
            make_category_group("Monthly Bills", categories=[
                make_category("Rent"),
            ]),
        ]
        result = analyze_credit_cards(accounts, groups)
        assert result.cards[0].payment_category_name is None
        assert result.cards[0].payment_available == 0.0


# --- Spending Forecast ---


class TestForecastSpending:
    def test_mid_month_projection(self):
        cat = make_category("Groceries", budgeted=500000)
        txns = [
            make_transaction(amount=-25000, date="2025-03-01"),
            make_transaction(amount=-25000, date="2025-03-05"),
            make_transaction(amount=-25000, date="2025-03-10"),
        ]
        result = forecast_spending(cat, txns, reference_date=date(2025, 3, 15))
        assert result.spent_so_far == 75.0
        assert result.days_elapsed == 15
        assert result.days_remaining == 16
        assert result.daily_rate == 5.0
        assert result.projected_total == 155.0
        assert result.will_stay_in_budget is True

    def test_over_budget_projection(self):
        cat = make_category("Dining", budgeted=100000)
        txns = [
            make_transaction(amount=-50000, date="2025-03-01"),
            make_transaction(amount=-30000, date="2025-03-05"),
        ]
        result = forecast_spending(cat, txns, reference_date=date(2025, 3, 10))
        assert result.spent_so_far == 80.0
        assert result.will_stay_in_budget is False

    def test_first_day_of_month(self):
        cat = make_category("Groceries", budgeted=500000)
        txns = [
            make_transaction(amount=-10000, date="2025-03-01"),
        ]
        result = forecast_spending(cat, txns, reference_date=date(2025, 3, 1))
        assert result.days_elapsed == 1
        assert result.days_remaining == 30

    def test_last_day_of_month(self):
        cat = make_category("Groceries", budgeted=500000)
        txns = [
            make_transaction(amount=-400000, date="2025-03-25"),
        ]
        result = forecast_spending(cat, txns, reference_date=date(2025, 3, 31))
        assert result.days_remaining == 0
        assert result.projected_total == result.spent_so_far

    def test_no_transactions(self):
        cat = make_category("Groceries", budgeted=500000)
        result = forecast_spending(cat, [], reference_date=date(2025, 3, 15))
        assert result.spent_so_far == 0.0
        assert result.daily_rate == 0.0
        assert result.will_stay_in_budget is True

    def test_excludes_inflows(self):
        cat = make_category("Groceries", budgeted=500000)
        txns = [
            make_transaction(amount=-50000, date="2025-03-05"),
            make_transaction(amount=20000, date="2025-03-06"),  # refund
        ]
        result = forecast_spending(cat, txns, reference_date=date(2025, 3, 10))
        assert result.spent_so_far == 50.0  # only outflow counts

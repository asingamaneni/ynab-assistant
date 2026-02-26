"""Tests for src/core/analyzers.py."""

from datetime import date

import pytest

from tests.conftest import make_account, make_category, make_category_group, make_scheduled_transaction, make_transaction
from src.core.analyzers import (
    analyze_credit_cards,
    analyze_overspending,
    analyze_spending_trends,
    build_subtransactions,
    check_affordability,
    compute_budget_assignments,
    compute_bulk_transaction_updates,
    compute_category_target_updates,
    compute_scheduled_transaction_updates,
    compute_transaction_updates,
    filter_scheduled_transaction_by_description,
    filter_transaction_by_description,
    filter_transactions,
    filter_uncategorized_transactions,
    forecast_spending,
    validate_split_amounts,
)
from src.models.results import FieldChange, SplitItem
from src.models.schemas import BulkTransactionUpdateInput, TransactionFlagColor, dollars_to_milliunits


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
        result = filter_uncategorized_transactions(txns)
        assert len(result) == 1
        assert result[0].category_id is None

    def test_excludes_deleted(self):
        txns = [
            make_transaction(category_id=None, category_name=None, deleted=True),
        ]
        result = filter_uncategorized_transactions(txns)
        assert len(result) == 0

    def test_empty_list(self):
        assert filter_uncategorized_transactions([]) == []


class TestFindTransactionByDescription:
    def test_matches_by_payee(self):
        txns = [
            make_transaction(payee_name="Walmart", amount=-174010),
            make_transaction(payee_name="HEB", amount=-45000),
        ]
        result = filter_transaction_by_description(txns, "walmart")
        assert result is not None
        assert result.payee_name == "Walmart"

    def test_matches_by_memo(self):
        txns = [make_transaction(memo="Monthly CC payment")]
        result = filter_transaction_by_description(txns, "cc payment")
        assert result is not None

    def test_matches_by_date(self):
        txns = [make_transaction(date="2025-01-15")]
        result = filter_transaction_by_description(txns, "2025-01-15")
        assert result is not None

    def test_matches_by_amount(self):
        txns = [make_transaction(amount=-174010)]
        result = filter_transaction_by_description(txns, "174.01")
        assert result is not None

    def test_skips_deleted(self):
        txns = [make_transaction(payee_name="Walmart", deleted=True)]
        result = filter_transaction_by_description(txns, "walmart")
        assert result is None

    def test_returns_none_when_no_match(self):
        txns = [make_transaction(payee_name="HEB")]
        result = filter_transaction_by_description(txns, "costco")
        assert result is None

    def test_finds_categorized_transactions(self):
        txns = [make_transaction(payee_name="Vanguard", category_id="cat-1", category_name="Business")]
        result = filter_transaction_by_description(txns, "vanguard")
        assert result is not None
        assert result.category_name == "Business"


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


# --- Transaction Update Builder ---


class TestBuildTransactionUpdates:
    def test_updates_memo(self):
        txn = make_transaction(memo="old memo")
        updates, changes = compute_transaction_updates(txn, memo="new memo")
        assert updates == {"memo": "new memo"}
        assert len(changes) == 1
        assert changes[0].field_name == "Memo"
        assert changes[0].old_value == "old memo"
        assert changes[0].new_value == "new memo"

    def test_clears_memo_with_empty_string(self):
        txn = make_transaction(memo="some memo")
        updates, changes = compute_transaction_updates(txn, memo="")
        assert updates == {"memo": ""}
        assert changes[0].new_value == "(cleared)"

    def test_adds_memo_when_none(self):
        txn = make_transaction(memo=None)
        updates, changes = compute_transaction_updates(txn, memo="new note")
        assert updates == {"memo": "new note"}
        assert changes[0].old_value == "(none)"

    def test_updates_category(self):
        txn = make_transaction(category_id="cat-groceries", category_name="Groceries")
        updates, changes = compute_transaction_updates(
            txn, category_id="cat-dining", category_name="Dining"
        )
        assert updates == {"category_id": "cat-dining"}
        assert changes[0].field_name == "Category"
        assert changes[0].old_value == "Groceries"
        assert changes[0].new_value == "Dining"

    def test_updates_payee(self):
        txn = make_transaction(payee_name="HEB")
        updates, changes = compute_transaction_updates(txn, payee_name="Costco")
        assert updates == {"payee_name": "Costco"}
        assert changes[0].old_value == "HEB"
        assert changes[0].new_value == "Costco"

    def test_updates_date(self):
        txn = make_transaction(date="2025-01-15")
        updates, changes = compute_transaction_updates(txn, date="2025-01-20")
        assert updates == {"date": "2025-01-20"}
        assert changes[0].old_value == "2025-01-15"
        assert changes[0].new_value == "2025-01-20"

    def test_updates_amount(self):
        txn = make_transaction(amount=-45000)
        updates, changes = compute_transaction_updates(txn, amount_milliunits=-60000)
        assert updates == {"amount": -60000}
        assert changes[0].field_name == "Amount"
        assert "$45.00" in changes[0].old_value
        assert "$60.00" in changes[0].new_value

    def test_updates_flag_color(self):
        txn = make_transaction()
        updates, changes = compute_transaction_updates(txn, flag_color="red")
        assert updates == {"flag_color": "red"}
        assert changes[0].old_value == "(none)"
        assert changes[0].new_value == "red"

    def test_updates_cleared(self):
        txn = make_transaction()
        updates, changes = compute_transaction_updates(txn, cleared="cleared")
        assert updates == {"cleared": "cleared"}
        assert changes[0].old_value == "uncleared"
        assert changes[0].new_value == "cleared"

    def test_skips_unchanged_fields(self):
        txn = make_transaction(memo="same memo", payee_name="HEB")
        updates, changes = compute_transaction_updates(
            txn, memo="same memo", payee_name="HEB"
        )
        assert updates == {}
        assert changes == []

    def test_multiple_fields_at_once(self):
        txn = make_transaction(memo=None, payee_name="HEB", date="2025-01-15")
        updates, changes = compute_transaction_updates(
            txn, memo="new note", payee_name="Costco", date="2025-02-01"
        )
        assert "memo" in updates
        assert "payee_name" in updates
        assert "date" in updates
        assert len(changes) == 3

    def test_none_parameters_are_ignored(self):
        txn = make_transaction()
        updates, changes = compute_transaction_updates(txn)
        assert updates == {}
        assert changes == []


# --- Scheduled Transaction Lookup ---


class TestFindScheduledTransactionByDescription:
    def test_finds_by_payee(self):
        sts = [make_scheduled_transaction(payee_name="Netflix")]
        result = filter_scheduled_transaction_by_description(sts, "Netflix")
        assert result is not None
        assert result.payee_name == "Netflix"

    def test_finds_by_date_next(self):
        sts = [make_scheduled_transaction(date_next="2025-02-01")]
        result = filter_scheduled_transaction_by_description(sts, "2025-02-01")
        assert result is not None

    def test_finds_by_amount(self):
        sts = [make_scheduled_transaction(amount=-15990)]
        result = filter_scheduled_transaction_by_description(sts, "15.99")
        assert result is not None

    def test_skips_deleted(self):
        sts = [make_scheduled_transaction(payee_name="Netflix", deleted=True)]
        result = filter_scheduled_transaction_by_description(sts, "Netflix")
        assert result is None

    def test_no_match_returns_none(self):
        sts = [make_scheduled_transaction(payee_name="Netflix")]
        result = filter_scheduled_transaction_by_description(sts, "Spotify")
        assert result is None


# --- Scheduled Transaction Update Builder ---


class TestComputeScheduledTransactionUpdates:
    def test_updates_date(self):
        st = make_scheduled_transaction(date_next="2025-02-01")
        payload, changes = compute_scheduled_transaction_updates(st, date="2025-03-01")
        assert payload == {"date": "2025-03-01"}
        assert len(changes) == 1
        assert changes[0] == FieldChange(field_name="Date", old_value="2025-02-01", new_value="2025-03-01")

    def test_updates_frequency(self):
        st = make_scheduled_transaction(frequency="monthly")
        payload, changes = compute_scheduled_transaction_updates(st, frequency_value="weekly")
        assert payload == {"frequency": "weekly"}
        assert changes[0] == FieldChange(field_name="Frequency", old_value="monthly", new_value="weekly")

    def test_updates_amount(self):
        st = make_scheduled_transaction(amount=-15990)
        new_amt = dollars_to_milliunits(-abs(20.0))
        payload, changes = compute_scheduled_transaction_updates(st, amount_milliunits=new_amt)
        assert payload == {"amount": new_amt}
        assert changes[0].field_name == "Amount"
        assert "$15.99" in changes[0].old_value
        assert "$20.00" in changes[0].new_value

    def test_updates_payee(self):
        st = make_scheduled_transaction(payee_name="Netflix")
        payload, changes = compute_scheduled_transaction_updates(st, payee="Hulu")
        assert payload == {"payee_name": "Hulu"}
        assert changes[0] == FieldChange(field_name="Payee", old_value="Netflix", new_value="Hulu")

    def test_updates_category(self):
        st = make_scheduled_transaction(category_name="Subscriptions")
        payload, changes = compute_scheduled_transaction_updates(
            st, category_id="cat-entertainment", category_name="Entertainment"
        )
        assert payload == {"category_id": "cat-entertainment"}
        assert changes[0] == FieldChange(field_name="Category", old_value="Subscriptions", new_value="Entertainment")

    def test_updates_memo(self):
        st = make_scheduled_transaction(memo="old note")
        payload, changes = compute_scheduled_transaction_updates(st, memo="new note")
        assert payload == {"memo": "new note"}
        assert changes[0] == FieldChange(field_name="Memo", old_value="old note", new_value="new note")

    def test_clears_memo(self):
        st = make_scheduled_transaction(memo="old note")
        payload, changes = compute_scheduled_transaction_updates(st, memo="")
        assert payload == {"memo": ""}
        assert changes[0] == FieldChange(field_name="Memo", old_value="old note", new_value="(cleared)")

    def test_updates_flag(self):
        st = make_scheduled_transaction()
        payload, changes = compute_scheduled_transaction_updates(st, flag_color="red")
        assert payload == {"flag_color": "red"}
        assert changes[0] == FieldChange(field_name="Flag", old_value="(none)", new_value="red")

    def test_none_parameters_are_ignored(self):
        st = make_scheduled_transaction()
        payload, changes = compute_scheduled_transaction_updates(st)
        assert payload == {}
        assert changes == []

    def test_multiple_fields_at_once(self):
        st = make_scheduled_transaction(payee_name="Netflix", memo=None)
        payload, changes = compute_scheduled_transaction_updates(
            st, payee="Hulu", memo="shared account", date="2025-04-01"
        )
        assert "payee_name" in payload
        assert "memo" in payload
        assert "date" in payload
        assert len(changes) == 3


# --- Bulk Transaction Update Builder ---


class TestComputeBulkTransactionUpdateInputs:
    def test_matches_and_builds_updates(self):
        txns = [make_transaction(payee_name="HEB", amount=-45000)]
        groups = [make_category_group(
            name="Food", categories=[make_category(name="Dining", group_id="grp-food")]
        )]
        updates = [BulkTransactionUpdateInput(
            transaction_description="HEB", category_name="Dining"
        )]
        api_updates, errors = compute_bulk_transaction_updates(txns, groups, updates)
        assert len(api_updates) == 1
        assert api_updates[0]["category_id"] == "cat-dining"
        assert errors == []

    def test_collects_unmatched_errors(self):
        txns = [make_transaction(payee_name="HEB")]
        groups = []
        updates = [BulkTransactionUpdateInput(
            transaction_description="Nonexistent", memo="test"
        )]
        api_updates, errors = compute_bulk_transaction_updates(txns, groups, updates)
        assert len(api_updates) == 0
        assert len(errors) == 1
        assert "Nonexistent" in errors[0]

    def test_deduplicates_by_transaction_id(self):
        txns = [make_transaction(payee_name="HEB", date="2025-01-15")]
        groups = []
        updates = [
            BulkTransactionUpdateInput(transaction_description="HEB", memo="first"),
            BulkTransactionUpdateInput(transaction_description="HEB", memo="second"),
        ]
        api_updates, errors = compute_bulk_transaction_updates(txns, groups, updates)
        assert len(api_updates) == 1
        assert api_updates[0]["memo"] == "second"

    def test_updates_flag_and_cleared(self):
        txns = [make_transaction(payee_name="HEB")]
        groups = []
        updates = [BulkTransactionUpdateInput(
            transaction_description="HEB", flag_color=TransactionFlagColor.RED, approved=True
        )]
        api_updates, errors = compute_bulk_transaction_updates(txns, groups, updates)
        assert len(api_updates) == 1
        assert api_updates[0]["flag_color"] == "red"
        assert api_updates[0]["approved"] is True


# --- Category Target Updates ---


class TestComputeCategoryTargetUpdates:
    def test_set_new_target_no_existing_goal(self):
        cat = make_category(name="Vacation", budgeted=100_000, balance=50_000)
        updates, result = compute_category_target_updates(
            cat, target_amount_milliunits=500_000, target_date=None, clear=False
        )
        assert updates == {"goal_target": 500_000}
        assert result.action == "set"
        assert result.new_target == 500.0
        assert result.old_target is None
        assert result.new_target_date is None

    def test_update_existing_target(self):
        cat = make_category(
            name="Vacation", goal_type="NEED", goal_target=300_000
        )
        updates, result = compute_category_target_updates(
            cat, target_amount_milliunits=500_000, target_date=None, clear=False
        )
        assert updates == {"goal_target": 500_000}
        assert result.action == "updated"
        assert result.old_target == 300.0
        assert result.new_target == 500.0

    def test_set_target_with_date(self):
        cat = make_category(name="Vacation")
        updates, result = compute_category_target_updates(
            cat,
            target_amount_milliunits=2_000_000,
            target_date="2026-12-01",
            clear=False,
        )
        assert updates == {"goal_target": 2_000_000, "goal_target_date": "2026-12-01"}
        assert result.action == "set"
        assert result.new_target == 2000.0
        assert result.new_target_date == "2026-12-01"

    def test_clear_target(self):
        cat = make_category(
            name="Vacation",
            goal_type="NEED",
            goal_target=500_000,
            goal_target_date="2026-06-01",
        )
        updates, result = compute_category_target_updates(
            cat, target_amount_milliunits=None, target_date=None, clear=True
        )
        assert updates == {"goal_target": None, "goal_target_date": None}
        assert result.action == "removed"
        assert result.old_target == 500.0
        assert result.old_target_date == "2026-06-01"
        assert result.new_target is None

    def test_clear_target_with_no_prior_goal(self):
        cat = make_category(name="Vacation")
        updates, result = compute_category_target_updates(
            cat, target_amount_milliunits=None, target_date=None, clear=True
        )
        assert result.action == "removed"
        assert result.old_target is None
        assert result.old_target_date is None

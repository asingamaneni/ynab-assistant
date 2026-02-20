"""Tests for MCP response formatters."""

from tests.conftest import make_account, make_category, make_category_group, make_transaction
from src.models.results import (
    AffordabilityResult,
    BudgetAssignment,
    CategoryBalance,
    CreditCardAnalysis,
    CreditCardInfo,
    MoveSuggestion,
    OverspendingResult,
    SpendingForecast,
    SpendingTrendResult,
    AnomalyItem,
)
from src.models.schemas import Budget
from src.mcp.formatters import (
    format_accounts,
    format_affordability_check,
    format_budget_setup_preview,
    format_budget_summary,
    format_budgets,
    format_category_detail,
    format_credit_card_analysis,
    format_learned_categories,
    format_move_result,
    format_overspending_analysis,
    format_spending_forecast,
    format_spending_trends,
    format_split_transaction_created,
    format_transaction_categorized,
    format_transaction_created,
    format_transactions,
    format_uncategorized_transactions,
)


class TestFormatBudgets:
    def test_empty(self):
        assert format_budgets([]) == "No budgets found."

    def test_renders_names_and_ids(self):
        budgets = [Budget(id="b1", name="My Budget")]
        result = format_budgets(budgets)
        assert "My Budget" in result
        assert "b1" in result


class TestFormatAccounts:
    def test_skips_closed(self):
        accounts = [
            make_account("Open", balance=100000),
            make_account("Closed", closed=True),
        ]
        result = format_accounts(accounts)
        assert "Open" in result
        assert "Closed" not in result

    def test_no_open_accounts(self):
        accounts = [make_account("Closed", closed=True)]
        assert "No open accounts" in format_accounts(accounts)

    def test_shows_balance(self):
        accounts = [make_account("Checking", balance=150000)]
        result = format_accounts(accounts)
        assert "$150.00" in result

    def test_negative_balance_no_double_negative(self):
        accounts = [make_account("Chase", type_="creditCard", balance=-1234560)]
        result = format_accounts(accounts)
        assert "- **Chase**" in result
        assert "$1,234.56" in result
        assert "$-" not in result


class TestFormatBudgetSummary:
    def test_skips_hidden_groups(self):
        groups = [
            make_category_group("Hidden", hidden=True, categories=[
                make_category("Secret", budgeted=100000),
            ]),
            make_category_group("Visible", categories=[
                make_category("Rent", budgeted=1500000, activity=-1500000),
            ]),
        ]
        result = format_budget_summary(groups)
        assert "Secret" not in result
        assert "Rent" in result

    def test_shows_totals(self):
        groups = [
            make_category_group("Bills", categories=[
                make_category("Rent", budgeted=1500000, activity=-1500000, balance=0),
            ]),
        ]
        result = format_budget_summary(groups)
        assert "Totals" in result


class TestFormatTransactions:
    def test_empty(self):
        assert "No transactions" in format_transactions([], limit=25)

    def test_skips_deleted(self):
        txns = [
            make_transaction(payee_name="HEB"),
            make_transaction(payee_name="Deleted", deleted=True),
        ]
        result = format_transactions(txns, limit=25)
        assert "HEB" in result
        assert "Deleted" not in result

    def test_respects_limit(self):
        txns = [make_transaction(payee_name=f"Store{i}") for i in range(10)]
        result = format_transactions(txns, limit=3)
        assert "3 shown" in result

    def test_shows_memo(self):
        txns = [make_transaction(payee_name="HEB", memo="Weekly groceries")]
        result = format_transactions(txns, limit=25)
        assert "Weekly groceries" in result


class TestFormatCategoryDetail:
    def test_renders_budget_and_transactions(self):
        cat = make_category("Groceries", budgeted=500000, activity=-200000, balance=300000)
        txns = [make_transaction(payee_name="HEB", amount=-45000)]
        result = format_category_detail(cat, txns)
        assert "Groceries" in result
        assert "$500.00" in result
        assert "HEB" in result


class TestFormatMoveResult:
    def test_renders_amounts(self):
        result = format_move_result("Dining", "Groceries", 50.0, 100000, 200000)
        assert "$50.00" in result
        assert "Dining" in result
        assert "Groceries" in result


class TestFormatTransactionCreated:
    def test_outflow(self):
        result = format_transaction_created(-45000, "HEB", "Groceries", "Checking", "2025-01-15", None)
        assert "outflow" in result
        assert "HEB" in result
        assert "Groceries" in result

    def test_inflow(self):
        result = format_transaction_created(100000, "Employer", "Income", "Checking", "2025-01-15", None)
        assert "inflow" in result

    def test_with_memo(self):
        result = format_transaction_created(-5000, "Coffee", "Dining", "Checking", "2025-01-15", "Morning latte")
        assert "Morning latte" in result

    def test_uncategorized(self):
        result = format_transaction_created(-5000, "Unknown", None, "Checking", "2025-01-15", None)
        assert "Uncategorized" in result


class TestFormatLearnedCategories:
    def test_renders_count_and_samples(self):
        mappings = {
            "heb": {"category_name": "Groceries", "category_id": "cat1", "count": 5},
            "starbucks": {"category_name": "Dining", "category_id": "cat2", "count": 3},
        }
        result = format_learned_categories(2, 10, mappings)
        assert "2 payee" in result
        assert "10 transactions" in result
        assert "Heb" in result
        assert "Starbucks" in result


# --- New Formatter Tests ---


class TestFormatSpendingTrends:
    def test_renders_table(self):
        result = SpendingTrendResult(
            monthly_totals={
                "2025-01": {"Groceries": 400.0},
                "2025-02": {"Groceries": 450.0},
            },
            averages={"Groceries": 425.0},
            num_months=2,
        )
        output = format_spending_trends(result)
        assert "Groceries" in output
        assert "$400.00" in output
        assert "$425.00" in output

    def test_renders_anomalies(self):
        result = SpendingTrendResult(
            monthly_totals={"2025-03": {"Dining": 300.0}},
            averages={"Dining": 150.0},
            anomalies=[AnomalyItem("Dining", 300.0, 150.0, 100.0)],
            num_months=3,
        )
        output = format_spending_trends(result)
        assert "Anomalies" in output
        assert "100%" in output

    def test_empty_data(self):
        result = SpendingTrendResult(monthly_totals={}, averages={}, num_months=3)
        output = format_spending_trends(result)
        assert "No spending data" in output


class TestFormatUncategorizedTransactions:
    def test_lists_with_index(self):
        txns = [
            make_transaction(payee_name="Store A", category_id=None, category_name=None),
            make_transaction(payee_name="Store B", category_id=None, category_name=None, date="2025-01-16"),
        ]
        output = format_uncategorized_transactions(txns)
        assert "1." in output
        assert "2." in output
        assert "Store A" in output

    def test_empty(self):
        output = format_uncategorized_transactions([])
        assert "No uncategorized" in output


class TestFormatTransactionCategorized:
    def test_confirmation(self):
        output = format_transaction_categorized("HEB", -45000, "Groceries")
        assert "HEB" in output
        assert "Groceries" in output
        assert "$45.00" in output


class TestFormatOverspendingAnalysis:
    def test_with_overspending(self):
        result = OverspendingResult(
            overspent=[CategoryBalance("Rent", "c1", -50.0)],
            sources=[CategoryBalance("Dining", "c2", 100.0)],
            suggestions=[MoveSuggestion("Dining", "c2", "Rent", "c1", 50.0)],
            total_overspent=50.0,
        )
        output = format_overspending_analysis(result)
        assert "Rent" in output
        assert "$50.00" in output
        assert "Dining" in output

    def test_no_overspending(self):
        result = OverspendingResult()
        output = format_overspending_analysis(result)
        assert "No overspending" in output


class TestFormatAffordabilityCheck:
    def test_can_afford(self):
        result = AffordabilityResult(
            can_afford=True, category_name="Dining",
            available=150.0, requested=50.0, remaining_after=100.0,
            budget=200.0, utilization_pct=25.0,
        )
        output = format_affordability_check(result)
        assert "Yes" in output
        assert "$50.00" in output

    def test_cannot_afford(self):
        result = AffordabilityResult(
            can_afford=False, category_name="Dining",
            available=20.0, requested=50.0, remaining_after=-30.0,
            budget=200.0, utilization_pct=90.0,
        )
        output = format_affordability_check(result)
        assert "No" in output


class TestFormatSplitTransactionCreated:
    def test_shows_splits(self):
        splits = [
            {"amount": -120000, "category_name": "Groceries", "memo": None},
            {"amount": -80000, "category_name": "Household", "memo": "cleaning"},
        ]
        output = format_split_transaction_created(-200000, "Costco", "Checking", "2025-03-15", splits)
        assert "Costco" in output
        assert "Groceries" in output
        assert "Household" in output
        assert "cleaning" in output


class TestFormatBudgetSetupPreview:
    def test_renders_table(self):
        assignments = [
            BudgetAssignment("c1", "Groceries", 400.0, 450.0),
            BudgetAssignment("c2", "Dining", 200.0, 200.0),
        ]
        output = format_budget_setup_preview(assignments)
        assert "Groceries" in output
        assert "$450.00" in output
        assert "apply" in output.lower()


class TestFormatCreditCardAnalysis:
    def test_shows_card_status(self):
        result = CreditCardAnalysis(
            cards=[CreditCardInfo("Chase", "a1", -500.0, "Chase", 500.0, 0.0)],
            total_owed=500.0,
            total_payment_available=500.0,
        )
        output = format_credit_card_analysis(result)
        assert "Chase" in output
        assert "$500.00" in output
        assert "Fully funded" in output

    def test_shows_underfunded(self):
        result = CreditCardAnalysis(
            cards=[CreditCardInfo("Chase", "a1", -500.0, "Chase", 300.0, -200.0)],
            total_owed=500.0,
            total_payment_available=300.0,
        )
        output = format_credit_card_analysis(result)
        assert "Underfunded" in output
        assert "$200.00" in output

    def test_no_cards(self):
        result = CreditCardAnalysis()
        output = format_credit_card_analysis(result)
        assert "No open credit card" in output


class TestFormatSpendingForecast:
    def test_on_track(self):
        result = SpendingForecast(
            category_name="Groceries", budget=500.0, spent_so_far=200.0,
            days_elapsed=15, days_remaining=16, daily_rate=13.33,
            projected_total=413.28, will_stay_in_budget=True, projected_remaining=86.72,
        )
        output = format_spending_forecast(result)
        assert "Groceries" in output
        assert "On track" in output

    def test_over_budget(self):
        result = SpendingForecast(
            category_name="Dining", budget=100.0, spent_so_far=80.0,
            days_elapsed=10, days_remaining=21, daily_rate=8.0,
            projected_total=248.0, will_stay_in_budget=False, projected_remaining=-148.0,
        )
        output = format_spending_forecast(result)
        assert "Projected to exceed budget" in output

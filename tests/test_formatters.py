"""Tests for MCP response formatters."""

from tests.conftest import (
    make_account,
    make_category,
    make_category_group,
    make_payee,
    make_scheduled_transaction,
    make_transaction,
)
from src.models.results import (
    AffordabilityResult,
    AnomalyItem,
    BudgetAssignment,
    CategoryBalance,
    CategoryTargetResult,
    CreditCardAnalysis,
    CreditCardInfo,
    FieldChange,
    MoveSuggestion,
    OverspendingResult,
    SpendingForecast,
    SpendingTrendResult,
    TransactionUpdateResult,
)
from src.models.schemas import (
    Budget,
    BudgetSettings,
    CurrencyFormat,
    DateFormat,
    Payee,
    PayeeLocation,
    User,
)
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
    format_transaction_recategorized,
    format_transaction_updated,
    format_transactions,
    format_uncategorized_transactions,
    format_payees,
    format_transaction_deleted,
    format_payee_updated,
    format_category_metadata_updated,
    format_category_targets,
    format_category_target_set,
    format_account_created,
    format_import_result,
    format_bulk_update_result,
    format_budget_settings,
    format_user,
    format_payee_locations,
    format_scheduled_transactions,
    format_scheduled_transaction_created,
    format_scheduled_transaction_updated,
    format_scheduled_transaction_deleted,
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

    def test_shows_approval_status(self):
        approved_txn = make_transaction(payee_name="HEB")
        unapproved_txn = make_transaction(payee_name="Shell", approved=False)
        result = format_transactions([approved_txn, unapproved_txn], limit=25)
        assert "✓" in result
        assert "⏳" in result


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


class TestFormatTransactionRecategorized:
    def test_shows_old_and_new_category(self):
        output = format_transaction_recategorized("Vanguard", -160000, "Business Investment", "Legal")
        assert "Vanguard" in output
        assert "$160.00" in output
        assert "Business Investment" in output
        assert "Legal" in output
        assert "→" in output

    def test_handles_none_old_category(self):
        output = format_transaction_recategorized("Nike", 1000000, None, "Inflow: Ready to Assign")
        assert "Uncategorized" in output
        assert "Inflow: Ready to Assign" in output
        assert "$1,000.00" in output


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


class TestFormatTransactionUpdated:
    def test_single_change(self):
        result = TransactionUpdateResult(
            payee_name="HEB",
            amount_milliunits=-45000,
            date="2025-01-15",
            changes=[FieldChange("Category", "Groceries", "Dining Out")],
        )
        output = format_transaction_updated(result)
        assert "HEB" in output
        assert "$45.00" in output
        assert "Category" in output
        assert "Groceries" in output
        assert "Dining Out" in output
        assert "→" in output

    def test_multiple_changes(self):
        result = TransactionUpdateResult(
            payee_name="HEB",
            amount_milliunits=-45000,
            date="2025-01-15",
            changes=[
                FieldChange("Memo", "(none)", "Weekly shopping"),
                FieldChange("Flag", "(none)", "blue"),
            ],
        )
        output = format_transaction_updated(result)
        assert "Memo" in output
        assert "Flag" in output
        assert "Weekly shopping" in output
        assert "blue" in output

    def test_shows_date(self):
        result = TransactionUpdateResult(
            payee_name="Amazon",
            amount_milliunits=-120000,
            date="2025-03-10",
            changes=[FieldChange("Payee", "Amazon", "Amazon Prime")],
        )
        output = format_transaction_updated(result)
        assert "2025-03-10" in output
        assert "$120.00" in output


# --- API Feature Formatter Tests ---


class TestFormatPayees:
    def test_empty(self):
        assert format_payees([]) == "No payees found."

    def test_sorted_alphabetically(self):
        payees = [make_payee("Starbucks"), make_payee("Amazon")]
        output = format_payees(payees)
        amazon_pos = output.index("Amazon")
        starbucks_pos = output.index("Starbucks")
        assert amazon_pos < starbucks_pos

    def test_filters_deleted(self):
        payees = [make_payee("HEB"), make_payee("Old Store", deleted=True)]
        output = format_payees(payees)
        assert "HEB" in output
        assert "Old Store" not in output


class TestFormatTransactionDeleted:
    def test_basic_deletion(self):
        output = format_transaction_deleted("HEB", -45000, "2025-01-15")
        assert "Deleted" in output
        assert "$45.00" in output
        assert "HEB" in output
        assert "2025-01-15" in output

    def test_inflow_deletion(self):
        output = format_transaction_deleted("Employer", 100000, "2025-02-01")
        assert "$100.00" in output
        assert "Employer" in output


class TestFormatPayeeUpdated:
    def test_basic_rename(self):
        output = format_payee_updated("HEB Grocery", "H-E-B")
        assert "HEB Grocery" in output
        assert "H-E-B" in output
        assert "Renamed" in output

    def test_shows_arrow(self):
        output = format_payee_updated("Old Name", "New Name")
        assert "→" in output


class TestFormatCategoryMetadataUpdated:
    def test_name_change(self):
        output = format_category_metadata_updated("Groceries", old_name="Groceries", new_name="Food")
        assert "Groceries" in output
        assert "Food" in output
        assert "→" in output

    def test_note_change(self):
        output = format_category_metadata_updated("Dining", old_note="Old note", new_note="New note")
        assert "Dining" in output
        assert "Old note" in output
        assert "New note" in output

    def test_multiple_changes(self):
        output = format_category_metadata_updated(
            "Dining", old_name="Dining", new_name="Eating Out",
            old_note=None, new_note="Weekly budget",
        )
        assert "Dining" in output
        assert "Eating Out" in output
        assert "Weekly budget" in output


class TestFormatAccountCreated:
    def test_basic_account(self):
        output = format_account_created("Savings", "savings", 5000.0)
        assert "Savings" in output
        assert "savings" in output
        assert "$5,000.00" in output
        assert "Account created" in output

    def test_zero_balance(self):
        output = format_account_created("New Checking", "checking", 0.0)
        assert "New Checking" in output
        assert "$0.00" in output


class TestFormatImportResult:
    def test_empty(self):
        output = format_import_result([])
        assert "no new transactions" in output.lower()

    def test_multiple_transactions(self):
        output = format_import_result(["t1", "t2", "t3"])
        assert "3" in output
        assert "transactions" in output

    def test_single_transaction(self):
        output = format_import_result(["t1"])
        assert "1" in output
        assert "transaction" in output
        assert "transactions" not in output


class TestFormatBulkUpdateResult:
    def test_success_only(self):
        output = format_bulk_update_result(5, [])
        assert "5" in output
        assert "transaction" in output
        assert "Error" not in output

    def test_with_errors(self):
        errors = ["Failed to update txn-1", "Category not found"]
        output = format_bulk_update_result(3, errors)
        assert "3" in output
        assert "Errors" in output
        assert "Failed to update txn-1" in output
        assert "Category not found" in output


class TestFormatBudgetSettings:
    def test_basic_settings(self):
        settings = BudgetSettings(
            date_format=DateFormat(format="MM/DD/YYYY"),
            currency_format=CurrencyFormat(
                iso_code="USD",
                example_format="$1,234.56",
                decimal_digits=2,
                decimal_separator=".",
                symbol_first=True,
                group_separator=",",
                currency_symbol="$",
                display_symbol=True,
            ),
        )
        output = format_budget_settings(settings)
        assert "MM/DD/YYYY" in output
        assert "USD" in output
        assert "$" in output
        assert "$1,234.56" in output
        assert "2" in output


class TestFormatUser:
    def test_basic_user(self):
        user = User(id="user-abc-123")
        output = format_user(user)
        assert "user-abc-123" in output
        assert "Authenticated" in output

    def test_different_user_id(self):
        user = User(id="xyz-789")
        output = format_user(user)
        assert "xyz-789" in output


class TestFormatPayeeLocations:
    def test_empty(self):
        assert format_payee_locations([], []) == "No payee locations found."

    def test_with_location(self):
        locations = [
            PayeeLocation(id="loc-1", payee_id="payee-heb", latitude="30.123", longitude="-97.456"),
        ]
        payees = [Payee(id="payee-heb", name="HEB")]
        output = format_payee_locations(locations, payees)
        assert "HEB" in output
        assert "30.123" in output
        assert "-97.456" in output

    def test_filters_deleted_locations(self):
        locations = [
            PayeeLocation(id="loc-1", payee_id="payee-heb", latitude="30.0", longitude="-97.0", deleted=True),
        ]
        payees = [Payee(id="payee-heb", name="HEB")]
        output = format_payee_locations(locations, payees)
        assert "No payee locations found." in output


class TestFormatScheduledTransactions:
    def test_empty(self):
        assert "No scheduled transactions" in format_scheduled_transactions([])

    def test_sorted_by_date(self):
        scheduled = [
            make_scheduled_transaction(payee_name="Spotify", date_next="2025-03-01"),
            make_scheduled_transaction(payee_name="Netflix", date_next="2025-02-01"),
        ]
        output = format_scheduled_transactions(scheduled)
        netflix_pos = output.index("Netflix")
        spotify_pos = output.index("Spotify")
        assert netflix_pos < spotify_pos

    def test_filters_deleted(self):
        scheduled = [
            make_scheduled_transaction(payee_name="Netflix"),
            make_scheduled_transaction(payee_name="Old Sub", deleted=True),
        ]
        output = format_scheduled_transactions(scheduled)
        assert "Netflix" in output
        assert "Old Sub" not in output


class TestFormatScheduledTransactionCreated:
    def test_basic_creation(self):
        st = make_scheduled_transaction(
            payee_name="Netflix",
            amount=-15990,
            category_name="Subscriptions",
            date_first="2025-01-01",
            frequency="monthly",
        )
        output = format_scheduled_transaction_created(st, "Checking", "Subscriptions")
        assert "Scheduled transaction created" in output
        assert "Netflix" in output
        assert "$15.99" in output
        assert "Checking" in output
        assert "Subscriptions" in output
        assert "monthly" in output

    def test_with_memo(self):
        st = make_scheduled_transaction(payee_name="Gym", memo="Monthly membership")
        output = format_scheduled_transaction_created(st, "Checking", "Fitness")
        assert "Monthly membership" in output


class TestFormatScheduledTransactionUpdated:
    def test_basic_update(self):
        changes = [FieldChange(field_name="Amount", old_value="$15.99", new_value="$22.99")]
        output = format_scheduled_transaction_updated("Netflix", changes)
        assert "Netflix" in output
        assert "$15.99" in output
        assert "$22.99" in output
        assert "→" in output
        assert "Updated" in output

    def test_multiple_changes(self):
        changes = [
            FieldChange(field_name="Frequency", old_value="monthly", new_value="yearly"),
            FieldChange(field_name="Amount", old_value="$15.99", new_value="$159.99"),
        ]
        output = format_scheduled_transaction_updated("Spotify", changes)
        assert "Spotify" in output
        assert "monthly" in output
        assert "yearly" in output
        assert "$15.99" in output
        assert "$159.99" in output


class TestFormatScheduledTransactionDeleted:
    def test_basic_deletion(self):
        output = format_scheduled_transaction_deleted("Netflix", -15990, "2025-03-01")
        assert "Deleted" in output
        assert "Netflix" in output
        assert "$15.99" in output
        assert "2025-03-01" in output

    def test_inflow_deletion(self):
        output = format_scheduled_transaction_deleted("Employer", 5000000, "2025-04-01")
        assert "$5,000.00" in output
        assert "Employer" in output


class TestFormatCategoryTargetSet:
    def test_target_set_new(self):
        result = CategoryTargetResult(
            category_name="Vacation",
            action="set",
            new_target=500.0,
            new_target_date=None,
            old_target=None,
            old_target_date=None,
            goal_type="NEED",
            percentage_complete=0,
            under_funded=500.0,
        )
        output = format_category_target_set(result)
        assert "Target set" in output
        assert "Vacation" in output
        assert "$500.00" in output
        assert "NEED" in output
        assert "0%" in output

    def test_target_updated_with_previous(self):
        result = CategoryTargetResult(
            category_name="Groceries",
            action="updated",
            new_target=600.0,
            new_target_date=None,
            old_target=400.0,
            old_target_date=None,
            goal_type="NEED",
            percentage_complete=50,
            under_funded=None,
        )
        output = format_category_target_set(result)
        assert "Target updated" in output
        assert "$400.00" in output
        assert "$600.00" in output
        assert "50%" in output

    def test_target_removed(self):
        result = CategoryTargetResult(
            category_name="Vacation",
            action="removed",
            new_target=None,
            new_target_date=None,
            old_target=1000.0,
            old_target_date="2026-06-01",
            goal_type=None,
            percentage_complete=None,
            under_funded=None,
        )
        output = format_category_target_set(result)
        assert "Target removed" in output
        assert "Vacation" in output
        assert "$1,000.00" in output
        assert "2026-06-01" in output

    def test_target_with_date(self):
        result = CategoryTargetResult(
            category_name="Vacation",
            action="set",
            new_target=2000.0,
            new_target_date="2026-12-01",
            old_target=None,
            old_target_date=None,
            goal_type="TBD",
            percentage_complete=10,
            under_funded=200.0,
        )
        output = format_category_target_set(result)
        assert "2026-12-01" in output
        assert "$2,000.00" in output
        assert "TBD" in output


class TestFormatCategoryTargets:
    def test_categories_with_targets(self):
        groups = [
            make_category_group(
                name="Housing",
                categories=[
                    make_category(
                        name="Rent",
                        goal_type="NEED",
                        goal_target=2000000,
                        goal_percentage_complete=100,
                        goal_under_funded=0,
                    ),
                    make_category(
                        name="Utilities",
                        goal_type="MF",
                        goal_target=150000,
                        goal_percentage_complete=50,
                        goal_under_funded=75000,
                    ),
                ],
            ),
            make_category_group(
                name="Savings",
                categories=[
                    make_category(
                        name="Vacation",
                        goal_type="TBD",
                        goal_target=5000000,
                        goal_target_date="2026-12-01",
                        goal_percentage_complete=20,
                        goal_under_funded=200000,
                    ),
                ],
            ),
        ]
        output = format_category_targets(groups)
        assert "## Category Targets" in output
        assert "### Housing" in output
        assert "Rent" in output
        assert "$2,000.00" in output
        assert "Needed for Spending" in output
        assert "100% funded" in output
        assert "Utilities" in output
        assert "$150.00" in output
        assert "Monthly Funding" in output
        assert "$75.00 underfunded" in output
        assert "### Savings" in output
        assert "Vacation" in output
        assert "Target Balance by Date" in output
        assert "2026-12-01" in output
        assert "3 categories with targets" in output

    def test_no_targets(self):
        groups = [
            make_category_group(
                name="Food",
                categories=[make_category(name="Groceries")],
            ),
        ]
        output = format_category_targets(groups)
        assert "No category targets/goals found." in output

    def test_hidden_and_deleted_excluded(self):
        groups = [
            make_category_group(
                name="Active",
                categories=[
                    make_category(
                        name="Visible",
                        goal_type="NEED",
                        goal_target=100000,
                        goal_percentage_complete=80,
                    ),
                    make_category(
                        name="Hidden Cat",
                        hidden=True,
                        goal_type="NEED",
                        goal_target=200000,
                    ),
                    make_category(
                        name="Deleted Cat",
                        deleted=True,
                        goal_type="NEED",
                        goal_target=300000,
                    ),
                ],
            ),
            make_category_group(
                name="Hidden Categories",
                categories=[
                    make_category(
                        name="Should Skip",
                        goal_type="NEED",
                        goal_target=400000,
                    ),
                ],
            ),
        ]
        output = format_category_targets(groups)
        assert "Visible" in output
        assert "Hidden Cat" not in output
        assert "Deleted Cat" not in output
        assert "Should Skip" not in output
        assert "1 categories with targets" in output

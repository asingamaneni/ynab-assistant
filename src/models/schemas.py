"""Pydantic models for YNAB API data types."""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- YNAB uses "milliunits" for currency (1000 = $1.00) ---

def milliunits_to_dollars(milliunits: int) -> float:
    """Convert YNAB milliunits to dollars."""
    return milliunits / 1000.0


def dollars_to_milliunits(dollars: float) -> int:
    """Convert dollars to YNAB milliunits."""
    return round(dollars * 1000)


# --- Enums ---

class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "creditCard"
    CASH = "cash"
    LINE_OF_CREDIT = "lineOfCredit"
    OTHER_ASSET = "otherAsset"
    OTHER_LIABILITY = "otherLiability"
    MORTGAGE = "mortgage"
    AUTO_LOAN = "autoLoan"
    STUDENT_LOAN = "studentLoan"
    PERSONAL_LOAN = "personalLoan"
    MEDICAL_DEBT = "medicalDebt"
    OTHER_DEBT = "otherDebt"


class TransactionClearedStatus(str, Enum):
    CLEARED = "cleared"
    UNCLEARED = "uncleared"
    RECONCILED = "reconciled"


class TransactionFlagColor(str, Enum):
    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PURPLE = "purple"


class ScheduledTransactionFrequency(str, Enum):
    NEVER = "never"
    DAILY = "daily"
    WEEKLY = "weekly"
    EVERY_OTHER_WEEK = "everyOtherWeek"
    TWICE_A_MONTH = "twiceAMonth"
    EVERY_FOUR_WEEKS = "every4Weeks"
    MONTHLY = "monthly"
    EVERY_OTHER_MONTH = "everyOtherMonth"
    EVERY_THREE_MONTHS = "every3Months"
    EVERY_FOUR_MONTHS = "every4Months"
    TWICE_A_YEAR = "twiceAYear"
    YEARLY = "yearly"


# --- Response Models ---

class Budget(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    last_modified_on: Optional[str] = None
    first_month: Optional[str] = None
    last_month: Optional[str] = None


class Account(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    type: AccountType
    on_budget: bool
    closed: bool
    balance: int  # milliunits
    cleared_balance: int  # milliunits
    uncleared_balance: int  # milliunits
    note: Optional[str] = None

    @property
    def balance_dollars(self) -> float:
        return milliunits_to_dollars(self.balance)


class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    category_group_id: str
    category_group_name: Optional[str] = None
    name: str
    budgeted: int  # milliunits
    activity: int  # milliunits
    balance: int  # milliunits
    hidden: bool = False
    deleted: bool = False
    note: Optional[str] = None
    # --- Goal/target fields (read-only from API) ---
    goal_type: str | None = None              # TB, TBD, MF, NEED, DEBT
    goal_target: int | None = None            # milliunits
    goal_target_date: str | None = None       # YYYY-MM-DD
    goal_percentage_complete: int | None = None
    goal_under_funded: int | None = None      # milliunits
    goal_overall_funded: int | None = None    # milliunits
    goal_months_to_budget: int | None = None
    goal_creation_month: str | None = None

    @property
    def budgeted_dollars(self) -> float:
        return milliunits_to_dollars(self.budgeted)

    @property
    def activity_dollars(self) -> float:
        return milliunits_to_dollars(self.activity)

    @property
    def balance_dollars(self) -> float:
        return milliunits_to_dollars(self.balance)


class CategoryGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    hidden: bool = False
    deleted: bool = False
    categories: list[Category] = []


class Payee(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    deleted: bool = False


class SubTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    transaction_id: str
    amount: int  # milliunits
    payee_id: Optional[str] = None
    payee_name: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    memo: Optional[str] = None
    deleted: bool = False


class Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    date: str
    amount: int  # milliunits
    memo: Optional[str] = None
    cleared: TransactionClearedStatus = TransactionClearedStatus.UNCLEARED
    approved: bool = False
    flag_color: Optional[TransactionFlagColor] = None
    flag_name: Optional[str] = None
    account_id: str
    account_name: Optional[str] = None
    payee_id: Optional[str] = None
    payee_name: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    subtransactions: list[SubTransaction] = []
    deleted: bool = False

    @property
    def amount_dollars(self) -> float:
        return milliunits_to_dollars(self.amount)


class MonthSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    month: str
    income: int  # milliunits
    budgeted: int  # milliunits
    activity: int  # milliunits
    to_be_budgeted: int  # milliunits
    deleted: bool = False


class ScheduledSubTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    scheduled_transaction_id: str
    amount: int  # milliunits
    payee_id: str | None = None
    payee_name: str | None = None
    category_id: str | None = None
    category_name: str | None = None
    memo: str | None = None
    deleted: bool = False


class ScheduledTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    date_first: str
    date_next: str
    frequency: ScheduledTransactionFrequency
    amount: int  # milliunits
    account_id: str
    account_name: str | None = None
    payee_id: str | None = None
    payee_name: str | None = None
    category_id: str | None = None
    category_name: str | None = None
    memo: str | None = None
    flag_color: TransactionFlagColor | None = None
    subtransactions: list[ScheduledSubTransaction] = []
    deleted: bool = False

    @property
    def amount_dollars(self) -> float:
        return milliunits_to_dollars(self.amount)


class PayeeLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    payee_id: str
    latitude: str
    longitude: str
    deleted: bool = False


class DateFormat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    format: str


class CurrencyFormat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    iso_code: str
    example_format: str
    decimal_digits: int
    decimal_separator: str
    symbol_first: bool
    group_separator: str
    currency_symbol: str
    display_symbol: bool


class BudgetSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date_format: DateFormat
    currency_format: CurrencyFormat


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str


# --- Input Models for Creating/Updating ---

class CreateTransactionInput(BaseModel):
    """Input for creating a new transaction in YNAB."""
    model_config = ConfigDict(str_strip_whitespace=True)

    account_id: str = Field(..., description="The account ID for the transaction")
    date: str = Field(..., description="Transaction date in ISO format (YYYY-MM-DD)")
    amount: int = Field(..., description="Transaction amount in milliunits (negative for outflow)")
    payee_name: Optional[str] = Field(None, description="Payee name", max_length=200)
    category_id: Optional[str] = Field(None, description="Category ID")
    memo: Optional[str] = Field(None, description="Transaction memo", max_length=200)
    cleared: TransactionClearedStatus = Field(
        default=TransactionClearedStatus.UNCLEARED,
        description="Transaction cleared status"
    )
    approved: bool = Field(default=True, description="Whether the transaction is approved")
    subtransactions: Optional[list[dict]] = Field(
        None, description="Split transaction sub-items (each with amount, category_id, optional memo)"
    )


class UpdateCategoryInput(BaseModel):
    """Input for updating a category's budgeted amount."""
    model_config = ConfigDict(str_strip_whitespace=True)

    budgeted: int = Field(..., description="New budgeted amount in milliunits")


# --- MCP Tool Input Models ---


class GetTransactionsInput(BaseModel):
    """Input for querying transactions."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    since_date: Optional[str] = Field(
        None, description="Only return transactions on or after this date (YYYY-MM-DD)"
    )
    account_name: Optional[str] = Field(
        None, description="Filter by account name (partial match)"
    )
    category_name: Optional[str] = Field(
        None, description="Filter by category name (partial match)"
    )
    limit: int = Field(
        default=25, description="Max number of transactions to return", ge=1, le=100
    )


class CreateTransactionNLInput(BaseModel):
    """Natural language input for creating a transaction."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    amount: float = Field(
        ..., description="Dollar amount (positive for outflow, negative for inflow/refund)"
    )
    payee: str = Field(..., description="Who you paid (e.g. 'HEB', 'Amazon', 'Starbucks')")
    account_name: Optional[str] = Field(
        None, description="Account name to use. If not specified, uses first checking account."
    )
    category_name: Optional[str] = Field(
        None,
        description="Category name. If not specified, auto-categorization is attempted."
    )
    memo: Optional[str] = Field(None, description="Optional note for the transaction")
    date: Optional[str] = Field(
        None, description="Transaction date (YYYY-MM-DD). Defaults to today."
    )


class MoveBudgetInput(BaseModel):
    """Input for moving money between budget categories."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    from_category: str = Field(..., description="Source category name")
    to_category: str = Field(..., description="Destination category name")
    amount: float = Field(..., description="Dollar amount to move", gt=0)
    month: Optional[str] = Field(
        None, description="Budget month (YYYY-MM-DD, first of month). Defaults to current month."
    )


class SpendingTrendInput(BaseModel):
    """Input for spending trend analysis."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category_name: Optional[str] = Field(
        None, description="Focus on a specific category (partial match)"
    )
    num_months: int = Field(
        default=3, ge=1, le=12, description="Number of months to analyze"
    )


class SearchTransactionsInput(BaseModel):
    """Enhanced transaction search with payee, amount range, and memo filters."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    since_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    payee_name: Optional[str] = Field(None, description="Filter by payee name (partial match)")
    min_amount: Optional[float] = Field(None, description="Minimum dollar amount (absolute value)")
    max_amount: Optional[float] = Field(None, description="Maximum dollar amount (absolute value)")
    memo_contains: Optional[str] = Field(None, description="Filter by memo text (partial match)")
    category_name: Optional[str] = Field(None, description="Filter by category name (partial match)")
    account_name: Optional[str] = Field(None, description="Filter by account name (partial match)")
    uncategorized_only: bool = Field(default=False, description="Only show uncategorized transactions")
    limit: int = Field(default=25, ge=1, le=100, description="Max results")


class CategorizeTransactionInput(BaseModel):
    """Input for categorizing a single uncategorized transaction."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    transaction_description: str = Field(
        ..., min_length=1, description="Payee name, date, or amount to identify the transaction"
    )
    category_name: str = Field(..., description="Category to assign")


class RecategorizeTransactionInput(BaseModel):
    """Input for changing the category of any transaction (including already-categorized ones)."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    transaction_description: str = Field(
        ..., min_length=1, description="Payee name, date, or amount to identify the transaction"
    )
    new_category_name: str = Field(
        ..., description="New category to assign (use 'Inflow: Ready to Assign' for income)"
    )


class UpdateTransactionInput(BaseModel):
    """Input for updating any editable field on an existing transaction."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    transaction_description: str = Field(
        ..., min_length=1, description="Payee name, date, or amount to identify the transaction to update"
    )
    memo: str | None = Field(
        None, description="New memo text (set to empty string to clear)", max_length=200
    )
    category_name: str | None = Field(
        None, description="New category name (use 'Inflow: Ready to Assign' for income)"
    )
    payee: str | None = Field(
        None, description="New payee name", max_length=200
    )
    date: str | None = Field(
        None, description="New transaction date (YYYY-MM-DD)"
    )
    amount: float | None = Field(
        None, description="New dollar amount (positive for outflow, negative for inflow/refund)"
    )
    flag_color: TransactionFlagColor | None = Field(
        None, description="Flag color: red, orange, yellow, green, blue, purple"
    )
    cleared: TransactionClearedStatus | None = Field(
        None, description="Cleared status: cleared, uncleared, reconciled"
    )
    approved: bool | None = Field(
        None, description="Whether the transaction is approved (imported transactions start unapproved)"
    )

    @model_validator(mode="after")
    def _at_least_one_update_field(self) -> "UpdateTransactionInput":
        update_fields = [
            self.memo, self.category_name, self.payee,
            self.date, self.amount, self.flag_color, self.cleared,
            self.approved,
        ]
        if all(f is None for f in update_fields):
            raise ValueError(
                "At least one field to update must be provided "
                "(memo, category_name, payee, date, amount, flag_color, cleared, approved)"
            )
        return self


class AffordabilityCheckInput(BaseModel):
    """Input for checking if a purchase is affordable within a category."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category_name: str = Field(..., description="Budget category to check")
    amount: float = Field(..., description="Dollar amount to check", gt=0)


class CreateSplitTransactionInput(BaseModel):
    """Input for creating a split transaction across multiple categories."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    amount: float = Field(..., description="Total dollar amount (positive for outflow)")
    payee: str = Field(..., description="Payee name")
    account_name: Optional[str] = Field(None, description="Account name")
    date: Optional[str] = Field(None, description="Date (YYYY-MM-DD), defaults to today")
    memo: Optional[str] = Field(None, description="Overall transaction memo")
    splits: list[dict] = Field(
        ...,
        description="List of splits, each with 'category_name' (str), 'amount' (float), optional 'memo' (str)",
        min_length=2,
    )


class BudgetSetupInput(BaseModel):
    """Input for setting up monthly budget assignments."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    month: Optional[str] = Field(
        None, description="Target month (YYYY-MM-DD, first of month). Defaults to next month."
    )
    strategy: str = Field(
        default="last_month_budget",
        description="Strategy: 'last_month_budget' copies budgeted amounts, 'last_month_actual' uses actual spending",
    )
    apply: bool = Field(
        default=False,
        description="If False, returns a preview. If True, applies the assignments.",
    )


class SpendingForecastInput(BaseModel):
    """Input for projecting category spending through end of month."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category_name: str = Field(..., description="Category to forecast")


class DeleteTransactionInput(BaseModel):
    """Input for deleting a transaction."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    transaction_description: str = Field(
        ..., min_length=1, description="Payee name, date, or amount to identify the transaction to delete"
    )


class UpdatePayeeInput(BaseModel):
    """Input for renaming a payee."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    payee_name: str = Field(..., description="Current payee name (partial match)")
    new_name: str = Field(..., description="New name for the payee", max_length=500)


class UpdateCategoryMetadataInput(BaseModel):
    """Input for updating a category's name or note."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category_name: str = Field(..., description="Current category name (partial match)")
    new_name: str | None = Field(None, description="New name for the category")
    note: str | None = Field(
        None, description="New note for the category (set to empty string to clear)"
    )

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateCategoryMetadataInput":
        if self.new_name is None and self.note is None:
            raise ValueError("At least one of new_name or note must be provided")
        return self


class SetCategoryTargetInput(BaseModel):
    """Input for setting or removing a category's savings target/goal."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category_name: str = Field(..., description="Category name (partial match)")
    target_amount: float | None = Field(
        None,
        description="Target amount in dollars. Creates a 'Needed for Spending' goal. "
        "Omit and set clear_target=true to remove an existing target.",
        gt=0,
    )
    target_date: str | None = Field(
        None,
        description="Optional target date (YYYY-MM-DD, first of month). "
        "If provided with target_amount, creates a 'Target by Date' goal.",
    )
    clear_target: bool = Field(
        default=False,
        description="Set to true to remove the existing target/goal from this category.",
    )

    @model_validator(mode="after")
    def _validate_target_or_clear(self) -> "SetCategoryTargetInput":
        if self.clear_target and self.target_amount is not None:
            raise ValueError(
                "Cannot set both target_amount and clear_target=true. "
                "Use target_amount to set a goal, or clear_target=true to remove one."
            )
        if not self.clear_target and self.target_amount is None:
            raise ValueError(
                "Either target_amount must be provided, or clear_target must be true."
            )
        if self.target_date is not None and self.target_amount is None:
            raise ValueError(
                "target_date requires target_amount to also be provided."
            )
        return self


class CreateAccountInput(BaseModel):
    """Input for creating a new budget account."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., description="Account name")
    type: AccountType = Field(..., description="Account type (checking, savings, creditCard, etc.)")
    balance: float = Field(default=0.0, description="Starting balance in dollars")


class BulkTransactionUpdateInput(BaseModel):
    """A single transaction update within a bulk operation."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    transaction_description: str = Field(
        ..., min_length=1, description="Payee name, date, or amount to identify the transaction"
    )
    category_name: str | None = Field(None, description="New category name")
    memo: str | None = Field(None, description="New memo")
    flag_color: TransactionFlagColor | None = Field(None, description="New flag color")
    cleared: TransactionClearedStatus | None = Field(None, description="New cleared status")
    approved: bool | None = Field(
        None, description="Whether the transaction is approved (imported transactions start unapproved)"
    )

    @model_validator(mode="after")
    def _at_least_one_update_field(self) -> "BulkTransactionUpdateInput":
        update_fields = [
            self.category_name, self.memo, self.flag_color,
            self.cleared, self.approved,
        ]
        if all(f is None for f in update_fields):
            raise ValueError(
                "At least one field to update must be provided "
                "(category_name, memo, flag_color, cleared, approved)"
            )
        return self


class BulkUpdateTransactionsInput(BaseModel):
    """Input for updating multiple transactions at once."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    updates: list[BulkTransactionUpdateInput] = Field(
        ..., description="List of transaction updates", min_length=1, max_length=50
    )


class GetPayeeTransactionsInput(BaseModel):
    """Input for getting transactions for a specific payee."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    payee_name: str = Field(..., description="Payee name (partial match)")
    since_date: str | None = Field(None, description="Start date (YYYY-MM-DD)")
    limit: int = Field(default=25, ge=1, le=100, description="Max results")


class CreateScheduledTransactionInput(BaseModel):
    """Input for creating a scheduled/recurring transaction."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    account_name: str | None = Field(
        None, description="Account name. Defaults to first checking account."
    )
    date: str = Field(
        ..., description="First date for the scheduled transaction (YYYY-MM-DD, must be future)"
    )
    frequency: ScheduledTransactionFrequency = Field(
        ..., description="How often the transaction repeats"
    )
    amount: float = Field(
        ..., description="Dollar amount (positive for outflow, negative for inflow)"
    )
    payee: str = Field(..., description="Payee name")
    category_name: str | None = Field(None, description="Category name (partial match)")
    memo: str | None = Field(None, description="Transaction memo", max_length=500)


class UpdateScheduledTransactionInput(BaseModel):
    """Input for updating a scheduled transaction."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    scheduled_transaction_description: str = Field(
        ..., min_length=1, description="Payee name, date, or amount to identify the scheduled transaction"
    )
    date: str | None = Field(None, description="New next date (YYYY-MM-DD)")
    frequency: ScheduledTransactionFrequency | None = Field(None, description="New frequency")
    amount: float | None = Field(None, description="New dollar amount")
    payee: str | None = Field(None, description="New payee name")
    category_name: str | None = Field(None, description="New category name")
    memo: str | None = Field(None, description="New memo")
    flag_color: TransactionFlagColor | None = Field(None, description="New flag color")

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateScheduledTransactionInput":
        fields = [self.date, self.frequency, self.amount, self.payee,
                  self.category_name, self.memo, self.flag_color]
        if all(f is None for f in fields):
            raise ValueError("At least one field to update must be provided")
        return self


class DeleteScheduledTransactionInput(BaseModel):
    """Input for deleting a scheduled transaction."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    scheduled_transaction_description: str = Field(
        ..., min_length=1, description="Payee name, date, or amount to identify the scheduled transaction"
    )

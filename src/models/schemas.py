"""Pydantic models for YNAB API data types."""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
        ..., description="Payee name, date, or amount to identify the transaction"
    )
    category_name: str = Field(..., description="Category to assign")


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

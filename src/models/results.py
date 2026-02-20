"""Result dataclasses for YNAB analyzer outputs.

These are internal types consumed by formatters — lightweight dataclasses
rather than Pydantic models since they don't need validation.
"""

from dataclasses import dataclass, field


@dataclass
class AnomalyItem:
    """A category where spending is significantly above average."""
    category_name: str
    current_amount: float       # dollars, this month
    average_amount: float       # dollars, historical average
    pct_above_average: float    # e.g. 75.0 means 75% above average


@dataclass
class SpendingTrendResult:
    """Month-over-month spending comparison."""
    monthly_totals: dict[str, dict[str, float]]  # month_str -> {category: dollars}
    averages: dict[str, float]                    # category -> avg dollars
    anomalies: list[AnomalyItem] = field(default_factory=list)
    category_filter: str | None = None
    num_months: int = 3


@dataclass
class CategoryBalance:
    """A category with its balance amount."""
    name: str
    category_id: str
    amount: float  # dollars (positive = available, negative = overspent)


@dataclass
class MoveSuggestion:
    """A suggested money move to cover overspending."""
    from_category: str
    from_category_id: str
    to_category: str
    to_category_id: str
    amount: float  # dollars


@dataclass
class OverspendingResult:
    """Analysis of overspent categories with suggested fixes."""
    overspent: list[CategoryBalance] = field(default_factory=list)
    sources: list[CategoryBalance] = field(default_factory=list)
    suggestions: list[MoveSuggestion] = field(default_factory=list)
    total_overspent: float = 0.0


@dataclass
class AffordabilityResult:
    """Result of checking if a purchase fits the budget."""
    can_afford: bool
    category_name: str
    available: float       # dollars currently available
    requested: float       # dollars requested
    remaining_after: float # dollars remaining (can be negative)
    budget: float          # dollars budgeted this month
    utilization_pct: float # 0-100, % of budget already spent


@dataclass
class SplitItem:
    """A single line in a split transaction."""
    category_name: str
    amount: float          # dollars, positive
    memo: str | None = None


@dataclass
class BudgetAssignment:
    """A proposed or applied budget assignment for a category."""
    category_id: str
    category_name: str
    current_budgeted: float   # dollars
    proposed_budgeted: float  # dollars


@dataclass
class CreditCardInfo:
    """Status of a single credit card."""
    account_name: str
    account_id: str
    balance: float               # dollars (what's owed, negative in YNAB)
    payment_category_name: str | None = None
    payment_available: float = 0.0
    discrepancy: float = 0.0     # payment_available - abs(balance)


@dataclass
class CreditCardAnalysis:
    """Overall credit card status."""
    cards: list[CreditCardInfo] = field(default_factory=list)
    total_owed: float = 0.0
    total_payment_available: float = 0.0


@dataclass
class SpendingForecast:
    """Projected spending for a category through end of month."""
    category_name: str
    budget: float              # dollars budgeted
    spent_so_far: float        # dollars (absolute)
    days_elapsed: int
    days_remaining: int
    daily_rate: float          # dollars per day
    projected_total: float     # dollars projected spend
    will_stay_in_budget: bool
    projected_remaining: float # dollars (negative = over budget)

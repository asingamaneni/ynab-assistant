"""Pure analysis functions for YNAB budget data.

All functions take already-fetched domain objects and return result
dataclasses. No I/O — keeps business logic testable without mocking.
"""

from datetime import date, timedelta

from src.models.results import (
    AffordabilityResult,
    AnomalyItem,
    BudgetAssignment,
    CategoryBalance,
    CreditCardAnalysis,
    CreditCardInfo,
    MoveSuggestion,
    OverspendingResult,
    SplitItem,
    SpendingForecast,
    SpendingTrendResult,
)
from src.models.schemas import (
    Account,
    AccountType,
    Category,
    CategoryGroup,
    Transaction,
    dollars_to_milliunits,
    milliunits_to_dollars,
)

# Internal category groups to skip in analysis
_INTERNAL_GROUPS = {"Internal Master Category", "Hidden Categories"}


# --- Spending Trend Analysis ---


def analyze_spending_trends(
    transactions: list[Transaction],
    num_months: int = 3,
    category_name: str | None = None,
    reference_date: date | None = None,
) -> SpendingTrendResult:
    """Analyze spending trends across months with anomaly detection.

    Groups outflow transactions by month and category, computes averages,
    and flags categories where current month spending exceeds 1.5x the
    historical average.
    """
    today = reference_date or date.today()
    current_month_str = today.strftime("%Y-%m")

    # Build month boundaries
    month_keys: list[str] = []
    d = today.replace(day=1)
    for _ in range(num_months):
        month_keys.append(d.strftime("%Y-%m"))
        d = (d - timedelta(days=1)).replace(day=1)
    month_keys.reverse()  # oldest first

    # Group transactions by month and category
    monthly_totals: dict[str, dict[str, float]] = {m: {} for m in month_keys}

    for t in transactions:
        if t.deleted or t.amount >= 0:  # skip inflows and deleted
            continue
        t_month = t.date[:7]  # "YYYY-MM"
        if t_month not in monthly_totals:
            continue
        cat = t.category_name or "Uncategorized"
        if category_name and category_name.lower() not in cat.lower():
            continue
        dollars = abs(milliunits_to_dollars(t.amount))
        monthly_totals[t_month][cat] = monthly_totals[t_month].get(cat, 0.0) + dollars

    # Compute averages across all months
    all_categories: set[str] = set()
    for month_data in monthly_totals.values():
        all_categories.update(month_data.keys())

    averages: dict[str, float] = {}
    for cat in all_categories:
        values = [monthly_totals[m].get(cat, 0.0) for m in month_keys]
        averages[cat] = sum(values) / len(values) if values else 0.0

    # Detect anomalies in the current month
    anomalies: list[AnomalyItem] = []
    if current_month_str in monthly_totals:
        for cat, amount in monthly_totals[current_month_str].items():
            avg = averages.get(cat, 0.0)
            if avg > 0 and amount > avg * 1.5:
                pct = ((amount - avg) / avg) * 100
                anomalies.append(AnomalyItem(
                    category_name=cat,
                    current_amount=round(amount, 2),
                    average_amount=round(avg, 2),
                    pct_above_average=round(pct, 1),
                ))

    # Round values for clean output
    for m in monthly_totals:
        monthly_totals[m] = {c: round(v, 2) for c, v in monthly_totals[m].items()}
    averages = {c: round(v, 2) for c, v in averages.items()}

    return SpendingTrendResult(
        monthly_totals=monthly_totals,
        averages=averages,
        anomalies=sorted(anomalies, key=lambda a: a.pct_above_average, reverse=True),
        category_filter=category_name,
        num_months=num_months,
    )


# --- Uncategorized Transaction Review ---


def find_uncategorized_transactions(
    transactions: list[Transaction],
) -> list[Transaction]:
    """Filter to non-deleted transactions with no category assigned."""
    return [
        t for t in transactions
        if not t.deleted and t.category_id is None
    ]


# --- Cover Overspending Workflow ---


def analyze_overspending(
    groups: list[CategoryGroup],
) -> OverspendingResult:
    """Find overspent categories and suggest moves to cover them.

    Pairs each overspent category with the best available source
    (highest positive balance), respecting source capacity.
    """
    overspent: list[CategoryBalance] = []
    sources: list[CategoryBalance] = []

    for group in groups:
        if group.name in _INTERNAL_GROUPS or group.hidden or group.deleted:
            continue
        for cat in group.categories:
            if cat.hidden or cat.deleted:
                continue
            balance = milliunits_to_dollars(cat.balance)
            if balance < -0.005:  # overspent (with rounding tolerance)
                overspent.append(CategoryBalance(
                    name=cat.name, category_id=cat.id, amount=round(balance, 2),
                ))
            elif balance > 0.005:  # has available funds
                sources.append(CategoryBalance(
                    name=cat.name, category_id=cat.id, amount=round(balance, 2),
                ))

    # Sort: most overspent first, richest source first
    overspent.sort(key=lambda c: c.amount)
    sources.sort(key=lambda c: c.amount, reverse=True)

    # Generate suggestions
    suggestions: list[MoveSuggestion] = []
    source_remaining = {s.category_id: s.amount for s in sources}

    for deficit in overspent:
        needed = abs(deficit.amount)
        for source in sources:
            avail = source_remaining.get(source.category_id, 0.0)
            if avail <= 0:
                continue
            move = min(needed, avail)
            suggestions.append(MoveSuggestion(
                from_category=source.name,
                from_category_id=source.category_id,
                to_category=deficit.name,
                to_category_id=deficit.category_id,
                amount=round(move, 2),
            ))
            source_remaining[source.category_id] = avail - move
            needed -= move
            if needed <= 0.005:
                break

    total_overspent = round(sum(abs(c.amount) for c in overspent), 2)

    return OverspendingResult(
        overspent=overspent,
        sources=sources,
        suggestions=suggestions,
        total_overspent=total_overspent,
    )


# --- Affordability Check ---


def check_affordability(
    category: Category,
    amount_dollars: float,
) -> AffordabilityResult:
    """Check if a category can afford a given purchase amount."""
    available = milliunits_to_dollars(category.balance)
    budget = milliunits_to_dollars(category.budgeted)
    activity = abs(milliunits_to_dollars(category.activity))
    remaining = available - amount_dollars
    utilization = (activity / budget * 100) if budget > 0 else 0.0

    return AffordabilityResult(
        can_afford=remaining >= -0.005,  # tolerance for rounding
        category_name=category.name,
        available=round(available, 2),
        requested=round(amount_dollars, 2),
        remaining_after=round(remaining, 2),
        budget=round(budget, 2),
        utilization_pct=round(utilization, 1),
    )


# --- Enhanced Transaction Search ---


def filter_transactions(
    transactions: list[Transaction],
    *,
    payee_name: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    memo_contains: str | None = None,
    category_name: str | None = None,
    account_name: str | None = None,
    uncategorized_only: bool = False,
) -> list[Transaction]:
    """Filter transactions by multiple criteria (AND logic)."""
    result = []
    for t in transactions:
        if t.deleted:
            continue
        if uncategorized_only and t.category_id is not None:
            continue
        if payee_name and payee_name.lower() not in (t.payee_name or "").lower():
            continue
        if category_name and category_name.lower() not in (t.category_name or "").lower():
            continue
        if account_name and account_name.lower() not in (t.account_name or "").lower():
            continue
        if memo_contains and memo_contains.lower() not in (t.memo or "").lower():
            continue
        abs_dollars = abs(milliunits_to_dollars(t.amount))
        if min_amount is not None and abs_dollars < min_amount:
            continue
        if max_amount is not None and abs_dollars > max_amount:
            continue
        result.append(t)
    return result


# --- Split Transaction Helpers ---


def validate_split_amounts(
    total_dollars: float,
    splits: list[SplitItem],
) -> None:
    """Raise ValueError if split amounts don't sum to the total."""
    split_sum = sum(s.amount for s in splits)
    if abs(split_sum - total_dollars) > 0.01:
        raise ValueError(
            f"Split amounts sum to ${split_sum:.2f} but total is ${total_dollars:.2f}. "
            f"Difference: ${abs(split_sum - total_dollars):.2f}"
        )


def build_subtransactions(
    splits: list[SplitItem],
    resolved_categories: dict[str, tuple[str, str]],
) -> list[dict]:
    """Build subtransaction dicts for the YNAB API payload.

    Args:
        splits: List of SplitItem with category_name and amount.
        resolved_categories: Mapping of category_name -> (category_id, resolved_name).
    """
    subtxns = []
    for s in splits:
        cat_id, _ = resolved_categories[s.category_name]
        subtxns.append({
            "amount": dollars_to_milliunits(-abs(s.amount)),
            "category_id": cat_id,
            "memo": s.memo,
        })
    return subtxns


# --- Monthly Budget Setup ---


def compute_budget_assignments(
    source_categories: list[Category],
    strategy: str = "last_month_budget",
) -> list[BudgetAssignment]:
    """Compute budget assignments for next month.

    Strategies:
        - "last_month_budget": Copy the current month's budgeted amounts.
        - "last_month_actual": Use actual spending (absolute activity) as the budget.
    """
    assignments = []
    for cat in source_categories:
        if cat.hidden or cat.deleted:
            continue
        current = milliunits_to_dollars(cat.budgeted)
        if strategy == "last_month_actual":
            proposed = abs(milliunits_to_dollars(cat.activity))
        else:
            proposed = current

        assignments.append(BudgetAssignment(
            category_id=cat.id,
            category_name=cat.name,
            current_budgeted=round(current, 2),
            proposed_budgeted=round(proposed, 2),
        ))
    return assignments


# --- Credit Card Payment Helper ---


def analyze_credit_cards(
    accounts: list[Account],
    groups: list[CategoryGroup],
) -> CreditCardAnalysis:
    """Match credit card accounts to payment categories and flag discrepancies.

    YNAB creates a "Credit Card Payments" category group with a category
    named after each credit card account.
    """
    # Find credit card payment categories
    cc_payment_cats: dict[str, Category] = {}
    for group in groups:
        if "credit card" in group.name.lower():
            for cat in group.categories:
                if cat.deleted or cat.hidden:
                    continue
                cc_payment_cats[cat.name.lower()] = cat

    cards: list[CreditCardInfo] = []
    total_owed = 0.0
    total_payment = 0.0

    for acct in accounts:
        if acct.type != AccountType.CREDIT_CARD or acct.closed:
            continue
        balance = milliunits_to_dollars(acct.balance)  # negative = owed
        owed = abs(balance)

        # Find matching payment category
        payment_cat = cc_payment_cats.get(acct.name.lower())
        payment_avail = 0.0
        payment_name = None
        if payment_cat:
            payment_avail = milliunits_to_dollars(payment_cat.balance)
            payment_name = payment_cat.name

        discrepancy = payment_avail - owed

        cards.append(CreditCardInfo(
            account_name=acct.name,
            account_id=acct.id,
            balance=round(balance, 2),
            payment_category_name=payment_name,
            payment_available=round(payment_avail, 2),
            discrepancy=round(discrepancy, 2),
        ))

        total_owed += owed
        total_payment += payment_avail

    return CreditCardAnalysis(
        cards=cards,
        total_owed=round(total_owed, 2),
        total_payment_available=round(total_payment, 2),
    )


# --- Spending Forecast ---


def forecast_spending(
    category: Category,
    transactions: list[Transaction],
    reference_date: date | None = None,
) -> SpendingForecast:
    """Project spending for a category through end of month.

    Calculates daily spend rate from month-to-date transactions and
    projects whether the budget will hold.
    """
    today = reference_date or date.today()
    first_of_month = today.replace(day=1)
    days_elapsed = (today - first_of_month).days + 1  # include today

    # Last day of month
    if today.month == 12:
        last_day = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(today.year, today.month + 1, 1) - timedelta(days=1)
    days_remaining = (last_day - today).days

    # Sum outflows
    total_spent_mu = sum(
        abs(t.amount) for t in transactions
        if t.amount < 0 and not t.deleted
    )
    spent_dollars = milliunits_to_dollars(total_spent_mu)

    daily_rate = spent_dollars / days_elapsed if days_elapsed > 0 else 0.0
    projected_total = spent_dollars + (daily_rate * days_remaining)
    budget = milliunits_to_dollars(category.budgeted)

    return SpendingForecast(
        category_name=category.name,
        budget=round(budget, 2),
        spent_so_far=round(spent_dollars, 2),
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
        daily_rate=round(daily_rate, 2),
        projected_total=round(projected_total, 2),
        will_stay_in_budget=projected_total <= budget + 0.005,
        projected_remaining=round(budget - projected_total, 2),
    )

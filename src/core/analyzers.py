"""Pure analysis functions for YNAB budget data.

All functions take already-fetched domain objects and return result
dataclasses. No I/O — keeps business logic testable without mocking.
"""

from datetime import date, timedelta
from typing import Any

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
    SplitItem,
    SpendingForecast,
    SpendingTrendResult,
)
from src.core.resolvers import ResolverError, resolve_category
from src.models.schemas import (
    Account,
    AccountType,
    BulkTransactionUpdateInput,
    Category,
    CategoryGroup,
    ScheduledTransaction,
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


def filter_uncategorized_transactions(
    transactions: list[Transaction],
) -> list[Transaction]:
    """Filter to non-deleted transactions with no category assigned."""
    return [
        t for t in transactions
        if not t.deleted and t.category_id is None
    ]


def filter_transaction_by_description(
    transactions: list[Transaction],
    query: str,
) -> Transaction | None:
    """Find a non-deleted transaction matching a search query.

    Searches across payee name, memo, date, and formatted amount.
    Returns the first match or ``None``.
    """
    q = query.lower()
    if not q:
        return None
    for t in transactions:
        if t.deleted:
            continue
        amount_str = f"{abs(milliunits_to_dollars(t.amount)):,.2f}"
        if (
            q in (t.payee_name or "").lower()
            or q in (t.memo or "").lower()
            or q in t.date
            or q in amount_str
        ):
            return t
    return None


# --- Scheduled Transaction Lookup ---


def filter_scheduled_transaction_by_description(
    scheduled_transactions: list[ScheduledTransaction],
    query: str,
) -> ScheduledTransaction | None:
    """Find a non-deleted scheduled transaction matching a search query.

    Searches across payee name, memo, date_next, and formatted amount.
    Returns the first match or ``None``.
    """
    q = query.lower()
    if not q:
        return None
    for st in scheduled_transactions:
        if st.deleted:
            continue
        amount_str = f"{abs(milliunits_to_dollars(st.amount)):,.2f}"
        if (
            q in (st.payee_name or "").lower()
            or q in (st.memo or "").lower()
            or q in st.date_next
            or q in amount_str
        ):
            return st
    return None


# --- Transaction Update Builder ---


def compute_transaction_updates(
    transaction: Transaction,
    *,
    memo: str | None = None,
    category_id: str | None = None,
    category_name: str | None = None,
    payee_name: str | None = None,
    date: str | None = None,
    amount_milliunits: int | None = None,  # milliunits
    flag_color: str | None = None,
    cleared: str | None = None,
    approved: bool | None = None,
) -> tuple[dict[str, Any], list[FieldChange]]:
    """Build the YNAB API update payload and a list of field changes.

    Only includes fields that differ from the current transaction state.
    All parameters except *transaction* are pre-resolved values ready for
    the API.

    Returns a tuple of ``(api_updates_dict, changes_list)``.
    """
    updates: dict[str, Any] = {}
    changes: list[FieldChange] = []

    if memo is not None and memo != (transaction.memo or ""):
        updates["memo"] = memo
        changes.append(FieldChange(
            field_name="Memo",
            old_value=transaction.memo or "(none)",
            new_value=memo or "(cleared)",
        ))

    if category_id is not None and category_id != transaction.category_id:
        updates["category_id"] = category_id
        changes.append(FieldChange(
            field_name="Category",
            old_value=transaction.category_name or "Uncategorized",
            new_value=category_name or category_id,
        ))

    if payee_name is not None and payee_name != (transaction.payee_name or ""):
        updates["payee_name"] = payee_name
        changes.append(FieldChange(
            field_name="Payee",
            old_value=transaction.payee_name or "(none)",
            new_value=payee_name,
        ))

    if date is not None and date != transaction.date:
        updates["date"] = date
        changes.append(FieldChange(
            field_name="Date",
            old_value=transaction.date,
            new_value=date,
        ))

    if amount_milliunits is not None and amount_milliunits != transaction.amount:
        updates["amount"] = amount_milliunits
        old_amt = abs(milliunits_to_dollars(transaction.amount))
        new_amt = abs(milliunits_to_dollars(amount_milliunits))
        changes.append(FieldChange(
            field_name="Amount",
            old_value=f"${old_amt:,.2f}",
            new_value=f"${new_amt:,.2f}",
        ))

    if flag_color is not None and flag_color != (
        transaction.flag_color.value if transaction.flag_color else None
    ):
        updates["flag_color"] = flag_color
        changes.append(FieldChange(
            field_name="Flag",
            old_value=(transaction.flag_color.value if transaction.flag_color else "(none)"),
            new_value=flag_color,
        ))

    if cleared is not None and cleared != transaction.cleared.value:
        updates["cleared"] = cleared
        changes.append(FieldChange(
            field_name="Cleared",
            old_value=transaction.cleared.value,
            new_value=cleared,
        ))

    if approved is not None and approved != transaction.approved:
        updates["approved"] = approved
        changes.append(FieldChange(
            field_name="Approved",
            old_value=str(transaction.approved),
            new_value=str(approved),
        ))

    return updates, changes


def compute_scheduled_transaction_updates(
    scheduled: ScheduledTransaction,
    *,
    date: str | None = None,
    frequency_value: str | None = None,
    amount_milliunits: int | None = None,  # milliunits
    payee: str | None = None,
    category_id: str | None = None,
    category_name: str | None = None,
    memo: str | None = None,
    flag_color: str | None = None,
) -> tuple[dict[str, Any], list[FieldChange]]:
    """Build the YNAB API update payload and a list of field changes.

    Only includes fields that differ from the current scheduled transaction
    state. All parameters except *scheduled* are pre-resolved values ready
    for the API.

    Returns a tuple of ``(api_payload_dict, changes_list)``.
    """
    payload: dict[str, Any] = {}
    changes: list[FieldChange] = []

    if date is not None and date != scheduled.date_next:
        payload["date"] = date
        changes.append(FieldChange(
            field_name="Date",
            old_value=scheduled.date_next,
            new_value=date,
        ))

    if frequency_value is not None and frequency_value != scheduled.frequency.value:
        payload["frequency"] = frequency_value
        changes.append(FieldChange(
            field_name="Frequency",
            old_value=scheduled.frequency.value,
            new_value=frequency_value,
        ))

    if amount_milliunits is not None and amount_milliunits != scheduled.amount:
        payload["amount"] = amount_milliunits
        old_amt = abs(milliunits_to_dollars(scheduled.amount))
        new_amt = abs(milliunits_to_dollars(amount_milliunits))
        changes.append(FieldChange(
            field_name="Amount",
            old_value=f"${old_amt:,.2f}",
            new_value=f"${new_amt:,.2f}",
        ))

    if payee is not None and payee != (scheduled.payee_name or ""):
        payload["payee_name"] = payee
        changes.append(FieldChange(
            field_name="Payee",
            old_value=scheduled.payee_name or "Unknown",
            new_value=payee,
        ))

    if category_id is not None and category_id != scheduled.category_id:
        payload["category_id"] = category_id
        changes.append(FieldChange(
            field_name="Category",
            old_value=scheduled.category_name or "Uncategorized",
            new_value=category_name or category_id,
        ))

    if memo is not None and memo != (scheduled.memo or ""):
        payload["memo"] = memo
        changes.append(FieldChange(
            field_name="Memo",
            old_value=scheduled.memo or "(none)",
            new_value=memo or "(cleared)",
        ))

    if flag_color is not None and flag_color != (
        scheduled.flag_color.value if scheduled.flag_color else None
    ):
        payload["flag_color"] = flag_color
        old_flag = scheduled.flag_color.value if scheduled.flag_color else "(none)"
        changes.append(FieldChange(
            field_name="Flag",
            old_value=old_flag,
            new_value=flag_color,
        ))

    return payload, changes


def compute_bulk_transaction_updates(
    transactions: list[Transaction],
    groups: list[CategoryGroup],
    updates: list[BulkTransactionUpdateInput],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build merged API payloads for a bulk transaction update.

    For each item in *updates*, matches the transaction by description,
    resolves the category (if provided), builds the per-transaction update
    dict, and deduplicates by transaction ID (later updates win).

    Returns a tuple of ``(api_payloads, errors)`` where *api_payloads* is
    the list of merged update dicts ready for the YNAB bulk API, and
    *errors* is a list of human-readable error strings for unmatched items.
    """
    merged: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for item in updates:
        matched = filter_transaction_by_description(transactions, item.transaction_description)
        if not matched:
            errors.append(f"No match for '{item.transaction_description}'")
            continue

        update: dict[str, Any] = {"id": matched.id}
        if item.category_name:
            try:
                cat = resolve_category(groups, item.category_name)
            except ResolverError:
                errors.append(
                    f"No category matching '{item.category_name}'"
                    f" for '{item.transaction_description}'"
                )
                continue
            update["category_id"] = cat.id
        if item.memo is not None:
            update["memo"] = item.memo
        if item.flag_color is not None:
            update["flag_color"] = item.flag_color.value
        if item.cleared is not None:
            update["cleared"] = item.cleared.value
        if item.approved is not None:
            update["approved"] = item.approved

        if matched.id in merged:
            merged[matched.id].update(update)
        else:
            merged[matched.id] = update

    return list(merged.values()), errors


# --- Category Target Updates ---


def compute_category_target_updates(
    category: Category,
    target_amount_milliunits: int | None,
    target_date: str | None,
    clear: bool,
) -> tuple[dict[str, Any], CategoryTargetResult]:
    """Build the PATCH payload and result for setting/clearing a category target.

    Pure function — no I/O.
    """
    old_target = (
        milliunits_to_dollars(category.goal_target)
        if category.goal_target is not None
        else None
    )
    old_target_date = category.goal_target_date

    updates: dict[str, Any] = {}

    if clear:
        updates["goal_target"] = None
        updates["goal_target_date"] = None
        result = CategoryTargetResult(
            category_name=category.name,
            action="removed",
            new_target=None,
            new_target_date=None,
            old_target=old_target,
            old_target_date=old_target_date,
            goal_type=None,
            percentage_complete=None,
            under_funded=None,
        )
    else:
        updates["goal_target"] = target_amount_milliunits
        if target_date is not None:
            updates["goal_target_date"] = target_date

        action = "updated" if category.goal_target is not None else "set"
        new_target_dollars = (
            milliunits_to_dollars(target_amount_milliunits)
            if target_amount_milliunits is not None
            else None
        )
        result = CategoryTargetResult(
            category_name=category.name,
            action=action,
            new_target=new_target_dollars,
            new_target_date=target_date,
            old_target=old_target,
            old_target_date=old_target_date,
            goal_type=None,
            percentage_complete=None,
            under_funded=None,
        )

    return updates, result


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

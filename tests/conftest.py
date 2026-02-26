"""Shared test fixtures for YNAB assistant tests."""

from src.models.schemas import (
    Account,
    AccountType,
    Category,
    CategoryGroup,
    MonthSummary,
    Payee,
    ScheduledTransaction,
    ScheduledTransactionFrequency,
    Transaction,
    TransactionClearedStatus,
    TransactionFlagColor,
)


def make_account(
    name: str = "Checking",
    type_: str = "checking",
    on_budget: bool = True,
    closed: bool = False,
    balance: int = 0,
) -> Account:
    return Account(
        id=f"acc-{name.lower().replace(' ', '-')}",
        name=name,
        type=AccountType(type_),
        on_budget=on_budget,
        closed=closed,
        balance=balance,
        cleared_balance=balance,
        uncleared_balance=0,
    )


def make_category(
    name: str = "Groceries",
    group_id: str = "grp-1",
    hidden: bool = False,
    deleted: bool = False,
    budgeted: int = 0,
    activity: int = 0,
    balance: int = 0,
    goal_type: str | None = None,
    goal_target: int | None = None,
    goal_target_date: str | None = None,
    goal_percentage_complete: int | None = None,
    goal_under_funded: int | None = None,
) -> Category:
    return Category(
        id=f"cat-{name.lower().replace(' ', '-')}",
        category_group_id=group_id,
        name=name,
        hidden=hidden,
        deleted=deleted,
        budgeted=budgeted,
        activity=activity,
        balance=balance,
        goal_type=goal_type,
        goal_target=goal_target,
        goal_target_date=goal_target_date,
        goal_percentage_complete=goal_percentage_complete,
        goal_under_funded=goal_under_funded,
    )


def make_category_group(
    name: str = "Monthly Bills",
    categories: list[Category] | None = None,
    hidden: bool = False,
    deleted: bool = False,
) -> CategoryGroup:
    return CategoryGroup(
        id=f"grp-{name.lower().replace(' ', '-')}",
        name=name,
        hidden=hidden,
        deleted=deleted,
        categories=categories or [],
    )


def make_transaction(
    payee_name: str = "HEB",
    amount: int = -45000,
    category_name: str | None = "Groceries",
    category_id: str | None = "cat-groceries",
    account_name: str = "Checking",
    date: str = "2025-01-15",
    memo: str | None = None,
    deleted: bool = False,
    flag_color: str | None = None,
    cleared: str = "uncleared",
    approved: bool = True,
) -> Transaction:
    return Transaction(
        id=f"txn-{payee_name.lower().replace(' ', '-')}-{date}",
        date=date,
        amount=amount,
        memo=memo,
        cleared=TransactionClearedStatus(cleared),
        approved=approved,
        flag_color=TransactionFlagColor(flag_color) if flag_color else None,
        account_id="acc-checking",
        account_name=account_name,
        payee_name=payee_name,
        category_id=category_id,
        category_name=category_name,
        deleted=deleted,
    )


def make_payee(
    name: str = "HEB",
    deleted: bool = False,
) -> Payee:
    return Payee(
        id=f"payee-{name.lower().replace(' ', '-')}",
        name=name,
        deleted=deleted,
    )


def make_scheduled_transaction(
    payee_name: str = "Netflix",
    amount: int = -15990,
    category_name: str | None = "Subscriptions",
    category_id: str | None = "cat-subscriptions",
    account_name: str = "Checking",
    date_first: str = "2025-01-01",
    date_next: str = "2025-02-01",
    frequency: str = "monthly",
    memo: str | None = None,
    deleted: bool = False,
) -> ScheduledTransaction:
    return ScheduledTransaction(
        id=f"st-{payee_name.lower().replace(' ', '-')}-{date_first}",
        date_first=date_first,
        date_next=date_next,
        frequency=ScheduledTransactionFrequency(frequency),
        amount=amount,
        account_id="acc-checking",
        account_name=account_name,
        payee_name=payee_name,
        category_id=category_id,
        category_name=category_name,
        memo=memo,
        deleted=deleted,
    )


def make_month_summary(
    month: str = "2025-01-01",
    income: int = 5000000,
    budgeted: int = 4500000,
    activity: int = -3200000,
    to_be_budgeted: int = 500000,
) -> MonthSummary:
    return MonthSummary(
        month=month,
        income=income,
        budgeted=budgeted,
        activity=activity,
        to_be_budgeted=to_be_budgeted,
    )

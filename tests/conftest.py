"""Shared test fixtures for YNAB assistant tests."""

from src.models.schemas import (
    Account,
    AccountType,
    Category,
    CategoryGroup,
    MonthSummary,
    Transaction,
    TransactionClearedStatus,
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
) -> Transaction:
    return Transaction(
        id=f"txn-{payee_name.lower().replace(' ', '-')}-{date}",
        date=date,
        amount=amount,
        memo=memo,
        cleared=TransactionClearedStatus.UNCLEARED,
        approved=True,
        account_id="acc-checking",
        account_name=account_name,
        payee_name=payee_name,
        category_id=category_id,
        category_name=category_name,
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

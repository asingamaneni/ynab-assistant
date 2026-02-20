"""Entity resolution helpers for YNAB resources.

Pure functions that resolve user-friendly names (partial, case-insensitive)
to YNAB domain objects. No I/O — they operate on already-fetched data.
"""

from __future__ import annotations

from src.models.schemas import Account, Category, CategoryGroup


class ResolverError(Exception):
    """Raised when an entity cannot be resolved by name."""

    def __init__(
        self,
        entity_type: str,
        query: str,
        available: list[str] | None = None,
    ):
        self.entity_type = entity_type
        self.query = query
        self.available = available or []
        detail = f"No {entity_type} found matching '{query}'."
        if self.available:
            detail += f" Available: {', '.join(self.available)}"
        super().__init__(detail)


def resolve_account(
    accounts: list[Account],
    name: str | None = None,
) -> Account:
    """Find an account by name (partial, case-insensitive).

    If *name* is ``None``, returns the first on-budget checking account,
    falling back to the first on-budget account of any type.

    Raises :class:`ResolverError` if nothing matches.
    """
    open_accounts = [a for a in accounts if not a.closed]

    if name:
        for a in open_accounts:
            if name.lower() in a.name.lower():
                return a
        raise ResolverError(
            "account",
            name,
            available=[a.name for a in open_accounts],
        )

    # Default: prefer checking, then any on-budget
    for a in open_accounts:
        if a.on_budget and a.type.value == "checking":
            return a
    for a in open_accounts:
        if a.on_budget:
            return a

    raise ResolverError("account", "<default>")


def resolve_category(
    groups: list[CategoryGroup],
    name: str,
) -> Category:
    """Find a category by name (partial, case-insensitive) across all groups.

    Raises :class:`ResolverError` if nothing matches.
    """
    _internal_groups = {"Internal Master Category", "Hidden Categories"}
    for group in groups:
        if group.name in _internal_groups or group.hidden or group.deleted:
            continue
        for cat in group.categories:
            if name.lower() in cat.name.lower() and not cat.hidden and not cat.deleted:
                return cat
    raise ResolverError("category", name)

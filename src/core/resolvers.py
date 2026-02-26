"""Entity resolution helpers for YNAB resources.

Pure functions that resolve user-friendly names (partial, case-insensitive)
to YNAB domain objects. No I/O — they operate on already-fetched data.
"""

from __future__ import annotations

from src.models.schemas import Account, Category, CategoryGroup, Payee


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


def resolve_category_or_inflow(
    groups: list[CategoryGroup],
    name: str,
) -> Category:
    """Resolve a category by name, including the special "Inflow: Ready to Assign" category.

    Unlike :func:`resolve_category`, this also searches the
    ``Internal Master Category`` group for the inflow category so that
    income transactions can be categorized.

    Raises :class:`ResolverError` if nothing matches.
    """
    _inflow_name = "Inflow: Ready to Assign"
    _inflow_aliases = {"inflow", "inflow: ready to assign", "ready to assign"}
    if name.strip().lower() in _inflow_aliases:
        for group in groups:
            for cat in group.categories:
                if cat.name == _inflow_name and not cat.deleted:
                    return cat

    # Fall back to standard resolution for regular categories
    return resolve_category(groups, name)


def resolve_payee(
    payees: list[Payee],
    name: str,
) -> Payee:
    """Find a payee by name (partial, case-insensitive).

    Skips deleted payees.  Raises :class:`ResolverError` if nothing matches.
    """
    active = [p for p in payees if not p.deleted]
    for p in active:
        if name.lower() in p.name.lower():
            return p
    raise ResolverError(
        "payee",
        name,
        available=[p.name for p in active[:20]],
    )

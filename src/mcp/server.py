"""YNAB MCP Server.

Exposes YNAB budget operations as MCP tools for use with Claude Desktop
and Claude Code. Provides natural language budget management.
"""

import os
import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP

# Ensure project root is on sys.path so `src` is importable when loaded
# directly by tools like `mcp dev` (which use importlib, not `python -m`).
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

load_dotenv()

from src.core.analyzers import (
    analyze_credit_cards,
    analyze_overspending,
    analyze_spending_trends,
    build_subtransactions,
    check_affordability,
    compute_budget_assignments,
    filter_transactions,
    find_uncategorized_transactions,
    forecast_spending,
    validate_split_amounts,
)
from src.core.categorizer import Categorizer
from src.core.resolvers import resolve_account, resolve_category
from src.core.ynab_client import YNABClient
from src.mcp.error_handling import handle_tool_errors
from src.mcp.formatters import (
    format_accounts,
    format_affordability_check,
    format_budget_setup_applied,
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
    format_transactions,
    format_uncategorized_transactions,
)
from src.models.results import SplitItem
from src.models.schemas import (
    AffordabilityCheckInput,
    BudgetSetupInput,
    CategorizeTransactionInput,
    CreateSplitTransactionInput,
    CreateTransactionInput,
    CreateTransactionNLInput,
    GetTransactionsInput,
    MoveBudgetInput,
    SearchTransactionsInput,
    SpendingForecastInput,
    SpendingTrendInput,
    UpdateCategoryInput,
    dollars_to_milliunits,
    milliunits_to_dollars,
)


# --- Lifespan: initialize shared resources ---


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    token = os.environ.get("YNAB_API_TOKEN", "")
    budget_id = os.environ.get("YNAB_BUDGET_ID", "default")

    if not token:
        raise RuntimeError(
            "YNAB_API_TOKEN environment variable is required. "
            "Get one at https://app.ynab.com/settings/developer"
        )

    client = YNABClient(api_token=token, budget_id=budget_id)

    # Resolve "default" to an actual budget ID (the YNAB API shortcut
    # doesn't work for all accounts).
    if budget_id == "default":
        budgets = await client.get_budgets()
        if budgets:
            client.budget_id = budgets[0].id

    categorizer = Categorizer()

    yield {"ynab": client, "categorizer": categorizer}

    await client.close()


mcp = FastMCP("ynab_mcp", lifespan=app_lifespan)


# --- Helper to get client from context ---


def _get_deps(ctx) -> tuple[YNABClient, Categorizer]:
    state = ctx.request_context.lifespan_context
    return state["ynab"], state["categorizer"]


# --- Read-Only Tools ---


@mcp.tool(
    name="ynab_get_budgets",
    annotations={
        "title": "List YNAB Budgets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_budgets(ctx: Context) -> str:
    """List all YNAB budgets for the authenticated user."""
    ynab, _ = _get_deps(ctx)
    budgets = await ynab.get_budgets()
    return format_budgets(budgets)


@mcp.tool(
    name="ynab_get_accounts",
    annotations={
        "title": "List YNAB Accounts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_accounts(ctx: Context) -> str:
    """List all accounts in the default budget with their balances."""
    ynab, _ = _get_deps(ctx)
    accounts = await ynab.get_accounts()
    return format_accounts(accounts)


@mcp.tool(
    name="ynab_get_budget_summary",
    annotations={
        "title": "Budget Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_budget_summary(ctx: Context) -> str:
    """Get a summary of the current month's budget with category breakdowns."""
    ynab, _ = _get_deps(ctx)
    groups = await ynab.get_categories()
    return format_budget_summary(groups)


@mcp.tool(
    name="ynab_get_transactions",
    annotations={
        "title": "Get Transactions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_transactions(params: GetTransactionsInput, ctx: Context) -> str:
    """Get recent transactions, optionally filtered by date, account, or category."""
    ynab, _ = _get_deps(ctx)
    transactions = await ynab.get_transactions(since_date=params.since_date)

    # Apply client-side name filters
    filtered = []
    for t in transactions:
        if t.deleted:
            continue
        if params.account_name and params.account_name.lower() not in (t.account_name or "").lower():
            continue
        if params.category_name and params.category_name.lower() not in (t.category_name or "").lower():
            continue
        filtered.append(t)

    return format_transactions(filtered, params.limit)


@mcp.tool(
    name="ynab_get_category_spending",
    annotations={
        "title": "Category Spending Detail",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_category_spending(category_name: str, ctx: Context) -> str:
    """Get detailed spending for a specific category this month."""
    ynab, _ = _get_deps(ctx)

    groups = await ynab.get_categories()
    matched = resolve_category(groups, category_name)

    today = date.today()
    first_of_month = today.replace(day=1).isoformat()
    transactions = await ynab.get_transactions(
        category_id=matched.id, since_date=first_of_month
    )

    return format_category_detail(matched, transactions)


# --- Write Tools ---


@mcp.tool(
    name="ynab_assign_budget",
    annotations={
        "title": "Assign Budget to Category",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_assign_budget(category_name: str, amount: float, ctx: Context) -> str:
    """Assign a budgeted amount to a category for the current month."""
    ynab, _ = _get_deps(ctx)

    groups = await ynab.get_categories()
    cat = resolve_category(groups, category_name)

    month = date.today().replace(day=1).isoformat()
    budgeted_milliunits = dollars_to_milliunits(amount)

    await ynab.update_category(
        cat.id, month, UpdateCategoryInput(budgeted=budgeted_milliunits)
    )

    return f"Assigned ${amount:,.2f} to **{cat.name}** for {month}."


@mcp.tool(
    name="ynab_add_transaction",
    annotations={
        "title": "Add Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_add_transaction(params: CreateTransactionNLInput, ctx: Context) -> str:
    """Add a new transaction to YNAB with auto-categorization."""
    ynab, categorizer = _get_deps(ctx)

    # Resolve account
    accounts = await ynab.get_accounts()
    account = resolve_account(accounts, params.account_name)

    # Resolve category
    category_id = None
    category_name_resolved = None
    if params.category_name:
        groups = await ynab.get_categories()
        cat = resolve_category(groups, params.category_name)
        category_id, category_name_resolved = cat.id, cat.name
    else:
        suggestion = categorizer.suggest_category(params.payee)
        if suggestion:
            category_id = suggestion["category_id"]
            category_name_resolved = suggestion["category_name"]

    # Build transaction
    txn_date = params.date or date.today().isoformat()
    amount_milliunits = dollars_to_milliunits(-abs(params.amount))
    if params.amount < 0:
        amount_milliunits = dollars_to_milliunits(abs(params.amount))

    result = await ynab.create_transaction(
        CreateTransactionInput(
            account_id=account.id,
            date=txn_date,
            amount=amount_milliunits,
            payee_name=params.payee,
            category_id=category_id,
            memo=params.memo,
        )
    )

    # Learn the mapping for next time
    if category_id:
        categorizer.learn_from_transactions([{
            "payee_name": params.payee,
            "category_id": category_id,
            "category_name": category_name_resolved,
        }])

    return format_transaction_created(
        result.amount,
        params.payee,
        category_name_resolved,
        result.account_name or account.name,
        txn_date,
        params.memo,
    )


@mcp.tool(
    name="ynab_move_money",
    annotations={
        "title": "Move Money Between Categories",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_move_money(params: MoveBudgetInput, ctx: Context) -> str:
    """Move budgeted money from one category to another."""
    ynab, _ = _get_deps(ctx)

    groups = await ynab.get_categories()
    from_cat = resolve_category(groups, params.from_category)
    to_cat = resolve_category(groups, params.to_category)

    if from_cat.id == to_cat.id:
        return f"Source and destination are the same category ('{from_cat.name}'). No money moved."

    month = params.month or date.today().replace(day=1).isoformat()
    move_amount = dollars_to_milliunits(params.amount)

    # When targeting a non-current month, fetch month-specific budgeted
    # values so the arithmetic is correct.
    from_budgeted = from_cat.budgeted
    to_budgeted = to_cat.budgeted
    if params.month:
        month_data = await ynab.get_month(params.month)
        month_cats = {
            c["id"]: c for c in month_data.get("categories", [])
        }
        if from_cat.id in month_cats:
            from_budgeted = month_cats[from_cat.id].get("budgeted", 0)
        if to_cat.id in month_cats:
            to_budgeted = month_cats[to_cat.id].get("budgeted", 0)

    new_from_budget = from_budgeted - move_amount
    await ynab.update_category(
        from_cat.id, month, UpdateCategoryInput(budgeted=new_from_budget)
    )

    new_to_budget = to_budgeted + move_amount
    await ynab.update_category(
        to_cat.id, month, UpdateCategoryInput(budgeted=new_to_budget)
    )

    return format_move_result(
        from_cat.name, to_cat.name, params.amount,
        new_from_budget, new_to_budget,
    )


@mcp.tool(
    name="ynab_learn_categories",
    annotations={
        "title": "Learn Category Patterns",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_learn_categories(ctx: Context) -> str:
    """Analyze transaction history to learn payee -> category patterns for auto-categorization."""
    ynab, categorizer = _get_deps(ctx)

    transactions = await ynab.get_transactions()
    txn_dicts = [
        {
            "payee_name": t.payee_name,
            "category_id": t.category_id,
            "category_name": t.category_name,
        }
        for t in transactions
        if t.payee_name and t.category_id and not t.deleted
    ]

    categorizer.learn_from_transactions(txn_dicts)
    mappings = categorizer.get_all_mappings()

    return format_learned_categories(len(mappings), len(txn_dicts), mappings)


# --- Analysis Tools ---


@mcp.tool(
    name="ynab_spending_trends",
    annotations={
        "title": "Spending Trends",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_spending_trends(params: SpendingTrendInput, ctx: Context) -> str:
    """Analyze spending trends across months. Compare category spending over time and flag anomalies."""
    ynab, _ = _get_deps(ctx)

    # Fetch transactions going back num_months + 1 to get full data
    today = date.today()
    start = today.replace(day=1)
    for _ in range(params.num_months):
        start = (start - timedelta(days=1)).replace(day=1)

    transactions = await ynab.get_transactions(since_date=start.isoformat())
    result = analyze_spending_trends(
        transactions,
        num_months=params.num_months,
        category_name=params.category_name,
    )
    return format_spending_trends(result)


@mcp.tool(
    name="ynab_search_transactions",
    annotations={
        "title": "Search Transactions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_search_transactions(params: SearchTransactionsInput, ctx: Context) -> str:
    """Search transactions by payee, amount range, memo, category, or uncategorized status."""
    ynab, _ = _get_deps(ctx)

    transactions = await ynab.get_transactions(since_date=params.since_date)
    filtered = filter_transactions(
        transactions,
        payee_name=params.payee_name,
        min_amount=params.min_amount,
        max_amount=params.max_amount,
        memo_contains=params.memo_contains,
        category_name=params.category_name,
        account_name=params.account_name,
        uncategorized_only=params.uncategorized_only,
    )
    return format_transactions(filtered, params.limit)


@mcp.tool(
    name="ynab_uncategorized",
    annotations={
        "title": "Review Uncategorized Transactions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_uncategorized(ctx: Context) -> str:
    """List all uncategorized transactions for review."""
    ynab, _ = _get_deps(ctx)
    transactions = await ynab.get_transactions()
    uncategorized = find_uncategorized_transactions(transactions)
    return format_uncategorized_transactions(uncategorized)


@mcp.tool(
    name="ynab_categorize_transaction",
    annotations={
        "title": "Categorize Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_categorize_transaction(params: CategorizeTransactionInput, ctx: Context) -> str:
    """Assign a category to an uncategorized transaction."""
    ynab, categorizer = _get_deps(ctx)

    # Find the uncategorized transaction matching the description
    transactions = await ynab.get_transactions()
    uncategorized = find_uncategorized_transactions(transactions)

    query = params.transaction_description.lower()
    matched = None
    for t in uncategorized:
        amount_str = f"{abs(milliunits_to_dollars(t.amount)):,.2f}"
        if (query in (t.payee_name or "").lower()
                or query in (t.memo or "").lower()
                or query in t.date
                or query in amount_str):
            matched = t
            break

    if not matched:
        return f"No uncategorized transaction found matching '{params.transaction_description}'."

    # Resolve category
    groups = await ynab.get_categories()
    cat = resolve_category(groups, params.category_name)

    # Update the transaction
    await ynab.update_transaction(matched.id, {"category_id": cat.id})

    # Learn for future auto-categorization
    if matched.payee_name:
        categorizer.learn_from_transactions([{
            "payee_name": matched.payee_name,
            "category_id": cat.id,
            "category_name": cat.name,
        }])

    return format_transaction_categorized(
        matched.payee_name or "Unknown",
        matched.amount,
        cat.name,
    )


@mcp.tool(
    name="ynab_cover_overspending",
    annotations={
        "title": "Cover Overspending",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_cover_overspending(ctx: Context) -> str:
    """Analyze overspent categories and suggest moves to cover them."""
    ynab, _ = _get_deps(ctx)
    groups = await ynab.get_categories()
    result = analyze_overspending(groups)
    return format_overspending_analysis(result)


@mcp.tool(
    name="ynab_affordability_check",
    annotations={
        "title": "Affordability Check",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_affordability_check(params: AffordabilityCheckInput, ctx: Context) -> str:
    """Check if a purchase amount fits within a category's remaining budget."""
    ynab, _ = _get_deps(ctx)

    groups = await ynab.get_categories()
    category = resolve_category(groups, params.category_name)
    result = check_affordability(category, params.amount)
    return format_affordability_check(result)


# --- Tier 2 Tools ---


@mcp.tool(
    name="ynab_add_split_transaction",
    annotations={
        "title": "Add Split Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_add_split_transaction(params: CreateSplitTransactionInput, ctx: Context) -> str:
    """Add a split transaction across multiple categories (e.g. Costco: groceries + household)."""
    ynab, categorizer = _get_deps(ctx)

    # Resolve account
    accounts = await ynab.get_accounts()
    account = resolve_account(accounts, params.account_name)

    # Parse and validate splits
    splits = [SplitItem(**s) for s in params.splits]
    validate_split_amounts(params.amount, splits)

    # Resolve each split's category
    groups = await ynab.get_categories()
    resolved: dict[str, tuple[str, str]] = {}
    for s in splits:
        cat = resolve_category(groups, s.category_name)
        resolved[s.category_name] = (cat.id, cat.name)

    subtxns = build_subtransactions(splits, resolved)

    txn_date = params.date or date.today().isoformat()
    total_milliunits = dollars_to_milliunits(-abs(params.amount))

    result = await ynab.create_transaction(
        CreateTransactionInput(
            account_id=account.id,
            date=txn_date,
            amount=total_milliunits,
            payee_name=params.payee,
            memo=params.memo,
            subtransactions=subtxns,
        )
    )

    # Skip categorizer learning for split transactions — calling
    # learn_from_transactions per-split causes the count-decay logic to
    # fight itself, leaving only the last split's category.

    # Build split info for the formatter
    display_splits = []
    for s in splits:
        _, cat_name = resolved[s.category_name]
        display_splits.append({
            "amount": dollars_to_milliunits(-abs(s.amount)),
            "category_name": cat_name,
            "memo": s.memo,
        })

    return format_split_transaction_created(
        result.amount,
        params.payee,
        result.account_name or account.name,
        txn_date,
        display_splits,
        params.memo,
    )


@mcp.tool(
    name="ynab_setup_budget",
    annotations={
        "title": "Setup Monthly Budget",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_setup_budget(params: BudgetSetupInput, ctx: Context) -> str:
    """Set up next month's budget based on last month's budgeted amounts or actual spending."""
    ynab, _ = _get_deps(ctx)

    # Determine target month
    today = date.today()
    if params.month:
        target_month = params.month
    else:
        if today.month == 12:
            target_month = date(today.year + 1, 1, 1).isoformat()
        else:
            target_month = date(today.year, today.month + 1, 1).isoformat()

    # Get current month categories as source
    groups = await ynab.get_categories()
    all_cats = []
    for group in groups:
        if group.name in ("Internal Master Category", "Hidden Categories"):
            continue
        if group.hidden or group.deleted:
            continue
        all_cats.extend(group.categories)

    assignments = compute_budget_assignments(all_cats, params.strategy)

    if not params.apply:
        return format_budget_setup_preview(assignments)

    # Apply assignments
    for a in assignments:
        if a.proposed_budgeted >= 0:
            await ynab.update_category(
                a.category_id,
                target_month,
                UpdateCategoryInput(budgeted=dollars_to_milliunits(a.proposed_budgeted)),
            )

    return format_budget_setup_applied(assignments, target_month)


@mcp.tool(
    name="ynab_credit_card_status",
    annotations={
        "title": "Credit Card Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_credit_card_status(ctx: Context) -> str:
    """Show credit card payment status, balances, and flag underfunded cards."""
    ynab, _ = _get_deps(ctx)
    accounts = await ynab.get_accounts()
    groups = await ynab.get_categories()
    result = analyze_credit_cards(accounts, groups)
    return format_credit_card_analysis(result)


@mcp.tool(
    name="ynab_spending_forecast",
    annotations={
        "title": "Spending Forecast",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_spending_forecast(params: SpendingForecastInput, ctx: Context) -> str:
    """Forecast spending for a category through end of month based on current pace."""
    ynab, _ = _get_deps(ctx)

    groups = await ynab.get_categories()
    category = resolve_category(groups, params.category_name)

    today = date.today()
    first_of_month = today.replace(day=1).isoformat()
    transactions = await ynab.get_transactions(
        category_id=category.id, since_date=first_of_month
    )

    result = forecast_spending(category, transactions)
    return format_spending_forecast(result)


# --- Entry point ---

if __name__ == "__main__":
    mcp.run()

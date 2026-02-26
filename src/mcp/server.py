"""YNAB MCP Server.

Exposes YNAB budget operations as MCP tools for use with Claude Desktop
and Claude Code. Provides natural language budget management.
"""

import os
import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

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
    compute_bulk_transaction_updates,
    compute_category_target_updates,
    compute_scheduled_transaction_updates,
    compute_transaction_updates,
    filter_scheduled_transaction_by_description,
    filter_transaction_by_description,
    filter_transactions,
    filter_uncategorized_transactions,
    forecast_spending,
    validate_split_amounts,
)
from src.core.categorizer import Categorizer
from src.core.resolvers import (
    resolve_account,
    resolve_category,
    resolve_category_or_inflow,
    resolve_payee,
)
from src.core.ynab_client import YNABClient
from src.mcp.error_handling import handle_tool_errors
from src.mcp.formatters import (
    format_account_created,
    format_accounts,
    format_affordability_check,
    format_budget_settings,
    format_budget_setup_applied,
    format_budget_setup_preview,
    format_budget_summary,
    format_budgets,
    format_bulk_update_result,
    format_category_detail,
    format_category_metadata_updated,
    format_category_targets,
    format_category_target_set,
    format_credit_card_analysis,
    format_import_result,
    format_learned_categories,
    format_move_result,
    format_overspending_analysis,
    format_payee_locations,
    format_payee_updated,
    format_payees,
    format_scheduled_transaction_created,
    format_scheduled_transaction_deleted,
    format_scheduled_transaction_updated,
    format_scheduled_transactions,
    format_spending_forecast,
    format_spending_trends,
    format_split_transaction_created,
    format_transaction_categorized,
    format_transaction_created,
    format_transaction_deleted,
    format_transaction_recategorized,
    format_transaction_updated,
    format_transactions,
    format_uncategorized_transactions,
    format_user,
)
from src.models.results import SplitItem, TransactionUpdateResult
from src.models.schemas import (
    AffordabilityCheckInput,
    BudgetSetupInput,
    BulkUpdateTransactionsInput,
    CategorizeTransactionInput,
    CreateAccountInput,
    CreateScheduledTransactionInput,
    CreateSplitTransactionInput,
    CreateTransactionInput,
    CreateTransactionNLInput,
    DeleteScheduledTransactionInput,
    DeleteTransactionInput,
    GetPayeeTransactionsInput,
    GetTransactionsInput,
    MoveBudgetInput,
    RecategorizeTransactionInput,
    SearchTransactionsInput,
    SetCategoryTargetInput,
    SpendingForecastInput,
    SpendingTrendInput,
    UpdateCategoryInput,
    UpdateCategoryMetadataInput,
    UpdatePayeeInput,
    UpdateScheduledTransactionInput,
    UpdateTransactionInput,
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
    uncategorized = filter_uncategorized_transactions(transactions)
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
    uncategorized = filter_uncategorized_transactions(transactions)

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

    # Update the transaction and auto-approve (imported transactions need explicit approval)
    await ynab.update_transaction(matched.id, {"category_id": cat.id, "approved": True})

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
    name="ynab_recategorize_transaction",
    annotations={
        "title": "Recategorize Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_recategorize_transaction(params: RecategorizeTransactionInput, ctx: Context) -> str:
    """Change the category of any transaction, including already-categorized ones. Supports income (Inflow: Ready to Assign)."""
    ynab, categorizer = _get_deps(ctx)

    # Search all non-deleted transactions
    transactions = await ynab.get_transactions()
    matched = filter_transaction_by_description(transactions, params.transaction_description)

    if not matched:
        return f"No transaction found matching '{params.transaction_description}'."

    # Resolve category (including inflow for income)
    groups = await ynab.get_categories()
    cat = resolve_category_or_inflow(groups, params.new_category_name)

    # Update the transaction and auto-approve (imported transactions need explicit approval)
    old_category = matched.category_name
    await ynab.update_transaction(matched.id, {"category_id": cat.id, "approved": True})

    # Learn for future auto-categorization (skip for inflow)
    if matched.payee_name and "inflow" not in cat.name.lower():
        categorizer.learn_from_transactions([{
            "payee_name": matched.payee_name,
            "category_id": cat.id,
            "category_name": cat.name,
        }])

    return format_transaction_recategorized(
        matched.payee_name or "Unknown",
        matched.amount,
        old_category,
        cat.name,
    )


@mcp.tool(
    name="ynab_update_transaction",
    annotations={
        "title": "Update Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_update_transaction(params: UpdateTransactionInput, ctx: Context) -> str:
    """Update any editable field on an existing transaction (memo, category, payee, date, amount, flag, cleared, approved)."""
    ynab, categorizer = _get_deps(ctx)

    # 1. Find the transaction
    transactions = await ynab.get_transactions()
    matched = filter_transaction_by_description(transactions, params.transaction_description)
    if not matched:
        return f"No transaction found matching '{params.transaction_description}'."

    # 2. Resolve category if provided
    resolved_cat_id: str | None = None
    resolved_cat_name: str | None = None
    if params.category_name is not None:
        groups = await ynab.get_categories()
        cat = resolve_category_or_inflow(groups, params.category_name)
        resolved_cat_id = cat.id
        resolved_cat_name = cat.name

    # 3. Convert amount if provided
    amount_milliunits: int | None = None
    if params.amount is not None:
        if params.amount < 0:  # inflow/refund
            amount_milliunits = dollars_to_milliunits(abs(params.amount))
        else:
            amount_milliunits = dollars_to_milliunits(-abs(params.amount))

    # 4. Build update payload (pure)
    updates, changes = compute_transaction_updates(
        matched,
        memo=params.memo,
        category_id=resolved_cat_id,
        category_name=resolved_cat_name,
        payee_name=params.payee,
        date=params.date,
        amount_milliunits=amount_milliunits,
        flag_color=params.flag_color.value if params.flag_color else None,
        cleared=params.cleared.value if params.cleared else None,
        approved=params.approved,
    )

    if not updates:
        return (
            f"No changes needed — the transaction at "
            f"**{matched.payee_name or 'Unknown'}** already has those values."
        )

    # 5. Apply the update
    result_txn = await ynab.update_transaction(matched.id, updates)

    # 6. Learn category mapping if category was changed
    if resolved_cat_id and "inflow" not in (resolved_cat_name or "").lower():
        payee_for_learning = params.payee or matched.payee_name
        if payee_for_learning:
            categorizer.learn_from_transactions([{
                "payee_name": payee_for_learning,
                "category_id": resolved_cat_id,
                "category_name": resolved_cat_name,
            }])

    # 7. Format and return
    update_result = TransactionUpdateResult(
        payee_name=result_txn.payee_name or matched.payee_name or "Unknown",
        amount_milliunits=result_txn.amount,
        date=result_txn.date,
        changes=changes,
    )
    return format_transaction_updated(update_result)


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


# --- New API Feature Tools ---


@mcp.tool(
    name="ynab_delete_transaction",
    annotations={
        "title": "Delete Transaction",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_delete_transaction(params: DeleteTransactionInput, ctx: Context) -> str:
    """Delete a transaction by description (payee, date, or amount)."""
    ynab, _ = _get_deps(ctx)

    transactions = await ynab.get_transactions()
    matched = filter_transaction_by_description(transactions, params.transaction_description)
    if not matched:
        return f"No transaction found matching '{params.transaction_description}'."

    payee = matched.payee_name or "Unknown"
    amount = matched.amount
    txn_date = matched.date

    await ynab.delete_transaction(matched.id)
    return format_transaction_deleted(payee, amount, txn_date)


@mcp.tool(
    name="ynab_get_payees",
    annotations={
        "title": "List Payees",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_payees(ctx: Context) -> str:
    """List all payees in the budget."""
    ynab, _ = _get_deps(ctx)
    payees = await ynab.get_payees()
    return format_payees(payees)


@mcp.tool(
    name="ynab_update_payee",
    annotations={
        "title": "Rename Payee",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_update_payee(params: UpdatePayeeInput, ctx: Context) -> str:
    """Rename a payee."""
    ynab, _ = _get_deps(ctx)

    payees = await ynab.get_payees()
    matched = resolve_payee(payees, params.payee_name)
    old_name = matched.name

    await ynab.update_payee(matched.id, params.new_name)
    return format_payee_updated(old_name, params.new_name)


@mcp.tool(
    name="ynab_update_category_metadata",
    annotations={
        "title": "Update Category Name/Note",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_update_category_metadata(params: UpdateCategoryMetadataInput, ctx: Context) -> str:
    """Update a category's name or note."""
    ynab, _ = _get_deps(ctx)

    groups = await ynab.get_categories()
    cat = resolve_category(groups, params.category_name)

    updates: dict[str, str] = {}
    if params.new_name is not None:
        updates["name"] = params.new_name
    if params.note is not None:
        updates["note"] = params.note

    await ynab.update_category_metadata(cat.id, updates)
    return format_category_metadata_updated(
        cat.name,
        old_name=cat.name if params.new_name is not None else None,
        new_name=params.new_name,
        old_note=cat.note if params.note is not None else None,
        new_note=params.note,
    )


@mcp.tool(
    name="ynab_get_category_targets",
    annotations={
        "title": "Get Category Targets/Goals",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@handle_tool_errors
async def ynab_get_category_targets(ctx: Context) -> str:
    """List all categories that have a target/goal set, with funding progress."""
    ynab, _ = _get_deps(ctx)
    groups = await ynab.get_categories()
    return format_category_targets(groups)


@mcp.tool(
    name="ynab_set_category_target",
    annotations={
        "title": "Set Category Target/Goal",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_set_category_target(params: SetCategoryTargetInput, ctx: Context) -> str:
    """Set, update, or remove a savings target/goal on a budget category."""
    ynab, _ = _get_deps(ctx)

    # 1. Fetch categories and resolve by name
    groups = await ynab.get_categories()
    cat = resolve_category(groups, params.category_name)

    # 2. Re-fetch the single category to get current goal fields
    cat_full = await ynab.get_category(cat.id)

    # 3. Compute updates (pure)
    target_milliunits = (
        dollars_to_milliunits(params.target_amount)
        if params.target_amount is not None
        else None
    )
    updates, result = compute_category_target_updates(
        cat_full,
        target_amount_milliunits=target_milliunits,
        target_date=params.target_date,
        clear=params.clear_target,
    )

    # 4. Apply via the existing category-level PATCH endpoint
    updated_cat = await ynab.update_category_metadata(cat.id, updates)

    # 5. Enrich result with post-update goal fields from API response
    result.goal_type = updated_cat.goal_type
    result.percentage_complete = updated_cat.goal_percentage_complete
    result.under_funded = (
        milliunits_to_dollars(updated_cat.goal_under_funded)
        if updated_cat.goal_under_funded is not None
        else None
    )

    # 6. Format and return
    return format_category_target_set(result)


@mcp.tool(
    name="ynab_create_account",
    annotations={
        "title": "Create Account",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_create_account(params: CreateAccountInput, ctx: Context) -> str:
    """Create a new budget account."""
    ynab, _ = _get_deps(ctx)

    balance_milliunits = dollars_to_milliunits(params.balance)
    account = await ynab.create_account(params.name, params.type.value, balance_milliunits)
    return format_account_created(account.name, account.type.value, params.balance)


@mcp.tool(
    name="ynab_import_transactions",
    annotations={
        "title": "Import Bank Transactions",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_import_transactions(ctx: Context) -> str:
    """Trigger linked account import and return newly imported transactions."""
    ynab, _ = _get_deps(ctx)
    transaction_ids = await ynab.import_transactions()
    return format_import_result(transaction_ids)


@mcp.tool(
    name="ynab_bulk_update_transactions",
    annotations={
        "title": "Bulk Update Transactions",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_bulk_update_transactions(params: BulkUpdateTransactionsInput, ctx: Context) -> str:
    """Update multiple transactions at once (category, memo, flag, cleared, approved)."""
    ynab, _ = _get_deps(ctx)

    transactions = await ynab.get_transactions()
    groups = await ynab.get_categories()

    api_updates, errors = compute_bulk_transaction_updates(
        transactions, groups, params.updates
    )

    if api_updates:
        await ynab.bulk_update_transactions(api_updates)

    return format_bulk_update_result(len(api_updates), errors)


@mcp.tool(
    name="ynab_get_budget_settings",
    annotations={
        "title": "Budget Settings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_budget_settings(ctx: Context) -> str:
    """Get budget settings (date format, currency format)."""
    ynab, _ = _get_deps(ctx)
    settings = await ynab.get_budget_settings()
    return format_budget_settings(settings)


@mcp.tool(
    name="ynab_get_user",
    annotations={
        "title": "Get User",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_user(ctx: Context) -> str:
    """Get the authenticated YNAB user."""
    ynab, _ = _get_deps(ctx)
    user = await ynab.get_user()
    return format_user(user)


@mcp.tool(
    name="ynab_get_payee_locations",
    annotations={
        "title": "Payee Locations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_payee_locations(ctx: Context) -> str:
    """List all payee locations (latitude/longitude)."""
    ynab, _ = _get_deps(ctx)
    locations = await ynab.get_payee_locations()
    payees = await ynab.get_payees()
    return format_payee_locations(locations, payees)


@mcp.tool(
    name="ynab_get_scheduled_transactions",
    annotations={
        "title": "List Scheduled Transactions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_scheduled_transactions(ctx: Context) -> str:
    """List all scheduled/recurring transactions."""
    ynab, _ = _get_deps(ctx)
    scheduled = await ynab.get_scheduled_transactions()
    return format_scheduled_transactions(scheduled)


@mcp.tool(
    name="ynab_create_scheduled_transaction",
    annotations={
        "title": "Create Scheduled Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_create_scheduled_transaction(
    params: CreateScheduledTransactionInput, ctx: Context
) -> str:
    """Create a new scheduled/recurring transaction."""
    ynab, _ = _get_deps(ctx)

    accounts = await ynab.get_accounts()
    account = resolve_account(accounts, params.account_name)

    category_id = None
    category_name_resolved = None
    if params.category_name:
        groups = await ynab.get_categories()
        cat = resolve_category(groups, params.category_name)
        category_id = cat.id
        category_name_resolved = cat.name

    amount_milliunits = dollars_to_milliunits(-abs(params.amount))
    if params.amount < 0:
        amount_milliunits = dollars_to_milliunits(abs(params.amount))

    payload: dict[str, Any] = {
        "account_id": account.id,
        "date": params.date,
        "frequency": params.frequency.value,
        "amount": amount_milliunits,
        "payee_name": params.payee,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    if params.memo is not None:
        payload["memo"] = params.memo

    result = await ynab.create_scheduled_transaction(payload)
    return format_scheduled_transaction_created(
        result, account.name, category_name_resolved
    )


@mcp.tool(
    name="ynab_update_scheduled_transaction",
    annotations={
        "title": "Update Scheduled Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_update_scheduled_transaction(
    params: UpdateScheduledTransactionInput, ctx: Context
) -> str:
    """Update a scheduled transaction's fields."""
    ynab, _ = _get_deps(ctx)

    scheduled = await ynab.get_scheduled_transactions()
    matched = filter_scheduled_transaction_by_description(
        scheduled, params.scheduled_transaction_description
    )
    if not matched:
        return f"No scheduled transaction found matching '{params.scheduled_transaction_description}'."

    # Resolve dependent values before the pure computation step
    amount_milliunits = None
    if params.amount is not None:
        amount_milliunits = dollars_to_milliunits(-abs(params.amount))
        if params.amount < 0:
            amount_milliunits = dollars_to_milliunits(abs(params.amount))

    category_id = None
    category_name_resolved = None
    if params.category_name is not None:
        groups = await ynab.get_categories()
        cat = resolve_category(groups, params.category_name)
        category_id = cat.id
        category_name_resolved = cat.name

    payload, changes = compute_scheduled_transaction_updates(
        matched,
        date=params.date,
        frequency_value=params.frequency.value if params.frequency else None,
        amount_milliunits=amount_milliunits,
        payee=params.payee,
        category_id=category_id,
        category_name=category_name_resolved,
        memo=params.memo,
        flag_color=params.flag_color.value if params.flag_color else None,
    )

    if not payload:
        return (
            f"No changes needed — the scheduled transaction for "
            f"**{matched.payee_name or 'Unknown'}** already has those values."
        )

    await ynab.update_scheduled_transaction(matched.id, payload)
    return format_scheduled_transaction_updated(
        matched.payee_name or "Unknown", changes
    )


@mcp.tool(
    name="ynab_delete_scheduled_transaction",
    annotations={
        "title": "Delete Scheduled Transaction",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_delete_scheduled_transaction(
    params: DeleteScheduledTransactionInput, ctx: Context
) -> str:
    """Delete a scheduled/recurring transaction."""
    ynab, _ = _get_deps(ctx)

    scheduled = await ynab.get_scheduled_transactions()
    matched = filter_scheduled_transaction_by_description(
        scheduled, params.scheduled_transaction_description
    )
    if not matched:
        return f"No scheduled transaction found matching '{params.scheduled_transaction_description}'."

    payee = matched.payee_name or "Unknown"
    amount = matched.amount
    date_next = matched.date_next

    await ynab.delete_scheduled_transaction(matched.id)
    return format_scheduled_transaction_deleted(payee, amount, date_next)


@mcp.tool(
    name="ynab_get_payee_transactions",
    annotations={
        "title": "Get Payee Transactions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
@handle_tool_errors
async def ynab_get_payee_transactions(params: GetPayeeTransactionsInput, ctx: Context) -> str:
    """Get transactions for a specific payee."""
    ynab, _ = _get_deps(ctx)

    payees = await ynab.get_payees()
    matched = resolve_payee(payees, params.payee_name)

    transactions = await ynab.get_payee_transactions(
        matched.id, since_date=params.since_date
    )
    return format_transactions(transactions, params.limit)


# --- Entry point ---

if __name__ == "__main__":
    mcp.run()

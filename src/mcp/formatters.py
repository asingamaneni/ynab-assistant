"""Markdown formatters for MCP tool responses.

Pure functions that take domain objects and return human-readable Markdown strings.
"""

from __future__ import annotations

from src.models.results import (
    AffordabilityResult,
    BudgetAssignment,
    CreditCardAnalysis,
    OverspendingResult,
    SpendingForecast,
    SpendingTrendResult,
)
from src.models.schemas import (
    Budget,
    Account,
    Category,
    CategoryGroup,
    Transaction,
    milliunits_to_dollars,
)


def format_budgets(budgets: list[Budget]) -> str:
    if not budgets:
        return "No budgets found."
    lines = ["## Your Budgets\n"]
    for b in budgets:
        lines.append(f"- **{b.name}** (ID: `{b.id}`)")
    return "\n".join(lines)


def format_accounts(accounts: list[Account]) -> str:
    lines = ["## Accounts\n"]
    for a in accounts:
        if a.closed:
            continue
        balance = milliunits_to_dollars(a.balance)
        status = "+" if balance >= 0 else "-"
        lines.append(f"- {status} **{a.name}** ({a.type.value}): ${abs(balance):,.2f}")
    return "\n".join(lines) if len(lines) > 1 else "No open accounts found."


def format_budget_summary(groups: list[CategoryGroup]) -> str:
    lines = ["## Budget Summary (Current Month)\n"]
    total_budgeted = 0
    total_activity = 0
    total_balance = 0

    for group in groups:
        if group.hidden or group.deleted:
            continue
        if group.name in ("Internal Master Category", "Hidden Categories"):
            continue

        active_cats = [c for c in group.categories if not c.hidden and not c.deleted]
        group_budgeted = sum(c.budgeted for c in active_cats)
        group_activity = sum(c.activity for c in active_cats)
        group_balance = sum(c.balance for c in active_cats)

        if group_budgeted == 0 and group_activity == 0:
            continue

        lines.append(f"\n### {group.name}")
        for cat in active_cats:
            if cat.budgeted == 0 and cat.activity == 0:
                continue
            bal = milliunits_to_dollars(cat.balance)
            act = milliunits_to_dollars(cat.activity)
            bud = milliunits_to_dollars(cat.budgeted)
            emoji = "OK" if bal >= 0 else "!!"
            lines.append(
                f"  [{emoji}] {cat.name}: "
                f"${bud:,.2f} budgeted | ${abs(act):,.2f} spent | ${bal:,.2f} left"
            )

        total_budgeted += group_budgeted
        total_activity += group_activity
        total_balance += group_balance

    lines.append("\n---")
    lines.append(
        f"**Totals:** ${milliunits_to_dollars(total_budgeted):,.2f} budgeted | "
        f"${abs(milliunits_to_dollars(total_activity)):,.2f} spent | "
        f"${milliunits_to_dollars(total_balance):,.2f} remaining"
    )
    return "\n".join(lines)


def format_transactions(transactions: list[Transaction], limit: int) -> str:
    filtered = [t for t in transactions if not t.deleted]
    filtered.sort(key=lambda t: t.date, reverse=True)
    filtered = filtered[:limit]

    if not filtered:
        return "No transactions found matching your criteria."

    lines = [f"## Transactions ({len(filtered)} shown)\n"]
    for t in filtered:
        amount = milliunits_to_dollars(t.amount)
        direction = "IN" if amount > 0 else "OUT"
        lines.append(
            f"- {t.date} [{direction}] **${abs(amount):,.2f}** "
            f"| {t.payee_name or 'Unknown'} "
            f"| {t.category_name or 'Uncategorized'} "
            f"| {t.account_name or ''}"
        )
        if t.memo:
            lines.append(f"  _Memo: {t.memo}_")
    return "\n".join(lines)


def format_category_detail(category: Category, transactions: list[Transaction]) -> str:
    bud = milliunits_to_dollars(category.budgeted)
    act = milliunits_to_dollars(category.activity)
    bal = milliunits_to_dollars(category.balance)

    lines = [
        f"## {category.name}",
        f"**Budgeted:** ${bud:,.2f}",
        f"**Spent:** ${abs(act):,.2f}",
        f"**Remaining:** ${bal:,.2f}",
        "",
        f"### Transactions this month ({len(transactions)})",
    ]

    for t in sorted(transactions, key=lambda x: x.date, reverse=True):
        if t.deleted:
            continue
        amt = milliunits_to_dollars(t.amount)
        lines.append(f"- {t.date} | ${abs(amt):,.2f} | {t.payee_name or 'Unknown'}")
    return "\n".join(lines)


def format_move_result(
    from_name: str,
    to_name: str,
    amount: float,
    new_from_budget: int,
    new_to_budget: int,
) -> str:
    return (
        f"Moved ${amount:,.2f}\n\n"
        f"- **From:** {from_name} (new budget: ${milliunits_to_dollars(new_from_budget):,.2f})\n"
        f"- **To:** {to_name} (new budget: ${milliunits_to_dollars(new_to_budget):,.2f})"
    )


def format_transaction_created(
    amount_milliunits: int,
    payee: str,
    category_name: str | None,
    account_name: str,
    txn_date: str,
    memo: str | None,
) -> str:
    amt = milliunits_to_dollars(amount_milliunits)
    lines = [
        "Transaction added!\n",
        f"- **Amount:** ${abs(amt):,.2f} {'inflow' if amt > 0 else 'outflow'}",
        f"- **Payee:** {payee}",
        f"- **Category:** {category_name or 'Uncategorized'}",
        f"- **Account:** {account_name}",
        f"- **Date:** {txn_date}",
    ]
    if memo:
        lines.append(f"- **Memo:** {memo}")
    return "\n".join(lines)


def format_learned_categories(mapping_count: int, txn_count: int, mappings: dict) -> str:
    lines = [
        f"Learned {mapping_count} payee -> category mappings "
        f"from {txn_count} transactions.\n",
        "Now when you add a transaction, I'll auto-suggest the category. Examples:",
    ]
    for k, v in list(mappings.items())[:10]:
        lines.append(f"- {k.title()} -> {v['category_name']}")
    return "\n".join(lines)


# --- New Formatters ---


def format_spending_trends(result: SpendingTrendResult) -> str:
    """Month-over-month spending comparison with anomaly flags."""
    title = "Spending Trends"
    if result.category_filter:
        title += f" ({result.category_filter})"
    lines = [f"## {title}\n"]

    if not result.monthly_totals or all(
        not cats for cats in result.monthly_totals.values()
    ):
        return "No spending data found for the requested period."

    # Collect all categories across months
    all_cats = sorted(result.averages.keys())
    months = sorted(result.monthly_totals.keys())

    # Header row
    header = "| Category | " + " | ".join(months) + " | Avg |"
    sep = "|" + "---|" * (len(months) + 2)
    lines.append(header)
    lines.append(sep)

    for cat in all_cats:
        row = f"| {cat} "
        for m in months:
            val = result.monthly_totals[m].get(cat, 0.0)
            row += f"| ${val:,.2f} "
        row += f"| ${result.averages[cat]:,.2f} |"
        lines.append(row)

    if result.anomalies:
        lines.append("\n### Anomalies")
        for a in result.anomalies:
            lines.append(
                f"- **{a.category_name}**: ${a.current_amount:,.2f} this month "
                f"vs ${a.average_amount:,.2f} avg "
                f"({a.pct_above_average:.0f}% above average)"
            )

    return "\n".join(lines)


def format_uncategorized_transactions(transactions: list[Transaction]) -> str:
    """List uncategorized transactions with index numbers for reference."""
    if not transactions:
        return "No uncategorized transactions found."

    lines = [f"## Uncategorized Transactions ({len(transactions)})\n"]
    for i, t in enumerate(sorted(transactions, key=lambda x: x.date, reverse=True), 1):
        amount = milliunits_to_dollars(t.amount)
        direction = "IN" if amount > 0 else "OUT"
        lines.append(
            f"{i}. {t.date} [{direction}] **${abs(amount):,.2f}** "
            f"| {t.payee_name or 'Unknown'} "
            f"| {t.account_name or ''}"
        )
        if t.memo:
            lines.append(f"   _Memo: {t.memo}_")

    lines.append("\nTo categorize, tell me which transaction and what category.")
    return "\n".join(lines)


def format_transaction_categorized(payee: str, amount_milliunits: int, new_category: str) -> str:
    """Confirmation after categorizing a transaction."""
    amt = milliunits_to_dollars(amount_milliunits)
    return (
        f"Categorized **${abs(amt):,.2f}** at **{payee}** "
        f"as **{new_category}**."
    )


def format_overspending_analysis(result: OverspendingResult) -> str:
    """Show overspent categories, sources, and suggested moves."""
    if not result.overspent:
        return "No overspending found. All categories are on track!"

    lines = [
        f"## Overspending Analysis",
        f"\nTotal overspent: **${result.total_overspent:,.2f}**\n",
        "### Overspent Categories",
    ]
    for c in result.overspent:
        lines.append(f"- **{c.name}**: ${abs(c.amount):,.2f} over budget")

    if result.suggestions:
        lines.append("\n### Suggested Moves")
        for s in result.suggestions:
            lines.append(
                f"- Move **${s.amount:,.2f}** from {s.from_category} -> {s.to_category}"
            )
        lines.append(
            "\nUse `ynab_move_money` to execute these moves, "
            "or tell me to cover them."
        )
    else:
        lines.append(
            "\nNo categories with enough surplus to cover the overspending."
        )

    return "\n".join(lines)


def format_affordability_check(result: AffordabilityResult) -> str:
    """Clear yes/no with budget context."""
    verdict = "Yes" if result.can_afford else "No"
    emoji = "OK" if result.can_afford else "!!"

    lines = [
        f"## [{emoji}] {verdict}, {'you can' if result.can_afford else 'you cannot'} afford ${result.requested:,.2f} in {result.category_name}\n",
        f"- **Available:** ${result.available:,.2f}",
        f"- **After purchase:** ${result.remaining_after:,.2f}",
        f"- **Budget:** ${result.budget:,.2f}",
        f"- **Budget used:** {result.utilization_pct:.0f}%",
    ]
    return "\n".join(lines)


def format_split_transaction_created(
    total_milliunits: int,
    payee: str,
    account_name: str,
    txn_date: str,
    splits: list[dict],
    memo: str | None = None,
) -> str:
    """Confirmation showing the split breakdown."""
    amt = milliunits_to_dollars(total_milliunits)
    lines = [
        "Split transaction added!\n",
        f"- **Total:** ${abs(amt):,.2f} {'inflow' if amt > 0 else 'outflow'}",
        f"- **Payee:** {payee}",
        f"- **Account:** {account_name}",
        f"- **Date:** {txn_date}",
    ]
    if memo:
        lines.append(f"- **Memo:** {memo}")

    lines.append("\n**Splits:**")
    for s in splits:
        s_amt = abs(milliunits_to_dollars(s.get("amount", 0)))
        s_cat = s.get("category_name", "Unknown")
        s_memo = s.get("memo", "")
        line = f"  - ${s_amt:,.2f} -> {s_cat}"
        if s_memo:
            line += f" ({s_memo})"
        lines.append(line)

    return "\n".join(lines)


def format_budget_setup_preview(assignments: list[BudgetAssignment]) -> str:
    """Preview table of proposed budget assignments."""
    if not assignments:
        return "No categories to assign."

    lines = [
        "## Budget Setup Preview\n",
        "| Category | Current | Proposed | Change |",
        "|---|---|---|---|",
    ]
    for a in assignments:
        change = a.proposed_budgeted - a.current_budgeted
        sign = "+" if change > 0 else ""
        lines.append(
            f"| {a.category_name} "
            f"| ${a.current_budgeted:,.2f} "
            f"| ${a.proposed_budgeted:,.2f} "
            f"| {sign}${change:,.2f} |"
        )

    total_proposed = sum(a.proposed_budgeted for a in assignments)
    lines.append(f"\n**Total proposed:** ${total_proposed:,.2f}")
    lines.append("\nSet `apply: true` to apply these assignments.")
    return "\n".join(lines)


def format_budget_setup_applied(assignments: list[BudgetAssignment], month: str) -> str:
    """Confirmation after applying budget assignments."""
    lines = [f"## Budget Applied for {month}\n"]
    for a in assignments:
        lines.append(f"- {a.category_name}: ${a.proposed_budgeted:,.2f}")
    total = sum(a.proposed_budgeted for a in assignments)
    lines.append(f"\n**Total assigned:** ${total:,.2f}")
    return "\n".join(lines)


def format_credit_card_analysis(result: CreditCardAnalysis) -> str:
    """Per-card status with payment discrepancies."""
    if not result.cards:
        return "No open credit card accounts found."

    lines = ["## Credit Card Status\n"]
    for card in result.cards:
        owed = abs(card.balance)
        status = "OK" if card.discrepancy >= -0.005 else "!!"
        lines.append(f"### [{status}] {card.account_name}")
        lines.append(f"- **Balance owed:** ${owed:,.2f}")
        lines.append(f"- **Payment available:** ${card.payment_available:,.2f}")
        if card.discrepancy < -0.005:
            lines.append(f"- **Underfunded by:** ${abs(card.discrepancy):,.2f}")
        elif card.discrepancy > 0.005:
            lines.append(f"- **Overfunded by:** ${card.discrepancy:,.2f}")
        else:
            lines.append("- **Fully funded**")
        lines.append("")

    lines.append("---")
    lines.append(f"**Total owed:** ${result.total_owed:,.2f}")
    lines.append(f"**Total payment available:** ${result.total_payment_available:,.2f}")
    return "\n".join(lines)


def format_spending_forecast(result: SpendingForecast) -> str:
    """Daily rate, projected total, and budget status."""
    status = "OK" if result.will_stay_in_budget else "!!"
    verdict = "on track" if result.will_stay_in_budget else "projected to exceed budget"

    lines = [
        f"## [{status}] {result.category_name} Forecast\n",
        f"- **Budget:** ${result.budget:,.2f}",
        f"- **Spent so far:** ${result.spent_so_far:,.2f} ({result.days_elapsed} days)",
        f"- **Daily rate:** ${result.daily_rate:,.2f}/day",
        f"- **Projected total:** ${result.projected_total:,.2f} ({result.days_remaining} days left)",
        f"- **Projected remaining:** ${result.projected_remaining:,.2f}",
        f"\n**Status:** {verdict.capitalize()}",
    ]
    return "\n".join(lines)

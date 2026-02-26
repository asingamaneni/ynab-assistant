"""Markdown formatters for MCP tool responses.

Pure functions that take domain objects and return human-readable Markdown strings.
"""

from __future__ import annotations

from src.models.results import (
    AffordabilityResult,
    BudgetAssignment,
    CategoryTargetResult,
    CreditCardAnalysis,
    FieldChange,
    OverspendingResult,
    SpendingForecast,
    SpendingTrendResult,
    TransactionUpdateResult,
)
from src.models.schemas import (
    Budget,
    Account,
    BudgetSettings,
    Category,
    CategoryGroup,
    Payee,
    PayeeLocation,
    ScheduledTransaction,
    Transaction,
    User,
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
        status = "✓" if t.approved else "⏳"
        lines.append(
            f"- {t.date} [{direction}] **${abs(amount):,.2f}** "
            f"| {t.payee_name or 'Unknown'} "
            f"| {t.category_name or 'Uncategorized'} "
            f"| {t.account_name or ''} "
            f"| {status}"
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


def format_transaction_recategorized(
    payee: str,
    amount_milliunits: int,
    old_category: str | None,
    new_category: str,
) -> str:
    """Confirmation after recategorizing a transaction."""
    amt = milliunits_to_dollars(amount_milliunits)
    old = old_category or "Uncategorized"
    return (
        f"Recategorized **${abs(amt):,.2f}** at **{payee}**: "
        f"{old} → **{new_category}**."
    )


def format_transaction_updated(result: TransactionUpdateResult) -> str:
    """Confirmation after updating transaction fields."""
    amt = milliunits_to_dollars(result.amount_milliunits)
    lines = [
        f"Updated **${abs(amt):,.2f}** at **{result.payee_name}** ({result.date})\n",
    ]
    for change in result.changes:
        lines.append(f"- **{change.field_name}:** {change.old_value} → {change.new_value}")
    return "\n".join(lines)


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


# --- New API Feature Formatters ---


def format_payees(payees: list[Payee]) -> str:
    """Alphabetically sorted list of active payees."""
    active = [p for p in payees if not p.deleted]
    active.sort(key=lambda p: p.name.lower())
    if not active:
        return "No payees found."
    lines = [f"## Payees ({len(active)})\n"]
    for p in active:
        lines.append(f"- {p.name}")
    return "\n".join(lines)


def format_transaction_deleted(payee: str, amount_milliunits: int, txn_date: str) -> str:
    """Confirmation after deleting a transaction."""
    amt = milliunits_to_dollars(amount_milliunits)
    return (
        f"Deleted **${abs(amt):,.2f}** at **{payee}** ({txn_date})."
    )


def format_payee_updated(old_name: str, new_name: str) -> str:
    """Confirmation after renaming a payee."""
    return f"Renamed payee **{old_name}** → **{new_name}**."


def format_category_metadata_updated(
    name: str,
    old_name: str | None = None,
    new_name: str | None = None,
    old_note: str | None = None,
    new_note: str | None = None,
) -> str:
    """Confirmation after updating category name/note."""
    lines = [f"Updated category **{name}**:\n"]
    if new_name is not None:
        lines.append(f"- **Name:** {old_name or name} → {new_name}")
    if new_note is not None:
        old = old_note or "(none)"
        new = new_note or "(cleared)"
        lines.append(f"- **Note:** {old} → {new}")
    return "\n".join(lines)


_GOAL_TYPE_LABELS = {
    "TB": "Target Balance",
    "TBD": "Target Balance by Date",
    "MF": "Monthly Funding",
    "NEED": "Needed for Spending",
    "DEBT": "Debt Payment",
}


def format_category_targets(groups: list[CategoryGroup]) -> str:
    """List all categories that have a target/goal set, grouped by category group."""
    lines = ["## Category Targets\n"]
    total_target = 0.0
    total_underfunded = 0.0
    count = 0

    for group in groups:
        if group.hidden or group.deleted:
            continue
        if group.name in ("Internal Master Category", "Hidden Categories"):
            continue

        cats_with_targets = [
            c for c in group.categories
            if not c.hidden and not c.deleted and c.goal_type is not None
        ]
        if not cats_with_targets:
            continue

        lines.append(f"\n### {group.name}")
        for cat in cats_with_targets:
            count += 1
            goal_label = _GOAL_TYPE_LABELS.get(cat.goal_type or "", cat.goal_type or "")
            target_dollars = (
                milliunits_to_dollars(cat.goal_target) if cat.goal_target else 0.0
            )
            total_target += target_dollars
            underfunded = (
                milliunits_to_dollars(cat.goal_under_funded)
                if cat.goal_under_funded
                else 0.0
            )
            total_underfunded += underfunded
            pct = cat.goal_percentage_complete or 0

            parts = [f"  - **{cat.name}**: ${target_dollars:,.2f} ({goal_label})"]
            parts.append(f"— {pct}% funded")
            if underfunded > 0.005:
                parts.append(f"| ${underfunded:,.2f} underfunded")
            if cat.goal_target_date:
                parts.append(f"| by {cat.goal_target_date}")
            lines.append(" ".join(parts))

    if count == 0:
        return "No category targets/goals found."

    lines.append("\n---")
    lines.append(f"**{count} categories with targets**")
    lines.append(f"**Total target amount:** ${total_target:,.2f}")
    if total_underfunded > 0.005:
        lines.append(f"**Total underfunded:** ${total_underfunded:,.2f}")

    return "\n".join(lines)


def format_category_target_set(result: CategoryTargetResult) -> str:
    """Confirmation after setting or removing a category target."""
    if result.action == "removed":
        lines = [f"Target removed from **{result.category_name}**."]
        if result.old_target is not None:
            lines.append(f"- **Previous target:** ${result.old_target:,.2f}")
            if result.old_target_date:
                lines.append(f"- **Previous target date:** {result.old_target_date}")
        return "\n".join(lines)

    verb = "Target set" if result.action == "set" else "Target updated"
    lines = [f"{verb} for **{result.category_name}**:\n"]

    if result.old_target is not None:
        lines.append(f"- **Previous target:** ${result.old_target:,.2f}")
    if result.new_target is not None:
        lines.append(f"- **New target:** ${result.new_target:,.2f}")
    if result.new_target_date:
        lines.append(f"- **Target date:** {result.new_target_date}")
    if result.goal_type:
        lines.append(f"- **Goal type:** {result.goal_type}")
    if result.percentage_complete is not None:
        lines.append(f"- **Progress:** {result.percentage_complete}% complete")
    if result.under_funded is not None and result.under_funded > 0.005:
        lines.append(f"- **Under-funded:** ${result.under_funded:,.2f}")

    return "\n".join(lines)


def format_account_created(name: str, type_: str, balance: float) -> str:
    """Confirmation after creating a new account."""
    return (
        f"Account created!\n\n"
        f"- **Name:** {name}\n"
        f"- **Type:** {type_}\n"
        f"- **Balance:** ${balance:,.2f}"
    )


def format_import_result(transaction_ids: list[str]) -> str:
    """Summary after triggering a bank import."""
    count = len(transaction_ids)
    if count == 0:
        return "Import complete — no new transactions found."
    return f"Imported **{count}** new transaction{'s' if count != 1 else ''}."


def format_bulk_update_result(count: int, errors: list[str]) -> str:
    """Summary of a bulk transaction update."""
    lines = [f"Updated **{count}** transaction{'s' if count != 1 else ''}."]
    if errors:
        lines.append(f"\n**Errors ({len(errors)}):**")
        for err in errors:
            lines.append(f"- {err}")
    return "\n".join(lines)


def format_budget_settings(settings: BudgetSettings) -> str:
    """Display budget date and currency format settings."""
    cf = settings.currency_format
    return (
        f"## Budget Settings\n\n"
        f"- **Date format:** {settings.date_format.format}\n"
        f"- **Currency:** {cf.currency_symbol} ({cf.iso_code})\n"
        f"- **Example:** {cf.example_format}\n"
        f"- **Decimal digits:** {cf.decimal_digits}"
    )


def format_user(user: User) -> str:
    """Display the authenticated user."""
    return f"Authenticated as user `{user.id}`."


def format_payee_locations(
    locations: list[PayeeLocation],
    payees: list[Payee],
) -> str:
    """List payee locations with payee names."""
    active = [loc for loc in locations if not loc.deleted]
    if not active:
        return "No payee locations found."

    payee_map = {p.id: p.name for p in payees}
    lines = [f"## Payee Locations ({len(active)})\n"]
    for loc in active:
        name = payee_map.get(loc.payee_id, "Unknown")
        lines.append(f"- **{name}**: ({loc.latitude}, {loc.longitude})")
    return "\n".join(lines)


def format_scheduled_transactions(scheduled: list[ScheduledTransaction]) -> str:
    """List scheduled transactions sorted by next date."""
    active = [st for st in scheduled if not st.deleted]
    active.sort(key=lambda st: st.date_next)

    if not active:
        return "No scheduled transactions found."

    lines = [f"## Scheduled Transactions ({len(active)})\n"]
    for st in active:
        amt = milliunits_to_dollars(st.amount)
        direction = "IN" if amt > 0 else "OUT"
        freq = st.frequency.value
        lines.append(
            f"- {st.date_next} [{direction}] **${abs(amt):,.2f}** "
            f"| {st.payee_name or 'Unknown'} "
            f"| {st.category_name or 'Uncategorized'} "
            f"| {freq}"
        )
        if st.memo:
            lines.append(f"  _Memo: {st.memo}_")
    return "\n".join(lines)


def format_scheduled_transaction_created(
    st: ScheduledTransaction,
    account_name: str,
    category_name: str | None,
) -> str:
    """Confirmation after creating a scheduled transaction."""
    amt = milliunits_to_dollars(st.amount)
    lines = [
        "Scheduled transaction created!\n",
        f"- **Amount:** ${abs(amt):,.2f} {'inflow' if amt > 0 else 'outflow'}",
        f"- **Payee:** {st.payee_name or 'Unknown'}",
        f"- **Category:** {category_name or 'Uncategorized'}",
        f"- **Account:** {account_name}",
        f"- **First date:** {st.date_first}",
        f"- **Frequency:** {st.frequency.value}",
    ]
    if st.memo:
        lines.append(f"- **Memo:** {st.memo}")
    return "\n".join(lines)


def format_scheduled_transaction_updated(
    payee: str,
    changes: list[FieldChange],
) -> str:
    """Confirmation after updating a scheduled transaction."""
    lines = [f"Updated scheduled transaction for **{payee}**:\n"]
    for change in changes:
        lines.append(f"- **{change.field_name}:** {change.old_value} → {change.new_value}")
    return "\n".join(lines)


def format_scheduled_transaction_deleted(
    payee: str,
    amount_milliunits: int,
    date_next: str,
) -> str:
    """Confirmation after deleting a scheduled transaction."""
    amt = milliunits_to_dollars(amount_milliunits)
    return (
        f"Deleted scheduled transaction: **${abs(amt):,.2f}** "
        f"at **{payee}** (next: {date_next})."
    )

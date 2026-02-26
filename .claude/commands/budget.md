Interactive monthly budget planning. Walk through setting up next month's budget step by step — compare to previous month, identify new needs, review categories, and apply.

## Phase 0: Gather Data

Fetch all data upfront before presenting anything to the user:

1. `ynab_get_budget_summary` — current month category breakdowns (budgeted, spent, remaining per category).
2. `ynab_spending_trends` with `num_months: 3` — 3-month spending history with averages and anomaly detection.
3. `ynab_cover_overspending` — find overspent categories and suggested moves.
4. `ynab_credit_card_status` — credit card payment vs balance discrepancies.
5. `ynab_get_scheduled_transactions` — recurring/scheduled transactions for upcoming months.

Hold all of this data in memory for the rest of the workflow.

## Phase 1: Dashboard & Health Check

Present a concise snapshot of where things stand:

```
## Budget Planning for [Next Month YYYY]

### Current Month Snapshot ([Current Month])
- Total budgeted: $X,XXX.XX
- Total spent: $X,XXX.XX
- Ready to Be Assigned: $X,XXX.XX

### Health Flags
- [!!] N overspent categories totaling $XXX.XX
- [!!] Credit card "[Name]" underfunded by $XX.XX
- [!!] "[Category]" spending is XX% above 3-month average

### Scheduled Transactions Due Next Month
- $XXX.XX | [Payee] | [frequency] | [date]
- Total scheduled: $X,XXX.XX
```

If there are zero health flags, display a brief "Current month looks healthy!" and skip the question below.

If there are health flags, use `AskUserQuestion`:

**Question:** `"Before we plan next month, would you like to address current month issues first?"`

**Options:**
- `"Yes, fix overspending first"`
- `"No, let's plan next month"`
- `"Show me more detail on current month"`

### Phase 1b: Overspending Resolution (conditional)

Only entered if the user chose to fix overspending.

1. Display the overspent categories and suggested moves from `ynab_cover_overspending`.

2. Use `AskUserQuestion`:

   **Question:** `"Here are suggested moves to cover overspending. What would you like to do?"`

   **Options:**
   - `"Apply all suggested moves"`
   - `"Let me pick which moves to make"`
   - `"Skip — I'll handle it later"`

3. If "Apply all": Execute each suggested move via `ynab_move_money`. Summarize results.

4. If "Let me pick": For each suggested move, use `AskUserQuestion`:

   **Question:** `"Move $XX.XX from [Source] → [Overspent Category]?"`

   **Options:**
   - `"Yes, move it"`
   - `"Skip this one"`
   - `"Use a different source"` — ask follow-up for source category name via Other field

5. Execute approved moves via `ynab_move_money`. Summarize what was moved, then continue.

## Phase 2: New Needs for This Month

Before choosing a strategy, surface anything new or different about the upcoming month.

**Proactively display** (no question needed, just informational):
- Scheduled transactions due next month that were NOT due this month (new recurring bills starting)
- Annual or irregular-frequency scheduled transactions (yearly, quarterly, etc.) — call these out explicitly so the user budgets for them
- Categories with non-empty notes — these often contain savings targets or reminders (e.g., "save $200/mo for vacation"). Show the note text as context.

**Then use `AskUserQuestion`:**

**Question:** `"Any new or unusual expenses coming up in [Next Month]? (e.g., annual bills, planned purchases, trips, events)"`

**Options:**
- `"Yes, let me list them"`
- `"No, pretty standard month"`

If "Yes": For each new expense, use `AskUserQuestion`:

**Question:** `"What's the expense?"`

Let the user type in the Other field. Then ask:

**Question:** `"Which category should this go under, and how much?"`

**Options:** Suggest likely categories based on the description, plus Other for custom input. Capture the category name and dollar amount.

For each new need, note whether it's a new category (needs creating) or an increase to an existing one. These feed into the comparison table in Phase 3.

## Phase 3: Choose Strategy

Use `AskUserQuestion`:

**Question:** `"How would you like to seed next month's budget?"`

**Options:**
- `"Copy last month's budgeted amounts"` — uses `ynab_setup_budget` with strategy `"last_month_budget"`
- `"Base it on last month's actual spending"` — uses `ynab_setup_budget` with strategy `"last_month_actual"`
- `"Start from scratch (zero-based)"` — every category starts at $0, user assigns in Phase 5

Call `ynab_setup_budget` with `apply: false` (preview mode) using the chosen strategy. Overlay any new needs from Phase 2 onto the preview (increase proposed amounts for categories with new expenses).

## Phase 4: Comparison Table

Present the proposed budget alongside current month data:

```
## Proposed Budget for [Next Month YYYY]

| Category Group / Category | This Month Budget | This Month Spent | 3-Mo Avg | Proposed | Change |
|---------------------------|-------------------|------------------|----------|----------|--------|
| **Housing & Home**        |                   |                  |          |          |        |
|   Rent                    | $1,500.00         | $1,500.00        | $1,500   | $1,500   | --     |
|   Electric                | $120.00           | $145.00 [!!]     | $130     | $120.00  | --     |
| **Food**                  |                   |                  |          |          |        |
|   Groceries               | $600.00           | $720.00 [!!]     | $650     | $600.00  | --     |
|   Dining Out              | $200.00           | $340.00 [!!]     | $220     | $200.00  | --     |
|   New Tires               |                   |                  |          | $400.00  | [NEW]  |

**Total proposed:** $X,XXX.XX
**Ready to Be Assigned after:** $X,XXX.XX
```

**Formatting rules:**
- Group categories by their category group
- Mark categories where actual spending exceeded budget with `[!!]`
- Mark new needs from Phase 2 with `[NEW]`
- Show category notes inline when present (budget targets, reminders)
- Show the "Ready to Be Assigned" delta
- Skip categories with $0 budgeted AND $0 spent AND $0 proposed (noise reduction)
- Flag unbudgeted spending (categories with $0 budget but non-zero spend)

**Then use `AskUserQuestion`:**

**Question:** `"Here's the proposed budget. What would you like to do?"`

**Options:**
- `"Looks good — apply it!"`
- `"Review category by category"`
- `"Just review the flagged categories"`
- `"Adjust specific categories"` — user types category names in Other field

## Phase 5: Category-by-Category Review

Walk through categories that need attention. Group by category group for logical flow.

**For each category (or only flagged categories if user chose "just flagged"):**

Format the question based on the category's situation:

*Overspent/anomaly category:*
`"[Dining Out] Budget: $200 | Spent: $340 [!!] | 3-mo avg: $220\nThis category went $140 over budget. 3-month average suggests $220. What should we budget next month?"`

*Normal category:*
`"[Groceries] Budget: $600 | Spent: $720 | 3-mo avg: $650\nWhat should we budget next month?"`

*Zero-budget category with spending:*
`"[Coffee Shops] Budget: $0 | Spent: $45 | 3-mo avg: $38\nThis category has no budget but regular spending. Want to add one?"`

*Category with a note:*
Include the note text as context: `Note: "Save $200/mo for vacation"`

**Options (dynamic based on context):**
- `"Keep at $[current budget]"`
- `"Set to 3-month average ($[avg])"`
- `"Match last month's spending ($[actual])"`
- `"Set to $0 (skip this month)"`

The user can type a custom dollar amount in the Other field.

**After every 10 categories**, check in:

**Question:** `"Reviewed [N] categories. [M] remaining. Ready to Be Assigned: $X,XXX.XX. Continue?"`

**Options:**
- `"Continue reviewing"`
- `"Accept defaults for the rest"`
- `"Show me just the remaining flagged ones"`

### Phase 5b: Ready to Be Assigned Reconciliation

After all category adjustments, check the RTA balance.

**If over-allocated (negative RTA):**

**Question:** `"Your proposed budget is $[X] over what's available (Ready to Be Assigned: -$[Y]). What would you like to do?"`

**Options:**
- `"Show categories with the most surplus"` — display top 5 categories by proposed minus 3-month average gap, let user trim
- `"Reduce proportionally across all categories"`
- `"I'll add income before the month starts"` — accept the over-allocation
- `"Let me pick categories to reduce"` — free-form via Other

**If significantly under-allocated (positive RTA > $50):**

**Question:** `"You have $[X] unassigned after this budget. Would you like to allocate it?"`

**Options:**
- `"Add to savings/emergency fund"` — ask which savings category
- `"Spread across underfunded categories"` — identify categories where proposed < 3-month average
- `"Leave unassigned for now"`
- `"Add to a specific category"` — user types category name in Other

**If balanced (RTA within $50):** Skip this step entirely.

## Phase 6: Final Confirmation

Show the complete final budget with all adjustments incorporated:

```
## Final Budget for [Next Month YYYY]

[Same table format as Phase 4, with updated Proposed column]

**Total budgeted:** $X,XXX.XX
**Ready to Be Assigned:** $XX.XX
**Categories changed from default:** [N]
```

**Use `AskUserQuestion`:**

**Question:** `"Ready to apply this budget for [Next Month]?"`

**Options:**
- `"Apply it!"`
- `"Go back and adjust more"`
- `"Save as preview only (don't apply)"`

## Phase 7: Apply Budget

**If user accepted the default strategy with no individual changes:**
- Call `ynab_setup_budget` with the chosen strategy and `apply: true`.

**If user made individual category adjustments:**
- Call `ynab_setup_budget` with the chosen strategy and `apply: true` to set the baseline for all categories.
- Then for each category the user customized to a different amount, use `ynab_move_money` with the `month` parameter set to the target month (e.g., `2026-03-01`) to redistribute money between categories. Compute the delta between the baseline and the desired amount, and move from/to categories accordingly.
- For new categories that need creating (from Phase 2), use browser automation to create them first (see "Creating Categories via Browser" below), then apply the budget.

**If user chose "Save as preview only":** Print a summary of all proposed amounts the user can reference later. Do not apply anything.

After applying, confirm success.

## Phase 8: Wrap-Up

Present a final summary:

```
## Budget Applied for [Next Month YYYY]

- Total budgeted: $X,XXX.XX
- Categories assigned: [N]
- Categories changed from default: [M]
- Ready to Be Assigned: $XX.XX

### Key Changes from This Month
- Dining Out: $200 → $250 (+$50, based on 3-month average)
- Groceries: $600 → $650 (+$50, based on 3-month average)
- New Tires: $0 → $400 [NEW]

### Reminders
- [If overspending deferred] N categories still overspent this month
- [If CC underfunded] [Card Name] payment category needs $XX.XX more
- [If scheduled > budgeted] $X,XXX in scheduled transactions vs $Y,YYY budgeted
```

## Behavioral Notes

- Be conversational but efficient — budget planning is a task the user wants to complete, not linger on.
- Present one question at a time via `AskUserQuestion`. Never batch multiple decisions.
- Never apply budget changes without explicit user confirmation.
- Format all dollar amounts as `$X,XXX.XX` with two decimal places.
- Use `[!!]` markers for attention items and `[NEW]` for new needs — not emoji.
- Always show the running "Ready to Be Assigned" total after changes so the user knows their allocation status.
- If the user says "just do what I did last month" at any point, treat as "Copy last month's budgeted amounts" + "Apply it" — skip review.
- If there are more than 20 non-zero categories, warn the user when they choose "review category by category" and suggest "just review flagged" instead.
- Skip Credit Card Payment categories in the review — YNAB auto-manages these. Explain why if the user asks.
- Track all actions taken (categories adjusted, amounts changed, moves made) for the wrap-up summary.
- For the target month, compute correctly: if today is in month M, next month is M+1. Handle December → January year rollover. Format as `YYYY-MM-01`.

## Edge Cases

### First of the Month
When running on the 1st, current month spending is near zero. Use **last** month as the spending reference. Present last month's complete picture and budget for the current month (which just started).

### Next Month Already Has Assignments
If the target month already has budget assignments, detect this and ask:

**Question:** `"[Next Month] already has $X,XXX.XX budgeted across [N] categories. What would you like to do?"`

**Options:**
- `"Start fresh (replace all)"`
- `"Review and adjust what's there"`
- `"Actually, adjust the current month instead"`

### Zero-Budget Categories with Recurring Spending
Flag these prominently in the comparison table — they are budget leaks. The 3-month average from spending trends makes this detection automatic.

### Seasonal/Irregular Expenses
When a category has spending in some months but not others (e.g., $0 in 2 of 3 months, then $200), note: "This category has irregular spending — consider a savings target instead of monthly budgeting."

### Internal and Hidden Categories
Always filter out `"Internal Master Category"` and `"Hidden Categories"` groups and skip hidden/deleted categories — consistent with existing codebase conventions.

## Creating Categories via Browser

When a new expense from Phase 2 needs a category that doesn't exist, use Chrome browser automation (`mcp__claude-in-chrome__*`):

1. Navigate to `app.ynab.com` (reuse existing tab if open).
2. Click the **Budget** tab in the left sidebar.
3. Find the appropriate category group. If unsure, ask the user via `AskUserQuestion`.
4. Click the group header, then the **"+"** button to add a new category.
5. Type the category name and confirm.
6. Wait for YNAB to save.
7. Return to the budget flow and apply the assignment.

Only fall back to asking the user to manually create categories if browser automation fails after 2 attempts.

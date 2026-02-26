Run a daily budget review for the user. Walk through every recent transaction one at a time and help categorize, recategorize, memo, flag, or delete them.

## Phase 1: Gather Data

1. Fetch any uncategorized transactions using `ynab_uncategorized`.

2. Fetch unapproved transactions using `ynab_get_transactions` with `since_date` set to the **1st of the current month** and `limit` of 100. Filter the results to only unapproved transactions.

3. Fetch the current budget summary using `ynab_get_budget_summary`.

## Phase 2: Summary

4. Present a brief summary to the user:
   - How many uncategorized transactions need attention
   - How many unapproved (but categorized) transactions remain
   - Any overspent categories from the budget summary
   - Keep it concise — a few lines, not a wall of text
   - If there are zero uncategorized and zero unapproved transactions, say "Nothing to review — all transactions are categorized and approved!" and exit.

## Phase 3: Review Uncategorized Transactions First

5. If there are uncategorized transactions, review them first. For **each** uncategorized transaction, use the `AskUserQuestion` tool to present it. Format the question like:

   **Question:** `"📋 [date] | $XX.XX | [payee] | [account] | memo: [memo or 'none']\nThis transaction is uncategorized. What would you like to do?"`

   **Options:**
   - `"Categorize as [best guess category]"` — make a smart guess from the payee name (e.g., HEB → Groceries, Shell → Gas, Netflix → Subscriptions). Only include this option if you can make a reasonable guess.
   - `"Add memo first"` — user wants to add a memo before categorizing
   - `"Delete this transaction"`
   - `"Skip"`

   The user can also type a custom category in the "Other" field that AskUserQuestion automatically provides.

6. Based on the user's response:
   - **Suggested category chosen:** Use `ynab_categorize_transaction` with the payee name as `transaction_description` and the chosen category name. The tool auto-approves the transaction.
   - **Custom category typed in Other:** Use `ynab_categorize_transaction` with their specified category. The tool auto-approves.
   - **Category doesn't exist:** If `ynab_categorize_transaction` fails because the category doesn't exist, automatically create it using browser automation (see "Creating Categories via Browser" below), then retry the categorization.
   - **Add memo:** Ask a follow-up `AskUserQuestion` for the memo text, then note it (memo updates require the API — inform user if not possible and move on). Then ask about categorization.
   - **Delete:** Use browser automation to delete via the YNAB web app at app.ynab.com, or inform the user they need to delete it manually if browser automation is unavailable.
   - **Skip:** Move to the next transaction.

## Phase 4: Review Unapproved Categorized Transactions

7. For **each** unapproved but already-categorized transaction, use `AskUserQuestion`:

   **Question:** `"📋 [date] | $XX.XX | [payee] | [category] | [account] | memo: [memo or 'none']\nThis transaction is categorized but unapproved. Is it correct?"`

   **Options:**
   - `"Looks good ✓"`
   - `"Recategorize"`
   - `"Add/edit memo"`
   - `"Flag for review"`
   - `"Delete"`
   - `"Skip remaining transactions"`

8. Based on the user's response:
   - **Looks good:** Approve the transaction if it's unapproved (use `ynab_update_transaction` with `approved: true`). Move to the next.
   - **Recategorize:** Ask a follow-up `AskUserQuestion`: "What category should this be?" with common categories as options (Groceries, Dining Out, Gas, etc.) plus the Other field for custom input. Then use `ynab_recategorize_transaction` (auto-approves). If the category doesn't exist, create it via browser automation (see "Creating Categories via Browser") and retry.
   - **Add/edit memo:** Ask a follow-up for the memo text. Note if memo updates aren't supported via the current tools.
   - **Flag for review:** Note it in a running list to show in the wrap-up summary.
   - **Delete:** Same as Phase 3 — browser automation or manual.
   - **Skip remaining:** Exit the review loop immediately and go to Phase 5.

## Phase 4b: Bulk Approve Remaining Transactions

9. After completing the individual transaction review, check if any unapproved transactions remain from the list that were skipped or not yet addressed in Phases 3–4.

10. If there are unapproved transactions remaining, present a summary using `AskUserQuestion`:

    **Question:** `"You have [N] unapproved transaction(s) remaining:\n[brief list: date | $amount | payee | category]\n\nWould you like to approve them all?"`

    **Options:**
    - `"Approve all"` — bulk approve every remaining unapproved transaction
    - `"Review individually"` — go back through them one at a time (same as Phase 4 flow)
    - `"Leave unapproved"` — skip approval, they'll stay pending in YNAB

11. Based on the user's response:
    - **Approve all:** Use `ynab_bulk_update_transactions` with an update entry for each unapproved transaction, setting `approved: true`. Use the format `[payee] [date] [$amount]` for `transaction_description` to ensure unique matching. If there are more than 50 unapproved transactions, batch into groups of 50.
    - **Review individually:** Loop through unapproved transactions one at a time using the same Phase 4 flow.
    - **Leave unapproved:** Move directly to the wrap-up phase.

12. Track the count of bulk-approved transactions for the wrap-up summary.

## Phase 5: Wrap-Up

13. Present a final summary:
    - How many transactions were reviewed
    - How many were categorized or recategorized
    - How many were approved
    - How many were flagged for later review (list them)
    - How many were skipped
    - Any overspent categories that need attention — suggest running `ynab_cover_overspending` if applicable

## Behavioral Notes

- Be conversational but concise — this is a daily check-in, not an audit.
- **Approval is part of the review.** Every transaction the user reviews should be approved when done. `ynab_categorize_transaction` and `ynab_recategorize_transaction` auto-approve. For "Looks good" responses on already-categorized transactions, explicitly approve unapproved ones via `ynab_update_transaction`.
- Start with debit/checking account transactions first, then credit card transactions. This helps identify CC payment sources before encountering their matching inflows.
- If there are more than 15 transactions to review, group them by account and ask the user after each group if they want to continue.
- Format all dollar amounts as `$X.XX` with two decimal places.
- For payee-based category suggestions, use common sense (grocery stores → Groceries, gas stations → Gas/Fuel, restaurants → Dining Out, streaming services → Subscriptions, etc.). If unsure, don't suggest — let the user type it.
- Present one transaction at a time. Never batch multiple transactions into a single AskUserQuestion.
- Track all actions taken (categorized, recategorized, approved, flagged, deleted, skipped) for the wrap-up summary.
- Each subscription/service should have its own category (e.g., "Grammarly", "Netflix") — not a generic "Subscriptions" bucket.
- Kids activities categories should be prefixed with child's name (e.g., "Adhvaith Music Lessons").
- **CC payment transfers** (payee = `Transfer : [CC Account Name]`) that show as uncategorized are already proper YNAB transfers — YNAB auto-assigns the `Credit Card Payments` category. Do NOT try to convert them. Just approve them: select the transaction in the browser and click Approve (or press A). Skip asking the user about these entirely.
- **Delta cache fallback:** If `ynab_update_transaction`, `ynab_categorize_transaction`, or `ynab_bulk_update_transactions` returns "No transaction found", the MCP server's delta cache is stale. Fall back to browser automation: navigate to the relevant account in YNAB, select the transaction, and use the Approve/Categorize buttons directly in the web UI.
- Tracking account starting balances don't need categories — they're off-budget by design.

## Creating Categories via Browser

When a user requests a category that doesn't exist in YNAB, use the Chrome browser automation tools (`mcp__claude-in-chrome__*`) to create it automatically:

1. Navigate to `app.ynab.com` (use an existing tab if already open, otherwise create a new one).
2. Click the **Budget** tab in the left sidebar to ensure you're on the budget view.
3. Find the appropriate category group (e.g., "Housing & Home", "Food", "Transportation"). If unsure which group, ask the user via `AskUserQuestion`.
4. Click the category group header to expand it, then click the **"+"** button or right-click to add a new category.
5. Type the new category name and confirm.
6. Wait for YNAB to save (the category should appear in the list).
7. Return to the review flow and retry `ynab_categorize_transaction` with the newly created category.

Do **not** ask the user to manually create categories — always attempt browser automation first. Only fall back to asking the user if browser automation fails after 2 attempts.

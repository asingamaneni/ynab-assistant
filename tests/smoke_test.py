"""Quick smoke test against the live YNAB API.

Run: python -m tests.smoke_test
Requires YNAB_API_TOKEN in .env
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from src.core.ynab_client import YNABClient, YNABError
from src.core.categorizer import Categorizer
from src.core.resolvers import resolve_account, resolve_category
from src.models.schemas import milliunits_to_dollars


async def main():
    token = os.environ.get("YNAB_API_TOKEN", "")
    if not token:
        print("YNAB_API_TOKEN not set in .env")
        sys.exit(1)

    budget_id = os.environ.get("YNAB_BUDGET_ID", "default")
    client = YNABClient(api_token=token, budget_id=budget_id)

    try:
        # 1. Budgets — also resolves "default" to an actual ID
        print("1. Fetching budgets...")
        budgets = await client.get_budgets()
        for b in budgets:
            print(f"   - {b.name} (ID: {b.id})")

        if budget_id == "default" and budgets:
            client.budget_id = budgets[0].id
            print(f"   Resolved 'default' -> {budgets[0].name} ({budgets[0].id})")

        # 2. Accounts
        print("\n2. Fetching accounts...")
        accounts = await client.get_accounts()
        print(f"   Found {len(accounts)} accounts total")
        open_accounts = [a for a in accounts if not a.closed]
        print(f"   {len(open_accounts)} open accounts")
        for a in open_accounts:
            print(f"   - {a.name} ({a.type.value}, on_budget={a.on_budget}): ${milliunits_to_dollars(a.balance):,.2f}")

        # 3. Test resolver
        print("\n3. Testing account resolver (default)...")
        if open_accounts:
            default = resolve_account(accounts)
            print(f"   Default account: {default.name}")
        else:
            print("   Skipped — no open accounts")

        # 4. Categories
        print("\n4. Fetching categories...")
        groups = await client.get_categories()
        cat_count = sum(len(g.categories) for g in groups)
        print(f"   {len(groups)} groups, {cat_count} categories")

        # 5. Recent transactions
        print("\n5. Fetching recent transactions...")
        transactions = await client.get_transactions()
        recent = sorted(
            [t for t in transactions if not t.deleted],
            key=lambda t: t.date,
            reverse=True,
        )[:5]
        for t in recent:
            amt = milliunits_to_dollars(t.amount)
            print(f"   - {t.date} | ${abs(amt):,.2f} | {t.payee_name or 'Unknown'} | {t.category_name or 'Uncategorized'}")

        # 6. Categorizer learning
        print("\n6. Testing categorizer...")
        categorizer = Categorizer()
        txn_dicts = [
            {"payee_name": t.payee_name, "category_id": t.category_id, "category_name": t.category_name}
            for t in transactions if t.payee_name and t.category_id and not t.deleted
        ]
        categorizer.learn_from_transactions(txn_dicts)
        mappings = categorizer.get_all_mappings()
        print(f"   Learned {len(mappings)} payee mappings")
        for k, v in list(mappings.items())[:3]:
            print(f"   - {k.title()} -> {v['category_name']}")

        print("\nAll checks passed!")

    except YNABError as e:
        print(f"\nYNAB API error: {e.detail}")
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

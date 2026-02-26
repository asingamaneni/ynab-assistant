"""YNAB API client wrapper.

Async HTTP client for the YNAB REST API (https://api.ynab.com/v1).
Handles authentication, error handling, delta requests, and rate limiting.
"""

import json
from typing import Any, Optional

import httpx

from src.models.schemas import (
    Account,
    Budget,
    BudgetSettings,
    Category,
    CategoryGroup,
    CreateTransactionInput,
    MonthSummary,
    Payee,
    PayeeLocation,
    ScheduledTransaction,
    Transaction,
    UpdateCategoryInput,
    User,
)

BASE_URL = "https://api.ynab.com/v1"
DEFAULT_TIMEOUT = 30.0


class YNABError(Exception):
    """Base exception for YNAB API errors."""

    def __init__(self, status_code: int, error_id: str, name: str, detail: str):
        self.status_code = status_code
        self.error_id = error_id
        self.name = name
        self.detail = detail
        super().__init__(f"YNAB API Error [{status_code}] {name}: {detail}")


class YNABClient:
    """Async client for the YNAB API."""

    def __init__(self, api_token: str, budget_id: str = "default"):
        self.api_token = api_token
        self.budget_id = budget_id
        self._client: Optional[httpx.AsyncClient] = None
        self._server_knowledge: dict[str, int] = {}
        self._delta_cache: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=DEFAULT_TIMEOUT,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _merge_delta(
        self, path: str, items: list[dict[str, Any]],
        id_field: str = "id",
    ) -> list[dict[str, Any]]:
        """Merge delta response items into the cache and return the full list.

        Each item is keyed by *id_field* (default ``"id"``).  Items with
        ``"deleted": True`` are removed from the cache.  All other items
        are upserted by their key.
        """
        if path not in self._delta_cache:
            self._delta_cache[path] = {}

        cache = self._delta_cache[path]

        for item in items:
            item_id = item.get(id_field)
            if not item_id:
                continue
            if item.get("deleted", False):
                cache.pop(item_id, None)
            else:
                cache[item_id] = item

        return list(cache.values())

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        use_delta: bool = False,
        delta_key: str | None = None,
        delta_id_field: str = "id",
    ) -> dict[str, Any]:
        """Make an authenticated request to the YNAB API.

        When *use_delta* is ``True`` and *delta_key* names the list field in
        the response (e.g. ``"accounts"``), the client merges incremental
        results into a local cache so callers always receive the full list.
        """
        if params is None:
            params = {}

        if use_delta and path in self._server_knowledge:
            params["last_knowledge_of_server"] = self._server_knowledge[path]

        try:
            response = await self.client.request(
                method=method,
                url=path,
                params=params,
                json=json_data,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = e.response.json() if e.response.content else {}
            error = body.get("error", {})
            raise YNABError(
                status_code=e.response.status_code,
                error_id=error.get("id", str(e.response.status_code)),
                name=error.get("name", "unknown_error"),
                detail=error.get("detail", str(e)),
            ) from e
        except httpx.TimeoutException as e:
            raise YNABError(
                status_code=408,
                error_id="timeout",
                name="request_timeout",
                detail="Request to YNAB API timed out. Please try again.",
            ) from e

        data = response.json().get("data", {})

        if use_delta and "server_knowledge" in data:
            self._server_knowledge[path] = data["server_knowledge"]

        if use_delta and delta_key and delta_key in data:
            data[delta_key] = self._merge_delta(
                path, data[delta_key], id_field=delta_id_field,
            )

        return data

    # --- Budgets ---

    async def get_budgets(self) -> list[Budget]:
        """Get all budgets for the authenticated user."""
        data = await self._request("GET", "/budgets")
        return [Budget(**b) for b in data.get("budgets", [])]

    async def get_budget(self, budget_id: Optional[str] = None) -> Budget:
        """Get a specific budget."""
        bid = budget_id or self.budget_id
        data = await self._request("GET", f"/budgets/{bid}")
        return Budget(**data.get("budget", {}))

    # --- Accounts ---

    async def get_accounts(self, budget_id: Optional[str] = None) -> list[Account]:
        """Get all accounts for a budget."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/accounts", use_delta=True, delta_key="accounts"
        )
        return [Account(**a) for a in data.get("accounts", [])]

    async def get_account(
        self, account_id: str, budget_id: Optional[str] = None
    ) -> Account:
        """Get a specific account."""
        bid = budget_id or self.budget_id
        data = await self._request("GET", f"/budgets/{bid}/accounts/{account_id}")
        return Account(**data.get("account", {}))

    async def create_account(
        self,
        name: str,
        type_: str,
        balance: int,  # milliunits
        budget_id: str | None = None,
    ) -> Account:
        """Create a new account."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "POST",
            f"/budgets/{bid}/accounts",
            json_data={"account": {"name": name, "type": type_, "balance": balance}},
        )
        return Account(**data.get("account", {}))

    # --- Categories ---

    async def get_categories(
        self, budget_id: Optional[str] = None
    ) -> list[CategoryGroup]:
        """Get all category groups and their categories."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/categories"
        )
        return [CategoryGroup(**cg) for cg in data.get("category_groups", [])]

    async def get_category(
        self, category_id: str, budget_id: Optional[str] = None
    ) -> Category:
        """Get a specific category."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/categories/{category_id}"
        )
        return Category(**data.get("category", {}))

    async def update_category(
        self,
        category_id: str,
        month: str,
        input_data: UpdateCategoryInput,
        budget_id: Optional[str] = None,
    ) -> Category:
        """Update a category's budgeted amount for a specific month."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "PATCH",
            f"/budgets/{bid}/months/{month}/categories/{category_id}",
            json_data={"category": input_data.model_dump(exclude_none=True)},
        )
        return Category(**data.get("category", {}))

    async def update_category_metadata(
        self,
        category_id: str,
        updates: dict[str, Any],
        budget_id: str | None = None,
    ) -> Category:
        """Update a category's name and/or note."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "PATCH",
            f"/budgets/{bid}/categories/{category_id}",
            json_data={"category": updates},
        )
        return Category(**data.get("category", {}))

    # --- Transactions ---

    async def get_transactions(
        self,
        budget_id: Optional[str] = None,
        since_date: Optional[str] = None,
        account_id: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> list[Transaction]:
        """Get transactions, optionally filtered."""
        bid = budget_id or self.budget_id
        params: dict[str, Any] = {}
        if since_date:
            params["since_date"] = since_date

        if account_id:
            path = f"/budgets/{bid}/accounts/{account_id}/transactions"
        elif category_id:
            path = f"/budgets/{bid}/categories/{category_id}/transactions"
        else:
            path = f"/budgets/{bid}/transactions"

        has_filter = since_date or account_id or category_id
        data = await self._request(
            "GET",
            path,
            params=params,
            use_delta=not has_filter,
            delta_key="transactions" if not has_filter else None,
        )
        return [Transaction(**t) for t in data.get("transactions", [])]

    async def get_transaction(
        self, transaction_id: str, budget_id: Optional[str] = None
    ) -> Transaction:
        """Get a specific transaction."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/transactions/{transaction_id}"
        )
        return Transaction(**data.get("transaction", {}))

    async def create_transaction(
        self,
        input_data: CreateTransactionInput,
        budget_id: Optional[str] = None,
    ) -> Transaction:
        """Create a new transaction."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "POST",
            f"/budgets/{bid}/transactions",
            json_data={"transaction": input_data.model_dump(exclude_none=True)},
        )
        return Transaction(**data.get("transaction", {}))

    async def delete_transaction(
        self,
        transaction_id: str,
        budget_id: str | None = None,
    ) -> None:
        """Delete a transaction."""
        bid = budget_id or self.budget_id
        await self._request(
            "DELETE", f"/budgets/{bid}/transactions/{transaction_id}"
        )
        # Evict from delta cache so subsequent reads don't serve stale data
        path = f"/budgets/{bid}/transactions"
        if path in self._delta_cache:
            self._delta_cache[path].pop(transaction_id, None)

    async def update_transaction(
        self,
        transaction_id: str,
        updates: dict[str, Any],
        budget_id: Optional[str] = None,
    ) -> Transaction:
        """Update an existing transaction."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "PATCH",
            f"/budgets/{bid}/transactions/{transaction_id}",
            json_data={"transaction": updates},
        )
        return Transaction(**data.get("transaction", {}))

    async def import_transactions(
        self,
        budget_id: str | None = None,
    ) -> list[str]:
        """Trigger linked account import. Returns imported transaction IDs."""
        bid = budget_id or self.budget_id
        data = await self._request("POST", f"/budgets/{bid}/transactions/import")
        return data.get("transaction_ids", [])

    async def bulk_update_transactions(
        self,
        transactions: list[dict[str, Any]],
        budget_id: str | None = None,
    ) -> list[Transaction]:
        """Update multiple transactions at once."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "PATCH",
            f"/budgets/{bid}/transactions",
            json_data={"transactions": transactions},
        )
        return [Transaction(**t) for t in data.get("transactions", [])]

    # --- Payees ---

    async def get_payees(self, budget_id: Optional[str] = None) -> list[Payee]:
        """Get all payees."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/payees", use_delta=True, delta_key="payees"
        )
        return [Payee(**p) for p in data.get("payees", [])]

    async def update_payee(
        self,
        payee_id: str,
        name: str,
        budget_id: str | None = None,
    ) -> Payee:
        """Update a payee's name."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "PATCH",
            f"/budgets/{bid}/payees/{payee_id}",
            json_data={"payee": {"name": name}},
        )
        return Payee(**data.get("payee", {}))

    async def get_payee_transactions(
        self,
        payee_id: str,
        since_date: str | None = None,
        budget_id: str | None = None,
    ) -> list[Transaction]:
        """Get transactions for a specific payee."""
        bid = budget_id or self.budget_id
        params: dict[str, Any] = {}
        if since_date:
            params["since_date"] = since_date
        data = await self._request(
            "GET", f"/budgets/{bid}/payees/{payee_id}/transactions", params=params
        )
        return [Transaction(**t) for t in data.get("transactions", [])]

    async def get_payee_locations(
        self,
        budget_id: str | None = None,
    ) -> list[PayeeLocation]:
        """Get all payee locations."""
        bid = budget_id or self.budget_id
        data = await self._request("GET", f"/budgets/{bid}/payee_locations")
        return [PayeeLocation(**pl) for pl in data.get("payee_locations", [])]

    # --- Month Summaries ---

    async def get_months(self, budget_id: Optional[str] = None) -> list[MonthSummary]:
        """Get budget month summaries."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/months",
            use_delta=True, delta_key="months", delta_id_field="month",
        )
        return [MonthSummary(**m) for m in data.get("months", [])]

    async def get_month(
        self, month: str, budget_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Get a specific month's detail including categories."""
        bid = budget_id or self.budget_id
        data = await self._request("GET", f"/budgets/{bid}/months/{month}")
        return data.get("month", {})

    async def get_budget_settings(
        self,
        budget_id: str | None = None,
    ) -> BudgetSettings:
        """Get budget settings (date format, currency format)."""
        bid = budget_id or self.budget_id
        data = await self._request("GET", f"/budgets/{bid}/settings")
        return BudgetSettings(**data.get("settings", {}))

    # --- User ---

    async def get_user(self) -> User:
        """Get the authenticated user."""
        data = await self._request("GET", "/user")
        return User(**data.get("user", {}))

    # --- Scheduled Transactions ---

    async def get_scheduled_transactions(
        self,
        budget_id: str | None = None,
    ) -> list[ScheduledTransaction]:
        """Get all scheduled transactions."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/scheduled_transactions"
        )
        return [
            ScheduledTransaction(**st)
            for st in data.get("scheduled_transactions", [])
        ]

    async def get_scheduled_transaction(
        self,
        scheduled_transaction_id: str,
        budget_id: str | None = None,
    ) -> ScheduledTransaction:
        """Get a specific scheduled transaction."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET",
            f"/budgets/{bid}/scheduled_transactions/{scheduled_transaction_id}",
        )
        return ScheduledTransaction(**data.get("scheduled_transaction", {}))

    async def create_scheduled_transaction(
        self,
        payload: dict[str, Any],
        budget_id: str | None = None,
    ) -> ScheduledTransaction:
        """Create a new scheduled transaction."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "POST",
            f"/budgets/{bid}/scheduled_transactions",
            json_data={"scheduled_transaction": payload},
        )
        return ScheduledTransaction(**data.get("scheduled_transaction", {}))

    async def update_scheduled_transaction(
        self,
        scheduled_transaction_id: str,
        payload: dict[str, Any],
        budget_id: str | None = None,
    ) -> ScheduledTransaction:
        """Update a scheduled transaction."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "PUT",
            f"/budgets/{bid}/scheduled_transactions/{scheduled_transaction_id}",
            json_data={"scheduled_transaction": payload},
        )
        return ScheduledTransaction(**data.get("scheduled_transaction", {}))

    async def delete_scheduled_transaction(
        self,
        scheduled_transaction_id: str,
        budget_id: str | None = None,
    ) -> None:
        """Delete a scheduled transaction."""
        bid = budget_id or self.budget_id
        await self._request(
            "DELETE",
            f"/budgets/{bid}/scheduled_transactions/{scheduled_transaction_id}",
        )

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
    Category,
    CategoryGroup,
    CreateTransactionInput,
    MonthSummary,
    Payee,
    Transaction,
    UpdateCategoryInput,
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
        self, path: str, key: str, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge delta response items into the cache and return the full list.

        Each item must have an ``"id"`` field.  Items with ``"deleted": True``
        are removed from the cache.  All other items are upserted by id.
        """
        if path not in self._delta_cache:
            self._delta_cache[path] = {}

        cache = self._delta_cache[path]

        for item in items:
            item_id = item.get("id")
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

        if "server_knowledge" in data:
            self._server_knowledge[path] = data["server_knowledge"]

        if use_delta and delta_key and delta_key in data:
            data[delta_key] = self._merge_delta(path, delta_key, data[delta_key])

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

        data = await self._request(
            "GET", path, params=params, use_delta=True, delta_key="transactions"
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
        budget_id: Optional[str] = None,
    ) -> None:
        """Delete a transaction."""
        bid = budget_id or self.budget_id
        await self._request(
            "DELETE", f"/budgets/{bid}/transactions/{transaction_id}"
        )

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

    # --- Payees ---

    async def get_payees(self, budget_id: Optional[str] = None) -> list[Payee]:
        """Get all payees."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/payees", use_delta=True, delta_key="payees"
        )
        return [Payee(**p) for p in data.get("payees", [])]

    # --- Month Summaries ---

    async def get_months(self, budget_id: Optional[str] = None) -> list[MonthSummary]:
        """Get budget month summaries."""
        bid = budget_id or self.budget_id
        data = await self._request(
            "GET", f"/budgets/{bid}/months", use_delta=True, delta_key="months"
        )
        return [MonthSummary(**m) for m in data.get("months", [])]

    async def get_month(
        self, month: str, budget_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Get a specific month's detail including categories."""
        bid = budget_id or self.budget_id
        data = await self._request("GET", f"/budgets/{bid}/months/{month}")
        return data.get("month", {})

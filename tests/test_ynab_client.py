"""Tests for the YNAB API client using httpx.MockTransport."""

import pytest
import httpx

from src.core.ynab_client import YNABClient, YNABError
from src.models.schemas import CreateTransactionInput


@pytest.fixture
def mock_client():
    """Factory that creates a YNABClient with a mocked transport."""
    async def _make(handler):
        client = YNABClient(api_token="test-token", budget_id="test-budget")
        transport = httpx.MockTransport(handler)
        client._client = httpx.AsyncClient(
            transport=transport,
            base_url="https://api.ynab.com/v1",
            headers={"Authorization": "Bearer test-token"},
            timeout=30.0,
        )
        return client
    return _make


class TestGetAccounts:
    async def test_returns_parsed_accounts(self, mock_client):
        def handler(request):
            return httpx.Response(200, json={
                "data": {
                    "accounts": [{
                        "id": "a1",
                        "name": "Checking",
                        "type": "checking",
                        "on_budget": True,
                        "closed": False,
                        "balance": 500000,
                        "cleared_balance": 500000,
                        "uncleared_balance": 0,
                    }],
                    "server_knowledge": 1,
                },
            })

        client = await mock_client(handler)
        accounts = await client.get_accounts()
        assert len(accounts) == 1
        assert accounts[0].name == "Checking"
        assert accounts[0].balance == 500000

    async def test_api_error_raises_ynab_error(self, mock_client):
        def handler(request):
            return httpx.Response(401, json={
                "error": {
                    "id": "401",
                    "name": "unauthorized",
                    "detail": "Bad token",
                },
            })

        client = await mock_client(handler)
        with pytest.raises(YNABError) as exc_info:
            await client.get_accounts()
        assert exc_info.value.status_code == 401
        assert "Bad token" in exc_info.value.detail


class TestGetCategories:
    async def test_returns_parsed_category_groups(self, mock_client):
        def handler(request):
            return httpx.Response(200, json={
                "data": {
                    "category_groups": [{
                        "id": "grp1",
                        "name": "Monthly Bills",
                        "hidden": False,
                        "deleted": False,
                        "categories": [{
                            "id": "cat1",
                            "category_group_id": "grp1",
                            "name": "Rent",
                            "budgeted": 1500000,
                            "activity": -1500000,
                            "balance": 0,
                        }],
                    }],
                    "server_knowledge": 5,
                },
            })

        client = await mock_client(handler)
        groups = await client.get_categories()
        assert len(groups) == 1
        assert groups[0].name == "Monthly Bills"
        assert groups[0].categories[0].name == "Rent"


class TestCreateTransaction:
    async def test_creates_and_returns_transaction(self, mock_client):
        def handler(request):
            return httpx.Response(201, json={
                "data": {
                    "transaction": {
                        "id": "t1",
                        "date": "2025-01-15",
                        "amount": -45000,
                        "account_id": "a1",
                        "cleared": "uncleared",
                        "approved": True,
                        "deleted": False,
                        "subtransactions": [],
                    },
                },
            })

        client = await mock_client(handler)
        result = await client.create_transaction(
            CreateTransactionInput(
                account_id="a1",
                date="2025-01-15",
                amount=-45000,
                payee_name="HEB",
            )
        )
        assert result.id == "t1"
        assert result.amount == -45000


class TestDeltaSync:
    async def test_stores_and_sends_server_knowledge(self, mock_client):
        call_count = 0

        def handler(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                assert "last_knowledge_of_server" not in str(request.url)
            else:
                assert "last_knowledge_of_server=42" in str(request.url)
            return httpx.Response(200, json={
                "data": {"accounts": [], "server_knowledge": 42},
            })

        client = await mock_client(handler)
        await client.get_accounts()
        await client.get_accounts()
        assert call_count == 2


class TestErrorHandling:
    async def test_timeout_raises_ynab_error(self, mock_client):
        def handler(request):
            raise httpx.ReadTimeout("timed out")

        client = await mock_client(handler)
        with pytest.raises(YNABError) as exc_info:
            await client.get_accounts()
        assert exc_info.value.status_code == 408
        assert "timed out" in exc_info.value.detail.lower()

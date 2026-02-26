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


class TestDeleteTransaction:
    async def test_deletes_transaction(self, mock_client):
        def handler(request):
            assert request.method == "DELETE"
            assert "/transactions/t1" in str(request.url)
            return httpx.Response(200, json={"data": {}})

        client = await mock_client(handler)
        await client.delete_transaction("t1")


class TestGetPayees:
    async def test_returns_parsed_payees(self, mock_client):
        def handler(request):
            return httpx.Response(200, json={
                "data": {
                    "payees": [
                        {"id": "p1", "name": "HEB", "deleted": False},
                        {"id": "p2", "name": "Costco", "deleted": False},
                    ],
                    "server_knowledge": 10,
                },
            })

        client = await mock_client(handler)
        payees = await client.get_payees()
        assert len(payees) == 2
        assert payees[0].name == "HEB"


class TestUpdatePayee:
    async def test_renames_payee(self, mock_client):
        def handler(request):
            assert request.method == "PATCH"
            return httpx.Response(200, json={
                "data": {"payee": {"id": "p1", "name": "H-E-B", "deleted": False}},
            })

        client = await mock_client(handler)
        payee = await client.update_payee("p1", "H-E-B")
        assert payee.name == "H-E-B"


class TestCreateAccount:
    async def test_creates_account(self, mock_client):
        def handler(request):
            assert request.method == "POST"
            return httpx.Response(201, json={
                "data": {
                    "account": {
                        "id": "a-new",
                        "name": "Savings",
                        "type": "savings",
                        "on_budget": True,
                        "closed": False,
                        "balance": 100000,
                        "cleared_balance": 100000,
                        "uncleared_balance": 0,
                    },
                },
            })

        client = await mock_client(handler)
        account = await client.create_account("Savings", "savings", 100000)
        assert account.name == "Savings"
        assert account.balance == 100000


class TestImportTransactions:
    async def test_returns_imported_ids(self, mock_client):
        def handler(request):
            assert request.method == "POST"
            return httpx.Response(200, json={
                "data": {"transaction_ids": ["t1", "t2"]},
            })

        client = await mock_client(handler)
        ids = await client.import_transactions()
        assert ids == ["t1", "t2"]


class TestBulkUpdateTransactions:
    async def test_updates_multiple(self, mock_client):
        def handler(request):
            assert request.method == "PATCH"
            return httpx.Response(200, json={
                "data": {
                    "transactions": [
                        {
                            "id": "t1", "date": "2025-01-15", "amount": -10000,
                            "account_id": "a1", "cleared": "uncleared",
                            "approved": True, "deleted": False, "subtransactions": [],
                        },
                    ],
                },
            })

        client = await mock_client(handler)
        results = await client.bulk_update_transactions([{"id": "t1", "memo": "updated"}])
        assert len(results) == 1


class TestGetBudgetSettings:
    async def test_returns_settings(self, mock_client):
        def handler(request):
            return httpx.Response(200, json={
                "data": {
                    "settings": {
                        "date_format": {"format": "MM/DD/YYYY"},
                        "currency_format": {
                            "iso_code": "USD",
                            "example_format": "$1,234.56",
                            "decimal_digits": 2,
                            "decimal_separator": ".",
                            "symbol_first": True,
                            "group_separator": ",",
                            "currency_symbol": "$",
                            "display_symbol": True,
                        },
                    },
                },
            })

        client = await mock_client(handler)
        settings = await client.get_budget_settings()
        assert settings.currency_format.iso_code == "USD"


class TestGetUser:
    async def test_returns_user(self, mock_client):
        def handler(request):
            return httpx.Response(200, json={
                "data": {"user": {"id": "user-123"}},
            })

        client = await mock_client(handler)
        user = await client.get_user()
        assert user.id == "user-123"


class TestGetScheduledTransactions:
    async def test_returns_scheduled_list(self, mock_client):
        def handler(request):
            return httpx.Response(200, json={
                "data": {
                    "scheduled_transactions": [{
                        "id": "st1",
                        "date_first": "2025-01-01",
                        "date_next": "2025-02-01",
                        "frequency": "monthly",
                        "amount": -15990,
                        "account_id": "a1",
                        "deleted": False,
                        "subtransactions": [],
                    }],
                },
            })

        client = await mock_client(handler)
        scheduled = await client.get_scheduled_transactions()
        assert len(scheduled) == 1
        assert scheduled[0].frequency.value == "monthly"


class TestDeleteScheduledTransaction:
    async def test_deletes_scheduled(self, mock_client):
        def handler(request):
            assert request.method == "DELETE"
            assert "/scheduled_transactions/st1" in str(request.url)
            return httpx.Response(200, json={"data": {}})

        client = await mock_client(handler)
        await client.delete_scheduled_transaction("st1")

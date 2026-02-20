"""Tests for MCP error handling decorator."""

import httpx
from pydantic import ValidationError

from src.core.resolvers import ResolverError
from src.core.ynab_client import YNABError
from src.mcp.error_handling import handle_tool_errors


class TestHandleToolErrors:
    async def test_returns_result_on_success(self):
        @handle_tool_errors
        async def tool():
            return "ok"

        assert await tool() == "ok"

    async def test_catches_ynab_error(self):
        @handle_tool_errors
        async def tool():
            raise YNABError(404, "not_found", "not_found", "Resource not found")

        result = await tool()
        assert "Resource not found" in result

    async def test_catches_resolver_error(self):
        @handle_tool_errors
        async def tool():
            raise ResolverError("category", "xyz", ["Groceries", "Dining"])

        result = await tool()
        assert "xyz" in result

    async def test_catches_connect_error(self):
        @handle_tool_errors
        async def tool():
            raise httpx.ConnectError("Connection refused")

        result = await tool()
        assert "Cannot connect" in result

    async def test_catches_timeout(self):
        @handle_tool_errors
        async def tool():
            raise httpx.ReadTimeout("timed out")

        result = await tool()
        assert "timed out" in result.lower()

    async def test_catches_validation_error(self):
        @handle_tool_errors
        async def tool():
            from src.models.schemas import MoveBudgetInput
            MoveBudgetInput()  # type: ignore[call-arg]

        result = await tool()
        assert "Invalid data" in result
        assert "validation error" in result

    async def test_catches_unexpected_exception(self):
        @handle_tool_errors
        async def tool():
            raise RuntimeError("boom")

        result = await tool()
        assert "Unexpected error" in result
        assert "RuntimeError" in result
        assert "boom" in result

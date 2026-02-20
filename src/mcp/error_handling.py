"""Consistent error handling for MCP tool functions."""

from __future__ import annotations

import functools
import logging
from typing import Callable

import httpx
from pydantic import ValidationError

from src.core.resolvers import ResolverError
from src.core.ynab_client import YNABError

logger = logging.getLogger("ynab_mcp")


def handle_tool_errors(fn: Callable) -> Callable:
    """Decorator that catches known exceptions and returns user-friendly error strings.

    MCP tools must return ``str``, not raise.  This ensures all tools
    follow that contract without duplicating try/except blocks.
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except YNABError as e:
            return f"YNAB API error: {e.detail}"
        except ResolverError as e:
            return str(e)
        except httpx.ConnectError:
            return "Cannot connect to YNAB API. Check your network connection."
        except httpx.TimeoutException:
            return "Request to YNAB timed out. Please try again."
        except ValidationError as e:
            return f"Invalid data: {e.error_count()} validation error(s). Check your input."
        except Exception as e:
            logger.exception("Unexpected error in tool %s", fn.__name__)
            return f"Unexpected error: {type(e).__name__}: {e}"

    return wrapper

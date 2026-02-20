# CLAUDE.md

## Project Overview

YNAB Personal Assistant — a Python MCP server exposing YNAB budget management as 17+ tools for Claude Desktop/Code. Built with FastMCP, httpx, and Pydantic v2.

## Quick Reference

```bash
# Install
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Run MCP server
uv run python -m src.mcp.server

# Run smoke test (requires real YNAB_API_TOKEN in .env)
uv run python -m tests.smoke_test
```

## Claude Desktop / Claude Code Integration

To register this MCP server, add the following to your config:

- **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Claude Code:** `~/.claude.json`

```json
{
  "mcpServers": {
    "ynab": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp.server"],
      "cwd": "/absolute/path/to/ynab-assistant",
      "env": {
        "YNAB_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

The server registers as `ynab_mcp` via FastMCP. All 17 tools will appear prefixed with `ynab_` (e.g., `ynab_get_accounts`, `ynab_add_transaction`).

## Architecture

Strict three-layer separation — never violate these boundaries:

```
src/models/    → Data types only (Pydantic schemas + result dataclasses)
src/core/      → Business logic (NO I/O in analyzers.py and resolvers.py)
src/mcp/       → MCP boundary (tools, formatters, error handling)
```

**Key rule:** `analyzers.py` and `resolvers.py` must NEVER perform I/O (no HTTP, no file system, no MCP calls). All data must be pre-fetched and passed in. This keeps business logic testable without mocking.

**Orchestration pattern in each tool:**
1. Fetch data via `ynab.*` methods
2. Resolve names via `resolve_*` (pure)
3. Analyze via `analyze_*` or other pure functions (pure)
4. Format via `format_*` (pure)
5. Return the formatted string

## Coding Conventions

### Naming

- **Files:** `snake_case.py`
- **Classes:** `PascalCase`. API models = entity name (`Transaction`), inputs = `*Input`, results = `*Result`
- **Functions:** analyzers use `analyze_*`/`check_*`/`compute_*`/`filter_*`, formatters use `format_*`, resolvers use `resolve_*`, MCP tools use `ynab_<verb>_<noun>`
- **Internal helpers:** prefix with `_`
- **Constants:** `_UPPER_SNAKE_CASE` with leading underscore when module-private

### Imports

- Always use absolute imports from project root (`from src.models.schemas import ...`)
- Never use relative imports
- Group: stdlib, then third-party, then `src.*`, separated by blank lines

### Type Annotations

- Full annotations on all function signatures (params and return)
- Prefer `X | None` over `Optional[X]` in new code
- Use built-in lowercase generics (`list[T]`, `dict[K, V]`)
- Annotate milliunit fields with `# milliunits` inline comments

### Currency

All YNAB amounts are **milliunits** (1000 = $1.00). Use only the canonical conversion functions from `src/models/schemas.py`:

```python
from src.models.schemas import milliunits_to_dollars, dollars_to_milliunits
```

- Never reimplement these inline
- API response model fields are `int` (milliunits), never `float`
- Input model dollar amounts are `float`
- Outflows are negative milliunits; negate with `dollars_to_milliunits(-abs(amount))`
- Round dollars to 2 decimal places, percentages to 1
- Format output as `${value:,.2f}`

### Pydantic Models

- API response models: `model_config = ConfigDict(extra="ignore")` — absorb unknown YNAB fields
- MCP input models: `extra="forbid"` with `Field(...)` constraints and rich `description=` strings
- Use `model_dump(exclude_none=True)` for API payloads
- Input models use `str_strip_whitespace=True`

### Error Handling

- MCP tools **never raise** — they return `str`. The `@handle_tool_errors` decorator catches all exceptions
- Domain exceptions (`YNABError`, `ResolverError`) live in the module that raises them and carry structured attributes
- Decorator order: `@mcp.tool(...)` on top, `@handle_tool_errors` immediately below
- Currency comparisons use `0.005` epsilon (half a cent), not `== 0`

### MCP Tool Pattern

```python
@mcp.tool(
    name="ynab_<verb>_<noun>",
    annotations={"title": "...", "readOnlyHint": bool, "destructiveHint": bool, ...},
)
@handle_tool_errors
async def ynab_verb_noun(params: SomeInput, ctx: Context) -> str:
    ynab, categorizer = _get_deps(ctx)
    # ... fetch, resolve, analyze, format
    return format_result(...)
```

- Tool function name must match the `name=` parameter
- `ctx: Context` is always the last parameter (FastMCP requires the `Context` type annotation to inject the context object; using `Any` causes it to pass an empty dict)
- All tools return Markdown-formatted `str`
- Separate tool sections with `# --- Section Name ---` comments

### Filtering Conventions

- Always check `.deleted` before including any entity (transactions, categories, accounts, payees)
- Always check `.hidden` for categories/groups (except when rendering complete summaries)
- Internal category groups (`"Internal Master Category"`, `"Hidden Categories"`) are filtered out

## Testing

- **Framework:** pytest + pytest-asyncio with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed)
- **Factory functions** in `conftest.py`: `make_account`, `make_category`, `make_category_group`, `make_transaction`, `make_month_summary` — plain functions, not fixtures
- **HTTP mocking:** Use `httpx.MockTransport` with inline handler functions — no `unittest.mock`
- **Test organization:** `TestClassName` per feature, `test_descriptive_behavior` methods
- **One test file per source module:** `test_analyzers.py`, `test_categorizer.py`, etc.

## Environment

- `YNAB_API_TOKEN` — required, obtain from https://app.ynab.com/settings/developer
- `YNAB_BUDGET_ID` — optional, defaults to `"default"` (auto-resolves first budget at startup)
- Never log, print, or include tokens in error messages
- `.env` and `.history/` must remain in `.gitignore`

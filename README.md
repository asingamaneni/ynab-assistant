# YNAB Personal Assistant

A natural language interface for YNAB (You Need A Budget) that lets you manage your budget through conversation via Claude Desktop (MCP).

## Architecture

```
+--------------------------------------------------+
|                  Claude (You)                     |
|         "I spent $45 at HEB on groceries"         |
+--------------------------------------------------+
|               MCP Server (Desktop)                |
+--------------------------------------------------+
|              Core Logic Layer                     |
|  +----------+ +--------------+ +-----------+     |
|  |  YNAB    | |    Auto      | | Entity    |     |
|  |  Client  | | Categorizer  | | Resolvers |     |
|  +----------+ +--------------+ +-----------+     |
+--------------------------------------------------+
|              YNAB API (api.ynab.com/v1)           |
+--------------------------------------------------+
```

## Tech Stack

- **Language:** Python 3.12+
- **MCP Framework:** FastMCP
- **HTTP Client:** httpx (async)
- **Validation:** Pydantic v2

## Project Structure

```
ynab-assistant/
├── src/
│   ├── core/              # Shared business logic
│   │   ├── ynab_client.py       # YNAB API wrapper
│   │   ├── categorizer.py       # Auto-categorization engine
│   │   └── resolvers.py         # Account/category resolution
│   ├── mcp/               # MCP server (Claude Desktop)
│   │   ├── server.py            # Tool definitions
│   │   ├── formatters.py        # Markdown response formatting
│   │   └── error_handling.py    # Consistent error decorator
│   └── models/            # Pydantic models
│       └── schemas.py
├── tests/
│   ├── conftest.py
│   ├── test_resolvers.py
│   ├── test_categorizer.py
│   ├── test_ynab_client.py
│   └── test_formatters.py
├── requirements.txt
└── README.md
```

## Setup

### Quick Setup (Claude Code)

If you're using Claude Code, just run the `/setup` command — it handles everything automatically (venv, dependencies, MCP config).

### Manual Setup

#### 1. Get your YNAB API Token

Go to https://app.ynab.com/settings/developer -> New Token -> Copy it.

#### 2. Configure Environment

```bash
cp .env.example .env
# Add your YNAB_API_TOKEN to .env
```

#### 3. Install Dependencies

```bash
uv venv
uv pip install -e ".[dev]"
```

#### 4. Add to Claude Desktop

Edit your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

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

Restart Claude Desktop to pick up the new server.

#### 5. Add to Claude Code

Add to your Claude Code settings (`~/.claude.json`):

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

#### 6. Run Tests

```bash
uv run pytest
```

## Available Tools (37)

### Read-Only
| Tool | Description |
|------|-------------|
| `ynab_get_budgets` | List all YNAB budgets |
| `ynab_get_accounts` | List accounts with balances |
| `ynab_get_budget_summary` | Current month budget breakdown |
| `ynab_get_transactions` | Get transactions with filters |
| `ynab_get_category_spending` | Category spending detail |
| `ynab_search_transactions` | Search by payee, amount, memo |
| `ynab_uncategorized` | List uncategorized transactions |
| `ynab_spending_trends` | Month-over-month spending analysis |
| `ynab_cover_overspending` | Analyze overspent categories |
| `ynab_affordability_check` | Check if a purchase fits budget |
| `ynab_credit_card_status` | Credit card payment status |
| `ynab_spending_forecast` | Project category spending |
| `ynab_get_payees` | List all payees |
| `ynab_get_payee_transactions` | Transactions for a specific payee |
| `ynab_get_payee_locations` | Payee location data |
| `ynab_get_budget_settings` | Date and currency format settings |
| `ynab_get_user` | Authenticated user info |
| `ynab_get_scheduled_transactions` | List scheduled/recurring transactions |

### Write
| Tool | Description |
|------|-------------|
| `ynab_add_transaction` | Add transaction with auto-categorization |
| `ynab_add_split_transaction` | Split transaction across categories |
| `ynab_update_transaction` | Update any transaction field |
| `ynab_delete_transaction` | Delete a transaction |
| `ynab_categorize_transaction` | Categorize an uncategorized transaction |
| `ynab_recategorize_transaction` | Change a transaction's category |
| `ynab_bulk_update_transactions` | Update multiple transactions at once |
| `ynab_assign_budget` | Set budget amount for a category |
| `ynab_move_money` | Move money between categories |
| `ynab_setup_budget` | Set up next month's budget |
| `ynab_learn_categories` | Learn payee-to-category patterns |
| `ynab_update_payee` | Rename a payee |
| `ynab_update_category_metadata` | Update category name or note |
| `ynab_set_category_target` | Set, update, or remove a savings target/goal on a category |
| `ynab_create_account` | Create a new account |
| `ynab_import_transactions` | Trigger linked bank import |
| `ynab_create_scheduled_transaction` | Create a recurring transaction |
| `ynab_update_scheduled_transaction` | Update a scheduled transaction |
| `ynab_delete_scheduled_transaction` | Delete a scheduled transaction |

## Claude Code Commands

| Command | Description |
|---------|-------------|
| `/setup` | Create venv, install dependencies, and configure MCP server |
| `/daily-review` | Daily budget check-in: review transactions, categorize, and get a spending summary |
| `/budget` | Interactive monthly budget planning: compare, review, and apply next month's budget |

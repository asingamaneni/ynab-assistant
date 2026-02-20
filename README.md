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

### 1. Get your YNAB API Token

Go to https://app.ynab.com/settings/developer -> New Token -> Copy it.

### 2. Configure Environment

```bash
cp .env.example .env
# Add your YNAB_API_TOKEN to .env
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Add to Claude Desktop

Edit your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the following to the `mcpServers` object:

```json
{
  "mcpServers": {
    "ynab": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/absolute/path/to/ynab-assistant",
      "env": {
        "YNAB_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

Replace `/absolute/path/to/ynab-assistant` with the actual project path and `your-token-here` with your YNAB API token.

Restart Claude Desktop to pick up the new server.

### 5. Add to Claude Code

Add to your Claude Code settings (`~/.claude.json`):

```json
{
  "mcpServers": {
    "ynab": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/absolute/path/to/ynab-assistant",
      "env": {
        "YNAB_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

### 6. Run Tests

```bash
pip install -e ".[dev]"
pytest
```

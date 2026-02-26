Set up the YNAB Assistant development environment from scratch:

1. Create a Python virtual environment using uv:
   ```
   uv venv
   ```

2. Install all project dependencies (including dev):
   ```
   uv pip install -e ".[dev]"
   ```

3. Verify the installation by running the test suite:
   ```
   uv run pytest -q
   ```

4. Set up the MCP server for Claude Code by ensuring `~/.claude.json` has the ynab server configured. Read the existing file first, then add or update the `ynab` entry under `mcpServers`:
   ```json
   {
     "mcpServers": {
       "ynab": {
         "command": "uv",
         "args": ["run", "python", "-m", "src.mcp.server"],
         "cwd": "$PROJECT_DIR",
         "env": {
           "YNAB_API_TOKEN": "$YNAB_TOKEN"
         }
       }
     }
   }
   ```
   - Replace `$PROJECT_DIR` with the absolute path to this repository
   - For the YNAB_API_TOKEN: check if a `.env` file exists in the project root and read the token from there. If not, ask the user to provide their token from https://app.ynab.com/settings/developer
   - Do NOT overwrite existing mcpServers entries — merge the ynab entry in

5. Confirm setup is complete and remind the user to run `/mcp` to connect to the YNAB server.

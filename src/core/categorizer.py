"""Auto-categorization engine for YNAB transactions.

Learns payee -> category mappings from transaction history and applies
them to new transactions. Uses exact match first, then fuzzy matching.
"""

import json
from pathlib import Path
from typing import Optional


class Categorizer:
    """Maps payees to YNAB categories based on historical patterns."""

    def __init__(self, mappings_file: Optional[str] = None):
        self._mappings_file = mappings_file or str(
            Path.home() / ".ynab-assistant" / "categorizer.json"
        )
        self._mappings: dict[str, dict] = {}
        self._load()

    def _load(self):
        """Load mappings from disk."""
        path = Path(self._mappings_file)
        if path.exists():
            try:
                self._mappings = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self._mappings = {}

    def _save(self):
        """Persist mappings to disk."""
        path = Path(self._mappings_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._mappings, indent=2))

    def learn_from_transactions(self, transactions: list[dict]):
        """Build mappings from historical transactions."""
        for txn in transactions:
            payee = txn.get("payee_name")
            cat_id = txn.get("category_id")
            cat_name = txn.get("category_name")

            if not payee or not cat_id:
                continue

            key = payee.strip().lower()
            if key not in self._mappings:
                self._mappings[key] = {
                    "category_id": cat_id,
                    "category_name": cat_name or "",
                    "count": 0,
                }

            existing = self._mappings[key]
            if cat_id == existing["category_id"]:
                existing["count"] += 1
            else:
                existing["count"] -= 1
                if existing["count"] <= 0:
                    self._mappings[key] = {
                        "category_id": cat_id,
                        "category_name": cat_name or "",
                        "count": 1,
                    }

        self._save()

    def suggest_category(self, payee_name: str) -> Optional[dict]:
        """Suggest a category for a given payee."""
        if not payee_name:
            return None

        key = payee_name.strip().lower()

        # Exact match
        if key in self._mappings:
            m = self._mappings[key]
            return {"category_id": m["category_id"], "category_name": m["category_name"]}

        # Partial match
        for known_key, mapping in self._mappings.items():
            if known_key in key or key in known_key:
                return {
                    "category_id": mapping["category_id"],
                    "category_name": mapping["category_name"],
                }

        return None

    def add_mapping(self, payee_name: str, category_id: str, category_name: str = ""):
        """Manually add or override a payee -> category mapping."""
        key = payee_name.strip().lower()
        self._mappings[key] = {
            "category_id": category_id,
            "category_name": category_name,
            "count": 100,
        }
        self._save()

    def get_all_mappings(self) -> dict[str, dict]:
        """Get all current payee -> category mappings."""
        return dict(self._mappings)

    def clear(self):
        """Clear all mappings."""
        self._mappings = {}
        self._save()

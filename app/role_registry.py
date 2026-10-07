"""Legacy specialist-role metadata catalog, separate from loaded skill text.

Catalog descriptions do not establish that a role has been tested or executes
as an independent agent. Selected source-verified playbooks live in skills/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AgentRole:
    id: str
    name: str
    description: str
    category: str
    file: str
    kind: str


class RoleRegistry:
    """Look up descriptive role metadata; never execute or approve an action."""

    def __init__(self, catalog_path: Optional[Path | str] = None):
        if catalog_path is None:
            catalog_path = Path(__file__).resolve().parent.parent / "config" / "agency_roles_catalog.json"
        self.catalog_path = Path(catalog_path)
        self.roles: Dict[str, AgentRole] = {}
        self.categories: Dict[str, List[AgentRole]] = {}
        self._load()

    def _load(self) -> None:
        if not self.catalog_path.exists():
            return

        with self.catalog_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            role = AgentRole(
                id=item.get("id", ""),
                name=item.get("name", ""),
                description=item.get("description", ""),
                category=item.get("category", "general"),
                file=item.get("file", ""),
                kind=item.get("kind", "standard-role"),
            )
            self.roles[role.id] = role
            self.categories.setdefault(role.category, []).append(role)

    def get_role(self, role_id: str) -> Optional[AgentRole]:
        """Look up role by exact ID (e.g. 'engineering/engineering-code-reviewer')."""
        return self.roles.get(role_id)

    def list_categories(self) -> List[str]:
        """Return all available categories."""
        return sorted(list(self.categories.keys()))

    def get_roles_by_category(self, category: str) -> List[AgentRole]:
        """Return all roles belonging to a specific category."""
        return self.categories.get(category.lower(), [])

    def search_roles(self, query: str, limit: int = 10) -> List[AgentRole]:
        """Search roles by keyword in name, ID, or description."""
        q = query.lower()
        results = []
        for role in self.roles.values():
            if q in role.id.lower() or q in role.name.lower() or q in role.description.lower():
                results.append(role)
                if len(results) >= limit:
                    break
        return results

    def format_agent_prompt(self, role_id: str, custom_instructions: str = "") -> str:
        """Composes a system prompt incorporating the role's identity and description."""
        role = self.get_role(role_id)
        if not role:
            return custom_instructions

        lines = [
            f"You are the {role.name} ({role.id}).",
            f"Role Specification: {role.description}",
            "Operating Invariants: Follow the operator's approval rules and tool boundaries. This role grants no additional permissions.",
        ]
        if custom_instructions:
            lines.append(f"\nTask Context & Instructions:\n{custom_instructions}")
        return "\n".join(lines)


# Global singleton instance
role_registry = RoleRegistry()

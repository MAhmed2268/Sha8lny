"""
skill_graph_loader.py
=====================
Public loader module for the curated skill graph.

Used by assessment and roadmap modules to import the skill graph
without coupling them to the file path or JSON structure.

Usage:
    from Backend.data.skill_graph_loader import load_skill_graph, get_role

    graph = load_skill_graph()
    role  = get_role("frontend_developer")
    # → {"subskills": [...], "levels": {...}, "priority": {...}}

All functions return empty structures (never raise KeyError) when a
role or skill is not found, so callers need no defensive wrapping.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_GRAPH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "role_graph.json")


@lru_cache(maxsize=1)
def load_skill_graph() -> dict[str, Any]:
    """
    Load and return the full curated skill graph as a dict.

    The result is cached after the first successful load; subsequent
    calls within the same process are free (no I/O, no re-parsing).

    Returns:
        dict  →  role_key (str) → {
                     "subskills": list[str],
                     "levels":    dict[str, str],   # beginner|intermediate|advanced
                     "priority":  dict[str, str],   # essential|optional
                 }

    Raises:
        FileNotFoundError  →  if role_graph.json has not been generated.
        json.JSONDecodeError  →  if the file is malformed.
    """
    if not os.path.isfile(_GRAPH_PATH):
        raise FileNotFoundError(
            f"role_graph.json not found at '{_GRAPH_PATH}'. "
            "Run Backend/scripts/build_skill_graph.py first."
        )
    with open(_GRAPH_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def get_role(role_key: str) -> dict[str, Any]:
    """Return the full skill data dict for a single role, or {} if not found."""
    return load_skill_graph().get(role_key, {})


def list_roles() -> list[str]:
    """Return all available role keys in the graph."""
    return list(load_skill_graph().keys())


def get_subskills(role_key: str) -> list[str]:
    """Return the ordered subskills list for a role, or [] if not found."""
    return get_role(role_key).get("subskills", [])


def get_skill_level(role_key: str, skill: str) -> str | None:
    """Return 'beginner', 'intermediate', 'advanced', or None if not found."""
    return get_role(role_key).get("levels", {}).get(skill)


def get_skill_priority(role_key: str, skill: str) -> str | None:
    """Return 'essential', 'optional', or None if not found."""
    return get_role(role_key).get("priority", {}).get(skill)


def get_essential_skills(role_key: str) -> list[str]:
    """Return only the essential subskills for a role, in original order."""
    role = get_role(role_key)
    prio = role.get("priority", {})
    return [s for s in role.get("subskills", []) if prio.get(s) == "essential"]


def get_skills_by_level(role_key: str, level: str) -> list[str]:
    """Return subskills matching a specific level for a role."""
    role   = get_role(role_key)
    levels = role.get("levels", {})
    return [s for s in role.get("subskills", []) if levels.get(s) == level]

"""
validate_graph.py
=================
Schema validation for role_graph.json.

Checks:
  1. File exists and is valid JSON
  2. Top-level is a non-empty dict
  3. All role keys are snake_case
  4. Each role has 'subskills', 'levels', 'priority'
  5. 'subskills' is a non-empty list with no duplicates and no blank entries
  6. 'levels' values are only: beginner | intermediate | advanced
  7. 'priority' values are only: essential | optional
  8. Every skill in 'subskills' is present in both 'levels' and 'priority'
  9. 'levels' and 'priority' contain no orphan keys absent from 'subskills'
  10. Flag roles with fewer than MIN_SUBSKILLS (5) skills for manual review

Exit code 0  → validation passed (warnings may exist)
Exit code 1  → one or more errors found
"""

import json
import os
import re
import sys

_HERE      = os.path.dirname(os.path.abspath(__file__))
GRAPH_PATH = os.path.join(_HERE, "..", "data", "role_graph.json")

VALID_LEVELS    = {"beginner", "intermediate", "advanced"}
VALID_PRIORITY  = {"essential", "optional"}
SNAKE_RE        = re.compile(r"^[a-z][a-z0-9_]*$")
MIN_SUBSKILLS   = 5

errors:   list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)
    print(f"    [ERROR]   {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"    [WARNING] {msg}")


def validate(graph: object) -> None:
    if not isinstance(graph, dict):
        err("Top-level structure is not a dict.")
        return
    if not graph:
        err("Graph is empty — no roles found.")
        return

    for role_key, role_data in graph.items():
        print(f"\n  Role: {role_key}")

        if not SNAKE_RE.match(role_key):
            err(f"[{role_key}] Key is not valid snake_case.")

        for required in ("subskills", "levels", "priority"):
            if required not in role_data:
                err(f"[{role_key}] Missing required key '{required}'.")

        subskills = role_data.get("subskills", [])
        levels    = role_data.get("levels",    {})
        priority  = role_data.get("priority",  {})

        if not isinstance(subskills, list):
            err(f"[{role_key}] 'subskills' is not a list.")
            continue

        if not subskills:
            err(f"[{role_key}] 'subskills' is empty.")
            continue

        for skill in subskills:
            if not isinstance(skill, str) or not skill.strip():
                err(f"[{role_key}] Blank or non-string entry in 'subskills': {skill!r}")

        seen: set[str] = set()
        for skill in subskills:
            if skill in seen:
                err(f"[{role_key}] Duplicate skill in 'subskills': '{skill}'")
            seen.add(skill)

        subskill_set = set(subskills)

        for skill, level in levels.items():
            if level not in VALID_LEVELS:
                err(f"[{role_key}] Skill '{skill}' has invalid level '{level}'.")

        for skill, prio in priority.items():
            if prio not in VALID_PRIORITY:
                err(f"[{role_key}] Skill '{skill}' has invalid priority '{prio}'.")

        for skill in subskill_set:
            if skill not in levels:
                err(f"[{role_key}] Skill '{skill}' missing from 'levels'.")
            if skill not in priority:
                err(f"[{role_key}] Skill '{skill}' missing from 'priority'.")

        for skill in levels:
            if skill not in subskill_set:
                err(f"[{role_key}] 'levels' has orphan key '{skill}' not in subskills.")
        for skill in priority:
            if skill not in subskill_set:
                err(f"[{role_key}] 'priority' has orphan key '{skill}' not in subskills.")

        if len(subskills) < MIN_SUBSKILLS:
            warn(f"[{role_key}] Only {len(subskills)} subskill(s) — flag for manual review.")

        essential_count = sum(1 for p in priority.values() if p == "essential")
        level_counts = {lv: sum(1 for l in levels.values() if l == lv) for lv in VALID_LEVELS}
        print(
            f"    subskills={len(subskills)}  essential={essential_count}  "
            f"beginner={level_counts['beginner']}  "
            f"intermediate={level_counts['intermediate']}  "
            f"advanced={level_counts['advanced']}"
        )


def main() -> None:
    print("=" * 60)
    print("Curated Skill Graph  —  Validation")
    print("=" * 60)

    graph_path = os.path.normpath(GRAPH_PATH)

    if not os.path.isfile(graph_path):
        print(f"\n[FATAL] role_graph.json not found at:\n  {graph_path}")
        print("  Run build_skill_graph.py first.")
        sys.exit(1)

    with open(graph_path, "r", encoding="utf-8") as fh:
        try:
            graph = json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"\n[FATAL] role_graph.json is not valid JSON:\n  {exc}")
            sys.exit(1)

    print(f"\nLoaded: {graph_path}")
    print(f"Roles found: {list(graph.keys()) if isinstance(graph, dict) else 'N/A'}")

    validate(graph)

    print("\n" + "=" * 60)
    if errors:
        print(f"RESULT: FAILED  —  ({len(errors)} error(s), {len(warnings)} warning(s))")
        for e in errors:
            print(f"  [X]  {e}")
        sys.exit(1)
    else:
        if warnings:
            print(f"RESULT: PASSED  OK  with {len(warnings)} warning(s)")
            for w in warnings:
                print(f"  [!]  {w}")
        else:
            print("RESULT: PASSED  OK  all checks clean, zero warnings.")
        sys.exit(0)


if __name__ == "__main__":
    main()

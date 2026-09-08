"""Category name + parent lineage resolution for anything that needs to
show a human-readable category instead of a bare id -- see
AliClient.get_categories() for where the underlying data comes from and
collector/store.py:upsert_categories for how it lands in the `categories`
table this reads.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple


@dataclass(frozen=True)
class CategoryPath:
    name: str
    path: str  # "Root > ... > name"; just `name` for a top-level category


def load_category_paths(conn: sqlite3.Connection) -> Dict[int, CategoryPath]:
    """category_id -> (name, full breadcrumb path), walking parent_category_id
    up to a top-level category (parent_category_id IS NULL)."""
    rows = conn.execute("SELECT category_id, category_name, parent_category_id FROM categories").fetchall()
    by_id = {row["category_id"]: (row["category_name"], row["parent_category_id"]) for row in rows}

    paths: Dict[int, CategoryPath] = {}
    for category_id, (name, _parent) in by_id.items():
        breadcrumbs = [name]
        current_parent = by_id[category_id][1]
        seen = {category_id}  # guards against a cycle in source data, however unlikely
        while current_parent is not None and current_parent in by_id and current_parent not in seen:
            parent_name, next_parent = by_id[current_parent]
            breadcrumbs.append(parent_name)
            seen.add(current_parent)
            current_parent = next_parent
        paths[category_id] = CategoryPath(name=name, path=" > ".join(reversed(breadcrumbs)))
    return paths


def category_display(
    category_id: Optional[int],
    paths: Dict[int, CategoryPath],
    ancestor_ids: Sequence[int] = (),
) -> Tuple[Optional[str], Optional[str]]:
    """(category_name, category_path) for a product's category_id.

    Tries category_id itself first, then walks ancestor_ids (a product's
    full root-to-leaf category path -- see
    normalize.parse_category_ancestor_ids) from leaf back toward root,
    using the deepest one that resolves. Necessary because AliExpress's
    category-name lookup (`categories` table, populated by
    collector/cli.py sync-categories) only covers a much broader/
    shallower tree than real per-product leaf category ids -- confirmed
    live, a bare leaf id resolved to a name only ~2% of the time in one
    production catalog, while an ancestor a level or two up usually does.
    Falls back to a synthetic "Category <id>" label only once every
    candidate in the path is exhausted.
    """
    if category_id is None:
        return None, None
    for candidate in (category_id, *reversed(ancestor_ids)):
        found = paths.get(candidate)
        if found is not None:
            return found.name, found.path
    fallback = f"Category {category_id}"
    return fallback, fallback

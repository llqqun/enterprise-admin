"""Generic tree building.

Used for the department tree and the menu/route tree alike, so the nesting rules —
including what happens to an orphan — exist in exactly one place.
"""

from collections.abc import Mapping, Sequence
from typing import Any


def build_tree(
    items: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    parent_field: str,
    children_field: str = "children",
    root_parent: Any = 0,
) -> list[dict[str, Any]]:
    """Nest flat nodes into a forest of plain dicts.

    A node whose parent is not present in `items` is promoted to a root rather than
    dropped: silently losing a subtree is far worse than showing it one level too
    high. Input order is preserved, so callers control sibling order by sorting
    before calling.
    """
    nodes: dict[Any, dict[str, Any]] = {}
    for item in items:
        node = dict(item)
        node[children_field] = []
        nodes[node[id_field]] = node

    roots: list[dict[str, Any]] = []
    for node in nodes.values():
        parent_id = node.get(parent_field)
        parent = nodes.get(parent_id)
        if parent is None or parent_id == root_parent:
            roots.append(node)
        else:
            parent[children_field].append(node)

    return roots

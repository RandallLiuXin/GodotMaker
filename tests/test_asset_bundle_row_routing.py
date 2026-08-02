"""The supersede whitelist must stay the planner's routing table, not a copy.

`asset_bundle_rows.py` decides which planner request rows a bundle production
may close out. That set is not its own to invent: `asset-planner.md`'s ASSETS
Family Routing table is what actually routes a row to a production unit. This
test reads the table and fails when the two drift apart, so adding a routing
there without widening the tool — or the reverse — cannot pass silently.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from asset_bundle_rows import SERVED_REQUEST_FAMILIES  # noqa: E402
from asset_stable_entry import BUNDLE_FAMILIES  # noqa: E402

PLANNER = ROOT / "skills" / "core" / "gm-asset" / "references" / "asset-planner.md"
ROUTING_HEADING = "## ASSETS Family Routing"


def _routing_table() -> dict[str, set[str]]:
    """Return ``production unit -> {request family}`` from the planner doc."""
    lines = PLANNER.read_text(encoding="utf-8").splitlines()
    start = lines.index(ROUTING_HEADING) + 1
    routing: dict[str, set[str]] = {}
    for line in lines[start:]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 2:
            continue
        family, unit = (cell.strip("`") for cell in cells)
        if family in {"Family", "--------"} or set(family) <= {"-"}:
            continue
        routing.setdefault(unit, set()).add(family)
    return routing


def test_the_routing_table_is_parsed_at_all():
    routing = _routing_table()
    assert routing, f"no ASSETS Family Routing rows parsed from {PLANNER}"
    assert "ui-kit" in routing


def test_every_bundle_family_declares_exactly_the_rows_the_planner_routes_to_it():
    routing = _routing_table()
    for family in sorted(BUNDLE_FAMILIES):
        assert family in SERVED_REQUEST_FAMILIES, (
            f"{family} is a bundle family but declares no serveable request rows"
        )
        assert SERVED_REQUEST_FAMILIES[family] == routing.get(family, set()), (
            f"{family} supersede whitelist has drifted from the planner routing "
            f"table in {PLANNER}"
        )


def test_no_non_bundle_family_claims_serveable_rows():
    assert set(SERVED_REQUEST_FAMILIES) == BUNDLE_FAMILIES

"""Contract tests for `DESIGN.md` as the asset stage's visual authority.

The asset stage inverts the old "reference-first, DESIGN.md as a seed" rule:
`DESIGN.md` is the visual specification authority, and role-labeled reference
images are visual conditioning attached alongside its rules.

The producer and every asset skill are LLMs reading Markdown, so the contract
itself is the Markdown. These tests pin it the same way
`tests/test_verify_report_fixtures.py` pins the verify protocol: parse the
documented Design Rule Selection table, cross-bind it to the request schema's
family enum and to the `DESIGN.md` template headings, and assert the prose
that carries the authority, conflict, and boundedness rules is actually there.

`select_design_sections()` is a reference implementation of the documented
retrieval — it proves the table and the template agree on the section names and
that selection stays bounded and verbatim. It is not the production selector;
the planner performs the selection in its own context.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLANNER = REPO_ROOT / "skills" / "core" / "gm-asset" / "references" / "asset-planner.md"
MANAGER = REPO_ROOT / "skills" / "core" / "gm-asset" / "SKILL.md"
PRODUCER = REPO_ROOT / "agents" / "asset-producer.md"
ANALYST_DISPATCH = REPO_ROOT / "skills" / "core" / "_shared" / "analyst-dispatch.md"
SHARED_CONTRACT = (
    REPO_ROOT / "skills" / "assets" / "_shared" / "asset-skill-contract.md"
)
REQUEST_SCHEMA = (
    REPO_ROOT / "skills" / "assets" / "_shared" / "schema"
    / "asset-skill-request.schema.json"
)
DESIGN_TEMPLATE = REPO_ROOT / "templates" / "DESIGN.md"

# The nine image-style dimension headings, in template order. Mirrors
# tests/test_design_md_contract.py — the section names are one fixed contract.
DIMENSIONS = (
    "Medium And Rendering",
    "Color And Value",
    "Shape And Silhouette",
    "Line And Edge",
    "Material And Texture",
    "Lighting And Shadow",
    "Space, Perspective, And Depth",
    "Composition And Visual Hierarchy",
    "Detail Density And Abstraction",
)

# Dimensions no generated image can be produced without.
UNIVERSAL_DIMENSIONS = frozenset({1, 2, 3, 4, 5, 6, 9})
# The two families that own the whole frame, so they own composition and depth.
FULL_FRAME_FAMILIES = frozenset({"screen-reference", "background-map"})
# The families whose output is a reusable UI surface system.
UI_FAMILIES = frozenset({"ui-kit", "card-kit"})

# Reference dispositions, as exact values the planner and producer must use.
DISPOSITIONS = ("consistent", "excluded_candidate", "blocker")

FAMILY_SKILLS = {
    path.parent.name: path
    for path in sorted((REPO_ROOT / "skills" / "assets").glob("*/SKILL.md"))
}

# Every project document the asset-stage docs may name. A visual document not
# on this list is a second style source — exactly what this contract forbids.
KNOWN_NON_VISUAL_DOCS = frozenset({
    "ASSETS.md", "PLAN.md", "SCENES.md", "STRUCTURE.md", "ROADMAP.md",
    "GDD.md", "GAP.md", "MEMORY.md", "TOC.md", "CLAUDE.md", "SKILL.md",
})
PROJECT_DOC = re.compile(r"\b([A-Z][A-Z0-9_-]*\.md)\b")

ASSET_STAGE_DOCS = (PLANNER, MANAGER, PRODUCER, ANALYST_DISPATCH, SHARED_CONTRACT)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return one `## heading` section body, up to the next `## `."""
    assert f"\n## {heading}\n" in text, f"missing section: ## {heading}"
    body = text.split(f"\n## {heading}\n", 1)[1]
    return body.split("\n## ", 1)[0]


# ---------------------------------------------------------------------------
# Design Rule Selection table — the caller-side authority
# ---------------------------------------------------------------------------

def _parse_selection_table() -> dict[str, dict[str, object]]:
    """Parse the documented per-family selection into a comparable mapping."""
    body = _section(_read(PLANNER), "Design Rule Selection")
    rows = {}
    for line in body.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        family, identity, dims, ui, do_dont = cells
        family = family.strip("`")
        if dims == "1-9":
            numbers = set(range(1, 10))
        else:
            numbers = {int(part) for part in dims.split(",")}
        rows[family] = {
            "visual_identity": identity == "yes",
            "dimensions": numbers,
            "ui_visual_language": ui == "yes",
            "do_dont": do_dont == "yes",
        }
    assert rows, "Design Rule Selection must document a per-family table"
    return rows


SELECTION = _parse_selection_table()


def test_selection_covers_exactly_the_request_schema_families():
    """The table is bound to the request enum, not to a private family list."""
    schema = json.loads(_read(REQUEST_SCHEMA))
    families = set(schema["properties"]["asset_type"]["enum"])
    assert set(SELECTION) == families
    assert families == set(FAMILY_SKILLS), (
        "every request family must have a first-class Asset Skill"
    )


@pytest.mark.parametrize("family", sorted(SELECTION))
def test_every_family_selects_visual_identity_and_do_dont(family):
    row = SELECTION[family]
    assert row["visual_identity"], f"{family} must carry Visual Identity"
    assert row["do_dont"], f"{family} must carry Do / Don't"


@pytest.mark.parametrize("family", sorted(SELECTION))
def test_every_family_selects_the_universal_dimensions(family):
    numbers = SELECTION[family]["dimensions"]
    assert numbers <= set(range(1, 10)), f"{family} names a dimension outside 1-9"
    missing = UNIVERSAL_DIMENSIONS - numbers
    assert not missing, f"{family} drops always-applicable dimensions: {sorted(missing)}"


def test_ui_visual_language_is_selected_for_the_ui_families():
    """AC-03: `ui-kit` and `card-kit` additionally consume UI Visual Language."""
    for family in UI_FAMILIES:
        assert SELECTION[family]["ui_visual_language"], family
    # A subject family has no UI surface to style.
    for family in sorted(set(SELECTION) - UI_FAMILIES - FULL_FRAME_FAMILIES):
        assert not SELECTION[family]["ui_visual_language"], family


def test_selection_stays_bounded_per_asset_type():
    """AC-05: only the full-frame families take the whole contract."""
    all_nine = set(range(1, 10))
    for family, row in SELECTION.items():
        if family in FULL_FRAME_FAMILIES:
            assert row["dimensions"] == all_nine, family
        else:
            assert row["dimensions"] < all_nine, (
                f"{family} selection is not bounded — it takes every dimension"
            )
    # Composition belongs to whoever owns the frame; depth to whoever has one.
    for family in sorted(set(SELECTION) - FULL_FRAME_FAMILIES - UI_FAMILIES):
        assert 8 not in SELECTION[family]["dimensions"], family
    for family in sorted(UI_FAMILIES):
        assert 7 not in SELECTION[family]["dimensions"], family
        assert 8 in SELECTION[family]["dimensions"], family


def test_selection_names_verbatim_retrieval_and_forbids_a_second_source():
    """AC-05: scoped retrieval selects DESIGN.md text, it never derives a copy."""
    body = _section(_read(PLANNER), "Design Rule Selection")
    assert "verbatim" in body
    assert "Do not summarize them" in body
    assert "do not persist a derived style file" in body
    assert "never produces a second style source" in body
    assert "the brief stays bounded" in body


# ---------------------------------------------------------------------------
# Reference implementation of the documented retrieval
# ---------------------------------------------------------------------------

def _design_sections(text: str) -> dict[str, str]:
    """Split a DESIGN.md into `heading -> body`, including the nine dimensions."""
    sections = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            current = line.lstrip("#").strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def select_design_sections(design_text: str, asset_type: str) -> list[str]:
    """Reference implementation of Design Rule Selection (planner-side)."""
    row = SELECTION[asset_type]
    sections = _design_sections(design_text)
    wanted = []
    if row["visual_identity"]:
        wanted.append("Visual Identity")
    wanted += [
        f"{number}. {DIMENSIONS[number - 1]}"
        for number in sorted(row["dimensions"])
    ]
    if row["ui_visual_language"]:
        wanted.append("UI Visual Language")
    if row["do_dont"]:
        wanted += ["Do", "Don't"]

    selected = []
    for heading in wanted:
        body = sections[heading]
        if body in {"{unspecified}", ""} or body.startswith("N/A"):
            continue  # documented skip rule
        selected.append(heading)
    return selected


def test_table_dimension_numbers_bind_to_the_template_headings():
    """A renamed or renumbered template dimension must fail here, loudly."""
    headings = set(_design_sections(_read(DESIGN_TEMPLATE)))
    for number, name in enumerate(DIMENSIONS, start=1):
        assert f"{number}. {name}" in headings
    for heading in ("Visual Identity", "UI Visual Language", "Do", "Don't"):
        assert heading in headings
    # Selection resolves against the template for every documented family.
    for family in SELECTION:
        select_design_sections(_read(DESIGN_TEMPLATE), family)


FILLED_DESIGN = """# DESIGN: Fixture

## Visual Identity

Hand-inked storybook fantasy with warm parchment values.

## Image Style

### 1. Medium And Rendering

Hand-inked cel shading.

- Flat fills with one ink pass.

### 2. Color And Value

Warm parchment mid-values.

- Keep saturation under the mid range.

### 3. Shape And Silhouette

Rounded, readable silhouettes.

- Read the subject at 48 px tall.

### 4. Line And Edge

One dark ink outline.

- MUST keep a closed outer contour.

### 5. Material And Texture

Dry paper grain.

- Keep grain off gameplay-critical shapes.

### 6. Lighting And Shadow

Single warm key from upper left.

- One soft contact shadow.

### 7. Space, Perspective, And Depth

Flat side-on projection.

- Separate planes by value, not by blur.

### 8. Composition And Visual Hierarchy

Centered focal subject.

- Keep the lower third clear for the HUD.

### 9. Detail Density And Abstraction

{unspecified}

## UI Visual Language

UI reads as inked parchment panels.

- Panels use the parchment surface with a dark ink border.

## Do

- Do keep gameplay-critical shapes unobstructed.

## Don't

- Don't render neon or chrome materials.
"""


def test_reference_selection_is_bounded_and_verbatim():
    ui = select_design_sections(FILLED_DESIGN, "ui-kit")
    assert "UI Visual Language" in ui
    assert "8. Composition And Visual Hierarchy" in ui
    assert "7. Space, Perspective, And Depth" not in ui

    character = select_design_sections(FILLED_DESIGN, "character-bundle")
    assert "7. Space, Perspective, And Depth" in character
    assert "8. Composition And Visual Hierarchy" not in character
    assert "UI Visual Language" not in character

    foundation = select_design_sections(FILLED_DESIGN, "screen-reference")
    assert len(foundation) > len(character)

    # Every selection is drawn from DESIGN.md text — never rewritten.
    sections = _design_sections(FILLED_DESIGN)
    for heading in foundation:
        assert sections[heading] in FILLED_DESIGN


def test_reference_selection_skips_unspecified_and_na_sections():
    assert "9. Detail Density And Abstraction" not in select_design_sections(
        FILLED_DESIGN, "character-bundle"
    )
    no_ui = FILLED_DESIGN.replace(
        "UI reads as inked parchment panels.\n\n"
        "- Panels use the parchment surface with a dark ink border.",
        "N/A - this project has no visible UI.",
    )
    assert "UI Visual Language" not in select_design_sections(no_ui, "ui-kit")


# ---------------------------------------------------------------------------
# AC-01: the foundation reference
# ---------------------------------------------------------------------------

def test_anchor_gate_plans_one_design_driven_foundation_reference():
    body = _section(_read(PLANNER), "Visual Anchor Gate")
    assert "plan exactly one foundation unit and nothing else" in body
    assert "single `screen-reference`" in body
    assert "complete\n`DESIGN.md` visual contract verbatim" in body
    for heading in ("Visual Identity", "UI Visual Language", "Do", "Don't"):
        assert heading in body
    assert "content brief" in body
    assert "It has no reference\ninput" in body
    assert "design provenance" in body


def test_screen_reference_skill_treats_the_brief_as_the_whole_specification():
    text = _read(FAMILY_SKILLS["screen-reference"])
    assert "Carry\nevery visual rule stated in `brief` into that prompt as written" in text
    assert "the brief is the whole visual specification" in text
    assert "Do not invent a rule the\nbrief does not state." in text


# ---------------------------------------------------------------------------
# AC-02 / AC-03: rules and attached references reach the provider together
# ---------------------------------------------------------------------------

def test_manager_brief_carries_design_rules_and_role_labeled_references():
    text = _read(MANAGER)
    assert "### Design Rules" in text
    assert "copied verbatim from" in text
    assert "visual specification\nauthority for this unit" in text
    assert "never send only the file path" in text
    assert "### Reference Inputs" in text
    for role in ("canonical", "style", "screen"):
        assert f"`{role}`" in text
    assert "attached to the provider call as real image bytes" in text
    assert "Design Rule Selection and Reference\nConflict Disposition" in text


def test_producer_prompt_rules_put_design_above_references():
    rules = _section(_read(PRODUCER), "Prompt Rules")
    authority = "visual specification\n   authority"
    conditioning = "visual\n   conditioning"
    assert authority in rules, "the carried DESIGN.md rules must be the authority"
    assert conditioning in rules, "references must be stated as conditioning"
    # Rule order is the authority order: rules first, references second.
    assert rules.index(authority) < rules.index(conditioning)
    assert "a design rule the\n   brief lists but the prompt drops is an unfinished unit" in rules
    assert "never outrank, extend, or replace a design rule" in rules
    # No second style source, and no independent read of a project visual doc.
    assert "do not summarize the\n   carried rules into a second style description" in rules
    assert "do not read `DESIGN.md`\n   or any other project visual document yourself" in rules
    assert "The brief is the only style\n   source." in rules


def test_producer_report_records_design_and_attachment_evidence():
    text = _read(PRODUCER)
    visual_inputs = text.split("### Visual Inputs", 1)[1].split("### Outputs", 1)[0]
    assert "Design sections carried by the brief" in visual_inputs
    assert "Design sections written into the prompt" in visual_inputs
    for field in ("role", "path", "sha256", "attached"):
        assert field in visual_inputs
    assert "Reference conflicts" in visual_inputs


@pytest.mark.parametrize("family", sorted(FAMILY_SKILLS))
def test_every_family_skill_takes_its_visual_rules_from_the_brief(family):
    text = _read(FAMILY_SKILLS[family])
    assert "stated in `brief`" in text, (
        f"{family} must state that the brief carries its visual rules"
    )


def test_shared_contract_states_the_authority_and_conditioning_split():
    body = _section(_read(SHARED_CONTRACT), "Request")
    assert "`brief` is the only style source an asset skill has" in body
    assert "the rules in `brief` are the visual\nspecification authority" in body
    assert "the skill stays independent: it\nnever opens a project visual document itself" in body
    assert "`references` is visual conditioning" in body
    assert "never outranks, extends, or replaces a rule stated in `brief`" in body
    assert "A path named only in prompt text\nis not an attachment." in body


def test_ui_families_keep_technical_output_in_the_skill_contract():
    """AC-03: UI rules shape the visuals; the output shape stays contractual."""
    body = _section(_read(PLANNER), "Design Rule Selection")
    assert (
        "their technical output shape still comes only from the Asset Skill contract"
        in body
    )
    ui_kit = _read(FAMILY_SKILLS["ui-kit"])
    assert "they cover both the\n   image style and the UI visual language" in ui_kit
    # The theme plan resolves the rules for one request; it is not a style store.
    assert "it is a production artifact, never a reusable\n   style source" in ui_kit
    card_kit = _read(FAMILY_SKILLS["card-kit"])
    assert "they cover both the image style\nand the UI visual language" in card_kit


# ---------------------------------------------------------------------------
# AC-04: conflict disposition
# ---------------------------------------------------------------------------

def test_conflict_disposition_documents_exactly_three_named_outcomes():
    body = _section(_read(PLANNER), "Reference Conflict Disposition")
    for disposition in DISPOSITIONS:
        assert f"`{disposition}`" in body, disposition
    # Ordered, numbered, one disposition each — no fourth escape hatch.
    assert [
        line.split("`")[1]
        for line in body.splitlines()
        if re.match(r"^\d+\. `", line)
    ] == list(DISPOSITIONS)


def test_only_an_unselected_candidate_may_be_dropped():
    body = _section(_read(PLANNER), "Reference Conflict Disposition")
    excluded = body.split("`excluded_candidate`", 1)[1].split("3. `blocker`", 1)[0]
    assert "a candidate that is in no request yet" in excluded
    assert "`excluded_reference`" in excluded
    assert "the conflicting section heading" in excluded
    assert "This is the only case where a conflicting\n   reference may be dropped." in excluded


def test_request_user_and_binding_references_conflict_into_a_locatable_blocker():
    body = _section(_read(PLANNER), "Reference Conflict Disposition")
    blocker = body.split("3. `blocker`", 1)[1]
    assert "already in `request.references`" in blocker
    assert "named by the user" in blocker
    assert "required by a family binding" in blocker
    assert "Keep it in the\n   request" in blocker
    # Locatable: role, path, and the conflicting heading.
    assert "naming the reference role\n   and path plus the `DESIGN.md` section heading" in blocker
    assert "Never silently drop it,\n   downgrade its role, or let it override the rule." in blocker


def test_producer_never_drops_a_supplied_reference():
    text = _read(PRODUCER)
    tail = text.split("## Prompt Rules", 1)[1].split("## Report Format", 1)[0]
    assert "stop the unit\nand report a blocker naming the reference role, its path" in tail
    assert "section heading it contradicts" in tail
    assert (
        "Never drop, reweight, or downgrade a reference\nthe brief supplied, a user "
        "named, or a family binding requires" in tail
    )
    assert "candidate\nexclusion is the planner's decision, not yours" in tail


@pytest.mark.parametrize("family", sorted(FAMILY_SKILLS))
def test_every_family_skill_stops_on_a_reference_rule_contradiction(family):
    text = _read(FAMILY_SKILLS[family]).lower()
    assert "contradict" in text, f"{family} must state the contradiction outcome"
    assert "stop" in text or "blocker" in text, family


def test_shared_contract_makes_a_contradiction_a_stop():
    body = _section(_read(SHARED_CONTRACT), "Request")
    assert "the request is\ncontradictory: STOP with a blocker naming the reference role" in body
    assert "Silently following either side is not a valid result." in body


# ---------------------------------------------------------------------------
# AC-06: DESIGN.md is the one visual document the asset stage reads
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path", ASSET_STAGE_DOCS, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_asset_stage_docs_name_no_second_visual_document(path):
    """A visual document other than DESIGN.md is a second style source."""
    named = set(PROJECT_DOC.findall(_read(path)))
    unexpected = named - KNOWN_NON_VISUAL_DOCS
    assert unexpected <= {"DESIGN.md"}, (
        f"{path.name} names another project visual document: {sorted(unexpected)}"
    )


def test_planner_and_manager_read_only_design_for_visual_rules():
    planner = _section(_read(PLANNER), "Visual Authority")
    assert "the only visual document the asset stage reads" in planner
    assert "that file is closed history" in planner
    assert (
        "never let its text enter a brief, a prompt, a reference\nselection, or provenance"
        in planner
    )
    assert "Read only `DESIGN.md` for visual rules" in _read(MANAGER)


def test_analyst_dispatch_states_the_inverted_authority():
    body = _section(_read(ANALYST_DISPATCH), "Analyze User-Provided Assets")
    assert "DESIGN.md is the project's visual specification authority." in body
    assert "visual\n  conditioning" in body
    assert "never\n  outrank, extend, or replace a DESIGN.md rule" in body
    assert "is closed history" in body


# ---------------------------------------------------------------------------
# AC-07: the mechanical attachment contract is unchanged
# ---------------------------------------------------------------------------

def test_reference_roles_agree_across_schema_checker_and_generator():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import asset_source_generate  # noqa: PLC0415
        from asset_skill_contract_check import REFERENCE_ROLES  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    schema = json.loads(_read(REQUEST_SCHEMA))
    roles = set(
        schema["properties"]["references"]["items"]["properties"]["role"]["enum"]
    )
    assert roles == set(REFERENCE_ROLES) == asset_source_generate.REFERENCE_ROLES
    # The planner assigns exactly these roles, no new vocabulary.
    planner = _section(_read(PLANNER), "Reference Conflict Disposition")
    for role in roles:
        assert f"`{role}`" in planner

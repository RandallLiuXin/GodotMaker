"""Workflow-level checks for the GDD audit loop (current-tag-scoped;
Pass 1 always runs, Pass 2 is conditional on Pass 1's findings).

Validates that the contract between game-planner SKILL.md (the dispatcher) and
agents/gdd-auditor.md (the sub-agent) stays intact across edits to either side.
The frontmatter check in test_agents.py only proves the agent file parses;
this file proves the surrounding workflow still wires up correctly.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GAME_PLANNER = REPO_ROOT / "skills" / "core" / "game-planner" / "SKILL.md"
GDD_AUDITOR = REPO_ROOT / "agents" / "gdd-auditor.md"


def _planner_text():
    return GAME_PLANNER.read_text(encoding="utf-8")


def _auditor_text():
    return GDD_AUDITOR.read_text(encoding="utf-8")


def test_game_planner_dispatches_gdd_auditor():
    """Both audit rounds must keep their gdd-auditor dispatch block in the
    doc. Pass 1 runs unconditionally and Pass 2 is conditional, but both
    blocks must stay present — this counts textual dispatch blocks, not
    runtime invocations. A missing block means a round was deleted, not gated."""
    text = _planner_text()
    dispatch_count = len(re.findall(r'subagent_type:\s*"gdd-auditor"', text))
    assert dispatch_count >= 2, (
        f"Expected at least 2 gdd-auditor dispatches in game-planner SKILL.md "
        f"(Round 6 + Round 7), found {dispatch_count}."
    )


def test_game_planner_uses_auditor_model_from_config():
    """Both dispatches must read auditor_model from config rather than
    hardcoding a model — otherwise users can't override it."""
    text = _planner_text()
    refs = re.findall(r"auditor_model from \.godotmaker/config\.yaml", text)
    assert len(refs) >= 2, (
        f"Expected both audit dispatches to reference auditor_model from config, "
        f"found {len(refs)} reference(s)."
    )


def test_game_planner_has_two_audit_rounds():
    """Round 6 and Round 7 must both exist as headings — Pass 1 (always) and
    Pass 2 (conditional) are the user-readable names of the audit phase."""
    text = _planner_text()
    assert re.search(r"###\s*Round\s*6\s*[—-]\s*Audit Pass 1", text), (
        "Round 6 audit heading missing from game-planner SKILL.md"
    )
    assert re.search(r"###\s*Round\s*7\s*[—-]\s*Audit Pass 2", text), (
        "Round 7 audit heading missing from game-planner SKILL.md"
    )


def test_round_7_marks_previously_asked_as_mandatory():
    """The `Previously Asked` field is what stops Round 7 from re-asking
    Round 6's questions. Without a MUST-populate marker the planner can
    legitimately read the prompt as 'optional' and skip it."""
    text = _planner_text()
    # Find the Round 7 section and confirm it contains both the field name
    # and a strong-emphasis MUST-populate instruction nearby.
    round_7_match = re.search(
        r"###\s*Round\s*7.*?(?=###\s*Round\s*8|\Z)", text, re.DOTALL
    )
    assert round_7_match, "Round 7 section not found"
    round_7 = round_7_match.group(0)
    assert "Previously Asked" in round_7, (
        "Round 7 must reference the `Previously Asked` field"
    )
    assert re.search(r"\*\*You MUST populate.*Previously Asked", round_7), (
        "Round 7 must mark `Previously Asked` as MUST-populate (bold), "
        "otherwise the auditor re-asks Round 6's questions in fresh context."
    )


def test_gdd_auditor_prohibits_repeating_previously_asked():
    """The auditor side of the contract: even if the planner accidentally
    leaks duplicates, the auditor must refuse to re-ask them."""
    text = _auditor_text()
    prohibitions_match = re.search(
        r"##\s*Absolute Prohibitions(.*?)(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE
    )
    assert prohibitions_match, "gdd-auditor.md must declare Absolute Prohibitions"
    prohibitions = prohibitions_match.group(1)
    assert "Previously Asked" in prohibitions, (
        "gdd-auditor.md prohibitions must explicitly reference the "
        "`Previously Asked` field — otherwise the no-repeat contract is implicit only."
    )


def test_gdd_auditor_brief_format_documents_previously_asked():
    """Brief Format must document the field shape so the planner knows
    how to populate it. If the field name drifts here it must drift in
    game-planner too — caught by the previous test."""
    text = _auditor_text()
    # Anchor on the next real section heading (Report Format) rather than the
    # generic `## ` so we don't stop inside the code-fenced example brief.
    brief_match = re.search(
        r"##\s*Brief Format.*?(?=##\s+Report Format)", text, re.DOTALL
    )
    assert brief_match, "gdd-auditor.md must document a Brief Format section"
    brief = brief_match.group(0)
    assert "Previously Asked" in brief, (
        "Brief Format must list `Previously Asked` as a brief field"
    )
    assert "Iteration" in brief, "Brief Format must list `Iteration` as a brief field"
    assert "GDD Path" in brief, "Brief Format must list `GDD Path` as a brief field"


def test_pass_2_is_conditional():
    """Round 7 (Pass 2) must be gated on a trigger derived from Pass 1's
    findings — not an unconditional second pass. The trigger keeps simple /
    already-clear tag scopes from being over-audited while preserving the
    independent-review safety net for the rounds that actually need it."""
    text = _planner_text()
    round_7_match = re.search(
        r"###\s*Round\s*7.*?(?=###\s*Round\s*8|\Z)", text, re.DOTALL
    )
    assert round_7_match, "Round 7 section not found"
    round_7 = round_7_match.group(0)
    assert "conditional" in round_7.lower(), (
        "Round 7 must be marked conditional, not an unconditional second pass."
    )
    assert re.search(r"only if", round_7, re.IGNORECASE), (
        "Round 7 must state the trigger condition (e.g. 'Run Pass 2 only if ...')."
    )
    assert "contradiction" in round_7.lower(), (
        "Round 7 trigger must reference contradictions surfaced by Pass 1."
    )


def test_audit_briefs_carry_current_tag_scope():
    """Both audit briefs must pass the current tag's scope so the auditor
    constrains findings to the tag being planned, not the whole cross-tag GDD."""
    text = _planner_text()
    count = text.count("Current Tag Scope")
    assert count >= 2, (
        "Both Round 6 and Round 7 audit briefs must include a `Current Tag Scope` "
        f"field; found {count}."
    )


def test_gdd_auditor_scopes_to_current_tag():
    """The auditor must declare that it audits only the current tag's scope
    and document the scope fields in its brief — otherwise it re-audits the
    whole cross-tag GDD and re-litigates already-shipped tags."""
    text = _auditor_text()
    assert "Audit Scope" in text, (
        "gdd-auditor.md must declare an `Audit Scope` section limiting it to the current tag."
    )
    assert "Current Tag Scope" in text, (
        "gdd-auditor.md Brief Format must document the `Current Tag Scope` field."
    )


def test_gdd_auditor_has_no_question_floor():
    """The auditor must have no lower bound on question count — a clear,
    complete tag scope should yield zero questions instead of a manufactured
    5-8. Only the upper cap of 8 remains."""
    text = _auditor_text()
    assert "5-8" not in text, (
        "gdd-auditor.md still mandates a 5-8 question floor; the lower bound must be removed."
    )
    assert "0-8" in text, (
        "gdd-auditor.md should express the question count as 0-8 (upper bound only)."
    )
    assert re.search(r"no floor|no minimum|return zero", text, re.IGNORECASE), (
        "gdd-auditor.md must explicitly allow zero questions when the scope is complete."
    )

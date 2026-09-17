#!/usr/bin/env python3
"""Turn the project `DESIGN.md` visual contract into rule-level visual checks.

`/gm-evaluate` judges generated assets and final scenes against the rules the
project actually wrote down, not against how closely a screenshot resembles a
reference image. This tool owns the deterministic half of that judgement:

0. ``subject-for``    - map an Asset Skill family to its subject class.
1. ``rules``          - split `DESIGN.md` into individually addressable rules.
2. ``build-request``  - pick the rules that apply to one subject and emit the
                        request a visual-qa Question-mode call is built from.
3. ``grade``          - map the per-rule verdicts a VQA backend returned onto
                        dispositions, severities, and the scene result.

The split matters. A VLM supplies observation (`verdict`, `evidence`,
`confidence`); it never decides what blocks a tag. Blocking is a property of
the rule text — `Don't` entries, literal `MUST` / `MUST NOT`, and rules the
author explicitly marked required — combined with the reported confidence, and
that mapping lives here so it stays auditable and identical across runs.

A migrated project's legacy visual seed file is never read. When one still
sits next to `DESIGN.md`, its text cannot reach a request: the only input is
the DESIGN path, and the preserved `Legacy Style Notes` section is excluded
from rule extraction.

Usage:
    python tools/design_rules.py subject-for character-bundle
    python tools/design_rules.py rules --design DESIGN.md [--subject ui]
    python tools/design_rules.py build-request --design DESIGN.md \
        --subject mixed --name scene_battle \
        --capture e2e/screenshots/scene_battle.png \
        [--project-root .] \
        --requirement "Player sprite visible centered-left" \
        [--reference references/scene_battle.png] \
        [--output .godotmaker/design-checks/scene_battle-request.json]
    python tools/design_rules.py grade --request <request.json> \
        --findings <findings.json> [--output <graded.json>]
    python tools/design_rules.py grade --request <request.json> \
        --backend-error "gemini: 503 unavailable"

Exit codes:
    0  succeeded
    1  input file missing or unreadable
    2  bad CLI usage or an invalid request/findings payload
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUEST_SCHEMA = "gm-design-rule-check/v1"
RESULT_SCHEMA = "gm-design-rule-result/v1"

DESIGN_FILE = "DESIGN.md"

# Sections that carry rules. `Legacy Style Notes` deliberately does not: it is
# the verbatim body of a removed legacy seed file, kept as history only.
IDENTITY_HEADING = "Visual Identity"
IMAGE_STYLE_HEADING = "Image Style"
UI_HEADING = "UI Visual Language"
DO_HEADING = "Do"
DONT_HEADING = "Don't"
LEGACY_HEADING = "Legacy Style Notes"

UI_NA_SENTENCE = "N/A - this project has no visible UI."

# What the capture shows. Drives which rule groups can be observed at all.
SUBJECT_CLASSES = ("character", "environment", "effect", "ui", "mixed")

# Asset family -> subject class, so `/gm-asset` never guesses what a produced
# sheet shows. Every first-class Asset Skill family appears exactly once; a new
# family without an entry is caught by the contract tests, not silently
# defaulted into the wrong rule set.
ASSET_SUBJECT_CLASSES = {
    "character-bundle": "character",
    "background-map": "environment",
    "platform-strip": "environment",
    "scene-prop-set": "environment",
    "compact-prop-pack": "environment",
    "tileset": "environment",
    "fx-bundle": "effect",
    "ui-kit": "ui",
    "card-kit": "ui",
    # A screen reference is a whole composed screen: world content and UI.
    "screen-reference": "mixed",
}

# Rule group -> subject classes where the group is observable. A group absent
# from a class is reported `not_applicable`, never silently dropped: the audit
# trail has to show the rule was considered.
GROUP_APPLICABILITY = {
    "identity": set(SUBJECT_CLASSES),
    "d1": set(SUBJECT_CLASSES),
    "d2": set(SUBJECT_CLASSES),
    "d3": set(SUBJECT_CLASSES),
    "d4": set(SUBJECT_CLASSES),
    "d5": set(SUBJECT_CLASSES),
    # Lighting and cast shadows are a property of rendered art, not of a flat
    # UI layer judged on its own.
    "d6": {"character", "environment", "effect", "mixed"},
    # Perspective and depth need a staged space; an isolated character or
    # effect sheet and a UI-only capture have none.
    "d7": {"environment", "mixed"},
    # An isolated character or effect sheet has no scene composition to judge.
    "d8": {"environment", "ui", "mixed"},
    "d9": set(SUBJECT_CLASSES),
    "ui": {"ui", "mixed"},
    "do": set(SUBJECT_CLASSES),
    "dont": set(SUBJECT_CLASSES),
}

NA_REASONS = {
    "d6": "lighting and shadow are not observable in a UI-only capture",
    "d7": "no staged space or depth cue is present in this capture",
    "d8": "no scene composition is present in an isolated subject capture",
    "ui": "this capture shows no UI surface",
}

VERDICTS = ("pass", "fail", "uncertain", "not_applicable")
CONFIDENCES = ("high", "medium", "low")
REQUIREMENTS = ("required", "normal")
DISPOSITIONS = ("pass", "blocking", "non_blocking", "human_review", "not_applicable")
SEVERITIES = ("blocker", "major", "minor", "none")

# A rule is required only when the author said so in the rule text itself, or
# by writing it as a prohibition. Everything else — including every ordinary
# `Do` entry and every ordinary dimension bullet — is advisory.
REQUIRED_LITERALS = re.compile(r"\b(MUST NOT|MUST|REQUIRED|MANDATORY)\b")

HEADING_RE = re.compile(r"^(#{2,3})\s+(.*?)\s*$")
DIMENSION_RE = re.compile(r"^(\d+)\.\s+(.*)$")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$")


class DesignError(Exception):
    """A DESIGN.md or payload problem the caller has to fix."""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _strip_comments(text: str) -> str:
    return HTML_COMMENT_RE.sub("", text)


def _is_authored(line: str) -> bool:
    """False for template placeholders like `{principle}` or `{unspecified}`."""
    stripped = line.strip()
    if not stripped:
        return False
    return not PLACEHOLDER_RE.match(stripped)


def _split_sections(text: str) -> list[tuple[str, str, list[str]]]:
    """Return `(level, heading, body_lines)` for every `##`/`###` section.

    Fenced blocks are skipped so a preserved legacy seed body cannot
    introduce phantom headings.
    """
    sections: list[tuple[str, str, list[str]]] = []
    current: tuple[str, str, list[str]] | None = None
    fence: str | None = None

    for line in _strip_comments(text).splitlines():
        fence_match = FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            if current is not None:
                current[2].append(line)
            continue
        if fence is not None:
            if current is not None:
                current[2].append(line)
            continue

        heading = HEADING_RE.match(line)
        if heading:
            if current is not None:
                sections.append(current)
            current = (heading.group(1), heading.group(2), [])
            continue
        if current is not None:
            current[2].append(line)

    if current is not None:
        sections.append(current)
    return sections


def _principle(body: list[str]) -> str:
    """First authored non-bullet paragraph line of a section."""
    for line in body:
        if BULLET_RE.match(line):
            break
        if _is_authored(line):
            return line.strip()
    return ""


def _bullets(body: list[str]) -> list[str]:
    out = []
    for line in body:
        match = BULLET_RE.match(line)
        if match and _is_authored(match.group(1)):
            out.append(match.group(1).strip())
    return out


def _requirement_for(group: str, text: str) -> str:
    if group == "dont":
        return "required"
    return "required" if REQUIRED_LITERALS.search(text) else "normal"


def _rule(group: str, rule_id: str, source: str, text: str) -> dict:
    return {
        "rule_id": rule_id,
        "group": group,
        "source": source,
        "text": text,
        "requirement": _requirement_for(group, text),
    }


def extract_rules(design_text: str) -> list[dict]:
    """Split an authored `DESIGN.md` into individually addressable rules.

    Unfilled `{placeholder}` lines produce no rule — an unwritten section is
    simply not evaluated, which is what "leave anything unknown unspecified"
    has to mean downstream.
    """
    rules: list[dict] = []
    dimension_index: int | None = None
    section = None

    for level, heading, body in _split_sections(design_text):
        if level == "##":
            if heading == LEGACY_HEADING:
                # History only. Never a rule source, whatever it contains.
                break
            section = heading
            dimension_index = None

        if level == "##" and heading == IDENTITY_HEADING:
            identity = " ".join(
                line.strip() for line in body if _is_authored(line)
            ).strip()
            if identity:
                rules.append(
                    _rule("identity", "identity", f"{DESIGN_FILE} > {IDENTITY_HEADING}", identity)
                )
            continue

        if level == "###" and section == IMAGE_STYLE_HEADING:
            match = DIMENSION_RE.match(heading)
            if not match:
                continue
            dimension_index = int(match.group(1))
            group = f"d{dimension_index}"
            source = f"{DESIGN_FILE} > {IMAGE_STYLE_HEADING} > {heading}"
            principle = _principle(body)
            if principle:
                rules.append(_rule(group, f"{group}.principle", source, principle))
            for index, bullet in enumerate(_bullets(body), start=1):
                rules.append(_rule(group, f"{group}.r{index}", source, bullet))
            continue

        if level == "##" and heading == UI_HEADING:
            authored = [line.strip() for line in body if _is_authored(line)]
            if any(UI_NA_SENTENCE in line for line in authored):
                # The project declared it has no visible UI. No UI rules exist.
                continue
            source = f"{DESIGN_FILE} > {UI_HEADING}"
            principle = _principle(body)
            if principle:
                rules.append(_rule("ui", "ui.principle", source, principle))
            for index, bullet in enumerate(_bullets(body), start=1):
                rules.append(_rule("ui", f"ui.r{index}", source, bullet))
            continue

        if level == "##" and heading in (DO_HEADING, DONT_HEADING):
            group = "do" if heading == DO_HEADING else "dont"
            source = f"{DESIGN_FILE} > {heading}"
            for index, bullet in enumerate(_bullets(body), start=1):
                rules.append(_rule(group, f"{group}.r{index}", source, bullet))
            continue

    return rules


def applicability(group: str, subject_class: str) -> tuple[bool, str]:
    """`(applicable, na_reason)` for one rule group against one subject."""
    allowed = GROUP_APPLICABILITY.get(group)
    if allowed is None:
        raise DesignError(f"unknown rule group: {group!r}")
    if subject_class in allowed:
        return True, ""
    return False, NA_REASONS.get(group, f"{group} is not observable for a {subject_class} capture")


# ---------------------------------------------------------------------------
# Capture paths
# ---------------------------------------------------------------------------

RES_PREFIX = "res://"


def resolve_capture(value: str) -> str:
    """Map one declared image path to a project-root-relative POSIX path.

    An Asset Skill result states its paths as Godot resource paths
    (`res://assets/generated/...png`). A VQA backend reads files, not Godot
    resources, so a `res://` value handed straight to visual-qa fails its
    existence check before any model call — which would then look like a
    backend outage and reject a perfectly good asset.

    Both callers already run from the project root, so a relative POSIX path is
    what visual-qa can actually open, and it stays portable in the audit.
    """
    raw = (value or "").strip()
    if not raw:
        raise DesignError("capture path must be non-empty")

    remainder = raw[len(RES_PREFIX):] if raw.startswith(RES_PREFIX) else raw
    # Both forms funnel through one guard. Splitting them was how a drive
    # letter smuggled inside a `res://` value skipped the absolute-path check.
    normalised = remainder.replace("\\", "/")
    if normalised.startswith("/"):
        # A rooted path, or the `res:///` form the asset contract rejects.
        # Reinterpreting it as project-relative would quietly change which
        # file is read, so it is an error rather than a silent rewrite.
        raise DesignError(
            f"path {raw!r} must be project-relative, not rooted at '/'"
        )
    # `.` is a no-op segment; `..` is the one that walks out.
    segments = [s for s in normalised.split("/") if s not in ("", ".")]
    if not segments:
        raise DesignError(
            f"invalid path {raw!r}: expected a relative path to an image"
        )

    for segment in segments:
        if segment == "..":
            raise DesignError(
                f"path {raw!r} must stay inside the project: "
                "'..' segments are not allowed"
            )
        if ":" in segment:
            # `C:/...` as a whole path or hidden after res://, and NTFS
            # alternate data streams (`sheet.png:secret`). Neither is a
            # project-relative image path.
            raise DesignError(
                f"path {raw!r} must be project-relative: the segment "
                f"{segment!r} names a drive or stream"
            )
    return "/".join(segments)


def _contained(project_root: Path, target: str) -> Path:
    """Resolve `target` under `project_root`, refusing anything outside it.

    The string guards above already reject the obvious escapes; this is the
    check that cannot be argued with, and it also catches a symlink inside the
    project that points somewhere else.
    """
    root = project_root.resolve()
    resolved = (root / target).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise DesignError(
            f"path {target!r} resolves to {resolved}, which is outside the "
            f"project root {root}. Captures are project files only."
        ) from None
    return resolved


def _resolved_paths(
    values: list[str],
    *,
    project_root: Path | None,
    label: str,
    require_existing: bool,
) -> tuple[list[str], list[str]]:
    """`(resolved, originals)` for a list of declared image paths."""
    resolved: list[str] = []
    for value in values:
        target = resolve_capture(value)
        if project_root is not None:
            # Containment is checked for every path, existing or not: a
            # reference is quoted into the prompt, so it must be a project
            # path too.
            on_disk = _contained(project_root, target)
            if require_existing and not on_disk.is_file():
                raise DesignError(
                    f"{label} {value!r} resolves to {target!r}, which does not "
                    f"exist under {project_root.resolve()}. This is a problem "
                    "with the asset or the capture, not a visual-qa backend "
                    "error - do not grade it as one."
                )
        resolved.append(target)
    return resolved, [v.strip() for v in values]


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------

def build_request(
    design_text: str,
    *,
    subject_name: str,
    subject_class: str,
    subject_kind: str = "scene",
    captures: list[str] | None = None,
    requirements: list[str] | None = None,
    references: list[str] | None = None,
    project_root: Path | None = None,
) -> dict:
    """Build the deterministic request behind one visual-qa Question call.

    Captures may be given as Godot resource paths (`res://...`) exactly as an
    Asset Skill result states them; they are resolved to project-relative paths
    visual-qa can open, and the declared originals are kept for the audit.
    Pass `project_root` to also require every capture to exist — the CLI always
    does, so a missing image fails here rather than surfacing later as a fake
    backend error.

    `references` are recorded as provenance context only. Overall resemblance
    to a reference is never a criterion: two captures in the same visual
    language with different compositions both pass, and copying a reference's
    composition does not excuse a rule violation.
    """
    if subject_class not in SUBJECT_CLASSES:
        raise DesignError(
            f"subject class must be one of {list(SUBJECT_CLASSES)}, got {subject_class!r}"
        )
    if not subject_name:
        raise DesignError("subject name is required")
    declared_captures = list(captures or [])
    if not declared_captures:
        raise DesignError("at least one capture is required")
    resolved_captures, capture_resources = _resolved_paths(
        declared_captures,
        project_root=project_root,
        label="capture",
        require_existing=True,
    )
    # A reference is only named in the prompt, never opened, so it is shape-
    # checked but not required to exist.
    resolved_references, reference_resources = _resolved_paths(
        list(references or []),
        project_root=project_root,
        label="reference",
        require_existing=False,
    )

    rules = []
    for rule in extract_rules(design_text):
        applicable, na_reason = applicability(rule["group"], subject_class)
        entry = dict(rule, applicable=applicable)
        if not applicable:
            entry["na_reason"] = na_reason
        rules.append(entry)

    return {
        "schema": REQUEST_SCHEMA,
        "design_source": DESIGN_FILE,
        "subject": {
            "name": subject_name,
            "class": subject_class,
            "kind": subject_kind,
        },
        # What visual-qa is handed, and what the producer declared.
        "captures": resolved_captures,
        "capture_resources": capture_resources,
        "content_requirements": list(requirements or []),
        "reference_provenance": resolved_references,
        "reference_resources": reference_resources,
        "rules": rules,
    }


def _wrap(prefix: str, text: str) -> str:
    return f"{prefix}{text}"


def render_question(request: dict) -> str:
    """Render the request as the `--question` string for visual-qa."""
    subject = request["subject"]
    lines = [
        f"Judge this {subject['kind']} capture rule by rule against the project "
        f"{DESIGN_FILE} visual contract. Subject: {subject['name']} "
        f"(class: {subject['class']}).",
        "",
        "Design rules - answer every one of them:",
    ]
    for rule in request["rules"]:
        if rule["applicable"]:
            lines.append(
                f"- [{rule['rule_id']}] ({rule['requirement']}) {rule['text']}"
            )
        else:
            lines.append(
                f"- [{rule['rule_id']}] N/A - {rule['na_reason']}"
            )

    requirements = request.get("content_requirements") or []
    if requirements:
        lines += ["", "Scene content requirements - verify these independently:"]
        lines += [_wrap("- ", item) for item in requirements]

    references = request.get("reference_provenance") or []
    if references:
        lines += [
            "",
            "Reference provenance (context only, never a criterion): "
            + ", ".join(references),
        ]

    lines += [
        "",
        "For every applicable rule report: verdict (pass | fail | uncertain), "
        "the observable evidence in the capture, confidence (high | medium | "
        "low), and which capture you read it from. Report N/A rules as "
        "not_applicable. Do not judge overall similarity to any reference "
        "image, and do not assign severity - severity is derived from the rule "
        "text, not from your opinion.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def classify(
    verdict: str,
    requirement: str,
    confidence: str,
    *,
    evidence_conflict: bool = False,
) -> tuple[str, str]:
    """`(disposition, severity)` for one observed rule verdict.

    The whole blocking policy is this function:

    - only a high-confidence failure of a required rule blocks;
    - an ordinary `Do` entry or ordinary dimension deviation is reported and
      never blocks;
    - `uncertain`, conflicting evidence, and low-confidence suspected
      violations of required rules go to a human — never silently to PASS and
      never to a hard fail.
    """
    if verdict not in VERDICTS:
        raise DesignError(f"verdict must be one of {list(VERDICTS)}, got {verdict!r}")
    if requirement not in REQUIREMENTS:
        raise DesignError(
            f"requirement must be one of {list(REQUIREMENTS)}, got {requirement!r}"
        )
    if verdict == "not_applicable":
        return "not_applicable", "none"
    if confidence not in CONFIDENCES:
        raise DesignError(
            f"confidence must be one of {list(CONFIDENCES)}, got {confidence!r}"
        )

    if verdict == "pass":
        # Conflicting evidence means the backend saw the rule both ways; that
        # is not a pass, whoever reported it as one.
        return ("human_review", "major") if evidence_conflict else ("pass", "none")

    if verdict == "uncertain" or evidence_conflict:
        return "human_review", "major" if requirement == "required" else "minor"

    # verdict == "fail"
    if requirement == "required":
        if confidence == "high":
            return "blocking", "blocker"
        return "human_review", "major"
    return "non_blocking", "major" if confidence == "high" else "minor"


def scene_result(findings: list[dict]) -> str:
    """`fail` / `warning` / `pass` for one subject's graded findings."""
    dispositions = {finding["disposition"] for finding in findings}
    if "blocking" in dispositions:
        return "fail"
    if "human_review" in dispositions:
        return "warning"
    if any(
        finding["disposition"] == "non_blocking" and finding["severity"] == "major"
        for finding in findings
    ):
        return "warning"
    return "pass"


def _validate_request(request: dict) -> None:
    if request.get("schema") != REQUEST_SCHEMA:
        raise DesignError(f"request schema must be {REQUEST_SCHEMA!r}")
    if not isinstance(request.get("rules"), list):
        raise DesignError("request.rules must be a list")


def grade(
    request: dict,
    findings: list[dict],
    *,
    backend_error: str | None = None,
) -> dict:
    """Apply the blocking policy to the verdicts a VQA backend reported.

    A backend error is a result, not an absence of one: it rejects, because a
    visual contract that was never actually checked must not read as checked.
    """
    _validate_request(request)
    subject = request.get("subject", {})
    base = {
        "schema": RESULT_SCHEMA,
        "subject": subject,
        "captures": list(request.get("captures") or []),
        "design_source": request.get("design_source", DESIGN_FILE),
        "findings": [],
        "result": "fail",
        "human_review_required": False,
        "observational_na": [],
        "critical_issues": [],
        "major_issues": [],
        "minor_issues": [],
    }

    if backend_error:
        base["backend_error"] = backend_error
        base["critical_issues"] = [
            f"visual-qa backend error for {subject.get('name', '<subject>')}: "
            f"{backend_error}"
        ]
        return base

    by_id = {rule["rule_id"]: rule for rule in request["rules"]}
    if len(by_id) != len(request["rules"]):
        raise DesignError("request.rules contains duplicate rule_id values")

    seen: set[str] = set()
    graded: list[dict] = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise DesignError(f"findings[{index}] must be an object")
        rule_id = finding.get("rule_id")
        rule = by_id.get(rule_id)
        if rule is None:
            raise DesignError(f"findings[{index}] names unknown rule_id {rule_id!r}")
        if rule_id in seen:
            raise DesignError(f"findings[{index}] repeats rule_id {rule_id!r}")
        seen.add(rule_id)

        verdict = finding.get("verdict")
        if not rule["applicable"] and verdict != "not_applicable":
            raise DesignError(
                f"rule {rule_id!r} is not applicable to a "
                f"{subject.get('class')!r} capture; verdict must be "
                f"'not_applicable', got {verdict!r}"
            )
        observational_na = False
        if rule["applicable"] and verdict == "not_applicable":
            # The rule group fits the subject but this particular capture does
            # not show what the rule talks about. Allowed, but it has to say
            # why: an unexplained N/A is how a contract quietly stops being
            # checked.
            if not (finding.get("na_reason") or "").strip():
                raise DesignError(
                    f"rule {rule_id!r} applies to this capture; reporting it "
                    "'not_applicable' requires a na_reason"
                )
            observational_na = True

        evidence = (finding.get("evidence") or "").strip()
        if verdict in ("fail", "uncertain") and not evidence:
            raise DesignError(
                f"rule {rule_id!r} reported {verdict!r} without observable evidence"
            )

        confidence = finding.get("confidence", "high")
        conflict = bool(finding.get("evidence_conflict"))
        disposition, severity = classify(
            verdict,
            rule["requirement"],
            confidence,
            evidence_conflict=conflict,
        )

        entry = {
            "rule_id": rule_id,
            "group": rule["group"],
            "source": rule["source"],
            "rule_text": rule["text"],
            "requirement": rule["requirement"],
            "verdict": verdict,
            "evidence": evidence,
            "confidence": None if verdict == "not_applicable" else confidence,
            "evidence_conflict": conflict,
            "disposition": disposition,
            "severity": severity,
            "captures": list(finding.get("captures") or base["captures"]),
        }
        if not rule["applicable"]:
            entry["na_reason"] = rule.get("na_reason", "")
        elif observational_na:
            entry["na_reason"] = finding["na_reason"].strip()
            entry["observational_na"] = True

        override = finding.get("override")
        if override is not None:
            entry.update(_apply_override(rule_id, override, entry))
        graded.append(entry)

    missing = sorted(set(by_id) - seen)
    if missing:
        raise DesignError(f"findings omit rules: {missing}")

    base["findings"] = graded
    base["result"] = scene_result(graded)
    base["human_review_required"] = any(
        finding["disposition"] == "human_review" for finding in graded
    )
    base["observational_na"] = [
        f["rule_id"] for f in graded if f.get("observational_na")
    ]
    base["critical_issues"] = [_issue(f) for f in graded if f["severity"] == "blocker"]
    base["major_issues"] = [_issue(f) for f in graded if f["severity"] == "major"]
    base["minor_issues"] = [_issue(f) for f in graded if f["severity"] == "minor"]
    return base


def _apply_override(rule_id: str, override: object, entry: dict) -> dict:
    """Record an explicit human decision over a derived disposition.

    Only a human can do this, and only with a reason. It exists so a person can
    resolve an `uncertain` or contest a blocker — the machine never promotes or
    demotes a finding on its own.
    """
    if not isinstance(override, dict):
        raise DesignError(f"rule {rule_id!r} override must be an object")
    if override.get("by") != "human":
        raise DesignError(f"rule {rule_id!r} may only be overridden by a human")
    disposition = override.get("disposition")
    if disposition not in DISPOSITIONS:
        raise DesignError(
            f"rule {rule_id!r} override disposition must be one of "
            f"{list(DISPOSITIONS)}, got {disposition!r}"
        )
    reason = (override.get("reason") or "").strip()
    if not reason:
        raise DesignError(f"rule {rule_id!r} override requires a reason")
    severity = override.get("severity")
    if severity is None:
        severity = {
            "blocking": "blocker",
            "human_review": "major",
            "non_blocking": "minor",
            "pass": "none",
            "not_applicable": "none",
        }[disposition]
    if severity not in SEVERITIES:
        raise DesignError(
            f"rule {rule_id!r} override severity must be one of {list(SEVERITIES)}"
        )
    return {
        "disposition": disposition,
        "severity": severity,
        "override": {
            "by": "human",
            "reason": reason,
            "from_disposition": entry["disposition"],
            "from_severity": entry["severity"],
        },
    }


def _issue(finding: dict) -> str:
    return (
        f"{finding['rule_id']} [{finding['requirement']}] {finding['verdict']} "
        f"(confidence: {finding['confidence']}) - {finding['rule_text']} - "
        f"{finding['evidence']}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(1)


def _read_json(path: Path):
    text = _read_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"Error: {path} is not valid JSON: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _emit(payload, output: str | None) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"Wrote {target}")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    subject = sub.add_parser(
        "subject-for", help="print the subject class for an Asset Skill family"
    )
    subject.add_argument("asset_type")

    listing = sub.add_parser("rules", help="list the rules DESIGN.md declares")
    listing.add_argument("--design", default=DESIGN_FILE)
    listing.add_argument("--subject", choices=SUBJECT_CLASSES)
    listing.add_argument("--output")

    request = sub.add_parser("build-request", help="build one rule-check request")
    request.add_argument("--design", default=DESIGN_FILE)
    request.add_argument("--subject", choices=SUBJECT_CLASSES, required=True)
    request.add_argument("--name", required=True)
    request.add_argument("--kind", default="scene")
    request.add_argument("--capture", action="append", default=[])
    request.add_argument("--requirement", action="append", default=[])
    request.add_argument(
        "--reference",
        action="append",
        default=[],
        help="provenance context only; never a similarity criterion",
    )
    request.add_argument(
        "--project-root",
        default=".",
        help="root the captures are resolved against and checked for existence",
    )
    request.add_argument("--question", action="store_true", help="print the question text")
    request.add_argument("--output")

    grading = sub.add_parser("grade", help="apply the blocking policy to VQA verdicts")
    grading.add_argument("--request", required=True)
    grading.add_argument("--findings")
    grading.add_argument("--backend-error")
    grading.add_argument("--output")

    args = parser.parse_args(argv)

    try:
        if args.command == "subject-for":
            subject_class = ASSET_SUBJECT_CLASSES.get(args.asset_type)
            if subject_class is None:
                raise DesignError(
                    f"no subject class for asset family {args.asset_type!r}; "
                    f"known families: {sorted(ASSET_SUBJECT_CLASSES)}"
                )
            sys.stdout.write(subject_class + "\n")
            return 0

        if args.command == "rules":
            rules = extract_rules(_read_text(Path(args.design)))
            if args.subject:
                rules = [
                    dict(rule, applicable=applicability(rule["group"], args.subject)[0])
                    for rule in rules
                ]
            _emit(rules, args.output)
            return 0

        if args.command == "build-request":
            payload = build_request(
                _read_text(Path(args.design)),
                subject_name=args.name,
                subject_class=args.subject,
                subject_kind=args.kind,
                captures=args.capture,
                requirements=args.requirement,
                references=args.reference,
                project_root=Path(args.project_root),
            )
            if args.question:
                sys.stdout.write(render_question(payload) + "\n")
                return 0
            _emit(payload, args.output)
            return 0

        if args.command == "grade":
            if not args.findings and not args.backend_error:
                print(
                    "Error: grade needs --findings or --backend-error",
                    file=sys.stderr,
                )
                return 2
            payload = grade(
                _read_json(Path(args.request)),
                _read_json(Path(args.findings)) if args.findings else [],
                backend_error=args.backend_error,
            )
            _emit(payload, args.output)
            return 0
    except DesignError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

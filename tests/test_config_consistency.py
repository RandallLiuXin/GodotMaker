"""Cross-layer consistency checks between skills and the shipped config defaults.

Catches drift like: a skill references `auditor_model from .godotmaker/config.yaml,
default: opus` while config.yaml.default declares `auditor_model: sonnet` (or omits
the key entirely). Both values must agree, otherwise published projects either
fall back to the wrong default or fail to find the key.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
CONFIG_DEFAULT = REPO_ROOT / "config" / "config.yaml.default"

# Matches: {worker_model from .godotmaker/config.yaml, default: opus}
# Tolerates extra whitespace around the comma and colon.
SKILL_REF_RE = re.compile(
    r"(\w+_model)\s+from\s+\.godotmaker/config\.yaml\s*,\s*default:\s*([\w\-]+)"
)
# Matches a top-level YAML scalar `key: value` (no nesting in this file).
CONFIG_KEY_RE = re.compile(r"^([\w_]+):\s*(\S+)\s*$", re.MULTILINE)


def _collect_skill_references():
    """Return a list of (key, default, source_path) tuples found across skills/."""
    refs = []
    for path in SKILLS_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for match in SKILL_REF_RE.finditer(text):
            refs.append((match.group(1), match.group(2), path))
    return refs


def _load_config_defaults():
    text = CONFIG_DEFAULT.read_text(encoding="utf-8")
    return dict(CONFIG_KEY_RE.findall(text))


def test_skill_referenced_models_exist_in_config_default():
    """Every `<role>_model` referenced by a skill must be declared in the
    shipped config.yaml.default. Missing keys silently fall back to whatever
    the skill author wrote in the prompt — that's the drift this catches."""
    config = _load_config_defaults()
    missing = sorted({key for key, _default, _path in _collect_skill_references()
                      if key not in config})
    assert not missing, (
        f"Skills reference *_model keys not declared in config.yaml.default: {missing}. "
        "Add them to config/config.yaml.default with the same default value."
    )


def test_skill_referenced_defaults_match_config_default():
    """When a skill writes `default: X` for a config key, X must equal the
    value in config.yaml.default. Otherwise the user-visible default and the
    fallback used inside the skill prompt diverge."""
    config = _load_config_defaults()
    mismatches = []
    for key, default, path in _collect_skill_references():
        actual = config.get(key)
        if actual is not None and actual != default:
            mismatches.append(
                f"{path.relative_to(REPO_ROOT)}: says '{key}' default is "
                f"'{default}', but config.yaml.default has '{key}: {actual}'"
            )
    assert not mismatches, "Skill default hints disagree with config:\n" + "\n".join(mismatches)


def test_config_template_documents_cli_pipeline_model_override():
    """The project config template must show where godotmaker-cli model
    overrides belong without pinning downstream-owned model variants."""
    text = CONFIG_DEFAULT.read_text(encoding="utf-8")
    assert "godotmaker-cli pipeline model override" in text
    assert "godotmaker-cli owns the supported model IDs" in text
    assert "pipeline:" in text
    assert "model: <codex-model-id>" in text
    assert "buildModel: <build-model-id>" in text
    assert "evalModel: <eval-model-id>" in text
    assert "gpt-5.6" not in text

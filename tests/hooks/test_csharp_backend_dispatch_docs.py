"""Contracts for backend-aware worker and verifier dispatch documentation."""
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

BACKEND_AWARE_DOCS = [
    "agents/worker.md",
    "agents/verifier.md",
    "skills/core/_shared/worker-dispatch.md",
    "skills/core/_shared/verifier-dispatch.md",
    "skills/core/gm-build/SKILL.md",
    "skills/core/gm-fixgap/SKILL.md",
    "skills/core/headless-build/SKILL.md",
]

CSHARP_BUILD_DOCS = [
    "agents/verifier.md",
    "skills/core/_shared/worker-dispatch.md",
    "skills/core/_shared/verifier-dispatch.md",
    "skills/core/headless-build/SKILL.md",
]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_dispatch_docs_use_the_approved_unit_test_backend_key():
    for relative_path in BACKEND_AWARE_DOCS:
        text = _read(relative_path)
        assert "unit_test_backend" in text, relative_path
        assert "verification_backend" not in text, relative_path


def test_csharp_build_docs_include_the_godot_project_target():
    for relative_path in CSHARP_BUILD_DOCS:
        text = _read(relative_path)
        assert "dotnet build <dotnet_target>" in text, relative_path
        assert "dotnet build <godot_csharp_project>" in text, relative_path

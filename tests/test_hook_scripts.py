from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PRE_PUSH = REPO_ROOT / "scripts" / "pre-push"


def test_pre_push_clears_inherited_git_environment_before_pytest():
    text = PRE_PUSH.read_text(encoding="utf-8")
    cleanup = "unset $(git rev-parse --local-env-vars)"

    assert cleanup in text
    assert text.index(cleanup) < text.index("python -m pytest --tb=short")

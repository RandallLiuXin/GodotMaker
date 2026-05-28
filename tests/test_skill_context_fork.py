"""Guard core skills against `context: fork`.

`context: fork` runs a skill in an isolated context whose internal tool
activity does not surface on the parent process's stdout under a headless
`claude -p` run. When such a skill is invoked from inside a worker subagent
(routine during `/gm-build`), the forked context does real work the runner
never sees, so the idle-timeout watchdog kills an otherwise-healthy build.
The whole pipeline runs headless, so no core skill may declare it.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SKILLS = sorted((REPO_ROOT / "skills" / "core").glob("*/SKILL.md"))


def _frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[: end if end != -1 else len(text)]


@pytest.mark.parametrize("skill", CORE_SKILLS, ids=lambda p: p.parent.name)
def test_core_skill_does_not_fork_context(skill):
    fm = _frontmatter(skill)
    assert not re.search(r"^context:\s*fork\s*$", fm, re.MULTILINE), (
        f"{skill.parent.name}/SKILL.md declares `context: fork`, which hangs "
        f"headless runs when the skill is invoked from a worker subagent: the "
        f"forked context's activity never reaches the parent stdout, so the "
        f"runner's idle watchdog kills the build. Run the skill inline instead."
    )

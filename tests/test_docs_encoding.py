"""Protect published documentation from common UTF-8 mojibake markers."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT))

from hooks.metrics.outcome import OUTPUT_CATEGORIES  # noqa: E402
MOJIBAKE_MARKERS = ("\ufffd", "鈥", "锟斤拷", "浠ｇ爜")


def test_published_docs_do_not_contain_known_utf8_mojibake_markers():
    offenders = []
    for path in DOCS.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        markers = [marker for marker in MOJIBAKE_MARKERS if marker in text]
        if markers:
            offenders.append(f"{path.relative_to(ROOT)} ({', '.join(markers)})")

    assert not offenders, "UTF-8 mojibake found: " + "; ".join(offenders)


def test_hook_output_category_tables_match_the_runtime_schema():
    for path in (DOCS / "hooks.md", DOCS / "zh" / "hooks.md"):
        output_row = next(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("| `outputs` |")
        )
        missing = [category for category in OUTPUT_CATEGORIES if f"`{category}`" not in output_row]
        assert not missing, f"{path.relative_to(ROOT)} omits output categories: {', '.join(missing)}"

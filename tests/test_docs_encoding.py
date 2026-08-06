"""Protect published documentation from common UTF-8 mojibake markers."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MOJIBAKE_MARKERS = ("\ufffd", "鈥", "锟斤拷", "浠ｇ爜")


def test_published_docs_do_not_contain_known_utf8_mojibake_markers():
    offenders = []
    for path in DOCS.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        markers = [marker for marker in MOJIBAKE_MARKERS if marker in text]
        if markers:
            offenders.append(f"{path.relative_to(ROOT)} ({', '.join(markers)})")

    assert not offenders, "UTF-8 mojibake found: " + "; ".join(offenders)

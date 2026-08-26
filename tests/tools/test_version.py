"""Tests for the shared SemVer parser and ordering contract."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

from _version import SemVer, parse_version
from publish import read_changelog_section, read_source_version, write_target_version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.8.2", SemVer(0, 8, 2)),
        ("1.0.0-alpha.1", SemVer(1, 0, 0, ("alpha", "1"))),
        (
            "1.0.0-rc.1+windows.x64",
            SemVer(1, 0, 0, ("rc", "1"), ("windows", "x64")),
        ),
    ],
)
def test_parse_and_preserve_exact_semver(text, expected):
    parsed = parse_version(text)
    assert parsed == expected
    assert str(parsed) == text


@pytest.mark.parametrize(
    "text",
    [
        "1.0",
        "v1.0.0",
        "1.0.0 trailing",
        "01.0.0",
        "1.0.0-alpha.01",
        "1.0.0-",
    ],
)
def test_rejects_non_semver_input(text):
    assert parse_version(text) is None


def test_prerelease_precedence_matches_semver():
    versions = [
        "0.8.2",
        "1.0.0-alpha.1",
        "1.0.0-alpha.2",
        "1.0.0-beta.1",
        "1.0.0-rc.1",
        "1.0.0",
    ]
    parsed = [parse_version(version) for version in versions]
    assert all(version is not None for version in parsed)
    assert parsed == sorted(parsed)


def test_numeric_prerelease_identifiers_sort_before_text_identifiers():
    numeric = parse_version("1.0.0-1")
    text = parse_version("1.0.0-alpha")
    assert numeric is not None and text is not None
    assert numeric < text


def test_build_metadata_does_not_change_precedence():
    first = parse_version("1.0.0-alpha.1+build.1")
    second = parse_version("1.0.0-alpha.1+build.2")
    assert first == second
    assert not first < second
    assert not second < first


def test_publish_helpers_preserve_prerelease_suffix(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "VERSION").write_text("1.0.0-alpha.1\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.0.0-alpha.1] - 2026-08-26\n\n- Alpha release.\n",
        encoding="utf-8",
    )

    version = read_source_version(repo)
    assert version is not None
    assert str(version) == "1.0.0-alpha.1"
    assert "Alpha release." in read_changelog_section(repo, version)

    target = tmp_path / "target"
    write_target_version(target, version)
    assert (target / ".godotmaker" / "version").read_text(
        encoding="utf-8"
    ) == "1.0.0-alpha.1\n"

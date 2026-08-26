#!/usr/bin/env python3
"""Shared semantic versioning utilities for GodotMaker tools."""
from dataclasses import dataclass
from functools import total_ordering
import re


_IDENTIFIER = r"[0-9A-Za-z-]+"
_VERSION_RE = re.compile(
    rf"^(0|[1-9]\d*)\."
    rf"(0|[1-9]\d*)\."
    rf"(0|[1-9]\d*)"
    rf"(?:-({_IDENTIFIER}(?:\.{_IDENTIFIER})*))?"
    rf"(?:\+({_IDENTIFIER}(?:\.{_IDENTIFIER})*))?$"
)


@total_ordering
@dataclass(frozen=True, eq=False)
class SemVer:
    """A SemVer 2.0.0 value with prerelease and build identifiers."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += "-" + ".".join(self.prerelease)
        if self.build:
            text += "+" + ".".join(self.build)
        return text

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        # Build metadata is excluded from SemVer precedence.
        return self._precedence_key() == other._precedence_key()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented

        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return core < other_core

        if not self.prerelease:
            return False
        if not other.prerelease:
            return True

        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return int(left) < int(right)
            if left_numeric != right_numeric:
                return left_numeric
            return left < right
        return len(self.prerelease) < len(other.prerelease)

    def __hash__(self) -> int:
        return hash(self._precedence_key())

    def _precedence_key(self) -> tuple[int, int, int, tuple[str, ...]]:
        return self.major, self.minor, self.patch, self.prerelease


def parse_version(text: str) -> "SemVer | None":
    """Parse an exact SemVer 2.0.0 string. Returns None on failure."""
    m = _VERSION_RE.fullmatch(text.strip())
    if not m:
        return None

    prerelease = tuple(m.group(4).split(".")) if m.group(4) else ()
    if any(part.isdigit() and len(part) > 1 and part.startswith("0")
           for part in prerelease):
        return None

    build = tuple(m.group(5).split(".")) if m.group(5) else ()
    return SemVer(
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        prerelease,
        build,
    )

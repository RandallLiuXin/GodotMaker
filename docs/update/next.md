# Next Release

> **Contributors:** Every pull request MUST include an entry in this file describing the change.
> When a new version is released, this file will be archived as `vX.Y.Z.md` and a fresh copy will take its place.

## How to add an entry

Append your change under the appropriate category below. Use this format:

```
- Brief description of the change (#PR_NUMBER) — @author
```

If no category fits, add a new one following [Keep a Changelog](https://keepachangelog.com/) conventions.

---

## Added

## Changed

- Replaced the project `STYLE.md` visual seed with a plain-text `DESIGN.md` visual contract covering visual identity, nine image-style dimensions, UI visual language, and Do / Don't lists; existing projects migrate on publish, legacy text preserved verbatim.
- Asset generation now treats `DESIGN.md` as the visual specification authority and role-labeled reference images as visual conditioning: each production unit carries its applicable design sections verbatim in the request brief, and a conflicting reference is a blocker instead of a silent drop.

## Fixed

## Removed

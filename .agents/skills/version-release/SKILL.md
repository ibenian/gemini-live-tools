---
name: version-release
description: Tag a release, create a GitHub release with notes, and bump to the next patch version. Reports current state, tags, publishes, and bumps in one flow.
---

# Version Release

Tag, release, and bump the version for gemini-live-tools in one command.

## When to Use This Skill

- User says "release", "tag", "version release", or "cut a release"
- User wants to publish the current version

## Version Location

| Version | File | Purpose |
|---------|------|---------|
| **version** | `python/pyproject.toml` | Python package version |

**Project root**: `/Users/ibenian/dev/gemini-live-tools`

## Step 1: Report Current State

Before anything, read and report:

```bash
grep '^version' python/pyproject.toml
git tag --sort=-v:refname | head -5
gh release list --limit 5
git branch --show-current
```

Tell the user:
- Current version in `pyproject.toml`
- Latest git tag
- Latest GitHub release
- Current branch

## Step 2: Confirm with User

Show what will happen:
- Tag `vX.Y.Z` on current commit
- Create GitHub release `vX.Y.Z` with notes
- Bump `pyproject.toml` to `X.Y.(Z+1)` via PR
- Merge the bump PR

Wait for user confirmation before proceeding.

## Step 3: Tag and Release

Must be on `main` and up to date:

```bash
git checkout main && git pull
```

Generate release notes from commits since last tag:

```bash
git log v0.1.(Z-1)..HEAD --oneline
```

Tag and create the GitHub release:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --notes "release notes here"
```

## Step 4: Bump to Next Version

Create a PR to bump `pyproject.toml` to the next patch:

```bash
git checkout -b chore/bump-version-X.Y.(Z+1)
# Edit python/pyproject.toml: X.Y.Z → X.Y.(Z+1)
git add python/pyproject.toml
git commit -m "chore: bump version to X.Y.(Z+1)"
git push -u origin chore/bump-version-X.Y.(Z+1)
gh pr create --title "chore: bump version to X.Y.(Z+1)" --body "Post-release version bump." --label chore
```

Merge the bump PR:

```bash
gh pr merge --squash --delete-branch --admin
```

Return to main:

```bash
git checkout main && git pull
```

## Versioning Rules

- Follows `MAJOR.MINOR.PATCH` (e.g., `0.1.16`)
- Releases are git tags (`v0.1.16`) with matching GitHub releases
- The version in `pyproject.toml` on `main` is always the **next unreleased version**
- Consumers pin to a tag (e.g., `pip install ... @v0.1.16`)
- Bump commit message: **`chore: bump version to X.Y.Z`**
- Bump PRs are labeled `chore` and merged with `--admin`

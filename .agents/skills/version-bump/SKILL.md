---
name: version-bump
description: Manage gemini-live-tools version numbers. Reports current version state, bumps for new PRs, and prepares releases. Always report current state before making changes.
---

# Version Bump

Manage version numbers for the gemini-live-tools project.

## When to Use This Skill

- User asks to bump, increment, or check the version
- Starting a new PR branch
- Preparing for a release

## Version Location

One version number, one file:

| Version | File | Purpose |
|---------|------|---------|
| **version** | `python/pyproject.toml` | Python package version |

**Project root**: `/Users/ibenian/dev/gemini-live-tools`

## Step 1: Always Report Current State First

Before any version change, read and report:

```bash
grep '^version' python/pyproject.toml
git tag --sort=-v:refname | head -5
git branch --show-current
```

Tell the user:
- Current version in `pyproject.toml`
- Latest git tag
- Current git branch

## Step 2: Determine What to Do

### For New PR Development

The version in `pyproject.toml` is already the version being developed. No change needed unless the version wasn't bumped after the last release.

### For Release

The version in `pyproject.toml` is the version to release. The release flow is:

1. **Ensure on main** and up to date:
   ```bash
   git checkout main && git pull
   ```

2. **Tag** the current commit and create a GitHub release:
   ```bash
   git tag v0.1.X
   git push origin v0.1.X
   gh release create v0.1.X --title "v0.1.X" --notes "..."
   ```
   Include release notes summarizing PRs merged since the last tag:
   ```bash
   git log v0.1.(X-1)..HEAD --oneline
   ```

3. **Immediately bump** `pyproject.toml` to the next patch version via a PR:
   ```bash
   git checkout -b chore/bump-version-0.1.(X+1)
   # Edit python/pyproject.toml: 0.1.X → 0.1.(X+1)
   git add python/pyproject.toml
   git commit -m "chore: bump version to 0.1.(X+1)"
   git push -u origin chore/bump-version-0.1.(X+1)
   gh pr create --title "chore: bump version to 0.1.(X+1)" --body "..." --label chore
   ```

4. **Merge the bump PR** (with `--admin` per project rules):
   ```bash
   gh pr merge --squash --admin
   ```

5. **Return to main**:
   ```bash
   git checkout main && git pull
   ```

This ensures:
- The tag `v0.1.X` points to a commit where `pyproject.toml` says `0.1.X`
- The tip of `main` immediately moves to `0.1.(X+1)`, representing the next dev cycle
- Consumers pinning to `v0.1.X` in `requirements.txt` get the correct version
- The bump goes through a PR for clean git history

## Versioning Rules

- Follows `MAJOR.MINOR.PATCH` (e.g., `0.1.3`)
- Releases are git tags (`v0.1.3`)
- The version in `pyproject.toml` on `main` is always the **next unreleased version**
- Consumers (e.g., algebench) pin to a tag in `requirements.txt`
- Commit message: **`chore: bump version to X.Y.Z`**
- PRs are labeled `chore` and merged with `--admin`

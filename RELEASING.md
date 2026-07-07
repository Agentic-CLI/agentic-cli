# Releasing Agentic CLI

This is the practical runbook for cutting a release of **Agentic CLI**. Releases
are driven entirely by pushing a git tag; the
[`release.yml`](.github/workflows/release.yml) workflow does the rest.

## Versioning policy

Agentic CLI follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Given a version `MAJOR.MINOR.PATCH`:

- **MAJOR** — incompatible / breaking changes to the CLI, its config format
  (e.g. `.agentic/bundle.yaml`), or the compiled output contract.
- **MINOR** — new, backwards-compatible functionality (new commands, flags, packs).
- **PATCH** — backwards-compatible bug fixes only.

> **Pre-1.0 caveat.** While the version is `0.y.z`, the public API is not yet
> stable. Per SemVer, **anything may change at any time** — in practice we treat
> a bump of the **minor** (`0.Y.z`) as the signal for a potentially breaking
> change, and the **patch** (`0.y.Z`) for backwards-compatible fixes and additions.
> Do not assume stability across minor bumps until 1.0.0.

The changelog format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).

## Single source of truth for the version

The version is declared in **two** places and they **must be kept in sync**:

1. `src/agentic/__init__.py` — `__version__ = "X.Y.Z"`
2. `pyproject.toml` — `version = "X.Y.Z"`

Both must be identical before you tag. The git tag (`vX.Y.Z`) must match them too.
There is no automation that reconciles these files today — keeping them in sync is
a manual step in the checklist below. A mismatch means the built artifact reports
a different version than the tag.

## Cut a release — checklist

Do this from a clean, up-to-date `main` (or your release branch), with all
intended changes already merged.

1. **Update the changelog.** In `CHANGELOG.md`, rename the `## [Unreleased]`
   section to `## [X.Y.Z] - YYYY-MM-DD` (today's date, ISO 8601), and add a fresh
   empty `## [Unreleased]` section above it. Update the link references at the
   bottom of the file (add a `[X.Y.Z]` compare/tag link and repoint
   `[Unreleased]`).

2. **Bump the version** in both files so they match:
   - `src/agentic/__init__.py` → `__version__ = "X.Y.Z"`
   - `pyproject.toml` → `version = "X.Y.Z"`

3. **Commit** the changelog + version bump together:

   ```sh
   git add CHANGELOG.md src/agentic/__init__.py pyproject.toml
   git commit -m "Release vX.Y.Z"
   ```

4. **Tag and push.** The tag name must be `vX.Y.Z` (leading `v`):

   ```sh
   git push origin main
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

5. **Let CI do the release.** Pushing the `v*` tag triggers
   [`release.yml`](.github/workflows/release.yml), which:
   - checks out the tag,
   - builds the sdist + wheel with `python -m build`,
   - creates a **GitHub Release** for the tag with the built artifacts attached
     and notes drawn from `CHANGELOG.md` (falling back to auto-generated notes).

   Watch the Actions run; once it's green, verify the Release appears under
   **Releases** with `dist/*` attached.

### If something goes wrong

If the workflow fails or the tag was wrong, delete and recreate the tag:

```sh
git push origin :refs/tags/vX.Y.Z   # delete the remote tag
git tag -d vX.Y.Z                    # delete the local tag
# fix the problem, then re-run steps 3–5
```

If a bad Release was already published, delete it in the GitHub UI (or
`gh release delete vX.Y.Z`) before re-tagging.

## How users install a release

Agentic CLI is **not yet on PyPI** (the name is currently taken there). Until
that changes, install a specific release straight from the tagged git ref with
[pipx](https://pipx.pypa.io/):

```sh
pipx install "git+https://github.com/Agentic-CLI/agentic-cli.git@vX.Y.Z"
```

To track the latest development tip instead of a release:

```sh
pipx install "git+https://github.com/Agentic-CLI/agentic-cli.git"
```

Agentic CLI has **zero runtime dependencies**, so no extra install steps are
required.

## TODO: PyPI publishing (Trusted Publishing / OIDC)

<!--
  TODO(release): enable PyPI publishing once the package name on PyPI is
  finalized/claimed.

  Plan:
    1. Register the (final) project name on PyPI and configure a Trusted
       Publisher (OIDC) for this repo + the `release.yml` workflow — no API
       tokens/secrets needed.
    2. Uncomment the `pypa/gh-action-pypi-publish` step in
       `.github/workflows/release.yml` (and its `id-token: write` permission).
    3. Update the "How users install a release" section above to prefer
       `pipx install agentic-cli==X.Y.Z` (or `pip install`), keeping the
       git-ref method as a fallback.
-->

PyPI publishing is **not enabled yet**. Once the PyPI package name is finalized,
we will publish via **Trusted Publishing (OIDC)** — no long-lived API tokens. The
release workflow already contains a clearly-marked, commented-out
`pypa/gh-action-pypi-publish` step; enabling it plus configuring the Trusted
Publisher on PyPI is all that's required.

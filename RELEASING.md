# Releasing OpenRVDAS

This document is for maintainers cutting a numbered release. For contributing
changes, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Branch model

- **`dev`** is the integration branch. All pull requests land here.
- **`master`** holds released code. It only ever advances by merging `dev`
  at release time.

Release tags (`v2.6.1`, etc.) live on the merge commit that brings `dev` into
`master`.

## Cutting a release

### 1. Check `dev` is ready

```bash
git checkout dev
git pull
pytest test/
```

Confirm CI on `dev` is green and that anything intended for the release has
merged.

If the release needs testing on real installations first, cut release
candidates from `dev`; see [Release candidates](#release-candidates). Once the
last one is tagged, don't merge anything else into `dev` until the release is
out: step 2 merges `dev` as it stands, so anything merged in the meantime ships
without having been in a release candidate.

### 2. Merge `dev` into `master` as a true merge

```bash
git checkout master
git pull
git merge --no-ff dev
```

**Use a merge commit, not a squash.** On GitHub this is the "Create a merge
commit" option — *not* "Squash and merge". This matters; see
[Why `--no-ff`](#why---no-ff) below.

In practice `master` is protected, so this is a pull request from `dev` into
`master`, and it needs an approving review — which GitHub doesn't let a pull
request's author give. Open it from an account other than the approving
maintainer's. Then **approve it, but don't merge it with the button**: in this
repository the button defaults to "Squash and merge". Merge from the command
line instead:

```bash
gh pr merge <PR number> --merge
```

### 3. Tag the merge commit

```bash
git tag -a v2.6.2 -m "Release v2.6.2"
git push origin master v2.6.2
```

Use an annotated tag (`-a`), and the `vX.Y.Z` form — tooling matches on the
leading `v`.

### 4. Merge `master` back into `dev`

This step is easy to forget and its absence is invisible until something reads
tags. Do not skip it.

```bash
git checkout dev
git merge --no-ff origin/master
git push origin dev
```

The merge should be **content-neutral** for `dev` — `master`'s release commit
is `dev`'s own content, so there is nothing new to bring back. Verify:

```bash
git log -1 --format=%p        # expect TWO parent hashes
git diff HEAD^1 HEAD          # expect EMPTY
```

On GitHub `dev` is protected too, so this is a pull request from `master` into
`dev`, which also needs an approval. Merge it the same way, with
`gh pr merge <PR number> --merge`. A squash here defeats the purpose: a squash
commit has one parent, so the release tag stays out of `dev`'s history. That
happened to v2.7.0's first back-merge (#739), which had to be redone as #740;
step 5's check catches it.

If conflicts appear, resolve them in `dev`'s favour (`git checkout --ours
<file>`); `--ours` during a merge means the branch you are on, i.e. `dev`.

A non-empty diff means something reached `master` without going through
`dev` — stop and investigate rather than committing the merge.

### 5. Verify tag reachability from `dev`

```bash
git describe --tags --abbrev=0 dev    # expect: the release you just tagged
```

If this reports an *older* release, the release is not properly reachable from
`dev` and version-derivation tooling will report stale numbers. See
[Why `--no-ff`](#why---no-ff).

`scripts/check_release_tags.sh` makes this check, and runs in CI on every push
and pull request to `dev` (the Release Tags workflow). It fails if the latest
release on `master` isn't reachable from `dev`, or if `dev`'s nearest tag is
anything other than that release or a pre-release of a later version. Run it
locally with:

```bash
scripts/check_release_tags.sh origin/dev origin/master
```

Between steps 3 and 4 it fails on purpose, as a reminder that the back-merge is
still to do.

## Release candidates

To have a release tested before it's cut, tag release candidates on `dev`:

```bash
git tag -a v2.7.0rc1 -m "Release candidate 1 for v2.7.0"
git push origin v2.7.0rc1
gh release create v2.7.0rc1 --verify-tag --prerelease --latest=false \
    --title "v2.7.0rc1 (release candidate)" --notes-file notes.md
```

- `--latest=false` keeps the current release marked Latest on GitHub.
- `setuptools_scm` handles `rcN` tags: commits after `v2.7.0rc1` report
  `2.7.0rc2.devN`.
- The release tags check accepts a release candidate as `dev`'s nearest tag, as
  long as it's for a version after the latest release.
- If code changes land on `dev` after the last candidate, cut another before
  releasing. A documentation-only change needn't wait for one.

## Why `--no-ff`

`git describe` reports the **nearest** reachable tag by commit distance, not
the newest one.

Releases used to be squash-merged onto `master`. A squash commit has a single
parent, so `master`'s line contained none of `dev`'s individual commits — which
put every release tag 100+ commits away from `dev`'s tip, while an older tag
that happened to sit on `dev`'s own mainline stayed much closer and won. The
result was `dev` describing as `v2.3.1` long after `v2.6.x` had shipped
(see [#621](https://github.com/OceanDataTools/openrvdas/issues/621)).

A `--no-ff` merge gives the release commit `dev`'s tip as a parent. After the
back-merge in step 4 the tag sits a handful of commits from `dev`, so
`git describe` stays correct, and both distances grow in lockstep afterwards so
it stays correct permanently.

## Marker tags (retired)

Before v2.7.0, releases were squash-merged, and `dev` carried a marker tag of the
form `vX.Y.Z.dev0` (`v2.6.2.dev0`, then `v2.6.3.dev0`) so that tag-walking tooling
reported a sensible version. v2.7.0 was the first release cut as a true merge,
so its tag does that job, and **no more marker tags are needed**; the old ones
are harmless and stay. See
[#624](https://github.com/OceanDataTools/openrvdas/issues/624).

If one is ever needed again, it must end in `.dev0`, never `.dev1` and so on.
`setuptools_scm` derives the running count itself, and a hand-numbered `.devN`
tag breaks the build as soon as another commit lands after it (`ValueError:
choosing custom numbers for the .devX distance is not supported`).

## Version numbers

`vMAJOR.MINOR.PATCH`, incremented as:

- **PATCH** — bug fixes, no new features (`v2.6.0` → `v2.6.1`)
- **MINOR** — new features, backward compatible (`v2.5.1` → `v2.6.0`)
- **MAJOR** — breaking changes

The git tag is the single source of truth. `pyproject.toml` declares
`dynamic = ["version"]` and `setuptools_scm` derives the version from the
nearest reachable tag, so there is no version field to bump — tagging the
release in step 3 *is* setting the version.

This is also why steps 4 and 5 matter: a release tag that isn't reachable from
`dev` at a short distance silently yields a stale version everywhere the number
is displayed. See [Why `--no-ff`](#why---no-ff).

### How the displayed version is resolved

`logger/utils/read_version.py` recomputes the version **live from the git tree**
on each call, via `setuptools_scm` (a runtime dependency, not just a build one).
A deployment upgraded with a plain `git pull` therefore picks up the new version
straight away — no reinstall needed for the Django footer, the React nav, or the
FastAPI `/version` endpoint to update.

It falls back to the version frozen into package metadata at install time only
when the live read isn't possible — no `.git` tree (a non-editable install from
a built wheel or sdist), or `setuptools_scm` missing from the environment — and
to `"unknown"` if the package isn't installed at all.

**One upgrade gotcha:** environments created before `setuptools_scm` became a
runtime dependency don't have it installed, so they silently take the fallback
path and keep reporting whatever was frozen in at their original install — which
for older checkouts is the long-stale `0.1.0`. A version that looks implausibly
old is the symptom; `pip install -e /opt/openrvdas` (or re-running the
installer) fixes it by pulling in the new dependency.

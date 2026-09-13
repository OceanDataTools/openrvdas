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

### 2. Merge `dev` into `master` as a true merge

```bash
git checkout master
git pull
git merge --no-ff dev
```

**Use a merge commit, not a squash.** On GitHub this is the "Create a merge
commit" option — *not* "Squash and merge". This matters; see
[Why `--no-ff`](#why---no-ff) below.

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

If conflicts appear, resolve them in `dev`'s favour (`git checkout --ours
<file>`); `--ours` during a merge means the branch you are on, i.e. `dev`.

A non-empty diff means something reached `master` without going through
`dev` — stop and investigate rather than committing the merge.

### 5. Verify tag reachability from `dev`

```bash
git describe --tags dev       # expect: v2.6.2
```

If this reports an *older* release, the release is not properly reachable from
`dev` and version-derivation tooling will report stale numbers. See
[Why `--no-ff`](#why---no-ff).

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

## Marker tags (transitional)

Until the first `--no-ff` release lands, `dev` carries a marker tag of the form
`vX.Y.Z.dev0` (currently `v2.6.2.dev0`) so that tag-walking tooling reports a
sensible version. These are a workaround for the squash-merge history, not part
of the process.

**Once a release has been cut as a true merge, stop creating them** — the
release tag itself does the job. See
[#624](https://github.com/OceanDataTools/openrvdas/issues/624).

### Marker tags must end in `.dev0`

Tag `vX.Y.Z.dev0` and nothing else — never `.dev1`, `.dev2`, and so on.
`setuptools_scm` derives the running count itself, so one `.dev0` marker per
release cycle is all that is needed: with `v2.6.2.dev0` on `dev`, a commit on
top reports `2.6.2.dev1+g<sha>`, the next `2.6.2.dev2+g<sha>`, and so on.

Tagging a hand-numbered `.devN` instead breaks the build as soon as any commit
lands after it:

```
ValueError: choosing custom numbers for the `.devX` distance is not supported.
 The 2.6.2.dev1 can't be bumped
Please drop the tag or create a new supported one ending in .dev0
```

The tag itself is accepted, so this does not fail until the next commit — by
which point the bad tag may already be pushed. If that happens, delete the tag
(locally and on the remote) and re-cut it as `.dev0`.

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

### The displayed version updates only on reinstall

OpenRVDAS is installed editable (`pip install -e .`), and `setuptools_scm`
resolves the version at **install** time, freezing it into the package metadata
that `logger/utils/read_version.py` reads. It is not recomputed from git on
import.

So a deployment upgraded with a plain `git pull` keeps reporting the *previous*
version in the Django footer, the React nav, and the FastAPI `/version`
endpoint — indefinitely, with nothing indicating it is stale. To pick up a new
release:

```bash
pip install -e /opt/openrvdas
```

Worth mentioning in release notes for anyone who upgrades without re-running
the installer.

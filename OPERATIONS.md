# OpenRVDAS — Operational Notes

Companion to `CLAUDE.md`. That file covers architecture and conventions, both of
which are visible in the repo. This one collects the things that are **not**
derivable from the code, the git history, or the docs — the traps that have
actually cost contributors time, and the decisions whose reasoning would
otherwise be lost.

Time-sensitive facts are marked **[as of <date>]**. Re-verify those before
relying on them; everything else is structural.

---

## 1. GitHub mechanics

### Multiple `gh` accounts — check which one is active before pushing

If you have more than one account authenticated with `gh` (a bot or CI account
alongside your own, say), git uses the **active** one for HTTPS pushes. Pushing
to a fork you own while a different account is active fails with **403**, which
reads as a permissions problem rather than the account-selection problem it
actually is.

```bash
gh auth status              # which account is active?
gh auth switch --user <you> # make yours active before pushing
```

### `dev` is protected — your own PRs will show BLOCKED

`dev` on `OceanDataTools/openrvdas` requires **1 approving review**, and GitHub
does not let an author approve their own PR. Any self-authored PR therefore
reports `mergeStateStatus: BLOCKED` / `reviewDecision: REVIEW_REQUIRED` even
with every check green.

**This is the rule working, not a failure.** Two ways through:

- a review from the co-maintainer (Webb Pinner is the active one), or
- `enforce_admins` is `false` and the maintainer has `admin: true`, so
  `gh pr merge <n> --squash --admin` overrides.

Prefer surfacing the choice over silently using `--admin`.

### Merge method depends on the PR type

| PR | Command | Why |
|---|---|---|
| Feature branch → `dev` | `gh pr merge <n> --squash` | WIP commits aren't worth keeping |
| Release `dev` → `master` | `gh pr merge <n> --merge` | **Must** be a real merge commit — see §2 |
| Back-merge `master` → `dev` | `gh pr merge <n> --merge` | **Must** be a real merge commit too — see §2 |

Use the explicit flag every time. **Don't merge release or back-merge PRs with
the GitHub button:** here it has defaulted to "Squash and merge", and that is
how v2.7.0's first back-merge (#739) was squashed and had to be redone (#740).
Approve in the UI, then merge with `gh pr merge <n> --merge`. All three merge methods stay enabled on the
repo deliberately: GitHub has no "default merge method" setting (only the three
`allow_*` booleans), so disabling squash to force correct releases would also
stop feature PRs from squashing. **Don't "fix" the repo settings.**

---

## 2. Release process — the squash-merge legacy

Every `dev` → `master` release through **v2.6.1** was a squash merge rather than
a true merge (v2.6.2 was a hotfix cherry-picked onto `master`). **v2.7.0
(2026-11-03) was the first release cut as a true merge** (#720), and merged back
into `dev` as one (#740). Two consequences of the older history are easy to
confuse.

### Commit counts overstate divergence

For history before v2.7.0, `git log master..dev` reports many commits whose
*content* was already in master. Use `git diff master..dev --stat` for the real
delta. On 2026-09-10 the counts were 119 commits vs. 25 files actually differing.

### Release tags fell out of `git describe` range

`git describe` returns the nearest reachable tag **by commit distance**, not the
newest one. Because master's squash line contained none of dev's individual
commits, every release tag sat 100+ commits from dev's tip — while `v2.3.1`,
the one tag that landed on a real two-parent merge on dev's own mainline, sat
closer and won. `dev` described itself as `v2.3.1-79` long after v2.6.x shipped,
and `setuptools_scm` derived `2.3.2.devN` from it. Tracked as
[#621](https://github.com/OceanDataTools/openrvdas/issues/621).

**Two traps worth internalizing:**

1. **Reachability alone isn't enough.** v2.4.0–v2.6.0 *were* already ancestors of
   dev, so `git merge-base --is-ancestor <tag> dev` passed while the bug was
   live. A check has to assert that `git describe --tags dev` **names** the
   latest release, as `scripts/check_release_tags.sh` does (it checks
   reachability too, which catches a skipped or squashed back-merge).
2. **Back-merging a squashed release into dev doesn't fix it.** Both distances
   just increment (verified 2026-09-10). Only a true-merge release followed by a
   true-merge back-merge does.

### The fix, as exercised in v2.7.0

The release commit (`ae353258`) has dev's tip as a parent, and after the
back-merge `git describe --tags dev` reports `v2.7.0-N-g…`. setuptools_scm gives
`dev` `2.7.1.devN`, and the `v2.7.0` tag exactly `2.7.0`. The squash commit from
the botched first back-merge (#739) is still in dev's history; it is empty and
harmless.

The **Release Tags** CI workflow (`scripts/check_release_tags.sh`, on every push
and pull request to `dev`) keeps it that way. It deliberately accepts a release
candidate (`vX.Y.ZrcN`) as dev's nearest tag if it is for a version after the
latest release; the plain string comparison first drafted in #624 would have
gone red for every release-candidate cycle. Between tagging a release on
`master` and merging it back, it fails on purpose.

### Marker tags are retired

Until v2.7.0, `dev` carried `vX.Y.Z.dev0` marker tags (`v2.6.2.dev0`,
`v2.6.3.dev0`) to work around the squash history. They are no longer needed and
shouldn't be cut. If one ever is, it must end in `.dev0`: setuptools_scm refuses
to bump a hand-numbered `.devN` tag, and raises
`ValueError: choosing custom numbers for the .devX distance is not supported`
as soon as the next commit lands — possibly after the tag has been pushed.

---

## 3. How the displayed version is resolved

Since [#622](https://github.com/OceanDataTools/openrvdas/pull/622) (merged
2026-09-12), the version in the Django footer, React nav, and FastAPI `/version`
comes from `logger/utils/read_version.py`:

1. `setuptools_scm.get_version()` — **live against the git tree**
2. fallback: `importlib.metadata.version('openrvdas')` — frozen at install
3. fallback: `'unknown'`

`setuptools_scm>=8,<11` is a **runtime** dependency in `pyproject.toml`, not just
a build requirement. That is deliberate: it makes step 1 work, so a plain
`git pull` updates the displayed version with no reinstall.

### The stale-version gotcha

(Observed 2026-09-13.) A venv created *before* `setuptools_scm` became a runtime dep doesn't have it.
Step 1 then fails **silently** and the UI shows whatever was frozen in at
original install — `0.1.0` for older checkouts, a long-dead hand-maintained
value. Nothing signals that it's stale.

- **Symptom:** implausibly old version in the UI.
- **Fix:** `pip install -e /opt/openrvdas`
- **Expected side effect:** this enforces `pyproject.toml`'s ceilings, which
  downgrades Django 6.1 → 6.0.x. That is intended — `django>=4.2,<6.1` exists
  because Django 6.1 requires SQLite 3.37, newer than RHEL 9 / Rocky 9 ship.

The same missing-dependency class of bug hit the React UI separately via the
`web_backend` venv (#634, fixed in #635).

---

## 4. Dependencies

### `pyproject.toml` is the single source of truth

**Edit `pyproject.toml`, never `utils/requirements.txt`.** The latter is now a
stub that installs the project itself and carries a comment saying so.

Historical note, because older docs and habits still assume otherwise: the two
files used to duplicate each other by hand with nothing keeping them in sync,
and the installer ran both — so a package added in only one place was installed
twice or not at all depending on which file you edited. That was the root cause
of having to patch both in #591 and #592, and it was fixed in #595 (issue #594).
Adding a package to `requirements.txt` today installs it without recording it as
a project dependency, which is exactly the drift that change removed.

The installer runs `pip install -e .` when `pyproject.toml` exists, and falls
back to `requirements.txt` only for pre-v2.x checkouts.

### What's core and what's an extra

Core dependencies were cut 14 → 8 in August 2026, driven by OpenRVDAS being
uninstallable on a Raspberry Pi (ARMv6/v7 has no `pyogrio` wheel; `uwsgi` needs
a C compiler). **A default install no longer needs a C compiler.**

**Django is core, not an extra** — `LoggerManager` uses the Django ORM as its
backing store regardless of UI choice, and the installer runs `setup_django`
unconditionally. `django`, `djangorestframework` and `drf-spectacular` are pure
Python, so they don't block a compiler-free install. This is why #592's attempt
to make Django optional broke headless installs and #597 put it back.

Extras: **`web`** (`uwsgi` only — the one web dependency needing a C compiler;
installed when `UI_TYPE == django`), **`geofence`** (`geopandas`, `shapely`),
**`google`**, **`mysql`**, **`redis`**, **`mqtt`** (`paho-mqtt`), **`dev`**.

`GeofenceTransform` guards its imports and raises an `ImportError` naming the
exact install command.

Two version ceilings exist for hard-won reasons, both documented inline:
`django>=4.2,<6.1` (6.1 requires SQLite 3.37; RHEL/Rocky/Alma 9 ship 3.34.1 —
issue #590) and `websockets<18`.

### Two known dependency traps

- **`contrib/` drivers have undocumented dependencies.** `bme688_reader.py` needs
  `adafruit_bme680` and `board`, which appear in no requirements file.
- **`database/settings.py` does `sys.path.append('.')`**, imported via a
  `try/except` in `logger/readers/database_reader.py`. This accidentally puts the
  repo root on `sys.path` whenever that generated (gitignored) file exists *and*
  cwd happens to be the repo root. It masks `contrib`/`local` import bugs, which
  is why the #593 bug looked unreproducible on a dev box. **Before debugging a
  `contrib` import failure, check whether `database/settings.py` exists.**

---

## 5. `utils/install_openrvdas.sh` — platform constraints

~2,500 lines of platform-conditional shell targeting macOS, Ubuntu 22.04+,
Debian 12+, and RHEL/Rocky/AlmaLinux 9+. It refuses releases below a
per-distribution floor and accepts newer ones, including releases that came
out after it was written, with a notice (`check_os_supported`, #722). Its
correctness lives in environments no CI job reproduces. **Changes here need
real machines, not a green `bash -n`.**

### macOS ships bash 3.2 — two constructs are unavailable

1. **A heredoc containing `;;` inside a command substitution does not parse.**
   `V=$(cat <<EOF … case … ;; … EOF)` is a syntax error on bash 3.2 and fine on
   bash 4+. Build such strings as quoted multi-line strings instead. This is why
   the venv-activation snippet in `add_venv_to_login_script` is written the way
   it is — **do not "clean it up" into a heredoc.**
2. **`read -r -d '' VAR <<EOF` returns non-zero at EOF**, and the script runs
   under `#!/bin/bash -e`, so it aborts the install. Use command substitution.

### Privilege model

- The script runs as a **sudo-capable normal user**, not as root. It validates
  `sudo -v` up front and refreshes the timestamp in the background.
- **On macOS it must not be run under sudo at all** — Homebrew refuses to run as
  root, and the script exits early if `EUID` is 0.
- Consequence: anything writing into the RVDAS user's home must go through
  `sudo -u "$RVDAS_USER"`, or it leaves root-owned files there.

### `create_user` usually doesn't create a user

It calls `adduser` only when `id -u` fails. The common paths — re-runs,
pre-provisioned accounts, and **all of macOS** (where the script refuses to
create users and defaults `RVDAS_USER` to `${SUDO_USER:-$USER}`) — take the
"user exists" branch. **Never key a feature off "when we create the user"; it
will miss most installs.**

### Nothing at runtime depends on venv activation

Every program supervisord runs invokes the venv binaries by **absolute path**,
with explicit `PATH=` and `PYTHONPATH=` in each program block. Shell-level venv
activation is a convenience for humans only.

---

## 6. Testing caveats

- **Database tests skip automatically when the database is unreachable** — the
  test files check connectivity at startup. A green suite on a machine without
  MySQL/InfluxDB has silently skipped those tests. When reviewing someone else's
  test run, ask *which tests skipped*, not just whether it passed.
- Much of the pipeline is serial ports, UDP on specific interfaces, and live MQTT
  brokers. Those paths are not exercised by a generic CI or cloud environment.
- `pytest test/` for the full suite; `flake8` on changed Python files (settings in
  `.flake8`). CI runs on `dev`.

---

## 7. Submodules

`web_backend` and `web_frontend` are **separate repositories**, not directories:

| Path | Repo | Stack |
|---|---|---|
| `web_backend` | `OceanDataTools/fastapi-template` | FastAPI, Poetry, JWT + API-key auth |
| `web_frontend` | `OceanDataTools/vite-react-template` | Vite, React, TypeScript, Tailwind, Redux |

Ordering matters: a fix lands in the submodule repo via its own PR **first**,
then a pointer-bump PR in the main repo picks it up (e.g. #632). Work that
touches submodule pointers must be serialized — parallel branches collide on
those two lines.

`web_backend` requires **Python ≥ 3.11** (stdlib `tomllib`), the same floor as
the core package since #716, so the installer builds both venvs with one
interpreter. Node must be **≥ 22.13.0** for vite/vitest/jsdom (#633).

---

## 8. Repo layout notes

- `local/` holds vessel-specific overrides and is typically a **symlink to an
  external repo**. Don't modify its device definitions unless the task
  specifically requires it.
- `contrib/devices/` holds community-contributed device definitions used by the
  NMEA parser.
- Docs are auto-generated via GitHub Actions and PR'd against `dev`; the workflow
  opens a PR rather than pushing directly, because `dev` is protected.

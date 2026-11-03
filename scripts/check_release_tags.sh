#!/bin/bash
#
# Fail if a branch doesn't describe as the latest release (#621, #624).
#
# `git describe` names the *nearest* reachable tag, not the newest, and
# setuptools_scm derives the version the UIs display from it. When releases
# were squash-merged onto master, dev described as v2.3.1 long after v2.6.x
# had shipped. Releases are now true merges that are merged back into dev
# (RELEASING.md), which keeps the latest release the nearest tag. This checks
# that it is:
#
#   1. The latest release - the nearest tag on the release branch - must be
#      reachable from the branch. If it isn't, the release was never merged
#      back into dev (or was merged back with a squash, which has the same
#      effect).
#   2. The branch's nearest tag must be that release, or a pre-release of a
#      later version: a release candidate such as v2.8.0rc1, or an old-style
#      vX.Y.Z.dev0 marker. Anything else - an older release, or a pre-release
#      of the latest version or an earlier one - is the #621 failure.
#
# Usage:
#   scripts/check_release_tags.sh [branch [release_branch]]
#
# The defaults, HEAD and origin/master, are what CI checks. It needs the full
# history and tags (in GitHub Actions, check out with fetch-depth: 0).

set -u

branch=${1:-HEAD}
release_branch=${2:-origin/master}

if ! latest=$(git describe --tags --abbrev=0 "$release_branch" 2> /dev/null); then
    echo "No tag is reachable from $release_branch, so there's nothing to check."
    exit 0
fi
if ! found=$(git describe --tags --abbrev=0 "$branch" 2> /dev/null); then
    echo "FAIL: no tag is reachable from $branch; the latest release is $latest."
    exit 1
fi

if ! git merge-base --is-ancestor "$latest" "$branch"; then
    echo "FAIL: the latest release, $latest, is not reachable from $branch."
    echo "Merge $release_branch back into it with a true merge commit, not a"
    echo "squash; see RELEASING.md, step 4."
    exit 1
fi

if [ "$found" = "$latest" ]; then
    echo "OK: $branch describes as $latest, the latest release."
    exit 0
fi

# vMAJOR.MINOR.PATCH, then any pre-release suffix (rc1, .dev0, a1, b2, ...)
version_re='^v([0-9]+)\.([0-9]+)\.([0-9]+)(.*)$'
prerelease_re='^(\.?(rc|a|b|alpha|beta)[0-9]+|\.dev[0-9]+)$'

# Succeed if version $1 (as "major minor patch") is later than version $2
later_than() {
    local a b
    read -r -a a <<< "$1"
    read -r -a b <<< "$2"
    local i
    for i in 0 1 2; do
        if [ "${a[$i]}" -gt "${b[$i]}" ]; then return 0; fi
        if [ "${a[$i]}" -lt "${b[$i]}" ]; then return 1; fi
    done
    return 1
}

if [[ $found =~ $version_re ]]; then
    found_version="${BASH_REMATCH[1]} ${BASH_REMATCH[2]} ${BASH_REMATCH[3]}"
    found_suffix=${BASH_REMATCH[4]}
    if [[ $latest =~ $version_re ]]; then
        latest_version="${BASH_REMATCH[1]} ${BASH_REMATCH[2]} ${BASH_REMATCH[3]}"
        if [[ $found_suffix =~ $prerelease_re ]] && \
               later_than "$found_version" "$latest_version"; then
            echo "OK: $branch describes as $found, a pre-release of a version"
            echo "after the latest release, $latest."
            exit 0
        fi
    fi
fi

echo "FAIL: $branch describes as $found, but the latest release is $latest."
echo "git describe, and the version setuptools_scm derives from it, will report"
echo "$found. See RELEASING.md and issue #621."
exit 1

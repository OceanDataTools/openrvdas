#!/bin/bash
#
# Fail if any shell script defines the same function name twice.
#
# Bash silently accepts a redefinition and uses the last one, so a function
# duplicated by a bad merge changes behaviour with no error anywhere. That is
# what happened in issue #615, where install_openrvdas.sh carried two
# setup_ufw definitions and shipped that way.
#
# ShellCheck does not catch this - it has no check for redefined functions -
# so this is a separate, deliberately small script.
#
# Usage:
#   scripts/check_duplicate_functions.sh [file ...]
#
# With no arguments, checks every tracked *.sh file except local/ (a symlink
# to a ship-specific repo) and utils/deprecated/.

set -u

if [ "$#" -gt 0 ]; then
    FILES=("$@")
else
    # shellcheck disable=SC2207
    FILES=($(git ls-files '*.sh' | grep -v '^local/' | grep -v '^utils/deprecated/'))
fi

STATUS=0

for f in "${FILES[@]}"; do
    [ -f "$f" ] || continue

    # Two definition styles, both anchored at column 0:
    #   function name {   /   function name() {
    #   name() {
    # Requiring either the 'function' keyword or '()' keeps embedded config
    # heredocs out of the results - an nginx block like "events {" would
    # otherwise look like a definition.
    DUPES=$(sed -nE \
        -e 's/^function[[:space:]]+([A-Za-z_][A-Za-z0-9_]*).*/\1/p' \
        -e 's/^([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*\(\)[[:space:]]*\{.*/\1/p' \
        "$f" | sort | uniq -d)

    if [ -n "$DUPES" ]; then
        STATUS=1
        while IFS= read -r name; do
            echo "ERROR: $f defines '$name' more than once, at line(s):"
            grep -nE "^(function[[:space:]]+${name}([[:space:]]|\(|\{)|${name}[[:space:]]*\(\)[[:space:]]*\{)" \
                "$f" | sed 's/^/    /'
        done <<< "$DUPES"
    fi
done

if [ "$STATUS" -eq 0 ]; then
    echo "No duplicate function definitions found in ${#FILES[@]} file(s)."
fi

exit $STATUS

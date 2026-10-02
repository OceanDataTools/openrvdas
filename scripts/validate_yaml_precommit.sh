#!/bin/bash
#
# Pre-commit hook to validate YAML configuration files.
#
# Installation:
#   ln -sf ../../scripts/validate_yaml_precommit.sh .git/hooks/pre-commit
#
# Or add to your existing pre-commit hook.
#

# Find the repository root
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Get list of staged YAML files
STAGED_YAML=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(yaml|yml)$' | grep -v '^\.github/')

if [ -z "$STAGED_YAML" ]; then
    # No YAML files staged, nothing to validate
    exit 0
fi

# Check if the validator exists
VALIDATOR="$REPO_ROOT/logger/utils/validate_config.py"
if [ ! -f "$VALIDATOR" ]; then
    echo "Warning: YAML validator not found at $VALIDATOR"
    exit 0
fi

# Prefer the project's own venv. Otherwise this runs under whatever python3
# happens to be first on PATH - a pyenv shim, an unrelated venv, the distro
# python - which need not have PyYAML. OpenRVDAS installs its dependencies
# into $REPO_ROOT/venv, so a developer who has not activated it is the normal
# case rather than the unusual one. See issue #646.
PYTHON=python3
if [ -x "$REPO_ROOT/venv/bin/python3" ]; then
    PYTHON="$REPO_ROOT/venv/bin/python3"
fi

# Being unable to run the check is not the same as the YAML being wrong. Warn
# and let the commit through - as we already do just above for a missing
# validator - rather than reporting valid YAML as broken, which also trains
# people to reach for --no-verify as a matter of habit.
if ! "$PYTHON" -c 'import yaml' 2> /dev/null; then
    # Report the interpreter we actually resolved to, not the word "python3" -
    # which one got picked is the whole question when this fires.
    RESOLVED="$(command -v "$PYTHON" || echo "$PYTHON")"
    echo "Warning: PyYAML is not available to $RESOLVED, so YAML files were"
    echo "         not validated. Activate the OpenRVDAS virtual environment,"
    echo "         or install it there:"
    echo "             $RESOLVED -m pip install pyyaml"
    exit 0
fi

# Validate staged YAML files
echo "Validating YAML configuration files..."

ERRORS=0
for file in $STAGED_YAML; do
    # Skip files that don't exist (deleted files)
    if [ ! -f "$REPO_ROOT/$file" ]; then
        continue
    fi

    # Run validator
    if ! "$PYTHON" "$VALIDATOR" "$REPO_ROOT/$file" 2>&1; then
        ERRORS=1
    fi
done

if [ $ERRORS -eq 1 ]; then
    echo ""
    echo "YAML validation failed. Please fix the errors above."
    echo "To bypass this check, use: git commit --no-verify"
    exit 1
fi

echo "YAML validation passed."
exit 0

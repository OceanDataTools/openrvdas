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
STAGED_YAML=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(yaml|yml)$')

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

# Validate staged YAML files
echo "Validating YAML configuration files..."

ERRORS=0
for file in $STAGED_YAML; do
    # Skip files that don't exist (deleted files)
    if [ ! -f "$REPO_ROOT/$file" ]; then
        continue
    fi

    # Run validator
    if ! python3 "$VALIDATOR" "$REPO_ROOT/$file" 2>&1; then
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

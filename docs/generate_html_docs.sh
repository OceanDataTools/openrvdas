#!/usr/bin/env bash
# Generate HTML API documentation for OpenRVDAS logger and server components.
# Uses pdoc (>= 14.0.0) which produces fully self-contained HTML with no
# external resource dependencies, so the output works offline.
#
# Usage:
#   ./docs/generate_html_docs.sh          # regenerate docs
#   pdoc logger server                    # live-reloading preview in browser
#
# Requirements:
#   pdoc >= 14.0.0  (pip install "pdoc>=14.0.0")
#   All OpenRVDAS dependencies installed (for import to succeed)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/html"
TEMPLATE_DIR="$SCRIPT_DIR/pdoc_templates"

cd "$REPO_ROOT"

# Activate venv if present and pdoc not already on PATH
if ! command -v pdoc &>/dev/null; then
    if [[ -f "$REPO_ROOT/venv/bin/activate" ]]; then
        # shellcheck source=/dev/null
        source "$REPO_ROOT/venv/bin/activate"
    fi
fi

if ! command -v pdoc &>/dev/null; then
    echo "Error: pdoc not found. Install with: pip install 'pdoc>=14.0.0'" >&2
    exit 1
fi

PDOC_VERSION=$(pdoc --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
PDOC_MAJOR="${PDOC_VERSION%%.*}"
if [[ "$PDOC_MAJOR" -lt 14 ]]; then
    echo "Error: pdoc >= 14.0.0 required (found $PDOC_VERSION). Install with: pip install 'pdoc>=14.0.0'" >&2
    exit 1
fi

# Find subpackages whose Python files contain no docstrings at all.
# Returns newline-separated list of relative package paths (e.g. "logger/devices").
EMPTY_PKG_PATHS=$(python3 - << 'PYEOF'
import ast, os

def has_any_docstring(filepath):
    try:
        tree = ast.parse(open(filepath).read())
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node):
                return True
    return False

for pkg in ['logger', 'server']:
    for root, dirs, files in os.walk(pkg):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        py_files = [f for f in files if f.endswith('.py') and not f.startswith('test_')]
        if not py_files or root == pkg:
            continue
        if not any(has_any_docstring(os.path.join(root, f)) for f in py_files):
            print(root)
PYEOF
)

echo "Generating documentation with pdoc $PDOC_VERSION..."
echo "Output: $OUTPUT_DIR"

# Remove old generated content so stale files don't linger.
# Covers both old (logger/, server/) and new (openrvdas/) output structures.
rm -rf "$OUTPUT_DIR/logger" "$OUTPUT_DIR/server" "$OUTPUT_DIR/openrvdas" \
       "$OUTPUT_DIR/index.html" "$OUTPUT_DIR/search.js" \
       "$OUTPUT_DIR/logger.html" "$OUTPUT_DIR/server.html"

pdoc \
    --output-directory "$OUTPUT_DIR" \
    --template-dir "$TEMPLATE_DIR" \
    --docformat restructuredtext \
    --footer-text "OpenRVDAS" \
    ./logger \
    ./server

# Remove generated pages for subpackages that have no docstrings at all,
# and scrub their references from index.html and search.js.
# pdoc places output under openrvdas/ (the project directory name).
if [[ -n "$EMPTY_PKG_PATHS" ]]; then
    echo "Removing empty package pages:"
    while IFS= read -r pkg_path; do
        [[ -z "$pkg_path" ]] && continue
        flat_html="$OUTPUT_DIR/openrvdas/${pkg_path}.html"
        pkg_dir="$OUTPUT_DIR/openrvdas/$pkg_path"
        if [[ -f "$flat_html" ]]; then
            echo "  Removing $flat_html"
            rm -f "$flat_html"
        fi
        if [[ -d "$pkg_dir" ]]; then
            echo "  Removing $pkg_dir/"
            rm -rf "$pkg_dir"
        fi
        # Remove references from index.html and search.js (use dotted module name).
        # sed -i.bak is portable across macOS and Linux; we remove the backup immediately.
        mod_name="${pkg_path//\//.}"
        sed -i.bak "/${mod_name//./\.}/d" "$OUTPUT_DIR/index.html" "$OUTPUT_DIR/search.js"
        rm -f "$OUTPUT_DIR/index.html.bak" "$OUTPUT_DIR/search.js.bak"
        # Remove reference from the parent package HTML (e.g. logger.html lists devices).
        leaf="${pkg_path##*/}"
        parent_html="$OUTPUT_DIR/openrvdas/${pkg_path%/*}.html"
        if [[ -f "$parent_html" ]]; then
            sed -i.bak "/${leaf}/d" "$parent_html"
            rm -f "${parent_html}.bak"
        fi
    done <<< "$EMPTY_PKG_PATHS"
fi

echo ""
echo "Done. Open $OUTPUT_DIR/index.html to browse."
echo ""
echo "For a live-reloading preview during development, run:"
echo "  pdoc logger server"

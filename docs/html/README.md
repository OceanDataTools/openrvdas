# OpenRVDAS Logger Component HTML Documents

This directory contains automatically-generated HTML documentation for OpenRVDAS
logger components and server scripts.

The docs are fully self-contained (no external resources fetched), so they work
offline. Open `index.html` in any browser to start browsing.

## Regenerating

Run the generation script from the repo root:

```bash
./docs/generate_html_docs.sh
```

Requirements: `pdoc >= 14.0.0` and all OpenRVDAS dependencies installed.
If using the project venv, pdoc is included in `utils/requirements.txt` and the
script will activate the venv automatically.

## Live preview during development

```bash
# Serves docs with live reload at http://localhost:8080
source venv/bin/activate
pdoc logger server
```

## Generated with

[pdoc](https://pdoc.dev/) >= 14.0.0

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository. It has two sections:

1. **[Architecture](#part-1-architecture)** — what the system is and how it
   fits together: the data pipeline, server layer, web frontends,
   configuration system, and the commands used to build, test, and run it.
2. **[Workflow](#part-2-workflow)** — how to work on it: branching and PR
   conventions, code style, component patterns, and things to avoid.

Full project documentation: https://www.oceandatatools.org/openrvdas-docs/

---

# Part 1: Architecture

## Overview

OpenRVDAS (Open Research Vessel Data Acquisition System) is a Python framework
for building modular data acquisition systems on research vessels. It follows a
**Reader → Transform → Writer** composition pattern where `Listener` objects
chain these components together.

## Development Commands

All commands assume the virtual environment is active:
```bash
source /opt/openrvdas/venv/bin/activate
```

**Run all tests:**
```bash
pytest test/
```

**Run a single test file or test:**
```bash
pytest test/logger/readers/test_text_file_reader.py
pytest test/logger/readers/test_text_file_reader.py::TextFileReaderTest::test_read
```

**Run the listener directly:**
```bash
listen --config_file test/configs/simple_logger.yaml
# or
python logger/listener/listen.py --logfile test/NBP1406/... --write_file -
```

**Regenerate API docs:**
```bash
bash docs/generate_html_docs.sh
```

## Core Data Pipeline

The fundamental unit is the **Listener** (`logger/listener/listener.py`), which
composes:
- One or more **Readers** (`logger/readers/`) — data sources (serial ports,
  files, network, MQTT, HTTP, databases, etc.)
- Zero or more **Transforms** (`logger/transforms/`) — processing (parse,
  filter, prefix, QC, format conversion, etc.)
- One or more **Writers** (`logger/writers/`) — data sinks (files, network,
  databases, InfluxDB, Grafana, etc.)

Readers run in parallel; transforms run in series; writers run in parallel.

```
SerialReader ─┐
NetworkReader ─┤→ ParseTransform → PrefixTransform → FileWriter
               │                                    → DatabaseWriter
               │                                    → CachedDataWriter
```

### Base Classes

- `logger/utils/base_module.py` — `BaseModule`: parent of all
  readers/transforms/writers; provides type-checking via Python type hints,
  `can_process_record()`, and `digest_record()` for handling lists and Nones
- `logger/readers/reader.py` — `Reader(BaseModule)`: requires `read()` method
- `logger/writers/writer.py` — `Writer(BaseModule)`: requires `write(record)`
  method
- `logger/transforms/transform.py` — `Transform(BaseModule)`: requires
  `transform(record)` method

### DAS Records

Parsed data flows as `DASRecord` objects (`logger/utils/das_record.py`):
`{timestamp, message_type, fields: {name: value, ...}}`. Raw strings also flow
through the pipeline before parsing.

## Server Layer

`server/logger_manager.py` manages multiple loggers as configured processes.
It reads desired configuration from a `ServerAPI` implementation and runs each
logger config in its own subprocess via `LoggerRunner`
(`server/logger_runner.py`), capturing the process's stderr and restarting
loggers that die unexpectedly:

- `server/server_api.py` — abstract `ServerAPI` base class; defines the cruise
  configuration data model
- `server/sqlite_server_api.py`, `server/in_memory_server_api.py` — standalone
  implementations
- `server/fastapi_server_api.py`, `django_gui/django_server_api.py` —
  web-backed implementations
- `server/cached_data_server.py` — WebSocket server that caches latest data
  values and broadcasts status

## Web Frontends

**Django GUI** (`django_gui/`) — the primary management console; served via
uWSGI + nginx; manages cruise configs, logger control, data display.

**FastAPI Backend** (`web_backend/`) — a git submodule; provides JWT + API key
auth for a new React-based UI. Has its own `CLAUDE.md` at
`web_backend/CLAUDE.md`. Run with `poetry run uvicorn app.main:app`.

**React Frontend** (`web_frontend/`) — Vite + React + TypeScript + Tailwind +
Redux. Run with:
```bash
cd web_frontend && npm run dev      # dev server (port 5173)
cd web_frontend && npm run build    # production build
cd web_frontend && npm run test     # vitest
cd web_frontend && npm run lint     # eslint
```

## Configuration System

Loggers are defined by YAML cruise configs (e.g.,
`test/NBP1406/NBP1406_cruise.yaml`). A config defines:
- **loggers** — named loggers with lists of valid configs and optional host
  restrictions
- **modes** — named operating modes mapping logger names to config names
- **configs** — inline or file-referenced reader/transform/writer
  specifications

`logger/utils/read_config.py` handles YAML loading. The `validate_config` CLI
checks configs for correctness.

## Process Management

Production systems run via `supervisord`. Config files live in
`/etc/supervisor.d/` (RHEL) or `/etc/supervisor/conf.d/` (Ubuntu). Templates
are in `server/supervisord/`.

## Repository Notes

- The `local/` directory holds vessel-specific overrides and is typically a
  symlink to an external repo
- `contrib/devices/` holds community-contributed device type definitions used
  by the NMEA parser
- Database tests are skipped automatically when the relevant database is
  unavailable — the test files check connectivity at startup
- CI runs on the `dev` branch; docs are auto-generated via GitHub Actions and
  PRed against `dev`

---

# Part 2: Workflow

## Branching

- Always create a new branch before making any changes — never commit directly
  to `dev` or `master`
- Base all branches off `dev`, not `master`
- Use descriptive branch names that reference the issue being addressed, e.g.
  `issue_42` or `issue-42-fix-serial-reader-timeout`

## Pull Requests

- All changes land via pull request; the target branch is `dev` (not `master`)
- When the work addresses an issue, use a PR title of the form
  `[Issue #N] Short description`
- The PR body should summarize what changed and why, reference the issue
  number, and note any tests added or modified
- Note any new Python package dependencies explicitly in the PR

## Before Opening a PR

1. Run the existing tests relevant to the changed component
   (`pytest test/<subdirectory>/`), or the full suite (`pytest test/`)
2. Run flake8 on changed files (project settings are in `.flake8`)
3. Only open the PR if tests pass — if they fail, attempt to fix before
   escalating

## Code Style

- Python 3.8+ compatible (per `requires-python` in `pyproject.toml`)
- Follow existing patterns in the file being modified — do not introduce new
  style conventions mid-file
- Type hints are encouraged on `read()`/`write()`/`transform()` methods; see
  https://www.oceandatatools.org/openrvdas-docs/type_hints/
- Docstrings follow the existing format in the codebase
- YAML/JSON config files use 2-space indentation

## Component Patterns

- New Readers must implement a `read()` method; new Transforms a
  `transform(record)` method; new Writers a `write(record)` method — each
  subclassing the appropriate base class, with type hints to enable automatic
  type-checking via `can_process_record()`
- All components should handle None records gracefully (pass through or
  ignore)
- Prefer composition over inheritance — snap components together rather than
  subclassing heavily
- Components should make use of the type hints-based utility in base_module.py to determine whether they can handle a particular type of input, and how to handle it

## What NOT to Do

- Do not commit directly to `dev` or `master` — always work on a branch and
  open a PR
- Do not base branches on `master` — always use `dev`
- Do not modify `local/` device definition files unless the issue specifically
  requires it — these are ship-specific configurations
- Do not install new Python packages without noting them explicitly in the PR
- Do not leave the Django server or long-running logger processes running
- Do not modify `.env` files or any credential or config files

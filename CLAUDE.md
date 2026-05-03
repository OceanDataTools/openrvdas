# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

OpenRVDAS (Open Research Vessel Data Acquisition System) is a Python framework for building data acquisition systems on research vessels. It follows a **Reader → Transform → Writer** composition pattern where `Listener` objects chain these components together.

## Development Commands

All commands assume the virtual environment is active:
```bash
source /opt/openrvdas/venv/bin/activate
```

**Run all tests:**
```bash
pytest test/
```

**Run a single test file:**
```bash
pytest test/logger/readers/test_text_file_reader.py
```

**Run a specific test:**
```bash
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

## Architecture

### Core Data Pipeline

The fundamental unit is the **Listener** (`logger/listener/listener.py`), which composes:
- One or more **Readers** (`logger/readers/`) — data sources (serial ports, files, network, MQTT, HTTP, databases, etc.)
- Zero or more **Transforms** (`logger/transforms/`) — processing (parse, filter, prefix, QC, format conversion, etc.)
- One or more **Writers** (`logger/writers/`) — data sinks (files, network, databases, InfluxDB, Grafana, etc.)

Readers run in parallel; transforms run in series; writers run in parallel.

```
SerialReader ─┐
NetworkReader ─┤→ ParseTransform → PrefixTransform → FileWriter
               │                                    → DatabaseWriter
               │                                    → CachedDataWriter
```

### Base Classes

- `logger/utils/base_module.py` — `BaseModule`: parent of all readers/transforms/writers; provides type-checking via Python type hints, `can_process_record()`, and `digest_record()` for handling lists and Nones
- `logger/readers/reader.py` — `Reader(BaseModule)`: requires `read()` method
- `logger/writers/writer.py` — `Writer(BaseModule)`: requires `write(record)` method
- `logger/transforms/transform.py` — `Transform(BaseModule)`: requires `transform(record)` method

### Server Layer

`server/logger_manager.py` manages multiple loggers as configured processes. It reads desired configuration from a `ServerAPI` implementation and spawns `LoggerSupervisor` processes:

- `server/server_api.py` — abstract `ServerAPI` base class; defines the cruise configuration data model
- `server/sqlite_server_api.py`, `server/in_memory_server_api.py` — standalone implementations
- `server/fastapi_server_api.py`, `django_gui/django_server_api.py` — web-backed implementations
- `server/cached_data_server.py` — WebSocket server that caches latest data values and broadcasts status

### Web Frontends

**Django GUI** (`django_gui/`) — the primary management console; served via uWSGI + nginx; manages cruise configs, logger control, data display.

**FastAPI Backend** (`web_backend/`) — a git submodule; provides JWT + API key auth for a new React-based UI. Has its own `CLAUDE.md` at `web_backend/CLAUDE.md`. Run with `poetry run uvicorn app.main:app`.

**React Frontend** (`web_frontend/`) — Vite + React + TypeScript + Tailwind + Redux. Run with:
```bash
cd web_frontend && npm run dev      # dev server (port 5173)
cd web_frontend && npm run build    # production build
cd web_frontend && npm run test     # vitest
cd web_frontend && npm run lint     # eslint
```

### Configuration System

Loggers are defined by YAML cruise configs (e.g., `test/NBP1406/NBP1406_cruise.yaml`). A config defines:
- **loggers** — named loggers with lists of valid configs and optional host restrictions
- **modes** — named operating modes mapping logger names to config names
- **configs** — inline or file-referenced reader/transform/writer specifications

`logger/utils/read_config.py` handles YAML loading. `validate_config` CLI checks configs for correctness.

### DAS Records

Parsed data flows as `DASRecord` objects (`logger/utils/das_record.py`): `{timestamp, message_type, fields: {name: value, ...}}`. Raw strings also flow through the pipeline before parsing.

### Process Management

Production systems run via `supervisord`. Config files live in `/etc/supervisor.d/` (RHEL) or `/etc/supervisor/conf.d/` (Ubuntu). Templates are in `server/supervisord/`.

## Key Conventions

- New readers/writers/transforms should subclass the appropriate base class and use type hints on `read()`/`write()`/`transform()` to enable automatic type-checking via `can_process_record()`.
- Database tests are skipped automatically when the relevant database is unavailable — the test files check connectivity at startup.
- The `local/` directory holds vessel-specific overrides and is typically a symlink to an external repo.
- `contrib/devices/` holds community-contributed device type definitions used by the NMEA parser.
- CI runs on the `dev` branch; docs are auto-generated via GitHub Actions and PRed against `dev`.

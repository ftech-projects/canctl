# canctl — CAN Bus JSON CLI Runtime

## Overview
Python CAN CLI tool for LLM-controlled CAN device communication.
JSON Lines exclusive output, all stdout parseable JSONL.

## Stack
- Python 3.11+, click, python-can, cantools
- Exit codes: 0=success, 1=error, 2=timeout

## File Map

### Entry Point
- `canctl/canctl.py` — Click CLI entry point, subcommand registration

### Core Modules (`canctl/core/`)
- `bus.py` — Bus factory (open_bus), DryRunBus, VirtualBus, ReplayBus + CAN FD
- `message.py` — CanFrame dataclass (internal schema, ts nanosec, cmd/core 통일)
- `output.py` — JSONL stdout helper (emit, emit_error, emit_warning, format_bus)
- `errors.py` — Error codes (BUS_OFF, ARB_LOST, DECODE_ERROR, SIGNAL_CONFLICT, etc.)
- `filter.py` — FilterManager (HW filter + SW fallback 통합)
- `periodic.py` — PeriodicManager (HW send_periodic → SW per-job thread fallback)
- `dbc.py` — Multi-DBC load + conflict detection (later/first/error policy) + decode
- `jsonl.py` — JSONL file read/write utilities

### Commands (`canctl/cmd/`)
- `hw.py` — `hw list` interface enumeration
- `send.py` — Frame send (single or repeat, --fd, --dry-run)
- `recv.py` — Frame receive (queue-based, FilterManager, DBC decode, --requires)
- `monitor.py` — Full bus raw capture (thread-safe stats, rate_msg_s, overflow warning)
- `decode.py` — Offline DBC decoding (stdin or file, --dbc-priority)
- `play.py` — JSONL replay by timestamp (--speed, --loop, --jitter, --burst, --dry-run)

### Tests (`tests/`)
- `test_core.py` — Unit tests (51 tests: core modules + message + filter + bus types)
- `test_commands.py` — CLI simulation tests (dry-run, no hardware)
- `test.dbc` — Test DBC file (EngineData + VehicleSpeed)
- `sample_capture.jsonl` — Sample capture for decode/play tests

## JSON Output Types
frame, decoded, unknown, send, play, hw, stats, summary, warning, error,
periodic_start, periodic_stop

## Error Codes
HW_NOT_FOUND, TIMEOUT, INVALID_ARG, FILE_NOT_FOUND,
BUS_ERROR, BUS_OFF, ARB_LOST, SEND_FAIL, QUEUE_OVERFLOW,
PERIODIC_FAIL, DBC_PARSE_FAIL, INVALID_DBC, DECODE_ERROR, SIGNAL_CONFLICT

## Work Log
- 2026-03-26 — Initial implementation (P1-P7)
- 2026-03-26 — Architecture overhaul: CanFrame schema, bus types, filter API,
  periodic HW/SW fallback, DBC conflict, CAN FD, play jitter/burst, error expansion

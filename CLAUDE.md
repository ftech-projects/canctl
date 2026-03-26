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
- `bus.py` — Context Manager Bus factory (open_bus), DryRunBus
- `output.py` — JSONL stdout helper (emit, emit_error, emit_warning, format_bus)
- `errors.py` — Error code constants + CanctlError exception
- `periodic.py` — PeriodicManager (single scheduler thread for --requires)
- `dbc.py` — cantools wrapper, multi-DBC load + decode
- `jsonl.py` — JSONL file read/write utilities

### Commands (`canctl/cmd/`)
- `hw.py` — `hw list` interface enumeration
- `send.py` — Frame send (single or repeat, --dry-run)
- `recv.py` — Frame receive (filter + realtime DBC decode + --requires)
- `monitor.py` — Full bus raw capture (queue/overflow/stats threads)
- `decode.py` — Offline DBC decoding (stdin or file input)
- `play.py` — JSONL replay by timestamp (--speed, --loop, --dry-run)

### Tests (`tests/`)
- `test_core.py` — Unit tests for core modules
- `test_commands.py` — CLI simulation tests (dry-run, no hardware)
- `test.dbc` — Test DBC file (EngineData + VehicleSpeed)
- `sample_capture.jsonl` — Sample capture for decode/play tests

## JSON Output Types
frame, decoded, unknown, send, play, hw, stats, summary, warning, error,
periodic_start, periodic_stop

## Work Log
- 2026-03-26 — Initial implementation (P1-P7)

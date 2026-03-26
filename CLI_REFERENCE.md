# canctl CLI Reference — LLM API Document

## Overview

canctl is a JSON-only CAN Bus CLI. All stdout is parseable JSONL (one JSON object per line).
No human-readable text is ever printed. Errors also go to stdout as JSON.

- Exit code: `0` success, `1` error, `2` timeout
- Every output line contains: `type`, `ts` (unix timestamp), `bus` (e.g. `"pcan:PCAN_USBBUS1"`)
- `--dry-run` is available on all bus commands — runs full logic without hardware

---

## Commands

### hw list

Enumerate available CAN interfaces.

```
canctl hw list [--probe]
```

| Option | Default | Description |
|--------|---------|-------------|
| --probe | false | Actually attempt driver connection (slow) |

Output:
```jsonl
{"type":"hw","ts":1710000000.0,"bus":null,"interface":"pcan","channel":"PCAN_USBBUS1","state":"unknown"}
```

---

### send

Send CAN frame(s).

```
canctl send --id ID --data DATA [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| --interface, -i | pcan | pcan / vector / kvaser |
| --channel, -c | PCAN_USBBUS1 | Channel name |
| --bitrate, -b | 500000 | Bitrate in bps |
| --id | **required** | CAN ID in hex (e.g. 0x201, 0x18FF50E5) |
| --ext | false | Use 29-bit extended ID |
| --data | **required** | Hex bytes, space-separated OK (e.g. "01 02 03" or "010203") |
| --repeat | 1 | Send count (0 = infinite, Ctrl+C to stop) |
| --interval | 0.0 | Interval between repeats in seconds |
| --dry-run | false | Simulate without hardware |

Output per frame:
```jsonl
{"type":"send","ts":1710000000.1,"bus":"pcan:PCAN_USBBUS1","id":"0x201","ext":false,"dlc":8,"data":"0102030405060708","status":"ok"}
```

Final:
```jsonl
{"type":"summary","ts":1710000001.0,"bus":"pcan:PCAN_USBBUS1","sent":3}
```

---

### recv

Receive CAN frames with ID filtering and optional DBC decoding.

```
canctl recv --id ID [--id ID ...] [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| --interface, -i | pcan | pcan / vector / kvaser |
| --channel, -c | PCAN_USBBUS1 | Channel name |
| --bitrate, -b | 500000 | Bitrate in bps |
| --id | **required** | Filter ID(s) in hex, multiple allowed |
| --mask | 0x1FFFFFFF | Filter mask |
| --count | 0 | Stop after N frames (0 = infinite) |
| --timeout | 0.0 | Timeout in seconds (0 = infinite) |
| --dbc | none | DBC file path(s), multiple allowed |
| --requires | none | Periodic send spec "ID:DATA:INTERVALms", multiple allowed |
| --dry-run | false | Simulate without hardware |

Output per frame:
```jsonl
{"type":"frame","ts":1710000000.5,"bus":"pcan:PCAN_USBBUS1","id":"0x201","ext":false,"dlc":8,"data":"FF3C000000000000","signals":{"EngineRPM":3200.0}}
```

`signals` field appears only when `--dbc` is provided and decoding succeeds.

On timeout with zero frames:
```jsonl
{"type":"error","ts":1710000003.0,"bus":"pcan:PCAN_USBBUS1","code":"TIMEOUT","message":"no frame received within 3.0s"}
```

Final:
```jsonl
{"type":"summary","ts":1710000003.0,"bus":"pcan:PCAN_USBBUS1","received":10,"timeout":false,"elapsed":3.201}
```

---

### monitor

Capture all bus traffic (raw, no decoding). Use `decode` command for post-processing.

```
canctl monitor [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| --interface, -i | pcan | pcan / vector / kvaser |
| --channel, -c | PCAN_USBBUS1 | Channel name |
| --bitrate, -b | 500000 | Bitrate in bps |
| --output, -o | stdout | Save JSONL to file path |
| --duration | 0.0 | Capture duration in seconds (0 = until Ctrl+C) |
| --stats-interval | 0.0 | Print stats every N seconds (0 = disabled) |
| --queue-size | 10000 | Internal queue size |
| --overflow | ring | Queue overflow mode: drop / block / ring |
| --requires | none | Periodic send spec "ID:DATA:INTERVALms" |
| --dry-run | false | Simulate without hardware |

Output per frame:
```jsonl
{"type":"frame","ts":1710000000.5,"bus":"pcan:PCAN_USBBUS1","id":"0x201","ext":false,"dlc":8,"data":"FF3C000000000000"}
```

Stats (if --stats-interval > 0):
```jsonl
{"type":"stats","ts":1710000010.0,"bus":"pcan:PCAN_USBBUS1","total":8423,"dropped":0,"elapsed":10.0}
```

Final:
```jsonl
{"type":"summary","ts":1710000010.0,"bus":"pcan:PCAN_USBBUS1","total":8423,"dropped":0,"elapsed":10.0}
```

Overflow modes:
- `ring` (default): Drop oldest frames when queue is full
- `drop`: Drop new frames when queue is full
- `block`: Block receive thread until queue has space

---

### decode

Offline DBC decoding. Reads JSONL from stdin or file, outputs decoded JSONL.

```
canctl decode --dbc PATH [--dbc PATH ...] [--input PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| --dbc | **required** | DBC file path(s), multiple allowed |
| --input | stdin | JSONL input file path |

Input: `type: "frame"` records with `id` and `data` fields.
Non-frame records pass through unchanged.

Output:
```jsonl
{"type":"decoded","ts":1710000001.0,"bus":"pcan:PCAN_USBBUS1","id":"0x201","data":"FF3C000000000000","msg":"EngineData","signals":{"EngineRPM":{"value":3200.0,"unit":"rpm","min":0,"max":8000}}}
```

If frame ID is not in any DBC:
```jsonl
{"type":"unknown","ts":1710000001.0,"bus":"pcan:PCAN_USBBUS1","id":"0x999","data":"0102030405060708"}
```

`data` field is always preserved (raw + decoded coexist).

---

### play

Replay captured JSONL file with original timestamps.

```
canctl play INPUT_FILE [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| --interface, -i | pcan | pcan / vector / kvaser |
| --channel, -c | PCAN_USBBUS1 | Channel name |
| --bitrate, -b | 500000 | Bitrate in bps |
| --speed | 1.0 | Playback speed (2.0 = 2x, 0 = instant) |
| --loop | false | Loop playback |
| --dry-run | false | Simulate without hardware |

Output per frame:
```jsonl
{"type":"play","ts":1710000001.0,"bus":"pcan:PCAN_USBBUS1","id":"0x201","data":"FF3C000000000000","status":"sent"}
```

Final:
```jsonl
{"type":"summary","ts":1710000010.0,"bus":"pcan:PCAN_USBBUS1","played":8423,"elapsed":10.0}
```

---

## --requires (Periodic Send)

Available on `recv` and `monitor`. Sends frames periodically while the command runs.
Format: `ID:DATA:INTERVALms`

```
--requires "0x700:00:100ms"          # Send 0x00 to 0x700 every 100ms
--requires "0x300:FF00:50ms"         # Send 0xFF00 to 0x300 every 50ms
```

Multiple `--requires` allowed. Managed by a single scheduler thread.

Events emitted:
```jsonl
{"type":"periodic_start","ts":...,"bus":"pcan:PCAN_USBBUS1","id":"0x700","data":"00","interval_ms":100}
{"type":"periodic_stop","ts":...,"bus":"pcan:PCAN_USBBUS1","id":"0x700"}
```

---

## JSON Output Type Reference

| type | Emitted by | Description |
|------|-----------|-------------|
| hw | hw list | Interface info |
| send | send | Frame sent confirmation |
| frame | recv, monitor | Received raw frame |
| decoded | decode | DBC-decoded frame |
| unknown | decode | Frame not in DBC |
| play | play | Replayed frame |
| periodic_start | recv, monitor | Periodic send started |
| periodic_stop | recv, monitor | Periodic send stopped |
| stats | monitor | Periodic statistics |
| summary | all | Final summary on exit |
| warning | monitor | Non-fatal issue (e.g. queue overflow) |
| error | all | Error with code and message |

---

## Error Codes

| Code | Description |
|------|-------------|
| HW_NOT_FOUND | CAN interface not available |
| TIMEOUT | No frame received within timeout |
| SEND_FAIL | Frame send failed |
| BUS_ERROR | CAN bus error |
| PERIODIC_FAIL | Periodic manager crashed |
| DBC_PARSE_FAIL | DBC file parse error |
| INVALID_ARG | Invalid argument format |
| QUEUE_OVERFLOW | Monitor queue overflow |
| FILE_NOT_FOUND | Input file not found |

---

## Common Patterns

### 1. Read ECU signal with heartbeat requirement
```bash
canctl recv --id 0x201 --count 10 --timeout 5.0 \
            --dbc engine.dbc \
            --requires "0x700:00:100ms"
```

### 2. Capture full bus then analyze offline
```bash
canctl monitor --duration 10 --output session.jsonl \
               --requires "0x700:00:100ms"

canctl decode --dbc engine.dbc --dbc body.dbc --input session.jsonl
```

### 3. Pipe: capture → decode (realtime)
```bash
canctl recv --id 0x201 --id 0x202 --count 100 \
  | canctl decode --dbc engine.dbc
```

### 4. Offline test without hardware
```bash
canctl play session.jsonl --dry-run --speed 0 \
  | canctl decode --dbc engine.dbc
```

### 5. Bug reproduction at half speed
```bash
canctl play bug_session.jsonl --speed 0.5 --loop
```

### 6. Send single command frame
```bash
canctl send --id 0x18FF50E5 --ext --data "01 02 03 04 05 06 07 08"
```

### 7. Verify DBC decoding without bus
```bash
canctl decode --dbc signals.dbc --input captured.jsonl
```

---

## Parsing Rules for LLM

1. Read stdout line by line. Each line is a valid JSON object.
2. Check `type` field first to determine record kind.
3. `ts` is always present — use for time correlation.
4. `bus` identifies the channel — important for multi-bus setups.
5. On `type: "error"`, check `code` field for programmatic handling.
6. On `type: "summary"`, the command has finished.
7. `--dry-run` produces identical JSON structure — safe for logic testing.
8. stderr is never used. All output is stdout JSON.

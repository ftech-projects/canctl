# canctl CLI Reference — LLM API Document

## Overview

canctl is a JSON-only CAN Bus CLI. All stdout is parseable JSONL (one JSON object per line).
No human-readable text is ever printed. Errors also go to stdout as JSON.

- Exit code: `0` success, `1` error, `2` timeout
- Every output line contains: `type`, `ts` (unix timestamp), `bus` (e.g. `"pcan:PCAN_USBBUS1"`)
- `--dry-run` is available on all bus commands — runs full logic without hardware
- `--pretty` global flag for human-readable colored output

---

## Global Options

| Option | Description |
|--------|-------------|
| --pretty | Human-readable colored output (default: JSONL) |
| --version | Show version |

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
| --fd | false | CAN FD mode |
| --data-bitrate | 0 | CAN FD data bitrate (0 = same as bitrate) |
| --dry-run | false | Simulate without hardware |

Output per frame:
```jsonl
{"type":"send","ts":1710000000.1,"bus":"pcan:PCAN_USBBUS1","id":"0x201","ext":false,"dlc":8,"data":"0102030405060708","status":"ok"}
```

CAN FD frame includes `"fd":true` field.

Final:
```jsonl
{"type":"summary","ts":1710000001.0,"bus":"pcan:PCAN_USBBUS1","sent":3}
```

---

### recv

Receive CAN frames with queue-based architecture, ID filtering, and optional DBC decoding.

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
| --dbc-priority | later | DBC frame_id conflict policy: later / first / error |
| --requires | none | Periodic send spec "ID:DATA:INTERVALms", multiple allowed |
| --fd | false | CAN FD mode |
| --data-bitrate | 0 | CAN FD data bitrate |
| --dry-run | false | Simulate without hardware |

Architecture: Dedicated recv thread → queue → main thread consume. Non-blocking.

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

Capture all bus traffic (raw, no decoding). Thread-safe counters with rate calculation.

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
| --fd | false | CAN FD mode |
| --data-bitrate | 0 | CAN FD data bitrate |
| --dry-run | false | Simulate without hardware |

Output per frame:
```jsonl
{"type":"frame","ts":1710000000.5,"bus":"pcan:PCAN_USBBUS1","id":"0x201","ext":false,"dlc":8,"data":"FF3C000000000000"}
```

Stats (if --stats-interval > 0):
```jsonl
{"type":"stats","ts":1710000010.0,"bus":"pcan:PCAN_USBBUS1","total":8423,"dropped":0,"rate_msg_s":842.3,"elapsed":10.0}
```

Real-time overflow warning (emitted every 5s when drops occur):
```jsonl
{"type":"warning","ts":...,"bus":"pcan:PCAN_USBBUS1","code":"QUEUE_OVERFLOW","message":"ring buffer overflow: 123 dropped, rate=1500.0 msg/s","dropped":123,"rate":1500.0}
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
| --dbc-priority | later | DBC frame_id conflict policy: later / first / error |
| --input | stdin | JSONL input file path |

**DBC Conflict Policies:**
- `later` (default): Later-loaded DBC overrides earlier on same frame_id
- `first`: First-loaded DBC wins, later duplicates ignored with warning
- `error`: Raise SIGNAL_CONFLICT error on any frame_id duplication

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
| --jitter | 0.0 | Random ±jitter in milliseconds per frame |
| --burst | 1 | Send each frame N times (burst mode) |
| --fd | false | CAN FD mode |
| --data-bitrate | 0 | CAN FD data bitrate |
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

Multiple `--requires` allowed.

**Implementation strategy:**
1. Try `bus.send_periodic()` (driver-level HW timer, e.g. PCAN HW timer)
2. Fallback: per-job independent thread with drift compensation

Events emitted:
```jsonl
{"type":"periodic_start","ts":...,"bus":"pcan:PCAN_USBBUS1","id":"0x700","data":"00","interval_ms":100,"mode":"hw"}
{"type":"periodic_stop","ts":...,"bus":"pcan:PCAN_USBBUS1","id":"0x700"}
```

`mode` field: `"hw"` = driver-level periodic, `"sw"` = software thread fallback.

---

## Bus Types

| Type | Interface | Use Case |
|------|-----------|----------|
| Real bus | pcan/vector/kvaser | Production hardware |
| DryRunBus | `--dry-run` | Logic testing without hardware |
| VirtualBus | programmatic | LLM test automation (send → recv loopback) |
| ReplayBus | programmatic | Replay from JSONL records |

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
| stats | monitor | Periodic statistics (includes rate_msg_s) |
| summary | all | Final summary on exit |
| warning | monitor, recv | Non-fatal issue (e.g. queue overflow, DBC conflict) |
| error | all | Error with code and message |

---

## Error Codes

| Code | Description |
|------|-------------|
| HW_NOT_FOUND | CAN interface not available |
| TIMEOUT | No frame received within timeout |
| SEND_FAIL | Frame send failed |
| BUS_ERROR | CAN bus error |
| BUS_OFF | CAN bus-off state (hardware error) |
| ARB_LOST | CAN arbitration lost |
| PERIODIC_FAIL | Periodic manager crashed |
| DBC_PARSE_FAIL | DBC file parse error |
| INVALID_DBC | Invalid DBC file format |
| DECODE_ERROR | DBC signal decode failed for a frame |
| SIGNAL_CONFLICT | DBC frame_id duplication detected |
| INVALID_ARG | Invalid argument format |
| QUEUE_OVERFLOW | Monitor queue overflow |
| FILE_NOT_FOUND | Input file not found |

---

## Internal Message Schema

All commands use a unified `CanFrame` dataclass internally:
```json
{
  "type": "frame",
  "ts": 1710000000.123456789,
  "bus": "pcan:PCAN_USBBUS1",
  "id": "0x201",
  "ext": false,
  "dlc": 8,
  "data": "FF3C000000000000",
  "fd": false
}
```

- `ts`: float seconds (internal: nanosecond int for precision)
- `fd`: only present when CAN FD is active
- `id`: always hex string format "0x..."

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

### 5. Bug reproduction at half speed with jitter
```bash
canctl play bug_session.jsonl --speed 0.5 --jitter 5 --loop
```

### 6. Stress test with burst replay
```bash
canctl play session.jsonl --speed 0 --burst 10 --dry-run
```

### 7. Send CAN FD frame
```bash
canctl send --id 0x201 --data "0102030405060708090A0B0C" --fd --data-bitrate 2000000
```

### 8. Multi-DBC decode with priority
```bash
canctl decode --dbc oem.dbc --dbc custom.dbc --dbc-priority later --input session.jsonl
```

### 9. Send single command frame
```bash
canctl send --id 0x18FF50E5 --ext --data "01 02 03 04 05 06 07 08"
```

### 10. Verify DBC decoding without bus
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
9. `fd` field only appears when CAN FD is active.
10. `rate_msg_s` in stats shows real-time message throughput.

---

## Remote Execution via FtechEngine

canctl은 FtechEngine의 `diag/exec` API를 통해 원격 장비에서 실행할 수 있다.

### 동작 원리

FtechEngine `diag/exec`는 내부적으로 `cmd /c chcp 65001 >nul && {command}`로 실행하며,
stdout/stderr를 전체 버퍼링하여 JSON 응답으로 반환한다.

**ExecResponse 스키마:**
```json
{
  "Command": "C:/canctl/canctl.exe send --id 0x201 --data FF3C --dry-run",
  "ExitCode": 0,
  "Stdout": "{\"type\":\"send\",...}\n{\"type\":\"summary\",...}\n",
  "Stderr": ""
}
```

### curl 사용 예시

**프레임 송신:**
```bash
curl -X POST http://192.168.1.100:5050/api/v1/diag/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "canctl send --id 0x201 --data FF3C000000000000 --dry-run",
    "workingDirectory": "C:/canctl",
    "timeoutMs": 10000
  }'
```

**수신 대기 (timeout 필수):**
```bash
curl -X POST http://192.168.1.100:5050/api/v1/diag/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "canctl recv --id 0x201 --timeout 5.0 --count 10 --requires \"0x700:00:100ms\"",
    "workingDirectory": "C:/canctl",
    "timeoutMs": 30000
  }'
```

**버스 모니터링 (duration 필수):**
```bash
curl -X POST http://192.168.1.100:5050/api/v1/diag/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "canctl monitor --duration 10 --stats-interval 2",
    "workingDirectory": "C:/canctl",
    "timeoutMs": 30000
  }'
```

**캡처 → 디코드 (2단계 호출):**
```bash
# Step 1: 모니터링으로 캡처
curl -X POST http://192.168.1.100:5050/api/v1/diag/exec \
  -d '{"command": "canctl monitor --duration 5 --output C:/canctl/session.jsonl", "timeoutMs": 15000}'

# Step 2: 오프라인 디코드
curl -X POST http://192.168.1.100:5050/api/v1/diag/exec \
  -d '{"command": "canctl decode --dbc C:/canctl/engine.dbc --input C:/canctl/session.jsonl", "timeoutMs": 10000}'
```

### 제약사항

| 항목 | 설명 |
|------|------|
| 스트리밍 불가 | stdout 전체 버퍼링 → `recv`, `monitor`는 반드시 `--timeout` 또는 `--duration` 지정 |
| 파이프 불가 | `cmd1 \| cmd2` 파이프라인 사용 불가 → 별도 호출로 대체 |
| 메모리 주의 | 대량 출력(수천 프레임)은 Stdout 버퍼에 쌓임 → `--count`/`--duration`으로 제한 |
| timeoutMs 설정 | canctl timeout보다 여유 있게 (canctl 5s → timeoutMs 10000 이상) |
| SYSTEM 계정 | FtechEngine은 SYSTEM 계정으로 실행 → PCAN USB 드라이버 접근 현장 확인 필요 |
| 인증 없음 | diag/exec API에 인증 없음 → 네트워크 격리 또는 방화벽 필수 |

### 권장 패턴

1. **송신**: `canctl send --id ID --data DATA [--repeat N]` — 단순, 즉시 완료
2. **수신**: `canctl recv --id ID --timeout T --count N` — 반드시 종료 조건 지정
3. **모니터링**: `canctl monitor --duration T --output FILE` — 파일 저장 후 별도 디코드
4. **디코드**: `canctl decode --dbc DBC --input FILE` — 오프라인, 빠름
5. **재생**: `canctl play FILE --speed S` — 캡처 파일 기반, 즉시 완료

### ExecResponse 파싱 (Python)

```python
import json
import httpx

# diag/exec 호출
resp = httpx.post("http://192.168.1.100:5050/api/v1/diag/exec", json={
    "command": "canctl send --id 0x201 --data FF3C --dry-run",
    "timeoutMs": 10000,
})
exec_result = resp.json()

# exit code 확인
if exec_result["ExitCode"] != 0:
    print(f"실패: {exec_result['Stderr']}")
else:
    # JSONL 줄별 파싱
    for line in exec_result["Stdout"].strip().split("\n"):
        record = json.loads(line)
        if record["type"] == "send":
            print(f"송신 완료: {record['id']} → {record['data']}")
        elif record["type"] == "summary":
            print(f"총 {record['sent']}프레임 송신")
```

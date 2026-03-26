"""에러 코드 정의 및 에러 JSON 생성"""

# 에러 코드 상수 — 일반
HW_NOT_FOUND = "HW_NOT_FOUND"
TIMEOUT = "TIMEOUT"
INVALID_ARG = "INVALID_ARG"
FILE_NOT_FOUND = "FILE_NOT_FOUND"

# 에러 코드 상수 — 버스/송수신
BUS_ERROR = "BUS_ERROR"
BUS_OFF = "BUS_OFF"
ARB_LOST = "ARB_LOST"
SEND_FAIL = "SEND_FAIL"
QUEUE_OVERFLOW = "QUEUE_OVERFLOW"

# 에러 코드 상수 — 주기 송신
PERIODIC_FAIL = "PERIODIC_FAIL"

# 에러 코드 상수 — DBC/디코딩
DBC_PARSE_FAIL = "DBC_PARSE_FAIL"
INVALID_DBC = "INVALID_DBC"
DECODE_ERROR = "DECODE_ERROR"
SIGNAL_CONFLICT = "SIGNAL_CONFLICT"


class CanctlError(Exception):
    """canctl 공통 예외. code + message 보유."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

"""에러 코드 정의 및 에러 JSON 생성"""

# 에러 코드 상수
HW_NOT_FOUND = "HW_NOT_FOUND"
TIMEOUT = "TIMEOUT"
PERIODIC_FAIL = "PERIODIC_FAIL"
DBC_PARSE_FAIL = "DBC_PARSE_FAIL"
INVALID_ARG = "INVALID_ARG"
QUEUE_OVERFLOW = "QUEUE_OVERFLOW"
SEND_FAIL = "SEND_FAIL"
BUS_ERROR = "BUS_ERROR"
FILE_NOT_FOUND = "FILE_NOT_FOUND"


class CanctlError(Exception):
    """canctl 공통 예외. code + message 보유."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

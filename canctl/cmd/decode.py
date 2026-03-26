"""decode — 오프라인 DBC 디코딩 (stdin 또는 파일 입력)"""

import click

from ..core.dbc import DbcDecoder
from ..core.jsonl import read_jsonl
from ..core.output import emit


@click.command("decode")
@click.option("--dbc", "dbc_paths", multiple=True, required=True,
              help="DBC 경로, 복수 지정 가능")
@click.option("--input", "input_path", default=None,
              help="JSONL 입력 파일 (기본: stdin)")
def decode(dbc_paths, input_path):
    """오프라인 DBC 디코딩. stdin 또는 파일 입력."""
    decoder = DbcDecoder(dbc_paths)

    for record in read_jsonl(input_path):
        # frame 타입만 디코딩
        if record.get("type") != "frame":
            emit(record)
            continue

        data_hex = record.get("data", "")
        id_str = record.get("id", "0x0")
        arb_id = int(id_str, 16)

        try:
            data = bytes.fromhex(data_hex)
        except ValueError:
            emit(record)
            continue

        result = decoder.decode(arb_id, data)

        decoded_record = {
            "type": "decoded",
            "ts": record.get("ts"),
            "bus": record.get("bus"),
            "id": id_str,
            "data": data_hex,
        }

        if result:
            decoded_record["msg"] = result["msg"]
            decoded_record["signals"] = result["signals"]
        else:
            # DBC에 없는 메시지 → unknown 타입
            decoded_record["type"] = "unknown"

        emit(decoded_record)

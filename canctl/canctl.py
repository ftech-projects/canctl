"""canctl - CAN Bus JSON CLI runtime"""

import os
import sys

# Windows cp949 인코딩 문제 방지
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

import click

from . import __version__
from .core.errors import CanctlError
from .core.output import emit_error, set_pretty


@click.group()
@click.version_option(version=__version__, prog_name="canctl")
@click.option("--pretty", is_flag=True, default=False,
              help="Human-readable output (default: JSONL)")
def cli(pretty):
    """canctl - CAN Bus JSON CLI for LLM-controlled device communication."""
    set_pretty(pretty)


# 서브커맨드 등록
from .cmd.hw import hw       # noqa: E402
from .cmd.send import send   # noqa: E402
from .cmd.recv import recv   # noqa: E402
from .cmd.monitor import monitor  # noqa: E402
from .cmd.decode import decode    # noqa: E402
from .cmd.play import play        # noqa: E402

cli.add_command(hw)
cli.add_command(send)
cli.add_command(recv)
cli.add_command(monitor)
cli.add_command(decode)
cli.add_command(play)


def main():
    try:
        cli(standalone_mode=False)
    except CanctlError as e:
        emit_error(e.code, e.message)
        sys.exit(1)
    except SystemExit as e:
        sys.exit(e.code)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        emit_error("UNKNOWN", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()

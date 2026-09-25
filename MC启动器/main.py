"""MCL-神启动器 入口。

用法：
  python main.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcl import utils  # noqa: E402

utils.get_logger("main").info("MCL 启动器启动")


def main() -> None:
    from mcl.ui import run
    run()


if __name__ == "__main__":
    main()

"""NCL 启动器 入口。

用法：
  python main.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcl import paths, utils  # noqa: E402

log = utils.get_logger("main")
log.info("NCL 启动器启动")


def main() -> None:
    # 单文件 exe 双击即用：首次运行自动铺开 NCLData 与 .minecraft 目录骨架
    info = paths.ensure_layout()
    log.info("数据目录: %s", info["root"])
    log.info("游戏目录: %s", info["minecraft"])
    log.info("新建目录 %d 个, 首次运行=%s", len(info["created"]), info["first_run"])
    from mcl.ui import run
    run()


if __name__ == "__main__":
    main()

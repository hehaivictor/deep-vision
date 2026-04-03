#!/usr/bin/env python3
"""DeepVision Web 预启动初始化。

用途：
- 在 Web 进程真正开始接收请求前，显式完成必须自动执行的数据库初始化
- 打印启动阶段耗时，避免继续依赖 import 副作用
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def main() -> int:
    from web.server import ensure_runtime_startup_initialized

    ensure_runtime_startup_initialized(reason="prestart", emit_logs=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

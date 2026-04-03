#!/usr/bin/env python3
"""DeepVision Gunicorn 启动器。

用途：
- 从 web/server.py 顶部读取 inline dependency metadata
- 自动追加 gunicorn 依赖
- 通过 uv run 构造完整运行环境后启动 web.wsgi:app
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = ROOT_DIR / "web" / "server.py"
GUNICORN_CONFIG = "web/gunicorn.conf.py"
WSGI_APP = "web.wsgi:app"
PRESTART_SCRIPT = "scripts/prestart_web.py"


def parse_server_dependencies() -> list[str]:
    text = SERVER_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^# dependencies = (\[.*\])\s*$", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"未在 {SERVER_SCRIPT} 中找到 inline dependencies 声明")

    raw = ast.literal_eval(match.group(1))
    if not isinstance(raw, list):
        raise RuntimeError(f"{SERVER_SCRIPT} 的 dependencies 不是列表")

    deps = [str(item).strip() for item in raw if str(item).strip()]
    if not deps:
        raise RuntimeError(f"{SERVER_SCRIPT} 的 dependencies 为空")
    return deps


def build_uv_prefix() -> list[str]:
    cmd = ["uv", "run"]
    for dep in parse_server_dependencies():
        cmd.extend(["--with", dep])
    return cmd


def build_prestart_command() -> list[str]:
    cmd = build_uv_prefix()
    cmd.extend(["python", PRESTART_SCRIPT])
    return cmd


def build_command(extra_args: list[str]) -> list[str]:
    cmd = build_uv_prefix()
    cmd.extend(["--with", "gunicorn", "gunicorn", "-c", GUNICORN_CONFIG])
    cmd.extend(extra_args)
    cmd.append(WSGI_APP)
    return cmd


def main(argv: list[str]) -> int:
    uv_bin = shutil.which("uv")
    if not uv_bin:
        print("未找到 uv，请先安装 uv 后再启动 Gunicorn。", file=sys.stderr)
        return 1

    os.chdir(ROOT_DIR)
    prestart_cmd = build_prestart_command()
    cmd = build_command(argv[1:])

    print("启动 DeepVision 生产模式（Gunicorn）")
    print("依赖来源: web/server.py inline dependency metadata + gunicorn")
    print(f"配置文件: {GUNICORN_CONFIG}")
    print("预启动初始化命令:")
    print("  " + " ".join(shlex.quote(part) for part in prestart_cmd))
    prestart_result = subprocess.run(prestart_cmd, check=False)
    if prestart_result.returncode != 0:
        print(f"预启动初始化失败，退出码: {prestart_result.returncode}", file=sys.stderr)
        return int(prestart_result.returncode or 1)
    print("执行命令:")
    print("  " + " ".join(shlex.quote(part) for part in cmd))

    os.execvp(cmd[0], cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

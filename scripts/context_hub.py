#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
DeepVision Context Hub 包装脚本。

目标：
1. 把 Context Hub 作为仓库内统一的第三方文档检索入口。
2. 优先复用本地或全局安装，缺失时自动回退到 npx。
3. 明确它只服务于开发/Agent 侧，不接入线上用户链路。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence


ROOT_DIR = Path(__file__).resolve().parent.parent
PACKAGE_NAME = "@aisuite/chub"


@dataclass(frozen=True)
class ResolvedCommand:
    tool_name: str
    source: str
    command: tuple[str, ...]


def _candidate_local_bins(tool_name: str, *, root_dir: Path) -> list[Path]:
    base_dir = root_dir / "node_modules" / ".bin"
    candidates = [base_dir / tool_name]
    if os.name == "nt":
        candidates.extend([base_dir / f"{tool_name}.cmd", base_dir / f"{tool_name}.ps1"])
    return candidates


def resolve_command(
    tool_name: str,
    *,
    root_dir: Path = ROOT_DIR,
    which: Callable[[str], str | None] = shutil.which,
) -> ResolvedCommand:
    for candidate in _candidate_local_bins(tool_name, root_dir=root_dir):
        if candidate.exists():
            return ResolvedCommand(
                tool_name=tool_name,
                source="local-node_modules",
                command=(str(candidate),),
            )

    global_path = which(tool_name)
    if global_path:
        return ResolvedCommand(
            tool_name=tool_name,
            source="global-path",
            command=(global_path,),
        )

    npx_path = which("npx")
    if not npx_path:
        raise RuntimeError(
            "未找到可用的 Context Hub 执行入口。请先安装 Node.js/npm，或执行 "
            "`npm install -g @aisuite/chub`。"
        )

    return ResolvedCommand(
        tool_name=tool_name,
        source="npx-package",
        command=(npx_path, "--yes", "--package", PACKAGE_NAME, "--", tool_name),
    )


def build_doctor_payload(
    *,
    root_dir: Path = ROOT_DIR,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "root_dir": str(root_dir),
        "package_name": PACKAGE_NAME,
        "runtime": {
            "node": which("node") or "",
            "npm": which("npm") or "",
            "npx": which("npx") or "",
        },
        "tools": {},
        "recommendation": (
            "优先用 `python3 scripts/context_hub.py get <id>` 获取第三方 SDK/API 文档；"
            "它只用于开发/Agent 侧，不用于线上业务链路。"
        ),
    }
    tools: dict[str, object] = {}
    for tool_name in ("chub", "chub-mcp"):
        try:
            resolved = resolve_command(tool_name, root_dir=root_dir, which=which)
            tools[tool_name] = asdict(resolved)
        except RuntimeError as exc:
            tools[tool_name] = {
                "tool_name": tool_name,
                "source": "unavailable",
                "command": (),
                "error": str(exc),
            }
    payload["tools"] = tools
    return payload


def print_doctor(payload: dict[str, object]) -> None:
    runtime = payload.get("runtime") or {}
    tools = payload.get("tools") or {}
    print("DeepVision Context Hub 诊断")
    print(f"- root_dir: {payload.get('root_dir')}")
    print(f"- package: {payload.get('package_name')}")
    print(f"- node: {runtime.get('node') or '未找到'}")
    print(f"- npm: {runtime.get('npm') or '未找到'}")
    print(f"- npx: {runtime.get('npx') or '未找到'}")
    for tool_name in ("chub", "chub-mcp"):
        tool_payload = tools.get(tool_name) or {}
        source = tool_payload.get("source") or "unknown"
        command = " ".join(tool_payload.get("command") or [])
        if source == "unavailable":
            print(f"- {tool_name}: 不可用")
            print(f"  error: {tool_payload.get('error')}")
            continue
        print(f"- {tool_name}: {source}")
        print(f"  command: {command}")
    print(f"- recommendation: {payload.get('recommendation')}")


def run_passthrough(
    tool_name: str,
    tool_args: Sequence[str],
    *,
    dry_run: bool = False,
    root_dir: Path = ROOT_DIR,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    resolved = resolve_command(tool_name, root_dir=root_dir, which=which)
    command = [*resolved.command, *tool_args]
    if dry_run:
        print(" ".join(command))
        return 0
    completed = subprocess.run(command, cwd=str(root_dir), check=False)
    return int(completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DeepVision 的 Context Hub 统一入口，用于第三方 SDK/API 文档检索。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印实际将执行的命令，不真正调用 Context Hub。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="检查 chub / chub-mcp 的可用性")
    doctor_parser.add_argument("--json", action="store_true", help="以 JSON 输出诊断结果")

    command_help = {
        "search": "透传到 `chub search`，用于查找可用文档 ID",
        "get": "透传到 `chub get`，用于拉取具体文档",
        "annotate": "透传到 `chub annotate`，记录本地经验",
        "feedback": "透传到 `chub feedback`，给文档投票反馈",
        "cache": "透传到 `chub cache`",
        "build": "透传到 `chub build`",
        "update": "透传到 `chub update`",
        "raw": "透传到 `chub`，用于上游新增命令尚未映射时",
        "mcp": "透传到 `chub-mcp`，用于以 MCP server 方式运行",
    }
    for name, help_text in command_help.items():
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="其余参数原样透传给上游命令",
        )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        payload = build_doctor_payload()
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_doctor(payload)
        return 0

    tool_name = "chub-mcp" if args.command == "mcp" else "chub"
    passthrough_args = list(args.args)
    if args.command not in {"raw", "mcp"}:
        passthrough_args.insert(0, args.command)
    return run_passthrough(tool_name, passthrough_args, dry_run=bool(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["flask", "flask-cors", "anthropic", "requests", "reportlab", "pillow", "jdcloud-sdk", "psycopg[binary]", "boto3"]
# ///
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="手动补齐历史对象存储迁移，不再依赖 Web 启动链路")
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="显式指定环境文件，可重复传入；后面的文件会覆盖前面的同名键",
    )
    parser.add_argument("--presentations", action="store_true", help="仅迁移历史演示稿记录")
    parser.add_argument("--ops-archives", action="store_true", help="仅迁移历史运维归档")
    parser.add_argument("--force", action="store_true", help="忽略进程内已执行标记，强制重新扫描")
    parser.add_argument("--output-json", default="", help="将结果写入指定 JSON 文件")
    return parser.parse_args()


def resolve_env_chain(args: argparse.Namespace) -> str:
    explicit = [str(item).strip() for item in (args.env_file or []) if str(item).strip()]
    if explicit:
        normalized = []
        for item in explicit:
            env_path = Path(item).expanduser()
            if not env_path.is_absolute():
                env_path = (ROOT_DIR / env_path).resolve()
            normalized.append(str(env_path))
        return os.pathsep.join(normalized)
    return str(os.environ.get("DEEPVISION_ENV_FILE") or "").strip()


def write_json_if_needed(output_json: str, payload: dict) -> None:
    target = str(output_json or "").strip()
    if not target:
        return
    output_path = Path(target).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    env_chain = resolve_env_chain(args)
    if env_chain:
        os.environ["DEEPVISION_ENV_FILE"] = env_chain

    os.chdir(ROOT_DIR)

    from web import server as server_module  # noqa: WPS433

    sync_presentations = bool(args.presentations)
    sync_ops_archives = bool(args.ops_archives)
    if not sync_presentations and not sync_ops_archives:
        sync_presentations = True
        sync_ops_archives = True

    if not server_module.is_object_storage_enabled():
        raise SystemExit("对象存储未启用，无法执行历史迁移")

    server_module.ensure_meta_index_schema()

    result = {
        "env_files": list(server_module.LOADED_ENV_FILES),
        "object_storage_enabled": True,
        "tasks": {},
    }
    failed = False

    if sync_presentations:
        summary = server_module.migrate_presentation_assets_to_object_storage_if_needed(force=bool(args.force))
        result["tasks"]["presentations"] = summary
        failed = failed or bool(summary.get("error"))

    if sync_ops_archives:
        summary = server_module.migrate_ops_archives_to_object_storage_if_needed(force=bool(args.force))
        result["tasks"]["ops_archives"] = summary
        failed = failed or bool(summary.get("error"))

    write_json_if_needed(args.output_json, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

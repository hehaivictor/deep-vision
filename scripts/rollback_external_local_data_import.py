#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["flask", "flask-cors", "anthropic", "requests", "reportlab", "pillow", "jdcloud-sdk", "psycopg[binary]"]
# ///
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import import_external_local_data_to_cloud as import_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回滚一次外部本地 data 导入")
    parser.add_argument("--backup-dir", required=True, help="导入脚本生成的备份目录")
    parser.add_argument("--output-json", default="", help="将回滚结果写入指定 JSON 文件")
    return parser.parse_args()


def run_rollback(*, backup_dir: str, output_json: str = "", server_module=None) -> dict:
    if server_module is None:
        server_module = import_service.load_server_module()

    backup_path = Path(backup_dir).expanduser().resolve()
    if not backup_path.exists() or not backup_path.is_dir():
        raise RuntimeError(f"备份目录不存在: {backup_path}")

    server_module.ensure_meta_index_schema()
    auth_db_path = str(server_module.AUTH_DB_PATH)
    meta_index_db_path = str(server_module.get_meta_index_db_target())
    cloud_summary_before = import_service.summarize_cloud_tables(server_module)
    restored = import_service.restore_db_snapshot(
        backup_path,
        auth_db_path=auth_db_path,
        meta_index_db_path=meta_index_db_path,
    )
    cloud_summary_after = import_service.summarize_cloud_tables(server_module)
    result = {
        "backup_dir": str(backup_path),
        "restored": restored,
        "cloud_summary_before": cloud_summary_before,
        "cloud_summary_after": cloud_summary_after,
        "applied": True,
    }
    if str(output_json or "").strip():
        import_service.write_json_file(Path(output_json).expanduser().resolve(), result)
    return result


def main() -> None:
    args = parse_args()
    result = run_rollback(
        backup_dir=args.backup_dir,
        output_json=args.output_json,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

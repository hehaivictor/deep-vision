# 云端导入预演

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`cloud-import` | 来源：`resources/harness/tasks/cloud-import.json`

外部本地 data 导入云端时，先确认源目录、目标用户、dry-run 结果和回滚入口，再决定是否进入 apply。

## 什么时候用

- 需要把外部本地 data 目录导入到云端目标用户
- 需要确认源目录是否完整、目标用户是否存在、dry-run 是否命中预期对象
- 正式导入前需要先准备回滚目录和专项回归

## 先跑哪些命令

```bash
python3 scripts/agent_harness.py --task cloud-import --task-var source_data_dir=/path/to/source-data --task-var target_user_id=123 --profile cloud --artifact-dir artifacts/harness-runs
python3 scripts/import_external_local_data_to_cloud.py --source-data-dir /path/to/source-data --target-user-id 123 --dry-run --output-json artifacts/harness-runs/cloud-import-dry-run.json
python3 -m unittest tests.test_external_local_data_import
```

确认需要正式执行时，再显式使用：

```bash
python3 scripts/import_external_local_data_to_cloud.py --source-data-dir /path/to/source-data --target-user-id 123 --apply --output-json artifacts/harness-runs/cloud-import-apply.json
```

如需回滚：

```bash
python3 scripts/rollback_external_local_data_import.py --backup-dir data/operations/cloud-imports/<backup-id> --output-json artifacts/harness-runs/cloud-import-rollback.json
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 workflow.json`
- `artifacts/harness-runs/cloud-import-dry-run.json`
- `artifacts/harness-runs/cloud-import-apply.json`
- `artifacts/harness-runs/cloud-import-rollback.json`

重点看：

- source_data_dir 是否完整，dry-run 命中的 sessions / reports / assets 是否合理
- target_user_id 是否存在且目标实例范围符合预期
- 专项回归是否覆盖导入与回滚链路
- apply 后是否产出可用于回滚的 backup_dir 和 JSON 摘要

## 哪些操作必须人工确认

- 使用 --apply 正式导入外部数据
- 覆盖已有目标用户数据或跨实例范围导入
- 执行 rollback 或手工修改 backup_dir 内容

## 相关文档

- `docs/agent/migration.md`
- `docs/full-data-migration-runbook.md`
- `docs/external-local-data-cloud-import-guide.md`

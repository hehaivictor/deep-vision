# 归属迁移预演

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`ownership-migration` | 来源：`resources/harness/tasks/ownership-migration.json`

优先使用 task harness 和 preview 链路确认账号、范围、备份与回滚入口，不直接跳到 apply。

## 什么时候用

- 需要把历史会话或报告批量归属给某个账号
- 需要确认某个用户当前拥有多少数据，再决定迁移范围
- 迁移前需要保留摘要 JSON、备份目录和回滚路径

## 先跑哪些命令

```bash
python3 scripts/admin_migrate_ownership.py list-users --query 137
python3 scripts/admin_migrate_ownership.py audit --user-account 13700000000
python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000 --profile auto --artifact-dir artifacts/harness-runs
python3 scripts/admin_migrate_ownership.py migrate --to-account 13700000000 --scope unowned --summary-json artifacts/ownership-migration-preview.json
```

确认需要正式执行时，再显式使用：

```bash
python3 scripts/admin_migrate_ownership.py migrate --to-account 13700000000 --scope unowned --apply --summary-json artifacts/ownership-migration-apply.json
```

如需回滚：

```bash
python3 scripts/admin_migrate_ownership.py rollback --backup-dir data/operations/ownership-migrations/<backup-id>
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 workflow.json`
- `对应 run 目录下的 guardrails.json`
- `artifacts/ownership-migration-preview.json`
- `data/operations/ownership-migrations/<backup-id>/metadata.json`
- `data/operations/ownership-migrations/<backup-id>/rollback.json`

重点看：

- 目标账号、scope、kind 是否符合预期
- preview 命中的 sessions / reports 数量是否异常偏大
- guardrails 是否仍通过 owner / scope 边界检查
- apply 后是否生成了可用备份目录

## 哪些操作必须人工确认

- 使用 --apply 正式改写归属
- 使用 scope=all 或 scope=from-user
- 删除、覆盖或手工修改备份目录内容
- 对生产风格数据执行 rollback

## 相关文档

- `docs/agent/admin-ops.md`
- `docs/agent/migration.md`
- `docs/full-data-migration-runbook.md`

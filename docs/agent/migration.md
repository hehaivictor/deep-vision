# 迁移与实例隔离

## 适用范围

当任务涉及以下内容时，先读本文档：

- `INSTANCE_SCOPE_KEY` 配置与多实例隔离
- 外部本地历史数据导入云端
- 历史数据回滚、对象存储历史补齐
- 迁移期手工治理与上线前检查

## 主要文档与脚本

- 实例隔离说明：[docs/instance-scope.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/instance-scope.md)
- 完整迁移手册：[docs/full-data-migration-runbook.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/full-data-migration-runbook.md)
- 外部本地数据导入指南：[docs/external-local-data-cloud-import-guide.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/external-local-data-cloud-import-guide.md)
- 业务迁移脚本：[scripts/import_external_local_data_to_cloud.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/import_external_local_data_to_cloud.py)
- 回滚脚本：[scripts/rollback_external_local_data_import.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/rollback_external_local_data_import.py)
- 对象存储历史补齐：[scripts/sync_object_storage_history.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/sync_object_storage_history.py)

## 先建立的心智模型

1. 在线服务必需初始化和历史治理任务是两类事情，不要混在一起。
2. `auth_db`、`license_db`、`meta_index schema` 这类当前环境必需动作可以自动完成。
3. 历史导入、对象存储补齐、老数据清理属于迁移期治理任务，默认要人工触发。
4. `INSTANCE_SCOPE_KEY` 决定共享 `data/` 时的数据可见边界，配置错误会造成跨实例串看或“数据消失”。

## 不变量

- 同一业务链接的所有副本，`INSTANCE_SCOPE_KEY` 必须一致。
- 不同业务链接如果共享同一份 `data/`，`INSTANCE_SCOPE_KEY` 必须不同。
- 业务迁移优先 `dry-run`，正式执行前要保留输出 JSON 和备份目录。
- 对象存储历史补齐不会替代业务迁移，也不会被业务回滚脚本自动撤销。

## 推荐执行顺序

1. 先确认目标环境和 `INSTANCE_SCOPE_KEY`。
2. 执行业务迁移 dry-run，检查用户映射、冲突、scope 策略。
3. 确认后再 apply。
4. 登录页面验证数据是否按预期可见。
5. 最后再执行对象存储历史补齐。
6. 仅在业务迁移异常时使用回滚脚本。

## 推荐验证

- 配置与部署边界：先读 [docs/instance-scope.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/instance-scope.md)
- 迁移顺序与执行命令：先读 [docs/full-data-migration-runbook.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/full-data-migration-runbook.md)
- 迁移类型快速判断：补读 [docs/external-local-data-cloud-import-guide.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/external-local-data-cloud-import-guide.md)

## 常见失误

- 把历史治理脚本误当成在线常驻任务。
- 在看不到旧文件的机器上执行对象存储补齐，结果长期空转。
- 修改 `INSTANCE_SCOPE_KEY` 后不重启服务，或者同一站点多副本配置不一致。

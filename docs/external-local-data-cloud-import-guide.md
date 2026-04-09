# 第三方历史数据导入云端快速入口

本文档只负责做迁移场景分流，不再重复维护完整命令和长流程。

如果你要执行完整迁移，请优先阅读：

- [docs/full-data-migration-runbook.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/full-data-migration-runbook.md)

## 1. 先判断属于哪类迁移

只回答一个问题：

你的迁移包里有没有 `data/auth/users.db`？

- 有：走“有用户体系迁移”
- 没有：走“无用户体系迁移”

## 2. 这三类脚本分别负责什么

### 2.1 业务迁移脚本

- [scripts/import_external_local_data_to_cloud.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/import_external_local_data_to_cloud.py)

负责：

- 会话主数据导入
- 报告元数据导入
- 自定义场景导入
- `owner_user_id` 修复
- `instance_scope_key` 改写与历史 scope 残留清理

### 2.2 回滚脚本

- [scripts/rollback_external_local_data_import.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/rollback_external_local_data_import.py)

负责：

- 回滚业务迁移时写入数据库和索引的结果

不负责：

- 删除已经补传到对象存储的历史文件

### 2.3 对象存储历史补齐脚本

- [scripts/sync_object_storage_history.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/sync_object_storage_history.py)

负责：

- 历史演示稿补传
- 历史运维归档补传
- 历史备份补传到对象存储

它不替代业务迁移，只用于补齐历史文件资产。

## 3. 推荐执行顺序

完整迁移固定按下面顺序执行：

1. 先确认目标云端环境与 `INSTANCE_SCOPE_KEY`
2. 执行业务迁移 `dry-run`
3. 检查用户映射、冲突和 scope 策略
4. 再执行 `apply`
5. 登录页面验证用户是否能看到迁移后的会话和报告
6. 最后执行对象存储历史补齐
7. 仅在业务迁移异常时使用回滚脚本

一句话：

`先迁业务数据，再补历史文件。`

## 4. 哪台机器运行哪个脚本

### 4.1 业务迁移脚本

目标始终是“新云端系统”，但运行机器可以是：

- 本地运维机
- 旧服务器
- 专用迁移机

前提是这台机器同时满足：

- 能看到旧迁移包
- 能连接新云端数据库

### 4.2 对象存储补齐脚本

目标仍然是“新云端系统”，但运行机器必须满足：

- 能看到那些历史文件

所以如果旧演示稿、旧归档还只在旧机器磁盘上，就应该在旧机器执行这个脚本，并加载新云端环境。

## 5. 最少需要准备什么

有用户体系：

- `data/`
- `data/auth/users.db`
- 目标云端环境配置

无用户体系：

- `data/`
- 明确的 `target_user_id`
- 目标云端环境配置

## 6. 从哪里看完整命令

完整命令、参数、输出 JSON、回滚目录和验证步骤，统一看：

- [docs/full-data-migration-runbook.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/full-data-migration-runbook.md)

推荐重点阅读章节：

- “2. 推荐执行顺序”
- “3. 先准备云端环境”
- “4. 迁移前检查清单”
- “5. 第一步：业务迁移”
- “6. 第二步：对象存储历史补全”
- “7. 第三步：如需回滚”

## 7. 常见误区

- 以为补齐对象存储就等于完成业务迁移
- 在看不到旧文件的机器上执行历史补齐脚本
- 没做 `dry-run` 就直接 `apply`
- 把迁移脚本当成在线常驻任务
- 以为回滚脚本会自动删除对象存储中的历史文件

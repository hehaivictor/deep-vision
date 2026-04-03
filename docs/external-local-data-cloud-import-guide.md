# 第三方历史数据导入云端操作手册

本文档用于指导第三方将本地 `data/` 历史数据导入到当前 DeepVision 云端环境。

如果你要执行“完整迁移”，包括：

- 业务数据导入
- 历史演示稿与运维归档补齐到对象存储
- 迁移后验证与回滚

请优先阅读：

- [docs/full-data-migration-runbook.md](./full-data-migration-runbook.md)

默认行为说明：

- 脚本会自动把导入数据的 `instance_scope_key` 改写成当前云端实例的 scope。
- 这样迁移后的会话和报告可以直接在当前实例页面显示。
- 只有在你明确需要保留源端 scope 时，才额外传 `--preserve-source-scope`。

适用脚本：

- [/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/import_external_local_data_to_cloud.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/import_external_local_data_to_cloud.py)
- [/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/rollback_external_local_data_import.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/rollback_external_local_data_import.py)

## 1. 先判断属于哪种迁移

只回答一个问题：

你的迁移包里有没有 `data/auth/users.db`？

- 有：走“有用户体系”
- 没有：走“无用户体系”

## 2. 迁移包目录结构

### 有用户体系

```text
data/
  sessions/
  reports/
  auth/
    users.db
```

### 无用户体系

```text
data/
  sessions/
  reports/
```

## 3. 所有场景都先做这一步

先进入项目目录：

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/DeepVision
```

所有操作都建议在这个目录下执行。

## 4. 有用户体系

### 步骤 1：先做 dry-run 预检查

把下面命令里的路径替换成真实路径：

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --source-auth-db /你的路径/data/auth/users.db \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

### 步骤 2：查看 dry-run 结果

打开：

```text
/tmp/import-dry-run.json
```

重点看这些字段：

- `resolved_user_mappings`
- `unresolved_users`
- `ambiguous_users`
- `conflicts.sessions`
- `conflicts.reports`

判断方式：

- 如果 `unresolved_users` 和 `ambiguous_users` 都为空，可以继续
- 如果不为空，先不要正式导入，补充映射后再执行

### 步骤 3：如需人工映射，准备 user-map.json

示例：

```json
{
  "default_target_user_id": 3,
  "source_user_map": {
    "1": 3,
    "2": 7
  },
  "session_map": {},
  "report_map": {}
}
```

说明：

- `source_user_map`：把源端用户 ID 映射到云端用户 ID
- `session_map`：单独指定某个会话归到哪个云端用户
- `report_map`：单独指定某个报告归到哪个云端用户

如果使用映射文件，再执行一次 dry-run：

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --source-auth-db /你的路径/data/auth/users.db \
  --user-map-json /你的路径/user-map.json \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

### 步骤 4：正式导入

确认 dry-run 没问题后，执行：

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --source-auth-db /你的路径/data/auth/users.db \
  --user-map-json /你的路径/user-map.json \
  --apply \
  --output-json /tmp/import-apply.json
```

如果没有映射文件，就去掉 `--user-map-json` 参数。

如果你明确要保留源端 scope，再额外追加：

```bash
--preserve-source-scope
```

### 步骤 5：记录备份目录

打开：

```text
/tmp/import-apply.json
```

找到：

- `backup.backup_dir`

后续如需回滚，必须使用这个目录。

### 步骤 6：登录页面验证

用映射后的目标用户登录，检查：

- 会话列表是否看到历史会话
- 会话详情是否能打开
- 报告列表是否看到历史报告
- 报告详情是否能打开

## 5. 无用户体系

### 步骤 1：先确定目标云端用户

你需要明确这批历史数据要归到哪个云端用户下面。

例如：

- 目标手机号：`13886047722`
- 目标 `target_user_id = 3`

### 步骤 2：先做 dry-run 预检查

把下面命令里的路径和 `3` 改成真实值：

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

### 步骤 3：查看 dry-run 结果

打开：

```text
/tmp/import-dry-run.json
```

重点看：

- `planned_import.sessions`
- `planned_import.reports`
- `conflicts.sessions`
- `conflicts.reports`

如果没有明显异常，可以继续。

### 步骤 4：如需把不同会话/报告分给不同用户，准备 user-map.json

示例：

```json
{
  "default_target_user_id": 3,
  "session_map": {
    "dv-20260305004312-de77f5e0": 7
  },
  "report_map": {
    "deep-vision-20260305-交互式访谈产品需求调研.md": 7
  }
}
```

说明：

- `default_target_user_id`：默认归属的云端用户
- `session_map`：个别会话改归其他用户
- `report_map`：个别报告改归其他用户

无用户体系场景下，不使用 `source_user_map`。

如果用了映射文件，再执行一次 dry-run：

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --user-map-json /你的路径/user-map.json \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

### 步骤 5：正式导入

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --user-map-json /你的路径/user-map.json \
  --apply \
  --output-json /tmp/import-apply.json
```

如果没有映射文件，就去掉 `--user-map-json` 参数。

如果你明确要保留源端 scope，再额外追加：

```bash
--preserve-source-scope
```

### 步骤 6：记录备份目录

打开：

```text
/tmp/import-apply.json
```

找到：

- `backup.backup_dir`

### 步骤 7：登录页面验证

用目标用户登录，检查：

- 会话列表
- 会话详情
- 报告列表
- 报告详情

## 6. 回滚操作

### 步骤 1：找到备份目录

在：

```text
/tmp/import-apply.json
```

里找到：

- `backup.backup_dir`

### 步骤 2：执行回滚

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/DeepVision

uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/rollback_external_local_data_import.py \
  --backup-dir /备份目录路径 \
  --output-json /tmp/import-rollback.json
```

### 步骤 3：验证回滚结果

重新登录页面，确认数据恢复到导入前状态。

## 7. 默认规则

脚本默认行为如下：

- 必须先 `dry-run` 再 `apply`
- 导入前自动备份
- `session_id` 冲突默认跳过
- 同名报告默认跳过
- 无法映射到云端用户的数据默认跳过
- 不覆盖现有云端数据

## 8. 最常用命令模板

### 模板 1：有用户体系

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/DeepVision

uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --source-auth-db /你的路径/data/auth/users.db \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

### 模板 2：无用户体系

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/DeepVision

uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

## 9. 建议执行顺序

推荐固定按这个顺序操作：

1. 准备迁移包
2. 进入项目目录
3. 执行 `dry-run`
4. 检查 `/tmp/import-dry-run.json`
5. 如有需要，补 `user-map.json`
6. 再执行 `apply`
7. 记录 `backup.backup_dir`
8. 登录页面验证
9. 如果有问题，执行回滚

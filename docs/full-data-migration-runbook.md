# DeepVision 完整数据迁移操作手册

本文档用于指导 DeepVision 从“外部本地历史数据”迁移到“当前云端环境”的完整流程。

适用目标：

- 把本地 `data/` 历史会话、报告、自定义场景迁移到当前云端用户体系
- 把历史演示稿、历史运维归档补齐到对象存储
- 在迁移完成后，保证云端用户既能看到自己的数据，也能访问历史文件资产

不适用目标：

- 仅做管理员账号归属迁移  
  这类操作请使用 `admin_migrate_ownership.py` 或管理员中心
- 仅做对象存储历史补传  
  这类操作可以只执行 `sync_object_storage_history.py`

## 1. 先理解三个脚本分别做什么

### 1.1 业务迁移脚本

脚本：

- [scripts/import_external_local_data_to_cloud.py](../scripts/import_external_local_data_to_cloud.py)

职责：

- 导入会话主数据
- 导入报告元数据
- 导入自定义场景
- 建立或修复 `owner_user_id`
- 默认把导入数据改写到当前实例的 `instance_scope_key`
- 可选清理目标用户历史遗留的旧 `scope` 残留

它解决的问题是：

`这些业务数据属于谁，要落到哪些库表里`

### 1.2 对象存储补全脚本

脚本：

- [scripts/sync_object_storage_history.py](../scripts/sync_object_storage_history.py)

职责：

- 补齐历史演示稿记录到对象存储
- 补齐 `data/operations/` 历史归档
- 补齐 `data/restore_backups/` 历史回滚备份
- 补齐 `data/session_backups/` 历史会话备份

它解决的问题是：

`这些已经存在于本地磁盘的历史文件，是否也要进入对象存储`

### 1.3 业务迁移回滚脚本

脚本：

- [scripts/rollback_external_local_data_import.py](../scripts/rollback_external_local_data_import.py)

职责：

- 按业务迁移时生成的备份目录回滚数据库侧导入结果

注意：

- 它回滚的是“业务迁移”
- 它不会自动删除已经补传到对象存储的历史文件

## 2. 推荐执行顺序

完整迁移建议固定按下面顺序执行：

1. 选择云端联调环境配置
2. 对业务数据先做 `dry-run`
3. 确认用户映射、冲突、scope 处理策略
4. 正式执行业务迁移
5. 登录页面验证业务数据是否可见
6. 执行对象存储历史补全
7. 验证旧演示稿、旧归档是否可访问
8. 如业务迁移结果异常，再执行回滚

一句话概括：

`先迁业务数据，再补历史文件`

原因：

- 业务迁移先解决“系统认不认识这些数据”
- 对象存储补全再解决“系统能不能跨实例拿到这些旧文件”

## 3. 先准备云端环境

推荐优先使用两套环境中的云端联调链路：

- 本机自建的 `web/.env.cloud`
推荐写法：

```bash
cd /Users/hehai/Documents/开目软件/Agents/project/DeepVision

export DEEPVISION_ENV_FILE="web/.env.cloud"
```

说明：

- `DEEPVISION_ENV_FILE` 直接指向当前云端联调文件
- 生产环境仍建议使用平台或进程环境变量注入，而不是依赖本地 env 文件

## 4. 迁移前检查清单

执行任何正式迁移前，先检查：

1. 当前云端用户、数据库、对象存储已经可正常登录与访问
2. `INSTANCE_SCOPE_KEY` 已配置为目标云端实例值
3. 迁移包中的 `data/` 目录结构完整
4. 如果源端有用户体系，确认 `data/auth/users.db` 存在
5. 如果源端无用户体系，确认目标云端 `target_user_id`
6. 目标环境已经完成必要的 schema 初始化

建议额外留存这些备份：

- 源端原始迁移包
- 迁移生成的 `dry-run` JSON
- 迁移生成的 `apply` JSON
- 迁移时自动生成的 `backup.backup_dir`

## 5. 第一步：业务迁移

详细导入参数说明可参考：

- [docs/external-local-data-cloud-import-guide.md](./external-local-data-cloud-import-guide.md)

这里仅保留完整迁移所需的关键顺序。

### 5.1 有用户体系

适用条件：

- 迁移包里存在 `data/auth/users.db`

先做 `dry-run`：

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --source-auth-db /你的路径/data/auth/users.db \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

重点检查：

- `resolved_user_mappings`
- `unresolved_users`
- `ambiguous_users`
- `conflicts.sessions`
- `conflicts.reports`

如果需要人工映射，再准备 `user-map.json` 后重新 `dry-run`。

确认无误后正式执行：

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --source-auth-db /你的路径/data/auth/users.db \
  --user-map-json /你的路径/user-map.json \
  --apply \
  --output-json /tmp/import-apply.json
```

如果没有映射文件，就去掉 `--user-map-json`。

### 5.2 无用户体系

适用条件：

- 迁移包中没有 `data/auth/users.db`

这时必须明确目标云端用户 ID，例如 `3`。

先做 `dry-run`：

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

确认无误后正式执行：

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --user-map-json /你的路径/user-map.json \
  --apply \
  --output-json /tmp/import-apply.json
```

## 6. 第二步：验证业务迁移结果

业务迁移完成后，不要立刻跑对象存储补全，先验证数据是否已经“能看见”。

重点检查：

1. 目标用户登录后能看到历史会话列表
2. 历史会话详情可以打开
3. 历史报告列表可以看到
4. 历史报告详情可以打开
5. 自定义场景能正常显示

如果这一步都还不对，不要继续补文件，应先排查：

- 用户映射是否正确
- `owner_user_id` 是否落对
- 是否保留了错误的源端 `scope`
- `dry-run` 中是否已有冲突被跳过

## 7. 第三步：执行对象存储历史补全

当业务数据已经可见后，再执行对象存储补全。

### 7.1 全量补全

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/sync_object_storage_history.py \
  --output-json /tmp/object-storage-sync.json
```

### 7.2 只补演示稿

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/sync_object_storage_history.py \
  --presentations \
  --output-json /tmp/object-storage-sync-presentations.json
```

### 7.3 只补运维归档

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/sync_object_storage_history.py \
  --ops-archives \
  --output-json /tmp/object-storage-sync-ops.json
```

### 7.4 什么时候需要 `--force`

只有在以下情况再用：

- 你确认上一次扫描中断了
- 你修改了对象存储配置，需要重新补传
- 你就是要重扫一遍历史文件

示例：

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/sync_object_storage_history.py \
  --ops-archives \
  --force
```

## 8. 第四步：验证历史文件资产

对象存储补全完成后，再验证“旧文件”而不是只看“业务数据”。

重点检查：

1. 旧演示稿是否还能下载或打开
2. 历史 ownership migration 归档能否在后台查看
3. 需要从对象存储物化恢复的回滚备份能否正常读取

一句话说：

- 第 6 步验证的是“数据是否可见”
- 第 8 步验证的是“旧文件是否可取”

## 9. 回滚说明

如果业务迁移有问题，可以按 `import-apply.json` 里的 `backup.backup_dir` 回滚：

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/rollback_external_local_data_import.py \
  --backup-dir /备份目录路径 \
  --output-json /tmp/import-rollback.json
```

注意：

- 这个回滚只针对业务迁移的数据库侧结果
- 它不会自动删除已经补传到对象存储的历史文件
- 所以最稳妥的顺序是：先确认业务迁移没问题，再跑对象存储补全

## 10. 常见误区

### 10.1 只跑补全脚本，不跑业务迁移脚本

结果通常是：

- 对象存储里可能有了文件
- 但用户仍然看不到自己的会话和报告

因为系统先要“认识这些数据”，文件补传不能代替业务迁移。

### 10.2 只跑业务迁移脚本，不跑补全脚本

结果通常是：

- 用户能看到自己的会话和报告
- 但旧演示稿、旧运维归档可能还不能跨实例稳定访问

### 10.3 把对象存储补全当成 Web 启动的一部分

现在不建议这样做。  
历史对象存储补全已经从 Web 启动链路移出，目的是避免云端重启被历史文件扫描拖慢。

## 11. 最简执行模板

如果你只想记住一套完整顺序，照着下面执行即可。

### 11.1 业务迁移 dry-run

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --dry-run \
  --output-json /tmp/import-dry-run.json
```

### 11.2 业务迁移 apply

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/import_external_local_data_to_cloud.py \
  --source-data-dir /你的路径/data \
  --target-user-id 3 \
  --apply \
  --output-json /tmp/import-apply.json
```

### 11.3 补全历史对象存储

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 \
python3 scripts/sync_object_storage_history.py \
  --output-json /tmp/object-storage-sync.json
```

### 11.4 业务回滚

```bash
DEEPVISION_ENV_FILE="web/.env.cloud" \
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' \
python3 scripts/rollback_external_local_data_import.py \
  --backup-dir /备份目录路径 \
  --output-json /tmp/import-rollback.json
```

## 12. 最后结论

完整迁移时，推荐固定遵循：

1. 先做业务迁移
2. 再做对象存储补全
3. 业务回滚只回滚数据库迁移，不回滚对象存储补传

一句话总结：

`迁移脚本负责“把数据迁进系统”，补全脚本负责“把历史文件补进对象存储”。`

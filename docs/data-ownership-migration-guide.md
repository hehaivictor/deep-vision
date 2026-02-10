# DeepVision 数据归属迁移操作手册

## 0. 超简版（10 行命令清单）

```bash
# 1) 列用户（确认目标账号）
python3 scripts/admin_migrate_ownership.py list-users

# 2) 预览（推荐：仅迁移无归属）
python3 scripts/admin_migrate_ownership.py migrate --to-account 13800138000 --scope unowned

# 3) 预览（从旧账号迁到新账号）
python3 scripts/admin_migrate_ownership.py migrate --to-user-id 3 --scope from-user --from-user-id 10 --kinds sessions,reports

# 4) 落盘执行（确认后再加 --apply）
python3 scripts/admin_migrate_ownership.py migrate --to-user-id 3 --scope from-user --from-user-id 10 --kinds sessions,reports --apply

# 5) 审计结果
python3 scripts/admin_migrate_ownership.py audit --user-id 3

# 6) 如需回滚
python3 scripts/admin_migrate_ownership.py rollback --backup-dir data/operations/ownership-migrations/<迁移目录>
```

## 1. 适用场景

当启用用户隔离后，历史会话/报告如果仍归属在旧账号或未知归属下，可能导致新登录账号“看不到历史数据”。

本手册用于指导管理员通过脚本，**手动、可审计、可回滚**地完成历史数据归属迁移。

相关脚本：`scripts/admin_migrate_ownership.py`

---

## 2. 迁移原则

1. 先预览后执行：默认 `dry-run`，仅在确认后加 `--apply` 落盘。
2. 优先最小范围：优先使用 `--scope unowned` 或 `--scope from-user`，避免误迁移。
3. 可回滚：每次 `--apply` 自动生成备份目录。
4. 可审计：迁移前后执行 `audit` 对比结果。

---

## 3. 迁移范围说明

脚本支持三种范围：

- `--scope unowned`
  - 仅迁移无归属数据（`owner_user_id` 为空、无效或 `<=0`）
  - 推荐默认方案

- `--scope from-user --from-user-id <N>`
  - 仅迁移“来源用户 N”的数据到目标用户
  - 适合“账号更换、账号合并”场景

- `--scope all`
  - 将全部会话/报告归属重写为目标用户
  - 风险最高，仅在明确需要时使用

可通过 `--kinds` 控制对象：

- `--kinds sessions` 仅迁移会话
- `--kinds reports` 仅迁移报告
- `--kinds sessions,reports` 同时迁移（默认）

---

## 4. 标准迁移流程（SOP）

### 步骤 1：列出用户并确认目标账号

```bash
python3 scripts/admin_migrate_ownership.py list-users
```

记录目标用户 `user_id` 或账号（手机号/邮箱）。

### 步骤 2：先做预览（不落盘）

#### 方案 A：迁移无归属数据（推荐）

```bash
python3 scripts/admin_migrate_ownership.py migrate \
  --to-account 13800138000 \
  --scope unowned
```

#### 方案 B：从旧用户迁到新用户

```bash
python3 scripts/admin_migrate_ownership.py migrate \
  --to-user-id 3 \
  --scope from-user \
  --from-user-id 10 \
  --kinds sessions,reports
```

观察输出中的 `matched` 与 `updated` 预估值。

### 步骤 3：执行落盘迁移

```bash
python3 scripts/admin_migrate_ownership.py migrate \
  --to-user-id 3 \
  --scope from-user \
  --from-user-id 10 \
  --kinds sessions,reports \
  --apply
```

执行后会输出自动生成的备份目录，例如：

`data/operations/ownership-migrations/20260210-163953-to-3`

### 步骤 4：执行后审计

```bash
python3 scripts/admin_migrate_ownership.py audit --user-id 3
```

确认 `sessions`、`reports` 已达到预期数量。

### 步骤 5：业务侧验证

使用目标账号登录 Web 页面，验证：

1. 会话列表是否可见
2. 报告列表是否可见
3. 典型历史数据是否可正常打开

---

## 5. 回滚方法

当迁移结果不符合预期时，使用备份目录回滚：

```bash
python3 scripts/admin_migrate_ownership.py rollback \
  --backup-dir data/operations/ownership-migrations/<迁移目录>
```

回滚完成后，重新执行 `audit` 校验。

---

## 6. 常见问题排查

### Q1：执行了 `--apply`，为什么账号下还是看不到历史数据？

最常见原因：本次迁移命中数为 0。

请检查：

1. 迁移输出里的 `matched` / `updated` 是否为 0
2. 是否误用了 `--scope unowned`（而数据实际已归属到其他用户）
3. 目标用户是否选错（手机号/邮箱对应账号不一致）

建议先用：

```bash
python3 scripts/admin_migrate_ownership.py migrate ...   # 不加 --apply，先 dry-run
```

确认命中后再执行落盘。

### Q2：如何只迁移报告、不动会话？

```bash
python3 scripts/admin_migrate_ownership.py migrate \
  --to-user-id 3 \
  --scope from-user \
  --from-user-id 10 \
  --kinds reports \
  --apply
```

### Q3：如何保留完整审计记录？

迁移时可追加摘要输出：

```bash
python3 scripts/admin_migrate_ownership.py migrate \
  --to-user-id 3 \
  --scope from-user \
  --from-user-id 10 \
  --apply \
  --summary-json data/operations/ownership-migrations/latest-summary.json
```

---

## 7. 运维建议

1. 迁移前短时维护窗口，避免并发写入。
2. 单次迁移一个目标账号，便于追踪与回滚。
3. 每次迁移后立即执行 `audit` + 人工登录抽检。
4. 保留备份目录至少 7 天再清理。


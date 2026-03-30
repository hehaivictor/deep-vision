# DeepVision 多实例云部署计划

## Summary

采用长期方案：把业务状态从实例本地磁盘迁出，应用实例只保留计算与请求处理能力。

默认技术选型固定为：

- 结构化数据：PostgreSQL
- 文件与产物：S3 兼容对象存储
- 可选缓存/队列：Redis
- 应用实例：无状态副本，可水平扩容

## Key Changes

- 将 `data/auth/users.db` 与 `data/meta_index.db` 从 SQLite 迁移到 PostgreSQL。
- 将 `data/sessions/*.json` 的会话主数据迁移到 PostgreSQL；如需保留原始 JSON，可作为对象存储归档，不再作为在线主存储。
- 将报告正文、报告附属 JSON、演示元数据映射迁移到 PostgreSQL；演示文件与上传原件接入 S3 兼容对象存储。
- `data/summaries/` 改为 Redis 或 PostgreSQL 缓存表；允许失效重建，不再依赖实例本地磁盘。
- `data/temp/`、`data/metrics/` 保留为实例本地临时目录，但不得承载用户核心数据。
- 同一业务站点的所有副本统一使用同一个 `SECRET_KEY`、`AUTH_DB_PATH`、`INSTANCE_SCOPE_KEY`。
- 不同业务链接如果共享同一套数据库或对象存储，继续使用不同 `INSTANCE_SCOPE_KEY` 做业务隔离；同一链接的所有副本必须一致。

## Recommended Rollout

1. 第一步先迁移鉴权库和索引库到 PostgreSQL，保证登录、用户归属、索引查询不依赖本地 SQLite。
2. 第二步迁移会话、报告正文、报告附属 JSON、演示元数据映射到 PostgreSQL，完成文本型主数据云端化。
3. 第三步把演示文件本体、上传附件、导出文件切到对象存储，数据库只存引用。
4. 第四步将缓存类目录从实例本地迁走或降级为可失效缓存，只保留临时目录。
5. 第五步在负载均衡后扩容副本，不依赖会话亲和。

## Data Migration Matrix

按多实例部署要求，建议不要再按“目录名”思考迁移，而是按“数据类型”划分目标存储。

| 数据/功能 | 当前主要载体 | 推荐目标 | 当前状态 | 优先级 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 用户鉴权、微信身份 | `users.db` / `AUTH_DB_PATH` | PostgreSQL | 已迁移 | P0 | 结构化主数据，适合长期保留在数据库 |
| License、激活事件 | `licenses.db` / `LICENSE_DB_PATH` | PostgreSQL | 已迁移 | P0 | 结构化主数据，适合长期保留在数据库 |
| 会话主数据 | `data/sessions/*.json` | PostgreSQL `session_store` | 已迁移 | P0 | PostgreSQL 模式下已不再依赖本地 JSON 作为在线主存储 |
| 会话索引 | `session_index` | PostgreSQL | 已迁移 | P0 | 多实例列表查询、分页、隔离的基础能力 |
| 报告归属/作用域/分享/软删除元数据 | `.owners.json` / `.scopes.json` / `.solution_shares.json` / 删除记录 | PostgreSQL `report_meta_*` | 已迁移 | P0 | 元数据已经数据库化，后台运维链路已适配 |
| 报告索引 | `report_index` | PostgreSQL | 已迁移 | P0 | 用于报告列表、归属过滤、实例隔离 |
| 自定义场景 | `data/scenarios/custom/*.json` | PostgreSQL `custom_scenarios` | 已迁移 | P0 | 个人场景已数据库化，并带 owner 与 scope 隔离 |
| 报告正文 Markdown | `data/reports/*.md` | PostgreSQL `report_store` | 已迁移 | P0 | 报告读取、生成、列表索引都已走数据库主存储 |
| 报告 sidecar / solution payload | `*.solution.json` / `*.solution.payload.json` | PostgreSQL | 已迁移 | P0 | 结构化小文本数据已进入数据库表 |
| 演示元数据映射 | `.presentation_map.json` | PostgreSQL | 已迁移 | P1 | 演示任务映射已走数据库主存储 |
| 演示文件本体 | `Downloads` / `data/presentations/` 引用 | S3 兼容对象存储 + PostgreSQL 元数据 | 已迁移 | P1 | 新下载演示直接入对象存储，历史本地记录启动时自动补传 |
| 上传原件 | `data/temp/` 中转 | S3 兼容对象存储 + PostgreSQL 元数据 | 已迁移（新上传） | P1 | 新上传原件会归档到对象存储；历史临时文件因缺少稳定引用不做自动回填 |
| 导出文件 / 二进制产物 | 本地目录 | S3 兼容对象存储 + PostgreSQL 元数据 | 未迁移 | P1 | 包括 PPT/PDF/图片等大文件 |
| 转换产物 | `data/converted/*.md` | Redis 或 PostgreSQL 缓存表 | 已迁移到 PostgreSQL 缓存表 | P2 | 上传转换优先查 PostgreSQL 缓存，未命中才调用本地转换 |
| 摘要缓存 | `data/summaries/*.txt` | Redis 优先，其次 PostgreSQL 缓存表 | 已迁移到 PostgreSQL 缓存表 | P2 | 当前已数据库化；后续如需更低延迟可再切 Redis |
| 运行配置（前端展示配置） | `web/site-config.js` | 静态发布或 PostgreSQL 配置表 | 未迁移 | P2 | 不建议继续用实例本地可变文件 |
| 本地临时文件 | `data/temp/` | 本地临时目录 | 保留本地 | P3 | 仅用于短时中转，不得承载业务真相 |
| 本地锁文件 | `data/.locks/` | 本地锁或 Redis 锁 | 保留本地 | P3 | 仅实例内有效，不能作为多实例全局一致性机制 |
| 指标文件 | `data/metrics/api_metrics.json` | 日志平台 / Prometheus / 外部监控 | 未迁移 | P3 | 不建议用本地文件做多实例聚合 |
| 运维备份与回滚产物 | `data/operations/` / `restore_backups/` | 对象存储归档 | 部分本地 | P3 | 适合做冷备份或归档，不应继续依赖实例本地 |

## Recommended Targets

### PostgreSQL

适合承载：

- 用户、License、微信身份
- 会话主数据与会话索引
- 报告正文、报告 sidecar、报告 payload 缓存、报告索引、报告归属元数据
- 自定义场景
- 演示元数据映射
- 轻量级缓存表（在没有 Redis 时）

原则：

- 体量小
- 结构化
- 需要按 `owner_user_id`、`INSTANCE_SCOPE_KEY`、时间排序做查询
- 需要参与归属迁移、审计、回滚

### S3 Compatible Object Storage

适合承载：

- 上传原件
- 演示文件本体
- 导出文件
- 图片、PDF、PPT 等大文件
- 运维归档备份

原则：

- 文件型
- 体积可能较大
- 面向下载、预览、归档
- 不适合塞进 PostgreSQL 文本字段

### Redis

优先用于：

- 摘要缓存
- 转换缓存
- 可选的分布式锁、短期任务状态

原则：

- 可失效
- 可重建
- 对低延迟读取更敏感

### Local Temporary Storage

仅保留：

- 上传处理中转
- 文档转换 scratch 文件
- 实例内短期锁文件

禁止承载：

- 会话真相数据
- 报告正文主副本
- 用户上传原件唯一副本
- 任何跨实例必须共享的业务数据

## Priority Roadmap

建议按下面顺序推进：

1. 导出文件迁入对象存储，数据库仅保存对象键与元数据。
2. 如有更高并发或更低延迟需求，再把转换缓存从 PostgreSQL 缓存表切到 Redis。
3. `site-config.js` 从实例本地可变文件改为静态发布或数据库配置。
4. 清理 `data/` 中仍被当作主数据源的目录，保留 `temp/` 与必要 scratch 目录。
5. 为对象存储补充批量回填、生命周期清理、监控告警与回滚策略。

## Object Storage Config

当前代码已支持通过环境变量接入 S3 兼容对象存储：

- `OBJECT_STORAGE_ENDPOINT`
- `OBJECT_STORAGE_REGION`
- `OBJECT_STORAGE_BUCKET`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `OBJECT_STORAGE_FORCE_PATH_STYLE`
- `OBJECT_STORAGE_SIGNATURE_VERSION`
- `OBJECT_STORAGE_PREFIX`

当前已接入的对象存储链路：

- 演示文件下载后直接上传对象存储，并由受保护接口回放下载。
- 历史演示文件记录如果仍指向本地路径，服务启动时会自动补传到对象存储。
- 新上传的原始参考文档会归档到对象存储，并把对象键写入会话主数据。
- 文档转换结果已进入 PostgreSQL `converted_cache_store`，命中缓存时不再依赖本地 `data/converted/`。

当前仍未接入对象存储的文件型数据：

- 导出附件与其他二进制产物
- 运维备份归档

## Decision Rules

用于后续评估任何新功能的数据去向：

- 小而结构化、需要查询过滤、需要归属迁移：放 PostgreSQL。
- 大而文件化、面向下载/预览/归档：放对象存储。
- 可失效、可重建、主要为性能优化：放 Redis 或缓存表。
- 仅当前实例短时使用：放本地临时目录。

## Test Plan

- 同一用户连续请求命中不同实例，能读取同一份会话和报告。
- 实例扩容、重启、滚动发布后，用户数据不丢失、不串实例。
- 两个不同 `INSTANCE_SCOPE_KEY` 的站点共享后端存储时，互相不可见。
- 并发创建会话、生成报告、上传文件时，不出现重复写、覆盖写、索引缺失。
- 所有副本共享同一 `SECRET_KEY` 后，登录态在切实例时保持有效。

## Assumptions

- 目标是生产级多实例部署，不接受“偶发查不到数据”的行为。
- 可以接受一次数据迁移。
- 优先保证一致性和可扩展性，而不是最小改动上线。

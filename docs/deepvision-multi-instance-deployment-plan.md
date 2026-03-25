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
- 将 `data/reports/`、`data/presentations/`、上传文档等文件迁移到对象存储；数据库仅保存元数据、归属、作用域、对象键、更新时间。
- `data/summaries/` 改为 Redis 或 PostgreSQL 缓存表；允许失效重建，不再依赖本地磁盘。
- `data/temp/`、`data/metrics/` 保留为实例本地临时目录，但不得承载用户核心数据。
- 同一业务站点的所有副本统一使用同一个 `SECRET_KEY`、`AUTH_DB_PATH`、`INSTANCE_SCOPE_KEY`。
- 不同业务链接如果共享同一套数据库或对象存储，继续使用不同 `INSTANCE_SCOPE_KEY` 做业务隔离；同一链接的所有副本必须一致。

## Recommended Rollout

1. 第一步先迁移鉴权库和索引库到 PostgreSQL，保证登录、用户归属、索引查询不依赖本地 SQLite。
2. 第二步迁移会话和报告元数据，新增数据库读写路径，保留文件读作为短期兼容。
3. 第三步把报告、演示、上传附件切到对象存储，数据库只存引用。
4. 第四步下线本地 `data/` 作为主数据源，只保留临时缓存目录。
5. 第五步在负载均衡后扩容副本，不依赖会话亲和。

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

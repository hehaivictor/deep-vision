# DeepVision AI 可执行全量升级清单

> 目标：让 AI 基于本清单直接开始升级实施。  
> 适用范围：DeepVision 从 MVP 升级到可支撑多用户与高并发的生产形态。

## 执行约束（给 AI 的硬规则）

1. 每个任务必须提交：代码改动、测试结果、回滚说明。  
2. 所有新能力都必须有开关，默认兼容旧逻辑。  
3. 关键写接口必须保证幂等。  
4. 每完成 1 个任务卡提交 1 次中文 commit（按改动分类分行描述）。  
5. 未通过验收命令，不得进入下一个依赖任务。  

## 建议改造锚点文件

1. `/Users/hehai/.claude/skills/deep-vision/web/server.py`
2. `/Users/hehai/.claude/skills/deep-vision/web/config.example.py`
3. `/Users/hehai/.claude/skills/deep-vision/tests/test_api_comprehensive.py`
4. `/Users/hehai/.claude/skills/deep-vision/tests/test_security_regression.py`
5. `/Users/hehai/.claude/skills/deep-vision/scripts/`
6. `/Users/hehai/.claude/skills/deep-vision/docs/`
7. `/Users/hehai/.claude/skills/deep-vision/web/README.md`
8. `/Users/hehai/.claude/skills/deep-vision/README.md`

## P0（上线前必须完成）

| ID | 依赖 | AI 执行内容 | 产物 / DoD |
|---|---|---|---|
| P0-01 | 无 | 建立配置中心与开关：`DB_ENABLED`、`DUAL_WRITE_ENABLED`、`QUEUE_ENABLED`、`REDIS_ENABLED`、`RATE_LIMIT_ENABLED` | 开关默认关闭时行为与当前一致 |
| P0-02 | P0-01 | 拆分单体入口：路由层 / 服务层 / 存储层 | `server.py` 职责收敛，核心逻辑可单测 |
| P0-03 | P0-01 | 引入 PostgreSQL 连接管理与事务封装 | 可通过环境变量切换 DB |
| P0-04 | P0-03 | 建立核心表：`users/sessions/interview_logs/documents/reports/report_jobs/idempotency_keys/audit_logs` | schema 可自动初始化 |
| P0-05 | P0-04 | 实现 Repository 层，替换直接文件读写入口 | 关键 API 可走 DB 读写 |
| P0-06 | P0-05 | 实现双写（JSON + PG）与读优先策略开关 | 双写打开后请求可成功 |
| P0-07 | P0-06 | 实现 JSON -> PG 迁移脚本（增量可重复执行） | 脚本可幂等重跑 |
| P0-08 | P0-07 | 实现数据一致性校验脚本（数量、关键字段、哈希） | 输出对账报告与差异明细 |
| P0-09 | P0-01 | 引入任务队列基础（Redis broker + worker） | worker 可启动并消费任务 |
| P0-10 | P0-09 | 报告生成改异步：提交 / 状态查询 / 取消 | 生成接口不再长阻塞 |
| P0-11 | P0-10 | 任务重试、退避、死信处理 | 失败任务可观测可重放 |
| P0-12 | P0-01 | 引入 Redis 缓存：会话热数据、摘要缓存 | 命中率指标可见 |
| P0-13 | P0-12 | 引入限流（用户 / IP 双维，分接口配额） | 超限返回标准错误码 |
| P0-14 | P0-05 | 关键写接口幂等（创建会话 / 提交答案 / 生成报告） | 重复请求不重复落库 |
| P0-15 | P0-05 | 会话写入乐观锁（`version` 字段） | 并发写冲突可检测并提示 |
| P0-16 | P0-01 | 抽象文件存储（本地 / 对象存储） | 切换存储后接口不变 |
| P0-17 | P0-10 | AI 调用韧性：超时 / 重试 / 熔断 / 降级 | 外部 AI 故障时系统可降级 |
| P0-18 | P0-01 | 安全加固：上传白名单 + MIME 检测 + 大小限制 + 文件名净化 | 安全回归用例通过 |
| P0-19 | P0-02 | 统一可观测：`request_id`、结构化日志、耗时、错误码、队列堆积 | 关键指标可查询 |
| P0-20 | P0-19 | 健康检查：`/healthz`、`/readyz` | 依赖异常时 `readyz` 正确失败 |
| P0-21 | P0-19 | 部署配置：Gunicorn / Nginx / 进程参数 | 多 worker 稳定运行 |
| P0-22 | P0-21 | 压测脚本：500 并发核心链路 | 产出压测报告（P95 / 错误率） |
| P0-23 | P0-22 | 灰度发布脚本：10% -> 30% -> 100% | 每步可暂停、可回滚 |
| P0-24 | P0-23 | 生产 Runbook：告警处置、回滚、任务清理 | 值班可按文档执行 |

## P1（上线后 1-2 个月）

| ID | 依赖 | AI 执行内容 | 产物 / DoD |
|---|---|---|---|
| P1-01 | P0 完成 | 多租户数据模型（`tenant_id` 全链路） | 查询与写入都带租户隔离 |
| P1-02 | P1-01 | RBAC（组织 / 项目 / 角色） | 关键接口权限校验可测 |
| P1-03 | P0-19 | 成本治理：token 预算、用户配额、超限降级 | 预算超限自动降级 |
| P1-04 | P1-03 | 用量计费事件模型（请求 / 任务 / 报告） | 可导出账单明细 |
| P1-05 | P0-16 | 对象存储生命周期策略（归档 / 清理） | 冷数据自动归档 |
| P1-06 | P0-24 | 自动化备份与恢复演练脚本 | 恢复演练有记录 |
| P1-07 | P0-19 | 运维看板（错误率 / 延迟 / 队列 / 成本） | 看板可支持日常值班 |
| P1-08 | P0-18 | 安全扫描流程（依赖漏洞、静态扫描） | CI 可阻断高危漏洞 |

## P2（中长期）

| ID | 依赖 | AI 执行内容 | 产物 / DoD |
|---|---|---|---|
| P2-01 | P1-06 | 跨可用区容灾（RTO / RPO 目标） | 容灾切换演练通过 |
| P2-02 | P1-07 | 混沌演练（DB 慢 / Redis 挂 / AI 超时） | 演练报告与改进项闭环 |
| P2-03 | P1-04 | 数据仓库与经营分析（留存 / 转化 / 成本） | 管理报表自动化 |
| P2-04 | P1-08 | 合规体系（审计留痕、脱敏、保留策略） | 合规检查清单可复用 |

## AI 统一验收门禁

1. 单测与回归  
`python3 -m unittest discover -s /Users/hehai/.claude/skills/deep-vision/tests -p "test_*.py" -v`

2. 一致性对账  
`python3 /Users/hehai/.claude/skills/deep-vision/scripts/data_consistency_check.py`

3. 压测  
`python3 /Users/hehai/.claude/skills/deep-vision/tests/load/load_smoke.py --users 500 --seconds 180`

4. 性能门槛  
- 非 AI 接口：`P95 < 300ms`  
- 错误率：`< 1%`  
- 任务成功率：`>= 99%`  

## 可直接给 AI 的执行指令

```text
按清单从 P0-01 开始执行，严格遵守依赖顺序。每完成一个任务卡必须提交：1) 改动文件清单 2) 验收命令结果 3) 回滚方式 4) 中文 commit。若验收失败，先修复再进入下一任务。现在开始执行 P0-01。
```


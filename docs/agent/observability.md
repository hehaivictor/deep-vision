# 运行态观察

## 适用范围

当任务涉及以下内容时，先跑观察入口，而不是直接改代码：

- 最近接口是否异常、超时或明显变慢
- 当前数据库、摘要缓存、指标存储是否健康
- 最近是否有 ownership migration / cloud import / harness 失败
- 想知道当前仓库“最近发生了什么”，但还不确定该改哪里

## 固定入口

- 只读观察：`python3 scripts/agent_observe.py --profile auto`
- 查看最近 10 条：`python3 scripts/agent_observe.py --profile auto --recent 10`
- 查看最近历史索引：`python3 scripts/agent_history.py --kind all --limit 5`
- 对比最近两次 harness：`python3 scripts/agent_history.py --kind harness --diff`
- 输出 JSON：`python3 scripts/agent_observe.py --profile auto --json`
- 在 harness 中附带观察阶段：`python3 scripts/agent_harness.py --observe --profile auto`

## 当前观察面

`agent_observe` 当前会汇总以下信息：

- 环境文件来源与关键开关摘要
- 最近一次启动初始化快照（优先读取 `runtime_metrics_store.runtime_startup`，回退到 `data/operations/runtime-startup/latest.json`）
- `auth_db` / `license_db` / `meta_index_db` 的存在性与基础计数
- `runtime_metrics_store` 或 `data/metrics/api_metrics.json` 的指标摘要
- 摘要缓存命中面
- 配置中心三类来源的文件存在性与修改时间
- 本地 ownership migration 历史
- cloud import 备份历史
- `data/operations/` 最近运行产物
- `artifacts/harness-runs/` 最近运行与最近失败
- `history_trends`：最近 harness / evaluator / CI 运行概览、最近两次 harness / evaluator 漂移摘要，以及连续失败链路 / 重复 blocker / 慢场景回归阈值信号
- `diagnostic_panel`：最近最常失败 task、Top blocker、慢场景、阈值化告警摘要和推荐复跑命令
- `agent_history.py` 继续用于下钻 `harness-runs`、`harness-eval` 与 `artifacts/ci/*` 的完整索引和 diff

## 当前边界

- `startup initialization` 只会读取最近一次持久化快照；observe 仍然不会主动触发初始化。
- 配置中心目前也没有独立写入审计；observe 只能基于源文件修改时间做近似观察。
- 该脚本默认只读，不会执行 preview、apply、rollback，也不会修复问题。

## 推荐用法

1. 先跑 `python3 scripts/agent_observe.py --profile auto`
2. 如果 `history_trends` 或 `diagnostic_panel` 显示最近有 `problem` 或 `warning`，优先看 `streak`、`blocker_repeat`、`regression` 三类信号，再按推荐复跑命令定位对应 task / scenario 并打开相关 `latest.json`
3. 如果任务属于高风险运维链路，再跑对应的 `agent_harness --task ...`
4. 只有在观察结果足够清晰后，再进入代码修改或管理员操作

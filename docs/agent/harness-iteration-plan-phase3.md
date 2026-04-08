# DeepVision Harness 三阶段迭代计划

这份计划承接二阶段结果，聚焦“真实度、治理性、运营性”三条主线，不重复记录已经落地的统一入口、task workflow、artifact/handoff、browser smoke、evaluator、多执行器场景与 CI 收口能力。

## 目标

- 把现有 harness 从“可运行的检查系统”继续推进为“更接近真实业务与真实风险的评估系统”
- 强化多租户/实例隔离、资产归属和高风险管理动作的治理深度
- 把 observe 从诊断摘要继续推进成带阈值和建议动作的运营面板
- 进一步降低失败回灌成本，让事故更快沉淀成 evaluator 场景
- 在维持信号质量的前提下，继续优化 CI 运行成本和触发策略

## 当前基线

- 统一入口：`scripts/agent_harness.py`
- 受控任务执行：`scripts/agent_workflow.py`
- 只读观察与历史对比：`scripts/agent_observe.py`、`scripts/agent_history.py`
- 场景 evaluator：`scripts/agent_eval.py`
- 浏览器 UI smoke：`scripts/agent_browser_smoke.py`
- task-backed playbook：`scripts/agent_playbook_sync.py`
- PR / browser / nightly workflow 与 GitHub Step Summary 已接通
- 任务画像：8 个
- evaluator 场景：16 个

## 状态约定

- `planned`：已排期，尚未开始
- `active`：正在执行
- `done`：已完成并验证
- `blocked`：有明确阻塞，需要先处理依赖

## 三阶段清单

| 编号 | 状态 | 主题 | 目标 | 主要交付物 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| H3-1 | done | 真链路浏览器扩容 | 在现有 `live-minimal` 之外补更接近真实业务的浏览器真链路 | `scripts/agent_browser_smoke.py`、`scripts/agent_browser_smoke_runner.mjs`、`tests/harness_scenarios/browser/*.json` | 至少补 2 条 seeded/live 浏览器场景，覆盖 `report-solution` 或公开分享等真实前后端联动链路 |
| H3-2 | done | 租户隔离语料库 | 把 `INSTANCE_SCOPE_KEY`、资产归属、跨账号共享、对象存储元数据等风险收成独立场景组 | `tests/harness_scenarios/tenant/**/*.json` 或扩展现有 `security/ops` 目录 | 新增一组多租户/实例隔离场景，并能稳定进入 nightly 或 manual evaluator |
| H3-3 | done | Observe 告警化 | 让 observe 不只给摘要，还给阈值、连续失败统计和推荐动作 | `scripts/agent_observe.py`、`scripts/agent_history.py`、`docs/agent/observability.md` | 至少输出连续失败、慢场景回归和高频 blocker 三类告警信号 |
| H3-4 | done | Workflow 治理字段 | 为高风险 task 增加变更原因、操作者、审批人、关联工单等治理字段 | `scripts/agent_workflow.py`、`resources/harness/tasks/*.json`、artifact/handoff 模板 | 高风险 workflow 的 apply/rollback 工件能带出治理元数据并进入 handoff |
| H3-5 | done | 失败回灌自动化 | 让失败 run 更快变成正式场景，减少人工复制与分类成本 | `scripts/agent_scenario_scaffold.py`、`scripts/agent_artifacts.py`、文档入口 | failure-summary / handoff 可直接给出更完整的场景脚手架建议和默认分类 |
| H3-6 | active | CI 成本优化 | 在不削弱信号的前提下继续做路径过滤、缓存和 lane 分层 | `.github/workflows/*.yml`、CI 文档 | PR / nightly 总耗时或重复安装成本下降，且 required checks 语义不变差 |

## 推荐执行顺序

1. H3-1 真链路浏览器扩容
2. H3-2 租户隔离语料库
3. H3-3 Observe 告警化
4. H3-4 Workflow 治理字段
5. H3-5 失败回灌自动化
6. H3-6 CI 成本优化

## 每项执行要求

每完成一个编号，必须同步更新 [harness-progress-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase3.md)，至少记录：

- 完成日期
- 对应编号
- 实际改动范围
- 已执行的验证命令
- 关键 artifact / 文档入口
- 剩余风险和下一步

如果某项只完成一部分，也要先登记 `active` 或 `blocked`，不要等全部做完再补记。

## 第一批建议直接启动的事项

- H3-1：优先补 `report-solution` 与公开分享真链路
- H3-2：优先把实例隔离、共享资产归属和对象存储元数据边界收成 evaluator 场景

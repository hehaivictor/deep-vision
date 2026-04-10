# DeepVision Harness 五阶段迭代计划

这份计划承接四阶段结果，聚焦“架构地图、任务使命、全局短记忆、修复指令、依赖硬规则、低风险园丁”六条主线，不重复记录已经落地的统一入口、task workflow、planner / contract / calibration、browser smoke、multi-executor evaluator 与 CI 收口能力。

## 目标

- 为 DeepVision 增加仓库级 `ARCHITECTURE.md`，把“代码在哪里、边界在哪里、不允许什么依赖”显式化
- 为 Planner 增加上层 `mission` 契约，让一句话需求先扩成可测试、可审计的目标定义
- 补一层全局短记忆 `heartbeat / memory`，承接当前阶段、主入口、活跃计划和最近稳定能力
- 让静态 guardrail 不只报错，还能输出明确的 `Action for Agent`
- 继续把分层依赖关系固化成机械规则，而不是只靠人工记忆
- 用低风险 `doc gardening / orchestrator` 收口计划、契约、playbook 和文档漂移

## 当前基线

- 统一入口：`scripts/agent_harness.py`
- 受控任务执行：`scripts/agent_workflow.py`
- 只读观察与历史对比：`scripts/agent_observe.py`、`scripts/agent_history.py`
- Planner / Contract / Calibration：`scripts/agent_planner.py`、`scripts/agent_contracts.py`、`scripts/agent_calibration.py`
- 场景 evaluator：`scripts/agent_eval.py`
- 静态架构规则：`scripts/agent_static_guardrails.py`
- 四阶段计划与台账：已完成，见 [harness-iteration-plan-phase4.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase4.md) 与 [harness-progress-phase4.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase4.md)

## 状态约定

- `planned`：已排期，尚未开始
- `active`：正在执行
- `done`：已完成并验证
- `blocked`：有明确阻塞，需要先处理依赖

## 五阶段清单

| 编号 | 状态 | 主题 | 目标 | 主要交付物 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| H5-1 | done | Architecture Map | 建立仓库级物理地图，显式说明代码分层、领域边界与“不允许什么依赖” | `ARCHITECTURE.md`、入口导航调整、必要的领域链接 | 新 agent 可仅靠 `AGENTS.md + ARCHITECTURE.md` 快速定位主要实现与边界 |
| H5-2 | done | Mission Contract | 为 Planner 增加比 task plan 更高一层的任务契约，把一句话需求扩成目标、非目标、验收标准与风险 | `mission.md` 模板或 `artifacts/planner/missions/*.json`、`scripts/agent_planner.py` 扩展 | 至少 1 条高频任务支持先生成 mission，再进入 planner / workflow |
| H5-3 | done | Global Heartbeat Memory | 增加极薄的全局短记忆层，只存稳定指针和当前阶段状态，不存长逻辑 | `docs/agent/heartbeat.md` 或 `artifacts/memory/latest.json`、更新脚本或规范 | 入口文档不再承担阶段状态广播；heartbeat 能准确指向当前活跃计划和稳定入口 |
| H5-4 | done | Action-for-Agent Guardrails | 让静态 guardrail 输出更像下一轮 agent 的修复提示，而不只是失败列表 | `scripts/agent_static_guardrails.py`、规则输出模板、`agent_harness` 高亮、相关文档 | 任一静态规则失败时，日志中都能看到建议修复层级、推荐动作和复跑命令 |
| H5-5 | done | Dependency Rule Hardening | 把关键分层依赖关系继续固化成机械规则，减少架构回退 | `scripts/agent_static_guardrails.py`、导入方向规则、测试、文档 | 至少新增 1 条导入/调用方向规则，并进入 PR 基础检查 |
| H5-6 | done | Doc Gardening / Orchestrator | 增加低风险后台清理与一致性检查，优先生成报告，不自动改业务代码 | `scripts/agent_doc_gardener.py`、报告输出、文档 | 能自动检查 plan / contract / playbook / docs 是否漂移，并输出可执行建议 |

## 推荐执行顺序

1. H5-1 Architecture Map
2. H5-2 Mission Contract
3. H5-3 Global Heartbeat Memory
4. H5-4 Action-for-Agent Guardrails
5. H5-5 Dependency Rule Hardening
6. H5-6 Doc Gardening / Orchestrator

## 每项执行要求

每完成一个编号，必须同步更新 [harness-progress-phase5.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase5.md)，至少记录：

- 完成日期
- 对应编号
- 实际改动范围
- 已执行的验证命令
- 关键 artifact / 文档入口
- 剩余风险和下一步

如果某项只完成一部分，也要先登记 `active` 或 `blocked`，不要等全部做完再补记。

## 第一批建议直接启动的事项

- H5-1：先补 `ARCHITECTURE.md`，只写代码物理地图、边界和禁止依赖，不写业务细节
- H5-2：优先为 `report-solution` 或 `ownership-migration` 增加 `mission` 工件，验证“需求 -> mission -> plan -> workflow”的最短闭环
- H5-4：先把现有配置中心与高风险路由静态规则升级成带“建议修复层级 + 推荐复跑命令”的输出

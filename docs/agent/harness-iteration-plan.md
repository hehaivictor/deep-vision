# DeepVision Harness 二阶段迭代计划

这份计划只覆盖 DeepVision 在现有 harness 基线之上的第二阶段优化，不重复记录已经落地的入口、artifact、task profile、browser smoke、CI summary 和 history/observe 能力。

## 目标

- 把现有的多套检查能力收敛成更统一的持续评估系统
- 提高前后端真实联动回归的覆盖深度，减少只在 mock 环境下为绿的风险
- 让 task workflow、evaluator、observe、CI 三层之间的信息流更顺畅
- 把后续执行痕迹固定沉淀到仓库内，而不是散落在对话里

## 当前基线

- 统一入口：`scripts/agent_harness.py`
- 受控任务执行：`scripts/agent_workflow.py`
- 只读观察与历史对比：`scripts/agent_observe.py`、`scripts/agent_history.py`
- 场景 evaluator：`scripts/agent_eval.py`
- 浏览器 UI smoke：`scripts/agent_browser_smoke.py`
- task-backed playbook：`scripts/agent_playbook_sync.py`
- PR / nightly workflow 与 GitHub Step Summary 已接通

## 状态约定

- `planned`：已排期，尚未开始
- `active`：正在执行
- `done`：已完成并验证
- `blocked`：有明确阻塞，需要先处理依赖

## 迭代清单

| 编号 | 状态 | 主题 | 目标 | 主要交付物 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| H2-1 | done | 多执行器 evaluator | 让 evaluator 不再只跑 `unittest`，可原生评估 `browser_smoke`、`workflow`、`harness` | `scripts/agent_eval.py`、`tests/harness_scenarios/**/*.json` | nightly 可混跑至少 1 个 `browser_smoke` 场景和 1 个 `workflow` 场景 |
| H2-2 | done | 浏览器回归真链路 | 在 mock browser smoke 之外补一条 seeded backend / live profile 回归 | `scripts/agent_browser_smoke.py`、`scripts/agent_browser_smoke_runner.mjs`、`tests/harness_scenarios/browser/browser-smoke-live-minimal.json` | 至少 1 条前后端真实联动链路可稳定执行并落 artifact |
| H2-3 | done | Browser PR lane | 把 browser smoke 纳入更常规的 PR 检查，而不是只靠手动或周跑 | `.github/workflows/browser-smoke.yml`、CI 触发条件 | 前端相关改动能自动触发 browser smoke，并上传摘要与工件 |
| H2-4 | done | Task 覆盖扩编 | 把高频但尚未 task 化的操作收进统一画像 | `resources/harness/tasks/*.json`、`docs/agent/playbooks/*.md`、`docs/agent/auth-identity.md` | 新增 `account-merge`、`license-admin`、`presentation-export` 3 个 task，均可 `--list-tasks`、生成 playbook、跑通 preview |
| H2-5 | done | Workflow DSL 强化 | 补更细的前置条件和步骤语义 | `scripts/agent_workflow.py`、`scripts/agent_profiles.py`、`resources/harness/tasks/*.json` | 已支持 `requires_admin_session`、`requires_browser_env`、`requires_live_backend`，并接入高风险管理员 task |
| H2-6 | done | Observe 诊断面板 | 让 observe 从“趋势摘要”升级成“可直接决策的诊断面板” | `scripts/agent_observe.py`、`scripts/agent_history.py` | 输出最近最常失败 task、Top blocker、慢场景和推荐复跑命令 |
| H2-7 | done | 语料库扩容 | 扩大 evaluator 场景覆盖，补 UI、回滚、多租户、导出下载等真实故障面 | `tests/harness_scenarios/**/*.json` | evaluator 场景数从当前基线继续扩展，并覆盖 UI / 运维 / 安全三类新场景 |
| H2-8 | done | CI 拓扑收敛 | 清理 `pr-smoke`、`agent-smoke`、`guardrails`、`browser-smoke` 的重复感 | `.github/workflows/*.yml`、CI 文档 | PR 检查矩阵更清晰，重复执行减少，摘要入口保持统一 |

## 推荐执行顺序

二阶段计划已完成，如需继续优化请开启下一阶段排期。

## 每项执行要求

每完成一个编号，必须同步更新 [harness-progress.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress.md)，至少记录：

- 完成日期
- 对应编号
- 实际改动范围
- 已执行的验证命令
- 关键 artifact / 文档入口
- 剩余风险和下一步

如果某项只完成一部分，也要先登记 `active` 或 `blocked`，不要等全部做完再补记。

## 第一批建议直接启动的事项

- H2-4：补高频但尚未 task 化的任务画像
- H2-5：继续把 workflow 语义往更强约束推进

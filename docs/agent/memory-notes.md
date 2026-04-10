# DeepVision Memory Notes

> 生成时间：2026-04-10T07:45:35Z

## 当前焦点

- 当前阶段：`phase6`
- 当前优先项：`H6-5 Dependency Chain Hardening`
- 阶段台账：`docs/agent/harness-progress-phase6.md`
- 阶段计划：`docs/agent/harness-iteration-plan-phase6.md`

## 最近稳定经验

- 先读 heartbeat 与就近 AGENTS，再决定进入哪个领域文档、task workflow 或 evaluator 场景。
- 高风险 task 默认先走 workflow preview，并保留 artifact / handoff，而不是直接进入 apply 或裸跑脚本。
- 修改 task 画像后先跑 `agent_playbook_sync.py --check` 和 `agent_doc_gardener.py`，避免 playbook 漂移。
- 新增需求优先先生成 mission + planner latest 指针，再进入 workflow / evaluator，避免只留控制台历史。
- 高风险 task 已有 Sprint Contract，默认按 contract 的 done_when / evidence_required 收口，而不是临时定义完成标准。
- 进入 `web/`、`web/server_modules/`、`web/app_modules/`、`scripts/`、`tests/` 时优先读取局部 AGENTS，减少上下文加载成本。

## 最近健康指针

- 关键不变量 gate 最近稳定，涉及高风险边界时优先先看 guardrails，再决定是否下钻到单测。
- Runtime smoke 最近稳定，改动后优先走 `agent_harness.py --profile auto` 而不是单独挑命令。
- 前端相关改动优先沿 browser smoke lane 验证，减少只靠 unittest 的盲区。

## 注意事项

- 当前没有额外注意事项。

## 刷新命令

- `python3 scripts/agent_autodream.py`
- `python3 scripts/agent_heartbeat.py`
- `python3 scripts/agent_doc_gardener.py`
- `python3 scripts/agent_harness.py --profile auto`
- `python3 scripts/agent_eval.py --tag nightly`

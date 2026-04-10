# DeepVision Harness 五阶段进度台账

这份台账用于记录五阶段 harness 优化的执行痕迹。后续每做完一项，或出现阻塞，都在这里追加一条记录。

## 当前执行面

- 当前阶段：`phase5`
- 当前优先项：`已完成，待新阶段计划`
- 对应计划：[harness-iteration-plan-phase5.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase5.md)

## 进度记录

| 日期 | 编号 | 状态 | 事项 | 证据 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| 2026-04-10 | PLAN-5 | done | 建立五阶段 harness 迭代计划与独立进度台账，收口 Architecture Map、Mission Contract、Global Heartbeat、Action-for-Agent、依赖规则强化与低风险园丁方向 | [harness-iteration-plan-phase5.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase5.md)、[harness-progress-phase5.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase5.md) | 启动 H5-1，先补仓库级 `ARCHITECTURE.md` |
| 2026-04-10 | H5-1 | done | 新增仓库级 `ARCHITECTURE.md`，收口后端、前端、数据配置与 harness 的物理地图，并明确允许的依赖方向与禁止回退的边界；同步把入口导航挂回 `AGENTS.md`、`README.md` 与 `docs/agent/README.md` | [ARCHITECTURE.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/ARCHITECTURE.md)、[AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)、[README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)、[docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)、验证命令 `git diff --check` | 启动 H5-2，补 Mission Contract，使一句话需求先进入 mission 再生成 task plan |
| 2026-04-10 | H5-2 | done | 新增 `scripts/agent_missions.py`，把一句话需求先物化为 Mission Contract，再由 `agent_planner.py` 同步写出 mission + plan；`workflow / harness / evaluator / handoff` 已开始共同引用 mission 指针；首批接入 `report-solution` 与 `ownership-migration` | [scripts/agent_missions.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_missions.py)、[scripts/agent_planner.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_planner.py)、[resources/harness/tasks/report-solution.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/resources/harness/tasks/report-solution.json)、[resources/harness/tasks/ownership-migration.json](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/resources/harness/tasks/ownership-migration.json)、验证命令 `python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`、`python3 scripts/agent_planner.py --task report-solution --goal "修复方案页分享异常并保留旧报告兼容" --artifact-dir artifacts/planner`、`python3 scripts/agent_workflow.py --task report-solution --execute plan`、`python3 scripts/agent_eval.py --scenario report-solution-preview --artifact-dir artifacts/harness-eval/h5-2-mission` | 启动 H5-3，补全局 heartbeat / memory 指针层，避免阶段状态继续散落在入口文档里 |
| 2026-04-10 | H5-3 | done | 新增 `scripts/agent_heartbeat.py`、`docs/agent/heartbeat.md` 与 `artifacts/memory/latest.json`，把当前活跃阶段、稳定入口、最近 mission/plan 与最新运行指针收口成全局短记忆；同步把入口文档改成优先引用 heartbeat，而不是继续在导航里广播阶段状态 | [scripts/agent_heartbeat.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_heartbeat.py)、[docs/agent/heartbeat.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/heartbeat.md)、[AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)、[docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)、验证命令 `python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`、`python3 scripts/agent_heartbeat.py`、`git diff --check` | 启动 H5-4，升级静态 guardrail 输出，补 Action-for-Agent 修复建议 |
| 2026-04-10 | H5-4 | done | 扩展 `agent_static_guardrails.py` 输出结构，为每条失败规则补 `修复层级 + 建议动作 + 推荐复跑命令`，并让 `agent_harness` 的 `static_guardrails` 高亮优先提炼这些修复提示；同步更新 phase5 台账、入口文档与 heartbeat 当前优先项 | [scripts/agent_static_guardrails.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_static_guardrails.py)、[scripts/agent_harness.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_harness.py)、[tests/test_scripts_comprehensive.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_scripts_comprehensive.py)、[docs/agent/heartbeat.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/heartbeat.md)、验证命令 `python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`、`python3 scripts/agent_static_guardrails.py`、`python3 scripts/agent_heartbeat.py`、`git diff --check` | 启动 H5-5，继续把导入/调用方向规则机械化，先从配置中心和高风险路由边界下手 |
| 2026-04-10 | H5-5 | done | 新增 `business_python_does_not_import_harness` 静态规则，扫描 `web/` 下 Python 业务代码，阻止 `web/server.py` 与 `web/server_modules/*` 反向 import `scripts.agent_*` harness 脚本；同步更新静态规则文本输出、入口文档与 heartbeat 当前优先项 | [scripts/agent_static_guardrails.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_static_guardrails.py)、[tests/test_scripts_comprehensive.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_scripts_comprehensive.py)、[AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)、[docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)、验证命令 `python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`、`python3 scripts/agent_static_guardrails.py`、`python3 scripts/agent_heartbeat.py`、`git diff --check` | 启动 H5-6，补低风险 doc gardening / orchestrator，优先做一致性报告而非自动改业务代码 |
| 2026-04-10 | H5-6 | done | 新增 `scripts/agent_doc_gardener.py` 与 `artifacts/doc-gardening/.gitignore`，把 playbook 漂移、入口索引、contract 覆盖、mission/planner latest 指针与 calibration 登记状态收口为只读一致性报告；同步更新入口文档、phase5 计划与 heartbeat | [scripts/agent_doc_gardener.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_doc_gardener.py)、[artifacts/doc-gardening/.gitignore](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/doc-gardening/.gitignore)、[AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)、[docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)、[docs/agent/heartbeat.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/heartbeat.md)、验证命令 `python3 scripts/agent_doc_gardener.py`、`python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`、`python3 scripts/agent_heartbeat.py`、`git diff --check` | phase5 已完成；如继续推进，先新建下一阶段计划，再决定是补 contract/mission 覆盖还是继续做 repo hygiene |

## 记录模板

复制以下模板追加到表格末尾：

```text
| YYYY-MM-DD | H5-x | planned/active/done/blocked | 简述本次推进内容 | 关键文件或 artifact 链接 | 明确下一步 |
```

## 补充说明

- 如果本次执行修改了 planner、workflow、contract、observe、evaluator 或 static guardrails，优先同时补链接到对应文件。
- 如果执行了验证命令，但没有新增 artifact，也要在“证据”里写明命令。
- 如果出现阻塞，必须写出阻塞点，不要只写“待继续”。

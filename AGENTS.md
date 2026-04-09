<INSTRUCTIONS>

# DeepVision Agent 入口

本文件只做导航，不承载完整领域知识。进入仓库后先看这里，再按任务跳转到对应文档。

## 沟通与提交

- Codex 回答和思考过程要求使用中文。
- 提交信息必须使用中文。
- 提交信息需按改动内容分类分行描述，不要把所有改动写成一句话。
- 提交前需根据改动内容自动判断版本升级级别，但不要在提交信息里单独写“版本判定”。
- 提交信息需逻辑清晰、简明扼要、避免错别字。

## 首先阅读

- 仓库总览与启动方式：[README.md](README.md)
- Agent 分层索引：[docs/agent/README.md](docs/agent/README.md)
- 访谈链路：[docs/agent/interview.md](docs/agent/interview.md)
- 鉴权、绑定与账号合并：[docs/agent/auth-identity.md](docs/agent/auth-identity.md)
- 报告与方案页：[docs/agent/report-solution.md](docs/agent/report-solution.md)
- 管理后台与运维能力：[docs/agent/admin-ops.md](docs/agent/admin-ops.md)
- 运行态观察：[docs/agent/observability.md](docs/agent/observability.md)
- 场景 evaluator：[docs/agent/evaluator.md](docs/agent/evaluator.md)
- Harness 二阶段复盘：[docs/agent/harness-iteration-plan.md](docs/agent/harness-iteration-plan.md)
- Harness 二阶段进度台账：[docs/agent/harness-progress.md](docs/agent/harness-progress.md)
- Harness 三阶段计划：[docs/agent/harness-iteration-plan-phase3.md](docs/agent/harness-iteration-plan-phase3.md)
- Harness 三阶段进度台账：[docs/agent/harness-progress-phase3.md](docs/agent/harness-progress-phase3.md)
- 高频任务标准流程：[docs/agent/playbooks/README.md](docs/agent/playbooks/README.md)
- 数据迁移与实例隔离：[docs/agent/migration.md](docs/agent/migration.md)
- 多 worktree 交付约定：[docs/worktree-shipping.md](docs/worktree-shipping.md)

## 启动命令

- 单入口检查：`python3 scripts/agent_harness.py --profile local`
- 交付/CI 场景单入口检查：`python3 scripts/agent_harness.py --profile auto`
- 落盘 harness 工件：`python3 scripts/agent_harness.py --profile auto --artifact-dir artifacts/harness-runs`
- 列出内置任务画像：`python3 scripts/agent_harness.py --list-tasks`
- 只读运行态观察（含最近运行趋势）：`python3 scripts/agent_observe.py --profile auto`
- 查看最近 harness / evaluator / CI 历史：`python3 scripts/agent_history.py --kind all --limit 5`
- 对比最近两次 harness 漂移：`python3 scripts/agent_history.py --kind harness --diff`
- 查看二阶段优化排期：`sed -n '1,240p' docs/agent/harness-iteration-plan.md`
- 查看二阶段执行进度台账：`sed -n '1,240p' docs/agent/harness-progress.md`
- 查看三阶段优化排期：`sed -n '1,240p' docs/agent/harness-iteration-plan-phase3.md`
- 查看三阶段执行进度台账：`sed -n '1,240p' docs/agent/harness-progress-phase3.md`
- 从最新 artifact 生成场景脚手架：`python3 scripts/agent_scenario_scaffold.py --source latest --dry-run`
- 从 latest.json 生成 CI 摘要：`python3 scripts/agent_ci_summary.py --latest-json artifacts/ci/browser-smoke/latest.json --title "Browser Smoke Summary"`
- 检查 task-backed playbook 是否与任务画像同步：`python3 scripts/agent_playbook_sync.py --check`
- 带观察阶段的 harness：`python3 scripts/agent_harness.py --observe --profile auto`
- 源码级静态 guardrail：`python3 scripts/agent_static_guardrails.py`
- 浏览器级 UI smoke：`python3 scripts/agent_browser_smoke.py --suite minimal`
- 扩展浏览器级 UI smoke：`python3 scripts/agent_browser_smoke.py --suite extended`
- 隔离后端真链路 browser smoke：`python3 scripts/agent_browser_smoke.py --suite live-minimal`
- 扩展版真链路 browser smoke：`python3 scripts/agent_browser_smoke.py --suite live-extended`
- 在 harness 中附加 browser smoke：`python3 scripts/agent_harness.py --profile auto --browser-smoke`
- 列出 evaluator 场景：`python3 scripts/agent_eval.py --list`
- 执行 nightly evaluator：`python3 scripts/agent_eval.py --tag nightly`
- 落盘 evaluator 工件：`python3 scripts/agent_eval.py --tag nightly --artifact-dir artifacts/harness-eval`
- 按任务画像执行：`python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000`
- 单独预演 task workflow：`python3 scripts/agent_workflow.py --task ownership-migration --task-var target_account=13700000000 --execute plan`
- 在 harness 中执行安全 workflow：`python3 scripts/agent_harness.py --task report-solution --workflow-execute preview`
- 显示高风险 apply/rollback 步骤：`python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000 --allow-apply`
- 只读环境自检：`python3 scripts/agent_doctor.py --profile local`
- 关键不变量 gate：`python3 scripts/agent_guardrails.py --quiet`
- 最小主链路回归：`python3 scripts/agent_smoke.py`
- 本地开发：`./scripts/start-local-dev.sh`
- 云端联调：`./scripts/start-cloud-dev.sh`
- 生产启动：`./scripts/start-production.sh`
- 生产预启动初始化：`python3 scripts/prestart_web.py`
- 自定义环境文件：`DEEPVISION_ENV_FILE=/path/to/custom.env uv run web/server.py`

## 最小测试矩阵

- 单入口检查：`python3 scripts/agent_harness.py --profile local`
- 交付前聚合检查：`python3 scripts/agent_harness.py --profile auto`
- 交付前落盘证据：`python3 scripts/agent_harness.py --profile auto --artifact-dir artifacts/harness-runs`
- 高风险 task 默认只展示 preview 路径；需要人工确认后才使用 `--allow-apply`
- task workflow 默认 `plan` 只预演；切到 `--workflow-execute preview/full` 才会实际执行步骤
- task workflow 中的 `unittest` 步骤会复用 `agent_test_runner`，与 `smoke/guardrails` 使用同一套 `uv run` 测试执行壳
- 高风险 workflow 步骤现在会额外校验 `confirmation_token`、`backup_dir` 和 `produces_artifact`；不要只看命令返回码
- 高风险 workflow 的 apply/rollback 现在还会强制校验治理字段；执行前补齐 `change_reason / operator / approver / ticket`
- task workflow 现在支持前置条件检查；已内置 `account_exists`、`user_exists`、`active_license_exists`、`path_exists`、`requires_admin_session`、`requires_browser_env`、`requires_live_backend`
- `ownership-migration`、`config-center`、`license-admin` 现在会先验证管理员白名单是否就绪；`cloud-import` 仍会先验证源目录和目标用户
- `agent_harness` 默认会先执行 `static_guardrails`，用于扫描高风险路由的源码级权限与确认链路
- browser smoke 为显式 opt-in 阶段；首次执行前先运行 `npm install`，再执行 `npx playwright install chromium chromium-headless-shell`
- PR 基础检查已收口到 `.github/workflows/pr-harness.yml`，其中 `pr-smoke` 负责脚本回归与 `static_guardrails`，`agent-smoke` 只跑 runtime smoke，`guardrails` 只跑 runtime guardrails
- 浏览器回归已提供独立 workflow：`.github/workflows/browser-smoke.yml`，当前会在前端相关 PR 改动时自动触发 `extended` 套件，并保留手动与周跑入口
- `pr-harness.yml`、`browser-smoke.yml` 与 `harness-nightly.yml` 现在都会额外写 GitHub Step Summary，便于直接查看一屏结论
- `pr-harness.yml` 现已增加 `changes` 预判；当 PR 未涉及 runtime harness 相关路径时，`agent-smoke` 与 `guardrails` 会输出 `SKIPPED` 摘要而不再重复安装 `uv`
- `browser-smoke.yml` 与 `harness-nightly.yml` 现已缓存 pip 与 Playwright 浏览器目录，并为 nightly 增加并发收敛，减少重复安装与重叠运行成本
- `agent_observe.py` 的 `history_trends` 现在会额外聚合最近最常告警 task、blocker 和慢场景，并标记连续失败、重复 blocker、慢场景回归三类阈值信号
- `agent_observe.py` 现在还会输出 `diagnostic_panel`，直接给出 Top task / blocker / 慢场景、阈值告警摘要和推荐复跑命令
- `extended` browser smoke 现在覆盖帮助页、方案页分享、公开分享只读、登录前端视图、License 门禁前端视图、License 绑定成功切回业务壳、报告详情与方案入口以及管理员配置中心页签切换
- `live-minimal` browser smoke 会在隔离 `DATA_DIR` 下启动真实后端，验证“验证码登录 -> License 绑定 -> 进入访谈会话”的真链路
- `live-extended` browser smoke 会在 `live-minimal` 基础上继续验证真实报告详情、方案页和公开分享只读链路
- `live-minimal` 目前仍保留为手动深回归，不进入 PR lane
- evaluator 已拆出 `tenant` 主题场景，用于单独跟踪实例隔离、分享 owner、账号合并资产归属和导出资产对象存储元数据边界
- 关键不变量 gate：`python3 scripts/agent_guardrails.py --quiet`
- 固定 smoke 入口：`python3 scripts/agent_smoke.py`
- 场景 evaluator：`python3 scripts/agent_eval.py --tag nightly`
- evaluator 场景已支持 `unittest`、`browser_smoke`、`workflow` 和 `harness` 多执行器
- evaluator 场景库当前共 14 条，已补到扩展 UI、账号合并回滚、License 管理预演、环境文件叠加解析和演示稿 sidecar 并发完整性
- 新事故优先用 `python3 scripts/agent_scenario_scaffold.py` 生成 `tests/harness_scenarios` 模板，再人工补充背景与 tags
- `failure-summary.md` / `handoff.json` 现在会直接给出带 `name/category/tag/budget/output` 的场景脚手架预览/写入命令；`browser_smoke`、`workflow`、`harness` 失败也能自动生成对应 executor 模板
- 最小脚本冒烟：`python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`
- 主接口回归：`python3 -m unittest tests.test_api_comprehensive`
- 安全与权限回归：`python3 -m unittest tests.test_security_regression`
- 方案页载荷回归：`python3 -m unittest tests.test_solution_payload`
- 全量回归：`python3 -m unittest discover -s tests -p 'test_*.py'`

说明：

- 当前 CI 已通过 `pr-harness.yml` 提供 `pr-smoke`、`agent-smoke` 与 `guardrails` 三条基础检查；更重的场景语料回归交由 `harness-nightly` 执行。
- `agent-smoke` 与 `guardrails` 在 PR 中会上传结构化工件，可直接查看 `progress.md`、`failure-summary.md` 与 `handoff.json`。
- `agent_observe.py` 现在会直接带出最近运行趋势、Top blocker 与推荐复跑命令；`agent_history.py` 用于继续向下钻取完整索引与 diff。
- 现有测试大多会把 `DATA_DIR`、鉴权库和索引库切到临时目录；新增测试时优先沿用这种隔离方式，避免污染仓库下的 `data/`。
- `--artifact-dir` 会把 `summary.json`、分阶段 JSON、stdout/stderr 和 `latest.json` 指针写到指定目录，适合交接和失败排查。
- 开启 `--artifact-dir` 后，还会写出 `progress.md`、`failure-summary.md`、`handoff.json`、`latest-progress.md`、`latest-failure-summary.md` 和 `latest-handoff.json`。
- 当前内置 task 画像包括 `report-solution`、`presentation-export`、`account-merge`、`license-audit`、`license-admin`、`ownership-migration`、`config-center`、`cloud-import`，配置文件位于 `resources/harness/tasks/*.json`。
- task-backed playbook 默认由 `resources/harness/tasks/*.json` 生成，修改任务画像后优先运行 `python3 scripts/agent_playbook_sync.py` 或 `--check`。
- 场景语料文件位于 `tests/harness_scenarios/**/*.json`，新增线上事故回归时优先补对应 `unittest`，再挂入场景文件。
- 高频操作 playbook 位于 `docs/agent/playbooks/*.md`，默认先按 playbook 收集证据，再决定是否进入高风险步骤。
- 执行 `docs/agent/harness-iteration-plan.md` 中的优化项后，必须同步更新 `docs/agent/harness-progress.md`。

## 关键不变量

- 所有写接口默认要求登录；运维接口默认要求管理员权限。
- 会话、报告、分享、批量删除都必须同时尊重 `owner_user_id` 与 `instance_scope_key`。
- 方案页默认消费已绑定报告的最终快照；老报告允许回退到 Markdown 解析，但不能破坏现有兼容链路。
- 服务启动前必须保证 `auth_db`、`license_db`、`meta_index schema` 已就绪；不要再依赖 import 副作用完成关键初始化。
- 高风险数据操作优先 `dry-run`、预览、备份、可回滚，正式执行必须有明确确认。

## 高风险操作

- 不要默认修改 `web/.env.local`、`web/.env.cloud`、真实部署环境变量或 `data/` 下的运行数据，除非用户明确要求。
- `scripts/admin_migrate_ownership.py`、`scripts/import_external_local_data_to_cloud.py`、`scripts/rollback_external_local_data_import.py` 这类脚本优先使用预览模式。
- `scripts/sync_object_storage_history.py` 属于迁移阶段治理工具，不要把它当作常驻在线任务。
- 管理后台涉及 License 批量操作、配置中心写入、归属迁移 apply/rollback，默认视为高风险变更。

## 工作方式建议

- `web/server.py` 与 `web/app.js` 体量很大，改动前先读对应领域文档和相关测试，再局部定位代码。
- 能复用现有脚本和 runbook 时，不要新造一套并行流程。
- 涉及发布链路时，遵循版本碎片机制与 `worktree-shipping` 约定，不要手工绕开现有流程。

</INSTRUCTIONS>

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `/Users/hehai/.local/share/uv/tools/graphifyy/bin/python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current

# DeepVision Agent 文档索引

这些文档服务于 brownfield 仓库里的 agent 入口问题：先快速建立地图，再进入对应领域细节，避免每次都从 [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md) 和超大文件里重新摸索。

## 推荐阅读顺序

1. 先读 [AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)，确认启动方式、测试矩阵、风险边界和关键不变量。
2. 再根据任务选择一个领域文档：
   - 访谈与下一题逻辑：[interview.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/interview.md)
   - 登录、绑定与账号合并：[auth-identity.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/auth-identity.md)
   - 报告生成、方案页与分享：[report-solution.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/report-solution.md)
   - 管理后台、运行监控与配置治理：[admin-ops.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/admin-ops.md)
   - 运行态观察、最近工件与历史回溯：[observability.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/observability.md)
   - 场景语料库、nightly evaluator 与失败热点：[evaluator.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/evaluator.md)
   - Harness 二阶段复盘：[harness-iteration-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan.md)
   - Harness 二阶段执行台账：[harness-progress.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress.md)
   - Harness 三阶段计划：[harness-iteration-plan-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-iteration-plan-phase3.md)
   - Harness 三阶段进度台账：[harness-progress-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase3.md)
   - 高频任务标准流程：[playbooks/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/README.md)
   - 实例隔离、导入迁移与历史补齐：[migration.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/migration.md)
3. 真正编辑前，再补读对应测试与 runbook。

## 快速选路

- 改会话创建、题目推进、证据 ledger、文档上传、访谈恢复：看 [interview.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/interview.md)
- 改登录、手机号/微信绑定、账号冲突和合并回滚：看 [auth-identity.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/auth-identity.md)
- 改报告模板、生成队列、方案页渲染、分享、导出、演示稿：看 [report-solution.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/report-solution.md)
- 改 License、管理员中心、配置中心、指标、摘要缓存、归属迁移：看 [admin-ops.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/admin-ops.md)
- 改 `INSTANCE_SCOPE_KEY`、云端导入、回滚、对象存储历史补齐：看 [migration.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/migration.md)

## 固定入口命令

- 单入口检查：`python3 scripts/agent_harness.py --profile local`
- 交付/CI 场景单入口检查：`python3 scripts/agent_harness.py --profile auto`
- 落盘 harness 工件：`python3 scripts/agent_harness.py --profile auto --artifact-dir artifacts/harness-runs`
- 只读运行态观察：`python3 scripts/agent_observe.py --profile auto`
- 查看最近历史：`python3 scripts/agent_history.py --kind all --limit 5`
- 对比最近两次 harness：`python3 scripts/agent_history.py --kind harness --diff`
- 查看二阶段优化排期：`sed -n '1,240p' docs/agent/harness-iteration-plan.md`
- 查看二阶段执行进度台账：`sed -n '1,240p' docs/agent/harness-progress.md`
- 查看三阶段优化排期：`sed -n '1,240p' docs/agent/harness-iteration-plan-phase3.md`
- 查看三阶段执行进度台账：`sed -n '1,240p' docs/agent/harness-progress-phase3.md`
- 从 artifact 生成场景脚手架：`python3 scripts/agent_scenario_scaffold.py --source latest --dry-run`
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
- evaluator 现在已支持 `unittest`、`browser_smoke`、`workflow` 和 `harness` 多执行器场景
- 场景语料库当前共 14 条，已扩到扩展 UI、账号合并回滚、License 管理预演、环境文件叠加解析和演示稿 sidecar 并发完整性
- 列出 task 画像：`python3 scripts/agent_harness.py --list-tasks`
- 任务画像执行示例：`python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000`
- 单独预演 workflow：`python3 scripts/agent_workflow.py --task ownership-migration --task-var target_account=13700000000 --execute plan`
- 在 harness 中执行安全 workflow：`python3 scripts/agent_harness.py --task report-solution --workflow-execute preview`
- task workflow 中的测试步骤默认复用统一 `unittest` 执行壳，不再裸跑 `python3 -m unittest`
- 高风险 workflow 步骤会额外校验 `confirmation_token`、`backup_dir` 与 `produces_artifact`
- 高风险 workflow 的 apply/rollback 现在还会强制校验治理字段；执行前补齐 `change_reason / operator / approver / ticket`
- 内置高风险 task 还会先执行前置条件检查，例如目标账号存在、源目录存在、活跃 License 存在、管理员白名单是否就绪
- workflow DSL 现已支持 `requires_admin_session`、`requires_browser_env`、`requires_live_backend` 三类环境语义，可用于把管理员会话、浏览器依赖和 live backend 条件机器化
- `agent_harness` 默认会先执行 `static_guardrails`，用于补源码级路由权限与确认链路回归
- browser smoke 用于补帮助页、方案页分享、公开分享只读边界、登录前端视图、License 门禁前端视图、License 绑定成功切换、报告详情链路和管理员配置中心入口的浏览器级回归；首次执行前先运行 `npm install` 和 `npx playwright install chromium chromium-headless-shell`
- `live-minimal` 会在隔离 `DATA_DIR` 下启动真实后端，执行“验证码登录 -> License 绑定 -> 进入访谈会话”的手动深回归
- `live-extended` 会在 `live-minimal` 基础上继续验证真实报告详情、方案页和公开分享只读链路
- evaluator 已补 `tenant` 主题场景：`instance-scope-boundaries` 用于 nightly 跟踪实例隔离，`asset-ownership-boundaries` 用于 manual 跟踪分享 owner、账号合并和导出资产元数据边界
- PR 基础检查已统一收口到 `.github/workflows/pr-harness.yml`；其中 `pr-smoke` 负责脚本回归与 `static_guardrails`，`agent-smoke` 只跑 runtime smoke，`guardrails` 只跑 runtime guardrails
- 仓库已提供独立的 browser smoke workflow，位于 `.github/workflows/browser-smoke.yml`；前端相关 PR 改动会自动触发 `extended` 套件，`live-minimal` 继续保留为手动深回归
- PR / nightly 相关 workflow 现在都会额外写 GitHub Step Summary，可先看摘要再决定是否下载 artifact
- `agent_scenario_scaffold.py` 会优先从 harness/evaluator artifact 里提取 unittest id，生成 `manual + incident` 场景模板，再由人工补充业务背景
- `agent_scenario_scaffold.py` 现在还会自动推断 `category / tags / budget / output`；对 `browser_smoke`、`workflow`、`harness` 失败也能直接生成 executor 场景模板
- `agent_observe.py` 现在会附带最近 harness / evaluator / CI 趋势摘要；`agent_history.py` 用于继续查看完整 diff
- `agent_observe.py` 的 `history_trends` 会额外聚合最近最常告警 task、blocker 和慢场景，并标出连续失败、重复 blocker、慢场景回归三类阈值信号
- `agent_observe.py` 还会输出 `diagnostic_panel`，直接带出阈值告警摘要和推荐复跑命令，便于先复查再改代码
- 环境自检：`python3 scripts/agent_doctor.py --profile local`
- 关键不变量 gate：`python3 scripts/agent_guardrails.py --quiet`
- 最小主链路回归：`python3 scripts/agent_smoke.py`
- 扩展 smoke 套件：`python3 scripts/agent_smoke.py --suite extended`

当前内置 task：

- `report-solution`：报告生成、方案页与分享链路
- `presentation-export`：报告导出、附录 PDF、演示稿和导出资产权限
- `account-merge`：手机号/微信绑定冲突、merge preview/apply 与管理员 rollback
- `license-audit`：License 状态、运行时开关和账号绑定审计
- `license-admin`：License 生成、延期、撤销与运行时 enforcement 写操作
- `ownership-migration`：管理员归属迁移，默认先 audit / preview
- `config-center`：配置中心修改，默认先读当前值和专项回归
- `cloud-import`：外部本地 data 导入云端，默认先 dry-run

当前场景 evaluator 分类：

- `browser`：浏览器级 UI 最小链路
- `report-solution`：报告生成、方案页与旧报告兼容
- `migration`：归属迁移与管理员运维边界
- `security`：匿名写接口、License 门禁和分享只读链路
- `ops`：配置中心、启动快照和 observe 读取链路
- `workflow`：task profile 的安全预演与专项回归

交接工件约定：

- `summary.json`：结构化摘要，适合程序继续读取
- `progress.md`：给下一位 agent / 人类的高层进度说明
- `failure-summary.md`：只聚焦失败、告警、热点和下一步处理入口
- `handoff.json`：标准化待办、阻塞、下一步和可直接复跑的命令

当前 playbook：

- `report-debug`：报告生成、方案页和分享链路排查
- `presentation-export`：导出资产、附录 PDF 与演示稿能力边界核对
- `account-merge-verify`：手机号/微信绑定冲突、merge preview/apply 与 rollback 核对
- `migration-preview`：归属迁移的预演、apply 前确认和回滚入口
- `cloud-import-verify`：外部本地 data 导入云端前的 dry-run、专项回归与回滚准备
- `license-audit`：License 状态、运行时开关和账号绑定审计
- `license-admin`：License 生成、延期、撤销和运行时 enforcement 写入前核对
- `config-center-verify`：配置中心写入前的运行态核对
- 上述 playbook 均由 `resources/harness/tasks/*.json` 自动生成

## 共享原则

- 优先使用仓库内现有脚本和测试，把文档、代码、验证路径保持在同一个仓库里。
- 大文件不等于无边界。即使实际实现还在 [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py) 里，也要先按领域定位，再读取局部。
- 改动前先决定验证范围。DeepVision 当前 CI 已通过 `pr-harness.yml` 运行 `pr-smoke`、`agent-smoke` 与 `guardrails`；nightly evaluator 则负责更重的场景语料回归。
- 执行二阶段事项时，继续维护 [harness-progress.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress.md)；执行三阶段事项时，改维护 [harness-progress-phase3.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase3.md)。

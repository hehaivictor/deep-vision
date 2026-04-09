# DeepVision

DeepVision 是一个面向需求访谈、方案沉淀与交付输出的 AI Web 应用。系统覆盖「发起访谈 -> 沉淀记录 -> 生成报告 -> 派生方案页 -> 导出与分享」的完整链路，适合需求调研、售前咨询、业务诊断与方案澄清场景。

当前版本：`5.0.2`（`2026-03-19`，见 [web/version.json](web/version.json)）

## 近期更新

- 访谈链路：补齐下一题生成的超时看门狗与失活恢复，异常请求不会再长期停留在加载态
- 报告与方案页：统一消费已绑定报告的最终快照，方案页支持跟随自定义章节蓝图渲染
- 帮助与导航：修复帮助文档目录定位与当前章节高亮，补齐方案页与会话页的前端一致性体验
- 管理后台：新增独立管理员中心，统一收口 License 生命周期、配置中心、运行监控、摘要缓存与账号归属迁移

## 核心能力

- 智能访谈：按场景驱动问题生成，支持追问、进度推进、会话持久化，以及下一题超时恢复
- 资料输入：支持 `md`、`txt`、`pdf`、`docx`、`xlsx`、`pptx` 上传并转为可引用内容
- 报告生成：异步队列化生成、状态轮询、质量门控、证据索引、自定义章节蓝图
- 方案页输出：从报告派生结构化方案页，默认基于最终报告快照生成，支持匿名只读分享链接
- 导出能力：支持 Markdown、Word、PDF、附录 PDF
- 鉴权能力：手机号验证码登录（`mock` / 京东云短信），支持可选微信扫码登录，可按开关启用登录后 License 强制校验
- 管理员中心：独立后台页签，支持 `.env / config.py` 配置分组编辑、License 生成/筛选/延期/撤销/时间线、运行监控、摘要缓存清理与归属迁移 dry-run/apply/rollback
- 场景管理：内置场景 + 自定义场景，支持目录化加载
- 帮助文档：内置帮助页，支持 `h2-h4` 目录、本节目录与当前章节高亮
- 稳定性优化：分页、ETag/304、429 快速失败、缓存预热、最终态快照与前端请求看门狗

## 技术结构

- 后端：Flask 单文件主服务 [web/server.py](web/server.py)
- 前端：原生 HTML / CSS / JavaScript，主入口为 [web/index.html](web/index.html) 与 [web/app.js](web/app.js)
- 方案页：独立入口 [web/solution.html](web/solution.html)、[web/solution.js](web/solution.js)、[web/solution.css](web/solution.css)
- 帮助页：独立入口 [web/help.html](web/help.html)
- 生产运行：Gunicorn + [web/wsgi.py](web/wsgi.py)
- 依赖管理：使用 `uv run` 直接读取 [web/server.py](web/server.py) 顶部的 inline dependency metadata

面向 Codex / agent 的最小仓库入口见 [AGENTS.md](AGENTS.md)，领域分层说明见 [docs/agent/README.md](docs/agent/README.md)。
高频任务标准流程见 [docs/agent/playbooks/README.md](docs/agent/playbooks/README.md)。
新增的账号绑定/合并与导出/演示稿链路，可分别从 [docs/agent/auth-identity.md](docs/agent/auth-identity.md) 和 `account-merge`、`presentation-export` task 画像进入。
task-backed playbook 可通过 `python3 scripts/agent_playbook_sync.py --check` 校验是否与 `resources/harness/tasks/*.json` 保持同步。
二阶段 harness 复盘见 [docs/agent/harness-iteration-plan.md](docs/agent/harness-iteration-plan.md)，执行记录见 [docs/agent/harness-progress.md](docs/agent/harness-progress.md)。
第三阶段排期见 [docs/agent/harness-iteration-plan-phase3.md](docs/agent/harness-iteration-plan-phase3.md)，进度记录见 [docs/agent/harness-progress-phase3.md](docs/agent/harness-progress-phase3.md)。
第四阶段排期见 [docs/agent/harness-iteration-plan-phase4.md](docs/agent/harness-iteration-plan-phase4.md)，进度记录见 [docs/agent/harness-progress-phase4.md](docs/agent/harness-progress-phase4.md)。
Planner artifact 目录见 [docs/agent/plans/README.md](docs/agent/plans/README.md)，可先把简短需求收口成结构化计划，再进入 task workflow。
高风险 Sprint Contract 位于 `resources/harness/contracts/*.json`，当前已接入 `ownership-migration` 与 `license-admin`，workflow / evaluator / handoff 会共享同一份完成定义。
Evaluator 校准样本见 [docs/agent/evaluator-calibration.md](docs/agent/evaluator-calibration.md) 与 `tests/harness_calibration/*.json`，当前已接入 `report-solution` 的真实误判样本。
场景 evaluator 当前已支持 `unittest`、`browser_smoke`、`workflow` 和 `harness` 多执行器场景。
task workflow 现已支持 `requires_admin_session`、`requires_browser_env`、`requires_live_backend` 前置条件，高风险管理员任务会先验证管理员白名单是否就绪。
`agent_planner.py` 现在会为每个 task 维护 `artifacts/planner/by-task/<task>/latest.json`，Planner / Contract / Workflow / Evaluator / Handoff 已能通过这份指针形成固定信息流。
源码级 static guardrail 现在还会强制检查配置中心路由必须委托 `build_admin_config_center_payload()` / `save_admin_config_group()`，防止在 Flask 路由层重新出现直写配置文件的架构回退。

## 快速开始

### 1. 环境要求

- Python `>= 3.10`
- 安装 [uv](https://docs.astral.sh/uv/)

### 2. 准备配置

推荐保持两套本地私有环境文件：

- `web/.env.local`：本地开发，默认本地 SQLite、本地文件、关闭对象存储与真实短信/微信接入
- `web/.env.cloud`：云端联调，连接云端数据库、对象存储和真实接入能力

准备方式：

- 先参考 [web/.env.example](web/.env.example) 自行创建 `web/.env.local` 与 `web/.env.cloud`
- 这两个文件只在本机使用，不提交仓库
- 默认 `CONFIG_RESOLUTION_MODE=auto`
- 对象存储历史补迁移已不再依赖 Web 启动；需要时请手动运行 `scripts/sync_object_storage_history.py`

配置优先建议：

- 部署、密钥、数据库、对象存储、第三方接入放在进程环境变量，或本机自建的 `web/.env.local` / `web/.env.cloud`
- 仓库内已提供 `web/config.py`，用于维护非敏感的策略默认值
- 不要把真实密钥或部署凭证写入 `web/config.py`

可参考：

- [web/.env.example](web/.env.example)
- [web/config.py](web/config.py)
- [web/CONFIG.md](web/CONFIG.md)（仅说明 `site-config.js` 前端展示配置）
- [docs/instance-scope.md](docs/instance-scope.md)

### 3. 启动开发环境

```bash
./scripts/start-local-dev.sh
```

默认访问地址：

```text
http://127.0.0.1:5001
```

说明：

- 本地开发脚本只加载 `web/.env.local`
- 如果要联调云端数据库、对象存储和真实接入，请使用：

```bash
./scripts/start-cloud-dev.sh
```

- 云端联调脚本只加载 `web/.env.cloud`
- 如需显式指定环境文件，可使用 `DEEPVISION_ENV_FILE=/path/to/custom.env uv run web/server.py`
- 首次运行时，`uv` 会按 [web/server.py](web/server.py) 顶部声明自动准备依赖

## 生产启动

生产部署文件位于：

- [deploy/docker-compose.production.yml](deploy/docker-compose.production.yml)
- [deploy/Dockerfile.production](deploy/Dockerfile.production)
- [deploy/nginx/deepvision.conf.example](deploy/nginx/deepvision.conf.example)

### 方式一：使用脚本

```bash
./scripts/start-production.sh
```

### 方式二：直接运行 Gunicorn

```bash
python3 scripts/run_gunicorn.py
```

说明：

- [scripts/run_gunicorn.py](scripts/run_gunicorn.py) 会自动读取 [web/server.py](web/server.py) 顶部的 inline dependency metadata，并额外补上 `gunicorn`
- Gunicorn 运行参数由 [web/gunicorn.conf.py](web/gunicorn.conf.py) 从进程环境变量读取
- 如果只改 `web/config.py`，Gunicorn 相关参数不会自动生效
- Nginx 示例配置见 [deploy/nginx/deepvision.conf.example](deploy/nginx/deepvision.conf.example)
- 如需使用 Docker Compose 生产部署，请以 [deploy/docker-compose.production.yml](deploy/docker-compose.production.yml) 为唯一正式入口
- 生产环境启动前会校验关键安全配置；`SECRET_KEY` 为模板占位值、`INSTANCE_SCOPE_KEY` 为空或 `SMS_PROVIDER=mock` 时会拒绝启动

## 关键配置项

配置模板以 [web/.env.example](web/.env.example) 为准，常用项如下：

鉴权与索引相关数据可按需落在 SQLite 或 PostgreSQL：

- `AUTH_DB_PATH`：保存用户、登录验证码、微信身份等个人鉴权数据，默认 `data/auth/users.db`
- `LICENSE_DB_PATH`：保存 License、License 事件与 License 签名元数据，默认 `data/auth/licenses.db`
- `META_INDEX_DB_PATH`：保存会话主数据（`session_store`）、报告归属/分享等元数据，以及 `session_index` / `report_index` 索引，默认 `data/meta_index.db`

应用首次升级到该版本时，会在启动时自动把旧 `users.db` 中的 License 数据迁移到独立的 `licenses.db`。

- AI 与模型：
  - `ENABLE_AI`
  - `ANTHROPIC_API_KEY`
  - `ANTHROPIC_BASE_URL`
  - `QUESTION_MODEL_NAME`
  - `REPORT_MODEL_NAME`
  - `REPORT_DRAFT_MODEL_NAME`
  - `REPORT_REVIEW_MODEL_NAME`
- 配置解析：
  - `CONFIG_RESOLUTION_MODE`
  - `DEEPVISION_ENV_FILE`
- 鉴权：
  - `SECRET_KEY`
  - `AUTH_DB_PATH`
  - `LICENSE_DB_PATH`
  - `META_INDEX_DB_PATH`
  - `LICENSE_ENFORCEMENT_ENABLED`
  - `LICENSE_CODE_SIGNING_SECRET`
  - `ADMIN_USER_IDS`
  - `ADMIN_PHONE_NUMBERS`
  - `SMS_PROVIDER`
  - `SMS_TEST_CODE`
- 运行与性能：
  - `LIST_API_DEFAULT_PAGE_SIZE`
  - `LIST_API_MAX_PAGE_SIZE`
  - `REPORT_GENERATION_MAX_WORKERS`
  - `REPORT_GENERATION_MAX_PENDING`
- 目录与隔离：
  - `BUILTIN_SCENARIOS_DIR`
  - `CUSTOM_SCENARIOS_DIR`
  - `INSTANCE_SCOPE_KEY`

## 内测 / 演示环境建议

如果当前阶段仍使用 `mock` 短信登录，建议在本机自建的 `web/.env.local` 或 `web/.env.cloud` 中显式配置：

```env
DEBUG_MODE=true
ENABLE_DEBUG_LOG=false
SECRET_KEY=replace-with-your-own-random-secret
INSTANCE_SCOPE_KEY=deepvision-demo
SMS_PROVIDER=mock
SMS_TEST_CODE=666666
ADMIN_PHONE_NUMBERS=13886047722
```

说明：

- `SMS_PROVIDER=mock` 仅适用于本地调试、内测或演示环境；当 `DEBUG_MODE=false` 时，服务会在启动期拒绝使用 `mock`
- 配置 `SMS_TEST_CODE` 后，内测环境可直接使用固定验证码；未配置时，`mock` 仅会把验证码写入服务端日志
- `ADMIN_PHONE_NUMBERS` / `ADMIN_USER_IDS` 只用于运维接口白名单，不影响普通业务功能
- 变更环境变量或本机自建的 `web/.env.local` / `web/.env.cloud` 后需要重启服务进程；已登录的旧会话如未刷新权限，重新登录一次即可
- 使用固定测试码意味着“知道站点地址的人都可能尝试任意手机号登录”，因此演示环境不要直接暴露到公网

## 运维接口

当前运维接口既可以通过前端“管理员中心”使用，也可以直接通过 JSON API 或脚本调用：

- `GET /api/metrics`：查看接口性能指标、列表接口统计和报告生成队列状态
- `POST /api/metrics/reset`：清空性能指标历史
- `GET /api/summaries`：查看文档摘要缓存数量、大小和开关状态
- `POST /api/summaries/clear`：清空文档摘要缓存，不会删除会话或报告正文
- `GET /api/admin/license-enforcement`：查看当前 License 校验开关状态（运行时值）
- `POST /api/admin/license-enforcement`：动态开启或关闭 License 校验，无需重启服务
- `GET /api/admin/licenses/summary`：查看 License 状态统计、即将到期数量与近期事件
- `POST /api/admin/licenses/batch`：批量生成 License
- `GET /api/admin/licenses`：按批次/状态/账号/时间范围/明文码精确查询 License
- `GET /api/admin/licenses/<id>`：查看单条 License 详情
- `GET /api/admin/licenses/<id>/events`：查看单条 License 生命周期时间线
- `POST /api/admin/licenses/bulk-revoke`：批量撤销 License
- `POST /api/admin/licenses/bulk-extend`：批量延期 License
- `POST /api/admin/licenses/<id>/revoke`：撤销指定 License
- `POST /api/admin/licenses/<id>/extend`：延期指定 License
- `GET /api/admin/config-center`：按分组读取 `.env` 与 `config.py` 配置目录、文件位置、当前运行值与文件值
- `POST /api/admin/config-center/save`：按分组写入 `.env` 或 `config.py` 托管区块，大多数改动需要重启后完全生效
- `GET /api/admin/users`：搜索用户，用于归属迁移或后台定位
- `POST /api/admin/ownership-migrations/audit`：审计目标用户当前拥有的会话 / 报告
- `POST /api/admin/ownership-migrations/preview`：执行 dry-run 预览，返回命中样例、确认词和 preview token
- `POST /api/admin/ownership-migrations/apply`：根据 preview token 和确认词正式执行迁移
- `GET /api/admin/ownership-migrations`：查看迁移历史与可回滚备份
- `POST /api/admin/ownership-migrations/rollback`：按备份记录回滚一次迁移

权限说明：

- 以上接口仅对白名单管理员开放
- 如果当前项目没有正式管理员角色，内测阶段可临时把演示手机号写入 `ADMIN_PHONE_NUMBERS`

## 测试

运行全量回归：

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

面向 agent 的固定入口：

```bash
python3 scripts/agent_harness.py --profile local
python3 scripts/agent_harness.py --profile auto
python3 scripts/agent_harness.py --profile auto --artifact-dir artifacts/harness-runs
python3 scripts/agent_observe.py --profile auto
python3 scripts/agent_history.py --kind all --limit 5
python3 scripts/agent_history.py --kind harness --diff
python3 scripts/agent_scenario_scaffold.py --source latest --dry-run
python3 scripts/agent_ci_summary.py --latest-json artifacts/ci/browser-smoke/latest.json --title "Browser Smoke Summary"
python3 scripts/agent_harness.py --observe --profile auto
python3 scripts/agent_static_guardrails.py
python3 scripts/agent_browser_smoke.py --suite minimal
python3 scripts/agent_browser_smoke.py --suite extended
python3 scripts/agent_harness.py --profile auto --browser-smoke
python3 scripts/agent_eval.py --list
python3 scripts/agent_eval.py --tag nightly
python3 scripts/agent_eval.py --tag nightly --artifact-dir artifacts/harness-eval
python3 scripts/agent_harness.py --list-tasks
python3 scripts/agent_harness.py --task report-solution
python3 scripts/agent_harness.py --task presentation-export --observe
python3 scripts/agent_harness.py --task account-merge
python3 scripts/agent_harness.py --task license-audit
python3 scripts/agent_harness.py --task license-admin
python3 scripts/agent_harness.py --task ownership-migration --task-var target_account=13700000000
python3 scripts/agent_workflow.py --task ownership-migration --task-var target_account=13700000000 --execute plan
python3 scripts/agent_harness.py --task report-solution --workflow-execute preview
python3 scripts/agent_doctor.py --profile local
python3 scripts/agent_guardrails.py --quiet
python3 scripts/agent_smoke.py
```

- 本地开发优先使用 `python3 scripts/agent_harness.py --profile local`
- CI、ship 或不确定环境文件来源时，优先使用 `python3 scripts/agent_harness.py --profile auto`
- 需要保留执行证据或交接排查时，使用 `python3 scripts/agent_harness.py --profile auto --artifact-dir artifacts/harness-runs`
- harness 工件目录会写出 `summary.json`、`progress.md`、`failure-summary.md`、`handoff.json`、`doctor.json`、`guardrails.json`、`smoke.json` 以及 `latest.json`
- 需要先看“最近状态”而不是立刻修改时，优先用 `python3 scripts/agent_observe.py --profile auto`，它现在会顺带输出最近运行趋势与 harness/evaluator 漂移摘要
- `agent_observe.py` 的 `history_trends` 还会额外给出最近最常告警 task、blocker 和慢场景，并标出连续失败、重复 blocker、慢场景回归这三类阈值信号
- `agent_observe.py` 现在还会输出 `diagnostic_panel`，直接附带推荐复跑命令，优先按它给出的 task / scenario 命令复查
- 需要看最近几次 harness / evaluator / CI 结果时，用 `python3 scripts/agent_history.py --kind all --limit 5`
- 需要确认这次和上次相比哪里漂移时，用 `python3 scripts/agent_history.py --kind harness --diff`
- 新增事故、失败 run 或 evaluator 场景需要沉淀为 JSON 模板时，用 `python3 scripts/agent_scenario_scaffold.py --source latest --dry-run`；确认后再写入 `tests/harness_scenarios/<category>/`
- `agent_scenario_scaffold.py` 现在会自动推荐 `category / tags / budget / output`；如果失败来源是 `browser_smoke`、`workflow` 或 `harness`，也会直接生成对应 executor 模板，不再只适用于 `unittest`
- 需要把运行态观察和回归一起收口时，用 `python3 scripts/agent_harness.py --observe --profile auto`
- 需要在跑 runtime 测试前先做源码级权限/确认链路扫描时，用 `python3 scripts/agent_static_guardrails.py`
- 需要补静态资源、方案页交互和管理员中心入口的真实浏览器回归时，用 `python3 scripts/agent_browser_smoke.py --suite minimal`
- 如果要覆盖公开分享只读边界、登录前端视图、License 门禁前端视图、License 绑定成功切换、报告详情链路和配置中心页签切换，使用 `python3 scripts/agent_browser_smoke.py --suite extended`
- 如果要验证隔离运行态下的真实前后端联动链路，使用 `python3 scripts/agent_browser_smoke.py --suite live-minimal`
- 如果要在真实后端下继续覆盖报告详情、方案页和公开分享只读链路，使用 `python3 scripts/agent_browser_smoke.py --suite live-extended`
- browser smoke 是显式 opt-in 阶段；首次执行前先运行 `npm install`，再运行 `npx playwright install chromium chromium-headless-shell`
- PR 基础检查已统一收口到 `.github/workflows/pr-harness.yml`；其中 `pr-smoke` 负责脚本回归与 `static_guardrails`，`agent-smoke` 只跑 runtime smoke，`guardrails` 只跑 runtime guardrails
- 仓库内已提供独立的 browser smoke workflow：`.github/workflows/browser-smoke.yml`；当前会在前端相关 PR 改动时自动触发 `extended` 套件，并保留手动与周跑入口
- `pr-harness.yml`、`browser-smoke.yml` 与 `harness-nightly.yml` 现在会额外写 GitHub Step Summary，失败时不必先下载 artifact 才能看结论
- `pr-harness.yml` 现在会先识别变更路径；若 PR 未触及 runtime harness 相关目录，`agent-smoke` 与 `guardrails` 会直接写 `SKIPPED` 摘要，避免无效安装 `uv`
- `browser-smoke.yml` 与 `harness-nightly.yml` 现在会缓存 pip 与 Playwright 浏览器目录，nightly 还会在同一 ref 上自动取消重叠运行
- `--task` 会按任务画像自动选择 doctor 场景、guardrails/smoke 套件和 workflow 预演步骤
- `agent_workflow.py` 用于单独执行 task workflow；`--execute plan` 仅预演，`--execute preview` 执行安全步骤，`--execute full` 只在 `--allow-apply` 后才会真正覆盖高风险步骤
- `agent_harness.py --workflow-execute preview/full` 会把 workflow 执行结果并入 harness 阶段摘要和 artifact
- task workflow 里的 `unittest` 步骤会复用 `agent_test_runner.py`，与 `agent_smoke.py` / `agent_guardrails.py` 使用同一套 `uv run` 测试执行壳
- 高风险 workflow 步骤会额外校验 `confirmation_token`、`backup_dir` 和 `produces_artifact`；即使命令返回成功，只要约定工件缺失也会被判为失败
- 高风险 workflow 的 apply/rollback 现在还会强制校验治理字段；执行前补齐 `--task-var change_reason=... --task-var operator=... --task-var approver=... --task-var ticket=...`
- `ownership-migration`、`cloud-import`、`config-center` 这类 task 现在会先跑前置条件检查，例如目标账号存在、源目录存在、活跃 License 存在
- `license-audit` 属于只读 task，默认把 observe、License 状态脚本和专项回归收口到同一条审计链路
- `agent_harness.py` 默认包含 `static_guardrails -> guardrails -> smoke` 三层回归，其中 `static_guardrails` 负责源码级高风险路由扫描
- 需要把浏览器级 UI smoke 并入单入口摘要时，可显式追加 `--browser-smoke`
- `tests/harness_scenarios/browser/browser-smoke-live-minimal.json` 与 `tests/harness_scenarios/browser/browser-smoke-live-extended.json` 提供了 live browser smoke 的手动 evaluator 场景，可用 `python3 scripts/agent_eval.py --scenario browser-smoke-live-extended --artifact-dir artifacts/harness-eval` 验证
- `live-minimal` 仍定位为手动深回归，不进入 PR lane；PR 自动触发的是 mock 驱动的 `extended` 套件
- `tests/harness_scenarios/tenant/instance-scope-boundaries.json` 和 `tests/harness_scenarios/tenant/asset-ownership-boundaries.json` 用于单独跟踪实例隔离、资产归属、分享 owner 和导出资产元数据边界
- `agent_eval.py` 会从 `tests/harness_scenarios/**/*.json` 读取高价值场景语料，输出失败热点、慢场景和波动场景摘要
- 场景语料库当前共 16 条，已覆盖扩展 UI 浏览器回归、账号合并回滚、License 管理 workflow 预演、环境文件叠加解析、租户隔离和演示稿 sidecar 并发完整性
- `artifacts/harness-eval` 会写出 evaluator 的 `summary.json`、`progress.md`、`failure-summary.md`、`handoff.json`、每场景结果和 `latest.json`
- 两类 artifact 根目录下都会同步生成 `latest-progress.md`、`latest-failure-summary.md` 与 `latest-handoff.json`，便于直接交接
- PR 中的 `agent-smoke` 与 `guardrails` 会额外上传 CI artifact，便于直接下载对应的 `progress.md`、`failure-summary.md` 与 `handoff.json`
- 高风险 task 默认隐藏 apply/rollback 步骤；只有明确传入 `--allow-apply` 才会展示

常见专项测试：

- `python3 -m unittest tests.test_api_comprehensive`
- `python3 -m unittest tests.test_question_fast_strategy`
- `python3 -m unittest tests.test_security_regression`
- `python3 -m unittest tests.test_solution_payload`
- `python3 -m unittest tests.test_version_manager`
- `python3 -m unittest tests.test_config_template_consistency`

## 目录结构

```text
DeepVision/
├── web/                 # Web 服务、前端页面、静态资源与配置模板
├── resources/           # 内置场景资源
├── scripts/             # 启动、迁移、压测、版本管理等脚本
├── tests/               # 回归测试
├── docs/                # 配置、交付与专题文档
├── deploy/              # 部署示例（如 Nginx）
├── data/                # 运行期数据（会话、报告、摘要、鉴权、演示产物等）
├── .githooks/           # 仓库内 Git Hook
└── changes/             # 待发布变更碎片目录，首次生成碎片时自动创建
```

`data/` 下常见子目录包括：

- `data/sessions/`：访谈会话数据
- `data/reports/`：生成后的 Markdown 报告与分享映射；新报告文件名包含 `session_id` 以避免同日同主题碰撞
- `data/presentations/`：演示或导出相关产物
- `data/summaries/`：文档摘要缓存
- `data/auth/`：鉴权相关运行数据

## 常用脚本

- [scripts/start-production.sh](scripts/start-production.sh)：Gunicorn 生产启动包装脚本
- [scripts/start-local-dev.sh](scripts/start-local-dev.sh)：本地开发环境启动脚本（只读取 `web/.env.local`）
- [scripts/start-cloud-dev.sh](scripts/start-cloud-dev.sh)：云端联调环境启动脚本（只读取 `web/.env.cloud`）
- [scripts/run_gunicorn.py](scripts/run_gunicorn.py)：按 [web/server.py](web/server.py) 的 inline 依赖启动 Gunicorn
- [scripts/sync_object_storage_history.py](scripts/sync_object_storage_history.py)：手动补齐历史演示稿与运维归档到对象存储
- [scripts/install-hooks.sh](scripts/install-hooks.sh)：启用仓库内 Git Hook
- [scripts/version_manager.py](scripts/version_manager.py)：维护变更碎片与正式版本日志
- [scripts/loadtest_list_endpoints.py](scripts/loadtest_list_endpoints.py)：列表接口压测
- [scripts/admin_migrate_ownership.py](scripts/admin_migrate_ownership.py)：账号归属迁移
- [scripts/admin_ownership_service.py](scripts/admin_ownership_service.py)：归属迁移服务层，供 Web API 与 CLI 共用
- [scripts/license_manager.py](scripts/license_manager.py)：License 批量生成、查询、撤销、延期，以及运行时开关查看与切换
- [scripts/migrate_session_evidence_annotations.py](scripts/migrate_session_evidence_annotations.py)：历史数据迁移
- [scripts/replay_preflight_diagnostics.py](scripts/replay_preflight_diagnostics.py)：预检诊断重放

对象存储历史补迁移示例：

```bash
python3 scripts/sync_object_storage_history.py --env-file web/.env.cloud
python3 scripts/sync_object_storage_history.py --ops-archives --force
```

## 提交流程

- 首次拉取仓库后建议执行 `./scripts/install-hooks.sh`
- `post-commit` Hook 会调用 [scripts/version_manager.py](scripts/version_manager.py) 自动刷新 `changes/unreleased/*.json`
- 正式版本号与历史日志维护在 [web/version.json](web/version.json)
- 合入主分支后，GitHub Actions 会聚合待发布碎片并更新正式版本

本地预览版本变更可执行：

```bash
python3 scripts/version_manager.py fragment --dry-run
python3 scripts/version_manager.py release --dry-run
```

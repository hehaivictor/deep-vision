# DeepVision

DeepVision 是一个面向需求访谈、方案沉淀与交付输出的 AI Web 应用。系统覆盖「发起访谈 -> 沉淀记录 -> 生成报告 -> 派生方案页 -> 导出与分享」的完整链路，适合需求调研、售前咨询、业务诊断与方案澄清场景。

当前版本：`4.0.0`（`2026-03-17`，见 [web/version.json](web/version.json)）

## 核心能力

- 智能访谈：按场景驱动问题生成，支持追问、进度推进、会话持久化
- 资料输入：支持 `md`、`txt`、`pdf`、`docx`、`xlsx`、`pptx` 上传并转为可引用内容
- 报告生成：异步队列化生成、状态轮询、质量门控、证据索引
- 方案页输出：从报告派生结构化方案页，支持匿名只读分享链接
- 导出能力：支持 Markdown、Word、PDF、附录 PDF
- 鉴权能力：手机号验证码登录（`mock` / 京东云短信），支持可选微信扫码登录
- 场景管理：内置场景 + 自定义场景，支持目录化加载
- 稳定性优化：分页、ETag/304、429 快速失败、缓存与预热

## 技术结构

- 后端：Flask 单文件主服务 [web/server.py](web/server.py)
- 前端：原生 HTML / CSS / JavaScript，主入口为 [web/index.html](web/index.html) 与 [web/app.js](web/app.js)
- 方案页：独立入口 [web/solution.html](web/solution.html)、[web/solution.js](web/solution.js)、[web/solution.css](web/solution.css)
- 生产运行：Gunicorn + [web/wsgi.py](web/wsgi.py)
- 依赖管理：使用 `uv run` 直接读取 [web/server.py](web/server.py) 顶部的 inline dependency metadata

## 快速开始

### 1. 环境要求

- Python `>= 3.10`
- 安装 [uv](https://docs.astral.sh/uv/)

### 2. 准备配置

```bash
cp web/.env.example web/.env
```

如需使用 Python 配置文件兜底，也可以执行：

```bash
cp web/config.example.py web/config.py
```

配置优先建议：

- 优先把真实密钥、模型路由、超时和运行参数写入 `web/.env`
- `web/config.py` 更适合本地开发兜底
- 默认 `CONFIG_RESOLUTION_MODE=auto`

可参考：

- [web/.env.example](web/.env.example)
- [web/config.example.py](web/config.example.py)
- [web/CONFIG.md](web/CONFIG.md)（仅说明 `site-config.js` 前端展示配置）
- [docs/instance-scope.md](docs/instance-scope.md)

### 3. 启动开发环境

```bash
uv run web/server.py
```

默认访问地址：

```text
http://127.0.0.1:5001
```

说明：

- 首次运行时，`uv` 会按 [web/server.py](web/server.py) 顶部声明自动准备依赖
- 如果要显式指定环境文件，可使用 `DEEPVISION_ENV_FILE=/path/to/.env uv run web/server.py`

## 生产启动

### 方式一：使用脚本

```bash
./scripts/start-production.sh
```

### 方式二：直接运行 Gunicorn

```bash
uv run --with gunicorn gunicorn -c web/gunicorn.conf.py web.wsgi:app
```

说明：

- Gunicorn 运行参数由 [web/gunicorn.conf.py](web/gunicorn.conf.py) 从进程环境变量读取
- 如果只改 `web/config.py`，Gunicorn 相关参数不会自动生效
- Nginx 示例配置见 [deploy/nginx/deepvision.conf.example](deploy/nginx/deepvision.conf.example)
- 生产环境启动前会校验关键安全配置；`SECRET_KEY` 为模板占位值、`INSTANCE_SCOPE_KEY` 为空或 `SMS_PROVIDER=mock` 时会拒绝启动

## 关键配置项

配置模板以 [web/.env.example](web/.env.example) 为准，常用项如下：

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

如果当前阶段仍使用 `mock` 短信登录，建议在 [web/.env](web/.env) 中显式配置：

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
- 变更 `web/.env` 后需要重启服务进程；已登录的旧会话如未刷新权限，重新登录一次即可
- 使用固定测试码意味着“知道站点地址的人都可能尝试任意手机号登录”，因此演示环境不要直接暴露到公网

## 运维接口

当前运维接口以 JSON API 形式提供，前端没有独立管理页面：

- `GET /api/metrics`：查看接口性能指标、列表接口统计和报告生成队列状态
- `POST /api/metrics/reset`：清空性能指标历史
- `GET /api/summaries`：查看文档摘要缓存数量、大小和开关状态
- `POST /api/summaries/clear`：清空文档摘要缓存，不会删除会话或报告正文

权限说明：

- 以上接口仅对白名单管理员开放
- 如果当前项目没有正式管理员角色，内测阶段可临时把演示手机号写入 `ADMIN_PHONE_NUMBERS`

## 测试

运行全量回归：

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

常见专项测试：

- `python3 -m unittest tests.test_api_comprehensive`
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

- [scripts/start-production.sh](scripts/start-production.sh)：Gunicorn 生产启动
- [scripts/install-hooks.sh](scripts/install-hooks.sh)：启用仓库内 Git Hook
- [scripts/version_manager.py](scripts/version_manager.py)：维护变更碎片与正式版本日志
- [scripts/loadtest_list_endpoints.py](scripts/loadtest_list_endpoints.py)：列表接口压测
- [scripts/admin_migrate_ownership.py](scripts/admin_migrate_ownership.py)：账号归属迁移
- [scripts/migrate_session_evidence_annotations.py](scripts/migrate_session_evidence_annotations.py)：历史数据迁移
- [scripts/replay_preflight_diagnostics.py](scripts/replay_preflight_diagnostics.py)：预检诊断重放

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

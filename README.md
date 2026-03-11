# DeepVision

DeepVision 是一个面向需求访谈场景的 AI Web 应用，支持从访谈提问、回答沉淀到报告生成与导出的完整链路。

当前版本：`2.7.0`（见 [web/version.json](web/version.json)）

## 核心能力

- 账号体系：手机号验证码登录（`mock` / 京东云短信），支持微信扫码登录（可选）
- 智能访谈：按场景驱动多维度提问，支持追问、进度推进、会话持久化
- 场景管理：内置场景 + 自定义场景，兼容历史目录迁移
- 报告生成：支持异步队列化生成、状态轮询、过载保护
- 报告导出：支持 Markdown、DOCX、附录 PDF 导出
- 并发优化：列表分页、ETag/304、429 快速失败、元数据索引回退机制

## 技术栈

- 后端：Flask（单文件主服务 [web/server.py](web/server.py)）
- 前端：原生 HTML/CSS/JS（`web/index.html` + `web/app.js`）
- 运行方式：`uv run`（开发）/ Gunicorn（生产）

## 快速开始（开发）

### 1) 准备环境

- Python `>= 3.10`
- 安装 [uv](https://docs.astral.sh/uv/)

### 2) 配置

```bash
cp web/config.example.py web/config.py
```

按需修改 [web/config.py](web/config.py)（本地文件，不入库）。

### 3) 启动

```bash
uv run web/server.py
```

默认访问：`http://localhost:5001`

## 生产启动

### 方式一：启动脚本

```bash
./scripts/start-production.sh
```

### 方式二：直接 Gunicorn

```bash
uv run --with gunicorn gunicorn -c web/gunicorn.conf.py web.wsgi:app
```

可参考 Nginx 示例配置：
[deploy/nginx/deepvision.conf.example](deploy/nginx/deepvision.conf.example)

## 关键配置项

配置示例见 [web/config.example.py](web/config.example.py)。

- AI 与模型：
  - `ENABLE_AI`
  - `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL`
  - `QUESTION_MODEL_NAME` / `REPORT_MODEL_NAME`
- 鉴权：
  - `SECRET_KEY`
  - `SMS_PROVIDER`（`mock`/`jdcloud`）
  - `SMS_TEST_CODE`（仅测试环境）
- 并发与性能：
  - `LIST_API_DEFAULT_PAGE_SIZE` / `LIST_API_MAX_PAGE_SIZE`
  - `SESSIONS_LIST_MAX_INFLIGHT` / `REPORTS_LIST_MAX_INFLIGHT`
  - `REPORT_GENERATION_MAX_WORKERS` / `REPORT_GENERATION_MAX_PENDING`
- 场景目录：
  - `BUILTIN_SCENARIOS_DIR`
  - `CUSTOM_SCENARIOS_DIR`
- 多实例隔离：
  - `INSTANCE_SCOPE_KEY`（规范见 [docs/instance-scope.md](docs/instance-scope.md)）

## 测试

```bash
python3 -m unittest tests.test_api_comprehensive
python3 -m unittest tests.test_security_regression
python3 -m unittest tests.test_scripts_comprehensive
```

## 目录结构

```text
DeepVision/
├── web/                 # 前后端主程序与静态资源
├── scripts/             # 运维/迁移/压测等脚本
├── resources/           # 内置场景资源
├── tests/               # 回归测试
├── deploy/              # 部署示例（Nginx）
├── docs/                # 运维与配置文档
└── data/                # 运行时数据目录（已忽略，不入库）
```

## 常用脚本

- [scripts/admin_migrate_ownership.py](scripts/admin_migrate_ownership.py)：账号归属迁移
- [scripts/loadtest_list_endpoints.py](scripts/loadtest_list_endpoints.py)：列表接口压测
- [scripts/version_manager.py](scripts/version_manager.py)：版本号与变更记录维护
- [scripts/install-hooks.sh](scripts/install-hooks.sh)：安装仓库内 Git Hook，统一按钮提交与命令行提交后的版本日志生成

## 提交流程建议

- 首次拉取仓库后执行 `./scripts/install-hooks.sh`，将 Git Hook 固定到仓库内的 `.githooks/`。
- 提交信息如果本身规范，更新日志会优先沿用提交标题与正文。
- 即使点击客户端的“提交”按钮只填写了简短标题，`post-commit` 也会根据本次改动文件自动整理出结构化更新日志，避免版本历史出现脏标题或重复单条。

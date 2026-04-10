# Web 局部入口

这个目录承载 DeepVision 的后端入口、前端入口和共享静态资源。

## 先看什么

- 仓库总入口：[../AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)
- 物理地图：[../ARCHITECTURE.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/ARCHITECTURE.md)
- 领域索引：[../docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)

## 目录职责

- `server.py` / `wsgi.py` / `gunicorn.conf.py`：后端入口与生产运行参数
- `server_modules/`：后端 runtime / service 抽离层
- `app.js` / `app_modules/`：前端主应用编排与状态层
- `solution.*`：方案页入口
- `help.html` / `intro.html`：帮助与引导页
- `config.py` / `site-config.js`：配置默认值与前端展示配置

## 局部边界

- 这里仍是 brownfield 目录，但优先把新逻辑放到 `server_modules/` 或 `app_modules/`，不要继续把 `server.py` / `app.js` 堆得更厚
- 不要默认修改 `.env.local`、`.env.cloud`、`.env.production`，除非用户明确要求
- 不要让前端模块依赖 Python runtime 细节，也不要让后端业务代码反向依赖 `scripts/agent_*`
- 配置中心相关改动优先委托 helper / service，不要在路由层直接写配置文件

## 改动后先跑

- 后端聚合检查：`python3 scripts/agent_harness.py --profile auto`
- 源码级静态 guardrail：`python3 scripts/agent_static_guardrails.py`
- 前端浏览器回归：`python3 scripts/agent_browser_smoke.py --suite extended`

## 继续下钻

- 改后端 runtime / service：看 [server_modules/AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/AGENTS.md)
- 改前端状态 / 页面编排：看 [app_modules/AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/AGENTS.md)

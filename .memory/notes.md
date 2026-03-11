# Notes: DeepVision 全面审查

## 基线
- `web/server.py`：21208 行
- `web/app.js`：8760 行
- 现有测试：100 项，失败 1 项
- 基线命令：`python3 -m unittest tests.test_security_regression tests.test_api_comprehensive tests.test_scripts_comprehensive tests.test_question_fast_strategy tests.test_solution_payload`

## 关键证据

### 1. 生效配置存在高危登录绕过组合
- `web/config.py:146` `SMS_PROVIDER = "mock"`
- `web/config.py:154` `SMS_TEST_CODE = "111111"`
- `web/server.py:3288`-`web/server.py:3292` 固定验证码直接生效
- `web/server.py:3345`-`web/server.py:3349` mock 短信直接返回成功，不走真实短信
- `web/server.py:3410`-`web/server.py:3444` 发码后把固定验证码写入校验库
- 脱敏验证：随机手机号 `send-code=200`，随后用 `111111` 登录 `200`

### 2. 会话硬化与运行模式不安全
- `web/config.py:137` `DEBUG_MODE = True`
- `web/config.py:141` `SECRET_KEY = "replace-with-a-strong-random-secret"`
- `web/server.py:1239`-`web/server.py:1252` 直接使用配置中的 `SECRET_KEY`，并在 `DEBUG_MODE=True` 时关闭 `SESSION_COOKIE_SECURE`

### 3. Mermaid 渲染链路存在潜在 DOM XSS 面
- `web/index.html:236` `securityLevel: 'loose'`
- `web/index.html:240` 附近 `htmlLabels: true`
- `web/app.js:6753`-`web/app.js:6808` Markdown HTML 有白名单清洗
- `web/app.js:6915`-`web/app.js:7035` Mermaid 定义经处理后直接 `element.innerHTML = svg`

### 4. 配置与测试存在漂移
- `web/server.py:774` `REPORT_V3_QUALITY_FORCE_SINGLE_LANE` fallback 是 `True`
- `tests/test_security_regression.py:647` 断言 quality 默认必须为 `True`
- `web/.env:60`、`web/config.py:68`、`web/.env.example:81`、`web/config.example.py:75` 实际示例/生效值均为 `false`

### 5. Gunicorn 配置面存在“死配置”
- `web/config.example.py:162`-`web/config.example.py:168` 暴露 `GUNICORN_*`
- `web/gunicorn.conf.py:42`-`web/gunicorn.conf.py:58` 仅从进程环境读取，不读取 `web/config.py`

### 6. 配置优先级与双源混用
- `web/server.py:75`-`web/server.py:109` 自动加载 `web/.env`
- `web/server.py:174`-`web/server.py:188` 读取优先级：`DEEPVISION_*` > 同名环境变量 > `config.py` > 默认值
- 实际运行为混合来源：`.env` 覆盖部分项，其余继续从 `web/config.py` 回填

### 7. 上传转换链路无 timeout
- `web/server.py:17125`-`web/server.py:17131` `subprocess.run([...])` 未设置 `timeout`

## 已验证的保护项
- `web/solution.js:4`-`web/solution.js:10` 存在 `solutionEscapeHtml`
- `web/solution.js:42`-`web/solution.js:45` 方案页关键状态文案经过转义
- `web/server.py:13950`-`web/server.py:13971` 静态文件路由做了路径穿越校验
- `tests/test_security_regression.py` 覆盖匿名写接口、报告归属、状态最小暴露等回归

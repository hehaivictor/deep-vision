# DeepVision 参数配置与代码风险审计报告

审计日期：2026-03-11  
审计范围：后端、前端、脚本、部署参数、示例配置、文档，以及当前工作区生效配置（脱敏）  
审计方式：只读审查 + 定向验证 + 基线测试

## 执行摘要

本次审查确认 DeepVision 当前工作区存在 **1 个 P0、3 个 P1、4 个 P2、2 个 P3** 级别问题，其中最紧急的是：

1. **当前生效配置启用了 mock 短信并固定验证码，可直接绕过真实手机号验证登录任意手机号账号。**
2. **运行模式仍处于 `DEBUG_MODE=true`，会话密钥使用占位字符串，Session Cookie 未强制 Secure。**
3. **工作区同时存在真实外部服务凭据与双源配置混用，导致安全参数和运行参数容易“半来自 `.env`、半来自 `config.py`”。**

基线验证结果：

- 全量回归命令：`python3 -m unittest tests.test_security_regression tests.test_api_comprehensive tests.test_scripts_comprehensive tests.test_question_fast_strategy tests.test_solution_payload`
- 结果：**100 项测试，1 项失败**
- 失败项：`tests.test_security_regression.SecurityRegressionTests.test_report_v3_runtime_quality_single_lane_defaults`
- 直接原因：`REPORT_V3_QUALITY_FORCE_SINGLE_LANE` 的实现 fallback、测试预期、示例配置和当前生效配置互相漂移。

## 立即关注项

### 1. 立即止血：关闭 mock 短信与固定验证码
- 当前生效配置中，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:146` 为 `SMS_PROVIDER = "mock"`
- 当前生效配置中，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:154` 为 `SMS_TEST_CODE = "111111"`
- 运行逻辑中，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:3288` 会优先采用固定测试验证码，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:3345` 在 `mock` 模式下直接视为“发码成功”，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:3410` 则把该验证码写入校验库。
- 脱敏验证结果：随机手机号先调用 `/api/auth/sms/send-code` 返回 `200`，随后使用固定验证码 `111111` 调用 `/api/auth/login/code` 返回 `200`。

### 2. 立即止血：切出开发模式并更换会话密钥
- 生效配置中，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:137` 仍为 `DEBUG_MODE = True`
- 生效配置中，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:141` 仍为占位符 `SECRET_KEY`
- 运行逻辑中，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:1239` 会直接采用该值，`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:1252` 会在 `DEBUG_MODE=true` 时关闭 `SESSION_COOKIE_SECURE`

### 3. 立即止血：轮换工作区内所有真实凭据
- 当前工作区的 `web/.env` 与 `web/config.py` 中均检测到真实 API 凭据/业务秘钥配置。
- 这些值虽然未被 Git 跟踪，但已是**明文落盘**状态，且在导入 `server.py` 时会触发客户端初始化与连通性测试。
- 证据：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:5618`-`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:5678`

## 风险清单

### P0

#### P0-1 模拟短信 + 固定验证码导致任意手机号账号登录/注册
- **问题描述**：当前生效配置启用了 `mock` 短信通道，并设置了固定验证码。攻击者无需控制真实手机号，即可对任意手机号发起验证码发送，再用固定验证码完成登录；对于不存在的手机号，系统还会自动创建新账号。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:146`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:154`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:3288`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:3345`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:3410`
- **影响面**：登录体系、账号归属、会话/报告访问边界、后续微信绑定链路。
- **触发条件/利用场景**：公开访问者只需两次接口调用：先发码，再用固定验证码登录。
- **建议修复方向**：生产环境强制 `SMS_PROVIDER=jdcloud` 或其他真实短信网关；生产环境禁止设置 `SMS_TEST_CODE`；启动阶段增加 hard-fail 校验，检测到 `mock`/固定验证码直接拒绝启动。
- **建议优先级**：立即修复。
- **是否属于立即止血**：是。

### P1

#### P1-1 生产仍以开发模式运行，会话密钥使用占位值，Session Cookie 未强制 Secure
- **问题描述**：当前生效配置显示服务仍处于开发模式，且会话密钥为占位字符串而非强随机值。服务端直接采用该值，并据此关闭 `SESSION_COOKIE_SECURE`。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:137`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:141`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:1237`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:1249`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:1252`
- **影响面**：会话签名可信度、Cookie 传输安全、环境区分与运维基线。
- **触发条件/利用场景**：当前配置直接触发；一旦存在中间人、误用 HTTP、会话签名被复制或配置泄露，会扩大会话风险。
- **建议修复方向**：生产强制 `DEBUG_MODE=false`；只接受高熵 `SECRET_KEY`；将 `SESSION_COOKIE_SECURE=True` 作为生产 hard-fail 条件。
- **建议优先级**：高。
- **是否属于立即止血**：是。

#### P1-2 工作区存在真实凭据落盘，且模块导入即主动初始化外部客户端
- **问题描述**：当前工作区中 `web/.env` 与 `web/config.py` 都存在真实外部服务凭据。与此同时，`server.py` 在模块加载阶段就会初始化多个网关客户端并执行连接测试，放大了凭据误用、日志暴露和误触真实外部服务的风险。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:75`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:174`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:5618`-`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:5678`
- **影响面**：凭据治理、开发/测试隔离、CI/脚本导入副作用、第三方调用成本与审计面。
- **触发条件/利用场景**：任何直接导入 `server.py` 的脚本、交互式检查、错误用法都可能触发真实外部连接。
- **建议修复方向**：生产只允许环境变量注入敏感值；禁止 `web/config.py` 与 `web/.env` 同时承载真实凭据；将外部客户端初始化延后到显式启动流程或首用时；默认关闭连接测试。
- **建议优先级**：高。
- **是否属于立即止血**：是。

#### P1-3 安全关键参数存在双源回填，真实运行状态不透明
- **问题描述**：配置优先级为 `DEEPVISION_*` > 同名环境变量 > `config.py` > 默认值，而 `web/.env` 只定义了部分参数，缺省项会继续由 `web/config.py` 回填，造成“部分来自 `.env`、部分来自 `config.py`”的混合运行状态。当前高危项 `DEBUG_MODE`、`SECRET_KEY`、`SMS_PROVIDER`、`SMS_TEST_CODE` 就由 `config.py` 生效。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:75`-`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:109`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:174`-`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:188`
- **影响面**：安全参数治理、故障定位、环境一致性、文档可信度。
- **触发条件/利用场景**：`.env` 漏写一个键，服务就会静默回落到 `config.py`；运维难以通过单一文件判断真实运行状态。
- **建议修复方向**：生产模式统一为环境变量单源；对安全参数采用白名单校验并输出来源日志；禁止 `config.py` 在生产生效。
- **建议优先级**：高。
- **是否属于立即止血**：否，但应紧随 P0 处理。

### P2

#### P2-1 Mermaid 以 loose 模式运行，并把图表 SVG 直接写入 `innerHTML`
- **问题描述**：报告 Markdown 渲染链路本身已有白名单清洗，但 Mermaid 图表渲染绕过了这层清洗：前端将图表定义送入 Mermaid，在 `securityLevel: 'loose'` 且 `htmlLabels: true` 的配置下生成 SVG，再直接写入 `innerHTML`。这会形成一条潜在的 DOM XSS 面，尤其是当报告内容、上传文档或外部来源可影响 Mermaid 定义时。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/index.html:236`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js:6753`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js:6881`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js:6915`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js:7035`
- **影响面**：报告查看页、导出流程、前端执行上下文。
- **触发条件/利用场景**：攻击者能够影响报告中的 Mermaid 图表定义，且 Mermaid 在 loose 模式下输出含危险行为的 SVG/HTML。
- **建议修复方向**：将 Mermaid 切换到 `strict`/更安全模式；关闭 `htmlLabels`；在插入 SVG 前做二次净化；为 Mermaid 图表增加针对性安全回归。
- **建议优先级**：中高。
- **是否属于立即止血**：否。

#### P2-2 文档转换子进程没有 timeout，存在可用性与资源耗尽风险
- **问题描述**：上传的 Office/PDF 文档会触发子进程转换，但 `subprocess.run()` 未设置 `timeout`，异常文档或外部转换工具卡死时可能占满线程或拖垮请求处理。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:17125`-`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:17131`
- **影响面**：上传接口、线程池占用、服务可用性。
- **触发条件/利用场景**：上传畸形或复杂文档，触发转换器长时间阻塞。
- **建议修复方向**：给转换子进程设置 timeout；超时后清理临时文件并返回可恢复错误；为上传链路增加负载保护与观测指标。
- **建议优先级**：中。
- **是否属于立即止血**：否。

#### P2-3 `REPORT_V3_QUALITY_FORCE_SINGLE_LANE` 默认策略与测试/示例/生效配置相互漂移
- **问题描述**：运行时代码在未配置时默认认为 quality 档应强制单 lane，但测试也依赖该默认；然而示例配置和当前生效配置又显式设置为 `false`。结果是：在真实配置下测试失败，线上行为也不再体现代码作者和测试所表达的默认策略。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:774`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py:647`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/.env:60`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py:68`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/.env.example:81`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.example.py:75`
- **影响面**：报告质量策略、测试可信度、配置文档可信度。
- **触发条件/利用场景**：只要带着当前 `.env`/`config.py` 运行，quality 档行为就会偏离测试预期。
- **建议修复方向**：统一默认策略来源；要么修改测试与文档，要么修改示例和运行配置；禁止关键策略出现“三套默认”。
- **建议优先级**：中。
- **是否属于立即止血**：否。

#### P2-4 Gunicorn 参数在示例配置中可写，但生产启动路径实际上并不读取这些值
- **问题描述**：`web/config.example.py` 与 `web/config.py` 暴露了 `GUNICORN_*` 参数，看起来像可配置项；但 `web/gunicorn.conf.py` 只从进程环境读取，不读取 `config.py`。这会导致运维误以为改了配置文件就已生效，实际并没有。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.example.py:162`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/gunicorn.conf.py:42`-`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/gunicorn.conf.py:58`
- **影响面**：生产并发、超时、日志、线程数、资源评估。
- **触发条件/利用场景**：运维仅修改 `config.py` 或示例配置，不导出环境变量。
- **建议修复方向**：统一 Gunicorn 配置入口；要么让 `gunicorn.conf.py` 复用同一配置解析器，要么从示例配置中移除这些“死配置”。
- **建议优先级**：中。
- **是否属于立即止血**：否。

### P3

#### P3-1 CORS 当前对任意 Origin 反射放行，虽未开启凭据但边界过宽
- **问题描述**：服务直接调用 `CORS(app)`，实际响应会对请求 Origin 进行反射，未见显式白名单控制。当前未开启 `Access-Control-Allow-Credentials`，因此风险尚未升级为跨站带凭据读取，但匿名接口已默认可被任意站点跨域调用。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:1234`
- **影响面**：匿名接口边界、未来敏感接口演进风险。
- **触发条件/利用场景**：任意第三方站点均可在浏览器中直接读取匿名可见接口。
- **建议修复方向**：引入显式 Origin 白名单；区分匿名只读接口与鉴权接口；为 CORS 策略加回归测试。
- **建议优先级**：低到中。
- **是否属于立即止血**：否。

#### P3-2 后端单文件过大，前端缺少自动化安全回归，长期维护风险高
- **问题描述**：`server.py` 已超过 2.1 万行，承载配置、鉴权、会话、报告、导出、第三方集成等多种职责；当前自动化测试主要集中在 Python 后端，未见前端安全/渲染回归测试，导致很多 DOM/渲染链路依赖人工审查。
- **证据位置**：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:1`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js:1`、`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py:1`
- **影响面**：变更风险、测试覆盖、故障定位效率。
- **触发条件/利用场景**：功能继续叠加时，跨模块副作用更难发现；前端渲染安全问题容易回归。
- **建议修复方向**：分拆后端模块；把配置、鉴权、报告、导出和第三方客户端拆开；增加前端渲染与 XSS 回归测试。
- **建议优先级**：低。
- **是否属于立即止血**：否。

## 参数矩阵（关键项，脱敏）

| 参数 | 当前生效状态 | 实际来源 | 代码默认/说明 | 风险级别 | 文档/实现漂移 |
|---|---|---|---|---|---|
| `SECRET_KEY` | 已配置，但为占位值 | `web/config.py` | `server.py` 直接采用 | P1 | 文档要求强随机，当前不是 |
| `DEBUG_MODE` | `true` | `web/config.py` | 影响 Cookie Secure 等 | P1 | 示例默认也为 `true`，不适合作生产模板 |
| `SMS_PROVIDER` | `mock` | `web/config.py` | 默认即 `mock` | P0 | 生产环境高风险 |
| `SMS_TEST_CODE` | 已配置 | `web/config.py` | 未配置时才随机生成 | P0 | 示例为空，但实际生效非空 |
| `WECHAT_LOGIN_ENABLED` | `true` | `web/.env` | 默认 `false` | P2 | 与 `config.py` 同时存在配置 |
| `INSTANCE_SCOPE_KEY` | 已配置 | `web/.env` / `web/config.py` | 默认空 | 低 | 文档基本一致 |
| `ENABLE_WEB_SEARCH` | `true` | `web/.env` | 默认 `false` | P2 | 功能开启与成本/隐私边界需评估 |
| `REPORT_V3_QUALITY_FORCE_SINGLE_LANE` | `false` | `web/.env` | 运行时代码 fallback 为 `true` | P2 | 测试/示例/生效配置不一致 |
| `GUNICORN_*` | 配置文件中有值，但实际未见统一生效 | `web/config.py` / 示例文件 | `gunicorn.conf.py` 只读进程环境 | P2 | 存在“死配置” |
| `QUESTION/REPORT/SUMMARY/SEARCH_DECISION API Key` | 全部已配置 | `web/.env` / `web/config.py` | 无安全默认 | P1 | 明文落盘且分散 |
| `ZHIPU_API_KEY` | 已配置 | `web/.env` / `web/config.py` | 无安全默认 | P1 | 明文落盘 |
| `REFLY_API_KEY` | 已配置 | `web/.env` / `web/config.py` | 无安全默认 | P1 | 明文落盘 |

## 实现 / 文档 / 测试漂移清单

1. **`REPORT_V3_QUALITY_FORCE_SINGLE_LANE` 三套默认**
   - 代码 fallback：`true`
   - 测试预期：`true`
   - 示例/当前生效配置：`false`

2. **Gunicorn 配置入口不一致**
   - 示例配置文件暴露 `GUNICORN_*`
   - 实际 Gunicorn 仅读进程环境，不读 `config.py`

3. **安全相关示例默认过于宽松**
   - `DEBUG_MODE=true`
   - `SMS_PROVIDER=mock`
   - `SECRET_KEY=replace-with-a-strong-random-secret`
   - 这些值适合作本地开发示例，不适合作生产模板直接沿用

4. **配置源混用导致真实状态不透明**
   - `web/.env` 与 `web/config.py` 同时存在
   - `.env` 缺失的键会静默回填到 `config.py`

5. **模块导入存在外部网络副作用**
   - 导入 `server.py` 即可能初始化并探测多个外部网关

## 已验证的保护项

- `sanitizeMarkdownHtml()` 已对 Markdown HTML 做基础白名单清洗：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js:6753`
- 方案页多数动态插值经过 `solutionEscapeHtml()` 转义：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.js:4`
- 静态文件路由有路径穿越防护：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py:13950`
- 现有安全回归已覆盖匿名写接口、归属校验、匿名状态最小暴露等核心边界：`/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py:1`

## 优先修复顺序

### 第一批：当天完成
- 关闭 `mock` 短信
- 清空 `SMS_TEST_CODE`
- 将 `DEBUG_MODE` 置为 `false`
- 配置强随机 `SECRET_KEY`
- 轮换当前工作区已落盘的所有真实凭据
- 复核当前线上/预发实例是否已被以上配置影响

### 第二批：1-2 天内完成
- 统一生产配置入口，只保留环境变量单源
- 修正 `REPORT_V3_QUALITY_FORCE_SINGLE_LANE` 的默认策略与测试、示例配置
- 让 Gunicorn 与应用共用同一套配置解析逻辑，或移除死配置
- 为文档转换子进程增加 timeout 与异常清理
- 收紧 Mermaid 安全模式并补充针对性回归

### 第三批：1-2 周内完成
- 按职责拆分 `server.py`
- 将第三方客户端初始化从模块导入阶段移出
- 增加前端渲染/XSS/导出链路自动化测试
- 收敛配置文档，只保留一套“开发模板”和一套“生产模板”

## 后续可能需要调整的公开契约

- 生产环境是否强制只接受环境变量注入敏感参数
- Gunicorn 配置是否统一并入 DeepVision 主配置解析器
- Mermaid 图表是否需要降级安全能力以换取前端安全
- `REPORT_V3_QUALITY_FORCE_SINGLE_LANE` 的官方默认策略应以代码、测试还是示例配置为准

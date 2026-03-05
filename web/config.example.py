"""
Deep Vision 配置文件示例

使用说明：
1. 复制此文件并重命名为 config.py
2. 填入实际的 API Key 和其他配置值
3. config.py 已被添加到 .gitignore，不会被提交到版本控制

注意：请勿在此示例文件中填入真实的 API Key！
"""

# ============ 大模型 API 配置 ============

# Anthropic API 配置
# 从环境变量获取或直接填入（不推荐直接填入，建议使用环境变量）
ANTHROPIC_API_KEY = "your-anthropic-api-key-here"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"  # 或使用代理地址

# 模型配置
MODEL_NAME = "claude-sonnet-4-20250514"  # 可选: claude-3-opus, claude-3-sonnet, claude-3-haiku
# 可选：将问题生成与报告生成拆分为不同模型（默认均使用 MODEL_NAME）
QUESTION_MODEL_NAME = MODEL_NAME
REPORT_MODEL_NAME = MODEL_NAME
# 可选：将摘要与搜索决策拆分为独立模型（默认跟随 QUESTION_MODEL_NAME）
SUMMARY_MODEL_NAME = QUESTION_MODEL_NAME
SEARCH_DECISION_MODEL_NAME = SUMMARY_MODEL_NAME

# 可选：将问题与报告拆分到不同网关（未配置时回落到 ANTHROPIC_API_KEY/ANTHROPIC_BASE_URL）
# 例如：问答走 GLM Anthropic 兼容，报告走 Claude 官方或代理
QUESTION_API_KEY = ""
QUESTION_BASE_URL = ""
REPORT_API_KEY = ""
REPORT_BASE_URL = ""

# 可选：将摘要与搜索决策拆分到独立网关（未配置时回落到报告/问题网关）
SUMMARY_API_KEY = ""
SUMMARY_BASE_URL = ""
SEARCH_DECISION_API_KEY = ""
SEARCH_DECISION_BASE_URL = ""

# 可选：按通道配置 Bearer 鉴权（aicodemirror 建议开启）
SUMMARY_USE_BEARER_AUTH = False
SEARCH_DECISION_USE_BEARER_AUTH = False

# Token 限制配置（与 server.py 默认值保持一致）
MAX_TOKENS_DEFAULT = 5000      # 默认最大 token 数
MAX_TOKENS_QUESTION = 2000     # 生成问题时的最大 token 数
MAX_TOKENS_REPORT = 10000      # 生成报告时的最大 token 数
MAX_TOKENS_SUMMARY = 500       # 文档摘要生成最大 token 数

# AI 运行策略配置（建议统一在此调整）
API_TIMEOUT = 90.0             # 通用 API 超时（秒）
REPORT_API_TIMEOUT = 210.0     # 报告生成专用超时（秒）
REPORT_DRAFT_API_TIMEOUT = 180.0              # 报告草案阶段专用超时（秒，建议 <= REPORT_API_TIMEOUT）
REPORT_V3_DRAFT_MAX_TOKENS = 5500             # 报告 V3 草案单次输出 token 上限
REPORT_V3_DRAFT_FACTS_LIMIT = 48              # 报告 V3 草案引用的证据问答上限
REPORT_V3_DRAFT_MIN_FACTS_LIMIT = 24          # 降载重试时最少保留的证据问答数
REPORT_V3_DRAFT_RETRY_COUNT = 2               # 报告 V3 草案失败后的额外重试次数
REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS = 1.5   # 报告 V3 草案重试退避时间（秒）
REPORT_V3_FAILOVER_ENABLED = True             # V3 主网关失败后是否切备用网关再试一次
REPORT_V3_FAILOVER_LANE = "question"          # 备用网关 lane: question/report
CONTEXT_WINDOW_SIZE = 5        # 保留最近 N 条问答
SUMMARY_THRESHOLD = 8          # 超过此数量触发历史摘要
SUMMARY_UPDATE_DEBOUNCE_SECONDS = 60  # 摘要异步更新最小间隔（秒）
SEARCH_DECISION_CACHE_TTL_SECONDS = 600  # 搜索决策缓存有效期（秒）
SEARCH_DECISION_CACHE_MAX_ENTRIES = 256  # 搜索决策缓存条目上限
SEARCH_DECISION_INFLIGHT_WAIT_SECONDS = 10.0  # 并发同决策请求等待首个结果的最长时间（秒）
SEARCH_RESULT_CACHE_TTL_SECONDS = 300  # 搜索结果缓存有效期（秒）
SEARCH_RESULT_CACHE_MAX_ENTRIES = 128  # 搜索结果缓存条目上限
SEARCH_RESULT_INFLIGHT_WAIT_SECONDS = 12.0  # 并发同查询等待首个结果的最长时间（秒）
PREFETCH_IDLE_ONLY = True  # 仅在主链路空闲时触发预生成
PREFETCH_IDLE_MAX_LOW_RUNNING = 0  # 触发预生成时允许的低优先级并发数上限
PREFETCH_IDLE_WAIT_SECONDS = 8.0  # 预生成等待空闲的最长时间（秒）
FIRST_QUESTION_PREFETCH_PRIORITY_ENABLED = True  # 新会话首题预生成优先窗口开关
FIRST_QUESTION_PREFETCH_PRIORITY_WINDOW_SECONDS = 120.0  # 首题预生成优先窗口时长（秒）
QUESTION_FAST_PATH_ENABLED = True  # 问题生成启用快档+兜底双档策略
QUESTION_FAST_TIMEOUT = 20.0  # 问题生成快档超时（秒）
QUESTION_FAST_MAX_TOKENS = 1400  # 问题生成快档最大 token
QUESTION_HEDGED_ENABLED = True  # 问题生成启用超时竞速（主通道慢时并发备用通道）
QUESTION_HEDGED_DELAY_SECONDS = 8.0  # 主通道启动后触发竞速的延迟（秒）
QUESTION_HEDGED_SECONDARY_LANE = "report"  # 竞速备用通道路由：report/summary/search_decision
QUESTION_HEDGED_ONLY_WHEN_DISTINCT_CLIENT = True  # 仅当备用通道客户端与主通道不同才启用竞速
QUESTION_RESULT_CACHE_TTL_SECONDS = 120  # 问题结果幂等缓存有效期（秒）
QUESTION_RESULT_CACHE_MAX_ENTRIES = 512  # 问题结果幂等缓存条目上限
METRICS_ASYNC_FLUSH_INTERVAL_SECONDS = 1.5  # 指标异步刷盘间隔（秒）
METRICS_ASYNC_BATCH_SIZE = 20  # 指标异步批量刷盘条数
METRICS_ASYNC_MAX_PENDING = 5000  # 指标内存队列最大积压条数
INTERVIEW_PROMPT_CACHE_TTL_SECONDS = 45  # 访谈 prompt 构建缓存有效期（秒）
INTERVIEW_PROMPT_CACHE_MAX_ENTRIES = 256  # 访谈 prompt 构建缓存条目上限
MAX_DOC_LENGTH = 2000          # 单个文档最大截断长度（字符）
MAX_TOTAL_DOCS = 5000          # 所有文档总长度限制（字符）
ENABLE_SMART_SUMMARY = True    # 是否启用智能摘要
SMART_SUMMARY_THRESHOLD = 1500 # 文档长度超过该值时触发智能摘要
SMART_SUMMARY_TARGET = 800     # 智能摘要目标长度（字符）
SUMMARY_CACHE_ENABLED = True   # 是否启用摘要缓存

# ============ 服务器配置 ============

# Flask 服务器配置
SERVER_HOST = "0.0.0.0"        # 监听地址，0.0.0.0 表示所有网卡
SERVER_PORT = 5001             # 监听端口
DEBUG_MODE = True              # 是否开启调试模式

# 列表接口分页与过载保护（并发优化）
LIST_API_DEFAULT_PAGE_SIZE = 20
LIST_API_MAX_PAGE_SIZE = 100
SESSIONS_LIST_MAX_INFLIGHT = 8
REPORTS_LIST_MAX_INFLIGHT = 8
LIST_API_RETRY_AFTER_SECONDS = 2

# 报告生成任务池（队列化 + 状态轮询）
REPORT_GENERATION_MAX_WORKERS = 2
REPORT_GENERATION_MAX_PENDING = 16
REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS = 3

# Gunicorn 生产配置（配合 scripts/start-production.sh）
GUNICORN_WORKERS = 8
GUNICORN_THREADS = 2
GUNICORN_TIMEOUT = 120
GUNICORN_GRACEFUL_TIMEOUT = 30
GUNICORN_KEEPALIVE = 5
GUNICORN_WORKER_CLASS = "gthread"
GUNICORN_LOG_LEVEL = "info"

# 登录鉴权配置（MVP）
# 建议在生产环境配置固定 SECRET_KEY，否则重启服务后登录态会失效
SECRET_KEY = "replace-with-a-strong-random-secret"
# 用户账号数据库路径（相对路径将按 Deep Vision 根目录解析）
AUTH_DB_PATH = "data/auth/users.db"

# 手机号验证码登录配置
# mock: 本地开发/测试模式（控制台输出验证码）
# jdcloud: 京东云短信平台
SMS_PROVIDER = "mock"
SMS_CODE_LENGTH = 6
SMS_CODE_TTL_SECONDS = 300
SMS_SEND_COOLDOWN_SECONDS = 60
SMS_MAX_SEND_PER_PHONE_PER_DAY = 10
SMS_MAX_VERIFY_ATTEMPTS = 5

# 测试环境可固定验证码，生产请置空
SMS_TEST_CODE = ""
# 验证码哈希签名密钥，未配置会复用 SECRET_KEY
SMS_CODE_SIGNING_SECRET = ""

# 京东云短信配置（SMS_PROVIDER=jdcloud 时必填）
JD_SMS_ACCESS_KEY_ID = ""
JD_SMS_ACCESS_KEY_SECRET = ""
JD_SMS_REGION_ID = "cn-north-1"
JD_SMS_SIGN_ID = ""
JD_SMS_TEMPLATE_ID_LOGIN = ""
JD_SMS_TEMPLATE_ID_BIND = ""
JD_SMS_TEMPLATE_ID_RECOVER = ""
JD_SMS_TIMEOUT = 8.0

# 场景目录配置（可选）
# 内置场景建议随代码发布，默认在 resources/scenarios/builtin
BUILTIN_SCENARIOS_DIR = "resources/scenarios/builtin"
# 自定义场景建议使用用户目录（容器可改为 /var/lib/deepvision/scenarios/custom）
CUSTOM_SCENARIOS_DIR = "~/.deepvision/scenarios/custom"

# 微信扫码登录配置（可选）
# 关闭时将隐藏前端微信登录入口
WECHAT_LOGIN_ENABLED = False
WECHAT_APP_ID = ""
WECHAT_APP_SECRET = ""
# 建议填写完整 HTTPS 回调地址；为空时将自动使用当前服务域名拼接 /api/auth/wechat/callback
WECHAT_REDIRECT_URI = ""
# PC 网站扫码登录建议使用 snsapi_login
WECHAT_OAUTH_SCOPE = "snsapi_login"
# 微信 OAuth 网络请求超时（秒）
WECHAT_OAUTH_TIMEOUT = 8.0
# state 防重放有效期（秒）
WECHAT_OAUTH_STATE_TTL_SECONDS = 300

# ============ 功能开关 ============

# 是否启用 AI 功能（如果为 False，将使用模拟数据）
ENABLE_AI = True

# 是否启用调试日志
ENABLE_DEBUG_LOG = True

# 是否启用联网搜索（需要配置 ZHIPU_API_KEY）
ENABLE_WEB_SEARCH = True

# 深度模式跳过追问是否要求二次确认
DEEP_MODE_SKIP_FOLLOWUP_CONFIRM = True

# ============ 搜索 API 配置 ============

# 智谱AI Web Search API 配置
# 获取 API Key: https://open.bigmodel.cn/
ZHIPU_API_KEY = "your-zhipu-api-key-here"
ZHIPU_SEARCH_ENGINE = "search_pro"  # 搜索引擎：search_std(基础版), search_pro(高阶版), search_pro_sogou(搜狗), search_pro_quark(夸克)

# 搜索配置
SEARCH_MAX_RESULTS = 3        # 每次搜索返回的最大结果数
SEARCH_TIMEOUT = 10           # 搜索超时时间（秒）

# ============ 图片处理配置 ============

# 智谱 Vision API 配置（使用视觉模型描述图片）
# 复用 ZHIPU_API_KEY，无需额外配置
VISION_MODEL_NAME = "glm-4v-flash"  # 免费视觉模型，或使用 glm-4.6v（收费）
VISION_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ENABLE_VISION = True  # 是否启用图片描述功能

# 图片大小限制
MAX_IMAGE_SIZE_MB = 10  # 最大 10MB
SUPPORTED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

# ============ Refly API 配置 ============

# Refly Workflow API 配置
# 请根据 Refly 文档填写正确的 API 地址与参数
REFLY_API_URL = "https://api.refly.ai/v1/workflows/run"
REFLY_API_KEY = "your-refly-api-key-here"
REFLY_WORKFLOW_ID = "c-yydcpevbwl6wgwe6i0uk8omw"
REFLY_INPUT_FIELD = "report"
REFLY_TIMEOUT = 30  # 请求超时（秒）

"""
Deep Vision 配置文件示例

使用说明：
1. 二选一：复制本文件为 config.py，或复制 .env.example 为 .env
2. 按注释填入实际的 API Key 和业务配置
3. config.py / .env 都已加入忽略规则，不会提交到版本库

说明：
- 本示例已按“配置来源 -> AI 路由 -> 运行策略 -> 外部集成”重新分组，便于按职责查找配置。
- 本示例采用当前项目推荐的模型分工：问题=minimax-2.5，报告草案=kimi-k2.5，报告审稿=glm-5，摘要/搜索决策/评分=glm-5。
- 报告 V3 默认使用 balanced 档，并启用双阶段路由：草案走 report_draft 网关，审稿走 report_review 网关。
- 报告 V3 的时延/长度参数默认留空(None)，这样可按档位自动取值：balanced 更快，quality 更稳。
- 当 `.env` 存在且包含实际键值时，AI 运行参数默认不再回落 `config.py`；如需保留历史混合模式，可在 `.env` 中设置 `CONFIG_RESOLUTION_MODE=hybrid`。
"""

# ============ 配置来源与客户端初始化 ===========
# 决定配置从哪里生效，以及服务启动时是否预热 AI 客户端。
# `CONFIG_RESOLUTION_MODE` 常用值：`auto` / `hybrid` / `env_only`。
# 作用：控制 .env 与 config.py 的配置解析优先级，建议保持 auto。
CONFIG_RESOLUTION_MODE = "auto"
# 作用：控制服务启动时是否立刻初始化所有 AI 客户端。
AI_CLIENT_EAGER_INIT = False
# 作用：控制初始化 AI 客户端时是否发送一条探测请求验证连通性。
AI_CLIENT_INIT_CONNECTION_TEST = False

# ============ 模型角色分工 ===========
# 先看这一组，就能知道问题、报告、摘要、评分各自走哪个模型。
# 作用：设置全局默认模型名，未单独指定 lane 模型时会回落到这里。
MODEL_NAME = "minimax-2.5"  # 默认主模型（问题链路）
# 作用：设置问题生成链路使用的模型名称。
QUESTION_MODEL_NAME = MODEL_NAME
# 作用：设置报告主链路使用的模型名称。
REPORT_MODEL_NAME = "kimi-k2.5"
# 作用：设置报告草案阶段使用的模型名称。
REPORT_DRAFT_MODEL_NAME = REPORT_MODEL_NAME
# 作用：设置报告审稿阶段使用的模型名称。
REPORT_REVIEW_MODEL_NAME = "glm-5"
# 作用：设置摘要链路使用的模型名称。
SUMMARY_MODEL_NAME = "glm-5"
# 作用：设置搜索决策链路使用的模型名称。
SEARCH_DECISION_MODEL_NAME = SUMMARY_MODEL_NAME
# 作用：设置评分链路使用的模型名称。
ASSESSMENT_MODEL_NAME = SEARCH_DECISION_MODEL_NAME

# ============ 默认回落网关 ===========
# 当某条 lane 没有单独配置网关时，会回落到这里。
# 作用：设置全局默认 Anthropic 兼容网关使用的 API Key。
ANTHROPIC_API_KEY = "your-global-api-key"
# 作用：设置全局默认 Anthropic 兼容网关请求的根地址。
ANTHROPIC_BASE_URL = "https://your-global-base-url"
# 作用：控制全局默认 Anthropic 兼容网关是否使用 Bearer Authorization 鉴权。
ANTHROPIC_USE_BEARER_AUTH = True

# ============ 按链路网关与鉴权 ===========
# 问题、报告、摘要、搜索决策、评分都可以绑定独立网关。
# 作用：设置问题生成链路使用的 API Key。
QUESTION_API_KEY = "your-question-api-key"
# 作用：设置问题生成链路请求的根地址。
QUESTION_BASE_URL = "https://your-minimax-base-url"
# 作用：控制问题生成链路是否使用 Bearer Authorization 鉴权。
QUESTION_USE_BEARER_AUTH = True
# 作用：设置报告主链路使用的 API Key。
REPORT_API_KEY = "your-report-default-api-key"
# 作用：设置报告主链路请求的根地址。
REPORT_BASE_URL = "https://your-report-default-base-url"
# 作用：控制报告主链路是否使用 Bearer Authorization 鉴权。
REPORT_USE_BEARER_AUTH = True
# 作用：设置报告草案阶段使用的 API Key。
REPORT_DRAFT_API_KEY = "your-kimi-api-key"
# 作用：设置报告草案阶段请求的根地址。
REPORT_DRAFT_BASE_URL = "https://your-kimi-base-url"
# 作用：控制报告草案阶段是否使用 Bearer Authorization 鉴权。
REPORT_DRAFT_USE_BEARER_AUTH = True
# 作用：设置报告审稿阶段使用的 API Key。
REPORT_REVIEW_API_KEY = "your-glm-api-key"
# 作用：设置报告审稿阶段请求的根地址。
REPORT_REVIEW_BASE_URL = "https://your-glm-base-url"
# 作用：控制报告审稿阶段是否使用 Bearer Authorization 鉴权。
REPORT_REVIEW_USE_BEARER_AUTH = True
# 作用：设置摘要链路使用的 API Key。
SUMMARY_API_KEY = "your-summary-api-key"
# 作用：设置摘要链路请求的根地址。
SUMMARY_BASE_URL = "https://your-glm-base-url"
# 作用：控制摘要链路是否使用 Bearer Authorization 鉴权。
SUMMARY_USE_BEARER_AUTH = True
# 作用：设置搜索决策链路使用的 API Key。
SEARCH_DECISION_API_KEY = "your-search-decision-api-key"
# 作用：设置搜索决策链路请求的根地址。
SEARCH_DECISION_BASE_URL = "https://your-glm-base-url"
# 作用：控制搜索决策链路是否使用 Bearer Authorization 鉴权。
SEARCH_DECISION_USE_BEARER_AUTH = True
# 作用：设置评分链路使用的 API Key。
ASSESSMENT_API_KEY = SEARCH_DECISION_API_KEY
# 作用：设置评分链路请求的根地址。
ASSESSMENT_BASE_URL = SEARCH_DECISION_BASE_URL
# 作用：控制评分链路是否使用 Bearer Authorization 鉴权。
ASSESSMENT_USE_BEARER_AUTH = True

# ============ AI 通用运行限制 ===========
# 控制通用超时、单次输出体量、上下文长度和长文压缩策略。
# 作用：设置通用 AI 调用的默认超时时间（秒）。
API_TIMEOUT = 90.0
# 作用：设置未单独指定链路时，单次 AI 调用默认允许输出的最大 token 数。
MAX_TOKENS_DEFAULT = 4000
# 作用：设置问题生成链路单次响应允许输出的最大 token 数。
MAX_TOKENS_QUESTION = 1600
# 作用：设置报告主生成链路单次响应允许输出的最大 token 数。
MAX_TOKENS_REPORT = 7000
# 作用：设置摘要链路单次响应允许输出的最大 token 数。
MAX_TOKENS_SUMMARY = 500
# 作用：设置搜索决策首轮轻量判断阶段允许输出的最大 token 数。
SEARCH_DECISION_FIRST_MAX_TOKENS = 220
# 作用：设置搜索决策重试阶段允许输出的最大 token 数。
SEARCH_DECISION_RETRY_MAX_TOKENS = 420
# 作用：设置单题评分调用允许输出的最大 token 数。
ASSESSMENT_SCORE_MAX_TOKENS = 96
# 作用：设置会话上下文中保留的最近完整问答轮数。
CONTEXT_WINDOW_SIZE = 5
# 作用：设置触发历史摘要前需要累积的问答条数阈值。
SUMMARY_THRESHOLD = 8
# 作用：设置单份参考资料参与 Prompt 前允许保留的最大字符数。
MAX_DOC_LENGTH = 1800
# 作用：设置所有参考资料合并后允许保留的最大总字符数。
MAX_TOTAL_DOCS = 5000
# 作用：控制是否启用长文档智能摘要。
ENABLE_SMART_SUMMARY = True
# 作用：设置触发智能摘要的文档长度阈值。
SMART_SUMMARY_THRESHOLD = 1400
# 作用：设置智能摘要压缩后的目标字符长度。
SMART_SUMMARY_TARGET = 700
# 作用：控制是否启用摘要结果缓存。
SUMMARY_CACHE_ENABLED = True

# ============ 问题生成链路 ===========
# 控制快档、竞速、按 lane 覆盖以及问题链路的长尾优化。
# 作用：控制问题生成是否先尝试快档。
QUESTION_FAST_PATH_ENABLED = True
# 作用：设置问题快档调用的超时时间（秒）。
QUESTION_FAST_TIMEOUT = 12.0
# 作用：设置问题快档调用允许输出的最大 token 数。
QUESTION_FAST_MAX_TOKENS = 1000
# 作用：设置仍允许走问题快档的 Prompt 最大字符数。
QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS = 1800
# 作用：控制存在截断文档时是否直接跳过问题快档。
QUESTION_FAST_SKIP_WHEN_TRUNCATED_DOCS = True
# 作用：控制问题快档是否根据命中率自动冷却。
QUESTION_FAST_ADAPTIVE_ENABLED = True
# 作用：设置问题快档命中率统计窗口大小。
QUESTION_FAST_ADAPTIVE_WINDOW_SIZE = 20
# 作用：设置问题快档启用自适应判断前所需的最少样本数。
QUESTION_FAST_ADAPTIVE_MIN_SAMPLES = 8
# 作用：设置问题快档允许的最低命中率阈值。
QUESTION_FAST_ADAPTIVE_MIN_HIT_RATE = 0.35
# 作用：设置问题快档低命中率后进入冷却的持续时间（秒）。
QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS = 900.0
# 作用：控制问题生成是否启用备用通道竞速。
QUESTION_HEDGED_ENABLED = True
# 作用：设置问题竞速启动备用通道前的等待时间（秒）。
QUESTION_HEDGED_DELAY_SECONDS = 1.5
# 作用：设置问题竞速时备用通道使用的 lane。
QUESTION_HEDGED_SECONDARY_LANE = "summary"  # 用 glm-5 做问题链路备用，避免让 Opus 抢答高频问题
# 作用：控制只有主备客户端不同才启用问题竞速。
QUESTION_HEDGED_ONLY_WHEN_DISTINCT_CLIENT = True
# 作用：按 lane 覆盖问题快档超时时间。
QUESTION_FAST_TIMEOUT_BY_LANE = {"question": 12.0, "summary": 9.0, "report": 14.0, "search_decision": 8.0}
# 作用：按 lane 覆盖问题快档最大 token 数。
QUESTION_FAST_MAX_TOKENS_BY_LANE = {"question": 1000, "summary": 820, "report": 1100, "search_decision": 720}
# 作用：按 lane 覆盖问题全量档超时时间。
QUESTION_FULL_TIMEOUT_BY_LANE = {"question": 30.0, "summary": 24.0, "report": 42.0, "search_decision": 20.0}
# 作用：按 lane 覆盖问题全量档最大 token 数。
QUESTION_FULL_MAX_TOKENS_BY_LANE = {"question": 1600, "summary": 1300, "report": 1700, "search_decision": 1100}
# 作用：按 lane 覆盖问题竞速的备用通道启动延迟。
QUESTION_HEDGE_DELAY_BY_LANE = {"question": 1.5, "summary": 1.0, "report": 1.8, "search_decision": 0.8}

# ============ 报告生成链路 ===========
# 集中放置报告 V3 的档位、双阶段、质量门与失败兜底策略。
# 留空为 `None` 的高级参数，会由 `server.py` 按 `balanced/quality` 档位自动补默认值。
# 作用：设置报告 V3 默认使用的运行档位。
REPORT_V3_PROFILE = "balanced"  # 默认报告档位：balanced / quality
# 作用：设置报告链路默认调用超时时间（秒）。
REPORT_API_TIMEOUT = 180.0
# 作用：设置报告草案阶段的调用超时时间（秒）。
REPORT_DRAFT_API_TIMEOUT = 150.0
# 作用：设置报告审稿阶段的调用超时时间（秒）。
REPORT_REVIEW_API_TIMEOUT = 120.0
# 作用：设置报告草案阶段允许生成的最大 token 数，留空则按档位默认。
REPORT_V3_DRAFT_MAX_TOKENS = None
# 作用：设置报告草案阶段可注入的事实证据上限。
REPORT_V3_DRAFT_FACTS_LIMIT = None
# 作用：设置报告草案重试降载后保留的最小事实证据数。
REPORT_V3_DRAFT_MIN_FACTS_LIMIT = None
# 作用：设置报告草案阶段的重试次数。
REPORT_V3_DRAFT_RETRY_COUNT = None
# 作用：设置报告草案阶段每轮重试前的退避等待时间（秒）。
REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS = None
# 作用：设置报告审稿阶段允许生成的最大 token 数。
REPORT_V3_REVIEW_MAX_TOKENS = None
# 作用：设置报告 V3 基础审稿轮数。
REPORT_V3_REVIEW_BASE_ROUNDS = None
# 作用：设置 quality 档额外补修轮数。
REPORT_V3_QUALITY_FIX_ROUNDS = None
# 作用：设置报告 V3 至少执行的审稿轮数，0 表示按档位默认。
REPORT_V3_MIN_REVIEW_ROUNDS = 0  # 0=按档位默认(balanced=1, quality=2)
# 作用：控制报告 V3 是否启用草案与审稿双阶段流程。
REPORT_V3_DUAL_STAGE_ENABLED = True
# 作用：设置报告草案阶段默认优先进入的外部 lane。
REPORT_V3_DRAFT_PRIMARY_LANE = "report"
# 作用：设置报告审稿阶段默认优先进入的外部 lane。
REPORT_V3_REVIEW_PRIMARY_LANE = "report"
# 作用：控制 quality 档是否强制草案和审稿共用同一 lane。
REPORT_V3_QUALITY_FORCE_SINGLE_LANE = False
# 作用：设置 quality 档单 lane 模式下优先使用的 lane。
REPORT_V3_QUALITY_PRIMARY_LANE = "report"
# 作用：控制审稿 JSON 解析失败时是否触发结构化修复重试。
REPORT_V3_REVIEW_REPAIR_RETRY_ENABLED = True
# 作用：设置审稿修复重试允许使用的最大 token 数。
REPORT_V3_REVIEW_REPAIR_MAX_TOKENS = 2200
# 作用：设置审稿修复重试的超时时间（秒）。
REPORT_V3_REVIEW_REPAIR_TIMEOUT = 45.0
# 作用：控制报告 V3 是否根据结构化数据自动渲染 Mermaid 图表。
REPORT_V3_RENDER_MERMAID_FROM_DATA = True
# 作用：控制报告 V3 是否启用弱绑定补全策略。
REPORT_V3_WEAK_BINDING_ENABLED = True
# 作用：设置报告 V3 触发弱绑定补全时要求的最低匹配分数。
REPORT_V3_WEAK_BINDING_MIN_SCORE = 0.46
# 作用：控制报告 V3 在质量门未通过时是否尝试挽救输出。
REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE = True
# 作用：控制报告 V3 主 lane 失败后是否尝试备用 lane。
REPORT_V3_FAILOVER_ENABLED = True
# 作用：设置报告 V3 切换失败备用通道时使用的 lane。
REPORT_V3_FAILOVER_LANE = "question"
# 作用：控制审稿仅剩单个可修复问题时是否允许切备用 lane 再试。
REPORT_V3_FAILOVER_ON_SINGLE_ISSUE = True
# 作用：控制 balanced 档是否要求把盲区直接转换成行动项。
REPORT_V3_BLINDSPOT_ACTION_REQUIRED_BALANCED = False
# 作用：控制 quality 档是否要求把盲区直接转换成行动项。
REPORT_V3_BLINDSPOT_ACTION_REQUIRED_QUALITY = True
# 作用：控制 unknown 证据过多时是否自动补充开放问题。
REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_ENABLED = True
# 作用：设置自动补充开放问题时最多新增的条目数。
REPORT_V3_UNKNOWNS_TO_OPEN_QUESTIONS_MAX_ITEMS = 3
# 作用：设置触发 unknown 自动补问的比例阈值。
REPORT_V3_UNKNOWN_RATIO_TRIGGER = 0.65

# ============ 缓存、预生成与异步调度 ===========
# 统一放置缓存、后台预生成、摘要去抖和指标异步刷盘参数。
# 作用：控制预生成任务是否只在主链路空闲时才执行。
PREFETCH_IDLE_ONLY = True
# 作用：设置触发预生成时允许并行的低优先级任务上限。
PREFETCH_IDLE_MAX_LOW_RUNNING = 0
# 作用：设置预生成等待系统空闲的最长时间（秒）。
PREFETCH_IDLE_WAIT_SECONDS = 8.0
# 作用：控制新会话首题是否启用预生成优先窗口。
FIRST_QUESTION_PREFETCH_PRIORITY_ENABLED = True
# 作用：设置首题预生成优先窗口持续时间（秒）。
FIRST_QUESTION_PREFETCH_PRIORITY_WINDOW_SECONDS = 120.0
# 作用：设置后台预生成问题全量档的超时时间（秒）。
PREFETCH_QUESTION_TIMEOUT = 60.0
# 作用：设置后台预生成问题全量档允许输出的最大 token 数。
PREFETCH_QUESTION_MAX_TOKENS = 1400
# 作用：设置后台预生成问题快档的超时时间（秒）。
PREFETCH_QUESTION_FAST_TIMEOUT = 10.0
# 作用：设置后台预生成问题快档允许输出的最大 token 数。
PREFETCH_QUESTION_FAST_MAX_TOKENS = 850
# 作用：设置后台预生成问题竞速的备用通道启动延迟。
PREFETCH_QUESTION_HEDGE_DELAY_SECONDS = 2.2
# 作用：设置后台预生成问题时优先使用的 lane。
PREFETCH_QUESTION_PRIMARY_LANE = "question"
# 作用：设置后台预生成问题时备用使用的 lane。
PREFETCH_QUESTION_SECONDARY_LANE = "summary"
# 作用：设置问题结果幂等缓存的保留时长（秒）。
QUESTION_RESULT_CACHE_TTL_SECONDS = 180
# 作用：设置问题结果幂等缓存允许保存的最大条目数。
QUESTION_RESULT_CACHE_MAX_ENTRIES = 512
# 作用：设置摘要异步更新的最小触发间隔（秒）。
SUMMARY_UPDATE_DEBOUNCE_SECONDS = 60
# 作用：设置搜索决策缓存的保留时长（秒）。
SEARCH_DECISION_CACHE_TTL_SECONDS = 900
# 作用：设置搜索决策缓存允许保存的最大条目数。
SEARCH_DECISION_CACHE_MAX_ENTRIES = 256
# 作用：设置并发命中同一搜索决策时等待首个结果的最长时间（秒）。
SEARCH_DECISION_INFLIGHT_WAIT_SECONDS = 10.0
# 作用：设置搜索结果缓存的保留时长（秒）。
SEARCH_RESULT_CACHE_TTL_SECONDS = 300
# 作用：设置搜索结果缓存允许保存的最大条目数。
SEARCH_RESULT_CACHE_MAX_ENTRIES = 128
# 作用：设置并发命中同一搜索请求时等待首个结果的最长时间（秒）。
SEARCH_RESULT_INFLIGHT_WAIT_SECONDS = 12.0
# 作用：设置访谈 Prompt 构建缓存的保留时长（秒）。
INTERVIEW_PROMPT_CACHE_TTL_SECONDS = 120
# 作用：设置访谈 Prompt 构建缓存允许保存的最大条目数。
INTERVIEW_PROMPT_CACHE_MAX_ENTRIES = 256
# 作用：设置指标异步批量刷盘的时间间隔（秒）。
METRICS_ASYNC_FLUSH_INTERVAL_SECONDS = 1.5
# 作用：设置每次异步刷盘提交的指标条数。
METRICS_ASYNC_BATCH_SIZE = 20
# 作用：设置指标异步队列允许积压的最大条数。
METRICS_ASYNC_MAX_PENDING = 5000

# ============ 服务运行与任务并发 ===========
# 服务监听、分页保护、任务队列等基础运行参数都在这里。
# 作用：设置 Web 服务监听的主机地址。
SERVER_HOST = "0.0.0.0"
# 作用：设置 Web 服务监听的端口。
SERVER_PORT = 5001
# 作用：控制服务是否以调试模式运行。
DEBUG_MODE = True
# 作用：设置列表接口默认分页大小。
LIST_API_DEFAULT_PAGE_SIZE = 20
# 作用：设置列表接口允许的最大分页大小。
LIST_API_MAX_PAGE_SIZE = 100
# 作用：设置会话列表接口允许并发处理的最大请求数。
SESSIONS_LIST_MAX_INFLIGHT = 8
# 作用：设置报告列表接口允许并发处理的最大请求数。
REPORTS_LIST_MAX_INFLIGHT = 8
# 作用：设置列表接口过载时返回的建议重试时间（秒）。
LIST_API_RETRY_AFTER_SECONDS = 2
# 作用：设置报告生成任务池的最大工作线程数。
REPORT_GENERATION_MAX_WORKERS = 2
# 作用：设置报告生成任务队列允许积压的最大任务数。
REPORT_GENERATION_MAX_PENDING = 16
# 作用：设置报告生成队列繁忙时建议的重试时间（秒）。
REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS = 3

# ============ Gunicorn 生产部署 ===========
# 这一组只对 Gunicorn 生产部署生效，直接从进程环境读取。
# `web/gunicorn.conf.py` 只读取进程环境，不会读取 `config.py` 里的同名键。
# 作用：设置 Gunicorn 工作进程数量。
GUNICORN_WORKERS = 8
# 作用：设置每个 Gunicorn 工作进程使用的线程数。
GUNICORN_THREADS = 2
# 作用：设置 Gunicorn 请求处理超时时间（秒）。
GUNICORN_TIMEOUT = 120
# 作用：设置 Gunicorn 优雅关闭等待时间（秒）。
GUNICORN_GRACEFUL_TIMEOUT = 30
# 作用：设置 Gunicorn 长连接保活时间（秒）。
GUNICORN_KEEPALIVE = 5
# 作用：设置 Gunicorn 使用的 worker 类型。
GUNICORN_WORKER_CLASS = "gthread"
# 作用：设置 Gunicorn 日志输出级别。
GUNICORN_LOG_LEVEL = "info"

# ============ 功能开关 ===========
# 排查功能是否开启时，先看这一组。
# 作用：控制是否启用真实 AI 调用。
ENABLE_AI = True
# 作用：控制是否输出调试日志。
ENABLE_DEBUG_LOG = True
# 作用：控制是否隐藏状态轮询接口的访问日志。
SUPPRESS_STATUS_POLL_ACCESS_LOG = True
# 作用：控制深度模式下是否跳过追问前的二次确认。
DEEP_MODE_SKIP_FOLLOWUP_CONFIRM = True

# ============ 联网搜索 ===========
# 真实联网搜索的开关、供应商凭据和结果规模都在这里。
# 作用：控制是否启用联网搜索能力。
ENABLE_WEB_SEARCH = True
# 作用：设置智谱搜索与多模态服务的 API Key。
ZHIPU_API_KEY = "your-zhipu-api-key"
# 作用：设置联网搜索默认使用的智谱搜索引擎。
ZHIPU_SEARCH_ENGINE = "search_pro"
# 作用：设置每次联网搜索最多返回的结果条数。
SEARCH_MAX_RESULTS = 3
# 作用：设置联网搜索请求的超时时间（秒）。
SEARCH_TIMEOUT = 10

# ============ 安全鉴权与短信登录 ===========
# 包含会话密钥、用户库、短信验证码与短信供应商配置。
# `SMS_PROVIDER` 常用值：`mock`（本地）/ `jdcloud`（生产）。
# 作用：设置 Flask 会话与签名使用的密钥。
SECRET_KEY = "replace-with-a-strong-random-secret"
# 作用：设置登录鉴权数据库文件路径。
AUTH_DB_PATH = "data/auth/users.db"
# 作用：设置短信登录使用的服务提供商。
SMS_PROVIDER = "mock"
# 作用：设置短信验证码长度。
SMS_CODE_LENGTH = 6
# 作用：设置短信验证码的有效期（秒）。
SMS_CODE_TTL_SECONDS = 300
# 作用：设置同一手机号再次发送验证码前的冷却时间（秒）。
SMS_SEND_COOLDOWN_SECONDS = 60
# 作用：设置同一手机号每天允许发送验证码的最大次数。
SMS_MAX_SEND_PER_PHONE_PER_DAY = 10
# 作用：设置同一验证码允许校验失败的最大次数。
SMS_MAX_VERIFY_ATTEMPTS = 5
# 作用：设置测试环境可直接使用的固定短信验证码。
SMS_TEST_CODE = "666666"
# 作用：设置短信验证码签名使用的密钥。
SMS_CODE_SIGNING_SECRET = ""
# 作用：设置京东云短信服务的 Access Key ID。
JD_SMS_ACCESS_KEY_ID = ""
# 作用：设置京东云短信服务的 Access Key Secret。
JD_SMS_ACCESS_KEY_SECRET = ""
# 作用：设置京东云短信服务使用的地域 ID。
JD_SMS_REGION_ID = "cn-north-1"
# 作用：设置京东云短信服务的签名 ID。
JD_SMS_SIGN_ID = ""
# 作用：设置京东云短信登录验证码模板 ID。
JD_SMS_TEMPLATE_ID_LOGIN = ""
# 作用：设置京东云短信绑定手机号模板 ID。
JD_SMS_TEMPLATE_ID_BIND = ""
# 作用：设置京东云短信找回/恢复模板 ID。
JD_SMS_TEMPLATE_ID_RECOVER = ""
# 作用：设置京东云短信接口调用超时时间（秒）。
JD_SMS_TIMEOUT = 8.0

# ============ 场景目录与实例隔离 ===========
# 场景目录和多实例隔离配置放在一起，便于运维排查。
# 多实例共享数据目录时，`INSTANCE_SCOPE_KEY` 必须按业务实例区分。
# 作用：设置内置场景配置目录路径。
BUILTIN_SCENARIOS_DIR = "resources/scenarios/builtin"
# 作用：设置用户自定义场景配置目录路径。
CUSTOM_SCENARIOS_DIR = "~/.deepvision/scenarios/custom"
# 作用：设置当前部署实例的业务作用域标识。
INSTANCE_SCOPE_KEY = ""

# ============ 微信登录 ===========
# 微信扫码登录相关参数集中放置，回调地址要与部署域名一致。
# 作用：控制是否启用微信扫码登录。
WECHAT_LOGIN_ENABLED = False
# 作用：设置微信开放平台应用的 AppID。
WECHAT_APP_ID = ""
# 作用：设置微信开放平台应用的 AppSecret。
WECHAT_APP_SECRET = ""
# 作用：设置微信登录完成后的回调地址。
WECHAT_REDIRECT_URI = ""
# 作用：设置微信 OAuth 请求使用的授权范围。
WECHAT_OAUTH_SCOPE = "snsapi_login"
# 作用：设置微信 OAuth 接口调用超时时间（秒）。
WECHAT_OAUTH_TIMEOUT = 8.0
# 作用：设置微信登录 state 参数的有效期（秒）。
WECHAT_OAUTH_STATE_TTL_SECONDS = 300

# ============ 图片理解 ===========
# 图片理解模型、接口地址与上传限制。
# 作用：设置图片理解链路使用的视觉模型名称。
VISION_MODEL_NAME = "glm-4v-flash"
# 作用：设置图片理解接口的请求地址。
VISION_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 作用：控制是否启用图片理解能力。
ENABLE_VISION = True
# 作用：设置允许上传到视觉模型的单张图片大小上限（MB）。
MAX_IMAGE_SIZE_MB = 10
# 作用：设置视觉链路允许处理的图片文件扩展名列表。
SUPPORTED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

# ============ Refly 工作流 ===========
# 与 Refly 工作流对接相关的配置统一放在这里。
# 作用：设置 Refly Workflow API 的服务地址。
REFLY_API_URL = "https://api.refly.ai/v1"
# 作用：设置 Refly Workflow API 的认证密钥。
REFLY_API_KEY = "your-refly-api-key"
# 作用：设置默认调用的 Refly 工作流 ID。
REFLY_WORKFLOW_ID = "replace-with-your-workflow-id"
# 作用：设置 Refly 工作流中承接主文本输入的字段名。
REFLY_INPUT_FIELD = "input"
# 作用：设置 Refly 工作流中承接文件输入的字段名。
REFLY_FILES_FIELD = "files"
# 作用：设置 Refly 工作流请求的超时时间（秒）。
REFLY_TIMEOUT = 30

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

# Token 限制配置（与 server.py 默认值保持一致）
MAX_TOKENS_DEFAULT = 5000      # 默认最大 token 数
MAX_TOKENS_QUESTION = 2000     # 生成问题时的最大 token 数
MAX_TOKENS_REPORT = 10000      # 生成报告时的最大 token 数
MAX_TOKENS_SUMMARY = 500       # 文档摘要生成最大 token 数

# AI 运行策略配置（建议统一在此调整）
API_TIMEOUT = 90.0             # 通用 API 超时（秒）
REPORT_API_TIMEOUT = 210.0     # 报告生成专用超时（秒）
CONTEXT_WINDOW_SIZE = 5        # 保留最近 N 条问答
SUMMARY_THRESHOLD = 8          # 超过此数量触发历史摘要
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

# 登录鉴权配置（MVP）
# 建议在生产环境配置固定 SECRET_KEY，否则重启服务后登录态会失效
SECRET_KEY = "replace-with-a-strong-random-secret"
# 用户账号数据库路径（相对路径将按 Deep Vision 根目录解析）
AUTH_DB_PATH = "data/auth/users.db"

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

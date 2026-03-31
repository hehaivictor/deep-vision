"""
Deep Vision 策略配置示例

使用说明：
1. 复制本文件为 config.py，只保留需要覆盖的本地策略默认值
2. 复制 .env.example 为 .env，并在 .env 中填写密钥、地址、部署路径和运维开关
3. config.py / .env 都已加入忽略规则，不会提交到版本库

说明：
- config.example.py 负责研发策略默认值：模型分工、链路阈值、缓存预算、报告/问题生成策略。
- .env.example 负责部署差异：密钥、网关地址、部署路径、运维开关和少量应急覆盖项。
- 自动模式下，若 `.env` 已加载，环境接入/部署类配置优先使用 env/default，不再回落 `config.py`；策略型配置仍可回落 `config.py`。
"""

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

# ============ AI 客户端初始化 ===========
# 控制服务启动时是否预热客户端，以及是否额外做连通性探测。
# 作用：控制服务启动时是否提前初始化各 lane 的 AI 客户端。
AI_CLIENT_EAGER_INIT = False
# 作用：控制预热 AI 客户端时是否额外发送探测请求验证连通性。
AI_CLIENT_INIT_CONNECTION_TEST = False
# 作用：设置 AI 客户端单次请求在 SDK 层允许的最大重试次数。
AI_CLIENT_MAX_RETRIES = 0

# ============ AI 通用运行默认值 ===========
# 通用运行限制放在 config，必要时可由 env 临时覆盖。
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
# 作用：设置问题生成接口允许的最大并发请求数。
QUESTION_GENERATION_MAX_INFLIGHT = 2
# 作用：设置问题生成链路触发并发保护后的建议重试时间（秒）。
QUESTION_GENERATION_RETRY_AFTER_SECONDS = 2
# 作用：控制问题生成是否先尝试快档。
QUESTION_FAST_PATH_ENABLED = True
# 作用：控制发布模式下的问题链路是否启用保守策略。
QUESTION_RELEASE_CONSERVATIVE_MODE = True
# 作用：设置问题快档调用的超时时间（秒）。
QUESTION_FAST_TIMEOUT = 12.0
# 作用：设置问题快档在轻量参考资料模式下的请求超时时间（秒）。
QUESTION_FAST_REFERENCE_TIMEOUT = 15.0
# 作用：设置问题快档调用允许输出的最大 token 数。
QUESTION_FAST_MAX_TOKENS = 1000
# 作用：设置仍允许走问题快档的 Prompt 最大字符数。
QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS = 1800
# 作用：控制问题快档是否允许启用轻量参考资料模式。
QUESTION_FAST_LIGHT_REFERENCE_DOCS_ENABLED = True
# 作用：设置轻量参考资料模式下最多注入的参考资料条数。
QUESTION_FAST_LIGHT_MAX_REFERENCE_DOCS = 2
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
# 作用：控制问题链路是否允许基于历史表现自动切换 lane。
QUESTION_LANE_DYNAMIC_ENABLED = True
# 作用：设置问题链路动态 lane 统计的窗口大小。
QUESTION_LANE_STATS_WINDOW_SIZE = 24
# 作用：设置问题链路动态 lane 生效前要求的最小样本数。
QUESTION_LANE_STATS_MIN_SAMPLES = 6
# 作用：设置问题链路切换时要求的最小成功率优势阈值。
QUESTION_LANE_SWITCH_SUCCESS_MARGIN = 0.08
# 作用：设置问题链路切换时允许接受的时延劣化比例上限。
QUESTION_LANE_SWITCH_LATENCY_RATIO = 0.18
# 作用：控制问题生成是否启用备用通道竞速。
QUESTION_HEDGED_ENABLED = True
# 作用：设置问题竞速启动备用通道前的等待时间（秒）。
QUESTION_HEDGED_DELAY_SECONDS = 1.5
# 作用：设置问题竞速时备用通道使用的 lane。
QUESTION_HEDGED_SECONDARY_LANE = "summary"  # 用 glm-5 做问题链路备用，避免让 Opus 抢答高频问题
# 作用：高取证强度问题的主通道，默认固定走 question lane。
QUESTION_HIGH_EVIDENCE_PRIMARY_LANE = "question"
# 作用：高取证强度问题的备用通道，默认走 report lane，禁用 summary 竞速。
QUESTION_HIGH_EVIDENCE_SECONDARY_LANE = "report"
# 作用：高取证强度问题是否禁用基于历史时延/成功率的动态 lane 晋升。
QUESTION_HIGH_EVIDENCE_DISABLE_DYNAMIC_LANE = True
# 作用：高取证强度问题是否允许继续走快档。
QUESTION_HIGH_EVIDENCE_FAST_PATH_ENABLED = True
# 作用：高取证强度问题是否允许直接并发备用通道，默认关闭，优先单发失败后补发。
QUESTION_HIGH_EVIDENCE_HEDGED_ENABLED = False
# 作用：是否启用主通道失败后的备用通道补发。
QUESTION_HEDGE_FAILURE_FALLBACK_ENABLED = True
# 作用：是否仅允许真正阻塞 shadow draft 的题目启用并发竞速。
QUESTION_HEDGE_REQUIRE_SHADOW_BLOCKER = True
# 作用：轻量参考资料模式是否绕过问题竞速预算限制。
QUESTION_FAST_REFERENCE_HEDGE_BYPASS_BUDGET = True
# 作用：单个会话内允许发生问题并发竞速的总次数预算。
QUESTION_SESSION_HEDGE_BUDGET = 4
# 作用：单个维度内允许发生问题并发竞速的次数预算。
QUESTION_DIMENSION_HEDGE_BUDGET = 1
# 作用：控制只有主备客户端不同才启用问题竞速。
QUESTION_HEDGED_ONLY_WHEN_DISTINCT_CLIENT = True
# 作用：控制是否启用问题竞速延迟的自适应策略。
QUESTION_HEDGE_ADAPTIVE_ENABLED = True
# 作用：设置问题竞速自适应策略生效所需的最小样本数。
QUESTION_HEDGE_ADAPTIVE_MIN_SAMPLES = 8
# 作用：设置问题竞速自适应延迟计算采用的耗时分位点。
QUESTION_HEDGE_ADAPTIVE_PERCENTILE = 0.8
# 作用：设置问题竞速自适应延迟相对主请求超时的比例上限。
QUESTION_HEDGE_ADAPTIVE_TIMEOUT_RATIO = 0.45
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
# 作用：设置报告 V3 默认使用的生成模式，前台不再单独让用户选择。
REPORT_V3_PROFILE = "balanced"  # 报告生成模式：balanced / quality
# 作用：控制发布模式下 balanced 档是否启用保守发布策略。
REPORT_V3_RELEASE_CONSERVATIVE_MODE = True
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
# 作用：设置草案为空时是否立即失败；`None` 表示按档位默认。
REPORT_V3_FAST_FAIL_ON_DRAFT_EMPTY = None
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
# 作用：控制发布保守模式下是否允许草案阶段切换到备用 lane。
REPORT_V3_ALLOW_DRAFT_ALTERNATE_LANE_IN_RELEASE_CONSERVATIVE = False
# 作用：控制发布保守模式下是否直接跳过模型审稿，优先走模板/规则化兜底。
REPORT_V3_SKIP_MODEL_REVIEW_IN_RELEASE_CONSERVATIVE = True
# 作用：控制发布保守模式下是否启用短路 fallback。
REPORT_V3_RELEASE_SHORT_CIRCUIT_ENABLED = True
# 作用：控制报告 V3 在质量门未通过时是否尝试挽救输出。
REPORT_V3_SALVAGE_ON_QUALITY_GATE_FAILURE = True
# 作用：控制报告 V3 主 lane 失败后是否尝试备用 lane。
REPORT_V3_FAILOVER_ENABLED = True
# 作用：设置报告 V3 切换失败备用通道时使用的 lane。
REPORT_V3_FAILOVER_LANE = "question"
# 作用：控制 failover 时是否强制草案与审稿共用同一 lane。
REPORT_V3_FAILOVER_FORCE_SINGLE_LANE = False
# 作用：控制审稿仅剩单个可修复问题时是否允许切备用 lane 再试。
REPORT_V3_FAILOVER_ON_SINGLE_ISSUE = True
# 作用：允许 deterministic fix bucket 类型的问题在少量聚集时也触发 failover。
REPORT_V3_FAILOVER_ON_DETERMINISTIC_BUCKET = True
# 作用：deterministic failover 最多允许的问题数，避免内容性失败误触发切换。
REPORT_V3_FAILOVER_DETERMINISTIC_MAX_ISSUES = 3
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
# 作用：控制报告 V3 是否在草案阶段先对证据做瘦身裁剪。
REPORT_V3_EVIDENCE_SLIM_ENABLED = True
# 作用：设置每个维度保留的证据条数上限。
REPORT_V3_EVIDENCE_DIM_QUOTA = 6
# 作用：控制证据列表是否按内容相似度做去重。
REPORT_V3_EVIDENCE_DEDUP_ENABLED = True
# 作用：设置证据进入报告主链路前要求的最低质量分数。
REPORT_V3_EVIDENCE_MIN_QUALITY = 0.2
# 作用：控制高优先级硬触发证据是否始终保留，不参与瘦身裁剪。
REPORT_V3_EVIDENCE_KEEP_HARD_TRIGGERED = True
# 作用：控制是否启用网关熔断保护，避免连续故障反复击穿同一 lane。
GATEWAY_CIRCUIT_BREAKER_ENABLED = True
# 作用：设置触发网关熔断所需的连续失败阈值。
GATEWAY_CIRCUIT_FAIL_THRESHOLD = 2
# 作用：设置网关熔断后的冷却时间（秒）。
GATEWAY_CIRCUIT_COOLDOWN_SECONDS = 120.0
# 作用：设置统计网关失败次数的时间窗口（秒）。
GATEWAY_CIRCUIT_FAILURE_WINDOW_SECONDS = 180.0

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
# 作用：设置提交答案后优先等待预生成结果的最长时间（秒）。
QUESTION_SUBMIT_PREFETCH_WAIT_SECONDS = 25.0
# 作用：设置问题结果幂等缓存的保留时长（秒）。
QUESTION_RESULT_CACHE_TTL_SECONDS = 180
# 作用：设置问题结果幂等缓存允许保存的最大条目数。
QUESTION_RESULT_CACHE_MAX_ENTRIES = 512
# 作用：设置会话 payload 热缓存的保留时长（秒）。
SESSION_PAYLOAD_CACHE_TTL_SECONDS = 4.0
# 作用：设置会话 payload 热缓存允许保存的最大条目数。
SESSION_PAYLOAD_CACHE_MAX_ENTRIES = 96
# 作用：设置并发命中同一预生成问题时等待首个结果的最长时间（秒）。
QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS = 1.8
# 作用：设置摘要异步更新的最小触发间隔（秒）。
SUMMARY_UPDATE_DEBOUNCE_SECONDS = 60
# 作用：设置搜索决策缓存的保留时长（秒）。
SEARCH_DECISION_CACHE_TTL_SECONDS = 900
# 作用：设置搜索决策缓存允许保存的最大条目数。
SEARCH_DECISION_CACHE_MAX_ENTRIES = 256
# 作用：设置搜索决策接口允许的最大并发请求数。
SEARCH_DECISION_MAX_INFLIGHT = 1
# 作用：控制搜索决策预取阶段是否仅使用规则判断，不直接触发模型调用。
SEARCH_DECISION_PREFETCH_RULE_ONLY = True
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

# ============ 服务默认值与任务并发 ===========
# 服务侧的产品默认值和并发预算放在这里，必要时可由 env 临时覆盖。
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
# 作用：设置前端估算报告队列等待时采用的单槽位平均耗时（秒）。
REPORT_GENERATION_ESTIMATED_SLOT_SECONDS = 55.0
# 作用：控制是否在后台预热报告方案 payload。
SOLUTION_PAYLOAD_PREWARM_ENABLED = True
# 作用：设置报告方案 payload 预热线程池的最大工作线程数。
SOLUTION_PAYLOAD_PREWARM_MAX_WORKERS = 2
# 作用：控制是否全局开放演示文稿生成能力。
PRESENTATION_GLOBAL_ENABLED = True

# ============ 对象存储默认值 ===========
# 演示文稿、导出资产等对象存储接入的默认值放在这里，便于研发统一切换实现。
# 作用：设置对象存储访问的 Endpoint 地址。
OBJECT_STORAGE_ENDPOINT = ""
# 作用：设置对象存储访问的 Region。
OBJECT_STORAGE_REGION = "us-east-1"
# 作用：设置对象存储使用的 Bucket。
OBJECT_STORAGE_BUCKET = ""
# 作用：设置对象存储使用的 Access Key ID。
OBJECT_STORAGE_ACCESS_KEY_ID = ""
# 作用：设置对象存储使用的 Secret Access Key。
OBJECT_STORAGE_SECRET_ACCESS_KEY = ""
# 作用：控制对象存储是否强制使用 path-style 访问。
OBJECT_STORAGE_FORCE_PATH_STYLE = False
# 作用：设置对象存储签名版本。
OBJECT_STORAGE_SIGNATURE_VERSION = "v4"
# 作用：设置对象存储内的统一前缀目录。
OBJECT_STORAGE_PREFIX = "deepvision"

# ============ 场景目录兼容默认值 ===========
# 兼容旧版“单一场景根目录”配置；留空时按内置/自定义目录各自解析。
# 作用：设置统一场景根目录，启用后会派生 builtin/custom 子目录。
SCENARIOS_DIR = ""

# ============ 功能默认值 ===========
# 排查体验和交互策略时，先看这一组。
# 作用：控制深度模式下是否跳过追问前的二次确认。
DEEP_MODE_SKIP_FOLLOWUP_CONFIRM = True

# ============ 联网搜索默认值 ===========
# 结果规模与超时留在 config，便于研发统一评估成本与时延。
# 作用：设置每次联网搜索最多返回的结果条数。
SEARCH_MAX_RESULTS = 3
# 作用：设置联网搜索请求的超时时间（秒）。
SEARCH_TIMEOUT = 10

# ============ 安全鉴权与登录策略 ===========
# 密钥、数据库路径、短信供应商等部署差异放 env；这里保留策略阈值默认值。
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
# 作用：设置微信 OAuth 接口调用超时时间（秒）。
WECHAT_OAUTH_TIMEOUT = 8.0
# 作用：设置微信登录 state 参数的有效期（秒）。
WECHAT_OAUTH_STATE_TTL_SECONDS = 300

# ============ 文档处理默认值 ===========
# 文档导入、格式转换和解析超时放在这里。
# 作用：设置文档转换或预处理链路的超时时间（秒）。
DOCUMENT_CONVERT_TIMEOUT_SECONDS = 60

# ============ 图片理解默认值 ===========
# 模型选择和上传约束属于产品默认值，可按环境临时覆盖。
# 作用：设置图片理解链路使用的视觉模型名称。
VISION_MODEL_NAME = "glm-4v-flash"
# 作用：设置允许上传到视觉模型的单张图片大小上限（MB）。
MAX_IMAGE_SIZE_MB = 10
# 作用：设置视觉链路允许处理的图片文件扩展名列表。
SUPPORTED_IMAGE_TYPES = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

# ============ Refly 工作流默认值 ===========
# 作用：设置 Refly 工作流请求的超时时间（秒）。
REFLY_TIMEOUT = 30
# 作用：设置 Refly 工作流轮询的最长等待时间（秒）。
REFLY_POLL_TIMEOUT = 600
# 作用：设置 Refly 工作流轮询状态的时间间隔（秒）。
REFLY_POLL_INTERVAL = 2.0

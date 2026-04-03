"""
Deep Vision 策略配置

使用说明：
1. 本文件负责当前环境的策略默认值：模型分工、链路阈值、缓存预算、报告/问题生成策略
2. 密钥、网关地址、部署路径和运维开关请写入 .env
3. 本文件已纳入版本库，只保留非敏感策略默认值，不要写入真实凭证
"""

# ============ 模型角色分工 ===========
# 先看这一组，就能知道问题、报告、摘要、评分各自走哪个模型。
# 作用：设置全局默认模型名，未单独指定 lane 模型时会回落到这里。
MODEL_NAME = "doubao-seed-2-0-pro"  # 默认主模型（问题链路）
# 作用：设置问题生成链路使用的模型名称。
QUESTION_MODEL_NAME = MODEL_NAME
# 作用：设置深度访谈模式下 question lane 的专用模型名称。
QUESTION_MODEL_NAME_DEEP = "deepseek-ai/DeepSeek-V3.2"
# 作用：设置报告主链路使用的模型名称。
REPORT_MODEL_NAME = "deepseek-ai/DeepSeek-V3.2"
# 作用：设置报告草案阶段使用的模型名称。
REPORT_DRAFT_MODEL_NAME = REPORT_MODEL_NAME
# 作用：设置报告审稿阶段使用的模型名称。
REPORT_REVIEW_MODEL_NAME = "doubao-seed-2-0-pro"
# 作用：设置摘要链路使用的模型名称。
SUMMARY_MODEL_NAME = "deepseek-ai/DeepSeek-V3.2"
# 作用：设置搜索决策链路使用的模型名称。
SEARCH_DECISION_MODEL_NAME = "doubao-seed-2.0-code"
# 作用：设置评分链路使用的模型名称。
ASSESSMENT_MODEL_NAME = "deepseek-ai/DeepSeek-V3.2"

# ============ AI 客户端通用策略 ===========
# 客户端启动方式与接入开关请放在 .env；这里只保留非敏感运行默认值。
# 作用：设置 AI 客户端在 SDK 层允许的最大重试次数。
AI_CLIENT_MAX_RETRIES = 0

# ============ AI 通用运行默认值 ===========
# 通用运行限制放在 config，必要时可由 env 临时覆盖。
# 作用：设置通用 AI 调用的默认超时时间（秒）。
API_TIMEOUT = 120.0
# 作用：设置未单独指定链路时，单次 AI 调用默认允许输出的最大 token 数。
MAX_TOKENS_DEFAULT = 4000
# 作用：设置问题生成链路单次响应允许输出的最大 token 数。
MAX_TOKENS_QUESTION = 2200
# 作用：设置报告主生成链路单次响应允许输出的最大 token 数。
MAX_TOKENS_REPORT = 8000
# 作用：设置摘要链路单次响应允许输出的最大 token 数。
MAX_TOKENS_SUMMARY = 600
# 作用：设置搜索决策首轮轻量判断阶段允许输出的最大 token 数。
SEARCH_DECISION_FIRST_MAX_TOKENS = 220
# 作用：设置搜索决策重试阶段允许输出的最大 token 数。
SEARCH_DECISION_RETRY_MAX_TOKENS = 420
# 作用：设置单题评分调用允许输出的最大 token 数。
ASSESSMENT_SCORE_MAX_TOKENS = 160
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
# 作用：设置问题快档在轻量参考资料模式下的请求超时时间（秒）。
QUESTION_FAST_REFERENCE_TIMEOUT = 15.0
# 作用：设置轻量参考资料模式下 question lane 的请求超时时间（秒）。
QUESTION_FAST_REFERENCE_QUESTION_TIMEOUT = QUESTION_FAST_REFERENCE_TIMEOUT
# 作用：设置轻量参考资料模式下 report lane 的请求超时时间（秒）。
QUESTION_FAST_REFERENCE_REPORT_TIMEOUT = max(14.0, QUESTION_FAST_REFERENCE_QUESTION_TIMEOUT - 1.0)
# 作用：控制问题生成是否先尝试快档。
QUESTION_FAST_PATH_ENABLED = True
# 作用：设置问题快档调用的超时时间（秒）。
QUESTION_FAST_TIMEOUT = 8.0
# 作用：设置问题快档调用允许输出的最大 token 数。
QUESTION_FAST_MAX_TOKENS = 900
# 作用：设置轻量参考资料模式下 question lane 允许输出的最大 token 数。
QUESTION_FAST_REFERENCE_QUESTION_MAX_TOKENS = max(QUESTION_FAST_MAX_TOKENS, 1000)
# 作用：设置轻量参考资料模式下 report lane 允许输出的最大 token 数。
QUESTION_FAST_REFERENCE_REPORT_MAX_TOKENS = min(
    MAX_TOKENS_QUESTION,
    max(QUESTION_FAST_REFERENCE_QUESTION_MAX_TOKENS, 1100),
)
# 作用：设置仍允许走问题快档的 Prompt 最大字符数。
QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS = 2200
# 作用：设置轻量参考资料模式可消耗的参考资料字符预算。
QUESTION_FAST_LIGHT_DOC_BUDGET = min(MAX_TOTAL_DOCS, max(1200, QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS))
# 作用：设置轻量参考资料模式下扩展 Prompt 的最大字符数。
QUESTION_FAST_REFERENCE_PROMPT_MAX_CHARS = max(
    QUESTION_FAST_LIGHT_PROMPT_MAX_CHARS,
    QUESTION_FAST_LIGHT_DOC_BUDGET + 900,
)
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
QUESTION_FAST_ADAPTIVE_COOLDOWN_SECONDS = 180.0
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
QUESTION_HEDGED_DELAY_SECONDS = 1.2
# 作用：设置问题竞速时备用通道使用的 lane。
QUESTION_HEDGED_SECONDARY_LANE = "report"
# 作用：高取证强度问题的主通道，默认固定走 question lane。
QUESTION_HIGH_EVIDENCE_PRIMARY_LANE = "question"
# 作用：高取证强度问题的备用通道，默认走 report lane，禁用 summary 竞速。
QUESTION_HIGH_EVIDENCE_SECONDARY_LANE = "report"
# 作用：高取证强度问题是否禁用基于历史时延/成功率的动态 lane 晋升。
QUESTION_HIGH_EVIDENCE_DISABLE_DYNAMIC_LANE = True
# 作用：高取证强度问题是否允许继续走快档。
QUESTION_HIGH_EVIDENCE_FAST_PATH_ENABLED = True
# 作用：高取证强度问题是否允许直接并发备用通道，默认关闭，优先单发失败后补发。
QUESTION_HIGH_EVIDENCE_HEDGED_ENABLED = True
# 作用：是否启用主通道失败后的备用通道补发。
QUESTION_HEDGE_FAILURE_FALLBACK_ENABLED = True
# 作用：是否仅允许真正阻塞 shadow draft 的题目启用并发竞速。
QUESTION_HEDGE_REQUIRE_SHADOW_BLOCKER = False
# 作用：轻量参考资料模式是否绕过问题竞速预算限制。
QUESTION_FAST_REFERENCE_HEDGE_BYPASS_BUDGET = True
# 作用：单个会话内允许发生问题并发竞速的总次数预算。
QUESTION_SESSION_HEDGE_BUDGET = 4
# 作用：单个维度内允许发生问题并发竞速的次数预算。
QUESTION_DIMENSION_HEDGE_BUDGET = 1
# 作用：控制只有主备客户端不同才启用问题竞速。
QUESTION_HEDGED_ONLY_WHEN_DISTINCT_CLIENT = False
# 作用：控制是否启用问题竞速延迟的自适应策略。
QUESTION_HEDGE_ADAPTIVE_ENABLED = True
# 作用：设置问题竞速自适应策略生效所需的最小样本数。
QUESTION_HEDGE_ADAPTIVE_MIN_SAMPLES = 8
# 作用：设置问题竞速自适应延迟计算采用的耗时分位点。
QUESTION_HEDGE_ADAPTIVE_PERCENTILE = 0.8
# 作用：设置问题竞速自适应延迟相对主请求超时的比例上限。
QUESTION_HEDGE_ADAPTIVE_TIMEOUT_RATIO = 0.45
# 作用：按 lane 覆盖问题快档超时时间。
QUESTION_FAST_TIMEOUT_BY_LANE = {"question": 8.0, "summary": 6.0, "report": 12.0, "search_decision": 6.0}
# 作用：按 lane 覆盖问题快档最大 token 数。
QUESTION_FAST_MAX_TOKENS_BY_LANE = {"question": 900, "summary": 600, "report": 1200, "search_decision": 420}

# 作用：控制发布期问题链路是否默认启用保守降档策略。
QUESTION_RELEASE_CONSERVATIVE_MODE = False
# 作用：按 lane 覆盖问题全量档超时时间。
QUESTION_FULL_TIMEOUT_BY_LANE = {"question": 18.0, "summary": 12.0, "report": 45.0, "search_decision": 12.0}
# 作用：按 lane 覆盖问题全量档最大 token 数。
QUESTION_FULL_MAX_TOKENS_BY_LANE = {"question": 1500, "summary": 900, "report": 1800, "search_decision": 420}
# 作用：按 lane 覆盖问题竞速的备用通道启动延迟。
QUESTION_HEDGE_DELAY_BY_LANE = {"question": 1.2, "summary": 0.8, "report": 1.6, "search_decision": 0.8}
# 作用：设置快速/标准/深度三档模式进入 prompt 的最大盲区数量。
INTERVIEW_MODE_MAX_BLINDSPOTS_QUICK = 1
INTERVIEW_MODE_MAX_BLINDSPOTS_STANDARD = 2
INTERVIEW_MODE_MAX_BLINDSPOTS_DEEP = 4
# 作用：设置切换访谈模式时默认视为关键维度的维度 ID 列表。
INTERVIEW_MODE_CRITICAL_DIMENSION_IDS = [
    "tech_constraints",
    "project_constraints",
    "target_architecture",
    "risks",
]
# 作用：设置切换访谈模式时用于识别关键维度的关键词列表。
INTERVIEW_MODE_CRITICAL_DIMENSION_KEYWORDS = ["技术", "约束", "风险", "验收", "目标", "架构", "集成"]
# 作用：设置标准/深度模式将 medium 证据提升为 high 所需的强信号数量。
QUESTION_HIGH_EVIDENCE_PROMOTION_MIN_SIGNALS_STANDARD = 3
QUESTION_HIGH_EVIDENCE_PROMOTION_MIN_SIGNALS_DEEP = 2
# 作用：设置三档模式对 AI 推荐的最低置信度要求。
AI_RECOMMENDATION_MIN_CONFIDENCE_QUICK = "high"
AI_RECOMMENDATION_MIN_CONFIDENCE_STANDARD = "medium"
AI_RECOMMENDATION_MIN_CONFIDENCE_DEEP = "medium"
# 作用：控制深度模式下 AI 推荐是否必须携带证据。
AI_RECOMMENDATION_REQUIRE_EVIDENCE_DEEP = True

# ============ 报告生成链路 ===========
# 集中放置报告 V3 的档位、双阶段、质量门与失败兜底策略。
# 留空为 `None` 的高级参数，会由 `server.py` 按 `balanced/quality` 档位自动补默认值。
# 作用：设置报告 V3 默认使用的运行档位。
REPORT_V3_PROFILE = "balanced"
# 作用：设置报告链路默认调用超时时间（秒）。
REPORT_API_TIMEOUT = 240.0
# 作用：设置报告草案阶段的调用超时时间（秒）。
REPORT_DRAFT_API_TIMEOUT = 120.0
# 作用：设置报告审稿阶段的调用超时时间（秒）。
REPORT_REVIEW_API_TIMEOUT = 60.0
# 作用：设置报告草案阶段允许生成的最大 token 数，留空则按档位默认。
REPORT_V3_DRAFT_MAX_TOKENS = 5200
# 作用：设置报告草案阶段可注入的事实证据上限。
REPORT_V3_DRAFT_FACTS_LIMIT = 30
# 作用：设置报告草案重试降载后保留的最小事实证据数。
REPORT_V3_DRAFT_MIN_FACTS_LIMIT = 18
# 作用：设置报告草案阶段的重试次数。
REPORT_V3_DRAFT_RETRY_COUNT = None
# 作用：设置报告草案阶段每轮重试前的退避等待时间（秒）。
REPORT_V3_DRAFT_RETRY_BACKOFF_SECONDS = None
# 作用：设置草案为空时是否立即失败；`None` 表示按档位默认。
REPORT_V3_FAST_FAIL_ON_DRAFT_EMPTY = None
# 作用：设置报告审稿阶段允许生成的最大 token 数。
REPORT_V3_REVIEW_MAX_TOKENS = None
# 作用：设置报告 V3 基础审稿轮数。
REPORT_V3_REVIEW_BASE_ROUNDS = 2
# 作用：设置 quality 档额外补修轮数。
REPORT_V3_QUALITY_FIX_ROUNDS = 1
# 作用：设置报告 V3 至少执行的审稿轮数，0 表示按档位默认。
REPORT_V3_MIN_REVIEW_ROUNDS = 0
# 作用：控制报告 V3 是否启用草案与审稿双阶段流程。
REPORT_V3_DUAL_STAGE_ENABLED = True
# 作用：控制发布期报告链路是否默认启用保守降档策略。
REPORT_V3_RELEASE_CONSERVATIVE_MODE = False
# 作用：控制发布期保守模式下是否允许草案阶段切到备用 lane。
REPORT_V3_ALLOW_DRAFT_ALTERNATE_LANE_IN_RELEASE_CONSERVATIVE = False
# 作用：控制发布期保守模式下是否跳过模型审稿。
REPORT_V3_SKIP_MODEL_REVIEW_IN_RELEASE_CONSERVATIVE = True
# 作用：控制发布期报告链路是否在连续超时或熔断时直接短路到标准回退。
REPORT_V3_RELEASE_SHORT_CIRCUIT_ENABLED = False
# 作用：控制发布期保守模式下是否强制草案主链路保持在主 lane。
REPORT_V3_DRAFT_STRICT_PRIMARY_LANE_IN_RELEASE_CONSERVATIVE = True
# 作用：设置发布期短路回退触发所需的超时次数阈值。
REPORT_V3_RELEASE_SHORT_CIRCUIT_TIMEOUT_THRESHOLD = 2
# 作用：设置发布期短路回退时使用的 fallback lane。
REPORT_V3_RELEASE_SHORT_CIRCUIT_FALLBACK_LANE = "report_review"
# 作用：设置发布期短路回退时的调用超时时间（秒）。
REPORT_V3_RELEASE_SHORT_CIRCUIT_FALLBACK_TIMEOUT = 60.0
# 作用：设置发布期短路回退时允许输出的最大 token 数。
REPORT_V3_RELEASE_SHORT_CIRCUIT_FALLBACK_MAX_TOKENS = 2200
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
REPORT_V3_REVIEW_REPAIR_MAX_TOKENS = 1800
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
PREFETCH_QUESTION_FAST_TIMEOUT = 8.0
# 作用：设置后台预生成问题快档允许输出的最大 token 数。
PREFETCH_QUESTION_FAST_MAX_TOKENS = 700
# 作用：设置后台预生成问题竞速的备用通道启动延迟。
PREFETCH_QUESTION_HEDGE_DELAY_SECONDS = 1.8
# 作用：设置后台预生成问题时优先使用的 lane。
PREFETCH_QUESTION_PRIMARY_LANE = "question"
# 作用：设置后台预生成问题时备用使用的 lane。
PREFETCH_QUESTION_SECONDARY_LANE = "report"
# 作用：设置问题结果幂等缓存的保留时长（秒）。
QUESTION_RESULT_CACHE_TTL_SECONDS = 180
# 作用：设置问题结果幂等缓存允许保存的最大条目数。
QUESTION_RESULT_CACHE_MAX_ENTRIES = 512
# 作用：设置并发命中同一预生成问题时等待首个结果的最长时间（秒）。
QUESTION_PREFETCH_INFLIGHT_WAIT_SECONDS = 1.8
# 作用：设置提交答案后优先等待预生成结果的最长时间（秒）。
QUESTION_SUBMIT_PREFETCH_WAIT_SECONDS = 3.0
# 作用：设置摘要异步更新的最小触发间隔（秒）。
SUMMARY_UPDATE_DEBOUNCE_SECONDS = 60
# 作用：设置搜索决策缓存的保留时长（秒）。
SEARCH_DECISION_CACHE_TTL_SECONDS = 900
# 作用：设置搜索决策缓存允许保存的最大条目数。
SEARCH_DECISION_CACHE_MAX_ENTRIES = 256
# 作用：设置并发命中同一搜索决策时等待首个结果的最长时间（秒）。
SEARCH_DECISION_INFLIGHT_WAIT_SECONDS = 10.0
# 作用：设置搜索决策链路允许并发处理的最大请求数。
SEARCH_DECISION_MAX_INFLIGHT = 1
# 作用：控制搜索决策预生成是否只使用规则判断，不直接发模型请求。
SEARCH_DECISION_PREFETCH_RULE_ONLY = True
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
# 作用：设置会话详情 payload 缓存的保留时长（秒）。
SESSION_PAYLOAD_CACHE_TTL_SECONDS = 4.0
# 作用：设置会话详情 payload 缓存允许保存的最大条目数。
SESSION_PAYLOAD_CACHE_MAX_ENTRIES = 96
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
# 作用：设置问题生成接口允许并发处理的最大请求数。
QUESTION_GENERATION_MAX_INFLIGHT = 4
# 作用：设置问题生成队列允许积压的最大请求数。
QUESTION_GENERATION_MAX_PENDING = 10
# 作用：设置问题生成排队时允许等待空闲槽位的最长时间（秒）。
QUESTION_GENERATION_QUEUE_WAIT_SECONDS = 8.0
# 作用：设置问题生成接口过载时返回的建议重试时间（秒）。
QUESTION_GENERATION_RETRY_AFTER_SECONDS = 2
# 作用：设置报告生成任务池的最大工作线程数。
REPORT_GENERATION_MAX_WORKERS = 2
# 作用：设置报告生成任务队列允许积压的最大任务数。
REPORT_GENERATION_MAX_PENDING = 16
# 作用：设置报告生成队列繁忙时建议的重试时间（秒）。
REPORT_GENERATION_QUEUE_RETRY_AFTER_SECONDS = 3
# 作用：设置报告生成队列估算单槽位耗时（秒），用于前端估计等待时长。
REPORT_GENERATION_ESTIMATED_SLOT_SECONDS = 55.0
# 作用：控制是否在后台预热报告方案 payload。
SOLUTION_PAYLOAD_PREWARM_ENABLED = True
# 作用：设置报告方案 payload 预热线程池的最大工作线程数。
SOLUTION_PAYLOAD_PREWARM_MAX_WORKERS = 2

# ============ 场景目录兼容默认值 ===========
# 兼容旧版“单一场景根目录”配置；留空时按内置/自定义目录各自解析。
# 作用：设置统一场景根目录，启用后会派生 builtin/custom 子目录。
SCENARIOS_DIR = ""

# ============ 功能默认值 ===========
# 排查体验和交互策略时，先看这一组。
# 作用：控制深度模式下是否跳过追问前的二次确认。
DEEP_MODE_SKIP_FOLLOWUP_CONFIRM = True
# 作用：控制演示文稿相关能力是否默认启用。
PRESENTATION_GLOBAL_ENABLED = True

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
SMS_MAX_SEND_PER_PHONE_PER_DAY = 20
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

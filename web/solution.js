const SOLUTION_ASSET_VERSION = '20260314-solution-v30';
const SOLUTION_API_BASE = `${window.location.origin}/api`;
const SOLUTION_SOURCE_MODE_LABELS = {
    structured_sidecar: '结构化快照',
    legacy_markdown: '历史兼容',
    degraded: '降级视图'
};
const SOLUTION_NAV_ITEMS = [
    { id: 'overview', label: '方案概览' },
    { id: 'comparison', label: '系统对比' },
    { id: 'solutions', label: '落地方案' },
    { id: 'integration', label: '系统集成' },
    { id: 'knowledge', label: '知识统一' },
    { id: 'flywheel', label: '数据联动' },
    { id: 'value', label: '预期价值' },
    { id: 'fit', label: '为什么适合' }
];
const SOLUTION_BUSINESS_FOCUS_REPLACEMENTS = [
    ['MLOps/LLMOps自动化平台', 'AI工程底座'],
    ['MLOps/LLMOps平台', 'AI工程底座'],
    ['MLOps平台', 'AI工程底座'],
    ['LLMOps平台', 'AI工程底座'],
    ['分层解耦架构落地', '分层架构'],
    ['分层解耦架构', '分层架构'],
    ['规格驱动接口治理', '接口治理'],
    ['规格驱动化接口治理', '接口治理'],
    ['自动化迁移工具链建设', '迁移工具链'],
    ['混合云架构', '混合云能力'],
    ['混合云资源调度能力', '混合云能力'],
    ['企业微信 + ERP/CRM 全面打通', '系统打通']
];
const SOLUTION_BUSINESS_SENTENCE_REPLACEMENTS = [
    ['云厂商托管AI服务', '托管AI服务'],
    ['模型训练-验证-部署-监控全链路自动化', '训练、部署和监控统一'],
    ['模型层/推理层/网关层', '模型、推理和网关三层'],
    ['建立OpenAPI/gRPC契约，通过代码生成严格管控层间接口', '建立统一接口契约，用自动化门禁锁定层间边界'],
    ['OpenAPI/gRPC契约规范', '统一接口契约'],
    ['代码生成工具与CI门禁', '代码生成和自动化门禁'],
    ['公私云动态调度与秒级故障转移', '公私云统一调度和快速切换'],
    ['核心模型私有化+弹性推理公有云，智能路由按延迟/成本/负载动态调度', '核心模型私有化，弹性推理走公有云，统一调度延迟、成本和负载'],
    ['跨框架转换流水线', '跨框架迁移流水线'],
    ['自动化精度验证与性能基线对比能力', '自动化验证和性能基线能力'],
    ['降低对AI平台工程师/SRE的强依赖', '降低对少数专家的强依赖'],
    ['高质量方案页必须解释为什么推荐这条路径，而不是只给一个结果。', '当前需要把推荐路径、边界和取舍讲清楚。'],
    ['高质量提案页不只讲这次怎么做，还要讲每次执行如何反哺后续项目和知识资产。', '让本次试点结论持续沉淀，后续方案才会越做越快。'],
    ['样例页里最强的部分不是某一张图，而是“为什么这些模块会相互增强”的解释。', '关键模块之间必须形成真实联动，方案才能持续放大。'],
    ['样例页真正强的最后一击，是把价值、适配性和边界同时摆出来，帮助管理层完成决策收束。', '价值、适配性和边界要同时成立，管理层才能完成决策。'],
    ['页面最后必须回答“为什么是你、为什么是现在、为什么是这条路”，否则说服力会断掉。', '最后需要把适配性、时机和路径选择一次讲清。'],
    ['如果各模块之间没有真正联动，这套方案就只是并排摆放的功能列表，不是体系。', '如果模块之间不能回流协同，这套方案就无法持续放大。'],
    ['如果每次访谈和试点都不能沉淀成可复用资产，方案页再漂亮也只是一次性交付。', '如果试点结论不能沉淀复用，后续项目还会重复踩坑。'],
    ['已有足够结构化素材支撑高级提案页', '已有足够事实支撑试点方案'],
    ['当前已有完整结构化素材和页面骨架渲染上下文。', '当前访谈结论、方案和行动已经足以支撑试点判断。'],
    ['方案页再漂亮也只是一次性交付。', '否则这次试点仍会停留在一次性交付。']
];
const SOLUTION_HARD_TECH_TERMS = ['MLOps', 'LLMOps', 'TensorFlow', 'PyTorch', 'ONNX', 'OpenAPI', 'gRPC', 'SRE', 'CI门禁', 'P99', '静态图', '动态调试'];

function solutionEscapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function solutionNormalizeList(value) {
    return Array.isArray(value) ? value.filter(Boolean) : [];
}

function solutionShortText(value, maxLength = 72) {
    const normalized = String(value || '').trim().replace(/\s+/g, ' ');
    if (!normalized) return '';
    if (normalized.length <= maxLength) return normalized;
    return `${normalized.slice(0, maxLength).trim()}...`;
}

function solutionBusinessReplace(value) {
    let text = String(value || '').trim();
    if (!text) return '';
    SOLUTION_BUSINESS_FOCUS_REPLACEMENTS.forEach(([source, target]) => {
        text = text.split(source).join(target);
    });
    SOLUTION_BUSINESS_SENTENCE_REPLACEMENTS.forEach(([source, target]) => {
        text = text.split(source).join(target);
    });
    text = text.replace(/证据\s*Q[\d、, ]+/gi, '');
    text = text.replace(/Q\d+(?:、Q\d+)*/gi, '');
    text = text.replace(/[·•]+/g, '，');
    return text.trim();
}

function solutionHasHardTechTerms(value) {
    const text = String(value || '').toLowerCase();
    return SOLUTION_HARD_TECH_TERMS.some((term) => text.includes(term.toLowerCase()));
}

function solutionLooksLikePlaceholderTitle(value) {
    const text = String(value || '').toLowerCase();
    return ['why_now', 'comparison', 'blueprint', 'workstreams', 'integration', 'roadmap', 'value_fit'].some((token) => text.includes(token));
}

function solutionBusinessFocusLabel(value, maxLength = 18) {
    let text = solutionBusinessReplace(value);
    if (!text) return '';
    const quoted = text.match(/[「"]([^」"]{2,24})[」"]/);
    if (quoted?.[1]) text = quoted[1];
    text = text.replace(/（[^）]{0,24}）/g, '').replace(/\([^)]{0,24}\)/g, '');
    text = text.replace(/^精准切入[「"]?/g, '');
    text = text.replace(/[」"]?的?闭环试点路径$/g, '');
    text = text.replace(/[」"]?的?闭环试点$/g, '');
    text = text.replace(/(优先建设路径|优先路径|优先建设|建设路径|落地方案|双核心落地|全链路|落地|方案|路径|工作流|模块)$/g, '').trim();
    return solutionShortText(text, maxLength);
}

function solutionBusinessSentence(value, maxLength = 96) {
    const text = solutionBusinessReplace(value).replace(/\s+/g, ' ').trim();
    return solutionShortText(text, maxLength);
}

function solutionShouldUseContentFallback(value, maxLength = 96) {
    const raw = String(value || '').trim();
    if (!raw) return true;
    return solutionHasHardTechTerms(raw) || solutionShouldUseNarrativeFallback(raw) || raw.length > maxLength * 1.4;
}

function solutionBusinessParagraph(value, fallback = '', maxLength = 120) {
    const raw = String(value || '').trim();
    const fallbackText = solutionBusinessSentence(fallback, maxLength);
    if (!raw) return fallbackText;
    const candidate = solutionBusinessSentence(raw, maxLength);
    if (solutionShouldUseContentFallback(raw, maxLength) && fallbackText) return fallbackText;
    return candidate || fallbackText;
}

function solutionBusinessHeading(value, fallback = '', maxLength = 72) {
    const raw = String(value || '').trim();
    const fallbackText = solutionBusinessSentence(fallback, maxLength);
    if (!raw) return fallbackText;
    if (solutionHasHardTechTerms(raw) || solutionLooksLikePlaceholderTitle(raw) || solutionShouldUseNarrativeFallback(raw) || raw.length > maxLength + 8) {
        return fallbackText || solutionBusinessSentence(raw, maxLength);
    }
    return solutionBusinessSentence(raw, maxLength) || fallbackText;
}

function solutionBusinessMetricLabel(value, fallback = '关键指标') {
    const label = solutionBusinessFocusLabel(value, 18) || solutionShortText(fallback, 18) || '关键指标';
    if (/(建设节奏|推进度|落地率|效率)$/.test(label)) return label;
    if (label.includes('底座')) return `${label}建设节奏`;
    if (label.includes('架构')) return `${label}推进度`;
    if (label.includes('治理')) return `${label}落地率`;
    if (label.includes('迁移')) return `${label}效率`;
    return label;
}

function solutionBusinessMetricValue(value, maxLength = 40) {
    let text = solutionBusinessSentence(value, maxLength * 2);
    if (!text) return '';
    [
        ['完成平台选型与POC', '完成平台POC'],
        ['完成核心流水线搭建', '上线核心流水线'],
        ['模型上线周期从周级降至天级', '上线周期降到天级'],
        ['人工干预环节减少70%', '人工干预减少70%'],
        ['核心判断能直接回溯到样本、风险和执行动作', '核心判断可直接回溯'],
        ['形成可复用的模块、路径与风险边界', '形成统一提案资产'],
        ['支持管理层、业务和技术团队共用一套判断框架', '支持跨团队共用判断框架']
    ].forEach(([source, target]) => {
        text = text.split(source).join(target);
    });
    return solutionShortText(text, maxLength);
}

function solutionBusinessMetricNote(value, maxLength = 56) {
    let text = solutionBusinessSentence(value, maxLength * 2);
    if (!text) return '';
    [
        ['关键入口和核心角色可按阶段投入', '前提：关键角色持续投入'],
        ['首轮试点聚焦单一高信号场景', '前提：试点范围保持聚焦'],
        ['样本真实性与触发时机控制到位', '前提：试点样本真实可控'],
        ['关键问题能稳定命中核心访谈对象', '前提：核心问题持续命中'],
        ['关键事实与阶段结论持续沉淀到统一台账', '前提：结论持续沉淀'],
        ['试点结论能沉淀为统一提案资产', '前提：试点结论持续沉淀']
    ].forEach(([source, target]) => {
        text = text.split(source).join(target);
    });
    if (!text.startsWith('前提：')) text = `前提：${text}`;
    return solutionShortText(text, maxLength);
}

function solutionBusinessMetaLabel(value, maxLength = 72) {
    const raw = String(value || '');
    const refs = raw.match(/Q\d+/gi);
    if (refs?.length) return solutionShortText(Array.from(new Set(refs.map((item) => item.toUpperCase()))).slice(0, 4).join(' · '), maxLength);
    return solutionShortText(solutionBusinessSentence(raw, maxLength), maxLength);
}

function solutionShouldUseNarrativeFallback(value) {
    const text = String(value || '').trim();
    if (!text) return true;
    return [
        '不是把内容堆满',
        '没有回流机制',
        '高级方案页的最后一章',
        '终结碎片化内容堆积',
        '每个模块都应反哺整个方案体系',
        '把「',
        '双核心落地',
        '全链路',
        '优先建设',
        '闭环试点',
        '结构化素材',
        '高级提案页',
    ].some((token) => text.includes(token));
}

function solutionPercent(value) {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return '0%';
    return `${Math.max(0, Math.round(numeric * 100))}%`;
}

function solutionCellText(value) {
    if (Array.isArray(value)) return value.map((item) => solutionCellText(item)).filter(Boolean).join('、');
    if (value === null || value === undefined) return '';
    return String(value).trim();
}

function solutionGetReportName() {
    const params = new URLSearchParams(window.location.search || '');
    return String(params.get('report') || '').trim();
}

function solutionSetState(title, text, badge = '提示') {
    const card = document.getElementById('solution-state-card');
    if (!card) return;
    card.innerHTML = `
        <div class="solution-state-badge">${solutionEscapeHtml(badge)}</div>
        <h1 class="solution-state-title">${solutionEscapeHtml(title)}</h1>
        <p class="solution-state-text">${solutionEscapeHtml(text)}</p>
    `;
}

async function solutionApiCall(endpoint) {
    const separator = endpoint.includes('?') ? '&' : '?';
    const url = `${SOLUTION_API_BASE}${endpoint}${separator}v=${encodeURIComponent(SOLUTION_ASSET_VERSION)}&_=${Date.now()}`;
    const response = await fetch(url, {
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' }
    });

    let payload = null;
    try {
        payload = await response.json();
    } catch (error) {
        payload = null;
    }

    if (!response.ok) {
        const err = new Error(payload?.error || payload?.detail || `HTTP ${response.status}`);
        err.status = response.status;
        throw err;
    }
    return payload || {};
}

function solutionExtractRefs(value) {
    if (typeof value !== 'string') return [];
    const matches = value.toUpperCase().match(/Q\d+/g);
    return matches ? matches : [];
}

function solutionCollectRefs(...values) {
    const refs = [];
    const seen = new Set();
    const visit = (entry) => {
        if (!entry) return;
        if (Array.isArray(entry)) {
            entry.forEach(visit);
            return;
        }
        if (typeof entry === 'string') {
            solutionExtractRefs(entry).forEach((ref) => {
                if (!seen.has(ref)) {
                    seen.add(ref);
                    refs.push(ref);
                }
            });
            return;
        }
        if (typeof entry === 'object') {
            const nestedRefs = entry.evidenceRefs || entry.evidence_refs || [];
            visit(nestedRefs);
        }
    };
    values.forEach(visit);
    return refs;
}

function solutionUniqueBy(items, getKey) {
    const result = [];
    const seen = new Set();
    solutionNormalizeList(items).forEach((item, index) => {
        const key = String(getKey(item, index) || '').trim();
        if (!key || seen.has(key)) return;
        seen.add(key);
        result.push(item);
    });
    return result;
}

function solutionCompactStrings(values, maxItems = 4, maxLength = 72) {
    const result = [];
    const seen = new Set();
    solutionNormalizeList(Array.isArray(values) ? values : [values]).forEach((value) => {
        const text = solutionShortText(solutionBusinessSentence(solutionCellText(value), maxLength), maxLength);
        if (!text) return;
        const key = text.toLowerCase().replace(/\s+/g, '');
        if (seen.has(key)) return;
        seen.add(key);
        result.push(text);
    });
    return result.slice(0, maxItems);
}

function solutionNormalizeMetricItem(item) {
    if (!item || typeof item !== 'object') return null;
    const label = solutionBusinessMetricLabel(item.label || item.metric || '', '关键指标');
    const value = solutionBusinessMetricValue(item.value || item.target || item.range || '', 40);
    if (!label || !value) return null;
    const note = solutionBusinessMetricNote(item.note || item.description || solutionNormalizeList(item.assumptions)[0] || '', 56);
    const delta = solutionBusinessMetricValue(item.delta || item.range || '', 28);
    return {
        label,
        value,
        note,
        delta,
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionNormalizeCardItem(item) {
    if (!item || typeof item !== 'object') return null;
    const rawTitle = item.title || item.name || '';
    const title = solutionHasHardTechTerms(rawTitle) || String(rawTitle || '').length > 24
        ? solutionBusinessFocusLabel(rawTitle, 24)
        : solutionBusinessHeading(rawTitle, '', 42);
    const desc = solutionBusinessSentence(item.desc || item.description || item.summary || item.detail || '', 140);
    if (!title || !desc) return null;
    return {
        title,
        desc,
        tag: solutionShortText(item.tag || item.badge || item.owner || '', 18),
        meta: solutionBusinessMetaLabel(item.meta || item.detail || '', 88),
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionNormalizeChapter(chapter) {
    if (!chapter || typeof chapter !== 'object') return null;
    return {
        id: String(chapter.id || '').trim(),
        navLabel: String(chapter.navLabel || chapter.nav_label || chapter.label || chapter.title || '章节').trim(),
        eyebrow: String(chapter.eyebrow || chapter.kicker || '').trim(),
        title: solutionBusinessHeading(chapter.title || chapter.label || '', '', 88),
        judgement: solutionBusinessSentence(chapter.judgement || chapter.description || '', 180),
        summary: solutionBusinessSentence(chapter.summary || '', 180),
        layout: String(chapter.layout || 'text').trim(),
        metrics: solutionNormalizeList(chapter.metrics).map(solutionNormalizeMetricItem).filter(Boolean),
        cards: solutionNormalizeList(chapter.cards).map(solutionNormalizeCardItem).filter(Boolean),
        diagram: chapter.diagram && typeof chapter.diagram === 'object' ? chapter.diagram : null,
        cta: chapter.cta && typeof chapter.cta === 'object' ? chapter.cta : null,
        evidenceRefs: solutionCollectRefs(chapter)
    };
}

function solutionNormalizeAudienceProfile(value) {
    if (!value || typeof value !== 'object') return null;
    const key = solutionShortText(value.key || value.audience || '', 24).toLowerCase();
    const label = solutionShortText(value.label || '', 24);
    if (!key && !label) return null;
    return {
        key: key || 'decision_maker',
        label: label || '决策层视角',
        reasoning: solutionShortText(value.reasoning || '', 96),
        proposalGoal: solutionShortText(value.proposal_goal || value.proposalGoal || '', 24)
    };
}

function solutionNormalizeComparisonMatrix(value) {
    if (!value || typeof value !== 'object') return null;
    const rows = solutionNormalizeList(value.rows).map((row) => {
        if (!row || typeof row !== 'object') return null;
        const dimension = solutionShortText(row.dimension || '', 24);
        if (!dimension) return null;
        return {
            dimension,
            winner: solutionShortText(row.winner || '', 28),
            cells: solutionNormalizeList(row.cells).map((cell) => {
                if (!cell || typeof cell !== 'object') return null;
                return {
                    option: solutionShortText(cell.option || '', 28),
                    decision: solutionShortText(cell.decision || '', 16).toLowerCase(),
                    badge: solutionShortText(cell.badge || '', 8),
                    reason: solutionShortText(cell.reason || '', 48)
                };
            }).filter(Boolean)
        };
    }).filter(Boolean);
    if (!rows.length) return null;
    return {
        recommendedName: solutionShortText(value.recommended_name || value.recommendedName || '', 32),
        rows
    };
}

function solutionNormalizeValueBoard(value) {
    if (!value || typeof value !== 'object') return null;
    const items = solutionNormalizeList(value.items).map((item) => {
        if (!item || typeof item !== 'object') return null;
        const label = solutionShortText(item.label || '', 28);
        const mainValue = solutionShortText(item.value || '', 40);
        if (!label || !mainValue) return null;
        return {
            label,
            value: mainValue,
            delta: solutionShortText(item.delta || '', 28),
            assumption: solutionShortText(item.assumption || '', 56),
            baseline: solutionShortText(item.baseline || '', 80),
            audienceHint: solutionShortText(item.audience_hint || item.audienceHint || '', 48)
        };
    }).filter(Boolean);
    if (!items.length) return null;
    return {
        headline: solutionShortText(value.headline || '量化价值与成立前提', 40),
        items
    };
}

function solutionNormalizeQualityReview(value) {
    if (!value || typeof value !== 'object') return null;
    const overallScore = Number(value.overall_score);
    return {
        audience: solutionShortText(value.audience || '', 24).toLowerCase() || 'decision_maker',
        overallScore: Number.isFinite(overallScore) ? overallScore : 0,
        status: solutionShortText(value.status || '', 24).toLowerCase() || 'solid',
        issues: solutionCompactStrings(value.issues, 6, 88),
        reviewMode: solutionShortText(value.review_mode || '', 16).toLowerCase() || 'heuristic'
    };
}

function solutionNormalizeClosingBlock(value) {
    if (!value || typeof value !== 'object') return null;
    const headline = solutionBusinessSentence(value.headline || '', 120);
    const decision = solutionBusinessSentence(value.decision || '', 120);
    const boundary = solutionBusinessSentence(value.boundary || '', 120);
    if (!headline && !decision && !boundary) return null;
    return {
        eyebrow: solutionShortText(value.eyebrow || '决策收束', 24),
        title: solutionShortText(value.title || '最终建议', 32),
        headline,
        decision,
        boundary,
        evidenceRefs: solutionCollectRefs(value.evidence_refs || value.evidenceRefs || []),
        nextActionRefs: solutionCollectRefs(value.next_action_refs || value.nextActionRefs || [])
    };
}

function solutionNormalizeSummaryCard(value) {
    if (!value || typeof value !== 'object') return null;
    const title = solutionBusinessHeading(value.title || '', '', 96);
    const bullets = solutionCompactStrings(value.bullets, 3, 96);
    if (!title && !bullets.length) return null;
    return {
        title,
        audienceLabel: solutionShortText(value.audience_label || value.audienceLabel || '', 24),
        bullets
    };
}

function solutionNormalizeRenderModel(value) {
    if (!value || typeof value !== 'object') return null;
    const mode = solutionShortText(value.mode || 'proposal', 24).toLowerCase() || 'proposal';
    const overview = value.overview && typeof value.overview === 'object' ? {
        eyebrow: solutionShortText(value.overview.eyebrow || '', 24),
        title: solutionBusinessHeading(value.overview.title || '', '', 96),
        subtitle: solutionBusinessSentence(value.overview.subtitle || '', 180),
        judgement: solutionBusinessSentence(value.overview.judgement || '', 180),
        proofPoints: solutionCompactStrings(value.overview.proofPoints, 3, 88),
        metrics: solutionNormalizeList(value.overview.metrics).map(solutionNormalizeMetricItem).filter(Boolean),
        track: solutionNormalizeList(value.overview.track).map((item) => ({
            badge: solutionShortText(item?.badge || '', 18),
            title: solutionShortText(item?.title || '', 32),
            detail: solutionShortText(item?.detail || '', 96),
            meta: solutionShortText(item?.meta || '', 48)
        })).filter((item) => item.title),
        audience: solutionNormalizeAudienceProfile(value.overview.audience),
        evidenceRefs: solutionCollectRefs(value.overview.evidenceRefs || value.overview.evidence_refs || [])
    } : null;
    if (!overview?.title) return null;
    return {
        mode,
        hasProposal: value.hasProposal !== false,
        brandTitle: solutionShortText(value.brandTitle || '', 48),
        navItems: solutionNormalizeList(value.navItems).filter((item) => item?.id && item?.label),
        contentPriorityPlan: value.contentPriorityPlan && typeof value.contentPriorityPlan === 'object' ? value.contentPriorityPlan : null,
        overview,
        comparison: value.comparison && typeof value.comparison === 'object' ? {
            eyebrow: solutionShortText(value.comparison.eyebrow || '', 24),
            title: solutionBusinessHeading(value.comparison.title || '', '', 88),
            summary: solutionBusinessSentence(value.comparison.summary || '', 180),
            judgement: solutionBusinessSentence(value.comparison.judgement || '', 180),
            left: solutionNormalizeOption(value.comparison.left || {}),
            right: solutionNormalizeOption(value.comparison.right || {}),
            tertiary: value.comparison.tertiary ? solutionNormalizeOption(value.comparison.tertiary) : null,
            analogy: {
                title: solutionShortText(value.comparison.analogy?.title || '当前判断', 24),
                body: solutionBusinessSentence(value.comparison.analogy?.body || '', 220)
            },
            cases: solutionNormalizeList(value.comparison.cases).map((item) => ({
                badge: solutionShortText(item?.badge || '', 18),
                title: solutionShortText(item?.title || '', 32),
                left: solutionShortText(item?.left || '', 88),
                right: solutionShortText(item?.right || '', 88),
                effect: solutionShortText(item?.effect || '', 56)
            })).filter((item) => item.title),
            tableRows: solutionNormalizeList(value.comparison.tableRows),
            matrix: solutionNormalizeComparisonMatrix(value.comparison.matrix),
            evidenceRefs: solutionCollectRefs(value.comparison.evidenceRefs || value.comparison.evidence_refs || [])
        } : null,
        solutions: value.solutions && typeof value.solutions === 'object' ? {
            eyebrow: solutionShortText(value.solutions.eyebrow || '', 24),
            title: solutionBusinessHeading(value.solutions.title || '', '', 88),
            summary: solutionBusinessSentence(value.solutions.summary || '', 180),
            judgement: solutionBusinessSentence(value.solutions.judgement || '', 180),
            blueprint: value.solutions.blueprint && typeof value.solutions.blueprint === 'object' ? {
                eyebrow: solutionShortText(value.solutions.blueprint.eyebrow || '', 24),
                title: solutionBusinessHeading(value.solutions.blueprint.title || '', '', 88),
                summary: solutionBusinessSentence(value.solutions.blueprint.summary || '', 180),
                judgement: solutionBusinessSentence(value.solutions.blueprint.judgement || '', 160),
                cards: solutionNormalizeList(value.solutions.blueprint.cards).map(solutionNormalizeCardItem).filter(Boolean),
                figure: value.solutions.blueprint.figure && typeof value.solutions.blueprint.figure === 'object' ? value.solutions.blueprint.figure : null
            } : null,
            tabs: solutionNormalizeList(value.solutions.tabs),
            evidenceRefs: solutionCollectRefs(value.solutions.evidenceRefs || value.solutions.evidence_refs || [])
        } : null,
        integration: value.integration && typeof value.integration === 'object' ? {
            eyebrow: solutionShortText(value.integration.eyebrow || '', 24),
            title: solutionBusinessHeading(value.integration.title || '', '', 88),
            summary: solutionBusinessSentence(value.integration.summary || '', 180),
            judgement: solutionBusinessSentence(value.integration.judgement || '', 180),
            entryTitle: solutionShortText(value.integration.entryTitle || '', 20),
            entrySummary: solutionBusinessSentence(value.integration.entrySummary || '', 96),
            pathTitle: solutionShortText(value.integration.pathTitle || '', 20),
            pathSummary: solutionBusinessSentence(value.integration.pathSummary || '', 96),
            figureTitle: solutionShortText(value.integration.figureTitle || '', 20),
            figureSummary: solutionBusinessSentence(value.integration.figureSummary || '', 96),
            leftScenarios: solutionNormalizeList(value.integration.leftScenarios),
            phases: solutionNormalizeList(value.integration.phases).map(solutionNormalizePhase).filter(Boolean),
            systemFigure: value.integration.systemFigure && typeof value.integration.systemFigure === 'object' ? value.integration.systemFigure : null,
            businessFlowMermaid: solutionShortText(value.integration.businessFlowMermaid || '', 12000),
            evidenceRefs: solutionCollectRefs(value.integration.evidenceRefs || value.integration.evidence_refs || [])
        } : null,
        knowledge: value.knowledge && typeof value.knowledge === 'object' ? value.knowledge : null,
        flywheel: value.flywheel && typeof value.flywheel === 'object' ? value.flywheel : null,
        value: value.value && typeof value.value === 'object' ? {
            eyebrow: solutionShortText(value.value.eyebrow || '', 24),
            title: solutionBusinessHeading(value.value.title || '', '', 88),
            summary: solutionBusinessSentence(value.value.summary || '', 180),
            judgement: solutionBusinessSentence(value.value.judgement || '', 180),
            metrics: solutionNormalizeList(value.value.metrics).map(solutionNormalizeMetricItem).filter(Boolean),
            board: solutionNormalizeValueBoard(value.value.board),
            detailGroups: solutionNormalizeList(value.value.detailGroups),
            evidenceRefs: solutionCollectRefs(value.value.evidenceRefs || value.value.evidence_refs || [])
        } : null,
        fit: value.fit && typeof value.fit === 'object' ? {
            eyebrow: solutionShortText(value.fit.eyebrow || '', 24),
            title: solutionBusinessHeading(value.fit.title || '', '', 88),
            summary: solutionBusinessSentence(value.fit.summary || '', 180),
            judgement: solutionBusinessSentence(value.fit.judgement || '', 180),
            cards: solutionNormalizeList(value.fit.cards).map(solutionNormalizeCardItem).filter(Boolean),
            evidenceRefs: solutionCollectRefs(value.fit.evidenceRefs || value.fit.evidence_refs || [])
        } : null,
        closing: solutionNormalizeClosingBlock(value.closing),
        summaryCard: solutionNormalizeSummaryCard(value.summaryCard),
        qualityReview: solutionNormalizeQualityReview(value.qualityReview)
    };
}

function solutionGetProposalPage(payload) {
    const proposal = payload?.proposal_page;
    const chapters = solutionNormalizeList(proposal?.chapters).map(solutionNormalizeChapter).filter((chapter) => chapter?.id);
    const renderModel = solutionNormalizeRenderModel(proposal?.render_model || payload?.render_model);
    if (!chapters.length && !renderModel) return null;
    return {
        theme: String(proposal?.theme || 'executive_dark_editorial'),
        navItems: solutionNormalizeList(proposal?.nav_items).filter((item) => item?.id),
        audienceProfile: solutionNormalizeAudienceProfile(proposal?.audience_profile || payload?.audience_profile),
        comparisonMatrix: solutionNormalizeComparisonMatrix(proposal?.comparison_matrix || payload?.comparison_matrix),
        valueBoard: solutionNormalizeValueBoard(proposal?.value_board || payload?.value_board),
        contentPriorityPlan: proposal?.content_priority_plan || payload?.content_priority_plan || null,
        closingBlock: solutionNormalizeClosingBlock(proposal?.closing_block || payload?.closing_block),
        summaryCard: solutionNormalizeSummaryCard(proposal?.summary_card || payload?.summary_card),
        renderModel,
        qualityReview: solutionNormalizeQualityReview(proposal?.quality_review || payload?.quality_review),
        chapters
    };
}

function solutionGetChapterMap(payload) {
    const proposal = solutionGetProposalPage(payload);
    const map = new Map();
    solutionNormalizeList(proposal?.chapters).forEach((chapter) => {
        if (chapter?.id) map.set(chapter.id, chapter);
    });
    return map;
}

function solutionGetProposalBrief(payload) {
    return payload?.proposal_brief && typeof payload.proposal_brief === 'object' ? payload.proposal_brief : {};
}

function solutionGetProposalSupport(payload) {
    return payload?.proposal_support && typeof payload.proposal_support === 'object' ? payload.proposal_support : {};
}

function solutionGetSupportVisualizations(payload) {
    const support = solutionGetProposalSupport(payload);
    return support?.visualizations && typeof support.visualizations === 'object' ? support.visualizations : {};
}

function solutionGetSupportVisualization(payload, key) {
    const visualizations = solutionGetSupportVisualizations(payload);
    const value = visualizations?.[key];
    return typeof value === 'string' ? value.trim() : '';
}

function solutionNormalizeSupportCard(item) {
    if (!item || typeof item !== 'object') return null;
    const title = solutionHasHardTechTerms(item.title || item.name || '')
        ? solutionBusinessFocusLabel(item.title || item.name || '', 24)
        : solutionBusinessHeading(item.title || item.name || '', '', 42);
    const summary = solutionBusinessParagraph(
        item.summary || item.description || item.desc || '',
        title ? `围绕「${title}」先冻结边界、节奏和验收口径。` : '',
        120
    );
    const detail = solutionBusinessParagraph(
        item.detail || item.guardrail || item.meta || '',
        title ? `让「${title}」直接进入评审、试点或复盘。` : '',
        88
    );
    if (!title) return null;
    return {
        title,
        summary,
        detail,
        tag: solutionShortText(item.eyebrow || item.owner || item.step || item.tag || '', 20),
        timeline: solutionShortText(item.timeline || '', 24),
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionGetSupportCards(payload, key) {
    const support = solutionGetProposalSupport(payload);
    const derived = support?.derived && typeof support.derived === 'object' ? support.derived : {};
    return solutionNormalizeList(derived?.[key]).map(solutionNormalizeSupportCard).filter(Boolean);
}

function solutionGetSupportTableRows(payload, key) {
    const support = solutionGetProposalSupport(payload);
    const derived = support?.derived && typeof support.derived === 'object' ? support.derived : {};
    const table = derived?.[key];
    if (!table || typeof table !== 'object') return [];
    return solutionNormalizeList(table.rows).filter((row) => row && typeof row === 'object');
}

function solutionParseMermaidFlowchart(source) {
    const normalized = String(source || '').replace(/\s+/g, ' ').trim();
    if (!normalized) return null;
    const directionMatch = normalized.match(/flowchart\s+([A-Z]{2})/i);
    const tokenRe = /subgraph\s+[^\[]*\["[^"]+"\]|end\b|[A-Za-z][A-Za-z0-9_]*\[[^\]]+\]|[A-Za-z][A-Za-z0-9_]*\([^)]+\)|[A-Za-z][A-Za-z0-9_]*\s*-->(?:\|[^|]+\|)?\s*[A-Za-z][A-Za-z0-9_]*/g;
    const groupStack = [];
    const groups = [];
    const groupMap = new Map();
    const nodeMap = new Map();
    const edges = [];

    const ensureGroup = (label) => {
        const groupLabel = solutionShortText(String(label || '关键层').replace(/^["']|["']$/g, '').trim(), 24) || '关键层';
        if (groupMap.has(groupLabel)) return groupMap.get(groupLabel);
        const group = { id: `group-${groupMap.size + 1}`, label: groupLabel, nodes: [] };
        groupMap.set(groupLabel, group);
        groups.push(group);
        return group;
    };

    const ensureNode = (id, label = '') => {
        const nodeId = String(id || '').trim();
        if (!nodeId) return null;
        if (nodeMap.has(nodeId)) {
            const existing = nodeMap.get(nodeId);
            if (label && (!existing.label || existing.label === existing.id)) {
                existing.label = solutionShortText(label, 22) || existing.label;
            }
            return existing;
        }
        const node = {
            id: nodeId,
            label: solutionShortText(label || nodeId, 22) || nodeId,
            groupId: null
        };
        nodeMap.set(nodeId, node);
        return node;
    };

    let token;
    while ((token = tokenRe.exec(normalized))) {
        const text = token[0];
        if (text.startsWith('subgraph')) {
            const match = text.match(/\["([^"]+)"\]/);
            const group = ensureGroup(match?.[1] || text.replace(/^subgraph\s+/i, '').trim());
            groupStack.push(group);
            continue;
        }
        if (text === 'end') {
            groupStack.pop();
            continue;
        }
        const edgeMatch = text.match(/^([A-Za-z][A-Za-z0-9_]*)\s*-->(?:\|([^|]+)\|)?\s*([A-Za-z][A-Za-z0-9_]*)$/);
        if (edgeMatch) {
            const from = ensureNode(edgeMatch[1]);
            const to = ensureNode(edgeMatch[3]);
            if (from && to) {
                edges.push({
                    from: from.id,
                    to: to.id,
                    label: solutionShortText(edgeMatch[2] || '', 24)
                });
            }
            continue;
        }
        const nodeMatch = text.match(/^([A-Za-z][A-Za-z0-9_]*)(?:\[(.+)\]|\((.+)\))$/);
        if (nodeMatch) {
            const label = String(nodeMatch[2] || nodeMatch[3] || '').replace(/^["']|["']$/g, '').trim();
            const node = ensureNode(nodeMatch[1], label);
            const currentGroup = groupStack[groupStack.length - 1] || ensureGroup('关键节点');
            if (node && currentGroup && !node.groupId) {
                node.groupId = currentGroup.id;
                currentGroup.nodes.push(node);
            }
        }
    }

    const fallbackGroup = ensureGroup('关键节点');
    Array.from(nodeMap.values()).forEach((node) => {
        if (node.groupId) return;
        node.groupId = fallbackGroup.id;
        fallbackGroup.nodes.push(node);
    });

    const normalizedGroups = groups
        .map((group) => ({
            id: group.id,
            label: group.label,
            nodes: solutionUniqueBy(group.nodes, (item) => item.id).slice(0, 4)
        }))
        .filter((group) => group.nodes.length);

    if (!normalizedGroups.length) return null;
    return {
        direction: String(directionMatch?.[1] || 'TB').toUpperCase(),
        groups: normalizedGroups.slice(0, 5),
        edges: solutionUniqueBy(edges, (item) => `${item.from}-${item.to}-${item.label || ''}`).slice(0, 8)
    };
}

function solutionBuildBlueprintFigure(parsedDiagram, blueprintCards) {
    if (parsedDiagram?.groups?.length) {
        return {
            type: 'mermaid_flow',
            groups: parsedDiagram.groups,
            edges: parsedDiagram.edges,
            direction: parsedDiagram.direction
        };
    }
    const cards = solutionNormalizeList(blueprintCards).slice(0, 4);
    if (!cards.length) return null;
    return {
        type: 'card_flow',
        groups: [{
            id: 'group-1',
            label: '关键蓝图',
            nodes: cards.map((item, index) => ({
                id: `bp-${index + 1}`,
                label: item.title
            }))
        }],
        edges: cards.slice(0, -1).map((item, index) => ({
            from: `bp-${index + 1}`,
            to: `bp-${index + 2}`,
            label: '推进'
        })),
        direction: 'LR'
    };
}

function solutionBuildComparisonDetailRows(compareRows, recommended, alternative) {
    const rows = solutionNormalizeList(compareRows).map((row) => ({
        dimension: solutionShortText(row.title || row.label || '关键维度', 28),
        conventional: solutionShortText(alternative?.positioning || '继续沿用常规增强路径。', 86),
        recommended: solutionShortText(row.description || recommended?.positioning || '先锁定推荐路径，再按阶段扩张。', 96),
        signal: solutionShortText([row.metric, row.timeline, row.owner].filter(Boolean).join(' · '), 96),
        evidence: solutionShortText(row.evidence || '', 32)
    })).filter((row) => row.dimension && row.recommended);

    if (rows.length) return rows.slice(0, 6);

    return solutionNormalizeList([recommended]).filter(Boolean).map(() => ({
        dimension: '推荐路径',
        conventional: solutionShortText(alternative?.positioning || '继续沿用常规增强路径。', 86),
        recommended: solutionShortText(recommended?.positioning || '先锁定推荐路径，再按阶段扩张。', 96),
        signal: solutionShortText(recommended?.fitFor || '', 96),
        evidence: solutionCollectRefs(recommended).join('、')
    }));
}

function solutionNormalizeOption(item) {
    if (!item || typeof item !== 'object') return null;
    const name = solutionBusinessHeading(item.name || '', '', 34);
    const positioning = solutionBusinessSentence(item.positioning || '', 160);
    if (!name || !positioning) return null;
    return {
        name,
        positioning,
        pros: solutionCompactStrings(item.pros, 4, 72),
        cons: solutionCompactStrings(item.cons, 4, 72),
        fitFor: solutionBusinessSentence(item.fit_for || item.fitFor || '', 96),
        notFitFor: solutionBusinessSentence(item.not_fit_for || item.notFitFor || '', 96),
        decision: String(item.decision || 'alternative').trim().toLowerCase(),
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionNormalizeWorkstream(item) {
    if (!item || typeof item !== 'object') return null;
    const name = solutionBusinessFocusLabel(item.name || '', 24) || solutionBusinessHeading(item.name || '', '', 40);
    const objective = solutionBusinessSentence(item.objective || '', 160);
    if (!name || !objective) return null;
    return {
        name,
        objective,
        keyActions: solutionCompactStrings(item.key_actions || item.keyActions, 4, 72),
        deliverables: solutionCompactStrings(item.deliverables, 4, 72),
        ownerRole: solutionShortText(item.owner_role || item.ownerRole || '', 24),
        timeline: solutionShortText(item.timeline || '', 24),
        dependencies: solutionCompactStrings(item.dependencies, 4, 72),
        acceptanceSignals: solutionCompactStrings(item.acceptance_signals || item.acceptanceSignals, 4, 72),
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionNormalizeValueItem(item) {
    if (!item || typeof item !== 'object') return null;
    const metric = solutionBusinessMetricLabel(item.metric || '', '关键指标');
    const target = solutionBusinessMetricValue(item.target || item.range || '', 80);
    if (!metric || !target) return null;
    return {
        metric,
        baseline: solutionBusinessSentence(item.baseline || '', 104),
        target,
        range: solutionBusinessMetricValue(item.range || '', 80),
        assumptions: solutionCompactStrings(item.assumptions, 4, 72),
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionNormalizeFitReason(item) {
    if (!item || typeof item !== 'object') return null;
    const title = solutionBusinessHeading(item.title || '', '', 40);
    const detail = solutionBusinessSentence(item.detail || '', 140);
    if (!title || !detail) return null;
    return {
        title,
        detail,
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionNormalizeRiskBoundary(item) {
    if (!item || typeof item !== 'object') return null;
    const title = solutionBusinessHeading(item.title || '', '', 40);
    const detail = solutionBusinessSentence(item.detail || '', 140);
    if (!title || !detail) return null;
    return {
        title,
        detail,
        type: solutionShortText(item.type || 'risk', 16).toLowerCase(),
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionNormalizePhase(item) {
    if (!item || typeof item !== 'object') return null;
    const phase = solutionBusinessHeading(item.phase || '', '', 32);
    const goal = solutionBusinessSentence(item.goal || '', 140);
    if (!phase || !goal) return null;
    return {
        phase,
        goal,
        actions: solutionCompactStrings(item.actions, 4, 72),
        milestone: solutionShortText(item.milestone || '', 80),
        evidenceRefs: solutionCollectRefs(item)
    };
}

function solutionBuildMetricWall(payload, chapterMap, valueItems) {
    const metrics = [];
    const heroChapter = chapterMap.get('hero');
    solutionNormalizeList(heroChapter?.metrics).forEach((item) => metrics.push(item));
    solutionNormalizeList(valueItems).forEach((item) => {
        metrics.push(solutionNormalizeMetricItem({
            label: item.metric,
            value: item.target || item.range,
            note: item.assumptions[0] || item.baseline || '',
            delta: item.range || ''
        }));
    });
    solutionNormalizeList(payload?.metrics).forEach((item) => metrics.push(solutionNormalizeMetricItem(item)));
    const deduped = solutionUniqueBy(metrics.filter(Boolean), (item) => item.label);
    return deduped.slice(0, 4);
}

function solutionBuildProofPoints(chapterMap, fitReasons, recommended, context, support) {
    const heroChapter = chapterMap.get('hero');
    const points = [];
    solutionNormalizeList(heroChapter?.cards).forEach((item) => {
        points.push(item.title || item.desc);
    });
    solutionNormalizeList(support?.decisionCards).forEach((item) => {
        points.push(item.title || item.summary);
    });
    solutionNormalizeList(support?.currentStateCards).forEach((item) => {
        points.push(item.title || item.summary);
    });
    fitReasons.forEach((item) => points.push(item.title || item.detail));
    solutionCompactStrings(recommended.integrationPoints, 4, 48).forEach((item) => points.push(item));
    solutionCompactStrings(context.constraints, 4, 48).forEach((item) => points.push(item));
    return solutionCompactStrings(points, 4, 88);
}

function solutionBuildHeroTrack(workstreams, phases, supportMilestones) {
    const items = [];
    solutionNormalizeList(supportMilestones).slice(0, 3).forEach((item, index) => {
        items.push({
            badge: String(index + 1).padStart(2, '0'),
            title: item.title,
            detail: item.detail || item.summary,
            meta: [item.timeline, item.summary].filter(Boolean).join(' · ')
        });
    });
    if (items.length) return items.slice(0, 3);
    solutionNormalizeList(phases).forEach((phase, index) => {
        items.push({
            badge: String(index + 1).padStart(2, '0'),
            title: phase.phase,
            detail: phase.goal,
            meta: phase.milestone || solutionNormalizeList(phase.actions)[0] || ''
        });
    });
    if (!items.length) {
        solutionNormalizeList(workstreams).slice(0, 3).forEach((item, index) => {
            items.push({
                badge: String(index + 1).padStart(2, '0'),
                title: item.name,
                detail: item.objective,
                meta: [item.ownerRole, item.timeline].filter(Boolean).join(' · ')
            });
        });
    }
    return items.slice(0, 3);
}

function solutionBuildWorkstreamCapabilities(workstream) {
    const cards = [];
    workstream.keyActions.forEach((item) => {
        cards.push({ title: item, desc: '将关键动作前置冻结，避免方案停留在抽象判断。', tag: '关键动作' });
    });
    workstream.deliverables.forEach((item) => {
        cards.push({ title: item, desc: '交付物必须能直接进入评审或试点，不只是描述性文本。', tag: '交付物' });
    });
    workstream.acceptanceSignals.forEach((item) => {
        cards.push({ title: item, desc: '验收信号用于判断这条工作流是否真的有效，而不是只做了动作。', tag: '验收信号' });
    });
    workstream.dependencies.forEach((item) => {
        cards.push({ title: item, desc: '这些依赖需要在启动前处理，否则试点节奏会被拖慢。', tag: '前置条件' });
    });
    if (!cards.length) {
        cards.push({ title: workstream.name, desc: workstream.objective, tag: '工作流' });
    }
    return solutionUniqueBy(cards, (item) => `${item.tag}-${item.title}`).slice(0, 6);
}

function solutionBuildSolutionTabs(workstreams, chapterMap, valueItems, supportWorkstreams) {
    const chapter = chapterMap.get('workstreams');
    const supportTabs = solutionNormalizeList(supportWorkstreams).map((item, index) => ({
        id: `tab-support-${index + 1}`,
        label: item.title,
        headline: item.title,
        summary: solutionBusinessParagraph(item.summary || item.detail || '', `围绕「${item.title}」锁定动作、交付和验收。`, 96),
        tag: item.tag || `模块 ${index + 1}`,
        owner: item.tag || '关键模块',
        dependencies: solutionCompactStrings(item.detail, 2, 48),
        deliverables: solutionCompactStrings(item.detail, 2, 48),
        metrics: solutionNormalizeList(valueItems).slice(index, index + 2),
        capabilities: [
            { title: item.title, desc: solutionBusinessParagraph(item.summary || item.detail || '', `当前需要先把「${item.title}」做成可评审模块。`, 88), tag: item.tag || '模块' },
            { title: '执行边界', desc: `本模块要同时冻结节奏、交付物和验收口径。`, tag: '执行备注' }
        ],
        evidenceRefs: item.evidenceRefs
    }));
    if (supportTabs.length >= 3) return supportTabs.slice(0, 4);
    const tabs = solutionNormalizeList(workstreams).map((workstream, index) => ({
        id: `tab-${index + 1}`,
        label: workstream.name,
        headline: workstream.name,
        summary: workstream.objective,
        tag: workstream.timeline || `工作流 ${index + 1}`,
        owner: workstream.ownerRole || '待定角色',
        dependencies: workstream.dependencies,
        deliverables: workstream.deliverables,
        metrics: solutionNormalizeList(valueItems).slice(index, index + 2),
        capabilities: solutionBuildWorkstreamCapabilities(workstream),
        evidenceRefs: workstream.evidenceRefs
    }));
    if (tabs.length) return tabs.slice(0, 4);
    const fallbackCards = solutionNormalizeList(chapter?.cards);
    return fallbackCards.slice(0, 3).map((item, index) => ({
        id: `tab-fallback-${index + 1}`,
        label: item.title,
        headline: item.title,
        summary: item.desc,
        tag: item.tag || `模块 ${index + 1}`,
        owner: item.meta || '待定角色',
        dependencies: [],
        deliverables: solutionCompactStrings(item.meta, 2, 60),
        metrics: solutionNormalizeList(valueItems).slice(index, index + 2),
        capabilities: [
            { title: item.title, desc: item.desc, tag: '模块说明' },
            { title: item.meta || '待补充执行信息', desc: '当前仅有模块摘要，需结合后端槽位继续增强。', tag: '执行备注' }
        ],
        evidenceRefs: item.evidenceRefs
    }));
}

function solutionBuildComparisonCases(workstreams, recommended, alternative, compareRows) {
    const richCases = solutionNormalizeList(compareRows).map((row, index) => ({
        badge: String(index + 1).padStart(2, '0'),
        title: solutionShortText(row.title || row.label || '关键方案', 36),
        left: solutionBusinessParagraph(row.description || row.owner || alternative.positioning || '', '保守推进更快，但难以形成可评审方案。', 86),
        right: solutionBusinessParagraph([row.metric, row.timeline].filter(Boolean).join(' · ') || recommended.positioning || '', '推荐路径更适合先打透一条可验证闭环。', 86),
        effect: solutionShortText(row.evidence || row.metric || row.timeline || '', 86)
    }));
    if (richCases.length) return richCases.slice(0, 4);
    return solutionNormalizeList(workstreams).slice(0, 4).map((item, index) => ({
        badge: String(index + 1).padStart(2, '0'),
        title: item.name,
        left: solutionShortText(alternative.positioning || '仅输出常规报告内容，难以形成结构化提案。', 86),
        right: solutionShortText(item.objective || recommended.positioning || '', 86),
        effect: solutionShortText(item.acceptanceSignals[0] || item.deliverables[0] || recommended.fitFor || '', 86)
    }));
}

function solutionBuildKnowledgeLayers(context, workstreams, recommended, valueItems, support) {
    const layers = [
        {
            title: '问题判断层',
            items: solutionCompactStrings([
                ...solutionNormalizeList(support?.currentStateCards).map((item) => item.title || item.summary),
                ...(context.currentState || []),
                ...(context.coreConflicts || [])
            ].map((item) => solutionBusinessFocusLabel(item, 20) || item), 3, 42)
        },
        {
            title: '方案模块层',
            items: solutionCompactStrings([
                ...solutionNormalizeList(support?.blueprintCards).map((item) => item.title),
                ...solutionNormalizeList(workstreams).slice(0, 3).map((item) => item.name)
            ], 3, 42)
        },
        {
            title: '系统接入层',
            items: solutionCompactStrings(solutionNormalizeList(recommended.integrationPoints).map((item) => solutionBusinessFocusLabel(item, 20) || item), 3, 42)
        },
        {
            title: '价值复盘层',
            items: solutionNormalizeList(valueItems).slice(0, 3).map((item) => item.metric)
        }
    ];
    return layers.filter((layer) => solutionNormalizeList(layer.items).length);
}

function solutionBuildKnowledgeLoop(phases, workstreams, supportMilestones) {
    const loop = [];
    solutionNormalizeList(supportMilestones).slice(0, 3).forEach((item) => {
        loop.push({
            title: item.title,
            detail: solutionShortText(item.detail || item.summary, 88)
        });
    });
    if (loop.length >= 3) {
        loop.push({
            title: '结构化沉淀',
            detail: '把阶段结论沉淀为下一轮方案判断、图解节点和价值复盘素材。'
        });
        return loop.slice(0, 4);
    }
    if (solutionNormalizeList(phases).length) {
        phases.slice(0, 3).forEach((phase) => {
            loop.push({
                title: phase.phase,
                detail: solutionShortText(phase.goal, 88)
            });
        });
    }
    if (loop.length < 4) {
        [
            '结构化沉淀',
            '知识中枢更新',
            '下一轮方案更准',
            '组织复利增强'
        ].forEach((title, index) => {
            if (loop.length >= 4) return;
            const ws = workstreams[index];
            loop.push({
                title,
                detail: solutionShortText(ws?.objective || '每次执行都应反哺后续方案和知识库。', 88)
            });
        });
    }
    return loop.slice(0, 4);
}

function solutionBuildFlywheelNodes(workstreams, topic, recommended, supportBlueprintCards) {
    const items = solutionNormalizeList(supportBlueprintCards).slice(0, 4).map((item) => ({
        title: item.title,
        detail: solutionShortText(item.summary || item.detail, 74)
    }));
    if (!items.length) {
        solutionNormalizeList(workstreams).slice(0, 4).forEach((item) => {
            items.push({
                title: item.name,
                detail: solutionShortText(item.objective, 74)
            });
        });
    }
    while (items.length < 4) {
        items.push({
            title: solutionShortText(solutionNormalizeList(recommended.integrationPoints)[items.length] || `联动节点 ${items.length + 1}`, 32),
            detail: '每个节点都应服务于下一轮判断、执行和复盘。'
        });
    }
    return {
        centerTitle: solutionShortText(topic || '企业级方案中枢', 40),
        centerDetail: solutionShortText(recommended.northStar || recommended.architectureStatement || '让方案、系统和知识沉淀形成持续增强闭环。', 110),
        nodes: items.slice(0, 4)
    };
}

function solutionBuildFlywheelCases(workstreams, phases, valueItems, supportMilestones) {
    const cases = [];
    const milestoneList = solutionNormalizeList(supportMilestones);
    const wsList = solutionNormalizeList(workstreams);
    if (wsList[0] && wsList[1]) {
        cases.push({
            badge: '01',
            title: `${wsList[0].name} -> ${wsList[1].name}`,
            body: `前者稳定样本与入口，后者才能真正把触发时机和试点节奏跑顺。`
        });
    }
    if (wsList[1] && wsList[2]) {
        cases.push({
            badge: '02',
            title: `${wsList[1].name} -> ${wsList[2].name}`,
            body: `规则冻结后，复现与洞察沉淀的质量才会显著提高。`
        });
    }
    if (milestoneList[0] && milestoneList[1]) {
        cases.push({
            badge: '03',
            title: `${milestoneList[0].title} -> ${milestoneList[1].title}`,
            body: solutionShortText(milestoneList[1].detail || milestoneList[1].summary || '阶段推进应当形成自然递进关系。', 96)
        });
    }
    if (solutionNormalizeList(phases)[0] && solutionNormalizeList(phases)[1]) {
        cases.push({
            badge: milestoneList[0] && milestoneList[1] ? '04' : '03',
            title: `${phases[0].phase} -> ${phases[1].phase}`,
            body: `先冻结边界，再执行试点，可以显著降低返工成本。`
        });
    }
    if (solutionNormalizeList(valueItems)[0]) {
        cases.push({
            badge: '05',
            title: '全部沉淀 -> 价值复盘',
            body: `${valueItems[0].metric} 不应只是结果数字，而要反哺下一轮提案与执行策略。`
        });
    }
    return cases.slice(0, 4);
}

function solutionBuildValueDetailGroups(valueItems) {
    return solutionNormalizeList(valueItems).map((item) => ({
        title: item.metric,
        body: [item.baseline, item.target].filter(Boolean).join(' -> '),
        note: solutionNormalizeList(item.assumptions).join('、')
    })).slice(0, 6);
}

function solutionBuildFitCards(fitReasons, riskBoundaries) {
    const cards = [];
    solutionNormalizeList(fitReasons).forEach((item) => cards.push({
        title: item.title,
        desc: item.detail,
        tag: '适配理由',
        evidenceRefs: item.evidenceRefs
    }));
    solutionNormalizeList(riskBoundaries).slice(0, 2).forEach((item) => cards.push({
        title: item.title,
        desc: item.detail,
        tag: item.type === 'risk' ? '风险边界' : '边界条件',
        evidenceRefs: item.evidenceRefs
    }));
    return solutionUniqueBy(cards, (item) => `${item.tag}-${item.title}`).slice(0, 6);
}

function solutionBuildClosingStatements(thesis, recommended, context) {
    return solutionUniqueBy([
        solutionShortText(thesis.coreDecision || '', 160),
        solutionShortText(recommended.northStar || '', 160),
        solutionShortText(thesis.subheadline || '', 160),
        solutionShortText(`先围绕「${solutionShortText(context.businessScene || '当前场景', 24)}」完成首轮闭环，再决定是否扩大范围。`, 160)
    ].filter(Boolean), (item) => item.toLowerCase());
}

function solutionBuildProposalModel(payload) {
    const proposalPage = solutionGetProposalPage(payload);
    if (proposalPage?.renderModel?.overview?.title) {
        return proposalPage.renderModel;
    }
    const brief = solutionGetProposalBrief(payload);
    const chapterMap = solutionGetChapterMap(payload);
    const support = solutionGetProposalSupport(payload);
    const supportVisualizations = solutionGetSupportVisualizations(payload);
    const supportDecisionCards = solutionGetSupportCards(payload, 'decision_cards');
    const supportCurrentStateCards = solutionGetSupportCards(payload, 'current_state_cards');
    const supportBlueprintCards = solutionGetSupportCards(payload, 'target_blueprint_cards');
    const supportWorkstreamCards = solutionGetSupportCards(payload, 'workstream_cards');
    const supportMilestones = solutionGetSupportCards(payload, 'milestones');
    const supportRiskCards = solutionGetSupportCards(payload, 'risk_cards');
    const supportCompareRows = solutionGetSupportTableRows(payload, 'solution_compare_table');
    const architectureFlow = solutionParseMermaidFlowchart(supportVisualizations.architecture_mermaid);
    const businessFlow = solutionParseMermaidFlowchart(supportVisualizations.business_flow_mermaid);
    const thesis = brief?.thesis && typeof brief.thesis === 'object' ? brief.thesis : {};
    const context = brief?.context && typeof brief.context === 'object' ? brief.context : {};
    const recommendedSolution = brief?.recommended_solution && typeof brief.recommended_solution === 'object' ? brief.recommended_solution : {};
    const options = solutionNormalizeList(brief?.options).map(solutionNormalizeOption).filter(Boolean);
    const workstreams = solutionNormalizeList(brief?.workstreams).map(solutionNormalizeWorkstream).filter(Boolean);
    const valueItems = solutionNormalizeList(brief?.value_model).map(solutionNormalizeValueItem).filter(Boolean);
    const fitReasons = solutionNormalizeList(brief?.fit_reasons).map(solutionNormalizeFitReason).filter(Boolean);
    const riskBoundaries = solutionNormalizeList(brief?.risks_and_boundaries).map(solutionNormalizeRiskBoundary).filter(Boolean);
    const phases = solutionNormalizeList(brief?.next_steps).map(solutionNormalizePhase).filter(Boolean);
    const recommendedOption = options.find((item) => item.decision === 'recommended') || options[0] || {
        name: '推荐路径',
        positioning: solutionShortText(thesis.coreDecision || '优先围绕高信号切口完成首轮闭环试点。', 160),
        pros: ['更接近真实问题', '更容易形成可执行方案'],
        cons: ['需要先锁定边界', '需要跨角色协同'],
        fitFor: '适合需要进入评审和试点设计的项目',
        notFitFor: '不适合完全无法获得关键入口和执行资源的场景',
        decision: 'recommended',
        evidenceRefs: solutionCollectRefs(brief)
    };
    const alternativeOption = options.find((item) => item.decision === 'alternative') || options.find((item) => item.name !== recommendedOption.name) || {
        name: '常规路径',
        positioning: '继续沿用传统报告整理和串行对齐，先做更多信息收集再进入方案评审。',
        pros: ['启动成本更低', '适合只需要方向判断的早期探索'],
        cons: ['很难形成清晰取舍和实施节奏', '容易继续停留在信息堆积而非方案判断'],
        fitFor: '预算极紧、只需要轻量摘要的场景',
        notFitFor: '需要立项、售前或管理层评审的项目',
        decision: 'alternative',
        evidenceRefs: []
    };
    const tertiaryOption = options.find((item) => item.decision === 'rejected') || options[2] || null;
    const recommendedFocus = solutionBusinessFocusLabel(recommendedOption.name || '', 24) || '关键路径';
    const secondaryFocus = solutionBusinessFocusLabel(
        supportBlueprintCards[1]?.title
        || solutionNormalizeList(recommendedSolution.modules)?.[1]?.name
        || '分层架构',
        24
    ) || '分层架构';
    const topicFocus = solutionBusinessFocusLabel(brief?.meta?.topic || payload?.title || '当前方案', 24) || '当前方案';
    const metricWall = solutionBuildMetricWall(payload, chapterMap, valueItems);
    const proofPoints = solutionBuildProofPoints(chapterMap, fitReasons, {
        integrationPoints: solutionCompactStrings(recommendedSolution.integration_points, 4, 84),
        northStar: solutionShortText(recommendedSolution.north_star || '', 96),
        architectureStatement: solutionShortText(recommendedSolution.architecture_statement || '', 120)
    }, {
        constraints: solutionCompactStrings(context.constraints, 4, 84)
    }, {
        decisionCards: supportDecisionCards,
        currentStateCards: supportCurrentStateCards
    });
    const heroTrack = solutionBuildHeroTrack(workstreams, phases, supportMilestones);
    const solutionTabs = solutionBuildSolutionTabs(workstreams, chapterMap, valueItems, supportWorkstreamCards.length ? supportWorkstreamCards : supportBlueprintCards);
    const chapterComparison = chapterMap.get('comparison');
    const chapterBlueprint = chapterMap.get('blueprint');
    const chapterSolutions = chapterMap.get('workstreams');
    const chapterIntegration = chapterMap.get('integration');
    const chapterValue = chapterMap.get('value_fit');
    const chapterHero = chapterMap.get('hero');
    const audienceProfile = proposalPage?.audienceProfile || solutionNormalizeAudienceProfile(payload?.audience_profile) || {
        key: 'decision_maker',
        label: '决策层视角',
        reasoning: '',
        proposalGoal: ''
    };
    const comparisonMatrix = proposalPage?.comparisonMatrix || null;
    const valueBoard = proposalPage?.valueBoard || null;
    const qualityReview = proposalPage?.qualityReview || null;

    const model = {
        mode: 'proposal',
        hasProposal: Boolean(solutionTabs.length || options.length || valueItems.length || proposalPage),
        brandTitle: solutionShortText(brief?.meta?.topic || payload?.title || 'DeepVision 企业提案', 48),
        navItems: solutionNormalizeList(proposalPage?.navItems).length ? proposalPage.navItems : SOLUTION_NAV_ITEMS,
        overview: {
            eyebrow: chapterHero?.eyebrow || 'DeepVision 企业级提案方案',
            title: solutionBusinessHeading(
                chapterHero?.title || thesis.headline || payload?.title || '生成企业级解决方案',
                `先把「${recommendedFocus}」和「${secondaryFocus}」打稳，再让「${topicFocus}」进入可复制推进`,
                96
            ),
            subtitle: solutionBusinessSentence(chapterHero?.summary || thesis.subheadline || payload?.subtitle || payload?.overview || '', 180),
            judgement: solutionBusinessSentence(chapterHero?.judgement || thesis.coreDecision || thesis.why_now || '', 180),
            proofPoints,
            metrics: metricWall,
            track: heroTrack,
            audience: audienceProfile,
            evidenceRefs: solutionCollectRefs(chapterHero, thesis, fitReasons.slice(0, 2), valueItems.slice(0, 2))
        },
        comparison: {
            eyebrow: chapterComparison?.eyebrow || '系统定位与协同',
            title: solutionBusinessHeading(
                solutionShouldUseNarrativeFallback(chapterComparison?.title) ? '' : chapterComparison?.title,
                `为什么当前先做「${recommendedFocus}」`,
                88
            ),
            summary: solutionBusinessSentence(chapterComparison?.summary || `当前需要把「${recommendedFocus}」的推荐理由、边界和取舍一次讲清。`, 180),
            judgement: solutionBusinessSentence(chapterComparison?.judgement || `当前不是追求覆盖面最大，而是在投入、速度、风险和可验证性之间先找到最稳的一条路径。`, 180),
            left: alternativeOption,
            right: recommendedOption,
            tertiary: tertiaryOption,
            analogy: {
                title: '一个更直观的理解',
                body: solutionShortText(
                    supportDecisionCards[0]?.detail
                    || recommendedOption.positioning
                    || `先用访谈结论锁定关键切口、系统边界和推进节奏，再把这些判断组织成可评审、可试点、可扩张的完整方案。`,
                    220
                )
            },
            cases: solutionBuildComparisonCases(workstreams, recommendedOption, alternativeOption, supportCompareRows),
            tableRows: solutionBuildComparisonDetailRows(supportCompareRows, recommendedOption, alternativeOption),
            matrix: comparisonMatrix,
            evidenceRefs: solutionCollectRefs(chapterComparison, recommendedOption, alternativeOption, tertiaryOption, supportCompareRows)
        },
        solutions: {
            eyebrow: chapterSolutions?.eyebrow || '核心落地方案',
            title: solutionBusinessHeading(chapterSolutions?.title || '', '把推荐路径拆成团队真正能接手的关键模块', 88),
            summary: solutionBusinessSentence(chapterSolutions?.summary || '每个模块都要明确动作、交付物、负责人和验收信号，团队才能真正接住。', 180),
            judgement: solutionBusinessSentence(chapterSolutions?.judgement || '真正决定落地质量的，不是模块数量，而是每个模块是否能直接进入试点执行。', 180),
            blueprint: {
                eyebrow: chapterBlueprint?.eyebrow || '推荐蓝图',
                title: solutionBusinessHeading(
                    solutionShouldUseNarrativeFallback(chapterBlueprint?.title) ? '' : chapterBlueprint?.title,
                    `推荐蓝图：先稳住「${recommendedFocus}」，再拉通「${secondaryFocus}」`,
                    88
                ),
                summary: solutionBusinessSentence(chapterBlueprint?.summary || recommendedSolution.north_star || '先把能力底座、系统分层和治理方式接成一条连续路径。', 180),
                judgement: solutionBusinessSentence(chapterBlueprint?.judgement || recommendedSolution.architecture_statement || '推荐路径不是堆卡片，而是从入口、底座到治理的连续结构。', 180),
                cards: solutionNormalizeList(supportBlueprintCards).slice(0, 4),
                figure: solutionBuildBlueprintFigure(architectureFlow, supportBlueprintCards)
            },
            tabs: solutionTabs,
            evidenceRefs: solutionCollectRefs(chapterSolutions, chapterBlueprint, workstreams, supportBlueprintCards)
        },
        integration: {
            eyebrow: chapterIntegration?.eyebrow || '系统集成层',
            title: solutionBusinessHeading(
                solutionShouldUseNarrativeFallback(chapterIntegration?.title) ? '' : chapterIntegration?.title,
                `把「${recommendedFocus}」接进系统闭环`,
                88
            ),
            summary: solutionBusinessSentence(chapterIntegration?.summary || '先围绕高信号入口接入，再分阶段打通系统，方案才会真正跑起来。', 180),
            judgement: solutionBusinessSentence(chapterIntegration?.judgement || '系统闭环决定这套方案能否从单次试点变成长期能力。', 180),
            leftScenarios: solutionCompactStrings(recommendedSolution.integration_points, 4, 84).map((item, index) => ({
                eyebrow: `入口 ${String(index + 1).padStart(2, '0')}`,
                title: solutionBusinessFocusLabel(item, 24) || item,
                detail: solutionBusinessParagraph(
                    solutionNormalizeList(recommendedSolution.dataflow)[index] || solutionNormalizeList(context.current_state)[index] || '',
                    `围绕该入口组织接入、执行和回流动作。`,
                    96
                )
            })).concat(solutionNormalizeList(supportBlueprintCards).slice(0, 4).map((item, index) => ({
                eyebrow: item.tag || `入口 ${String(index + 1).padStart(2, '0')}`,
                title: item.title,
                detail: solutionBusinessParagraph(item.summary || item.detail || '', `围绕该入口组织接入、执行和回流动作。`, 96)
            }))).slice(0, 4),
            phases,
            systemFigure: businessFlow || solutionBuildBlueprintFigure(null, solutionNormalizeList(supportMilestones).slice(0, 4)),
            evidenceRefs: solutionCollectRefs(chapterIntegration, recommendedSolution, phases, supportBlueprintCards, businessFlow)
        },
        knowledge: {
            eyebrow: '知识统一与持续增强',
            title: '把试点结论沉淀成统一知识资产',
            summary: '把本次试点的判断、模块和边界沉淀进统一台账，后续项目才能越做越快。',
            judgement: '如果试点结论不能复用，后续项目还会重复踩坑。',
            pains: solutionCompactStrings([...(context.current_state || []), ...(context.core_conflicts || []), ...supportCurrentStateCards.map((item) => item.title || item.summary), ...riskBoundaries.map((item) => item.title)], 4, 88),
            solutions: solutionCompactStrings([...(solutionNormalizeList(recommendedSolution.governance)), ...supportBlueprintCards.map((item) => item.title), ...fitReasons.map((item) => item.title), ...workstreams.map((item) => item.name)], 5, 88),
            layers: solutionBuildKnowledgeLayers({
                currentState: solutionCompactStrings(context.current_state, 4, 72),
                coreConflicts: solutionCompactStrings(context.core_conflicts, 4, 72)
            }, workstreams, {
                integrationPoints: solutionCompactStrings(recommendedSolution.integration_points, 4, 72)
            }, valueItems, {
                currentStateCards: supportCurrentStateCards,
                blueprintCards: supportBlueprintCards
            }),
            loop: solutionBuildKnowledgeLoop(phases, workstreams, supportMilestones),
            evidenceRefs: solutionCollectRefs(recommendedSolution, fitReasons, riskBoundaries, supportCurrentStateCards, supportBlueprintCards)
        },
        flywheel: {
            eyebrow: '跨模块联动',
            title: '让关键模块形成持续联动',
            summary: '把切口、模块、系统接入和价值复盘接成循环，方案才会持续放大。',
            judgement: '如果模块之间不能回流协同，这套方案就无法形成真正的组织复利。',
            diagram: solutionBuildFlywheelNodes(workstreams, brief?.meta?.topic || payload?.title, {
                northStar: recommendedSolution.north_star,
                architectureStatement: recommendedSolution.architecture_statement,
                integrationPoints: solutionCompactStrings(recommendedSolution.integration_points, 4, 72)
            }, supportBlueprintCards),
            cases: solutionBuildFlywheelCases(workstreams, phases, valueItems, supportMilestones),
            evidenceRefs: solutionCollectRefs(workstreams, phases, valueItems, supportMilestones, supportBlueprintCards)
        },
        value: {
            eyebrow: chapterValue?.eyebrow || '预期价值总览',
            title: solutionBusinessHeading(
                solutionShouldUseNarrativeFallback(chapterValue?.title) ? '' : chapterValue?.title,
                '为什么这条路径更适合当前团队进入试点决策阶段',
                88
            ),
            summary: solutionShortText(chapterValue?.summary || '让每个投入都能对应到更清晰的效率、判断深度和推进节奏。', 180),
            judgement: solutionShortText(chapterValue?.judgement || '量化不是装饰，而是让方案页真正进入决策层讨论的最低门槛。', 180),
            metrics: solutionUniqueBy(
                [...metricWall, ...solutionNormalizeList(valueItems).map((item) => solutionNormalizeMetricItem({
                    label: item.metric,
                    value: item.target || item.range,
                    note: item.assumptions[0] || item.baseline || '',
                    delta: item.range || ''
                }))].filter(Boolean),
                (item) => item.label
            ).slice(0, 6),
            board: valueBoard,
            detailGroups: solutionBuildValueDetailGroups(valueItems),
            evidenceRefs: solutionCollectRefs(valueItems, chapterValue)
        },
        fit: {
            eyebrow: '适配性与最终收束',
            title: solutionBusinessHeading(chapterValue?.title || '', '为什么这条路径尤其适合当前团队', 88),
            summary: '最后要把适配性、时机和路径选择一次讲清，管理层才能做最终判断。',
            judgement: '只有价值、适配性和边界同时成立，这件事才值得进入试点和立项。',
            cards: solutionBuildFitCards(fitReasons, riskBoundaries).concat(solutionNormalizeList(supportRiskCards).slice(0, 2).map((item) => ({
                title: item.title,
                desc: solutionBusinessParagraph(item.summary || item.detail || '', `提前识别「${item.title}」的边界和处置方式。`, 96),
                tag: item.tag || '风险边界',
                evidenceRefs: item.evidenceRefs
            }))).slice(0, 6),
            closing: solutionBuildClosingStatements(thesis, {
                northStar: recommendedSolution.north_star
            }, {
                businessScene: context.business_scene || brief?.meta?.topic || payload?.title
            }),
            evidenceRefs: solutionCollectRefs(fitReasons, riskBoundaries, thesis, supportRiskCards)
        },
        qualityReview
    };

    return model;
}

function solutionShouldShowQualityStrip(payload) {
    const params = new URLSearchParams(window.location.search || '');
    if (params.get('debug_quality') === '1') return true;
    const reasons = solutionNormalizeList(payload?.quality_signals?.degraded_reasons);
    if (payload?.source_mode === 'degraded') return true;
    return reasons.length > 0;
}

function solutionRenderAudienceBadge(audience) {
    if (!audience?.label) return '';
    return `
        <span class="proposal-audience-badge" title="${solutionEscapeHtml(audience.reasoning || '')}">
            ${solutionEscapeHtml(audience.label)}
        </span>
    `;
}

function solutionRenderTopbar(model, payload) {
    const topbar = document.getElementById('solution-topbar');
    const mobileNav = document.getElementById('solution-mobile-nav');
    if (!topbar || !mobileNav) return;
    const renderButtons = (items, mobile = false) => solutionNormalizeList(items).map((item) => `
        <button type="button" class="solution-nav-button${mobile ? ' is-mobile' : ''}" data-scroll-target="${solutionEscapeHtml(item.id)}">
            ${solutionEscapeHtml(item.label)}
        </button>
    `).join('');
    const finalTarget = model?.closing?.headline ? 'closing' : 'fit';
    topbar.innerHTML = `
        <div class="solution-topbar-inner">
            <div class="solution-brand">
                <div class="solution-brand-mark">DV</div>
                <div class="solution-brand-copy">
                    <div class="solution-brand-kicker">样例式提案方案 · ${solutionEscapeHtml(SOLUTION_SOURCE_MODE_LABELS[payload?.source_mode] || '方案')}</div>
                    <div class="solution-brand-title">${solutionEscapeHtml(model.brandTitle)}</div>
                </div>
            </div>
            <nav class="solution-nav" aria-label="方案章节导航">
                ${renderButtons(model.navItems)}
            </nav>
            <div class="solution-topbar-actions">
                ${solutionRenderAudienceBadge(model.overview?.audience)}
                <button type="button" class="solution-topbar-action" data-scroll-target="${solutionEscapeHtml(finalTarget)}">查看结论</button>
            </div>
        </div>
    `;
    mobileNav.hidden = false;
    mobileNav.innerHTML = renderButtons(model.navItems, true);
}

function solutionRenderEvidenceButton(title, refs, label = '查看证据') {
    const list = solutionCollectRefs(refs);
    if (!list.length) return '';
    return `
        <button
            type="button"
            class="solution-inline-evidence"
            data-evidence-title="${solutionEscapeHtml(title || '当前章节证据')}"
            data-evidence-refs="${solutionEscapeHtml(list.join('||'))}"
        >
            ${solutionEscapeHtml(label)}
        </button>
    `;
}

function solutionRenderQualityStrip(payload) {
    const root = document.getElementById('solution-quality-strip');
    if (!root) return;
    if (!solutionShouldShowQualityStrip(payload)) {
        root.hidden = true;
        root.innerHTML = '';
        return;
    }
    const quality = payload?.quality_signals || {};
    const brief = solutionGetProposalBrief(payload);
    const proposalPage = solutionGetProposalPage(payload);
    const qualityReview = proposalPage?.qualityReview || solutionNormalizeQualityReview(payload?.quality_review);
    const audienceProfile = proposalPage?.audienceProfile || solutionNormalizeAudienceProfile(payload?.audience_profile);
    const generationMode = brief?.meta?.generation_mode === 'ai' ? 'AI 提案' : '规则兜底';
    const rows = [
        {
            label: '数据来源',
            value: SOLUTION_SOURCE_MODE_LABELS[payload?.source_mode] || payload?.source_mode || '未知',
            detail: '当前页面所使用的方案事实来源。'
        },
        {
            label: '提案引擎',
            value: generationMode,
            detail: brief?.meta?.generation_mode === 'ai' ? '优先采用 AI 生成提案文案，再由母版渲染。' : '当前未命中 AI 生成或走了规则兜底。'
        },
        {
            label: '受众视角',
            value: audienceProfile?.label || '决策层视角',
            detail: audienceProfile?.reasoning || '当前按默认决策层口吻组织提案。'
        },
        {
            label: '证据绑定率',
            value: solutionPercent(quality?.evidence_binding_ratio),
            detail: '结构化条目与真实证据的绑定程度。'
        },
        {
            label: '近期差异度',
            value: `${Math.max(0, Math.round((1 - Number(quality?.similarity_score || 0)) * 100))}%`,
            detail: quality?.similar_report_name ? `最近对比对象：${solutionShortText(quality.similar_report_name, 18)}` : '基于近期方案相似度估算。'
        },
        {
            label: '提案审校',
            value: qualityReview ? `${Math.round((qualityReview.overallScore || 0) * 100)}分` : '未审校',
            detail: qualityReview ? `${qualityReview.reviewMode === 'ai' ? 'AI 自审' : '启发式审查'} · ${qualityReview.status || 'solid'}` : '当前未生成审校结果。'
        },
    ];
    const alerts = solutionNormalizeList(quality?.degraded_reasons);
    root.hidden = false;
    root.innerHTML = `
        <div class="solution-quality-grid">
            ${rows.map((item) => `
                <article class="solution-quality-item">
                    <div class="solution-quality-label">${solutionEscapeHtml(item.label)}</div>
                    <div class="solution-quality-value">${solutionEscapeHtml(item.value)}</div>
                    <div class="solution-quality-detail">${solutionEscapeHtml(item.detail)}</div>
                </article>
            `).join('')}
        </div>
        ${alerts.length ? `
            <div class="solution-quality-alert">
                ${alerts.map((item) => `<div class="solution-quality-alert-item">${solutionEscapeHtml(item)}</div>`).join('')}
            </div>
        ` : ''}
    `;
}

function solutionRenderSectionHead(section) {
    return `
        <div class="proposal-section-head">
            <div class="proposal-section-label-row">
                <span class="proposal-section-label">${solutionEscapeHtml(section.eyebrow || '方案章节')}</span>
                ${solutionRenderEvidenceButton(section.title || section.label, section.evidenceRefs)}
            </div>
            <h2 class="proposal-section-title">${solutionEscapeHtml(section.title || '未命名章节')}</h2>
            ${section.summary ? `<p class="proposal-section-summary">${solutionEscapeHtml(section.summary)}</p>` : ''}
            ${section.judgement ? `<p class="proposal-section-judgement">${solutionEscapeHtml(section.judgement)}</p>` : ''}
        </div>
    `;
}

function solutionRenderComparisonMatrix(matrix) {
    const rows = solutionNormalizeList(matrix?.rows);
    if (!rows.length) return '';
    return `
        <div class="proposal-comparison-matrix">
            <div class="proposal-comparison-matrix-head">
                <div class="proposal-section-label">对比矩阵</div>
                <h4>把推荐路径放进明确维度里比较，而不是只凭直觉选择</h4>
            </div>
            <div class="proposal-comparison-matrix-table">
                ${rows.map((row) => `
                    <div class="proposal-comparison-matrix-row">
                        <div class="proposal-comparison-matrix-dimension">
                            <div class="proposal-comparison-matrix-title">${solutionEscapeHtml(row.dimension)}</div>
                            ${row.winner ? `<div class="proposal-comparison-matrix-winner">更优：${solutionEscapeHtml(row.winner)}</div>` : ''}
                        </div>
                        <div class="proposal-comparison-matrix-cells">
                            ${solutionNormalizeList(row.cells).map((cell) => `
                                <article class="proposal-comparison-matrix-cell is-${solutionEscapeHtml(cell.decision || 'alternative')}">
                                    <div class="proposal-comparison-matrix-cell-head">
                                        <span>${solutionEscapeHtml(cell.option || '路径')}</span>
                                        <span class="proposal-comparison-matrix-badge">${solutionEscapeHtml(cell.badge || '中')}</span>
                                    </div>
                                    <p>${solutionEscapeHtml(cell.reason || '待补充')}</p>
                                </article>
                            `).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function solutionRenderValueBoard(board) {
    const items = solutionNormalizeList(board?.items);
    if (!items.length) return '';
    return `
        <div class="proposal-value-board">
            <div class="proposal-value-board-head">
                <div class="proposal-section-label">${solutionEscapeHtml(board.headline || '量化价值与成立前提')}</div>
                <h3>把预期收益和成立前提放在一起，管理层才能快速判断值不值得做</h3>
            </div>
            <div class="proposal-value-board-grid">
                ${items.map((item) => `
                    <article class="proposal-value-board-card">
                        <div class="proposal-value-board-label">${solutionEscapeHtml(item.label)}</div>
                        <div class="proposal-value-board-value">${solutionEscapeHtml(item.value)}</div>
                        ${item.delta ? `<div class="proposal-value-board-delta">${solutionEscapeHtml(item.delta)}</div>` : ''}
                        ${item.assumption ? `<div class="proposal-value-board-assumption">${solutionEscapeHtml(item.assumption)}</div>` : ''}
                        ${item.audienceHint ? `<div class="proposal-value-board-hint">${solutionEscapeHtml(item.audienceHint)}</div>` : ''}
                    </article>
                `).join('')}
            </div>
        </div>
    `;
}

function solutionRenderHeroSection(section) {
    return `
        <section class="proposal-section proposal-hero" id="overview" data-solution-section>
            <div class="proposal-hero-grid">
                <div class="proposal-hero-copy">
                    <div class="proposal-hero-top">
                        <span class="proposal-eyebrow">${solutionEscapeHtml(section.eyebrow)}</span>
                        ${solutionRenderAudienceBadge(section.audience)}
                        <span class="proposal-year-tag">DeepVision ${new Date().getFullYear()}</span>
                    </div>
                    <h1 class="proposal-hero-title">${solutionEscapeHtml(section.title)}</h1>
                    ${section.subtitle ? `<p class="proposal-hero-subtitle">${solutionEscapeHtml(section.subtitle)}</p>` : ''}
                    ${section.judgement ? `<p class="proposal-hero-judgement">${solutionEscapeHtml(section.judgement)}</p>` : ''}
                    <div class="proposal-proof-list">
                        ${solutionNormalizeList(section.proofPoints).map((item) => `
                            <div class="proposal-proof-item">
                                <span class="proposal-proof-dot"></span>
                                <span>${solutionEscapeHtml(item)}</span>
                            </div>
                        `).join('')}
                    </div>
                    <div class="proposal-hero-actions">
                        <button type="button" class="solution-primary-action" data-scroll-target="solutions">深入了解方案</button>
                        ${solutionRenderEvidenceButton(section.title, section.evidenceRefs, '查看结论证据')}
                    </div>
                </div>
                <div class="proposal-hero-side">
                    <div class="proposal-metric-wall">
                        ${solutionNormalizeList(section.metrics).map((item) => `
                            <article class="proposal-metric-card">
                                <div class="proposal-metric-label">${solutionEscapeHtml(item.label)}</div>
                                <div class="proposal-metric-value">${solutionEscapeHtml(item.value)}</div>
                                ${item.delta ? `<div class="proposal-metric-delta">${solutionEscapeHtml(item.delta)}</div>` : ''}
                                ${item.note ? `<div class="proposal-metric-note">${solutionEscapeHtml(item.note)}</div>` : ''}
                            </article>
                        `).join('')}
                    </div>
                    <article class="proposal-track-card">
                        <div class="proposal-track-label">推进节奏</div>
                        <div class="proposal-track-list">
                            ${solutionNormalizeList(section.track).map((item) => `
                                <div class="proposal-track-item">
                                    <div class="proposal-track-badge">${solutionEscapeHtml(item.badge)}</div>
                                    <div class="proposal-track-body">
                                        <div class="proposal-track-title">${solutionEscapeHtml(item.title)}</div>
                                        <div class="proposal-track-detail">${solutionEscapeHtml(item.detail)}</div>
                                        ${item.meta ? `<div class="proposal-track-meta">${solutionEscapeHtml(item.meta)}</div>` : ''}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </article>
                </div>
            </div>
        </section>
    `;
}

function solutionRenderOptionCard(option, variant = 'default') {
    return `
        <article class="proposal-option-card proposal-option-card-${solutionEscapeHtml(variant)}">
            <div class="proposal-option-head">
                <div>
                    <div class="proposal-option-tag">${solutionEscapeHtml(variant === 'recommended' ? '推荐路径' : '对照路径')}</div>
                    <h3 class="proposal-option-title">${solutionEscapeHtml(option.name || '未命名路径')}</h3>
                </div>
                <div class="proposal-option-chip">${solutionEscapeHtml(option.decision === 'recommended' ? '优先采用' : '对照参考')}</div>
            </div>
            <p class="proposal-option-positioning">${solutionEscapeHtml(option.positioning || '待补充路径定位')}</p>
            <div class="proposal-option-columns">
                <div class="proposal-option-column">
                    <div class="proposal-option-column-label">优点</div>
                    <ul class="proposal-bullet-list">
                        ${solutionNormalizeList(option.pros).map((item) => `<li>${solutionEscapeHtml(item)}</li>`).join('') || '<li>当前暂无优势描述</li>'}
                    </ul>
                </div>
                <div class="proposal-option-column">
                    <div class="proposal-option-column-label">边界与代价</div>
                    <ul class="proposal-bullet-list">
                        ${solutionNormalizeList(option.cons).map((item) => `<li>${solutionEscapeHtml(item)}</li>`).join('') || '<li>当前暂无边界说明</li>'}
                    </ul>
                </div>
            </div>
            <div class="proposal-option-fit">
                <div><span>适合：</span>${solutionEscapeHtml(option.fitFor || '待补充')}</div>
                <div><span>不适合：</span>${solutionEscapeHtml(option.notFitFor || '待补充')}</div>
            </div>
        </article>
    `;
}

function solutionRenderComparisonSection(section) {
    return `
        <section class="proposal-section" id="comparison" data-solution-section>
            ${solutionRenderSectionHead(section)}
            <div class="proposal-comparison-grid">
                ${solutionRenderOptionCard(section.left, 'contrast')}
                <div class="proposal-comparison-center">
                    <div class="proposal-comparison-center-label">推荐结论</div>
                    <div class="proposal-comparison-center-value">${solutionEscapeHtml(section.judgement)}</div>
                    ${section.summary ? `<div class="proposal-comparison-center-note">${solutionEscapeHtml(section.summary)}</div>` : ''}
                </div>
                ${solutionRenderOptionCard(section.right, 'recommended')}
            </div>
            ${section.tertiary ? `
                <div class="proposal-comparison-tertiary">
                    <span class="proposal-tertiary-label">不建议直接采用</span>
                    <span class="proposal-tertiary-text">${solutionEscapeHtml(section.tertiary.name)}：${solutionEscapeHtml(section.tertiary.positioning)}</span>
                </div>
            ` : ''}
            <article class="proposal-analogy-card">
                <div class="proposal-analogy-label">${solutionEscapeHtml(section.analogy.title)}</div>
                <p>${solutionEscapeHtml(section.analogy.body)}</p>
            </article>
            <button type="button" class="solution-expand-toggle" data-toggle-target="comparison-detail">
                查看完整对比细节
            </button>
            <div class="proposal-expand-panel" id="comparison-detail" hidden>
                ${solutionRenderComparisonMatrix(section.matrix)}
                ${solutionNormalizeList(section.tableRows).length ? `
                    <div class="proposal-table-wrap proposal-comparison-table-wrap">
                        <table class="proposal-table">
                            <thead>
                                <tr>
                                    <th>关键维度</th>
                                    <th>常规路径</th>
                                    <th>推荐路径</th>
                                    <th>推进信号</th>
                                    <th>证据</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${solutionNormalizeList(section.tableRows).map((row) => `
                                    <tr>
                                        <td>${solutionEscapeHtml(row.dimension)}</td>
                                        <td>${solutionEscapeHtml(row.conventional)}</td>
                                        <td>${solutionEscapeHtml(row.recommended)}</td>
                                        <td>${solutionEscapeHtml(row.signal || '-')}</td>
                                        <td>${solutionEscapeHtml(row.evidence || '-')}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : ''}
                <div class="proposal-case-grid">
                    ${solutionNormalizeList(section.cases).map((item) => `
                        <article class="proposal-case-card">
                            <div class="proposal-case-badge">${solutionEscapeHtml(item.badge)}</div>
                            <div class="proposal-case-body">
                                <h4>${solutionEscapeHtml(item.title)}</h4>
                                <p><strong>常规路径：</strong>${solutionEscapeHtml(item.left)}</p>
                                <p><strong>推荐路径：</strong>${solutionEscapeHtml(item.right)}</p>
                                <div class="proposal-case-effect">${solutionEscapeHtml(item.effect)}</div>
                            </div>
                        </article>
                    `).join('')}
                </div>
            </div>
        </section>
    `;
}

function solutionRenderBlueprintFigure(blueprint) {
    const figure = blueprint?.figure;
    const cards = solutionNormalizeList(blueprint?.cards);
    if (!figure?.groups?.length) {
        return cards.length ? `
            <div class="proposal-blueprint-card-grid">
                ${cards.map((item) => `
                    <article class="proposal-blueprint-card">
                        <div class="proposal-blueprint-card-tag">${solutionEscapeHtml(item.tag || '蓝图模块')}</div>
                        <h4>${solutionEscapeHtml(item.title)}</h4>
                        <p>${solutionEscapeHtml(item.summary || item.detail || '')}</p>
                    </article>
                `).join('')}
            </div>
        ` : '';
    }
    const nodeLabelMap = new Map();
    solutionNormalizeList(figure.groups).forEach((group) => {
        solutionNormalizeList(group.nodes).forEach((node) => {
            if (node?.id) nodeLabelMap.set(node.id, node.label || node.id);
        });
    });
    return `
        <div class="proposal-blueprint-shell">
            <div class="proposal-blueprint-lanes">
                ${solutionNormalizeList(figure.groups).map((group) => `
                    <article class="proposal-blueprint-lane">
                        <div class="proposal-blueprint-lane-label">${solutionEscapeHtml(group.label)}</div>
                        <div class="proposal-blueprint-node-list">
                            ${solutionNormalizeList(group.nodes).map((node) => `
                                <div class="proposal-blueprint-node">${solutionEscapeHtml(node.label)}</div>
                            `).join('')}
                        </div>
                    </article>
                `).join('')}
            </div>
            ${solutionNormalizeList(figure.edges).length ? `
                <div class="proposal-blueprint-flow-list">
                    ${solutionNormalizeList(figure.edges).map((edge) => `
                        <div class="proposal-blueprint-flow-item">
                            <span>${solutionEscapeHtml(nodeLabelMap.get(edge.from) || edge.from)}</span>
                            <span class="proposal-blueprint-flow-arrow">→</span>
                            <span>${solutionEscapeHtml(nodeLabelMap.get(edge.to) || edge.to)}</span>
                            ${edge.label ? `<span class="proposal-blueprint-flow-tag">${solutionEscapeHtml(edge.label)}</span>` : ''}
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        </div>
    `;
}

function solutionRenderSolutionTabsSection(section) {
    return `
        <section class="proposal-section" id="solutions" data-solution-section>
            ${solutionRenderSectionHead(section)}
            ${section.blueprint ? `
                <div class="proposal-blueprint-block">
                    <div class="proposal-blueprint-head">
                        <div class="proposal-section-label">${solutionEscapeHtml(section.blueprint.eyebrow || '推荐蓝图')}</div>
                        <h3>${solutionEscapeHtml(section.blueprint.title || '推荐蓝图')}</h3>
                        ${section.blueprint.summary ? `<p>${solutionEscapeHtml(section.blueprint.summary)}</p>` : ''}
                        ${section.blueprint.judgement ? `<div class="proposal-blueprint-judgement">${solutionEscapeHtml(section.blueprint.judgement)}</div>` : ''}
                    </div>
                    ${solutionRenderBlueprintFigure(section.blueprint)}
                </div>
            ` : ''}
            <div class="proposal-tabs" data-solution-tabs>
                <div class="proposal-tab-list" role="tablist" aria-label="落地方案模块">
                    ${solutionNormalizeList(section.tabs).map((item, index) => `
                        <button
                            type="button"
                            class="proposal-tab-button${index === 0 ? ' is-active' : ''}"
                            data-tab-target="${solutionEscapeHtml(item.id)}"
                            role="tab"
                            aria-selected="${index === 0 ? 'true' : 'false'}"
                        >
                            ${solutionEscapeHtml(item.label)}
                        </button>
                    `).join('')}
                </div>
                <div class="proposal-tab-panels">
                    ${solutionNormalizeList(section.tabs).map((item, index) => `
                        <article class="proposal-tab-panel${index === 0 ? ' is-active' : ''}" id="${solutionEscapeHtml(item.id)}" role="tabpanel" ${index === 0 ? '' : 'hidden'}>
                            <div class="proposal-tab-panel-head">
                                <div>
                                    <div class="proposal-tab-panel-tag">${solutionEscapeHtml(item.tag)}</div>
                                    <h3 class="proposal-tab-panel-title">${solutionEscapeHtml(item.headline)}</h3>
                                    <p class="proposal-tab-panel-summary">${solutionEscapeHtml(item.summary)}</p>
                                </div>
                                <div class="proposal-meta-pills">
                                    <span class="proposal-meta-pill">${solutionEscapeHtml(item.owner || '待定角色')}</span>
                                    ${item.dependencies[0] ? `<span class="proposal-meta-pill">${solutionEscapeHtml(item.dependencies[0])}</span>` : ''}
                                    ${item.deliverables[0] ? `<span class="proposal-meta-pill">${solutionEscapeHtml(item.deliverables[0])}</span>` : ''}
                                </div>
                            </div>
                            <div class="proposal-capability-grid">
                                ${solutionNormalizeList(item.capabilities).map((card) => `
                                    <article class="proposal-capability-card">
                                        <div class="proposal-capability-tag">${solutionEscapeHtml(card.tag || '能力')}</div>
                                        <h4>${solutionEscapeHtml(card.title)}</h4>
                                        <p>${solutionEscapeHtml(card.desc)}</p>
                                    </article>
                                `).join('')}
                            </div>
                            ${solutionNormalizeList(item.metrics).length ? `
                                <div class="proposal-tab-metrics">
                                    ${solutionNormalizeList(item.metrics).map((metric) => `
                                        <div class="proposal-tab-metric">
                                            <div class="proposal-tab-metric-label">${solutionEscapeHtml(metric.metric || metric.label || '指标')}</div>
                                            <div class="proposal-tab-metric-value">${solutionEscapeHtml(metric.target || metric.value || metric.range || '')}</div>
                                            ${metric.note ? `<div class="proposal-tab-metric-note">${solutionEscapeHtml(metric.note)}</div>` : ''}
                                        </div>
                                    `).join('')}
                                </div>
                            ` : ''}
                        </article>
                    `).join('')}
                </div>
            </div>
        </section>
    `;
}

function solutionRenderIntegrationSection(section) {
    return `
        <section class="proposal-section" id="integration" data-solution-section>
            ${solutionRenderSectionHead(section)}
            <div class="proposal-integration-grid">
                <article class="proposal-integration-card">
                    <div class="proposal-integration-card-head">
                        <div class="proposal-section-label">${solutionEscapeHtml(section.entryTitle || '关键接入入口')}</div>
                        <h3>${solutionEscapeHtml(section.entrySummary || '围绕高信号触点进入，先把首轮闭环跑通。')}</h3>
                    </div>
                    <div class="proposal-entry-stack">
                        ${solutionNormalizeList(section.leftScenarios).map((item) => `
                            <article class="proposal-entry-card">
                                <div class="proposal-entry-badge">${solutionEscapeHtml(item.eyebrow)}</div>
                                <div class="proposal-entry-title">${solutionEscapeHtml(item.title)}</div>
                                <div class="proposal-entry-detail">${solutionEscapeHtml(item.detail)}</div>
                            </article>
                        `).join('')}
                    </div>
                </article>
                <article class="proposal-integration-card">
                    <div class="proposal-integration-card-head">
                        <div class="proposal-section-label">${solutionEscapeHtml(section.pathTitle || '推进路径')}</div>
                        <h3>${solutionEscapeHtml(section.pathSummary || '先锁定阶段路径，再逐步打通执行闭环。')}</h3>
                    </div>
                    <div class="proposal-phase-path">
                        ${solutionNormalizeList(section.phases).map((item, index) => `
                            <article class="proposal-phase-card">
                                <div class="proposal-phase-step">${solutionEscapeHtml(String(index + 1).padStart(2, '0'))}</div>
                                <div class="proposal-phase-copy">
                                    <div class="proposal-phase-title">${solutionEscapeHtml(item.phase)}</div>
                                    <p>${solutionEscapeHtml(item.goal)}</p>
                                    ${solutionNormalizeList(item.actions).length ? `
                                        <ul class="proposal-bullet-list">
                                            ${solutionNormalizeList(item.actions).map((action) => `<li>${solutionEscapeHtml(action)}</li>`).join('')}
                                        </ul>
                                    ` : ''}
                                    ${item.milestone ? `<div class="proposal-phase-milestone">${solutionEscapeHtml(item.milestone)}</div>` : ''}
                                </div>
                            </article>
                        `).join('')}
                    </div>
                </article>
            </div>
            ${section.systemFigure?.groups?.length ? `
                <div class="proposal-system-figure-block">
                    <div class="proposal-system-figure-head">
                        <div class="proposal-section-label">${solutionEscapeHtml(section.figureTitle || '系统流转图')}</div>
                        <h3>${solutionEscapeHtml(section.figureSummary || '把入口、执行、回流和阶段节奏组织成真正的系统结构')}</h3>
                    </div>
                    ${solutionRenderBlueprintFigure({ figure: section.systemFigure, cards: [] })}
                </div>
            ` : ''}
        </section>
    `;
}

function solutionRenderKnowledgeSection(section) {
    return `
        <section class="proposal-section" id="knowledge" data-solution-section>
            ${solutionRenderSectionHead(section)}
            <div class="proposal-knowledge-contrast">
                <article class="proposal-knowledge-card is-problem">
                    <div class="proposal-knowledge-card-label">当前困境</div>
                    <ul class="proposal-bullet-list">
                        ${solutionNormalizeList(section.pains).map((item) => `<li>${solutionEscapeHtml(item)}</li>`).join('')}
                    </ul>
                </article>
                <article class="proposal-knowledge-card is-solution">
                    <div class="proposal-knowledge-card-label">统一方案</div>
                    <ul class="proposal-bullet-list">
                        ${solutionNormalizeList(section.solutions).map((item) => `<li>${solutionEscapeHtml(item)}</li>`).join('')}
                    </ul>
                </article>
            </div>
            <div class="proposal-layer-grid">
                ${solutionNormalizeList(section.layers).map((layer) => `
                    <article class="proposal-layer-card">
                        <div class="proposal-layer-title">${solutionEscapeHtml(layer.title)}</div>
                        <div class="proposal-layer-items">
                            ${solutionNormalizeList(layer.items).map((item) => `<span class="proposal-layer-pill">${solutionEscapeHtml(item)}</span>`).join('')}
                        </div>
                    </article>
                `).join('')}
            </div>
            <div class="proposal-loop-row">
                ${solutionNormalizeList(section.loop).map((item, index) => `
                    <div class="proposal-loop-item">
                        <div class="proposal-loop-title">${solutionEscapeHtml(item.title)}</div>
                        <div class="proposal-loop-detail">${solutionEscapeHtml(item.detail)}</div>
                        ${index < section.loop.length - 1 ? '<div class="proposal-loop-arrow">→</div>' : ''}
                    </div>
                `).join('')}
            </div>
        </section>
    `;
}

function solutionRenderFlywheelSection(section) {
    const nodes = solutionNormalizeList(section.diagram?.nodes);
    return `
        <section class="proposal-section" id="flywheel" data-solution-section>
            ${solutionRenderSectionHead(section)}
            <div class="proposal-flywheel-grid">
                <div class="proposal-flywheel-diagram">
                    <article class="proposal-flywheel-center">
                        <div class="proposal-flywheel-center-label">企业级方案中枢</div>
                        <h3>${solutionEscapeHtml(section.diagram.centerTitle)}</h3>
                        <p>${solutionEscapeHtml(section.diagram.centerDetail)}</p>
                    </article>
                    ${nodes[0] ? `<article class="proposal-flywheel-node is-top-left"><h4>${solutionEscapeHtml(nodes[0].title)}</h4><p>${solutionEscapeHtml(nodes[0].detail)}</p></article>` : ''}
                    ${nodes[1] ? `<article class="proposal-flywheel-node is-top-right"><h4>${solutionEscapeHtml(nodes[1].title)}</h4><p>${solutionEscapeHtml(nodes[1].detail)}</p></article>` : ''}
                    ${nodes[2] ? `<article class="proposal-flywheel-node is-bottom-left"><h4>${solutionEscapeHtml(nodes[2].title)}</h4><p>${solutionEscapeHtml(nodes[2].detail)}</p></article>` : ''}
                    ${nodes[3] ? `<article class="proposal-flywheel-node is-bottom-right"><h4>${solutionEscapeHtml(nodes[3].title)}</h4><p>${solutionEscapeHtml(nodes[3].detail)}</p></article>` : ''}
                </div>
                <div class="proposal-flywheel-case-list">
                    ${solutionNormalizeList(section.cases).map((item) => `
                        <article class="proposal-case-card">
                            <div class="proposal-case-badge">${solutionEscapeHtml(item.badge)}</div>
                            <div class="proposal-case-body">
                                <h4>${solutionEscapeHtml(item.title)}</h4>
                                <p>${solutionEscapeHtml(item.body)}</p>
                            </div>
                        </article>
                    `).join('')}
                </div>
            </div>
        </section>
    `;
}

function solutionRenderValueSection(section) {
    return `
        <section class="proposal-section" id="value" data-solution-section>
            ${solutionRenderSectionHead(section)}
            ${solutionRenderValueBoard(section.board)}
            <div class="proposal-value-grid">
                ${solutionNormalizeList(section.metrics).map((item) => `
                    <article class="proposal-value-card">
                        <div class="proposal-value-card-label">${solutionEscapeHtml(item.label)}</div>
                        <div class="proposal-value-card-value">${solutionEscapeHtml(item.value)}</div>
                        ${item.note ? `<div class="proposal-value-card-note">${solutionEscapeHtml(item.note)}</div>` : ''}
                    </article>
                `).join('')}
            </div>
            <button type="button" class="solution-expand-toggle" data-toggle-target="value-details">
                查看详细价值说明
            </button>
            <div class="proposal-expand-panel" id="value-details" hidden>
                <div class="proposal-detail-grid">
                    ${solutionNormalizeList(section.detailGroups).map((item) => `
                        <article class="proposal-detail-card">
                            <h4>${solutionEscapeHtml(item.title)}</h4>
                            <p>${solutionEscapeHtml(item.body)}</p>
                            ${item.note ? `<div class="proposal-detail-note">${solutionEscapeHtml(item.note)}</div>` : ''}
                        </article>
                    `).join('')}
                </div>
            </div>
        </section>
    `;
}

function solutionRenderFitSection(section) {
    return `
        <section class="proposal-section" id="fit" data-solution-section>
            ${solutionRenderSectionHead(section)}
            <div class="proposal-fit-grid">
                ${solutionNormalizeList(section.cards).map((item) => `
                    <article class="proposal-fit-card">
                        <div class="proposal-fit-tag">${solutionEscapeHtml(item.tag)}</div>
                        <h3>${solutionEscapeHtml(item.title)}</h3>
                        <p>${solutionEscapeHtml(item.desc)}</p>
                    </article>
                `).join('')}
            </div>
        </section>
    `;
}

function solutionRenderClosingSection(section, summaryCard) {
    if (!section?.headline && !section?.decision && !section?.boundary && !summaryCard?.title) return '';
    const hasClosingContent = Boolean(section?.headline || section?.decision || section?.boundary);
    return `
        <section class="proposal-section proposal-closing-section" id="closing" data-solution-section>
            <div class="proposal-closing-shell">
                <div class="proposal-closing-main">
                    <div class="proposal-section-label-row">
                        <span class="proposal-section-label">${solutionEscapeHtml(section?.eyebrow || '决策收束')}</span>
                        ${solutionRenderEvidenceButton(section?.title || '最终建议', section?.evidenceRefs || [])}
                    </div>
                    <h2 class="proposal-section-title">${solutionEscapeHtml(section?.title || '最终建议')}</h2>
                    ${section?.headline ? `<p class="proposal-closing-lead">${solutionEscapeHtml(section.headline)}</p>` : ''}
                    <div class="proposal-closing">
                        ${section?.decision ? `<p class="proposal-closing-decision">${solutionEscapeHtml(section.decision)}</p>` : ''}
                        ${section?.boundary ? `<p class="proposal-closing-boundary">${solutionEscapeHtml(section.boundary)}</p>` : ''}
                    </div>
                </div>
                ${!hasClosingContent && (summaryCard?.title || solutionNormalizeList(summaryCard?.bullets).length) ? `
                    <aside class="proposal-summary-card">
                        <div class="proposal-summary-card-kicker">${solutionEscapeHtml(summaryCard?.audienceLabel || '传播摘要')}</div>
                        ${summaryCard?.title ? `<h3>${solutionEscapeHtml(summaryCard.title)}</h3>` : ''}
                        <ul class="proposal-bullet-list">
                            ${solutionNormalizeList(summaryCard?.bullets).map((item) => `<li>${solutionEscapeHtml(item)}</li>`).join('')}
                        </ul>
                    </aside>
                ` : ''}
            </div>
        </section>
    `;
}

function solutionRenderGenericCards(items) {
    return `
        <div class="proposal-detail-grid">
            ${solutionNormalizeList(items).map((item) => `
                <article class="proposal-detail-card">
                    <div class="proposal-fit-tag">${solutionEscapeHtml(item.eyebrow || item.tag || '信息')}</div>
                    <h4>${solutionEscapeHtml(item.title || '未命名')}</h4>
                    ${item.summary ? `<p>${solutionEscapeHtml(item.summary)}</p>` : ''}
                    ${item.detail ? `<div class="proposal-detail-note">${solutionEscapeHtml(item.detail)}</div>` : ''}
                </article>
            `).join('')}
        </div>
    `;
}

function solutionRenderGenericTimeline(items) {
    return `
        <div class="proposal-phase-path">
            ${solutionNormalizeList(items).map((item, index) => `
                <article class="proposal-phase-card">
                    <div class="proposal-phase-step">${solutionEscapeHtml(item.step || String(index + 1).padStart(2, '0'))}</div>
                    <div class="proposal-phase-copy">
                        <div class="proposal-phase-title">${solutionEscapeHtml(item.title || '未命名阶段')}</div>
                        ${item.summary ? `<p>${solutionEscapeHtml(item.summary)}</p>` : ''}
                        ${item.detail ? `<div class="proposal-phase-milestone">${solutionEscapeHtml(item.detail)}</div>` : ''}
                        ${item.timeline ? `<div class="proposal-fit-tag">${solutionEscapeHtml(item.timeline)}</div>` : ''}
                    </div>
                </article>
            `).join('')}
        </div>
    `;
}

function solutionRenderGenericTable(section) {
    const columns = solutionNormalizeList(section.columns);
    const rows = solutionNormalizeList(section.rows);
    if (!columns.length || !rows.length) {
        return '<div class="solution-empty">当前章节暂无表格内容。</div>';
    }
    return `
        <div class="proposal-table-wrap">
            <table class="proposal-table">
                <thead>
                    <tr>
                        ${columns.map((column) => `<th>${solutionEscapeHtml(column?.label || column?.key || '')}</th>`).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${rows.map((row) => `
                        <tr>
                            ${columns.map((column) => `<td>${solutionEscapeHtml(solutionCellText(row?.[column?.key || ''])) || '-'}</td>`).join('')}
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function solutionRenderGenericText(paragraphs) {
    return `
        <div class="proposal-rich-text">
            ${solutionNormalizeList(paragraphs).map((item) => `<p>${solutionEscapeHtml(item)}</p>`).join('')}
        </div>
    `;
}

function solutionRenderGenericSection(section) {
    let body = '<div class="solution-empty">当前章节暂无内容。</div>';
    const layout = String(section?.layout || 'text').trim();
    if (layout === 'cards') body = solutionRenderGenericCards(section.items);
    else if (layout === 'steps' || layout === 'timeline') body = solutionRenderGenericTimeline(section.items);
    else if (layout === 'checklist') body = solutionRenderGenericCards(solutionNormalizeList(section.items).map((item) => ({
        title: item.title,
        summary: item.detail,
        detail: item.owner,
        eyebrow: '执行动作'
    })));
    else if (layout === 'table') body = solutionRenderGenericTable(section);
    else body = solutionRenderGenericText(section.paragraphs);

    return `
        <section class="proposal-section" id="${solutionEscapeHtml(section.id || 'section')}" data-solution-section>
            <div class="proposal-section-head">
                <div class="proposal-section-label-row">
                    <span class="proposal-section-label">${solutionEscapeHtml(section.kicker || section.label || '真实信息')}</span>
                </div>
                <h2 class="proposal-section-title">${solutionEscapeHtml(section.title || section.label || '未命名章节')}</h2>
                ${section.description ? `<p class="proposal-section-summary">${solutionEscapeHtml(section.description)}</p>` : ''}
            </div>
            ${body}
        </section>
    `;
}

function solutionRenderDegradedExperience(payload) {
    const content = document.getElementById('solution-content');
    if (!content) return [];
    const hero = payload?.hero || {};
    const sections = solutionNormalizeList(payload?.sections).filter((section) => section?.id);
    const navItems = [{ id: 'overview', label: '真实信息摘要' }].concat(sections.map((section) => ({
        id: section.id,
        label: section.label || section.title || '章节'
    })));
    content.innerHTML = `
        <section class="proposal-section proposal-hero" id="overview" data-solution-section>
            <div class="proposal-hero-grid">
                <div class="proposal-hero-copy">
                    <div class="proposal-hero-top">
                        <span class="proposal-eyebrow">${solutionEscapeHtml(hero.eyebrow || '真实信息摘要')}</span>
                        <span class="proposal-year-tag">${solutionEscapeHtml(SOLUTION_SOURCE_MODE_LABELS[payload?.source_mode] || '降级视图')}</span>
                    </div>
                    <h1 class="proposal-hero-title">${solutionEscapeHtml(payload?.title || hero?.title || '当前无法展示完整提案')}</h1>
                    ${payload?.subtitle ? `<p class="proposal-hero-subtitle">${solutionEscapeHtml(payload.subtitle)}</p>` : ''}
                    ${hero?.summary ? `<p class="proposal-hero-judgement">${solutionEscapeHtml(hero.summary)}</p>` : ''}
                </div>
                <div class="proposal-hero-side">
                    <div class="proposal-metric-wall">
                        ${solutionNormalizeList(hero?.metrics).map((item) => `
                            <article class="proposal-metric-card">
                                <div class="proposal-metric-label">${solutionEscapeHtml(item?.label || '指标')}</div>
                                <div class="proposal-metric-value">${solutionEscapeHtml(item?.value || '-')}</div>
                                ${item?.note ? `<div class="proposal-metric-note">${solutionEscapeHtml(item.note)}</div>` : ''}
                            </article>
                        `).join('')}
                    </div>
                </div>
            </div>
        </section>
        ${sections.map(solutionRenderGenericSection).join('')}
    `;
    return navItems;
}

function solutionRenderProposalExperience(model) {
    const content = document.getElementById('solution-content');
    if (!content) return [];
    content.innerHTML = [
        solutionRenderHeroSection(model.overview),
        solutionRenderComparisonSection(model.comparison),
        solutionRenderSolutionTabsSection(model.solutions),
        solutionRenderIntegrationSection(model.integration),
        solutionRenderKnowledgeSection(model.knowledge),
        solutionRenderFlywheelSection(model.flywheel),
        solutionRenderValueSection(model.value),
        solutionRenderFitSection(model.fit),
        solutionRenderClosingSection(model.closing, model.summaryCard)
    ].join('');
    return model.navItems;
}

function solutionRenderNavButtons(root, items, mobile = false) {
    if (!root) return;
    root.querySelectorAll('.solution-nav-button').forEach((button) => {
        button.classList.remove('is-active');
    });
    root.innerHTML = solutionNormalizeList(items).map((item) => `
        <button type="button" class="solution-nav-button${mobile ? ' is-mobile' : ''}" data-scroll-target="${solutionEscapeHtml(item.id)}">
            ${solutionEscapeHtml(item.label)}
        </button>
    `).join('');
}

function solutionOpenEvidenceDrawer(title, refs) {
    const drawer = document.getElementById('solution-evidence-drawer');
    const drawerTitle = document.getElementById('solution-evidence-title');
    const drawerBody = document.getElementById('solution-evidence-body');
    if (!drawer || !drawerTitle || !drawerBody) return;
    const list = solutionCollectRefs(refs);
    drawerTitle.textContent = title || '当前章节证据';
    drawerBody.innerHTML = list.length ? `
        <div class="solution-evidence-chip-list">
            ${list.map((ref) => `<span class="solution-evidence-chip">${solutionEscapeHtml(ref)}</span>`).join('')}
        </div>
        <div class="solution-evidence-note">后续可在这里继续展开访谈摘录、原始片段和更细的证据锚点说明。</div>
    ` : '<div class="solution-empty">当前章节暂无明确证据锚点。</div>';
    drawer.hidden = false;
    document.body.classList.add('is-evidence-open');
}

function solutionCloseEvidenceDrawer() {
    const drawer = document.getElementById('solution-evidence-drawer');
    if (!drawer) return;
    drawer.hidden = true;
    document.body.classList.remove('is-evidence-open');
}

function solutionBindEvidenceDrawer() {
    document.querySelectorAll('[data-evidence-title]').forEach((button) => {
        button.addEventListener('click', () => {
            const title = button.getAttribute('data-evidence-title') || '当前章节证据';
            const refs = (button.getAttribute('data-evidence-refs') || '').split('||').filter(Boolean);
            solutionOpenEvidenceDrawer(title, refs);
        });
    });
    document.querySelectorAll('[data-evidence-close]').forEach((button) => {
        button.addEventListener('click', solutionCloseEvidenceDrawer);
    });
}

function solutionBindScrollTargets() {
    document.querySelectorAll('[data-scroll-target]').forEach((button) => {
        button.addEventListener('click', () => {
            const targetId = button.getAttribute('data-scroll-target') || '';
            const target = document.getElementById(targetId);
            if (!target) return;
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });
}

function solutionBindTabs() {
    document.querySelectorAll('[data-solution-tabs]').forEach((root) => {
        const buttons = Array.from(root.querySelectorAll('.proposal-tab-button[data-tab-target]'));
        const panels = Array.from(root.querySelectorAll('.proposal-tab-panel'));
        buttons.forEach((button) => {
            button.addEventListener('click', () => {
                const target = button.getAttribute('data-tab-target');
                buttons.forEach((item) => {
                    const active = item === button;
                    item.classList.toggle('is-active', active);
                    item.setAttribute('aria-selected', active ? 'true' : 'false');
                });
                panels.forEach((panel) => {
                    const active = panel.id === target;
                    panel.classList.toggle('is-active', active);
                    panel.hidden = !active;
                });
            });
        });
    });
}

function solutionBindTogglePanels() {
    document.querySelectorAll('[data-toggle-target]').forEach((button) => {
        button.addEventListener('click', () => {
            const target = document.getElementById(button.getAttribute('data-toggle-target') || '');
            if (!target) return;
            const nextHidden = !target.hidden;
            target.hidden = nextHidden;
            button.classList.toggle('is-open', !nextHidden);
            button.textContent = nextHidden ? button.textContent.replace('收起', '查看') : button.textContent.replace('查看', '收起');
        });
    });
}

function solutionBindScrollSpy() {
    if (typeof IntersectionObserver === 'undefined') return;
    const topButtons = Array.from(document.querySelectorAll('.solution-topbar .solution-nav-button[data-scroll-target]'));
    const mobileButtons = Array.from(document.querySelectorAll('.solution-mobile-nav .solution-nav-button[data-scroll-target]'));
    const buttonGroups = [topButtons, mobileButtons].filter((group) => group.length);
    const sections = Array.from(document.querySelectorAll('[data-solution-section]'));
    if (!buttonGroups.length || !sections.length) return;

    const setActive = (id) => {
        buttonGroups.forEach((group) => {
            group.forEach((button) => {
                button.classList.toggle('is-active', button.getAttribute('data-scroll-target') === id);
            });
        });
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                setActive(entry.target.id);
            }
        });
    }, {
        rootMargin: '-18% 0px -62% 0px',
        threshold: [0.15, 0.35, 0.6]
    });

    sections.forEach((section) => observer.observe(section));
    if (sections[0]) setActive(sections[0].id);
}

function solutionRegisterReveals() {
    const sections = Array.from(document.querySelectorAll('[data-solution-section]'));
    if (!sections.length || typeof IntersectionObserver === 'undefined') {
        sections.forEach((section) => section.classList.add('is-visible'));
        return;
    }
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.12,
        rootMargin: '0px 0px -8% 0px'
    });
    sections.forEach((section) => observer.observe(section));
}

function solutionRender(payload) {
    const model = solutionBuildProposalModel(payload);
    document.title = `${model?.overview?.title || payload?.title || '查看方案'} | DeepVision`;
    const shell = document.getElementById('solution-shell');
    const state = document.getElementById('solution-state-card');
    if (!shell || !state) return;

    solutionRenderTopbar(model, payload);
    solutionRenderQualityStrip(payload);
    const navItems = payload?.source_mode === 'degraded' || !model.hasProposal
        ? solutionRenderDegradedExperience(payload)
        : solutionRenderProposalExperience(model);

    const navRoot = document.querySelector('.solution-topbar .solution-nav');
    const mobileNavRoot = document.getElementById('solution-mobile-nav');
    solutionRenderNavButtons(navRoot, navItems);
    solutionRenderNavButtons(mobileNavRoot, navItems, true);

    state.hidden = true;
    shell.hidden = false;
    solutionBindEvidenceDrawer();
    solutionBindScrollTargets();
    solutionBindTabs();
    solutionBindTogglePanels();
    solutionBindScrollSpy();
    solutionRegisterReveals();
}

async function initSolutionPage() {
    const reportName = solutionGetReportName();
    if (!reportName) {
        solutionSetState('缺少报告参数', '请从访谈报告详情页点击“查看方案”进入。', '参数错误');
        return;
    }

    try {
        const payload = await solutionApiCall(`/reports/${encodeURIComponent(reportName)}/solution`);
        solutionRender(payload);
    } catch (error) {
        if (error.status === 401) {
            solutionSetState('登录已失效', '请先返回主站登录，再重新打开方案页。', '需要登录');
            return;
        }
        if (error.status === 404) {
            solutionSetState('报告不存在', '当前报告不存在，或你没有权限查看对应方案。', '未找到');
            return;
        }
        solutionSetState('方案加载失败', error.message || '暂时无法生成方案，请稍后重试。', '加载失败');
    }
}

document.addEventListener('DOMContentLoaded', initSolutionPage);

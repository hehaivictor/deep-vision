const SOLUTION_ASSET_VERSION = '20260310-solution-v16';
const SOLUTION_API_BASE = `${window.location.origin}/api`;

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

function solutionShortText(value, maxLength = 36) {
    const normalized = String(value || '').trim().replace(/\s+/g, ' ');
    if (!normalized) return '';
    if (normalized.length <= maxLength) return normalized;
    return `${normalized.slice(0, maxLength).trim()}...`;
}

function solutionGetReportName() {
    const params = new URLSearchParams(window.location.search || '');
    return String(params.get('report') || '').trim();
}

function solutionBuildReportUrl(reportName = '') {
    const normalized = String(reportName || '').trim();
    if (!normalized) return 'index.html?view=reports';
    const params = new URLSearchParams();
    params.set('view', 'reports');
    params.set('report', normalized);
    params.set('v', SOLUTION_ASSET_VERSION);
    return `index.html?${params.toString()}`;
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
    const response = await fetch(`${SOLUTION_API_BASE}${endpoint}`, {
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

function solutionSetSectionVisibility(id, visible) {
    const section = document.getElementById(id);
    if (!section) return false;
    section.hidden = !visible;
    return visible;
}

function solutionDefaultNavItems() {
    return [
        { id: 'decision', label: '方案判断' },
        { id: 'comparison', label: '方案对比' },
        { id: 'modules', label: '落地模块' },
        { id: 'architecture', label: '能力架构' },
        { id: 'dataflow', label: '闭环机制' },
        { id: 'value', label: '价值测算' },
        { id: 'roadmap', label: '实施路径' },
        { id: 'risks', label: '风险边界' },
        { id: 'actions', label: '下一步推进' }
    ];
}

function solutionRenderNav(items, visibleIds) {
    const nav = document.getElementById('solution-nav');
    if (!nav) return;
    const fallback = solutionDefaultNavItems();
    const navItems = solutionNormalizeList(items).length ? solutionNormalizeList(items) : fallback;
    const allowed = visibleIds instanceof Set ? visibleIds : new Set();
    const filtered = navItems.filter((item) => !allowed.size || allowed.has(item.id));
    nav.innerHTML = filtered.map((item) => `
        <button type="button" class="solution-nav-button" data-target="${solutionEscapeHtml(item.id)}">
            ${solutionEscapeHtml(item.label)}
        </button>
    `).join('');

    nav.querySelectorAll('[data-target]').forEach((button) => {
        button.addEventListener('click', () => {
            const targetId = button.getAttribute('data-target') || '';
            const target = document.getElementById(targetId);
            if (!target) return;
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            target.classList.add('is-highlight');
            window.setTimeout(() => target.classList.remove('is-highlight'), 1200);
        });
    });
}

function solutionNormalizeCompareText(value) {
    return String(value || '')
        .trim()
        .replace(/\s+/g, '')
        .replace(/[《》「」"'“”‘’、，。！？!?:：;；\-—（）()【】\[\]\/]/g, '')
        .toLowerCase();
}

function solutionTextRepeats(value, references = []) {
    const current = solutionNormalizeCompareText(value);
    if (!current) return true;
    return references.some((reference) => {
        const normalized = solutionNormalizeCompareText(reference);
        if (!normalized) return false;
        return normalized.includes(current) || current.includes(normalized);
    });
}

function solutionFilterUniqueInfoItems(items, references = [], limit = 3) {
    const pool = Array.isArray(references) ? [...references] : [];
    const seen = new Set();
    const results = [];

    for (const item of solutionNormalizeList(items)) {
        const label = String(item?.label || '').trim();
        const value = String(item?.value || '').trim();
        if (!value) continue;

        const normalized = solutionNormalizeCompareText(`${label}${value}`);
        if (!normalized || seen.has(normalized) || solutionTextRepeats(value, pool)) {
            continue;
        }

        seen.add(normalized);
        pool.push(value);
        results.push(item);
        if (results.length >= limit) break;
    }

    return results;
}

function solutionBuildRoadmapSpan(items) {
    const steps = solutionNormalizeList(items).slice(0, 3);
    if (!steps.length) return '';

    const first = String(steps[0]?.timeline || '').trim();
    const last = String(steps[steps.length - 1]?.timeline || '').trim();
    const firstMatch = first.match(/(\d+)\s*-\s*(\d+)/);
    const lastMatch = last.match(/(\d+)\s*-\s*(\d+)/);

    if (firstMatch && lastMatch) {
        return `第${firstMatch[1]}-${lastMatch[2]}周`;
    }
    return last || first;
}

function solutionSplitHeroTitle(value) {
    const title = String(value || '').trim() || '查看方案';
    const suffixes = ['落地方案', '实施方案', '解决方案', '提案方案'];
    for (const suffix of suffixes) {
        if (title.endsWith(suffix) && title.length > suffix.length) {
            return {
                primary: title.slice(0, -suffix.length).trim(),
                secondary: suffix
            };
        }
    }
    if (title.length >= 10) {
        const splitIndex = Math.ceil(title.length * 0.58);
        return {
            primary: title.slice(0, splitIndex).trim(),
            secondary: title.slice(splitIndex).trim()
        };
    }
    return { primary: title, secondary: '' };
}

function solutionRenderHeroPrimary(payload, decisionCards) {
    const root = document.getElementById('solution-hero-primary');
    if (!root) return false;

    const cards = solutionNormalizeList(decisionCards);
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const scene = headlineCards[0]?.value || payload.title || '当前场景';
    const entry = headlineCards[2]?.value || '关键触点';
    const primary = cards[0] || null;
    const verdict = primary?.title && !solutionTextRepeats(primary.title, [payload.title])
        ? primary.title
        : '适合立即推进首轮试点';
    const fallbackCopy = `围绕「${solutionShortText(scene, 14)}」启动首轮试点，优先从「${solutionShortText(entry, 12)}」切入验证。`;
    const decisionSummary = payload.decision_summary || primary?.summary || payload.overview || '';
    const copy = decisionSummary && !solutionTextRepeats(decisionSummary, [verdict, payload.title])
        ? decisionSummary
        : fallbackCopy;
    const tags = [
        { label: '聚焦场景', value: scene },
        { label: '推进切口', value: entry }
    ].filter((item) => item.value);

    root.hidden = !verdict && !copy;
    root.innerHTML = `
        <div class="solution-hero-primary-kicker">主判断</div>
        <h2 class="solution-hero-primary-title">${solutionEscapeHtml(solutionShortText(verdict, 18))}</h2>
        <p class="solution-hero-primary-copy">${solutionEscapeHtml(solutionShortText(copy, 60))}</p>
        <div class="solution-hero-primary-tags">
            ${tags.map((item) => `
                <div class="solution-hero-primary-tag">
                    <span class="solution-hero-primary-tag-label">${solutionEscapeHtml(item.label)}</span>
                    <span class="solution-hero-primary-tag-value">${solutionEscapeHtml(solutionShortText(item.value, 14))}</span>
                </div>
            `).join('')}
        </div>
    `;
    return !root.hidden;
}

function solutionRenderHeroSignals(payload) {
    const root = document.getElementById('solution-hero-signals');
    if (!root) return false;

    const roadmap = solutionNormalizeList(payload.roadmap).slice(0, 3);
    if (roadmap.length) {
        root.hidden = true;
        root.innerHTML = '';
        return false;
    }

    const signals = roadmap.map((item, index) => ({
        label: item.phase || `阶段 ${index + 1}`,
        value: item.timeline || '推进中'
    }));

    root.hidden = !signals.length;
    root.innerHTML = signals.map((item, index) => `
        <article class="solution-hero-signal" data-accent="${index % 4}">
            <div class="solution-hero-signal-label">${solutionEscapeHtml(solutionShortText(item.label, 16))}</div>
            <div class="solution-hero-signal-value">${solutionEscapeHtml(solutionShortText(item.value, 10))}</div>
        </article>
    `).join('');
    return signals.length > 0;
}

function solutionRenderHeroStage(payload) {
    const root = document.getElementById('solution-hero-stage');
    if (!root) return false;

    const roadmap = solutionNormalizeList(payload.roadmap).slice(0, 3);
    const overview = payload.overview || payload.decision_summary || '';
    const cards = roadmap.length ? roadmap.map((item, index) => {
        const phaseParts = String(item.phase || '').split('·').map((part) => part.trim()).filter(Boolean);
        return {
            label: phaseParts[0] || `阶段 ${index + 1}`,
            value: phaseParts[1] || item.goal || `步骤 ${index + 1}`,
            detail: item.goal || '',
            timeline: item.timeline || ''
        };
    }) : [
        { label: '阶段一', value: '场景对齐', detail: '统一问题、样本与试点范围。', timeline: '第 1-2 周' },
        { label: '阶段二', value: '方案设计', detail: '形成可评审的流程、原型与清单。', timeline: '第 3-5 周' },
        { label: '阶段三', value: '试点验证', detail: '回收结果并判断是否进入扩展。', timeline: '第 6-8 周' }
    ];
    const summary = cards[0]?.detail || overview;
    const badgeText = (cards[cards.length - 1] && cards[cards.length - 1].timeline) || '三步闭环';

    root.innerHTML = `
        <div class="solution-hero-stage-head">
            <div>
                <div class="solution-hero-stage-kicker">首轮推进节奏</div>
                <h2 class="solution-hero-stage-title">三步完成从共识到试点</h2>
            </div>
            <div class="solution-hero-stage-badge">${solutionEscapeHtml(solutionShortText(badgeText, 12))}</div>
        </div>
        ${summary ? `<p class="solution-hero-stage-summary">${solutionEscapeHtml(solutionShortText(summary, 64))}</p>` : ''}
        <div class="solution-hero-stage-grid">
            ${cards.map((item, index) => `
                <article class="solution-hero-stage-card" data-accent="${index % 4}">
                    <div class="solution-hero-stage-card-top">
                        <div class="solution-hero-stage-index">${String(index + 1).padStart(2, '0')}</div>
                        ${item.timeline ? `<div class="solution-hero-stage-timeline">${solutionEscapeHtml(solutionShortText(item.timeline, 12))}</div>` : ''}
                    </div>
                    <div class="solution-hero-stage-card-label">${solutionEscapeHtml(item.label)}</div>
                    <div class="solution-hero-stage-card-value">${solutionEscapeHtml(solutionShortText(item.value, 14))}</div>
                    ${item.detail ? `<div class="solution-hero-stage-card-detail">${solutionEscapeHtml(solutionShortText(item.detail, 34))}</div>` : ''}
                </article>
            `).join('')}
        </div>
    `;
    return true;
}

function solutionRenderHeroFocus(payload, decisionCards) {
    const root = document.getElementById('solution-hero-focus');
    if (!root) return false;

    const cards = solutionNormalizeList(decisionCards);
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const primary = cards[0] || null;
    const title = primary?.title || '建议进入首轮试点';
    const summary = primary?.summary || payload.decision_summary || payload.overview || '根据当前访谈报告提炼首轮试点路径。';
    const detail = primary?.detail || payload.overview || '';
    const detailText = solutionTextRepeats(detail, [title, summary, payload.decision_summary, payload.overview]) ? '' : detail;
    const facts = solutionFilterUniqueInfoItems(
        [headlineCards[0], headlineCards[1], headlineCards[2]],
        [title, summary, detailText, payload.title, payload.subtitle],
        2
    );

    root.innerHTML = `
        <article class="solution-hero-focus-card">
            <div class="solution-hero-focus-topline">
                <div class="solution-hero-focus-kicker">决策结论</div>
                <div class="solution-hero-focus-badge">A 级建议</div>
            </div>
            <h2 class="solution-hero-focus-title">${solutionEscapeHtml(solutionShortText(title, 20))}</h2>
            <p class="solution-hero-focus-copy">${solutionEscapeHtml(solutionShortText(summary, 60))}</p>
            ${detailText ? `<p class="solution-hero-focus-meta">${solutionEscapeHtml(solutionShortText(detailText, 72))}</p>` : ''}
            ${facts.length ? `<div class="solution-hero-focus-facts">
                ${facts.map((item) => `
                    <div class="solution-hero-focus-fact">
                        <div class="solution-hero-focus-fact-label">${solutionEscapeHtml(item.label || '信息')}</div>
                        <div class="solution-hero-focus-fact-value">${solutionEscapeHtml(solutionShortText(item.value, 14))}</div>
                    </div>
                `).join('')}
            </div>` : ''}
            <div class="solution-hero-focus-foot">
                <span class="solution-hero-focus-pill">建议立即推进</span>
                <span class="solution-hero-focus-pill solution-hero-focus-pill-subtle">控制在首轮试点</span>
            </div>
        </article>
    `;
    return true;
}

function solutionRenderHeroActions(actionItems, decisionCards) {
    const root = document.getElementById('solution-hero-actions');
    if (!root) return false;

    let items = solutionNormalizeList(actionItems).slice(0, 2);
    if (!items.length) {
        items = solutionNormalizeList(decisionCards).slice(0, 2).map((item, index) => ({
            owner: `判断 ${index + 1}`,
            title: item.title,
            detail: item.summary || item.detail || ''
        }));
    }

    root.hidden = !items.length;
    root.innerHTML = items.map((item, index) => `
        <article class="solution-hero-action-item" data-accent="${index % 4}">
            <div class="solution-hero-action-step">${String(index + 1).padStart(2, '0')}</div>
            <div class="solution-hero-action-body">
                <div class="solution-hero-action-owner">${solutionEscapeHtml(item.owner || '立即推进')}</div>
                <div class="solution-hero-action-title">${solutionEscapeHtml(solutionShortText(item.title, 22))}</div>
                ${item.detail ? `<div class="solution-hero-action-detail">${solutionEscapeHtml(solutionShortText(item.detail, 24))}</div>` : ''}
            </div>
        </article>
    `).join('');
    return items.length > 0;
}

function solutionRenderHeroMetrics(items, roadmap) {
    const root = document.getElementById('solution-hero-metric-row');
    if (!root) return false;

    const metrics = solutionNormalizeList(items).slice(0, 2);
    const timeline = solutionBuildRoadmapSpan(roadmap);
    const chips = [
        timeline ? { label: '首轮周期', value: timeline } : null,
        ...metrics.map((item) => ({ label: item.label, value: item.value }))
    ].filter(Boolean);

    root.hidden = !chips.length;
    root.innerHTML = chips.map((item) => `
        <article class="solution-hero-metric-chip">
            <div class="solution-hero-metric-chip-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-hero-metric-chip-value">${solutionEscapeHtml(item.value)}</div>
        </article>
    `).join('');
    return chips.length > 0;
}

function solutionRenderDecisionSummary(payload, decisionCards) {
    const root = document.getElementById('solution-decision-summary-card');
    if (!root) return false;

    const cards = solutionNormalizeList(decisionCards);
    const metas = solutionNormalizeList(payload.overview_meta).slice(0, 4);
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const scene = metas.find((item) => item.label === '聚焦场景')?.value || headlineCards[0]?.value || payload.title || '当前场景';
    const entry = metas.find((item) => item.label === '推进切口')?.value || headlineCards[2]?.value || '关键触点';
    const readyCount = metas.length || 4;
    const verdict = cards.length ? '适合现在推进' : '可进入首轮试点';
    const note = `${readyCount} 项前提已具备，建议围绕「${solutionShortText(scene, 14)}」启动首轮试点。`;
    const sideNote = `先从「${solutionShortText(entry, 12)}」切入，不建议直接大范围铺开。`;

    root.innerHTML = `
        <div class="solution-decision-verdict-kicker">判断结论</div>
        <div class="solution-decision-verdict-main">${solutionEscapeHtml(verdict)}</div>
        <p class="solution-decision-verdict-copy">${solutionEscapeHtml(note)}</p>
        <div class="solution-decision-verdict-tags">
            <span class="solution-decision-tag">建议立即推进</span>
            <span class="solution-decision-tag solution-decision-tag-subtle">控制在首轮试点</span>
        </div>
        <div class="solution-decision-verdict-side">${solutionEscapeHtml(sideNote)}</div>
    `;
    return true;
}

function solutionRenderOverviewMeta(items) {
    const root = document.getElementById('solution-overview-meta');
    if (!root) return false;
    const metas = solutionNormalizeList(items).slice(0, 4);
    root.innerHTML = metas.map((item, index) => {
        const isBoundary = String(item.label || '').includes('边界');
        const status = isBoundary ? '需控制' : '已明确';
        const tone = isBoundary ? 'warning' : (index === 0 ? 'focus' : 'ready');
        return `
            <article class="solution-decision-signal" data-tone="${tone}">
                <div class="solution-decision-signal-head">
                    <div class="solution-decision-signal-label">${solutionEscapeHtml(item.label)}</div>
                    <div class="solution-decision-signal-status" data-tone="${tone}">${solutionEscapeHtml(status)}</div>
                </div>
                <div class="solution-decision-signal-value">${solutionEscapeHtml(solutionShortText(item.value, 18))}</div>
            </article>
        `;
    }).join('');
    return metas.length > 0;
}

function solutionBuildDecisionFallback(payload) {
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const focusCards = solutionNormalizeList(payload.focus_cards);
    const roadmap = solutionNormalizeList(payload.roadmap);
    const valueCards = solutionNormalizeList(payload.value_cards);
    const scene = headlineCards[0]?.value || payload.title || '当前业务场景';
    const pain = headlineCards[1]?.value || '核心问题';
    const entry = headlineCards[2]?.value || '关键触点';
    const constraint = headlineCards[3]?.value || '试点边界';
    const phase = roadmap[0]?.goal || '先统一试点范围，再进入方案设计与验证';
    const value = valueCards[0]?.value || '首轮收益';
    return [
        {
            title: '为什么现在推进',
            summary: focusCards[0]?.summary || `围绕「${scene}」已经形成足够清晰的试点切口。`,
            detail: payload.decision_summary || `当前报告已经把「${pain}」明确为首轮优先验证的问题，可直接进入试点规划。`
        },
        {
            title: '为什么先从这个切口进入',
            summary: focusCards[2]?.summary || `优先从「${entry}」切入，更容易快速看到业务反馈。`,
            detail: phase
        },
        {
            title: '为什么这份报告足以支持判断',
            summary: focusCards[1]?.summary || `报告已补齐与「${pain}」相关的用户心理、流程触点与执行边界。`,
            detail: `在「${constraint}」边界内，预期可率先验证 ${value} 的改善空间。`
        }
    ];
}

function solutionRenderDecisionCards(items) {
    const root = document.getElementById('solution-decision-cards');
    if (!root) return false;
    const cards = solutionNormalizeList(items).slice(0, 3);
    root.innerHTML = !cards.length ? '' : `
        <div class="solution-decision-evidence-head">支持判断的依据</div>
        ${cards.map((item, index) => {
            const summary = !solutionTextRepeats(item.summary, [item.title])
                ? item.summary
                : (!solutionTextRepeats(item.detail, [item.title, item.summary]) ? item.detail : '');
            return `
                <article class="solution-decision-evidence-item" data-accent="${index % 4}">
                    <div class="solution-decision-evidence-index">${String(index + 1).padStart(2, '0')}</div>
                    <div class="solution-decision-evidence-body">
                        <h3 class="solution-decision-evidence-title">${solutionEscapeHtml(solutionShortText(item.title, 18))}</h3>
                        ${summary ? `<p class="solution-decision-evidence-copy">${solutionEscapeHtml(solutionShortText(summary, 38))}</p>` : ''}
                    </div>
                </article>
            `;
        }).join('')}
    `;
    return cards.length > 0;
}

function solutionBuildComparisonFallback(payload) {
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const scene = headlineCards[0]?.value || payload.title || '当前场景';
    const pain = headlineCards[1]?.value || '核心问题';
    const entry = headlineCards[2]?.value || '关键触点';
    return [
        {
            label: '洞察形成',
            traditional: '依赖人工整理纪要，问题归因分散在多个文档和讨论中。',
            proposed: `围绕「${scene}」提炼结构化问题、模块和试点动作，形成统一提案。`,
            effect: '让结论从主观判断变为可复盘的方案资产。'
        },
        {
            label: '推进速度',
            traditional: '需要多轮跨团队对齐后才能进入试点，前期沟通成本高。',
            proposed: `优先从「${entry}」进入首轮试跑，先验证高价值触点。`,
            effect: '缩短从报告生成到业务试点的启动链路。'
        },
        {
            label: '组织协同',
            traditional: '产品、研究、设计、研发各自理解问题，协同口径难统一。',
            proposed: '通过模块、路径、风险和动作四类结构化信息形成统一协作面。',
            effect: '降低内部认知偏差和推进扯皮成本。'
        },
        {
            label: '价值沉淀',
            traditional: `即使解决了「${pain}」，经验也容易停留在单次项目中。`,
            proposed: '将方案沉淀为可复用的章节化提案与后续试点模板。',
            effect: '让首轮试点结果可继续向后续场景复制。'
        }
    ];
}

function solutionRenderComparison(items) {
    const root = document.getElementById('solution-comparison-grid');
    if (!root) return false;
    const cards = solutionNormalizeList(items);
    root.innerHTML = cards.map((item, index) => `
        <article class="solution-compare-card solution-glass-card" data-accent="${index % 4}">
            <div class="solution-compare-head">
                <div class="solution-compare-label">${solutionEscapeHtml(item.label)}</div>
                <div class="solution-card-index">${String(index + 1).padStart(2, '0')}</div>
            </div>
            <div class="solution-compare-body">
                <div class="solution-compare-column solution-compare-column-muted">
                    <div class="solution-compare-kicker">传统方式</div>
                    <p>${solutionEscapeHtml(item.traditional)}</p>
                </div>
                <div class="solution-compare-column solution-compare-column-active">
                    <div class="solution-compare-kicker">DeepVision 方案</div>
                    <p>${solutionEscapeHtml(item.proposed)}</p>
                </div>
            </div>
            <div class="solution-compare-foot">${solutionEscapeHtml(item.effect)}</div>
        </article>
    `).join('');
    return cards.length > 0;
}

function solutionRenderDimensionCards(items) {
    const root = document.getElementById('solution-dimension-cards');
    if (!root) return false;
    const cards = solutionNormalizeList(items);
    root.innerHTML = cards.map((item, index) => {
        const points = solutionNormalizeList(item.points);
        return `
        <article class="solution-card solution-card-module" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-card-badge">${solutionEscapeHtml(item.badge || '业务模块')}</div>
                <div class="solution-card-index">${String(index + 1).padStart(2, '0')}</div>
            </div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.name)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.summary)}</p>
            <ul class="solution-card-list">
                ${points.map((point) => `<li>${solutionEscapeHtml(point)}</li>`).join('')}
            </ul>
            <div class="solution-card-foot">
                <span>模块要点</span>
                <span>${points.length || 0} 项</span>
            </div>
        </article>`;
    }).join('');
    return cards.length > 0;
}

function solutionBuildArchitectureFallback(payload) {
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const roadmap = solutionNormalizeList(payload.roadmap);
    const metrics = solutionNormalizeList(payload.metrics);
    const scene = headlineCards[0]?.value || payload.title || '当前场景';
    const pain = headlineCards[1]?.value || '核心问题';
    const entry = headlineCards[2]?.value || '关键触点';
    const constraint = headlineCards[3]?.value || '试点边界';
    return [
        {
            stage: '输入层',
            title: '访谈输入',
            summary: `围绕「${scene}」组织样本、问题和原始回答，形成首轮输入池。`,
            inputs: ['场景目标', '样本回答'],
            outputs: ['原始素材', '关键触点']
        },
        {
            stage: '诊断层',
            title: '问题识别',
            summary: `把「${pain}」拆成问题树、假设与优先级，避免停留在表层现象。`,
            inputs: ['访谈内容', '问题标签'],
            outputs: ['问题树', '优先级']
        },
        {
            stage: '方案层',
            title: '方案映射',
            summary: '把识别出的关键问题映射为可落地的模块、对比和价值主张。',
            inputs: ['问题树', '模块清单'],
            outputs: ['模块方案', '价值主张']
        },
        {
            stage: '执行层',
            title: '试点推进',
            summary: roadmap[1]?.goal || `围绕「${entry}」组织路径、里程碑和动作清单。`,
            inputs: ['实施路径', '动作清单'],
            outputs: ['试点任务', '协同节奏']
        },
        {
            stage: '反馈层',
            title: '价值回流',
            summary: `在「${constraint}」边界内，用指标和复盘结果持续校准方案优先级。`,
            inputs: metrics.slice(0, 2).map((item) => item.label),
            outputs: ['价值测算', '二期建议']
        }
    ];
}

function solutionRenderChipList(items) {
    return solutionNormalizeList(items).map((item) => `<span class="solution-chip">${solutionEscapeHtml(item)}</span>`).join('');
}

function solutionRenderArchitecture(items) {
    const root = document.getElementById('solution-architecture-map');
    if (!root) return false;
    const nodes = solutionNormalizeList(items);
    root.innerHTML = nodes.map((item, index) => `
        <article class="solution-architecture-node solution-glass-card" data-accent="${index % 4}">
            <div class="solution-architecture-stage">${solutionEscapeHtml(item.stage || `阶段 ${index + 1}`)}</div>
            <h3 class="solution-architecture-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-architecture-copy">${solutionEscapeHtml(item.summary)}</p>
            <div class="solution-architecture-meta">
                <div>
                    <div class="solution-architecture-meta-label">输入</div>
                    <div class="solution-chip-list">${solutionRenderChipList(item.inputs)}</div>
                </div>
                <div>
                    <div class="solution-architecture-meta-label">输出</div>
                    <div class="solution-chip-list">${solutionRenderChipList(item.outputs)}</div>
                </div>
            </div>
        </article>
    `).join('');
    return nodes.length > 0;
}

function solutionBuildDataflowFallback(payload) {
    const roadmap = solutionNormalizeList(payload.roadmap);
    const actions = solutionNormalizeList(payload.action_items);
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const scene = headlineCards[0]?.value || payload.title || '当前场景';
    const entry = headlineCards[2]?.value || '关键触点';
    return [
        {
            stage: '01',
            title: '锁定场景与样本',
            detail: `围绕「${scene}」确定首轮样本范围、触发时机与回收标准。`,
            owner: '产品 / 研究'
        },
        {
            stage: '02',
            title: '识别问题与优先级',
            detail: roadmap[0]?.tasks?.[0] || '从访谈回答中提取核心问题、假设与试点优先级。',
            owner: '研究 / 产品'
        },
        {
            stage: '03',
            title: '映射模块与方案',
            detail: `将「${entry}」相关问题映射为模块方案、路径设计和边界控制。`,
            owner: '产品 / 设计'
        },
        {
            stage: '04',
            title: '进入试点执行',
            detail: roadmap[1]?.goal || '把方案转成原型、试点动作和协同清单。',
            owner: '设计 / 研发'
        },
        {
            stage: '05',
            title: '回收结果并迭代',
            detail: actions[actions.length - 1]?.detail || '用指标和业务反馈复盘结果，决定下一轮扩展策略。',
            owner: '运营 / 管理'
        }
    ];
}

function solutionRenderDataflow(items) {
    const root = document.getElementById('solution-dataflow-steps');
    if (!root) return false;
    const steps = solutionNormalizeList(items);
    root.innerHTML = steps.map((item, index) => `
        <article class="solution-flow-step solution-glass-card" data-accent="${index % 4}">
            <div class="solution-flow-index">${solutionEscapeHtml(item.stage || String(index + 1).padStart(2, '0'))}</div>
            <div class="solution-flow-body">
                <div class="solution-flow-owner">${solutionEscapeHtml(item.owner || '协同推进')}</div>
                <h3 class="solution-flow-title">${solutionEscapeHtml(item.title)}</h3>
                <p class="solution-flow-copy">${solutionEscapeHtml(item.detail)}</p>
            </div>
        </article>
    `).join('');
    return steps.length > 0;
}

function solutionRenderMetrics(items) {
    const root = document.getElementById('solution-metrics');
    if (!root) return false;
    const metrics = solutionNormalizeList(items);
    root.innerHTML = metrics.map((item) => `
        <article class="solution-metric-card solution-glass-card">
            <div class="solution-metric-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-metric-value">${solutionEscapeHtml(item.value)}</div>
            <div class="solution-metric-note">${solutionEscapeHtml(item.note)}</div>
        </article>
    `).join('');
    return metrics.length > 0;
}

function solutionRenderValueCards(items) {
    const root = document.getElementById('solution-value-cards');
    if (!root) return false;
    const cards = solutionNormalizeList(items);
    root.innerHTML = cards.map((item, index) => `
        <article class="solution-card solution-card-value" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-card-badge">预期收益</div>
                <div class="solution-card-index">${String(index + 1).padStart(2, '0')}</div>
            </div>
            <h3 class="solution-card-title solution-card-value-hero">${solutionEscapeHtml(item.value)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.title)}</p>
            <p class="solution-card-meta">${solutionEscapeHtml(item.description)}</p>
        </article>
    `).join('');
    return cards.length > 0;
}

function solutionBuildValueDetailFallback(payload) {
    const metrics = solutionNormalizeList(payload.metrics);
    const valueCards = solutionNormalizeList(payload.value_cards);
    const headlineCards = solutionNormalizeList(payload.headline_cards);
    const scene = headlineCards[0]?.value || payload.title || '当前场景';
    const entry = headlineCards[2]?.value || '关键触点';
    const rows = metrics.slice(0, 3).map((item) => ({
        domain: scene,
        metric: item.label,
        baseline: '依赖人工整理与分散判断',
        target: item.value,
        effect: item.note
    }));
    valueCards.slice(0, 2).forEach((item) => {
        rows.push({
            domain: entry,
            metric: item.title,
            baseline: '试点前缺少统一价值口径',
            target: item.value,
            effect: item.description
        });
    });
    return rows;
}

function solutionBindExpandablePanel(panelId, toggleId, toggleTextId) {
    const panel = document.getElementById(panelId);
    const toggle = document.getElementById(toggleId);
    const toggleText = document.getElementById(toggleTextId);
    if (!panel || !toggle || !toggleText) return;
    toggle.addEventListener('click', () => {
        const expanded = panel.classList.toggle('is-expanded');
        toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        toggleText.textContent = expanded ? '收起明细' : '展开查看';
    });
}

function solutionRenderValueDetail(items) {
    const panel = document.getElementById('solution-value-detail-panel');
    const root = document.getElementById('solution-value-detail');
    if (!panel || !root) return false;
    const rows = solutionNormalizeList(items);
    panel.hidden = !rows.length;
    panel.classList.remove('is-expanded');
    if (!rows.length) {
        root.innerHTML = '';
        return false;
    }
    root.innerHTML = `
        <table class="solution-value-table">
            <thead>
                <tr>
                    <th>板块</th>
                    <th>核心指标</th>
                    <th>目标值</th>
                    <th>预期效果</th>
                </tr>
            </thead>
            <tbody>
                ${rows.map((item) => `
                    <tr>
                        <td>${solutionEscapeHtml(item.domain || '-')}</td>
                        <td>${solutionEscapeHtml(item.metric || '-')}</td>
                        <td>${solutionEscapeHtml(item.target || item.baseline || '-')}</td>
                        <td>${solutionEscapeHtml(item.effect || '-')}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    return true;
}

function solutionRenderRoadmap(items) {
    const root = document.getElementById('solution-roadmap');
    if (!root) return false;
    const steps = solutionNormalizeList(items);
    root.innerHTML = `<div class="solution-roadmap-track">${steps.map((item, index) => `
        <article class="solution-roadmap-item solution-glass-card" data-step="${String(index + 1).padStart(2, '0')}">
            <div class="solution-roadmap-node">
                <div class="solution-roadmap-index">${String(index + 1).padStart(2, '0')}</div>
                <div class="solution-roadmap-dot"></div>
            </div>
            <div class="solution-roadmap-panel">
                <div class="solution-roadmap-meta">
                    <div class="solution-roadmap-phase">${solutionEscapeHtml(item.phase)}</div>
                    <div class="solution-roadmap-time">${solutionEscapeHtml(item.timeline)}</div>
                </div>
                <h3 class="solution-roadmap-title">${solutionEscapeHtml(item.goal)}</h3>
                <ul class="solution-roadmap-list">
                    ${solutionNormalizeList(item.tasks).map((task) => `<li>${solutionEscapeHtml(task)}</li>`).join('')}
                </ul>
            </div>
        </article>
    `).join('')}</div>`;
    return steps.length > 0;
}

function solutionRenderRiskCards(items) {
    const root = document.getElementById('solution-risk-cards');
    if (!root) return false;
    const cards = solutionNormalizeList(items);
    root.innerHTML = cards.map((item, index) => `
        <article class="solution-card solution-card-risk" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-card-badge">风险边界</div>
                <div class="solution-card-index">${String(index + 1).padStart(2, '0')}</div>
            </div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.description)}</p>
            <div class="solution-card-guardrail">
                <div class="solution-card-guardrail-label">防护动作</div>
                <div class="solution-card-meta">${solutionEscapeHtml(item.guardrail)}</div>
            </div>
        </article>
    `).join('');
    return cards.length > 0;
}

function solutionRenderActions(items) {
    const root = document.getElementById('solution-actions');
    if (!root) return false;
    const cards = solutionNormalizeList(items);
    root.innerHTML = cards.map((item, index) => `
        <article class="solution-action-item solution-glass-card" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-action-owner">${solutionEscapeHtml(item.owner)}</div>
                <div class="solution-card-index">${String(index + 1).padStart(2, '0')}</div>
            </div>
            <h3 class="solution-action-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-action-copy">${solutionEscapeHtml(item.detail)}</p>
            <div class="solution-action-foot">立即推进</div>
        </article>
    `).join('');
    return cards.length > 0;
}

function solutionBindScrollSpy() {
    const buttons = Array.from(document.querySelectorAll('.solution-nav-button'));
    const sections = Array.from(document.querySelectorAll('[data-solution-section]:not([hidden])'));
    if (!buttons.length || !sections.length || typeof IntersectionObserver === 'undefined') {
        return;
    }

    const buttonMap = new Map(buttons.map((button) => [button.getAttribute('data-target'), button]));
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            const id = entry.target.id;
            buttonMap.forEach((button, key) => {
                button.classList.toggle('is-active', key === id);
            });
        });
    }, {
        rootMargin: '-18% 0px -62% 0px',
        threshold: [0.12, 0.32, 0.58]
    });

    sections.forEach((section) => observer.observe(section));
    const firstButton = buttons[0];
    if (firstButton) firstButton.classList.add('is-active');
}

function solutionRegisterSectionReveal() {
    const sections = Array.from(document.querySelectorAll('.solution-reveal:not([hidden])'));
    sections.forEach((section) => section.classList.add('is-visible'));
    if (typeof IntersectionObserver === 'undefined') return;
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
    sections.forEach((section) => {
        section.classList.remove('is-visible');
        observer.observe(section);
    });
}

function solutionRender(payload) {
    document.title = `${payload.title || '查看方案'} | DeepVision`;
    const shell = document.getElementById('solution-shell');
    const state = document.getElementById('solution-state-card');
    if (!shell || !state) return;

    const subtitle = payload.subtitle || payload.overview || '';
    const decisionCards = solutionNormalizeList(payload.decision_cards).length ? payload.decision_cards : solutionBuildDecisionFallback(payload);
    const comparisonItems = solutionNormalizeList(payload.comparison_items).length ? payload.comparison_items : solutionBuildComparisonFallback(payload);
    const architectureNodes = solutionNormalizeList(payload.architecture_nodes).length ? payload.architecture_nodes : solutionBuildArchitectureFallback(payload);
    const dataflowSteps = solutionNormalizeList(payload.dataflow_steps).length ? payload.dataflow_steps : solutionBuildDataflowFallback(payload);
    const valueDetailItems = solutionNormalizeList(payload.value_table).length ? payload.value_table : solutionBuildValueDetailFallback(payload);

    const titleNode = document.getElementById('solution-title');
    if (titleNode) {
        const titleParts = solutionSplitHeroTitle(payload.title || '查看方案');
        titleNode.innerHTML = `
            <span class="solution-title-line solution-title-line-primary">${solutionEscapeHtml(titleParts.primary)}</span>
            ${titleParts.secondary ? `<span class="solution-title-line solution-title-line-secondary">${solutionEscapeHtml(titleParts.secondary)}</span>` : ''}
        `;
    }

    const subtitleNode = document.getElementById('solution-subtitle');
    if (subtitleNode) {
        subtitleNode.textContent = solutionShortText(subtitle, 58);
        subtitleNode.hidden = !subtitle;
    }

    solutionRenderHeroPrimary(payload, decisionCards);
    solutionRenderHeroActions(payload.action_items, decisionCards);
    solutionRenderHeroMetrics(payload.metrics, payload.roadmap);

    const visibleIds = new Set();
    const hasDecision = solutionRenderDecisionSummary(payload, decisionCards) || solutionRenderOverviewMeta(payload.overview_meta) || solutionRenderDecisionCards(decisionCards);
    if (solutionSetSectionVisibility('decision', hasDecision)) visibleIds.add('decision');
    if (solutionSetSectionVisibility('comparison', solutionRenderComparison(comparisonItems))) visibleIds.add('comparison');
    if (solutionSetSectionVisibility('modules', solutionRenderDimensionCards(payload.dimension_cards))) visibleIds.add('modules');
    if (solutionSetSectionVisibility('architecture', solutionRenderArchitecture(architectureNodes))) visibleIds.add('architecture');
    if (solutionSetSectionVisibility('dataflow', solutionRenderDataflow(dataflowSteps))) visibleIds.add('dataflow');

    const hasValue = solutionRenderMetrics(payload.metrics) || solutionRenderValueCards(payload.value_cards) || solutionRenderValueDetail(valueDetailItems);
    if (solutionSetSectionVisibility('value', hasValue)) visibleIds.add('value');

    if (solutionSetSectionVisibility('roadmap', solutionRenderRoadmap(payload.roadmap))) visibleIds.add('roadmap');
    if (solutionSetSectionVisibility('risks', solutionRenderRiskCards(payload.risk_cards))) visibleIds.add('risks');
    if (solutionSetSectionVisibility('actions', solutionRenderActions(payload.action_items))) visibleIds.add('actions');

    solutionRenderNav(payload.nav_items, visibleIds);
    solutionBindExpandablePanel('solution-value-detail-panel', 'solution-value-detail-toggle', 'solution-value-detail-toggle-text');

    state.hidden = true;
    shell.hidden = false;
    solutionBindScrollSpy();
    solutionRegisterSectionReveal();
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

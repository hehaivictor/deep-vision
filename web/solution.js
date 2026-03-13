const SOLUTION_ASSET_VERSION = '20260314-solution-v19';
const SOLUTION_API_BASE = `${window.location.origin}/api`;
const SOLUTION_SOURCE_MODE_LABELS = {
    structured_sidecar: '结构化快照',
    legacy_markdown: '历史兼容',
    degraded: '降级视图'
};

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

function solutionNormalizeChapter(chapter) {
    if (!chapter || typeof chapter !== 'object') return null;
    return {
        id: String(chapter.id || '').trim(),
        navLabel: String(chapter.navLabel || chapter.nav_label || chapter.label || chapter.title || '章节').trim(),
        eyebrow: String(chapter.eyebrow || chapter.kicker || '').trim(),
        title: String(chapter.title || chapter.label || '').trim(),
        judgement: String(chapter.judgement || chapter.description || '').trim(),
        summary: String(chapter.summary || '').trim(),
        layout: String(chapter.layout || 'text').trim(),
        metrics: solutionNormalizeList(chapter.metrics),
        cards: solutionNormalizeList(chapter.cards),
        diagram: chapter.diagram && typeof chapter.diagram === 'object' ? chapter.diagram : null,
        cta: chapter.cta && typeof chapter.cta === 'object' ? chapter.cta : null,
        evidenceRefs: solutionNormalizeList(chapter.evidenceRefs || chapter.evidence_refs),
    };
}

function solutionGetProposalPage(payload) {
    const proposal = payload?.proposal_page;
    const chapters = solutionNormalizeList(proposal?.chapters).map(solutionNormalizeChapter).filter((chapter) => chapter?.id);
    if (!chapters.length) return null;
    return {
        theme: String(proposal?.theme || 'executive_dark_editorial'),
        navItems: solutionNormalizeList(proposal?.nav_items).filter((item) => item?.id),
        chapters
    };
}

function solutionGetHeroChapter(payload) {
    const proposal = solutionGetProposalPage(payload);
    if (!proposal) return null;
    return proposal.chapters.find((chapter) => chapter.id === 'hero') || proposal.chapters[0] || null;
}

function solutionGetBodyChapters(payload) {
    const proposal = solutionGetProposalPage(payload);
    if (!proposal) return [];
    return proposal.chapters.filter((chapter) => chapter.id !== 'hero');
}

function solutionGetHeroActionItems(payload) {
    const proposal = solutionGetProposalPage(payload);
    if (!proposal) return solutionNormalizeList(payload?.hero?.actions);
    const roadmap = proposal.chapters.find((chapter) => chapter.id === 'roadmap');
    const workstreams = proposal.chapters.find((chapter) => chapter.id === 'workstreams');
    const sourceCards = solutionNormalizeList(roadmap?.cards).length ? roadmap.cards : solutionNormalizeList(workstreams?.cards);
    return sourceCards.slice(0, 3).map((item, index) => ({
        owner: item?.tag || `阶段 ${index + 1}`,
        title: item?.title || '待补充',
        detail: item?.meta || item?.desc || ''
    }));
}

function solutionBuildNavItems(payload) {
    const proposal = solutionGetProposalPage(payload);
    if (proposal?.navItems?.length) return proposal.navItems;
    if (proposal?.chapters?.length) {
        return proposal.chapters.map((chapter) => ({
            id: chapter.id,
            label: chapter.navLabel || chapter.title || '章节'
        }));
    }
    const navItems = solutionNormalizeList(payload?.nav_items);
    if (navItems.length) return navItems;
    return solutionNormalizeList(payload?.sections).map((section) => ({
        id: section.id,
        label: section.label || section.title || '章节'
    }));
}

function solutionRenderNav(items) {
    const nav = document.getElementById('solution-nav');
    if (!nav) return;
    const navItems = solutionNormalizeList(items).filter((item) => item?.id);
    nav.innerHTML = navItems.map((item) => `
        <button type="button" class="solution-nav-button" data-target="${solutionEscapeHtml(item.id)}">
            ${solutionEscapeHtml(item.label || item.title || item.id)}
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

function solutionRenderQualityStrip(payload) {
    const root = document.getElementById('solution-quality-strip');
    if (!root) return;
    const quality = payload?.quality_signals || {};
    const fingerprint = payload?.fingerprint || {};
    const schemaMeta = payload?.solution_schema_meta || {};
    const proposal = solutionGetProposalPage(payload);
    const rows = [
        {
            label: '数据来源',
            value: SOLUTION_SOURCE_MODE_LABELS[payload?.source_mode] || payload?.source_mode || '未知',
            detail: payload?.source_mode === 'degraded' ? '已停止自动拼装完整方案，改为真实信息视图。' : '当前方案页所使用的事实源。'
        },
        {
            label: '渲染模式',
            value: proposal ? '提案编排' : (schemaMeta?.render_mode === 'schema' ? '配置驱动' : '兼容旧模板'),
            detail: proposal?.chapters?.length ? `当前提案共 ${proposal.chapters.length} 个章节。` : (schemaMeta?.section_count ? `当前目录共 ${schemaMeta.section_count} 个章节。` : '当前未提供可识别的方案目录配置。')
        },
        {
            label: '模板回退率',
            value: solutionPercent(quality?.fallback_ratio),
            detail: '事实槽位越充分，回退率越低。'
        },
        {
            label: '证据绑定率',
            value: solutionPercent(quality?.evidence_binding_ratio),
            detail: '结构化条目与真实证据的绑定比例。'
        },
        {
            label: '近期差异度',
            value: `${Math.max(0, Math.round((1 - Number(quality?.similarity_score || 0)) * 100))}%`,
            detail: quality?.similar_report_name ? `最近对比对象：${solutionShortText(quality.similar_report_name, 18)}` : '基于近期方案相似度计算。'
        }
    ];
    const reasons = solutionNormalizeList(quality?.degraded_reasons);
    const fingerprintMeta = [fingerprint.scene, fingerprint.pain_point, fingerprint.entry_point].filter(Boolean).slice(0, 3);

    root.hidden = false;
    root.classList.toggle('is-degraded', payload?.source_mode === 'degraded');
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
        ${fingerprintMeta.length ? `
            <div class="solution-quality-meta">
                ${fingerprintMeta.map((item) => `<span class="solution-quality-pill">${solutionEscapeHtml(solutionShortText(item, 24))}</span>`).join('')}
            </div>
        ` : ''}
        ${reasons.length ? `
            <div class="solution-quality-alert">
                ${reasons.map((reason) => `<div class="solution-quality-alert-item">${solutionEscapeHtml(reason)}</div>`).join('')}
            </div>
        ` : ''}
    `;
}

function solutionRenderHero(payload) {
    const hero = payload?.hero || {};
    const heroChapter = solutionGetHeroChapter(payload);
    const eyebrow = document.getElementById('solution-hero-eyebrow');
    const title = document.getElementById('solution-title');
    const subtitle = document.getElementById('solution-subtitle');
    const summary = document.getElementById('solution-hero-summary');
    const highlights = document.getElementById('solution-hero-highlights');
    const actions = document.getElementById('solution-hero-actions');
    const metrics = document.getElementById('solution-hero-metrics');

    if (eyebrow) {
        const metaBits = [
            heroChapter?.eyebrow || hero?.eyebrow || 'DeepVision 高级提案页',
            SOLUTION_SOURCE_MODE_LABELS[payload?.source_mode] || '',
            payload?.report_template || '',
            payload?.report_type || ''
        ].filter(Boolean);
        eyebrow.textContent = metaBits.join(' · ');
    }

    if (title) {
        title.textContent = heroChapter?.title || payload?.title || hero?.title || '查看方案';
    }

    if (subtitle) {
        const text = heroChapter?.summary || heroChapter?.judgement || payload?.subtitle || hero?.subtitle || payload?.overview || '';
        subtitle.textContent = text;
        subtitle.hidden = !text;
    }

    if (summary) {
        const summaryText = heroChapter?.judgement || hero?.summary || payload?.overview || '当前方案已按真实证据组织为可执行章节。';
        const evidenceButton = solutionNormalizeList(heroChapter?.evidenceRefs).length ? `
            <button type="button" class="solution-inline-evidence" data-evidence-title="${solutionEscapeHtml(heroChapter.title || '方案判断')}" data-evidence-refs="${solutionEscapeHtml(heroChapter.evidenceRefs.join('||'))}">
                查看证据
            </button>
        ` : '';
        summary.innerHTML = `
            <div class="solution-hero-summary-top">
                <div class="solution-hero-summary-kicker">章节判断</div>
                ${evidenceButton}
            </div>
            <div class="solution-hero-summary-text">${solutionEscapeHtml(summaryText)}</div>
        `;
    }

    const highlightItems = solutionNormalizeList(heroChapter?.cards).length
        ? heroChapter.cards.map((item) => ({
            label: item?.tag || '重点',
            value: item?.title || '未命名模块',
            detail: item?.desc || item?.meta || ''
        }))
        : (solutionNormalizeList(hero?.highlights).length ? solutionNormalizeList(hero.highlights) : solutionNormalizeList(payload?.headline_cards));
    if (highlights) {
        highlights.innerHTML = highlightItems.map((item) => `
            <article class="solution-hero-highlight-card">
                <div class="solution-hero-highlight-label">${solutionEscapeHtml(item?.label || '重点')}</div>
                <div class="solution-hero-highlight-value">${solutionEscapeHtml(solutionShortText(item?.value, 36))}</div>
                ${item?.detail ? `<div class="solution-hero-highlight-detail">${solutionEscapeHtml(solutionShortText(item.detail, 72))}</div>` : ''}
            </article>
        `).join('');
    }

    const actionItems = solutionGetHeroActionItems(payload);
    if (actions) {
        actions.innerHTML = actionItems.length ? actionItems.map((item, index) => `
            <article class="solution-panel-list-item" data-accent="${index % 4}">
                <div class="solution-panel-list-index">${String(index + 1).padStart(2, '0')}</div>
                <div class="solution-panel-list-body">
                    <div class="solution-panel-list-title">${solutionEscapeHtml(item?.title || '待补充')}</div>
                    <div class="solution-panel-list-meta">${solutionEscapeHtml([item?.owner, item?.detail].filter(Boolean).join(' · ') || '等待进一步事实补充')}</div>
                </div>
            </article>
        `).join('') : '<div class="solution-empty">当前暂无首轮行动。</div>';
    }

    const metricItems = solutionNormalizeList(heroChapter?.metrics).length ? solutionNormalizeList(heroChapter.metrics) : (solutionNormalizeList(hero?.metrics).length ? solutionNormalizeList(hero.metrics) : solutionNormalizeList(payload?.metrics));
    if (metrics) {
        metrics.innerHTML = metricItems.length ? metricItems.map((item) => `
            <article class="solution-metric-card-lite">
                <div class="solution-metric-card-lite-label">${solutionEscapeHtml(item?.label || '指标')}</div>
                <div class="solution-metric-card-lite-value">${solutionEscapeHtml(item?.value || '-')}</div>
                ${item?.delta ? `<div class="solution-metric-card-lite-delta">${solutionEscapeHtml(solutionShortText(item.delta, 32))}</div>` : ''}
                ${item?.note ? `<div class="solution-metric-card-lite-note">${solutionEscapeHtml(solutionShortText(item.note, 56))}</div>` : ''}
            </article>
        `).join('') : '<div class="solution-empty">当前暂无质量指标。</div>';
    }
}

function solutionRenderCards(section) {
    const columns = Math.max(1, Math.min(Number(section?.columns || 2), 3));
    const items = solutionNormalizeList(section?.items);
    return items.length ? `
        <div class="solution-generic-grid" style="--solution-grid-columns:${columns};">
            ${items.map((item) => `
                <article class="solution-generic-card">
                    ${item?.eyebrow ? `<div class="solution-card-badge">${solutionEscapeHtml(item.eyebrow)}</div>` : ''}
                    <h3 class="solution-card-title">${solutionEscapeHtml(item?.title || '未命名模块')}</h3>
                    ${item?.summary ? `<p class="solution-card-summary">${solutionEscapeHtml(item.summary)}</p>` : ''}
                    ${item?.detail ? `<p class="solution-card-detail">${solutionEscapeHtml(item.detail)}</p>` : ''}
                </article>
            `).join('')}
        </div>
    ` : '<div class="solution-empty">当前章节暂无结构化卡片。</div>';
}

function solutionRenderSteps(section) {
    const items = solutionNormalizeList(section?.items);
    return items.length ? `
        <div class="solution-step-list">
            ${items.map((item, index) => `
                <article class="solution-step-item">
                    <div class="solution-step-index">${solutionEscapeHtml(item?.step || String(index + 1).padStart(2, '0'))}</div>
                    <div class="solution-step-body">
                        <div class="solution-step-title-row">
                            <h3 class="solution-step-title">${solutionEscapeHtml(item?.title || '未命名步骤')}</h3>
                            ${item?.timeline ? `<span class="solution-step-timeline">${solutionEscapeHtml(item.timeline)}</span>` : ''}
                        </div>
                        ${item?.summary ? `<p class="solution-step-summary">${solutionEscapeHtml(item.summary)}</p>` : ''}
                        ${item?.detail ? `<p class="solution-step-detail">${solutionEscapeHtml(item.detail)}</p>` : ''}
                    </div>
                </article>
            `).join('')}
        </div>
    ` : '<div class="solution-empty">当前章节暂无步骤内容。</div>';
}

function solutionRenderTimeline(section) {
    const items = solutionNormalizeList(section?.items);
    return items.length ? `
        <div class="solution-step-list solution-step-list-timeline">
            ${items.map((item, index) => `
                <article class="solution-step-item solution-step-item-timeline">
                    <div class="solution-step-index">${solutionEscapeHtml(item?.step || String(index + 1).padStart(2, '0'))}</div>
                    <div class="solution-step-body">
                        <div class="solution-step-title-row">
                            <h3 class="solution-step-title">${solutionEscapeHtml(item?.title || '未命名阶段')}</h3>
                            ${item?.timeline ? `<span class="solution-step-timeline">${solutionEscapeHtml(item.timeline)}</span>` : ''}
                        </div>
                        ${item?.summary ? `<p class="solution-step-summary">${solutionEscapeHtml(item.summary)}</p>` : ''}
                        ${item?.detail ? `<p class="solution-step-detail">${solutionEscapeHtml(item.detail)}</p>` : ''}
                    </div>
                </article>
            `).join('')}
        </div>
    ` : '<div class="solution-empty">当前章节暂无时间线内容。</div>';
}

function solutionRenderChecklist(section) {
    const items = solutionNormalizeList(section?.items);
    return items.length ? `
        <div class="solution-checklist">
            ${items.map((item) => `
                <article class="solution-checklist-item">
                    <div class="solution-checklist-dot"></div>
                    <div class="solution-checklist-body">
                        <div class="solution-checklist-title-row">
                            <h3 class="solution-checklist-title">${solutionEscapeHtml(item?.title || '未命名动作')}</h3>
                            ${item?.owner ? `<span class="solution-checklist-owner">${solutionEscapeHtml(item.owner)}</span>` : ''}
                        </div>
                        ${item?.detail ? `<p class="solution-checklist-detail">${solutionEscapeHtml(item.detail)}</p>` : ''}
                    </div>
                </article>
            `).join('')}
        </div>
    ` : '<div class="solution-empty">当前章节暂无执行清单。</div>';
}

function solutionRenderTable(section) {
    const columns = solutionNormalizeList(section?.columns);
    const rows = solutionNormalizeList(section?.rows);
    if (!columns.length || !rows.length) {
        return '<div class="solution-empty">当前章节暂无表格内容。</div>';
    }
    return `
        <div class="solution-table-wrap">
            <table class="solution-table">
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

function solutionRenderText(section) {
    const paragraphs = solutionNormalizeList(section?.paragraphs);
    return paragraphs.length ? `
        <div class="solution-richtext">
            ${paragraphs.map((paragraph) => `<p>${solutionEscapeHtml(paragraph)}</p>`).join('')}
        </div>
    ` : '<div class="solution-empty">当前章节暂无正文内容。</div>';
}

function solutionRenderSectionBody(section) {
    const layout = String(section?.layout || 'text').trim();
    if (layout === 'cards') return solutionRenderCards(section);
    if (layout === 'steps') return solutionRenderSteps(section);
    if (layout === 'timeline') return solutionRenderTimeline(section);
    if (layout === 'checklist') return solutionRenderChecklist(section);
    if (layout === 'table') return solutionRenderTable(section);
    return solutionRenderText(section);
}

function solutionRenderProposalEvidenceButton(chapter) {
    const refs = solutionNormalizeList(chapter?.evidenceRefs);
    if (!refs.length) return '';
    return `
        <button
            type="button"
            class="solution-inline-evidence"
            data-evidence-title="${solutionEscapeHtml(chapter.title || chapter.navLabel || '当前章节')}"
            data-evidence-refs="${solutionEscapeHtml(refs.join('||'))}"
        >
            查看证据
        </button>
    `;
}

function solutionRenderProposalDiagram(diagram) {
    if (!diagram || typeof diagram !== 'object') return '';
    const nodes = solutionNormalizeList(diagram.nodes);
    const edges = solutionNormalizeList(diagram.edges);
    const nodeLabelMap = new Map(nodes.map((node) => [String(node?.id || ''), String(node?.label || node?.id || '')]));
    return `
        <div class="solution-proposal-diagram" data-diagram-type="${solutionEscapeHtml(diagram.type || 'architecture')}">
            <div class="solution-proposal-diagram-grid">
                ${nodes.map((node, index) => `
                    <article class="solution-proposal-node" data-accent="${index % 4}">
                        ${node?.group ? `<div class="solution-card-badge">${solutionEscapeHtml(node.group)}</div>` : ''}
                        <h3 class="solution-card-title">${solutionEscapeHtml(node?.label || '节点')}</h3>
                    </article>
                `).join('')}
            </div>
            ${edges.length ? `
                <div class="solution-proposal-edge-list">
                    ${edges.map((edge) => `
                        <div class="solution-proposal-edge-item">
                            <span>${solutionEscapeHtml(nodeLabelMap.get(String(edge?.from || '')) || edge?.from || '')}</span>
                            <span class="solution-proposal-edge-arrow">→</span>
                            <span>${solutionEscapeHtml(nodeLabelMap.get(String(edge?.to || '')) || edge?.to || '')}</span>
                            ${edge?.label ? `<span class="solution-proposal-edge-label">${solutionEscapeHtml(edge.label)}</span>` : ''}
                        </div>
                    `).join('')}
                </div>
            ` : ''}
            ${diagram?.caption ? `<div class="solution-proposal-diagram-caption">${solutionEscapeHtml(diagram.caption)}</div>` : ''}
        </div>
    `;
}

function solutionRenderProposalCardsGrid(cards, columns = 2) {
    const items = solutionNormalizeList(cards);
    return items.length ? `
        <div class="solution-generic-grid" style="--solution-grid-columns:${Math.max(1, columns)};">
            ${items.map((item, index) => `
                <article class="solution-generic-card solution-proposal-card" data-accent="${index % 4}">
                    ${item?.tag ? `<div class="solution-card-badge">${solutionEscapeHtml(item.tag)}</div>` : ''}
                    <h3 class="solution-card-title">${solutionEscapeHtml(item?.title || '未命名卡片')}</h3>
                    ${item?.desc ? `<p class="solution-card-summary">${solutionEscapeHtml(item.desc)}</p>` : ''}
                    ${item?.meta ? `<p class="solution-card-detail">${solutionEscapeHtml(item.meta)}</p>` : ''}
                </article>
            `).join('')}
        </div>
    ` : '<div class="solution-empty">当前章节暂无结构化卡片。</div>';
}

function solutionRenderProposalComparison(chapter) {
    const cards = solutionNormalizeList(chapter?.cards);
    if (!cards.length) return '<div class="solution-empty">当前章节暂无可比较路径。</div>';
    return `
        <div class="solution-compare-list">
            ${cards.map((card, index) => `
                <article class="solution-compare-card" data-accent="${index % 4}">
                    <div class="solution-compare-head">
                        <div class="solution-compare-kicker">${solutionEscapeHtml(card?.tag || '路径')}</div>
                        ${card?.meta ? `<div class="solution-card-foot">${solutionEscapeHtml(solutionShortText(card.meta, 60))}</div>` : ''}
                    </div>
                    <h3 class="solution-compare-label">${solutionEscapeHtml(card?.title || '未命名路径')}</h3>
                    <div class="solution-compare-body">
                        <div class="solution-compare-column solution-compare-column-active">
                            <div class="solution-compare-kicker">路径定位</div>
                            <p>${solutionEscapeHtml(card?.desc || '待补充')}</p>
                        </div>
                        <div class="solution-compare-column solution-compare-column-muted">
                            <div class="solution-compare-kicker">适用边界</div>
                            <p>${solutionEscapeHtml(card?.meta || '当前暂无边界说明')}</p>
                        </div>
                    </div>
                </article>
            `).join('')}
        </div>
    `;
}

function solutionRenderProposalTabbedCards(chapter) {
    const cards = solutionNormalizeList(chapter?.cards);
    if (!cards.length) return '<div class="solution-empty">当前章节暂无工作流内容。</div>';
    return `
        <div class="solution-proposal-tabs" data-proposal-tabs="${solutionEscapeHtml(chapter.id)}">
            <div class="solution-proposal-tab-list" role="tablist" aria-label="${solutionEscapeHtml(chapter.title || '工作流')}">
                ${cards.map((card, index) => `
                    <button
                        type="button"
                        class="solution-proposal-tab${index === 0 ? ' is-active' : ''}"
                        data-tab-target="${solutionEscapeHtml(chapter.id)}-${index}"
                        role="tab"
                        aria-selected="${index === 0 ? 'true' : 'false'}"
                    >
                        ${solutionEscapeHtml(card?.title || `模块 ${index + 1}`)}
                    </button>
                `).join('')}
            </div>
            <div class="solution-proposal-tab-panels">
                ${cards.map((card, index) => `
                    <article
                        class="solution-proposal-tab-panel${index === 0 ? ' is-active' : ''}"
                        id="${solutionEscapeHtml(chapter.id)}-${index}"
                        role="tabpanel"
                        ${index === 0 ? '' : 'hidden'}
                    >
                        ${card?.tag ? `<div class="solution-card-badge">${solutionEscapeHtml(card.tag)}</div>` : ''}
                        <h3 class="solution-card-title">${solutionEscapeHtml(card?.title || '未命名工作流')}</h3>
                        ${card?.desc ? `<p class="solution-card-summary">${solutionEscapeHtml(card.desc)}</p>` : ''}
                        ${card?.meta ? `<p class="solution-card-detail">${solutionEscapeHtml(card.meta)}</p>` : ''}
                    </article>
                `).join('')}
            </div>
        </div>
    `;
}

function solutionRenderProposalValueGrid(chapter) {
    const metrics = solutionNormalizeList(chapter?.metrics);
    const cards = solutionNormalizeList(chapter?.cards);
    return `
        ${metrics.length ? `
            <div class="solution-metric-grid solution-proposal-value-grid">
                ${metrics.map((item) => `
                    <article class="solution-metric-card-lite solution-proposal-value-card">
                        <div class="solution-metric-card-lite-label">${solutionEscapeHtml(item?.label || '指标')}</div>
                        <div class="solution-metric-card-lite-value">${solutionEscapeHtml(item?.value || '-')}</div>
                        ${item?.delta ? `<div class="solution-metric-card-lite-delta">${solutionEscapeHtml(solutionShortText(item.delta, 32))}</div>` : ''}
                        ${item?.note ? `<div class="solution-metric-card-lite-note">${solutionEscapeHtml(solutionShortText(item.note, 56))}</div>` : ''}
                    </article>
                `).join('')}
            </div>
        ` : ''}
        ${solutionRenderProposalCardsGrid(cards, 2)}
    `;
}

function solutionRenderProposalTimeline(chapter) {
    const items = solutionNormalizeList(chapter?.cards).map((card, index) => ({
        step: String(index + 1).padStart(2, '0'),
        title: card?.title || `阶段 ${index + 1}`,
        summary: card?.desc || '',
        detail: card?.meta || '',
        timeline: card?.tag || ''
    }));
    return solutionRenderTimeline({ items });
}

function solutionRenderProposalChapterBody(chapter) {
    const layout = String(chapter?.layout || 'text').trim();
    if (layout === 'conflict_cards') return solutionRenderProposalCardsGrid(chapter?.cards, 4);
    if (layout === 'dual_comparison') return solutionRenderProposalComparison(chapter);
    if (layout === 'blueprint_diagram') {
        return `
            ${solutionRenderProposalDiagram(chapter?.diagram)}
            ${solutionRenderProposalCardsGrid(chapter?.cards, 4)}
        `;
    }
    if (layout === 'tabbed_cards') return solutionRenderProposalTabbedCards(chapter);
    if (layout === 'loop_diagram') {
        return `
            ${solutionRenderProposalDiagram(chapter?.diagram)}
            ${solutionRenderProposalCardsGrid(chapter?.cards, 4)}
        `;
    }
    if (layout === 'phased_timeline') return solutionRenderProposalTimeline(chapter);
    if (layout === 'value_grid') return solutionRenderProposalValueGrid(chapter);
    if (layout === 'hero_metrics') return solutionRenderProposalValueGrid(chapter);
    return solutionRenderProposalCardsGrid(chapter?.cards, 2);
}

function solutionRenderLegacySections(payload) {
    const root = document.getElementById('solution-sections');
    if (!root) return [];
    const sections = solutionNormalizeList(payload?.sections).filter((section) => section?.id);
    root.innerHTML = sections.length ? sections.map((section, index) => `
        <section class="solution-section solution-reveal" id="${solutionEscapeHtml(section.id)}" data-solution-section data-layout="${solutionEscapeHtml(section.layout || 'text')}">
            <div class="solution-section-head">
                <span class="solution-section-kicker">${solutionEscapeHtml(section.kicker || `章节 ${index + 1}`)}</span>
                <h2>${solutionEscapeHtml(section.title || section.label || '未命名章节')}</h2>
                ${section.description ? `<p>${solutionEscapeHtml(section.description)}</p>` : ''}
            </div>
            <div class="solution-section-body">${solutionRenderSectionBody(section)}</div>
        </section>
    `).join('') : `
        <section class="solution-section solution-reveal" id="solution-empty-section" data-solution-section>
            <div class="solution-section-head">
                <span class="solution-section-kicker">摘要</span>
                <h2>暂无可展示章节</h2>
                <p>当前报告尚未沉淀足够的结构化信息。</p>
            </div>
        </section>
    `;
    return sections;
}

function solutionRenderProposalSections(payload) {
    const root = document.getElementById('solution-sections');
    if (!root) return [];
    const chapters = solutionGetBodyChapters(payload);
    root.innerHTML = chapters.length ? chapters.map((chapter, index) => `
        <section class="solution-section solution-reveal solution-section-proposal" id="${solutionEscapeHtml(chapter.id)}" data-solution-section data-layout="${solutionEscapeHtml(chapter.layout || 'text')}">
            <div class="solution-section-head solution-section-head-proposal">
                <div class="solution-section-head-top">
                    <span class="solution-section-kicker">${solutionEscapeHtml(chapter.eyebrow || `章节 ${index + 2}`)}</span>
                    ${solutionRenderProposalEvidenceButton(chapter)}
                </div>
                <h2>${solutionEscapeHtml(chapter.title || chapter.navLabel || '未命名章节')}</h2>
                ${chapter.judgement ? `<p class="solution-section-judgement">${solutionEscapeHtml(chapter.judgement)}</p>` : ''}
                ${chapter.summary ? `<p class="solution-section-summary">${solutionEscapeHtml(chapter.summary)}</p>` : ''}
            </div>
            <div class="solution-section-body">${solutionRenderProposalChapterBody(chapter)}</div>
            ${chapter.cta?.target ? `
                <div class="solution-section-cta-row">
                    <button type="button" class="solution-section-cta" data-target="${solutionEscapeHtml(chapter.cta.target)}">
                        ${solutionEscapeHtml(chapter.cta.label || '继续查看')}
                    </button>
                </div>
            ` : ''}
        </section>
    `).join('') : '';
    return chapters;
}

function solutionRenderSections(payload) {
    const proposal = solutionGetProposalPage(payload);
    if (proposal) {
        return solutionRenderProposalSections(payload);
    }
    return solutionRenderLegacySections(payload);
}

function solutionBindProposalTabs() {
    document.querySelectorAll('[data-proposal-tabs]').forEach((root) => {
        const buttons = Array.from(root.querySelectorAll('.solution-proposal-tab[data-tab-target]'));
        const panels = Array.from(root.querySelectorAll('.solution-proposal-tab-panel'));
        if (!buttons.length || !panels.length) return;
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

function solutionOpenEvidenceDrawer(title, refs) {
    const drawer = document.getElementById('solution-evidence-drawer');
    const drawerTitle = document.getElementById('solution-evidence-title');
    const drawerBody = document.getElementById('solution-evidence-body');
    if (!drawer || !drawerTitle || !drawerBody) return;
    const list = solutionNormalizeList(refs);
    drawerTitle.textContent = title || '当前章节证据';
    drawerBody.innerHTML = list.length ? `
        <div class="solution-evidence-chip-list">
            ${list.map((ref) => `<span class="solution-evidence-chip">${solutionEscapeHtml(ref)}</span>`).join('')}
        </div>
        <div class="solution-evidence-note">后续可在这里展开访谈摘录、章节编号与结构化证据明细。</div>
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
            const refsRaw = button.getAttribute('data-evidence-refs') || '';
            const refs = refsRaw ? refsRaw.split('||').filter(Boolean) : [];
            solutionOpenEvidenceDrawer(title, refs);
        });
    });
    document.querySelectorAll('[data-evidence-close]').forEach((button) => {
        button.addEventListener('click', solutionCloseEvidenceDrawer);
    });
}

function solutionBindSectionCtas() {
    document.querySelectorAll('[data-target].solution-section-cta').forEach((button) => {
        button.addEventListener('click', () => {
            const targetId = button.getAttribute('data-target') || '';
            const target = document.getElementById(targetId);
            if (!target) return;
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });
}

function solutionBindScrollSpy() {
    const buttons = Array.from(document.querySelectorAll('.solution-nav-button[data-target]'));
    const sections = Array.from(document.querySelectorAll('[data-solution-section]'));
    if (!buttons.length || !sections.length || typeof IntersectionObserver === 'undefined') return;

    const buttonMap = new Map(buttons.map((button) => [button.getAttribute('data-target'), button]));
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            const id = entry.target.id;
            if (!buttonMap.has(id)) return;
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
    document.title = `${payload?.title || '查看方案'} | DeepVision`;
    const shell = document.getElementById('solution-shell');
    const state = document.getElementById('solution-state-card');
    if (!shell || !state) return;

    solutionRenderQualityStrip(payload);
    solutionRenderHero(payload);
    const sections = solutionRenderSections(payload);
    solutionRenderNav(solutionBuildNavItems({ ...payload, sections }));

    state.hidden = true;
    shell.hidden = false;
    solutionBindProposalTabs();
    solutionBindEvidenceDrawer();
    solutionBindSectionCtas();
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

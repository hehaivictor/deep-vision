const SOLUTION_ASSET_VERSION = '20260313-solution-v18';
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

function solutionBuildNavItems(payload) {
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
    const rows = [
        {
            label: '数据来源',
            value: SOLUTION_SOURCE_MODE_LABELS[payload?.source_mode] || payload?.source_mode || '未知',
            detail: payload?.source_mode === 'degraded' ? '已停止自动拼装完整方案，改为真实信息视图。' : '当前方案页所使用的事实源。'
        },
        {
            label: '渲染模式',
            value: schemaMeta?.render_mode === 'schema' ? '配置驱动' : '兼容旧模板',
            detail: schemaMeta?.section_count ? `当前目录共 ${schemaMeta.section_count} 个章节。` : '当前未提供可识别的方案目录配置。'
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
    const eyebrow = document.getElementById('solution-hero-eyebrow');
    const title = document.getElementById('solution-title');
    const subtitle = document.getElementById('solution-subtitle');
    const summary = document.getElementById('solution-hero-summary');
    const highlights = document.getElementById('solution-hero-highlights');
    const actions = document.getElementById('solution-hero-actions');
    const metrics = document.getElementById('solution-hero-metrics');

    if (eyebrow) {
        const metaBits = [
            hero?.eyebrow || 'DeepVision 差异化方案',
            SOLUTION_SOURCE_MODE_LABELS[payload?.source_mode] || '',
            payload?.report_template || '',
            payload?.report_type || ''
        ].filter(Boolean);
        eyebrow.textContent = metaBits.join(' · ');
    }
    if (title) title.textContent = payload?.title || hero?.title || '查看方案';
    if (subtitle) {
        const text = payload?.subtitle || hero?.subtitle || payload?.overview || '';
        subtitle.textContent = text;
        subtitle.hidden = !text;
    }

    if (summary) {
        const summaryText = hero?.summary || payload?.overview || '当前方案已按真实证据组织为可执行章节。';
        summary.innerHTML = `
            <div class="solution-hero-summary-kicker">方案摘要</div>
            <div class="solution-hero-summary-text">${solutionEscapeHtml(summaryText)}</div>
        `;
    }

    const highlightItems = solutionNormalizeList(hero?.highlights).length ? solutionNormalizeList(hero.highlights) : solutionNormalizeList(payload?.headline_cards);
    if (highlights) {
        highlights.innerHTML = highlightItems.map((item) => `
            <article class="solution-hero-highlight-card">
                <div class="solution-hero-highlight-label">${solutionEscapeHtml(item?.label || '重点')}</div>
                <div class="solution-hero-highlight-value">${solutionEscapeHtml(solutionShortText(item?.value, 36))}</div>
                ${item?.detail ? `<div class="solution-hero-highlight-detail">${solutionEscapeHtml(solutionShortText(item.detail, 72))}</div>` : ''}
            </article>
        `).join('');
    }

    const actionItems = solutionNormalizeList(hero?.actions);
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

    const metricItems = solutionNormalizeList(hero?.metrics).length ? solutionNormalizeList(hero.metrics) : solutionNormalizeList(payload?.metrics);
    if (metrics) {
        metrics.innerHTML = metricItems.length ? metricItems.map((item) => `
            <article class="solution-metric-card-lite">
                <div class="solution-metric-card-lite-label">${solutionEscapeHtml(item?.label || '指标')}</div>
                <div class="solution-metric-card-lite-value">${solutionEscapeHtml(item?.value || '-')}</div>
                ${item?.note ? `<div class="solution-metric-card-lite-note">${solutionEscapeHtml(solutionShortText(item.note, 56))}</div>` : ''}
            </article>
        `).join('') : '<div class="solution-empty">当前暂无质量指标。</div>';
    }
}

function solutionCellText(value) {
    if (Array.isArray(value)) return value.map((item) => solutionCellText(item)).filter(Boolean).join('、');
    if (value === null || value === undefined) return '';
    return String(value).trim();
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

function solutionRenderSections(payload) {
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

function solutionBindScrollSpy() {
    const buttons = Array.from(document.querySelectorAll('.solution-nav-button[data-target]'));
    const sections = Array.from(document.querySelectorAll('[data-solution-section]'));
    if (!buttons.length || !sections.length || typeof IntersectionObserver === 'undefined') return;

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

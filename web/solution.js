const SOLUTION_ASSET_VERSION = '20260310-solution-v6';
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

function solutionResolveSameOriginReferrer() {
    const referrer = String(document.referrer || '').trim();
    if (!referrer) return '';
    try {
        const url = new URL(referrer, window.location.origin);
        if (url.origin !== window.location.origin) return '';
        return url.toString();
    } catch (error) {
        return '';
    }
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
        const error = new Error(payload?.error || payload?.detail || `HTTP ${response.status}`);
        error.status = response.status;
        throw error;
    }
    return payload || {};
}

function solutionRenderNav(items) {
    const nav = document.getElementById('solution-nav');
    if (!nav) return;
    const navItems = solutionNormalizeList(items);
    nav.innerHTML = navItems.map((item) => `
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

function solutionRenderHeroSignals(items) {
    const root = document.getElementById('solution-hero-signals');
    if (!root) return;
    const signals = solutionNormalizeList(items).slice(0, 4);
    root.hidden = !signals.length;
    root.innerHTML = signals.map((item, index) => `
        <article class="solution-hero-signal" data-accent="${index % 4}">
            <div class="solution-hero-signal-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-hero-signal-value">${solutionEscapeHtml(solutionShortText(item.value, 24))}</div>
        </article>
    `).join('');
}

function solutionRenderHeroFocus(items, overviewText) {
    const root = document.getElementById('solution-hero-focus');
    if (!root) return;
    const primary = solutionNormalizeList(items)[0] || null;
    const label = primary?.label || '首轮主线';
    const title = primary?.value || '围绕核心问题启动首轮落地';
    const detail = primary?.detail || overviewText || '根据当前访谈报告提炼首轮试点路径。';
    root.innerHTML = `
        <article class="solution-hero-focus-card">
            <div class="solution-hero-focus-topline">
                <div class="solution-hero-focus-kicker">${solutionEscapeHtml(label)}</div>
                <div class="solution-hero-focus-badge">01</div>
            </div>
            <h2 class="solution-hero-focus-title">${solutionEscapeHtml(title)}</h2>
            <p class="solution-hero-focus-copy">${solutionEscapeHtml(solutionShortText(detail, 72))}</p>
            <div class="solution-hero-focus-foot">
                <span>访谈提炼</span>
                <span>可直接启动</span>
            </div>
        </article>
    `;
}

function solutionRenderHeroMetrics(items) {
    const root = document.getElementById('solution-hero-metric-row');
    if (!root) return;
    const metrics = solutionNormalizeList(items).slice(0, 2);
    root.hidden = !metrics.length;
    root.innerHTML = metrics.map((item) => `
        <article class="solution-hero-metric">
            <div class="solution-hero-metric-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-hero-metric-value">${solutionEscapeHtml(item.value)}</div>
            <div class="solution-hero-metric-note">${solutionEscapeHtml(solutionShortText(item.note, 28))}</div>
        </article>
    `).join('');
}

function solutionRenderMetrics(items) {
    const root = document.getElementById('solution-metrics');
    if (!root) return;
    root.innerHTML = solutionNormalizeList(items).map((item) => `
        <article class="solution-metric-card">
            <div class="solution-metric-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-metric-value">${solutionEscapeHtml(item.value)}</div>
            <div class="solution-metric-note">${solutionEscapeHtml(item.note)}</div>
        </article>
    `).join('');
}

function solutionRenderOverviewMeta(items) {
    const root = document.getElementById('solution-overview-meta');
    if (!root) return;
    root.innerHTML = solutionNormalizeList(items).map((item) => `
        <article class="solution-overview-meta-item">
            <div class="solution-overview-meta-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-overview-meta-value">${solutionEscapeHtml(item.value)}</div>
        </article>
    `).join('');
}

function solutionFormatCardIndex(index) {
    return String(Number(index || 0) + 1).padStart(2, '0');
}

function solutionRenderHeadlineCards(items) {
    const root = document.getElementById('solution-headline-cards');
    if (!root) return;
    const cards = solutionNormalizeList(items);
    const secondaryCards = cards.length > 1 ? cards.slice(1, 4) : cards.slice(0, 3);
    root.hidden = !secondaryCards.length;
    root.innerHTML = secondaryCards.map((item, index) => `
        <article class="solution-summary-card" data-accent="${(index + 1) % 4}">
            <div class="solution-summary-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-summary-value">${solutionEscapeHtml(item.value)}</div>
            <div class="solution-summary-detail">${solutionEscapeHtml(solutionShortText(item.detail, 44))}</div>
        </article>
    `).join('');
}

function solutionRenderFocusCards(items) {
    const root = document.getElementById('solution-focus-cards');
    if (!root) return;
    root.innerHTML = solutionNormalizeList(items).map((item, index) => `
        <article class="solution-card solution-card-insight" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-card-badge">重点洞察</div>
                <div class="solution-card-index">${solutionFormatCardIndex(index)}</div>
            </div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.summary)}</p>
            <p class="solution-card-meta">${solutionEscapeHtml(item.detail)}</p>
        </article>
    `).join('');
}

function solutionRenderDimensionCards(items) {
    const root = document.getElementById('solution-dimension-cards');
    if (!root) return;
    root.innerHTML = solutionNormalizeList(items).map((item, index) => {
        const points = solutionNormalizeList(item.points);
        return `
        <article class="solution-card solution-card-module" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-card-badge">${solutionEscapeHtml(item.badge || '业务板块')}</div>
                <div class="solution-card-index">${solutionFormatCardIndex(index)}</div>
            </div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.name)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.summary)}</p>
            <ul class="solution-card-list solution-card-list-module">
                ${points.map((point) => `<li>${solutionEscapeHtml(point)}</li>`).join('')}
            </ul>
            <div class="solution-card-foot">
                <span>模块要点</span>
                <span>${points.length || 0} 项</span>
            </div>
        </article>`;
    }).join('');
}

function solutionRenderRoadmap(items) {
    const root = document.getElementById('solution-roadmap');
    if (!root) return;
    const steps = solutionNormalizeList(items).map((item, index) => `
        <article class="solution-roadmap-item" data-step="${solutionFormatCardIndex(index)}">
            <div class="solution-roadmap-node">
                <div class="solution-roadmap-index">${solutionFormatCardIndex(index)}</div>
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
    `).join('');
    root.innerHTML = `<div class="solution-roadmap-track">${steps}</div>`;
}

function solutionRenderValueCards(items) {
    const root = document.getElementById('solution-value-cards');
    if (!root) return;
    root.innerHTML = solutionNormalizeList(items).map((item, index) => `
        <article class="solution-card solution-card-value" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-card-badge">预期收益</div>
                <div class="solution-card-index">${solutionFormatCardIndex(index)}</div>
            </div>
            <h3 class="solution-card-title solution-card-value-hero">${solutionEscapeHtml(item.value)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.title)}</p>
            <p class="solution-card-meta">${solutionEscapeHtml(item.description)}</p>
        </article>
    `).join('');
}

function solutionRenderRiskCards(items) {
    const root = document.getElementById('solution-risk-cards');
    if (!root) return;
    root.innerHTML = solutionNormalizeList(items).map((item, index) => `
        <article class="solution-card solution-card-risk" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-card-badge">风险依赖</div>
                <div class="solution-card-index">${solutionFormatCardIndex(index)}</div>
            </div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.description)}</p>
            <div class="solution-card-guardrail">
                <div class="solution-card-guardrail-label">防护动作</div>
                <div class="solution-card-meta">${solutionEscapeHtml(item.guardrail)}</div>
            </div>
        </article>
    `).join('');
}

function solutionRenderActions(items) {
    const root = document.getElementById('solution-actions');
    if (!root) return;
    root.innerHTML = solutionNormalizeList(items).map((item, index) => `
        <article class="solution-action-item" data-accent="${index % 4}">
            <div class="solution-card-topline">
                <div class="solution-action-owner">${solutionEscapeHtml(item.owner)}</div>
                <div class="solution-card-index">${solutionFormatCardIndex(index)}</div>
            </div>
            <h3 class="solution-action-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-action-copy">${solutionEscapeHtml(item.detail)}</p>
            <div class="solution-action-foot">立即推进</div>
        </article>
    `).join('');
}

function solutionBindScrollSpy() {
    const buttons = Array.from(document.querySelectorAll('.solution-nav-button'));
    const sections = Array.from(document.querySelectorAll('[data-solution-section]'));
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
        rootMargin: '-20% 0px -60% 0px',
        threshold: [0.15, 0.35, 0.6]
    });

    sections.forEach((section) => observer.observe(section));
    const firstButton = buttons[0];
    if (firstButton) {
        firstButton.classList.add('is-active');
    }
}

function solutionBindHeaderActions(reportName) {
    const backButton = document.getElementById('solution-back-btn');
    const openReportButton = document.getElementById('solution-open-report-btn');
    const referrerUrl = solutionResolveSameOriginReferrer();

    if (backButton) {
        backButton.addEventListener('click', () => {
            if (referrerUrl) {
                window.location.href = referrerUrl;
                return;
            }
            if (window.history.length > 1) {
                window.history.back();
                return;
            }
            window.location.href = solutionBuildReportUrl(reportName);
        });
    }

    if (openReportButton) {
        openReportButton.addEventListener('click', () => {
            window.location.href = solutionBuildReportUrl(reportName);
        });
    }
}

function solutionRender(payload) {
    document.title = `${payload.title || '查看方案'} | DeepVision`;
    const shell = document.getElementById('solution-shell');
    const state = document.getElementById('solution-state-card');
    if (!shell || !state) return;

    const subtitle = payload.subtitle || payload.overview || '';
    const overview = payload.overview || payload.subtitle || '';
    const heroSignalSource = solutionNormalizeList(payload.overview_meta).length ? payload.overview_meta : payload.headline_cards;
    const heroAbstract = document.getElementById('solution-hero-abstract');
    const heroAbstractCard = document.getElementById('solution-hero-abstract-card');
    const subtitleNode = document.getElementById('solution-subtitle');

    document.getElementById('solution-title').textContent = payload.title || '查看方案';
    if (subtitleNode) {
        subtitleNode.textContent = subtitle;
        subtitleNode.hidden = !subtitle;
    }
    if (heroAbstract) {
        heroAbstract.textContent = overview;
    }
    if (heroAbstractCard) {
        heroAbstractCard.hidden = !overview;
    }
    document.getElementById('solution-overview-text').textContent = overview;

    solutionRenderNav(payload.nav_items);
    solutionRenderHeroSignals(heroSignalSource);
    solutionRenderHeroFocus(payload.headline_cards, overview);
    solutionRenderHeadlineCards(payload.headline_cards);
    solutionRenderHeroMetrics(payload.metrics);
    solutionRenderOverviewMeta(payload.overview_meta);
    solutionRenderMetrics(payload.metrics);
    solutionRenderFocusCards(payload.focus_cards);
    solutionRenderDimensionCards(payload.dimension_cards);
    solutionRenderRoadmap(payload.roadmap);
    solutionRenderValueCards(payload.value_cards);
    solutionRenderRiskCards(payload.risk_cards);
    solutionRenderActions(payload.action_items);

    state.hidden = true;
    shell.hidden = false;
    solutionBindScrollSpy();
    solutionBindHeaderActions(payload.report_name || solutionGetReportName());
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

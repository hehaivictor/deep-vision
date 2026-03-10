const SOLUTION_API_BASE = `${window.location.origin}/api`;

function solutionEscapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
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
    params.set('v', '20260310-solution-v3');
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
    nav.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
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

function solutionRenderMetrics(items) {
    const root = document.getElementById('solution-metrics');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
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
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-overview-meta-item">
            <div class="solution-overview-meta-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-overview-meta-value">${solutionEscapeHtml(item.value)}</div>
        </article>
    `).join('');
}

function solutionRenderHeadlineCards(items) {
    const root = document.getElementById('solution-headline-cards');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-summary-card">
            <div class="solution-summary-label">${solutionEscapeHtml(item.label)}</div>
            <div class="solution-summary-value">${solutionEscapeHtml(item.value)}</div>
            <div class="solution-summary-detail">${solutionEscapeHtml(item.detail)}</div>
        </article>
    `).join('');
}

function solutionRenderFocusCards(items) {
    const root = document.getElementById('solution-focus-cards');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-card">
            <div class="solution-card-badge">重点洞察</div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.summary)}</p>
            <p class="solution-card-meta">${solutionEscapeHtml(item.detail)}</p>
        </article>
    `).join('');
}

function solutionRenderDimensionCards(items) {
    const root = document.getElementById('solution-dimension-cards');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-card">
            <div class="solution-card-badge">${solutionEscapeHtml(item.badge)}</div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.name)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.summary)}</p>
            <ul class="solution-card-list">
                ${(Array.isArray(item.points) ? item.points : []).map((point) => `<li>${solutionEscapeHtml(point)}</li>`).join('')}
            </ul>
        </article>
    `).join('');
}

function solutionRenderRoadmap(items) {
    const root = document.getElementById('solution-roadmap');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-roadmap-item">
            <div class="solution-roadmap-side">
                <div class="solution-roadmap-phase">${solutionEscapeHtml(item.phase)}</div>
                <div class="solution-roadmap-time">${solutionEscapeHtml(item.timeline)}</div>
            </div>
            <div>
                <h3 class="solution-roadmap-title">${solutionEscapeHtml(item.goal)}</h3>
                <ul class="solution-roadmap-list">
                    ${(Array.isArray(item.tasks) ? item.tasks : []).map((task) => `<li>${solutionEscapeHtml(task)}</li>`).join('')}
                </ul>
            </div>
        </article>
    `).join('');
}

function solutionRenderValueCards(items) {
    const root = document.getElementById('solution-value-cards');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-card">
            <div class="solution-card-badge">预期收益</div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.value)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.title)}</p>
            <p class="solution-card-meta">${solutionEscapeHtml(item.description)}</p>
        </article>
    `).join('');
}

function solutionRenderRiskCards(items) {
    const root = document.getElementById('solution-risk-cards');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-card">
            <div class="solution-card-badge">风险依赖</div>
            <h3 class="solution-card-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-card-copy">${solutionEscapeHtml(item.description)}</p>
            <p class="solution-card-meta">${solutionEscapeHtml(item.guardrail)}</p>
        </article>
    `).join('');
}

function solutionRenderActions(items) {
    const root = document.getElementById('solution-actions');
    if (!root) return;
    root.innerHTML = (Array.isArray(items) ? items : []).map((item) => `
        <article class="solution-action-item">
            <div class="solution-action-owner">${solutionEscapeHtml(item.owner)}</div>
            <h3 class="solution-action-title">${solutionEscapeHtml(item.title)}</h3>
            <p class="solution-action-copy">${solutionEscapeHtml(item.detail)}</p>
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

    document.getElementById('solution-title').textContent = payload.title || '查看方案';
    document.getElementById('solution-subtitle').textContent = payload.subtitle || '';
    document.getElementById('solution-overview-text').textContent = payload.overview || '';

    solutionRenderHeadlineCards(payload.headline_cards);
    solutionRenderNav(payload.nav_items);
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

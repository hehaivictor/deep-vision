(function (global) {
    function cloneDefaultValue(value) {
        if (Array.isArray(value)) {
            return value.map((item) => cloneDefaultValue(item));
        }
        if (value && typeof value === 'object') {
            return Object.fromEntries(
                Object.entries(value).map(([key, item]) => [key, cloneDefaultValue(item)])
            );
        }
        return value;
    }

    const reportStateDefaults = {
        useVirtualReportList: true,
        virtualReportCardHeight: 96,
        virtualReportGroupHeight: 40,
        virtualReportRowGap: 16,
        virtualReportOverscan: 6,
        virtualReportScrollTop: 0,
        virtualReportViewportHeight: 0,
        reportGridColumns: 1,
        reportItemHeights: {},
        reportItemOffsets: [0],
        reportTotalHeight: 0,
        reportMeasureRaf: null,
        reports: [],
        reportsLoaded: false,
        filteredReports: [],
        reportItems: [],
        selectedReport: null,
        presentationPdfUrl: '',
        presentationLocalUrl: '',
        reportContent: '',
        showDeleteReportModal: false,
        reportToDelete: null,
        reportBatchMode: false,
        selectedReportNames: [],
        reportSearchQuery: '',
        reportSortOrder: 'newest',
        reportGroupBy: 'none',
        reportSearchDebounceTimer: null,
        appendixExportOutsideHandler: null,
        selectedReportMeta: {
            name: '',
            title: '',
            scenarioName: '',
            createdAt: '',
            templateLabel: '',
            sessionId: '',
            reportProfile: '',
            sourceReportName: '',
            variantLabel: '',
        },
        reportDetailModel: {
            sections: [],
            primarySections: [],
            currentSectionId: '',
            currentTopSectionId: '',
            currentSectionLabel: '阅读中',
            progressPercent: 0,
            remainingLabel: '-',
            summaryText: '',
            overviewItems: [],
            actionItems: [],
            mobileNavOpen: false,
        },
        reportDetailCache: {},
        reportDetailEnhancing: false,
        reportDetailEnhanceTimer: null,
        reportDetailObserver: null,
        reportDetailSectionRegistry: [],
        reportTableCleanupFns: [],
        lastPresentationUrl: '',
    };

    const reportStateMethods = {
        refreshReportsView(options = {}) {
            const hasCachedReports = this.reportsLoaded;
            return this.loadReports({
                suppressErrorToast: hasCachedReports,
                ...options,
            });
        },

        confirmDeleteReport(reportName) {
            this.reportToDelete = reportName;
            this.showDeleteReportModal = true;
        },

        async deleteReport() {
            if (!this.reportToDelete) return;

            try {
                await this.apiCall(`/reports/${encodeURIComponent(this.reportToDelete)}`, { method: 'DELETE' });
                if (this.selectedReportMeta?.name === this.reportToDelete) {
                    this.resetSelectedReportDetail();
                }
                this.invalidateReportDetailCache(this.reportToDelete);
                this.reports = this.reports.filter(r => r.name !== this.reportToDelete);
                this.filterReports();
                this.showDeleteReportModal = false;
                this.reportToDelete = null;
                this.showToast('报告已删除', 'success');
            } catch (error) {
                this.showToast('删除报告失败', 'error');
            }
        },

        enterReportBatchMode() {
            this.exitSessionBatchMode();
            this.reportBatchMode = true;
            this.selectedReportNames = [];
        },

        exitReportBatchMode() {
            this.reportBatchMode = false;
            this.selectedReportNames = [];
            if (this.batchDeleteTarget === 'reports') {
                this.showBatchDeleteModal = false;
            }
        },

        isReportSelected(reportName) {
            return this.selectedReportNames.includes(reportName);
        },

        toggleReportSelection(reportName) {
            if (!this.reportBatchMode) return;
            if (this.isReportSelected(reportName)) {
                this.selectedReportNames = this.selectedReportNames.filter(name => name !== reportName);
            } else {
                this.selectedReportNames = [...this.selectedReportNames, reportName];
            }
        },

        getFilteredReportNames() {
            return this.filteredReports.map(report => report.name).filter(Boolean);
        },

        areAllFilteredReportsSelected() {
            const filteredNames = this.getFilteredReportNames();
            if (filteredNames.length === 0) return false;
            return filteredNames.every(name => this.selectedReportNames.includes(name));
        },

        toggleSelectAllReports() {
            if (!this.reportBatchMode) return;
            const filteredNames = this.getFilteredReportNames();
            if (filteredNames.length === 0) return;
            if (this.areAllFilteredReportsSelected()) {
                this.selectedReportNames = this.selectedReportNames.filter(name => !filteredNames.includes(name));
            } else {
                const merged = new Set([...this.selectedReportNames, ...filteredNames]);
                this.selectedReportNames = Array.from(merged);
            }
        },

        pruneSelectedReports() {
            const valid = new Set(this.reports.map(report => report.name));
            this.selectedReportNames = this.selectedReportNames.filter(name => valid.has(name));
        },

        findMatchedSessionForReport(report) {
            const reportSessionId = String(report?.session_id || '').trim();
            if (!reportSessionId || !Array.isArray(this.sessions) || this.sessions.length === 0) {
                return null;
            }
            return this.sessions.find(session => String(session?.session_id || '').trim() === reportSessionId) || null;
        },

        extractReportDisplayTitle(reportName) {
            if (!reportName || typeof reportName !== 'string') return '';

            let normalized = reportName.trim();
            normalized = normalized.replace(/\.[^.]+$/, '');
            normalized = normalized.replace(/^deep-vision-\d{8}-/i, '');
            normalized = normalized.replace(/^deep-vision-/i, '');
            normalized = normalized.replace(/[-_]+/g, ' ').trim();

            return normalized || reportName;
        },

        resolveReportDisplayTitle(report, matchedSession = null) {
            if (!report) return '未命名报告';

            const explicitTitle = (report.title || report.topic || report.report_title || '').trim();
            if (explicitTitle) return explicitTitle;

            const linkedSession = matchedSession || this.findMatchedSessionForReport(report);
            const sessionTopic = (linkedSession?.topic || '').trim();
            if (sessionTopic) return sessionTopic;

            const fallbackTitle = this.extractReportDisplayTitle(report.name || '');
            return fallbackTitle || report.name || '未命名报告';
        },

        resolveReportScenarioName(report, matchedSession = null) {
            if (!report) return '未分类场景';

            const explicitScenario = (report.scenario_name || report.scenario_label || report.scenario || '').trim();
            if (explicitScenario) return explicitScenario;

            const linkedSession = matchedSession || this.findMatchedSessionForReport(report);
            const scenarioName = (linkedSession?.scenario_config?.name || '').trim();
            if (scenarioName) return scenarioName;

            if (linkedSession?.scenario_id) {
                const scenario = this.scenarios.find(item => item.id === linkedSession.scenario_id);
                if (scenario?.name) return scenario.name;
            }

            return '未分类场景';
        },

        createEmptySelectedReportMeta() {
            return {
                name: '',
                title: '',
                scenarioName: '',
                createdAt: '',
                templateLabel: '',
                sessionId: '',
                reportProfile: '',
                sourceReportName: '',
                variantLabel: ''
            };
        },

        createEmptyReportDetailModel() {
            return {
                sections: [],
                primarySections: [],
                currentSectionId: '',
                currentTopSectionId: '',
                currentSectionLabel: '阅读中',
                progressPercent: 0,
                remainingLabel: '-',
                summaryText: '',
                overviewItems: [],
                actionItems: [],
                mobileNavOpen: false
            };
        },

        cloneSelectedReportMeta(meta = {}) {
            return {
                ...this.createEmptySelectedReportMeta(),
                ...(meta && typeof meta === 'object' ? meta : {})
            };
        },

        cloneReportDetailModel(model = {}) {
            const source = model && typeof model === 'object' ? model : {};
            return {
                ...this.createEmptyReportDetailModel(),
                ...source,
                sections: Array.isArray(source.sections)
                    ? source.sections.map(item => ({ ...item }))
                    : [],
                primarySections: Array.isArray(source.primarySections)
                    ? source.primarySections.map(item => ({ ...item }))
                    : [],
                overviewItems: Array.isArray(source.overviewItems)
                    ? source.overviewItems.map(item => ({ ...item }))
                    : [],
                actionItems: Array.isArray(source.actionItems)
                    ? source.actionItems.map(item => ({ ...item }))
                    : []
            };
        },

        getCachedReportDetail(filename = '') {
            const targetFilename = String(filename || '').trim();
            if (!targetFilename || !this.reportDetailCache || typeof this.reportDetailCache !== 'object') {
                return null;
            }
            const entry = this.reportDetailCache[targetFilename];
            if (!entry || typeof entry !== 'object') return null;
            if (!String(entry.content || '').trim()) return null;
            return {
                content: String(entry.content || ''),
                meta: this.cloneSelectedReportMeta(entry.meta),
                detailModel: this.cloneReportDetailModel(entry.detailModel)
            };
        },

        cacheCurrentReportDetailSnapshot() {
            const targetFilename = String(this.selectedReport || this.selectedReportMeta?.name || '').trim();
            if (!targetFilename || !String(this.reportContent || '').trim()) return;

            this.reportDetailCache = {
                ...(this.reportDetailCache && typeof this.reportDetailCache === 'object' ? this.reportDetailCache : {}),
                [targetFilename]: {
                    content: String(this.reportContent || ''),
                    meta: this.cloneSelectedReportMeta(this.selectedReportMeta),
                    detailModel: this.cloneReportDetailModel(this.reportDetailModel)
                }
            };
        },

        invalidateReportDetailCache(filename = '') {
            const targetFilename = String(filename || '').trim();
            if (!targetFilename) {
                this.reportDetailCache = {};
                return;
            }
            if (!this.reportDetailCache || typeof this.reportDetailCache !== 'object' || !this.reportDetailCache[targetFilename]) {
                return;
            }
            const nextCache = { ...this.reportDetailCache };
            delete nextCache[targetFilename];
            this.reportDetailCache = nextCache;
        },

        findReportBySessionId(sessionId = '') {
            const targetSessionId = this.normalizeComparableId(sessionId);
            if (!targetSessionId || !Array.isArray(this.reports)) return null;
            return this.reports.find(report => this.normalizeComparableId(report?.session_id) === targetSessionId) || null;
        },

        resolveReportTemplateLabel(report, matchedSession = null) {
            const explicitTemplate = String(
                report?.report_template ||
                report?.template_name ||
                report?.template ||
                ''
            ).trim();
            if (explicitTemplate) return explicitTemplate;

            const linkedSession = matchedSession || this.findMatchedSessionForReport(report);
            const reportType = String(
                report?.report_type ||
                linkedSession?.scenario_config?.report_type ||
                ''
            ).trim().toLowerCase();

            if (reportType === 'assessment') return '评估模板';
            if (reportType === 'standard') return '标准模板';
            return '';
        },

        buildSelectedReportMeta(filename) {
            const record = Array.isArray(this.reports)
                ? this.reports.find(item => item?.name === filename)
                : null;
            const fallbackReport = record || { name: filename };
            const matchedSession = this.findMatchedSessionForReport(fallbackReport);

            return {
                name: filename || '',
                title: this.resolveReportDisplayTitle(fallbackReport, matchedSession),
                scenarioName: this.resolveReportScenarioName(fallbackReport, matchedSession),
                createdAt: fallbackReport?.created_at || matchedSession?.updated_at || matchedSession?.created_at || '',
                templateLabel: this.resolveReportTemplateLabel(fallbackReport, matchedSession),
                sessionId: String(fallbackReport?.session_id || matchedSession?.session_id || '').trim(),
                reportProfile: this.normalizeReportProfile(fallbackReport?.report_profile, 'balanced'),
                sourceReportName: String(fallbackReport?.source_report_name || '').trim(),
                variantLabel: String(
                    fallbackReport?.report_variant_label
                    || (this.normalizeReportProfile(fallbackReport?.report_profile, 'balanced') === 'quality' ? '精审版' : '普通版')
                ).trim(),
            };
        },

        cleanupReportDetailEnhancements(options = {}) {
            const { resetModel = true } = options;

            if (this.reportDetailEnhanceTimer) {
                window.clearTimeout(this.reportDetailEnhanceTimer);
                this.reportDetailEnhanceTimer = null;
            }

            if (this.reportDetailObserver) {
                this.reportDetailObserver.disconnect();
                this.reportDetailObserver = null;
            }

            if (this.appendixExportOutsideHandler) {
                document.removeEventListener('click', this.appendixExportOutsideHandler, true);
                this.appendixExportOutsideHandler = null;
            }

            if (Array.isArray(this.reportTableCleanupFns) && this.reportTableCleanupFns.length > 0) {
                this.reportTableCleanupFns.forEach((cleanup) => {
                    if (typeof cleanup !== 'function') return;
                    try {
                        cleanup();
                    } catch (error) {
                        console.warn('清理报告表格增强失败:', error);
                    }
                });
            }
            this.reportTableCleanupFns = [];

            this.reportDetailSectionRegistry = [];
            if (resetModel) {
                this.reportDetailModel = this.createEmptyReportDetailModel();
                this.reportDetailEnhancing = false;
            } else if (this.reportDetailModel) {
                this.reportDetailModel.mobileNavOpen = false;
            }
        },

        closeSelectedReportDetail() {
            this.reportDetailEnhancing = false;
            this.selectedReport = null;
            this.presentationPdfUrl = '';
            this.presentationLocalUrl = '';
            this.stopPresentationPolling();
            this.resetPresentationProgressFeedback();
            if (this.reportDetailModel) {
                this.reportDetailModel.mobileNavOpen = false;
            }
        },

        resetSelectedReportDetail() {
            this.cleanupReportDetailEnhancements();
            this.reportDetailEnhancing = false;
            this.selectedReport = null;
            this.reportContent = '';
            this.selectedReportMeta = this.createEmptySelectedReportMeta();
            this.presentationPdfUrl = '';
            this.presentationLocalUrl = '';
            this.stopPresentationPolling();
            this.resetPresentationProgressFeedback();
        },

        scheduleReportDetailEnhancement(options = {}) {
            const { silent = false } = options;
            if (!this.selectedReport || !this.reportContent) {
                this.reportDetailEnhancing = false;
                return;
            }

            this.reportDetailEnhancing = !silent;
            this.cleanupReportDetailEnhancements({ resetModel: false });
            this.reportDetailEnhanceTimer = window.setTimeout(() => {
                this.reportDetailEnhanceTimer = null;
                this.onReportRendered();
            }, 0);
        },

        goToReportSection(sectionId) {
            const target = document.getElementById(String(sectionId || '').trim());
            if (!target) return;

            this.updateActiveReportSection(sectionId);

            const prefersReducedMotion = typeof window !== 'undefined'
                && typeof window.matchMedia === 'function'
                && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

            target.scrollIntoView({
                behavior: prefersReducedMotion ? 'auto' : 'smooth',
                block: 'start'
            });
            target.classList.add('is-highlighted');
            window.setTimeout(() => target.classList.remove('is-highlighted'), 1200);
            this.reportDetailModel.mobileNavOpen = false;
            if (typeof target.focus === 'function') {
                target.focus({ preventScroll: true });
            }
        },

        isReportNavItemActive(section) {
            if (!section || !this.reportDetailModel) return false;
            const depth = Number(section.depth || 0);
            if (depth === 0) {
                return this.reportDetailModel.currentTopSectionId === section.id;
            }
            return this.reportDetailModel.currentSectionId === section.id;
        },

        ensureReportNavItemVisible(sectionId) {
            if (!sectionId || !this.$nextTick) return;

            this.$nextTick(() => {
                const root = this.$refs?.reportDetailView || document;
                const selector = `[data-section-id="${String(sectionId)}"]`;
                const navTargets = [
                    root?.querySelector?.('.dv-report-sidebar-nav'),
                    root?.querySelector?.('.dv-report-mobile-nav-list')
                ].filter(Boolean);

                navTargets.forEach((container) => {
                    const target = container.querySelector(selector);
                    if (!target) return;

                    const containerRect = container.getBoundingClientRect();
                    const targetRect = target.getBoundingClientRect();
                    const padding = 10;

                    if (targetRect.top < containerRect.top) {
                        container.scrollTop -= (containerRect.top - targetRect.top) + padding;
                    } else if (targetRect.bottom > containerRect.bottom) {
                        container.scrollTop += (targetRect.bottom - containerRect.bottom) + padding;
                    }
                });
            });
        },

        async loadReports(options = {}) {
            const {
                suppressErrorToast = false
            } = options;
            try {
                this.reports = await this.apiCall('/reports?page=1&page_size=100');
                this.reportsLoaded = true;
                this.filterReports();
            } catch (error) {
                console.error('加载报告失败:', error);
                if (!suppressErrorToast) {
                    this.showToast('加载报告列表失败', 'error');
                }
            }
        },

        onReportSearchInput() {
            if (this.reportSearchDebounceTimer) {
                clearTimeout(this.reportSearchDebounceTimer);
            }
            this.reportSearchDebounceTimer = setTimeout(() => {
                this.filterReports();
            }, 300);
        },

        filterReports() {
            let result = Array.isArray(this.reports)
                ? this.reports.map(report => {
                    const matchedSession = this.findMatchedSessionForReport(report);
                    return {
                        ...report,
                        display_title: this.resolveReportDisplayTitle(report, matchedSession),
                        scenario_name: this.resolveReportScenarioName(report, matchedSession)
                    };
                })
                : [];

            if (this.reportSearchQuery.trim()) {
                const query = this.reportSearchQuery.toLowerCase();
                result = result.filter(r => {
                    const reportName = r.name?.toLowerCase() || '';
                    const displayTitle = (r.display_title || '').toLowerCase();
                    const scenarioName = (r.scenario_name || '').toLowerCase();
                    return reportName.includes(query) || displayTitle.includes(query) || scenarioName.includes(query);
                });
            }

            switch (this.reportSortOrder) {
                case 'oldest':
                    result.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
                    break;
                case 'newest':
                default:
                    result.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                    break;
            }

            this.filteredReports = result;
            this.pruneSelectedReports();
            this.reportItems = this.buildReportItems(result);
            this.initializeReportMeasurements();

            if (this.useVirtualReportList) {
                this.$nextTick(() => {
                    this.resetVirtualReportScroll();
                });
            }
            this.scheduleAppShellSnapshotPersist();
        },

        getReportDateKey(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            if (!Number.isFinite(date.getTime())) return '';
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        },

        formatReportDateLabel(dateKey) {
            if (!dateKey || dateKey === 'unknown-date') return '未标注日期';
            const parts = dateKey.split('-');
            if (parts.length !== 3) return dateKey;
            const year = Number(parts[0]);
            const month = Number(parts[1]);
            const day = Number(parts[2]);
            return `${year}年${month}月${day}日`;
        },

        buildReportItems(reports) {
            if (this.reportGroupBy === 'none') {
                return reports.map(report => ({
                    type: 'report',
                    key: report.name,
                    report
                }));
            }

            const groupsMap = new Map();
            const isOldest = this.reportSortOrder === 'oldest';

            reports.forEach(report => {
                let key = 'all';
                let label = '全部报告';

                if (this.reportGroupBy === 'date') {
                    const dateKey = this.getReportDateKey(report.created_at) || 'unknown-date';
                    key = `date-${dateKey}`;
                    label = this.formatReportDateLabel(dateKey);
                } else if (this.reportGroupBy === 'scenario') {
                    const scenarioName = (report.scenario_name || '未分类场景').trim();
                    key = scenarioName && scenarioName !== '未分类场景'
                        ? `scenario-${scenarioName}`
                        : 'scenario-uncategorized';
                    label = scenarioName || '未分类场景';
                }

                const createdAtTs = this.parseValidTimestamp(report.created_at);

                if (!groupsMap.has(key)) {
                    groupsMap.set(key, {
                        key,
                        label,
                        reports: [],
                        latestTs: createdAtTs,
                        oldestTs: createdAtTs
                    });
                }

                const group = groupsMap.get(key);
                group.reports.push(report);
                group.latestTs = Math.max(group.latestTs, createdAtTs);
                group.oldestTs = Math.min(group.oldestTs, createdAtTs);
            });

            const sortByCreatedAt = (a, b) => {
                const tsA = this.parseValidTimestamp(a.created_at);
                const tsB = this.parseValidTimestamp(b.created_at);
                return isOldest ? tsA - tsB : tsB - tsA;
            };

            const groups = Array.from(groupsMap.values());
            groups.forEach(group => {
                group.reports.sort(sortByCreatedAt);
            });

            groups.sort((a, b) => {
                const anchorA = isOldest ? a.oldestTs : a.latestTs;
                const anchorB = isOldest ? b.oldestTs : b.latestTs;
                if (anchorA !== anchorB) {
                    return isOldest ? anchorA - anchorB : anchorB - anchorA;
                }
                return a.label.localeCompare(b.label, 'zh-Hans');
            });

            if (this.reportGroupBy === 'scenario') {
                const uncategorizedIndex = groups.findIndex(group => group.key === 'scenario-uncategorized');
                if (uncategorizedIndex >= 0) {
                    const [uncategorized] = groups.splice(uncategorizedIndex, 1);
                    groups.push(uncategorized);
                }
            }

            const items = [];
            groups.forEach(group => {
                items.push({
                    type: 'group',
                    key: `group-${group.key}`,
                    label: group.label,
                    count: group.reports.length
                });

                group.reports.forEach(report => {
                    items.push({
                        type: 'report',
                        key: report.name,
                        report
                    });
                });
            });

            return items;
        },

        initializeReportMeasurements() {
            const nextHeights = {};
            this.reportItems.forEach(item => {
                const key = item.key;
                const fallback = item.type === 'group' ? this.virtualReportGroupHeight : this.virtualReportCardHeight;
                nextHeights[key] = this.reportItemHeights[key] || fallback;
            });
            this.reportItemHeights = nextHeights;
            this.recomputeReportOffsets();

            if (this.useVirtualReportList) {
                this.$nextTick(() => {
                    this.measureReportItemHeights();
                });
            }
        },

        recomputeReportOffsets() {
            const offsets = new Array(this.reportItems.length + 1);
            let total = 0;
            this.reportItems.forEach((item, index) => {
                const fallback = item.type === 'group' ? this.virtualReportGroupHeight : this.virtualReportCardHeight;
                const height = this.reportItemHeights[item.key] || fallback;
                if (index > 0) {
                    total += this.virtualReportRowGap;
                }
                offsets[index] = total;
                total += height;
            });
            offsets[this.reportItems.length] = total;
            this.reportItemOffsets = offsets;
            this.reportTotalHeight = total;
        },

        scheduleReportMeasure() {
            if (this.reportMeasureRaf) return;
            this.reportMeasureRaf = requestAnimationFrame(() => {
                this.reportMeasureRaf = null;
                this.measureReportItemHeights();
            });
        },

        measureReportItemHeights() {
            if (!this.useVirtualReportList || !this.$refs?.reportListScroller) return;
            const nodes = this.$refs.reportListScroller.querySelectorAll('[data-report-key]');
            let changed = false;
            nodes.forEach(node => {
                if (!node || node.offsetParent === null) return;
                const key = node.dataset.reportKey;
                if (!key) return;
                const height = Math.ceil(node.getBoundingClientRect().height);
                if (height && this.reportItemHeights[key] !== height) {
                    this.reportItemHeights[key] = height;
                    changed = true;
                }
            });
            if (changed) {
                this.recomputeReportOffsets();
                this.onReportListScroll();
            }
        },

        findReportIndexByOffset(offset) {
            const offsets = this.reportItemOffsets || [0];
            let low = 0;
            let high = offsets.length;
            while (low < high) {
                const mid = Math.floor((low + high) / 2);
                if (offsets[mid] <= offset) {
                    low = mid + 1;
                } else {
                    high = mid;
                }
            }
            return Math.max(0, low - 1);
        },

        setupVirtualReportList() {
            if (!this.useVirtualReportList) return;
            this.updateVirtualReportLayout();
            const onResize = () => this.updateVirtualReportLayout();
            const onScroll = () => this.onReportListScroll();
            window.addEventListener('resize', onResize);
            window.addEventListener('scroll', onScroll, { passive: true });
            this._virtualReportResizeHandler = onResize;
            this._virtualReportScrollHandler = onScroll;
        },

        updateVirtualReportLayout() {
            if (!this.useVirtualReportList) return;
            this.reportGridColumns = window.matchMedia('(min-width: 768px)').matches ? 2 : 1;
            this.virtualReportViewportHeight = window.innerHeight || 0;
            this.onReportListScroll();
        },

        resetVirtualReportScroll() {
            if (!this.useVirtualReportList) return;
            this.reportGridColumns = window.matchMedia('(min-width: 768px)').matches ? 2 : 1;
            this.virtualReportViewportHeight = window.innerHeight || 0;
            this.onReportListScroll();
        },

        onReportListScroll() {
            if (!this.useVirtualReportList) return;
            if (this.$refs?.reportListScroller) {
                const listTop = this.$refs.reportListScroller.getBoundingClientRect().top + window.scrollY;
                const scrollY = window.scrollY || window.pageYOffset || 0;
                const rawScrollTop = Math.max(0, scrollY - listTop);
                const maxScrollTop = Math.max(0, this.reportTotalHeight - this.virtualReportViewportHeight);
                this.virtualReportScrollTop = Math.min(rawScrollTop, maxScrollTop);
                this.scheduleReportMeasure();
            }
        },
    };

    const reportStateDescriptors = {
        virtualReportStartRow: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualReportList) return 0;
                const startIndex = this.findReportIndexByOffset(this.virtualReportScrollTop);
                return Math.max(0, startIndex - this.virtualReportOverscan);
            }
        },
        virtualReportEndRow: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualReportList) return this.reportItems.length;
                const bottomIndex = this.findReportIndexByOffset(this.virtualReportScrollTop + this.virtualReportViewportHeight);
                const end = bottomIndex + this.virtualReportOverscan + 1;
                return Math.min(this.reportItems.length, end);
            }
        },
        virtualReportPaddingTop: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualReportList || this.isReportTwoColumnLayout) return 0;
                const baseTop = this.reportItemOffsets[this.virtualReportStartRow] || 0;
                const gapAdjust = this.reportItems.length > 0 ? this.virtualReportRowGap : 0;
                return Math.max(0, baseTop - gapAdjust);
            }
        },
        virtualReportPaddingBottom: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualReportList || this.isReportTwoColumnLayout) return 0;
                const endOffset = this.reportItemOffsets[this.virtualReportEndRow] || 0;
                const gapAdjust = this.reportItems.length > 0 ? this.virtualReportRowGap : 0;
                return Math.max(0, this.reportTotalHeight - endOffset - gapAdjust);
            }
        },
        virtualVisibleReports: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualReportList || this.isReportTwoColumnLayout) return this.reportItems;
                return this.reportItems.slice(this.virtualReportStartRow, this.virtualReportEndRow);
            }
        },
        isReportTwoColumnLayout: {
            enumerable: true,
            configurable: true,
            get() {
                return this.reportGridColumns > 1;
            }
        },
        reportsToRender: {
            enumerable: true,
            configurable: true,
            get() {
                return this.useVirtualReportList ? this.virtualVisibleReports : this.reportItems;
            }
        },
        reportGroupCount: {
            enumerable: true,
            configurable: true,
            get() {
                if (this.reportGroupBy === 'none') return 0;
                return this.reportItems.filter(item => item.type === 'group').length;
            }
        },
    };

    function attach(app) {
        if (!app || typeof app !== 'object') return app;

        Object.entries(reportStateDefaults).forEach(([key, value]) => {
            if (typeof app[key] === 'undefined') {
                app[key] = cloneDefaultValue(value);
            }
        });

        Object.assign(app, reportStateMethods);
        Object.defineProperties(app, reportStateDescriptors);
        return app;
    }

    global.DeepVisionReportStateModule = { attach };
})(window);

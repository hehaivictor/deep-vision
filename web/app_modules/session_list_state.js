(function (global) {
    function cloneDefaultValue(value) {
        if (Array.isArray(value)) return value.slice();
        if (value && typeof value === 'object') return { ...value };
        return value;
    }

    const sessionListStateDefaults = {
        sessions: [],
        sessionsLoaded: false,
        sessionBatchMode: false,
        selectedSessionIds: [],
        sessionSearchQuery: '',
        sessionStatusFilter: 'all',
        sessionSortOrder: 'newest',
        sessionGroupBy: 'none',
        filteredSessions: [],
        currentPage: 1,
        pageSize: 10,
        searchDebounceTimer: null,
        useVirtualList: true,
        virtualCardHeight: 128,
        virtualRowGap: 12,
        virtualOverscan: 3,
        virtualScrollTop: 0,
        virtualViewportHeight: 0,
        virtualColumns: 2,
        sessionsAutoRefreshInterval: null,
        sessionsAutoRefreshInFlight: false,
    };

    const sessionListStateMethods = {
        async loadSessions(options = {}) {
            const {
                silent = false,
                preserveListState = false,
                suppressErrorToast = false
            } = options;

            if (!silent) {
                this.loading = true;
            }
            try {
                this.sessions = await this.apiCall('/sessions?page=1&page_size=100');
                this.sessionsLoaded = true;
                this.filterSessions({
                    preservePage: preserveListState
                });
                if (Array.isArray(this.reports) && this.reports.length > 0) {
                    this.filterReports();
                }
            } catch (error) {
                if (!suppressErrorToast) {
                    this.showToast('加载会话列表失败', 'error');
                }
            } finally {
                if (!silent) {
                    this.loading = false;
                }
                this.startSessionsAutoRefreshIfNeeded();
            }
        },

        hasActiveReportGenerationInSessions() {
            if (!Array.isArray(this.sessions) || this.sessions.length === 0) {
                return false;
            }
            return this.sessions.some(session => Boolean(this.getSessionReportGeneration(session)));
        },

        getSessionsAutoRefreshInterval() {
            const configuredInterval = Number(
                (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.api?.sessionListPollInterval)
                    ? SITE_CONFIG.api.sessionListPollInterval
                    : 0
            );
            if (Number.isFinite(configuredInterval) && configuredInterval >= 1000) {
                return Math.floor(configuredInterval);
            }
            return 3000;
        },

        startSessionsAutoRefreshIfNeeded() {
            const shouldAutoRefresh = this.authReady
                && this.currentView === 'sessions'
                && this.hasActiveReportGenerationInSessions();

            if (!shouldAutoRefresh) {
                this.stopSessionsAutoRefresh();
                return;
            }

            if (this.sessionsAutoRefreshInterval) {
                return;
            }

            const pollInterval = this.getSessionsAutoRefreshInterval();
            this.sessionsAutoRefreshInterval = setInterval(async () => {
                if (this.sessionsAutoRefreshInFlight) return;

                if (!this.authReady || this.currentView !== 'sessions') {
                    this.stopSessionsAutoRefresh();
                    return;
                }

                this.sessionsAutoRefreshInFlight = true;
                try {
                    await this.loadSessions({
                        silent: true,
                        preserveListState: true,
                        suppressErrorToast: true
                    });
                } finally {
                    this.sessionsAutoRefreshInFlight = false;
                }
            }, pollInterval);
        },

        stopSessionsAutoRefresh() {
            if (this.sessionsAutoRefreshInterval) {
                clearInterval(this.sessionsAutoRefreshInterval);
                this.sessionsAutoRefreshInterval = null;
            }
            this.sessionsAutoRefreshInFlight = false;
        },

        refreshSessionsView(options = {}) {
            const hasCachedSessions = this.sessionsLoaded;
            return this.loadSessions({
                silent: hasCachedSessions,
                preserveListState: hasCachedSessions,
                suppressErrorToast: hasCachedSessions,
                ...options,
            });
        },

        enterSessionBatchMode() {
            this.exitReportBatchMode();
            this.sessionBatchMode = true;
            this.selectedSessionIds = [];
        },

        exitSessionBatchMode() {
            this.sessionBatchMode = false;
            this.selectedSessionIds = [];
            if (this.batchDeleteTarget === 'sessions') {
                this.showBatchDeleteModal = false;
            }
        },

        isSessionSelected(sessionId) {
            return this.selectedSessionIds.includes(sessionId);
        },

        toggleSessionSelection(sessionId) {
            if (!this.sessionBatchMode) return;
            if (this.isSessionSelected(sessionId)) {
                this.selectedSessionIds = this.selectedSessionIds.filter(id => id !== sessionId);
            } else {
                this.selectedSessionIds = [...this.selectedSessionIds, sessionId];
            }
        },

        getFilteredSessionIds() {
            return this.filteredSessions.map(session => session.session_id).filter(Boolean);
        },

        areAllFilteredSessionsSelected() {
            const filteredIds = this.getFilteredSessionIds();
            if (filteredIds.length === 0) return false;
            return filteredIds.every(id => this.selectedSessionIds.includes(id));
        },

        toggleSelectAllSessions() {
            if (!this.sessionBatchMode) return;
            const filteredIds = this.getFilteredSessionIds();
            if (filteredIds.length === 0) return;
            if (this.areAllFilteredSessionsSelected()) {
                this.selectedSessionIds = this.selectedSessionIds.filter(id => !filteredIds.includes(id));
            } else {
                const merged = new Set([...this.selectedSessionIds, ...filteredIds]);
                this.selectedSessionIds = Array.from(merged);
            }
        },

        pruneSelectedSessions() {
            const valid = new Set(this.sessions.map(session => session.session_id));
            this.selectedSessionIds = this.selectedSessionIds.filter(id => valid.has(id));
        },

        onSessionSearchInput() {
            if (this.searchDebounceTimer) {
                clearTimeout(this.searchDebounceTimer);
            }
            this.searchDebounceTimer = setTimeout(() => {
                this.filterSessions();
            }, 300);
        },

        filterSessions(options = {}) {
            const { preservePage = false } = options;
            const previousPage = this.currentPage;
            let result = [...this.sessions];

            if (this.sessionSearchQuery.trim()) {
                const query = this.sessionSearchQuery.toLowerCase();
                result = result.filter(s =>
                    s.topic?.toLowerCase().includes(query) ||
                    s.scenario_config?.name?.toLowerCase().includes(query)
                );
            }

            if (this.sessionStatusFilter !== 'all') {
                result = result.filter(s => this.getEffectiveSessionStatus(s) === this.sessionStatusFilter);
            }

            switch (this.sessionSortOrder) {
                case 'oldest':
                    result.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
                    break;
                case 'newest':
                default:
                    result.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                    break;
            }

            this.filteredSessions = result;
            this.pruneSelectedSessions();
            if (preservePage) {
                const totalPages = Math.max(1, Math.ceil(this.filteredSessions.length / this.pageSize));
                this.currentPage = Math.min(Math.max(1, previousPage || 1), totalPages);
            } else {
                this.currentPage = 1;
            }
            if (this.useVirtualList) {
                this.$nextTick(() => {
                    this.resetVirtualScroll();
                });
            }
            this.scheduleAppShellSnapshotPersist();
        },

        getSessionReportGeneration(session) {
            const info = session?.report_generation;
            if (!info || typeof info !== 'object') return null;
            if (info.active !== true) return null;
            return info;
        },

        getSessionReportGenerationBadgeText(session) {
            const info = this.getSessionReportGeneration(session);
            if (!info) return '';
            const progress = Math.max(0, Math.min(99, Math.round(Number(info.progress) || 0)));
            return `报告生成中 ${progress}%`;
        },

        getSessionStatusBadgeText(session) {
            const statusText = this.getStatusText(this.getEffectiveSessionStatus(session));
            const generatingText = this.getSessionReportGenerationBadgeText(session);
            if (!generatingText) return statusText;
            return `${statusText}｜${generatingText}`;
        },

        getSessionStatusBadgeClass(status) {
            const classes = {
                'in_progress': 'session-status-badge--in-progress',
                'pending_review': 'session-status-badge--pending-review',
                'completed': 'session-status-badge--completed',
                'paused': 'session-status-badge--paused'
            };
            return classes[status] || 'session-status-badge--neutral';
        },

        getSessionStatusDotClass(status) {
            const classes = {
                'in_progress': 'session-status-dot--in-progress',
                'pending_review': 'session-status-dot--pending-review',
                'completed': 'session-status-dot--completed',
                'paused': 'session-status-dot--paused'
            };
            return classes[status] || 'session-status-dot--neutral';
        },

        getStatusBadgeClass(status) {
            return this.getSessionStatusBadgeClass(status);
        },

        getEffectiveSessionStatus(session) {
            if (!session) return 'in_progress';
            const raw = session.status || 'in_progress';
            const progress = this.getSessionTotalProgress(session);
            if (raw === 'in_progress' && progress >= 100) {
                return 'pending_review';
            }
            return raw;
        },

        getStatusText(status) {
            const texts = {
                'in_progress': '进行中',
                'completed': '已完成',
                'pending_review': '待确认',
                'paused': '已暂停'
            };
            return texts[status] || status;
        },

        getSessionStatusCount(status) {
            if (!Array.isArray(this.sessions)) return 0;
            return this.sessions.filter(s => this.getEffectiveSessionStatus(s) === status).length;
        },

        getSessionDateKey(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            if (!Number.isFinite(date.getTime())) return '';
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        },

        formatSessionDateGroupLabel(dateKey) {
            if (!dateKey || dateKey === 'unknown-date') return '未标注日期';

            const todayKey = this.getSessionDateKey(new Date().toISOString());
            const yesterday = new Date();
            yesterday.setDate(yesterday.getDate() - 1);
            const yesterdayKey = this.getSessionDateKey(yesterday.toISOString());

            if (dateKey === todayKey) return '今天';
            if (dateKey === yesterdayKey) return '昨天';

            const date = new Date(`${dateKey}T00:00:00`);
            if (!Number.isFinite(date.getTime())) return dateKey;
            const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
            return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${weekdays[date.getDay()]}`;
        },

        goToPage(page) {
            if (page >= 1 && page <= this.totalPages) {
                this.currentPage = page;
                const listEl = document.querySelector("[x-if=\"currentView === 'sessions'\"]");
                if (listEl) {
                    listEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        },

        setupVirtualList() {
            if (!this.useVirtualList) return;
            this.updateVirtualLayout();
            const onResize = () => this.updateVirtualLayout();
            const onScroll = () => this.onSessionListScroll();
            window.addEventListener('resize', onResize);
            window.addEventListener('scroll', onScroll, { passive: true });
            this._virtualResizeHandler = onResize;
            this._virtualScrollHandler = onScroll;
        },

        updateVirtualLayout() {
            if (!this.useVirtualList) return;
            this.virtualColumns = window.matchMedia('(min-width: 768px)').matches ? 2 : 1;
            this.virtualViewportHeight = window.innerHeight || 0;
            this.onSessionListScroll();
        },

        resetVirtualScroll() {
            if (!this.useVirtualList) return;
            this.virtualViewportHeight = window.innerHeight || 0;
            this.onSessionListScroll();
        },

        onSessionListScroll() {
            if (!this.useVirtualList) return;
            if (this.$refs?.sessionListScroller) {
                const listTop = this.$refs.sessionListScroller.getBoundingClientRect().top + window.scrollY;
                const scrollY = window.scrollY || window.pageYOffset || 0;
                const rawScrollTop = Math.max(0, scrollY - listTop);
                const maxScrollTop = Math.max(0, this.virtualTotalRows * this.virtualRowHeight - this.virtualViewportHeight);
                this.virtualScrollTop = Math.min(rawScrollTop, maxScrollTop);
            }
        },
    };

    const sessionListStateDescriptors = {
        totalPages: {
            enumerable: true,
            configurable: true,
            get() {
                return Math.ceil(this.filteredSessions.length / this.pageSize);
            }
        },
        paginatedSessions: {
            enumerable: true,
            configurable: true,
            get() {
                const start = (this.currentPage - 1) * this.pageSize;
                const end = start + this.pageSize;
                return this.filteredSessions.slice(start, end);
            }
        },
        virtualRowHeight: {
            enumerable: true,
            configurable: true,
            get() {
                return this.virtualCardHeight + this.virtualRowGap;
            }
        },
        virtualTotalRows: {
            enumerable: true,
            configurable: true,
            get() {
                return Math.ceil(this.filteredSessions.length / this.virtualColumns);
            }
        },
        virtualStartRow: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualList) return 0;
                const start = Math.floor(this.virtualScrollTop / this.virtualRowHeight) - this.virtualOverscan;
                return Math.max(0, start);
            }
        },
        virtualEndRow: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualList) return this.virtualTotalRows;
                const visibleRows = Math.ceil(this.virtualViewportHeight / this.virtualRowHeight);
                const end = this.virtualStartRow + visibleRows + this.virtualOverscan * 2;
                return Math.min(this.virtualTotalRows, end);
            }
        },
        virtualPaddingTop: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualList) return 0;
                return this.virtualStartRow * this.virtualRowHeight;
            }
        },
        virtualPaddingBottom: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualList) return 0;
                const remainingRows = this.virtualTotalRows - this.virtualEndRow;
                return Math.max(0, remainingRows * this.virtualRowHeight);
            }
        },
        virtualVisibleSessions: {
            enumerable: true,
            configurable: true,
            get() {
                if (!this.useVirtualList) return [];
                const startIndex = this.virtualStartRow * this.virtualColumns;
                const endIndex = this.virtualEndRow * this.virtualColumns;
                return this.filteredSessions.slice(startIndex, endIndex);
            }
        },
        sessionsToRender: {
            enumerable: true,
            configurable: true,
            get() {
                return this.useVirtualList && this.sessionGroupBy === 'none'
                    ? this.virtualVisibleSessions
                    : this.paginatedSessions;
            }
        },
        groupedSessions: {
            enumerable: true,
            configurable: true,
            get() {
                if (this.sessionGroupBy === 'none') {
                    return [];
                }

                const groupsMap = new Map();
                const isOldest = this.sessionSortOrder === 'oldest';

                this.filteredSessions.forEach(session => {
                    let key = 'none';
                    let label = '全部会话';

                    if (this.sessionGroupBy === 'scenario') {
                        const scenarioName = (session.scenario_config?.name || '').trim();
                        key = scenarioName ? `scenario-${scenarioName}` : 'scenario-uncategorized';
                        label = scenarioName || '未分类场景';
                    } else if (this.sessionGroupBy === 'date') {
                        const dateKey = this.getSessionDateKey(session.created_at) || 'unknown-date';
                        key = `date-${dateKey}`;
                        label = this.formatSessionDateGroupLabel(dateKey);
                    } else if (this.sessionGroupBy === 'status') {
                        const status = this.getEffectiveSessionStatus(session) || 'other';
                        key = `status-${status}`;
                        const statusLabelMap = {
                            in_progress: '进行中',
                            pending_review: '待确认',
                            completed: '已完成',
                            paused: '已暂停'
                        };
                        label = statusLabelMap[status] || '其他状态';
                    }

                    const createdAtTs = Number.isFinite(new Date(session.created_at).getTime())
                        ? new Date(session.created_at).getTime()
                        : 0;

                    if (!groupsMap.has(key)) {
                        groupsMap.set(key, {
                            key,
                            label,
                            sessions: [],
                            latestTs: createdAtTs,
                            oldestTs: createdAtTs,
                            statusCounts: {
                                in_progress: 0,
                                pending_review: 0,
                                completed: 0,
                                paused: 0,
                                other: 0
                            }
                        });
                    }

                    const group = groupsMap.get(key);
                    group.sessions.push(session);
                    group.latestTs = Math.max(group.latestTs, createdAtTs);
                    group.oldestTs = Math.min(group.oldestTs, createdAtTs);

                    const status = this.getEffectiveSessionStatus(session);
                    if (status === 'in_progress' || status === 'pending_review' || status === 'completed' || status === 'paused') {
                        group.statusCounts[status] += 1;
                    } else {
                        group.statusCounts.other += 1;
                    }
                });

                const sortByCreatedAt = (a, b) => {
                    const tsA = Number.isFinite(new Date(a.created_at).getTime()) ? new Date(a.created_at).getTime() : 0;
                    const tsB = Number.isFinite(new Date(b.created_at).getTime()) ? new Date(b.created_at).getTime() : 0;
                    return isOldest ? tsA - tsB : tsB - tsA;
                };

                const grouped = Array.from(groupsMap.values());
                grouped.forEach(group => {
                    group.sessions.sort(sortByCreatedAt);
                });

                grouped.sort((a, b) => {
                    if (this.sessionGroupBy === 'status') {
                        const statusOrder = {
                            'status-in_progress': 0,
                            'status-pending_review': 1,
                            'status-completed': 2,
                            'status-paused': 3
                        };
                        const orderA = statusOrder[a.key] ?? 99;
                        const orderB = statusOrder[b.key] ?? 99;
                        if (orderA !== orderB) {
                            return orderA - orderB;
                        }
                        return a.label.localeCompare(b.label, 'zh-Hans');
                    }

                    const anchorA = isOldest ? a.oldestTs : a.latestTs;
                    const anchorB = isOldest ? b.oldestTs : b.latestTs;
                    if (anchorA !== anchorB) {
                        return isOldest ? anchorA - anchorB : anchorB - anchorA;
                    }
                    return a.label.localeCompare(b.label, 'zh-Hans');
                });

                if (this.sessionGroupBy === 'scenario') {
                    const uncategorizedIndex = grouped.findIndex(group => group.key === 'scenario-uncategorized');
                    if (uncategorizedIndex >= 0) {
                        const [uncategorized] = grouped.splice(uncategorizedIndex, 1);
                        grouped.push(uncategorized);
                    }
                }

                return grouped;
            }
        },
        sessionDisplayGroups: {
            enumerable: true,
            configurable: true,
            get() {
                if (this.sessionGroupBy === 'none') {
                    return [{
                        key: 'group-all',
                        label: '',
                        showHeader: false,
                        sessions: this.sessionsToRender,
                        statusCounts: {
                            in_progress: 0,
                            pending_review: 0,
                            completed: 0,
                            paused: 0,
                            other: 0
                        }
                    }];
                }

                return this.groupedSessions.map(group => ({
                    ...group,
                    showHeader: true
                }));
            }
        },
        paginationStart: {
            enumerable: true,
            configurable: true,
            get() {
                if (this.filteredSessions.length === 0) return 0;
                if (this.sessionGroupBy !== 'none') return 1;
                return (this.currentPage - 1) * this.pageSize + 1;
            }
        },
        paginationEnd: {
            enumerable: true,
            configurable: true,
            get() {
                if (this.sessionGroupBy !== 'none') {
                    return this.filteredSessions.length;
                }
                return Math.min(this.currentPage * this.pageSize, this.filteredSessions.length);
            }
        },
        visiblePages: {
            enumerable: true,
            configurable: true,
            get() {
                const pages = [];
                const total = this.totalPages;
                const current = this.currentPage;

                if (total <= 7) {
                    for (let i = 1; i <= total; i += 1) pages.push(i);
                } else if (current <= 3) {
                    pages.push(1, 2, 3, 4, '...', total);
                } else if (current >= total - 2) {
                    pages.push(1, '...', total - 3, total - 2, total - 1, total);
                } else {
                    pages.push(1, '...', current - 1, current, current + 1, '...', total);
                }

                return pages;
            }
        },
    };

    function attach(app) {
        if (!app || typeof app !== 'object') return app;

        Object.entries(sessionListStateDefaults).forEach(([key, value]) => {
            if (typeof app[key] === 'undefined') {
                app[key] = cloneDefaultValue(value);
            }
        });

        Object.assign(app, sessionListStateMethods);
        Object.defineProperties(app, sessionListStateDescriptors);
        return app;
    }

    global.DeepVisionSessionListStateModule = { attach };
})(window);

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

    const reportDetailRuntimeDefaults = {
        generatingReportSessionId: '',
        reportGenerationState: 'idle',
        reportGenerationAction: 'generate',
        reportGenerationSessionId: '',
        reportGenerationRequestStartedAt: 0,
        reportGenerationStatusUpdatedAt: 0,
        reportGenerationTransitionTimer: null,
        reportGenerationResetTimer: null,
        reportGenerationPollInterval: null,
        reportGenerationPollingSessionId: '',
        reportGenerationSmoothTimer: null,
        reportGenerationProgress: 0,
        reportGenerationRawProgress: 0,
        reportGenerationPhaseStartedAt: 0,
        reportGenerationStageIndex: 0,
        reportGenerationTotalStages: 6,
        reportGenerationServerState: 'queued',
        reportGenerationServerMessage: '',
        reportGenerationLastError: '',
        reportGenerationTerminalHandledKey: '',
        generatingSlides: false,
        generatingSlidesReportName: '',
        presentationPolling: false,
        presentationPollInterval: null,
        presentationExecutionId: '',
        presentationPollingReportName: '',
        presentationProgress: 0,
        presentationRawProgress: 0,
        presentationStageIndex: 0,
        presentationTotalStages: 4,
        presentationStageStatus: 'pending',
        presentationState: 'idle',
        presentationPhaseStartedAt: 0,
        presentationSmoothTimer: null,
        presentationPdfUrl: '',
        presentationLocalUrl: '',
        lastPresentationUrl: '',
    };

    const reportDetailRuntimeMethods = {
        startReportGenerationFeedback(action = 'generate') {
            this.clearReportGenerationTransitionTimer();
            this.clearReportGenerationResetTimer();
            this.reportGenerationAction = action === 'regenerate' ? 'regenerate' : 'generate';
            this.reportGenerationSessionId = this.currentSession?.session_id || '';
            this.reportGenerationRequestStartedAt = Date.now();
            this.reportGenerationState = 'submitting';
            this.reportGenerationStatusUpdatedAt = Date.now();
            this.reportGenerationPhaseStartedAt = Date.now();
            this.reportGenerationProgress = 5;
            this.reportGenerationRawProgress = 5;
            this.reportGenerationStageIndex = 0;
            this.reportGenerationTotalStages = 6;
            this.reportGenerationServerState = 'queued';
            this.reportGenerationServerMessage = '';
            this.reportGenerationLastError = '';
            this.reportGenerationTerminalHandledKey = '';

            this.startReportGenerationSmoothing();

            this.reportGenerationTransitionTimer = setTimeout(() => {
                if (this.reportGenerationState === 'submitting') {
                    this.reportGenerationState = 'running';
                    this.reportGenerationStatusUpdatedAt = Date.now();
                    this.reportGenerationProgress = Math.max(this.reportGenerationProgress || 0, 8);
                    this.reportGenerationRawProgress = Math.max(this.reportGenerationRawProgress || 0, 8);
                }
            }, 450);
        },

        finishReportGenerationFeedback(result = 'success', errorMessage = '') {
            this.clearReportGenerationTransitionTimer();
            this.clearReportGenerationResetTimer();
            this.reportGenerationState = result === 'success' ? 'success' : 'error';
            this.reportGenerationStatusUpdatedAt = Date.now();
            this.reportGenerationServerState = result === 'success' ? 'completed' : 'failed';
            this.reportGenerationServerMessage = '';
            this.reportGenerationLastError = result === 'error' ? (errorMessage || '') : '';
            this.reportGenerationProgress = 100;
            this.reportGenerationRawProgress = 100;
            this.stopReportGenerationSmoothing();

            const resetDelay = result === 'success' ? 8000 : 12000;
            this.reportGenerationResetTimer = setTimeout(() => {
                this.resetReportGenerationFeedback();
            }, resetDelay);
        },

        clearReportGenerationTransitionTimer() {
            if (this.reportGenerationTransitionTimer) {
                clearTimeout(this.reportGenerationTransitionTimer);
                this.reportGenerationTransitionTimer = null;
            }
        },

        clearReportGenerationResetTimer() {
            if (this.reportGenerationResetTimer) {
                clearTimeout(this.reportGenerationResetTimer);
                this.reportGenerationResetTimer = null;
            }
        },

        resetReportGenerationFeedback() {
            this.clearReportGenerationTransitionTimer();
            this.clearReportGenerationResetTimer();
            this.stopReportGenerationPolling();
            this.stopReportGenerationSmoothing();
            this.stopWebSearchPolling();
            this.generatingReport = false;
            this.generatingReportSessionId = '';
            this.reportGenerationState = 'idle';
            this.reportGenerationAction = 'generate';
            this.reportGenerationSessionId = '';
            this.reportGenerationRequestStartedAt = 0;
            this.reportGenerationStatusUpdatedAt = 0;
            this.reportGenerationProgress = 0;
            this.reportGenerationRawProgress = 0;
            this.reportGenerationPhaseStartedAt = 0;
            this.reportGenerationStageIndex = 0;
            this.reportGenerationTotalStages = 6;
            this.reportGenerationServerState = 'queued';
            this.reportGenerationServerMessage = '';
            this.reportGenerationLastError = '';
            this.reportGenerationPollingSessionId = '';
            this.reportGenerationTerminalHandledKey = '';
        },

        isReportGenerationProcessing() {
            return this.reportGenerationState === 'submitting' || this.reportGenerationState === 'running';
        },

        applyReportGenerationStatusSnapshot(data, sessionId = '') {
            if (!data || typeof data !== 'object') return;

            const nextSessionId = String(sessionId || this.reportGenerationSessionId || '').trim();
            const state = String(data.state || this.reportGenerationServerState || 'queued').trim() || 'queued';
            const normalizedProgress = Math.max(0, Math.min(100, Number(data.progress) || 0));
            const statusUpdatedAt = this.parseValidTimestamp(data.updated_at) || Date.now();

            if (state !== this.reportGenerationServerState) {
                this.reportGenerationPhaseStartedAt = Date.now();
            }

            this.reportGenerationSessionId = nextSessionId;
            this.reportGenerationServerState = state;
            this.reportGenerationState = state === 'queued' ? 'submitting' : 'running';
            if (typeof data.report_profile === 'string' && data.report_profile.trim()) {
                const profileFromServer = this.normalizeReportProfile(
                    data.report_profile,
                    this.reportProfileDefault || 'balanced'
                );
                if (profileFromServer && this.canUseReportProfile(profileFromServer)) {
                    this.reportProfile = profileFromServer;
                }
            }
            this.reportGenerationRawProgress = Math.max(
                this.reportGenerationRawProgress || 0,
                normalizedProgress
            );
            this.reportGenerationProgress = Math.max(
                this.reportGenerationProgress || 0,
                this.reportGenerationRawProgress
            );
            this.reportGenerationStageIndex = Number.isFinite(Number(data.stage_index))
                ? Number(data.stage_index)
                : this.reportGenerationStageIndex;
            this.reportGenerationTotalStages = Number.isFinite(Number(data.total_stages))
                ? Number(data.total_stages)
                : this.reportGenerationTotalStages;
            this.reportGenerationStatusUpdatedAt = statusUpdatedAt;

            if (data.message) {
                this.reportGenerationServerMessage = data.message;
                if (state !== 'failed') {
                    this.reportGenerationLastError = '';
                }
            }

            const errorText = String(data.error || '').trim();
            if (errorText) {
                this.reportGenerationLastError = errorText;
            }
        },

        async handleReportGenerationTerminalState(sessionId, data = {}) {
            const state = String(data?.state || '').trim();
            if (!sessionId || (state !== 'completed' && state !== 'failed')) {
                return;
            }

            const normalizedSessionId = this.normalizeComparableId(sessionId);

            const terminalKey = [
                normalizedSessionId,
                state,
                data?.updated_at || '',
                data?.report_name || '',
                data?.error || ''
            ].join('|');
            if (terminalKey && this.reportGenerationTerminalHandledKey === terminalKey) {
                return;
            }
            this.reportGenerationTerminalHandledKey = terminalKey;

            const isCurrentSession = normalizedSessionId
                && this.normalizeComparableId(this.currentSession?.session_id) === normalizedSessionId;
            const wasTracking = normalizedSessionId
                && (
                    this.normalizeComparableId(this.generatingReportSessionId) === normalizedSessionId
                    || this.normalizeComparableId(this.reportGenerationSessionId) === normalizedSessionId
                );

            this.generatingReport = false;
            if (this.normalizeComparableId(this.generatingReportSessionId) === normalizedSessionId) {
                this.generatingReportSessionId = '';
            }
            this.stopWebSearchPolling();

            if (state === 'completed') {
                this.finishReportGenerationFeedback('success');
                if (isCurrentSession && this.currentSession) {
                    this.currentSession.status = 'completed';
                }

                await this.loadReports();
                const reportName = String(data?.report_name || '').trim();
                const aiGenerated = data?.ai_generated;
                const aiLabel = aiGenerated === true ? '（AI 生成）' : (aiGenerated === false ? '（模板生成）' : '');
                if (wasTracking) {
                    this.showToast(`访谈报告生成成功 ${aiLabel}`.trim(), 'success');
                }

                if (isCurrentSession) {
                    await this.openGeneratedReportForSession(normalizedSessionId, reportName, { forceReload: true });
                }
                return;
            }

            const message = this.normalizeReportGenerationError({
                message: data?.error || data?.message || '访谈报告生成失败'
            });
            this.finishReportGenerationFeedback('error', message);
            if (wasTracking) {
                this.showToast(message, 'error');
            }
        },

        async restoreReportGenerationState(sessionId) {
            const targetSessionId = String(sessionId || '').trim();
            if (!targetSessionId) return;

            try {
                const data = await this.apiCall(`/status/report-generation/${targetSessionId}`);
                const state = String(data?.state || '').trim();
                const isActive = data?.active === true;
                if (!isActive || (state === 'completed' || state === 'failed')) {
                    return;
                }

                this.clearReportGenerationTransitionTimer();
                this.clearReportGenerationResetTimer();
                this.reportGenerationAction = data?.action === 'regenerate' ? 'regenerate' : 'generate';
                this.reportGenerationRequestStartedAt = this.parseValidTimestamp(data?.started_at) || Date.now();
                this.reportGenerationStatusUpdatedAt = this.parseValidTimestamp(data?.updated_at) || Date.now();
                this.reportGenerationPhaseStartedAt = Date.now();
                this.reportGenerationProgress = Math.max(5, Math.min(99, Number(data?.progress) || 5));
                this.reportGenerationRawProgress = Math.max(5, Math.min(99, Number(data?.progress) || 5));
                this.reportGenerationStageIndex = Number.isFinite(Number(data?.stage_index))
                    ? Number(data.stage_index)
                    : 0;
                this.reportGenerationTotalStages = Number.isFinite(Number(data?.total_stages))
                    ? Number(data.total_stages)
                    : 6;
                this.reportGenerationServerState = state || 'queued';
                this.reportGenerationServerMessage = String(data?.message || '').trim();
                this.reportGenerationLastError = String(data?.error || '').trim();
                this.generatingReport = true;
                this.generatingReportSessionId = targetSessionId;
                this.reportGenerationSessionId = targetSessionId;
                this.reportGenerationState = (state || 'queued') === 'queued' ? 'submitting' : 'running';
                this.startReportGenerationSmoothing();
                this.startReportGenerationPolling(targetSessionId);
                this.startWebSearchPolling();
                this.showToast('检测到报告仍在生成，已自动恢复进度', 'info');
            } catch (error) {
                // 恢复失败不打断会话打开流程
            }
        },

        startReportGenerationPolling(sessionId) {
            this.stopReportGenerationPolling();
            if (!sessionId) return;
            this.reportGenerationPollingSessionId = sessionId;

            const pollInterval = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.api?.reportStatusPollInterval)
                ? SITE_CONFIG.api.reportStatusPollInterval
                : 600;

            let polling = false;
            const pollOnce = async () => {
                if (polling || this.reportGenerationPollingSessionId !== sessionId) return;
                polling = true;
                try {
                    const response = await fetch(`${API_BASE}/status/report-generation/${sessionId}`);
                    if (!response.ok) return;

                    const data = await response.json();
                    if (!data) return;

                    const state = data.state || this.reportGenerationServerState;
                    const statusUpdatedAt = this.parseValidTimestamp(data.updated_at);
                    const requestStartedAt = this.reportGenerationRequestStartedAt || 0;
                    if (statusUpdatedAt && requestStartedAt && statusUpdatedAt + 500 < requestStartedAt) {
                        return;
                    }

                    if (data.active === true) {
                        if (!this.generatingReport || this.generatingReportSessionId !== sessionId) {
                            this.generatingReport = true;
                            this.generatingReportSessionId = sessionId;
                        }
                        this.applyReportGenerationStatusSnapshot(data, sessionId);
                        if (!this.reportGenerationSmoothTimer) {
                            this.startReportGenerationSmoothing();
                        }
                        return;
                    }

                    if (state === 'completed' || state === 'failed') {
                        this.applyReportGenerationStatusSnapshot({
                            ...data,
                            progress: 100
                        }, sessionId);
                        this.stopReportGenerationPolling();
                        await this.handleReportGenerationTerminalState(sessionId, data);
                    }
                } catch (error) {
                    // 轮询失败静默处理
                } finally {
                    polling = false;
                }
            };

            pollOnce();
            this.reportGenerationPollInterval = setInterval(() => {
                pollOnce();
            }, pollInterval);
        },

        stopReportGenerationPolling() {
            if (this.reportGenerationPollInterval) {
                clearInterval(this.reportGenerationPollInterval);
                this.reportGenerationPollInterval = null;
            }
            this.reportGenerationPollingSessionId = '';
        },

        getReportGenerationExpectedDuration(state = '') {
            const phaseDurations = {
                queued: 2500,
                building_prompt: 9000,
                generating: 52000,
                fallback: 18000,
                saving: 5000,
                completed: 0,
                failed: 0
            };
            return phaseDurations[state] || 8000;
        },

        getReportGenerationPhaseTargetProgress(state = '') {
            const phaseTargets = {
                queued: 12,
                building_prompt: 36,
                generating: 86,
                fallback: 90,
                saving: 97,
                completed: 100,
                failed: this.reportGenerationProgress || this.reportGenerationRawProgress || 90
            };
            return Math.max(0, Math.min(100, phaseTargets[state] ?? 90));
        },

        startReportGenerationSmoothing() {
            this.stopReportGenerationSmoothing();

            this.reportGenerationSmoothTimer = setInterval(() => {
                if (!this.isReportGenerationProcessing()) return;

                const now = Date.now();
                const phaseStart = this.reportGenerationPhaseStartedAt || now;
                const elapsed = Math.max(0, now - phaseStart);
                const expected = this.getReportGenerationExpectedDuration(this.reportGenerationServerState);
                const phaseRatio = expected > 0 ? Math.min(1, elapsed / expected) : 1;

                const current = Math.max(0, Math.min(100, this.reportGenerationProgress || 0));
                const backend = Math.max(0, Math.min(100, this.reportGenerationRawProgress || 0));
                const phaseTarget = this.getReportGenerationPhaseTargetProgress(this.reportGenerationServerState);
                const softTarget = Math.max(backend, current, phaseTarget * phaseRatio);
                const hardCeiling = this.reportGenerationServerState === 'saving'
                    ? 99
                    : this.reportGenerationServerState === 'generating'
                        ? 94
                        : 96;
                const cappedTarget = Math.min(hardCeiling, softTarget);

                if (cappedTarget > current + 0.1) {
                    const step = Math.min(1.4, (cappedTarget - current) * 0.22 + 0.2);
                    this.reportGenerationProgress = Math.min(cappedTarget, current + step);
                } else if (backend > current + 0.1) {
                    this.reportGenerationProgress = Math.min(backend, current + 1.8);
                }
            }, 180);
        },

        stopReportGenerationSmoothing() {
            if (this.reportGenerationSmoothTimer) {
                clearInterval(this.reportGenerationSmoothTimer);
                this.reportGenerationSmoothTimer = null;
            }
        },

        isUltraNarrowViewport() {
            if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
                return false;
            }
            return window.matchMedia('(max-width: 420px)').matches;
        },

        getReportGenerationButtonText(defaultAction = 'generate') {
            if (!this.isGeneratingCurrentReport()) {
                return defaultAction === 'regenerate' ? '重新生成访谈报告' : '生成访谈报告';
            }

            if (this.isUltraNarrowViewport()) {
                return `生成中... ${this.getReportGenerationProgressText()}`;
            }

            const activeAction = this.reportGenerationAction || defaultAction;
            return activeAction === 'regenerate'
                ? `正在重新生成... ${this.getReportGenerationProgressText()}`
                : `正在生成... ${this.getReportGenerationProgressText()}`;
        },

        getReportGenerationProgressText() {
            const progress = Math.max(0, Math.min(100, Math.round(this.reportGenerationProgress || 0)));
            return `${progress}%`;
        },

        getReportGenerationButtonProgressStyle() {
            return `width: ${this.getReportGenerationProgressText()};`;
        },

        isRetriableReportGenerationError(error) {
            const message = String(error?.message || '').toLowerCase();
            if (!message) return false;
            return (
                message.includes('failed to fetch')
                || message.includes('networkerror')
                || message.includes('load failed')
                || message.includes('http 502')
                || message.includes('http 503')
                || message.includes('http 504')
            );
        },

        normalizeReportGenerationError(error) {
            const raw = String(error?.detail || error?.message || '').trim();
            if (!raw) return '访谈报告生成失败，请稍后重试';

            const lower = raw.toLowerCase();
            if (
                lower.includes('failed to fetch')
                || lower.includes('networkerror')
                || lower.includes('load failed')
            ) {
                return '网络连接异常，报告生成请求未送达，请确认服务在线后重试';
            }

            if (
                raw.startsWith('HTTP 502')
                || raw.startsWith('HTTP 503')
                || raw.startsWith('HTTP 504')
            ) {
                return '服务暂时不可用（网关或上游超时），请稍后重试';
            }

            return raw;
        },

        async requestGenerateReportWithRetry(sessionId, action = 'generate', maxRetries = 1, options = {}) {
            let lastError = null;
            const hasExplicitProfile = String(options?.reportProfile || '').trim().length > 0;
            const requestedProfile = hasExplicitProfile
                ? this.normalizeReportProfile(options?.reportProfile, this.reportProfileDefault || 'balanced')
                : 'balanced';
            const reportProfile = this.canUseReportProfile(requestedProfile)
                ? requestedProfile
                : 'balanced';
            const sourceReportName = String(options?.sourceReportName || '').trim();
            for (let attempt = 0; attempt <= maxRetries; attempt++) {
                try {
                    return await this.apiCall(`/sessions/${sessionId}/generate-report`, {
                        method: 'POST',
                        body: JSON.stringify({
                            action: action === 'regenerate' ? 'regenerate' : 'generate',
                            report_profile: reportProfile,
                            source_report_name: sourceReportName,
                        })
                    });
                } catch (error) {
                    lastError = error;
                    const canRetry = attempt < maxRetries && this.isRetriableReportGenerationError(error);
                    if (!canRetry) {
                        throw error;
                    }
                    console.warn(`报告生成请求失败，正在自动重试（第 ${attempt + 1} 次）`, error);
                    await new Promise((resolve) => setTimeout(resolve, 700));
                }
            }
            throw lastError || new Error('访谈报告生成失败');
        },

        async generateReport(action = 'generate', options = {}) {
            const sessionId = String(options?.sessionId || this.currentSession?.session_id || '').trim();
            if (!sessionId || this.generatingReport) return;
            if (!sessionId) return;

            this.generatingReport = true;
            this.generatingReportSessionId = sessionId;
            this.startReportGenerationFeedback(action);
            this.startReportGenerationPolling(sessionId);
            this.startWebSearchPolling();

            try {
                const result = await this.requestGenerateReportWithRetry(sessionId, action, 1, options);

                if (result?.success && !result?.processing && result?.report_name) {
                    const aiMsg = result.ai_generated ? '（AI 生成）' : '（模板生成）';
                    this.showToast(`访谈报告生成成功 ${aiMsg}`, 'success');
                    this.finishReportGenerationFeedback('success');
                    this.currentSession.status = 'completed';
                    await this.openGeneratedReportForSession(sessionId, result.report_name, { forceReload: true });
                    this.generatingReport = false;
                    this.generatingReportSessionId = '';
                    this.stopReportGenerationPolling();
                    this.stopWebSearchPolling();
                    return;
                }

                this.applyReportGenerationStatusSnapshot(result, sessionId);
                if (result?.active === false && (result?.state === 'completed' || result?.state === 'failed')) {
                    await this.handleReportGenerationTerminalState(sessionId, result);
                    return;
                }

                if (result?.already_running) {
                    this.showToast('报告正在后台生成，已恢复进度', 'info');
                } else {
                    this.showToast('已提交报告生成任务，刷新或离开后重新进入也会继续', 'success');
                }
            } catch (error) {
                const errorMsg = this.normalizeReportGenerationError(error);
                this.showToast(errorMsg, 'error');
                this.finishReportGenerationFeedback('error', errorMsg);
                this.generatingReport = false;
                this.generatingReportSessionId = '';
                this.stopReportGenerationPolling();
                this.stopWebSearchPolling();
            }
        },

        isGeneratingCurrentReport() {
            if (!this.generatingReport) return false;
            const currentId = this.currentSession?.session_id || '';
            return Boolean(currentId && currentId === this.generatingReportSessionId);
        },

        async viewLatestReportForSession() {
            if (!this.currentSession) return;
            await this.openGeneratedReportForSession(this.currentSession?.session_id || '', '', { forceReload: false });
        },

        async viewReport(filename, options = {}) {
            const targetFilename = String(filename || '').trim();
            if (!targetFilename) return;
            const { forceReload = false } = options;

            const nextMeta = this.buildSelectedReportMeta(targetFilename);
            const canReuseCurrentDetail = (
                !this.selectedReport
                && this.selectedReportMeta?.name === targetFilename
                && !!this.reportContent
                && !this.reportDetailEnhancing
            );
            if (canReuseCurrentDetail) {
                this.selectedReport = targetFilename;
                this.selectedReportMeta = nextMeta;
                await this.fetchPresentationStatus();
                return;
            }
            const cachedReport = forceReload ? null : this.getCachedReportDetail(targetFilename);
            try {
                this.cleanupReportDetailEnhancements();
                this.stopPresentationPolling();
                this.selectedReport = targetFilename;
                this.presentationPdfUrl = '';
                this.presentationLocalUrl = '';
                this.resetPresentationProgressFeedback();
                if (cachedReport) {
                    this.selectedReportMeta = this.cloneSelectedReportMeta(
                        cachedReport.meta?.name ? cachedReport.meta : nextMeta
                    );
                    this.reportDetailModel = this.cloneReportDetailModel(cachedReport.detailModel);
                    this.reportContent = cachedReport.content;
                    this.reportDetailEnhancing = false;
                    this.$nextTick(() => this.scheduleReportDetailEnhancement({ silent: true }));
                    await this.fetchPresentationStatus();
                    return;
                }
                this.selectedReportMeta = nextMeta;
                this.reportContent = '';
                this.reportDetailModel = this.createEmptyReportDetailModel();
                this.reportDetailEnhancing = true;
                const data = await this.apiCall(`/reports/${encodeURIComponent(targetFilename)}`);
                this.selectedReportMeta = this.cloneSelectedReportMeta({
                    ...nextMeta,
                    sessionId: String(data.session_id || nextMeta.sessionId || '').trim(),
                    reportProfile: this.normalizeReportProfile(data.report_profile, nextMeta.reportProfile || 'balanced'),
                    sourceReportName: String(data.source_report_name || nextMeta.sourceReportName || '').trim(),
                    variantLabel: String(
                        data.report_variant_label
                        || nextMeta.variantLabel
                        || (this.normalizeReportProfile(data.report_profile, 'balanced') === 'quality' ? '精审版' : '普通版')
                    ).trim(),
                });
                this.reportContent = data.content;
                this.$nextTick(() => this.scheduleReportDetailEnhancement());
                await this.fetchPresentationStatus();
            } catch (error) {
                this.resetSelectedReportDetail();
                this.showToast('加载报告失败', 'error');
            }
        },

        buildSolutionPageUrl(reportName = '') {
            const targetReport = String(reportName || this.selectedReport || '').trim();
            if (!targetReport) return '';
            const params = new URLSearchParams();
            params.set('report', targetReport);
            params.set('v', '20260317-solution-v63');
            return `solution.html?${params.toString()}`;
        },

        openSolutionPage(reportName = '') {
            if (!this.canViewSolutionPage()) {
                this.showToast(this.getLevelCapabilityDeniedMessage({
                    required_level: { name: '专业版' }
                }), 'warning');
                return;
            }
            const url = this.buildSolutionPageUrl(reportName);
            if (!url) return;
            const opened = this.openUrl(url);
            if (!opened) {
                this.showToast('浏览器拦截了新标签页，请允许后重试', 'warning');
            }
        },

        isSelectedReportQualityVariant() {
            return this.normalizeReportProfile(this.selectedReportMeta?.reportProfile, 'balanced') === 'quality';
        },

        canGenerateQualityVariantForSelectedReport() {
            if (!this.canGenerateQualityReport()) return false;
            const selectedReportName = String(this.selectedReport || this.selectedReportMeta?.name || '').trim();
            if (!selectedReportName) return false;
            if (this.isSelectedReportQualityVariant()) return false;
            const matchedReport = Array.isArray(this.reports)
                ? this.reports.find((item) => String(item?.name || '').trim() === selectedReportName)
                : null;
            const sessionId = String(
                this.selectedReportMeta?.sessionId
                || matchedReport?.session_id
                || ''
            ).trim();
            return !!sessionId;
        },

        async generateQualityReportVariant() {
            if (!this.canGenerateQualityVariantForSelectedReport()) return;
            const sessionId = String(this.selectedReportMeta?.sessionId || '').trim();
            const sourceReportName = String(this.selectedReport || this.selectedReportMeta?.name || '').trim();
            if (!sessionId || !sourceReportName) return;
            await this.generateReport('generate', {
                sessionId,
                reportProfile: 'quality',
                sourceReportName,
            });
        },

        async fetchPresentationStatus() {
            if (!this.canGeneratePresentation()) {
                this.presentationPdfUrl = '';
                this.presentationLocalUrl = '';
                this.resetPresentationProgressFeedback();
                return;
            }
            if (!this.selectedReport) {
                this.presentationPdfUrl = '';
                this.presentationLocalUrl = '';
                this.resetPresentationProgressFeedback();
                return;
            }
            try {
                const status = await this.apiCall(
                    `/reports/${encodeURIComponent(this.selectedReport)}/presentation/status`
                );
                this.presentationPdfUrl = status?.pdf_url || '';
                this.presentationLocalUrl = status?.presentation_local_url || '';
                this.updatePresentationProgressFromResult(status);
                if (status?.stopped) {
                    this.stopPresentationPolling();
                    this.resetPresentationProgressFeedback();
                    this.presentationState = 'stopped';
                    return;
                }
                if (status?.processing && status?.execution_id) {
                    this.startPresentationPolling(status.execution_id, this.selectedReport);
                } else if (status?.pdf_url) {
                    this.presentationProgress = 100;
                    this.presentationRawProgress = 100;
                    this.presentationState = 'completed';
                    this.stopPresentationProgressSmoothing();
                } else {
                    this.resetPresentationProgressFeedback();
                }
            } catch (error) {
                this.presentationPdfUrl = '';
                this.presentationLocalUrl = '';
                this.resetPresentationProgressFeedback();
            }
        },

        getPresentationStageProfiles() {
            return [
                {
                    title: '解析 Markdown 并规划内容结构',
                    expectedMs: 120000,
                    weight: 18,
                    keywords: ['markdown', '解析', '规划', '结构', 'outline']
                },
                {
                    title: '生成 4K 演示文稿图像',
                    expectedMs: 300000,
                    weight: 34,
                    keywords: ['4k', '演示', '文稿', '图像', 'slide', 'presentation']
                },
                {
                    title: '生成 4K 信息图',
                    expectedMs: 260000,
                    weight: 33,
                    keywords: ['4k', '信息图', 'infographic', '图表']
                },
                {
                    title: '整合为 PDF 并生成下载链接',
                    expectedMs: 90000,
                    weight: 15,
                    keywords: ['pdf', '下载', '链接', '整合', 'export']
                }
            ];
        },

        normalizeReflyStageStatus(rawStatus) {
            const text = String(rawStatus || '').trim().toLowerCase();
            if (!text) return 'pending';
            if (['finish', 'finished', 'completed', 'success', 'succeeded', 'done'].some((key) => text.includes(key))) {
                return 'finished';
            }
            if (['fail', 'failed', 'error', 'cancelled', 'canceled', 'aborted', 'stopped'].some((key) => text.includes(key))) {
                return 'failed';
            }
            if (['executing', 'running', 'processing', 'in_progress', 'working'].some((key) => text.includes(key))) {
                return 'running';
            }
            return 'pending';
        },

        matchPresentationStageIndex(title, fallbackIndex = -1) {
            const profiles = this.getPresentationStageProfiles();
            const normalizedTitle = String(title || '').trim().toLowerCase();
            let bestIndex = -1;
            let bestScore = 0;

            profiles.forEach((profile, index) => {
                const score = (profile.keywords || []).reduce((sum, keyword) => {
                    const token = String(keyword || '').trim().toLowerCase();
                    return token && normalizedTitle.includes(token) ? sum + 1 : sum;
                }, 0);

                if (score > bestScore) {
                    bestScore = score;
                    bestIndex = index;
                }
            });

            if (bestIndex >= 0) return bestIndex;
            if (fallbackIndex >= 0 && fallbackIndex < profiles.length) return fallbackIndex;
            return -1;
        },

        getPresentationNodeElapsedMs(startTime, endTime) {
            const startTs = this.parseValidTimestamp(startTime);
            if (!startTs) return 0;
            const endTs = this.parseValidTimestamp(endTime);
            const anchor = endTs || Date.now();
            return Math.max(0, anchor - startTs);
        },

        getPresentationStageBaseProgress(stageIndex = 0) {
            const profiles = this.getPresentationStageProfiles();
            const index = Math.max(0, Math.min(profiles.length, Number(stageIndex) || 0));
            let base = 0;
            for (let i = 0; i < index; i += 1) {
                base += profiles[i]?.weight || 0;
            }
            return base;
        },

        getPresentationStageWeight(stageIndex = 0) {
            const profiles = this.getPresentationStageProfiles();
            const profile = profiles[Math.max(0, Math.min(profiles.length - 1, Number(stageIndex) || 0))];
            return profile?.weight || 0;
        },

        getPresentationStageExpectedDuration(stageIndex = 0) {
            const profiles = this.getPresentationStageProfiles();
            const profile = profiles[Math.max(0, Math.min(profiles.length - 1, Number(stageIndex) || 0))];
            return profile?.expectedMs || 120000;
        },

        estimatePresentationProgressFromRefly(result) {
            const profiles = this.getPresentationStageProfiles();
            const totalStages = profiles.length;
            if (totalStages === 0) {
                return {
                    progress: result?.pdf_url ? 100 : 0,
                    stageIndex: 0,
                    totalStages: 0,
                    stageStatus: result?.pdf_url ? 'finished' : 'pending',
                    state: result?.pdf_url ? 'completed' : (result?.processing ? 'executing' : 'idle')
                };
            }

            if (result?.pdf_url) {
                return {
                    progress: 100,
                    stageIndex: totalStages - 1,
                    totalStages,
                    stageStatus: 'finished',
                    state: 'completed'
                };
            }

            const stageData = profiles.map((profile, index) => ({
                index,
                title: profile.title,
                status: 'pending',
                progress: 0,
                weight: profile.weight,
                expectedMs: profile.expectedMs
            }));

            const outputs = Array.isArray(result?.refly_response?.data?.output)
                ? result.refly_response.data.output
                : Array.isArray(result?.refly_response?.output)
                    ? result.refly_response.output
                    : [];

            const getPriority = (status) => {
                if (status === 'finished') return 4;
                if (status === 'failed') return 3;
                if (status === 'running') return 2;
                return 1;
            };

            outputs.forEach((node, nodeIndex) => {
                if (!node || typeof node !== 'object') return;
                const stageIndex = this.matchPresentationStageIndex(node.title || node.name || '', nodeIndex);
                if (stageIndex < 0 || stageIndex >= totalStages) return;

                const status = this.normalizeReflyStageStatus(node.status);
                const elapsedMs = this.getPresentationNodeElapsedMs(node.startTime, node.endTime);
                const expectedMs = stageData[stageIndex].expectedMs || 1;
                let stageProgress = 0;
                if (status === 'finished') {
                    stageProgress = 100;
                } else if (status === 'running') {
                    const ratio = elapsedMs > 0 ? elapsedMs / expectedMs : 0;
                    stageProgress = Math.min(92, Math.max(12, Math.round(ratio * 100)));
                } else if (status === 'failed') {
                    const ratio = elapsedMs > 0 ? elapsedMs / expectedMs : 0;
                    stageProgress = Math.min(96, Math.max(25, Math.round(ratio * 100) || 60));
                }

                const current = stageData[stageIndex];
                const shouldReplace = getPriority(status) > getPriority(current.status)
                    || (status === current.status && stageProgress >= current.progress);

                if (shouldReplace) {
                    current.status = status;
                    current.progress = Math.max(0, Math.min(100, stageProgress));
                    current.title = node.title || current.title;
                }
            });

            const totalWeight = stageData.reduce((sum, stage) => sum + (stage.weight || 0), 0) || 100;
            const weighted = stageData.reduce((sum, stage) => {
                return sum + ((stage.progress || 0) / 100) * (stage.weight || 0);
            }, 0);

            let progress = Math.round((weighted / totalWeight) * 100);

            const workflowStatus = String(
                result?.refly_status?.status
                || result?.refly_status?.data?.status
                || ''
            ).trim().toLowerCase();
            const workflowState = this.normalizeReflyStageStatus(workflowStatus);
            const isProcessing = Boolean(result?.processing);

            if (isProcessing && progress < 5) {
                progress = 5;
            }
            if (workflowState === 'finished' && progress < 96) {
                progress = 96;
            }
            if (isProcessing) {
                progress = Math.min(99, progress);
            }

            const runningStage = stageData.find((stage) => stage.status === 'running');
            const pendingStage = stageData.find((stage) => stage.status === 'pending');
            const failedStage = stageData.find((stage) => stage.status === 'failed');
            const finishedStages = stageData.filter((stage) => stage.status === 'finished');

            let stageIndex = 0;
            let stageStatus = 'pending';
            if (failedStage) {
                stageIndex = failedStage.index;
                stageStatus = 'failed';
            } else if (runningStage) {
                stageIndex = runningStage.index;
                stageStatus = 'running';
            } else if (pendingStage) {
                stageIndex = pendingStage.index;
                stageStatus = 'pending';
            } else if (finishedStages.length > 0) {
                stageIndex = Math.min(totalStages - 1, finishedStages[finishedStages.length - 1].index);
                stageStatus = 'finished';
            }

            return {
                progress: Math.max(0, Math.min(100, progress)),
                stageIndex,
                totalStages,
                stageStatus,
                state: workflowStatus || (isProcessing ? 'executing' : 'idle')
            };
        },

        isPresentationRunningForReport(reportName = '') {
            const normalizedReportName = String(reportName || '').trim();
            if (!normalizedReportName) {
                return false;
            }
            if (this.generatingSlides && this.generatingSlidesReportName === normalizedReportName) {
                return true;
            }
            if (this.presentationPolling && this.presentationPollingReportName === normalizedReportName) {
                return true;
            }
            return false;
        },

        isPresentationGeneratingCurrentReport() {
            return this.isPresentationRunningForReport(this.selectedReport);
        },

        updatePresentationProgressFromResult(result) {
            const estimate = this.estimatePresentationProgressFromRefly(result || {});
            const isRunning = this.isPresentationGeneratingCurrentReport();
            const nextStageIndex = Math.max(0, Math.min((estimate.totalStages || 1) - 1, Number(estimate.stageIndex) || 0));
            const stageChanged = nextStageIndex !== this.presentationStageIndex || estimate.stageStatus !== this.presentationStageStatus;

            this.presentationTotalStages = estimate.totalStages || this.presentationTotalStages || 4;
            this.presentationStageIndex = nextStageIndex;
            this.presentationStageStatus = estimate.stageStatus || this.presentationStageStatus || 'pending';
            this.presentationState = estimate.state || this.presentationState || 'idle';

            if (stageChanged || !this.presentationPhaseStartedAt) {
                this.presentationPhaseStartedAt = Date.now();
            }

            if (result?.pdf_url) {
                this.presentationRawProgress = 100;
                this.presentationProgress = 100;
                this.presentationState = 'completed';
                this.presentationStageStatus = 'finished';
                this.stopPresentationProgressSmoothing();
                return;
            }

            if (!isRunning) {
                return;
            }

            if (isRunning) {
                this.presentationRawProgress = Math.max(
                    this.presentationRawProgress || 0,
                    estimate.progress || 0,
                    5
                );
                this.presentationProgress = Math.max(
                    this.presentationProgress || 0,
                    this.presentationRawProgress || 0
                );
            } else {
                this.presentationRawProgress = estimate.progress || 0;
                this.presentationProgress = estimate.progress || 0;
            }

            if (estimate.progress >= 100) {
                this.presentationRawProgress = 100;
                this.presentationProgress = 100;
                this.presentationState = 'completed';
                this.presentationStageStatus = 'finished';
                this.stopPresentationProgressSmoothing();
            }
        },

        startPresentationProgressSmoothing() {
            this.stopPresentationProgressSmoothing();
            this.presentationSmoothTimer = setInterval(() => {
                const active = this.isPresentationGeneratingCurrentReport();
                if (!active) return;
                if (this.presentationState === 'completed' || this.presentationState === 'failed' || this.presentationState === 'stopped') {
                    return;
                }

                const now = Date.now();
                const phaseStart = this.presentationPhaseStartedAt || now;
                const elapsed = Math.max(0, now - phaseStart);
                const expected = this.getPresentationStageExpectedDuration(this.presentationStageIndex);
                const phaseRatio = expected > 0 ? Math.min(1, elapsed / expected) : 1;
                const base = this.getPresentationStageBaseProgress(this.presentationStageIndex);
                const weight = this.getPresentationStageWeight(this.presentationStageIndex);
                const phaseTarget = Math.min(99, base + weight * phaseRatio);

                const current = Math.max(0, Math.min(100, this.presentationProgress || 0));
                const backend = Math.max(0, Math.min(100, this.presentationRawProgress || 0));
                const softTarget = Math.max(current, backend, phaseTarget);
                const cappedTarget = Math.min(99, softTarget);

                if (cappedTarget > current + 0.1) {
                    const step = Math.min(1.2, (cappedTarget - current) * 0.22 + 0.18);
                    this.presentationProgress = Math.min(cappedTarget, current + step);
                } else if (backend > current + 0.1) {
                    this.presentationProgress = Math.min(backend, current + 1.4);
                }
            }, 180);
        },

        stopPresentationProgressSmoothing() {
            if (this.presentationSmoothTimer) {
                clearInterval(this.presentationSmoothTimer);
                this.presentationSmoothTimer = null;
            }
        },

        resetPresentationProgressFeedback() {
            this.stopPresentationProgressSmoothing();
            this.presentationProgress = 0;
            this.presentationRawProgress = 0;
            this.presentationStageIndex = 0;
            this.presentationTotalStages = 4;
            this.presentationStageStatus = 'pending';
            this.presentationState = 'idle';
            this.presentationPhaseStartedAt = 0;
        },

        getPresentationGenerationButtonProgressText() {
            const progress = Math.max(0, Math.min(100, Math.round(this.presentationProgress || 0)));
            return `${progress}%`;
        },

        getPresentationGenerationButtonProgressStyle() {
            return `width: ${this.getPresentationGenerationButtonProgressText()};`;
        },

        getPresentationGenerationButtonText() {
            if (!this.isPresentationGeneratingCurrentReport()) {
                return '生成演示文稿';
            }
            return `正在生成演示文稿...${this.getPresentationGenerationButtonProgressText()}（点击停止）`;
        },

        openPresentationPdf() {
            if (!this.canGeneratePresentation()) {
                this.showToast(this.getLevelCapabilityDeniedMessage({
                    required_level: { name: '专业版' }
                }), 'warning');
                return;
            }
            if (!this.presentationPdfUrl) {
                this.showToast('未找到可用的演示文稿链接', 'warning');
                return;
            }
            const localLink = `/api/reports/${encodeURIComponent(this.selectedReport)}/presentation/link`;
            const opened = this.openUrl(localLink);
            if (!opened) {
                this.showToast('已生成演示文稿，点击查看', 'success', {
                    actionLabel: '查看',
                    actionUrl: localLink,
                    duration: 7000
                });
            }
        },

        startPresentationPolling(executionId, reportName = '') {
            if (!executionId) return;
            const targetReportName = (reportName || this.selectedReport || '').trim();
            if (!targetReportName) return;
            if (
                this.presentationPolling
                && this.presentationExecutionId === executionId
                && this.presentationPollingReportName === targetReportName
            ) {
                return;
            }
            this.stopPresentationPolling();
            this.presentationPolling = true;
            this.presentationExecutionId = executionId;
            this.presentationPollingReportName = targetReportName;
            this.presentationState = 'executing';
            this.presentationPhaseStartedAt = this.presentationPhaseStartedAt || Date.now();
            this.presentationRawProgress = Math.max(this.presentationRawProgress || 0, 5);
            this.presentationProgress = Math.max(this.presentationProgress || 0, 5);
            this.startPresentationProgressSmoothing();
            let attempts = 0;
            const maxAttempts = 200;
            let timeoutNotified = false;
            const currentExecutionId = executionId;
            const currentReportName = targetReportName;

            const pollOnce = async () => {
                if (
                    !this.presentationPolling
                    || this.presentationExecutionId !== currentExecutionId
                    || this.presentationPollingReportName !== currentReportName
                ) {
                    return;
                }
                attempts += 1;
                try {
                    const result = await this.apiCall(
                        `/reports/${encodeURIComponent(currentReportName)}/refly/status?execution_id=${encodeURIComponent(currentExecutionId)}`
                    );
                    if (
                        !this.presentationPolling
                        || this.presentationExecutionId !== currentExecutionId
                        || this.presentationPollingReportName !== currentReportName
                    ) {
                        return;
                    }
                    if (result?.mismatch) {
                        this.stopPresentationPolling();
                        if (this.selectedReport === currentReportName) {
                            this.resetPresentationProgressFeedback();
                            this.showToast('检测到生成任务不属于当前报告，已停止自动轮询', 'warning');
                        }
                        return;
                    }
                    if (result?.stopped) {
                        this.stopPresentationPolling();
                        this.generatingSlides = false;
                        this.generatingSlidesReportName = '';
                        if (this.selectedReport === currentReportName) {
                            this.resetPresentationProgressFeedback();
                            this.presentationState = 'stopped';
                            this.showToast('演示文稿生成已停止', 'warning');
                        }
                        return;
                    }
                    this.updatePresentationProgressFromResult(result);
                    if (result?.pdf_url) {
                        this.presentationPdfUrl = result.pdf_url;
                        this.presentationState = 'completed';
                        this.presentationRawProgress = 100;
                        this.presentationProgress = 100;
                        this.stopPresentationPolling();
                        const localLink = `/api/reports/${encodeURIComponent(currentReportName)}/presentation/link`;
                        this.showToast('演示文稿已生成，点击查看', 'success', {
                            actionLabel: '查看',
                            actionUrl: localLink,
                            duration: 7000
                        });
                    } else if (attempts >= maxAttempts && !timeoutNotified) {
                        timeoutNotified = true;
                        this.showToast('演示文稿仍在生成中，请稍后再试', 'warning');
                    }
                } catch (error) {
                    // 忽略短暂错误，继续轮询
                }
            };

            pollOnce();
            this.presentationPollInterval = setInterval(pollOnce, 6000);
        },

        stopPresentationPolling() {
            if (this.presentationPollInterval) {
                clearInterval(this.presentationPollInterval);
                this.presentationPollInterval = null;
            }
            this.presentationPolling = false;
            this.presentationExecutionId = '';
            this.presentationPollingReportName = '';
            this.stopPresentationProgressSmoothing();
            this.presentationProgress = 0;
            this.presentationRawProgress = 0;
            this.presentationStageIndex = 0;
            this.presentationStageStatus = 'pending';
            this.presentationPhaseStartedAt = 0;
        },

        async stopPresentationGeneration() {
            const targetReportName = (this.presentationPollingReportName || this.selectedReport || '').trim();
            if (!targetReportName) return;
            const confirmed = await this.openActionConfirmDialog({
                title: '确认停止生成',
                message: '确定停止本次演示文稿生成？可稍后重新生成。',
                tone: 'warning',
                confirmText: '停止生成',
                cancelText: '取消'
            });
            if (!confirmed) return;
            try {
                const execParam = this.presentationExecutionId
                    ? `?execution_id=${encodeURIComponent(this.presentationExecutionId)}`
                    : '';
                await this.apiCall(
                    `/reports/${encodeURIComponent(targetReportName)}/presentation/abort${execParam}`,
                    { method: 'POST' }
                );
                this.stopPresentationPolling();
                this.generatingSlides = false;
                this.generatingSlidesReportName = '';
                this.presentationExecutionId = '';
                this.presentationState = 'stopped';
                this.presentationProgress = 0;
                this.presentationRawProgress = 0;
                this.presentationStageIndex = 0;
                this.presentationStageStatus = 'pending';
                this.presentationPhaseStartedAt = 0;
                this.showToast('已停止生成', 'success');
            } catch (error) {
                this.showToast('停止失败，请稍后重试', 'error');
            }
        },

        openUrl(url) {
            if (!url) return false;
            const win = window.open(url, '_blank');
            if (win) {
                try {
                    win.opener = null;
                } catch (error) {
                    // 忽略跨窗口安全限制，避免影响打开流程
                }
                try {
                    win.focus();
                } catch (error) {
                    // 某些浏览器不允许脚本主动聚焦新标签页
                }
                return true;
            }
            return false;
        },

        collectReflyUrls(payload, urls = []) {
            if (!payload) return urls;
            if (typeof payload === 'string') {
                if (payload.startsWith('http')) urls.push(payload);
                return urls;
            }
            if (Array.isArray(payload)) {
                payload.forEach((item) => this.collectReflyUrls(item, urls));
                return urls;
            }
            if (typeof payload === 'object') {
                Object.values(payload).forEach((value) => this.collectReflyUrls(value, urls));
            }
            return urls;
        },

        getReflyFileCandidates(result) {
            const files = result?.refly_response?.data?.files
                || result?.refly_response?.files
                || [];
            if (!Array.isArray(files)) return [];
            return files
                .map((file) => ({
                    url: file?.url,
                    name: file?.name || ''
                }))
                .filter((item) => typeof item.url === 'string' && item.url.startsWith('http'));
        },

        scoreReflyUrl(url, name = '') {
            const lowerUrl = (url || '').toLowerCase();
            const lowerName = (name || '').toLowerCase();
            const target = lowerName || lowerUrl;
            const extMatch = target.match(/\.[a-z0-9]+(?=$|\?)/);
            const ext = extMatch ? extMatch[0] : '';
            let score = 0;

            if (lowerUrl.includes('share') || lowerUrl.includes('preview') || lowerUrl.includes('presentation')) {
                score += 80;
            }
            if (lowerUrl.includes('slide')) score += 10;

            switch (ext) {
                case '.pptx':
                    score += 100;
                    break;
                case '.pdf':
                    score += 90;
                    break;
                case '.ppt':
                case '.key':
                    score += 80;
                    break;
                case '.html':
                case '.htm':
                    score += 70;
                    break;
                case '.png':
                case '.jpg':
                case '.jpeg':
                    score += 50;
                    break;
                case '.json':
                    score -= 10;
                    break;
                default:
                    break;
            }

            return score;
        },

        getBestReflyUrl(result) {
            const candidates = [];
            const addCandidate = (url, name = '') => {
                if (!url || typeof url !== 'string' || !url.startsWith('http')) return;
                candidates.push({ url, name });
            };

            const presentationUrl = result?.presentation_url;
            if (presentationUrl && typeof presentationUrl === 'string' && presentationUrl.startsWith('http')) {
                const lower = presentationUrl.toLowerCase();
                if (!lower.endsWith('.json')) {
                    return presentationUrl;
                }
                addCandidate(presentationUrl, 'presentation_url');
            }
            this.getReflyFileCandidates(result).forEach((item) => addCandidate(item.url, item.name));

            const extraUrls = this.collectReflyUrls(result?.refly_response, []);
            extraUrls.forEach((url) => addCandidate(url));

            const deduped = Array.from(new Map(candidates.map((item) => [item.url, item])).values());
            if (deduped.length === 0) return presentationUrl || '';

            deduped.sort((a, b) => this.scoreReflyUrl(b.url, b.name) - this.scoreReflyUrl(a.url, a.name));
            return deduped[0].url;
        },

        async generatePresentation() {
            const targetReportName = String(this.selectedReport || '').trim();
            if (!targetReportName) return;
            if (!this.canGeneratePresentation()) {
                this.showToast(this.getLevelCapabilityDeniedMessage({
                    required_level: { name: '专业版' }
                }), 'warning');
                return;
            }
            if (this.isPresentationGeneratingCurrentReport()) return;
            if (this.generatingSlides) {
                this.showToast('正在提交演示文稿生成任务，请稍候', 'warning');
                return;
            }

            this.generatingSlides = true;
            this.generatingSlidesReportName = targetReportName;
            if (
                this.presentationPolling
                && this.presentationPollingReportName
                && this.presentationPollingReportName !== targetReportName
            ) {
                this.stopPresentationPolling();
            }
            this.presentationPdfUrl = '';
            this.presentationExecutionId = '';
            this.presentationPolling = false;
            this.presentationState = 'submitting';
            this.presentationStageIndex = 0;
            this.presentationStageStatus = 'pending';
            this.presentationTotalStages = this.getPresentationStageProfiles().length || 4;
            this.presentationPhaseStartedAt = Date.now();
            this.presentationProgress = 5;
            this.presentationRawProgress = 5;
            this.startPresentationProgressSmoothing();
            try {
                const result = await this.apiCall(
                    `/reports/${encodeURIComponent(targetReportName)}/refly`,
                    { method: 'POST' }
                );
                const requestStillActive = this.generatingSlidesReportName === targetReportName
                    || this.presentationPollingReportName === targetReportName;
                if (!requestStillActive) {
                    return;
                }
                if (this.selectedReport === targetReportName) {
                    this.updatePresentationProgressFromResult(result);
                }
                if (result?.stopped) {
                    this.stopPresentationPolling();
                    if (this.selectedReport === targetReportName) {
                        this.resetPresentationProgressFeedback();
                        this.presentationState = 'stopped';
                    }
                    this.showToast('演示文稿生成已停止', 'warning');
                    return;
                }
                if (result?.processing) {
                    this.showToast('演示文稿生成中，将自动刷新', 'warning');
                    if (result?.execution_id) {
                        this.startPresentationPolling(result.execution_id, targetReportName);
                    }
                    return;
                }

                this.stopPresentationProgressSmoothing();
                const downloadPath = result?.download_path || result?.downloaded_path;
                const hasDownload = Boolean(downloadPath || result?.download_filename);
                const localUrl = result?.presentation_local_url;
                const pdfUrl = result?.pdf_url || '';
                if (pdfUrl) {
                    if (this.selectedReport === targetReportName) {
                        this.presentationPdfUrl = pdfUrl;
                        this.presentationState = 'completed';
                        this.presentationProgress = 100;
                        this.presentationRawProgress = 100;
                    }
                    this.lastPresentationUrl = pdfUrl;
                    const localLink = `/api/reports/${encodeURIComponent(targetReportName)}/presentation/link`;
                    const opened = this.selectedReport === targetReportName ? this.openUrl(localLink) : false;
                    const message = opened ? '演示文稿已生成，已在新窗口打开' : '演示文稿已生成，点击打开';
                    this.showToast(message, 'success', {
                        actionLabel: '打开',
                        actionUrl: localLink,
                        duration: 7000
                    });
                } else if (localUrl) {
                    if (this.selectedReport === targetReportName) {
                        this.presentationLocalUrl = localUrl;
                    }
                    this.lastPresentationUrl = localUrl;
                    const opened = this.selectedReport === targetReportName ? this.openUrl(localUrl) : false;
                    const baseMessage = hasDownload
                        ? '演示文稿已生成，已保存到下载文件夹'
                        : '演示文稿已生成';
                    const message = opened ? `${baseMessage}，点击可再次打开` : `${baseMessage}，点击打开`;
                    this.showToast(message, 'success', {
                        actionLabel: '打开',
                        actionUrl: localUrl,
                        duration: 7000
                    });
                } else if (hasDownload) {
                    this.showToast('演示文稿已生成，已保存到下载文件夹', 'success');
                } else {
                    this.showToast('已提交生成任务，正在生成演示文稿', 'success');
                }
            } catch (error) {
                const requestStillActive = this.generatingSlidesReportName === targetReportName
                    || this.presentationPollingReportName === targetReportName;
                if (!requestStillActive) {
                    return;
                }
                const rawMessage = error.message || '请求失败';
                const lower = rawMessage.toLowerCase();
                let message = `生成演示文稿失败：${rawMessage}`;
                if (lower.includes('timeout') || lower.includes('timed out') || lower.includes('ssl') || lower.includes('httpsconnectionpool')) {
                    message = '生成演示文稿超时，请稍后重试';
                }
                this.presentationState = 'failed';
                this.stopPresentationProgressSmoothing();
                this.showToast(message, 'error');
            } finally {
                if (this.generatingSlidesReportName === targetReportName) {
                    this.generatingSlides = false;
                    this.generatingSlidesReportName = '';
                }
            }
        },

        injectReportSummaryAndToc(reportElement) {
            if (!reportElement) return;

            this.removeReportInjectedArtifacts(reportElement);
            this.stripLegacyReportQualitySection(reportElement);

            const sections = this.collectReportSections(reportElement);
            if (sections.length === 0) {
                this.reportDetailModel = {
                    ...this.createEmptyReportDetailModel(),
                    summaryText: '当前报告已按原始 Markdown 展示，可继续使用顶部操作完成导出与分享。'
                };
                this.enhanceAppendixToggle(reportElement);
                return;
            }

            const navItems = this.buildReportDetailNavItems(sections);
            this.reportDetailModel = this.buildReportDetailModel(reportElement, sections, navItems);
            this.reportDetailSectionRegistry = navItems.map(item => ({
                id: item.id,
                title: item.title,
                breadcrumbLabel: item.breadcrumbLabel || item.title,
                indexLabel: item.indexLabel,
                isAppendix: item.isAppendix,
                depth: item.depth || 0,
                topLevelId: item.topLevelId || item.id,
                charCount: item.charCount || 0,
                startChars: item.startChars || 0,
                element: item.element
            }));
            this.setupReportSectionObserver();
            this.enhanceAppendixToggle(reportElement);
        },

        removeReportInjectedArtifacts(reportElement) {
            if (!reportElement) return;
            reportElement.querySelectorAll('#report-summary-block, #report-toc-block, .dv-report-inline-toc, .dv-appendix-export-wrap')
                .forEach(node => node.remove());
            reportElement.querySelectorAll('.dv-appendix-heading')
                .forEach(node => node.classList.remove('dv-appendix-heading'));
        },

        stripLegacyReportQualitySection(reportElement) {
            const headingsForQuality = Array.from(reportElement.querySelectorAll('h2, h3'));
            headingsForQuality.forEach(heading => {
                const text = this.cleanReportText(heading.textContent || '');
                if (text !== '报告质量指标') return;

                let cursor = heading.nextElementSibling;
                while (cursor) {
                    if (/^H[23]$/i.test(cursor.tagName)) break;
                    const next = cursor.nextElementSibling;
                    cursor.remove();
                    cursor = next;
                }
                heading.remove();
            });
        },

        cleanReportText(value) {
            return String(value || '')
                .replace(/\s+/g, ' ')
                .trim();
        },

        normalizeReportHeadingLabel(value) {
            const raw = this.cleanReportText(value);
            if (!raw) return '';

            const normalized = raw
                .replace(/^第\s*0*\d+\s*[章节部分]\s*/i, '')
                .replace(/^\d+(?:\.\d+)*\s*[、.．]\s*/u, '')
                .replace(/^\d+(?:\.\d+)*\s+/u, '')
                .replace(/^[（(]\d+[)）]\s*/u, '')
                .trim();

            return normalized || raw;
        },

        normalizeReportHeadingKey(value) {
            return this.normalizeReportHeadingLabel(value)
                .toLowerCase()
                .replace(/[\s:：、,，.．\-_/（）()\[\]【】]+/g, '');
        },

        extractReadableChars(value) {
            return this.cleanReportText(value).replace(/\s+/g, '').length;
        },

        extractReportNodesText(nodes = []) {
            return nodes
                .map(node => this.cleanReportText(node?.textContent || ''))
                .filter(Boolean)
                .join(' ');
        },

        collectReportSections(reportElement) {
            const headings = Array.from(reportElement.querySelectorAll('h2'));
            if (headings.length === 0) return [];

            let visibleIndex = 0;
            let accumulatedChars = 0;

            return headings.map((heading, index) => {
                const rawTitle = this.cleanReportText(heading.textContent || '');
                const normalizedTitle = this.normalizeReportHeadingLabel(rawTitle) || rawTitle || `章节 ${index + 1}`;
                const normalizedKey = this.normalizeReportHeadingKey(normalizedTitle);
                const isAppendix = normalizedKey.includes('附录');
                if (!isAppendix) {
                    visibleIndex += 1;
                }

                const sectionId = `report-section-${index + 1}`;
                heading.id = sectionId;
                heading.setAttribute('tabindex', '-1');
                heading.classList.add('dv-report-section-heading');
                heading.classList.toggle('is-appendix', isAppendix);

                const nextHeading = headings[index + 1] || null;
                const nodes = [];
                let cursor = heading.nextElementSibling;
                while (cursor && cursor !== nextHeading) {
                    nodes.push(cursor);
                    cursor = cursor.nextElementSibling;
                }

                const children = [];
                let childIndex = 0;
                const childCounters = [];
                const ancestorIds = [];
                const ancestorTitles = [];
                nodes.forEach(node => {
                    const tagName = String(node?.tagName || '').toUpperCase();
                    if (!/^H[3-6]$/.test(tagName)) return;

                    const level = Number(tagName.slice(1));
                    const depth = Math.max(1, level - 2);
                    childIndex += 1;
                    const childId = `${sectionId}-sub-${childIndex}`;
                    node.id = childId;
                    node.setAttribute('tabindex', '-1');
                    node.classList.add('dv-report-subheading');
                    const childTitle = this.normalizeReportHeadingLabel(node.textContent || '') || `小节 ${childIndex}`;
                    childCounters.length = depth;
                    ancestorIds.length = Math.max(depth - 1, 0);
                    ancestorTitles.length = Math.max(depth - 1, 0);
                    childCounters[depth - 1] = (childCounters[depth - 1] || 0) + 1;

                    const parentId = depth === 1
                        ? sectionId
                        : (ancestorIds[depth - 2] || sectionId);
                    const indexParts = isAppendix
                        ? ['附录', ...childCounters.slice(0, depth).map(value => String(value))]
                        : [String(visibleIndex), ...childCounters.slice(0, depth).map(value => String(value))];
                    const breadcrumbParts = [normalizedTitle, ...ancestorTitles, childTitle]
                        .map(part => this.cleanReportText(part))
                        .filter(Boolean);

                    children.push({
                        id: childId,
                        title: childTitle,
                        indexLabel: indexParts.join('.'),
                        depth,
                        level,
                        parentId,
                        topLevelId: sectionId,
                        element: node,
                        breadcrumbLabel: breadcrumbParts.join(' / ')
                    });

                    ancestorIds[depth - 1] = childId;
                    ancestorTitles[depth - 1] = childTitle;
                });

                const textContent = this.extractReportNodesText(nodes);
                const charCount = Math.max(this.extractReadableChars(textContent), children.length > 0 ? children.length * 18 : 48);
                const startChars = accumulatedChars;
                if (!isAppendix) {
                    accumulatedChars += charCount;
                }

                return {
                    id: sectionId,
                    element: heading,
                    title: isAppendix ? '附录：原始记录' : normalizedTitle,
                    rawTitle,
                    key: normalizedKey,
                    indexLabel: isAppendix ? '附录' : String(visibleIndex),
                    children,
                    nodes,
                    charCount,
                    startChars,
                    isAppendix
                };
            });
        },

        buildReportDetailNavItems(sections = []) {
            return sections.flatMap(section => {
                const topItem = {
                    id: section.id,
                    title: section.title,
                    breadcrumbLabel: section.title,
                    indexLabel: section.indexLabel,
                    isAppendix: section.isAppendix,
                    depth: 0,
                    topLevelId: section.id,
                    charCount: section.charCount,
                    startChars: section.startChars,
                    element: section.element
                };

                const childItems = Array.isArray(section.children)
                    ? section.children.map(child => ({
                        ...child,
                        isAppendix: section.isAppendix || child.isAppendix === true,
                        topLevelId: child.topLevelId || section.id
                    }))
                    : [];

                return [topItem, ...childItems];
            });
        },

        findReportSectionByKeywords(sections = [], keywords = []) {
            const normalizedKeywords = keywords
                .map(keyword => this.normalizeReportHeadingKey(keyword))
                .filter(Boolean);

            return sections.find(section => normalizedKeywords.some(keyword => section.key.includes(keyword))) || null;
        },

        extractSectionParagraphs(section) {
            if (!section?.nodes?.length) return [];

            const paragraphs = [];
            section.nodes.forEach(node => {
                if (!(node instanceof Element)) return;
                if (node.tagName === 'P') {
                    paragraphs.push(node);
                }
                node.querySelectorAll('p').forEach(paragraph => paragraphs.push(paragraph));
            });

            return paragraphs
                .map(paragraph => this.cleanReportText(paragraph.textContent || ''))
                .filter(text => text.length >= 24);
        },

        extractSectionListItems(section, maxItems = 3) {
            if (!section?.nodes?.length) return [];

            const values = [];
            section.nodes.forEach(node => {
                if (!(node instanceof Element)) return;
                const items = [];
                if (node.tagName === 'LI') items.push(node);
                node.querySelectorAll('li').forEach(item => items.push(item));
                items.forEach(item => {
                    const text = this.cleanReportText(item.textContent || '');
                    if (!text || values.includes(text)) return;
                    values.push(text);
                });
            });

            return values.slice(0, maxItems);
        },

        extractSectionTableFirstColumn(section, maxItems = 3) {
            if (!section?.nodes?.length) return [];

            const values = [];
            const tables = section.nodes
                .filter(node => node instanceof Element)
                .flatMap(node => {
                    const collection = [];
                    if (node.tagName === 'TABLE') collection.push(node);
                    node.querySelectorAll('table').forEach(table => collection.push(table));
                    return collection;
                });

            tables.forEach(table => {
                Array.from(table.querySelectorAll('tbody tr, tr')).forEach(row => {
                    if (row.closest('thead')) return;
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length === 0) return;
                    const firstText = this.cleanReportText(cells[0]?.textContent || '');
                    const secondText = this.cleanReportText(cells[1]?.textContent || '');
                    const looksLikePriority = /^P\d$/i.test(firstText) || /优先级|priority/i.test(firstText);
                    const text = looksLikePriority && secondText ? secondText : firstText;
                    if (!text || values.includes(text)) return;
                    values.push(text);
                });
            });

            return values.slice(0, maxItems);
        },

        extractOverviewFacts(section, maxItems = 4) {
            if (!section?.nodes?.length) return [];

            const tables = section.nodes
                .filter(node => node instanceof Element)
                .flatMap(node => {
                    const collection = [];
                    if (node.tagName === 'TABLE') collection.push(node);
                    node.querySelectorAll('table').forEach(table => collection.push(table));
                    return collection;
                });
            const table = tables[0];
            if (!table) return [];

            return Array.from(table.querySelectorAll('tbody tr, tr'))
                .filter(row => !row.closest('thead'))
                .map(row => Array.from(row.querySelectorAll('td')))
                .filter(cells => cells.length >= 2)
                .map(cells => ({
                    label: this.cleanReportText(cells[0].textContent || ''),
                    value: this.cleanReportText(cells[1].textContent || '')
                }))
                .filter(item => item.label && item.value)
                .slice(0, maxItems);
        },

        buildReportDetailModel(reportElement, sections = [], navItems = []) {
            const mainSections = sections.filter(section => !section.isAppendix);
            const totalChars = mainSections.reduce((sum, section) => sum + section.charCount, 0);
            const flatNavItems = Array.isArray(navItems) && navItems.length > 0
                ? navItems
                : this.buildReportDetailNavItems(sections);
            const primarySections = flatNavItems.filter(item => Number(item.depth || 0) === 0);
            const overviewSection = this.findReportSectionByKeywords(sections, ['访谈概述']);
            const nextActionSection = this.findReportSectionByKeywords(sections, ['下一步行动']);
            const proposalSection = this.findReportSectionByKeywords(sections, ['方案建议']);
            const summaryCandidates = mainSections
                .flatMap(section => this.extractSectionParagraphs(section))
                .slice(0, 3);
            const primaryActions = this.extractSectionListItems(nextActionSection, 3);
            const primaryActionFallback = this.extractSectionTableFirstColumn(nextActionSection, 3);
            const proposalActions = this.extractSectionListItems(proposalSection, 3);
            const proposalActionFallback = this.extractSectionTableFirstColumn(proposalSection, 3);

            const summaryText = summaryCandidates[0]
                || '当前报告已按章节组织为可阅读文档，可通过左侧目录快速定位重点。';

            const actionItems = primaryActions.length
                ? primaryActions
                : (
                    primaryActionFallback.length
                        ? primaryActionFallback
                        : (
                            proposalActions.length
                                ? proposalActions
                                : proposalActionFallback
                        )
                );

            const currentSection = flatNavItems[0] || null;
            const currentTopSection = primarySections[0] || null;
            const progressPercent = currentTopSection
                ? this.calculateReportProgressPercent(currentTopSection.id, sections, totalChars)
                : 0;
            const remainingLabel = currentTopSection
                ? this.calculateReportRemainingLabel(currentTopSection.id, sections, totalChars)
                : '-';

            return {
                sections: flatNavItems.map(item => ({
                    id: item.id,
                    title: item.title,
                    breadcrumbLabel: item.breadcrumbLabel || item.title,
                    indexLabel: item.indexLabel,
                    isAppendix: item.isAppendix,
                    depth: item.depth || 0,
                    topLevelId: item.topLevelId || item.id
                })),
                primarySections: primarySections.map(item => ({
                    id: item.id,
                    title: item.title,
                    indexLabel: item.indexLabel,
                    isAppendix: item.isAppendix,
                    depth: 0
                })),
                currentSectionId: currentSection?.id || '',
                currentTopSectionId: currentTopSection?.id || currentSection?.id || '',
                currentSectionLabel: currentSection?.breadcrumbLabel || currentSection?.title || '阅读中',
                progressPercent,
                remainingLabel,
                summaryText,
                overviewItems: this.extractOverviewFacts(overviewSection, 4),
                actionItems,
                mobileNavOpen: false
            };
        },

        calculateReportProgressPercent(sectionId, sections = [], totalChars = 0) {
            if (!sectionId || totalChars <= 0) return 0;
            const target = sections.find(section => section.id === sectionId) || null;
            if (!target) return 0;
            if (target.isAppendix) return 100;

            const estimate = (target.startChars + target.charCount * 0.4) / totalChars;
            return Math.max(6, Math.min(99, Math.round(estimate * 100)));
        },

        calculateReportRemainingLabel(sectionId, sections = [], totalChars = 0) {
            if (!sectionId || totalChars <= 0) return '-';
            const target = sections.find(section => section.id === sectionId) || null;
            if (!target) return '-';
            if (target.isAppendix) return '附录 / 原始记录';

            const remainingChars = Math.max(totalChars - target.startChars, 0);
            const remainingMinutes = Math.max(1, Math.ceil(remainingChars / 320));
            return `约 ${remainingMinutes} 分钟`;
        },

        setupReportSectionObserver() {
            if (!Array.isArray(this.reportDetailSectionRegistry) || this.reportDetailSectionRegistry.length === 0) {
                return;
            }

            if (this.reportDetailObserver) {
                this.reportDetailObserver.disconnect();
            }

            this.reportDetailObserver = new IntersectionObserver((entries) => {
                const activeEntry = entries
                    .filter(entry => entry.isIntersecting)
                    .sort((a, b) => {
                        if (b.intersectionRatio !== a.intersectionRatio) {
                            return b.intersectionRatio - a.intersectionRatio;
                        }
                        return a.boundingClientRect.top - b.boundingClientRect.top;
                    })[0];

                if (!activeEntry?.target?.id) return;
                this.updateActiveReportSection(activeEntry.target.id);
            }, {
                rootMargin: '-18% 0px -62% 0px',
                threshold: [0.12, 0.3, 0.6]
            });

            this.reportDetailSectionRegistry.forEach(section => {
                if (section?.element) {
                    this.reportDetailObserver.observe(section.element);
                }
            });

            const fallbackSectionId = this.reportDetailSectionRegistry[0]?.id || '';
            if (fallbackSectionId) {
                this.updateActiveReportSection(fallbackSectionId);
            }
        },

        updateActiveReportSection(sectionId) {
            if (!sectionId || !this.reportDetailModel) return;

            const target = this.reportDetailSectionRegistry.find(section => section.id === sectionId) || null;
            if (!target) return;

            const primarySections = this.reportDetailSectionRegistry
                .filter(section => Number(section.depth || 0) === 0);
            const totalChars = primarySections
                .filter(section => !section.isAppendix)
                .reduce((sum, section) => sum + section.charCount, 0);
            const progressSectionId = target.topLevelId || target.id;

            this.reportDetailModel.currentSectionId = sectionId;
            this.reportDetailModel.currentTopSectionId = progressSectionId;
            this.reportDetailModel.currentSectionLabel = target.breadcrumbLabel || target.title;
            this.reportDetailModel.progressPercent = this.calculateReportProgressPercent(
                progressSectionId,
                primarySections,
                totalChars
            );
            this.reportDetailModel.remainingLabel = this.calculateReportRemainingLabel(
                progressSectionId,
                primarySections,
                totalChars
            );

            this.reportDetailSectionRegistry.forEach(section => {
                if (!section?.element) return;
                section.element.classList.toggle('is-active', section.id === sectionId);
            });
            this.ensureReportNavItemVisible(sectionId);
        },

        enhanceAppendixToggle(reportElement) {
            if (!reportElement) return;

            if (this.appendixExportOutsideHandler) {
                document.removeEventListener('click', this.appendixExportOutsideHandler, true);
                this.appendixExportOutsideHandler = null;
            }

            const appendixHeading = Array.from(reportElement.querySelectorAll('h2'))
                .find(heading => (heading.textContent || '').includes('附录：完整访谈记录'));
            if (!appendixHeading) {
                return;
            }

            appendixHeading.classList.add('dv-appendix-heading');
            this.injectAppendixExportMenu(appendixHeading);

            let rootDetails = null;
            let cursor = appendixHeading.nextElementSibling;
            while (cursor) {
                if (cursor.tagName === 'H2') {
                    break;
                }
                if (cursor.tagName === 'DETAILS') {
                    rootDetails = cursor;
                    break;
                }
                cursor = cursor.nextElementSibling;
            }

            if (!rootDetails) {
                return;
            }

            const summary = rootDetails.firstElementChild?.tagName === 'SUMMARY'
                ? rootDetails.firstElementChild
                : null;
            if (summary) {
                const baseText = this.normalizeAppendixSummaryText(summary.textContent || '').trim();
                summary.textContent = baseText;
            }

            const childDetails = Array.from(rootDetails.querySelectorAll('details'))
                .filter(detail => detail !== rootDetails);
            if (childDetails.length === 0) {
                return;
            }

            const setChildrenOpenState = (open) => {
                childDetails.forEach(detail => {
                    detail.open = open;
                });
            };

            if (!rootDetails.open) {
                setChildrenOpenState(false);
            }

            if (rootDetails.dataset.dvAppendixBound === '1') {
                return;
            }

            rootDetails.addEventListener('toggle', () => {
                setChildrenOpenState(rootDetails.open);
            });
            rootDetails.dataset.dvAppendixBound = '1';
        },

        injectAppendixExportMenu(appendixHeading) {
            if (!appendixHeading) return;

            const existingWrap = appendixHeading.querySelector('.dv-appendix-export-wrap');
            if (existingWrap) {
                existingWrap.remove();
            }
            if (!this.canExportAppendix()) {
                return;
            }

            const menuWrap = document.createElement('div');
            menuWrap.className = 'dv-appendix-export-wrap';

            const trigger = document.createElement('button');
            trigger.type = 'button';
            trigger.className = 'dv-appendix-export-trigger';
            trigger.setAttribute('aria-haspopup', 'menu');
            trigger.setAttribute('aria-expanded', 'false');
            trigger.innerHTML = `
                <svg class="dv-appendix-export-trigger-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                <span>导出</span>
                <svg class="dv-appendix-export-trigger-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                </svg>
            `;
            menuWrap.appendChild(trigger);

            const panel = document.createElement('div');
            panel.className = 'dv-appendix-export-menu dv-popover-panel';
            panel.setAttribute('role', 'menu');
            panel.setAttribute('aria-hidden', 'true');

            const openMenu = () => {
                menuWrap.classList.add('is-open');
                trigger.setAttribute('aria-expanded', 'true');
                panel.setAttribute('aria-hidden', 'false');
                const firstItem = panel.querySelector('[data-first-item="1"]');
                firstItem?.focus();
            };

            const closeMenu = (options = {}) => {
                const { restoreFocus = false } = options;
                menuWrap.classList.remove('is-open');
                trigger.setAttribute('aria-expanded', 'false');
                panel.setAttribute('aria-hidden', 'true');
                if (restoreFocus) {
                    trigger.focus();
                }
            };

            const options = [
                {
                    format: 'md',
                    title: 'Markdown',
                    desc: '.md 源文件',
                    iconClass: 'is-md',
                    iconPath: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
                },
                {
                    format: 'pdf',
                    title: 'PDF',
                    desc: '适合打印分享',
                    iconClass: 'is-pdf',
                    iconPath: 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z'
                },
                {
                    format: 'docx',
                    title: 'Word',
                    desc: '.docx 可编辑',
                    iconClass: 'is-docx',
                    iconPath: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
                },
            ].filter((item) => this.canExportFormat('appendix', item.format));

            if (options.length === 0) {
                return;
            }

            options.forEach((item, index) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'dv-appendix-export-item';
                btn.setAttribute('data-format', item.format);
                if (index === 0) {
                    btn.setAttribute('data-first-item', '1');
                }
                btn.innerHTML = `
                    <svg class="dv-appendix-export-item-icon ${item.iconClass}" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${item.iconPath}"></path>
                    </svg>
                    <span class="dv-appendix-export-item-copy">
                        <span class="dv-appendix-export-item-title">${item.title}</span>
                        <span class="dv-appendix-export-item-desc">${item.desc}</span>
                    </span>
                `;
                btn.addEventListener('click', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    this.downloadAppendix(item.format);
                    closeMenu({ restoreFocus: true });
                });
                panel.appendChild(btn);
            });

            trigger.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (menuWrap.classList.contains('is-open')) {
                    closeMenu();
                    return;
                }
                openMenu();
            });

            trigger.addEventListener('keydown', (event) => {
                if (event.key !== 'ArrowDown') return;
                event.preventDefault();
                if (!menuWrap.classList.contains('is-open')) {
                    openMenu();
                }
            });

            menuWrap.addEventListener('keydown', (event) => {
                if (event.key !== 'Escape') return;
                event.preventDefault();
                closeMenu({ restoreFocus: true });
            });

            menuWrap.appendChild(panel);
            appendixHeading.appendChild(menuWrap);

            this.appendixExportOutsideHandler = (event) => {
                if (!menuWrap.classList.contains('is-open')) return;
                if (menuWrap.contains(event.target)) return;
                closeMenu();
            };
            document.addEventListener('click', this.appendixExportOutsideHandler, true);
        },

        onReportRendered() {
            const reportElement = this.$refs?.reportMarkdown || document.querySelector('.dv-report-markdown-body');
            if (!reportElement) {
                this.reportDetailEnhancing = false;
                return;
            }

            try {
                this.cleanupReportDetailEnhancements({ resetModel: false });
                this.renderMermaidCharts();
                this.injectReportSummaryAndToc(reportElement);
                this.enhanceReportTables(reportElement);
            } finally {
                this.reportDetailEnhancing = false;
            }

            this.cacheCurrentReportDetailSnapshot();
        },

        enhanceReportTables(reportElement) {
            if (!reportElement) return;

            const prefersReducedMotion = typeof window !== 'undefined'
                && typeof window.matchMedia === 'function'
                && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            const tables = Array.from(reportElement.querySelectorAll('table'));

            tables.forEach((table, index) => {
                if (!(table instanceof HTMLTableElement) || table.closest('.dv-report-table-shell')) return;
                const parent = table.parentNode;
                if (!parent) return;

                const shell = document.createElement('section');
                shell.className = 'dv-report-table-shell';

                const affordance = document.createElement('div');
                affordance.className = 'dv-report-table-affordance';

                const hint = document.createElement('span');
                hint.className = 'dv-report-table-hint';
                hint.textContent = '支持左右拖动、滚轮横移，也可点击两侧按钮查看隐藏列';

                const actions = document.createElement('div');
                actions.className = 'dv-report-table-actions';

                const buildButton = (direction, label) => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = `dv-report-table-button is-${direction}`;
                    button.setAttribute('aria-label', label);
                    button.innerHTML = direction === 'left'
                        ? `
                            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                                <path d="M12.5 4.5L7 10l5.5 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                            </svg>
                        `
                        : `
                            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                                <path d="M7.5 4.5L13 10l-5.5 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
                            </svg>
                        `;
                    return button;
                };

                const leftButton = buildButton('left', '向左查看表格');
                const rightButton = buildButton('right', '向右查看表格');
                actions.append(leftButton, rightButton);
                affordance.append(hint, actions);

                const scroller = document.createElement('div');
                scroller.className = 'dv-report-table-scroll';
                scroller.tabIndex = 0;
                scroller.setAttribute('role', 'region');
                const captionText = this.cleanReportText(table.querySelector('caption')?.textContent || '');
                scroller.setAttribute('aria-label', captionText ? `${captionText}（可左右滚动）` : `表格 ${index + 1}（可左右滚动）`);

                parent.insertBefore(shell, table);
                scroller.appendChild(table);
                shell.append(affordance, scroller);

                let activePointerId = null;
                let dragStartX = 0;
                let dragStartScrollLeft = 0;

                const getMaxScrollLeft = () => Math.max(0, scroller.scrollWidth - scroller.clientWidth);
                const getScrollStep = () => Math.max(220, Math.round(scroller.clientWidth * 0.72));

                const updateState = () => {
                    const maxScrollLeft = getMaxScrollLeft();
                    const scrollLeft = Math.max(0, scroller.scrollLeft);
                    const overflowing = maxScrollLeft > 8;
                    const atStart = !overflowing || scrollLeft <= 4;
                    const atEnd = !overflowing || scrollLeft >= maxScrollLeft - 4;

                    shell.classList.toggle('is-overflowing', overflowing);
                    shell.classList.toggle('is-at-start', atStart);
                    shell.classList.toggle('is-at-end', atEnd);
                    leftButton.disabled = atStart;
                    rightButton.disabled = atEnd;
                };

                const scrollByStep = (direction) => {
                    const nextLeft = direction === 'left'
                        ? Math.max(0, scroller.scrollLeft - getScrollStep())
                        : Math.min(getMaxScrollLeft(), scroller.scrollLeft + getScrollStep());
                    scroller.scrollTo({
                        left: nextLeft,
                        behavior: prefersReducedMotion ? 'auto' : 'smooth'
                    });
                };

                const stopDragging = () => {
                    if (activePointerId !== null && typeof scroller.hasPointerCapture === 'function' && scroller.hasPointerCapture(activePointerId)) {
                        scroller.releasePointerCapture(activePointerId);
                    }
                    activePointerId = null;
                    shell.classList.remove('is-dragging');
                };

                const handleScroll = () => updateState();
                const handleWheel = (event) => {
                    const maxScrollLeft = getMaxScrollLeft();
                    if (maxScrollLeft <= 0) return;
                    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
                    if (event.deltaY === 0) return;

                    const movingLeft = event.deltaY < 0;
                    const atStart = scroller.scrollLeft <= 1;
                    const atEnd = scroller.scrollLeft >= maxScrollLeft - 1;
                    if ((movingLeft && atStart) || (!movingLeft && atEnd)) return;

                    event.preventDefault();
                    scroller.scrollLeft += event.deltaY;
                };

                const handlePointerDown = (event) => {
                    if (event.pointerType === 'touch' || event.button !== 0 || getMaxScrollLeft() <= 0) return;
                    if (event.target instanceof Element && event.target.closest('a, button, input, textarea, select, summary')) return;

                    activePointerId = event.pointerId;
                    dragStartX = event.clientX;
                    dragStartScrollLeft = scroller.scrollLeft;
                    shell.classList.add('is-dragging');
                    if (typeof scroller.setPointerCapture === 'function') {
                        scroller.setPointerCapture(activePointerId);
                    }
                    event.preventDefault();
                };

                const handlePointerMove = (event) => {
                    if (activePointerId === null || event.pointerId !== activePointerId) return;
                    const deltaX = event.clientX - dragStartX;
                    scroller.scrollLeft = dragStartScrollLeft - deltaX;
                };

                const handlePointerUp = (event) => {
                    if (activePointerId === null || event.pointerId !== activePointerId) return;
                    stopDragging();
                };

                const handleKeydown = (event) => {
                    if (getMaxScrollLeft() <= 0) return;

                    if (event.key === 'ArrowLeft') {
                        event.preventDefault();
                        scrollByStep('left');
                        return;
                    }
                    if (event.key === 'ArrowRight') {
                        event.preventDefault();
                        scrollByStep('right');
                        return;
                    }
                    if (event.key === 'Home') {
                        event.preventDefault();
                        scroller.scrollTo({ left: 0, behavior: prefersReducedMotion ? 'auto' : 'smooth' });
                        return;
                    }
                    if (event.key === 'End') {
                        event.preventDefault();
                        scroller.scrollTo({ left: getMaxScrollLeft(), behavior: prefersReducedMotion ? 'auto' : 'smooth' });
                    }
                };

                const handleWindowResize = () => updateState();
                const handleLeftClick = () => scrollByStep('left');
                const handleRightClick = () => scrollByStep('right');
                const resizeObserver = typeof ResizeObserver !== 'undefined'
                    ? new ResizeObserver(() => updateState())
                    : null;

                scroller.addEventListener('scroll', handleScroll, { passive: true });
                scroller.addEventListener('wheel', handleWheel, { passive: false });
                scroller.addEventListener('pointerdown', handlePointerDown);
                scroller.addEventListener('pointermove', handlePointerMove);
                scroller.addEventListener('pointerup', handlePointerUp);
                scroller.addEventListener('pointercancel', handlePointerUp);
                scroller.addEventListener('keydown', handleKeydown);
                leftButton.addEventListener('click', handleLeftClick);
                rightButton.addEventListener('click', handleRightClick);
                window.addEventListener('resize', handleWindowResize);

                if (resizeObserver) {
                    resizeObserver.observe(scroller);
                    resizeObserver.observe(table);
                }

                window.requestAnimationFrame(() => updateState());

                this.reportTableCleanupFns.push(() => {
                    stopDragging();
                    scroller.removeEventListener('scroll', handleScroll);
                    scroller.removeEventListener('wheel', handleWheel);
                    scroller.removeEventListener('pointerdown', handlePointerDown);
                    scroller.removeEventListener('pointermove', handlePointerMove);
                    scroller.removeEventListener('pointerup', handlePointerUp);
                    scroller.removeEventListener('pointercancel', handlePointerUp);
                    scroller.removeEventListener('keydown', handleKeydown);
                    leftButton.removeEventListener('click', handleLeftClick);
                    rightButton.removeEventListener('click', handleRightClick);
                    window.removeEventListener('resize', handleWindowResize);
                    resizeObserver?.disconnect();

                    if (shell.isConnected && scroller.contains(table)) {
                        shell.parentNode?.insertBefore(table, shell);
                        shell.remove();
                    }
                });
            });
        }
    };

    function attach(app) {
        if (!app || typeof app !== 'object') return app;

        Object.entries(reportDetailRuntimeDefaults).forEach(([key, value]) => {
            if (typeof app[key] === 'undefined') {
                app[key] = cloneDefaultValue(value);
            }
        });

        Object.assign(app, reportDetailRuntimeMethods);
        return app;
    }

    global.DeepVisionReportDetailRuntimeModule = { attach };
})(window);

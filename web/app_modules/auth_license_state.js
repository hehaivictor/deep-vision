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

    const authLicenseStateDefaults = {
        authReady: false,
        authLoading: false,
        authChecking: true,
        smsLoginEnabled: true,
        smsCodeLength: 6,
        smsCooldownSeconds: 60,
        authCodeSending: false,
        authCodeCountdown: 0,
        authCodeTimer: null,
        wechatLoginEnabled: false,
        wechatLoginLoading: false,
        wechatBindLoading: false,
        authRedirectResult: null,
        authForm: {
            account: '',
            code: ''
        },
        authErrors: {
            account: '',
            code: ''
        },
        authAccountHistoryStorageKey: 'deepvision_auth_account_history',
        authAccountHistoryMaxItems: 5,
        authAccountHistory: [],
        authAccountSuggestionsOpen: false,
        authAccountSuggestionsCloseTimer: null,
        currentUser: null,
        licenseChecking: false,
        licenseEnforcementEnabled: false,
        hasValidLicense: false,
        licenseStatus: 'missing',
        licenseInfo: null,
        licenseGateActive: false,
        licenseGateMessage: '',
        licenseActivationLoading: false,
        licenseActivationForm: {
            code: ''
        },
        licenseActivationError: '',
        authViewLightLocked: false,
        showBindPhoneModal: false,
        bindPhoneLoading: false,
        bindCodeSending: false,
        bindCodeCountdown: 0,
        bindCodeTimer: null,
        bindPhoneForm: {
            phone: '',
            code: ''
        },
        bindPhoneErrors: {
            phone: '',
            code: ''
        },
        showAccountMergeModal: false,
        accountMergeLoading: false,
        accountMergeApplyLoading: false,
        accountMergeError: '',
        accountMergePreview: null,
        accountMergeConfirmText: '',
        showLogoutConfirmModal: false,
    };

    const authLicenseStateMethods = {
        async checkAuthStatus() {
            if (this.serverStatus && this.serverStatus.authenticated === false) {
                this.enterLoginState({ showToast: false });
                return;
            }
            if (this.serverStatus?.authenticated === true && this.serverStatus?.user) {
                this.currentUser = this.serverStatus.user || null;
                this.applyUserLevelPayload(this.serverStatus || {});
                this.applyPresentationFeaturePayload(this.serverStatus || {});
                this.authReady = Boolean(this.currentUser);
                return;
            }
            try {
                const result = await this.apiCall('/auth/me', {
                    skipAuthRedirect: true,
                    expectedStatuses: [401]
                });
                this.currentUser = result?.user || null;
                this.applyUserLevelPayload(result || {});
                this.applyPresentationFeaturePayload(result || {});
                this.authReady = Boolean(this.currentUser);
            } catch (error) {
                this.enterLoginState({ showToast: false });
            }
        },

        resetLicenseState() {
            this.resetUserLevelState();
            this.licenseChecking = false;
            this.licenseEnforcementEnabled = Boolean(this.serverStatus?.license_enforcement_enabled);
            this.hasValidLicense = false;
            this.licenseStatus = 'missing';
            this.licenseInfo = null;
            this.licenseGateActive = false;
            this.licenseGateMessage = '';
            this.licenseActivationLoading = false;
            this.licenseActivationForm = { code: '' };
            this.licenseActivationError = '';
        },

        applyLicenseStatusPayload(payload = {}, options = {}) {
            const {
                message = '',
                preserveInput = false
            } = options;
            const enforcementEnabled = Boolean(
                payload?.enforcement_enabled ?? this.serverStatus?.license_enforcement_enabled
            );
            const hasValidLicense = Boolean(payload?.has_valid_license);
            const status = String(payload?.status || 'missing').trim() || 'missing';
            this.licenseEnforcementEnabled = enforcementEnabled;
            this.hasValidLicense = hasValidLicense;
            this.licenseStatus = status;
            this.licenseInfo = payload?.license || null;
            this.licenseGateActive = enforcementEnabled && !hasValidLicense;
            this.licenseGateMessage = String(message || '').trim();
            this.applyUserLevelPayload(payload || {});
            if (!preserveInput && hasValidLicense) {
                this.licenseActivationForm.code = '';
                this.licenseActivationError = '';
            }
        },

        enterLicenseGateState(payload = {}, options = {}) {
            const errorCode = String(payload?.error_code || '').trim();
            const licenseStatus = String(
                payload?.license_status
                || (errorCode.startsWith('license_') ? errorCode.replace(/^license_/, '') : '')
                || this.licenseStatus
                || 'missing'
            ).trim();
            this.applyLicenseStatusPayload(
                {
                    enforcement_enabled: true,
                    has_valid_license: false,
                    status: licenseStatus,
                    license: payload?.license || this.licenseInfo || null
                },
                {
                    message: payload?.error || options.message || '',
                    preserveInput: true
                }
            );
            this.showAccountMenu = false;
            this.showSettingsModal = false;
            this.showNewSessionModal = false;
            this.showDeleteModal = false;
            this.showDeleteReportModal = false;
            this.showBatchDeleteModal = false;
            this.showRestartModal = false;
            this.showDeleteDocModal = false;
            this.showBindPhoneModal = false;
            this.clearAdminGeneratedLicenseBatch();
            this.abortQuestionRequest();
            this.stopQuestionRequestGuard();
            this.stopThinkingPolling();
            this.stopWebSearchPolling();
            this.stopReportGenerationPolling();
            this.stopSessionsAutoRefresh();
            this.stopPresentationPolling();
            this.loading = false;
            this.loadingQuestion = false;
            this.submitting = false;
            this.generatingReport = false;
            this.generatingSlides = false;
        },

        async refreshLicenseStatus(options = {}) {
            const { showToast = false } = options;
            if (!this.authReady) {
                this.resetLicenseState();
                return null;
            }

            this.licenseChecking = true;
            try {
                const payload = await this.apiCall('/licenses/current', {
                    skipAuthRedirect: true,
                    expectedStatuses: [401]
                });
                this.applyLicenseStatusPayload(payload);
                if (showToast && this.licenseGateActive) {
                    this.showToast(this.getLicenseGateDescription(), 'warning');
                }
                return payload;
            } catch (error) {
                if (error?.status === 401) {
                    this.enterLoginState({ showToast: false });
                    return null;
                }
                this.enterLicenseGateState(
                    {
                        error: error?.message || 'License 状态获取失败',
                        error_code: 'license_required',
                        license_status: this.licenseStatus || 'missing',
                        license: this.licenseInfo || null
                    },
                    { message: error?.message || 'License 状态获取失败' }
                );
                if (showToast) {
                    this.showToast(error?.message || 'License 状态获取失败', 'error');
                }
                return null;
            } finally {
                this.licenseChecking = false;
            }
        },

        getLicenseStatusLabel(status = '') {
            const normalized = String(status || this.licenseStatus || 'missing').trim();
            if (normalized === 'active') return '已生效';
            if (normalized === 'not_yet_active') return '未到生效时间';
            if (normalized === 'expired') return '已过期';
            if (normalized === 'revoked') return '已撤销';
            if (normalized === 'replaced') return '已替换';
            return '未绑定';
        },

        getLicenseGateTitle() {
            if (this.licenseStatus === 'expired') return 'License 已过期';
            if (this.licenseStatus === 'not_yet_active') return 'License 尚未生效';
            if (this.licenseStatus === 'revoked') return 'License 已被撤销';
            if (this.licenseStatus === 'replaced') return '需要重新绑定新的 License';
            return '请输入 License 继续使用';
        },

        getLicenseGateDescription() {
            if (this.licenseGateMessage) return this.licenseGateMessage;
            if (this.licenseStatus === 'expired') return '当前账号绑定的 License 已过期，请联系管理员续期或重新分配。';
            if (this.licenseStatus === 'not_yet_active') return '当前账号的 License 尚未到生效时间，请等待生效后再继续。';
            if (this.licenseStatus === 'revoked') return '当前账号绑定的 License 已被撤销，请联系管理员获取新的 License。';
            if (this.licenseStatus === 'replaced') return '当前账号之前绑定的 License 已被替换，请输入新的 License 完成换绑。';
            return '登录后必须绑定有效 License，才能继续使用访谈与报告功能。';
        },

        getLicenseRemainingText() {
            const status = String(this.licenseStatus || '').trim();
            if (status === 'revoked') return '已撤销';
            if (status === 'replaced') return '已替换';
            if (status === 'expired') return '已过期';
            if (status === 'not_yet_active') {
                const notBeforeAt = this.licenseInfo?.not_before_at;
                if (!notBeforeAt) return '未到生效时间';
                const notBeforeDate = new Date(notBeforeAt);
                if (!Number.isFinite(notBeforeDate.getTime())) return '未到生效时间';
                const diffMs = notBeforeDate.getTime() - Date.now();
                if (diffMs <= 0) return '未到生效时间';
                const diffDays = Math.ceil(diffMs / (24 * 60 * 60 * 1000));
                return diffDays <= 1 ? '不足 1 天后生效' : `约 ${diffDays} 天后生效`;
            }
            const expiresAt = this.licenseInfo?.expires_at;
            if (!expiresAt) return status === 'missing' ? '未绑定' : '未设置';
            const expiresDate = new Date(expiresAt);
            if (!Number.isFinite(expiresDate.getTime())) return '未设置';
            const diffMs = expiresDate.getTime() - Date.now();
            if (diffMs <= 0) return '已过期';
            const diffDays = Math.ceil(diffMs / (24 * 60 * 60 * 1000));
            return diffDays <= 1 ? '不足 1 天' : `约 ${diffDays} 天`;
        },

        canSubmitLicenseActivation() {
            return !!String(this.licenseActivationForm.code || '').trim() && !this.licenseActivationLoading;
        },

        async submitLicenseActivation() {
            if (!this.canSubmitLicenseActivation()) return;
            this.licenseActivationLoading = true;
            this.licenseActivationError = '';
            try {
                const payload = await this.apiCall('/licenses/activate', {
                    method: 'POST',
                    body: JSON.stringify({
                        code: String(this.licenseActivationForm.code || '').trim()
                    }),
                    skipAuthRedirect: true
                });
                this.applyLicenseStatusPayload(payload);
                this.showToast(payload?.message || 'License 绑定成功', 'success');
                if (!this.licenseGateActive) {
                    await this.bootstrapAuthenticatedApp({ skipLicenseRefresh: true });
                }
            } catch (error) {
                const payload = error?.payload || {};
                if (error?.status === 401) {
                    this.enterLoginState({ showToast: false });
                    return;
                }
                if (error?.status === 403 && String(payload?.error_code || '').startsWith('license_')) {
                    this.enterLicenseGateState(payload, { message: payload?.error || error?.message || '' });
                }
                this.licenseActivationError = payload?.error || error?.message || 'License 绑定失败，请稍后重试';
                this.showToast(this.licenseActivationError, 'error');
            } finally {
                this.licenseActivationLoading = false;
            }
        },

        readAuthRedirectResult() {
            if (typeof window === 'undefined') return;
            const params = new URLSearchParams(window.location.search || '');
            const result = params.get('auth_result');
            if (!result) return;

            const message = params.get('auth_message') || '';
            this.authRedirectResult = {
                result,
                message
            };

            params.delete('auth_result');
            params.delete('auth_message');
            const nextQuery = params.toString();
            const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
            window.history.replaceState({}, '', nextUrl);
        },

        async consumeInitialEntryRoute() {
            if (typeof window === 'undefined') return;
            const params = new URLSearchParams(window.location.search || '');
            const targetView = String(params.get('view') || '').trim();
            const targetReport = String(params.get('report') || '').trim();
            const targetSession = String(params.get('session') || '').trim();

            if (!targetView && !targetReport && !targetSession) return;
            if (targetReport) {
                this.currentView = 'reports';
                this.appShellRestoreTarget = {
                    view: 'reports',
                    sessionId: '',
                    reportName: targetReport,
                };
            } else if (targetView === 'interview' && targetSession) {
                this.currentView = 'interview';
                this.appShellRestoreTarget = {
                    view: 'interview',
                    sessionId: targetSession,
                    reportName: '',
                };
            } else if (targetView !== 'reports') {
                return;
            } else {
                this.currentView = 'reports';
            }

            params.delete('view');
            params.delete('report');
            params.delete('session');
            const nextQuery = params.toString();
            const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
            window.history.replaceState({}, '', nextUrl);
        },

        async consumeAuthRedirectToast() {
            if (!this.authRedirectResult) return;

            const result = String(this.authRedirectResult.result || '');
            const rawMessage = String(this.authRedirectResult.message || '').trim();
            let toastType = 'info';
            let fallbackMessage = '登录状态已更新';
            let shouldOpenAccountMerge = false;

            if (result === 'wechat_success') {
                toastType = this.authReady ? 'success' : 'warning';
                fallbackMessage = this.authReady ? '微信登录成功' : '微信登录未完成，请重试';
            } else if (result === 'wechat_cancel') {
                toastType = 'warning';
                fallbackMessage = '已取消微信登录';
            } else if (result === 'wechat_error') {
                toastType = 'error';
                fallbackMessage = '微信登录失败，请稍后重试';
            } else if (result === 'wechat_bind_success') {
                toastType = this.authReady ? 'success' : 'warning';
                fallbackMessage = this.authReady ? '微信绑定成功' : '微信绑定未完成，请重试';
            } else if (result === 'wechat_bind_error') {
                toastType = 'error';
                fallbackMessage = '微信绑定失败，请稍后重试';
            } else if (result === 'wechat_bind_merge_required') {
                toastType = 'warning';
                fallbackMessage = '发现另一个微信账号已有历史数据，请确认合并后继续绑定';
                shouldOpenAccountMerge = true;
            }

            this.showToast(rawMessage || fallbackMessage, toastType);
            this.authRedirectResult = null;
            if (shouldOpenAccountMerge && this.authReady) {
                await this.loadAccountMergePreview({ openModal: true, showToastOnError: true });
            }
        },

        enterLoginState(options = {}) {
            const {
                showToast = false,
                toastMessage = '登录状态已失效，请重新登录',
                toastType = 'warning'
            } = options;

            this.authChecking = false;
            this.authReady = false;
            this.currentUser = null;
            this.resetLicenseState();
            this.authLoading = false;
            this.wechatLoginLoading = false;
            this.wechatBindLoading = false;
            this.currentView = 'sessions';
            this.currentSession = null;
            this.sessions = [];
            this.sessionsLoaded = false;
            this.reports = [];
            this.reportsLoaded = false;
            this.filteredReports = [];
            this.filteredSessions = [];
            this.reportItems = [];
            this.cleanupReportDetailEnhancements();
            this.selectedReport = null;
            this.reportContent = '';
            this.reportDetailCache = {};
            this.selectedReportMeta = this.createEmptySelectedReportMeta();
            this.showNewSessionModal = false;
            this.showDeleteModal = false;
            this.showLogoutConfirmModal = false;
            this.showDeleteReportModal = false;
            this.showSettingsModal = false;
            this.showBatchDeleteModal = false;
            this.showRestartModal = false;
            this.showDeleteDocModal = false;
            this.showBindPhoneModal = false;
            this.showAccountMergeModal = false;
            this.showActionConfirmModal = false;
            if (typeof this.actionConfirmResolve === 'function') {
                this.actionConfirmResolve(false);
            }
            this.actionConfirmResolve = null;
            this.showAccountMenu = false;
            this.closeAuthAccountSuggestions();
            this.stopAuthCodeCountdown('auth');
            this.bindPhoneLoading = false;
            this.bindCodeSending = false;
            this.stopAuthCodeCountdown('bind');
            this.bindPhoneForm = { phone: '', code: '' };
            this.bindPhoneErrors = { phone: '', code: '' };
            this.accountMergeLoading = false;
            this.accountMergeApplyLoading = false;
            this.accountMergeError = '';
            this.accountMergePreview = null;
            this.accountMergeConfirmText = '';
            this.sessionBatchMode = false;
            this.reportBatchMode = false;
            this.selectedSessionIds = [];
            this.selectedReportNames = [];
            this.opsMetrics = null;
            this.opsMetricsError = '';
            this.opsMetricsLoading = false;
            this.opsMetricsLastUpdatedAt = 0;
            this.opsMetricsLastLoadedAt = 0;
            this.settingsTab = 'appearance';
            this.resetAdminCenterState();
            this.resetQuestionOpsLocalState();
            this.questionRequestId += 1;
            this.abortQuestionRequest();
            this.stopQuestionRequestGuard();
            this.stopThinkingPolling();
            this.stopWebSearchPolling();
            this.loadingQuestion = false;
            this.stopReportGenerationPolling();
            this.stopSessionsAutoRefresh();
            this.stopPresentationPolling();
            this.resetPresentationProgressFeedback();
            this.resetReportGenerationFeedback();
            this.enforceAuthViewLightTheme();
            this.clearAppShellSnapshot();

            if (showToast) {
                this.showToast(toastMessage, toastType);
            }
            this.$nextTick(() => this.focusAuthAccountInput());
        },

        async bootstrapAuthenticatedApp(options = {}) {
            const { skipLicenseRefresh = false } = options;
            if (!skipLicenseRefresh) {
                await this.refreshLicenseStatus({ showToast: false });
                if (this.licenseGateActive) {
                    return;
                }
            }
            this.startQuoteRotation();

            if (this.checkFirstVisit()) {
                return;
            }
            this.initGuide();
            await this.loadScenarios();
            await this.consumeInitialEntryRoute();
            const pendingAppShellRestore = this.consumeAppShellRestoreTarget();
            if (this.currentView === 'reports') {
                await this.refreshReportsView();
                const restoreReportName = !this.selectedReport
                    ? String(pendingAppShellRestore?.reportName || '').trim()
                    : '';
                if (restoreReportName) {
                    await this.viewReport(restoreReportName, { forceReload: false });
                }
                if (!this.sessionsLoaded) {
                    this.refreshSessionsView({
                        silent: true,
                        preserveListState: true,
                        suppressErrorToast: true
                    }).catch((error) => {
                        console.warn('静默刷新会话列表失败:', error);
                    });
                }
                return;
            }
            if (this.currentView === 'interview') {
                const restoreSessionId = String(pendingAppShellRestore?.sessionId || '').trim();
                if (!restoreSessionId) {
                    this.currentView = 'sessions';
                    await this.refreshSessionsView();
                    return;
                }
                await this.refreshSessionsView({
                    silent: true,
                    preserveListState: true,
                    suppressErrorToast: true
                });
                await this.openSession(restoreSessionId);
                return;
            }
            if (this.currentView === 'admin' && this.canViewAdminCenter()) {
                void this.ensureAdminDataForTab(this.adminTab || 'overview');
                return;
            }
            await this.refreshSessionsView();
        },

        focusAuthAccountInput() {
            const input = document.querySelector('[data-auth-autofocus]');
            if (input && typeof input.focus === 'function') {
                input.focus({ preventScroll: true });
            }
        },

        focusAuthCodeInput() {
            const input = document.querySelector('[data-auth-code]');
            if (input && typeof input.focus === 'function') {
                input.focus({ preventScroll: true });
            }
        },

        loadAuthAccountHistory() {
            if (typeof localStorage === 'undefined') return;

            try {
                const raw = localStorage.getItem(this.authAccountHistoryStorageKey);
                if (!raw) {
                    this.authAccountHistory = [];
                    return;
                }

                const parsed = JSON.parse(raw);
                if (!Array.isArray(parsed)) {
                    this.authAccountHistory = [];
                    return;
                }

                const deduped = [];
                parsed.forEach((item) => {
                    const value = this.normalizeAuthPhone(String(item || '').trim());
                    if (!value || deduped.includes(value)) return;
                    deduped.push(value);
                });

                this.authAccountHistory = deduped.slice(0, this.authAccountHistoryMaxItems);
            } catch (error) {
                this.authAccountHistory = [];
                console.warn('读取历史登录账号失败');
            }
        },

        persistAuthAccountHistory() {
            if (typeof localStorage === 'undefined') return;

            try {
                localStorage.setItem(this.authAccountHistoryStorageKey, JSON.stringify(this.authAccountHistory));
            } catch (error) {
                console.warn('保存历史登录账号失败');
            }
        },

        rememberAuthAccount(account = '') {
            const value = this.normalizeAuthPhone(account);
            if (!value) return;

            this.authAccountHistory = [value, ...this.authAccountHistory.filter((item) => item !== value)]
                .slice(0, this.authAccountHistoryMaxItems);
            this.persistAuthAccountHistory();
        },

        getFilteredAuthAccountHistory() {
            const history = Array.isArray(this.authAccountHistory) ? this.authAccountHistory : [];
            if (!history.length) return [];

            const keyword = this.normalizeAuthPhone(this.authForm.account);
            if (!keyword) return history.slice(0, this.authAccountHistoryMaxItems);

            const prefixMatches = history.filter((item) => item.startsWith(keyword));
            const fuzzyMatches = history.filter((item) => !item.startsWith(keyword) && item.includes(keyword));
            return [...prefixMatches, ...fuzzyMatches].slice(0, this.authAccountHistoryMaxItems);
        },

        cancelAuthAccountSuggestionsClose() {
            if (!this.authAccountSuggestionsCloseTimer) return;
            clearTimeout(this.authAccountSuggestionsCloseTimer);
            this.authAccountSuggestionsCloseTimer = null;
        },

        openAuthAccountSuggestions() {
            this.cancelAuthAccountSuggestionsClose();
            if (!this.authAccountHistory.length) {
                this.authAccountSuggestionsOpen = false;
                return;
            }
            this.authAccountSuggestionsOpen = true;
        },

        scheduleAuthAccountSuggestionsClose(delay = 120) {
            this.cancelAuthAccountSuggestionsClose();
            this.authAccountSuggestionsCloseTimer = setTimeout(() => {
                this.authAccountSuggestionsOpen = false;
                this.authAccountSuggestionsCloseTimer = null;
            }, delay);
        },

        closeAuthAccountSuggestions() {
            this.cancelAuthAccountSuggestionsClose();
            this.authAccountSuggestionsOpen = false;
        },

        focusFirstAuthHistoryItem() {
            if (!this.authAccountSuggestionsOpen) {
                this.openAuthAccountSuggestions();
            }
            this.$nextTick(() => {
                const first = document.querySelector('[data-auth-history-item]');
                if (first && typeof first.focus === 'function') {
                    first.focus({ preventScroll: true });
                }
            });
        },

        selectAuthHistoryAccount(account = '') {
            const value = String(account || '').trim();
            if (!value) return;

            this.authForm.account = value;
            this.authErrors.account = '';
            this.closeAuthAccountSuggestions();
            this.$nextTick(() => this.focusAuthCodeInput());
        },

        normalizeAuthPhone(account = '') {
            return String(account || '')
                .trim()
                .replace(/[\s-]/g, '')
                .replace(/^\+86/, '')
                .replace(/^86(?=1\d{10}$)/, '');
        },

        handleAuthCodeEnter(event) {
            if (event?.isComposing) return;
            event.preventDefault();
            this.submitAuth();
        },

        clearAuthErrors() {
            this.authErrors = { account: '', code: '' };
        },

        enforceAuthViewLightTheme() {
            const root = document.documentElement;
            if (!(root instanceof HTMLElement)) return;

            this.authViewLightLocked = true;
            this.effectiveTheme = 'light';
            root.setAttribute('data-theme-mode', 'light');
            root.setAttribute('data-theme', 'light');
            root.style.colorScheme = 'light';
            this.applyDesignTokens('light', 'light');
            this.applyMermaidTheme('light');
        },

        restoreThemeAfterAuth() {
            if (!this.authViewLightLocked) return;
            this.authViewLightLocked = false;
            this.applyThemeMode(this.themeMode, { persist: false, rerenderCharts: false });
        },

        getAuthInputType(account = '') {
            return 'tel';
        },

        getCurrentAccountDisplay() {
            if (!this.currentUser) return '未登录';

            const nickname = String(this.currentUser?.wechat_nickname || '').trim();
            if (this.currentUser?.wechat_bound && nickname) {
                return nickname;
            }

            const phone = String(this.currentUser?.phone || '').trim();
            if (phone) {
                return phone;
            }

            if (this.currentUser?.wechat_bound) {
                return '微信用户';
            }

            return '未登录';
        },

        canUseAccountBinding() {
            return Boolean(this.smsLoginEnabled && this.wechatLoginEnabled);
        },

        stopAuthCodeCountdown(scope = 'auth') {
            const timerKey = scope === 'bind' ? 'bindCodeTimer' : 'authCodeTimer';
            const countdownKey = scope === 'bind' ? 'bindCodeCountdown' : 'authCodeCountdown';
            if (this[timerKey]) {
                clearInterval(this[timerKey]);
                this[timerKey] = null;
            }
            this[countdownKey] = 0;
        },

        startAuthCodeCountdown(seconds = 60, scope = 'auth') {
            const timerKey = scope === 'bind' ? 'bindCodeTimer' : 'authCodeTimer';
            const countdownKey = scope === 'bind' ? 'bindCodeCountdown' : 'authCodeCountdown';
            this.stopAuthCodeCountdown(scope);
            this[countdownKey] = Math.max(0, Number(seconds) || 0);
            if (this[countdownKey] <= 0) return;
            this[timerKey] = setInterval(() => {
                const next = Math.max(0, this[countdownKey] - 1);
                this[countdownKey] = next;
                if (next <= 0 && this[timerKey]) {
                    clearInterval(this[timerKey]);
                    this[timerKey] = null;
                }
            }, 1000);
        },

        canSendAuthCode() {
            const phone = this.normalizeAuthPhone(this.authForm.account);
            return this.smsLoginEnabled && /^1\d{10}$/.test(phone) && !this.authCodeSending && this.authCodeCountdown <= 0;
        },

        async sendAuthCode() {
            if (!this.smsLoginEnabled) {
                this.showToast('短信登录暂未启用，请稍后再试', 'warning');
                return;
            }
            if (!this.canSendAuthCode()) return;
            const phone = this.normalizeAuthPhone(this.authForm.account);
            this.authCodeSending = true;
            try {
                const result = await this.apiCall('/auth/sms/send-code', {
                    method: 'POST',
                    body: JSON.stringify({
                        phone,
                        scene: 'login'
                    }),
                    skipAuthRedirect: true
                });
                const cooldown = Number(result?.cooldown_seconds || result?.retry_after || this.smsCooldownSeconds || 60);
                this.startAuthCodeCountdown(cooldown, 'auth');
                this.showToast('验证码已发送，请注意查收', 'success');
                this.$nextTick(() => this.focusAuthCodeInput());
            } catch (error) {
                const message = error?.message || '验证码发送失败，请稍后重试';
                this.showToast(message, 'error');
            } finally {
                this.authCodeSending = false;
            }
        },

        getAuthCodeLength() {
            const length = Number(this.smsCodeLength || 6);
            if (!Number.isFinite(length)) return 6;
            return Math.max(4, Math.min(8, Math.floor(length)));
        },

        validateAuthForm() {
            const errors = { account: '', code: '' };
            const account = this.normalizeAuthPhone(this.authForm.account);
            const code = String(this.authForm.code || '').trim();
            const expectedCodeLength = this.getAuthCodeLength();

            if (!account) {
                errors.account = '请输入手机号';
            } else if (!/^1\d{10}$/.test(account)) {
                errors.account = '请输入有效手机号（11位）';
            }

            if (!new RegExp(`^\\d{${expectedCodeLength}}$`).test(code)) {
                errors.code = `请输入 ${expectedCodeLength} 位数字验证码`;
            }

            this.authErrors = errors;
            return !errors.account && !errors.code;
        },

        async submitAuth() {
            if (this.authLoading) return;

            if (!this.validateAuthForm()) {
                this.showToast('请先修正表单错误', 'warning');
                return;
            }

            const account = this.normalizeAuthPhone(this.authForm.account);
            this.authLoading = true;
            try {
                const result = await this.apiCall('/auth/login/code', {
                    method: 'POST',
                    body: JSON.stringify({
                        account,
                        code: String(this.authForm.code || '').trim(),
                        scene: 'login'
                    }),
                    skipAuthRedirect: true
                });

                this.currentUser = result?.user || null;
                this.authReady = Boolean(this.currentUser);
                this.rememberAuthAccount(account);
                this.authForm.code = '';
                this.clearAuthErrors();
                this.restoreThemeAfterAuth();
                this.showToast(result?.created ? '注册成功，已自动登录' : '登录成功', 'success');

                this.bootstrapAuthenticatedApp().catch((error) => {
                    console.error('登录后初始化失败:', error);
                });
            } catch (error) {
                this.showToast(error?.message || '登录失败，请重试', 'error');
            } finally {
                this.authLoading = false;
            }
        },

        startWechatLogin() {
            if (!this.wechatLoginEnabled || this.authLoading || this.wechatLoginLoading) return;
            if (typeof window === 'undefined') return;

            this.wechatLoginLoading = true;
            const pathname = window.location.pathname === '/' ? '/index.html' : window.location.pathname;
            const returnTo = `${pathname}${window.location.search || ''}${window.location.hash || ''}`;
            const target = `${API_BASE}/auth/wechat/start?return_to=${encodeURIComponent(returnTo)}`;
            window.location.assign(target);
        },

        startWechatBind() {
            if (!this.authReady) return;
            if (!this.canUseAccountBinding()) {
                this.showToast('仅当短信登录和微信登录同时启用时，才支持账号绑定', 'warning');
                return;
            }
            if (this.authLoading || this.wechatBindLoading) return;
            if (typeof window === 'undefined') return;

            this.showAccountMenu = false;
            this.showSettingsModal = false;
            this.wechatBindLoading = true;
            const pathname = window.location.pathname === '/' ? '/index.html' : window.location.pathname;
            const returnTo = `${pathname}${window.location.search || ''}${window.location.hash || ''}`;
            const target = `${API_BASE}/auth/bind/wechat/start?return_to=${encodeURIComponent(returnTo)}`;
            window.location.assign(target);
        },

        openBindPhoneModal() {
            if (!this.authReady || this.bindPhoneLoading) return;
            if (!this.canUseAccountBinding()) {
                this.showToast('仅当短信登录和微信登录同时启用时，才支持账号绑定', 'warning');
                return;
            }
            this.showAccountMenu = false;
            this.showSettingsModal = false;
            this.bindCodeSending = false;
            this.stopAuthCodeCountdown('bind');
            this.bindPhoneErrors = { phone: '', code: '' };
            this.bindPhoneForm.phone = String(this.currentUser?.phone || '').trim();
            this.bindPhoneForm.code = '';
            this.showBindPhoneModal = true;
            this.$nextTick(() => {
                const input = document.querySelector('[data-bind-phone-input]');
                if (input && typeof input.focus === 'function') {
                    input.focus({ preventScroll: true });
                }
            });
        },

        closeBindPhoneModal() {
            if (this.bindPhoneLoading) return;
            this.bindCodeSending = false;
            this.stopAuthCodeCountdown('bind');
            this.bindPhoneForm.code = '';
            this.bindPhoneErrors.code = '';
            this.showBindPhoneModal = false;
        },

        resetAccountMergeState(options = {}) {
            const { closeModal = true } = options;
            if (closeModal) {
                this.showAccountMergeModal = false;
            }
            this.accountMergeLoading = false;
            this.accountMergeApplyLoading = false;
            this.accountMergeError = '';
            this.accountMergePreview = null;
            this.accountMergeConfirmText = '';
        },

        closeAccountMergeModal() {
            if (this.accountMergeLoading || this.accountMergeApplyLoading) return;
            this.resetAccountMergeState({ closeModal: true });
        },

        async loadAccountMergePreview(options = {}) {
            const {
                openModal = true,
                showToastOnError = false
            } = options;
            if (!this.authReady || this.accountMergeLoading) return null;

            this.accountMergeLoading = true;
            this.accountMergeError = '';
            try {
                const result = await this.apiCall('/auth/account-merge/preview', {
                    method: 'POST',
                    body: JSON.stringify({}),
                });
                this.accountMergePreview = result || null;
                this.accountMergeConfirmText = '';
                if (openModal) {
                    this.showBindPhoneModal = false;
                    this.showSettingsModal = false;
                    this.showAccountMergeModal = true;
                }
                return result;
            } catch (error) {
                const message = error?.message || '账号合并预览加载失败，请稍后重试';
                this.accountMergeError = message;
                if (showToastOnError) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.accountMergeLoading = false;
            }
        },

        async handleAccountMergeRequired(payload = {}, options = {}) {
            const {
                message = '',
                toastType = 'warning'
            } = options;
            const conflictMessage = String(message || payload?.error || '').trim();
            if (conflictMessage) {
                this.showToast(conflictMessage, toastType);
            }
            await this.loadAccountMergePreview({ openModal: true, showToastOnError: true });
        },

        getAccountMergeAssetItems(account = null) {
            const counts = account?.asset_counts || {};
            return [
                { key: 'sessions', label: '会话', value: Number(counts.sessions || 0) },
                { key: 'reports', label: '报告', value: Number(counts.reports || 0) },
                { key: 'custom_scenarios', label: '自定义场景', value: Number(counts.custom_scenarios || 0) },
                { key: 'solution_shares', label: '分享', value: Number(counts.solution_shares || 0) },
                { key: 'licenses', label: 'License', value: Number(counts.licenses || 0) },
            ];
        },

        async applyAccountMerge() {
            if (this.accountMergeApplyLoading || !this.accountMergePreview) return;
            this.accountMergeApplyLoading = true;
            this.accountMergeError = '';
            try {
                const result = await this.apiCall('/auth/account-merge/apply', {
                    method: 'POST',
                    body: JSON.stringify({
                        preview_token: this.accountMergePreview?.preview_token || '',
                        confirm_text: String(this.accountMergeConfirmText || '').trim(),
                    }),
                });
                this.currentUser = result?.user || this.currentUser;
                this.resetAccountMergeState({ closeModal: true });
                await this.refreshLicenseStatus({ showToast: false });
                await Promise.all([
                    this.loadScenarios(),
                    this.loadSessions(),
                    this.loadReports(),
                ]);
                this.showToast(result?.message || '账号历史已并入当前账号', 'success');
            } catch (error) {
                const message = error?.message || '账号合并失败，请稍后重试';
                this.accountMergeError = message;
                this.showToast(message, 'error');
            } finally {
                this.accountMergeApplyLoading = false;
            }
        },

        focusBindCodeInput() {
            const input = document.querySelector('[data-bind-phone-code]');
            if (input && typeof input.focus === 'function') {
                input.focus({ preventScroll: true });
            }
        },

        canSendBindCode() {
            const phone = this.normalizeAuthPhone(this.bindPhoneForm.phone);
            return this.canUseAccountBinding() && /^1\d{10}$/.test(phone) && !this.bindCodeSending && this.bindCodeCountdown <= 0;
        },

        async sendBindCode() {
            if (!this.canUseAccountBinding()) {
                this.showToast('仅当短信登录和微信登录同时启用时，才支持账号绑定', 'warning');
                return;
            }
            if (!this.canSendBindCode()) return;

            const phone = this.normalizeAuthPhone(this.bindPhoneForm.phone);
            this.bindCodeSending = true;
            this.bindPhoneErrors.phone = '';
            this.bindPhoneErrors.code = '';
            try {
                const result = await this.apiCall('/auth/sms/send-code', {
                    method: 'POST',
                    body: JSON.stringify({
                        phone,
                        scene: 'bind'
                    })
                });
                const cooldown = Number(result?.cooldown_seconds || result?.retry_after || this.smsCooldownSeconds || 60);
                this.startAuthCodeCountdown(cooldown, 'bind');
                this.showToast('验证码已发送，请注意查收', 'success');
                this.$nextTick(() => this.focusBindCodeInput());
            } catch (error) {
                const message = error?.message || '验证码发送失败，请稍后重试';
                if (message.includes('手机号') || message.includes('手机')) {
                    this.bindPhoneErrors.phone = message;
                }
                this.showToast(message, 'error');
            } finally {
                this.bindCodeSending = false;
            }
        },

        validateBindPhoneForm() {
            const phone = String(this.bindPhoneForm.phone || '')
                .trim()
                .replace(/[\s-]/g, '')
                .replace(/^\+86/, '')
                .replace(/^86(?=1\d{10}$)/, '');
            const code = String(this.bindPhoneForm.code || '').trim();
            const expectedCodeLength = this.getAuthCodeLength();

            if (!/^1\d{10}$/.test(phone)) {
                this.bindPhoneErrors.phone = '请输入有效手机号（11位）';
            } else {
                this.bindPhoneErrors.phone = '';
            }

            if (!new RegExp(`^\\d{${expectedCodeLength}}$`).test(code)) {
                this.bindPhoneErrors.code = `请输入 ${expectedCodeLength} 位数字验证码`;
            } else {
                this.bindPhoneErrors.code = '';
            }

            if (this.bindPhoneErrors.phone || this.bindPhoneErrors.code) {
                return null;
            }
            return {
                phone,
                code
            };
        },

        async submitBindPhone() {
            if (this.bindPhoneLoading) return;
            if (!this.canUseAccountBinding()) {
                this.showToast('仅当短信登录和微信登录同时启用时，才支持账号绑定', 'warning');
                return;
            }
            const payload = this.validateBindPhoneForm();
            if (!payload) return;

            this.bindPhoneLoading = true;
            try {
                const result = await this.apiCall('/auth/bind/phone', {
                    method: 'POST',
                    body: JSON.stringify({
                        phone: payload.phone,
                        code: payload.code
                    })
                });
                this.currentUser = result?.user || this.currentUser;
                this.bindCodeSending = false;
                this.stopAuthCodeCountdown('bind');
                this.showBindPhoneModal = false;
                this.showToast(result?.merge_applied ? '手机号绑定成功，历史数据已自动并入当前账号' : '手机号绑定成功', 'success');
            } catch (error) {
                if (error?.payload?.merge_required) {
                    this.bindPhoneLoading = false;
                    await this.handleAccountMergeRequired(error.payload, {
                        message: error?.payload?.error || '发现另一个手机号账号已有历史数据，请确认合并后继续绑定',
                        toastType: 'warning',
                    });
                    return;
                }
                const message = error?.message || '手机号绑定失败，请稍后重试';
                if (message.includes('验证码')) {
                    this.bindPhoneErrors.code = message;
                } else if (message.includes('手机号') || message.includes('手机')) {
                    this.bindPhoneErrors.phone = message;
                } else {
                    this.bindPhoneErrors.phone = '';
                }
                this.showToast(message, 'error');
            } finally {
                this.bindPhoneLoading = false;
            }
        },

        async logout() {
            if (this.authLoading) return;
            this.showAccountMenu = false;
            this.showLogoutConfirmModal = false;
            this.authLoading = true;
            try {
                await this.apiCall('/auth/logout', { method: 'POST', skipAuthRedirect: true });
            } catch (error) {
                // 忽略退出失败，前端仍执行本地登出
            } finally {
                this.enterLoginState({
                    showToast: true,
                    toastMessage: '已退出登录',
                    toastType: 'success'
                });
            }
        },

        requestLogout() {
            this.showAccountMenu = false;
            this.showSettingsModal = false;
            this.showLogoutConfirmModal = true;
        },

        async confirmLogout() {
            if (this.authLoading) return;
            this.showLogoutConfirmModal = false;
            await this.logout();
        },
    };

    function attach(app) {
        if (!app || typeof app !== 'object') return app;

        Object.entries(authLicenseStateDefaults).forEach(([key, value]) => {
            if (typeof app[key] === 'undefined') {
                app[key] = cloneDefaultValue(value);
            }
        });

        Object.assign(app, authLicenseStateMethods);
        return app;
    }

    global.DeepVisionAuthLicenseStateModule = { attach };
})(window);

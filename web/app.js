/**
 * Deep Vision - AI 驱动的智能访谈前端
 *
 * 核心功能：
 * - 调用后端 AI API 动态生成问题和选项
 * - 支持智能追问（挖掘本质需求）
 * - 支持冲突检测（与参考文档对比）
 * - 生成专业访谈报告
 */

// 从配置文件获取 API 地址，如果配置文件未加载则使用默认值
const API_BASE = window.location.origin + '/api';
const QUESTION_REQUEST_SOFT_TIMEOUT_MS = 30000;
const QUESTION_REQUEST_HARD_TIMEOUT_MS = 90000;
const QUESTION_REQUEST_WATCHDOG_INTERVAL_MS = 1000;
const QUESTION_REQUEST_STALL_GRACE_MS = 4000;
const QUESTION_REQUEST_IDLE_MS = 2500;
const QUESTION_SUBMIT_PREFETCH_WAIT_MS = 3000;
const QUESTION_OVERLOAD_RETRY_DEFAULT_SECONDS = 2;
const QUESTION_OVERLOAD_RETRY_MAX_WAIT_MS = 20000;
const QUESTION_SUCCESS_TRANSITION_DELAY_MS = 150;
const QUESTION_TYPING_CHAR_DELAY_MS = 14;
const QUESTION_OPTION_REVEAL_DELAY_MS = 70;
const QUESTION_INTERACTION_READY_DELAY_MS = 80;

function deepVision() {
    const app = {
        // ============ 状态 ============
        currentView: 'sessions',
        currentLevelInfo: null,
        userCapabilities: {},
        allowedReportProfiles: ['balanced'],
        allowedInterviewModes: ['quick'],
        interviewModeDefault: 'quick',
        interviewModeRequirements: {},
        presentationFeatureEnabled: true,
        showSettingsModal: false,
        settingsTab: 'appearance',
        opsMetrics: null,
        opsMetricsLoading: false,
        opsMetricsError: '',
        opsMetricsLastUpdatedAt: 0,
        opsMetricsLastLoadedAt: 0,
        opsMetricsLastN: 200,
        adminTab: 'overview',
        adminLicenseSummary: null,
        adminLicenseSummaryLoading: false,
        adminLicenseSummaryError: '',
        adminLicenseEnforcementMutating: false,
        adminPresentationFeatureMutating: false,
        adminLicenseList: [],
        adminLicenseListLoading: false,
        adminLicenseListError: '',
        adminLicenseFilters: {
            status: '',
            level_key: '',
            batch_id: '',
            bound_account: '',
            note: '',
            created_from: '',
            created_to: '',
            expires_from: '',
            expires_to: '',
            is_bound: '',
            code: '',
        },
        adminLicensePagination: {
            page: 1,
            page_size: 20,
            total_pages: 0,
            count: 0,
        },
        adminLicenseSort: {
            by: 'id',
            order: 'desc',
        },
        adminLicensePageJumpInput: '',
        adminLicenseSelectedIds: [],
        adminLicenseDetailId: null,
        adminLicenseDetail: null,
        adminLicenseDetailLoading: false,
        adminLicenseEvents: [],
        adminLicenseBootstrapStatus: null,
        adminLicenseBootstrapLoading: false,
        adminLicenseBootstrapSubmitting: false,
        adminLicenseBootstrapError: '',
        adminLicenseBootstrapForm: {
            duration_days: 365,
            note: '',
        },
        adminLicenseGenerateLoading: false,
        adminLicenseGenerateForm: {
            count: 10,
            duration_days: 30,
            level_key: 'standard',
            note: '',
        },
        adminLicenseGeneratedBatch: null,
        adminLicenseBulk: {
            revoke_reason: '',
            duration_days: '',
        },
        adminLicenseDetailForm: {
            revoke_reason: '',
            duration_days: '',
        },
        adminSummariesInfo: null,
        adminSummariesLoading: false,
        adminSummariesError: '',
        adminOwnershipTargetQuery: '',
        adminOwnershipTargetResults: [],
        adminOwnershipSourceQuery: '',
        adminOwnershipSourceResults: [],
        adminOwnershipSearchLoading: false,
        adminOwnershipForm: {
            to_user_id: '',
            to_account: '',
            scope: 'unowned',
            from_user_id: '',
            from_account: '',
            kinds: ['sessions', 'reports'],
            max_examples: 20,
        },
        adminOwnershipAudit: null,
        adminOwnershipAuditLoading: false,
        adminOwnershipAuditError: '',
        adminOwnershipPreview: null,
        adminOwnershipPreviewLoading: false,
        adminOwnershipPreviewError: '',
        adminOwnershipConfirmText: '',
        adminOwnershipApplyLoading: false,
        adminOwnershipHistory: [],
        adminOwnershipHistoryLoading: false,
        adminOwnershipHistoryError: '',
        adminConfigCenter: null,
        adminConfigLoading: false,
        adminConfigError: '',
        adminConfigSource: 'env',
        adminConfigSearch: '',
        adminConfigShowSecrets: false,
        adminConfigShowAdvanced: false,
        adminConfigActiveGroupId: {
            env: '',
            config: '',
            site: '',
        },
        adminConfigDraft: {
            env: {},
            config: {},
            site: {},
        },
        adminConfigSavingKey: '',
        loading: false,
        loadingQuestion: false,
        sessionOpenRequestId: 0,
        questionRequestId: 0,
        questionRequestStartedAt: 0,
        questionRequestLastActiveAt: 0,
        questionRequestWatchdogTimer: null,
        questionRequestAbortController: null,
        questionRequestPreferPrefetch: false,
        questionOpsLocalState: {
            lastRequestAt: 0,
            lastDimension: '',
            lastResultStatus: 'idle',
            lastTier: '',
            lastLane: '',
            lastProfile: '',
            lastFastHedge: null,
            lastFullHedge: null,
            lastHedgeTriggered: false,
            lastFallbackTriggered: false,
            lastOverloadRetryCount: 0,
            lastOverloadWaitMs: 0,
            lastPreferPrefetch: false,
            lastError: ''
        },
        thinkingPollRequestId: 0,
        webSearchPollRequestId: 0,
        scenarioRecognizeRequestId: 0,
        isGoingPrev: false,
        submitting: false,  // 提交答案进行中，防止并发操作
        generatingReport: false,
        generatingReportSessionId: '',
        reportProfileDefault: 'balanced',
        reportProfile: 'balanced',
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
        webSearching: false,  // Web Search API 调用状态
        webSearchPollInterval: null,  // Web Search 状态轮询定时器
        quoteRotationInterval: null,  // 诗句轮播定时器
        currentTipIndex: 0,  // 访谈小技巧当前索引
        currentTip: '',  // 当前显示的小技巧文本
        tipRotationInterval: null,  // 小技巧轮播定时器
        themeStorageKey: 'deepvision_theme_mode',
        appShellSnapshotStorageKey: 'deepvision_app_shell_snapshot',
        appShellSnapshotVersion: 1,
        appShellSnapshotPersistTimer: null,
        themeMode: 'system',
        effectiveTheme: 'light',
        visualPreset: (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.visualPresets?.default) || 'rational',
        showAccountMenu: false,
        dialogFocusWatchRegistered: false,
        dialogFocusReturnTargets: {},
        dialogTabTrapRegistered: false,
        dialogTabTrapListener: null,
        dialogA11yConfig: (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.a11y?.dialogs) ? SITE_CONFIG.a11y.dialogs : {},
        toastA11yConfig: (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.a11y?.toast) ? SITE_CONFIG.a11y.toast : {},
        managedDialogKeys: [
            'showNewSessionModal',
            'showCustomScenarioModal',
            'showAiGenerateModal',
            'showAiPreviewModal',
            'showDeleteModal',
            'showLogoutConfirmModal',
            'showRestartModal',
            'showDeleteDocModal',
            'showDeleteReportModal',
            'showSettingsModal',
            'showBindPhoneModal',
            'showAccountMergeModal',
            'showActionConfirmModal',
            'showBatchDeleteModal'
        ],
        systemThemeMedia: null,
        systemThemeListener: null,
        showGuide: false,
        guideStepIndex: 0,
        hasSeenGuide: false,
        guideSpotlightStyle: '',
        guideCardStyle: '',
        guideCloseHintLastAt: 0,
        guideHighlightedEl: null,
        guideResizeObserver: null,
        guideObservedEl: null,
        guideObservedModal: null,
        guideSteps: [
            {
                id: 'new-session',
                selector: '[data-guide="guide-new-session"]',
                title: '第一步：创建一次访谈',
                body: '点击新建访谈，开始第一次调研。',
                cta: '开始',
                onEnter: function () {
                    this.currentView = 'sessions';
                },
                onNext: function () {
                    this.resetScenarioSelection();
                    this.showNewSessionModal = true;
                }
            },
            {
                id: 'topic',
                selector: '[data-guide="guide-topic"]',
                title: '第二步：一句话目标',
                body: '只需一句话说明目标即可开始。',
                cta: '下一步',
                onEnter: function () {
                    if (!this.showNewSessionModal) {
                        this.resetScenarioSelection();
                        this.showNewSessionModal = true;
                    }
                    this.$nextTick(() => {
                        const el = document.querySelector('[data-guide="guide-topic"]');
                        if (el) el.focus();
                    });
                },
                onNext: function () {
                    if (!this.newSessionTopic.trim()) {
                        this.showToast('请先输入一句话目标', 'warning');
                        const el = document.querySelector('[data-guide="guide-topic"]');
                        if (el) el.focus();
                        return false;
                    }
                    return true;
                }
            },
            {
                id: 'scenario',
                selector: '[data-guide="guide-scenario"]',
                title: '第三步：选择场景',
                body: '选一个场景，问题会自动贴合行业语境。',
                cta: '下一步',
                onEnter: function () {
                    if (!this.showNewSessionModal) {
                        this.resetScenarioSelection();
                        this.showNewSessionModal = true;
                    }
                }
            },
            {
                id: 'start',
                selector: '[data-guide="guide-start"]',
                title: '最终确认',
                body: '确认无误后，点击开始进入访谈。',
                cta: '开始访谈',
                onEnter: function () {
                    if (!this.showNewSessionModal) {
                        this.resetScenarioSelection();
                        this.showNewSessionModal = true;
                    }
                },
                onNext: async function () {
                    if (!this.newSessionTopic.trim()) {
                        this.showToast('请先输入一句话目标', 'warning');
                        return false;
                    }
                    await this.createNewSession();
                    this.completeGuide();
                    return false;
                }
            }
        ],
        guideStepTotal: 3,

        // ========== 方案B+D 新增状态变量 ==========
        thinkingStage: null,           // 思考阶段数据
        thinkingPollInterval: null,    // 轮询定时器
        skeletonMode: false,           // 骨架填充模式
        typingText: '',                // 打字机文字
        typingComplete: false,         // 打字完成标记
        optionsVisible: [],            // 选项可见性数组
        interactionReady: false,       // 交互就绪标记

        // 服务状态
        serverStatus: null,
        aiAvailable: false,
        interviewDepthV2: {
            enabled: true,
            modes: ['quick', 'standard', 'deep'],
            deep_mode_skip_followup_confirm: true,
            mode_configs: null
        },

        // 会话相关
        currentSession: null,
        newSessionTopic: '',
        newSessionDescription: '',
        selectedInterviewMode: 'deep',  // 默认深度模式
        hoveredDepthMode: null,  // 深度选项悬停状态
        showScenarioSelector: false,  // 场景选择器面板
        scenarioSearchQuery: '',  // 场景搜索关键词
        showNewSessionModal: false,
        showDeleteModal: false,
        sessionToDelete: null,
        showActionConfirmModal: false,
        actionConfirmDialog: {
            title: '',
            message: '',
            tone: 'warning',
            confirmText: '确认',
            cancelText: '取消'
        },
        actionConfirmResolve: null,

        // 确认重新开始访谈对话框
        showRestartModal: false,

        // 确认删除文档对话框
        showDeleteDocModal: false,
        docToDelete: null,
        docDeleteCallback: null,

        // 拖放上传状态
        isDraggingDoc: false,
        isDraggingResearch: false,

        interviewTopicMinHeight: 0,

        // 批量删除
        showBatchDeleteModal: false,
        batchDeleteTarget: 'sessions',
        batchDeleteLoading: false,
        batchDeleteAlsoReports: false,
        batchDeleteSummary: {
            items: 0,
            sessions: 0,
            reports: 0
        },

        // 访谈相关
        interviewSteps: ['文档准备', '选择式访谈', '需求确认'],
        currentStep: 0,
        dimensionOrder: ['customer_needs', 'business_process', 'tech_constraints', 'project_constraints'],
        currentDimension: 'customer_needs',

        // 场景相关
        scenarios: [],
        selectedScenario: null,
        showScenarioSelector: false,
        scenarioLoaded: false,

        // 场景专属提示文案配置
        scenarioPlaceholders: {
            'product-requirement': {
                topic: '例如：CRM系统需求访谈、电商平台功能规划',
                description: '例如：公司目前有200+销售人员，使用Excel管理客户信息效率低下。希望引入专业的CRM系统，重点解决客户跟进记录、销售漏斗管理和数据分析问题。预算范围50-100万，计划3个月内上线。'
            },
            'user-research': {
                topic: '例如：外卖App用户体验调研、老年人智能手机使用习惯',
                description: '例如：我们的外卖App月活用户500万，但30天留存率只有15%。希望了解用户流失原因，重点关注下单流程体验、配送时效满意度、以及与竞品的对比感受。'
            },
            'tech-solution': {
                topic: '例如：微服务架构升级方案、数据中台建设规划',
                description: '例如：当前系统是单体架构，日均请求量1000万，高峰期响应时间超过3秒。团队有10名后端开发，希望在保证业务连续性的前提下，逐步迁移到微服务架构。'
            },
            'business-model': {
                topic: '例如：SaaS产品商业化路径、社区团购盈利模式',
                description: '例如：我们的协同办公SaaS产品已有5000家企业试用，但付费转化率不到5%。希望探讨定价策略、增值服务设计、以及企业客户的付费决策因素。'
            },
            'competitive-analysis': {
                topic: '例如：在线教育行业竞品分析、新能源汽车市场格局',
                description: '例如：我们是K12在线教育赛道的新进入者，主要竞品包括猿辅导、作业帮、好未来。希望深入了解各家的产品定位、获客策略、课程体系差异和技术壁垒。'
            },
            'problem-diagnosis': {
                topic: '例如：用户转化率下降原因分析、团队协作效率问题诊断',
                description: '例如：最近3个月，我们的付费转化率从8%下降到4%，但流量和用户质量没有明显变化。已排除价格因素，怀疑与产品改版、竞品活动或用户需求变化有关。'
            },
            'bidding-tendering': {
                topic: '例如：政务云平台建设项目、智慧园区解决方案招标',
                description: '例如：某市政府计划建设统一的政务云平台，预算3000万，要求支持50+委办局业务上云，需满足等保三级要求。我方作为投标方，需要了解甲方核心诉求和评分重点。'
            },
            'interview-assessment': {
                topic: '例如：高级产品经理候选人评估、技术总监能力面试',
                description: '例如：候选人应聘高级产品经理岗位，简历显示有5年B端产品经验，主导过2个千万级项目。本次面试重点评估其需求分析能力、跨部门协调能力和商业思维。'
            },
            'default': {
                topic: '例如：请输入本次访谈的主题',
                description: '例如：请描述本次访谈的背景、目标和关注重点，帮助AI生成更精准的访谈问题。'
            }
        },

        // 场景自动识别
        recognizing: false,           // 识别中状态
        recognizeTimer: null,         // 防抖定时器
        recognizedResult: null,       // 识别结果 {recommended, confidence, alternatives}
        autoRecognizeEnabled: true,   // 是否启用自动识别
        activeRecognizeFingerprint: '',
        documentUploading: false,

        // 当前问题（AI 生成）
        currentQuestion: {
            text: '',
            options: [],
            multiSelect: false,  // 是否多选
            questionMultiSelect: false,
            isFollowUp: false,
            followUpReason: null,
            answerMode: 'pick_only',
            requiresRationale: false,
            evidenceIntent: 'low',
            questionGenerationTier: '',
            questionSelectedLane: '',
            questionRuntimeProfile: '',
            decisionMeta: null,
            conflictDetected: false,
            conflictDescription: null,
            aiGenerated: false,
            aiRecommendation: null
        },
        aiRecommendationExpanded: false,
        aiRecommendationApplied: false,
        aiRecommendationPrevSelection: null,
        selectedAnswers: [],  // 改用数组支持多选
        rationaleText: '',
        otherAnswerText: '',
        otherSelected: false,  // "其他"选项是否被选中
        singleSelectDisambiguationActive: false,
        singleSelectDisambiguationOptions: [],
        singleSelectDisambiguationRawText: '',

        // Toast 通知
        toast: {
            show: false,
            message: '',
            type: 'success',
            actionLabel: '',
            actionUrl: '',
            role: 'status',
            ariaLive: 'polite',
            ariaAtomic: true,
            announceMode: 'polite'
        },
        toastTimer: null,

        // 版本信息
        appVersion: (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.version?.current) || '1.0.0',

        // 产品介绍
        showIntroPage: false,

        // 诗句轮播（从配置文件加载）
        quotes: (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.quotes?.items)
            ? SITE_CONFIG.quotes.items
            : [
                { text: '路漫漫其修远兮，吾将上下而求索', source: '——屈原《离骚》' },
                { text: '问渠那得清如许，为有源头活水来', source: '——朱熹《观书有感》' },
                { text: '千里之行始于足下，万象之理源于细微', source: '——老子《道德经》' }
            ],
        currentQuoteIndex: 0,
        currentQuote: '',  // 初始化时动态设置
        currentQuoteSource: '',  // 初始化时动态设置

        // 维度名称
        dimensionNames: {
            customer_needs: '客户需求',
            business_process: '业务流程',
            tech_constraints: '技术约束',
            project_constraints: '项目约束'
        },

        // ============ 初始化 ============
        async init() {
            // 初始化诗句轮播
            if (this.quotes.length > 0) {
                this.currentQuote = this.quotes[0].text;
                this.currentQuoteSource = this.quotes[0].source;
            }

            this.visualPreset = this.resolveVisualPreset();
            this.applyDesignTokens('system', this.resolveEffectiveTheme('system'));
            this.initTheme();
            this.loadAuthAccountHistory();
            this.readAuthRedirectResult();
            this.registerDialogFocusWatchers();
            await Promise.all([
                this.loadVersionInfo(),
                this.checkServerStatus()
            ]);
            await this.checkAuthStatus();

            if (!this.authReady) {
                await this.consumeAuthRedirectToast();
                this.enforceAuthViewLightTheme();
                this.authChecking = false;
                return;
            }

            const hasStatusLicensePayload = this.serverStatus?.authenticated === true && Boolean(this.serverStatus?.license);
            if (!hasStatusLicensePayload) {
                await this.refreshLicenseStatus({ showToast: false });
            }
            this.authChecking = false;
            await this.consumeAuthRedirectToast();
            if (!this.authReady || this.licenseChecking || this.licenseGateActive) {
                return;
            }
            this.restoreAppShellSnapshot();
            this.bootstrapAuthenticatedApp({ skipLicenseRefresh: hasStatusLicensePayload }).catch((error) => {
                console.error('登录后初始化失败:', error);
            });

            // 初始化虚拟列表
            this.$nextTick(() => {
                this.setupVirtualList();
                this.setupVirtualReportList();
            });
        },

        canUseSessionStorage() {
            try {
                return typeof sessionStorage !== 'undefined';
            } catch (error) {
                return false;
            }
        },

        normalizePersistedAppShellView(view = '') {
            const normalized = String(view || '').trim().toLowerCase();
            if (normalized === 'admin') return 'admin';
            if (normalized === 'reports') return 'reports';
            return 'sessions';
        },

        getAppShellSnapshotUserKey(user = this.currentUser) {
            const source = user && typeof user === 'object' ? user : {};
            const userId = Number(source.id || 0);
            const phone = String(source.phone || '').trim();
            const account = String(source.account || '').trim();
            return [
                userId > 0 ? `id:${userId}` : '',
                phone ? `phone:${phone}` : '',
                account ? `account:${account}` : ''
            ].filter(Boolean).join('|');
        },

        clearAppShellSnapshot() {
            if (this.appShellSnapshotPersistTimer) {
                clearTimeout(this.appShellSnapshotPersistTimer);
                this.appShellSnapshotPersistTimer = null;
            }
            if (!this.canUseSessionStorage()) return;
            try {
                sessionStorage.removeItem(this.appShellSnapshotStorageKey);
            } catch (error) {
                console.warn('清理页面快照失败:', error);
            }
        },

        scheduleAppShellSnapshotPersist() {
            if (this.appShellSnapshotPersistTimer) {
                clearTimeout(this.appShellSnapshotPersistTimer);
            }
            this.appShellSnapshotPersistTimer = setTimeout(() => {
                this.appShellSnapshotPersistTimer = null;
                this.persistAppShellSnapshot();
            }, 120);
        },

        persistAppShellSnapshot() {
            if (!this.canUseSessionStorage()) return;
            if (!this.authReady || this.licenseGateActive) {
                this.clearAppShellSnapshot();
                return;
            }

            const payload = {
                version: this.appShellSnapshotVersion,
                userKey: this.getAppShellSnapshotUserKey(),
                updatedAt: Date.now(),
                currentView: this.normalizePersistedAppShellView(this.currentView),
                sessionSearchQuery: String(this.sessionSearchQuery || ''),
                sessionStatusFilter: String(this.sessionStatusFilter || 'all'),
                sessionSortOrder: String(this.sessionSortOrder || 'newest'),
                sessionGroupBy: String(this.sessionGroupBy || 'none'),
                currentPage: Number.isFinite(Number(this.currentPage)) ? Math.max(1, Math.floor(Number(this.currentPage))) : 1,
                reportSearchQuery: String(this.reportSearchQuery || ''),
                reportSortOrder: String(this.reportSortOrder || 'newest'),
                reportGroupBy: String(this.reportGroupBy || 'none'),
                sessionsLoaded: Boolean(this.sessionsLoaded),
                reportsLoaded: Boolean(this.reportsLoaded),
                sessions: this.sessionsLoaded && Array.isArray(this.sessions) ? this.sessions : [],
                reports: this.reportsLoaded && Array.isArray(this.reports) ? this.reports : [],
            };

            try {
                sessionStorage.setItem(this.appShellSnapshotStorageKey, JSON.stringify(payload));
            } catch (error) {
                console.warn('保存页面快照失败:', error);
            }
        },

        restoreAppShellSnapshot() {
            if (!this.canUseSessionStorage() || !this.authReady) return false;

            let payload = null;
            try {
                const raw = sessionStorage.getItem(this.appShellSnapshotStorageKey);
                if (!raw) return false;
                payload = JSON.parse(raw);
            } catch (error) {
                this.clearAppShellSnapshot();
                return false;
            }

            if (!payload || typeof payload !== 'object') {
                this.clearAppShellSnapshot();
                return false;
            }
            if (Number(payload.version || 0) !== Number(this.appShellSnapshotVersion || 0)) {
                this.clearAppShellSnapshot();
                return false;
            }

            const expectedUserKey = this.getAppShellSnapshotUserKey();
            const snapshotUserKey = String(payload.userKey || '').trim();
            if (!expectedUserKey || !snapshotUserKey || snapshotUserKey !== expectedUserKey) {
                this.clearAppShellSnapshot();
                return false;
            }

            const restoredView = this.normalizePersistedAppShellView(payload.currentView);
            this.currentView = restoredView === 'admin' && !this.canViewAdminCenter()
                ? 'sessions'
                : restoredView;
            this.sessionSearchQuery = String(payload.sessionSearchQuery || '');
            this.sessionStatusFilter = String(payload.sessionStatusFilter || 'all') || 'all';
            this.sessionSortOrder = String(payload.sessionSortOrder || 'newest') || 'newest';
            this.sessionGroupBy = String(payload.sessionGroupBy || 'none') || 'none';
            this.reportSearchQuery = String(payload.reportSearchQuery || '');
            this.reportSortOrder = String(payload.reportSortOrder || 'newest') || 'newest';
            this.reportGroupBy = String(payload.reportGroupBy || 'none') || 'none';
            this.currentPage = Number.isFinite(Number(payload.currentPage))
                ? Math.max(1, Math.floor(Number(payload.currentPage)))
                : 1;

            const restoredSessions = Array.isArray(payload.sessions)
                ? payload.sessions.filter(item => item && typeof item === 'object')
                : [];
            const restoredReports = Array.isArray(payload.reports)
                ? payload.reports.filter(item => item && typeof item === 'object')
                : [];

            let restored = false;
            if (Boolean(payload.sessionsLoaded)) {
                this.sessions = restoredSessions;
                this.sessionsLoaded = true;
                this.filterSessions({ preservePage: true });
                restored = true;
            }

            if (Boolean(payload.reportsLoaded)) {
                this.reports = restoredReports;
                this.reportsLoaded = true;
                this.filterReports();
                restored = true;
            }

            return restored;
        },

        normalizeReportProfile(profile, fallback = 'balanced') {
            const raw = String(profile || '').trim().toLowerCase();
            if (raw === 'balanced' || raw === 'quality') return raw;
            const fallbackValue = String(fallback || '').trim().toLowerCase();
            if (!fallbackValue) return '';
            if (fallbackValue === 'balanced' || fallbackValue === 'quality') return fallbackValue;
            return 'balanced';
        },

        buildDefaultLevelInfo() {
            return {
                key: 'experience',
                name: '体验版',
                description: '适合体验核心报告生成能力',
                sort_order: 10,
            };
        },

        buildDefaultUserCapabilities() {
            return {
                'report.generate': true,
                'report.profile.quality': false,
                'report.export.basic': false,
                'report.export.docx': false,
                'report.export.appendix': false,
                'solution.view': false,
                'solution.share': false,
                'presentation.generate': false,
                'interview.mode.quick': true,
                'interview.mode.standard': false,
                'interview.mode.deep': false,
            };
        },

        normalizeAllowedReportProfiles(profiles) {
            const normalized = [];
            if (Array.isArray(profiles)) {
                profiles.forEach((item) => {
                    const profile = this.normalizeReportProfile(item, '');
                    if (profile && !normalized.includes(profile)) {
                        normalized.push(profile);
                    }
                });
            }
            return normalized.length > 0 ? normalized : ['balanced'];
        },

        normalizeInterviewMode(mode, fallback = 'quick') {
            const raw = String(mode || '').trim().toLowerCase();
            if (raw === 'quick' || raw === 'standard' || raw === 'deep') return raw;
            const fallbackValue = String(fallback || '').trim().toLowerCase();
            if (fallbackValue === 'quick' || fallbackValue === 'standard' || fallbackValue === 'deep') {
                return fallbackValue;
            }
            return 'quick';
        },

        normalizeAllowedInterviewModes(modes) {
            const normalized = [];
            if (Array.isArray(modes)) {
                modes.forEach((item) => {
                    const mode = this.normalizeInterviewMode(item, '');
                    if (mode && !normalized.includes(mode)) {
                        normalized.push(mode);
                    }
                });
            }
            return normalized.length > 0 ? normalized : ['quick'];
        },

        resetUserLevelState() {
            this.currentLevelInfo = this.buildDefaultLevelInfo();
            this.userCapabilities = this.buildDefaultUserCapabilities();
            this.allowedReportProfiles = ['balanced'];
            this.reportProfileDefault = 'balanced';
            this.allowedInterviewModes = ['quick'];
            this.interviewModeDefault = 'quick';
            this.interviewModeRequirements = {};
            if (!this.canUseReportProfile(this.reportProfile)) {
                this.reportProfile = 'balanced';
            }
            if (!this.canUseInterviewMode(this.selectedInterviewMode)) {
                this.selectedInterviewMode = this.interviewModeDefault;
            }
            if (!this.canGeneratePresentation()) {
                this.presentationPdfUrl = '';
                this.presentationLocalUrl = '';
                this.presentationExecutionId = '';
            }
        },

        applyPresentationFeaturePayload(payload = {}) {
            const enabled = payload?.presentation_feature_enabled !== false;
            this.presentationFeatureEnabled = enabled;
            if (this.serverStatus && typeof this.serverStatus === 'object') {
                this.serverStatus = {
                    ...this.serverStatus,
                    presentation_feature_enabled: enabled,
                    presentation_feature_source: String(payload?.presentation_feature_source || this.serverStatus.presentation_feature_source || 'env_default'),
                };
            }
            if (!enabled) {
                this.presentationPdfUrl = '';
                this.presentationLocalUrl = '';
                this.presentationExecutionId = '';
                this.stopPresentationPolling();
                this.resetPresentationProgressFeedback();
            }
        },

        applyUserLevelPayload(payload = {}) {
            const incomingLevel = payload?.level && typeof payload.level === 'object' ? payload.level : {};
            const levelKey = String(incomingLevel?.key || '').trim().toLowerCase() || 'experience';
            const defaultLevelInfo = this.buildDefaultLevelInfo();
            this.currentLevelInfo = {
                ...defaultLevelInfo,
                ...incomingLevel,
                key: ['experience', 'standard', 'professional'].includes(levelKey) ? levelKey : defaultLevelInfo.key,
            };

            const defaultCapabilities = this.buildDefaultUserCapabilities();
            const capabilityPayload = payload?.capabilities && typeof payload.capabilities === 'object' ? payload.capabilities : {};
            this.userCapabilities = Object.fromEntries(
                Object.entries(defaultCapabilities).map(([key, fallback]) => [key, Boolean(capabilityPayload?.[key] ?? fallback)])
            );

            this.allowedReportProfiles = this.normalizeAllowedReportProfiles(payload?.allowed_report_profiles);
            const preferredProfile = this.normalizeReportProfile(
                payload?.report_profile_default,
                this.serverStatus?.report_profile_default || this.reportProfileDefault || 'balanced'
            ) || 'balanced';
            this.reportProfileDefault = this.allowedReportProfiles.includes(preferredProfile)
                ? preferredProfile
                : (this.allowedReportProfiles[0] || 'balanced');
            if (!this.canUseReportProfile(this.reportProfile)) {
                this.reportProfile = this.reportProfileDefault;
            }

            this.allowedInterviewModes = this.normalizeAllowedInterviewModes(payload?.allowed_interview_modes);
            this.interviewModeDefault = this.normalizeInterviewMode(
                payload?.interview_mode_default,
                this.allowedInterviewModes[0] || 'quick'
            );
            if (!this.allowedInterviewModes.includes(this.interviewModeDefault)) {
                this.interviewModeDefault = this.allowedInterviewModes[0] || 'quick';
            }
            this.interviewModeRequirements = payload?.interview_mode_requirements && typeof payload.interview_mode_requirements === 'object'
                ? payload.interview_mode_requirements
                : {};
            if (!this.canUseInterviewMode(this.selectedInterviewMode)) {
                this.selectedInterviewMode = this.interviewModeDefault;
            }

            if (!this.canGeneratePresentation()) {
                this.presentationPdfUrl = '';
                this.presentationLocalUrl = '';
                this.presentationExecutionId = '';
                this.stopPresentationPolling();
                this.resetPresentationProgressFeedback();
            }

            if (this.selectedReport && this.reportContent && !this.reportDetailEnhancing) {
                this.$nextTick(() => this.scheduleReportDetailEnhancement());
            }
        },

        hasLevelCapability(capabilityKey = '') {
            const normalized = String(capabilityKey || '').trim();
            if (!normalized) return false;
            return Boolean(this.userCapabilities?.[normalized]);
        },

        canUseReportProfile(profile) {
            const normalized = this.normalizeReportProfile(profile, '');
            return !!normalized && Array.isArray(this.allowedReportProfiles) && this.allowedReportProfiles.includes(normalized);
        },

        canGenerateQualityReport() {
            return this.hasLevelCapability('report.profile.quality');
        },

        shouldShowReportProfileSelector() {
            return false;
        },

        canUseInterviewMode(mode) {
            const normalized = this.normalizeInterviewMode(mode, '');
            return !!normalized
                && Array.isArray(this.allowedInterviewModes)
                && this.allowedInterviewModes.includes(normalized)
                && this.hasLevelCapability(`interview.mode.${normalized}`);
        },

        getInterviewModeRequirementLabel(mode) {
            const normalized = this.normalizeInterviewMode(mode, '');
            const requirement = this.interviewModeRequirements?.[normalized] || {};
            return String(requirement?.name || requirement?.label || '').trim();
        },

        handleInterviewModeSelect(mode) {
            const normalized = this.normalizeInterviewMode(mode, this.interviewModeDefault || 'quick');
            if (!this.canUseInterviewMode(normalized)) {
                const requirement = this.interviewModeRequirements?.[normalized];
                this.showToast(this.getLevelCapabilityDeniedMessage({
                    required_level: requirement,
                    upgrade_hint: requirement?.description || '',
                }), 'warning');
                return;
            }
            this.selectedInterviewMode = normalized;
        },

        getReportProfileLabel(profile = '') {
            const normalized = this.normalizeReportProfile(profile, '');
            if (normalized === 'quality') return '精审模式（质量优先）';
            return '平衡模式（推荐）';
        },

        getReportProfileDescription(profile = '') {
            const normalized = this.normalizeReportProfile(profile, '');
            if (normalized === 'quality') {
                return '内容更严谨，但等待时间更长。';
            }
            return '速度更快，适合日常快速生成。';
        },

        getReportProfileSummaryText() {
            return '平衡模式出结果更快；精审模式会增加审稿与校验，质量更高但耗时更长。';
        },

        canExportFormat(scope = 'report', format = 'md') {
            const normalizedScope = scope === 'appendix' ? 'appendix' : 'report';
            const normalizedFormat = String(format || '').trim().toLowerCase();
            if (normalizedScope === 'appendix') {
                return this.hasLevelCapability('report.export.appendix');
            }
            if (normalizedFormat === 'docx') {
                return this.hasLevelCapability('report.export.docx');
            }
            if (normalizedFormat === 'md' || normalizedFormat === 'pdf') {
                return this.hasLevelCapability('report.export.basic');
            }
            return false;
        },

        canExportReportBasic() {
            return this.hasLevelCapability('report.export.basic');
        },

        canExportReportDocx() {
            return this.hasLevelCapability('report.export.docx');
        },

        canExportAppendix() {
            return this.hasLevelCapability('report.export.appendix');
        },

        hasAnyReportDownloadOption() {
            return this.canExportReportBasic() || this.canExportReportDocx();
        },

        canViewSolutionPage() {
            return this.hasLevelCapability('solution.view');
        },

        canShareSolutionPage() {
            return this.hasLevelCapability('solution.share');
        },

        canGeneratePresentation() {
            return this.hasLevelCapability('presentation.generate');
        },

        getLevelCapabilityDeniedMessage(payload = {}) {
            const requiredLevelName = String(payload?.required_level?.name || '').trim();
            if (requiredLevelName) {
                return `当前功能需升级到${requiredLevelName}后使用`;
            }
            return String(payload?.upgrade_hint || payload?.error || '当前用户级别暂未开放该功能').trim() || '当前用户级别暂未开放该功能';
        },

        openSettingsModal(tab = 'appearance') {
            if (!this.authReady) return;
            this.switchSettingsTab(tab, { forceOpen: true });
            this.showAccountMenu = false;
            this.showSettingsModal = true;
        },

        closeSettingsModal() {
            this.showSettingsModal = false;
        },

        switchSettingsTab(tab = 'appearance', options = {}) {
            const { forceOpen = false } = options;
            let normalizedTab = 'appearance';
            if (tab === 'account') {
                normalizedTab = 'account';
            }
            this.settingsTab = normalizedTab;
            if (forceOpen) {
                this.showSettingsModal = true;
            }
        },

        canViewOpsMetrics() {
            return !!this.currentUser?.is_admin;
        },

        canViewAdminCenter() {
            return !!this.currentUser?.is_admin;
        },

        canManageAdminLicenses() {
            return this.canViewAdminCenter() && !!this.hasValidLicense;
        },

        isAdminViewActive() {
            return this.currentView === 'admin';
        },

        toDateTimeLocalValue(input = null) {
            const date = input instanceof Date ? input : new Date(input || Date.now());
            if (!Number.isFinite(date.getTime())) return '';
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            return `${year}-${month}-${day}T${hours}:${minutes}`;
        },

        normalizeDateTimeInputToIso(value = '') {
            const raw = String(value || '').trim();
            if (!raw) return '';
            const parsed = new Date(raw);
            if (!Number.isFinite(parsed.getTime())) {
                return raw;
            }
            return parsed.toISOString().replace('Z', '+00:00');
        },

        formatIsoToDateTimeInput(value = '') {
            const raw = String(value || '').trim();
            if (!raw) return '';
            return this.toDateTimeLocalValue(raw);
        },

        normalizePositiveIntInput(value, fallback = 0) {
            const parsed = Number.parseInt(String(value ?? '').trim(), 10);
            if (!Number.isFinite(parsed) || parsed <= 0) {
                return fallback;
            }
            return parsed;
        },

        createDefaultAdminLicenseGenerateForm() {
            return {
                count: 10,
                duration_days: 30,
                level_key: 'standard',
                note: '',
            };
        },

        createDefaultAdminLicenseBootstrapForm() {
            return {
                duration_days: 365,
                note: '管理员首个种子 License',
            };
        },

        createDefaultAdminLicensePagination() {
            return {
                page: 1,
                page_size: 20,
                total_pages: 0,
                count: 0,
            };
        },

        createDefaultAdminLicenseSort() {
            return {
                by: 'id',
                order: 'desc',
            };
        },

        resetAdminCenterState() {
            this.adminTab = 'overview';
            this.adminLicenseSummary = null;
            this.adminLicenseSummaryLoading = false;
            this.adminLicenseSummaryError = '';
            this.adminLicenseEnforcementMutating = false;
            this.adminLicenseList = [];
            this.adminLicenseListLoading = false;
            this.adminLicenseListError = '';
            this.adminLicenseFilters = {
                status: '',
                level_key: '',
                batch_id: '',
                bound_account: '',
                note: '',
                created_from: '',
                created_to: '',
                expires_from: '',
                expires_to: '',
                is_bound: '',
                code: '',
            };
            this.adminLicensePagination = this.createDefaultAdminLicensePagination();
            this.adminLicenseSort = this.createDefaultAdminLicenseSort();
            this.adminLicensePageJumpInput = '';
            this.adminLicenseSelectedIds = [];
            this.adminLicenseDetailId = null;
            this.adminLicenseDetail = null;
            this.adminLicenseDetailLoading = false;
            this.adminLicenseEvents = [];
            this.adminLicenseBootstrapStatus = null;
            this.adminLicenseBootstrapLoading = false;
            this.adminLicenseBootstrapSubmitting = false;
            this.adminLicenseBootstrapError = '';
            this.adminLicenseBootstrapForm = this.createDefaultAdminLicenseBootstrapForm();
            this.adminLicenseGenerateLoading = false;
            this.adminLicenseGenerateForm = this.createDefaultAdminLicenseGenerateForm();
            this.adminLicenseGeneratedBatch = null;
            this.adminLicenseBulk = {
                revoke_reason: '',
                duration_days: '',
            };
            this.adminLicenseDetailForm = {
                revoke_reason: '',
                duration_days: '',
            };
            this.adminSummariesInfo = null;
            this.adminSummariesLoading = false;
            this.adminSummariesError = '';
            this.adminOwnershipTargetQuery = '';
            this.adminOwnershipTargetResults = [];
            this.adminOwnershipSourceQuery = '';
            this.adminOwnershipSourceResults = [];
            this.adminOwnershipSearchLoading = false;
            this.adminOwnershipForm = {
                to_user_id: '',
                to_account: '',
                scope: 'unowned',
                from_user_id: '',
                from_account: '',
                kinds: ['sessions', 'reports'],
                max_examples: 20,
            };
            this.adminOwnershipAudit = null;
            this.adminOwnershipAuditLoading = false;
            this.adminOwnershipAuditError = '';
            this.adminOwnershipPreview = null;
            this.adminOwnershipPreviewLoading = false;
            this.adminOwnershipPreviewError = '';
            this.adminOwnershipConfirmText = '';
            this.adminOwnershipApplyLoading = false;
            this.adminOwnershipHistory = [];
            this.adminOwnershipHistoryLoading = false;
            this.adminOwnershipHistoryError = '';
            this.adminConfigCenter = null;
            this.adminConfigLoading = false;
            this.adminConfigError = '';
            this.adminConfigSource = 'env';
            this.adminConfigSearch = '';
            this.adminConfigShowSecrets = false;
            this.adminConfigShowAdvanced = false;
            this.adminConfigActiveGroupId = {
                env: '',
                config: '',
                site: '',
            };
            this.adminConfigDraft = {
                env: {},
                config: {},
                site: {},
            };
            this.adminConfigSavingKey = '';
        },

        clearAdminGeneratedLicenseBatch() {
            this.adminLicenseGeneratedBatch = null;
        },

        openAdminCenter(tab = 'overview') {
            if (!this.canViewAdminCenter()) return;
            this.showAccountMenu = false;
            this.showSettingsModal = false;
            this.switchView('admin');
            this.switchAdminTab(tab);
        },

        switchAdminTab(tab = 'overview') {
            if (!this.canViewAdminCenter()) return;
            const allowedTabs = ['overview', 'license', 'ops', 'summaries', 'ownership', 'config'];
            const normalizedTab = allowedTabs.includes(tab) ? tab : 'overview';
            this.adminTab = normalizedTab;
            void this.ensureAdminDataForTab(normalizedTab);
        },

        async ensureAdminDataForTab(tab = this.adminTab) {
            if (!this.canViewAdminCenter()) return;
            if (tab === 'overview') {
                await this.loadAdminOverview();
                return;
            }
            if (tab === 'license') {
                this.adminLicenseBootstrapForm = {
                    ...this.createDefaultAdminLicenseBootstrapForm(),
                    ...this.adminLicenseBootstrapForm,
                    duration_days: this.normalizePositiveIntInput(
                        this.adminLicenseBootstrapForm?.duration_days,
                        this.createDefaultAdminLicenseBootstrapForm().duration_days,
                    ),
                };
                await this.loadAdminLicenseBootstrapStatus({ silent: true });
                this.adminLicenseGenerateForm = {
                    ...this.createDefaultAdminLicenseGenerateForm(),
                    ...this.adminLicenseGenerateForm,
                    duration_days: this.normalizePositiveIntInput(
                        this.adminLicenseGenerateForm?.duration_days,
                        this.createDefaultAdminLicenseGenerateForm().duration_days,
                    ),
                };
                if (this.canManageAdminLicenses()) {
                    await Promise.all([
                        this.loadAdminLicenseSummary(),
                        this.loadAdminLicenseList({ page: this.adminLicensePagination.page || 1 }),
                    ]);
                } else {
                    this.adminLicenseSummaryError = this.adminLicenseBootstrapStatus?.eligible
                        ? '当前账号尚未绑定有效 License，可先创建并绑定首个种子 License。'
                        : '当前账号需先绑定有效 License，才能进入 License 管理。';
                    this.adminLicenseList = [];
                    this.adminLicenseDetail = null;
                    this.adminLicenseEvents = [];
                }
                return;
            }
            if (tab === 'ops') {
                await this.loadOpsMetrics({ force: !this.opsMetrics });
                return;
            }
            if (tab === 'summaries') {
                await this.loadAdminSummariesInfo();
                return;
            }
            if (tab === 'ownership') {
                await this.loadAdminOwnershipHistory();
                return;
            }
            if (tab === 'config') {
                await this.loadAdminConfigCenter();
            }
        },

        async loadAdminOverview() {
            const tasks = [
                this.loadOpsMetrics({ silent: true }),
                this.loadAdminSummariesInfo({ silent: true }),
                this.loadAdminOwnershipHistory({ silent: true }),
            ];
            if (this.canManageAdminLicenses()) {
                tasks.push(this.loadAdminLicenseSummary({ silent: true }));
            }
            await Promise.all(tasks);
        },

        buildAdminLicenseQueryParams(page = 1) {
            const params = new URLSearchParams();
            params.set('page', String(Math.max(1, Number(page) || 1)));
            params.set('page_size', String(Math.max(1, Number(this.adminLicensePagination?.page_size) || 20)));
            params.set('sort_by', String(this.adminLicenseSort?.by || 'id'));
            params.set('sort_order', String(this.adminLicenseSort?.order || 'desc'));
            Object.entries(this.adminLicenseFilters || {}).forEach(([key, value]) => {
                const normalized = String(value ?? '').trim();
                if (normalized) {
                    params.set(key, normalized);
                }
            });
            return params;
        },

        syncAdminLicenseSelection() {
            const visibleIds = new Set((Array.isArray(this.adminLicenseList) ? this.adminLicenseList : []).map(item => Number(item?.id) || 0));
            this.adminLicenseSelectedIds = (Array.isArray(this.adminLicenseSelectedIds) ? this.adminLicenseSelectedIds : [])
                .map(item => Number(item) || 0)
                .filter(item => item > 0 && visibleIds.has(item));
        },

        async loadAdminLicenseBootstrapStatus(options = {}) {
            const { silent = false } = options;
            if (!this.canViewAdminCenter()) return null;
            this.adminLicenseBootstrapLoading = true;
            this.adminLicenseBootstrapError = '';
            try {
                const payload = await this.apiCall('/admin/licenses/bootstrap/status', {
                    skipAuthRedirect: true,
                });
                this.adminLicenseBootstrapStatus = payload && typeof payload === 'object' ? payload : null;
                return this.adminLicenseBootstrapStatus;
            } catch (error) {
                const message = error?.message || '种子 License 状态加载失败';
                this.adminLicenseBootstrapStatus = null;
                this.adminLicenseBootstrapError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.adminLicenseBootstrapLoading = false;
            }
        },

        canBootstrapAdminLicense() {
            return this.canViewAdminCenter() && !!this.adminLicenseBootstrapStatus?.eligible;
        },

        formatLicenseDurationDays(durationDays = 0) {
            const normalized = this.normalizePositiveIntInput(durationDays, 0);
            return normalized > 0 ? `${normalized} 天` : '-';
        },

        getAdminLicenseValidityLeadText(item = null) {
            if (item?.activation_starts_validity && !item?.not_before_at) {
                return '激活后开始';
            }
            return item?.not_before_at ? this.formatDate(item.not_before_at) : '-';
        },

        getAdminLicenseValidityTailLabel(item = null) {
            if (item?.activation_starts_validity && !item?.expires_at) {
                return '有效期';
            }
            return '到期';
        },

        getAdminLicenseValidityTailText(item = null) {
            if (item?.activation_starts_validity && !item?.expires_at) {
                return this.formatLicenseDurationDays(item?.duration_days);
            }
            return item?.expires_at ? this.formatDate(item.expires_at) : '-';
        },

        async bootstrapAdminLicenseSeed() {
            if (!this.canViewAdminCenter()) return;
            const durationDays = this.normalizePositiveIntInput(this.adminLicenseBootstrapForm?.duration_days, 0);
            if (!durationDays) {
                this.showToast('请填写有效期天数', 'warning');
                return;
            }
            this.adminLicenseBootstrapSubmitting = true;
            this.adminLicenseBootstrapError = '';
            try {
                const payload = await this.apiCall('/admin/licenses/bootstrap', {
                    method: 'POST',
                    body: JSON.stringify({
                        duration_days: durationDays,
                        note: String(this.adminLicenseBootstrapForm?.note || '').trim(),
                    }),
                    skipAuthRedirect: true,
                });
                this.applyLicenseStatusPayload(payload);
                this.adminLicenseBootstrapStatus = payload?.bootstrap_status && typeof payload.bootstrap_status === 'object'
                    ? payload.bootstrap_status
                    : this.adminLicenseBootstrapStatus;
                this.adminLicenseBootstrapForm = this.createDefaultAdminLicenseBootstrapForm();
                await Promise.all([
                    this.loadAdminLicenseBootstrapStatus({ silent: true }),
                    this.loadAdminLicenseSummary({ silent: true }),
                    this.loadAdminLicenseList({ page: 1, silent: true }),
                ]);
                this.showToast(payload?.message || '已生成并绑定首个种子 License', 'success');
            } catch (error) {
                const message = error?.payload?.bootstrap_status?.message
                    || error?.message
                    || '首个种子 License 创建失败';
                this.adminLicenseBootstrapStatus = error?.payload?.bootstrap_status && typeof error.payload.bootstrap_status === 'object'
                    ? error.payload.bootstrap_status
                    : this.adminLicenseBootstrapStatus;
                this.adminLicenseBootstrapError = message;
                this.showToast(message, 'error');
            } finally {
                this.adminLicenseBootstrapSubmitting = false;
            }
        },

        async loadAdminLicenseSummary(options = {}) {
            const { silent = false } = options;
            if (!this.canManageAdminLicenses()) {
                this.adminLicenseSummary = null;
                this.adminLicenseSummaryError = '当前账号需先绑定有效 License，才能进入 License 管理。';
                return null;
            }
            this.adminLicenseSummaryLoading = true;
            this.adminLicenseSummaryError = '';
            try {
                const payload = await this.apiCall('/admin/licenses/summary', {
                    skipAuthRedirect: true,
                });
                this.adminLicenseSummary = payload && typeof payload === 'object' ? payload : null;
                if (this.adminLicenseSummary?.enforcement) {
                    this.applyAdminLicenseEnforcementPayload(this.adminLicenseSummary.enforcement);
                }
                if (this.adminLicenseSummary?.presentation_feature) {
                    this.applyAdminPresentationFeaturePayload(this.adminLicenseSummary.presentation_feature);
                }
                return this.adminLicenseSummary;
            } catch (error) {
                const message = error?.message || 'License 概览加载失败';
                this.adminLicenseSummaryError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.adminLicenseSummaryLoading = false;
            }
        },

        async loadAdminLicenseList(options = {}) {
            const {
                page = this.adminLicensePagination?.page || 1,
                silent = false,
            } = options;
            if (!this.canManageAdminLicenses()) {
                this.adminLicenseList = [];
                this.adminLicenseListError = '当前账号需先绑定有效 License，才能进入 License 管理。';
                this.adminLicensePagination = this.createDefaultAdminLicensePagination();
                return null;
            }
            this.adminLicenseListLoading = true;
            this.adminLicenseListError = '';
            try {
                const params = this.buildAdminLicenseQueryParams(page);
                const payload = await this.apiCall(`/admin/licenses?${params.toString()}`, {
                    skipAuthRedirect: true,
                });
                this.adminLicenseList = Array.isArray(payload?.items) ? payload.items : [];
                this.adminLicensePagination = {
                    page: Number(payload?.page) || 1,
                    page_size: Number(payload?.page_size) || 20,
                    total_pages: Number(payload?.total_pages) || 0,
                    count: Number(payload?.count) || 0,
                };
                this.adminLicenseSort = {
                    by: String(payload?.sort_by || this.adminLicenseSort?.by || 'id'),
                    order: String(payload?.sort_order || this.adminLicenseSort?.order || 'desc'),
                };
                this.adminLicensePageJumpInput = String(Number(payload?.page) || 1);
                this.syncAdminLicenseSelection();
                if (this.adminLicenseDetailId) {
                    const exists = this.adminLicenseList.some(item => Number(item?.id) === Number(this.adminLicenseDetailId));
                    if (!exists && this.adminLicenseDetail && Number(this.adminLicenseDetail?.id) === Number(this.adminLicenseDetailId)) {
                        await this.loadAdminLicenseDetail(this.adminLicenseDetailId, { silent: true });
                    }
                }
                return payload;
            } catch (error) {
                const message = error?.message || 'License 列表加载失败';
                this.adminLicenseListError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.adminLicenseListLoading = false;
            }
        },

        async loadAdminLicenseDetail(licenseId, options = {}) {
            const { silent = false } = options;
            const normalizedId = Number(licenseId) || 0;
            if (!normalizedId || !this.canManageAdminLicenses()) {
                this.adminLicenseDetailId = null;
                this.adminLicenseDetail = null;
                this.adminLicenseEvents = [];
                return null;
            }
            this.adminLicenseDetailLoading = true;
            try {
                const [detail, eventsPayload] = await Promise.all([
                    this.apiCall(`/admin/licenses/${normalizedId}`, { skipAuthRedirect: true }),
                    this.apiCall(`/admin/licenses/${normalizedId}/events?limit=50`, { skipAuthRedirect: true }),
                ]);
                this.adminLicenseDetailId = normalizedId;
                this.adminLicenseDetail = detail && typeof detail === 'object' ? detail : null;
                this.adminLicenseEvents = Array.isArray(eventsPayload?.items) ? eventsPayload.items : [];
                this.adminLicenseDetailForm = {
                    revoke_reason: '',
                    duration_days: this.normalizePositiveIntInput(this.adminLicenseDetail?.duration_days, ''),
                };
                return this.adminLicenseDetail;
            } catch (error) {
                if (!silent) {
                    this.showToast(error?.message || 'License 详情加载失败', 'error');
                }
                return null;
            } finally {
                this.adminLicenseDetailLoading = false;
            }
        },

        getAdminLicenseStatusClass(status = '') {
            const normalized = String(status || '').trim().toLowerCase();
            if (normalized === 'active') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
            if (normalized === 'issued') return 'border-slate-200 bg-slate-100 text-slate-700';
            if (normalized === 'not_yet_active') return 'border-amber-200 bg-amber-50 text-amber-700';
            if (normalized === 'expired') return 'border-orange-200 bg-orange-50 text-orange-700';
            if (normalized === 'revoked') return 'border-red-200 bg-red-50 text-red-700';
            if (normalized === 'replaced') return 'border-violet-200 bg-violet-50 text-violet-700';
            return 'border-gray-200 bg-gray-50 text-gray-700';
        },

        formatAdminLicenseEventLabel(eventType = '') {
            const normalized = String(eventType || '').trim().toLowerCase();
            const labels = {
                generated: '已生成',
                activated: '已激活',
                bootstrap_seeded: '种子初始化',
                activate_failed: '激活失败',
                activate_reused: '重复激活',
                extended: '已延期',
                revoked: '已撤销',
                replaced: '已替换',
                enforcement_changed: '开关变更',
                presentation_feature_changed: '演示开关变更',
            };
            return labels[normalized] || (normalized || '未知事件');
        },

        getAdminLicenseEnforcementState() {
            const enforcement = this.adminLicenseSummary?.enforcement;
            return enforcement && typeof enforcement === 'object' ? enforcement : null;
        },

        getAdminLicenseEnforcementOverrideLabel() {
            const enforcement = this.getAdminLicenseEnforcementState();
            if (this.isAdminLicenseEnforcementFixed()) {
                return '固定开启';
            }
            if (!enforcement || enforcement.override_enabled === null || enforcement.override_enabled === undefined) {
                return '跟随默认值';
            }
            return enforcement.override_enabled ? '强制开启' : '强制关闭';
        },

        getAdminLicenseEnforcementSourceLabel() {
            const enforcement = this.getAdminLicenseEnforcementState();
            if (!enforcement) {
                return '-';
            }
            if (this.isAdminLicenseEnforcementFixed()) {
                return '系统固定要求';
            }
            if (enforcement.source === 'runtime_override') {
                return '运行时覆盖生效';
            }
            return '默认值生效';
        },

        isAdminLicenseEnforcementFixed() {
            return String(this.getAdminLicenseEnforcementState()?.source || '').trim() === 'mandatory_policy';
        },

        applyAdminLicenseEnforcementPayload(payload = {}) {
            const enabled = payload?.enabled !== false;
            this.licenseEnforcementEnabled = enabled;
            if (this.serverStatus && typeof this.serverStatus === 'object') {
                this.serverStatus = {
                    ...this.serverStatus,
                    license_enforcement_enabled: enabled,
                    license_enforcement_source: String(payload?.source || this.serverStatus.license_enforcement_source || 'env_default'),
                };
            }
            if (this.adminLicenseSummary && typeof this.adminLicenseSummary === 'object') {
                this.adminLicenseSummary = {
                    ...this.adminLicenseSummary,
                    enforcement: payload,
                };
            }
        },

        getAdminPresentationFeatureState() {
            const feature = this.adminLicenseSummary?.presentation_feature;
            return feature && typeof feature === 'object' ? feature : null;
        },

        getAdminPresentationFeatureOverrideLabel() {
            const feature = this.getAdminPresentationFeatureState();
            if (!feature || feature.override_enabled === null || feature.override_enabled === undefined) {
                return '跟随默认值';
            }
            return feature.override_enabled ? '强制开启' : '强制关闭';
        },

        getAdminPresentationFeatureSourceLabel() {
            const feature = this.getAdminPresentationFeatureState();
            if (!feature) {
                return '-';
            }
            if (feature.source === 'runtime_override') {
                return '运行时覆盖生效';
            }
            return '默认值生效';
        },

        applyAdminPresentationFeaturePayload(payload = {}) {
            this.applyPresentationFeaturePayload({
                presentation_feature_enabled: !!payload?.enabled,
                presentation_feature_source: String(payload?.source || 'env_default'),
            });
            if (this.adminLicenseSummary && typeof this.adminLicenseSummary === 'object') {
                this.adminLicenseSummary = {
                    ...this.adminLicenseSummary,
                    presentation_feature: payload,
                };
            }
        },

        toggleAdminLicenseSelection(licenseId) {
            const normalizedId = Number(licenseId) || 0;
            if (!normalizedId) return;
            if (this.adminLicenseSelectedIds.includes(normalizedId)) {
                this.adminLicenseSelectedIds = this.adminLicenseSelectedIds.filter(item => item !== normalizedId);
                return;
            }
            this.adminLicenseSelectedIds = [...this.adminLicenseSelectedIds, normalizedId];
        },

        isAdminLicenseDetailActive(licenseId) {
            const normalizedId = Number(licenseId) || 0;
            return normalizedId > 0 && normalizedId === (Number(this.adminLicenseDetailId) || 0);
        },

        openAdminLicenseDetailFromRow(licenseId) {
            const normalizedId = Number(licenseId) || 0;
            if (!normalizedId) return;
            void this.loadAdminLicenseDetail(normalizedId, { silent: true });
        },

        toggleAdminLicenseSelectionAndInspect(licenseId) {
            const normalizedId = Number(licenseId) || 0;
            if (!normalizedId) return;
            this.toggleAdminLicenseSelection(normalizedId);
            void this.loadAdminLicenseDetail(normalizedId, { silent: true });
        },

        areAllAdminLicensesSelected() {
            if (!Array.isArray(this.adminLicenseList) || this.adminLicenseList.length === 0) return false;
            return this.adminLicenseList.every(item => this.adminLicenseSelectedIds.includes(Number(item?.id) || 0));
        },

        toggleSelectAllAdminLicenses() {
            if (this.areAllAdminLicensesSelected()) {
                this.adminLicenseSelectedIds = [];
                return;
            }
            this.adminLicenseSelectedIds = this.adminLicenseList
                .map(item => Number(item?.id) || 0)
                .filter(item => item > 0);
        },

        async applyAdminLicenseFilters() {
            this.adminLicensePagination.page = 1;
            await this.loadAdminLicenseList({ page: 1 });
        },

        async resetAdminLicenseFilters() {
            this.adminLicenseFilters = {
                status: '',
                level_key: '',
                batch_id: '',
                bound_account: '',
                note: '',
                created_from: '',
                created_to: '',
                expires_from: '',
                expires_to: '',
                is_bound: '',
                code: '',
            };
            this.adminLicensePagination.page = 1;
            await this.loadAdminLicenseList({ page: 1 });
        },

        async applyAdminLicenseListTools() {
            this.adminLicensePagination.page = 1;
            await this.loadAdminLicenseList({ page: 1 });
        },

        async changeAdminLicensePageSize(pageSize) {
            const normalized = Math.max(1, Math.min(Number(pageSize) || 20, 100));
            this.adminLicensePagination.page_size = normalized;
            this.adminLicensePagination.page = 1;
            await this.loadAdminLicenseList({ page: 1 });
        },

        getAdminLicenseTotalPages() {
            return Math.max(1, Number(this.adminLicensePagination?.total_pages) || 1);
        },

        async goToAdminLicensePage(page) {
            const requested = Math.max(1, Math.min(Number(page) || 1, this.getAdminLicenseTotalPages()));
            await this.loadAdminLicenseList({ page: requested });
        },

        getAdminLicenseSortLabel(sortBy = '') {
            const labels = {
                id: 'ID',
                created_at: '创建时间',
                updated_at: '更新时间',
                expires_at: '到期时间',
                bound_at: '绑定时间',
                status: '状态',
                batch_id: '批次号',
                duration_days: '有效期天数',
            };
            return labels[String(sortBy || '').trim()] || 'ID';
        },

        async setAdminLicenseSortBy(sortBy) {
            this.adminLicenseSort.by = String(sortBy || 'id');
            await this.applyAdminLicenseListTools();
        },

        async toggleAdminLicenseSortOrder(order = '') {
            const normalized = String(order || '').trim().toLowerCase();
            if (normalized === 'asc' || normalized === 'desc') {
                this.adminLicenseSort.order = normalized;
            } else {
                this.adminLicenseSort.order = this.adminLicenseSort.order === 'asc' ? 'desc' : 'asc';
            }
            await this.applyAdminLicenseListTools();
        },

        async jumpAdminLicensePage() {
            const requested = Math.max(1, Math.min(Number(this.adminLicensePageJumpInput) || 1, this.getAdminLicenseTotalPages()));
            this.adminLicensePageJumpInput = String(requested);
            await this.goToAdminLicensePage(requested);
        },

        summarizeAdminLicenseMutationResult(payload = {}, verb = '处理') {
            const succeeded = Array.isArray(payload?.succeeded) ? payload.succeeded.length : 0;
            const failed = Array.isArray(payload?.failed) ? payload.failed.length : 0;
            if (failed > 0) {
                return `${verb}完成：成功 ${succeeded} 条，跳过 ${failed} 条`;
            }
            return `${verb}完成：成功 ${succeeded} 条`;
        },

        async toggleAdminLicenseEnforcement(enabled) {
            if (!this.canManageAdminLicenses()) {
                this.showToast('当前账号需先绑定有效 License，才能切换 License 开关', 'warning');
                return;
            }
            if (this.isAdminLicenseEnforcementFixed()) {
                this.showToast('当前版本固定要求登录后绑定有效 License，不支持关闭该规则', 'warning');
                return;
            }
            this.adminLicenseEnforcementMutating = true;
            try {
                const payload = await this.apiCall('/admin/license-enforcement', {
                    method: 'POST',
                    body: JSON.stringify({ enabled: !!enabled, sync_default: true }),
                    skipAuthRedirect: true,
                });
                this.applyAdminLicenseEnforcementPayload(payload);
                this.showToast(payload?.message || 'License 开关已更新', 'success');
            } catch (error) {
                this.showToast(error?.message || 'License 开关更新失败', 'error');
            } finally {
                this.adminLicenseEnforcementMutating = false;
            }
        },

        async followAdminLicenseEnforcementDefault() {
            if (!this.canManageAdminLicenses()) {
                this.showToast('当前账号需先绑定有效 License，才能调整 License 开关', 'warning');
                return;
            }
            if (this.isAdminLicenseEnforcementFixed()) {
                this.showToast('当前版本固定要求登录后绑定有效 License，无需额外恢复默认值', 'warning');
                return;
            }
            this.adminLicenseEnforcementMutating = true;
            try {
                const payload = await this.apiCall('/admin/license-enforcement/follow-default', {
                    method: 'POST',
                    body: JSON.stringify({}),
                    skipAuthRedirect: true,
                });
                this.applyAdminLicenseEnforcementPayload(payload);
                this.showToast(payload?.message || '已恢复跟随默认值', 'success');
            } catch (error) {
                this.showToast(error?.message || '恢复默认跟随失败', 'error');
            } finally {
                this.adminLicenseEnforcementMutating = false;
            }
        },

        async toggleAdminPresentationFeature(enabled) {
            if (!this.canManageAdminLicenses()) {
                this.showToast('当前账号需先绑定有效 License，才能切换演示文稿开关', 'warning');
                return;
            }
            this.adminPresentationFeatureMutating = true;
            try {
                const payload = await this.apiCall('/admin/presentation-feature', {
                    method: 'POST',
                    body: JSON.stringify({ enabled: !!enabled, sync_default: true }),
                    skipAuthRedirect: true,
                });
                this.applyAdminPresentationFeaturePayload(payload);
                this.showToast(payload?.message || '演示文稿开关已更新', 'success');
            } catch (error) {
                this.showToast(error?.message || '演示文稿开关更新失败', 'error');
            } finally {
                this.adminPresentationFeatureMutating = false;
            }
        },

        async followAdminPresentationFeatureDefault() {
            if (!this.canManageAdminLicenses()) {
                this.showToast('当前账号需先绑定有效 License，才能调整演示文稿开关', 'warning');
                return;
            }
            this.adminPresentationFeatureMutating = true;
            try {
                const payload = await this.apiCall('/admin/presentation-feature/follow-default', {
                    method: 'POST',
                    body: JSON.stringify({}),
                    skipAuthRedirect: true,
                });
                this.applyAdminPresentationFeaturePayload(payload);
                this.showToast(payload?.message || '已恢复跟随默认值', 'success');
            } catch (error) {
                this.showToast(error?.message || '恢复默认跟随失败', 'error');
            } finally {
                this.adminPresentationFeatureMutating = false;
            }
        },

        async generateAdminLicenseBatch() {
            if (!this.canManageAdminLicenses()) {
                this.showToast('当前账号需先绑定有效 License，才能生成 License', 'warning');
                return;
            }
            const count = Math.max(1, Number(this.adminLicenseGenerateForm?.count) || 0);
            if (!count) {
                this.showToast('请输入有效的生成数量', 'warning');
                return;
            }
            const durationDays = this.normalizePositiveIntInput(this.adminLicenseGenerateForm?.duration_days, 0);
            if (!durationDays) {
                this.showToast('请填写有效期天数', 'warning');
                return;
            }
            this.adminLicenseGenerateLoading = true;
            try {
                const payload = await this.apiCall('/admin/licenses/batch', {
                    method: 'POST',
                    body: JSON.stringify({
                        count,
                        duration_days: durationDays,
                        level_key: String(this.adminLicenseGenerateForm?.level_key || 'standard').trim() || 'standard',
                        note: String(this.adminLicenseGenerateForm?.note || '').trim(),
                    }),
                    skipAuthRedirect: true,
                });
                this.adminLicenseGeneratedBatch = payload;
                this.adminLicenseGenerateForm = {
                    ...this.createDefaultAdminLicenseGenerateForm(),
                    note: this.adminLicenseGenerateForm?.note || '',
                };
                await Promise.all([
                    this.loadAdminLicenseSummary({ silent: true }),
                    this.loadAdminLicenseList({ page: 1, silent: true }),
                ]);
                this.showToast(`已生成 ${payload?.count || 0} 条 License`, 'success');
            } catch (error) {
                this.showToast(error?.message || 'License 生成失败', 'error');
            } finally {
                this.adminLicenseGenerateLoading = false;
            }
        },

        async copyTextToClipboard(text = '') {
            const content = String(text || '');
            if (!content) return false;
            if (navigator?.clipboard?.writeText) {
                await navigator.clipboard.writeText(content);
                return true;
            }
            const textarea = document.createElement('textarea');
            textarea.value = content;
            textarea.setAttribute('readonly', 'readonly');
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            const copied = document.execCommand('copy');
            document.body.removeChild(textarea);
            return copied;
        },

        async copyAdminGeneratedLicenses() {
            const licenses = Array.isArray(this.adminLicenseGeneratedBatch?.licenses) ? this.adminLicenseGeneratedBatch.licenses : [];
            if (licenses.length === 0) return;
            try {
                const content = licenses.map(item => String(item?.code || '').trim()).filter(Boolean).join('\n');
                const copied = await this.copyTextToClipboard(content);
                this.showToast(copied ? '明文 License 已复制' : '复制失败，请稍后重试', copied ? 'success' : 'error');
            } catch (error) {
                this.showToast(error?.message || '复制失败，请稍后重试', 'error');
            }
        },

        async downloadAdminGeneratedLicenses(format = 'txt') {
            const payload = this.adminLicenseGeneratedBatch;
            const licenses = Array.isArray(payload?.licenses) ? payload.licenses : [];
            if (licenses.length === 0) return;

            const batchId = String(payload?.batch_id || 'licenses').trim() || 'licenses';
            let blob = null;
            let filename = '';
            if (format === 'csv') {
                const rows = [
                    ['id', 'code', 'masked_code', 'level_key', 'level_name', 'duration_days', 'not_before_at', 'expires_at'],
                    ...licenses.map(item => [
                        item?.id ?? '',
                        item?.code ?? '',
                        item?.masked_code ?? '',
                        item?.level_key ?? payload?.level_key ?? '',
                        item?.level_name ?? payload?.level_name ?? '',
                        item?.duration_days ?? '',
                        item?.not_before_at ?? '',
                        item?.expires_at ?? '',
                    ]),
                ];
                const content = rows
                    .map(row => row.map(cell => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(','))
                    .join('\n');
                blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
                filename = `${batchId}.csv`;
            } else {
                const content = licenses.map(item => String(item?.code || '').trim()).filter(Boolean).join('\n');
                blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
                filename = `${batchId}.txt`;
            }
            const target = { mode: 'fallback' };
            const saved = await this.commitExportBlob(target, blob, filename);
            if (saved) {
                this.showToast(format === 'csv' ? 'CSV 已导出' : '文本文件已导出', 'success');
            }
        },

        async runAdminLicenseBulkRevoke() {
            if (!this.canManageAdminLicenses()) return;
            const licenseIds = this.adminLicenseSelectedIds.filter(item => Number(item) > 0);
            if (licenseIds.length === 0) {
                this.showToast('请先勾选要撤销的 License', 'warning');
                return;
            }
            const confirmed = await this.openActionConfirmDialog({
                title: '确认批量撤销',
                message: `将撤销 ${licenseIds.length} 条 License，已绑定账号会立即失效，是否继续？`,
                tone: 'danger',
                confirmText: '确认撤销',
            });
            if (!confirmed) return;
            try {
                const payload = await this.apiCall('/admin/licenses/bulk-revoke', {
                    method: 'POST',
                    body: JSON.stringify({
                        license_ids: licenseIds,
                        reason: String(this.adminLicenseBulk?.revoke_reason || '').trim(),
                    }),
                    skipAuthRedirect: true,
                });
                this.adminLicenseBulk.revoke_reason = '';
                this.adminLicenseSelectedIds = [];
                await Promise.all([
                    this.loadAdminLicenseSummary({ silent: true }),
                    this.loadAdminLicenseList({ page: this.adminLicensePagination.page || 1, silent: true }),
                    this.adminLicenseDetailId ? this.loadAdminLicenseDetail(this.adminLicenseDetailId, { silent: true }) : Promise.resolve(null),
                ]);
                this.showToast(this.summarizeAdminLicenseMutationResult(payload, '撤销'), 'success');
            } catch (error) {
                this.showToast(error?.message || '批量撤销失败', 'error');
            }
        },

        async runAdminLicenseBulkExtend() {
            if (!this.canManageAdminLicenses()) return;
            const licenseIds = this.adminLicenseSelectedIds.filter(item => Number(item) > 0);
            if (licenseIds.length === 0) {
                this.showToast('请先勾选要延期的 License', 'warning');
                return;
            }
            const durationDays = this.normalizePositiveIntInput(this.adminLicenseBulk?.duration_days, 0);
            if (!durationDays) {
                this.showToast('请先填写新的有效期天数', 'warning');
                return;
            }
            try {
                const payload = await this.apiCall('/admin/licenses/bulk-extend', {
                    method: 'POST',
                    body: JSON.stringify({
                        license_ids: licenseIds,
                        duration_days: durationDays,
                    }),
                    skipAuthRedirect: true,
                });
                this.adminLicenseBulk.duration_days = '';
                await Promise.all([
                    this.loadAdminLicenseSummary({ silent: true }),
                    this.loadAdminLicenseList({ page: this.adminLicensePagination.page || 1, silent: true }),
                    this.adminLicenseDetailId ? this.loadAdminLicenseDetail(this.adminLicenseDetailId, { silent: true }) : Promise.resolve(null),
                ]);
                this.showToast(this.summarizeAdminLicenseMutationResult(payload, '延期'), 'success');
            } catch (error) {
                this.showToast(error?.message || '批量延期失败', 'error');
            }
        },

        async revokeAdminLicenseDetail() {
            const licenseId = Number(this.adminLicenseDetail?.id) || 0;
            if (!licenseId || !this.canManageAdminLicenses()) return;
            const confirmed = await this.openActionConfirmDialog({
                title: '确认撤销 License',
                message: '撤销后当前绑定账号将立即失效，是否继续？',
                tone: 'danger',
                confirmText: '确认撤销',
            });
            if (!confirmed) return;
            try {
                const payload = await this.apiCall(`/admin/licenses/${licenseId}/revoke`, {
                    method: 'POST',
                    body: JSON.stringify({
                        reason: String(this.adminLicenseDetailForm?.revoke_reason || '').trim(),
                    }),
                    skipAuthRedirect: true,
                });
                this.adminLicenseDetailForm.revoke_reason = '';
                await Promise.all([
                    this.loadAdminLicenseSummary({ silent: true }),
                    this.loadAdminLicenseList({ page: this.adminLicensePagination.page || 1, silent: true }),
                    this.loadAdminLicenseDetail(licenseId, { silent: true }),
                ]);
                this.showToast(payload?.status === 'revoked' ? 'License 已撤销' : '撤销完成', 'success');
            } catch (error) {
                this.showToast(error?.message || '撤销失败', 'error');
            }
        },

        async extendAdminLicenseDetail() {
            const licenseId = Number(this.adminLicenseDetail?.id) || 0;
            if (!licenseId || !this.canManageAdminLicenses()) return;
            const durationDays = this.normalizePositiveIntInput(this.adminLicenseDetailForm?.duration_days, 0);
            if (!durationDays) {
                this.showToast('请先填写新的有效期天数', 'warning');
                return;
            }
            try {
                const payload = await this.apiCall(`/admin/licenses/${licenseId}/extend`, {
                    method: 'POST',
                    body: JSON.stringify({ duration_days: durationDays }),
                    skipAuthRedirect: true,
                });
                await Promise.all([
                    this.loadAdminLicenseSummary({ silent: true }),
                    this.loadAdminLicenseList({ page: this.adminLicensePagination.page || 1, silent: true }),
                    this.loadAdminLicenseDetail(licenseId, { silent: true }),
                ]);
                this.showToast(payload?.duration_days ? 'License 有效期已更新' : '延期完成', 'success');
            } catch (error) {
                this.showToast(error?.message || '延期失败', 'error');
            }
        },

        async loadAdminSummariesInfo(options = {}) {
            const { silent = false } = options;
            if (!this.canViewAdminCenter()) return null;
            this.adminSummariesLoading = true;
            this.adminSummariesError = '';
            try {
                const payload = await this.apiCall('/summaries', { skipAuthRedirect: true });
                this.adminSummariesInfo = payload && typeof payload === 'object' ? payload : null;
                return this.adminSummariesInfo;
            } catch (error) {
                const message = error?.message || '摘要缓存信息加载失败';
                this.adminSummariesError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.adminSummariesLoading = false;
            }
        },

        async clearAdminSummariesCache() {
            if (!this.canViewAdminCenter()) return;
            const confirmed = await this.openActionConfirmDialog({
                title: '确认清空摘要缓存',
                message: '该操作会删除当前全部智能摘要缓存，但不会删除会话和报告数据。',
                tone: 'warning',
                confirmText: '确认清空',
            });
            if (!confirmed) return;
            try {
                const payload = await this.apiCall('/summaries/clear', {
                    method: 'POST',
                    body: JSON.stringify({}),
                    skipAuthRedirect: true,
                });
                await this.loadAdminSummariesInfo({ silent: true });
                this.showToast(payload?.message || '摘要缓存已清空', 'success');
            } catch (error) {
                this.showToast(error?.message || '摘要缓存清空失败', 'error');
            }
        },

        syncAdminConfigDraftFromPayload(payload = null) {
            const nextDraft = {
                env: {},
                config: {},
                site: {},
            };
            ['env', 'config', 'site'].forEach((source) => {
                const groups = Array.isArray(payload?.[source]?.groups) ? payload[source].groups : [];
                groups.forEach((group) => {
                    const groupId = String(group?.id || '').trim();
                    if (!groupId) return;
                    nextDraft[source][groupId] = {};
                    const items = Array.isArray(group?.items) ? group.items : [];
                    items.forEach((item) => {
                        const key = String(item?.key || '').trim();
                        if (!key) return;
                        nextDraft[source][groupId][key] = String(item?.value ?? '');
                    });
                });
            });
            this.adminConfigDraft = nextDraft;
        },

        getAdminConfigRequestErrorMessage(error, fallback = '配置中心加载失败') {
            if (Number(error?.status) === 404) {
                return '当前运行中的后端未包含配置中心接口，请重启服务或部署最新后端版本后再试';
            }
            return error?.message || fallback;
        },

        normalizeAdminConfigSource(source = this.adminConfigSource) {
            return source === 'config' || source === 'site' ? source : 'env';
        },

        setAdminConfigSource(source = 'env') {
            this.adminConfigSource = this.normalizeAdminConfigSource(source);
            this.ensureAdminConfigActiveGroup(this.adminConfigSource);
        },

        getAdminConfigSourceMeta(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            return this.adminConfigCenter?.meta?.source_meta?.[normalized] || {};
        },

        getAdminConfigSourceLabel(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            if (normalized === 'config') return 'config.py';
            if (normalized === 'site') return '共享前端配置';
            return '.env';
        },

        async loadAdminConfigCenter(options = {}) {
            const { silent = false } = options;
            if (!this.canViewAdminCenter()) return null;
            this.adminConfigLoading = true;
            this.adminConfigError = '';
            try {
                const payload = await this.apiCall('/admin/config-center', {
                    skipAuthRedirect: true,
                });
                this.adminConfigCenter = payload && typeof payload === 'object' ? payload : null;
                this.syncAdminConfigDraftFromPayload(this.adminConfigCenter);
                ['env', 'config', 'site'].forEach((source) => this.ensureAdminConfigActiveGroup(source));
                return this.adminConfigCenter;
            } catch (error) {
                const message = this.getAdminConfigRequestErrorMessage(error, '配置中心加载失败');
                this.adminConfigError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.adminConfigLoading = false;
            }
        },

        getAdminConfigSourcePayload(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            return this.adminConfigCenter?.[normalized] || { file: {}, groups: [] };
        },

        normalizeAdminConfigSearchText(value = '') {
            return String(value || '')
                .toLowerCase()
                .normalize('NFKC')
                .replace(/\s+/g, ' ')
                .trim();
        },

        compactAdminConfigSearchText(value = '') {
            return this.normalizeAdminConfigSearchText(value).replace(/[\s_\-./:@]+/g, '');
        },

        isAdminConfigSubsequenceMatch(text = '', keyword = '') {
            if (!keyword) return true;
            let cursor = 0;
            for (const char of String(text || '')) {
                if (char === keyword[cursor]) {
                    cursor += 1;
                    if (cursor >= keyword.length) {
                        return true;
                    }
                }
            }
            return false;
        },

        matchesAdminConfigSearchValue(value = '', keyword = this.adminConfigSearch) {
            const normalizedValue = this.normalizeAdminConfigSearchText(value);
            const normalizedKeyword = this.normalizeAdminConfigSearchText(keyword);
            if (!normalizedKeyword) return true;
            if (!normalizedValue) return false;
            if (normalizedValue.includes(normalizedKeyword)) return true;
            const compactValue = this.compactAdminConfigSearchText(normalizedValue);
            const compactKeyword = this.compactAdminConfigSearchText(normalizedKeyword);
            if (!compactKeyword) return true;
            if (compactValue.includes(compactKeyword)) return true;
            return this.isAdminConfigSubsequenceMatch(compactValue, compactKeyword);
        },

        matchesAdminConfigSearchParts(parts = [], keyword = this.adminConfigSearch) {
            const normalizedKeyword = this.normalizeAdminConfigSearchText(keyword);
            if (!normalizedKeyword) return true;
            const tokens = normalizedKeyword.split(' ').filter(Boolean);
            if (tokens.length === 0) return true;
            return tokens.every((token) => (
                parts.some((part) => this.matchesAdminConfigSearchValue(part, token))
            ));
        },

        getAdminConfigVisibleGroups(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            const payload = this.getAdminConfigSourcePayload(normalized);
            const groups = Array.isArray(payload?.groups) ? payload.groups : [];
            const showAdvanced = !!this.adminConfigShowAdvanced;
            return groups
                .map((group) => {
                    const items = Array.isArray(group?.items) ? group.items : [];
                    const visibleScopeItems = showAdvanced ? items : items.filter(item => !item?.advanced);
                    const visibleItems = visibleScopeItems.filter((item) => this.matchesAdminConfigSearchParts([
                        group?.title,
                        group?.description,
                        item?.label,
                        item?.key,
                        item?.description,
                        item?.placeholder,
                    ]));
                    return {
                        ...group,
                        visibleItems,
                        visibleItemCount: visibleItems.length,
                        totalItemCount: visibleScopeItems.length,
                    };
                })
                .filter((group) => Array.isArray(group.visibleItems) && group.visibleItems.length > 0);
        },

        ensureAdminConfigActiveGroup(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            const groups = this.getAdminConfigVisibleGroups(normalized);
            if (!groups.length) {
                this.adminConfigActiveGroupId[normalized] = '';
                return '';
            }
            const currentId = String(this.adminConfigActiveGroupId?.[normalized] || '');
            if (groups.some((group) => String(group?.id || '') === currentId)) {
                return currentId;
            }
            const nextId = String(groups[0]?.id || '');
            this.adminConfigActiveGroupId[normalized] = nextId;
            return nextId;
        },

        getAdminConfigCurrentGroupId(source = this.adminConfigSource) {
            return this.ensureAdminConfigActiveGroup(source);
        },

        setAdminConfigActiveGroup(source, groupId) {
            const normalized = this.normalizeAdminConfigSource(source);
            this.adminConfigActiveGroupId[normalized] = String(groupId || '');
        },

        getAdminConfigActiveGroup(source = this.adminConfigSource) {
            const normalized = this.normalizeAdminConfigSource(source);
            const groups = this.getAdminConfigVisibleGroups(normalized);
            const currentId = this.ensureAdminConfigActiveGroup(normalized);
            return groups.find((group) => String(group?.id || '') === String(currentId || '')) || null;
        },

        getAdminConfigDraftValue(source, groupId, key) {
            const normalizedSource = this.normalizeAdminConfigSource(source);
            return String(this.adminConfigDraft?.[normalizedSource]?.[groupId]?.[key] ?? '');
        },

        setAdminConfigDraftValue(source, groupId, key, value) {
            const normalizedSource = this.normalizeAdminConfigSource(source);
            if (!this.adminConfigDraft[normalizedSource]) {
                this.adminConfigDraft[normalizedSource] = {};
            }
            if (!this.adminConfigDraft[normalizedSource][groupId]) {
                this.adminConfigDraft[normalizedSource][groupId] = {};
            }
            this.adminConfigDraft[normalizedSource][groupId][key] = String(value ?? '');
        },

        getAdminConfigInputType(item = {}) {
            const fieldType = String(item?.type || 'text').trim();
            if (fieldType === 'integer' || fieldType === 'float') return 'number';
            if (item?.secret) return this.adminConfigShowSecrets ? 'text' : 'password';
            return 'text';
        },

        isAdminConfigGroupSaving(source, groupId) {
            return this.adminConfigSavingKey === `${source}:${groupId}`;
        },

        async saveAdminConfigGroup(source, groupId) {
            if (!this.canViewAdminCenter()) return;
            const normalizedSource = this.normalizeAdminConfigSource(source);
            const groups = Array.isArray(this.adminConfigCenter?.[normalizedSource]?.groups)
                ? this.adminConfigCenter[normalizedSource].groups
                : [];
            const targetGroup = groups.find((group) => String(group?.id || '') === String(groupId || ''));
            if (!targetGroup) {
                this.showToast('未找到配置分组', 'error');
                return;
            }
            const values = {};
            const items = Array.isArray(targetGroup?.items) ? targetGroup.items : [];
            items.forEach((item) => {
                const key = String(item?.key || '').trim();
                if (!key) return;
                values[key] = this.getAdminConfigDraftValue(normalizedSource, targetGroup.id, key);
            });
            this.adminConfigSavingKey = `${normalizedSource}:${targetGroup.id}`;
            try {
                const payload = await this.apiCall('/admin/config-center/save', {
                    method: 'POST',
                    body: JSON.stringify({
                        source: normalizedSource,
                        group_id: targetGroup.id,
                        values,
                    }),
                    skipAuthRedirect: true,
                });
                this.adminConfigCenter = payload?.config_center && typeof payload.config_center === 'object'
                    ? payload.config_center
                    : this.adminConfigCenter;
                this.syncAdminConfigDraftFromPayload(this.adminConfigCenter);
                this.showToast(payload?.message || '配置已保存', 'success');
            } catch (error) {
                this.showToast(this.getAdminConfigRequestErrorMessage(error, '配置保存失败'), 'error');
            } finally {
                this.adminConfigSavingKey = '';
            }
        },

        async searchAdminUsers(target = 'target') {
            if (!this.canViewAdminCenter()) return;
            const isSource = target === 'source';
            const query = String(isSource ? this.adminOwnershipSourceQuery : this.adminOwnershipTargetQuery || '').trim();
            this.adminOwnershipSearchLoading = true;
            try {
                const params = new URLSearchParams();
                if (query) {
                    params.set('q', query);
                }
                params.set('limit', '12');
                const payload = await this.apiCall(`/admin/users?${params.toString()}`, {
                    skipAuthRedirect: true,
                });
                const items = Array.isArray(payload?.items) ? payload.items : [];
                if (isSource) {
                    this.adminOwnershipSourceResults = items;
                } else {
                    this.adminOwnershipTargetResults = items;
                }
                return items;
            } catch (error) {
                this.showToast(error?.message || '用户搜索失败', 'error');
                return [];
            } finally {
                this.adminOwnershipSearchLoading = false;
            }
        },

        selectAdminOwnershipUser(user, target = 'target') {
            const normalizedUser = user && typeof user === 'object' ? user : null;
            if (!normalizedUser) return;
            const isSource = target === 'source';
            if (isSource) {
                this.adminOwnershipForm.from_user_id = String(normalizedUser.id || '');
                this.adminOwnershipForm.from_account = String(normalizedUser.account || normalizedUser.phone || normalizedUser.email || '').trim();
                this.adminOwnershipSourceQuery = this.adminOwnershipForm.from_account;
                this.adminOwnershipSourceResults = [];
                return;
            }
            this.adminOwnershipForm.to_user_id = String(normalizedUser.id || '');
            this.adminOwnershipForm.to_account = String(normalizedUser.account || normalizedUser.phone || normalizedUser.email || '').trim();
            this.adminOwnershipTargetQuery = this.adminOwnershipForm.to_account;
            this.adminOwnershipTargetResults = [];
        },

        toggleAdminOwnershipKind(kind = '') {
            const normalized = String(kind || '').trim();
            if (!normalized) return;
            const nextKinds = Array.isArray(this.adminOwnershipForm?.kinds)
                ? [...this.adminOwnershipForm.kinds]
                : [];
            if (nextKinds.includes(normalized)) {
                this.adminOwnershipForm.kinds = nextKinds.filter(item => item !== normalized);
                return;
            }
            this.adminOwnershipForm.kinds = [...nextKinds, normalized];
        },

        buildAdminOwnershipPayload() {
            const kinds = Array.isArray(this.adminOwnershipForm?.kinds)
                ? this.adminOwnershipForm.kinds.filter(item => item === 'sessions' || item === 'reports')
                : [];
            return {
                to_user_id: this.adminOwnershipForm?.to_user_id ? Number(this.adminOwnershipForm.to_user_id) : undefined,
                to_account: String(this.adminOwnershipForm?.to_account || this.adminOwnershipTargetQuery || '').trim(),
                scope: String(this.adminOwnershipForm?.scope || 'unowned').trim() || 'unowned',
                from_user_id: this.adminOwnershipForm?.scope === 'from-user' && this.adminOwnershipForm?.from_user_id
                    ? Number(this.adminOwnershipForm.from_user_id)
                    : undefined,
                kinds,
                max_examples: Math.max(1, Math.min(50, Number(this.adminOwnershipForm?.max_examples) || 20)),
            };
        },

        async auditAdminOwnership() {
            const targetUserId = Number(this.adminOwnershipForm?.to_user_id) || 0;
            const userAccount = String(this.adminOwnershipForm?.to_account || '').trim();
            if (!targetUserId && !userAccount) {
                this.showToast('请先选择目标用户', 'warning');
                return;
            }
            this.adminOwnershipAuditLoading = true;
            this.adminOwnershipAuditError = '';
            try {
                const payload = await this.apiCall('/admin/ownership-migrations/audit', {
                    method: 'POST',
                    body: JSON.stringify({
                        user_id: targetUserId || undefined,
                        user_account: userAccount || undefined,
                        kinds: this.buildAdminOwnershipPayload().kinds,
                    }),
                    skipAuthRedirect: true,
                });
                this.adminOwnershipAudit = payload;
                return payload;
            } catch (error) {
                const message = error?.message || '归属审计失败';
                this.adminOwnershipAuditError = message;
                this.showToast(message, 'error');
                return null;
            } finally {
                this.adminOwnershipAuditLoading = false;
            }
        },

        async previewAdminOwnershipMigration() {
            const payload = this.buildAdminOwnershipPayload();
            if (!payload.to_user_id && !payload.to_account) {
                this.showToast('请先选择目标用户', 'warning');
                return;
            }
            if (!Array.isArray(payload.kinds) || payload.kinds.length === 0) {
                this.showToast('请至少选择一种迁移对象', 'warning');
                return;
            }
            if (payload.scope === 'from-user' && !payload.from_user_id) {
                this.showToast('scope=from-user 时必须选择来源用户', 'warning');
                return;
            }
            this.adminOwnershipPreviewLoading = true;
            this.adminOwnershipPreviewError = '';
            this.adminOwnershipConfirmText = '';
            try {
                const result = await this.apiCall('/admin/ownership-migrations/preview', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                    skipAuthRedirect: true,
                });
                this.adminOwnershipPreview = result;
                this.showToast('dry-run 预览已生成，请确认后再正式迁移', 'success');
                return result;
            } catch (error) {
                const message = error?.message || 'dry-run 预览失败';
                this.adminOwnershipPreviewError = message;
                this.showToast(message, 'error');
                return null;
            } finally {
                this.adminOwnershipPreviewLoading = false;
            }
        },

        canApplyAdminOwnershipMigration() {
            const preview = this.adminOwnershipPreview;
            if (!preview || typeof preview !== 'object') return false;
            const confirmPhrase = String(preview.confirm_phrase || '').trim();
            return !!confirmPhrase && String(this.adminOwnershipConfirmText || '').trim() === confirmPhrase && !this.adminOwnershipApplyLoading;
        },

        async applyAdminOwnershipMigration() {
            if (!this.canApplyAdminOwnershipMigration()) {
                this.showToast('请先完成 dry-run，并输入正确确认词', 'warning');
                return;
            }
            const preview = this.adminOwnershipPreview || {};
            const payload = {
                ...this.buildAdminOwnershipPayload(),
                preview_token: preview.preview_token,
                confirm_text: String(this.adminOwnershipConfirmText || '').trim(),
            };
            this.adminOwnershipApplyLoading = true;
            try {
                const result = await this.apiCall('/admin/ownership-migrations/apply', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                    skipAuthRedirect: true,
                });
                this.adminOwnershipPreview = null;
                this.adminOwnershipConfirmText = '';
                await Promise.all([
                    this.loadAdminOwnershipHistory({ silent: true }),
                    this.auditAdminOwnership(),
                ]);
                this.showToast('归属迁移已执行', 'success');
                return result;
            } catch (error) {
                this.showToast(error?.message || '归属迁移失败', 'error');
                return null;
            } finally {
                this.adminOwnershipApplyLoading = false;
            }
        },

        async loadAdminOwnershipHistory(options = {}) {
            const { silent = false } = options;
            if (!this.canViewAdminCenter()) return [];
            this.adminOwnershipHistoryLoading = true;
            this.adminOwnershipHistoryError = '';
            try {
                const payload = await this.apiCall('/admin/ownership-migrations?limit=50', {
                    skipAuthRedirect: true,
                });
                this.adminOwnershipHistory = Array.isArray(payload?.items) ? payload.items : [];
                return this.adminOwnershipHistory;
            } catch (error) {
                const message = error?.message || '迁移历史加载失败';
                this.adminOwnershipHistoryError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return [];
            } finally {
                this.adminOwnershipHistoryLoading = false;
            }
        },

        async rollbackAdminOwnershipMigration(backupId = '') {
            const normalizedBackupId = String(backupId || '').trim();
            if (!normalizedBackupId) return;
            const confirmed = await this.openActionConfirmDialog({
                title: '确认回滚迁移',
                message: `将按备份 ${normalizedBackupId} 恢复归属关系，是否继续？`,
                tone: 'danger',
                confirmText: '确认回滚',
            });
            if (!confirmed) return;
            try {
                const payload = await this.apiCall('/admin/ownership-migrations/rollback', {
                    method: 'POST',
                    body: JSON.stringify({ backup_id: normalizedBackupId }),
                    skipAuthRedirect: true,
                });
                await Promise.all([
                    this.loadAdminOwnershipHistory({ silent: true }),
                    this.auditAdminOwnership(),
                ]);
                this.showToast(payload?.backup_id ? `已回滚 ${payload.backup_id}` : '迁移已回滚', 'success');
            } catch (error) {
                this.showToast(error?.message || '回滚失败', 'error');
            }
        },

        formatBytes(bytes = 0) {
            const value = Number(bytes) || 0;
            if (value <= 0) return '0 B';
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
            const size = value / (1024 ** exponent);
            return `${size.toFixed(size >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
        },

        getAdminOwnershipKindsLabel(kinds = []) {
            const values = Array.isArray(kinds) ? kinds : [];
            const labels = values.map(item => item === 'sessions' ? '会话' : (item === 'reports' ? '报告' : '')).filter(Boolean);
            return labels.length > 0 ? labels.join('、') : '未指定';
        },

        createQuestionOpsLocalState(overrides = {}) {
            return {
                lastRequestAt: 0,
                lastDimension: '',
                lastResultStatus: 'idle',
                lastTier: '',
                lastLane: '',
                lastProfile: '',
                lastFastHedge: null,
                lastFullHedge: null,
                lastHedgeTriggered: false,
                lastFallbackTriggered: false,
                lastOverloadRetryCount: 0,
                lastOverloadWaitMs: 0,
                lastPreferPrefetch: false,
                lastError: '',
                ...overrides
            };
        },

        resetQuestionOpsLocalState() {
            this.questionOpsLocalState = this.createQuestionOpsLocalState();
        },

        updateQuestionOpsLocalState(patch = {}) {
            this.questionOpsLocalState = this.createQuestionOpsLocalState({
                ...(this.questionOpsLocalState || {}),
                ...(patch || {})
            });
        },

        recordQuestionOpsRequestStart({ dimension = '', preferPrefetch = false } = {}) {
            this.updateQuestionOpsLocalState({
                lastRequestAt: Date.now(),
                lastDimension: String(dimension || '').trim(),
                lastResultStatus: 'loading',
                lastTier: '',
                lastLane: '',
                lastProfile: '',
                lastFastHedge: null,
                lastFullHedge: null,
                lastHedgeTriggered: false,
                lastFallbackTriggered: false,
                lastOverloadRetryCount: 0,
                lastOverloadWaitMs: 0,
                lastPreferPrefetch: !!preferPrefetch,
                lastError: ''
            });
        },

        recordQuestionOpsOverloadRetry({ retryCount = 0, waitMs = 0 } = {}) {
            this.updateQuestionOpsLocalState({
                lastResultStatus: 'overloaded',
                lastOverloadRetryCount: Math.max(0, Number(retryCount) || 0),
                lastOverloadWaitMs: Math.max(0, Number(waitMs) || 0)
            });
        },

        recordQuestionOpsOutcome(status = 'idle', payload = {}) {
            const normalizedStatus = String(status || 'idle').trim() || 'idle';
            const decisionMeta = payload?.decisionMeta && typeof payload.decisionMeta === 'object'
                ? payload.decisionMeta
                : {};
            const tier = String(payload?.tier || decisionMeta?.tier_used || '').trim();
            const lane = String(payload?.lane || decisionMeta?.selected_lane || '').trim();
            const profile = String(payload?.profile || '').trim();
            const fastHedgeValue = typeof payload?.fastHedge === 'boolean'
                ? payload.fastHedge
                : (typeof decisionMeta?.fast_hedged_enabled === 'boolean' ? decisionMeta.fast_hedged_enabled : null);
            const fullHedgeValue = typeof payload?.fullHedge === 'boolean'
                ? payload.fullHedge
                : (typeof decisionMeta?.full_hedged_enabled === 'boolean' ? decisionMeta.full_hedged_enabled : null);
            this.updateQuestionOpsLocalState({
                lastResultStatus: normalizedStatus,
                lastTier: tier,
                lastLane: lane,
                lastProfile: profile,
                lastFastHedge: fastHedgeValue,
                lastFullHedge: fullHedgeValue,
                lastHedgeTriggered: !!payload?.hedgeTriggered,
                lastFallbackTriggered: !!payload?.fallbackTriggered,
                lastOverloadRetryCount: Math.max(0, Number(payload?.overloadRetryCount) || 0),
                lastOverloadWaitMs: Math.max(0, Number(payload?.overloadWaitMs) || 0),
                lastError: String(payload?.error || '').trim()
            });
        },

        async loadOpsMetrics(options = {}) {
            const {
                force = false,
                silent = false
            } = options;
            if (!this.canViewOpsMetrics()) {
                return null;
            }
            if (this.opsMetricsLoading && !force) {
                return this.opsMetrics;
            }

            const now = Date.now();
            if (!force && this.opsMetrics && (now - (Number(this.opsMetricsLastLoadedAt) || 0)) < 15000) {
                return this.opsMetrics;
            }

            this.opsMetricsLoading = true;
            this.opsMetricsError = '';
            try {
                const lastN = Math.max(50, Number(this.opsMetricsLastN) || 200);
                const result = await this.apiCall(`/metrics?last_n=${lastN}`, {
                    suppressErrorLog: true,
                    expectedStatuses: [403]
                });
                this.opsMetrics = result && typeof result === 'object' ? result : {};
                this.opsMetricsLastUpdatedAt = Date.now();
                this.opsMetricsLastLoadedAt = this.opsMetricsLastUpdatedAt;
                return this.opsMetrics;
            } catch (error) {
                const message = error?.status === 403 ? '仅管理员可查看运行监控' : (error?.message || '监控数据加载失败');
                this.opsMetricsError = message;
                if (!silent) {
                    this.showToast(message, 'error');
                }
                return null;
            } finally {
                this.opsMetricsLoading = false;
            }
        },

        refreshOpsMetricsIfVisible(options = {}) {
            if (!this.canViewOpsMetrics()) {
                return;
            }
            if (!(this.currentView === 'admin' && this.adminTab === 'ops')) {
                return;
            }
            void this.loadOpsMetrics({
                force: true,
                silent: true,
                ...options
            });
        },

        getOpsMetricsFreshnessText() {
            const updatedAt = Number(this.opsMetricsLastUpdatedAt) || 0;
            if (!updatedAt) return '尚未加载';
            const deltaSeconds = Math.max(0, Math.floor((Date.now() - updatedAt) / 1000));
            if (deltaSeconds < 5) return '刚刚更新';
            if (deltaSeconds < 60) return `${deltaSeconds} 秒前更新`;
            const deltaMinutes = Math.floor(deltaSeconds / 60);
            if (deltaMinutes < 60) return `${deltaMinutes} 分钟前更新`;
            return this.formatDate(updatedAt);
        },

        getQuestionFastStageGroups(limit = 4) {
            const groups = Array.isArray(this.opsMetrics?.stage_profiles?.groups)
                ? this.opsMetrics.stage_profiles.groups
                : [];
            return groups
                .filter((group) => group && group.stage === 'question_fast')
                .sort((left, right) => {
                    const countGap = (Number(right?.count) || 0) - (Number(left?.count) || 0);
                    if (countGap !== 0) return countGap;
                    return (Number(left?.p50_ms) || 0) - (Number(right?.p50_ms) || 0);
                })
                .slice(0, Math.max(1, Number(limit) || 4));
        },

        getQuestionFastStageSummary() {
            const stageSummary = this.opsMetrics?.stage_profiles?.stages?.question_fast;
            if (stageSummary && typeof stageSummary === 'object') {
                return stageSummary;
            }
            return {
                count: 0,
                success_rate: 0,
                p50_ms: 0,
                p95_ms: 0
            };
        },

        getQuestionOpsStatusLabel(status = '') {
            const normalized = String(status || '').trim().toLowerCase();
            if (normalized === 'loading') return '请求中';
            if (normalized === 'success') return 'AI 成功';
            if (normalized === 'fallback') return '备用题目';
            if (normalized === 'overloaded') return '排队重试';
            if (normalized === 'completed') return '维度完成';
            if (normalized === 'stalled') return '请求停滞';
            if (normalized === 'interrupted') return '请求中断';
            if (normalized === 'error') return '请求失败';
            return '空闲';
        },

        formatOpsDurationMs(value) {
            const numeric = Number(value);
            if (!Number.isFinite(numeric) || numeric <= 0) return '0 ms';
            if (numeric >= 1000) return `${(numeric / 1000).toFixed(numeric >= 10000 ? 0 : 1)} s`;
            return `${Math.round(numeric)} ms`;
        },

        formatOpsPercent(value) {
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) return '0%';
            return `${numeric.toFixed(numeric % 1 === 0 ? 0 : 2)}%`;
        },

        formatOpsBool(flag, yesText = '开启', noText = '关闭', unknownText = '未知') {
            if (typeof flag !== 'boolean') return unknownText;
            return flag ? yesText : noText;
        },

        openActionConfirmDialog(options = {}) {
            if (typeof this.actionConfirmResolve === 'function') {
                this.actionConfirmResolve(false);
            }

            const {
                title = '确认操作',
                message = '是否继续？',
                tone = 'warning',
                confirmText = '确认',
                cancelText = '取消'
            } = options;

            this.actionConfirmDialog = {
                title,
                message,
                tone: tone === 'danger' ? 'danger' : 'warning',
                confirmText,
                cancelText
            };
            this.showActionConfirmModal = true;

            return new Promise((resolve) => {
                this.actionConfirmResolve = resolve;
            });
        },

        resolveActionConfirmDialog(confirmed) {
            this.showActionConfirmModal = false;
            const resolver = this.actionConfirmResolve;
            this.actionConfirmResolve = null;
            if (typeof resolver === 'function') {
                resolver(Boolean(confirmed));
            }
        },

        confirmActionConfirmDialog() {
            this.resolveActionConfirmDialog(true);
        },

        cancelActionConfirmDialog() {
            this.resolveActionConfirmDialog(false);
        },

        registerDialogFocusWatchers() {
            if (this.dialogFocusWatchRegistered || typeof this.$watch !== 'function') return;
            this.dialogFocusWatchRegistered = true;
            this.registerDialogTabTrap();

            this.managedDialogKeys.forEach((key) => {
                this.$watch(key, (isVisible) => {
                    if (isVisible) {
                        this.captureDialogFocusTarget(key);
                        this.$nextTick(() => this.focusDialogAutofocus(key));
                        return;
                    }
                    this.$nextTick(() => this.restoreDialogFocusTarget(key));
                });
            });
        },

        registerDialogTabTrap() {
            if (this.dialogTabTrapRegistered || typeof document === 'undefined') return;
            this.dialogTabTrapRegistered = true;

            this.dialogTabTrapListener = (event) => {
                if (event.key !== 'Tab') return;
                const key = this.getTopVisibleDialogKey();
                if (!key) return;

                const dialog = document.querySelector(`[data-dialog-key="${key}"]`);
                if (!(dialog instanceof HTMLElement)) return;
                this.trapDialogFocus(event, dialog);
            };

            document.addEventListener('keydown', this.dialogTabTrapListener, true);
        },

        getTopVisibleDialogKey() {
            for (let index = this.managedDialogKeys.length - 1; index >= 0; index -= 1) {
                const key = this.managedDialogKeys[index];
                if (this[key]) return key;
            }
            return '';
        },

        trapDialogFocus(event, dialog) {
            if (!(dialog instanceof HTMLElement)) return;

            const focusableSelector = 'button:not([disabled]):not([tabindex="-1"]), [href], input:not([disabled]):not([tabindex="-1"]), select:not([disabled]):not([tabindex="-1"]), textarea:not([disabled]):not([tabindex="-1"]), [tabindex]:not([tabindex="-1"])';
            const focusable = Array.from(dialog.querySelectorAll(focusableSelector)).filter((element) => {
                if (!(element instanceof HTMLElement)) return false;
                if (element.hasAttribute('disabled') || element.getAttribute('aria-hidden') === 'true') return false;
                return element.offsetParent !== null || element === document.activeElement;
            });

            if (focusable.length === 0) {
                event.preventDefault();
                if (typeof dialog.focus === 'function') {
                    dialog.focus({ preventScroll: true });
                }
                return;
            }

            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            const active = document.activeElement;
            const activeInside = active instanceof HTMLElement && dialog.contains(active);

            if (event.shiftKey) {
                if (active === first || !activeInside) {
                    event.preventDefault();
                    last.focus({ preventScroll: true });
                }
                return;
            }

            if (active === last || !activeInside) {
                event.preventDefault();
                first.focus({ preventScroll: true });
            }
        },

        captureDialogFocusTarget(key) {
            const activeElement = document.activeElement;
            if (!(activeElement instanceof HTMLElement)) return;
            if (typeof activeElement.focus !== 'function') return;
            this.dialogFocusReturnTargets[key] = activeElement;
        },

        getDialogConfig(key) {
            if (!key) return {};
            return this.dialogA11yConfig?.[key] || {};
        },

        getDialogAttrs(key) {
            const config = this.getDialogConfig(key);
            const attrs = {
                role: 'dialog',
                'aria-modal': 'true',
                tabindex: '-1'
            };

            if (config.dialogId) attrs.id = config.dialogId;
            if (config.titleId) attrs['aria-labelledby'] = config.titleId;
            if (config.descId) attrs['aria-describedby'] = config.descId;

            return attrs;
        },

        getDialogPanelAttrs(key) {
            const config = this.getDialogConfig(key);
            const attrs = {};

            if (config.titleId) attrs['aria-labelledby'] = config.titleId;
            if (config.descId) attrs['aria-describedby'] = config.descId;

            return attrs;
        },

        resolveDialogInitialFocus(key, dialog) {
            if (!(dialog instanceof HTMLElement)) return null;
            const config = this.getDialogConfig(key);
            if (config.initialFocus) {
                const preferred = dialog.querySelector(config.initialFocus);
                if (preferred instanceof HTMLElement && !preferred.hasAttribute('disabled')) {
                    return preferred;
                }
            }

            const fallback = dialog.querySelector('[data-dialog-autofocus]')
                || dialog.querySelector('input, textarea, button, [href], [tabindex]:not([tabindex="-1"])');
            if (!(fallback instanceof HTMLElement) || fallback.hasAttribute('disabled')) {
                return null;
            }
            return fallback;
        },

        focusDialogAutofocus(key) {
            const dialog = document.querySelector(`[data-dialog-key="${key}"]`);
            if (!(dialog instanceof HTMLElement)) return;

            const target = this.resolveDialogInitialFocus(key, dialog);
            if (!(target instanceof HTMLElement)) return;
            target.focus({ preventScroll: true });
        },

        isAnyDialogVisible(exceptKey = '') {
            return this.managedDialogKeys.some((key) => key !== exceptKey && Boolean(this[key]));
        },

        restoreDialogFocusTarget(key) {
            const target = this.dialogFocusReturnTargets[key];
            delete this.dialogFocusReturnTargets[key];

            if (this.isAnyDialogVisible(key)) return;
            if (target instanceof HTMLElement && target.isConnected && typeof target.focus === 'function') {
                target.focus({ preventScroll: true });
                return;
            }

            const returnSelector = this.getDialogConfig(key)?.returnFocus;
            if (!returnSelector) return;

            const fallbackTarget = document.querySelector(returnSelector);
            if (!(fallbackTarget instanceof HTMLElement)) return;
            if (typeof fallbackTarget.focus !== 'function') return;
            fallbackTarget.focus({ preventScroll: true });
        },

        applyDesignTokens(mode = 'system', effectiveTheme = this.effectiveTheme || 'light') {
            if (typeof document === 'undefined') return;

            const tokens = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.designTokens)
                ? SITE_CONFIG.designTokens
                : null;
            const visualPresetConfig = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.visualPresets?.options)
                ? SITE_CONFIG.visualPresets.options
                : null;
            const motion = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.motion)
                ? SITE_CONFIG.motion
                : null;
            const a11y = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.a11y)
                ? SITE_CONFIG.a11y
                : null;

            const root = document.documentElement;
            const palette = effectiveTheme === 'dark' ? tokens?.dark?.colors : tokens?.light?.colors;
            const preset = visualPresetConfig?.[this.visualPreset] || null;
            const presetByTheme = effectiveTheme === 'dark' ? preset?.dark : preset?.light;
            const presetColors = presetByTheme?.colors || {};
            const presetShadow = presetByTheme?.shadow || {};
            const presetRadius = preset?.radius || {};
            const presetMotion = preset?.motion || {};

            const tokenMap = {
                '--dv-color-brand': presetColors.brand ?? palette?.brand,
                '--dv-color-brand-hover': presetColors.brandHover ?? palette?.brandHover,
                '--dv-color-text-primary': palette?.textPrimary,
                '--dv-color-text-secondary': palette?.textSecondary,
                '--dv-color-text-muted': palette?.textMuted,
                '--dv-color-surface': palette?.surface,
                '--dv-color-surface-secondary': palette?.surfaceSecondary,
                '--dv-color-border': palette?.border,
                '--dv-color-success': palette?.success,
                '--dv-color-warning': palette?.warning,
                '--dv-color-danger': palette?.danger,
                '--dv-color-overlay': presetColors.overlay ?? palette?.overlay,
                '--dv-radius-sm': tokens?.radius?.sm,
                '--dv-radius-md': presetRadius.md ?? tokens?.radius?.md,
                '--dv-radius-lg': presetRadius.lg ?? tokens?.radius?.lg,
                '--dv-radius-xl': presetRadius.xl ?? tokens?.radius?.xl,
                '--dv-shadow-card': presetShadow.card ?? tokens?.shadow?.card,
                '--dv-shadow-modal': presetShadow.modal ?? tokens?.shadow?.modal,
                '--dv-shadow-focus': tokens?.shadow?.focus,
                '--dv-z-dropdown': Number.isFinite(tokens?.zIndex?.dropdown) ? String(tokens.zIndex.dropdown) : null,
                '--dv-z-modal': Number.isFinite(tokens?.zIndex?.modal) ? String(tokens.zIndex.modal) : null,
                '--dv-z-toast': Number.isFinite(tokens?.zIndex?.toast) ? String(tokens.zIndex.toast) : null,
                '--dv-z-guide': Number.isFinite(tokens?.zIndex?.guide) ? String(tokens.zIndex.guide) : null,
                '--dv-duration-fast': Number.isFinite(motion?.durations?.fast) ? `${motion.durations.fast}ms` : null,
                '--dv-duration-base': Number.isFinite(presetMotion?.durations?.base)
                    ? `${presetMotion.durations.base}ms`
                    : (Number.isFinite(motion?.durations?.base) ? `${motion.durations.base}ms` : null),
                '--dv-duration-slow': Number.isFinite(presetMotion?.durations?.slow)
                    ? `${presetMotion.durations.slow}ms`
                    : (Number.isFinite(motion?.durations?.slow) ? `${motion.durations.slow}ms` : null),
                '--dv-duration-progress': Number.isFinite(motion?.durations?.progress) ? `${motion.durations.progress}ms` : null,
                '--dv-ease-standard': motion?.easing?.standard,
                '--dv-ease-emphasized': presetMotion?.easing?.emphasized ?? motion?.easing?.emphasized
            };

            Object.entries(tokenMap).forEach(([key, value]) => {
                if (value === undefined || value === null || value === '') return;
                root.style.setProperty(key, value);
            });

            const focusRing = a11y?.focusRing || {};
            const isDark = effectiveTheme === 'dark';
            const focusMap = {
                '--dv-focus-border-color': isDark ? focusRing.borderColorDark : focusRing.borderColorLight,
                '--dv-focus-ring-color': isDark ? focusRing.ringColorDark : focusRing.ringColorLight,
                '--dv-focus-ring-strong': isDark ? focusRing.ringStrongDark : focusRing.ringStrongLight,
                '--dv-focus-underlay': isDark ? focusRing.underlayDark : focusRing.underlayLight
            };

            Object.entries(focusMap).forEach(([key, value]) => {
                if (value === undefined || value === null || value === '') return;
                root.style.setProperty(key, value);
            });
        },

        initTheme() {
            const validModes = ['light', 'dark', 'system'];
            const configuredMode = (typeof SITE_CONFIG !== 'undefined' ? SITE_CONFIG?.theme?.defaultMode : null) || 'system';
            let mode = validModes.includes(configuredMode) ? configuredMode : 'system';

            const bootstrap = window.__DV_THEME_BOOTSTRAP__;
            if (bootstrap && validModes.includes(bootstrap.mode)) {
                mode = bootstrap.mode;
            } else {
                try {
                    const savedMode = localStorage.getItem(this.themeStorageKey);
                    if (validModes.includes(savedMode)) {
                        mode = savedMode;
                    }
                } catch (error) {
                    console.warn('读取主题配置失败，使用默认模式');
                }
            }

            this.applyThemeMode(mode, { persist: false, rerenderCharts: false });

            if (!window.matchMedia) return;
            this.systemThemeMedia = window.matchMedia('(prefers-color-scheme: dark)');
            this.systemThemeListener = (event) => {
                if (this.themeMode !== 'system') return;
                this.applyThemeMode('system', {
                    persist: false,
                    rerenderCharts: true,
                    preferredDark: event.matches
                });
            };

            if (typeof this.systemThemeMedia.addEventListener === 'function') {
                this.systemThemeMedia.addEventListener('change', this.systemThemeListener);
            } else if (typeof this.systemThemeMedia.addListener === 'function') {
                this.systemThemeMedia.addListener(this.systemThemeListener);
            }
        },

        resolveEffectiveTheme(mode, preferredDark = null) {
            if (mode === 'light' || mode === 'dark') return mode;
            const matchesDark = preferredDark !== null
                ? preferredDark
                : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
            return matchesDark ? 'dark' : 'light';
        },
        resolveVisualPreset() {
            const presetConfig = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG?.visualPresets) ? SITE_CONFIG.visualPresets : null;
            const defaultPreset = presetConfig?.default || 'rational';
            const options = presetConfig?.options || {};
            return options[defaultPreset] ? defaultPreset : 'rational';
        },

        applyThemeMode(mode, options = {}) {
            const validModes = ['light', 'dark', 'system'];
            if (!validModes.includes(mode)) mode = 'system';

            const persist = options.persist !== false;
            const rerenderCharts = options.rerenderCharts !== false;
            const effective = this.resolveEffectiveTheme(mode, options.preferredDark ?? null);

            this.themeMode = mode;
            this.effectiveTheme = effective;
            this.showAccountMenu = false;

            const root = document.documentElement;
            root.setAttribute('data-theme-mode', mode);
            root.setAttribute('data-theme', effective);
            root.style.colorScheme = effective;
            this.applyDesignTokens(mode, effective);

            if (persist) {
                try {
                    localStorage.setItem(this.themeStorageKey, mode);
                } catch (error) {
                    console.warn('保存主题配置失败');
                }
            }

            this.applyMermaidTheme(effective);

            if (rerenderCharts) {
                this.$nextTick(() => this.rerenderMermaidChartsForTheme());
            }
        },

        setThemeMode(mode) {
            this.applyThemeMode(mode);
        },

        themeModeLabel(mode = this.themeMode) {
            if (mode === 'light') return '浅色';
            if (mode === 'dark') return '深色';
            return '跟随系统';
        },

        getThemeOptionClass(mode) {
            const active = this.themeMode === mode;
            if (this.effectiveTheme === 'dark') {
                return active ? 'dv-dark-theme-option-active' : 'dv-dark-theme-option';
            }
            return active
                ? 'bg-gray-900 text-white border-gray-900'
                : 'text-gray-600 border-transparent hover:bg-gray-100 hover:text-gray-900';
        },

        getHeaderNavClass(isActive = false) {
            if (this.effectiveTheme === 'dark') {
                return isActive ? 'dv-dark-nav-active' : 'dv-dark-nav';
            }
            return isActive
                ? 'bg-gray-900 text-white'
                : 'text-primary hover:bg-surface-secondary';
        },

        isSessionViewActive() {
            return this.currentView === 'sessions' || this.currentView === 'interview';
        },

        applyMermaidTheme(theme) {
            if (typeof mermaid === 'undefined') return;
            try {
                if (typeof window.getDeepVisionMermaidConfig === 'function') {
                    mermaid.initialize(window.getDeepVisionMermaidConfig(theme));
                }
            } catch (error) {
                console.warn('切换图表主题失败:', error);
            }
        },

        rerenderMermaidChartsForTheme() {
            const renderedCharts = document.querySelectorAll('.mermaid.mermaid-rendered');
            if (renderedCharts.length === 0) return;

            renderedCharts.forEach((element) => {
                const definition = element.dataset.mermaidDefinition;
                if (!definition) return;
                element.classList.remove('mermaid-rendered', 'mermaid-failed');
                element.textContent = definition;
            });

            this.renderMermaidCharts();
        },

        // 检查首次访问
        checkFirstVisit() {
            const hasSeenIntro = localStorage.getItem('deepvision_intro_seen');
            if (!hasSeenIntro) {
                localStorage.setItem('deepvision_intro_seen', 'true');
                window.location.href = 'intro.html';
                return true;
            }
            return false;
        },
        initGuide() {
            const params = new URLSearchParams(window.location.search);
            const forced = params.get('guide') === '1';
            this.hasSeenGuide = localStorage.getItem('deepvision_guide_seen') === 'true';
            if (forced || !this.hasSeenGuide) {
                this.openGuide();
            }
            if (forced) {
                params.delete('guide');
                const newUrl = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
                window.history.replaceState({}, '', newUrl);
            }
        },
        openGuide() {
            this.showGuide = true;
            this.guideStepIndex = 0;
            this.guideCloseHintLastAt = 0;
            this.runGuideStep();
        },
        exitGuide() {
            this.clearGuideHighlight();
            this.stopGuideObserver();
            this.showGuide = false;
            this.guideSpotlightStyle = '';
            this.guideCardStyle = '';
            this.hasSeenGuide = true;
            localStorage.setItem('deepvision_guide_seen', 'true');
        },
        completeGuide() {
            this.clearGuideHighlight();
            this.stopGuideObserver();
            this.showGuide = false;
            this.guideSpotlightStyle = '';
            this.guideCardStyle = '';
            this.hasSeenGuide = true;
            localStorage.setItem('deepvision_guide_seen', 'true');
        },
        async nextGuideStep() {
            const step = this.guideSteps[this.guideStepIndex];
            if (step?.onNext) {
                const result = await step.onNext.call(this);
                if (result === false) return;
            }
            if (this.guideStepIndex < this.guideSteps.length - 1) {
                this.guideStepIndex += 1;
                this.runGuideStep();
            } else {
                this.completeGuide();
            }
        },
        prevGuideStep() {
            if (this.guideStepIndex > 0) {
                this.guideStepIndex -= 1;
                this.runGuideStep();
            }
        },
        runGuideStep() {
            if (!this.showGuide) return;
            const step = this.guideSteps[this.guideStepIndex];
            if (!step) return;
            if (step.onEnter) {
                step.onEnter.call(this);
            }
            this.$nextTick(() => {
                this.scrollGuideTarget();
                this.waitForGuideTarget();
            });
        },
        scrollGuideTarget() {
            const step = this.guideSteps[this.guideStepIndex];
            const el = step ? document.querySelector(step.selector) : null;
            if (el && typeof el.scrollIntoView === 'function') {
                el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
            }
        },
        waitForGuideTarget(attempt = 0) {
            if (!this.showGuide) return;
            const step = this.guideSteps[this.guideStepIndex];
            const el = step ? document.querySelector(step.selector) : null;
            if (!el && attempt < 20) {
                setTimeout(() => this.waitForGuideTarget(attempt + 1), 200);
                return;
            }
            if (!el) {
                this.exitGuide();
                return;
            }
            this.updateGuideTarget();
        },
        updateGuideTarget() {
            if (!this.showGuide) return;
            const step = this.guideSteps[this.guideStepIndex];
            const el = step ? document.querySelector(step.selector) : null;
            if (!el) {
                this.clearGuideHighlight();
                this.guideSpotlightStyle = 'display:none;';
                this.guideCardStyle = 'opacity:0;';
                return;
            }
            this.setGuideHighlight(el);
            this.startGuideObserver(el);
            const rect = el.getBoundingClientRect();
            const padding = 10;
            const top = Math.max(rect.top - padding, 6);
            const left = Math.max(rect.left - padding, 6);
            const width = Math.min(rect.width + padding * 2, window.innerWidth - 12);
            const height = Math.min(rect.height + padding * 2, window.innerHeight - 12);
            this.guideSpotlightStyle = `top:${top}px;left:${left}px;width:${width}px;height:${height}px;`;

            const cardWidth = 320;
            const cardHeight = 160;
            let cardTop = rect.bottom + 14;
            if (cardTop + cardHeight > window.innerHeight) {
                cardTop = rect.top - cardHeight - 14;
            }
            if (cardTop < 12) cardTop = 12;
            let cardLeft = rect.left;
            if (cardLeft + cardWidth > window.innerWidth - 12) {
                cardLeft = window.innerWidth - cardWidth - 12;
            }
            if (cardLeft < 12) cardLeft = 12;
            this.guideCardStyle = `top:${cardTop}px;left:${cardLeft}px;width:${cardWidth}px;`;
        },
        setGuideHighlight(el) {
            if (this.guideHighlightedEl === el) return;
            this.clearGuideHighlight();
            this.guideHighlightedEl = el;
            el.classList.add('guide-highlight-target');
        },
        clearGuideHighlight() {
            if (this.guideHighlightedEl) {
                this.guideHighlightedEl.classList.remove('guide-highlight-target');
                this.guideHighlightedEl = null;
            }
        },
        startGuideObserver(el) {
            const modalEl = document.querySelector('[data-guide="guide-modal"]');
            if (!this.guideResizeObserver) {
                this.guideResizeObserver = new ResizeObserver(() => {
                    this.updateGuideTarget();
                });
            }
            if (this.guideObservedEl !== el) {
                if (this.guideObservedEl) {
                    this.guideResizeObserver.unobserve(this.guideObservedEl);
                }
                this.guideResizeObserver.observe(el);
                this.guideObservedEl = el;
            }
            if (modalEl && this.guideObservedModal !== modalEl) {
                if (this.guideObservedModal) {
                    this.guideResizeObserver.unobserve(this.guideObservedModal);
                }
                this.guideResizeObserver.observe(modalEl);
                this.guideObservedModal = modalEl;
            }
        },
        stopGuideObserver() {
            if (this.guideResizeObserver) {
                this.guideResizeObserver.disconnect();
                this.guideResizeObserver = null;
            }
            this.guideObservedEl = null;
            this.guideObservedModal = null;
        },

        // 加载版本信息
        async loadVersionInfo() {
            try {
                const configFile = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.version?.configFile) || 'version.json';
                const response = await fetch(configFile);
                if (response.ok) {
                    const data = await response.json();
                    this.appVersion = data.version || this.appVersion;
                }
            } catch (error) {
                console.warn('无法加载版本信息:', error);
            }
        },

        // 启动诗句轮播
        startQuoteRotation() {
            if (this.quoteRotationInterval) {
                clearInterval(this.quoteRotationInterval);
                this.quoteRotationInterval = null;
            }

            // 如果配置文件禁用了诗句轮播或没有诗句，则不启动
            if (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.quotes?.enabled === false) {
                return;
            }
            if (this.quotes.length === 0) {
                return;
            }

            // 从配置文件读取轮播间隔
            const interval = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.quotes?.interval)
                ? SITE_CONFIG.quotes.interval
                : 10000;  // 默认10秒

            this.quoteRotationInterval = setInterval(() => {
                this.currentQuoteIndex = (this.currentQuoteIndex + 1) % this.quotes.length;
                this.currentQuote = this.quotes[this.currentQuoteIndex].text;
                this.currentQuoteSource = this.quotes[this.currentQuoteIndex].source;
            }, interval);
        },

        // 检查服务器状态
        async checkServerStatus() {
            try {
                const response = await fetch(`${API_BASE}/status`);
                if (response.ok) {
                    this.serverStatus = await response.json();
                    this.licenseEnforcementEnabled = Boolean(this.serverStatus?.license_enforcement_enabled);
                    this.applyUserLevelPayload(this.serverStatus || {});
                    this.applyPresentationFeaturePayload(this.serverStatus || {});
                    if (this.serverStatus?.license) {
                        this.applyLicenseStatusPayload(this.serverStatus.license);
                    }
                    if (typeof this.serverStatus.ai_available === 'boolean') {
                        this.aiAvailable = this.serverStatus.ai_available;
                    }
                    if (typeof this.serverStatus.wechat_login_enabled === 'boolean') {
                        this.wechatLoginEnabled = this.serverStatus.wechat_login_enabled;
                    }
                    if (typeof this.serverStatus.sms_login_enabled === 'boolean') {
                        this.smsLoginEnabled = this.serverStatus.sms_login_enabled;
                        if (!this.smsLoginEnabled && this.showBindPhoneModal && !this.bindPhoneLoading) {
                            this.closeBindPhoneModal();
                        }
                    }
                    if (Number.isFinite(Number(this.serverStatus.sms_code_length))) {
                        this.smsCodeLength = Math.max(4, Math.min(8, Math.floor(Number(this.serverStatus.sms_code_length))));
                    }
                    if (Number.isFinite(Number(this.serverStatus.sms_cooldown_seconds))) {
                        this.smsCooldownSeconds = Math.max(1, Math.min(300, Number(this.serverStatus.sms_cooldown_seconds)));
                    }
                    const reportProfileDefault = this.normalizeReportProfile(
                        this.serverStatus?.report_profile_default,
                        this.reportProfileDefault || 'balanced'
                    ) || 'balanced';
                    this.reportProfileDefault = this.canUseReportProfile(reportProfileDefault)
                        ? reportProfileDefault
                        : (this.allowedReportProfiles[0] || 'balanced');
                    if (!this.canUseReportProfile(this.reportProfile)) {
                        this.reportProfile = this.reportProfileDefault;
                    }
                    const depthConfig = this.serverStatus?.interview_depth_v2 || {};
                    this.interviewDepthV2 = {
                        enabled: true,
                        modes: Array.isArray(depthConfig.modes) ? depthConfig.modes : ['quick', 'standard', 'deep'],
                        deep_mode_skip_followup_confirm: depthConfig.deep_mode_skip_followup_confirm !== false,
                        mode_configs: depthConfig.mode_configs || null
                    };
                    if (typeof this.serverStatus.ai_available === 'boolean' && !this.aiAvailable) {
                        this.showToast('AI 功能未启用（需设置 ANTHROPIC_API_KEY）', 'warning');
                    }
                }
            } catch (error) {
                console.error('服务器连接失败:', error);
                this.showToast('无法连接到服务器，请确保 server.py 正在运行', 'error');
            }
        },

        // 开始轮询 Web Search 状态
        startWebSearchPolling(requestId = this.questionRequestId) {
            // 先停止旧的轮询，防止多个轮询并发
            this.stopWebSearchPolling();
            const currentRequestId = Number(requestId) || 0;
            this.webSearchPollRequestId = currentRequestId;

            // 从配置文件读取轮询间隔
            const pollInterval = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.api?.webSearchPollInterval)
                ? SITE_CONFIG.api.webSearchPollInterval
                : 200;  // 默认 200ms

            this.webSearchPollInterval = setInterval(async () => {
                if (!this.loadingQuestion || currentRequestId !== this.questionRequestId || currentRequestId !== this.webSearchPollRequestId) {
                    this.stopWebSearchPolling();
                    return;
                }
                try {
                    const response = await fetch(`${API_BASE}/status/web-search`);
                    if (!this.loadingQuestion || currentRequestId !== this.questionRequestId || currentRequestId !== this.webSearchPollRequestId) {
                        return;
                    }
                    if (response.ok) {
                        const data = await response.json();
                        if (!this.loadingQuestion || currentRequestId !== this.questionRequestId || currentRequestId !== this.webSearchPollRequestId) {
                            return;
                        }
                        this.webSearching = data.active;
                        if (data.active) {
                            this.markQuestionRequestActive(currentRequestId);
                        } else if (this.questionRequestPreferPrefetch && (Date.now() - (Number(this.questionRequestStartedAt) || Date.now())) < QUESTION_SUBMIT_PREFETCH_WAIT_MS) {
                            this.markQuestionRequestActive(currentRequestId);
                        } else {
                            this.observeQuestionRequestIdle(currentRequestId);
                        }
                    }
                } catch (error) {
                    // 轮询失败时不显示错误，静默处理
                }
            }, pollInterval);
        },

        // 停止轮询 Web Search 状态
        stopWebSearchPolling() {
            if (this.webSearchPollInterval) {
                clearInterval(this.webSearchPollInterval);
                this.webSearchPollInterval = null;
            }
            this.webSearchPollRequestId = 0;
            this.webSearching = false;  // 重置状态
        },

        startQuestionRequestGuard(requestId = this.questionRequestId) {
            this.stopQuestionRequestGuard();
            const currentRequestId = Number(requestId) || 0;
            const now = Date.now();
            this.questionRequestStartedAt = now;
            this.questionRequestLastActiveAt = now;
            this.questionRequestWatchdogTimer = setInterval(() => {
                if (!this.loadingQuestion || currentRequestId !== this.questionRequestId) {
                    this.stopQuestionRequestGuard();
                    return;
                }

                const startedAt = Number(this.questionRequestStartedAt) || now;
                const lastActiveAt = Number(this.questionRequestLastActiveAt) || startedAt;
                const elapsed = Date.now() - startedAt;
                const idleElapsed = Date.now() - lastActiveAt;
                const waitingPrefetch = Boolean(this.questionRequestPreferPrefetch && elapsed < QUESTION_SUBMIT_PREFETCH_WAIT_MS);
                const hasLiveProgress = Boolean(this.webSearching || this.thinkingStage?.active || waitingPrefetch);

                if (elapsed >= QUESTION_REQUEST_HARD_TIMEOUT_MS) {
                    void this.recoverStalledQuestionRequest(currentRequestId, 'timeout');
                    return;
                }

                if (elapsed < QUESTION_REQUEST_SOFT_TIMEOUT_MS) {
                    return;
                }

                if (hasLiveProgress || idleElapsed < QUESTION_REQUEST_IDLE_MS) {
                    return;
                }

                void this.recoverStalledQuestionRequest(currentRequestId, 'timeout');
            }, QUESTION_REQUEST_WATCHDOG_INTERVAL_MS);
        },

        stopQuestionRequestGuard() {
            if (this.questionRequestWatchdogTimer) {
                clearInterval(this.questionRequestWatchdogTimer);
                this.questionRequestWatchdogTimer = null;
            }
            this.questionRequestStartedAt = 0;
            this.questionRequestLastActiveAt = 0;
        },

        abortQuestionRequest() {
            const controller = this.questionRequestAbortController;
            this.questionRequestAbortController = null;
            if (!controller) return;
            try {
                controller.abort();
            } catch (error) {
                console.warn('取消问题请求失败:', error);
            }
        },

        parseQuestionRetryAfterSeconds(response) {
            const rawHeader = String(response?.headers?.get('Retry-After') || '').trim();
            const parsedHeader = Number.parseFloat(rawHeader);
            if (Number.isFinite(parsedHeader) && parsedHeader > 0) {
                return Math.max(1, Math.ceil(parsedHeader));
            }
            return QUESTION_OVERLOAD_RETRY_DEFAULT_SECONDS;
        },

        async waitForQuestionOverloadRetry(requestId, delayMs) {
            const currentRequestId = Number(requestId) || 0;
            const safeDelayMs = Math.max(0, Number(delayMs) || 0);
            if (!safeDelayMs) {
                return currentRequestId === this.questionRequestId;
            }
            await new Promise((resolve) => setTimeout(resolve, safeDelayMs));
            return currentRequestId === this.questionRequestId;
        },

        markQuestionRequestActive(requestId = this.questionRequestId) {
            const currentRequestId = Number(requestId) || 0;
            if (!this.loadingQuestion || currentRequestId !== this.questionRequestId) {
                return;
            }
            this.questionRequestLastActiveAt = Date.now();
        },

        observeQuestionRequestIdle(requestId = this.questionRequestId) {
            const currentRequestId = Number(requestId) || 0;
            if (!this.loadingQuestion || currentRequestId !== this.questionRequestId) {
                return;
            }
            const startedAt = Number(this.questionRequestStartedAt) || 0;
            if (!startedAt) {
                return;
            }
            const now = Date.now();
            if (this.questionRequestPreferPrefetch && (now - startedAt) < QUESTION_SUBMIT_PREFETCH_WAIT_MS) {
                return;
            }
            if (now - startedAt < QUESTION_REQUEST_STALL_GRACE_MS) {
                return;
            }
            const lastActiveAt = Number(this.questionRequestLastActiveAt) || startedAt;
            if (now - lastActiveAt < QUESTION_REQUEST_IDLE_MS) {
                return;
            }
            if (this.webSearching || this.thinkingStage?.active) {
                return;
            }
            void this.recoverStalledQuestionRequest(currentRequestId, 'stalled');
        },

        async recoverStalledQuestionRequest(requestId = this.questionRequestId, reason = 'stalled') {
            const currentRequestId = Number(requestId) || 0;
            if (!this.loadingQuestion || currentRequestId !== this.questionRequestId) {
                return;
            }

            // 标记旧请求过期，避免迟到响应覆盖界面。
            this.questionRequestId += 1;
            this.abortQuestionRequest();
            this.stopQuestionRequestGuard();
            this.stopThinkingPolling();
            this.stopWebSearchPolling();
            this.stopTipRotation();
            this.loadingQuestion = false;
            this.isGoingPrev = false;

            const sessionId = this.currentSession?.session_id;
            if (sessionId) {
                try {
                    this.currentSession = await this.apiCall(`/sessions/${sessionId}`, { suppressErrorLog: true });
                    this.updateDimensionsFromSession(this.currentSession);
                } catch (error) {
                    console.warn('刷新会话状态失败:', error);
                }
            }

            const nextDim = this.getNextIncompleteDimension();
            const currentCoverage = Number(this.currentSession?.dimensions?.[this.currentDimension]?.coverage) || 0;
            if (!nextDim) {
                this.recordQuestionOpsOutcome('completed', {
                    error: ''
                });
                this.currentStep = 1;
                this.currentQuestion = this.createQuestionState();
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                this.showToast('所有维度访谈完成！', 'success');
                this.refreshOpsMetricsIfVisible();
                return;
            }

            if (currentCoverage >= 100 && nextDim !== this.currentDimension) {
                this.recordQuestionOpsOutcome('completed', {
                    error: ''
                });
                const completedDimension = this.currentDimension;
                this.ensureDimensionVisualComplete(completedDimension);
                this.currentDimension = nextDim;
                this.currentQuestion = this.createQuestionState();
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                this.showToast(`当前维度已完成，已恢复到${this.getDimensionName(nextDim)}`, 'warning');
                this.refreshOpsMetricsIfVisible();
                await this.fetchNextQuestion();
                return;
            }

            const timeoutTriggered = reason === 'timeout';
            this.recordQuestionOpsOutcome(timeoutTriggered ? 'error' : 'stalled', {
                error: timeoutTriggered ? '生成问题超时' : '问题生成已中断'
            });
            this.currentQuestion = this.createQuestionState({
                serviceError: true,
                errorTitle: timeoutTriggered ? '生成问题超时' : '问题生成已中断',
                errorDetail: timeoutTriggered
                    ? '获取下一题耗时过长，已自动停止等待。请点击“重新获取问题”继续。'
                    : '长时间没有收到新的问题结果，已自动停止等待。请点击“重新获取问题”继续；如果当前维度已完成，也可以直接跳到下一维度。'
            });
            this.aiRecommendationExpanded = false;
            this.aiRecommendationApplied = false;
            this.aiRecommendationPrevSelection = null;
            this.interactionReady = true;
            this.showToast(
                timeoutTriggered ? '获取下一题超时，已停止等待' : '未检测到新的问题输出，已停止等待',
                'warning'
            );
            this.refreshOpsMetricsIfVisible();
        },

        // ========== 方案B: 思考进度轮询 ==========
        startThinkingPolling(requestId = this.questionRequestId) {
            // 先停止旧的轮询，防止多个轮询并发
            this.stopThinkingPolling(false);
            const currentRequestId = Number(requestId) || 0;
            this.thinkingPollRequestId = currentRequestId;

            const pollInterval = 300;  // 300ms 轮询间隔

            this.thinkingPollInterval = setInterval(async () => {
                if (!this.loadingQuestion || currentRequestId !== this.questionRequestId || currentRequestId !== this.thinkingPollRequestId) {
                    this.stopThinkingPolling(false);
                    return;
                }
                try {
                    const sessionId = this.currentSession?.session_id;
                    if (!sessionId) return;

                    const response = await fetch(`${API_BASE}/status/thinking/${sessionId}`);
                    if (!this.loadingQuestion || currentRequestId !== this.questionRequestId || currentRequestId !== this.thinkingPollRequestId) {
                        return;
                    }
                    if (response.ok) {
                        const data = await response.json();
                        if (!this.loadingQuestion || currentRequestId !== this.questionRequestId || currentRequestId !== this.thinkingPollRequestId) {
                            return;
                        }
                        if (data.active) {
                            this.applyThinkingStage(data);
                            this.markQuestionRequestActive(currentRequestId);
                        } else if (this.questionRequestPreferPrefetch && (Date.now() - (Number(this.questionRequestStartedAt) || Date.now())) < QUESTION_SUBMIT_PREFETCH_WAIT_MS) {
                            this.applyThinkingStage({
                                stage_index: this.thinkingStage?.stage_index ?? 0,
                                stage_name: this.thinkingStage?.stage_name || '分析回答',
                                message: '正在等待上一题提交后的预取结果',
                                progress: Math.max(Number(this.thinkingStage?.progress ?? 0), 36)
                            });
                            this.markQuestionRequestActive(currentRequestId);
                        } else {
                            this.observeQuestionRequestIdle(currentRequestId);
                        }
                    }
                } catch (error) {
                    // 轮询失败时不显示错误，静默处理
                }
            }, pollInterval);
        },

        stopThinkingPolling(resetStage = true) {
            if (this.thinkingPollInterval) {
                clearInterval(this.thinkingPollInterval);
                this.thinkingPollInterval = null;
            }
            this.thinkingPollRequestId = 0;
            if (resetStage) {
                this.thinkingStage = null;
            }
        },

        // 访谈小技巧轮播
        startTipRotation() {
            const tips = typeof SITE_CONFIG !== 'undefined' ? SITE_CONFIG.researchTips : null;
            if (!tips || tips.length === 0) return;

            this.currentTipIndex = Math.floor(Math.random() * tips.length);
            this.currentTip = tips[this.currentTipIndex];
            this.stopTipRotation();
            this.tipRotationInterval = setInterval(() => {
                this.currentTipIndex = (this.currentTipIndex + 1) % tips.length;
                this.currentTip = tips[this.currentTipIndex];
            }, 5000);
        },

        stopTipRotation() {
            if (this.tipRotationInterval) {
                clearInterval(this.tipRotationInterval);
                this.tipRotationInterval = null;
            }
        },

        getThinkingStageDefaultProgress(stageIndex = 0) {
            const normalizedStageIndex = Math.max(0, Math.min(2, Number(stageIndex) || 0));
            const progressByStage = [18, 56, 82];
            return progressByStage[normalizedStageIndex] || 18;
        },

        buildThinkingStageState(stage = {}) {
            const normalizedStageIndex = Math.max(
                0,
                Math.min(2, Number(stage.stage_index ?? stage.stageIndex ?? 0) || 0)
            );
            const rawProgress = Number(stage.progress);
            const normalizedProgress = Number.isFinite(rawProgress)
                ? Math.max(0, Math.min(100, rawProgress))
                : this.getThinkingStageDefaultProgress(normalizedStageIndex);
            const fallbackStageName = ['分析回答', '检索资料', '生成问题'][normalizedStageIndex] || '分析回答';

            return {
                active: true,
                stage_index: normalizedStageIndex,
                stage_name: String(stage.stage_name || stage.stageName || stage.stage || fallbackStageName),
                message: String(stage.message || ''),
                progress: normalizedProgress
            };
        },

        applyThinkingStage(stage, options = {}) {
            if (!stage || stage.active === false) {
                return;
            }

            const preserveProgress = options.preserveProgress !== false;
            const normalizedStage = this.buildThinkingStageState(stage);
            const currentStageIndex = Number(this.thinkingStage?.stage_index ?? -1);
            const currentProgress = Number(this.thinkingStage?.progress ?? 0);

            if (preserveProgress && currentStageIndex > normalizedStage.stage_index) {
                normalizedStage.stage_index = currentStageIndex;
                normalizedStage.stage_name = this.thinkingStage?.stage_name || normalizedStage.stage_name;
                normalizedStage.message = this.thinkingStage?.message || normalizedStage.message;
                normalizedStage.progress = Math.max(currentProgress, normalizedStage.progress);
            } else if (preserveProgress && currentStageIndex === normalizedStage.stage_index) {
                normalizedStage.progress = Math.max(currentProgress, normalizedStage.progress);
            }

            this.thinkingStage = normalizedStage;
        },

        // ========== 方案D: 骨架填充 ==========
        async startSkeletonFill(result) {
            const questionText = result.question || '';
            const options = result.options || [];
            const aiRecommendation = this.normalizeAiRecommendation(result);

            // 验证必要数据
            if (!questionText || options.length === 0) {
                this.currentQuestion = this.createQuestionState({
                    serviceError: true,
                    errorTitle: '数据异常',
                    errorDetail: '问题或选项缺失，请重试'
                });
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                this.interactionReady = true;
                this.skeletonMode = false;
                return;
            }

            // 进入骨架填充模式
            this.skeletonMode = true;
            this.typingText = '';
            this.typingComplete = false;
            this.optionsVisible = [];
            this.interactionReady = false;

            // 设置当前问题数据（但先不显示）
            this.currentQuestion = this.createQuestionState({
                text: result.question,
                options: result.options || [],
                multiSelect: result.multi_select || false,
                questionMultiSelect: (result.question_multi_select ?? result.multi_select) || false,
                isFollowUp: result.is_follow_up || false,
                followUpReason: result.follow_up_reason,
                answerMode: result.answer_mode || 'pick_only',
                requiresRationale: !!result.requires_rationale,
                evidenceIntent: result.evidence_intent || 'low',
                questionGenerationTier: result.question_generation_tier || '',
                questionSelectedLane: result.question_selected_lane || '',
                questionRuntimeProfile: result.question_runtime_profile || '',
                questionHedgeTriggered: !!result.question_hedge_triggered,
                questionFallbackTriggered: !!result.question_fallback_triggered,
                preflightIntervened: !!(result.decision_meta && result.decision_meta.mid_interview_preflight && result.decision_meta.mid_interview_preflight.should_intervene),
                preflightFingerprint: (result.decision_meta && result.decision_meta.mid_interview_preflight && result.decision_meta.mid_interview_preflight.fingerprint) || '',
                preflightPlannerMode: (result.decision_meta && result.decision_meta.mid_interview_preflight && result.decision_meta.mid_interview_preflight.planner_mode) || '',
                preflightProbeSlots: Array.isArray(result.decision_meta && result.decision_meta.mid_interview_preflight && result.decision_meta.mid_interview_preflight.probe_slots)
                    ? result.decision_meta.mid_interview_preflight.probe_slots
                    : [],
                decisionMeta: result.decision_meta || null,
                conflictDetected: result.conflict_detected || false,
                conflictDescription: result.conflict_description,
                aiGenerated: result.ai_generated || false,
                aiRecommendation: aiRecommendation
            });
            this.aiRecommendationExpanded = false;
            this.aiRecommendationApplied = false;
            this.aiRecommendationPrevSelection = null;

            // 检查用户是否禁用了动效（可访问性支持）
            const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            const disableTypingEffect = (typeof SITE_CONFIG !== 'undefined'
                && SITE_CONFIG?.motion?.reducedMotion?.disableTypingEffect === true);

            if (prefersReducedMotion || disableTypingEffect) {
                // 禁用动效时：立即显示所有内容
                this.typingText = questionText;
                this.typingComplete = true;
                this.optionsVisible = options.map((_, i) => i);
                this.interactionReady = true;
                this.skeletonMode = false;
            } else {
                // 启用动效时：打字机效果 + 选项淡入
                const typingSpeed = QUESTION_TYPING_CHAR_DELAY_MS;
                for (let i = 0; i <= questionText.length; i++) {
                    this.typingText = questionText.substring(0, i);
                    await new Promise(resolve => setTimeout(resolve, typingSpeed));
                }
                this.typingComplete = true;

                // 选项依次淡入
                const optionDelay = QUESTION_OPTION_REVEAL_DELAY_MS;
                for (let i = 0; i < options.length; i++) {
                    this.optionsVisible.push(i);
                    await new Promise(resolve => setTimeout(resolve, optionDelay));
                }

                // 短暂延迟后允许交互
                await new Promise(resolve => setTimeout(resolve, QUESTION_INTERACTION_READY_DELAY_MS));
                this.interactionReady = true;
                this.skeletonMode = false;
            }
        },

        // ============ API 调用 ============
        async apiCall(endpoint, options = {}) {
            const {
                skipAuthRedirect = false,
                expectedStatuses = [],
                suppressErrorLog = false,
                ...fetchOptions
            } = options;
            try {
                const response = await fetch(`${API_BASE}${endpoint}`, {
                    headers: { 'Content-Type': 'application/json' },
                    ...fetchOptions
                });
                if (!response.ok) {
                    let errorMsg = `HTTP ${response.status}`;
                    let errorPayload = null;
                    try {
                        errorPayload = await response.json();
                        errorMsg = errorPayload.error || errorPayload.detail || errorMsg;
                        if (String(errorPayload?.error_code || '').trim() === 'level_capability_denied') {
                            errorMsg = this.getLevelCapabilityDeniedMessage(errorPayload);
                        }
                    } catch (parseError) {
                        // 响应非 JSON 格式，使用 HTTP 状态信息
                    }

                    if (response.status === 401 && !skipAuthRedirect) {
                        this.enterLoginState({
                            showToast: true,
                            toastMessage: '登录状态已失效，请重新登录',
                            toastType: 'warning'
                        });
                    }

                    if (
                        response.status === 403
                        && !skipAuthRedirect
                        && String(errorPayload?.error_code || '').startsWith('license_')
                    ) {
                        this.enterLicenseGateState(errorPayload, { message: errorMsg });
                    }

                    const error = new Error(errorMsg);
                    error.status = response.status;
                    error.isExpected = Array.isArray(expectedStatuses) && expectedStatuses.includes(response.status);
                    error.payload = errorPayload;
                    throw error;
                }
                return await response.json();
            } catch (error) {
                if (!error?.isExpected && !suppressErrorLog) {
                    console.error('API 调用失败:', error);
                }
                throw error;
            }
        },

        async createNewSession() {
            if (!this.newSessionTopic.trim() || this.loading) return;

            // 设置加载状态，防止并发
            this.loading = true;

            // 从配置获取限制
            const config = typeof SITE_CONFIG !== 'undefined' ? SITE_CONFIG.limits : null;
            const topicMaxLength = config?.topicMaxLength || 200;
            const descMaxLength = config?.descriptionMaxLength || 1000;

            // 验证主题长度
            if (this.newSessionTopic.length > topicMaxLength) {
                this.showToast(`访谈主题不能超过${topicMaxLength}个字符`, 'error');
                this.loading = false;
                return;
            }

            // 验证描述长度
            if (this.newSessionDescription.length > descMaxLength) {
                this.showToast(`访谈描述不能超过${descMaxLength}个字符`, 'error');
                this.loading = false;
                return;
            }

            try {
                const session = await this.apiCall('/sessions', {
                    method: 'POST',
                    body: JSON.stringify({
                        topic: this.newSessionTopic.trim(),
                        description: this.newSessionDescription.trim() || null,
                        interview_mode: this.selectedInterviewMode,
                        scenario_id: this.selectedScenario?.id || null
                    })
                });

                this.sessions.unshift(session);
                this.filterSessions();  // 刷新筛选列表
                this.currentSession = session;
                this.updateDimensionsFromSession(session);
                this.showNewSessionModal = false;
                this.newSessionTopic = '';
                this.newSessionDescription = '';
                this.selectedInterviewMode = this.interviewModeDefault || 'standard';
                this.selectedScenario = null;  // 重置场景选择
                this.showScenarioSelector = false;  // 重置场景选择器
                this.scenarioSearchQuery = '';  // 重置搜索关键词
                this.stopSessionsAutoRefresh();
                this.currentStep = 0;
                this.currentView = 'interview';
                this.showToast('会话创建成功', 'success');
            } catch (error) {
                const message = String(error?.message || '').trim();
                if (message.includes('请先登录')) {
                    this.showToast('登录状态已失效，请重新登录后再试', 'error');
                } else {
                    this.showToast(message || '创建会话失败', 'error');
                }
            } finally {
                this.loading = false;
            }
        },

        attemptCloseNewSessionModal() {
            if (this.showGuide) {
                const now = Date.now();
                if (now - this.guideCloseHintLastAt >= 2000) {
                    this.guideCloseHintLastAt = now;
                    this.showToast('操作指引进行中，请先完成步骤或点击“跳过”', 'info');
                }
                return;
            }
            this.showNewSessionModal = false;
        },

        findSessionSummaryById(sessionId) {
            const targetSessionId = this.normalizeComparableId(sessionId);
            return this.sessions.find(session => this.normalizeComparableId(session?.session_id) === targetSessionId) || null;
        },

        buildInterviewSessionPlaceholder(sessionId) {
            const sessionSummary = this.findSessionSummaryById(sessionId) || {};
            const dimensions = (sessionSummary?.dimensions && typeof sessionSummary.dimensions === 'object')
                ? JSON.parse(JSON.stringify(sessionSummary.dimensions))
                : {};
            const documents = Array.isArray(sessionSummary?.documents) ? [...sessionSummary.documents] : [];
            const interviewLog = Array.isArray(sessionSummary?.interview_log) ? [...sessionSummary.interview_log] : [];
            return {
                ...sessionSummary,
                session_id: sessionSummary?.session_id || sessionId,
                topic: sessionSummary?.topic || '访谈会话',
                description: sessionSummary?.description || '',
                dimensions,
                documents,
                interview_log: interviewLog,
                scenario_config: sessionSummary?.scenario_config || null,
            };
        },

        enterInterviewLoadingState(message = '正在读取会话与定位下一题') {
            this.currentStep = 1;
            this.loadingQuestion = true;
            this.skeletonMode = false;
            this.interactionReady = false;
            this.currentQuestion = this.createQuestionState();
            this.aiRecommendationExpanded = false;
            this.aiRecommendationApplied = false;
            this.aiRecommendationPrevSelection = null;
            this.applyThinkingStage({
                stage_index: 0,
                stage_name: '分析回答',
                message,
                progress: 20
            }, { preserveProgress: false });
            this.startTipRotation();
        },

        clearInterviewLoadingState() {
            this.loadingQuestion = false;
            this.skeletonMode = false;
            this.thinkingStage = null;
            this.stopTipRotation();
        },

        async openSession(sessionId) {
            const openRequestId = this.sessionOpenRequestId + 1;
            this.sessionOpenRequestId = openRequestId;
            const sessionPlaceholder = this.buildInterviewSessionPlaceholder(sessionId);
            const hasStartedInterview = Number(sessionPlaceholder?.interview_count || 0) > 0
                || (Array.isArray(sessionPlaceholder?.interview_log) && sessionPlaceholder.interview_log.length > 0);
            try {
                this.currentSession = sessionPlaceholder;
                this.resetReportGenerationFeedback();
                this.updateDimensionsFromSession(this.currentSession);
                this.stopSessionsAutoRefresh();
                this.currentView = 'interview';
                this.selectedAnswers = [];
                this.rationaleText = '';
                this.otherAnswerText = '';
                this.otherSelected = false;
                this.resetSingleSelectDisambiguation();
                const predictedNextDim = this.getNextIncompleteDimension();
                this.currentDimension = predictedNextDim || this.dimensionOrder[0] || 'customer_needs';
                if (hasStartedInterview && predictedNextDim) {
                    this.enterInterviewLoadingState('正在读取会话与定位下一题');
                } else if (!predictedNextDim && hasStartedInterview) {
                    this.clearInterviewLoadingState();
                    this.currentStep = 2;
                    this.currentQuestion = this.createQuestionState();
                    this.aiRecommendationExpanded = false;
                    this.aiRecommendationApplied = false;
                    this.aiRecommendationPrevSelection = null;
                } else {
                    this.clearInterviewLoadingState();
                    this.currentStep = 0;
                }
                this.scheduleAppShellSnapshotPersist();

                this.currentSession = await this.apiCall(`/sessions/${sessionId}`);
                if (openRequestId !== this.sessionOpenRequestId) {
                    return;
                }
                this.resetReportGenerationFeedback();
                this.updateDimensionsFromSession(this.currentSession);
                this.stopSessionsAutoRefresh();
                this.currentView = 'interview';

                // 检查所有维度是否已完成
                const nextDim = this.getNextIncompleteDimension();
                if (!nextDim && this.currentSession.interview_log.length > 0) {
                    // 所有维度已完成，直接进入确认阶段
                    this.clearInterviewLoadingState();
                    this.currentStep = 2;
                    this.currentDimension = this.dimensionOrder[this.dimensionOrder.length - 1];
                    this.currentQuestion = this.createQuestionState();
                    this.aiRecommendationExpanded = false;
                    this.aiRecommendationApplied = false;
                    this.aiRecommendationPrevSelection = null;
                } else if (this.currentSession.interview_log.length > 0) {
                    // 有未完成的维度，继续访谈流程
                    this.currentStep = 1;
                    this.currentDimension = nextDim;
                    await this.fetchNextQuestion({ force: true });
                } else {
                    // 还没开始访谈
                    this.clearInterviewLoadingState();
                    this.currentStep = 0;
                    this.currentDimension = this.dimensionOrder[0] || 'customer_needs';
                }

                void this.restoreReportGenerationState(this.currentSession?.session_id || '');
                this.scheduleAppShellSnapshotPersist();
            } catch (error) {
                if (openRequestId !== this.sessionOpenRequestId) {
                    return;
                }
                this.clearInterviewLoadingState();
                this.currentView = 'sessions';
                this.currentSession = null;
                this.refreshSessionsView();
                this.showToast('加载会话失败', 'error');
            }
        },

        async continueSession(sessionId) {
            await this.openSession(sessionId);
        },

        confirmDeleteSession(sessionId) {
            this.sessionToDelete = sessionId;
            this.showDeleteModal = true;
        },

        async deleteSession() {
            if (!this.sessionToDelete) return;

            try {
                await this.apiCall(`/sessions/${this.sessionToDelete}`, { method: 'DELETE' });
                this.sessions = this.sessions.filter(s => s.session_id !== this.sessionToDelete);
                this.filterSessions();  // 刷新筛选列表
                this.showDeleteModal = false;
                this.sessionToDelete = null;
                this.showToast('会话已删除', 'success');
            } catch (error) {
                this.showToast('删除会话失败', 'error');
            }
        },

        openBatchDeleteModal(target) {
            this.batchDeleteTarget = target;
            this.batchDeleteAlsoReports = false;

            if (target === 'sessions') {
                this.batchDeleteSummary = {
                    items: this.selectedSessionIds.length,
                    sessions: this.selectedSessionIds.length,
                    reports: this.estimateLinkedReportCount(this.selectedSessionIds)
                };
            } else {
                this.batchDeleteSummary = {
                    items: this.selectedReportNames.length,
                    sessions: 0,
                    reports: this.selectedReportNames.length
                };
            }
            this.showBatchDeleteModal = true;
        },

        updateSessionBatchSummary() {
            if (this.batchDeleteTarget !== 'sessions') return;
            this.batchDeleteSummary = {
                items: this.selectedSessionIds.length,
                sessions: this.selectedSessionIds.length,
                reports: this.batchDeleteAlsoReports
                    ? this.estimateLinkedReportCount(this.selectedSessionIds)
                    : 0
            };
        },

        buildSessionTopicSlug(topic) {
            if (!topic || typeof topic !== 'string') return '';
            return topic.trim().replace(/\s+/g, '-').slice(0, 30);
        },

        parseValidTimestamp(dateStr) {
            const timestamp = new Date(dateStr || '').getTime();
            return Number.isFinite(timestamp) ? timestamp : 0;
        },

        normalizeComparableId(value) {
            return String(value ?? '').trim();
        },

        async openGeneratedReportForSession(sessionId = '', preferredReportName = '', options = {}) {
            const normalizedSessionId = this.normalizeComparableId(sessionId);
            const preferredName = String(preferredReportName || '').trim();
            const { forceReload = false, showMissingToast = true } = options;

            if (!normalizedSessionId && !preferredName) return false;

            const hasPreferredInList = preferredName
                && Array.isArray(this.reports)
                && this.reports.some(report => report?.name === preferredName);
            if (!this.findReportBySessionId(normalizedSessionId) && !hasPreferredInList) {
                await this.loadReports();
            }

            const matchedReport = this.findReportBySessionId(normalizedSessionId);
            const targetReportName = String(
                preferredName
                || matchedReport?.name
                || ''
            ).trim();

            if (!targetReportName) {
                if (showMissingToast) {
                    this.showToast('报告已生成，但暂未在列表中找到，请稍后到报告页查看', 'warning');
                }
                return false;
            }

            this.currentView = 'reports';
            await this.viewReport(targetReportName, { forceReload });
            return true;
        },

        estimateLinkedReportCount(sessionIds) {
            if (!Array.isArray(sessionIds) || sessionIds.length === 0) return 0;
            const reportNames = new Set();
            const reports = Array.isArray(this.reports) ? this.reports : [];

            sessionIds.forEach(sessionId => {
                const session = this.sessions.find(item => item.session_id === sessionId);
                const slug = this.buildSessionTopicSlug(session?.topic || '');
                if (!slug) return;

                const suffix = `-${slug}.md`;
                reports.forEach(report => {
                    if (report?.name && report.name.endsWith(suffix)) {
                        reportNames.add(report.name);
                    }
                });
            });
            return reportNames.size;
        },

        closeBatchDeleteModal() {
            this.showBatchDeleteModal = false;
            this.batchDeleteLoading = false;
            this.batchDeleteAlsoReports = false;
        },

        async confirmBatchDelete() {
            if (this.batchDeleteLoading) return;

            if (this.batchDeleteTarget === 'sessions' && this.selectedSessionIds.length === 0) return;
            if (this.batchDeleteTarget === 'reports' && this.selectedReportNames.length === 0) return;

            this.batchDeleteLoading = true;
            try {
                if (this.batchDeleteTarget === 'sessions') {
                    const result = await this.apiCall('/sessions/batch-delete', {
                        method: 'POST',
                        body: JSON.stringify({
                            session_ids: this.selectedSessionIds,
                            delete_reports: this.batchDeleteAlsoReports,
                            skip_in_progress: false
                        })
                    });

                    const deletedSessions = result.deleted_sessions?.length || 0;
                    const deletedReports = result.deleted_reports?.length || 0;
                    const skippedSessions = result.skipped_sessions?.length || 0;
                    const missingSessions = result.missing_sessions?.length || 0;

                    await this.refreshSessionsView();
                    if (this.batchDeleteAlsoReports || deletedReports > 0) {
                        await this.loadReports();
                    }

                    this.closeBatchDeleteModal();
                    this.exitSessionBatchMode();

                    if (deletedSessions > 0) {
                        let message = `已删除 ${deletedSessions} 个会话`;
                        if (deletedReports > 0) {
                            message += `，并移除 ${deletedReports} 个关联报告`;
                        }
                        if (skippedSessions > 0 || missingSessions > 0) {
                            message += `（跳过 ${skippedSessions + missingSessions} 个）`;
                        }
                        this.showToast(message, 'success');
                    } else {
                        this.showToast('没有可删除的会话', 'warning');
                    }
                    return;
                }

                const result = await this.apiCall('/reports/batch-delete', {
                    method: 'POST',
                    body: JSON.stringify({
                        report_names: this.selectedReportNames
                    })
                });

                const deletedReports = result.deleted_reports?.length || 0;
                const skippedReports = result.skipped_reports?.length || 0;
                const missingReports = result.missing_reports?.length || 0;

                const selectedReportName = this.selectedReport || this.selectedReportMeta?.name || '';
                [
                    ...(Array.isArray(result.deleted_reports) ? result.deleted_reports : []),
                    ...(Array.isArray(result.missing_reports) ? result.missing_reports : [])
                ].forEach(name => this.invalidateReportDetailCache(name));
                await this.loadReports();
                if (selectedReportName && !this.reports.find(report => report.name === selectedReportName)) {
                    this.resetSelectedReportDetail();
                }

                this.closeBatchDeleteModal();
                this.exitReportBatchMode();

                if (deletedReports > 0) {
                    let message = `已删除 ${deletedReports} 个报告`;
                    if (skippedReports > 0 || missingReports > 0) {
                        message += `（跳过 ${skippedReports + missingReports} 个）`;
                    }
                    this.showToast(message, 'success');
                } else {
                    this.showToast('没有可删除的报告', 'warning');
                }
            } catch (error) {
                this.showToast('批量删除失败', 'error');
            } finally {
                this.batchDeleteLoading = false;
            }
        },

        // ============ 文档上传 ============
        async uploadDocument(event) {
            // 支持拖放上传和点击上传
            const files = event.dataTransfer?.files || event.target?.files;
            if (!files?.length || !this.currentSession) return;

            // 从配置获取限制
            const config = typeof SITE_CONFIG !== 'undefined' ? SITE_CONFIG.limits : null;
            const minFileSize = config?.minFileSize || 1;
            const maxFileSize = config?.maxFileSize || (10 * 1024 * 1024);
            const supportedTypes = config?.supportedFileTypes || {
                '.md': ['text/markdown', 'text/x-markdown', 'text/plain'],
                '.txt': ['text/plain'],
                '.pdf': ['application/pdf'],
                '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
                '.xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
                '.pptx': ['application/vnd.openxmlformats-officedocument.presentationml.presentation'],
                '.png': ['image/png'],
                '.jpg': ['image/jpeg'],
                '.jpeg': ['image/jpeg'],
                '.gif': ['image/gif'],
                '.webp': ['image/webp']
            };

            const sessionId = this.currentSession.session_id;
            let successCount = 0;
            this.documentUploading = true;
            try {
                for (const file of Array.from(files)) {
                // 验证文件大小 - 最小值
                if (file.size < minFileSize) {
                    this.showToast(`文件 ${file.name} 是空文件，请选择有效文件`, 'error');
                    continue;
                }

                // 验证文件大小 - 最大值
                if (file.size > maxFileSize) {
                    const sizeMB = (maxFileSize / (1024 * 1024)).toFixed(0);
                    this.showToast(`文件 ${file.name} 超过${sizeMB}MB限制`, 'error');
                    continue;
                }

                // 验证文件扩展名
                const ext = '.' + file.name.split('.').pop().toLowerCase();
                if (!supportedTypes[ext]) {
                    this.showToast(`不支持的文件类型: ${ext}`, 'error');
                    continue;
                }

                // 验证MIME类型（增强安全性）
                const allowedMimeTypes = supportedTypes[ext];
                if (allowedMimeTypes && !allowedMimeTypes.includes(file.type)) {
                    console.warn(`文件 ${file.name} 的MIME类型 ${file.type} 与扩展名 ${ext} 不匹配，但允许继续`);
                    // 警告但不阻止，因为某些系统的MIME类型识别可能不准确
                }

                const formData = new FormData();
                formData.append('file', file);

                try {
                    const response = await fetch(
                        `${API_BASE}/sessions/${sessionId}/documents`,
                        { method: 'POST', body: formData }
                    );

                    if (response.ok) {
                        await response.json();
                        successCount += 1;
                    } else {
                        // 尝试获取详细错误信息
                        let errorMsg = '上传失败';
                        try {
                            const errData = await response.json();
                            errorMsg = errData.error || errorMsg;
                        } catch (e) {}
                        throw new Error(errorMsg);
                    }
                } catch (error) {
                    this.showToast(`上传 ${file.name} 失败: ${error.message}`, 'error');
                }
                }

                // 清除 input 值（仅点击上传时）
                if (event.target?.value !== undefined) {
                    event.target.value = '';
                }
                if (successCount > 0 && this.currentSession?.session_id === sessionId) {
                    this.currentSession = await this.apiCall(`/sessions/${sessionId}`);
                    this.showToast(successCount === 1 ? '文档上传成功' : `已完成 ${successCount} 个文档上传`, 'success');
                }
            } finally {
                this.documentUploading = false;
            }
        },

        async removeDocument(index) {
            if (!this.currentSession || !this.currentSession.reference_materials) {
                return;
            }

            const doc = this.currentSession.reference_materials[index];

            // 使用自定义确认对话框
            this.docToDelete = doc;
            this.docDeleteCallback = async () => {
                try {
                    const query = doc?.doc_id ? `?doc_id=${encodeURIComponent(doc.doc_id)}` : '';
                    const response = await fetch(
                        `${API_BASE}/sessions/${this.currentSession.session_id}/documents/${encodeURIComponent(doc.name)}${query}`,
                        { method: 'DELETE' }
                    );

                    if (response.ok) {
                        // 刷新会话数据
                        this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);
                        this.showToast(`文档 ${doc.name} 已删除`, 'success');
                    } else {
                        throw new Error('删除失败');
                    }
                } catch (error) {
                    console.error('删除文档错误:', error);
                    this.showToast(`删除文档失败`, 'error');
                }
            };
            this.showDeleteDocModal = true;
        },

        getDocumentKey(doc, index = 0) {
            if (!doc || typeof doc !== 'object') return `doc-${index}`;
            return doc.doc_id || `${doc.uploaded_at || 'unknown'}-${doc.name || 'doc'}-${doc.source || 'upload'}-${index}`;
        },


        async confirmDeleteDoc() {
            if (this.docDeleteCallback) {
                await this.docDeleteCallback();
            }
            this.showDeleteDocModal = false;
            this.docToDelete = null;
            this.docDeleteCallback = null;
        },

        cancelDeleteDoc() {
            this.showDeleteDocModal = false;
            this.docToDelete = null;
            this.docDeleteCallback = null;
        },

        // ============ AI 驱动的访谈流程 ============
        startInterview() {
            // 检查是否所有维度都已完成
            const nextDim = this.getNextIncompleteDimension();
            if (!nextDim) {
                // 所有维度都已完成，直接进入确认阶段
                this.currentStep = 2;
                this.currentQuestion = this.createQuestionState();
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                return;
            }

            this.currentStep = 1;
            this.currentDimension = nextDim;  // 从第一个未完成的维度开始
            this.fetchNextQuestion();
        },

        getNextIncompleteDimension() {
            if (!this.currentSession || !this.currentSession.dimensions) {
                return this.dimensionOrder[0];
            }
            for (const dim of this.dimensionOrder) {
                const dimension = this.currentSession.dimensions[dim];
                if (dimension && dimension.coverage < 100) {
                    return dim;
                }
            }
            // 所有维度都已完成，返回 null
            return null;
        },

        ensureDimensionVisualComplete(dimensionKey) {
            if (!dimensionKey || !this.currentSession?.dimensions?.[dimensionKey]) {
                return;
            }
            const dimState = this.currentSession.dimensions[dimensionKey];
            const coverage = Number(dimState.coverage) || 0;
            if (coverage < 100) {
                dimState.coverage = 100;
            }
        },

        async fetchNextQuestion(options = {}) {
            if (this.loadingQuestion && !options?.force) return;
            const requestId = ++this.questionRequestId;
            let activeRequestAbortController = null;
            const preferPrefetch = !!options?.preferPrefetch;
            this.recordQuestionOpsRequestStart({
                dimension: this.currentDimension,
                preferPrefetch
            });
            this.loadingQuestion = true;
            this.skeletonMode = false;
            this.interactionReady = false;
            this.startTipRotation();
            // 重置问题状态，清除上一次可能的错误
            this.currentQuestion = this.createQuestionState();
            this.aiRecommendationExpanded = false;
            this.aiRecommendationApplied = false;
            this.aiRecommendationPrevSelection = null;
            if (preferPrefetch) {
                this.applyThinkingStage({
                    stage_index: this.thinkingStage?.stage_index ?? 0,
                    stage_name: this.thinkingStage?.stage_name || '分析回答',
                    message: '正在等待上一题提交后的预取结果',
                    progress: Math.max(Number(this.thinkingStage?.progress ?? 0), 36)
                });
            }
            this.startQuestionRequestGuard(requestId);
            this.questionRequestPreferPrefetch = preferPrefetch;
            this.startThinkingPolling(requestId);  // 方案B: 开始轮询思考进度
            this.startWebSearchPolling(requestId);  // 同时保留 Web Search 状态轮询
            this.selectedAnswers = [];
            this.rationaleText = '';
            this.otherAnswerText = '';
            this.otherSelected = false;
            this.resetSingleSelectDisambiguation();

            try {
                let overloadWaitMs = 0;
                let overloadRetryCount = 0;

                while (requestId === this.questionRequestId) {
                    const requestAbortController = typeof AbortController === 'function' ? new AbortController() : null;
                    activeRequestAbortController = requestAbortController;
                    this.questionRequestAbortController = requestAbortController;
                    this.startQuestionRequestGuard(requestId);
                    this.questionRequestPreferPrefetch = preferPrefetch;
                    this.startThinkingPolling(requestId);
                    this.startWebSearchPolling(requestId);

                    const response = await fetch(`${API_BASE}/sessions/${this.currentSession.session_id}/next-question`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            dimension: this.currentDimension,
                            prefer_prefetch: preferPrefetch
                        }),
                        signal: requestAbortController?.signal
                    });

                    let result = {};
                    try {
                        result = await response.json();
                    } catch (_error) {
                        result = {};
                    }

                    if (requestId !== this.questionRequestId) {
                        return;
                    }

                    if (this.questionRequestAbortController === requestAbortController) {
                        this.questionRequestAbortController = null;
                    }
                    this.stopQuestionRequestGuard();
                    this.stopThinkingPolling(false);
                    this.stopWebSearchPolling();

                    if (response.status === 429 && result?.code === 'overloaded') {
                        overloadRetryCount += 1;
                        const retryAfterSeconds = this.parseQuestionRetryAfterSeconds(response);
                        overloadWaitMs += retryAfterSeconds * 1000;
                        this.recordQuestionOpsOverloadRetry({
                            retryCount: overloadRetryCount,
                            waitMs: overloadWaitMs
                        });

                        if (overloadRetryCount === 1) {
                            this.showToast('问题生成链路繁忙，正在自动重试', 'warning');
                        }

                        if (overloadWaitMs > QUESTION_OVERLOAD_RETRY_MAX_WAIT_MS) {
                            this.recordQuestionOpsOutcome('overloaded', {
                                overloadRetryCount,
                                overloadWaitMs,
                                error: '问题生成繁忙'
                            });
                            this.loadingQuestion = false;
                            this.thinkingStage = null;
                            this.stopTipRotation();
                            this.currentQuestion = this.createQuestionState({
                                serviceError: true,
                                errorTitle: '问题生成繁忙',
                                errorDetail: `当前请求较多，已自动等待 ${Math.ceil(overloadWaitMs / 1000)} 秒仍未轮到本次生成。请点击“重试”继续。`
                            });
                            this.aiRecommendationExpanded = false;
                            this.aiRecommendationApplied = false;
                            this.aiRecommendationPrevSelection = null;
                            this.interactionReady = true;
                            return;
                        }

                        this.applyThinkingStage({
                            stage_index: 2,
                            stage_name: '生成问题',
                            message: `问题生成链路繁忙，正在排队，${retryAfterSeconds}秒后自动重试`,
                            progress: 92
                        }, { preserveProgress: false });

                        const shouldContinue = await this.waitForQuestionOverloadRetry(requestId, retryAfterSeconds * 1000);
                        if (!shouldContinue) {
                            return;
                        }
                        continue;
                    }

                    // 检查是否有错误
                    if (!response.ok || result.error) {
                        this.loadingQuestion = false;
                        this.thinkingStage = null;
                        this.stopTipRotation();
                        const errorTitle = result.error || '服务错误';
                        const errorDetail = result.detail || '请稍后重试';
                        this.recordQuestionOpsOutcome('error', {
                            overloadRetryCount,
                            overloadWaitMs,
                            error: errorTitle
                        });

                        this.showToast(errorTitle, 'error');
                        this.currentQuestion = this.createQuestionState({
                            serviceError: true,
                            errorTitle: errorTitle,
                            errorDetail: errorDetail
                        });
                        this.aiRecommendationExpanded = false;
                        this.aiRecommendationApplied = false;
                        this.aiRecommendationPrevSelection = null;
                        this.interactionReady = true;
                        return;
                    }

                    const hasUsableQuestion = Boolean(
                        typeof result.question === 'string'
                        && result.question.trim()
                        && Array.isArray(result.options)
                        && result.options.filter(option => String(option || '').trim()).length >= 2
                    );

                    if (!result.completed && !hasUsableQuestion) {
                        this.loadingQuestion = false;
                        this.thinkingStage = null;
                        this.stopTipRotation();
                        this.recordQuestionOpsOutcome('error', {
                            overloadRetryCount,
                            overloadWaitMs,
                            error: '问题数据异常'
                        });
                        this.currentQuestion = this.createQuestionState({
                            serviceError: true,
                            errorTitle: '问题数据异常',
                            errorDetail: '问题生成结果缺少有效问题或选项，请点击“重试”继续。'
                        });
                        this.aiRecommendationExpanded = false;
                        this.aiRecommendationApplied = false;
                        this.aiRecommendationPrevSelection = null;
                        this.interactionReady = true;
                        return;
                    }

                    this.applyThinkingStage({
                        stage_index: 2,
                        stage_name: '生成问题',
                        message: result.completed ? '当前维度已完成' : '问题生成完成',
                        progress: 100
                    }, { preserveProgress: false });

                    // 等待 600ms 让用户看到完成动画，然后再切换到新问题
                    await new Promise(resolve => setTimeout(resolve, QUESTION_SUCCESS_TRANSITION_DELAY_MS));

                    // 关闭加载状态
                    this.loadingQuestion = false;
                    this.thinkingStage = null;
                    this.stopTipRotation();

                    if (result.completed) {
                        this.recordQuestionOpsOutcome('completed', {
                            decisionMeta: result.decision_meta || null,
                            overloadRetryCount,
                            overloadWaitMs
                        });
                        // 当前维度已完成：自动推进流程，不再展示里程碑弹窗
                        const completedDimension = this.currentDimension;
                        const completedDimName = this.getDimensionName(completedDimension);

                        if (result.quality_warning) {
                            this.showToast('该维度已达上限保护完成，建议后续补充细节以提升结论可信度', 'warning');
                        }

                        this.ensureDimensionVisualComplete(completedDimension);

                        const currentIdx = this.dimensionOrder.indexOf(this.currentDimension);
                        let nextDim = null;
                        for (let i = 1; i <= this.dimensionOrder.length; i++) {
                            const dim = this.dimensionOrder[(currentIdx + i) % this.dimensionOrder.length];
                            const dimension = this.currentSession?.dimensions?.[dim];
                            if (dimension && dimension.coverage < 100) {
                                nextDim = dim;
                                break;
                            }
                        }

                        if (nextDim) {
                            this.currentDimension = nextDim;
                            this.showToast(`${completedDimName}收集完成，已自动进入${this.getDimensionName(nextDim)}`, 'success');
                            await this.fetchNextQuestion();
                        } else {
                            this.currentStep = 1;
                            this.currentQuestion = this.createQuestionState();
                            this.aiRecommendationExpanded = false;
                            this.aiRecommendationApplied = false;
                            this.aiRecommendationPrevSelection = null;
                            this.showToast('所有维度访谈完成！', 'success');
                        }
                        return;
                    }

                    const decisionMeta = result.decision_meta || null;
                    const fallbackTriggered = !!result.question_fallback_triggered || (!result.ai_generated && !!result.question);
                    this.recordQuestionOpsOutcome(fallbackTriggered ? 'fallback' : 'success', {
                        tier: result.question_generation_tier || '',
                        lane: result.question_selected_lane || '',
                        profile: result.question_runtime_profile || '',
                        decisionMeta,
                        hedgeTriggered: !!result.question_hedge_triggered,
                        fallbackTriggered,
                        overloadRetryCount,
                        overloadWaitMs,
                        error: ''
                    });
                    await this.startSkeletonFill(result);
                    return;
                }
            } catch (error) {
                if (requestId !== this.questionRequestId) {
                    return;
                }
                if (error?.name === 'AbortError') {
                    this.recordQuestionOpsOutcome('interrupted', {
                        error: '请求已取消'
                    });
                    return;
                }
                console.error('获取问题失败:', error);
                console.error('错误详情:', error.message, error.stack);

                // 网络错误或其他异常
                const errorTitle = '网络错误';
                const errorDetail = `无法连接到服务器: ${error.message}`;
                this.recordQuestionOpsOutcome('error', {
                    error: errorTitle,
                    overloadRetryCount,
                    overloadWaitMs
                });

                this.showToast(`${errorTitle}: ${error.message}`, 'error');
                this.currentQuestion = this.createQuestionState({
                    serviceError: true,
                    errorTitle: errorTitle,
                    errorDetail: errorDetail
                });
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                this.interactionReady = true;  // 错误状态下允许交互（重试）
            } finally {
                if (this.questionRequestAbortController === activeRequestAbortController) {
                    this.questionRequestAbortController = null;
                }
                if (requestId === this.questionRequestId) {
                    this.questionRequestPreferPrefetch = false;
                    // 确保停止轮询
                    this.stopQuestionRequestGuard();
                    this.stopThinkingPolling();
                    this.stopWebSearchPolling();
                    this.loadingQuestion = false;
                    this.isGoingPrev = false;
                }
                this.refreshOpsMetricsIfVisible();
            }
        },

        canSubmitAnswer() {
            // 防止并发提交
            if (this.submitting) {
                return false;
            }

            // 方案D: 骨架填充期间不允许提交
            if (!this.interactionReady) {
                return false;
            }

            if (!this.currentQuestion.text || this.currentQuestion.options.length === 0) {
                return false;
            }

            if (this.currentQuestion.multiSelect) {
                // 多选模式：至少选择一个选项，或者填写了"其他"
                const hasSelectedOptions = this.selectedAnswers.length > 0;
                const hasValidOther = this.otherSelected && this.otherAnswerText.trim().length > 0;
                return hasSelectedOptions || hasValidOther;
            } else {
                // 单选模式：必须选择一个选项，如果选择了"其他"需要填写内容
                if (this.otherSelected) {
                    return this.otherAnswerText.trim().length > 0;
                }
                return this.selectedAnswers.length > 0;
            }
        },

        normalizeAiRecommendation(result) {
            if (this.isAssessmentSession()) return null;

            const rec = result?.ai_recommendation;
            if (!rec || typeof rec !== 'object') return null;

            let recommendedOptions = [];
            if (Array.isArray(rec.recommended_options)) {
                recommendedOptions = rec.recommended_options.filter(Boolean);
            } else if (typeof rec.recommended_option === 'string') {
                recommendedOptions = [rec.recommended_option];
            }

            const summary = rec.summary || '';
            const reasons = Array.isArray(rec.reasons) ? rec.reasons.filter(r => r && r.text) : [];
            const confidence = rec.confidence || '';

            if (recommendedOptions.length === 0 && !summary && reasons.length === 0) {
                return null;
            }

            return { recommendedOptions, summary, reasons, confidence };
        },

        serializeAiRecommendation(recommendation) {
            if (this.isAssessmentSession()) return null;
            if (!recommendation || typeof recommendation !== 'object') return null;

            const recommendedOptions = Array.isArray(recommendation.recommendedOptions)
                ? recommendation.recommendedOptions.map(item => String(item || '').trim()).filter(Boolean)
                : [];
            const summary = String(recommendation.summary || '').trim();
            const confidence = String(recommendation.confidence || '').trim().toLowerCase();
            const reasons = Array.isArray(recommendation.reasons)
                ? recommendation.reasons
                    .filter(item => item && typeof item === 'object' && String(item.text || '').trim())
                    .map(item => ({
                        text: String(item.text || '').trim(),
                        evidence: Array.isArray(item.evidence)
                            ? item.evidence.map(value => String(value || '').trim()).filter(Boolean)
                            : []
                    }))
                : [];

            if (recommendedOptions.length === 0 && !summary && reasons.length === 0) {
                return null;
            }

            const payload = {
                recommended_options: recommendedOptions,
                summary,
                reasons,
            };
            if (confidence) {
                payload.confidence = confidence;
            }
            return payload;
        },

        clearAiRecommendationApplied() {
            if (!this.aiRecommendationApplied) return;
            this.aiRecommendationApplied = false;
            this.aiRecommendationPrevSelection = null;
        },

        formatAiConfidence(confidence) {
            if (confidence === 'high') return '高';
            if (confidence === 'medium') return '中';
            if (confidence === 'low') return '低';
            return '';
        },

        createQuestionState(overrides = {}) {
            return {
                text: '',
                options: [],
                multiSelect: false,
                questionMultiSelect: false,
                isFollowUp: false,
                followUpReason: null,
                answerMode: 'pick_only',
                requiresRationale: false,
                evidenceIntent: 'low',
                questionGenerationTier: '',
                questionSelectedLane: '',
                questionRuntimeProfile: '',
                questionHedgeTriggered: false,
                questionFallbackTriggered: false,
                preflightIntervened: false,
                preflightFingerprint: '',
                preflightPlannerMode: '',
                preflightProbeSlots: [],
                decisionMeta: null,
                conflictDetected: false,
                conflictDescription: null,
                aiGenerated: false,
                serviceError: false,
                errorTitle: '',
                errorDetail: '',
                aiRecommendation: null,
                ...overrides,
            };
        },

        escapeRegExp(text) {
            return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        },

        getOtherInputSelectAllPhrases() {
            return [
                '以上都可以',
                '以上都要',
                '以上都选',
                '以上都行',
                '以上所有',
                '以上全部',
                '所有都要',
                '全部都要',
                '全都要',
                '全都选',
                '都可以',
                '都要',
                '都选',
                '都行',
                '全选',
                '所有',
                '全部',
            ];
        },

        getOtherInputSelectAllRegex(flags = '') {
            const pattern = this.getOtherInputSelectAllPhrases()
                .map(item => this.escapeRegExp(item))
                .join('|');
            return new RegExp(pattern, flags);
        },

        normalizeOptionText(text) {
            return (text || '')
                .replace(/^[A-Ha-h][\.\)、:：]\s*/, '')
                .replace(/^[（(][A-Ha-h][）)]\s*/, '')
                .replace(/^\d{1,2}[\.\)、:：]\s*/, '')
                .replace(/^[（(]\d{1,2}[）)]\s*/, '')
                .replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, '')
                .toLowerCase()
                .replace(/\s+/g, '')
                .replace(/[（）()，,。．.]/g, '');
        },

        parseChineseNumberToken(token) {
            const normalized = String(token || '')
                .trim()
                .replace(/[两]/g, '二');
            if (!normalized) return null;

            if (/^\d+$/.test(normalized)) {
                return parseInt(normalized, 10);
            }

            const digitMap = {
                一: 1,
                二: 2,
                三: 3,
                四: 4,
                五: 5,
                六: 6,
                七: 7,
                八: 8,
                九: 9
            };

            if (normalized === '十') return 10;
            if (digitMap[normalized]) return digitMap[normalized];

            const tenPrefix = normalized.match(/^十([一二三四五六七八九])$/);
            if (tenPrefix) {
                return 10 + digitMap[tenPrefix[1]];
            }

            const tenComposite = normalized.match(/^([一二三四五六七八九])十([一二三四五六七八九])?$/);
            if (tenComposite) {
                const tens = digitMap[tenComposite[1]] * 10;
                const ones = tenComposite[2] ? digitMap[tenComposite[2]] : 0;
                return tens + ones;
            }

            return null;
        },

        resolveOtherInputReferences(inputText, options) {
            const text = (inputText || '').trim();
            const optionList = Array.isArray(options) ? options : [];
            if (!text || optionList.length === 0) {
                return {
                    matchedOptions: [],
                    customText: '',
                    pureReference: false,
                    intent: 'custom'
                };
            }

            const matchedIndexes = new Set();
            const compactText = text.replace(/\s+/g, '');
            const hasSelectAllHint = this.getOtherInputSelectAllRegex().test(compactText)
                && !/(不是|不要|不选|排除|除了)/.test(compactText);

            const ordinalPattern = /第\s*([0-9一二三四五六七八九十两]+)\s*[个项条点]?/g;
            let ordinalMatch;
            while ((ordinalMatch = ordinalPattern.exec(text)) !== null) {
                const parsed = this.parseChineseNumberToken(ordinalMatch[1]);
                if (Number.isInteger(parsed) && parsed >= 1 && parsed <= optionList.length) {
                    matchedIndexes.add(parsed - 1);
                }
            }

            const colloquialOrdinalPattern = /([一二三四五六七八九十两0-9]+)个/g;
            let colloquialMatch;
            while ((colloquialMatch = colloquialOrdinalPattern.exec(text)) !== null) {
                const parsed = this.parseChineseNumberToken(colloquialMatch[1]);
                if (Number.isInteger(parsed) && parsed >= 1 && parsed <= optionList.length) {
                    matchedIndexes.add(parsed - 1);
                }
            }

            const tokenized = text
                .replace(/[，,、；;／/]/g, ' ')
                .replace(/[（）()【】\[\]]/g, ' ')
                .replace(/\s+/g, ' ')
                .trim()
                .split(' ')
                .filter(Boolean);

            tokenized.forEach(token => {
                const cleaned = token.replace(/^[^\u4e00-\u9fa50-9]+|[^\u4e00-\u9fa50-9]+$/g, '');
                const parsed = this.parseChineseNumberToken(cleaned);
                if (Number.isInteger(parsed) && parsed >= 1 && parsed <= optionList.length) {
                    matchedIndexes.add(parsed - 1);
                }
            });

            if (hasSelectAllHint && matchedIndexes.size === 0) {
                optionList.forEach((_, idx) => matchedIndexes.add(idx));
            }

            const matchedOptions = Array.from(matchedIndexes)
                .sort((a, b) => a - b)
                .map(idx => optionList[idx]);

            const remainder = text
                .replace(/第\s*[0-9一二三四五六七八九十两]+\s*[个项条点]?/g, ' ')
                .replace(/\b\d+\b/g, ' ')
                .replace(/[一二三四五六七八九十两]+(?=[、，,;；\s]|$)/g, ' ')
                .replace(this.getOtherInputSelectAllRegex('g'), ' ')
                .replace(/(或者|和|及|与|或|、|，|,|;|；|\/)/g, ' ')
                .replace(/\s+/g, '');

            const pureReference = matchedOptions.length > 0 && remainder.length === 0;
            let intent = 'custom';
            if (pureReference && matchedOptions.length > 1) {
                intent = 'multi_reference';
            } else if (pureReference && matchedOptions.length === 1) {
                intent = 'single_reference';
            }

            return {
                matchedOptions,
                customText: pureReference ? '' : text,
                pureReference,
                intent
            };
        },

        buildOtherResolutionPayload(inputText, otherReference) {
            const sourceText = String(inputText || '').trim();
            const matchedOptions = Array.isArray(otherReference?.matchedOptions)
                ? otherReference.matchedOptions.map(item => String(item || '').trim()).filter(Boolean)
                : [];
            const customText = String(otherReference?.customText || '').trim();

            if (!sourceText && matchedOptions.length === 0 && !customText) {
                return null;
            }

            let mode = 'custom';
            if (matchedOptions.length > 0 && customText) {
                mode = 'mixed';
            } else if (matchedOptions.length > 0) {
                mode = 'reference';
            }

            return {
                mode,
                matched_options: Array.from(new Set(matchedOptions)),
                custom_text: customText,
                source_text: sourceText,
            };
        },

        splitAnswerTokens(answerText) {
            const text = String(answerText || '').trim();
            if (!text) return [];
            const tokens = text.split(/[；;]/).map(item => String(item || '').trim()).filter(Boolean);
            return tokens.length > 0 ? tokens : [text];
        },

        getLogOtherResolution(log, options = []) {
            if (!log || typeof log !== 'object') {
                return null;
            }

            const raw = log.other_resolution;
            if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
                return null;
            }

            const mode = String(raw.mode || '').trim().toLowerCase();
            if (!['reference', 'mixed', 'custom'].includes(mode)) {
                return null;
            }

            const optionSet = new Set(
                (Array.isArray(options) ? options : [])
                    .map(item => String(item || '').trim())
                    .filter(Boolean)
            );
            const matchedOptions = Array.isArray(raw.matched_options)
                ? raw.matched_options
                    .map(item => String(item || '').trim())
                    .filter(item => item && (!optionSet.size || optionSet.has(item)))
                : [];
            const customText = String(raw.custom_text || '').trim();
            const sourceText = String(raw.source_text || '').trim();

            if (mode === 'reference' && matchedOptions.length === 0) {
                return null;
            }
            if (mode === 'mixed' && (matchedOptions.length === 0 || !customText)) {
                return null;
            }
            if (mode === 'custom' && matchedOptions.length > 0) {
                return null;
            }

            return {
                mode,
                matchedOptions: Array.from(new Set(matchedOptions)),
                customText,
                sourceText,
            };
        },

        getLogSelectedOptions(log, options = [], otherResolution = null) {
            const optionList = Array.isArray(options)
                ? options.map(item => String(item || '').trim()).filter(Boolean)
                : [];
            if (optionList.length === 0) {
                return [];
            }

            const tokenSet = new Set(this.splitAnswerTokens(log?.answer || ''));
            if (otherResolution?.customText) {
                tokenSet.delete(otherResolution.customText);
            }

            const selectedSet = new Set(optionList.filter(option => tokenSet.has(option)));
            if (otherResolution?.matchedOptions?.length) {
                otherResolution.matchedOptions.forEach(option => selectedSet.add(option));
            }
            return optionList.filter(option => selectedSet.has(option));
        },

        resetSingleSelectDisambiguation() {
            this.singleSelectDisambiguationActive = false;
            this.singleSelectDisambiguationOptions = [];
            this.singleSelectDisambiguationRawText = '';
        },

        openSingleSelectDisambiguation(options, rawText = '') {
            this.singleSelectDisambiguationOptions = Array.isArray(options) ? [...options] : [];
            this.singleSelectDisambiguationRawText = rawText || '';
            this.singleSelectDisambiguationActive = this.singleSelectDisambiguationOptions.length > 1;
        },

        async submitSingleSelectAsMultiSelect() {
            if (this.submitting || !this.singleSelectDisambiguationOptions.length) return;
            this.resetSingleSelectDisambiguation();
            await this.submitAnswer({ allowSingleSelectMultiSubmit: true });
        },

        chooseSingleSelectDisambiguation(option) {
            if (!option) return;
            this.selectedAnswers = [option];
            this.otherSelected = false;
            this.otherAnswerText = '';
            this.resetSingleSelectDisambiguation();
            this.showToast('已按单选规则选择主项，可直接提交', 'info');
        },

        continueSingleSelectWithCustomText() {
            const template = '我更倾向于【】，因为【】';
            this.selectedAnswers = [];
            this.otherSelected = true;
            this.otherAnswerText = template;
            this.rationaleText = '';
            this.resetSingleSelectDisambiguation();
            this.showToast('已切换为自由补充模式，可直接描述你的判断', 'info');
            this.$nextTick(() => {
                const input = this.$refs.otherInput;
                if (!input) return;
                input.focus();
                const firstSlotStart = template.indexOf('【') + 1;
                if (firstSlotStart > 0) {
                    input.setSelectionRange(firstSlotStart, firstSlotStart);
                }
            });
        },

        matchRecommendedOption(recommended, options) {
            if (!recommended || !options || options.length === 0) return null;
            const direct = options.find(opt => opt === recommended);
            if (direct) return direct;

            const lower = recommended.toLowerCase();
            const lowerMatch = options.find(opt => opt.toLowerCase() === lower);
            if (lowerMatch) return lowerMatch;

            const containsMatch = options.find(opt => opt.includes(recommended) || recommended.includes(opt));
            if (containsMatch) return containsMatch;

            const normRec = this.normalizeOptionText(recommended);
            const normMatch = options.find(opt => {
                const normOpt = this.normalizeOptionText(opt);
                return normOpt.includes(normRec) || normRec.includes(normOpt);
            });
            return normMatch || null;
        },

        getAiRecommendationMatches() {
            if (this.isAssessmentSession()) return [];

            const rec = this.currentQuestion?.aiRecommendation;
            const options = this.currentQuestion?.options || [];
            if (!rec || !Array.isArray(rec.recommendedOptions)) return [];
            const matched = rec.recommendedOptions
                .map(item => this.matchRecommendedOption(item, options))
                .filter(Boolean);
            return matched;
        },

        getAiRecommendationDisplayOptions() {
            const matched = this.getAiRecommendationMatches();
            if (matched.length > 0) return matched;
            const rec = this.currentQuestion?.aiRecommendation;
            return Array.isArray(rec?.recommendedOptions) ? rec.recommendedOptions : [];
        },

        isOptionRecommended(option) {
            if (this.isAssessmentSession()) return false;
            return this.getAiRecommendationMatches().includes(option);
        },

        applyAiRecommendation() {
            if (this.isAssessmentSession()) return;

            const rec = this.currentQuestion?.aiRecommendation;
            if (!rec || !rec.recommendedOptions || rec.recommendedOptions.length === 0) return;

            this.aiRecommendationPrevSelection = {
                selectedAnswers: [...this.selectedAnswers],
                rationaleText: this.rationaleText,
                otherSelected: this.otherSelected,
                otherAnswerText: this.otherAnswerText
            };

            const matchedOptions = this.getAiRecommendationMatches();
            const targets = matchedOptions.length > 0 ? matchedOptions : rec.recommendedOptions;
            if (this.currentQuestion.multiSelect) {
                const merged = new Set([...this.selectedAnswers, ...targets]);
                this.selectedAnswers = Array.from(merged);
            } else {
                this.selectedAnswers = [targets[0]];
            }
            this.otherSelected = false;
            this.otherAnswerText = '';
            this.resetSingleSelectDisambiguation();
            this.aiRecommendationApplied = true;
        },

        revertAiRecommendation() {
            if (!this.aiRecommendationApplied || !this.aiRecommendationPrevSelection) return;
            const prev = this.aiRecommendationPrevSelection;
            this.selectedAnswers = [...(prev.selectedAnswers || [])];
            this.rationaleText = prev.rationaleText || '';
            this.otherSelected = !!prev.otherSelected;
            this.otherAnswerText = prev.otherAnswerText || '';
            this.resetSingleSelectDisambiguation();
            this.aiRecommendationApplied = false;
            this.aiRecommendationPrevSelection = null;
        },

        jumpToEvidence(evidenceId) {
            if (!evidenceId) return;
            const target = document.querySelector(`[data-qa-id="${evidenceId}"]`);
            if (!target) return;
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.classList.add('evidence-highlight');
            setTimeout(() => {
                target.classList.remove('evidence-highlight');
            }, 1800);
        },

        normalizeEvidenceId(evidence) {
            if (!evidence) return null;
            const raw = String(evidence).trim();
            const match = raw.match(/Q\s*(\d+)/i);
            if (match && match[1]) return `Q${match[1]}`;
            const pure = raw.match(/^\(?Q(\d+)\)?$/i);
            if (pure && pure[1]) return `Q${pure[1]}`;
            return null;
        },

        formatEvidenceLabel(evidence) {
            const id = this.normalizeEvidenceId(evidence);
            if (id) {
                const num = id.replace(/[^0-9]/g, '');
                return `第${num}题`;
            }
            return '要点';
        },

        evidenceCanJump(evidence) {
            return !!this.normalizeEvidenceId(evidence);
        },

        // 切换选项选择状态
        toggleOption(option) {
            this.clearAiRecommendationApplied();
            this.resetSingleSelectDisambiguation();
            if (this.currentQuestion.multiSelect) {
                // 多选模式：切换选中状态
                const index = this.selectedAnswers.indexOf(option);
                if (index > -1) {
                    this.selectedAnswers.splice(index, 1);
                } else {
                    this.selectedAnswers.push(option);
                }
            } else {
                // 单选模式：替换选中项
                this.selectedAnswers = [option];
                this.otherSelected = false;
                this.otherAnswerText = '';
            }
        },

        // 检查选项是否被选中
        isOptionSelected(option) {
            return this.selectedAnswers.includes(option);
        },

        // 切换"其他"选项
        toggleOther() {
            this.clearAiRecommendationApplied();
            this.resetSingleSelectDisambiguation();
            if (this.currentQuestion.multiSelect) {
                // 多选模式：切换"其他"选中状态
                this.otherSelected = !this.otherSelected;
                if (!this.otherSelected) {
                    this.otherAnswerText = '';
                }
            } else {
                // 单选模式：选中"其他"，清除其他选项
                this.selectedAnswers = [];
                this.otherSelected = true;
            }
        },

        async submitAnswer(submissionOptions = {}) {
            if (!this.canSubmitAnswer()) return;

            this.submitting = true;
            let handedOffToNextQuestion = false;

            const config = typeof SITE_CONFIG !== 'undefined' ? SITE_CONFIG.limits : null;
            const answerMaxLength = config?.answerMaxLength || 5000;
            const otherInputMaxLength = config?.otherInputMaxLength || 2000;
            const rationaleText = this.rationaleText.trim();

            if (this.otherSelected && this.otherAnswerText.length > otherInputMaxLength) {
                this.showToast(`自定义答案不能超过${otherInputMaxLength}个字符`, 'error');
                this.submitting = false;
                return;
            }

            let answer;
            const otherText = this.otherAnswerText.trim();
            const otherReference = this.otherSelected
                ? this.resolveOtherInputReferences(otherText, this.currentQuestion.options)
                : { matchedOptions: [], customText: '', pureReference: false, intent: 'custom' };
            const otherResolution = this.otherSelected
                ? this.buildOtherResolutionPayload(otherText, otherReference)
                : null;
            const questionMultiSelect = !!(this.currentQuestion.questionMultiSelect ?? this.currentQuestion.multiSelect);
            const canEscalateSingleSelect = !questionMultiSelect
                && this.otherSelected
                && otherReference.pureReference
                && otherReference.matchedOptions.length > 1;
            const effectiveMultiSelect = questionMultiSelect
                || (submissionOptions.allowSingleSelectMultiSubmit === true && canEscalateSingleSelect);
            const selectionEscalatedFromSingle = !questionMultiSelect && effectiveMultiSelect;

            if (canEscalateSingleSelect && !effectiveMultiSelect) {
                this.submitting = false;
                this.openSingleSelectDisambiguation(otherReference.matchedOptions, otherText);
                return;
            }

            if (effectiveMultiSelect) {
                const answers = [...this.selectedAnswers];
                if (this.otherSelected && otherText) {
                    if (otherReference.matchedOptions.length > 0) {
                        answers.push(...otherReference.matchedOptions);
                    }
                    if (otherReference.customText) {
                        answers.push(otherReference.customText);
                    }
                }
                const uniqueAnswers = Array.from(new Set(answers.map(item => String(item || '').trim()).filter(Boolean)));
                if (uniqueAnswers.length === 0) {
                    this.submitting = false;
                    return;
                }
                answer = uniqueAnswers.join('；');
            } else {
                if (this.otherSelected) {
                    if (otherReference.pureReference && otherReference.matchedOptions.length > 0) {
                        answer = otherReference.matchedOptions[0];
                    } else {
                        answer = otherText;
                    }
                } else {
                    answer = this.selectedAnswers.length > 0 ? this.selectedAnswers[0] : '';
                }
                if (!answer) {
                    this.submitting = false;
                    return;
                }
            }

            if (answer.length > answerMaxLength) {
                this.showToast(`答案内容过长，请简化后重试（最大${answerMaxLength}字符）`, 'error');
                this.submitting = false;
                return;
            }

            try {
                this.loadingQuestion = true;
                this.skeletonMode = false;
                this.interactionReady = false;
                this.startTipRotation();
                this.applyThinkingStage({
                    stage_index: 0,
                    stage_name: '分析回答',
                    message: '正在提交当前回答并准备下一题',
                    progress: 18
                }, { preserveProgress: false });

                const updatedSession = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/submit-answer`,
                    {
                        method: 'POST',
                        body: JSON.stringify({
                            question: this.currentQuestion.text,
                            answer: answer,
                            dimension: this.currentDimension,
                            options: this.currentQuestion.options,
                            multi_select: effectiveMultiSelect,
                            question_multi_select: questionMultiSelect,
                            selection_escalated_from_single: selectionEscalatedFromSingle,
                            other_selected: this.otherSelected,
                            other_answer_text: this.otherSelected ? this.otherAnswerText : '',
                            other_resolution: otherResolution || undefined,
                            is_follow_up: this.currentQuestion.isFollowUp || false,
                            answer_mode: this.currentQuestion.answerMode || 'pick_only',
                            requires_rationale: !!this.currentQuestion.requiresRationale,
                            evidence_intent: this.currentQuestion.evidenceIntent || 'low',
                            rationale_text: rationaleText,
                            question_generation_tier: this.currentQuestion.questionGenerationTier || '',
                            question_selected_lane: this.currentQuestion.questionSelectedLane || '',
                            question_runtime_profile: this.currentQuestion.questionRuntimeProfile || '',
                            question_hedge_triggered: !!this.currentQuestion.questionHedgeTriggered,
                            question_fallback_triggered: !!this.currentQuestion.questionFallbackTriggered,
                            ai_recommendation: this.serializeAiRecommendation(this.currentQuestion.aiRecommendation),
                            preflight_intervened: !!this.currentQuestion.preflightIntervened,
                            preflight_fingerprint: this.currentQuestion.preflightFingerprint || '',
                            preflight_planner_mode: this.currentQuestion.preflightPlannerMode || '',
                            preflight_probe_slots: Array.isArray(this.currentQuestion.preflightProbeSlots)
                                ? this.currentQuestion.preflightProbeSlots
                                : []
                        })
                    }
                );

                this.currentSession = updatedSession;

                const currentDim = this.currentSession.dimensions[this.currentDimension];
                if (currentDim && currentDim.coverage >= 100) {
                    const completedDimension = this.currentDimension;
                    this.ensureDimensionVisualComplete(completedDimension);
                    const nextDim = this.getNextIncompleteDimension();
                    if (nextDim) {
                        this.currentDimension = nextDim;
                    } else {
                        this.clearInterviewLoadingState();
                        this.currentQuestion = this.createQuestionState();
                        this.aiRecommendationExpanded = false;
                        this.aiRecommendationApplied = false;
                        this.aiRecommendationPrevSelection = null;
                        this.showToast('所有维度访谈完成！', 'success');
                        return;
                    }
                }

                handedOffToNextQuestion = true;
                await this.fetchNextQuestion({ preferPrefetch: true, force: true });

            } catch (error) {
                this.clearInterviewLoadingState();
                this.interactionReady = true;
                console.error('提交回答错误:', error);
                this.showToast(`提交回答失败: ${error.message}`, 'error');
            } finally {
                this.submitting = false;
                if (!handedOffToNextQuestion) {
                    this.clearInterviewLoadingState();
                    this.interactionReady = true;
                }
            }
        },

        getQuestionNumber() {
            // 只计算正式问题，追问不计入问题编号
            const answered = this.currentSession.interview_log.filter(
                l => l.dimension === this.currentDimension && !l.is_follow_up
            ).length;
            return answered + 1;
        },

        canGoPrevQuestion() {
            // 提交过程中不允许回退
            if (this.submitting) {
                return false;
            }
            return this.currentSession && this.currentSession.interview_log.length > 0;
        },

        async goPrevQuestion() {
            if (!this.canGoPrevQuestion()) return;

            // 设置提交状态，防止并发操作
            this.submitting = true;

            try {
                // 先保存要恢复的问题信息（在调用 undo 之前）
                const lastLog = this.currentSession.interview_log[this.currentSession.interview_log.length - 1];
                if (!lastLog) {
                    this.showToast('没有可撤销的问题', 'warning');
                    return;
                }

                const undoDimension = lastLog.dimension;
                const savedQuestion = this.createQuestionState({
                    text: lastLog.question,
                    options: lastLog.options || [],
                    multiSelect: (lastLog.question_multi_select ?? lastLog.multi_select) || false,
                    questionMultiSelect: (lastLog.question_multi_select ?? lastLog.multi_select) || false,
                    isFollowUp: lastLog.is_follow_up || false,
                    answerMode: lastLog.answer_mode || 'pick_only',
                    requiresRationale: !!lastLog.requires_rationale,
                    evidenceIntent: lastLog.evidence_intent || 'low',
                    questionGenerationTier: lastLog.question_generation_tier || '',
                    questionSelectedLane: lastLog.question_selected_lane || '',
                    questionRuntimeProfile: lastLog.question_runtime_profile || '',
                    questionHedgeTriggered: !!lastLog.question_hedge_triggered,
                    questionFallbackTriggered: !!lastLog.question_fallback_triggered,
                    aiRecommendation: this.normalizeAiRecommendation({ ai_recommendation: lastLog.ai_recommendation }),
                    preflightIntervened: !!lastLog.preflight_intervened,
                    preflightFingerprint: lastLog.preflight_fingerprint || '',
                    preflightPlannerMode: lastLog.preflight_planner_mode || '',
                    preflightProbeSlots: Array.isArray(lastLog.preflight_probe_slots) ? lastLog.preflight_probe_slots : [],
                    aiGenerated: true
                });

                // 调用后端 API 撤销最后一个回答
                const updatedSession = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/undo-answer`,
                    { method: 'POST' }
                );

                this.currentSession = updatedSession;

                // 切换到被撤销问题所在的维度
                this.currentDimension = undoDimension;

                // 标记为返回上一题操作
                this.isGoingPrev = true;

                // 直接恢复上一题的问题，而不是调用 AI 重新生成
                this.currentQuestion = savedQuestion;
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                this.selectedAnswers = [];
                this.rationaleText = '';
                this.otherAnswerText = '';
                this.otherSelected = false;
                this.resetSingleSelectDisambiguation();
                this.loadingQuestion = false;

                this.showToast('已恢复上一题，请重新作答', 'success');
            } catch (error) {
                this.showToast('撤销失败', 'error');
            } finally {
                this.isGoingPrev = false;
                this.submitting = false;  // 确保清除提交状态
            }
        },

        // 用户跳过当前问题的追问
        async skipFollowUp() {
            if (!this.currentSession || this.submitting) return;

            const currentMode = this.currentSession?.interview_mode || 'standard';
            const needConfirm = currentMode === 'deep'
                && this.interviewDepthV2?.deep_mode_skip_followup_confirm === true;

            if (needConfirm) {
                const confirmed = await this.openActionConfirmDialog({
                    title: '确认跳过追问',
                    message: '跳过追问会降低该维度结论可信度，是否继续？',
                    tone: 'warning',
                    confirmText: '继续跳过',
                    cancelText: '继续作答'
                });
                if (!confirmed) {
                    return;
                }
            }

            this.submitting = true;

            try {
                await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/skip-follow-up`,
                    {
                        method: 'POST',
                        body: JSON.stringify({ dimension: this.currentDimension })
                    }
                );

                this.showToast('已跳过追问', 'success');

                // 获取下一个问题
                await this.fetchNextQuestion();
            } catch (error) {
                this.showToast(`跳过失败: ${error.message}`, 'error');
            } finally {
                this.submitting = false;
            }
        },

        // 用户完成当前维度
        async completeDimension() {
            if (!this.currentSession) return;

            // 安全访问当前维度
            const currentDim = this.currentSession.dimensions[this.currentDimension];
            if (!currentDim) {
                this.showToast('维度数据异常', 'error');
                return;
            }

            const coverage = currentDim.coverage;
            if (coverage >= 100) {
                this.showToast('该维度已完成', 'info');
                return;
            }
            if (coverage < 50) {
                this.showToast('当前维度覆盖度不足50%，建议至少回答一半问题', 'warning');
                return;
            }

            const currentMode = this.currentSession?.interview_mode || 'standard';
            const needConfirm = currentMode === 'deep'
                && this.interviewDepthV2?.deep_mode_skip_followup_confirm === true;

            if (needConfirm) {
                const confirmed = await this.openActionConfirmDialog({
                    title: '确认跳到下一维度',
                    message: '提前结束当前维度会影响访谈质量，并降低该维度结论可信度，是否继续？',
                    tone: 'warning',
                    confirmText: '继续跳转',
                    cancelText: '继续访谈'
                });
                if (!confirmed) {
                    return;
                }
            }

            if (this.submitting) return;
            this.submitting = true;

            try {
                const result = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/complete-dimension`,
                    {
                        method: 'POST',
                        body: JSON.stringify({ dimension: this.currentDimension })
                    }
                );

                this.showToast(result.message, 'success');

                // 重新加载会话数据
                this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);

                // 切换到下一个未完成的维度
                const nextDim = this.getNextIncompleteDimension();
                if (nextDim) {
                    this.ensureDimensionVisualComplete(this.currentDimension);
                    this.currentDimension = nextDim;
                    await this.fetchNextQuestion();
                } else {
                    // 所有维度完成，停留在访谈阶段显示完成提示
                    this.currentStep = 1;
                    this.currentQuestion = this.createQuestionState();
                    this.aiRecommendationExpanded = false;
                    this.aiRecommendationApplied = false;
                    this.aiRecommendationPrevSelection = null;
                }
            } catch (error) {
                const errorMsg = error.detail || error.message || '完成维度失败';
                this.showToast(errorMsg, 'error');
            } finally {
                this.submitting = false;
            }
        },

        // 检查是否可以显示"跳过追问"按钮
        canShowSkipFollowUp() {
            return this.currentQuestion.isFollowUp;
        },

        // 检查是否可以显示"完成维度"按钮
        canShowCompleteDimension() {
            if (!this.currentSession) return false;
            const currentDim = this.currentSession.dimensions[this.currentDimension];
            if (!currentDim) return false;
            const coverage = currentDim.coverage;
            return coverage >= 50 && coverage < 100;
        },

        goToConfirmation() {
            this.currentStep = 2;
        },

        // ============ 重新开始访谈 ============
        confirmRestartResearch() {
            this.showRestartModal = true;
        },

        async restartResearch() {
            if (!this.currentSession) return;
            this.showRestartModal = false;

            try {
                const result = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/restart-interview`,
                    { method: 'POST' }
                );

                if (result.success) {
                    // 刷新会话数据
                    this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);
                    this.updateDimensionsFromSession(this.currentSession);

                    // 重置前端状态
                    this.questionRequestId += 1;
                    this.abortQuestionRequest();
                    this.stopQuestionRequestGuard();
                    this.stopThinkingPolling();
                    this.stopWebSearchPolling();
                    this.loadingQuestion = false;
                    this.currentStep = 0;
                    this.currentDimension = this.dimensionOrder[0] || 'customer_needs';
                    this.currentQuestion = null;

                    this.showToast('已保存当前访谈内容，已重新开始访谈流程', 'success');
                } else {
                    this.showToast('重新开始访谈失败', 'error');
                }
            } catch (error) {
                console.error('重新开始访谈错误:', error);
                this.showToast('重新开始访谈失败', 'error');
            }
        },

        // ============ 访谈报告生成（AI 驱动）============
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
                    if (!data) {
                        return;
                    }

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
                    await new Promise(resolve => setTimeout(resolve, 700));
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
            this.startWebSearchPolling();  // 开始轮询 Web Search 状态

            try {
                const result = await this.requestGenerateReportWithRetry(sessionId, action, 1, options);

                // 兼容旧同步返回：如果后端直接返回最终报告，则沿用旧逻辑。
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
                this.stopWebSearchPolling();  // 停止轮询 Web Search 状态
            }
        },

        isGeneratingCurrentReport() {
            if (!this.generatingReport) return false;
            const currentId = this.currentSession?.session_id || '';
            return Boolean(currentId && currentId === this.generatingReportSessionId);
        },

        // ============ 报告查看 ============
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
            if (['finish', 'finished', 'completed', 'success', 'succeeded', 'done'].some(key => text.includes(key))) {
                return 'finished';
            }
            if (['fail', 'failed', 'error', 'cancelled', 'canceled', 'aborted', 'stopped'].some(key => text.includes(key))) {
                return 'failed';
            }
            if (['executing', 'running', 'processing', 'in_progress', 'working'].some(key => text.includes(key))) {
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

            const runningStage = stageData.find(stage => stage.status === 'running');
            const pendingStage = stageData.find(stage => stage.status === 'pending');
            const failedStage = stageData.find(stage => stage.status === 'failed');
            const finishedStages = stageData.filter(stage => stage.status === 'finished');

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
            const maxAttempts = 200; // 约 20 分钟（每 6 秒）
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
                payload.forEach(item => this.collectReflyUrls(item, urls));
                return urls;
            }
            if (typeof payload === 'object') {
                Object.values(payload).forEach(value => this.collectReflyUrls(value, urls));
            }
            return urls;
        },

        getReflyFileCandidates(result) {
            const files = result?.refly_response?.data?.files
                || result?.refly_response?.files
                || [];
            if (!Array.isArray(files)) return [];
            return files
                .map(file => ({
                    url: file?.url,
                    name: file?.name || ''
                }))
                .filter(item => typeof item.url === 'string' && item.url.startsWith('http'));
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
            this.getReflyFileCandidates(result).forEach(item => addCandidate(item.url, item.name));

            const extraUrls = this.collectReflyUrls(result?.refly_response, []);
            extraUrls.forEach(url => addCandidate(url));

            const deduped = Array.from(new Map(candidates.map(item => [item.url, item])).values());
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

        // 当报告内容渲染完成后调用（由 x-effect 触发）
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

        async downloadReport(format = 'md') {
            if (!this.reportContent || !this.selectedReport) return;
            if (!this.canExportFormat('report', format)) {
                this.showToast('当前用户级别暂未开放该导出格式', 'warning');
                return;
            }

            const baseFilename = this.selectedReport.replace(/\.md$/, '');

            switch (format) {
                case 'md':
                    await this.downloadMarkdown(baseFilename);
                    break;
                case 'pdf':
                    await this.downloadPDF(baseFilename);
                    break;
                case 'docx':
                    await this.downloadDocx(baseFilename);
                    break;
                default:
                    await this.downloadMarkdown(baseFilename);
            }
        },

        async downloadAppendix(format = 'md') {
            if (!this.reportContent || !this.selectedReport) {
                this.showToast('暂无可导出的附录内容', 'error');
                return;
            }
            if (!this.canExportFormat('appendix', format)) {
                this.showToast('当前用户级别暂未开放附录导出', 'warning');
                return;
            }

            const appendixContent = this.getAppendixExportContent();
            if (!appendixContent) {
                this.showToast('未找到附录内容，无法导出', 'error');
                return;
            }

            const baseFilename = this.selectedReport.replace(/\.md$/, '');
            const appendixFilename = `${baseFilename}-完整访谈记录`;

            switch (format) {
                case 'md':
                    await this.downloadMarkdown(appendixFilename, { scope: 'appendix' });
                    break;
                case 'pdf':
                    await this.downloadPDF(appendixFilename, { scope: 'appendix' });
                    break;
                case 'docx':
                    await this.downloadDocx(appendixFilename, { scope: 'appendix' });
                    break;
                default:
                    await this.downloadMarkdown(appendixFilename, { scope: 'appendix' });
            }
        },

        getReportExportContent() {
            if (!this.reportContent) return '';
            let content = this.stripInlineEvidenceMarkers(this.reportContent);
            const appendixIndex = content.indexOf('## 附录：完整访谈记录');
            if (appendixIndex !== -1) {
                content = content.slice(0, appendixIndex).trimEnd();
            }
            // 导出时移除“报告质量指标”区块（兼容历史报告）
            content = content.replace(/(^|\n)###\s*报告质量指标[\s\S]*?(?=\n##\s|\n###\s|$)/g, '\n');
            // 导出时移除“生成方式”行（兼容历史报告）
            content = content.replace(/^\s*\*\*生成方式\*\*:[^\n]*\n?/gm, '');
            return content.trim();
        },

        getAppendixExportContent() {
            if (!this.reportContent) return '';
            const content = String(this.stripInlineEvidenceMarkers(this.reportContent) || '');
            const appendixIndex = content.indexOf('## 附录：完整访谈记录');
            if (appendixIndex === -1) return '';

            let appendix = content.slice(appendixIndex).trim();
            appendix = appendix.replace(/^\s*\*\*生成方式\*\*:[^\n]*\n?/gm, '');
            appendix = this.normalizeAppendixSummaryText(appendix);
            return appendix.trim();
        },

        normalizeAppendixSummaryText(content) {
            return String(content || '')
                .replace(/本次访谈共手机了/g, '本次访谈共收集了')
                .replace(/\s*[（(]点击展开\/收起[）)]/g, '')
                .replace(/[ \t]{2,}/g, ' ');
        },

        stripHtmlToPlainText(rawHtml) {
            const input = String(rawHtml || '');
            if (!input) return '';

            const normalizedInput = input
                .replace(/<br\s*\/?>/gi, '\n')
                .replace(/<\/(div|p|li|h[1-6]|tr|summary)>/gi, '</$1>\n')
                .replace(/<\/(ul|ol|table|thead|tbody|details)>/gi, '</$1>\n')
                .replace(/&nbsp;/gi, ' ');

            if (typeof DOMParser === 'undefined') {
                return normalizedInput
                    .replace(/<[^>]+>/g, '')
                    .replace(/&lt;/g, '<')
                    .replace(/&gt;/g, '>')
                    .replace(/&quot;/g, '"')
                    .replace(/&#39;/g, "'")
                    .replace(/&amp;/g, '&')
                    .replace(/\r/g, '');
            }

            const parser = new DOMParser();
            const doc = parser.parseFromString(`<div id="appendix-plain-text-root">${normalizedInput}</div>`, 'text/html');
            const root = doc.getElementById('appendix-plain-text-root');
            const text = root ? (root.textContent || '') : normalizedInput.replace(/<[^>]+>/g, '');
            return text.replace(/\r/g, '');
        },

        normalizeAppendixHtmlForDocx(markdownText) {
            let content = this.normalizeAppendixSummaryText(markdownText);
            if (!content) return '';

            content = content
                .replace(/<details>\s*/gi, '')
                .replace(/<\/details>\s*/gi, '\n')
                .replace(/<summary>([\s\S]*?)<\/summary>/gi, (_, rawText) => {
                    const text = this.stripHtmlToPlainText(rawText)
                        .replace(/\s+/g, ' ')
                        .trim();
                    return text ? `### ${text}\n` : '';
                })
                .replace(/<div\b[^>]*>([\s\S]*?)<\/div>/gi, (_, rawText) => {
                    const text = this.stripHtmlToPlainText(rawText)
                        .split('\n')
                        .map(line => line.trim())
                        .filter(Boolean)
                        .join('\n');
                    return text ? `${text}\n` : '\n';
                })
                .replace(/<br\s*\/?>/gi, '\n');

            const plainText = this.stripHtmlToPlainText(content)
                .replace(/[ \t]+\n/g, '\n')
                .replace(/\n[ \t]+/g, '\n')
                .replace(/[ \t]{2,}/g, ' ');

            const rawLines = plainText.split('\n');
            const cleanedLines = [];
            for (let i = 0; i < rawLines.length; i++) {
                const line = rawLines[i].trim();
                if (!line) {
                    if (cleanedLines[cleanedLines.length - 1] === '') {
                        continue;
                    }

                    let nextLine = '';
                    for (let j = i + 1; j < rawLines.length; j++) {
                        const candidate = rawLines[j].trim();
                        if (candidate) {
                            nextLine = candidate;
                            break;
                        }
                    }

                    const prevLine = cleanedLines[cleanedLines.length - 1] || '';
                    const prevIsAnswerLine = /^(回答：|[☐☑])/.test(prevLine);
                    const nextIsAnswerOption = /^[☐☑]/.test(nextLine);
                    if (prevIsAnswerLine && nextIsAnswerOption) {
                        continue;
                    }

                    cleanedLines.push('');
                    continue;
                }

                cleanedLines.push(line);
            }

            return cleanedLines.join('\n')
                .replace(/\n{3,}/g, '\n\n')
                .trim();
        },

        stripInlineEvidenceMarkers(content = '') {
            return String(content || '')
                .replace(/\[\s*证据\s*[：:][^\]\n]*\]/g, '')
                .replace(/[（(]\s*证据\s*[：:][^）)\n]*[）)]/g, '')
                .replace(/[（(]\s*Q\d+(?:\s*[,，、/]\s*Q\d+)*\s*[）)]/gi, '')
                .replace(/\[\s*Q\d+(?:\s*[,，、/]\s*Q\d+)*\s*\]/gi, '')
                .replace(/[ \t]{2,}/g, ' ')
                .replace(/\s+([，。！？；：,.!?;:])/g, '$1')
                .replace(/\n{3,}/g, '\n\n')
                .trim();
        },

        getAppendixExportContentForDocx() {
            let content = this.getAppendixExportContent();
            if (!content) return '';

            content = this.normalizeAppendixHtmlForDocx(content);
            return content;
        },

        escapeHtml(text) {
            return String(text || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        },

        formatMarkdownInlineForPdf(text) {
            const escaped = this.escapeHtml(text);
            return escaped
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.+?)\*/g, '<em>$1</em>')
                .replace(/`(.+?)`/g, '<code>$1</code>');
        },

        convertAppendixMarkdownToPdfHtml(markdownContent) {
            const lines = String(markdownContent || '').split('\n');
            const htmlParts = [];
            let listBuffer = [];

            const flushList = () => {
                if (listBuffer.length === 0) return;
                htmlParts.push('<ul>');
                listBuffer.forEach(item => {
                    htmlParts.push(`<li>${this.formatMarkdownInlineForPdf(item)}</li>`);
                });
                htmlParts.push('</ul>');
                listBuffer = [];
            };

            lines.forEach((rawLine) => {
                const line = String(rawLine || '').trim();
                if (!line) {
                    flushList();
                    return;
                }

                if (line.startsWith('- ')) {
                    listBuffer.push(line.slice(2).trim());
                    return;
                }

                flushList();

                if (line.startsWith('### ')) {
                    htmlParts.push(`<h3>${this.escapeHtml(line.slice(4).trim())}</h3>`);
                } else if (line.startsWith('## ')) {
                    htmlParts.push(`<h2>${this.escapeHtml(line.slice(3).trim())}</h2>`);
                } else if (line.startsWith('# ')) {
                    htmlParts.push(`<h1>${this.escapeHtml(line.slice(2).trim())}</h1>`);
                } else {
                    htmlParts.push(`<p>${this.formatMarkdownInlineForPdf(line)}</p>`);
                }
            });

            flushList();
            return htmlParts.join('\n').trim();
        },

        wrapCanvasText(ctx, text, maxWidth) {
            const content = String(text || '');
            if (!content) return [''];
            const chars = Array.from(content);
            const lines = [];
            let current = '';

            chars.forEach((ch) => {
                const candidate = `${current}${ch}`;
                if (current && ctx.measureText(candidate).width > maxWidth) {
                    lines.push(current);
                    current = ch;
                } else {
                    current = candidate;
                }
            });
            if (current) lines.push(current);
            return lines.length > 0 ? lines : [''];
        },

        renderAppendixCanvasPages(markdownContent) {
            const pageWidth = 1240;
            const pageHeight = 1754;
            const marginX = 86;
            const marginY = 92;
            const maxWidth = pageWidth - marginX * 2;
            const lines = String(markdownContent || '').split('\n');
            const pages = [];

            const createPage = () => {
                const canvas = document.createElement('canvas');
                canvas.width = pageWidth;
                canvas.height = pageHeight;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, pageWidth, pageHeight);
                ctx.textBaseline = 'top';
                ctx.fillStyle = '#111827';
                return { canvas, ctx, y: marginY };
            };

            let page = createPage();

            const ensureSpace = (heightNeeded) => {
                if (page.y + heightNeeded <= pageHeight - marginY) return;
                pages.push(page.canvas);
                page = createPage();
            };

            lines.forEach((rawLine) => {
                const line = String(rawLine || '').trim();
                if (!line) {
                    page.y += 18;
                    return;
                }

                let text = line;
                let fontSize = 25;
                let fontWeight = '400';
                let lineHeight = 37;
                let spacingAfter = 10;

                if (line.startsWith('# ')) {
                    text = line.slice(2).trim();
                    fontSize = 32;
                    fontWeight = '700';
                    lineHeight = 46;
                    spacingAfter = 18;
                } else if (line.startsWith('## ')) {
                    text = line.slice(3).trim();
                    fontSize = 28;
                    fontWeight = '700';
                    lineHeight = 40;
                    spacingAfter = 16;
                } else if (line.startsWith('### ')) {
                    text = line.slice(4).trim();
                    fontSize = 26;
                    fontWeight = '600';
                    lineHeight = 38;
                    spacingAfter = 14;
                } else if (line.startsWith('- ')) {
                    text = `• ${line.slice(2).trim()}`;
                    fontSize = 25;
                    lineHeight = 37;
                    spacingAfter = 6;
                } else {
                    fontSize = 25;
                    lineHeight = 37;
                    spacingAfter = 8;
                }

                text = this.stripMarkdownFormatting(text).trim();
                if (!text) return;

                page.ctx.font = `${fontWeight} ${fontSize}px "Microsoft YaHei", "PingFang SC", sans-serif`;
                const wrapped = this.wrapCanvasText(page.ctx, text, maxWidth);
                ensureSpace(wrapped.length * lineHeight + spacingAfter);
                wrapped.forEach((segment) => {
                    page.ctx.fillText(segment, marginX, page.y);
                    page.y += lineHeight;
                });
                page.y += spacingAfter;
            });

            pages.push(page.canvas);
            return pages;
        },

        async buildAppendixPdfBlobViaCanvas(markdownContent) {
            if (typeof html2pdf === 'undefined') return null;

            const pages = this.renderAppendixCanvasPages(markdownContent);
            if (!Array.isArray(pages) || pages.length === 0) return null;

            const isValidPdfBlob = (blob) => blob instanceof Blob && blob.size >= 1024;

            // 优先走 HTML 导出链路（与报告导出同源），稳定性更高
            try {
                const html = this.convertAppendixMarkdownToPdfHtml(markdownContent);
                if (html) {
                    const tempContainer = document.createElement('div');
                    tempContainer.style.cssText = 'padding: 40px; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; line-height: 1.8; color: #1a1a1a; background: #ffffff; width: 794px; box-sizing: border-box;';

                    const style = document.createElement('style');
                    style.textContent = `
                        h1 { font-size: 24px; font-weight: 700; margin: 24px 0 16px; color: #111; }
                        h2 { font-size: 20px; font-weight: 700; margin: 20px 0 12px; color: #222; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }
                        h3 { font-size: 16px; font-weight: 700; margin: 16px 0 8px; color: #333; }
                        p { margin: 8px 0; font-size: 14px; }
                        ul, ol { margin: 8px 0; padding-left: 24px; }
                        li { margin: 4px 0; font-size: 14px; }
                        code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
                    `;
                    tempContainer.appendChild(style);

                    const contentWrap = document.createElement('div');
                    contentWrap.innerHTML = html;
                    tempContainer.appendChild(contentWrap);
                    document.body.appendChild(tempContainer);

                    try {
                        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                        const worker = html2pdf().set({
                            margin: [15, 15, 15, 15],
                            filename: 'appendix.pdf',
                            image: { type: 'jpeg', quality: 0.98 },
                            html2canvas: {
                                scale: 2,
                                useCORS: true,
                                logging: false,
                                backgroundColor: '#ffffff',
                            },
                            jsPDF: {
                                unit: 'mm',
                                format: 'a4',
                                orientation: 'portrait'
                            },
                            pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
                        }).from(tempContainer).toPdf();

                        const pdf = await worker.get('pdf');
                        if (pdf) {
                            const htmlBlob = pdf.output('blob');
                            if (isValidPdfBlob(htmlBlob)) {
                                return htmlBlob;
                            }
                            console.warn('附录 PDF HTML 导出体积异常', { size: htmlBlob?.size || 0 });
                        }
                    } finally {
                        if (tempContainer.parentNode) {
                            tempContainer.parentNode.removeChild(tempContainer);
                        }
                    }
                }
            } catch (error) {
                console.warn('附录 PDF HTML 导出失败，回退 Canvas 方案:', error);
            }

            // 兜底：Canvas 直接写入 jsPDF
            try {
                const jsPdfCtor = (typeof window !== 'undefined' && window.jspdf && typeof window.jspdf.jsPDF === 'function')
                    ? window.jspdf.jsPDF
                    : ((typeof window !== 'undefined' && typeof window.jsPDF === 'function') ? window.jsPDF : null);

                if (jsPdfCtor) {
                    const pdf = new jsPdfCtor({
                        unit: 'mm',
                        format: 'a4',
                        orientation: 'portrait'
                    });

                    pages.forEach((canvas, index) => {
                        const imageData = canvas.toDataURL('image/jpeg', 0.96);
                        if (index > 0) {
                            pdf.addPage('a4', 'portrait');
                        }
                        pdf.addImage(imageData, 'JPEG', 0, 0, 210, 297, undefined, 'FAST');
                    });

                    const directBlob = pdf.output('blob');
                    if (isValidPdfBlob(directBlob)) {
                        return directBlob;
                    }
                    console.warn('附录 PDF 直写失败：Blob 体积异常', { pages: pages.length, size: directBlob?.size || 0 });
                }
            } catch (error) {
                console.warn('附录 PDF 直写失败，回退 html2pdf 容器方案:', error);
            }

            // 最后兜底：html2pdf 渲染 Canvas 容器
            const exportContainer = document.createElement('div');
            exportContainer.style.cssText = 'position:absolute;left:0;top:0;width:794px;background:#ffffff;z-index:-1;pointer-events:none;';

            pages.forEach((canvas, index) => {
                const pageWrap = document.createElement('div');
                pageWrap.style.cssText = 'width:794px;height:1123px;background:#ffffff;overflow:hidden;';
                if (index < pages.length - 1) {
                    pageWrap.style.pageBreakAfter = 'always';
                    pageWrap.style.breakAfter = 'page';
                }

                const pageCanvas = document.createElement('canvas');
                pageCanvas.width = canvas.width;
                pageCanvas.height = canvas.height;
                const pageCtx = pageCanvas.getContext('2d');
                if (pageCtx) {
                    pageCtx.drawImage(canvas, 0, 0);
                }
                pageCanvas.style.cssText = 'display:block;width:794px;height:1123px;';
                pageWrap.appendChild(pageCanvas);
                exportContainer.appendChild(pageWrap);
            });

            document.body.appendChild(exportContainer);

            try {
                // 等待浏览器完成布局，避免某些环境下首次抓取到空白画布
                await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

                const worker = html2pdf().set({
                    margin: [0, 0, 0, 0],
                    filename: 'appendix.pdf',
                    image: { type: 'jpeg', quality: 0.96 },
                    html2canvas: {
                        scale: 2,
                        useCORS: true,
                        logging: false,
                        backgroundColor: '#ffffff',
                    },
                    jsPDF: {
                        unit: 'mm',
                        format: 'a4',
                        orientation: 'portrait'
                    },
                    pagebreak: { mode: ['css', 'legacy'] }
                }).from(exportContainer).toPdf();
                const pdf = await worker.get('pdf');
                if (!pdf) return null;
                const blob = pdf.output('blob');
                if (!isValidPdfBlob(blob)) {
                    console.warn('附录 PDF 导出异常：文件体积过小', { pages: pages.length, size: blob.size });
                    return null;
                }
                return blob;
            } catch (error) {
                console.error('附录 Canvas PDF 导出失败:', error);
                return null;
            } finally {
                if (exportContainer.parentNode) {
                    exportContainer.parentNode.removeChild(exportContainer);
                }
            }
        },

        buildAppendixPdfHtmlFromDom(reportElement) {
            if (!reportElement) return '';

            const appendixHeading = Array.from(reportElement.querySelectorAll('h2'))
                .find(heading => (heading.textContent || '').includes('附录：完整访谈记录'));
            if (!appendixHeading) return '';

            const wrapper = document.createElement('div');
            const headingClone = appendixHeading.cloneNode(true);
            const exportWrap = headingClone.querySelector('.dv-appendix-export-wrap');
            if (exportWrap) exportWrap.remove();
            wrapper.appendChild(headingClone);

            let cursor = appendixHeading.nextElementSibling;
            while (cursor) {
                if (cursor.tagName === 'H2') {
                    break;
                }
                wrapper.appendChild(cursor.cloneNode(true));
                cursor = cursor.nextElementSibling;
            }

            wrapper.querySelectorAll('.dv-appendix-export-wrap').forEach(node => node.remove());

            const detailsNodes = Array.from(wrapper.querySelectorAll('details'));
            detailsNodes.reverse().forEach(detail => {
                const fragment = document.createDocumentFragment();
                const summary = detail.querySelector(':scope > summary') || detail.querySelector('summary');
                const summaryText = (summary?.textContent || '').replace(/\s+/g, ' ').trim();

                if (summaryText) {
                    const titleNode = document.createElement(summaryText.startsWith('问题 ') ? 'h3' : 'p');
                    titleNode.textContent = summaryText;
                    if (titleNode.tagName === 'P') {
                        titleNode.style.fontWeight = '600';
                    }
                    fragment.appendChild(titleNode);
                }

                Array.from(detail.childNodes).forEach(child => {
                    if (summary && child === summary) return;
                    fragment.appendChild(child.cloneNode(true));
                });
                detail.replaceWith(fragment);
            });

            return wrapper.innerHTML.trim();
        },

        async buildAppendixPdfBlobFromDom(reportElement) {
            if (typeof html2pdf === 'undefined' || !reportElement) return null;

            const appendixHtml = this.buildAppendixPdfHtmlFromDom(reportElement);
            if (!appendixHtml) return null;

            const tempContainer = document.createElement('div');
            tempContainer.style.cssText = 'padding: 40px; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; line-height: 1.8; color: #1a1a1a; background: #ffffff; width: 794px; box-sizing: border-box;';

            const style = document.createElement('style');
            style.textContent = `
                h1 { font-size: 24px; font-weight: bold; margin: 24px 0 16px; color: #111; }
                h2 { font-size: 20px; font-weight: bold; margin: 20px 0 12px; color: #222; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }
                h3 { font-size: 16px; font-weight: bold; margin: 16px 0 8px; color: #333; }
                p { margin: 8px 0; }
                ul, ol { margin: 8px 0; padding-left: 24px; }
                li { margin: 4px 0; }
                code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
                pre { background: #f3f4f6; padding: 16px; border-radius: 8px; overflow-x: auto; }
                blockquote { border-left: 4px solid #3b82f6; padding-left: 16px; margin: 16px 0; color: #4b5563; }
                table { border-collapse: collapse; width: 100%; margin: 16px 0; }
                th, td { border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; }
                th { background: #f9fafb; font-weight: 600; }
            `;

            try {
                tempContainer.appendChild(style);
                tempContainer.insertAdjacentHTML('beforeend', appendixHtml);
                document.body.appendChild(tempContainer);

                await this.convertMermaidToImages(tempContainer);

                const worker = html2pdf().set({
                    margin: [15, 15, 15, 15],
                    filename: 'appendix.pdf',
                    image: { type: 'jpeg', quality: 0.98 },
                    html2canvas: {
                        scale: 2,
                        useCORS: true,
                        logging: false,
                        backgroundColor: '#ffffff',
                    },
                    jsPDF: {
                        unit: 'mm',
                        format: 'a4',
                        orientation: 'portrait'
                    },
                    pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
                }).from(tempContainer).toPdf();

                const pdf = await worker.get('pdf');
                if (!pdf) return null;
                const blob = pdf.output('blob');
                if (!(blob instanceof Blob) || blob.size < 1024) return null;
                return blob;
            } catch (error) {
                console.error('附录 DOM PDF 导出失败:', error);
                return null;
            } finally {
                if (tempContainer.parentNode) {
                    tempContainer.parentNode.removeChild(tempContainer);
                }
            }
        },

        getExportPickerMeta(format) {
            switch (format) {
                case 'pdf':
                    return {
                        description: 'PDF 文档',
                        mime: 'application/pdf',
                        extensions: ['.pdf'],
                    };
                case 'docx':
                    return {
                        description: 'Word 文档',
                        mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        extensions: ['.docx'],
                    };
                case 'md':
                default:
                    return {
                        description: 'Markdown 文件',
                        mime: 'text/markdown',
                        extensions: ['.md'],
                    };
            }
        },

        async openExportTarget(filenameWithExt, format) {
            if (typeof window === 'undefined' || typeof window.showSaveFilePicker !== 'function') {
                return { mode: 'fallback' };
            }

            const meta = this.getExportPickerMeta(format);
            try {
                const handle = await window.showSaveFilePicker({
                    suggestedName: filenameWithExt,
                    types: [{
                        description: meta.description,
                        accept: {
                            [meta.mime]: meta.extensions,
                        },
                    }],
                });
                return { mode: 'picker', handle };
            } catch (error) {
                if (error?.name === 'AbortError') {
                    return { mode: 'cancelled' };
                }
                throw error;
            }
        },

        async commitExportBlob(target, blob, filenameWithExt) {
            if (!blob) return false;
            if (target.mode === 'cancelled') return false;

            if (target.mode === 'picker' && target.handle) {
                const writable = await target.handle.createWritable();
                await writable.write(blob);
                await writable.close();
                return true;
            }

            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filenameWithExt;
            a.click();
            URL.revokeObjectURL(url);
            return true;
        },

        buildExportSuccessMessage(label, scope = 'report', archived = false) {
            const prefix = scope === 'appendix' ? `附录 ${label}` : label;
            return archived ? `${prefix}已下载，并已同步云端归档` : `${prefix}已下载`;
        },

        async archiveExportBlob(blob, filenameWithExt, options = {}) {
            const reportName = String(options.reportName || this.selectedReport || '').trim();
            if (!(blob instanceof Blob) || blob.size <= 0 || !reportName) {
                return { ok: false, skipped: true };
            }

            const scope = options.scope === 'appendix' ? 'appendix' : 'report';
            const format = String(options.format || '').trim().toLowerCase();
            if (!format) {
                return { ok: false, skipped: true };
            }

            const formData = new FormData();
            formData.append('file', blob, filenameWithExt);
            formData.append('scope', scope);
            formData.append('format', format);
            formData.append('source', 'web_export');

            try {
                const response = await fetch(
                    `${API_BASE}/reports/${encodeURIComponent(reportName)}/exports`,
                    {
                        method: 'POST',
                        credentials: 'same-origin',
                        body: formData,
                    }
                );
                if (!response.ok) {
                    let errorMessage = '';
                    try {
                        const payload = await response.json();
                        errorMessage = payload?.error || '';
                    } catch (_error) {
                        errorMessage = '';
                    }
                    if (response.status === 401) {
                        this.enterLoginState({
                            showToast: true,
                            toastMessage: '登录状态已失效，请重新登录',
                            toastType: 'warning'
                        });
                    }
                    console.warn('导出资产归档失败', {
                        status: response.status,
                        reportName,
                        scope,
                        format,
                        error: errorMessage
                    });
                    return { ok: false, status: response.status, error: errorMessage };
                }
                const payload = await response.json();
                return { ok: true, payload };
            } catch (error) {
                console.warn('导出资产归档请求失败', error);
                return { ok: false, error: error?.message || '请求失败' };
            }
        },

        async fetchAppendixPdfBlobFromServer() {
            if (!this.selectedReport) {
                return { ok: false, error: '未选中报告' };
            }

            try {
                const response = await fetch(
                    `/api/reports/${encodeURIComponent(this.selectedReport)}/appendix/pdf`,
                    {
                        method: 'GET',
                        credentials: 'same-origin',
                        headers: {
                            Accept: 'application/pdf',
                        },
                    }
                );
                if (!response.ok) {
                    let errorMessage = '';
                    try {
                        const payload = await response.json();
                        errorMessage = payload?.error || '';
                    } catch (_error) {
                        try {
                            errorMessage = (await response.text() || '').trim();
                        } catch (_ignore) {
                            errorMessage = '';
                        }
                    }
                    console.warn('服务端附录 PDF 导出失败', { status: response.status, error: errorMessage });
                    return {
                        ok: false,
                        status: response.status,
                        error: errorMessage || '服务端导出失败',
                    };
                }
                const blob = await response.blob();
                if (!(blob instanceof Blob) || blob.size < 1024) {
                    console.warn('服务端附录 PDF Blob 异常', { size: blob?.size || 0 });
                    return {
                        ok: false,
                        status: response.status,
                        error: `服务端返回文件异常（${blob?.size || 0} bytes）`,
                    };
                }
                return { ok: true, blob };
            } catch (error) {
                console.warn('服务端附录 PDF 导出失败，回退前端导出:', error);
                return {
                    ok: false,
                    error: `网络异常：${error?.message || '请求失败'}`,
                };
            }
        },

        // 下载 Markdown 格式
        async downloadMarkdown(filename, options = {}) {
            const scope = options.scope === 'appendix' ? 'appendix' : 'report';
            const exportContent = scope === 'appendix'
                ? this.getAppendixExportContent()
                : this.getReportExportContent();
            if (!exportContent) {
                this.showToast(scope === 'appendix' ? '附录内容为空，无法导出' : '报告内容为空，无法导出', 'error');
                return;
            }

            const target = await this.openExportTarget(`${filename}.md`, 'md');
            if (target.mode === 'cancelled') {
                return;
            }

            const blob = new Blob([exportContent], { type: 'text/markdown;charset=utf-8' });
            const saved = await this.commitExportBlob(target, blob, `${filename}.md`);
            if (saved) {
                const archiveResult = await this.archiveExportBlob(blob, `${filename}.md`, {
                    scope,
                    format: 'md',
                });
                this.showToast(this.buildExportSuccessMessage('Markdown 文件', scope, archiveResult.ok), 'success');
            }
        },

        // 下载 PDF 格式
        async downloadPDF(filename, options = {}) {
            const scope = options.scope === 'appendix' ? 'appendix' : 'report';

            const target = await this.openExportTarget(`${filename}.pdf`, 'pdf');
            if (target.mode === 'cancelled') {
                return;
            }

            this.showToast(scope === 'appendix' ? '正在生成附录 PDF（处理图表中）...' : '正在生成 PDF（处理图表中）...', 'info');

            try {
                if (scope === 'appendix') {
                    const exportResult = await this.fetchAppendixPdfBlobFromServer();
                    if (exportResult?.ok && exportResult.blob) {
                        const saved = await this.commitExportBlob(target, exportResult.blob, `${filename}.pdf`);
                        if (saved) {
                            const archiveResult = await this.archiveExportBlob(exportResult.blob, `${filename}.pdf`, {
                                scope,
                                format: 'pdf',
                            });
                            this.showToast(this.buildExportSuccessMessage('PDF 文件', scope, archiveResult.ok), 'success');
                        }
                        return;
                    }

                    const errorMsg = exportResult?.error || '服务端导出失败';
                    const statusPart = exportResult?.status ? `HTTP ${exportResult.status}` : '请求失败';
                    this.showToast(`附录 PDF 导出失败：${statusPart}，${errorMsg}`, 'error');
                    return;
                }

                if (typeof html2pdf === 'undefined') {
                    this.showToast('PDF 导出功能暂不可用', 'error');
                    return;
                }

                // 获取渲染后的报告内容
                const reportElement = document.querySelector('.markdown-body');
                if (!reportElement) {
                    this.showToast('无法获取报告内容', 'error');
                    return;
                }

                const tempContainer = document.createElement('div');
                tempContainer.style.cssText = 'padding: 40px; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; line-height: 1.8; color: #1a1a1a; background: #ffffff; width: 794px; box-sizing: border-box;';
                try {
                    tempContainer.innerHTML = reportElement.innerHTML;

                    // 报告导出时移除摘要、目录、附录（完整访谈记录）
                    const summaryBlock = tempContainer.querySelector('#report-summary-block');
                    if (summaryBlock) summaryBlock.remove();
                    const tocBlock = tempContainer.querySelector('#report-toc-block');
                    if (tocBlock) tocBlock.remove();
                    const appendixExportControl = tempContainer.querySelector('.dv-appendix-export-wrap');
                    if (appendixExportControl) appendixExportControl.remove();
                    const appendixHeading = Array.from(tempContainer.querySelectorAll('h2'))
                        .find(h => (h.textContent || '').includes('附录：完整访谈记录'));
                    if (appendixHeading) {
                        let node = appendixHeading;
                        while (node) {
                            const next = node.nextSibling;
                            node.remove();
                            node = next;
                        }
                    }

                    // 添加PDF专用样式
                    const style = document.createElement('style');
                    style.textContent = `
                        h1 { font-size: 24px; font-weight: bold; margin: 24px 0 16px; color: #111; }
                        h2 { font-size: 20px; font-weight: bold; margin: 20px 0 12px; color: #222; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }
                        h3 { font-size: 16px; font-weight: bold; margin: 16px 0 8px; color: #333; }
                        p { margin: 8px 0; }
                        ul, ol { margin: 8px 0; padding-left: 24px; }
                        li { margin: 4px 0; }
                        code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
                        pre { background: #f3f4f6; padding: 16px; border-radius: 8px; overflow-x: auto; }
                        blockquote { border-left: 4px solid #3b82f6; padding-left: 16px; margin: 16px 0; color: #4b5563; }
                        table { border-collapse: collapse; width: 100%; margin: 16px 0; }
                        th, td { border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; }
                        th { background: #f9fafb; font-weight: 600; }
                        .mermaid-container { page-break-inside: avoid !important; break-inside: avoid !important; margin: 16px 0; }
                        .mermaid-container img { max-width: 100%; height: auto; page-break-inside: avoid !important; break-inside: avoid !important; }
                        .mermaid-container svg { page-break-inside: avoid !important; break-inside: avoid !important; }
                    `;
                    tempContainer.prepend(style);
                    document.body.appendChild(tempContainer);

                    // 将 Mermaid SVG 转换为图片
                    await this.convertMermaidToImages(tempContainer);

                    const pdfOptions = {
                        margin: [15, 15, 15, 15],
                        filename: `${filename}.pdf`,
                        image: { type: 'jpeg', quality: 0.98 },
                        html2canvas: {
                            scale: 2,
                            useCORS: true,
                            logging: false
                        },
                        jsPDF: {
                            unit: 'mm',
                            format: 'a4',
                            orientation: 'portrait'
                        },
                        pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
                    };

                    const worker = html2pdf().set(pdfOptions).from(tempContainer).toPdf();
                    const pdf = await worker.get('pdf');
                    if (!pdf) {
                        throw new Error('pdf instance missing');
                    }
                    const blob = pdf.output('blob');
                    const saved = await this.commitExportBlob(target, blob, `${filename}.pdf`);
                    if (saved) {
                        const archiveResult = await this.archiveExportBlob(blob, `${filename}.pdf`, {
                            scope,
                            format: 'pdf',
                        });
                        this.showToast(this.buildExportSuccessMessage('PDF 文件', scope, archiveResult.ok), 'success');
                    }
                } finally {
                    if (tempContainer.parentNode) {
                        tempContainer.parentNode.removeChild(tempContainer);
                    }
                }
            } catch (error) {
                console.error('PDF 导出失败:', error);
                this.showToast(scope === 'appendix' ? '附录 PDF 导出失败，请重试' : 'PDF 导出失败，请重试', 'error');
            }
        },

        // 下载 Word 格式
        async downloadDocx(filename, options = {}) {
            const scope = options.scope === 'appendix' ? 'appendix' : 'report';
            if (typeof docx === 'undefined') {
                this.showToast('Word 导出功能暂不可用', 'error');
                return;
            }

            const target = await this.openExportTarget(`${filename}.docx`, 'docx');
            if (target.mode === 'cancelled') {
                return;
            }

            this.showToast(scope === 'appendix' ? '正在生成附录 Word 文档（处理图表中）...' : '正在生成 Word 文档（处理图表中）...', 'info');

            try {
                const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, BorderStyle, ImageRun } = docx;

                // 先收集所有 Mermaid 图表的图片数据
                const mermaidImages = await this.collectMermaidImages();

                // 解析 Markdown 内容为文档段落（报告导出为精简版，附录导出为完整记录）
                const exportContent = scope === 'appendix'
                    ? this.getAppendixExportContentForDocx()
                    : this.getReportExportContent();
                if (!exportContent) {
                    this.showToast(scope === 'appendix' ? '未找到附录内容，无法导出 Word' : '报告内容为空，无法导出 Word', 'error');
                    return;
                }
                const lines = exportContent.split('\n');
                const children = [];
                let inMermaidBlock = false;
                let mermaidIndex = 0;

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];

                    // 检测 Mermaid 代码块开始
                    if (line.trim().startsWith('```mermaid')) {
                        inMermaidBlock = true;
                        // 插入对应的图片
                        if (mermaidImages[mermaidIndex]) {
                            const imgData = mermaidImages[mermaidIndex];
                            try {
                                // 将 base64 转换为 ArrayBuffer
                                const base64Data = imgData.dataUrl.split(',')[1];
                                const binaryString = atob(base64Data);
                                const bytes = new Uint8Array(binaryString.length);
                                for (let j = 0; j < binaryString.length; j++) {
                                    bytes[j] = binaryString.charCodeAt(j);
                                }

                                // 计算适合文档的尺寸（最大宽度 600px）
                                const maxWidth = 600;
                                const scale = Math.min(1, maxWidth / imgData.width);
                                const displayWidth = Math.round(imgData.width * scale);
                                const displayHeight = Math.round(imgData.height * scale);

                                children.push(new Paragraph({
                                    children: [
                                        new ImageRun({
                                            data: bytes.buffer,
                                            transformation: {
                                                width: displayWidth,
                                                height: displayHeight
                                            },
                                            type: 'png'
                                        })
                                    ],
                                    spacing: { before: 240, after: 240 },
                                    alignment: AlignmentType.CENTER,
                                    keepLines: true,
                                    keepNext: true
                                }));
                            } catch (imgError) {
                                console.error('图片插入失败:', imgError);
                                children.push(new Paragraph({
                                    text: '[图表无法显示]',
                                    spacing: { before: 120, after: 120 }
                                }));
                            }
                            mermaidIndex++;
                        }
                        continue;
                    }

                    // 检测代码块结束
                    if (inMermaidBlock && line.trim() === '```') {
                        inMermaidBlock = false;
                        continue;
                    }

                    // 跳过 Mermaid 代码块内容
                    if (inMermaidBlock) {
                        continue;
                    }

                    // 跳过其他代码块（非 Mermaid）
                    if (line.trim().startsWith('```')) {
                        continue;
                    }

                    if (!line.trim()) {
                        children.push(new Paragraph({ text: '' }));
                        continue;
                    }

                    // 标题处理
                    if (line.startsWith('### ')) {
                        children.push(new Paragraph({
                            text: line.replace('### ', ''),
                            heading: HeadingLevel.HEADING_3,
                            spacing: { before: 240, after: 120 }
                        }));
                    } else if (line.startsWith('## ')) {
                        children.push(new Paragraph({
                            text: line.replace('## ', ''),
                            heading: HeadingLevel.HEADING_2,
                            spacing: { before: 360, after: 160 },
                            border: {
                                bottom: { color: '#3B82F6', size: 6, style: BorderStyle.SINGLE }
                            }
                        }));
                    } else if (line.startsWith('# ')) {
                        children.push(new Paragraph({
                            text: line.replace('# ', ''),
                            heading: HeadingLevel.HEADING_1,
                            spacing: { before: 480, after: 240 }
                        }));
                    }
                    // 列表处理
                    else if (line.match(/^[-*] /)) {
                        const text = line.replace(/^[-*] /, '');
                        children.push(new Paragraph({
                            text: `• ${this.stripMarkdownFormatting(text)}`,
                            spacing: { before: 60, after: 60 },
                            indent: { left: 360 }
                        }));
                    }
                    // 有序列表
                    else if (line.match(/^\d+\. /)) {
                        children.push(new Paragraph({
                            text: this.stripMarkdownFormatting(line),
                            spacing: { before: 60, after: 60 },
                            indent: { left: 360 }
                        }));
                    }
                    // 引用
                    else if (line.startsWith('> ')) {
                        children.push(new Paragraph({
                            children: [
                                new TextRun({
                                    text: line.replace('> ', ''),
                                    italics: true,
                                    color: '4B5563'
                                })
                            ],
                            spacing: { before: 120, after: 120 },
                            indent: { left: 480 },
                            border: {
                                left: { color: '#3B82F6', size: 12, style: BorderStyle.SINGLE }
                            }
                        }));
                    }
                    // 普通段落
                    else {
                        const textRuns = this.parseMarkdownInline(line);
                        children.push(new Paragraph({
                            children: textRuns,
                            spacing: { before: 80, after: 80 }
                        }));
                    }
                }

                const doc = new Document({
                    sections: [{
                        properties: {
                            page: {
                                margin: {
                                    top: 1440,
                                    right: 1440,
                                    bottom: 1440,
                                    left: 1440
                                }
                            }
                        },
                        children: children
                    }]
                });

                const blob = await Packer.toBlob(doc);
                const saved = await this.commitExportBlob(target, blob, `${filename}.docx`);
                if (saved) {
                    const archiveResult = await this.archiveExportBlob(blob, `${filename}.docx`, {
                        scope,
                        format: 'docx',
                    });
                    this.showToast(this.buildExportSuccessMessage('Word 文档', scope, archiveResult.ok), 'success');
                }
            } catch (error) {
                console.error('Word 导出失败:', error);
                this.showToast(scope === 'appendix' ? '附录 Word 导出失败，请重试' : 'Word 导出失败，请重试', 'error');
            }
        },

        // 收集所有已渲染的 Mermaid 图表并转换为图片数据
        async collectMermaidImages() {
            const images = [];
            const reportElement = document.querySelector('.markdown-body');
            if (!reportElement) return images;

            const mermaidContainers = reportElement.querySelectorAll('.mermaid-container');

            for (const container of mermaidContainers) {
                const svg = container.querySelector('svg');
                if (svg) {
                    try {
                        const imageData = await this.svgToImage(svg);
                        images.push(imageData);
                    } catch (error) {
                        console.error('Mermaid 图表收集失败:', error);
                        images.push(null);
                    }
                } else {
                    images.push(null);
                }
            }

            return images;
        },

        // 将 SVG 元素转换为 PNG Base64 图片
        async svgToImage(svgElement) {
            return new Promise((resolve, reject) => {
                try {
                    // 克隆 SVG 以避免修改原始元素
                    const clonedSvg = svgElement.cloneNode(true);

                    // 确保 SVG 有明确的尺寸
                    const bbox = svgElement.getBoundingClientRect();
                    const width = bbox.width || svgElement.getAttribute('width') || 800;
                    const height = bbox.height || svgElement.getAttribute('height') || 600;

                    clonedSvg.setAttribute('width', width);
                    clonedSvg.setAttribute('height', height);

                    // 添加白色背景
                    const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    bgRect.setAttribute('width', '100%');
                    bgRect.setAttribute('height', '100%');
                    bgRect.setAttribute('fill', 'white');
                    clonedSvg.insertBefore(bgRect, clonedSvg.firstChild);

                    // 序列化 SVG
                    const svgData = new XMLSerializer().serializeToString(clonedSvg);
                    const svgBase64 = btoa(unescape(encodeURIComponent(svgData)));
                    const svgUrl = 'data:image/svg+xml;base64,' + svgBase64;

                    // 创建 Canvas 并绘制
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    const img = new Image();

                    img.onload = () => {
                        canvas.width = width * 2;  // 2x 分辨率
                        canvas.height = height * 2;
                        ctx.scale(2, 2);
                        ctx.fillStyle = 'white';
                        ctx.fillRect(0, 0, width, height);
                        ctx.drawImage(img, 0, 0, width, height);

                        resolve({
                            dataUrl: canvas.toDataURL('image/png'),
                            width: width,
                            height: height
                        });
                    };

                    img.onerror = (e) => {
                        console.error('SVG 转图片失败:', e);
                        reject(e);
                    };

                    img.src = svgUrl;
                } catch (error) {
                    console.error('SVG 处理失败:', error);
                    reject(error);
                }
            });
        },

        // 将所有 Mermaid 图表转换为图片（用于导出）
        async convertMermaidToImages(container) {
            const mermaidContainers = container.querySelectorAll('.mermaid-container');
            const conversions = [];

            for (const mermaidContainer of mermaidContainers) {
                const svg = mermaidContainer.querySelector('svg');
                if (svg) {
                    try {
                        const imageData = await this.svgToImage(svg);

                        // 创建图片元素替换 SVG
                        const img = document.createElement('img');
                        img.src = imageData.dataUrl;
                        img.style.cssText = `max-width: 100%; height: auto; display: block; margin: 16px auto;`;
                        img.alt = 'Mermaid 图表';

                        // 清空容器并插入图片
                        mermaidContainer.innerHTML = '';
                        mermaidContainer.appendChild(img);

                        conversions.push({ success: true });
                    } catch (error) {
                        console.error('Mermaid 图表转换失败:', error);
                        conversions.push({ success: false, error });
                    }
                }
            }

            return conversions;
        },

        // 去除 Markdown 格式标记
        stripMarkdownFormatting(text) {
            return text
                .replace(/\*\*(.*?)\*\*/g, '$1')
                .replace(/\*(.*?)\*/g, '$1')
                .replace(/`(.*?)`/g, '$1')
                .replace(/\[(.*?)\]\(.*?\)/g, '$1');
        },

        // 解析行内 Markdown 格式
        parseMarkdownInline(text) {
            if (typeof docx === 'undefined') return [];

            const { TextRun } = docx;
            const runs = [];
            let remaining = text;

            // 简化处理：直接返回去格式化的文本
            // 复杂的格式解析可能导致错误
            runs.push(new TextRun({
                text: this.stripMarkdownFormatting(remaining),
                size: 22
            }));

            return runs;
        },

        isSafeUrl(url) {
            const raw = String(url || '').trim();
            if (!raw) return false;
            const compact = raw.replace(/[\u0000-\u001F\u007F\s]+/g, '');
            if (!compact) return false;
            if (compact.startsWith('#') || compact.startsWith('/')) return true;
            return /^(https?:|mailto:)/i.test(compact);
        },

        sanitizeMarkdownHtml(rawHtml) {
            const input = String(rawHtml || '');
            if (!input) return '';

            if (typeof DOMParser === 'undefined' || typeof document === 'undefined') {
                return input
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
            }

            const parser = new DOMParser();
            const doc = parser.parseFromString(`<div id="md-root">${input}</div>`, 'text/html');
            const root = doc.getElementById('md-root');
            if (!root) return '';

            const allowedTags = new Set([
                'a', 'p', 'br', 'hr', 'strong', 'em', 'code', 'pre', 'blockquote',
                'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'table', 'thead', 'tbody', 'tr', 'th', 'td',
                'div', 'span', 'img', 'details', 'summary'
            ]);
            const allowedAttrs = {
                a: new Set(['href', 'title', 'target', 'rel']),
                img: new Set(['src', 'alt', 'title']),
                code: new Set(['class']),
                pre: new Set(['class', 'id']),
                div: new Set(['class']),
                span: new Set(['class']),
                details: new Set(['open']),
                th: new Set(['colspan', 'rowspan', 'align']),
                td: new Set(['colspan', 'rowspan', 'align'])
            };
            const classAllowPattern = /^[a-zA-Z0-9_-]{1,64}$/;
            const nodes = Array.from(root.querySelectorAll('*'));

            for (const node of nodes) {
                const tag = node.tagName.toLowerCase();
                if (!allowedTags.has(tag)) {
                    const textNode = doc.createTextNode(node.textContent || '');
                    node.replaceWith(textNode);
                    continue;
                }

                const attrs = Array.from(node.attributes);
                for (const attr of attrs) {
                    const attrName = attr.name.toLowerCase();
                    const attrValue = String(attr.value || '');
                    if (attrName.startsWith('on')) {
                        node.removeAttribute(attr.name);
                        continue;
                    }

                    const tagAllowedAttrs = allowedAttrs[tag] || new Set();
                    if (!tagAllowedAttrs.has(attrName)) {
                        node.removeAttribute(attr.name);
                        continue;
                    }

                    if ((attrName === 'href' || attrName === 'src') && !this.isSafeUrl(attrValue)) {
                        node.removeAttribute(attr.name);
                        continue;
                    }

                    if (attrName === 'class') {
                        const safeClasses = attrValue
                            .split(/\s+/)
                            .filter(token => classAllowPattern.test(token));
                        if (safeClasses.length === 0) {
                            node.removeAttribute(attr.name);
                            continue;
                        }
                        node.setAttribute('class', safeClasses.join(' '));
                    }
                }

                if (tag === 'a' && node.getAttribute('href')) {
                    node.setAttribute('rel', 'noopener noreferrer');
                    const target = node.getAttribute('target');
                    if (target && target !== '_blank') {
                        node.removeAttribute('target');
                    }
                }
            }

            return root.innerHTML;
        },

        renderMarkdown(content) {
            if (!content) return '';
            const sanitizedContent = this.stripInlineEvidenceMarkers(
                String(content)
                .replace(/^\s*\*\*生成方式\*\*:[^\n]*\n?/gm, '')
            );
            const normalizedContent = this.normalizeLegacyAppendixAnswerLayout(
                this.normalizeAppendixSummaryText(sanitizedContent)
            );

            if (typeof marked !== 'undefined') {
                // 使用 marked 渲染 Markdown
                let html = marked.parse(normalizedContent);

                // 检测并转换 Mermaid 代码块
                // 匹配 <pre><code class="language-mermaid">...</code></pre>
                html = html.replace(
                    /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g,
                    (match, mermaidCode) => {
                        // 生成唯一 ID
                        const id = 'mermaid-' + Math.random().toString(36).substr(2, 9);
                        // 解码 HTML 实体
                        const decodedCode = mermaidCode
                            .replace(/&lt;/g, '<')
                            .replace(/&gt;/g, '>')
                            .replace(/&amp;/g, '&')
                            .replace(/&quot;/g, '"')
                            .trim();

                        // 返回 Mermaid 容器
                        return `<div class="mermaid-container">
                            <pre class="mermaid" id="${id}">${decodedCode}</pre>
                        </div>`;
                    }
                );

                // 注意：不在这里调用 renderMermaidCharts()
                // 因为在 x-html 绑定中，DOM 可能还没更新
                // 应该在 viewReport() 中调用

                return this.sanitizeMarkdownHtml(html);
            }

            // 简单的 Markdown 渲染（无 marked.js 时的回退）
            const fallbackHtml = normalizedContent
                .replace(/^### (.*$)/gm, '<h3>$1</h3>')
                .replace(/^## (.*$)/gm, '<h2>$1</h2>')
                .replace(/^# (.*$)/gm, '<h1>$1</h1>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/^- (.*$)/gm, '<li>$1</li>')
                .replace(/\n/g, '<br>');
            return this.sanitizeMarkdownHtml(fallbackHtml);
        },

        normalizeLegacyAppendixAnswerLayout(markdownText) {
            const source = String(markdownText || '');
            if (!source) return '';

            return source.replace(
                /\*\*回答\*\*：\s*\n((?:[ \t]*[☐☑].*(?:\n|$))+)/g,
                (match, linesBlock) => {
                    const lines = String(linesBlock || '')
                        .split('\n')
                        .map(line => line.trim())
                        .filter(Boolean);
                    if (lines.length === 0) return match;
                    const htmlLines = lines.map(line => `<div>${line}</div>`).join('\n');
                    return `<div><strong>回答：</strong></div>\n${htmlLines}\n`;
                }
            );
        },

        // 渲染页面中的所有 Mermaid 图表
        async renderMermaidCharts() {
            if (typeof mermaid === 'undefined') {
                console.warn('⚠️ Mermaid 库未加载');
                return;
            }

            try {
                // 查找所有 .mermaid 元素
                const mermaidElements = document.querySelectorAll('.mermaid');

                if (mermaidElements.length === 0) {
                    return;
                }

                const isDarkTheme = this.effectiveTheme === 'dark';
                const chartBackground = isDarkTheme ? '#1f252d' : '#ffffff';

                // 逐个渲染图表
                let successCount = 0;
                for (let i = 0; i < mermaidElements.length; i++) {
                    const element = mermaidElements[i];

                    // 跳过已经渲染为 SVG 的元素
                    if (element.querySelector('svg')) {
                        continue;
                    }

                    try {
                        const graphDefinition = (element.dataset.mermaidDefinition || element.textContent || '').trim();
                        if (!graphDefinition) continue;
                        element.dataset.mermaidDefinition = graphDefinition;
                        const id = `mermaid-${Date.now()}-${i}`;

                        // 预处理：修复常见的语法问题
                        let fixedDefinition = graphDefinition;

                        // 修复1：检测 quadrantChart 的中文（quadrantChart 对中文支持不好，需要转换）
                        if (fixedDefinition.includes('quadrantChart')) {
                            // 替换所有包含冒号的 quadrant 标签（移除冒号后的部分）
                            fixedDefinition = fixedDefinition
                                .replace(/quadrant-1\s+[^:\n]*:\s*[^\n]*/g, 'quadrant-1 P1 High Priority')
                                .replace(/quadrant-2\s+[^:\n]*:\s*[^\n]*/g, 'quadrant-2 P2 Plan')
                                .replace(/quadrant-3\s+[^:\n]*:\s*[^\n]*/g, 'quadrant-3 P3 Later')
                                .replace(/quadrant-4\s+[^:\n]*:\s*[^\n]*/g, 'quadrant-4 Low Priority');

                            // 如果没有冒号，则直接替换包含中文的标签
                            fixedDefinition = fixedDefinition
                                .replace(/quadrant-1\s+[^\n]*[\u4e00-\u9fa5]+[^\n]*/g, 'quadrant-1 P1 High Priority')
                                .replace(/quadrant-2\s+[^\n]*[\u4e00-\u9fa5]+[^\n]*/g, 'quadrant-2 P2 Plan')
                                .replace(/quadrant-3\s+[^\n]*[\u4e00-\u9fa5]+[^\n]*/g, 'quadrant-3 P3 Later')
                                .replace(/quadrant-4\s+[^\n]*[\u4e00-\u9fa5]+[^\n]*/g, 'quadrant-4 Low Priority');

                            // 替换标题中的中文
                            fixedDefinition = fixedDefinition
                                .replace(/title\s+[^\n]*[\u4e00-\u9fa5]+[^\n]*/g, 'title Priority Matrix')
                                .replace(/x-axis\s+[^\n]*[\u4e00-\u9fa5]+[^\n]*/g, 'x-axis Low --> High')
                                .replace(/y-axis\s+[^\n]*[\u4e00-\u9fa5]+[^\n]*/g, 'y-axis Low --> High');

                            // 替换中文数据点名称为英文（Req1, Req2, ...）
                            let reqIndex = 1;
                            // 匹配任何包含中文的数据点名称（带或不带空格）
                            fixedDefinition = fixedDefinition.replace(
                                /^\s*([^\n:]*[\u4e00-\u9fa5]+[^\n:]*?):\s*\[/gm,
                                (match, chineseName) => {
                                    const englishName = `Req${reqIndex++}`;
                                    return `    ${englishName}: [`;
                                }
                            );

                            // 确保至少有一个数据点
                            if (!/\w+:\s*\[\s*[\d.]+\s*,\s*[\d.]+\s*\]/.test(fixedDefinition)) {
                                fixedDefinition += '\n    Sample: [0.5, 0.5]';
                            }
                        }

                        // 修复2：检测 flowchart/graph 中的语法问题（保留中文显示）
                        if (fixedDefinition.match(/^(graph|flowchart)\s/m)) {
                            // 修复 HTML 标签（如 <br>）为换行符
                            fixedDefinition = fixedDefinition.replace(/<br\s*\/?>/gi, ' ');

                            // 检查是否有未闭合的 subgraph（缺少 end）
                            const subgraphCount = (fixedDefinition.match(/subgraph\s/g) || []).length;
                            const endCount = (fixedDefinition.match(/\bend\b/g) || []).length;
                            if (subgraphCount > endCount) {
                                for (let j = 0; j < subgraphCount - endCount; j++) {
                                    fixedDefinition += '\n    end';
                                }
                            }

                            // 修复节点标签中的特殊字符（可能导致解析失败）
                            // 1. 替换节点标签中的半角冒号为短横线（但保留 subgraph 标识中的冒号）
                            fixedDefinition = fixedDefinition.replace(
                                /(\w+)\[([^\]]*):([^\]]*)\]/g,
                                (match, id, before, after) => `${id}[${before}-${after}]`
                            );

                            // 2. 替换节点标签中的半角引号
                            fixedDefinition = fixedDefinition.replace(
                                /(\w+)\[([^\]]*)"([^\]]*)\]/g,
                                (match, id, before, after) => `${id}[${before}${after}]`
                            );

                            // 3. 修复连接线上标签中的特殊字符
                            fixedDefinition = fixedDefinition.replace(
                                /-->\|([^|]*):([^|]*)\|/g,
                                (match, before, after) => `-->|${before}-${after}|`
                            );

                            // 4. 修复连接定义中使用 --- 的情况（改为 --）
                            // 处理 P1 --- P1D["..."] 格式，改为 P1 --> P1D["..."]
                            fixedDefinition = fixedDefinition.replace(
                                /(\w+)\s+---\s+(\w+)\[/g,
                                (match, from, to) => `${from} --> ${to}[`
                            );
                        }

                        // 使用 mermaid.render() 生成 SVG
                        const { svg } = await mermaid.render(id, fixedDefinition);

                        // 替换元素内容为渲染后的 SVG
                        element.innerHTML = svg;
                        element.classList.add('mermaid-rendered');

                        // 后处理：统一图表画布底色，避免在深浅主题切换时出现黑块
                        const svgEl = element.querySelector('svg');
                        if (svgEl) {
                            svgEl.style.backgroundColor = chartBackground;
                            svgEl.style.background = chartBackground;

                            const firstRect = svgEl.querySelector('rect');
                            if (firstRect) {
                                const fill = (firstRect.getAttribute('fill') || '').toLowerCase();
                                if (!fill || fill === 'none' || fill === '#000000' || fill === 'black' || fill === 'rgb(0, 0, 0)') {
                                    firstRect.setAttribute('fill', chartBackground);
                                    firstRect.style.fill = chartBackground;
                                }
                            }

                            if (!isDarkTheme) {
                                const rects = svgEl.querySelectorAll('rect');
                                rects.forEach((rect, idx) => {
                                    const fill = (rect.getAttribute('fill') || rect.style.fill || '').toLowerCase();
                                    if (idx === 0 || fill === '#000000' || fill === 'black' || fill === 'rgb(0, 0, 0)') {
                                        rect.setAttribute('fill', '#ffffff');
                                        rect.style.fill = '#ffffff';
                                    }
                                });

                                const styles = svgEl.querySelectorAll('style');
                                styles.forEach(style => {
                                    style.textContent = style.textContent.replace(/background:\s*#000000/g, 'background: #ffffff');
                                    style.textContent = style.textContent.replace(/background-color:\s*#000000/g, 'background-color: #ffffff');
                                });
                            }
                        }

                        successCount++;
                    } catch (error) {
                        console.error(`  ❌ 图表 ${i + 1} 渲染失败:`, error);
                        // 清空所有内容（包括 Mermaid 可能残留的错误 SVG）
                        element.innerHTML = '';
                        // 同时清除父容器中可能残留的 SVG
                        const parent = element.closest('.mermaid-container');
                        if (parent) {
                            const orphanSvgs = parent.querySelectorAll('svg');
                            orphanSvgs.forEach(svg => svg.remove());
                        }
                        // 清除页面中 Mermaid 可能创建的临时元素
                        document.querySelectorAll('svg[id^="dmermaid"], #dmermaid').forEach(el => el.remove());
                        // 显示友好的错误提示
                        element.innerHTML = `<div class="mermaid-error">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                <svg width="20" height="20" fill="none" stroke="#6c757d" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                                </svg>
                                <span style="font-weight: 500;">图表暂无法显示</span>
                            </div>
                            <p style="font-size: 13px; margin: 0; color: #6c757d;">该图表语法需要调整，请参阅报告原文查看数据</p>
                        </div>`;
                        // 移除可能的黑色边框样式
                        element.style.border = 'none';
                        element.style.outline = 'none';
                        element.classList.remove('mermaid');
                        element.classList.add('mermaid-failed');
                    }
                }
            } catch (error) {
                console.error('❌ Mermaid 渲染过程失败:', error);
            }
        },

        // ============ 工具方法 ============
        switchView(view) {
            if (!this.authReady) return;
            if (view === 'admin' && !this.canViewAdminCenter()) return;
            if (view !== 'sessions') {
                this.stopSessionsAutoRefresh();
            }
            if (view !== 'interview') {
                this.sessionOpenRequestId += 1;
                this.clearInterviewLoadingState();
            }
            this.currentView = view;
            this.resetSelectedReportDetail();
            this.exitSessionBatchMode();
            this.exitReportBatchMode();
            if (view === 'sessions') {
                this.resetReportGenerationFeedback();
                this.refreshSessionsView();
            } else if (view === 'reports') {
                this.refreshReportsView();
            } else if (view === 'admin') {
                void this.ensureAdminDataForTab(this.adminTab || 'overview');
            }
            this.scheduleAppShellSnapshotPersist();
        },

        exitInterview() {
            if (!this.authReady) return;
            // 清理所有定时器，防止内存泄漏
            this.sessionOpenRequestId += 1;
            this.questionRequestId += 1;
            this.abortQuestionRequest();
            this.stopQuestionRequestGuard();
            this.stopThinkingPolling();
            this.stopWebSearchPolling();
            this.clearInterviewLoadingState();
            this.resetReportGenerationFeedback();
            this.submitting = false;

            this.currentView = 'sessions';
            this.currentSession = null;
            this.refreshSessionsView();
        },

        getTotalProgress() {
            if (!this.currentSession) return 0;
            const dims = Object.values(this.currentSession.dimensions);
            if (dims.length === 0) return 0;  // 防止除以零
            const total = dims.reduce((sum, d) => sum + (d.coverage || 0), 0);
            return Math.round(total / dims.length);
        },

        // 获取访谈模式配置
        getInterviewModeConfig() {
            if (!this.currentSession) return null;
            const modeConfigs = this.interviewDepthV2?.mode_configs;
            const modes = modeConfigs ? {
                quick: {
                    formal: modeConfigs.quick?.formal_questions_per_dim ?? 2,
                    formalMax: modeConfigs.quick?.max_formal_questions_per_dim ?? 3,
                    followUp: modeConfigs.quick?.follow_up_budget_per_dim ?? 3,
                    total: modeConfigs.quick?.total_follow_up_budget ?? 10,
                    range: modeConfigs.quick?.estimated_questions ?? "14-20"
                },
                standard: {
                    formal: modeConfigs.standard?.formal_questions_per_dim ?? 3,
                    formalMax: modeConfigs.standard?.max_formal_questions_per_dim ?? 4,
                    followUp: modeConfigs.standard?.follow_up_budget_per_dim ?? 5,
                    total: modeConfigs.standard?.total_follow_up_budget ?? 18,
                    range: modeConfigs.standard?.estimated_questions ?? "24-34"
                },
                deep: {
                    formal: modeConfigs.deep?.formal_questions_per_dim ?? 4,
                    formalMax: modeConfigs.deep?.max_formal_questions_per_dim ?? 6,
                    followUp: modeConfigs.deep?.follow_up_budget_per_dim ?? 8,
                    total: modeConfigs.deep?.total_follow_up_budget ?? 30,
                    range: modeConfigs.deep?.estimated_questions ?? "34-52"
                }
            } : {
                quick: { formal: 2, formalMax: 3, followUp: 3, total: 10, range: "14-20" },
                standard: { formal: 3, formalMax: 4, followUp: 5, total: 18, range: "24-34" },
                deep: { formal: 4, formalMax: 6, followUp: 8, total: 30, range: "34-52" }
            };
            const mode = this.currentSession.interview_mode || 'standard';
            return modes[mode] || modes.standard;
        },

        // 获取当前问题总数
        getCurrentQuestionCount() {
            if (!this.currentSession) return 0;
            return this.currentSession.interview_log.length;
        },

        getCurrentFormalQuestionCount() {
            if (!this.currentSession) return 0;
            return (this.currentSession.interview_log || []).filter(log => !log?.is_follow_up).length;
        },

        getCurrentSessionDimensionCount() {
            if (!this.currentSession) return 0;
            return this.getSessionDimKeys(this.currentSession).length;
        },

        getEstimatedQuestionBounds() {
            const config = this.getInterviewModeConfig();
            const dimensionCount = Math.max(1, this.getCurrentSessionDimensionCount() || this.dimensionOrder.length || 4);
            if (!config) {
                return { min: 24, max: 24, expected: 24 };
            }

            const formalMin = Math.max(1, Number(config.formal || 0));
            const formalMax = Math.max(formalMin, Number(config.formalMax || formalMin));
            const perDimFollowUp = Math.max(0, Number(config.followUp || 0));
            const totalFollowUp = Math.max(0, Number(config.total || 0));
            const followUpCap = Math.min(totalFollowUp, perDimFollowUp * dimensionCount);

            const min = formalMin * dimensionCount;
            const max = formalMax * dimensionCount + followUpCap;
            const expected = Math.round((min + max) / 2);
            return { min, max, expected };
        },

        // 获取预估总问题数（中间值）
        getEstimatedTotalQuestions() {
            return this.getEstimatedQuestionBounds().expected;
        },

        // 获取预估剩余问题数
        getEstimatedRemainingQuestions() {
            if (!this.currentSession) return 0;

            if (this.getTotalProgress() >= 100) {
                return 0;
            }

            const answered = this.getCurrentQuestionCount();
            const bounds = this.getEstimatedQuestionBounds();
            const remainingMin = Math.max(0, bounds.min - answered);
            const remainingMax = Math.max(0, bounds.max - answered);
            const remaining = Math.round((remainingMin + remainingMax) / 2);
            return remaining > 50 ? '50+' : remaining;
        },

        // 获取进度反馈信息
        getProgressFeedback() {
            if (!this.currentSession) return null;

            // 在确认阶段（currentStep >= 2）不显示进度提示
            if (this.currentStep >= 2) return null;

            const progress = this.getTotalProgress();

            // 所有维度都已完成时不显示进度提示
            if (progress >= 100) return null;

            const remaining = this.getEstimatedRemainingQuestions();

            // 安全访问当前维度，防止维度不存在
            const currentDim = this.currentSession.dimensions[this.currentDimension];
            if (!currentDim) return null;

            const dimProgress = currentDim.coverage;

            if (progress >= 75) {
                return { type: 'success', message: '快完成了！还剩最后几个问题' };
            } else if (dimProgress >= 75) {
                return { type: 'info', message: `${this.getDimensionName(this.currentDimension)}维度即将完成` };
            } else if (progress >= 50) {
                return { type: 'info', message: '已完成一半，继续加油' };
            } else if (progress >= 25) {
                return { type: 'info', message: '进展顺利' };
            }
            return null;
        },

        getDimensionName(key) {
            return this.dimensionNames[key] || key;
        },

        getCollectedAnswerText(log) {
            const answerText = String(log?.answer || '').trim();
            if (!log || typeof log !== 'object') {
                return answerText;
            }

            if (!Boolean(log.other_selected)) {
                return answerText;
            }

            const options = Array.isArray(log.options)
                ? log.options.map(item => String(item || '').trim()).filter(Boolean)
                : [];
            const otherInput = String(log.other_answer_text || '').trim();
            const otherResolution = this.getLogOtherResolution(log, options);

            if (otherResolution) {
                const selectedOptions = this.getLogSelectedOptions(log, options, otherResolution);
                if (otherResolution.mode === 'reference') {
                    return selectedOptions.join('；') || answerText || otherResolution.sourceText;
                }

                if (otherResolution.mode === 'mixed') {
                    const details = [];
                    if (selectedOptions.length > 0) {
                        details.push(`已选：${selectedOptions.join('；')}`);
                    }
                    if (otherResolution.customText) {
                        details.push(`补充说明：${otherResolution.customText}`);
                    }
                    return details.join(' | ') || answerText || otherResolution.sourceText;
                }
            }

            const details = [];
            if (options.length > 0) {
                const numberedOptions = options
                    .map((opt, idx) => `${idx + 1}.${opt}`)
                    .join('；');
                details.push(`全部选项：${numberedOptions}`);
            }
            if (otherInput) {
                details.push(`自由输入：${otherInput}`);
            }

            if (details.length === 0) {
                return answerText;
            }
            return details.join(' | ');
        },

        // 获取指定会话的维度 key 列表
        getSessionDimKeys(session) {
            if (session?.scenario_config?.dimensions) {
                return session.scenario_config.dimensions.map(d => d.id);
            }
            return Object.keys(session?.dimensions || {});
        },

        // 获取指定会话中某个维度的名称
        getSessionDimName(session, key) {
            if (session?.scenario_config?.dimensions) {
                const dim = session.scenario_config.dimensions.find(d => d.id === key);
                if (dim) return dim.name;
            }
            return this.dimensionNames[key] || key;
        },

        // 安全获取会话维度的覆盖度
        getSessionDimCoverage(session, key) {
            return session?.dimensions?.[key]?.coverage ?? 0;
        },

        // 计算会话的总进度（所有维度覆盖度的平均值）
        getSessionTotalProgress(session) {
            const dimKeys = this.getSessionDimKeys(session);
            if (!dimKeys || dimKeys.length === 0) return 0;

            let total = 0;
            for (const key of dimKeys) {
                total += this.getSessionDimCoverage(session, key);
            }
            return Math.round(total / dimKeys.length);
        },

        // 判断当前会话是否为评估场景
        isAssessmentSession() {
            return this.currentSession?.scenario_config?.report?.type === 'assessment';
        },

        isPresentationEnabled() {
            return this.presentationFeatureEnabled !== false;
        },

        // 获取维度评分（评估场景）
        getDimensionScore(dimKey) {
            const score = this.currentSession?.dimensions?.[dimKey]?.score;
            return score !== null && score !== undefined ? score.toFixed(1) : '-';
        },

        // 获取综合评分（评估场景）
        getTotalScore() {
            if (!this.isAssessmentSession()) return 0;
            const dims = this.currentSession?.scenario_config?.dimensions || [];
            const sessionDims = this.currentSession?.dimensions || {};
            let totalScore = 0;
            let totalWeight = 0;
            for (const dim of dims) {
                const score = sessionDims[dim.id]?.score;
                if (score !== null && score !== undefined) {
                    totalScore += score * (dim.weight || 0.25);
                    totalWeight += (dim.weight || 0.25);
                }
            }
            return totalWeight > 0 ? (totalScore / totalWeight).toFixed(2) : '0.00';
        },

        // 获取推荐等级（评估场景）
        getRecommendationLevel() {
            if (!this.isAssessmentSession()) return null;
            const score = parseFloat(this.getTotalScore());
            const levels = this.currentSession?.scenario_config?.assessment?.recommendation_levels || [];
            for (const level of [...levels].sort((a, b) => (b.threshold || 0) - (a.threshold || 0))) {
                if (score >= (level.threshold || 0)) {
                    return level;
                }
            }
            return levels[levels.length - 1] || null;
        },

        // 从会话配置更新维度信息
        updateDimensionsFromSession(session) {
            if (session?.scenario_config?.dimensions) {
                this.dimensionOrder = session.scenario_config.dimensions.map(d => d.id);
                const names = {};
                session.scenario_config.dimensions.forEach(d => {
                    names[d.id] = d.name;
                });
                this.dimensionNames = names;
            }
        },

        // 加载场景列表
        async loadScenarios() {
            try {
                this.scenarios = await this.apiCall('/scenarios');
                this.scenarioLoaded = true;
            } catch (error) {
                console.warn('加载场景列表失败:', error);
                this.scenarios = [];
            }
        },

        // 选择场景
        selectScenario(scenario) {
            this.scenarioRecognizeRequestId += 1;
            if (this.selectedScenario?.id === scenario.id) {
                this.selectedScenario = null;  // 取消选择
            } else {
                this.selectedScenario = scenario;
            }
            // 手动选择时禁用自动识别覆盖
            if (scenario) {
                this.autoRecognizeEnabled = false;
            }
        },

        // 获取当前场景的主题提示文案
        getTopicPlaceholder() {
            const scenarioId = this.selectedScenario?.id;
            if (scenarioId && this.scenarioPlaceholders[scenarioId]) {
                return this.scenarioPlaceholders[scenarioId].topic;
            }
            // 自定义场景：根据场景名称生成提示
            if (this.selectedScenario?.custom && this.selectedScenario?.name) {
                return `例如：${this.selectedScenario.name}相关的访谈主题`;
            }
            return this.scenarioPlaceholders['default'].topic;
        },

        // 获取当前场景的描述提示文案
        getDescriptionPlaceholder() {
            const scenarioId = this.selectedScenario?.id;
            if (scenarioId && this.scenarioPlaceholders[scenarioId]) {
                return this.scenarioPlaceholders[scenarioId].description;
            }
            // 自定义场景：根据场景描述生成提示
            if (this.selectedScenario?.custom) {
                const dims = this.selectedScenario.dimensions?.map(d => d.name).join('、') || '';
                if (dims) {
                    return `例如：请描述您的具体情况，包括${dims}等方面的背景信息，帮助AI生成更精准的访谈问题。`;
                }
                return `例如：请描述本次「${this.selectedScenario.name || '访谈'}」的背景、目标和关注重点。`;
            }
            return this.scenarioPlaceholders['default'].description;
        },

        getScenarioRecognizeFingerprint(topic = '', description = '') {
            return `${String(topic || '').trim()}\n${String(description || '').trim()}`;
        },

        // 场景自动识别（防抖触发）
        onTopicInput() {
            // 清除之前的定时器
            if (this.recognizeTimer) {
                clearTimeout(this.recognizeTimer);
            }

            const topic = this.newSessionTopic.trim();

            // 主题少于 2 个字符时不触发识别
            if (topic.length < 2) {
                this.scenarioRecognizeRequestId += 1;
                this.activeRecognizeFingerprint = '';
                this.recognizedResult = null;
                return;
            }

            // 如果用户已手动选择场景，不自动覆盖
            if (!this.autoRecognizeEnabled && this.selectedScenario) {
                return;
            }

            // 800ms 防抖（AI 识别需要更长的输入稳定期）
            this.recognizeTimer = setTimeout(() => {
                this.recognizeScenario(topic);
            }, 800);
        },

        // 调用场景识别 API
        async recognizeScenario(topic) {
            if (!topic || topic.length < 2) return;

            const description = this.newSessionDescription.trim() || '';
            const requestId = ++this.scenarioRecognizeRequestId;
            const requestFingerprint = this.getScenarioRecognizeFingerprint(topic, description);
            this.activeRecognizeFingerprint = requestFingerprint;
            this.recognizing = true;
            try {
                const result = await this.apiCall('/scenarios/recognize', {
                    method: 'POST',
                    body: JSON.stringify({
                        topic,
                        description
                    })
                });

                const latestFingerprint = this.getScenarioRecognizeFingerprint(
                    this.newSessionTopic.trim(),
                    this.newSessionDescription.trim() || ''
                );
                if (
                    requestId !== this.scenarioRecognizeRequestId
                    || requestFingerprint !== this.activeRecognizeFingerprint
                    || requestFingerprint !== latestFingerprint
                ) {
                    return;
                }

                this.recognizedResult = result;

                // 如果置信度高于 0.5 且用户未手动选择，自动选中推荐场景
                if (result.confidence >= 0.5 && this.autoRecognizeEnabled) {
                    // 确保 scenarios 已加载
                    if (!this.scenarios || this.scenarios.length === 0) {
                        console.warn('场景列表未加载，等待加载后重试');
                        await this.loadScenarios();
                    }

                    const recommendedId = result.recommended?.id;
                    if (recommendedId) {
                        let recommendedScenario = this.scenarios.find(s => s.id === recommendedId);

                        // 如果精确匹配失败，尝试名称匹配（兼容 AI 可能返回不同格式的 ID）
                        if (!recommendedScenario && result.recommended?.name) {
                            recommendedScenario = this.scenarios.find(s => s.name === result.recommended.name);
                        }

                        if (recommendedScenario) {
                            this.selectedScenario = recommendedScenario;
                        } else {
                            console.warn('未找到推荐的场景:', recommendedId, '可用场景:', this.scenarios.map(s => s.id));
                        }
                    }
                }
            } catch (error) {
                console.warn('场景识别失败:', error);
                this.recognizedResult = null;
            } finally {
                this.recognizing = false;
            }
        },

        // 重置场景选择状态（打开新建弹窗时调用）
        resetScenarioSelection() {
            this.scenarioRecognizeRequestId += 1;
            this.selectedScenario = null;
            this.recognizedResult = null;
            this.autoRecognizeEnabled = true;
            this.showScenarioSelector = false;
            this.scenarioSearchQuery = '';
            this.activeRecognizeFingerprint = '';
        },

        shouldShowLowConfidenceScenarioHint() {
            if (!this.recognizedResult || this.aiGenerating || this.showScenarioSelector) return false;
            if (Number(this.recognizedResult?.confidence || 0) >= 0.5) return false;
            const recommendedId = String(this.recognizedResult?.recommended?.id || '').trim();
            const selectedId = String(this.selectedScenario?.id || '').trim();
            return !recommendedId || !selectedId || recommendedId !== selectedId;
        },

        // 一键生成专属场景（基于用户已输入的主题和描述）
        async generateScenarioFromInput() {
            const topic = this.newSessionTopic.trim();
            const description = this.newSessionDescription.trim();
            const userInput = description ? `${topic}。${description}` : topic;

            if (userInput.length < 10) {
                this.showToast('请先补充更多主题描述', 'error');
                return;
            }

            this.aiScenarioDescription = userInput;
            this.aiGenerating = true;
            this.aiGeneratedPreview = null;
            this.aiExplanation = '';

            try {
                const result = await this.apiCall('/scenarios/generate', {
                    method: 'POST',
                    body: JSON.stringify({ user_description: userInput })
                });

                if (result.success && result.generated_scenario) {
                    this.aiGeneratedPreview = result.generated_scenario;
                    this.aiExplanation = result.ai_explanation || '';
                    this.expandedDimensions = [];
                    this.aiExplanationExpanded = true;
                    this.showAiPreviewModal = true;
                } else {
                    this.showToast(result.error || '生成失败，请重试', 'error');
                }
            } catch (error) {
                this.showToast('生成场景失败: ' + error.message, 'error');
            } finally {
                this.aiGenerating = false;
            }
        },

        // ============ 自定义场景 ============

        // 自定义场景编辑器状态
        showCustomScenarioModal: false,
        customScenario: {
            name: '',
            description: '',
            dimensions: [
                { id: 'dim_1', name: '', description: '', key_aspects: '' }
            ],
            solution: {
                mode: 'auto',
                dsl: {
                    hero_focus: '推进判断',
                    solution_outline: '现状问题\n目标蓝图\n方案对比\n实施路径',
                    emphasis: '风险边界\n下一步推进'
                },
                schemaText: '{\n  "version": "v1",\n  "sections": [\n    "推进判断",\n    "现状问题",\n    "目标蓝图",\n    "方案对比",\n    "实施路径",\n    "风险边界",\n    "下一步推进"\n  ]\n}'
            }
        },
        savingCustomScenario: false,

        // AI 场景生成器状态
        showAiGenerateModal: false,      // AI 输入弹窗
        showAiPreviewModal: false,       // AI 预览弹窗
        aiScenarioDescription: '',       // 用户输入的描述
        aiGenerating: false,             // AI 生成中
        aiGeneratedPreview: null,        // AI 生成的预览数据
        aiExplanation: '',               // AI 设计说明
        expandedDimensions: [],          // 展开的维度索引
        aiExplanationExpanded: true,     // AI 说明是否展开

        createDefaultScenarioSolution() {
            return {
                mode: 'auto',
                dsl: {
                    hero_focus: '推进判断',
                    solution_outline: '现状问题\n目标蓝图\n方案对比\n实施路径',
                    emphasis: '风险边界\n下一步推进'
                },
                schemaText: JSON.stringify({
                    version: 'v1',
                    sections: [
                        '推进判断',
                        '现状问题',
                        '目标蓝图',
                        '方案对比',
                        '实施路径',
                        '风险边界',
                        '下一步推进'
                    ]
                }, null, 2)
            };
        },

        createEmptyCustomScenario() {
            return {
                name: '',
                description: '',
                dimensions: [
                    { id: 'dim_1', name: '', description: '', key_aspects: '' }
                ],
                solution: this.createDefaultScenarioSolution()
            };
        },

        ensureScenarioSolutionState(target) {
            if (!target || typeof target !== 'object') return;
            if (!target.solution || typeof target.solution !== 'object') {
                target.solution = this.createDefaultScenarioSolution();
            }
            if (!target.solution.dsl || typeof target.solution.dsl !== 'object') {
                target.solution.dsl = {};
            }
            target.solution.mode = String(target.solution.mode || 'auto').trim().toLowerCase() || 'auto';
            target.solution.dsl.hero_focus = String(target.solution.dsl.hero_focus || '推进判断').trim() || '推进判断';

            const outlineRaw = target.solution.dsl.solution_outline;
            if (Array.isArray(outlineRaw)) {
                target.solution.dsl.solution_outline = outlineRaw.filter(Boolean).join('\n');
            } else {
                target.solution.dsl.solution_outline = String(outlineRaw || '现状问题\n目标蓝图\n方案对比\n实施路径');
            }

            const emphasisRaw = target.solution.dsl.emphasis;
            if (Array.isArray(emphasisRaw)) {
                target.solution.dsl.emphasis = emphasisRaw.filter(Boolean).join('\n');
            } else {
                target.solution.dsl.emphasis = String(emphasisRaw || '风险边界\n下一步推进');
            }

            if (!target.solution.schemaText) {
                if (target.solution.schema && typeof target.solution.schema === 'object' && Object.keys(target.solution.schema).length) {
                    target.solution.schemaText = JSON.stringify(target.solution.schema, null, 2);
                } else {
                    target.solution.schemaText = this.createDefaultScenarioSolution().schemaText;
                }
            }
        },

        getScenarioSolutionModeLabel(mode) {
            const normalized = String(mode || 'auto').trim().toLowerCase();
            if (normalized === 'dsl') return '目录增强';
            if (normalized === 'schema') return '专家模式';
            return '自动推导';
        },

        normalizeScenarioSolutionLines(value) {
            return String(value || '')
                .split(/\n+/)
                .map(item => item.trim())
                .filter(Boolean);
        },

        normalizeScenarioPreviewLabel(item, fallback = '章节') {
            if (typeof item === 'string') return item.trim() || fallback;
            if (item && typeof item === 'object') {
                return String(item.nav_label || item.title || item.label || item.section_id || fallback).trim() || fallback;
            }
            return fallback;
        },

        inferAutoScenarioSections(target) {
            const dims = Array.isArray(target?.dimensions) ? target.dimensions : [];
            const labels = ['推进判断'];
            dims.forEach((dim) => {
                const name = String(dim?.name || '').trim();
                if (name) labels.push(name);
            });
            labels.push('实施计划', '风险与边界');
            return labels.filter((item, index, list) => item && list.indexOf(item) === index).slice(0, 10);
        },

        getScenarioDimensionCount(scenario) {
            return Array.isArray(scenario?.dimensions) ? scenario.dimensions.length : 0;
        },

        getScenarioSolutionPreview(target) {
            if (!target || typeof target !== 'object') {
                return { mode: 'auto', modeLabel: '自动推导', sections: [], error: '' };
            }
            this.ensureScenarioSolutionState(target);
            const mode = String(target.solution.mode || 'auto').trim().toLowerCase() || 'auto';
            let sections = [];
            let error = '';

            if (mode === 'schema') {
                try {
                    const parsed = JSON.parse(String(target.solution.schemaText || '{}'));
                    sections = Array.isArray(parsed.sections)
                        ? parsed.sections.map((item) => this.normalizeScenarioPreviewLabel(item)).filter(Boolean)
                        : [];
                    if (!sections.length) {
                        error = 'Schema 中至少需要一个 sections 条目。';
                    }
                } catch (parseError) {
                    error = 'Schema JSON 格式无效，当前无法预览。';
                }
            } else if (mode === 'dsl') {
                sections = [
                    String(target.solution.dsl.hero_focus || '').trim(),
                    ...this.normalizeScenarioSolutionLines(target.solution.dsl.solution_outline),
                    ...this.normalizeScenarioSolutionLines(target.solution.dsl.emphasis)
                ].filter((item, index, list) => item && list.indexOf(item) === index);
            } else {
                sections = this.inferAutoScenarioSections(target);
            }

            return {
                mode,
                modeLabel: this.getScenarioSolutionModeLabel(mode),
                sections,
                error
            };
        },

        buildScenarioSolutionPayload(target) {
            this.ensureScenarioSolutionState(target);
            const mode = String(target.solution.mode || 'auto').trim().toLowerCase() || 'auto';
            if (mode === 'schema') {
                let parsed = {};
                try {
                    parsed = JSON.parse(String(target.solution.schemaText || '{}'));
                } catch (parseError) {
                    throw new Error('方案页 schema JSON 格式无效');
                }
                return {
                    version: 'v1',
                    mode: 'schema',
                    schema: parsed
                };
            }
            if (mode === 'dsl') {
                return {
                    version: 'v1',
                    mode: 'dsl',
                    dsl: {
                        hero_focus: String(target.solution.dsl.hero_focus || '推进判断').trim() || '推进判断',
                        solution_outline: this.normalizeScenarioSolutionLines(target.solution.dsl.solution_outline),
                        emphasis: this.normalizeScenarioSolutionLines(target.solution.dsl.emphasis)
                    }
                };
            }
            return {
                version: 'v1',
                mode: 'auto'
            };
        },

        // 打开自定义场景编辑器
        openCustomScenarioEditor() {
            this.customScenario = this.createEmptyCustomScenario();
            this.showCustomScenarioModal = true;
        },

        // 添加维度
        addDimension() {
            if (this.customScenario.dimensions.length >= 8) return;
            const idx = this.customScenario.dimensions.length + 1;
            this.customScenario.dimensions.push({
                id: `dim_${idx}`,
                name: '',
                description: '',
                key_aspects: ''
            });
        },

        // 删除维度
        removeDimension(index) {
            if (this.customScenario.dimensions.length <= 1) return;
            this.customScenario.dimensions.splice(index, 1);
        },

        // 保存自定义场景
        async saveCustomScenario() {
            const name = this.customScenario.name.trim();
            if (!name) {
                this.showToast('请输入场景名称', 'error');
                return;
            }

            const dims = this.customScenario.dimensions.filter(d => d.name.trim());
            if (dims.length === 0) {
                this.showToast('至少需要一个维度', 'error');
                return;
            }

            this.savingCustomScenario = true;
            try {
                const dimensions = dims.map((d, i) => ({
                    id: `dim_${i + 1}`,
                    name: d.name.trim(),
                    description: d.description.trim(),
                    key_aspects: d.key_aspects
                        .split(/[,，、\s]+/)
                        .map(k => k.trim())
                        .filter(k => k),
                    min_questions: 2,
                    max_questions: 4
                }));

                const result = await this.apiCall('/scenarios/custom', {
                    method: 'POST',
                    body: JSON.stringify({
                        name,
                        description: this.customScenario.description.trim(),
                        dimensions,
                        solution: this.buildScenarioSolutionPayload(this.customScenario)
                    })
                });

                await this.loadScenarios();
                if (result?.scenario_id) {
                    const newScenario = this.scenarios.find(s => s.id === result.scenario_id);
                    if (newScenario) {
                        this.selectedScenario = newScenario;
                        this.autoRecognizeEnabled = false;
                    }
                }
                this.showCustomScenarioModal = false;
                this.showToast(`场景「${name}」创建成功`, 'success');
            } catch (error) {
                this.showToast('创建场景失败: ' + error.message, 'error');
            } finally {
                this.savingCustomScenario = false;
            }
        },

        // 删除自定义场景
        async deleteCustomScenario(scenarioId, scenarioName) {
            const confirmed = await this.openActionConfirmDialog({
                title: '确认删除场景',
                message: `确定要删除场景「${scenarioName}」吗？`,
                tone: 'danger',
                confirmText: '删除',
                cancelText: '取消'
            });
            if (!confirmed) return;
            try {
                await this.apiCall(`/scenarios/custom/${scenarioId}`, {
                    method: 'DELETE'
                });
                await this.loadScenarios();
                if (this.selectedScenario?.id === scenarioId) {
                    this.selectedScenario = null;
                }
                this.showToast(`场景「${scenarioName}」已删除`, 'success');
            } catch (error) {
                this.showToast('删除失败: ' + error.message, 'error');
            }
        },

        // ============ AI 场景生成器 ============

        // 打开 AI 场景生成输入弹窗
        openAiScenarioGenerator() {
            this.aiScenarioDescription = '';
            this.aiGeneratedPreview = null;
            this.aiExplanation = '';
            this.showAiGenerateModal = true;
        },

        // AI 生成场景配置
        async generateScenarioWithAi() {
            const description = this.aiScenarioDescription.trim();
            if (!description) {
                this.showToast('请输入您想做什么的描述', 'error');
                return;
            }
            if (description.length < 10) {
                this.showToast('描述太短，请至少输入10个字', 'error');
                return;
            }
            if (description.length > 500) {
                this.showToast('描述不能超过500字', 'error');
                return;
            }

            this.aiGenerating = true;
            try {
                const result = await this.apiCall('/scenarios/generate', {
                    method: 'POST',
                    body: JSON.stringify({ user_description: description })
                });

                if (result.success && result.generated_scenario) {
                    this.aiGeneratedPreview = result.generated_scenario;
                    this.ensureScenarioSolutionState(this.aiGeneratedPreview);
                    this.aiExplanation = result.ai_explanation || '';
                    this.expandedDimensions = [];
                    this.aiExplanationExpanded = true;
                    this.showAiGenerateModal = false;
                    this.showAiPreviewModal = true;
                } else {
                    this.showToast(result.error || '生成失败，请重试', 'error');
                }
            } catch (error) {
                this.showToast('生成场景失败: ' + error.message, 'error');
            } finally {
                this.aiGenerating = false;
            }
        },

        // 编辑 AI 生成的维度
        editAiDimension(index, field, value) {
            if (this.aiGeneratedPreview && this.aiGeneratedPreview.dimensions[index]) {
                if (field === 'key_aspects') {
                    this.aiGeneratedPreview.dimensions[index][field] = value
                        .split(/[,，、\s]+/)
                        .map(k => k.trim())
                        .filter(k => k);
                } else {
                    this.aiGeneratedPreview.dimensions[index][field] = value;
                }
            }
        },

        // 添加维度到 AI 预览
        addAiDimension() {
            if (!this.aiGeneratedPreview) return;
            if (this.aiGeneratedPreview.dimensions.length >= 8) {
                this.showToast('最多支持8个维度', 'warning');
                return;
            }
            const idx = this.aiGeneratedPreview.dimensions.length + 1;
            this.aiGeneratedPreview.dimensions.push({
                id: `dim_${idx}`,
                name: '',
                description: '',
                key_aspects: [],
                min_questions: 2,
                max_questions: 4
            });
        },

        // 删除 AI 预览中的维度
        removeAiDimension(index) {
            if (!this.aiGeneratedPreview) return;
            if (this.aiGeneratedPreview.dimensions.length <= 1) {
                this.showToast('至少需要1个维度', 'warning');
                return;
            }
            this.aiGeneratedPreview.dimensions.splice(index, 1);
            // 从展开列表中移除
            const expandedIdx = this.expandedDimensions.indexOf(index);
            if (expandedIdx > -1) {
                this.expandedDimensions.splice(expandedIdx, 1);
            }
            // 调整索引大于当前索引的展开项
            this.expandedDimensions = this.expandedDimensions.map(i => i > index ? i - 1 : i);
        },

        // 切换维度展开/折叠
        toggleDimension(index) {
            const idx = this.expandedDimensions.indexOf(index);
            if (idx > -1) {
                this.expandedDimensions.splice(idx, 1);
            } else {
                this.expandedDimensions.push(index);
            }
        },

        // 确认保存 AI 生成的场景
        async saveAiGeneratedScenario() {
            if (!this.aiGeneratedPreview) return;

            const name = this.aiGeneratedPreview.name?.trim();
            if (!name) {
                this.showToast('场景名称不能为空', 'error');
                return;
            }

            const validDims = this.aiGeneratedPreview.dimensions.filter(d => d.name?.trim());
            if (validDims.length === 0) {
                this.showToast('至少需要一个有效维度', 'error');
                return;
            }

            this.savingCustomScenario = true;
            try {
                const dimensions = validDims.map((d, i) => ({
                    id: `dim_${i + 1}`,
                    name: d.name.trim(),
                    description: d.description?.trim() || '',
                    key_aspects: Array.isArray(d.key_aspects) ? d.key_aspects : [],
                    min_questions: 2,
                    max_questions: 4
                }));

                const result = await this.apiCall('/scenarios/custom', {
                    method: 'POST',
                    body: JSON.stringify({
                        name,
                        description: this.aiGeneratedPreview.description?.trim() || '',
                        dimensions,
                        solution: this.buildScenarioSolutionPayload(this.aiGeneratedPreview)
                    })
                });

                await this.loadScenarios();

                // 自动选中新创建的场景
                if (result.scenario_id) {
                    const newScenario = this.scenarios.find(s => s.id === result.scenario_id);
                    if (newScenario) {
                        this.selectedScenario = newScenario;
                        this.autoRecognizeEnabled = false; // 禁用自动覆盖
                    }
                }

                this.showAiPreviewModal = false;
                this.aiGeneratedPreview = null;
                this.showToast(`场景「${name}」创建成功并已选中`, 'success');
            } catch (error) {
                this.showToast('保存场景失败: ' + error.message, 'error');
            } finally {
                this.savingCustomScenario = false;
            }
        },

        // 重新生成场景
        regenerateScenario() {
            this.showAiPreviewModal = false;
            this.showAiGenerateModal = true;
        },

        // 获取场景名称
        getScenarioName(session) {
            if (session?.scenario_config?.name) {
                return session.scenario_config.name;
            }
            if (session?.scenario_id) {
                const scenario = this.scenarios.find(s => s.id === session.scenario_id);
                return scenario?.name || session.scenario_id;
            }
            return '产品需求';
        },

        // 根据百分比计算进度条颜色
        getProgressColor(percentage) {
            // 100% 时使用鼠尾草蓝（从配置文件读取），与完成状态图标保持一致
            if (percentage >= 100) {
                return (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.colors?.progressComplete)
                    ? SITE_CONFIG.colors.progressComplete
                    : '#357BE2';  // 默认鼠尾草蓝
            }

            // 0-99%: 从浅灰 (#D4D4D4) 渐变到深灰 (#525252)
            const startColor = { r: 212, g: 212, b: 212 }; // 浅灰
            const endColor = { r: 82, g: 82, b: 82 };      // 深灰（不是纯黑）

            const ratio = Math.min(Math.max(percentage, 0), 100) / 100;

            const r = Math.round(startColor.r + (endColor.r - startColor.r) * ratio);
            const g = Math.round(startColor.g + (endColor.g - startColor.g) * ratio);
            const b = Math.round(startColor.b + (endColor.b - startColor.b) * ratio);

            return `rgb(${r}, ${g}, ${b})`;
        },

        getProgressBarStyle(percentage) {
            return `width: ${percentage}%; background-color: ${this.getProgressColor(percentage)}`;
        },

        getStepClass(idx) {
            if (idx < this.currentStep || (idx === 2 && this.generatingReport)) {
                return 'bg-[#357BE2] text-white';
            } else if (idx === this.currentStep) {
                return 'bg-cta text-white';
            }
            return 'bg-gray-200 text-gray-500';
        },

        formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        },

        syncInterviewHeaderHeight() {
            if (this.currentView !== 'interview' || this.currentStep !== 0) {
                this.interviewTopicMinHeight = 0;
                return;
            }
            if (!this.$refs?.interviewTopicCard || !this.$refs?.interviewReferenceCard) {
                this.interviewTopicMinHeight = 0;
                return;
            }
            this.$nextTick(() => {
                const height = Math.ceil(this.$refs.interviewReferenceCard.getBoundingClientRect().height);
                if (height > 0 && this.interviewTopicMinHeight !== height) {
                    this.interviewTopicMinHeight = height;
                }
            });
        },

        showToast(message, type = 'success', options = {}) {
            const actionLabel = options.actionLabel || '';
            const actionUrl = options.actionUrl || '';
            const duration = Number.isFinite(options.duration) ? options.duration : 4000;
            const persist = options.persist === true;
            const normalizedType = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'info';
            const a11yMeta = this.getToastA11yMeta(normalizedType, options);

            this.toast = {
                show: true,
                message,
                type: normalizedType,
                actionLabel,
                actionUrl,
                role: a11yMeta.role,
                ariaLive: a11yMeta.ariaLive,
                ariaAtomic: a11yMeta.ariaAtomic,
                announceMode: a11yMeta.announceMode
            };

            if (this.toastTimer) {
                clearTimeout(this.toastTimer);
            }
            if (!persist) {
                this.toastTimer = setTimeout(() => {
                    this.toast.show = false;
                }, duration);
            }
        },

        getToastA11yMeta(type = 'success', options = {}) {
            const config = this.toastA11yConfig || {};
            const defaultLive = config.defaultLive || 'polite';
            const errorLive = config.errorLive || 'assertive';
            const roleByType = config.roleByType || {};
            const announceMode = options.announceMode || (type === 'error' ? 'assertive' : defaultLive);

            return {
                role: roleByType[type] || (type === 'error' || type === 'warning' ? 'alert' : 'status'),
                ariaLive: announceMode === 'assertive' ? errorLive : defaultLive,
                ariaAtomic: options.atomic === false
                    ? 'false'
                    : (config.atomic === false ? 'false' : 'true'),
                announceMode
            };
        },

        // ============ 组合C：等待状态增强 ============
        // 获取当前思考阶段的子步骤（与三阶段进度同步）
        getThinkingSubSteps() {
            const stageIndex = this.thinkingStage?.stage_index ?? -1;
            // 简化逻辑：只依赖 stage_index，与三个圆圈进度保持同步
            // stage 0 = 分析阶段：完成前两个步骤
            // stage 1 = 检索阶段：完成第3、4个步骤
            // stage 2 = 生成阶段：完成最后两个步骤
            const steps = [
                { name: '解析回答关键信息', done: stageIndex >= 0 },
                { name: '识别未覆盖话题', done: stageIndex >= 1 },
                { name: '检索参考文档', done: stageIndex >= 1 },
                { name: '匹配追问策略', done: stageIndex >= 2 },
                { name: '生成候选问题', done: stageIndex >= 2 },
                { name: '优化问题表达', done: stageIndex >= 2 && this.thinkingStage?.progress === 100 }
            ];
            return steps;
        }
    };

    if (window.DeepVisionSessionListStateModule?.attach) {
        window.DeepVisionSessionListStateModule.attach(app);
    }
    if (window.DeepVisionReportStateModule?.attach) {
        window.DeepVisionReportStateModule.attach(app);
    }
    if (window.DeepVisionAuthLicenseStateModule?.attach) {
        window.DeepVisionAuthLicenseStateModule.attach(app);
    }

    return app;
}

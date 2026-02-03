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

function deepVision() {
    return {
        // ============ 状态 ============
        currentView: 'sessions',
        loading: false,
        loadingQuestion: false,
        isGoingPrev: false,
        submitting: false,  // 提交答案进行中，防止并发操作
        generatingReport: false,
        generatingSlides: false,
        webSearching: false,  // Web Search API 调用状态
        webSearchPollInterval: null,  // Web Search 状态轮询定时器
        quoteRotationInterval: null,  // 诗句轮播定时器
        currentTipIndex: 0,  // 访谈小技巧当前索引
        currentTip: '',  // 当前显示的小技巧文本
        tipRotationInterval: null,  // 小技巧轮播定时器

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

        // 会话相关
        sessions: [],
        currentSession: null,
        newSessionTopic: '',
        newSessionDescription: '',
        selectedInterviewMode: 'standard',  // 默认标准模式
        hoveredDepthMode: null,  // 深度选项悬停状态
        showScenarioSelector: false,  // 场景选择器面板
        scenarioSearchQuery: '',  // 场景搜索关键词
        showNewSessionModal: false,
        showDeleteModal: false,
        sessionToDelete: null,

        // 会话列表筛选和分页
        sessionSearchQuery: '',
        sessionStatusFilter: 'all',
        sessionSortOrder: 'newest',
        filteredSessions: [],
        currentPage: 1,
        pageSize: 10,
        searchDebounceTimer: null,

        // 确认重新访谈对话框
        showRestartModal: false,

        // 确认删除文档对话框
        showDeleteDocModal: false,
        docToDelete: null,
        docDeleteCallback: null,

        // 拖放上传状态
        isDraggingDoc: false,
        isDraggingResearch: false,

        // 报告相关
        reports: [],
        selectedReport: null,
        reportContent: '',
        showDeleteReportModal: false,
        reportToDelete: null,

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

        // 当前问题（AI 生成）
        currentQuestion: {
            text: '',
            options: [],
            multiSelect: false,  // 是否多选
            isFollowUp: false,
            followUpReason: null,
            conflictDetected: false,
            conflictDescription: null,
            aiGenerated: false
        },
        selectedAnswers: [],  // 改用数组支持多选
        otherAnswerText: '',
        otherSelected: false,  // "其他"选项是否被选中

        // Toast 通知
        toast: { show: false, message: '', type: 'success' },

        // 里程碑弹窗
        showMilestoneModal: false,
        milestoneData: null,  // { dimension: '...', dimName: '...', stats: {...}, nextDimension: '...' }

        // 版本信息
        appVersion: (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.version?.current) || '1.0.0',
        changelog: [],
        showChangelogModal: false,

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

            await this.loadVersionInfo();
            await this.checkServerStatus();
            await this.loadScenarios();
            await this.loadSessions();
            await this.loadReports();
            this.startQuoteRotation();

            // 检查是否首次访问，跳转产品介绍页
            this.checkFirstVisit();
        },

        // 检查首次访问
        checkFirstVisit() {
            const hasSeenIntro = localStorage.getItem('deepvision_intro_seen');
            if (!hasSeenIntro) {
                localStorage.setItem('deepvision_intro_seen', 'true');
                window.location.href = 'intro.html';
            }
        },

        // 加载版本信息
        async loadVersionInfo() {
            try {
                const configFile = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.version?.configFile) || 'version.json';
                const response = await fetch(configFile);
                if (response.ok) {
                    const data = await response.json();
                    this.appVersion = data.version || this.appVersion;
                    this.changelog = data.changelog || [];
                }
            } catch (error) {
                console.warn('无法加载版本信息:', error);
            }
        },

        // 启动诗句轮播
        startQuoteRotation() {
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
                    this.aiAvailable = this.serverStatus.ai_available;
                    if (!this.aiAvailable) {
                        this.showToast('AI 功能未启用（需设置 ANTHROPIC_API_KEY）', 'warning');
                    }
                }
            } catch (error) {
                console.error('服务器连接失败:', error);
                this.showToast('无法连接到服务器，请确保 server.py 正在运行', 'error');
            }
        },

        // 开始轮询 Web Search 状态
        startWebSearchPolling() {
            // 先停止旧的轮询，防止多个轮询并发
            this.stopWebSearchPolling();

            // 从配置文件读取轮询间隔
            const pollInterval = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.api?.webSearchPollInterval)
                ? SITE_CONFIG.api.webSearchPollInterval
                : 200;  // 默认 200ms

            this.webSearchPollInterval = setInterval(async () => {
                try {
                    const response = await fetch(`${API_BASE}/status/web-search`);
                    if (response.ok) {
                        const data = await response.json();
                        this.webSearching = data.active;
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
            this.webSearching = false;  // 重置状态
        },

        // ========== 方案B: 思考进度轮询 ==========
        startThinkingPolling() {
            // 先停止旧的轮询，防止多个轮询并发
            this.stopThinkingPolling();

            const pollInterval = 300;  // 300ms 轮询间隔

            this.thinkingPollInterval = setInterval(async () => {
                try {
                    const sessionId = this.currentSession?.session_id;
                    if (!sessionId) return;

                    const response = await fetch(`${API_BASE}/status/thinking/${sessionId}`);
                    if (response.ok) {
                        const data = await response.json();
                        if (data.active) {
                            this.thinkingStage = data;
                        } else {
                            this.thinkingStage = null;
                        }
                    }
                } catch (error) {
                    // 轮询失败时不显示错误，静默处理
                }
            }, pollInterval);
        },

        stopThinkingPolling() {
            if (this.thinkingPollInterval) {
                clearInterval(this.thinkingPollInterval);
                this.thinkingPollInterval = null;
            }
            this.thinkingStage = null;  // 重置状态
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

        // ========== 方案D: 骨架填充 ==========
        async startSkeletonFill(result) {
            const questionText = result.question || '';
            const options = result.options || [];

            // 验证必要数据
            if (!questionText || options.length === 0) {
                this.currentQuestion = {
                    text: '', options: [], multiSelect: false,
                    aiGenerated: false, serviceError: true,
                    errorTitle: '数据异常',
                    errorDetail: '问题或选项缺失，请重试'
                };
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
            this.currentQuestion = {
                text: result.question,
                options: result.options || [],
                multiSelect: result.multi_select || false,
                isFollowUp: result.is_follow_up || false,
                followUpReason: result.follow_up_reason,
                conflictDetected: result.conflict_detected || false,
                conflictDescription: result.conflict_description,
                aiGenerated: result.ai_generated || false
            };

            // 检查用户是否禁用了动效（可访问性支持）
            const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

            if (prefersReducedMotion) {
                // 禁用动效时：立即显示所有内容
                this.typingText = questionText;
                this.typingComplete = true;
                this.optionsVisible = options.map((_, i) => i);
                this.interactionReady = true;
                this.skeletonMode = false;
            } else {
                // 启用动效时：打字机效果 + 选项淡入
                const typingSpeed = 30;  // 每个字符 30ms
                for (let i = 0; i <= questionText.length; i++) {
                    this.typingText = questionText.substring(0, i);
                    await new Promise(resolve => setTimeout(resolve, typingSpeed));
                }
                this.typingComplete = true;

                // 选项依次淡入
                const optionDelay = 150;  // 每个选项间隔 150ms
                for (let i = 0; i < options.length; i++) {
                    this.optionsVisible.push(i);
                    await new Promise(resolve => setTimeout(resolve, optionDelay));
                }

                // 短暂延迟后允许交互
                await new Promise(resolve => setTimeout(resolve, 200));
                this.interactionReady = true;
                this.skeletonMode = false;
            }
        },

        // ============ API 调用 ============
        async apiCall(endpoint, options = {}) {
            try {
                const response = await fetch(`${API_BASE}${endpoint}`, {
                    headers: { 'Content-Type': 'application/json' },
                    ...options
                });
                if (!response.ok) {
                    let errorMsg = `HTTP ${response.status}`;
                    try {
                        const error = await response.json();
                        errorMsg = error.error || error.detail || errorMsg;
                    } catch (parseError) {
                        // 响应非 JSON 格式，使用 HTTP 状态信息
                    }
                    throw new Error(errorMsg);
                }
                return await response.json();
            } catch (error) {
                console.error('API 调用失败:', error);
                throw error;
            }
        },

        // ============ 会话管理 ============
        async loadSessions() {
            this.loading = true;
            try {
                this.sessions = await this.apiCall('/sessions');
                this.filterSessions();  // 加载完成后执行筛选
            } catch (error) {
                this.showToast('加载会话列表失败', 'error');
            } finally {
                this.loading = false;
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
                this.selectedInterviewMode = 'standard';  // 重置为默认值
                this.selectedScenario = null;  // 重置场景选择
                this.showScenarioSelector = false;  // 重置场景选择器
                this.scenarioSearchQuery = '';  // 重置搜索关键词
                this.currentStep = 0;
                this.currentView = 'interview';
                this.showToast('会话创建成功', 'success');
            } catch (error) {
                this.showToast('创建会话失败', 'error');
            } finally {
                this.loading = false;
            }
        },

        async openSession(sessionId) {
            try {
                this.currentSession = await this.apiCall(`/sessions/${sessionId}`);
                this.updateDimensionsFromSession(this.currentSession);
                this.currentView = 'interview';

                // 检查所有维度是否已完成
                const nextDim = this.getNextIncompleteDimension();
                if (!nextDim && this.currentSession.interview_log.length > 0) {
                    // 所有维度已完成，直接进入确认阶段
                    this.currentStep = 2;
                    this.currentDimension = this.dimensionOrder[this.dimensionOrder.length - 1];
                    this.currentQuestion = { text: '', options: [], multiSelect: false, aiGenerated: false };
                } else if (this.currentSession.interview_log.length > 0) {
                    // 有未完成的维度，继续访谈
                    this.currentStep = 1;
                    this.currentDimension = nextDim;
                    await this.fetchNextQuestion();
                } else {
                    // 还没开始访谈
                    this.currentStep = 0;
                    this.currentDimension = this.dimensionOrder[0] || 'customer_needs';
                }
            } catch (error) {
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

        // 确认删除报告
        confirmDeleteReport(reportName) {
            this.reportToDelete = reportName;
            this.showDeleteReportModal = true;
        },

        // 删除报告
        async deleteReport() {
            if (!this.reportToDelete) return;

            try {
                await this.apiCall(`/reports/${encodeURIComponent(this.reportToDelete)}`, { method: 'DELETE' });
                this.reports = this.reports.filter(r => r.name !== this.reportToDelete);
                this.showDeleteReportModal = false;
                this.reportToDelete = null;
                this.showToast('报告已删除', 'success');
            } catch (error) {
                this.showToast('删除报告失败', 'error');
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

            for (const file of files) {
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
                        `${API_BASE}/sessions/${this.currentSession.session_id}/documents`,
                        { method: 'POST', body: formData }
                    );

                    if (response.ok) {
                        const result = await response.json();
                        // 刷新会话数据
                        this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);
                        this.showToast(`文档 ${file.name} 上传成功`, 'success');
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
                    const response = await fetch(
                        `${API_BASE}/sessions/${this.currentSession.session_id}/documents/${encodeURIComponent(doc.name)}`,
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
                this.currentQuestion = { text: '', options: [], multiSelect: false, aiGenerated: false };
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

        async fetchNextQuestion() {
            this.loadingQuestion = true;
            this.skeletonMode = false;
            this.interactionReady = false;
            this.startTipRotation();
            // 重置问题状态，清除上一次可能的错误
            this.currentQuestion = {
                text: '', options: [], multiSelect: false,
                aiGenerated: false, serviceError: false
            };
            this.startThinkingPolling();  // 方案B: 开始轮询思考进度
            this.startWebSearchPolling();  // 同时保留 Web Search 状态轮询
            this.selectedAnswers = [];
            this.otherAnswerText = '';
            this.otherSelected = false;

            try {
                const response = await fetch(`${API_BASE}/sessions/${this.currentSession.session_id}/next-question`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dimension: this.currentDimension })
                });

                const result = await response.json();

                // 先停止轮询，手动设置完成状态让所有步骤显示为已完成
                this.stopThinkingPolling();
                this.stopWebSearchPolling();

                // 手动设置为完成状态，让用户看到所有步骤都完成
                this.thinkingStage = {
                    active: true,
                    stage_index: 2,
                    stage_name: '生成问题',
                    message: '问题生成完成',
                    progress: 100
                };

                // 等待 600ms 让用户看到完成动画，然后再切换到新问题
                await new Promise(resolve => setTimeout(resolve, 600));

                // 关闭加载状态
                this.loadingQuestion = false;
                this.thinkingStage = null;
                this.stopTipRotation();

                // 检查是否有错误
                if (!response.ok || result.error) {
                    const errorTitle = result.error || '服务错误';
                    const errorDetail = result.detail || '请稍后重试';

                    // 显示 Toast 提示
                    this.showToast(errorTitle, 'error');

                    // 设置错误状态
                    this.currentQuestion = {
                        text: '',
                        options: [],
                        multiSelect: false,
                        aiGenerated: false,
                        serviceError: true,
                        errorTitle: errorTitle,
                        errorDetail: errorDetail
                    };
                    this.interactionReady = true;  // 错误状态下允许交互（重试）
                    return;
                }

                if (result.completed) {
                    // 当前维度已完成，显示里程碑弹窗
                    const completedDimension = this.currentDimension;
                    const completedDimName = this.getDimensionName(completedDimension);
                    const stats = result.stats || {};

                    // 找下一个未完成的维度
                    const currentIdx = this.dimensionOrder.indexOf(this.currentDimension);
                    let nextDim = null;
                    for (let i = 1; i <= this.dimensionOrder.length; i++) {
                        const dim = this.dimensionOrder[(currentIdx + i) % this.dimensionOrder.length];
                        const dimension = this.currentSession.dimensions[dim];
                        if (dimension && dimension.coverage < 100) {
                            nextDim = dim;
                            break;
                        }
                    }

                    if (nextDim) {
                        // 还有未完成的维度，显示里程碑弹窗
                        this.milestoneData = {
                            dimension: completedDimension,
                            dimName: completedDimName,
                            stats: stats,
                            nextDimension: nextDim,
                            nextDimName: this.getDimensionName(nextDim),
                            isLastDimension: false
                        };
                        this.showMilestoneModal = true;
                    } else {
                        // 所有维度都完成
                        this.milestoneData = {
                            dimension: completedDimension,
                            dimName: completedDimName,
                            stats: stats,
                            nextDimension: null,
                            nextDimName: null,
                            isLastDimension: true
                        };
                        this.showMilestoneModal = true;
                    }
                } else {
                    // 方案D: 调用骨架填充（打字机效果 + 选项依次淡入）
                    await this.startSkeletonFill(result);
                }
            } catch (error) {
                console.error('获取问题失败:', error);
                console.error('错误详情:', error.message, error.stack);

                // 网络错误或其他异常
                const errorTitle = '网络错误';
                const errorDetail = `无法连接到服务器: ${error.message}`;

                this.showToast(`${errorTitle}: ${error.message}`, 'error');
                this.currentQuestion = {
                    text: '',
                    options: [],
                    multiSelect: false,
                    aiGenerated: false,
                    serviceError: true,
                    errorTitle: errorTitle,
                    errorDetail: errorDetail
                };
                this.interactionReady = true;  // 错误状态下允许交互（重试）
            } finally {
                // 确保停止轮询
                this.stopThinkingPolling();
                this.stopWebSearchPolling();
                this.loadingQuestion = false;
                this.isGoingPrev = false;
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

        // 切换选项选择状态
        toggleOption(option) {
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

        async submitAnswer() {
            if (!this.canSubmitAnswer()) return;

            // 设置提交状态，防止并发操作
            this.submitting = true;

            // 从配置获取限制
            const config = typeof SITE_CONFIG !== 'undefined' ? SITE_CONFIG.limits : null;
            const answerMaxLength = config?.answerMaxLength || 5000;
            const otherInputMaxLength = config?.otherInputMaxLength || 2000;

            // 验证"其他"选项输入长度
            if (this.otherSelected && this.otherAnswerText.length > otherInputMaxLength) {
                this.showToast(`自定义答案不能超过${otherInputMaxLength}个字符`, 'error');
                this.submitting = false;
                return;
            }

            // 构建答案
            let answer;
            if (this.currentQuestion.multiSelect) {
                // 多选：合并所有选中的答案
                const answers = [...this.selectedAnswers];
                if (this.otherSelected && this.otherAnswerText.trim()) {
                    answers.push(this.otherAnswerText.trim());
                }
                if (answers.length === 0) {
                    this.submitting = false;
                    return;
                }
                answer = answers.join('；');  // 使用中文分号分隔
            } else {
                // 单选
                if (this.otherSelected) {
                    answer = this.otherAnswerText.trim();
                } else {
                    answer = this.selectedAnswers.length > 0 ? this.selectedAnswers[0] : '';
                }
                if (!answer) {
                    this.submitting = false;
                    return;
                }
            }

            // 验证答案总长度
            if (answer.length > answerMaxLength) {
                this.showToast(`答案内容过长，请简化后重试（最大${answerMaxLength}字符）`, 'error');
                this.submitting = false;
                return;
            }

            try {
                const updatedSession = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/submit-answer`,
                    {
                        method: 'POST',
                        body: JSON.stringify({
                            question: this.currentQuestion.text,
                            answer: answer,
                            dimension: this.currentDimension,
                            options: this.currentQuestion.options,
                            multi_select: this.currentQuestion.multiSelect,
                            is_follow_up: this.currentQuestion.isFollowUp || false
                        })
                    }
                );

                this.currentSession = updatedSession;

                // 检查是否需要切换维度
                const currentDim = this.currentSession.dimensions[this.currentDimension];
                if (currentDim && currentDim.coverage >= 100) {
                    const nextDim = this.getNextIncompleteDimension();
                    if (nextDim) {
                        this.currentDimension = nextDim;
                    } else {
                        // 所有维度都已完成，直接进入确认阶段
                        this.currentStep = 2;
                        this.currentQuestion = { text: '', options: [], multiSelect: false, aiGenerated: false };
                        this.showToast('所有维度访谈完成！', 'success');
                        return;  // 不再调用 fetchNextQuestion
                    }
                }

                // 获取下一个问题
                await this.fetchNextQuestion();

            } catch (error) {
                console.error('提交回答错误:', error);
                this.showToast(`提交回答失败: ${error.message}`, 'error');
            } finally {
                // 确保清除提交状态
                this.submitting = false;
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
                const savedQuestion = {
                    text: lastLog.question,
                    options: lastLog.options || [],
                    multiSelect: lastLog.multi_select || false,
                    isFollowUp: false,
                    followUpReason: null,
                    conflictDetected: false,
                    conflictDescription: null,
                    aiGenerated: true  // 标记为之前 AI 生成的问题
                };

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
                this.selectedAnswers = [];
                this.otherAnswerText = '';
                this.otherSelected = false;
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
                    this.currentDimension = nextDim;
                    await this.fetchNextQuestion();
                } else {
                    // 所有维度完成，进入确认阶段
                    this.currentStep = 2;
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

        // 关闭里程碑弹窗并继续访谈
        async continueMilestone() {
            this.showMilestoneModal = false;

            if (this.milestoneData && this.milestoneData.isLastDimension) {
                // 所有维度都完成，自动进入确认阶段
                this.currentStep = 2;
                this.currentQuestion = {
                    text: '',
                    options: [],
                    multiSelect: false,
                    aiGenerated: false
                };
            } else if (this.milestoneData && this.milestoneData.nextDimension) {
                // 切换到下一个维度
                this.currentDimension = this.milestoneData.nextDimension;
                await this.fetchNextQuestion();
            }

            this.milestoneData = null;
        },

        goToConfirmation() {
            this.currentStep = 2;
        },

        // ============ 重新访谈 ============
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
                    this.currentStep = 0;
                    this.currentDimension = this.dimensionOrder[0] || 'customer_needs';
                    this.currentQuestion = null;

                    this.showToast('已保存当前访谈内容，开始新一轮访谈', 'success');
                } else {
                    this.showToast('重新访谈失败', 'error');
                }
            } catch (error) {
                console.error('重新访谈错误:', error);
                this.showToast('重新访谈失败', 'error');
            }
        },

        // ============ 报告生成（AI 驱动）============
        async generateReport() {
            this.generatingReport = true;
            this.startWebSearchPolling();  // 开始轮询 Web Search 状态

            try {
                const result = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/generate-report`,
                    { method: 'POST' }
                );

                if (result.success) {
                    const aiMsg = result.ai_generated ? '（AI 生成）' : '（模板生成）';
                    this.showToast(`报告生成成功 ${aiMsg}`, 'success');
                    this.currentSession.status = 'completed';
                    await this.loadReports();
                    this.currentView = 'reports';
                    // 自动打开新生成的报告
                    await this.viewReport(result.report_name);
                } else {
                    throw new Error('报告生成失败');
                }
            } catch (error) {
                this.showToast('报告生成失败', 'error');
            } finally {
                this.generatingReport = false;
                this.stopWebSearchPolling();  // 停止轮询 Web Search 状态
            }
        },

        // ============ 报告查看 ============
        async loadReports() {
            try {
                this.reports = await this.apiCall('/reports');
            } catch (error) {
                console.error('加载报告失败:', error);
            }
        },

        async viewReport(filename) {
            try {
                const data = await this.apiCall(`/reports/${encodeURIComponent(filename)}`);
                this.reportContent = data.content;
                this.selectedReport = filename;
            } catch (error) {
                this.showToast('加载报告失败', 'error');
            }
        },

        async generatePresentation() {
            if (!this.selectedReport || this.generatingSlides) return;

            this.generatingSlides = true;
            try {
                const result = await this.apiCall(
                    `/reports/${encodeURIComponent(this.selectedReport)}/refly`,
                    { method: 'POST' }
                );
                const reflyUrl = result?.presentation_url
                    || result?.url
                    || result?.refly_response?.url
                    || result?.refly_response?.data?.url
                    || result?.refly_response?.result?.url;
                if (reflyUrl) {
                    window.open(reflyUrl, '_blank', 'noopener');
                    this.showToast('演示文稿已生成，已为你打开', 'success');
                } else {
                    this.showToast('已提交到 Refly，正在生成演示文稿', 'success');
                }
            } catch (error) {
                this.showToast(`生成演示文稿失败：${error.message || '请求失败'}`, 'error');
            } finally {
                this.generatingSlides = false;
            }
        },

        // 当报告内容渲染完成后调用（由 x-effect 触发）
        onReportRendered() {
            this.renderMermaidCharts();
        },

        downloadReport(format = 'md') {
            if (!this.reportContent || !this.selectedReport) return;

            const baseFilename = this.selectedReport.replace(/\.md$/, '');

            switch (format) {
                case 'md':
                    this.downloadMarkdown(baseFilename);
                    break;
                case 'pdf':
                    this.downloadPDF(baseFilename);
                    break;
                case 'docx':
                    this.downloadDocx(baseFilename);
                    break;
                default:
                    this.downloadMarkdown(baseFilename);
            }
        },

        // 下载 Markdown 格式
        downloadMarkdown(filename) {
            const blob = new Blob([this.reportContent], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${filename}.md`;
            a.click();
            URL.revokeObjectURL(url);
            this.showToast('Markdown 文件已下载', 'success');
        },

        // 下载 PDF 格式
        async downloadPDF(filename) {
            if (typeof html2pdf === 'undefined') {
                this.showToast('PDF 导出功能暂不可用', 'error');
                return;
            }

            this.showToast('正在生成 PDF（处理图表中）...', 'info');

            try {
                // 获取渲染后的报告内容
                const reportElement = document.querySelector('.markdown-body');
                if (!reportElement) {
                    this.showToast('无法获取报告内容', 'error');
                    return;
                }

                // 创建临时容器用于PDF生成，避免影响原始DOM
                const tempContainer = document.createElement('div');
                tempContainer.innerHTML = reportElement.innerHTML;
                tempContainer.style.cssText = 'padding: 40px; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; line-height: 1.8; color: #1a1a1a;';

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

                const options = {
                    margin: [15, 15, 15, 15],
                    filename: `${filename}.pdf`,
                    image: { type: 'jpeg', quality: 0.98 },
                    html2canvas: {
                        scale: 2,
                        useCORS: true,
                        logging: false,
                        letterRendering: true
                    },
                    jsPDF: {
                        unit: 'mm',
                        format: 'a4',
                        orientation: 'portrait'
                    },
                    pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
                };

                await html2pdf().set(options).from(tempContainer).save();

                // 清理临时容器
                document.body.removeChild(tempContainer);

                this.showToast('PDF 文件已下载', 'success');
            } catch (error) {
                console.error('PDF 导出失败:', error);
                this.showToast('PDF 导出失败，请重试', 'error');
            }
        },

        // 下载 Word 格式
        async downloadDocx(filename) {
            if (typeof docx === 'undefined') {
                this.showToast('Word 导出功能暂不可用', 'error');
                return;
            }

            this.showToast('正在生成 Word 文档（处理图表中）...', 'info');

            try {
                const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, BorderStyle, ImageRun } = docx;

                // 先收集所有 Mermaid 图表的图片数据
                const mermaidImages = await this.collectMermaidImages();

                // 解析 Markdown 内容为文档段落
                const lines = this.reportContent.split('\n');
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
                saveAs(blob, `${filename}.docx`);

                this.showToast('Word 文档已下载', 'success');
            } catch (error) {
                console.error('Word 导出失败:', error);
                this.showToast('Word 导出失败，请重试', 'error');
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

        renderMarkdown(content) {
            if (!content) return '';

            if (typeof marked !== 'undefined') {
                // 使用 marked 渲染 Markdown
                let html = marked.parse(content);

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

                return html;
            }

            // 简单的 Markdown 渲染（无 marked.js 时的回退）
            return content
                .replace(/^### (.*$)/gm, '<h3>$1</h3>')
                .replace(/^## (.*$)/gm, '<h2>$1</h2>')
                .replace(/^# (.*$)/gm, '<h1>$1</h1>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/^- (.*$)/gm, '<li>$1</li>')
                .replace(/\n/g, '<br>');
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

                // 逐个渲染图表
                let successCount = 0;
                for (let i = 0; i < mermaidElements.length; i++) {
                    const element = mermaidElements[i];

                    // 跳过已经渲染为 SVG 的元素
                    if (element.querySelector('svg')) {
                        continue;
                    }

                    try {
                        const graphDefinition = element.textContent.trim();
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

                        // 后处理：修复黑色背景问题
                        const svgEl = element.querySelector('svg');
                        if (svgEl) {
                            // 设置 SVG 背景为白色
                            svgEl.style.backgroundColor = '#ffffff';
                            svgEl.style.background = '#ffffff';

                            // 获取 SVG 的 viewBox 并确保背景完全覆盖
                            const viewBox = svgEl.getAttribute('viewBox');
                            if (viewBox) {
                                const [x, y, width, height] = viewBox.split(' ').map(Number);
                                // 检查是否已有背景 rect
                                const firstRect = svgEl.querySelector('rect');
                                if (firstRect) {
                                    // 确保第一个 rect 是白色背景
                                    const fill = firstRect.getAttribute('fill');
                                    if (!fill || fill === '#000000' || fill === 'black' || fill === 'rgb(0, 0, 0)' || fill === 'none') {
                                        firstRect.setAttribute('fill', '#ffffff');
                                        firstRect.style.fill = '#ffffff';
                                    }
                                }
                            }

                            // 查找并修复所有黑色背景的 rect 元素
                            const rects = svgEl.querySelectorAll('rect');
                            rects.forEach((rect, idx) => {
                                const fill = rect.getAttribute('fill') || rect.style.fill;
                                // 第一个 rect 通常是背景
                                if (idx === 0) {
                                    rect.setAttribute('fill', '#ffffff');
                                    rect.style.fill = '#ffffff';
                                }
                                // 其他黑色填充的 rect 也改为白色
                                if (fill === '#000000' || fill === 'black' || fill === 'rgb(0, 0, 0)') {
                                    rect.setAttribute('fill', '#ffffff');
                                    rect.style.fill = '#ffffff';
                                }
                            });

                            // 移除可能的 style 标签中的黑色背景
                            const styles = svgEl.querySelectorAll('style');
                            styles.forEach(style => {
                                style.textContent = style.textContent.replace(/background:\s*#000000/g, 'background: #ffffff');
                                style.textContent = style.textContent.replace(/background-color:\s*#000000/g, 'background-color: #ffffff');
                            });
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
            this.currentView = view;
            this.selectedReport = null;
            if (view === 'sessions') {
                this.loadSessions();
            } else if (view === 'reports') {
                this.loadReports();
            }
        },

        exitInterview() {
            // 清理所有定时器，防止内存泄漏
            this.stopThinkingPolling();
            this.stopWebSearchPolling();
            this.submitting = false;

            this.currentView = 'sessions';
            this.currentSession = null;
            this.loadSessions();
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
            const modes = {
                quick: { formal: 2, followUp: 2, total: 8, range: "12-16" },
                standard: { formal: 3, followUp: 4, total: 16, range: "20-28" },
                deep: { formal: 4, followUp: 6, total: 24, range: "28-40" }
            };
            const mode = this.currentSession.interview_mode || 'standard';
            return modes[mode] || modes.standard;
        },

        // 获取当前问题总数
        getCurrentQuestionCount() {
            if (!this.currentSession) return 0;
            return this.currentSession.interview_log.length;
        },

        // 获取预估总问题数（中间值）
        getEstimatedTotalQuestions() {
            const config = this.getInterviewModeConfig();
            if (!config) return 24;
            const range = config.range.split('-');
            return Math.round((parseInt(range[0]) + parseInt(range[1])) / 2);
        },

        // 获取预估剩余问题数
        getEstimatedRemainingQuestions() {
            if (!this.currentSession) return 0;

            const progress = this.getTotalProgress();
            const current = this.getCurrentQuestionCount();

            // 基于进度反推剩余问题数
            // 如果进度是 25%，已答 53 题，则预估总数 = 53 / 0.25 = 212，剩余 = 212 - 53 = 159
            // 这样更准确反映实际情况
            if (progress > 0 && progress < 100) {
                const estimatedTotal = Math.round(current / (progress / 100));
                const remaining = Math.max(0, estimatedTotal - current);

                // 限制显示范围，避免数字过大
                if (remaining > 50) {
                    return '50+';
                }
                return remaining;
            } else if (progress >= 100) {
                return 0;
            } else {
                // 进度为0时，使用模式配置的预估
                const config = this.getInterviewModeConfig();
                if (!config) return 20;
                const range = config.range.split('-');
                return Math.round((parseInt(range[0]) + parseInt(range[1])) / 2);
            }
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

        // ============ 会话列表筛选和分页 ============

        // 搜索输入防抖
        onSessionSearchInput() {
            if (this.searchDebounceTimer) {
                clearTimeout(this.searchDebounceTimer);
            }
            this.searchDebounceTimer = setTimeout(() => {
                this.filterSessions();
            }, 300);
        },

        // 筛选和排序会话
        filterSessions() {
            let result = [...this.sessions];

            // 按搜索关键词筛选
            if (this.sessionSearchQuery.trim()) {
                const query = this.sessionSearchQuery.toLowerCase();
                result = result.filter(s =>
                    s.topic?.toLowerCase().includes(query) ||
                    s.scenario_config?.name?.toLowerCase().includes(query)
                );
            }

            // 按状态筛选
            if (this.sessionStatusFilter !== 'all') {
                result = result.filter(s => s.status === this.sessionStatusFilter);
            }

            // 排序
            switch (this.sessionSortOrder) {
                case 'newest':
                    result.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                    break;
                case 'oldest':
                    result.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
                    break;
                case 'progress':
                    result.sort((a, b) => this.getSessionTotalProgress(b) - this.getSessionTotalProgress(a));
                    break;
            }

            this.filteredSessions = result;
            this.currentPage = 1;  // 重置到第一页
        },

        // 分页相关计算属性
        get totalPages() {
            return Math.ceil(this.filteredSessions.length / this.pageSize);
        },

        get paginatedSessions() {
            const start = (this.currentPage - 1) * this.pageSize;
            const end = start + this.pageSize;
            return this.filteredSessions.slice(start, end);
        },

        get paginationStart() {
            if (this.filteredSessions.length === 0) return 0;
            return (this.currentPage - 1) * this.pageSize + 1;
        },

        get paginationEnd() {
            return Math.min(this.currentPage * this.pageSize, this.filteredSessions.length);
        },

        get visiblePages() {
            const pages = [];
            const total = this.totalPages;
            const current = this.currentPage;

            if (total <= 7) {
                for (let i = 1; i <= total; i++) pages.push(i);
            } else {
                if (current <= 3) {
                    pages.push(1, 2, 3, 4, '...', total);
                } else if (current >= total - 2) {
                    pages.push(1, '...', total - 3, total - 2, total - 1, total);
                } else {
                    pages.push(1, '...', current - 1, current, current + 1, '...', total);
                }
            }
            return pages;
        },

        goToPage(page) {
            if (page >= 1 && page <= this.totalPages) {
                this.currentPage = page;
                // 滚动到列表顶部
                const listEl = document.querySelector('[x-if="currentView === \'sessions\'"]');
                if (listEl) {
                    listEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        },

        // 判断当前会话是否为评估场景
        isAssessmentSession() {
            return this.currentSession?.scenario_config?.report?.type === 'assessment';
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

        // 场景自动识别（防抖触发）
        onTopicInput() {
            // 清除之前的定时器
            if (this.recognizeTimer) {
                clearTimeout(this.recognizeTimer);
            }

            const topic = this.newSessionTopic.trim();

            // 主题少于 2 个字符时不触发识别
            if (topic.length < 2) {
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

            this.recognizing = true;
            try {
                const result = await this.apiCall('/scenarios/recognize', {
                    method: 'POST',
                    body: JSON.stringify({
                        topic,
                        description: this.newSessionDescription.trim() || ''
                    })
                });

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
            this.selectedScenario = null;
            this.recognizedResult = null;
            this.autoRecognizeEnabled = true;
            this.showScenarioSelector = false;
            this.scenarioSearchQuery = '';
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
            ]
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

        // 打开自定义场景编辑器
        openCustomScenarioEditor() {
            this.customScenario = {
                name: '',
                description: '',
                dimensions: [
                    { id: 'dim_1', name: '', description: '', key_aspects: '' }
                ]
            };
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

                await this.apiCall('/scenarios/custom', {
                    method: 'POST',
                    body: JSON.stringify({
                        name,
                        description: this.customScenario.description.trim(),
                        dimensions
                    })
                });

                await this.loadScenarios();
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
            if (!confirm(`确定要删除场景「${scenarioName}」吗？`)) return;
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
                        dimensions
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

        getStatusBadgeClass(status) {
            const classes = {
                'in_progress': 'status-in-progress',
                'completed': 'status-completed',
                'paused': 'bg-yellow-100 text-yellow-700'
            };
            return classes[status] || 'bg-gray-100 text-gray-700';
        },

        getStatusText(status) {
            const texts = {
                'in_progress': '进行中',
                'completed': '已完成',
                'paused': '已暂停'
            };
            return texts[status] || status;
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

        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => {
                this.toast.show = false;
            }, 4000);
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
}

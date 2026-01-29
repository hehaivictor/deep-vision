/**
 * Deep Vision - AI 驱动的智能需求调研前端
 *
 * 核心功能：
 * - 调用后端 AI API 动态生成问题和选项
 * - 支持智能追问（挖掘本质需求）
 * - 支持冲突检测（与参考文档对比）
 * - 生成专业调研报告
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
        webSearching: false,  // Web Search API 调用状态
        webSearchPollInterval: null,  // Web Search 状态轮询定时器
        quoteRotationInterval: null,  // 诗句轮播定时器

        // ========== 方案B+D 新增状态变量 ==========
        thinkingStage: null,           // 思考阶段数据
        thinkingPollInterval: null,    // 轮询定时器
        currentTipIndex: 0,            // 调研小技巧当前索引
        skeletonMode: false,           // 骨架填充模式
        typingText: '',                // 打字机文字
        typingComplete: false,         // 打字完成标记
        optionsVisible: [],            // 选项可见性数组
        interactionReady: false,       // 交互就绪标记
        prefetchHit: false,            // 预生成命中标记

        // 服务状态
        serverStatus: null,
        aiAvailable: false,

        // 会话相关
        sessions: [],
        currentSession: null,
        newSessionTopic: '',
        newSessionDescription: '',
        selectedInterviewMode: 'standard',  // 默认标准模式
        showNewSessionModal: false,
        showDeleteModal: false,
        sessionToDelete: null,

        // 确认重新调研对话框
        showRestartModal: false,

        // 确认删除文档对话框
        showDeleteDocModal: false,
        docToDelete: null,
        docDeleteCallback: null,

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

            // 安全访问配置中的调研小技巧
            const tips = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.researchTips)
                ? SITE_CONFIG.researchTips : [];
            if (tips.length > 0) {
                this.currentTipIndex = Math.floor(Math.random() * tips.length);
            }

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
            this.prefetchHit = result.prefetched || false;

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
            } catch (error) {
                this.showToast('加载会话列表失败', 'error');
            } finally {
                this.loading = false;
            }
        },

        async createNewSession() {
            if (!this.newSessionTopic.trim()) return;

            try {
                const session = await this.apiCall('/sessions', {
                    method: 'POST',
                    body: JSON.stringify({
                        topic: this.newSessionTopic,
                        description: this.newSessionDescription.trim() || null,
                        interview_mode: this.selectedInterviewMode
                    })
                });

                this.sessions.unshift(session);
                this.currentSession = session;
                this.showNewSessionModal = false;
                this.newSessionTopic = '';
                this.newSessionDescription = '';
                this.selectedInterviewMode = 'standard';  // 重置为默认值
                this.currentStep = 0;
                this.currentView = 'interview';
                this.showToast('会话创建成功', 'success');
            } catch (error) {
                this.showToast('创建会话失败', 'error');
            }
        },

        async openSession(sessionId) {
            try {
                this.currentSession = await this.apiCall(`/sessions/${sessionId}`);
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
                    this.currentDimension = 'customer_needs';
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
            const files = event.target.files;
            if (!files.length || !this.currentSession) return;

            // 允许的文件类型
            const allowedTypes = ['.md', '.txt', '.pdf', '.docx', '.xlsx', '.pptx', '.png', '.jpg', '.jpeg', '.gif', '.webp'];

            for (const file of files) {
                // 验证文件类型
                const ext = '.' + file.name.split('.').pop().toLowerCase();
                if (!allowedTypes.includes(ext)) {
                    this.showToast(`不支持的文件类型: ${ext}`, 'error');
                    continue;
                }

                // 验证文件大小（10MB）
                if (file.size > 10 * 1024 * 1024) {
                    this.showToast(`文件 ${file.name} 超过10MB限制`, 'error');
                    continue;
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

            event.target.value = '';
        },

        async removeDocument(index) {
            console.log('removeDocument 被调用，index:', index);

            if (!this.currentSession || !this.currentSession.reference_docs) {
                console.log('没有当前会话或参考文档');
                return;
            }

            const doc = this.currentSession.reference_docs[index];
            console.log('准备删除文档:', doc.name);

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

        // ============ 已有调研成果上传 ============
        async uploadResearchDoc(event) {
            const files = event.target.files;
            if (!files.length || !this.currentSession) return;

            for (const file of files) {
                const formData = new FormData();
                formData.append('file', file);

                try {
                    const response = await fetch(
                        `${API_BASE}/sessions/${this.currentSession.session_id}/research-docs`,
                        { method: 'POST', body: formData }
                    );

                    if (response.ok) {
                        const result = await response.json();
                        // 刷新会话数据
                        this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);
                        this.showToast(`调研成果 ${file.name} 上传成功`, 'success');
                    } else {
                        throw new Error('上传失败');
                    }
                } catch (error) {
                    this.showToast(`上传 ${file.name} 失败`, 'error');
                }
            }

            event.target.value = '';
        },

        async removeResearchDoc(index) {
            console.log('removeResearchDoc 被调用，index:', index);

            if (!this.currentSession || !this.currentSession.research_docs) {
                console.log('没有当前会话或调研成果文档');
                return;
            }

            const doc = this.currentSession.research_docs[index];
            console.log('准备删除调研成果:', doc.name);

            // 使用自定义确认对话框
            this.docToDelete = doc;
            this.docDeleteCallback = async () => {
                try {
                    const response = await fetch(
                        `${API_BASE}/sessions/${this.currentSession.session_id}/research-docs/${encodeURIComponent(doc.name)}`,
                        { method: 'DELETE' }
                    );

                    if (response.ok) {
                        // 刷新会话数据
                        this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);
                        this.showToast(`调研成果 ${doc.name} 已删除`, 'success');
                    } else {
                        throw new Error('删除失败');
                    }
                } catch (error) {
                    console.error('删除调研成果错误:', error);
                    this.showToast(`删除调研成果失败`, 'error');
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
                        this.showToast('所有维度调研完成！', 'success');
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

        // ============ 重新调研 ============
        confirmRestartResearch() {
            this.showRestartModal = true;
        },

        async restartResearch() {
            if (!this.currentSession) return;
            this.showRestartModal = false;

            try {
                const result = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/restart-research`,
                    { method: 'POST' }
                );

                if (result.success) {
                    // 刷新会话数据
                    this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);

                    // 重置前端状态
                    this.currentStep = 0;
                    this.currentDimension = 'customer_needs';
                    this.currentQuestion = null;
                    this.currentOptions = [];

                    this.showToast('已保存当前调研成果，开始新一轮调研', 'success');
                } else {
                    this.showToast('重新调研失败', 'error');
                }
            } catch (error) {
                console.error('重新调研错误:', error);
                this.showToast('重新调研失败', 'error');
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

        // 当报告内容渲染完成后调用（由 x-effect 触发）
        onReportRendered() {
            console.log('📄 报告内容已渲染，开始处理 Mermaid 图表');
            this.renderMermaidCharts();
        },

        downloadReport() {
            if (!this.reportContent || !this.selectedReport) return;

            const blob = new Blob([this.reportContent], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = this.selectedReport;
            a.click();
            URL.revokeObjectURL(url);
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
                    console.log('ℹ️ 没有需要渲染的 Mermaid 图表');
                    return;
                }

                console.log(`🎨 发现 ${mermaidElements.length} 个 Mermaid 图表，开始渲染...`);

                // 逐个渲染图表
                let successCount = 0;
                for (let i = 0; i < mermaidElements.length; i++) {
                    const element = mermaidElements[i];

                    // 跳过已经渲染为 SVG 的元素
                    if (element.querySelector('svg')) {
                        console.log(`  ⏭️  图表 ${i + 1} 已渲染，跳过`);
                        continue;
                    }

                    try {
                        const graphDefinition = element.textContent.trim();
                        const id = `mermaid-${Date.now()}-${i}`;

                        // 预处理：修复常见的语法问题
                        let fixedDefinition = graphDefinition;

                        // 修复1：检测 quadrantChart 的中文（quadrantChart 对中文支持不好，需要转换）
                        if (fixedDefinition.includes('quadrantChart')) {
                            console.log(`  ⚠️  图表 ${i + 1} 是 quadrantChart，检查并修复中文...`);

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
                                    console.log(`    📝 将 "${chineseName.trim()}" 替换为 "${englishName}"`);
                                    return `    ${englishName}: [`;
                                }
                            );

                            // 确保至少有一个数据点
                            if (!/\w+:\s*\[\s*[\d.]+\s*,\s*[\d.]+\s*\]/.test(fixedDefinition)) {
                                console.log(`    ⚠️  未发现数据点，添加默认数据点`);
                                fixedDefinition += '\n    Sample: [0.5, 0.5]';
                            }

                            console.log(`  ✏️  quadrantChart 已将中文标签转换为英文（quadrantChart 限制）`);
                        }

                        // 修复2：检测 flowchart/graph 中的语法问题（保留中文显示）
                        if (fixedDefinition.match(/^(graph|flowchart)\s/m)) {
                            console.log(`  ⚠️  图表 ${i + 1} 是 flowchart/graph，检查语法...`);

                            // 修复 HTML 标签（如 <br>）为换行符
                            fixedDefinition = fixedDefinition.replace(/<br\s*\/?>/gi, ' ');

                            // 检查是否有未闭合的 subgraph（缺少 end）
                            const subgraphCount = (fixedDefinition.match(/subgraph\s/g) || []).length;
                            const endCount = (fixedDefinition.match(/\bend\b/g) || []).length;
                            if (subgraphCount > endCount) {
                                console.log(`    ⚠️  检测到 ${subgraphCount - endCount} 个未闭合的 subgraph，自动添加 end`);
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

                            console.log(`  ✅ flowchart/graph 语法检查完成，保留中文显示`);
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
                        console.log(`  ✅ 图表 ${i + 1}/${mermaidElements.length} 渲染成功`);
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

                console.log(`✅ Mermaid 渲染完成：${successCount}/${mermaidElements.length} 成功`);
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

            const progress = this.getTotalProgress();
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

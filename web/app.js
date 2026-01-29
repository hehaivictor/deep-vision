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

// ============ 登录（OIDC 完整流程）============
// 说明：
// - 未登录：跳转到后台给出的 OIDC 登录地址
// - 登录完成：Keycloak 会带着 ?code=... 重定向回 redirect_uri
// - 用 code 换取 access_token，再用 access_token 获取用户信息
const OIDC_BASE_URL = 'http://192.168.31.101:8888/realms/deep-vision-dev/protocol/openid-connect';
const OIDC_TOKEN_URL = `${OIDC_BASE_URL}/token`;
const OIDC_USERINFO_URL = `${OIDC_BASE_URL}/userinfo`;
const CLIENT_ID = 'deep-vision-frontend';
const AUTH_STORAGE_KEY = 'dv_auth';
const USERINFO_STORAGE_KEY = 'dv_userinfo';
const RETURN_TO_KEY = 'dv_return_to';
const CALLBACK_PROCESSED_KEY = 'dv_callback_processed';  // 防止重复处理回调

// 动态获取 redirect_uri（支持本地和线上部署）
function getRedirectUri() {
    // 使用当前页面的 origin，自动适配本地和线上环境
    return window.location.origin;
}

// 动态构建登录 URL
function buildOidcLoginUrl() {
    // 1. 获取当前页面的完整地址（自动适配本地和线上环境）
    const redirectUri = getRedirectUri();  // 例如: "http://192.168.80.19:5001/" 或线上地址
    
    // 2. 对 redirect_uri 进行 URL 编码（因为 URL 参数中不能直接包含特殊字符）
    // encodeURIComponent 会将 "http://192.168.80.19:5001/" 编码为 "http%3A%2F%2F192.168.80.19%3A5001%2F"
    // const encodedRedirectUri = encodeURIComponent(redirectUri);
    
    // 3. 构建完整的 OIDC 授权 URL
    // redirect_uri 参数必须是编码后的值，这样 Keycloak 才能正确解析
    return `${OIDC_BASE_URL}/auth?client_id=${CLIENT_ID}&redirect_uri=${redirectUri}&response_type=code&scope=openid`;
}

function getAuthState() {
    try {
        const raw = localStorage.getItem(AUTH_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

function setAuthState(next) {
    try {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(next));
    } catch {
        // ignore
    }
}

function clearAuthState() {
    try {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        clearUserInfo();  // 同时清除用户信息
    } catch {
        // ignore
    }
}

// 用 code 换取 access_token
async function exchangeCodeForToken(code) {
    try {
        const params = new URLSearchParams();
        params.append('grant_type', 'authorization_code');
        params.append('code', code);
        params.append('client_id', CLIENT_ID);
        params.append('client_secret', '');  // 根据图片，client_secret 为空
        params.append('redirect_uri', getRedirectUri());  // 使用动态获取的 redirect_uri

        const response = await fetch(OIDC_TOKEN_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: params.toString()
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Token 交换失败:', response.status, errorText);
            throw new Error(`Token 交换失败: ${response.status}`);
        }

        const tokenData = await response.json();
        return tokenData;
    } catch (error) {
        console.error('Token 交换异常:', error);
        throw error;
    }
}

// 用 access_token 获取用户信息
async function fetchUserInfo(accessToken) {
    try {
        const response = await fetch(OIDC_USERINFO_URL, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('获取用户信息失败:', response.status, errorText);
            throw new Error(`获取用户信息失败: ${response.status}`);
        }

        const userInfo = await response.json();
        return userInfo;
    } catch (error) {
        console.error('获取用户信息异常:', error);
        throw error;
    }
}

function getUserInfo() {
    try {
        const raw = localStorage.getItem(USERINFO_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

function setUserInfo(userInfo) {
    try {
        localStorage.setItem(USERINFO_STORAGE_KEY, JSON.stringify(userInfo));
    } catch {
        // ignore
    }
}

function clearUserInfo() {
    try {
        localStorage.removeItem(USERINFO_STORAGE_KEY);
    } catch {
        // ignore
    }
}

function isLoggedIn() {
    const s = getAuthState();
    // 判断：必须有 access_token 且未过期
    if (!s || !s.access_token) {
        return false;
    }
    // 检查 access_token 是否过期（expires_in 是秒数）
    if (s.expires_at && Date.now() >= s.expires_at) {
        // token 已过期，清除登录状态
        clearAuthState();
        clearUserInfo();
        return false;
    }
    return true;
}

function saveReturnTo(url) {
    try {
        localStorage.setItem(RETURN_TO_KEY, url);
    } catch {
        // ignore
    }
}

function loadReturnTo() {
    try {
        return localStorage.getItem(RETURN_TO_KEY);
    } catch {
        return null;
    }
}

function clearReturnTo() {
    try {
        localStorage.removeItem(RETURN_TO_KEY);
    } catch {
        // ignore
    }
}

function buildLoginUrl() {
    // 追加 state 用于回跳
    // state 里存一个随机值，实际回跳地址存在 localStorage（避免 URL 过长）
    const state = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
    return `${buildOidcLoginUrl()}&state=${encodeURIComponent(state)}`;
}

function redirectToLogin() {
    // 记录当前地址（去掉 code/state 等参数，避免循环）
    const url = new URL(window.location.href);
    // 移除 OIDC 回调相关的查询参数
    url.searchParams.delete('code');
    url.searchParams.delete('state');
    url.searchParams.delete('session_state');
    url.searchParams.delete('iss');
    saveReturnTo(url.toString());
    window.location.replace(buildLoginUrl());
}

// 返回值：
// - "none": 不是回调
// - "redirecting": 已触发跳转（例如去登录页）
// - "processed": 已完成 code->token->userinfo，并清理了 URL（无需刷新/跳转）
async function handleCallbackIfNeeded() {
    // Keycloak 跳转回来时，code 可能在根路径 / 或 /callback
    // 检查 URL 中是否有 code 参数（而不是只检查路径）
    const qs = new URLSearchParams(window.location.search || '');
    const code = qs.get('code');
    const error = qs.get('error');
    const errorDescription = qs.get('error_description');

    // 如果没有 code 也没有 error，说明不是回调
    if (!code && !error) {
        // 检查 URL 中是否还有 OIDC 相关参数（可能是残留的）
        const hasOidcParams = qs.has('state') || qs.has('session_state') || qs.has('iss');
        if (hasOidcParams) {
            // 清理残留的 OIDC 参数（不刷新页面）
            const cleanUrl = new URL(window.location.href);
            cleanUrl.searchParams.delete('code');
            cleanUrl.searchParams.delete('state');
            cleanUrl.searchParams.delete('session_state');
            cleanUrl.searchParams.delete('iss');
            window.history.replaceState({}, '', cleanUrl.toString());
        }
        return "none";
    }

    // 防止重复处理：如果当前 code 已经处理过，直接清理 URL 并返回
    const processedCode = sessionStorage.getItem(CALLBACK_PROCESSED_KEY);
    if (processedCode === code) {
        // 已经处理过这个 code，只需要清理 URL（不刷新）
        const cleanUrl = new URL(window.location.origin + window.location.pathname);
        cleanUrl.searchParams.delete('code');
        cleanUrl.searchParams.delete('state');
        cleanUrl.searchParams.delete('session_state');
        cleanUrl.searchParams.delete('iss');
        window.history.replaceState({}, '', cleanUrl.toString());
        return "processed";
    }

    // 处理错误情况
    if (error) {
        clearAuthState();
        console.error('登录失败:', error, errorDescription);
        redirectToLogin();
        return "redirecting";
    }

    // 处理成功情况：有 code
    if (code) {
        // 立即标记这个 code 已经处理过（防止重复处理）
        try {
            sessionStorage.setItem(CALLBACK_PROCESSED_KEY, code);
        } catch {}

        try {
            // 1. 用 code 换取 access_token
            console.log('正在用 code 换取 access_token...');
            const tokenData = await exchangeCodeForToken(code);
            
            // 2. 用 access_token 获取用户信息
            console.log('正在获取用户信息...');
            const userInfo = await fetchUserInfo(tokenData.access_token);
            
            // 3. 保存 token 信息（计算过期时间）
            const expiresAt = tokenData.expires_in 
                ? Date.now() + (tokenData.expires_in * 1000) 
                : null;
            
            setAuthState({
                loggedIn: true,
                access_token: tokenData.access_token,
                refresh_token: tokenData.refresh_token,
                token_type: tokenData.token_type,
                expires_in: tokenData.expires_in,
                expires_at: expiresAt,
                refresh_expires_in: tokenData.refresh_expires_in,
                id_token: tokenData.id_token,
                receivedAt: Date.now()
            });
            
            // 4. 保存用户信息到本地缓存
            setUserInfo(userInfo);
            console.log('登录成功，用户信息已保存:', userInfo);

            // 5. 获取回跳地址（去掉所有 OIDC 参数）
            const returnTo = loadReturnTo();
            clearReturnTo();

            // 6. 构建干净的 URL（最终地址不带任何参数）
            // 你要求“跳回 redirect_uri 不要带参数”，所以这里用 history.replaceState 清理地址栏。
            // 默认回到当前 origin + pathname（即 redirect_uri），必要时回到 returnTo。
            const cleanUrl = new URL(returnTo || (window.location.origin + window.location.pathname));
            cleanUrl.searchParams.delete('code');
            cleanUrl.searchParams.delete('state');
            cleanUrl.searchParams.delete('session_state');
            cleanUrl.searchParams.delete('iss');

            // 7. 只清理地址栏，不进行页面跳转/刷新
            window.history.replaceState({}, '', cleanUrl.toString());
            return "processed";
        } catch (error) {
            console.error('登录流程失败:', error);
            clearAuthState();
            // 登录失败，重新跳转到登录页
            redirectToLogin();
            return "redirecting";
        }
    }

    // 理论上不会到这里，但为了安全
    return "none";
}

function deepVision() {
    return {
        // ============ 状态 ============
        currentView: 'sessions',
        loading: false,
        loadingQuestion: false,
        isGoingPrev: false,
        generatingReport: false,
        webSearching: false,  // Web Search API 调用状态
        webSearchPollInterval: null,  // Web Search 状态轮询定时器

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
            // 1) 优先处理 OIDC 回调（检查 URL 中是否有 code 参数）
            // Keycloak 登录成功后会跳转回 redirect_uri，URL 中会带有 code 和 state 参数
            // 需要先处理这些参数：用 code 换取 access_token，获取用户信息，然后清理 URL
            const callbackResult = await handleCallbackIfNeeded();
            // - processed：已完成换 token + 拉 userinfo，并清理地址栏（不需要返回，继续初始化页面）
            // - redirecting：已触发跳转（去登录页等），直接结束 init
            // - none：不是回调，继续正常流程
            if (callbackResult === "redirecting") {
                return;
            }

            // 2) 非回调页面：检查登录状态，未登录则跳转到后台登录地址
            if (!isLoggedIn()) {
                redirectToLogin();
                return;
            }

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

            setInterval(() => {
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
            if (this.webSearchPollInterval) return;  // 已在轮询中

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
            if (this.thinkingPollInterval) return;  // 已在轮询中

            // 每次等待随机选一条调研小技巧
            this.currentTipIndex = Math.floor(Math.random() * SITE_CONFIG.researchTips.length);

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

            const questionText = result.question || '';
            const options = result.options || [];

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
                    const error = await response.json();
                    throw new Error(error.error || '请求失败');
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
                        description: this.newSessionDescription.trim() || null
                    })
                });

                this.sessions.unshift(session);
                this.currentSession = session;
                this.showNewSessionModal = false;
                this.newSessionTopic = '';
                this.newSessionDescription = '';
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
                this.currentStep = this.currentSession.interview_log.length > 0 ? 1 : 0;
                this.currentDimension = this.getNextIncompleteDimension();
                // 先切换到访谈视图，让用户看到加载状态
                this.currentView = 'interview';
                if (this.currentStep === 1) {
                    // 再获取下一个问题（会显示加载动画）
                    await this.fetchNextQuestion();
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

            for (const file of files) {
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
                        throw new Error('上传失败');
                    }
                } catch (error) {
                    this.showToast(`上传 ${file.name} 失败`, 'error');
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
            this.currentStep = 1;
            this.currentDimension = 'customer_needs';
            this.fetchNextQuestion();
        },

        getNextIncompleteDimension() {
            for (const dim of this.dimensionOrder) {
                if (this.currentSession.dimensions[dim].coverage < 100) {
                    return dim;
                }
            }
            return this.dimensionOrder[0];
        },

        async fetchNextQuestion() {
            this.loadingQuestion = true;
            this.skeletonMode = false;
            this.interactionReady = false;
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
                    // 当前维度已完成，切换到下一个
                    const currentIdx = this.dimensionOrder.indexOf(this.currentDimension);
                    for (let i = 1; i <= this.dimensionOrder.length; i++) {
                        const nextDim = this.dimensionOrder[(currentIdx + i) % this.dimensionOrder.length];
                        if (this.currentSession.dimensions[nextDim].coverage < 100) {
                            this.currentDimension = nextDim;
                            await this.fetchNextQuestion();
                            return;
                        }
                    }
                    // 所有维度都完成
                    this.currentQuestion = {
                        text: '所有问题已完成！您可以确认需求并生成报告。',
                        options: [],
                        multiSelect: false,
                        aiGenerated: false
                    };
                    this.interactionReady = true;
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

            // 构建答案
            let answer;
            if (this.currentQuestion.multiSelect) {
                // 多选：合并所有选中的答案
                const answers = [...this.selectedAnswers];
                if (this.otherSelected && this.otherAnswerText.trim()) {
                    answers.push(this.otherAnswerText.trim());
                }
                answer = answers.join('；');  // 使用中文分号分隔
            } else {
                // 单选
                answer = this.otherSelected ? this.otherAnswerText.trim() : this.selectedAnswers[0];
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
                if (this.currentSession.dimensions[this.currentDimension].coverage >= 100) {
                    this.currentDimension = this.getNextIncompleteDimension();
                }

                // 获取下一个问题
                await this.fetchNextQuestion();

            } catch (error) {
                console.error('提交回答错误:', error);
                this.showToast(`提交回答失败: ${error.message}`, 'error');
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
            return this.currentSession && this.currentSession.interview_log.length > 0;
        },

        async goPrevQuestion() {
            if (!this.canGoPrevQuestion()) return;

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
            }
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
            this.currentView = 'sessions';
            this.currentSession = null;
            this.loadSessions();
        },

        getTotalProgress() {
            if (!this.currentSession) return 0;
            const dims = Object.values(this.currentSession.dimensions);
            const total = dims.reduce((sum, d) => sum + (d.coverage || 0), 0);
            return Math.round(total / dims.length);
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

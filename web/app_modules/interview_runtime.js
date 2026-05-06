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

    function createDefaultQuestionState() {
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
        };
    }

    const interviewRuntimeDefaults = {
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
        isGoingPrev: false,
        submitting: false,
        webSearching: false,
        webSearchPollInterval: null,
        currentTipIndex: 0,
        currentTip: '',
        tipRotationInterval: null,
        thinkingStage: null,
        thinkingPollInterval: null,
        skeletonMode: false,
        typingText: '',
        typingComplete: false,
        optionsVisible: [],
        interactionReady: false,
        currentStep: 0,
        currentDimension: 'customer_needs',
        currentQuestion: createDefaultQuestionState(),
        selectedAnswers: [],
        rationaleText: '',
        otherAnswerText: '',
        otherSelected: false,
        assistantChatExpanded: false,
        assistantChatInput: '',
        assistantChatLoading: false,
        assistantChatError: '',
        assistantChatRetryMessage: '',
        assistantChatMessages: [],
        assistantChatQuestionFingerprint: '',
    };

    const interviewRuntimeMethods = {
        startWebSearchPolling(requestId = this.questionRequestId) {
            this.stopWebSearchPolling();
            const currentRequestId = Number(requestId) || 0;
            this.webSearchPollRequestId = currentRequestId;

            const pollInterval = (typeof SITE_CONFIG !== 'undefined' && SITE_CONFIG.api?.webSearchPollInterval)
                ? SITE_CONFIG.api.webSearchPollInterval
                : 200;

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
                } catch (_error) {
                }
            }, pollInterval);
        },

        stopWebSearchPolling() {
            if (this.webSearchPollInterval) {
                clearInterval(this.webSearchPollInterval);
                this.webSearchPollInterval = null;
            }
            this.webSearchPollRequestId = 0;
            this.webSearching = false;
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

        startThinkingPolling(requestId = this.questionRequestId) {
            this.stopThinkingPolling(false);
            const currentRequestId = Number(requestId) || 0;
            this.thinkingPollRequestId = currentRequestId;

            const pollInterval = 300;

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
                } catch (_error) {
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

        async startSkeletonFill(result) {
            const questionText = result.question || '';
            const options = result.options || [];
            const aiRecommendation = this.normalizeAiRecommendation(result);
            const allowsFreeText = result.report_readiness_resume === true
                || result.answer_mode === 'free_text'
                || result.answer_mode === 'pick_with_reason';

            if (!questionText || (options.length === 0 && !allowsFreeText)) {
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

            this.skeletonMode = true;
            this.typingText = '';
            this.typingComplete = false;
            this.optionsVisible = [];
            this.interactionReady = false;

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
            this.syncInterviewAssistantChatForCurrentQuestion();

            const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            const disableTypingEffect = (typeof SITE_CONFIG !== 'undefined'
                && SITE_CONFIG?.motion?.reducedMotion?.disableTypingEffect === true);

            if (prefersReducedMotion || disableTypingEffect) {
                this.typingText = questionText;
                this.typingComplete = true;
                this.optionsVisible = options.map((_, i) => i);
                this.interactionReady = true;
                this.skeletonMode = false;
            } else {
                const typingSpeed = QUESTION_TYPING_CHAR_DELAY_MS;
                for (let i = 0; i <= questionText.length; i++) {
                    this.typingText = questionText.substring(0, i);
                    await new Promise(resolve => setTimeout(resolve, typingSpeed));
                }
                this.typingComplete = true;

                const optionDelay = QUESTION_OPTION_REVEAL_DELAY_MS;
                for (let i = 0; i < options.length; i++) {
                    this.optionsVisible.push(i);
                    await new Promise(resolve => setTimeout(resolve, optionDelay));
                }

                await new Promise(resolve => setTimeout(resolve, QUESTION_INTERACTION_READY_DELAY_MS));
                this.interactionReady = true;
                this.skeletonMode = false;
            }
        },

        buildInterviewSessionPlaceholder(sessionId) {
            const sessionSummary = this.findSessionSummaryById(sessionId) || {};
            const rawDimensions = (sessionSummary?.dimensions && typeof sessionSummary.dimensions === 'object')
                ? JSON.parse(JSON.stringify(sessionSummary.dimensions))
                : {};
            const placeholderDimensionKeys = Array.isArray(sessionSummary?.scenario_config?.dimensions)
                ? sessionSummary.scenario_config.dimensions
                    .map((item) => String(item?.id || '').trim())
                    .filter(Boolean)
                : [...this.dimensionOrder];
            const dimensions = { ...rawDimensions };
            placeholderDimensionKeys.forEach((dimKey) => {
                if (!dimensions[dimKey] || typeof dimensions[dimKey] !== 'object') {
                    dimensions[dimKey] = {
                        coverage: 0,
                        items: [],
                        score: null,
                    };
                }
            });
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
                this.replaceAppEntryRoute({
                    view: 'interview',
                    session: sessionId,
                });
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
                this.replaceAppEntryRoute({
                    view: 'interview',
                    session: sessionId,
                });

                const nextDim = this.getNextIncompleteDimension();
                if (!nextDim && this.currentSession.interview_log.length > 0) {
                    this.clearInterviewLoadingState();
                    this.currentStep = 2;
                    this.currentDimension = this.dimensionOrder[this.dimensionOrder.length - 1];
                    this.currentQuestion = this.createQuestionState();
                    this.aiRecommendationExpanded = false;
                    this.aiRecommendationApplied = false;
                    this.aiRecommendationPrevSelection = null;
                } else if (this.currentSession.interview_log.length > 0) {
                    this.currentStep = 1;
                    this.currentDimension = nextDim;
                    await this.fetchNextQuestion({ force: true });
                } else {
                    this.clearInterviewLoadingState();
                    this.currentStep = 0;
                    this.currentDimension = this.dimensionOrder[0] || 'customer_needs';
                }

                void this.restoreReportGenerationState(this.currentSession?.session_id || '');
                this.scheduleAppShellSnapshotPersist();
            } catch (_error) {
                if (openRequestId !== this.sessionOpenRequestId) {
                    return;
                }
                this.clearInterviewLoadingState();
                this.currentView = 'sessions';
                this.currentSession = null;
                this.replaceAppEntryRoute();
                this.refreshSessionsView();
                this.showToast('加载会话失败', 'error');
            }
        },

        startInterview() {
            const nextDim = this.getNextIncompleteDimension();
            if (!nextDim) {
                this.currentStep = 2;
                this.currentQuestion = this.createQuestionState();
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                return;
            }

            this.currentStep = 1;
            this.currentDimension = nextDim;
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
            let overloadWaitMs = 0;
            let overloadRetryCount = 0;
            this.recordQuestionOpsRequestStart({
                dimension: this.currentDimension,
                preferPrefetch
            });
            this.loadingQuestion = true;
            this.skeletonMode = false;
            this.interactionReady = false;
            this.startTipRotation();
            this.currentQuestion = this.createQuestionState();
            this.aiRecommendationExpanded = false;
            this.aiRecommendationApplied = false;
            this.aiRecommendationPrevSelection = null;
            this.resetInterviewAssistantChatState();
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
            this.startThinkingPolling(requestId);
            this.startWebSearchPolling(requestId);
            this.selectedAnswers = [];
            this.rationaleText = '';
            this.otherAnswerText = '';
            this.otherSelected = false;
            this.resetSingleSelectDisambiguation();

            try {
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
                    const hasUsableFreeTextQuestion = Boolean(
                        typeof result.question === 'string'
                        && result.question.trim()
                        && Array.isArray(result.options)
                        && result.options.length === 0
                        && (
                            result.report_readiness_resume === true
                            || result.answer_mode === 'free_text'
                            || result.answer_mode === 'pick_with_reason'
                        )
                    );

                    if (!result.completed && !hasUsableQuestion && !hasUsableFreeTextQuestion) {
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

                    await new Promise(resolve => setTimeout(resolve, QUESTION_SUCCESS_TRANSITION_DELAY_MS));

                    this.loadingQuestion = false;
                    this.thinkingStage = null;
                    this.stopTipRotation();

                    if (result.completed) {
                        this.recordQuestionOpsOutcome('completed', {
                            decisionMeta: result.decision_meta || null,
                            overloadRetryCount,
                            overloadWaitMs
                        });
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
                this.interactionReady = true;
            } finally {
                if (this.questionRequestAbortController === activeRequestAbortController) {
                    this.questionRequestAbortController = null;
                }
                if (requestId === this.questionRequestId) {
                    this.questionRequestPreferPrefetch = false;
                    this.stopQuestionRequestGuard();
                    this.stopThinkingPolling();
                    this.stopWebSearchPolling();
                    this.loadingQuestion = false;
                    this.isGoingPrev = false;
                }
                this.refreshOpsMetricsIfVisible();
            }
        },

        buildInterviewAssistantQuestionFingerprint({
            dimension = '',
            question = '',
            options = [],
            answerMode = ''
        } = {}) {
            const source = JSON.stringify({
                dimension: String(dimension || '').trim(),
                question: String(question || '').trim(),
                options: Array.isArray(options)
                    ? options.map(item => String(item || '').trim())
                    : [],
                answer_mode: String(answerMode || '').trim(),
            });
            let hashValue = 2166136261;
            for (let index = 0; index < source.length; index += 1) {
                hashValue ^= source.charCodeAt(index);
                hashValue = Math.imul(hashValue, 16777619) >>> 0;
            }
            return `q-${hashValue.toString(16).padStart(8, '0')}`;
        },

        getInterviewAssistantQuestionFingerprint() {
            const question = this.currentQuestion;
            if (!question || !question.text) return '';
            return this.buildInterviewAssistantQuestionFingerprint({
                dimension: this.currentDimension,
                question: question.text,
                options: question.options || [],
                answerMode: question.answerMode || 'pick_only',
            });
        },

        resetInterviewAssistantChatState(options = {}) {
            const preserveExpanded = options.preserveExpanded === true;
            this.assistantChatExpanded = preserveExpanded ? !!this.assistantChatExpanded : false;
            this.assistantChatInput = '';
            this.assistantChatLoading = false;
            this.assistantChatError = '';
            this.assistantChatRetryMessage = '';
            this.assistantChatMessages = [];
            this.assistantChatQuestionFingerprint = '';
        },

        syncInterviewAssistantChatForCurrentQuestion(options = {}) {
            const fingerprint = this.getInterviewAssistantQuestionFingerprint();
            if (!fingerprint) {
                this.resetInterviewAssistantChatState();
                return;
            }
            const preserveExpanded = options.preserveExpanded === true;
            const store = this.currentSession?.interview_assistant_chats;
            const thread = store && typeof store === 'object' ? store[fingerprint] : null;
            const messages = Array.isArray(thread?.messages)
                ? thread.messages
                    .filter(item => item && typeof item === 'object')
                    .map(item => ({
                        message_id: String(item.message_id || `iac-local-${Date.now()}-${Math.random()}`),
                        role: item.role === 'assistant' ? 'assistant' : 'user',
                        content: String(item.content || ''),
                        suggested_answer: item.suggested_answer || null,
                        created_at: String(item.created_at || ''),
                        question_fingerprint: String(item.question_fingerprint || fingerprint),
                    }))
                    .filter(item => item.content)
                : [];
            this.assistantChatQuestionFingerprint = fingerprint;
            this.assistantChatMessages = messages;
            this.assistantChatInput = '';
            this.assistantChatLoading = false;
            this.assistantChatError = '';
            this.assistantChatRetryMessage = '';
            if (!preserveExpanded) {
                this.assistantChatExpanded = messages.length > 0 ? this.assistantChatExpanded : false;
            }
        },

        getAssistantChatClientMessages() {
            return (Array.isArray(this.assistantChatMessages) ? this.assistantChatMessages : [])
                .filter(item => item && (item.role === 'user' || item.role === 'assistant') && item.content)
                .slice(-8)
                .map(item => ({
                    role: item.role,
                    content: item.content,
                }));
        },

        canSendInterviewAssistantChat() {
            if (this.assistantChatLoading || this.loadingQuestion || this.submitting) return false;
            if (!this.currentSession?.session_id || !this.currentQuestion?.text || this.currentQuestion?.serviceError) return false;
            return String(this.assistantChatInput || '').trim().length > 0;
        },

        appendAssistantChatMessage(message) {
            const fingerprint = this.getInterviewAssistantQuestionFingerprint();
            if (!fingerprint || !message) return;
            const normalized = {
                message_id: String(message.message_id || `iac-local-${Date.now()}-${Math.random()}`),
                role: message.role === 'assistant' ? 'assistant' : 'user',
                content: String(message.content || ''),
                suggested_answer: message.suggested_answer || null,
                created_at: String(message.created_at || new Date().toISOString()),
                question_fingerprint: String(message.question_fingerprint || fingerprint),
            };
            if (!normalized.content) return;
            this.assistantChatQuestionFingerprint = fingerprint;
            this.assistantChatMessages = [...(this.assistantChatMessages || []), normalized].slice(-20);

            if (!this.currentSession) return;
            if (!this.currentSession.interview_assistant_chats || typeof this.currentSession.interview_assistant_chats !== 'object') {
                this.currentSession.interview_assistant_chats = {};
            }
            const thread = this.currentSession.interview_assistant_chats[fingerprint] || {};
            const existingMessages = Array.isArray(thread.messages) ? thread.messages : [];
            this.currentSession.interview_assistant_chats[fingerprint] = {
                ...thread,
                question_fingerprint: fingerprint,
                dimension: this.currentDimension,
                question: this.currentQuestion.text,
                options: this.currentQuestion.options || [],
                answer_mode: this.currentQuestion.answerMode || 'pick_only',
                updated_at: normalized.created_at,
                messages: [...existingMessages, normalized].slice(-20),
            };
        },

        async sendInterviewAssistantChat() {
            if (!this.canSendInterviewAssistantChat()) return;

            const message = String(this.assistantChatInput || '').trim();
            const fingerprint = this.getInterviewAssistantQuestionFingerprint();
            const clientMessages = this.getAssistantChatClientMessages();
            this.assistantChatExpanded = true;
            this.assistantChatInput = '';
            this.assistantChatError = '';
            this.assistantChatRetryMessage = '';
            this.assistantChatLoading = true;
            this.appendAssistantChatMessage({
                message_id: `iac-user-local-${Date.now()}`,
                role: 'user',
                content: message,
                created_at: new Date().toISOString(),
                question_fingerprint: fingerprint,
            });

            try {
                const result = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/interview-assistant-chat`,
                    {
                        method: 'POST',
                        body: JSON.stringify({
                            dimension: this.currentDimension,
                            question: this.currentQuestion.text,
                            options: this.currentQuestion.options || [],
                            multi_select: !!this.currentQuestion.multiSelect,
                            answer_mode: this.currentQuestion.answerMode || 'pick_only',
                            selected_answers: this.selectedAnswers || [],
                            other_answer_text: this.otherSelected ? this.otherAnswerText : '',
                            message,
                            question_fingerprint: fingerprint,
                            client_messages: clientMessages,
                        }),
                    }
                );
                if (fingerprint !== this.getInterviewAssistantQuestionFingerprint()) {
                    return;
                }
                this.appendAssistantChatMessage({
                    message_id: result.message_id,
                    role: 'assistant',
                    content: result.content,
                    suggested_answer: result.suggested_answer || null,
                    created_at: result.created_at,
                    question_fingerprint: result.question_fingerprint || fingerprint,
                });
            } catch (error) {
                this.assistantChatError = error?.message || 'AI 助手暂时不可用';
                this.assistantChatRetryMessage = message;
            } finally {
                this.assistantChatLoading = false;
            }
        },

        async retryInterviewAssistantChat() {
            if (this.assistantChatLoading) return;
            const retryMessage = String(this.assistantChatRetryMessage || '').trim();
            if (!retryMessage) return;
            this.assistantChatInput = retryMessage;
            this.assistantChatRetryMessage = '';
            await this.sendInterviewAssistantChat();
        },

        normalizeAssistantOptionReferenceText(value) {
            return String(value || '')
                .trim()
                .replace(/[\s"'“”‘’《》<>「」『』（）()【】[\]]+/g, '');
        },

        parseAssistantOptionReferenceIndex(value, optionCount = 0) {
            const text = String(value || '').trim();
            if (!text || optionCount <= 0) return null;
            const chineseIndexes = {
                一: 1,
                二: 2,
                两: 2,
                三: 3,
                四: 4,
                五: 5,
                六: 6,
                七: 7,
                八: 8,
            };
            const parsed = /^\d+$/.test(text) ? Number(text) : chineseIndexes[text];
            if (!Number.isInteger(parsed) || parsed < 1 || parsed > optionCount) return null;
            return parsed - 1;
        },

        extractAssistantOptionReferenceIndexes(text, optionCount = 0) {
            const source = String(text || '');
            if (!source || optionCount <= 0) return [];
            const indexes = [];
            const seen = new Set();
            const patterns = [
                /(?:选项|第)\s*([一二两三四五六七八\d]+)\s*(?:项|个)?/g,
                /(?:^|[^A-Za-z0-9])([1-8])\s*[.、)]/g,
            ];
            for (const pattern of patterns) {
                let match = pattern.exec(source);
                while (match) {
                    const parsed = this.parseAssistantOptionReferenceIndex(match[1], optionCount);
                    if (parsed !== null && !seen.has(parsed)) {
                        indexes.push(parsed);
                        seen.add(parsed);
                    }
                    match = pattern.exec(source);
                }
            }
            return indexes;
        },

        appendUniqueAssistantOption(target, seen, option) {
            const normalized = String(option || '').trim();
            if (!normalized || seen.has(normalized)) return;
            target.push(normalized);
            seen.add(normalized);
        },

        mapAssistantOptionReferencesToOptions(rawItems = [], options = []) {
            if (!Array.isArray(rawItems) || !Array.isArray(options) || options.length === 0) return [];
            const normalizedLookup = new Map();
            options.forEach(option => {
                const normalized = this.normalizeAssistantOptionReferenceText(option);
                if (normalized) normalizedLookup.set(normalized, option);
            });

            const selectedOptions = [];
            const seen = new Set();
            rawItems.forEach(item => {
                const text = String(item || '').trim();
                if (!text) return;
                if (options.includes(text)) {
                    this.appendUniqueAssistantOption(selectedOptions, seen, text);
                    return;
                }
                const normalizedMatch = normalizedLookup.get(this.normalizeAssistantOptionReferenceText(text));
                if (normalizedMatch) {
                    this.appendUniqueAssistantOption(selectedOptions, seen, normalizedMatch);
                    return;
                }
                this.extractAssistantOptionReferenceIndexes(text, options.length)
                    .forEach(index => this.appendUniqueAssistantOption(selectedOptions, seen, options[index]));
            });
            return selectedOptions;
        },

        getAssistantOptionHintSegments(text) {
            const source = String(text || '');
            if (!source) return [];
            const positiveHints = /(建议|推荐|优先|应选|选择|可选|更匹配|适合|核心|主要|关联|保障|直接关系)/;
            const negativeHints = /(不建议|不优先|不需要|无需|不如|不是|后续|较低|容许|侧重)/;
            return source
                .split(/[\n。！？!?；;]+/)
                .map(segment => segment.trim())
                .filter(segment => segment && positiveHints.test(segment) && !negativeHints.test(segment));
        },

        inferAssistantSuggestedOptionsFromText(texts = [], options = []) {
            if (!Array.isArray(texts) || !Array.isArray(options) || options.length === 0) return [];
            const selectedOptions = [];
            const seen = new Set();
            const normalizedOptions = options
                .map(option => ({
                    option,
                    normalized: this.normalizeAssistantOptionReferenceText(option),
                }))
                .filter(item => item.normalized);

            texts.forEach(text => {
                this.getAssistantOptionHintSegments(text).forEach(segment => {
                    const normalizedSegment = this.normalizeAssistantOptionReferenceText(segment);
                    normalizedOptions.forEach(({ option, normalized }) => {
                        if (normalizedSegment.includes(normalized)) {
                            this.appendUniqueAssistantOption(selectedOptions, seen, option);
                        }
                    });
                    this.extractAssistantOptionReferenceIndexes(segment, options.length)
                        .forEach(index => this.appendUniqueAssistantOption(selectedOptions, seen, options[index]));
                });
            });
            return selectedOptions;
        },

        getAssistantSuggestedAnswer(message) {
            const suggested = message?.suggested_answer;
            if (!suggested || typeof suggested !== 'object') return null;
            const options = Array.isArray(this.currentQuestion?.options) ? this.currentQuestion.options : [];
            const customText = String(suggested.custom_text || '').trim();
            const rationaleText = String(suggested.rationale_text || '').trim();
            const rawSelectedOptions = Array.isArray(suggested.selected_options)
                ? suggested.selected_options.map(item => String(item || '').trim()).filter(Boolean)
                : [];
            let selectedOptions = this.mapAssistantOptionReferencesToOptions(rawSelectedOptions, options);
            if (selectedOptions.length === 0) {
                selectedOptions = this.inferAssistantSuggestedOptionsFromText(
                    [rationaleText, customText, message?.content],
                    options,
                );
            }
            if (selectedOptions.length === 0 && !customText && !rationaleText) return null;
            return {
                selectedOptions,
                customText,
                rationaleText,
                hasAnswer: selectedOptions.length > 0 || !!customText,
            };
        },

        getAssistantSuggestionApplyLabel(message) {
            const suggestion = this.getAssistantSuggestedAnswer(message);
            return suggestion?.hasAnswer ? '采纳为待提交答案' : '采纳补充说明';
        },

        canApplyAssistantSuggestion(message) {
            const suggestion = this.getAssistantSuggestedAnswer(message);
            if (!suggestion) return false;
            const fingerprint = this.getInterviewAssistantQuestionFingerprint();
            return !!fingerprint && String(message?.question_fingerprint || '') === fingerprint;
        },

        applyAssistantSuggestion(message) {
            if (!this.canApplyAssistantSuggestion(message)) {
                this.showToast('当前题目已变化，请重新向助手提问', 'warning');
                return;
            }

            const suggestion = this.getAssistantSuggestedAnswer(message);
            if (!suggestion) return;

            const options = Array.isArray(this.currentQuestion?.options) ? this.currentQuestion.options : [];
            const matchedOptions = suggestion.selectedOptions.filter(option => options.includes(option));
            if (matchedOptions.length > 0) {
                this.selectedAnswers = this.currentQuestion.multiSelect ? Array.from(new Set(matchedOptions)) : [matchedOptions[0]];
                this.otherSelected = false;
                this.otherAnswerText = '';
            } else if (suggestion.customText) {
                this.selectedAnswers = [];
                this.otherSelected = true;
                this.otherAnswerText = suggestion.customText;
            }

            if (suggestion.rationaleText) {
                this.rationaleText = suggestion.rationaleText;
            }
            this.clearAiRecommendationApplied();
            this.resetSingleSelectDisambiguation();
            this.showToast(
                suggestion.hasAnswer ? '已预填助手建议，请确认后再提交' : '已预填补充说明，请确认后再提交',
                'info',
            );
        },

        canSubmitAnswer() {
            if (this.submitting) {
                return false;
            }

            if (!this.interactionReady) {
                return false;
            }

            if (!this.currentQuestion.text) {
                return false;
            }

            const hasOptions = Array.isArray(this.currentQuestion.options) && this.currentQuestion.options.length > 0;
            if (!hasOptions) {
                return this.otherAnswerText.trim().length > 0;
            }

            if (this.currentQuestion.multiSelect) {
                const hasSelectedOptions = this.selectedAnswers.length > 0;
                const hasValidOther = this.otherSelected && this.otherAnswerText.trim().length > 0;
                return hasSelectedOptions || hasValidOther;
            }

            if (this.otherSelected) {
                return this.otherAnswerText.trim().length > 0;
            }
            return this.selectedAnswers.length > 0;
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
            const hasQuestionOptions = Array.isArray(this.currentQuestion.options) && this.currentQuestion.options.length > 0;
            const canEscalateSingleSelect = !questionMultiSelect
                && this.otherSelected
                && otherReference.pureReference
                && otherReference.matchedOptions.length > 1;
            const effectiveMultiSelect = questionMultiSelect
                || (submissionOptions.allowSingleSelectMultiSubmit === true && canEscalateSingleSelect);
            const selectionEscalatedFromSingle = !questionMultiSelect && effectiveMultiSelect;

            if (hasQuestionOptions && canEscalateSingleSelect && !effectiveMultiSelect) {
                this.submitting = false;
                this.openSingleSelectDisambiguation(otherReference.matchedOptions, otherText);
                return;
            }

            if (!hasQuestionOptions) {
                answer = otherText;
                if (!answer) {
                    this.submitting = false;
                    return;
                }
            } else if (effectiveMultiSelect) {
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
            const answered = this.currentSession.interview_log.filter(
                l => l.dimension === this.currentDimension && !l.is_follow_up
            ).length;
            return answered + 1;
        },

        canGoPrevQuestion() {
            if (this.submitting) {
                return false;
            }
            return this.currentSession && this.currentSession.interview_log.length > 0;
        },

        async goPrevQuestion() {
            if (!this.canGoPrevQuestion()) return;

            this.submitting = true;

            try {
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

                const updatedSession = await this.apiCall(
                    `/sessions/${this.currentSession.session_id}/undo-answer`,
                    { method: 'POST' }
                );

                this.currentSession = updatedSession;
                this.currentDimension = undoDimension;
                this.isGoingPrev = true;
                this.currentQuestion = savedQuestion;
                this.aiRecommendationExpanded = false;
                this.aiRecommendationApplied = false;
                this.aiRecommendationPrevSelection = null;
                this.syncInterviewAssistantChatForCurrentQuestion();
                this.selectedAnswers = [];
                this.rationaleText = '';
                this.otherAnswerText = '';
                this.otherSelected = false;
                this.resetSingleSelectDisambiguation();
                this.loadingQuestion = false;

                this.showToast('已恢复上一题，请重新作答', 'success');
            } catch (_error) {
                this.showToast('撤销失败', 'error');
            } finally {
                this.isGoingPrev = false;
                this.submitting = false;
            }
        },

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
                await this.fetchNextQuestion();
            } catch (error) {
                this.showToast(`跳过失败: ${error.message}`, 'error');
            } finally {
                this.submitting = false;
            }
        },

        async completeDimension() {
            if (!this.currentSession) return;

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
                this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);

                const nextDim = this.getNextIncompleteDimension();
                if (nextDim) {
                    this.ensureDimensionVisualComplete(this.currentDimension);
                    this.currentDimension = nextDim;
                    await this.fetchNextQuestion();
                } else {
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

        canShowSkipFollowUp() {
            return this.currentQuestion.isFollowUp;
        },

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
                    this.currentSession = await this.apiCall(`/sessions/${this.currentSession.session_id}`);
                    this.updateDimensionsFromSession(this.currentSession);

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
    };

    function attach(app) {
        if (!app || typeof app !== 'object') return app;

        Object.entries(interviewRuntimeDefaults).forEach(([key, value]) => {
            if (typeof app[key] === 'undefined') {
                app[key] = cloneDefaultValue(value);
            }
        });

        Object.assign(app, interviewRuntimeMethods);
        return app;
    }

    global.DeepVisionInterviewRuntimeModule = { attach };
})(window);

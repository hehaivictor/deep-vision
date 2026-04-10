# 第二阶段模块化拆分计划

本文档用于承接第一批基础设施与状态模块拆分之后的下一阶段规划。目标不是一次性继续大拆，而是先明确“下一刀应该落在哪一块业务热点”，并把范围、风险与验证方式提前写清。

## 当前基线

第一批已完成拆分：

- 后端：
  - [web/server_modules/runtime_bootstrap.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/runtime_bootstrap.py)
  - [web/server_modules/object_storage_history.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/object_storage_history.py)
  - [web/server_modules/admin_config_center.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/admin_config_center.py)
  - [web/server_modules/ownership_admin_flow.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/ownership_admin_flow.py)
- 前端：
  - [web/app_modules/session_list_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/session_list_state.js)
  - [web/app_modules/report_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/report_state.js)
  - [web/app_modules/auth_license_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/auth_license_state.js)

当前主文件体量：

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)：约 `47010` 行
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)：约 `11355` 行

说明：

- 第一批拆分主要解决了“启动初始化、配置治理、列表状态、认证状态”这类低耦合横切能力
- 第二阶段应开始进入业务热点，但仍然要保持“一轮只动一个高耦合主题”的节奏

## 选择原则

第二阶段候选模块优先满足以下条件：

1. 功能边界清晰，有明确入口函数或调用链
2. 已经在单文件内形成局部高密度聚集
3. 有配套文档与测试可以兜底
4. 抽离后不会立刻引入新的配置真相源或并行流程

不建议优先拆的类型：

- 同时跨越登录、访谈、报告、管理员中心四个领域的混合逻辑
- 纯 UI 模板碎片而缺少稳定行为边界的部分
- 当前测试覆盖明显不足、又缺少稳定入口的异步链路

## 后端候选模块

### 候选 A：报告生成编排与质量门控

优先级：`最高`
状态：`已完成（2026-04-10，报告生成编排入口已切到 report_generation_runtime）`

核心函数：

- [generate_report_v3_pipeline](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L26499)
- [run_report_generation_job](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L33921)
- [generate_report](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L34992)
- [build_report_prompt_with_options](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L21184)
- [build_report_evidence_pack](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L21789)
- [compute_report_quality_meta_v3](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L25148)

适合先拆的原因：

- 已经形成完整闭环：提示词构建 -> 草稿生成 -> 评审校验 -> 异步任务执行 -> 最终生成接口
- 体量大、耦合集中，拆出去对 `server.py` 减负最明显
- 有明确的生成入口与测试落点，适合先做 service 化

建议模块名：

- `web/server_modules/report_generation_runtime.py`

当前结果：

- `compute_report_quality_meta_v3`、`build_report_quality_meta_fallback`、`generate_report_v3_pipeline`
- `is_unusable_legacy_report_content`、`classify_v3_pipeline_exception`
- `run_report_generation_job`

以上逻辑已迁入 `web/server_modules/report_generation_runtime.py`，`web/server.py` 入口已改为统一走运行时绑定与薄包装调用；后续还需补一轮旧内联实现清扫，真正缩减主文件体量。

拆分边界：

- 保留 Flask 路由在 `server.py`
- 将编排、质量门控、draft/review helper、异步任务执行迁到模块
- 不在这一步同时动方案页与导出逻辑

主要风险：

- 异步任务状态、缓存键与最终快照写入点多，迁移时容易漏掉 side effect
- 需要确保现有报告 V3/V2 兼容分支不被误伤

推荐验证：

- `python3 -m unittest tests.test_api_comprehensive`
- `python3 -m unittest tests.test_solution_payload`
- `python3 scripts/agent_smoke.py`

### 候选 B：访谈问题推进与超时恢复

优先级：`高`
状态：`已完成（2026-04-10，访谈问题推进与运行时档位链路已切到 interview_runtime）`

核心函数：

- [build_interview_prompt](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L20256)
- [_select_question_generation_runtime_profile](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L30510)
- [get_next_question](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L31557)
- [submit_answer](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L32442)
- [generate_question_with_tiered_strategy](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L31333)

适合拆分的原因：

- 是 DeepVision 主链路中最常改、最易感知的业务热点
- 已经具备稳定的入口函数和明确的超时恢复逻辑

暂不放第一优先的原因：

- 与前端等待态、预取、恢复页、watchdog 交互更紧
- 一旦边界划不好，容易引发“下一题卡住”这类高敏感回归

建议模块名：

- `web/server_modules/interview_runtime.py`

当前结果：

- `build_interview_prompt`
- `_select_question_generation_runtime_profile`
- `_prepare_question_generation_runtime`
- `_call_question_with_optional_hedge`
- `generate_question_with_tiered_strategy`

以上逻辑已迁入 `web/server_modules/interview_runtime.py`，`web/server.py` 对外保留薄包装；`get_next_question` 与 `submit_answer` 继续留在主文件中，避免本轮同时触发路由层与持久化写回的大范围回归。

主要风险：

- 预取、runtime profile、缓存命中、回退档切换都在这条链上
- 改动后需要和前端等待态一起回归

推荐验证：

- `python3 -m unittest tests.test_api_comprehensive`
- `python3 -m unittest tests.test_security_regression`
- `python3 scripts/agent_browser_smoke.py --suite minimal`

### 候选 C：方案页构建链路

优先级：`中`

核心函数：

- [build_solution_render_model](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L41345)
- [build_solution_proposal_brief](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L43463)
- [build_solution_chapter_copy](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py#L43897)

适合拆分的原因：

- 方案页属于独立产物模型，天然适合 service 化

暂不优先的原因：

- 当前链路相对稳定，且已在文档中说明清楚
- 优先级不如报告生成和访谈推进

建议模块名：

- `web/server_modules/solution_rendering.py`

## 前端候选模块

### 候选 A：报告详情、导出与演示稿状态链路

优先级：`最高`

核心方法：

- [generateReport](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L6546)
- [viewReport](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L6608)
- [startPresentationGeneration](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L7432)

适合先拆的原因：

- 已经和 `report_state.js` 形成天然上下游关系
- 报告列表与详情缓存已独立，下一步顺着拆详情/导出状态最自然

建议模块名：

- `web/app_modules/report_detail_runtime.js`

主要风险：

- 详情页渲染、演示稿轮询、导出入口和报告生成回跳都在这条链上
- 需要防止报告列表缓存与详情状态断裂

推荐验证：

- `node --check web/app.js`
- `node --check web/app_modules/report_detail_runtime.js`
- `python3 scripts/agent_browser_smoke.py --suite extended`

当前结果：

- `generateReport`、`viewReport`、`viewLatestReportForSession`
- 方案页跳转与精审版再生成入口
- 报告生成反馈状态与轮询
- 演示稿生成、轮询、停止、进度平滑
- 报告详情渲染完成后的表格增强入口

以上逻辑已迁入 `web/app_modules/report_detail_runtime.js`，`web/app.js` 只保留 Markdown 结构解析与导航模型构建等更细粒度 helper。

### 候选 B：访谈问答主流程

优先级：`高`
状态：`已完成（2026-04-10，访谈问答主流程已切到 interview_runtime）`

核心方法：

- [openSession](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L4238)
- [fetchNextQuestion](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L4724)
- [submitAnswer](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L5630)

适合拆分的原因：

- 已经与会话列表状态模块形成边界
- 是用户体感最敏感的交互主链路

暂不放第一优先的原因：

- 与页面状态、看门狗、等待页、恢复逻辑深度耦合
- 拆分难度高于报告详情链

建议模块名：

- `web/app_modules/interview_runtime.js`

主要风险：

- 一旦拆分不稳，容易引入“点会话慢”“下一题卡”“恢复页误判”等回归

推荐验证：

- `node --check web/app.js`
- `python3 scripts/agent_browser_smoke.py --suite minimal`
- `python3 scripts/agent_smoke.py`

当前结果：

- `startWebSearchPolling`、`stopWebSearchPolling`
- `startQuestionRequestGuard`、`recoverStalledQuestionRequest`
- `startThinkingPolling`、`startSkeletonFill`
- `openSession`、`startInterview`、`fetchNextQuestion`
- `submitAnswer`、`goPrevQuestion`、`skipFollowUp`
- `completeDimension`、`restartResearch`

以上逻辑已迁入 `web/app_modules/interview_runtime.js`，`web/app.js` 仅保留 `createQuestionState`、AI 推荐与“其他输入”解析等更细粒度 helper。

### 候选 C：管理员中心页签逻辑

优先级：`中`
状态：`已完成（2026-04-10，管理员中心页签编排与 ops/summaries/config/ownership 状态已切到 admin_center_state）`

核心方法与状态：

- [switchView](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L10187)
- [loadAdminConfigCenter](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js#L2219)
- 管理员中心相关状态：`adminConfig*`、`adminLicense*`、`adminOwnership*`

适合拆分的原因：

- 页签清晰，功能分组明确
- 第一批已把认证与 License gate 独立出去，管理员中心成为下一块可见边界

暂不优先的原因：

- 管理员中心本身就是复合功能集合
- 更适合按“license / config / ownership / ops”四个子页签继续细分，而不是一次性整块抽走

建议模块方向：

- `web/app_modules/admin_center_state.js`
- `admin_license_state.js` 可作为后续更细颗粒度拆分方向

当前结果：

- `openAdminCenter`、`switchAdminTab`、`ensureAdminDataForTab`
- `loadAdminOverview`
- `loadAdminSummariesInfo`、`clearAdminSummariesCache`
- `loadOpsMetrics`、`refreshOpsMetricsIfVisible`
- 配置中心可见分组、草稿同步与保存
- 归属迁移搜索、审计、preview/apply/rollback 与历史列表

以上逻辑已迁入 `web/app_modules/admin_center_state.js`，`web/app.js` 中保留 License 管理子链路与通用 helper；后续如需继续减主文件，可再单独抽 `admin_license_state.js`。

## 推荐执行顺序

建议下一阶段按下面顺序推进：

1. 后端：报告生成编排与质量门控
2. 前端：报告详情、导出与演示稿状态链路
3. 后端：访谈问题推进与超时恢复
4. 前端：访谈问答主流程
5. 管理员中心页签逻辑

选择理由：

- 先沿着“报告列表状态已拆 -> 报告详情链继续拆”这一条自然边界推进，风险最低
- 再处理访谈主链路，避免在同一轮同时动两条高敏感路径
- 管理员中心放后，是因为它更适合拆成多块子状态，而不是先做整块搬迁

## 不建议的做法

- 不要同一轮同时拆后端访谈链和前端访谈链
- 不要同一轮同时拆报告生成和方案页渲染
- 不要为了“尽快缩小行数”而一次性拆多个热点
- 不要在没有对应 smoke/browser 回归兜底前就动高频交互链路

## 推荐交付方式

每次只做一个候选模块，单独提交，并执行最小验证：

```bash
python3 scripts/agent_guardrails.py --quiet
python3 scripts/agent_smoke.py
```

若涉及前端交互或报告详情，再追加：

```bash
python3 scripts/agent_browser_smoke.py --suite minimal
python3 scripts/agent_browser_smoke.py --suite extended
```

一句话总结：

`第二阶段不要追求一次性把大文件拆小，而要先沿着最自然的业务边界，一块一块把高频热点剥离出去。`

# DeepVision Architecture Map

这份文档只回答三类问题：

1. 代码物理上放在哪里
2. 主要边界在哪里
3. 哪些依赖方向不允许出现

它不是业务说明书。业务细节请回到 [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md) 里的领域文档。

## 1. 总体分层

DeepVision 当前仍是 brownfield 仓库，主应用没有完全拆成多服务，但已经形成稳定的逻辑分层：

```text
Types / Config / Docs
  -> Repo / DB / Object Storage
    -> Service / Runtime / Orchestration
      -> Route / HTTP / Admin API
        -> UI / Browser / Static Assets
```

当前实现不是按目录一一对应，而是按“主入口 + 模块化运行时 + harness 约束”组合实现。

## 2. 后端物理地图

### 2.1 核心入口

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
  - Flask 主服务入口
  - 仍承载主要路由与一部分编排
  - 应尽量保持为“路由 + 薄编排 + 必要 glue code”
- [web/wsgi.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/wsgi.py)
  - WSGI 入口
- [web/gunicorn.conf.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/gunicorn.conf.py)
  - 生产运行参数

### 2.2 已抽离的 server runtime / service 模块

- [web/server_modules/runtime_bootstrap.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/runtime_bootstrap.py)
  - 启动初始化协调器与 startup snapshot
- [web/server_modules/report_generation_runtime.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/report_generation_runtime.py)
  - 报告生成编排与质量门控运行时
- [web/server_modules/interview_runtime.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/interview_runtime.py)
  - 访谈问题推进、下一题生成、超时恢复相关运行时
- [web/server_modules/admin_config_center.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/admin_config_center.py)
  - 配置中心读写服务
- [web/server_modules/ownership_admin_flow.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/ownership_admin_flow.py)
  - 管理员归属迁移 API 编排
- [web/server_modules/object_storage_history.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/object_storage_history.py)
  - 对象存储历史补齐与归档能力

### 2.3 脚本层服务

- [scripts/admin_ownership_service.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/admin_ownership_service.py)
  - 账号归属迁移、审计、回滚的核心脚本服务
- [scripts/import_external_local_data_to_cloud.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/import_external_local_data_to_cloud.py)
  - 本地数据导入云端
- [scripts/rollback_external_local_data_import.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/rollback_external_local_data_import.py)
  - 导入回滚
- [scripts/sync_object_storage_history.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/sync_object_storage_history.py)
  - 历史对象存储记录补齐

## 3. 前端物理地图

### 3.1 页面入口

- [web/index.html](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/index.html)
  - 主应用入口
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
  - 主前端编排入口
- [web/solution.html](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.html)
  - 方案页入口
- [web/solution.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.js)
  - 方案页脚本
- [web/help.html](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/help.html)
  - 帮助页入口

### 3.2 已抽离的 app 模块

- [web/app_modules/interview_runtime.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/interview_runtime.js)
  - 访谈问答主流程
- [web/app_modules/report_detail_runtime.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/report_detail_runtime.js)
  - 报告详情、导出、演示稿状态链路
- [web/app_modules/admin_center_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/admin_center_state.js)
  - 管理员中心页签状态与 ops/config/ownership 协调
- [web/app_modules/session_list_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/session_list_state.js)
  - 会话列表状态
- [web/app_modules/report_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/report_state.js)
  - 报告态管理
- [web/app_modules/auth_license_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/auth_license_state.js)
  - 登录与 License 状态

## 4. 数据与配置地图

### 4.1 配置来源

- [web/.env.example](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/.env.example)
  - 环境变量模板
- [web/config.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py)
  - 非敏感默认策略
- `web/.env.local` / `web/.env.cloud`
  - 本机私有环境文件，不进入版本库

### 4.2 数据与索引

- `AUTH_DB_PATH`
  - 鉴权、用户、登录态
- `LICENSE_DB_PATH`
  - License 生命周期与签名元数据
- `META_INDEX_DB_PATH`
  - 会话、报告、分享、索引元数据
- `data/operations/**`
  - 迁移、回滚、归档、startup snapshot 等运维数据

说明：

- `data/` 是运行态数据，不是源代码目录
- 新测试优先使用临时目录隔离，不要污染仓库下的 `data/`

## 5. Harness 物理地图

### 5.1 单入口与执行层

- [scripts/agent_harness.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_harness.py)
  - 统一 harness 入口
- [scripts/agent_workflow.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_workflow.py)
  - task workflow 执行器
- [scripts/agent_doctor.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_doctor.py)
  - 环境自检
- [scripts/agent_observe.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_observe.py)
  - 运行态观察与诊断面板
- [scripts/agent_history.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_history.py)
  - 历史索引与 diff

### 5.2 规则与验证层

- [scripts/agent_static_guardrails.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_static_guardrails.py)
  - 源码级静态规则
- [scripts/agent_guardrails.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_guardrails.py)
  - 运行态关键不变量
- [scripts/agent_smoke.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_smoke.py)
  - 最小主链路回归
- [scripts/agent_browser_smoke.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_browser_smoke.py)
  - 浏览器 UI smoke
- [scripts/agent_eval.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_eval.py)
  - 场景 evaluator

### 5.3 计划、契约、校准、交接

- [scripts/agent_planner.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_planner.py)
  - Planner artifact 生成
- [scripts/agent_plans.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_plans.py)
  - 按 task 的 latest plan 指针
- [scripts/agent_contracts.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_contracts.py)
  - Sprint Contract 装载
- [scripts/agent_calibration.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_calibration.py)
  - Evaluator 校准样本
- [scripts/agent_artifacts.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_artifacts.py)
  - progress / failure-summary / handoff / latest 指针

### 5.4 配置与语料

- [resources/harness/tasks](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/resources/harness/tasks)
  - task 画像
- [resources/harness/contracts](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/resources/harness/contracts)
  - Sprint Contract
- [tests/harness_scenarios](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_scenarios)
  - evaluator 场景
- [tests/harness_calibration](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/harness_calibration)
  - evaluator 校准样本

## 6. 允许的依赖方向

推荐的稳定方向是：

```text
Types / Config / Docs
  -> DB / Repo / Storage
    -> Runtime / Service / Orchestration
      -> Route / API
        -> UI
```

落到当前仓库，至少要遵守这些规则：

- `web/server_modules/*` 可以依赖通用配置、repo、runtime helper，但不应反向依赖前端文件
- `web/app_modules/*` 只能依赖前端共享 helper，不得依赖 Python runtime/service
- `scripts/agent_*` 可以读取 task / contract / scenario / calibration，但业务代码不应反向依赖 harness 脚本
- 配置中心路由必须委托 service/helper，不应在路由层直接写 `.env`、`config.py` 或 `site-config.js`

## 7. 明确“不允许什么”

以下属于架构回退，默认不允许：

- 不要让 UI 或前端状态层反向依赖 Python runtime / service 细节
- 不要让业务代码反向依赖 `scripts/agent_*` harness 脚本
- 不要在路由层重新堆积大块业务实现；路由层应尽量薄
- 不要在配置中心路由中直接写配置文件，必须经过委托 helper / service
- 不要把运行态数据、artifact、临时产物写回源码目录作为“正式状态”
- 不要把 `data/` 下的真实运行数据当成代码依赖

## 8. 阅读建议

进入仓库后，推荐顺序：

1. 先看 [AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)
2. 再看这份 [ARCHITECTURE.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/ARCHITECTURE.md)
3. 然后按任务跳到 [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md) 对应领域文档

如果要改大文件，优先先确认：

- 真正实现是否已经迁入 `server_modules` / `app_modules`
- 当前改动属于业务逻辑、运行态编排，还是 harness 规则
- 是否已有对应 task、contract、playbook、scenario 可以复用

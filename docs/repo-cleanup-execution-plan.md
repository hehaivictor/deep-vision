# DeepVision 仓库收口与精简活跃计划

本文档只保留当前仍需推进的收尾任务，避免继续混入已完成阶段的历史执行细节。

已归档的历史执行记录见：

- [docs/archive/repo-cleanup-execution-history.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/archive/repo-cleanup-execution-history.md)

## 1. 当前状态

已完成：

- 统一生产部署入口
- 清理 `.memory` 过程文档
- 收口迁移文档
- 收口配置文档与 ignore 规则
- 第一批启动与前端状态模块化拆分
- 清理无消费方的 `PATH.ai.md` / `README.ai.md` 与空目录残留

当前剩余重点：

1. 清理 `web/server.py` 中 report / interview 两条链路的过渡绑定与薄包装残留
2. 收口 `web/app.js` 与 `app_modules` 之间模块化后的重复默认状态、旧 helper 与边界注释
3. 暂缓第三批系统性拆分，仅在后续业务热点重新升温时按需启动

## 2. 执行原则

1. 每个任务单独提交，不混做。
2. 先做文档与入口边界收口，再进入下一阶段代码拆分。
3. 每一步都保留明确验收命令，不靠主观判断“应该没问题”。
4. 不直接修改真实运行数据、真实部署环境变量或生产实例配置。
5. 第二阶段模块化先规划、再拆分、再验证，不做一次性大手术。

## 3. 任务十：清理后端运行时过渡残留

### 3.1 目标

在不启动第三批系统性拆分的前提下，先把 `web/server.py` 中已经迁入 `report_generation_runtime` / `interview_runtime` 的过渡绑定、薄包装和重复编排语义清掉，真正降低主文件认知负担。

### 3.2 当前问题

- `web/server.py` 已完成报告生成与访谈运行时模块切换，但主文件仍保留一层过渡胶水
- 这些残留包括运行时绑定函数、local name 集合和多个纯转发薄包装
- 当前阅读体验依然是“模块已存在，但主文件还像半拆状态”，后续维护者很难一眼判断真实实现在哪

### 3.3 具体动作

- [x] 清点并收口 `report_generation_runtime` 相关过渡入口
- [x] 清点并收口 `interview_runtime` 相关过渡入口
- [x] 删除 `_ensure_*_runtime_bound()`、`*_LOCAL_NAMES` 一类仅服务迁移阶段的胶水
- [x] 将 `web/server.py` 保持为“路由 + 极薄入口 + 必要 glue code”，不再保留纯转发包装
- [x] 更新阶段计划文档，记录哪些过渡层已清理完成

### 3.4 涉及文件

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- [web/server_modules/report_generation_runtime.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/report_generation_runtime.py)
- [web/server_modules/interview_runtime.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/interview_runtime.py)
- [docs/agent/plans/module-split-phase2.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/plans/module-split-phase2.md)

### 3.5 验收命令

```bash
rg -n "_ensure_(report|interview)_runtime_bound|_INTERVIEW_RUNTIME_LOCAL_NAMES|generate_report_v3_pipeline|run_report_generation_job|build_interview_prompt|_select_question_generation_runtime_profile|_prepare_question_generation_runtime|_call_question_with_optional_hedge|generate_question_with_tiered_strategy" /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py
python3 -m py_compile /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/report_generation_runtime.py /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/interview_runtime.py
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_guardrails.py --quiet
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_smoke.py
```

### 3.6 完成标准

- `web/server.py` 中不再保留仅用于迁移期的运行时绑定胶水
- report / interview 相关入口只剩必要的路由和极薄编排层
- 新维护者能直接定位真实实现所在模块

当前结果：

- `report_generation_runtime` / `interview_runtime` 的运行时绑定已改为显式同步入口
- 迁移期 `_ensure_*_runtime_bound`、`*_LOCAL_NAMES` 与 report 小型 helper 残留已清掉
- 任务十相关回归已补跑：
  - `python3 -m py_compile web/server.py web/server_modules/report_generation_runtime.py web/server_modules/interview_runtime.py tests/test_security_regression.py`
  - `uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 -m unittest tests.test_security_regression.SecurityRegressionTests.test_run_report_generation_job_short_circuits_to_legacy_fallback tests.test_security_regression.SecurityRegressionTests.test_generate_report_v3_pipeline_falls_back_to_alternate_draft_lane_once tests.test_security_regression.SecurityRegressionTests.test_generate_report_v3_pipeline_recovers_from_review_parse_failure_via_repair`
  - `uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 -m unittest tests.test_question_fast_strategy`
  - `python3 scripts/agent_guardrails.py --quiet`
  - `python3 scripts/agent_smoke.py`

## 4. 任务十一：收口前端模块化边界重复定义

### 4.1 目标

在不继续新建前端业务模块的前提下，检查 `web/app.js` 与现有 `app_modules` 的边界，清掉模块化后残留的旧默认状态、重复 helper 和过时注释。

### 4.2 当前问题

- `web/app.js` 已从一万多行降到约七千多行，但模块化后的边界还没做完整收边
- 报告详情、访谈主流程、管理员中心都已拆出，主文件里仍可能留有重复默认状态或只服务历史实现的辅助逻辑
- 这类重复不会立刻出 bug，但会在下一轮需求迭代时再次拉高理解成本

### 4.3 具体动作

- [x] 盘点 `interview_runtime.js` 对应的旧 helper / 默认状态残留
- [x] 盘点 `report_detail_runtime.js` 对应的旧 helper / 默认状态残留
- [x] 盘点 `admin_center_state.js` 对应的旧 helper / 默认状态残留
- [x] 删除已经不再被主链路消费的旧注释和重复状态说明
- [x] 保持 `app.js` 只保留跨模块共享的稳定 helper

### 4.4 涉及文件

- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
- [web/app_modules/interview_runtime.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/interview_runtime.js)
- [web/app_modules/report_detail_runtime.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/report_detail_runtime.js)
- [web/app_modules/admin_center_state.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/admin_center_state.js)

### 4.5 验收命令

```bash
node --check /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js
node --check /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/interview_runtime.js
node --check /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/report_detail_runtime.js
node --check /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules/admin_center_state.js
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_guardrails.py --quiet
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_smoke.py
```

### 4.6 完成标准

- `web/app.js` 不再保留明显只服务旧实现的重复状态与 helper
- `app.js` 与各 `app_modules` 的职责边界清晰可解释
- 前端不再继续为“缩行数”而新拆模块

当前结果：

- 报告详情链路的章节模型、目录观察器、附录导出菜单等专用 helper 已从 `web/app.js` 收回 `web/app_modules/report_detail_runtime.js`
- `interview_runtime.js` 残留审计已完成，`app.js` 中保留的是 `createQuestionState`、AI 推荐与“其他输入”解析等跨模块共享 helper
- `admin_center_state.js` 残留审计已完成，`app.js` 中保留的是仍与 License 管理子链路耦合的状态重置与表单 helper，当前不再继续机械搬迁

## 5. 任务十二：第三批拆分决策门

### 5.1 目标

把“是否继续第三批拆分”从默认动作改成明确决策门，只在某块业务重新进入高频改动、且现有模块边界不足时才启动新一轮拆分。

### 5.2 当前问题

- 第二阶段列出的候选块已经全部完成
- 当前继续拆分的收益明显下降，风险上升
- 如果没有明确的启动条件，容易重新回到“为了拆而拆”

### 5.3 具体动作

- [x] 约定第三批拆分只在具体业务热点触发时启动
- [x] 将 `solution_rendering.py`、`admin_license_state.js` 等方向标记为“按需候选”，不是默认待办
- [x] 在相关文档中明确“先清旧实现，再决定是否新拆”

### 5.4 涉及文件

- [docs/repo-cleanup-execution-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/repo-cleanup-execution-plan.md)
- [docs/agent/plans/module-split-phase2.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/plans/module-split-phase2.md)

### 5.5 验收命令

```bash
rg -n "第三批|solution_rendering|admin_license_state|过渡残留" /Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/repo-cleanup-execution-plan.md /Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/plans/module-split-phase2.md
```

### 5.6 完成标准

- 文档不再把“继续大拆”描述为默认下一步
- 新一轮拆分必须绑定具体热点与明确收益

当前结果：

- 第三批拆分已从默认待办改成显式决策门
- 只有满足“相关模块连续高频改动、现有边界明显失效、已有最小回归兜底”三项条件时，才允许新开拆分任务
- `solution_rendering.py`、`admin_license_state.js` 现统一视为按需候选，不再作为活跃计划默认下一步

## 6. 任务八：收瘦 README 与 agent 命令入口

### 3.1 目标

把 `README.md` 收回到“仓库总览 + 启动方式 + 配置入口 + 关键链接”，把详细的 agent / harness 命令继续压回 `docs/agent/README.md` 与 `AGENTS.md`。

### 3.2 当前问题

- `README.md` 目前同时承担产品总览、配置说明、生产部署、运维接口和长篇 agent 命令索引
- [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md) 已具备承接命令导航的能力
- [AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md) 已包含更适合 agent 使用的高密度入口

### 3.3 具体动作

- [x] 将 `README.md` 中超长的 agent / harness 命令区块压缩为跳转说明
- [x] 保留 `README.md` 中最小必要的本地启动、云端联调、生产部署入口
- [x] 将详细命令继续收口到 `docs/agent/README.md`
- [x] 校验 `AGENTS.md`、`docs/agent/README.md`、`README.md` 三者的入口边界不再重复

### 3.4 涉及文件

- [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)
- [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)
- [AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)

### 3.5 验收命令

```bash
python3 - <<'PY'
from pathlib import Path
for p in ['README.md','docs/agent/README.md','AGENTS.md']:
    path=Path('/Users/hehai/Documents/开目软件/Agents/project/DeepVision')/p
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        lines=sum(1 for _ in f)
    print(f'{p}: {lines}')
PY
rg -n "agent_harness.py --profile auto|agent_smoke.py|agent_guardrails.py" /Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md /Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md /Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md
```

### 3.6 完成标准

- `README.md` 只保留全局入口，不再维护超长 agent 命令列表
- 详细命令入口由 `docs/agent/README.md` 和 `AGENTS.md` 承担
- 三份入口文档的职责边界清晰可解释

## 7. 任务九：规划第二阶段模块化拆分

### 4.1 目标

在第一批基础设施与状态模块拆分完成后，继续明确第二阶段最值得拆的业务热点，但不急于一次性大改。

### 4.2 当前问题

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py) 仍约 4.7 万行
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js) 仍约 1.1 万行
- 第一批拆出的 `server_modules` / `app_modules` 主要解决了启动、配置、列表状态与登录边界
- 还未触及最重的业务热点：
  - 访谈推进编排
  - 报告生成与质量门控
  - 管理员中心复杂页签逻辑
  - 报告详情渲染与导出编排

### 4.3 具体动作

- [x] 对 `web/server.py` 做一次热点分段标注，明确下一个拆分对象
- [x] 对 `web/app.js` 做一次热点分段标注，明确下一个拆分对象
- [x] 为第二阶段拆分生成一份“候选模块清单 + 风险说明”
- [x] 优先评估以下候选：
  - 报告生成编排与质量门控
  - 访谈问题推进与超时恢复
  - 管理员中心页签与配置交互
  - 报告详情渲染、导出与演示稿状态链路

### 4.4 涉及文件

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
- [web/server_modules](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules)
- [web/app_modules](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules)
- 可新增的规划文档，例如 `docs/agent/plans/`
- [docs/agent/plans/module-split-phase2.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/plans/module-split-phase2.md)

### 4.5 验收命令

```bash
python3 - <<'PY'
from pathlib import Path
for p in ['web/server.py','web/app.js']:
    path=Path('/Users/hehai/Documents/开目软件/Agents/project/DeepVision')/p
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        lines=sum(1 for _ in f)
    print(f'{p}: {lines}')
PY
find /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules -maxdepth 1 -type f | sort
find /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules -maxdepth 1 -type f | sort
```

### 4.6 完成标准

- 明确第二阶段模块化的下一批目标
- 不在同一轮里同时实施多块高耦合业务拆分
- 保持“先规划，再拆分，再验证”的节奏

## 8. 推荐推进顺序

1. 先完成任务十，清理 `web/server.py` 中 report / interview 的过渡残留
2. 视需要执行任务十一，收口前端模块化边界重复定义
3. 仅在明确出现新热点时，才通过任务十二启动第三批拆分决策

一句话总结：

`当前先做过渡残留清理，不默认继续第三批系统性拆分。`

# DeepVision 接入方案生成服务改造方案 v1.0

本文档用于沉淀 DeepVision 侧的正式改造方案。目标是在不改前端交互的前提下，把当前“本地生成方案页/演示文稿”的逻辑切到统一的“方案生成服务”。

## 当前状态

- 状态：`draft`
- 宿主项目：`DeepVision`
- 目标服务：`方案生成服务 v1.0`
- 前端策略：`保持现状`
- 后端策略：`从本地生成切到 BFF/代理模式`

## 一、目标与非目标

### 1.1 目标

1. DeepVision 后端可以为任意报告组装 `ProposalSnapshot v1`。
2. 方案页接口改为调用 `方案生成服务 /v1/solutions/render`。
3. 演示文稿接口改为调用 `方案生成服务 /v1/presentations/jobs`。
4. 方案页页面、报告详情页和现有交互不改。
5. 迁移期保留 fallback，避免一次性切换导致回归风险失控。

### 1.2 非目标

1. 不重写方案页前端。
2. 不重写报告详情页的演示文稿轮询交互。
3. 不把登录、分享、权限、公开只读、owner 校验迁到新服务。
4. 不要求在第一阶段删除所有本地旧逻辑。

## 二、保持不变的内容

以下能力继续留在 DeepVision：

- 登录态与用户上下文
- `solution.view` / `solution.share` / `presentation.generate` 等等级能力校验
- 报告 owner 校验与公开分享边界
- 方案页前端渲染：
  - [web/solution.js](../../../web/solution.js)
- 报告详情页演示文稿交互：
  - [web/app_modules/report_detail_runtime.js](../../../web/app_modules/report_detail_runtime.js) `:731`

## 三、后端新增能力

### 3.1 新增配置

- [ ] `PROPOSAL_SERVICE_ENABLED`
- [ ] `PROPOSAL_SERVICE_BASE_URL`
- [ ] `PROPOSAL_SERVICE_TIMEOUT`
- [ ] `PROPOSAL_SERVICE_API_KEY` 或等价 service token

### 3.2 新增客户端封装

建议新增：

- [ ] `web/server_modules/proposal_service_client.py`

职责：

1. 调用 `方案生成服务 /v1/solutions/render`
2. 调用 `方案生成服务 /v1/presentations/jobs`
3. 查询演示文稿 job 状态
4. 获取 artifact 信息

### 3.3 新增 ProposalSnapshot Mapper

建议新增：

- [ ] `web/server_modules/proposal_snapshot_mapper.py`

推荐暴露两个函数：

- `build_proposal_snapshot_for_report(report_name: str, owner_user_id: int = 0) -> dict`
- `map_deepvision_snapshot_to_proposal_snapshot(normalized_snapshot: dict, evidence_pack: dict, generated_at) -> dict`

## 四、ProposalSnapshot 组装逻辑

### 4.1 数据来源优先级

1. 优先读取 sidecar：
   - [read_solution_sidecar](../../../web/server.py) `:33990`
2. 无 sidecar 时，优先按绑定 session 回补：
   - [build_bound_solution_sidecar_snapshot](../../../web/server.py) `:34579`
3. 再不行，从历史报告 Markdown 回补：
   - [build_solution_snapshot_from_markdown_report](../../../web/server.py) `:34691`
4. 全部进入标准化入口：
   - [_normalize_solution_snapshot](../../../web/server.py) `:34379`

### 4.2 证据与质量补充

如果能定位到 session，则进一步构建：

- [build_report_evidence_pack](../../../web/server.py) `:21325`

该函数输出的：

- `facts`
- `contradictions`
- `unknowns`
- `blindspots`
- `overall_coverage`
- `quality_snapshot`
- `dimension_coverage`

会映射到 `ProposalSnapshot.evidence` 和 `ProposalSnapshot.quality`。

### 4.3 Mapper 伪代码

```python
def build_proposal_snapshot_for_report(report_name: str, owner_user_id: int = 0) -> dict:
    content = _load_report_content(report_name)
    generated_at = _get_report_generated_at(report_name)
    content = normalize_report_time_fields(content, generated_at=generated_at)

    sidecar = read_solution_sidecar(report_name)
    if not sidecar and owner_user_id > 0:
        bound_session = find_direct_bound_session_for_report(report_name, owner_user_id)
        if isinstance(bound_session, dict):
            rebound_snapshot = build_bound_solution_sidecar_snapshot(report_name, content, bound_session)
            if rebound_snapshot:
                sidecar = rebound_snapshot

    if sidecar:
        normalized_snapshot = _normalize_solution_snapshot(sidecar)
        if str(normalized_snapshot.get("snapshot_stage") or "").strip().lower() != "final_report":
            normalized_snapshot = build_final_solution_sidecar_snapshot(normalized_snapshot, content)
    else:
        normalized_snapshot = build_solution_snapshot_from_markdown_report(report_name, content)

    evidence_pack = {}
    session_id = str((normalized_snapshot or {}).get("session_id") or "").strip()
    if session_id:
        session_file = SESSIONS_DIR / f"{session_id}.json"
        session = safe_load_session(session_file)
        if isinstance(session, dict):
            evidence_pack = build_report_evidence_pack(session)

    return map_deepvision_snapshot_to_proposal_snapshot(
        normalized_snapshot=normalized_snapshot,
        evidence_pack=evidence_pack,
        generated_at=generated_at,
    )
```

### 4.4 逐字段映射

- `ProposalSnapshot.source/context/content/meta`
  - 主要来自 `_normalize_solution_snapshot()`
- `ProposalSnapshot.evidence/quality`
  - 主要来自 `build_report_evidence_pack()`

映射明细：

- `source.system` <- 固定 `deepvision`
- `source.object_type` <- 固定 `report`
- `source.object_id` <- `report_name`
- `source.title` <- `normalized_snapshot.topic`
- `source.generated_at` <- `generated_at`
- `context.topic` <- `normalized_snapshot.topic`
- `context.scenario_id` <- `normalized_snapshot.scenario_id`
- `context.scenario_name` <- `normalized_snapshot.scenario_name`
- `context.report_type` <- `normalized_snapshot.report_type`
- `context.report_profile` <- `normalized_snapshot.report_profile`
- `content.overview` <- `normalized_snapshot.draft.overview`
- `content.analysis.*` <- `normalized_snapshot.draft.analysis.*`
- `content.needs` <- `normalized_snapshot.draft.needs`
- `content.solutions` <- `normalized_snapshot.draft.solutions`
- `content.risks` <- `normalized_snapshot.draft.risks`
- `content.actions` <- `normalized_snapshot.draft.actions`
- `content.open_questions` <- `normalized_snapshot.draft.open_questions`
- `content.evidence_index` <- `normalized_snapshot.draft.evidence_index`
- `evidence.facts` <- `evidence_pack.facts`
- `evidence.contradictions` <- `evidence_pack.contradictions`
- `evidence.unknowns` <- `evidence_pack.unknowns`
- `evidence.blindspots` <- `evidence_pack.blindspots`
- `quality.has_structured_evidence` <- `normalized_snapshot.has_structured_evidence`
- `quality.overall_coverage` <- `evidence_pack.overall_coverage`，否则 `normalized_snapshot.overall_coverage`
- `quality.quality_score` <- `quality_snapshot.average_quality_score`
- `quality.quality_snapshot` <- `evidence_pack.quality_snapshot`，无则回退 `normalized_snapshot.quality_snapshot`
- `quality.dimension_coverage` <- `evidence_pack.dimension_coverage`
- `meta.report_schema` <- `normalized_snapshot.report_schema`
- `meta.solution_schema` <- `normalized_snapshot.solution_schema`
- `meta.snapshot_origin` <- `normalized_snapshot.snapshot_origin`
- `meta.snapshot_stage` <- `normalized_snapshot.snapshot_stage`

## 五、接口改造

### 5.1 方案页接口

当前入口：

- [get_report_solution](../../../web/server.py) `:42221`

当前逻辑：

1. 登录校验
2. 等级能力校验
3. owner 校验
4. 本地 `build_solution_payload_from_report(...)`

目标逻辑：

1. 登录校验
2. 等级能力校验
3. owner 校验
4. `build_proposal_snapshot_for_report(...)`
5. 调用 `方案生成服务 /v1/solutions/render`
6. 把结果映射成当前前端已有结构并返回

约束：

- [web/solution.js](../../../web/solution.js) 不需要改协议
- `viewer_capabilities` 仍在 DeepVision 本地组装

### 5.2 演示文稿提交接口

当前入口：

- [send_report_to_refly](../../../web/server.py) `:42385`

当前逻辑：

1. 登录校验
2. feature gate
3. 等级能力校验
4. owner 校验
5. 直接上传报告正文并调外部 provider

目标逻辑：

1. 登录校验
2. feature gate
3. 等级能力校验
4. owner 校验
5. `build_proposal_snapshot_for_report(...)`
6. 调用 `方案生成服务 /v1/presentations/jobs`
7. 返回与当前前端兼容的 job/状态信息

### 5.3 演示文稿状态接口

当前入口：

- [get_report_presentation_status](../../../web/server.py) `:32624`

目标逻辑：

1. DeepVision 本地做登录、权限、owner 校验
2. 查询新服务 job 状态
3. 映射为当前前端消费的字段：
   - `exists`
   - `pdf_url`
   - `presentation_local_url`
   - `execution_id`
   - `processing`
   - `stopped`

### 5.4 演示文稿下载/跳转接口

当前入口：

- [get_report_presentation_link](../../../web/server.py) `:32698`

目标逻辑：

1. DeepVision 本地做登录、权限、owner 校验
2. 从新服务或本地记录中获取 artifact
3. 保持当前前端行为不变，继续输出跳转或下载响应

## 六、迁移策略

### 6.1 开关

- [ ] `PROPOSAL_SERVICE_ENABLED`
- [ ] `PROPOSAL_SERVICE_SOLUTIONS_ENABLED`
- [ ] `PROPOSAL_SERVICE_PRESENTATIONS_ENABLED`

### 6.2 fallback

方案页：

- 首选：新服务 `/v1/solutions/render`
- 回退：本地 [build_solution_payload_from_report](../../../web/server.py) `:41848`

演示文稿：

- 首选：新服务 `/v1/presentations/jobs`
- 回退：当前旧链路

### 6.3 切换顺序

1. 先上线 ProposalSnapshot mapper
2. 再切方案页
3. 再切演示文稿 job
4. 稳定后清理本地生成逻辑

## 七、测试与验收

### 7.1 必跑回归

- [ ] [tests/test_solution_payload.py](../../../tests/test_solution_payload.py)
- [ ] [tests/test_api_comprehensive.py](../../../tests/test_api_comprehensive.py)
- [ ] 方案页相关 browser smoke
- [ ] 报告详情页演示文稿轮询与下载链路回归

### 7.2 完成标准

1. DeepVision 前端无感切换。
2. 方案页 payload 结构兼容当前消费方。
3. 演示文稿按钮、轮询、下载行为保持一致。
4. 分享、权限和 owner 边界不退化。

## 八、实施任务清单

- [ ] `DV-01` 增加新服务配置项
- [ ] `DV-02` 新增 `proposal_service_client.py`
- [ ] `DV-03` 新增 `proposal_snapshot_mapper.py`
- [ ] `DV-04` 实现 sidecar 优先的标准快照组装
- [ ] `DV-05` 实现 Markdown fallback 快照组装
- [ ] `DV-06` 补 evidence/quality 映射
- [ ] `DV-07` 改造 `/api/reports/<name>/solution`
- [ ] `DV-08` 保持方案页返回结构兼容
- [ ] `DV-09` 改造演示文稿提交接口
- [ ] `DV-10` 改造演示文稿状态接口
- [ ] `DV-11` 改造演示文稿下载/跳转接口
- [ ] `DV-12` 保留 fallback 与 feature flag
- [ ] `DV-13` 补测试与迁移说明

## 九、文件级实施清单

本节把 DeepVision 侧改造进一步压实到仓库文件级别，便于按文件拆解实施、review 和回归。

### 9.1 第一批新增文件

| 编号 | 文件 | 动作 | 目的 | 对应任务 |
| --- | --- | --- | --- | --- |
| `DV-F01` | `web/server_modules/proposal_service_client.py` | 新建 | 统一封装对 `方案生成服务` 的 HTTP 调用 | `DV-02` |
| `DV-F02` | `web/server_modules/proposal_snapshot_mapper.py` | 新建 | 把报告、sidecar、evidence pack 组装为 `ProposalSnapshot v1` | `DV-03` `DV-04` `DV-05` `DV-06` |
| `DV-F03` | `tests/test_proposal_snapshot_mapper.py` | 新建 | 校验 mapper 对 sidecar、markdown fallback、evidence pack 的映射正确性 | `DV-13` |
| `DV-F04` | `tests/test_proposal_service_client.py` | 新建 | 校验新服务 client 的请求、超时、错误处理与 fallback 分支 | `DV-13` |

### 9.2 第一批修改文件

| 编号 | 文件 | 动作 | 目的 | 对应任务 |
| --- | --- | --- | --- | --- |
| `DV-F05` | `web/server.py` | 修改 | 接入 mapper 与 client，替换本地方案页/演示稿主链路 | `DV-07` `DV-08` `DV-09` `DV-10` `DV-11` |
| `DV-F06` | `web/config.py` | 修改 | 增加 `PROPOSAL_SERVICE_*` 配置默认值与读取逻辑 | `DV-01` |
| `DV-F07` | `tests/test_solution_payload.py` | 修改 | 增加新服务模式下的 payload 兼容断言 | `DV-13` |
| `DV-F08` | `tests/test_api_comprehensive.py` | 修改 | 增加新服务方案页/演示稿接口回归 | `DV-13` |
| `DV-F09` | `tests/test_security_regression.py` | 修改 | 确认权限、分享、owner 边界在新链路下不退化 | `DV-13` |

### 9.3 按接口拆解的文件动作

| 接口/能力 | 主要修改文件 | 具体动作 |
| --- | --- | --- |
| 方案页标准快照组装 | `web/server_modules/proposal_snapshot_mapper.py` | 实现 sidecar 优先、绑定 session 回补、markdown fallback、evidence pack 补齐 |
| 方案页接口 `/api/reports/<name>/solution` | `web/server.py` | 在原权限校验后调用 mapper，再调用 `proposal_service_client.render_solution()` |
| 演示稿提交接口 | `web/server.py` | 在原权限校验后调用 mapper，再调用 `proposal_service_client.create_presentation_job()` |
| 演示稿状态接口 | `web/server.py` | 调用 `proposal_service_client.get_presentation_job()`，映射为现有前端字段 |
| 演示稿下载/跳转接口 | `web/server.py` | 调用 `proposal_service_client.get_presentation_artifact()`，维持原跳转/下载行为 |
| 前端兼容验证 | `web/app_modules/report_detail_runtime.js` `web/solution.js` | 原则上不改，只做契约校对与必要断言 |

### 9.4 mapper 的文件内职责切分

建议把 `web/server_modules/proposal_snapshot_mapper.py` 拆成以下内部函数，避免一个超长函数继续堆逻辑：

| 函数 | 职责 |
| --- | --- |
| `build_proposal_snapshot_for_report()` | 外部总入口 |
| `_load_or_build_solution_snapshot()` | sidecar、绑定回补、markdown fallback 选择 |
| `_load_report_evidence_pack()` | 按 session 读取 evidence pack |
| `map_deepvision_snapshot_to_proposal_snapshot()` | 标准字段映射 |
| `_build_snapshot_source_block()` | 组装 `source` |
| `_build_snapshot_context_block()` | 组装 `context` |
| `_build_snapshot_content_block()` | 组装 `content` |
| `_build_snapshot_quality_block()` | 组装 `quality` |
| `_build_snapshot_meta_block()` | 组装 `meta` |

### 9.5 client 的文件内职责切分

建议把 `web/server_modules/proposal_service_client.py` 固定成明确的请求边界，不要把业务逻辑塞进去：

| 函数 | 职责 |
| --- | --- |
| `render_solution(snapshot, options=None)` | 调 `/v1/solutions/render` |
| `create_presentation_job(snapshot, options=None)` | 调 `/v1/presentations/jobs` |
| `get_presentation_job(job_id)` | 调 job 查询 |
| `get_presentation_artifact(job_id)` | 调 artifact 查询 |
| `_request_json(method, path, payload=None)` | 统一请求、超时、鉴权、错误处理 |

### 9.6 推荐实施顺序

1. 先新建 `DV-F01` 到 `DV-F04`，把 mapper 与 client 跑通，并补单测。
2. 再修改 `DV-F05` 和 `DV-F06`，先接方案页，再接演示稿。
3. 最后修改 `DV-F07` 到 `DV-F09`，补齐回归测试和权限验证。

### 9.7 前端文件处理原则

以下文件在本次改造中原则上不新增业务逻辑，只做兼容确认：

| 文件 | 原则 |
| --- | --- |
| [web/solution.js](../../../web/solution.js) | 不改 API 协议，除非服务返回结构与现有契约无法兼容 |
| [web/app_modules/report_detail_runtime.js](../../../web/app_modules/report_detail_runtime.js) | 不改交互流程，保持现有按钮、轮询、下载行为 |

### 9.8 文件级测试映射

| 文件 | 至少验证什么 |
| --- | --- |
| `tests/test_proposal_snapshot_mapper.py` | sidecar 主路径、markdown fallback、evidence pack 映射、空字段容错 |
| `tests/test_proposal_service_client.py` | 超时、401/403/5xx、空响应、fallback 触发 |
| `tests/test_solution_payload.py` | 新服务返回结构与旧前端契约兼容 |
| `tests/test_api_comprehensive.py` | 方案页查看、演示稿提交、状态轮询、下载 |
| `tests/test_security_regression.py` | 登录、owner、分享、license gate 边界 |

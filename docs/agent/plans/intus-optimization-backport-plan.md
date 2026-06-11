# Intus 近期优化回迁 DeepVision 实施计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 Intus 近期已验证的质量、稳定性、前端体验和发布准入优化，按 DeepVision 现有架构做差异化回迁，避免重复实现并提升发布可信度。

**架构：** 先建立 Intus 与 DeepVision 的逐项差异台账，再按风险从“访谈质量 -> 报告可信度 -> 模型韧性 -> 生产发布 -> 前端体验 -> Harness 产品流”分阶段落地。每一阶段先补失败测试或场景语料，再实现最小代码，最后进入 harness / evaluator / browser smoke 发布准入。

**技术栈：** Python unittest、Flask 后端、Alpine.js 前端、Playwright browser smoke、DeepVision agent harness、resources/harness task profile、docs/agent playbook。

---

## 一、范围与非范围

### 1.1 本计划覆盖

- 访谈问题质量闸门、浅显重复问题拦截、题干内嵌选项清理。
- 报告生成失败态收紧，避免模型失败后被模板报告伪装成成功。
- 主备模型降级机制和配置中心可观测性。
- 多 worker 生产链路下问题生成状态一致性。
- 生产镜像 Node 运行时与 `.dockerignore` 发布边界核对。
- 报告导出、证据展示、Mermaid 兼容和访谈进度前端体验。
- `product-ui-flow` 类产品 UI 发布准入任务画像。

### 1.2 本计划不覆盖

- 不直接照搬 Intus 品牌文案、首页样例、配色和 logo。
- 不修改真实云端环境变量、真实生产数据库、`data/` 运行数据。
- 不做完整视觉回归、跨浏览器矩阵或无障碍专项。
- 不把所有 Intus 文档直接复制到 DeepVision；只迁移结构和可复用流程。

### 1.3 当前已知差异

- DeepVision 已有较强的报告 V3 质量门禁、Mermaid 渲染容错和部分报告导出基础，实施前必须逐项确认差异，不能重复叠加。
- DeepVision 当前未在长期任务画像中看到 `product-ui-flow` 文件，Intus 已具备 `resources/harness/tasks/product-ui-flow.json` 与对应 playbook。
- DeepVision 当前未确认是否完整具备 Intus 的用户可见问题质量闸门、分 lane 主备模型降级、生产多 worker 问题生成修复。

## 二、推荐落地顺序

| 阶段 | 优先级 | 主题 | 目标 |
| --- | --- | --- | --- |
| Phase 0 | P0 | 差异审计 | 建立精确台账，确认哪些已存在、哪些需要补齐 |
| Phase 1 | P0 | 访谈质量 | 阻断低质题、重复题和题干内嵌选项 |
| Phase 2 | P0 | 报告可信度 | 模型失败不再生成可交付模板报告 |
| Phase 3 | P1 | 模型韧性 | 建立主备模型降级和命中指标 |
| Phase 4 | P1 | 生产稳定 | 核对多 worker、Node runtime、dockerignore |
| Phase 5 | P2 | 前端体验 | 优化导出、证据、进度、Mermaid 兼容 |
| Phase 6 | P2 | Harness 产品流 | 引入 product-ui-flow 发布准入画像 |
| Phase 7 | P0 | 发布准入 | 完整回归、工件归档和结论输出 |

## 三、文件职责规划

### 3.1 预计修改文件

- `web/server.py`：访谈问题生成、模型降级配置入口、管理配置中心展示、报告辅助函数入口。
- `web/server_modules/interview_runtime.py`：访谈问题策略、预生成缓存和多 worker 状态辅助逻辑。
- `web/server_modules/report_generation_runtime.py`：报告失败诊断落盘、模板兜底状态、报告生成主链路失败态。
- `web/app.js`：访谈进度估算、报告导出、Mermaid 导出兼容和前端提示。
- `web/app_modules/report_detail_runtime.js`：报告详情页证据入口、模板兜底或模型失败提示。
- `web/config.py`：主备模型降级默认配置。
- `deploy/Dockerfile.production`：生产镜像 Node/npm 运行时核对。
- `.dockerignore`：排除本地交接、运行态和测试工件。

### 3.2 预计新增或修改测试

- `tests/test_question_fast_strategy.py`：访谈问题质量闸门、浅显重复和重试策略。
- `tests/test_api_comprehensive.py`：报告失败态、导出文件名、进度估算、生产相关 API 行为。
- `tests/test_security_regression.py`：owner/scope 不变量、报告失败不绑定、只读分享边界。
- `tests/test_runtime_token_config.py`：模型 fallback 配置解析、主备模型候选选择。
- `tests/test_scripts_comprehensive.py`：Dockerfile、`.dockerignore`、harness task 和场景索引。

### 3.3 预计新增或修改治理工件

- `tests/harness_scenarios/report-solution/deep-interview-question-quality.json`：深度访谈质量场景。
- `resources/harness/tasks/product-ui-flow.json`：产品 UI 流程任务画像。
- `docs/agent/playbooks/product-ui-flow.md`：产品 UI 流程核对 playbook。
- `docs/agent/README.md`：登记新增 task。
- `docs/agent/evaluator.md`：登记新增 evaluator 场景。
- `docs/agent/heartbeat.md`：执行后由 heartbeat 刷新，不手写伪造。
- `docs/agent/harness-progress-phase6.md`：若阶段六实施进入正式阶段，记录进度。

## 四、实施任务

### 任务 0：建立差异审计台账

**文件：**
- 创建：`artifacts/intus-backport-audit/summary.md`
- 创建：`artifacts/intus-backport-audit/intus-symbols.txt`
- 创建：`artifacts/intus-backport-audit/deepvision-symbols.txt`
- 不提交：`artifacts/intus-backport-audit/*`

- [ ] **步骤 0.1：采集 Intus 近期优化提交**

运行：

```bash
git -C /Users/hehai/Documents/开目软件/Agents/project/Intus log --oneline --no-merges -40
```

预期：能看到 `70a2290`、`3977f12`、`dc456df`、`2299bc5`、`bf82480`、`cc1a497` 等提交。

- [ ] **步骤 0.2：采集 Intus 关键符号**

运行：

```bash
mkdir -p artifacts/intus-backport-audit
rg -n "evaluate_visible_question_quality_gate|MODEL_FALLBACK_ENABLED|persist_report_failure_diagnostics|getProgressAlignedRemainingQuestions|normalizeMermaidBlocksForExport|product-ui-flow|deep-interview-question-quality" \
  /Users/hehai/Documents/开目软件/Agents/project/Intus/web \
  /Users/hehai/Documents/开目软件/Agents/project/Intus/tests \
  /Users/hehai/Documents/开目软件/Agents/project/Intus/resources \
  /Users/hehai/Documents/开目软件/Agents/project/Intus/docs/agent \
  -S -g '!web/vendor/**' -g '!web/version.json' \
  > artifacts/intus-backport-audit/intus-symbols.txt
```

预期：输出 Intus 中上述关键符号的位置。

- [ ] **步骤 0.3：采集 DeepVision 关键符号**

运行：

```bash
rg -n "evaluate_visible_question_quality_gate|MODEL_FALLBACK_ENABLED|persist_report_failure_diagnostics|getProgressAlignedRemainingQuestions|normalizeMermaidBlocksForExport|product-ui-flow|deep-interview-question-quality" \
  web tests resources docs/agent \
  -S -g '!web/vendor/**' -g '!web/version.json' \
  > artifacts/intus-backport-audit/deepvision-symbols.txt || true
```

预期：已有符号进入台账，缺失符号为空或缺项。

- [ ] **步骤 0.4：写差异摘要**

在 `artifacts/intus-backport-audit/summary.md` 写入：

```markdown
# Intus 优化回迁 DeepVision 差异审计

## 已确认 DeepVision 已具备

- `符号名`：`DeepVision 文件路径:行号` 已存在；对应测试为 `tests/具体测试文件.py::具体测试名`；与 Intus 差异为“无需回迁 / 只需补阈值 / 只需补文案”。

## 已确认 DeepVision 缺失或不完整

- `符号名`：Intus 位于 `/Users/hehai/Documents/开目软件/Agents/project/Intus/具体文件:行号`；DeepVision 未检出或行为不完整；建议进入 `任务 N`。

## 需要逐文件 diff 后确认

- `能力名称`：两个仓库存在同名或近似函数，但调用链、默认配置或测试覆盖不同；执行 `git -C /Users/hehai/Documents/开目软件/Agents/project/Intus show <commit> -- <file>` 与 DeepVision 当前文件对照后再决定。

## 建议进入实施的任务

- `任务 1`：访谈问题质量闸门，条件是 DeepVision 未覆盖用户可见低质题拦截。
- `任务 2`：报告生成失败态收紧，条件是模型失败仍可能绑定模板报告。
- `任务 3`：主备模型降级，条件是 DeepVision 缺少分 lane fallback 或命中指标。
```

- [ ] **步骤 0.5：不提交 artifacts**

运行：

```bash
git status --short
```

预期：`artifacts/intus-backport-audit/*` 不作为正式提交内容，除非用户明确要求保留审计工件。

### 任务 1：访谈问题质量闸门

**文件：**
- 修改：`web/server.py`
- 修改：`web/server_modules/interview_runtime.py`
- 测试：`tests/test_question_fast_strategy.py`
- 测试：`tests/test_scripts_comprehensive.py`
- 创建或修改：`tests/harness_scenarios/report-solution/deep-interview-question-quality.json`

- [ ] **步骤 1.1：编写低质可见问题闸门测试**

在 `tests/test_question_fast_strategy.py` 增加测试，覆盖泛化题、模板选项、占位符选项：

```python
def test_visible_question_quality_gate_rejects_generic_question(self):
    payload = {
        "question": "请介绍一下你的情况？",
        "options": ["非常重要", "比较重要", "一般", "不重要"],
    }
    result = self.server.evaluate_visible_question_quality_gate(
        payload,
        session={"topic": "工业视觉质检系统"},
        dimension="业务目标",
        source="unit-test",
    )
    self.assertFalse(result["ok"])
    self.assertIn("generic", result["reasons"])
```

- [ ] **步骤 1.2：编写题干内嵌选项清理测试**

在同一文件增加测试：

```python
def test_visible_question_quality_gate_cleans_embedded_options(self):
    payload = {
        "question": "你们更关注哪类能力？A. 缺陷检测 B. 尺寸测量 C. 追溯分析",
        "options": ["缺陷检测", "尺寸测量", "追溯分析"],
    }
    cleaned = self.server.clean_visible_question_text(payload["question"])
    self.assertNotIn("A.", cleaned)
    self.assertNotIn("B.", cleaned)
    self.assertIn("更关注哪类能力", cleaned)
```

- [ ] **步骤 1.3：编写缓存低质题被丢弃测试**

在同一文件增加测试：

```python
def test_cached_low_quality_question_is_rejected_before_serving(self):
    question = {
        "question": "请问还有什么补充？",
        "options": ["选项A", "选项B", "选项C"],
        "source": "cache",
    }
    result = self.server.should_reject_visible_question(
        question,
        session={"topic": "钢铁产线视觉检测"},
        dimension="场景约束",
        source="cache",
    )
    self.assertTrue(result["reject"])
    self.assertIn("visible_quality_gate", result["reason"])
```

- [ ] **步骤 1.4：运行测试确认失败**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_question_fast_strategy
```

预期：FAIL，原因是 `evaluate_visible_question_quality_gate`、`clean_visible_question_text` 或 `should_reject_visible_question` 未定义，或当前实现未拦截低质题。

- [ ] **步骤 1.5：实现可见问题质量闸门**

在 `web/server.py` 增加或补齐以下函数，并在实际问题生成、缓存命中和预生成命中前调用：

```python
def clean_visible_question_text(text: object) -> str:
    source = str(text or "").strip()
    source = re.sub(r"(?i)(^|\s)[A-D][.、]\s*[^A-D\n]+", " ", source)
    source = re.sub(r"\s+", " ", source).strip(" ：:")
    return source


def evaluate_visible_question_quality_gate(payload: dict, session: Optional[dict] = None, dimension: str = "", source: str = "") -> dict:
    question = clean_visible_question_text((payload or {}).get("question", ""))
    options = [str(item or "").strip() for item in ((payload or {}).get("options") or [])]
    reasons = []
    if len(question) < 8:
        reasons.append("too_short")
    if re.search(r"(你的情况|还有什么补充|请介绍一下|是否有需求)", question):
        reasons.append("generic_question")
    generic_options = {"选项A", "选项B", "选项C", "非常重要", "比较重要", "一般", "不重要"}
    if options and sum(1 for item in options if item in generic_options) >= max(1, len(options) // 2):
        reasons.append("generic_options")
    if not any(str(value or "").strip() and str(value or "").strip() in question for value in [
        (session or {}).get("topic"),
        dimension,
    ]):
        if len(question) < 18:
            reasons.append("weak_context")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "question": question,
        "source": source,
    }
```

说明：实际落地时优先复用 Intus 已验证实现，但命名、阈值和 DeepVision 领域词要按 DeepVision 当前代码调整。

- [ ] **步骤 1.6：接入问题生成链路**

在 `get_next_question`、预生成缓存读取和 fast 生成结果返回前统一调用：

```python
quality_gate = evaluate_visible_question_quality_gate(
    candidate_payload,
    session=session,
    dimension=dimension_name,
    source=question_source,
)
if not quality_gate.get("ok"):
    mark_question_quality_rejected(session, quality_gate)
    candidate_payload = retry_full_question_generation(...)
```

预期：低质 fast 问题不会直接展示给用户；full 重试失败时才进入明确的备用题。

- [ ] **步骤 1.7：补 evaluator 场景**

创建或同步 `tests/harness_scenarios/report-solution/deep-interview-question-quality.json`：

```json
{
  "name": "deep-interview-question-quality",
  "category": "report-solution",
  "tags": ["nightly", "stability-local", "interview", "quality-gate"],
  "executor": "unittest",
  "command": "python3 -m unittest tests.test_question_fast_strategy",
  "budget_seconds": 120,
  "description": "覆盖深度访谈问题质量闸门、浅显重复拦截、题干内嵌选项清理和 fast/full 重试边界"
}
```

- [ ] **步骤 1.8：运行测试验证通过**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_question_fast_strategy tests.test_scripts_comprehensive
```

预期：PASS。

- [ ] **步骤 1.9：Commit**

```bash
git add web/server.py web/server_modules/interview_runtime.py tests/test_question_fast_strategy.py tests/test_scripts_comprehensive.py tests/harness_scenarios/report-solution/deep-interview-question-quality.json
git commit -m "优化访谈问题质量闸门

访谈：拦截泛化题干、模板选项和题干内嵌选项。
测试：补充深度访谈问题质量场景和回归覆盖。"
```

### 任务 2：报告生成失败态收紧

**文件：**
- 修改：`web/server_modules/report_generation_runtime.py`
- 修改：`web/app_modules/report_detail_runtime.js`
- 测试：`tests/test_security_regression.py`
- 测试：`tests/test_api_comprehensive.py`

- [ ] **步骤 2.1：编写模型失败不绑定模板报告测试**

在 `tests/test_security_regression.py` 增加测试：

```python
def test_report_generation_model_failure_does_not_bind_template_report(self):
    session = {
        "id": "model-fail-session",
        "topic": "工业视觉检测",
        "report_status": "generating",
        "report_name": "",
    }
    result = self.server_modules["report_generation_runtime"].persist_report_failure_diagnostics(
        session=session,
        reason="model_generation_failed",
        error="upstream 503",
        stage="draft_generation",
    )
    self.assertEqual(result["status"], "failed")
    self.assertEqual(session.get("report_status"), "failed")
    self.assertFalse(session.get("report_name"))
    self.assertEqual(session.get("last_report_v3_debug", {}).get("runtime_path"), "model_generation_failed")
```

- [ ] **步骤 2.2：编写前端提示分类测试**

在 `tests/test_scripts_comprehensive.py` 或已有 JS 静态检查中增加断言：

```python
def test_report_detail_distinguishes_model_failure_from_template_fallback(self):
    content = Path("web/app_modules/report_detail_runtime.js").read_text(encoding="utf-8")
    self.assertIn("isModelGenerationFailedResult", content)
    self.assertIn("isTemplateFallbackReportResult", content)
    self.assertIn("模型报告生成失败", content)
    self.assertIn("模板兜底", content)
```

- [ ] **步骤 2.3：运行测试确认失败**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_security_regression tests.test_scripts_comprehensive
```

预期：FAIL，若 DeepVision 已有同类能力，则失败点应转为断言命名或行为差异。

- [ ] **步骤 2.4：实现失败诊断落盘**

在 `web/server_modules/report_generation_runtime.py` 补齐：

```python
def persist_report_failure_diagnostics(session: dict, reason: str, error: str = "", stage: str = "") -> dict:
    diagnostics = {
        "reason": reason or "model_generation_failed",
        "error": str(error or ""),
        "parse_stage": stage or "model_generation",
        "runtime_path": "model_generation_failed",
    }
    session["report_status"] = "failed"
    session["report_error"] = "模型报告生成失败，未生成可交付报告"
    session["last_report_v3_debug"] = diagnostics
    session.pop("report_name", None)
    return {"status": "failed", "diagnostics": diagnostics}
```

如果当前文件已有同名函数，应以现有实现为准，只补缺失字段和行为。

- [ ] **步骤 2.5：阻断模板伪成功路径**

在报告生成异常处理处确保：

```python
if model_generation_failed and not explicit_template_fallback_enabled:
    return persist_report_failure_diagnostics(
        session=session,
        reason="model_generation_failed",
        error=str(exc),
        stage="draft_generation",
    )
```

预期：只有明确启用模板兜底且返回内容被标记为 `template_fallback` 时，前端才显示兜底成功；模型失败默认失败。

- [ ] **步骤 2.6：补前端状态文案**

在 `web/app_modules/report_detail_runtime.js` 增加：

```javascript
function isModelGenerationFailedResult(result = {}) {
    const debug = result.last_report_v3_debug || result.debug || {};
    return result.report_status === 'failed'
        || debug.runtime_path === 'model_generation_failed'
        || debug.reason === 'model_generation_failed';
}

function isTemplateFallbackReportResult(result = {}) {
    const debug = result.last_report_v3_debug || result.debug || {};
    return result.runtime_path === 'simple_template_fallback'
        || debug.runtime_path === 'simple_template_fallback'
        || result.template_fallback === true;
}
```

并将失败提示统一为：

```javascript
'模型报告生成失败，未生成可交付报告，请检查模型服务后重试'
```

- [ ] **步骤 2.7：运行测试验证通过**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_security_regression tests.test_api_comprehensive tests.test_scripts_comprehensive
```

预期：PASS。

- [ ] **步骤 2.8：Commit**

```bash
git add web/server_modules/report_generation_runtime.py web/app_modules/report_detail_runtime.js tests/test_security_regression.py tests/test_api_comprehensive.py tests/test_scripts_comprehensive.py
git commit -m "收紧报告生成失败态

报告：模型失败时记录失败诊断并阻断模板伪成功。
前端：区分模型失败和显式模板兜底提示。
测试：补充失败态不绑定报告的回归覆盖。"
```

### 任务 3：主备模型降级机制

**文件：**
- 修改：`web/config.py`
- 修改：`web/server.py`
- 测试：`tests/test_runtime_token_config.py`
- 测试：`tests/test_api_comprehensive.py`

- [ ] **步骤 3.1：编写 fallback 配置解析测试**

在 `tests/test_runtime_token_config.py` 增加：

```python
def test_model_fallback_config_defaults_are_available(self):
    self.assertTrue(hasattr(self.server, "MODEL_FALLBACK_ENABLED"))
    self.assertTrue(hasattr(self.server, "QUESTION_FALLBACK_MODEL_NAME"))
    self.assertTrue(hasattr(self.server, "REPORT_DRAFT_FALLBACK_MODEL_NAME"))
    candidates = self.server.resolve_model_candidates("question", primary="primary-model")
    self.assertGreaterEqual(len(candidates), 1)
    self.assertEqual(candidates[0], "primary-model")
```

- [ ] **步骤 3.2：编写主模型失败后命中备用模型测试**

在同一文件增加：

```python
def test_call_model_with_fallback_tries_backup_after_retryable_failure(self):
    calls = []

    def fake_call(model_name, *_args, **_kwargs):
        calls.append(model_name)
        if model_name == "primary-model":
            raise RuntimeError("503 unavailable")
        return {"content": "backup-ok", "model": model_name}

    result = self.server.call_model_with_fallback(
        lane="question",
        primary_model="primary-model",
        fallback_model="backup-model",
        call_func=fake_call,
    )
    self.assertEqual(result["content"], "backup-ok")
    self.assertEqual(calls, ["primary-model", "backup-model"])
```

- [ ] **步骤 3.3：运行测试确认失败**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_runtime_token_config
```

预期：FAIL，原因是配置或 helper 不存在。

- [ ] **步骤 3.4：新增配置默认值**

在 `web/config.py` 增加：

```python
MODEL_FALLBACK_ENABLED = True
QUESTION_FALLBACK_MODEL_NAME = "kimi-for-coding"
QUESTION_MODEL_NAME_DEEP_FALLBACK = "doubao-seed-2-0-pro"
REPORT_DRAFT_FALLBACK_MODEL_NAME = "doubao-seed-2-0-pro"
REPORT_REVIEW_FALLBACK_MODEL_NAME = "gemini-3.1-pro-preview"
SUMMARY_FALLBACK_MODEL_NAME = "doubao-seed-2-0-pro"
SEARCH_DECISION_FALLBACK_MODEL_NAME = "doubao-seed-2-0-pro"
ASSESSMENT_FALLBACK_MODEL_NAME = "doubao-seed-2-0-pro"
```

如果 DeepVision 已有这些字段，则只补缺项，不改已有默认模型路由。

- [ ] **步骤 3.5：实现候选模型解析**

在 `web/server.py` 增加或补齐：

```python
def resolve_model_candidates(lane: str, primary: str = "", fallback: str = "") -> list:
    candidates = []
    for item in [primary, fallback]:
        value = str(item or "").strip()
        if value and value not in candidates:
            candidates.append(value)
    return candidates
```

- [ ] **步骤 3.6：实现串行降级调用壳**

在 `web/server.py` 增加：

```python
def call_model_with_fallback(lane: str, primary_model: str, fallback_model: str = "", call_func=None, *args, **kwargs):
    if call_func is None:
        raise ValueError("call_func is required")
    candidates = resolve_model_candidates(lane, primary=primary_model, fallback=fallback_model if MODEL_FALLBACK_ENABLED else "")
    last_error = None
    for index, model_name in enumerate(candidates):
        try:
            result = call_func(model_name, *args, **kwargs)
            record_model_fallback_metric(lane=lane, model_name=model_name, fallback_hit=index > 0)
            return result
        except Exception as exc:
            last_error = exc
            if not is_retryable_model_error(exc):
                raise
    raise last_error
```

实际接入时要优先接现有模型调用函数，不新增平行模型网关。

- [ ] **步骤 3.7：配置中心展示 fallback**

在管理配置中心 payload 中加入：

```python
_admin_bool("MODEL_FALLBACK_ENABLED", "启用主备模型降级")
```

并展示每条 lane 的主模型和备用模型字段。

- [ ] **步骤 3.8：接入问题、报告、摘要、搜索和评分 lane**

按 lane 分批替换：

```python
call_model_with_fallback(
    lane="report_draft",
    primary_model=REPORT_DRAFT_MODEL_NAME,
    fallback_model=REPORT_DRAFT_FALLBACK_MODEL_NAME,
    call_func=call_chat_model,
    messages=messages,
)
```

每次替换后运行对应单测，避免一次性大改。

- [ ] **步骤 3.9：运行测试验证通过**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_runtime_token_config tests.test_api_comprehensive
```

预期：PASS。

- [ ] **步骤 3.10：Commit**

```bash
git add web/config.py web/server.py tests/test_runtime_token_config.py tests/test_api_comprehensive.py
git commit -m "增加主备模型降级机制

模型：按业务 lane 解析主备候选并串行降级。
运维：配置中心展示模型降级开关和备用模型。
测试：补充配置解析和备用模型命中回归。"
```

### 任务 4：生产发布稳定性核对

**文件：**
- 修改：`deploy/Dockerfile.production`
- 修改：`.dockerignore`
- 修改：`web/server_modules/interview_runtime.py`
- 测试：`tests/test_scripts_comprehensive.py`
- 测试：`tests/test_question_fast_strategy.py`

- [ ] **步骤 4.1：编写 Dockerfile Node runtime 检查**

在 `tests/test_scripts_comprehensive.py` 增加：

```python
def test_production_dockerfile_includes_node_runtime_when_browser_smoke_supported(self):
    content = Path("deploy/Dockerfile.production").read_text(encoding="utf-8")
    self.assertIn("node", content.lower())
    self.assertIn("npm -v", content)
```

- [ ] **步骤 4.2：编写 dockerignore 排除本地交接文件测试**

在同一文件增加：

```python
def test_dockerignore_excludes_local_handoff_and_runtime_artifacts(self):
    content = Path(".dockerignore").read_text(encoding="utf-8")
    for pattern in ["artifacts/", "data/", "handoff", ".env.local"]:
        self.assertIn(pattern, content)
```

- [ ] **步骤 4.3：编写多 worker 状态一致性测试**

在 `tests/test_question_fast_strategy.py` 增加：

```python
def test_question_generation_pending_state_can_be_recovered_across_workers(self):
    session = {"id": "multi-worker-session", "pending_question_generation": True}
    recovered = self.server.recover_stale_question_generation_state(
        session,
        now_ts=120,
        started_ts=0,
        timeout_seconds=60,
    )
    self.assertTrue(recovered)
    self.assertFalse(session.get("pending_question_generation"))
```

- [ ] **步骤 4.4：运行测试确认失败或确认已满足**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_scripts_comprehensive tests.test_question_fast_strategy
```

预期：若 DeepVision 已满足，则 PASS；否则 FAIL 并进入实现。

- [ ] **步骤 4.5：补生产镜像 Node/npm**

在 `deploy/Dockerfile.production` 确保安装并验证 Node/npm：

```dockerfile
RUN apk add --no-cache nodejs npm \
    && node -v \
    && npm -v
```

如果基础镜像不是 Alpine，按现有 Dockerfile 包管理器调整，不改无关层。

- [ ] **步骤 4.6：补 dockerignore 边界**

在 `.dockerignore` 确保包含：

```dockerignore
artifacts/
data/
*.handoff
handoff/
web/.env.local
web/.env.cloud
```

- [ ] **步骤 4.7：补多 worker 恢复逻辑**

在 `web/server_modules/interview_runtime.py` 或现有状态管理处增加：

```python
def recover_stale_question_generation_state(session: dict, now_ts: float, started_ts: float, timeout_seconds: int = 60) -> bool:
    if not session.get("pending_question_generation"):
        return False
    if float(now_ts or 0) - float(started_ts or 0) < timeout_seconds:
        return False
    session["pending_question_generation"] = False
    session["question_generation_recovered"] = True
    return True
```

实际实现需接入当前 session 保存路径，确保恢复后落盘。

- [ ] **步骤 4.8：运行测试验证通过**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_scripts_comprehensive tests.test_question_fast_strategy
```

预期：PASS。

- [ ] **步骤 4.9：Commit**

```bash
git add deploy/Dockerfile.production .dockerignore web/server_modules/interview_runtime.py tests/test_scripts_comprehensive.py tests/test_question_fast_strategy.py
git commit -m "加固生产发布运行时边界

发布：核对生产镜像 Node/npm 运行时和 Docker 排除规则。
访谈：恢复多 worker 下过期的问题生成状态。
测试：补充镜像边界和状态恢复回归。"
```

### 任务 5：报告导出与前端体验增强

**文件：**
- 修改：`web/app.js`
- 修改：`web/app_modules/report_detail_runtime.js`
- 修改：`web/index.html`
- 测试：`tests/test_scripts_comprehensive.py`
- 可选：`scripts/agent_browser_smoke_runner.mjs`

- [ ] **步骤 5.1：编写导出文件名测试**

在 `tests/test_scripts_comprehensive.py` 增加：

```python
def test_report_export_filename_is_readable(self):
    content = Path("web/app.js").read_text(encoding="utf-8")
    self.assertIn("getReportExportBaseFilename", content)
    self.assertIn("sanitizeExportFilenameSegment", content)
```

- [ ] **步骤 5.2：编写 Mermaid 导出兼容测试**

在同一文件增加：

```python
def test_report_export_normalizes_mermaid_blocks(self):
    content = Path("web/app.js").read_text(encoding="utf-8")
    self.assertIn("normalizeMermaidBlocksForExport", content)
    self.assertIn("quadrantChart", content)
```

- [ ] **步骤 5.3：编写证据入口测试**

在同一文件增加：

```python
def test_report_detail_has_evidence_appendix_entry(self):
    content = Path("web/app_modules/report_detail_runtime.js").read_text(encoding="utf-8")
    self.assertIn("viewReportEvidenceAppendix", content)
    self.assertIn("完整访谈记录", content)
```

- [ ] **步骤 5.4：运行测试确认失败或确认已满足**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_scripts_comprehensive
```

预期：若 DeepVision 已有同类函数，则 PASS 或只需补缺失文案；否则 FAIL。

- [ ] **步骤 5.5：补导出文件名函数**

在 `web/app.js` 对应报告导出模块中补齐：

```javascript
sanitizeExportFilenameSegment(value = '') {
    return String(value || '')
        .replace(/[\\/:*?"<>|]+/g, '-')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '')
        .slice(0, 48) || '未命名报告';
},

getReportExportBaseFilename(report = {}) {
    const date = new Date().toISOString().slice(0, 10).replaceAll('-', '');
    const title = this.sanitizeExportFilenameSegment(report.title || report.topic || '');
    return `DeepVision-${date}-${title}`;
},
```

- [ ] **步骤 5.6：补 Mermaid 导出兼容**

在 `web/app.js` 增加或补齐：

```javascript
normalizeMermaidBlocksForExport(content = '') {
    return String(content || '').replace(/```mermaid([\s\S]*?)```/g, (_match, body) => {
        const normalized = String(body || '')
            .replace(/\|\s*([^|]+?)\s*\|/g, (_m, label) => `|${String(label).replace(/[|]/g, ' ')}|`)
            .replace(/\s+$/gm, '');
        return `\`\`\`mermaid${normalized}\n\`\`\``;
    });
},
```

实际实现要保留 DeepVision 现有 `normalizeMermaidDefinition`、`normalizeMermaidFlowchartLabels` 等逻辑。

- [ ] **步骤 5.7：补证据入口**

在 `web/app_modules/report_detail_runtime.js` 增加：

```javascript
viewReportEvidenceAppendix(report = {}) {
    const sessionId = report.session_id || report.sessionId || '';
    if (!sessionId) {
        this.showToast?.('当前报告未关联访谈记录', 'warning');
        return;
    }
    window.open(`/?session=${encodeURIComponent(sessionId)}&view=evidence`, '_blank');
    this.showToast?.('已打开完整访谈记录，可查看报告依据来源', 'success');
}
```

- [ ] **步骤 5.8：补访谈进度一致性**

在 `web/app.js` 保证：

```javascript
getProgressAlignedRemainingQuestions(answered, progress, fallbackRemaining) {
    const numericAnswered = Number(answered || 0);
    const numericProgress = Math.max(0, Math.min(100, Number(progress || 0)));
    if (numericProgress <= 0) return Math.max(0, Number(fallbackRemaining || 0));
    const estimatedTotal = Math.ceil(numericAnswered / (numericProgress / 100));
    return Math.max(0, estimatedTotal - numericAnswered);
},
```

并让 `getEstimatedRemainingQuestions()` 使用该函数。

- [ ] **步骤 5.9：运行脚本和 browser smoke**

运行：

```bash
node --check web/app.js
node --check web/app_modules/report_detail_runtime.js
python3 scripts/agent_browser_smoke.py --suite extended --artifact-dir artifacts/intus-backport-browser
```

预期：JS 语法通过，extended browser smoke PASS 或只出现可解释 WARN。

- [ ] **步骤 5.10：Commit**

```bash
git add web/app.js web/app_modules/report_detail_runtime.js web/index.html tests/test_scripts_comprehensive.py scripts/agent_browser_smoke_runner.mjs
git commit -m "优化报告导出与前端体验

前端：统一导出文件名、证据入口和访谈剩余题数估算。
报告：增强 Mermaid 导出兼容处理。
测试：补充导出、证据入口和浏览器烟测覆盖。"
```

### 任务 6：引入 product-ui-flow 发布准入画像

**文件：**
- 创建：`resources/harness/tasks/product-ui-flow.json`
- 生成或修改：`docs/agent/playbooks/product-ui-flow.md`
- 修改：`docs/agent/README.md`
- 修改：`docs/agent/evaluator.md`
- 测试：`tests/test_scripts_comprehensive.py`

- [ ] **步骤 6.1：编写 task profile 索引测试**

在 `tests/test_scripts_comprehensive.py` 增加：

```python
def test_product_ui_flow_task_profile_is_registered(self):
    profile = Path("resources/harness/tasks/product-ui-flow.json")
    self.assertTrue(profile.exists())
    data = json.loads(profile.read_text(encoding="utf-8"))
    self.assertEqual(data["name"], "product-ui-flow")
    self.assertIn("browser_smoke", json.dumps(data, ensure_ascii=False))
```

- [ ] **步骤 6.2：运行测试确认失败**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest tests.test_scripts_comprehensive
```

预期：FAIL，`product-ui-flow.json` 不存在或未登记。

- [ ] **步骤 6.3：创建 task profile**

创建 `resources/harness/tasks/product-ui-flow.json`：

```json
{
  "name": "product-ui-flow",
  "title": "产品 UI 流程发布准入",
  "category": "browser",
  "risk": "medium",
  "description": "覆盖登录、License gate、业务壳、访谈、报告详情、方案页、公开分享和配置中心的轻量前端体验准入。",
  "preconditions": [
    "requires_browser_env"
  ],
  "commands": [
    "python3 scripts/agent_browser_smoke.py --suite extended",
    "python3 scripts/agent_browser_smoke.py --suite live-minimal"
  ],
  "acceptance": [
    "关键页面桌面与移动视口无明显遮挡和主按钮不可点",
    "登录、License、访谈、报告详情、方案页、公开分享和配置中心有加载态或错误态",
    "刷新后 URL、状态和主操作提示保持一致",
    "只读分享不可写，表单和弹窗不重复提交"
  ],
  "evidence": [
    "artifacts/ci/browser-smoke/latest.json",
    "artifacts/harness-runs/latest-progress.md"
  ],
  "playbook": "docs/agent/playbooks/product-ui-flow.md"
}
```

- [ ] **步骤 6.4：生成 playbook**

运行：

```bash
python3 scripts/agent_playbook_sync.py --task product-ui-flow
```

预期：生成或更新 `docs/agent/playbooks/product-ui-flow.md`。

- [ ] **步骤 6.5：更新索引**

在 `docs/agent/README.md` 和 `docs/agent/evaluator.md` 中登记 `product-ui-flow`，说明其覆盖范围和推荐命令。

- [ ] **步骤 6.6：运行同步检查**

运行：

```bash
python3 scripts/agent_playbook_sync.py --check
python3 scripts/agent_ops.py task-gap
python3 -m unittest tests.test_scripts_comprehensive
```

预期：PASS，task gap 不新增阻断。

- [ ] **步骤 6.7：Commit**

```bash
git add resources/harness/tasks/product-ui-flow.json docs/agent/playbooks/product-ui-flow.md docs/agent/README.md docs/agent/evaluator.md tests/test_scripts_comprehensive.py
git commit -m "新增产品 UI 流程准入画像

Harness：新增 product-ui-flow 任务画像和前端体验验收标准。
文档：同步产品 UI 流程 playbook 与 Agent 索引。
测试：补充任务画像登记回归。"
```

### 任务 7：发布准入回归与报告

**文件：**
- 创建：`artifacts/intus-backport-release/summary.md`
- 不提交：`artifacts/intus-backport-release/*`

- [ ] **步骤 7.1：运行静态 guardrail**

运行：

```bash
python3 scripts/agent_static_guardrails.py
```

预期：PASS。

- [ ] **步骤 7.2：运行核心 unittest**

运行：

```bash
uv run --with flask --with flask-cors --with markdown --with requests --with beautifulsoup4 --with psutil --with docx --with PyMuPDF --with Pillow --with reportlab --with pydantic --with python-dotenv python -m unittest \
  tests.test_api_comprehensive \
  tests.test_security_regression \
  tests.test_solution_payload \
  tests.test_scripts_comprehensive \
  tests.test_version_manager \
  tests.test_runtime_token_config \
  tests.test_question_fast_strategy
```

预期：PASS。

- [ ] **步骤 7.3：运行 harness core**

运行：

```bash
python3 scripts/agent_harness.py --profile stability-local-core --artifact-dir artifacts/intus-backport-release/core
```

预期：PASS 或仅有可解释 WARN。

- [ ] **步骤 7.4：运行 evaluator**

运行：

```bash
python3 scripts/agent_eval.py --tag stability-local --artifact-dir artifacts/intus-backport-release/eval
```

预期：PASS 或仅有可解释 WARN。

- [ ] **步骤 7.5：运行扩展 browser smoke**

运行：

```bash
python3 scripts/agent_browser_smoke.py --suite extended --artifact-dir artifacts/intus-backport-release/browser-extended
```

预期：PASS；若失败，需判断是否属于按钮不可点、状态卡死、刷新丢上下文、只读态可写或错误态无反馈。

- [ ] **步骤 7.6：运行 live-minimal 手动深回归**

运行：

```bash
python3 scripts/agent_browser_smoke.py --suite live-minimal --artifact-dir artifacts/intus-backport-release/browser-live-minimal
```

预期：完成验证码登录、License 绑定和业务壳链路；本地 mock 短信可记录 WARN。

- [ ] **步骤 7.7：生成发布准入摘要**

创建 `artifacts/intus-backport-release/summary.md`：

```markdown
# Intus 优化回迁 DeepVision 发布准入报告

## 结论

- [建议发布 / 可发布但需记录 WARN / 暂缓发布 / 阻断发布]

## 已实施优化

- [列出 commit 和任务编号]

## 验证命令

- [列出命令、结果和 artifact 路径]

## WARN

- [列出 WARN 分类、影响和是否阻断]

## 阻断项

- [列出失败命令、失败证据和建议下一步]

## 前端体验结论

- [桌面/移动、关键路径、刷新恢复、弹窗表单、只读态]
```

- [ ] **步骤 7.8：最终状态检查**

运行：

```bash
git status --short
git diff --check
python3 scripts/agent_history.py --kind harness-stability-release --limit 5
```

预期：无格式错误；未提交文件只包含用户认可的 artifacts 或工作产物。

## 五、验收标准

### 5.1 必须满足

- 所有已选择实施的任务都有对应失败测试、实现和通过测试。
- `python3 scripts/agent_static_guardrails.py` 通过。
- 核心 unittest 通过。
- `stability-local-core` 和 `stability-local` evaluator 通过或仅有明确 WARN。
- `extended` browser smoke 通过。
- 如果改动影响登录、License、访谈、报告、方案页或分享，必须跑 `live-minimal`。

### 5.2 阻断发布

- 访谈主链路无法生成可用问题。
- 模型失败后仍被保存为正式可交付报告。
- owner/scope、公开分享只读、账号边界出现回归。
- 主备模型降级吞掉认证错误或权限错误。
- 生产镜像无法启动，或 Node/npm 依赖缺失导致发布后工具链不可用。
- 前端关键路径出现按钮不可点、状态卡死、刷新后丢上下文、只读态可写、错误态无反馈。

### 5.3 可放行 WARN

- 本地 mock 短信不可真实发送。
- 可选云端凭据缺失。
- 历史 latest 指针陈旧。
- 已知 DeprecationWarning。
- 轻微视觉问题，但不影响主流程完成和数据边界。

## 六、风险与回滚

- 访谈质量闸门可能误杀短问题。回滚方式：关闭闸门开关或放宽 `weak_context` 规则。
- 模型 fallback 可能掩盖主模型质量波动。回滚方式：关闭 `MODEL_FALLBACK_ENABLED`，保留指标观察。
- 报告失败态收紧可能让历史依赖模板报告的流程从成功变失败。回滚方式：只允许显式模板兜底，并在前端标记非正式报告。
- Node runtime 会增加镜像体积。回滚方式：仅在 browser smoke 或生产任务确实需要 npm 时保留。
- `product-ui-flow` 会增加发布准入耗时。回滚方式：先作为手动或 nightly 场景，不进入 PR lane。

## 七、建议评审决策

建议先批准：

1. 任务 0：差异审计。
2. 任务 1：访谈问题质量闸门。
3. 任务 2：报告生成失败态收紧。

建议第二批批准：

4. 任务 3：主备模型降级。
5. 任务 4：生产发布稳定性核对。

建议产品侧确认后再批准：

6. 任务 5：报告导出与前端体验增强。
7. 任务 6：product-ui-flow 发布准入画像。

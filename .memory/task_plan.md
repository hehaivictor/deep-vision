# Task Plan: V3 报告链路 P0-P2 实施

## Goal
按既定 P0/P1/P2 方案完成问题链路、证据口径、V3 门禁与 failover 的代码落地，并通过定向回归验证主路径。

## Phases
- [x] Phase 1: 复盘失败会话与现有实现
- [x] Phase 2: 识别设计问题、参数问题与隐藏问题
- [x] Phase 3: 整理完整整改方案
- [x] Phase 4: 落地问题采集契约与高取证问题运行时策略
- [x] Phase 5: 落地 coverage/quality/weak binding/failover 改造
- [x] Phase 6: 补前端提交字段与定向回归测试
- [x] Phase 7: 去掉强制依据输入，改为 rich option + 轻追问补证据
- [x] Phase 8: 增加历史会话证据补标 helper 与批量迁移脚本
- [x] Phase 9: 强化 blindspot/not_actionable 的 deterministic repair

## Key Questions
1. 取证型问题如何避免被 `summary` 竞速拉低证据密度？
2. coverage 与质量均值如何从“看起来完整”改成“真实可用”？
3. weak binding 与 failover 怎样从统一硬规则升级为字段感知和 deterministic bucket？
4. 前后端如何透传问题契约，确保用户回答能直接服务 V3 证据链？

## Decisions Made
- 问题链路新增 `answer_mode / requires_rationale / evidence_intent`，并由后端 runtime profile 驱动高取证档位。
- 高取证问题禁用 `summary` 动态晋升，并固定使用 `question -> report` 竞速组合。
- coverage 改为“关键方面覆盖 + 质量加权覆盖”，质量快照同时输出 raw/positive-only 均值。
- weak binding 改为字段感知，failover 扩展为 deterministic bucket。
- 前端不再强制“补充选择依据”，高取证题改为“单击优先 + 必要时下一题轻追问”。
- 报告证据链新增 `answer_evidence_class`，将高信息量选项回答识别为 `rich_option` 并按中间权重计入 V3 质量门。
- `build_report_evidence_pack` 在分析前会先按当前规则重算历史 `interview_log` 的契约、质量和证据分类。
- 新增 `scripts/migrate_session_evidence_annotations.py`，支持对旧会话做 dry-run 或正式落盘迁移。
- `apply_deterministic_report_repairs_v3` 现在会主动修复 `not_actionable`，自动补齐 `owner / timeline / metric`，并在需要时补弱绑定证据引用。
- `blindspot -> actions` 修复从“待验证行动”升级为“可执行 action”，会依据维度和文本推断 owner/timeline/metric。

## Errors Encountered
- `py_compile` 默认写系统缓存目录被沙箱拒绝，已改用 `PYTHONPYCACHEPREFIX=/tmp/pycache` 规避。

## Status
**Currently Completed** - P0/P1/P2、“rich option + 轻追问”补强、历史会话证据补标工具、blindspot/not_actionable 本地修复均已完成，`python3 -m pytest tests/test_question_fast_strategy.py tests/test_security_regression.py tests/test_scripts_comprehensive.py -q` 共 102 个用例通过。

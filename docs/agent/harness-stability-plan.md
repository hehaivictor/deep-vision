# DeepVision 稳定性提升测试计划 v2

这份计划用于承接当前一轮“完整细致全面测试”的执行，目标是在现有 `harness / smoke / static_guardrails / browser smoke / evaluator / observe / heartbeat / ops / doc gardener` 能力之上，建立一套可重复、可量化、可阻断发布的稳定性测试方案。计划默认以本地隔离环境为主，云端联调只作为补充，不作为主 gate。

## 目标

- 从“功能能跑通”升级为“长链路稳定、失败可恢复、状态不污染、性能不过线、问题可定位”
- 不新增第三套测试框架，所有能力优先复用现有 harness 体系
- 形成 `stability-local-core` 与 `stability-local-release` 两档稳定性专项 lane，分别用于专项回归和发布前深回归
- 每个新发现的问题都必须沉淀为自动回归资产，而不是停留在一次性排查结论

## 默认假设

- 测试优先级：`稳定性优先`
- 执行环境：`本地隔离环境为主`
- 云端联调：`只做补充验证，不作为主 gate`
- 本轮不启动第三批系统性模块拆分；测试中发现新的脆弱热点后再单独立项

## 与当前 harness 基线对齐

当前计划默认建立在 phase6 之后的 harness 基线上，执行时优先复用以下能力：

- `python3 scripts/agent_heartbeat.py`：刷新当前阶段、稳定入口和 latest pointer
- `python3 scripts/agent_ops.py status`：统一查看 phase、覆盖率、latest run、漂移和 blocker
- `python3 scripts/agent_doc_gardener.py`：确认 mission / planner / calibration / 文档导航一致性
- `python3 scripts/agent_harness.py`：统一编排 `observe + static_guardrails + guardrails + smoke`
- `python3 scripts/agent_eval.py`：执行多执行器 evaluator 场景
- `tests/harness_calibration/*.json`：沉淀 evaluator 误判、放水和稳定性例外样本

稳定性测试不再视为独立于 heartbeat/ops 的旁路计划，而是作为下一条专项执行线接入现有主观察面。

## 五层测试模型

### L1 单元 / 回归层

覆盖：

- fallback 与异常分支
- 权限边界
- 幂等逻辑
- 状态机分支

落点：

- `tests/test_*.py`
- 现有 regression / comprehensive 测试文件

### L2 接口与状态一致性层

覆盖：

- 登录、License、owner / scope
- 报告、分享、方案页状态切换
- 账号合并、归属迁移后的资产一致性

落点：

- `tests/test_api_comprehensive.py`
- `tests/test_security_regression.py`
- `tests/test_solution_payload.py`
- 必要的新增 regression 文件

### L3 浏览器主链路层

覆盖：

- 真实用户操作路径
- 页面刷新后的恢复行为
- 关键门禁与前端状态切换

落点：

- `scripts/agent_browser_smoke.py`
- `scripts/agent_browser_smoke_runner.mjs`
- 对应 live / mock 浏览器场景

### L4 故障注入与降级层

覆盖：

- AI 超时或失败
- search / vision / object storage 失败
- 配置缺失或 provider 关闭
- 报告 draft / review lane 回退

落点：

- `tests/harness_scenarios/**/*.json`
- `scripts/agent_eval.py`
- 必要的回归测试

### L5 重复执行与长稳层

覆盖：

- flaky
- 慢场景
- 状态污染
- 重复提交 / 重复触发 / 重复访问的幂等性

落点：

- `scripts/agent_harness.py`
- `scripts/agent_observe.py`
- `scripts/agent_eval.py`
- 相关 harness artifact 摘要

## 稳定性专项 lane

### stability-local-core

定位：

- 用途：日常稳定性专项 / 合并前专项
- 默认由本地隔离环境驱动
- 不包含 `live-minimal` 和 10 轮重复执行

固定执行顺序：

1. `python3 scripts/agent_ops.py status`
2. `python3 scripts/agent_doc_gardener.py`
3. `python3 scripts/agent_harness.py --profile stability-local-core`
4. `python3 scripts/agent_eval.py --tag stability-local`
5. `python3 scripts/agent_observe.py --profile auto`
6. `python3 scripts/agent_history.py --kind harness --diff`

工件输出：

- `artifacts/harness-runs/stability-local/core`

### stability-local-release

定位：

- 用途：发布前深回归
- 在 `stability-local-core` 基础上追加真实后端和长稳验证

固定执行顺序：

1. 完整执行 `stability-local-core`
2. `python3 scripts/agent_harness.py --profile stability-local-release`
3. 连续执行 `stability-local-release` 共 10 轮
4. 再次执行 `python3 scripts/agent_ops.py status`
5. 再次执行 `python3 scripts/agent_observe.py --profile auto`

工件输出：

- `artifacts/harness-runs/stability-local/release`

### 工件要求

必须保留：

- `summary.json`
- `progress.md`
- `failure-summary.md`
- `handoff.json`
- `latest.json`
- 逐轮执行记录
- `ops` / `observe` / `history diff` 摘要

## 四个稳定性专项

### A. 失败注入与降级

必须覆盖：

- 问题生成超时
- 报告生成 draft lane 失败
- 报告 review lane 解析失败 / 修复失败
- 联网搜索不可用或返回异常
- 视觉能力关闭或失败
- 对象存储不可用
- 配置缺失或 provider 关闭

每个场景必须验证：

- 不出现未处理 500
- 前端有明确可理解反馈
- 后端有结构化失败摘要
- 用户可继续下一步，或明确知道必须重试 / 回退
- 如果属于 evaluator 判定偏差，也要补 `tests/harness_calibration/*.json` 样本，而不是只补测试场景

### B. 状态一致性

优先覆盖：

- 登录 -> License 绑定 -> 进入业务壳
- 点击会话 -> 恢复访谈 -> 下一题 -> 报告生成 -> 报告详情 -> 方案页
- 页面刷新后恢复当前状态
- owner / scope / 分享只读边界
- 账号合并 / 归属迁移后资产归属与可见性一致

### C. 幂等与状态污染

单独作为稳定性专项，不并入普通功能回归：

- `submitAnswer` 重复提交不重复写入
- 报告生成重复触发不生成脏报告 / 重复报告
- License 绑定重复提交结果一致
- preview / apply / rollback 的重复执行边界明确
- 分享链接重复访问不改变资产状态
- 上一轮测试残留不会污染下一轮测试

### D. 恢复能力

必须新增恢复类场景：

- 访谈中刷新页面后继续
- 下一题加载中刷新页面后恢复
- 报告生成中切页 / 重进后状态一致
- 后端短暂失败后重试成功
- 会话 / 报告列表重新进入后不丢状态

## 非功能质量门

本轮先建立硬阈值，不在本计划内处理性能优化实现。

### 首版阈值

- 启动 ready：`<= 15s`
- 点击会话进入访谈加载态：`<= 2s`
- 提交答案进入下一题加载态：`<= 2s`
- `live-minimal` 登录 + License 绑定完成：`<= 20s`
- 单轮 `stability-local` 总时长：`<= 20min`

### 判定规则

- 超阈值但未超 20%：记 `WARN`
- 超阈值 20% 以上：记 `FAIL`
- 连续 3 轮超阈值：视为发布阻断项

## 可诊断性要求

每个失败场景都必须同时满足：

- 前端能看到明确状态或错误提示
- harness / evaluator 工件能直接看到失败阶段和原因
- 后置 `agent_observe` 能反映出慢场景、重复 blocker 或关键异常

不允许只有“失败了”而没有定位线索。

## 测试矩阵优先级

### 第一梯队：必须优先覆盖

- 访谈推进链路
- 报告生成与回退链路
- 登录 / License / 账号状态切换
- owner / scope / 分享只读边界
- 对应优先 task：`report-solution`、`presentation-export`、`license-audit`、`license-admin`

### 第二梯队：专项补充

- 管理员配置中心
- ownership migration / rollback
- cloud import 预览与治理边界
- 演示稿 / sidecar / 对象存储元数据一致性
- 对应优先 task：`ownership-migration`、`config-center`、`cloud-import`

### 第三梯队：轻量维持

- 帮助页
- 纯静态展示页
- 低风险说明性配置展示

## 实施方式

### 内部入口扩展

- 新增或扩展 harness profile：`stability-local-core`、`stability-local-release`
- 新增 evaluator tag：`stability-local`，由场景 tag 与内置 alias 共同承接
- 新增重复执行入口：固定连续运行 10 轮并输出 flaky 汇总
- 新增或扩展现有观测摘要字段，优先挂到 `agent_observe.py` 或 `agent_ops.py` 的 payload 中：
  - `key_latencies`
  - `flaky_summary`
  - `repeat_failures`
  - `state_pollution_signals`

### 新增测试资产落点

- L1 / L2：优先补到现有 unittest / regression 文件
- L3：补到现有 `browser smoke` 套件
- L4 / L5：补到 `tests/harness_scenarios` 和 `agent_eval`
- evaluator 判定误差优先补到 `tests/harness_calibration`
- 不允许新增平行测试脚本绕开现有 harness

## 验收标准

### 功能与稳定性

- `agent_doc_gardener.py` 结果保持 `HEALTHY`
- `agent_ops.py status` 在执行前后都能输出一致的总体健康态
- `guardrails extended` 全通过
- `smoke extended` 全通过
- `browser smoke extended` 全通过
- `browser smoke live-minimal` 全通过（仅 release）
- `evaluator tag=stability-local` 无 FAIL

### 长稳

- `stability-local` 连续执行 10 轮
- `FAIL = 0`
- `FLAKY 场景 <= 2 个`
- 任一单场景 flaky 率不得超过 `10%`
- 不得出现跨轮状态污染导致的错误

### 交付要求

- 每个新发现的真实缺陷，至少沉淀为一个自动回归用例
- 每个 evaluator 误判或放水问题，至少沉淀为一个 calibration 样本
- 输出稳定性测试摘要，至少包含：
  - 新增场景
  - 发现缺陷
  - flaky 统计
  - 时延基线
  - 待后续优化项
- 将 `stability-local-core` 定位为“日常专项 / 合并前专项”
- 将 `stability-local-release` 定位为“发布前专项”，不压入默认 PR 轻量 lane

## 建议执行顺序

1. 先跑 `heartbeat / ops / doc_gardener / harness / browser / evaluator` 形成基线缺口清单
2. 补失败注入与降级
3. 补状态一致性与恢复能力
4. 补幂等与状态污染
5. 接入 `stability-local-core`
6. 接入 `stability-local-release` 与 10 轮重复执行
7. 收口观测摘要、校准样本和验收口径

## 进度记录要求

执行本计划时，必须同步维护：

- [harness-stability-progress.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-stability-progress.md)

每完成一项，至少记录：

- 日期
- 编号
- 状态
- 本次改动范围
- 执行过的验证命令
- 关键工件或文档路径
- 剩余风险与下一步

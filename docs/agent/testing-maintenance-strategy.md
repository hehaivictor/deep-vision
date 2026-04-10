# DeepVision 测试体系长期维护策略

这份文档回答的不是“要不要做测试”，而是：

1. DeepVision 现在应该长期维持什么测试结构。
2. 哪些测试是 PR 必跑，哪些是发布前必跑。
3. 新功能和新问题最少要补到什么程度。

结论先说：

`DeepVision 需要同时保留单元/回归测试、集成测试、功能测试和稳定性专项。`

但它们不是平铺使用，而是按层次承担不同职责。

## 一、测试分层原则

### 1. 单元 / 回归测试

用途：

- 锁死纯逻辑边界
- 锁死 fallback、权限、幂等和状态机分支
- 用最低成本拦截回归

当前主要落点：

- [tests/test_api_comprehensive.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_api_comprehensive.py)
- [tests/test_security_regression.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py)
- [tests/test_solution_payload.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_solution_payload.py)
- [tests/test_scripts_comprehensive.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_scripts_comprehensive.py)

适合覆盖的问题：

- 报告生成 fallback
- 搜索/视觉/对象存储降级
- 登录 / License / 分享边界
- 重复提交 / 重复触发 / 单次 token 失效

### 2. 集成测试

用途：

- 锁多模块拼接后的状态一致性
- 锁数据库、对象存储、配置中心、鉴权、恢复链路
- 发现“单个函数都对，但串起来会坏”的问题

DeepVision 当前最重要的集成链路：

- 登录 -> License -> 业务壳
- 访谈 -> 下一题 -> 报告生成 -> 报告详情 -> 方案页
- owner / scope / 分享只读边界
- config-center / ownership-migration / report-generation / object-storage 跨模块链路

当前主要落点：

- `tests/test_api_comprehensive.py`
- `tests/test_security_regression.py`
- `agent_harness` 的 smoke / guardrails / workflow
- `agent_eval` 的 scenario

### 3. 功能测试 / 浏览器测试

用途：

- 站在真实用户视角确认“真的能用”
- 锁住前端恢复、刷新、切页、门禁、只读态

当前主要入口：

- [scripts/agent_browser_smoke.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_browser_smoke.py)
- [scripts/agent_browser_smoke_runner.mjs](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_browser_smoke_runner.mjs)
- `minimal / extended / live-minimal / live-extended`

### 4. 稳定性专项

用途：

- 锁失败注入
- 锁恢复能力
- 锁幂等与状态污染
- 锁 release 深回归和长稳表现

当前主要入口：

- [docs/agent/harness-stability-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-stability-plan.md)
- [docs/agent/harness-stability-progress.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-stability-progress.md)
- [docs/agent/harness-stability-summary.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-stability-summary.md)

## 二、长期执行策略

### A. PR 必跑

目标：

- 快速挡住明显回归
- 不把所有重型测试压进 PR

建议维持：

- `python3 scripts/agent_static_guardrails.py`
- `python3 scripts/agent_guardrails.py --quiet`
- `python3 scripts/agent_smoke.py`
- 必要时加：
  - `python3 scripts/agent_browser_smoke.py --suite extended`
  - 相关的 focused `unittest`

原则：

- PR lane 追求“足够快、足够准”
- 不默认跑 `live-minimal`
- 不默认跑 10 轮 release 重复执行

### B. 合并前专项

目标：

- 对高风险改动做一轮比 PR 更重的专项确认

建议入口：

```bash
python3 scripts/agent_harness.py --profile stability-local-core --artifact-dir artifacts/harness-runs/stability-local/core
python3 scripts/agent_eval.py --tag stability-local --artifact-dir artifacts/harness-eval/stability-local/core
python3 scripts/agent_ops.py status
python3 scripts/agent_observe.py --profile auto
```

适用场景：

- 改登录 / License / owner / scope
- 改访谈推进
- 改报告生成与回退
- 改管理员配置中心或 ownership migration

### C. 发布前必跑

目标：

- 作为真正的深回归入口

建议入口：

```bash
python3 scripts/agent_harness.py --profile stability-local-release --artifact-dir artifacts/harness-runs/stability-local/release
python3 scripts/agent_ops.py status
python3 scripts/agent_observe.py --profile auto
python3 scripts/agent_history.py --kind harness-stability-release --limit 5
```

当前策略：

- `stability-local-release` 必须作为发布前专项执行
- 但当前`不硬接默认发布阻断`
- 是否发布，由 release 工件 + ops/observe 摘要共同判断

## 三、新功能至少要补什么

### 1. 新功能涉及纯后端逻辑

至少补：

- 1 条 focused 单元 / 回归测试
- 如涉及权限、fallback、幂等，再补对应 regression case

### 2. 新功能涉及前后端状态切换

至少补：

- 1 条 API / regression 测试
- 1 条 browser smoke 或 evaluator 场景

典型例子：

- 登录态变化
- License gate 切换
- 新增报告详情交互
- 访谈页刷新恢复

### 3. 新功能涉及高风险链路

高风险定义：

- 登录 / License
- owner / scope / 分享只读
- 访谈推进
- 报告生成 / 回退
- ownership migration
- config-center

至少补：

- 1 条 focused regression
- 1 条 browser / evaluator 场景
- 必要时更新 `stability-local` 相关资产

## 四、新 bug 至少要补什么

规则非常明确：

`每个真实 bug，至少沉淀成一种自动资产。`

优先级如下：

### 1. 真实功能或状态错误

优先沉淀为：

- 单元 / regression 测试
- 必要时再补 browser smoke 或 evaluator

### 2. 真实浏览器交互问题

优先沉淀为：

- browser smoke 场景
- 如果根因在状态机或恢复逻辑，再补 regression

### 3. evaluator 判定偏差、误报、放水

优先沉淀为：

- `tests/harness_calibration/*.json`

不要只改文案或阈值而不留校准样本。

## 五、风险驱动优先级

DeepVision 后续测试投入应一直按下面顺序倾斜：

### 第一梯队

- 访谈推进链路
- 报告生成与回退链路
- 登录 / License / 账号状态切换
- owner / scope / 分享只读边界

### 第二梯队

- 管理员配置中心
- ownership migration / rollback
- cloud import 预览与治理边界
- 演示稿 / sidecar / 对象存储元数据一致性

### 第三梯队

- 帮助页
- 纯静态展示页
- 低风险说明性配置展示

原则：

- 不要为了覆盖率平均撒网
- 测试资源优先向第一梯队倾斜

## 六、不建议的做法

- 不再新建第三套测试框架
- 不为了覆盖率堆低价值 UI case
- 不把所有问题都推给 browser 测试
- 不只做一次性手工排查而不沉淀自动资产

## 七、建议维护节奏

### 日常

- PR 跑轻量 gate
- 高风险改动加一轮 `stability-local-core`

### 发布前

- 跑 `stability-local-release`
- 查看 `agent_ops.py status`
- 查看 `agent_observe.py --profile auto`

### 周期性

- 定期回看：
  - `docs/agent/harness-stability-summary.md`
  - `docs/agent/harness-stability-progress.md`
- 判断是否需要收紧 release 门槛

## 八、一句话原则

DeepVision 当前最适合的长期策略是：

`单元锁边界，集成锁状态，功能锁真实可用，稳定性专项锁发布前质量。`

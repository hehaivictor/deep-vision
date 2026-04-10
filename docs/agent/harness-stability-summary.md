# DeepVision 稳定性测试结果总表

这份文档用于收口本轮 `harness-stability-plan.md` 的实际结果，回答三件事：

1. 本轮稳定性测试到底覆盖到了什么。
2. 真实发现并修掉了哪些稳定性问题。
3. `stability-local-release` 的门槛现在应该如何使用，是否直接接入发布阻断。

## 一、执行范围

本轮已完整执行并收口以下 6 个阶段：

- `S0` 基线盘点
- `S1` 失败注入与降级
- `S2` 状态一致性与恢复
- `S3` 幂等与状态污染
- `S5` `stability-local-release` 深回归与 10 轮重复执行
- `S6` 非功能质量门与可诊断性

说明：

- `S4 stability-local-core` 已作为 lane 能力完成并吸收进日常专项，不再单独拆成结果章节。
- 本轮没有再启动新的第三套测试框架，全部复用现有 `harness / static_guardrails / smoke / browser smoke / evaluator / observe / ops / heartbeat / history`。

## 二、稳定性专项 lane 现状

### 1. stability-local-core

用途：

- 日常专项回归
- 合并前专项检查
- 定位失败注入、恢复、幂等和状态边界

当前状态：

- 已正式接入 `agent_harness --profile stability-local-core`
- 已接入 `agent_eval --tag stability-local`
- 已被 `ops / observe / history` 正式识别

### 2. stability-local-release

用途：

- 发布前深回归
- 包含真实后端 `live-minimal`
- 包含连续 10 轮重复执行

当前状态：

- 已正式接入 `agent_harness --profile stability-local-release`
- `release-baseline` 单轮通过
- `release-repeat` 10 轮全部完成，结果为 `10/10 READY_WITH_WARNINGS`
- 当前未出现 `FAIL / BLOCKED / flaky`

关键证据：

- [release-baseline latest progress](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-runs/stability-local/release-baseline/latest-progress.md)
- [release-repeat latest progress](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-runs/stability-local/release-repeat/latest-progress.md)

## 三、本轮已补齐的稳定性能力

### 1. 失败注入与降级

已覆盖：

- 微信登录配置缺失
- 视觉关闭
- 视觉超时
- 对象存储归档失败
- Refly 下载失败
- search / report 的既有降级链路

当前要求已满足：

- 无未处理 500
- 前端有明确反馈
- 后端有工件与摘要
- 用户可以继续流程，或明确知道需要重试

### 2. 状态一致性与恢复

已覆盖：

- 登录后进入 License gate，再进入业务壳
- License 绑定成功后刷新，仍停留在业务壳
- 公开分享页刷新后仍保持只读
- 报告详情刷新后恢复到同一份报告
- 访谈进行中刷新后恢复到同一会话和当前问题
- 报告生成中刷新后，仍保持在同一会话并继续显示生成进度

### 3. 幂等与状态污染

已覆盖：

- `submit-answer` 即时重复提交不重复写日志
- `generate-report` 重复触发复用当前任务
- License 重复激活保持绑定稳定
- 分享链接重复创建不生成脏 sidecar
- ownership preview 重新生成会使旧 token 失效
- ownership apply 只能单次执行

### 4. 可诊断性

当前已完成：

- harness `summary / latest / progress` 全部带 `duration_ms`
- `agent_history` 可递归发现嵌套 release 工件
- `agent_heartbeat` 可识别 `harness-stability-core / harness-stability-release`
- `agent_ops` 可显示 release 时长门槛与 `duration_ms`
- `agent_observe` 的 `history_trends / diagnostic_panel` 可显示 `release_gate=...`

## 四、本轮发现并修复的典型问题

### 1. 配置中心 runtime getter 调用不兼容

现象：

- `agent_harness --smoke-suite extended` 被配置中心/ops 权限回归阻塞

修复：

- 收口 [web/server_modules/admin_config_center.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules/admin_config_center.py) 的运行时 getter 调用和动态取值路径

### 2. 对象存储归档失败会导致会话文档上传直接 500

现象：

- 主流程上传成功，但 sidecar/归档失败时整条链路中断

修复：

- 调整为“主上传成功 + 返回归档告警”，不再把辅助归档失败升级为主流程失败

### 3. 访谈与报告详情刷新恢复存在真实前端状态缺口

现象：

- 刷新后丢失 interview / report detail 的恢复目标

修复：

- 收口 app shell 恢复顺序
- 先解析 URL，再消费 snapshot
- 报告详情同步进 URL，恢复目标不再只依赖内存态

### 4. 报告生成中刷新恢复存在真实缺陷

现象：

- 刷新后可能退回列表，或丢失“正在生成”状态

修复：

- 增加报告生成中的恢复状态持久化与 browser smoke 场景

## 五、当前门槛与实际结果

### 1. 既定门槛

- 启动 ready：`<= 15s`
- 点击会话进入访谈加载态：`<= 2s`
- 提交答案进入下一题加载态：`<= 2s`
- `live-minimal` 登录 + License 绑定完成：`<= 20s`
- 单轮 `stability-local-release`：`<= 20min`

### 2. 当前真正落地的可观测门

当前已机器化并进入 `ops / observe / history` 的，是：

- `stability-local-release WARN = 20min`
- `stability-local-release FAIL = 24min`

当前基线实测：

- `release-s6-check duration_ms = 44506.25`
- 折合约 `44.51s`
- 远低于 `20min WARN`

因此当前 release 时长门状态是：

- `PASS`

关键证据：

- [release-s6-check latest progress](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/artifacts/harness-runs/stability-local/release-s6-check/latest-progress.md)
- `python3 scripts/agent_ops.py status`
- `python3 scripts/agent_observe.py --profile auto`
- `python3 scripts/agent_history.py --kind harness-stability-release --limit 3`

## 六、关于“是否直接接入发布阻断”的决策

结论：

`当前先不把 release 阈值硬接进默认发布阻断规则。`

原因：

- 本轮已经把门槛接入 `heartbeat / ops / history / observe`，可见性已足够。
- 目前只完成了一轮基线和一轮 10 次重复执行，数据仍偏短。
- 当前 warning 仍混有本地 mock 短信和历史 browser smoke 噪音，不适合马上作为强阻断条件。

当前建议：

- `PR` 继续保持轻量 gate，不接入 `stability-local-release`
- `发布前人工/专项执行` 时，必须跑 `stability-local-release`
- 只有在以下条件同时满足后，再考虑硬接发布阻断：
  - 连续两周 release 工件稳定采集
  - release 时长门未出现假阳性
  - `ops / observe` 中 release gate 的信号足够稳定

也就是说，当前策略是：

- `可见`
- `可追踪`
- `可用于发布前决策`
- `但暂不自动阻断默认发布流程`

## 七、后续维护建议

下一轮不再默认继续扩测试矩阵，而是按事故和热点驱动补强：

- 如果出现新的外部依赖失败链路，补到 `S1` 资产
- 如果出现新的刷新/切页/重进恢复问题，补到 `S2` 资产
- 如果出现重复提交/重复触发/残留污染，补到 `S3` 资产
- 如果 release 时长开始逼近阈值，再单独立项处理 `S6`

当前最推荐的维持动作只有 3 个：

1. 发布前跑一次 `stability-local-release`
2. 观察 `agent_ops.py status` 和 `agent_observe.py --profile auto` 中的 release gate
3. 新真实问题优先沉淀为自动回归，而不是临时手工复查

## 八、建议命令

日常专项：

```bash
python3 scripts/agent_harness.py --profile stability-local-core --artifact-dir artifacts/harness-runs/stability-local/core
python3 scripts/agent_eval.py --tag stability-local --artifact-dir artifacts/harness-eval/stability-local/core
python3 scripts/agent_observe.py --profile auto
```

发布前深回归：

```bash
python3 scripts/agent_harness.py --profile stability-local-release --artifact-dir artifacts/harness-runs/stability-local/release
python3 scripts/agent_ops.py status
python3 scripts/agent_observe.py --profile auto
python3 scripts/agent_history.py --kind harness-stability-release --limit 5
```

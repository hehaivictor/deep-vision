# DeepVision 稳定性提升测试进度台账

这份台账用于记录 `harness-stability-plan.md` 的实际执行进度、证据和剩余风险。后续每完成一项，或出现阻塞，都在这里追加记录。

## 当前执行面

- 当前阶段：`planned`
- 当前优先项：`S0 基线盘点`
- 对应计划：[harness-stability-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-stability-plan.md)

## 执行分解

| 编号 | 状态 | 主题 | 目标 | 主要交付物 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| S0 | planned | 基线盘点 | 先跑一轮现有 harness / smoke / browser / evaluator / observe，形成缺口清单与初始时延基线 | 基线摘要、首轮 artifact、缺口清单 | 能明确知道当前覆盖空白、慢点和高波动场景 |
| S1 | planned | 失败注入与降级 | 补齐 AI、search、vision、object storage、配置缺失相关的失败注入与回退验证 | 新增回归测试、evaluator 场景、必要的 harness 工件摘要 | 所有目标场景都验证无未处理 500，且有明确回退或提示 |
| S2 | planned | 状态一致性与恢复 | 补齐登录、License、会话、报告、方案页在刷新/重进/切换场景下的一致性与恢复能力 | 新增 browser smoke / evaluator / regression 场景 | 刷新、重进、短暂失败后的状态恢复可自动验证 |
| S3 | planned | 幂等与状态污染 | 补齐重复提交、重复触发、重复访问、多轮执行残留污染等专项 | 新增 regression / scenario / flaky 统计项 | 连续执行时不出现重复资产、状态串扰或脏残留 |
| S4 | planned | stability-local lane | 建立稳定性专项套餐与 10 轮重复执行入口 | harness/profile、artifact 目录、重复执行汇总 | 能稳定输出 flaky、慢场景、重复 blocker 摘要 |
| S5 | planned | 非功能质量门与可诊断性 | 建立阈值门、输出关键时延与故障定位摘要 | 观测摘要字段、稳定性测试总结 | 超阈值场景可见、可追踪、可阻断发布 |

## 进度记录

| 日期 | 编号 | 状态 | 事项 | 证据 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| 2026-04-10 | PLAN-STABILITY | done | 新增稳定性测试计划与独立进度台账，明确五层测试模型、`stability-local` lane、四个稳定性专项、质量门与验收标准 | [harness-stability-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-stability-plan.md)、[harness-stability-progress.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-stability-progress.md) | 启动 S0，先跑现有入口形成基线缺口清单 |

## 记录模板

复制以下模板追加到表格末尾：

```text
| YYYY-MM-DD | Sx | planned/active/done/blocked | 简述本次推进内容 | 关键文件、artifact 或命令 | 明确下一步 |
```

## 记录要求

- 如果修改了 `agent_harness.py`、`agent_eval.py`、`agent_observe.py`、`agent_browser_smoke.py` 或相关测试文件，必须在“证据”里写清验证命令。
- 如果新增了场景文件，优先补路径和对应 tag / suite。
- 如果出现阻塞，必须写明阻塞点，不要只写“待继续”。
- 如果某个场景失败但暂不修复，也要在记录中说明是否已沉淀为自动回归用例。

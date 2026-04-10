# Planner Artifacts

这里用于沉淀 `Mission Contract + Planner artifact` 的长期计划工件。

默认情况下，`python3 scripts/agent_planner.py` 会把输出写到 `artifacts/planner/`，适合一次性规划、试运行和本地迭代；当某条计划需要进入仓库长期维护时，再把 markdown 输出显式指向本目录。

每次成功写入后，还会同步更新按 task 维度的 latest 指针：

- `artifacts/planner/missions/by-task/<task>/latest.json`
- `artifacts/planner/by-task/<task>/latest.json`

后续 `workflow / harness / evaluator / handoff` 都会优先引用这份指针，而不是要求人工自己找最近一次 plan 文件。

## 适用场景

- 用户只给了 1 到 4 句需求，需要先扩成结构化 mission，再进入 plan 和 task workflow
- 改动涉及高风险 task，希望先把“目标、范围、完成定义、风险”收口成正式工件
- 需要把后续 Sprint Contract、Evaluator 校准或 handoff 绑定到同一份计划

## 推荐用法

先做一次本地 mission + plan 预览：

```bash
python3 scripts/agent_planner.py \
  --task report-solution \
  --goal "修复方案页分享异常并保留旧报告兼容" \
  --context-line "用户反馈公开分享页偶发空白" \
  --context-line "需要先确认是 payload 回退还是分享边界问题" \
  --dry-run
```

需要把 mission / plan 一起落为长期文档时：

```bash
python3 scripts/agent_planner.py \
  --task report-solution \
  --goal "修复方案页分享异常并保留旧报告兼容" \
  --context-line "用户反馈公开分享页偶发空白" \
  --output-markdown docs/agent/plans/report-solution-share-fix.md
```

## 当前约定

- Mission Contract 先收口一句话需求的目标、非目标、验收标准、风险和证据要求，不在此阶段承诺底层实现细节
- Planner artifact 再基于 mission 收口执行范围、推荐命令和证据入口
- Mission Contract 和 Planner artifact 现在都会进入 `progress.md`、`failure-summary.md` 和 `handoff.json`，便于下一位直接回看任务使命、计划和完成定义
- 如果计划已经进入正式执行，请同步更新对应阶段台账，例如 [harness-progress-phase4.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/harness-progress-phase4.md)
- 后续若引入 Sprint Contract，应优先把 contract 文件与对应 Mission / Planner artifact 互相链接

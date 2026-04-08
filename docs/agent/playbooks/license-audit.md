# License 审计

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`license-audit` | 来源：`resources/harness/tasks/license-audit.json`

把 License 校验开关、活跃批次和账号绑定检查收口到固定只读流程，先看 observe 与运行态，再决定是否进入高风险写操作。

## 什么时候用

- 用户反馈无法进入业务链路，怀疑是 License 缺失、过期或运行时开关异常
- 需要核对当前 License 校验开关、批次分布、绑定账号和即将到期情况
- 需要在不改数据的前提下先完成审计

## 先跑哪些命令

```bash
python3 scripts/agent_observe.py --profile auto
python3 scripts/license_manager.py enforcement-status --json
python3 scripts/license_manager.py list --status active --json
python3 scripts/agent_harness.py --task license-audit --profile auto --artifact-dir artifacts/harness-runs
python3 scripts/agent_eval.py --scenario access-boundaries --artifact-dir artifacts/harness-eval
```

如需看某个账号的绑定情况，再补：

```bash
python3 scripts/license_manager.py list --bound-account 13700000000 --json
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 doctor.json`
- `对应 run 目录下的 workflow.json`
- `对应 run 目录下的 guardrails.json`
- `artifacts/harness-eval/latest.json`
- `对应 evaluator run 目录下的 access-boundaries.json`

重点看：

- LICENSE_ENFORCEMENT_ENABLED 当前运行态和默认值是否一致
- 活跃 License 批次、绑定账号和时间窗状态是否异常
- access-boundaries 是否仍保持匿名写拦截和分享只读边界
- doctor / observe 是否提示 mock 短信、实例隔离或配置来源风险

## 哪些操作必须人工确认

- enforcement-set --enabled true/false
- enforcement-set --sync-default
- revoke、extend、批量生成或批量撤销 License
- 将演示环境的 mock 行为带入生产风格配置

## 相关文档

- `docs/agent/admin-ops.md`

# 账号绑定与合并核对

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`account-merge` | 来源：`resources/harness/tasks/account-merge.json`

先确认当前登录态和候选上下文，再验证 merge preview/apply/rollback 与 takeover 边界，不直接跳到高风险合并。

## 什么时候用

- 手机号或微信绑定时提示存在历史账号，需要判断是否进入 merge preview / apply
- 用户反馈绑定后历史数据缺失、takeover 结果异常或 rollback 入口失效
- 需要确认 merge preview token、确认短语和管理员 rollback 链路是否仍完整

## 先跑哪些命令

```bash
python3 scripts/agent_observe.py --profile auto
python3 scripts/agent_harness.py --task account-merge --profile auto --artifact-dir artifacts/harness-runs
python3 -m unittest tests.test_api_comprehensive.ComprehensiveApiTests.test_account_merge_preview_requires_login_and_candidate_context tests.test_api_comprehensive.ComprehensiveApiTests.test_account_merge_apply_requires_login_and_active_preview tests.test_api_comprehensive.ComprehensiveApiTests.test_bind_phone_conflict_requires_preview_apply_and_admin_rollback tests.test_api_comprehensive.ComprehensiveApiTests.test_bind_wechat_conflict_redirects_to_merge_preview_and_apply
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 workflow.json`
- `对应 run 目录下的 guardrails.json`

重点看：

- merge preview 是否仍要求候选上下文和 preview token
- 手机号与微信冲突时是否仍区分 takeover 与 merge_required
- 管理员 rollback 与普通用户 apply 的边界是否仍在
- 绑定链路改动后，登录态与业务壳切换是否受影响

## 哪些操作必须人工确认

- 对真实候选账号执行 merge apply
- 回滚已完成的账号合并
- 手工修改 preview token、确认短语或历史账号归属

## 相关文档

- `docs/agent/auth-identity.md`
- `docs/agent/admin-ops.md`

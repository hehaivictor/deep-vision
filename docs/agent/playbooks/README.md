# Agent Playbooks

这些 playbook 只做一件事：把高频但有风险的操作流程固定下来，避免每次都靠临时判断。

## Task-Backed Playbook

以下文档由 `python3 scripts/agent_playbook_sync.py` 基于 `resources/harness/tasks/*.json` 自动生成。修改 task 画像后，优先重新同步，不要手工改生成段落。

- 报告与方案页问题排查：[report-debug.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/report-debug.md)
- 导出与演示稿链路核对：[presentation-export.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/presentation-export.md)
- 账号绑定与合并核对：[account-merge-verify.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/account-merge-verify.md)
- 归属迁移预演与执行前确认：[migration-preview.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/migration-preview.md)
- License 审计与开关核对：[license-audit.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/license-audit.md)
- License 管理与批量操作核对：[license-admin.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/license-admin.md)
- 配置中心变更前核对：[config-center-verify.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/config-center-verify.md)
- 云端导入预演与回滚准备：[cloud-import-verify.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/playbooks/cloud-import-verify.md)

## 使用原则

- 先跑只读命令，再决定是否进入高风险步骤。
- 优先读 `artifacts/harness-runs/latest.json` 和 `artifacts/harness-eval/latest.json`，不要只看终端最后几行。
- Playbook 负责固定顺序，不替代领域文档；复杂改动仍需回到对应模块文档和测试。
- task 画像改动后，优先执行 `python3 scripts/agent_playbook_sync.py --check`，确认文档没有漂移。
- 需要浏览器级证据时，优先跑 `python3 scripts/agent_browser_smoke.py --suite extended`，或改用 `.github/workflows/browser-smoke.yml` 产出 CI 工件；当前 `extended` 已覆盖公开分享只读、登录前端视图、License 门禁前端视图、License 绑定成功切换、报告详情链路和管理员配置中心页签切换。

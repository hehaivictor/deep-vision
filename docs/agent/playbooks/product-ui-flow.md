# 产品前端交互准入

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`product-ui-flow` | 来源：`resources/harness/tasks/product-ui-flow.json`

把发布前轻量前端体验检查固定到 extended browser smoke、harness 证据和手工检查项三段，避免只看接口 happy path。

## 什么时候用

- 发布前需要判断前端关键路径是否具备交付信心
- 登录、License、账号绑定、访谈、报告详情、方案页、公开分享或配置中心出现交互异常
- 需要确认刷新恢复、加载态、错误态、只读态和按钮可点击性

## 先跑哪些命令

```bash
python3 scripts/agent_browser_smoke.py --suite extended --artifact-dir artifacts/browser-smoke/product-ui-flow
python3 scripts/agent_eval.py --scenario browser-smoke-extended --artifact-dir artifacts/harness-eval
python3 scripts/agent_harness.py --profile auto --browser-smoke --artifact-dir artifacts/harness-runs
```

如自动化无法覆盖具体交互细项，记录为手工轻量检查项，不临时新建测试框架：

```bash
python3 scripts/agent_ci_summary.py --latest-json artifacts/browser-smoke/product-ui-flow/latest.json --title "Product UI Flow"
```

## 看哪些 artifact

- `artifacts/browser-smoke/product-ui-flow/latest.json`
- `artifacts/harness-eval/latest.json`
- `artifacts/harness-runs/latest.json`
- `artifacts/ci/browser-smoke/latest.json`

重点看：

- 桌面与移动视口下是否有明显遮挡、错位或按钮不可点
- 登录、License gate、账号绑定、访谈、报告详情、方案页、公开分享、配置中心是否都有明确加载态或错误态
- 刷新恢复后 URL、上下文、主操作按钮和提示文案是否一致
- 弹窗、表单、页签、只读态是否出现卡死、重复提交或越权写入

## 哪些操作必须人工确认

- 新增第三方前端测试框架或替换现有 browser smoke 执行路径
- 修改登录、License gate、公开分享只读或配置中心权限交互
- 将自动化未覆盖的前端体验项标记为已自动通过

## 相关文档

- `docs/agent/auth-identity.md`
- `docs/agent/interview.md`
- `docs/agent/report-solution.md`
- `docs/agent/admin-ops.md`

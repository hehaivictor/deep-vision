# 导出与演示稿链路核对

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`presentation-export` | 来源：`resources/harness/tasks/presentation-export.json`

先确认报告导出、附录 PDF、演示稿能力与权限门禁，再决定是否修改导出资产或 presentation feature。

## 什么时候用

- 报告导出、附录 PDF 或演示稿生成链路异常
- 需要确认标准版/专业版在导出和 presentation 能力上的边界
- 需要区分问题来自报告详情、导出资产权限，还是 presentation feature 开关

## 先跑哪些命令

```bash
python3 scripts/agent_observe.py --profile auto
python3 scripts/agent_harness.py --task presentation-export --observe --profile auto --artifact-dir artifacts/harness-runs
python3 scripts/agent_eval.py --scenario report-solution-core --artifact-dir artifacts/harness-eval
python3 -m unittest tests.test_api_comprehensive.ComprehensiveApiTests.test_standard_user_can_generate_balanced_but_cannot_access_solution_appendix_or_presentation tests.test_api_comprehensive.ComprehensiveApiTests.test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints tests.test_security_regression.SecurityRegressionTests.test_presentation_map_remains_valid_under_parallel_updates
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 observe.json`
- `对应 run 目录下的 workflow.json`
- `artifacts/harness-eval/latest.json`

重点看：

- 标准版与专业版在 appendix / presentation / export asset 上的能力边界
- presentation map 并发更新后是否仍保持记录有效
- 导出与演示稿链路在当前 License gate 下是否仍保持预期门禁

## 哪些操作必须人工确认

- 修改导出文件格式、appendix 下载策略或 presentation feature 开关
- 删除、覆盖或迁移历史演示稿记录
- 更改专业版能力边界或导出权限矩阵

## 相关文档

- `docs/agent/report-solution.md`
- `docs/agent/admin-ops.md`

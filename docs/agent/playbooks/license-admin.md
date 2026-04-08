# License 管理与批量操作核对

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`license-admin` | 来源：`resources/harness/tasks/license-admin.json`

先确认 enforcement 状态、活跃批次与管理员权限，再决定是否进入批量生成、延期、撤销或运行时开关写入。

## 什么时候用

- 需要批量生成、延期、撤销 License，或调整运行时 enforcement 开关
- 需要确认当前环境是否还能 bootstrap 首批种子 License
- 用户反馈 License 管理后台异常，需要区分是查询层、批量动作还是运行时开关问题

## 先跑哪些命令

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 scripts/license_manager.py --json enforcement-status
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 scripts/license_manager.py --json list --status active
python3 scripts/agent_harness.py --task license-admin --profile auto --artifact-dir artifacts/harness-runs
python3 -m unittest tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_license_routes_require_valid_license_even_when_gate_disabled tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_license_management_endpoints_cover_summary_detail_search_and_bulk_actions tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_generate_license_batch_can_assign_professional_level tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_can_bootstrap_first_seed_license_without_existing_license
```

确认需要正式执行时，再显式使用：

```bash
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 scripts/license_manager.py --json generate --count 5 --duration-days 30
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 scripts/license_manager.py --json revoke 12 --reason "manual revoke"
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 scripts/license_manager.py --json extend 12 --duration-days 30
uv run --with flask --with flask-cors --with anthropic --with requests --with reportlab --with pillow --with jdcloud-sdk --with 'psycopg[binary]' --with boto3 python3 scripts/license_manager.py enforcement-set --enabled true --sync-default
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 workflow.json`
- `对应 run 目录下的 guardrails.json`

重点看：

- enforcement 状态、活跃批次和批量动作接口是否仍一致
- 管理员 License 路由是否仍要求有效 License，不会被普通管理员直接绕过
- 无现有 License 时的 bootstrap 首批种子 License 是否仍可用
- 批量生成、延期、撤销后，权限边界和时间窗规则是否保持不变

## 哪些操作必须人工确认

- 批量生成、延期、撤销或替换真实 License
- 修改 enforcement 默认值或运行时开关
- 对生产风格账号执行高风险 License 写操作

## 相关文档

- `docs/agent/admin-ops.md`

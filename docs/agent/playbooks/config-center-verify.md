# 配置中心核对

> 本文件由 `python3 scripts/agent_playbook_sync.py` 基于 task 画像自动生成。
> 关联任务画像：`config-center` | 来源：`resources/harness/tasks/config-center.json`

先确认运行态、配置来源和 License 门禁，再进入配置中心专项回归和人工写入。

## 什么时候用

- 准备修改 .env、config.py 或配置中心托管区块前
- 需要判断某个配置应该改环境变量、后端配置，还是前端展示配置
- 用户反馈配置改了但没生效，需要确认运行态、文件值和重启边界

## 先跑哪些命令

```bash
python3 scripts/agent_observe.py --profile auto
python3 scripts/agent_harness.py --task config-center --observe --profile auto --artifact-dir artifacts/harness-runs
python3 scripts/agent_eval.py --scenario runtime-readiness --artifact-dir artifacts/harness-eval
```

如只做静态配置核对，再补：

```bash
python3 scripts/agent_doctor.py --profile auto
```

## 看哪些 artifact

- `artifacts/harness-runs/latest.json`
- `对应 run 目录下的 doctor.json`
- `对应 run 目录下的 observe.json`
- `对应 run 目录下的 workflow.json`
- `artifacts/harness-eval/latest.json`
- `对应 evaluator run 目录下的 runtime-readiness.json`

重点看：

- config_sources 中 env、config.py、site-config.js 的来源与修改时间
- doctor 是否提示 SECRET_KEY、INSTANCE_SCOPE_KEY、SMS_PROVIDER 风险
- runtime-readiness 是否仍通过 startup snapshot 和 observe 读取链路

## 哪些操作必须人工确认

- 通过配置中心写回 .env 或 config.py
- 修改 INSTANCE_SCOPE_KEY、SECRET_KEY、管理员白名单、短信与微信接入
- 依赖重启才能完全生效的配置变更

## 相关文档

- `docs/agent/admin-ops.md`
- `web/CONFIG.md`

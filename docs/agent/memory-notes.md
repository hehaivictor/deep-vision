# DeepVision Memory Notes

> 生成时间：2026-08-14T12:00:00Z

## 当前焦点

- 当前阶段：`product-hardening-w3`
- 当前优先项：分享表 scope、归属迁移按实例过滤、报告任务跨 worker 共享
- 阶段台账：`docs/agent/harness-progress-phase6.md`
- 阶段计划：已批准的实施改造计划 W3

## 最近稳定经验

- 浅题当一等缺陷：闸门失败和生成失败都不能把 `get_fallback_question` 作为 200 成功结果。
- 用户可见错误不要写“备用浅题”；按 `error_code` 分型，并给出重试 / 返回会话列表。
- Anthropic 兼容网关的 `base_url` 不要带尾部 `/v1`。
- 默认模型以网关实测为准：问题 `glm-5`，深度题 `ai/glm-5.1`，草案 `minimax-m3`，审稿 `gemini-3.1-pro-preview`。
- 高风险 task 默认先走 workflow preview；本周不要开 harness phase7，也不要先拆 `server.py`。
- 分享记录已带 `instance_scope_key`；创建、复用、删除和归属迁移按当前实例过滤，公开 token 读取不按当前进程 scope 拦截。
- 归属迁移与账号合并只改当前实例资产；云端导入的 rewrite/cleanup 仍是把导入数据改写到当前实例的既有语义。
- 报告任务状态会落盘到 `DATA_DIR/runtime/report-generation-status/`，跨 worker 以文件中的 `active` 为准，不要只看本进程 Future。

## 最近健康指针

- 改访谈质量闸门后优先跑 `tests.test_question_fast_strategy` 与 `tests.test_api_comprehensive` 中的 next-question 用例。
- 改报告绑定或重生失败态后优先跑 `tests.test_security_regression`。
- 改模型默认值后必须同步 `tests.test_scripts_comprehensive.test_model_role_defaults_match_release_config`。

## 注意事项

- 不要默认修改 `web/.env.local`、`web/.env.cloud`、真实部署环境或 `data/`。
- 不要全局关闭 `QUESTION_FAST_PATH_ENABLED`。
- 生产报告保守模式（W5）本周不做。

## 刷新命令

- `python3 scripts/agent_autodream.py`
- `python3 scripts/agent_heartbeat.py`
- `python3 scripts/agent_doc_gardener.py`
- `python3 scripts/agent_harness.py --profile auto`
- `python3 scripts/agent_eval.py --tag nightly`

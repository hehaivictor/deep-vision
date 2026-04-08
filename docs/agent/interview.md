# 访谈链路

## 适用范围

当任务涉及以下内容时，先读本文档：

- 会话创建、读取、更新、删除
- 下一题生成、回答提交、撤销、跳过追问、维度完成
- 访谈中途预检、证据 ledger、问题预取、超时恢复
- 会话内文档上传与删除

## 主要代码与测试

- 后端主入口：[web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- 前端访谈页：[web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
- API 综合回归：[tests/test_api_comprehensive.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_api_comprehensive.py)
- 提问策略与性能分流：[tests/test_question_fast_strategy.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_question_fast_strategy.py)
- 安全边界：[tests/test_security_regression.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py)
- 预检离线诊断脚本：[scripts/replay_preflight_diagnostics.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/replay_preflight_diagnostics.py)

## 先建立的心智模型

1. 访谈链路的核心对象是 session。
2. session 同时承载主题、维度覆盖、访谈日志、文档、报告生成上下文。
3. “下一题”不是纯前端逻辑，而是后端根据当前日志、证据 ledger、预检计划、lane 配置共同决策。
4. 前端要处理请求中的超时、失活恢复和中间态，后端则要保证接口在异常情况下能给出可恢复的状态。

## 进入代码前先看什么

- 如果改的是 API 行为，先搜索 `/api/sessions` 相关路由，再看对应测试。
- 如果改的是“为什么这里会追问 / 不追问 / 被预检打断”，先读 [scripts/replay_preflight_diagnostics.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/replay_preflight_diagnostics.py) 和相关安全回归测试。
- 如果改的是前端体验，例如加载态、超时看门狗、恢复逻辑，先在 [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js) 搜索 `nextQuestion`、`preflight`、`submitAnswer` 等关键词。

## 不变量

- 匿名用户不能调用会话写接口。
- 会话和其派生产物必须保留归属信息，不能绕过实例隔离。
- 下一题链路即使失败，也不能长期卡死在前端加载态。
- 预检干预需要留下结构化痕迹，例如是否干预、fingerprint、planner mode、probe slots。
- 测试环境默认禁用真实 AI 与外部依赖，保持 deterministic；新增测试时优先沿用这一模式。

## 推荐验证

- 改接口契约或会话生命周期：`python3 -m unittest tests.test_api_comprehensive`
- 改提问策略、lane、预检或 evidence ledger：`python3 -m unittest tests.test_question_fast_strategy`
- 改权限、匿名行为、隔离边界：`python3 -m unittest tests.test_security_regression`
- 改预检逻辑后，如需理解行为变化，可用历史会话执行：

```bash
python3 scripts/replay_preflight_diagnostics.py <session_id> --json
```

## 常见失误

- 只改前端状态，不补后端失败态，导致恢复链路仍不完整。
- 只看 happy path，不验证匿名写、跨账号访问、实例 scope 混淆。
- 在真实 `data/` 目录上手工构造测试数据，而不是复用临时目录测试模式。

# 报告与方案页

## 适用范围

当任务涉及以下内容时，先读本文档：

- 报告生成、状态轮询、质量门控、证据索引
- 报告模板、自定义章节蓝图、结构化快照
- 方案页 payload、渲染、分享链接
- 报告导出、附录 PDF、演示稿生成与状态查询

## 主要代码与测试

- 后端主入口：[web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- 方案页前端：[web/solution.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.js)
- 方案页页面与样式：[web/solution.html](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.html)、[web/solution.css](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.css)
- 主接口回归：[tests/test_api_comprehensive.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_api_comprehensive.py)
- 方案页载荷回归：[tests/test_solution_payload.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_solution_payload.py)
- 安全回归：[tests/test_security_regression.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py)

## 先建立的心智模型

1. 报告不是单一 Markdown 文件，而是一组结果：正文、结构化 sidecar、质量快照、导出资产、分享映射。
2. 方案页优先消费“已绑定报告的最终快照”，而不是重新从正文临时推断。
3. 老报告仍需要 Markdown fallback，因此新逻辑不能直接破坏兼容分支。
4. 分享是只读能力，任何公开 token 都不能反向获得写权限或越过 owner/scope 校验。

## 进入代码前先看什么

- 如果改报告生成链路，先定位 `generate-report`、状态轮询和质量门控相关路由。
- 如果改方案页输出，先读 [tests/test_solution_payload.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_solution_payload.py)，确认当前兼容矩阵。
- 如果改分享、公开访问、导出下载，先补看 [tests/test_security_regression.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py)。

## 不变量

- 方案页默认从绑定报告快照构建，不能悄悄退回到不完整的临时推导。
- 老报告的 Markdown fallback 必须继续可用，并保持 HTML 清洗与转义。
- 报告、导出资产、分享 token 的归属必须与 `owner_user_id`、`instance_scope_key` 一致。
- 公开分享接口只提供最小只读暴露，不能泄露管理态或其他用户数据。

## 推荐验证

- 改报告或方案页结构：`python3 -m unittest tests.test_solution_payload`
- 改报告 API、导出、分享、状态轮询：`python3 -m unittest tests.test_api_comprehensive`
- 改公开访问、权限或分享边界：`python3 -m unittest tests.test_security_regression`

## 常见失误

- 只改方案页前端，不同步更新后端 payload 结构和兼容测试。
- 忽略老报告 fallback，导致历史内容无法渲染。
- 在导出或分享路径上只验证拥有者 happy path，没有验证匿名与跨账号边界。

# 鉴权、绑定与账号合并

## 适用范围

当任务涉及以下内容时，先读本文档：

- 手机号验证码登录、绑定手机号、微信绑定
- 账号冲突、merge preview / apply、管理员 rollback
- 登录态失效、账号 takeover、身份绑定边界

## 主要代码与测试

- 后端主入口：[web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- 主前端入口：[web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
- 主接口回归：[tests/test_api_comprehensive.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_api_comprehensive.py)
- 安全与权限回归：[tests/test_security_regression.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/tests/test_security_regression.py)

## 先建立的心智模型

1. 登录、绑定和合并不是三套独立系统，而是一条“先识别当前用户，再决定接管、冲突提示或合并”的链路。
2. 绑定手机号或微信时，如果目标影子账号没有历史数据，可以直接 takeover；一旦对方已有历史数据，就必须走 preview / apply。
3. 账号合并是高风险写操作，必须同时看 preview token、确认短语和管理员 rollback 入口。

## 不变量

- 未登录用户不能直接进入 bind / merge apply。
- merge preview 和 merge apply 必须绑定当前候选上下文，不能跳过 preview 直接 apply。
- 绑定冲突时不能自动吞掉历史数据，必须先给出 merge_required 或 rollback 入口。
- 账号历史、导出资产、分享映射和归属关系不能因为绑定流程丢失。

## 推荐验证

- 改登录、绑定、合并主接口：`python3 -m unittest tests.test_api_comprehensive`
- 改匿名与越权边界：`python3 -m unittest tests.test_security_regression`
- 涉及前端登录态、License gate 或入口切换：`python3 scripts/agent_browser_smoke.py --suite extended`

## 常见失误

- 只验证直接绑定 happy path，没有验证冲突账号和 merge preview。
- 只看接口 200/400，没有验证 preview token、confirm phrase 和 rollback 入口是否仍在。
- 绑定链路改动后，没有回看登录视图、License gate 和主业务壳切换。

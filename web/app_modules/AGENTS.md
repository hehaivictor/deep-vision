# App Modules 局部入口

这个目录承载前端状态层与页面级 runtime 模块。

## 先看什么

- 仓库物理地图：[../../ARCHITECTURE.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/ARCHITECTURE.md)
- 报告与方案页：[../../docs/agent/report-solution.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/report-solution.md)
- 登录、绑定与账号合并：[../../docs/agent/auth-identity.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/auth-identity.md)
- 管理后台与运维：[../../docs/agent/admin-ops.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/admin-ops.md)

## 当前模块职责

- `interview_runtime.js`：访谈问答主流程
- `report_detail_runtime.js`：报告详情、导出、演示稿状态链
- `admin_center_state.js`：管理员中心页签与状态协调
- `session_list_state.js`：会话列表状态
- `report_state.js`：报告态管理
- `auth_license_state.js`：登录与 License 门禁状态

## 局部边界

- 这里是前端状态与交互层，不要引入 Python runtime / service 细节
- 优先通过 API 契约和已有页面状态协作，不要在前端硬编码后端内部实现词
- 方案页、分享页、License 门禁和管理员中心是高敏感 UI 链路；轻微文案改动与真实权限回退要分开看
- 不要为了让页面暂时可用而绕开 owner / license / readonly 边界

## 改动后先跑

- 浏览器回归：`python3 scripts/agent_browser_smoke.py --suite extended`
- 真链路浏览器回归：`python3 scripts/agent_browser_smoke.py --suite live-extended`
- 方案页载荷回归：`python3 -m unittest tests.test_solution_payload`
- 安全与权限回归：`python3 -m unittest tests.test_security_regression`

## 不要做什么

- 不要把新状态散落回 `app.js`，优先补进对应模块
- 不要把 mock-only 行为误当成真实后端契约
- 不要因为文案微调就放松对分享只读、登录态和 License gate 的真实边界验证

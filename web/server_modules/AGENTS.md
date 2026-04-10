# Server Modules 局部入口

这个目录承载从 `web/server.py` 抽离出来的后端 runtime / service 模块。

## 先看什么

- 仓库物理地图：[../../ARCHITECTURE.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/ARCHITECTURE.md)
- 管理后台与运维：[../../docs/agent/admin-ops.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/admin-ops.md)
- 访谈链路：[../../docs/agent/interview.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/interview.md)
- 报告与方案页：[../../docs/agent/report-solution.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/report-solution.md)

## 当前模块职责

- `runtime_bootstrap.py`：启动初始化与 startup snapshot
- `report_generation_runtime.py`：报告生成编排与质量门控
- `interview_runtime.py`：访谈推进与下一题运行时
- `admin_config_center.py`：配置中心读写服务
- `ownership_admin_flow.py`：管理员归属迁移编排
- `object_storage_history.py`：对象存储历史补齐与归档

## 局部边界

- 这里是 runtime / service 层，不是路由层；不要把 Flask request/response glue 再搬进来
- 不要 import 前端文件、静态资源或 `scripts.agent_*`
- 高风险写操作必须保留 preview / backup / rollback / evidence 链，不要只补 happy path
- 配置中心逻辑继续走 helper / service，不要在这里顺手增加环境文件直写捷径

## 改动后先跑

- 最小脚本回归：`python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`
- 主接口回归：`python3 -m unittest tests.test_api_comprehensive`
- 安全与权限回归：`python3 -m unittest tests.test_security_regression`
- 静态 guardrail：`python3 scripts/agent_static_guardrails.py`

## 不要做什么

- 不要为赶进度把新逻辑塞回 `web/server.py`
- 不要把运行时数据写回源码目录作为状态
- 不要绕开已有 task / contract / workflow 去做高风险生产动作

# Scripts 局部入口

这个目录承载 DeepVision 的 harness 脚本、运维脚本、迁移脚本和启动脚本。

## 先看什么

- 仓库总入口：[../AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)
- Harness 索引：[../docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)
- 物理地图：[../ARCHITECTURE.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/ARCHITECTURE.md)

## 目录职责

- `agent_*.py`：harness 主体、评估、观察、计划、契约、校准、园丁与心跳
- `admin_*` / `license_manager.py` / `sync_object_storage_history.py`：运维与治理脚本
- `import_*` / `rollback_*`：导入与回滚脚本
- `start-*.sh` / `run_gunicorn.py` / `prestart_web.py`：启动与部署辅助

## 局部边界

- 优先复用已有脚本，不要再造并行入口
- 高风险脚本默认先 preview / dry-run / audit，不要直接 apply
- `agent_*` 是 harness 层，不应被 `web/` 业务代码反向 import
- 这层负责 orchestration 与验证，不负责承载业务核心实现

## 改动后先跑

- 最小脚本回归：`python3 -m unittest tests.test_version_manager tests.test_scripts_comprehensive`
- 单入口检查：`python3 scripts/agent_harness.py --profile auto`
- 文档园丁：`python3 scripts/agent_doc_gardener.py`
- 薄运营面：`python3 scripts/agent_ops.py status`
- 刷新 heartbeat：`python3 scripts/agent_heartbeat.py`
- AutoDream Lite：`python3 scripts/agent_autodream.py`

## 高风险提醒

- 不要默认修改真实 `data/`、生产环境变量或导入/迁移目标目录
- `admin_migrate_ownership.py`、`import_external_local_data_to_cloud.py`、`rollback_external_local_data_import.py` 必须先看 task / playbook / contract

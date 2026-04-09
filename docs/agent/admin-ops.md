# 管理后台与运维能力

## 适用范围

当任务涉及以下内容时，先读本文档：

- License 批量生成、查询、延期、撤销与运行时开关
- 管理员中心、配置中心、运行监控、摘要缓存
- 用户搜索、归属迁移审计、preview、apply、rollback
- 列表接口性能与运维脚本

## 主要代码与文档

- 后端主入口：[web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- 管理员迁移脚本：[scripts/admin_migrate_ownership.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/admin_migrate_ownership.py)
- 迁移服务层：[scripts/admin_ownership_service.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/admin_ownership_service.py)
- License 管理脚本：[scripts/license_manager.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/license_manager.py)
- 列表接口压测：[scripts/loadtest_list_endpoints.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/loadtest_list_endpoints.py)
- 配置边界说明：[web/CONFIG.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/CONFIG.md)
- 实例隔离说明：[docs/instance-scope.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/instance-scope.md)

## 先建立的心智模型

1. 管理后台不是独立系统，而是挂在同一服务上的高权限接口集合。
2. 这里的大多数能力都具备破坏性或批量影响面，默认要先 preview、dry-run、审计或备份。
3. `site-config.js` 只管前端展示；后端运行、鉴权、白名单、实例隔离和第三方接入不在这里改。

## 不变量

- 管理后台接口必须要求管理员权限，普通登录用户不能透传。
- 运行时开关与批量操作要有明确边界，不能用前端显示配置代替真实服务端权限判断。
- 归属迁移、批量撤销、批量延期等操作默认应可 preview、可审计、可回滚。
- `mock` 短信、固定测试码、演示管理员手机号这类配置只适合调试或演示环境。
- 配置中心路由只负责参数收口与 helper 委托，不要在 `/api/admin/config-center*` 路由层直接拼装配置源或写 `.env / config.py / site-config.js`。

## 推荐验证

- 改管理员接口或权限边界：`python3 -m unittest tests.test_security_regression`
- 改脚本契约或命令行行为：`python3 -m pytest -q tests/test_scripts_comprehensive.py`
- 改综合接口返回：`python3 -m unittest tests.test_api_comprehensive`
- 改列表性能或缓存策略时，可补跑：

```bash
python3 scripts/loadtest_list_endpoints.py --base-url http://127.0.0.1:5001
```

## 操作建议

- 归属迁移优先 `list-users`、`audit`、`migrate` 的 dry-run，再决定是否 `--apply`。
- 配置中心写入前，先确认目标是 `.env`、`config.py` 还是 `site-config.js`，不要混淆层次。
- 调整配置中心接口时，优先复用 `build_admin_config_center_payload()` 与 `save_admin_config_group()`，不要把文件写入逻辑重新塞回 Flask 路由。
- 管理后台相关变更如果影响部署行为，务必同时检查 [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md) 和对应 runbook 是否需要更新。

## 常见失误

- 误把展示配置改到 `site-config.js`，而真正需要改的是环境变量或后端配置。
- 直接在生产风格数据上执行 apply，而不是先 preview 并保存摘要。
- 只验证管理员 happy path，不验证普通用户和匿名用户的拒绝路径。

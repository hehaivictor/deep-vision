# DeepVision 仓库收口与精简执行历史

> 归档时间：2026-04-09  
> 说明：本文档保留第一阶段仓库收口与第一轮后续清理的详细执行记录，供后续追溯使用。当前活跃计划请查看 [docs/repo-cleanup-execution-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/repo-cleanup-execution-plan.md)。

本文档用于把当前仓库结构审计后的结论，落成一份可执行、可跟踪、可验收的清理与优化计划。

适用目标：

- 收口多份真相源
- 清理过程性沉淀与重复文档
- 简化配置说明与忽略规则
- 为后续模块化重构提供稳定前置条件

不适用目标：

- 一次性重写 `web/server.py` 或 `web/app.js`
- 直接修改运行中的生产环境配置
- 改变现有用户数据或运行数据目录

## 1. 执行原则

1. 每个任务单独提交，不混做。
2. 优先收口文档、部署入口和目录结构，再进入代码重构。
3. 每一步都要保留明确验收命令，不靠主观判断“应该没问题”。
4. 不直接动真实运行数据；涉及 `data/`、真实 env、生产配置时先备份再操作。
5. 先做低风险高收益项，再做中期结构优化。

## 2. 总体顺序

建议按下面顺序推进：

1. 统一生产部署入口
2. 清理 `.memory` 过程文档
3. 收口迁移文档
4. 收口配置文档与 ignore 规则
5. 启动模块化重构计划

## 3. 任务一：统一生产部署入口

### 3.1 目标

只保留一套正式生产部署入口，消掉 `docs`、`output`、本地私有 env 之间的多份真相源问题。

### 3.2 当前问题

- 正式部署文件在 `output/`
- 生产环境变量模板在 `docs/`
- 私有生产基线又在本地 `web/.env.production`

长期看容易出现：

- 不确定该改哪一份
- 改了 compose，忘了改 docs
- 改了 docs，实际部署入口没变

### 3.3 具体动作

- [x] 将 `output/docker-compose.production.yml` 迁移到 `deploy/`
- [x] 将 `output/Dockerfile.production` 迁移到 `deploy/`
- [x] 精简或删除 `docs/docker-compose-production-environment.example.yml`
- [x] 更新 `README.md` 中的生产部署入口说明
- [x] 更新 `output/README.ai.md` 或清理 `output/` 中部署说明

### 3.4 涉及文件

- [deploy/docker-compose.production.yml](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/deploy/docker-compose.production.yml)
- [deploy/Dockerfile.production](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/deploy/Dockerfile.production)
- [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)
- [output/README.ai.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/output/README.ai.md)
- [deploy](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/deploy)

### 3.5 验收命令

```bash
rg -n "docker-compose.production|Dockerfile.production" /Users/hehai/Documents/开目软件/Agents/project/DeepVision
docker compose -f /Users/hehai/Documents/开目软件/Agents/project/DeepVision/deploy/docker-compose.production.yml config
```

### 3.6 完成标准

- 仓库中只剩一套正式可执行的生产部署入口
- 文档中不再出现另一套并行生产配置真相源

## 4. 任务二：清理 `.memory` 过程文档

### 4.1 目标

把个人工作痕迹移出仓库，只保留稳定的团队知识。

### 4.2 当前问题

`.memory/` 里已经有多份实施计划、问题整改方案、设计过程文档被纳入版本控制。它们更像工作痕迹，而不是长期知识资产。

### 4.3 具体动作

- [x] 审核 `.memory/` 下所有已跟踪文件
- [x] 将真正长期有效的内容迁入 `docs/` 或 `docs/agent/`
- [x] 将纯过程文件停止跟踪
- [x] 如有必要，在 `.memory/` 只保留一个索引说明文件

### 4.4 建议优先审查文件

- [.memory/solution-page-config-driven-implementation.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory/solution-page-config-driven-implementation.md)
- [.memory/solution-page-config-driven-dev-spec.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory/solution-page-config-driven-dev-spec.md)
- [.memory/task_plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory/task_plan.md)
- [.memory/v3_remediation_plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory/v3_remediation_plan.md)
- [.memory/notes.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory/notes.md)

### 4.5 验收命令

```bash
git ls-files /Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory
find /Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory -maxdepth 1 -type f | sort
```

### 4.6 完成标准

- `git ls-files .memory` 为空
- 或只保留 1 个稳定说明文件

## 5. 任务三：收口迁移文档

### 5.1 目标

迁移流程只维护一份主手册，避免命令、顺序、前置条件在多个文档里漂移。

### 5.2 当前问题

- `full-data-migration-runbook.md` 已经是完整主手册
- `external-local-data-cloud-import-guide.md` 顶部也已经导向它
- 但后者仍保留了大量重复命令和判断流程

### 5.3 具体动作

- [x] 保留 `docs/full-data-migration-runbook.md` 为唯一主手册
- [x] 将 `docs/external-local-data-cloud-import-guide.md` 缩成“快速判断 + 跳转”
- [x] 在 `docs/agent/migration.md` 只保留导航，不重复详细命令

### 5.4 涉及文件

- [docs/full-data-migration-runbook.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/full-data-migration-runbook.md)
- [docs/external-local-data-cloud-import-guide.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/external-local-data-cloud-import-guide.md)
- [docs/agent/migration.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/migration.md)

### 5.5 验收命令

```bash
rg -n "import_external_local_data_to_cloud.py|sync_object_storage_history.py|rollback_external_local_data_import.py" /Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs
```

### 5.6 完成标准

- 详细迁移命令只维护在一份主文档里
- 其他文档只做判断分流和跳转

## 6. 任务四：收口配置文档与 ignore 规则

### 6.1 目标

减少配置说明重复和 ignore 规则分叉。

### 6.2 当前问题

- `README.md` 与 `web/CONFIG.md` 同时在解释 env/config 边界
- `web/.gitignore` 与根 `.gitignore` 高度重复

### 6.3 具体动作

- [x] 缩减 `web/CONFIG.md`，只保留 `site-config.js` 说明
- [x] 保留 `README.md` 作为 env/config 全局入口
- [x] 删除 `web/.gitignore`
- [x] 将必要规则并回根 `.gitignore`

### 6.4 涉及文件

- [web/CONFIG.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/CONFIG.md)
- [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)
- [web/.gitignore](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/.gitignore)
- [/.gitignore](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.gitignore)

### 6.5 验收命令

```bash
rg -n "web/.env.local|web/.env.cloud|config.py|site-config.js" /Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/CONFIG.md
git check-ignore -v /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/.env.local
```

### 6.6 完成标准

- README 负责全局配置说明
- CONFIG 只负责前端展示配置说明
- ignore 规则只在根目录维护

## 7. 任务五：启动模块化重构计划

### 7.1 目标

不做一次性重写，先从低耦合职责开始拆分，为后续持续迭代降低复杂度。

### 7.2 当前问题

- `web/server.py` 已接近 5 万行
- `web/app.js` 也超过 1 万行
- 继续在单文件里累积功能，会让后续改动越来越高风险

### 7.3 第一批建议抽离职责

从 `web/server.py` 抽离：

- [x] 配置读取与启动初始化
- [x] 对象存储历史补传适配层
- [x] 管理员配置中心 helper
- [x] 迁移与归属修复 helper

从 `web/app.js` 抽离：

- [x] 会话列表状态管理
- [x] 报告列表与详情缓存
- [x] 登录 / License gate 状态管理

### 7.4 建议目录

- [x] 新增 `web/server_modules/`
- [x] 新增 `web/app_modules/`

### 7.5 涉及文件

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
- 计划新增的模块目录

### 7.6 验收命令

```bash
python3 -m py_compile /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py
node --check /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_guardrails.py --quiet
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_smoke.py
```

### 7.7 完成标准

- 至少有一批低耦合职责被稳定迁出大文件
- 不引入新的并行流程或配置真相源

### 7.8 当前进展

- [x] 已新增 `web/server_modules/runtime_bootstrap.py`
- [x] 已新增 `web/server_modules/object_storage_history.py`
- [x] 已新增 `web/server_modules/admin_config_center.py`
- [x] 已将 env 文件加载、启动状态协调器与启动摘要日志迁出 `web/server.py`
- [x] 已完成 `uv` / Gunicorn / `before_request` 三条启动链路对统一协调器的接线
- [x] 已将对象存储历史补传与运维归档记录适配层迁出 `web/server.py`
- [x] 已将管理员配置中心 payload / 保存逻辑迁出 `web/server.py`
- [x] 已新增 `web/server_modules/ownership_admin_flow.py`
- [x] 已将管理员归属迁移的 preview 会话态、审计、历史列表、apply 收尾与 rollback 编排迁出 `web/server.py`
- [x] 已新增 `web/app_modules/session_list_state.js`
- [x] 已将会话列表加载、筛选、分页、虚拟列表与状态徽标逻辑迁出 `web/app.js`
- [x] 已完成 `web/index.html` 对会话列表状态模块的脚本接线
- [x] 已新增 `web/app_modules/report_state.js`
- [x] 已将报告列表加载、筛选、分组、虚拟列表、批量选择与详情缓存逻辑迁出 `web/app.js`
- [x] 已完成 `web/index.html` 对报告状态模块的脚本接线
- [x] 已新增 `web/app_modules/auth_license_state.js`
- [x] 已将登录态检查、License gate、短信/微信登录、绑定手机号、账号合并与退出登录逻辑迁出 `web/app.js`
- [x] 已完成 `web/index.html` 对认证与 License 状态模块的脚本接线

## 8. 每步交付要求

每个任务执行时，都建议遵守：

1. 单独提交，不混入其他主题改动
2. 先更新文档和目录，再动代码
3. 每步完成后执行最小验证

建议固定验证命令：

```bash
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_guardrails.py --quiet
python3 /Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/agent_smoke.py
```

## 9. 进度记录模板

建议每完成一个任务，按下面模板记录：

```markdown
## YYYY-MM-DD - 任务 X

- 状态：进行中 / 已完成 / 已回退
- 实际改动：
- 验收结果：
- 遗留问题：
- 下一步：
```

## 10. 推荐推进方式

推荐采用以下节奏：

1. 先完成任务一和任务二
2. 再完成任务三和任务四
3. 最后进入任务五的模块化拆分

一句话总结：

`先收口真相源和过程噪音，再做结构优化。`

## 11. 第二轮复查后的后续任务

第一轮收口与第一批模块化已完成。基于最近一次复查，当前仓库不存在新的运行级风险，但仍有一批“低风险、高清洁度收益”的残留值得继续处理。

这一轮后续任务重点解决：

- 清理已经失效的 AI 目录索引文件
- 归档已完成的仓库收口执行台账
- 继续收窄 `README.md` 与 agent 文档的职责边界
- 为下一阶段业务模块化拆分建立更聚焦的候选清单

建议按下面顺序继续推进：

1. 清理 AI 目录索引与空目录
2. 归档已完成执行计划
3. 收瘦 README 与 agent 命令入口
4. 规划第二阶段模块化拆分

## 12. 任务六：清理 AI 目录索引与空目录

### 12.1 目标

删除已经没有真实消费方、且部分内容已过时的目录索引文件，减少“这些文件是不是还承担某种约定”的认知噪音。

### 12.2 当前问题

- `output/PATH.ai.md` 仍然引用已经迁走的生产部署文件，属于明确过时内容
- `output/README.ai.md`、`deploy/README.ai.md`、`memory/README.ai.md` 只起目录索引作用，当前没有真实流程消费
- `deploy/PATH.ai.md`、`memory/PATH.ai.md` 同样只是 AI 生成的目录提示，不属于长期知识资产
- `.memory/` 目前已经是空目录
- `memory/daily/` 目前也为空目录

### 12.3 具体动作

- [x] 删除 `output/PATH.ai.md`
- [x] 删除 `output/README.ai.md`
- [x] 删除 `deploy/PATH.ai.md`
- [x] 删除 `deploy/README.ai.md`
- [x] 删除 `memory/PATH.ai.md`
- [x] 删除 `memory/README.ai.md`
- [x] 删除空目录 `.memory/`
- [x] 评估并删除空目录 `memory/daily/`
- [x] 如 `memory/` 整体无后续用途，删除 `memory/` 目录并同步更新根 `.gitignore`

### 12.4 涉及文件与目录

- [output/PATH.ai.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/output/PATH.ai.md)
- [output/README.ai.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/output/README.ai.md)
- [deploy/PATH.ai.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/deploy/PATH.ai.md)
- [deploy/README.ai.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/deploy/README.ai.md)
- [memory/PATH.ai.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/memory/PATH.ai.md)
- [memory/README.ai.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/memory/README.ai.md)
- [/.memory](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory)
- [memory](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/memory)
- [/.gitignore](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.gitignore)

### 12.5 验收命令

```bash
rg -n "PATH\\.ai|README\\.ai|AI_GENERATED_START" /Users/hehai/Documents/开目软件/Agents/project/DeepVision
find /Users/hehai/Documents/开目软件/Agents/project/DeepVision/.memory -maxdepth 2 -type f 2>/dev/null
find /Users/hehai/Documents/开目软件/Agents/project/DeepVision/memory -maxdepth 2 -type f 2>/dev/null
```

### 12.6 完成标准

- 仓库中不再保留无消费方的 `PATH.ai.md` / `README.ai.md`
- `.memory/` 不再作为空目录残留
- `memory/` 若继续存在，必须有明确且真实的使用目的

## 13. 任务七：归档已完成执行计划

### 13.1 目标

避免 [docs/repo-cleanup-execution-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/repo-cleanup-execution-plan.md) 继续承担“主文档”角色，同时又保留大量已完成任务与历史路径，形成新的过时真相源。

### 13.2 当前问题

- 本文档前半部分已经是“已完成事项台账”
- 文中仍保留 `output/`、`.memory/` 等历史路径与动作说明
- 继续直接在主文档区维护，会逐渐从“计划”变成“半过时审计记录”

### 13.3 具体动作

- [ ] 将本文档拆分为“归档记录 + 当前活跃计划”两部分
- [ ] 新建归档目录，例如 `docs/archive/` 或 `docs/audits/`
- [ ] 将已完成的一至五任务归档到历史文档
- [ ] 保留一份新的精简版活跃计划，只保留任务六及后续事项
- [ ] 更新 README 或相关导航，避免继续直接指向过时计划

### 13.4 涉及文件

- [docs/repo-cleanup-execution-plan.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/repo-cleanup-execution-plan.md)
- 可能新增的归档文档目录，例如 `docs/archive/`
- [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)

### 13.5 验收命令

```bash
rg -n "repo-cleanup-execution-plan" /Users/hehai/Documents/开目软件/Agents/project/DeepVision
```

### 13.6 完成标准

- 主文档区只保留活跃计划
- 已完成的历史收口过程转入归档文档，不再与当前状态混写

## 14. 任务八：收瘦 README 与 agent 命令入口

### 14.1 目标

把 `README.md` 收回到“仓库总览 + 启动方式 + 配置入口 + 关键链接”，把长命令清单与 agent 细节继续压回 `docs/agent/README.md`。

### 14.2 当前问题

- `README.md` 现在已经同时承担：
  - 产品总览
  - 本地/云端/生产启动
  - 配置说明
  - 运维接口说明
  - 大段 agent/harness 命令索引
- 这让它再次接近“总览文档过重”的边界
- [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md) 已经具备承接详细命令索引的能力

### 14.3 具体动作

- [ ] 将 `README.md` 中超长的 agent/harness 命令区块压缩为跳转说明
- [ ] 保留 `README.md` 中最小必要的本地启动、云端联调、生产部署入口
- [ ] 将详细命令继续收口到 `docs/agent/README.md`
- [ ] 校验 `AGENTS.md`、`docs/agent/README.md`、`README.md` 三者的入口边界不再重复

### 14.4 涉及文件

- [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)
- [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)
- [AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)

### 14.5 验收命令

```bash
python3 - <<'PY'
from pathlib import Path
for p in ['README.md','docs/agent/README.md','AGENTS.md']:
    path=Path('/Users/hehai/Documents/开目软件/Agents/project/DeepVision')/p
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        lines=sum(1 for _ in f)
    print(f'{p}: {lines}')
PY
rg -n "agent_harness.py --profile auto|agent_smoke.py|agent_guardrails.py" /Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md /Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md /Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md
```

### 14.6 完成标准

- `README.md` 只保留全局入口，不再维护超长 agent 命令列表
- 详细命令入口由 `docs/agent/README.md` 和 `AGENTS.md` 承担
- 三份入口文档的职责边界清晰可解释

## 15. 任务九：规划第二阶段模块化拆分

### 15.1 目标

在第一批基础设施与状态模块拆分完成后，继续明确第二阶段最值得拆的业务热点，但不急于一次性大改。

### 15.2 当前问题

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py) 仍约 4.7 万行
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js) 仍约 1.1 万行
- 第一批拆出的 `server_modules` / `app_modules` 主要解决了启动、配置、列表状态与登录边界
- 还未触及最重的业务热点：
  - 访谈推进编排
  - 报告生成与质量门控
  - 管理员中心复杂页签逻辑
  - 报告详情渲染与导出编排

### 15.3 具体动作

- [ ] 对 `web/server.py` 做一次热点分段标注，明确下一个拆分对象
- [ ] 对 `web/app.js` 做一次热点分段标注，明确下一个拆分对象
- [ ] 为第二阶段拆分生成一份“候选模块清单 + 风险说明”
- [ ] 优先评估以下候选：
  - 报告生成编排与质量门控
  - 访谈问题推进与超时恢复
  - 管理员中心页签与配置交互
  - 报告详情渲染、导出与演示稿状态链路

### 15.4 涉及文件

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
- [web/server_modules](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules)
- [web/app_modules](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules)
- 可新增的规划文档，例如 `docs/agent/plans/`

### 15.5 验收命令

```bash
python3 - <<'PY'
from pathlib import Path
for p in ['web/server.py','web/app.js']:
    path=Path('/Users/hehai/Documents/开目软件/Agents/project/DeepVision')/p
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        lines=sum(1 for _ in f)
    print(f'{p}: {lines}')
PY
find /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules -maxdepth 1 -type f | sort
find /Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules -maxdepth 1 -type f | sort
```

### 15.6 完成标准

- 明确第二阶段模块化的下一批目标
- 不在同一轮里同时实施多块高耦合业务拆分
- 保持“先规划，再拆分，再验证”的节奏

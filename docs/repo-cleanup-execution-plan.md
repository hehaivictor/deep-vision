# DeepVision 仓库收口与精简活跃计划

本文档只保留当前仍需推进的收尾任务，避免继续混入已完成阶段的历史执行细节。

已归档的历史执行记录见：

- [docs/archive/repo-cleanup-execution-history.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/archive/repo-cleanup-execution-history.md)

## 1. 当前状态

已完成：

- 统一生产部署入口
- 清理 `.memory` 过程文档
- 收口迁移文档
- 收口配置文档与 ignore 规则
- 第一批启动与前端状态模块化拆分
- 清理无消费方的 `PATH.ai.md` / `README.ai.md` 与空目录残留

当前剩余重点：

1. 按第二阶段模块化拆分计划选择下一块业务热点实施

## 2. 执行原则

1. 每个任务单独提交，不混做。
2. 先做文档与入口边界收口，再进入下一阶段代码拆分。
3. 每一步都保留明确验收命令，不靠主观判断“应该没问题”。
4. 不直接修改真实运行数据、真实部署环境变量或生产实例配置。
5. 第二阶段模块化先规划、再拆分、再验证，不做一次性大手术。

## 3. 任务八：收瘦 README 与 agent 命令入口

### 3.1 目标

把 `README.md` 收回到“仓库总览 + 启动方式 + 配置入口 + 关键链接”，把详细的 agent / harness 命令继续压回 `docs/agent/README.md` 与 `AGENTS.md`。

### 3.2 当前问题

- `README.md` 目前同时承担产品总览、配置说明、生产部署、运维接口和长篇 agent 命令索引
- [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md) 已具备承接命令导航的能力
- [AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md) 已包含更适合 agent 使用的高密度入口

### 3.3 具体动作

- [x] 将 `README.md` 中超长的 agent / harness 命令区块压缩为跳转说明
- [x] 保留 `README.md` 中最小必要的本地启动、云端联调、生产部署入口
- [x] 将详细命令继续收口到 `docs/agent/README.md`
- [x] 校验 `AGENTS.md`、`docs/agent/README.md`、`README.md` 三者的入口边界不再重复

### 3.4 涉及文件

- [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)
- [docs/agent/README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/README.md)
- [AGENTS.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/AGENTS.md)

### 3.5 验收命令

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

### 3.6 完成标准

- `README.md` 只保留全局入口，不再维护超长 agent 命令列表
- 详细命令入口由 `docs/agent/README.md` 和 `AGENTS.md` 承担
- 三份入口文档的职责边界清晰可解释

## 4. 任务九：规划第二阶段模块化拆分

### 4.1 目标

在第一批基础设施与状态模块拆分完成后，继续明确第二阶段最值得拆的业务热点，但不急于一次性大改。

### 4.2 当前问题

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py) 仍约 4.7 万行
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js) 仍约 1.1 万行
- 第一批拆出的 `server_modules` / `app_modules` 主要解决了启动、配置、列表状态与登录边界
- 还未触及最重的业务热点：
  - 访谈推进编排
  - 报告生成与质量门控
  - 管理员中心复杂页签逻辑
  - 报告详情渲染与导出编排

### 4.3 具体动作

- [x] 对 `web/server.py` 做一次热点分段标注，明确下一个拆分对象
- [x] 对 `web/app.js` 做一次热点分段标注，明确下一个拆分对象
- [x] 为第二阶段拆分生成一份“候选模块清单 + 风险说明”
- [x] 优先评估以下候选：
  - 报告生成编排与质量门控
  - 访谈问题推进与超时恢复
  - 管理员中心页签与配置交互
  - 报告详情渲染、导出与演示稿状态链路

### 4.4 涉及文件

- [web/server.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server.py)
- [web/app.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app.js)
- [web/server_modules](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/server_modules)
- [web/app_modules](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/app_modules)
- 可新增的规划文档，例如 `docs/agent/plans/`
- [docs/agent/plans/module-split-phase2.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/plans/module-split-phase2.md)

### 4.5 验收命令

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

### 4.6 完成标准

- 明确第二阶段模块化的下一批目标
- 不在同一轮里同时实施多块高耦合业务拆分
- 保持“先规划，再拆分，再验证”的节奏

## 5. 推荐推进顺序

1. 按 [docs/agent/plans/module-split-phase2.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/docs/agent/plans/module-split-phase2.md) 选择下一块业务热点
2. 单模块推进并保留最小验证证据

一句话总结：

`先把第二阶段拆分目标讲清，再进入下一轮业务模块化。`

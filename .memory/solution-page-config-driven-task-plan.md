# Task Plan: 方案页场景配置驱动化

## Goal
将方案页从“后端按少量 profile 硬编码拼装”升级为“由场景配置声明目录、结构和提炼逻辑驱动”，做到新增场景主要靠配置，不再逐个写适配代码。

## Phases
- [x] Phase 1: 现状梳理与约束确认
- [x] Phase 2: 目标架构与数据模型设计
- [x] Phase 3: 实施路径拆解
- [x] Phase 4: 进入代码改造执行

## Key Questions
1. 如何让方案页目录完全由场景配置驱动，而不是关键词猜测？
2. 如何避免把每个场景都变成一套新的后端分支逻辑？
3. 如何在不推翻现有报告链路的前提下平滑迁移？
4. 如何验证新方案页不是“结构正确但内容仍然空洞”？

## Decisions Made
- 采用独立 `solution` 配置，而不是继续复用 `report.sections`
- 采用“声明式 schema + 通用 resolver/transform”架构，不再增加场景 if/else
- 保留现有报告 V3 流水线，新增独立 `solution_snapshot` 生成层
- 迁移策略采用“兼容旧链路 + 默认推导 + 显式配置优先”

## Errors Encountered
- 现有 `.memory/task_plan.md` 已被其他任务占用，不能覆盖；因此创建 scoped plan 文件
- `solution DSL` 中“未决问题”“下一步推进”在首版 token 映射里命中错误，已通过调整关键词顺序与补充中文关键词修复

## Status
**Currently in Phase 4** - 已完成方案页配置驱动主链路、自定义场景创建弹窗的 solution 配置入口与目录预览、方案页前端渲染状态联调及回归验证。

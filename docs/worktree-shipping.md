# DeepVision worktree-shipping 项目约定

本文档只描述 DeepVision 仓库在使用全局 `worktree-shipping` Skill 时的项目侧约定。通用命令和通用流程见全局操作手册：

- `/Users/hehai/.codex/skills/worktree-shipping/README.md`

## 适用范围

本仓库已经接入以下自动化链路：

- `worktree -> 分支 -> PR -> 顺序化 squash merge -> 清理 -> 主工作区同步`

项目级配置文件位于：

- `/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.codex/ship.yml`

任务级本地元数据位于：

- `<task-worktree>/.codex/task.json`

注意：

- `.codex/ship.yml` 入库
- `.codex/task.json` 只保存在本地 task worktree，不入库

## 当前项目配置

DeepVision 当前固定使用以下项目配置：

- `project.default_base = main`
- `project.branch_prefix = codex/`
- `pr.merge_method = squash`
- `checks.required_jobs = [pr-smoke]`
- `cleanup.remove_local_worktree = true`
- `cleanup.remove_local_branch = true`
- `cleanup.sync_main_after_batch = true`

## 版本与发布约定

DeepVision 保留现有版本碎片聚合机制，不改成普通项目的直接版本命令模式。

当前配置为：

- `versioning.mode = fragment_release`
- `versioning.fragment_refresh_command = python3 scripts/version_manager.py fragment`
- `versioning.post_merge_workflow_name = 聚合版本碎片`
- `versioning.structured_changelog = true`

实际含义：

- 功能分支不直接争抢正式版本号
- task 分支在提交和 ship 过程中，会刷新 `changes/unreleased/*.json` 变更碎片
- PR 合入 `main` 后，等待 GitHub Actions 工作流“聚合版本碎片”完成
- 聚合成功后由主线生成正式 `web/version.json`
- 结构化中文更新信息继续由 `scripts/version_manager.py` 生成

相关实现位置：

- `/Users/hehai/Documents/开目软件/Agents/project/DeepVision/scripts/version_manager.py`
- `/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.github/workflows/release-version.yml`
- `/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/version.json`

## 自动修复白名单

DeepVision 当前只允许两类确定性自动修复：

- `web/version.json -> keep_theirs`
- `changes/unreleased/*.json -> regenerate_with_command`

其中：

- `web/version.json` 冲突时，保留目标分支版本结果，避免功能分支覆盖主线正式版本
- `changes/unreleased/*.json` 冲突时，重新执行 `python3 scripts/version_manager.py fragment`

除此之外的业务代码冲突，不自动处理，整批停止。

## CI 与 merge 后等待

当前 PR 必需检查：

- `pr-smoke`

当前冒烟 workflow 位于：

- `/Users/hehai/Documents/开目软件/Agents/project/DeepVision/.github/workflows/pr-smoke.yml`

其职责是：

- 安装最小 Python 测试环境
- 执行 `tests/test_version_manager.py`
- 执行 `tests/test_scripts_comprehensive.py`

PR `squash merge` 成功后，交付链路不会立刻继续清理，而是先等待：

- GitHub Actions 工作流 `聚合版本碎片`

只有该工作流成功后，才继续：

- 删除远端分支
- 删除本地 worktree
- 删除本地分支
- 同步主工作区 `main`

## 推荐操作顺序

DeepVision 仓库推荐固定用下面这组命令：

```bash
# 1. 在主工作区查看整体状态
shipctl status

# 2. 在 task worktree 中标记 ready
shipctl ready

# 3. 回到主工作区预览交付顺序
shipctl preview

# 4. 在主工作区执行自动交付
shipctl apply

# 5. 如有必要，补跑清理
shipctl cleanup
```

如果尚未接入新仓库，则先在主工作区执行：

```bash
shipctl bootstrap --json
shipctl bootstrap --write --yes
```

## 故障处理边界

当前 DeepVision 与总控 Skill 的联动边界如下：

- rebase 出现业务代码冲突：整批停止
- 某个 PR 的 CI 真实失败：整批停止
- 某个 PR merge 后，“聚合版本碎片”失败：整批停止
- 若属于白名单自动修复或偶发 CI 失败，可在配置允许范围内自动重试

不会自动做的事情：

- 不会自动解决业务代码冲突
- 不会自动修改测试断言以换取 CI 通过
- 不会自动 rebase 仍在开发中的其他活跃 worktree

## 本地同步与清理结果

当整批任务全部成功后，当前默认收尾动作是：

1. `git fetch origin --prune`
2. 清理已成功合并任务对应的远端分支
3. 清理已成功合并任务对应的本地 worktree
4. 清理已成功合并任务对应的本地分支
5. 在主工作区执行 `git pull --ff-only origin main`

因此，成功 merge 的任务分支会一并清理，本地主工作区也会自动同步到最新主线。

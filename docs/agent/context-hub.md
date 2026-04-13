# Context Hub 接入说明

`Context Hub` 在 DeepVision 中的定位是“开发/Agent 侧的第三方文档检索基础设施”，不是线上用户功能，也不是现有智谱 MCP 联网搜索的替代品。

## 何时使用

- 你准备接第三方 SDK、API、框架能力，但不想靠模型记忆猜接口。
- 你需要当前版本的官方/策展文档，而不是泛搜索结果。
- 你希望把本次踩过的坑记录下来，供下次 agent 会话复用。

典型例子：

- 接 OpenAI / Anthropic / Stripe / LangChain / Playwright 等 SDK。
- 为 DeepVision 的脚本、harness 或 Web 逻辑接入新的外部依赖。

## 仓库内入口

先检查运行时：

```bash
python3 scripts/context_hub.py doctor
```

常用命令：

```bash
python3 scripts/context_hub.py search openai --json
python3 scripts/context_hub.py get openai/chat --lang py
python3 scripts/context_hub.py annotate openai/chat "DeepVision 当前优先使用 Responses API 风格"
python3 scripts/context_hub.py feedback openai/chat up --label accurate "Python 示例和最新模型命名一致"
```

如果你要把它跑成 MCP server：

```bash
python3 scripts/context_hub.py mcp
```

说明：

- 优先使用本地 `node_modules/.bin/chub`。
- 如果全局已安装 `chub` / `chub-mcp`，会直接复用。
- 两者都没有时，会自动回退到 `npx --package @aisuite/chub`。

## 与 DeepVision 现有能力的边界

- `web/server.py` 里的智谱 MCP 搜索，服务的是运行时联网检索。
- `scripts/context_hub.py` 服务的是仓库开发、脚本实现、Agent 编码时的文档取数。
- 不要把 `Context Hub` 直接塞进 DeepVision 的线上请求链路，除非后续明确要做用户侧新能力，并补齐鉴权、稳定性和缓存治理。

## 推荐工作流

1. 先 `search` 找到正确文档 ID。
2. 再 `get` 拉取当前语言/版本文档。
3. 基于文档写代码，而不是凭记忆猜接口。
4. 如果发现仓库特有坑点，用 `annotate` 写本地经验。
5. 文档质量有问题时，用 `feedback` 回传给上游。

## DeepVision 约定

- 只把它当“开发时的知识源”，不要引入线上硬依赖。
- 外部能力接入仍需走 DeepVision 现有测试矩阵，不因为拿到了文档就跳过验证。
- 高风险变更依然先走 preview / dry-run / harness，而不是直接 apply。

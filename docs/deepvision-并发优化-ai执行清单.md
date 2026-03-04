# DeepSense 并发优化 AI 执行清单

更新时间：2026-03-04  
数据来源：`/Users/hehai/Downloads/system-results/*.json`

## 1. 压测结论（当前基线）

1. 核心瓶颈集中在列表接口：`reports_list`、`sessions_list`。
2. `auth_login`、`auth_me` 在高并发下仍稳定，不是主瓶颈。
3. 主要错误为 `The read operation timed out`，属于后端处理慢导致的超时。
4. `reports_list` 在 10 线程开始明显恶化，20/30/40 线程接近或达到不可用。
5. `sessions_list` 在 30 线程开始明显超时，40 线程接近崩溃。

关键数据摘录：

| 并发线程 | 总错误率 | reports_list 错误率 | sessions_list 错误率 |
| --- | --- | --- | --- |
| 10 | 6.8% | 52.6% | 0.0% |
| 20 | 16.3% | 96.9% | 0.0% |
| 30 | 25.0% | 100.0% | 28.6% |
| 40 | 49.0% | 100.0% | 93.5% |

说明：`system-concurrency-result-20260227-192621.json`（50 线程，791772 请求且 100% 失败）明显异常，建议作为异常样本剔除，不作为容量依据。

## 2. 执行原则

1. 先止血再重构：先做 P0，把超时和雪崩降下来。
2. 保持接口兼容：默认返回结构不破坏前端。
3. 所有优化均可回滚：每项改动单独提交。
4. 每项都必须有验收命令和指标。

## 2.1 当前进度（2026-03-04）

- [x] P0 全部完成（缓存、分页、429、UTF-8、回归测试）。  
- [x] P1 全部完成（SQLite 元数据索引、写时同步、组合索引、列表观测指标）。  
- [x] P2-1 完成（Gunicorn/Wsgi 生产运行方式）。  
- [x] P2-2 完成（列表接口 `ETag/If-None-Match` 与 `304`）。  
- [x] P2-3 完成（报告生成任务池队列化 + 状态轮询 + 队列过载 `429` + 指标观测）。

## 3. AI 全量执行清单

## P0（当天完成，先止血）

1. 优化 `reports_list` 的 owner 读取路径  
目标：消除每个报告重复读取 `.owners.json` 的高开销。  
修改文件：`web/server.py`。  
改造要点：  
- `load_report_owners` 增加内存缓存（按 `mtime_ns + size` 失效）。  
- `list_reports` 改为单次加载 owner_map 后过滤。  
- 增加报告文件安全校验，仅处理 `REPORTS_DIR` 下 `.md`。  
验收：20/30 线程下 `reports_list` 超时率明显下降，接口字段保持不变。

2. 优化 `sessions_list` 的会话读取路径  
目标：避免每次列表请求反复 `json.loads` 全量会话文件。  
修改文件：`web/server.py`。  
改造要点：  
- 新增会话元数据缓存（key: 文件名；失效：`mtime_ns + size`）。  
- 列表读取只取轻量字段：`session_id/topic/status/created_at/updated_at/interview_count/scenario_id/scenario_config`。  
- 缓存清理逻辑：文件删除后自动剔除缓存项。  
验收：30/40 线程下 `sessions_list` 的 p95 与错误率显著下降。

3. 给列表接口加分页（强制）  
目标：防止全量扫描返回导致单请求放大。  
修改文件：`web/server.py`、必要时 `web/app.js`。  
改造要点：  
- `/api/sessions`、`/api/reports` 支持 `page/page_size`。  
- 默认 `page_size=20`，上限 `100`。  
- 保持不传参数时可兼容旧前端。  
验收：接口分页稳定，前端不报错。

4. 增加过载保护（快速失败）  
目标：避免线程被长超时拖死。  
修改文件：`web/server.py`。  
改造要点：  
- 对 `sessions_list`、`reports_list` 增加并发阈值控制。  
- 超阈值直接返回 `429` + `Retry-After`。  
- 日志记录降级触发次数。  
验收：高并发下 429 可控，read timeout 显著减少。

5. 统一编码兜底  
目标：彻底规避 `'ascii' codec can't encode`。  
修改文件：`web/server.py`。  
改造要点：  
- 文件读写、异常输出统一 UTF-8。  
- 对可能触发编码异常的日志路径做显式处理。  
验收：压测与日志中无 ascii 编码异常。

6. 补齐测试  
目标：防止性能修复引入行为回归。  
修改文件：`tests/test_api_comprehensive.py`。  
测试新增：  
- 分页参数与默认值测试。  
- 列表字段兼容测试。  
- 缓存命中与缓存失效测试。  
- 429 过载保护测试。  
验收命令：  
- `python3 -m py_compile web/server.py`  
- `python3 -m unittest tests.test_api_comprehensive`

## P1（3-7天，解决根因）

1. 建立元数据索引层（SQLite）  
目标：列表查询从“扫目录+读 JSON”改为“查索引表”。  
建议表：`sessions_meta`、`reports_meta`、`report_owners`、`deleted_reports`。

2. 改为写时同步索引  
目标：会话/报告创建更新删除时同步更新索引，消除读时聚合。

3. 增加组合索引  
目标：提升高并发下 owner 维度查询稳定性。  
索引建议：`(owner_user_id, updated_at DESC)`。

4. 增加观测指标  
目标：可持续追踪退化。  
指标建议：列表耗时、缓存命中率、目录扫描耗时、429 次数、超时原因分布。

## P2（1-2周，提升容量上限）

1. 生产模式改为 WSGI 多 worker  
目标：提升并发处理能力，避免 `app.run` 单进程瓶颈。  
建议：gunicorn/uwsgi + 多 worker + 合理超时。

2. 前置网关优化  
目标：降低传输成本和重复请求开销。  
建议：Nginx keepalive、gzip、`ETag/Last-Modified`、304 协商缓存。

3. 报告生成异步化  
目标：避免重任务占用接口线程，压垮列表请求。  
建议：队列化+状态轮询。

## 4. 下一轮压测验收门槛

1. 20 线程：总错误率 `<1%`，`reports_list p95 <2s`，`sessions_list p95 <1.5s`。
2. 30 线程：总错误率 `<3%`，无大面积 `read timeout`。
3. 40 线程：允许少量 `429`，但不允许超时雪崩。

## 5. 可直接复制给代码 AI 的执行指令

```text
请按以下顺序改造 deep-vision，并在每一步完成后运行回归测试并提交中文 commit：

1) 优化 web/server.py 的 reports_list 与 owner 映射读取：
- 对 load_report_owners 做 mtime_ns+size 缓存
- list_reports 改为单次 owner_map 过滤，不要每个报告重复读 .owners.json
- 保持接口返回结构不变

2) 优化 sessions_list：
- 增加会话列表元数据缓存（按文件签名失效）
- 列表接口不再反复 json.loads 全量会话
- 保持现有字段兼容

3) 增加分页与轻量模式：
- /api/sessions 和 /api/reports 支持 page/page_size（默认20，上限100）
- 列表默认轻量字段，详情接口返回完整字段

4) 增加过载保护：
- 列表接口超阈值直接返回 429 + Retry-After
- 避免读超时拖垮

5) 修复 UTF-8 编码兜底：
- 消除 ascii codec 报错路径

6) 补充 tests/test_api_comprehensive.py：
- 分页、缓存、429、兼容性测试

7) 执行验证：
- python3 -m py_compile web/server.py
- python3 -m unittest tests.test_api_comprehensive

8) 输出变更说明：
- 列出修改文件、关键函数、性能预期收益、潜在风险
```

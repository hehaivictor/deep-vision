# DeepVision 访谈—报告试点证据包实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 基于 DeepVision 仓库中的真实会话、报告和运行记录，生成适用于内部立项、阶段评审和项目验收的 Markdown 与 Word 证据包。

**架构：** 先将系统事实提取为结构化来源清单，再编写带真实性标签的综合证据报告。实施前基线和人员意见采用保守拟稿，并明确标注「待确认」或「待签署」。最后生成 Word 文档，通过内容核对、Office 文件完整性检查和页面渲染检查验证交付质量。

**技术栈：** Markdown、JSON、`jq`、Python 3、bundled workspace document runtime、Word `.docx`

---

## 文件结构

- 创建：`artifacts/review-materials/deepvision-evidence-package/evidence-source-summary.json`，保存系统侧事实和来源文件映射。
- 创建：`artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.md`，作为正式材料的可编辑原稿。
- 创建：`artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.docx`，作为可打印、可签署版本。
- 创建：`artifacts/review-materials/deepvision-evidence-package/rendered/`，保存 Word 渲染校验页，仅用于交付检查。
- 修改：`docs/superpowers/plans/2026-08-07-deepvision-evidence-package.md`，执行时逐项勾选完成状态。

### 任务 1：提取并校验系统侧证据

**文件：**

- 创建：`artifacts/review-materials/deepvision-evidence-package/evidence-source-summary.json`
- 读取：`data/sessions/dv-20260422092510-4ed2fe2a.json`
- 读取：`data/sessions/dv-20260403213643-d9071273.json`
- 读取：`data/sessions/dv-20260309111722-49d054db.json`
- 读取：`data/sessions/dv-20260305004312-de77f5e0.json`
- 读取：`data/reports/*.md`
- 读取：`data/operations/real-report-runtime-benchmark-*.json`

- [ ] **步骤 1：提取 4 个案例的系统字段**

提取会话编号、主题、状态、创建时间、更新时间、问题数量、参考资料数量、对应报告文件、报告编号、报告生成时间和报告输出版本数。

```bash
for file in \
  data/sessions/dv-20260422092510-4ed2fe2a.json \
  data/sessions/dv-20260403213643-d9071273.json \
  data/sessions/dv-20260309111722-49d054db.json \
  data/sessions/dv-20260305004312-de77f5e0.json; do
  jq '{session_id,topic,status,created_at,updated_at,question_count:(.interview_log|length),reference_count:(.reference_materials|length)}' "$file"
done
```

预期：输出 4 条合法 JSON，问题数量分别为 21、16、34、31。

- [ ] **步骤 2：提取真实报告生成耗时**

从包含 `status.runtime_timings.total_ms` 的基准文件中提取成功记录，报告中呈现最小值、中位数、最大值和样本数，不将测试执行器耗时当作业务报告生成耗时。

```bash
jq -s '[.[] | select(.status.state == "completed" and .status.runtime_timings.total_ms != null) | .status.runtime_timings.total_ms] | {count:length,min_ms:min,max_ms:max,sorted:sort}' data/operations/real-report-runtime-benchmark-*.json
```

预期：`count` 大于等于 4，`min_ms` 和 `max_ms` 均大于 0。

- [ ] **步骤 3：生成来源清单**

使用 `date` 生成 ISO 8601 时间。`cases` 包含 4 条记录；`limitations` 说明文件时间不等于人工投入、报告版本数不等于人工返工次数、跨日会话不进入快速周期均值。

```bash
generated_at=$(date '+%Y-%m-%dT%H:%M:%S%z')
jq -n --arg generated_at "$generated_at" '{schema_version:1,generated_at:$generated_at,truth_labels:["已核验","待确认","待签署"],cases:[],runtime_benchmarks:{},limitations:[]}'
```

- [ ] **步骤 4：校验来源清单**

```bash
jq -e '.schema_version == 1 and (.cases|length) == 4 and (.truth_labels|length) == 3 and (.limitations|length) >= 3' artifacts/review-materials/deepvision-evidence-package/evidence-source-summary.json
```

预期：退出码为 0，输出 `true`。

- [ ] **步骤 5：提交来源清单**

```bash
git add artifacts/review-materials/deepvision-evidence-package/evidence-source-summary.json
VERSION_SKIP=1 git commit -m "docs(评审材料): 整理试点系统证据来源" -m "数据：汇总四个真实会话与报告文件映射。\n数据：统计真实报告生成耗时并记录使用限制。"
```

### 任务 2：编写综合证据报告

**文件：**

- 创建：`artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.md`
- 读取：`artifacts/review-materials/deepvision-evidence-package/evidence-source-summary.json`
- 读取：`docs/superpowers/specs/2026-08-07-deepvision-evidence-package-design.md`

- [ ] **步骤 1：建立报告骨架**

正文依次包含：材料说明、执行摘要、项目背景、问题证据、影响证据、成因证据、实施前基线、试点案例、实施前后对比、试用反馈、阶段评审结论、风险限制、下一阶段建议、证据索引和 7 份附件。

- [ ] **步骤 2：填写实施前回溯基线**

使用 5 个匿名历史任务，人工投入分别为 8.5、10.0、9.0、11.0、8.0 小时，人工修改轮次分别为 2、3、2、3、2 次。所有相关单元格和结论标注「待确认」。

预期汇总：平均人工投入 9.3 小时，平均修改轮次 2.4 次。

- [ ] **步骤 3：填写 4 个真实试点案例**

系统字段直接来自来源清单。人员字段采用以下保守建议值，并在表头和脚注标明待确认：

| 案例 | 人工投入 | 人工修改 | 可用性 | 采纳 |
|---|---:|---:|---:|---|
| 智能访谈智能体需求调研 | 3.5 小时 | 1 次 | 4.3 分 | 修改后采纳 |
| 机加工艺生成智能产品调研 | 4.8 小时 | 2 次 | 3.8 分 | 有条件采纳 |
| 用户反馈 | 4.2 小时 | 1 次 | 4.1 分 | 修改后采纳 |
| 交互式访谈产品需求调研 | 3.9 小时 | 1 次 | 4.2 分 | 修改后采纳 |

预期汇总：平均人工投入 4.1 小时，较基线下降约 55.9%；平均修改轮次 1.3 次，下降约 47.9%；平均可用性 4.1 分；4 个案例均达到「有条件采纳」及以上。

- [ ] **步骤 4：编写 3 份人员访谈确认稿**

角色为项目负责人、产品负责人、交付或使用代表。每份纪要包含访谈目的、事实陈述、影响判断、成因判断、试点意见、异议栏、确认方式、签字和日期。内容使用「建议确认表述」，不得写成已经签署。

- [ ] **步骤 5：编写评审和验收附件**

阶段评审纪要采用「建议继续试点并补充规模化验证」结论。验收意见设置「通过」「有条件通过」「不通过」复选项，默认建议为「有条件通过」，但不得预先勾选或代签。

- [ ] **步骤 6：执行内容自检**

```bash
file='artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.md'
test -s "$file"
rg -n '已核验|待确认|待签署|9\.3 小时|4\.1 小时|55\.9%|47\.9%|项目负责人|产品负责人|交付或使用代表|有条件通过' "$file"
! rg -n '已经签字|一致确认无误|100%提升|完全替代人工' "$file"
git diff --check -- "$file"
```

预期：正向关键词均存在，禁止性措辞无匹配，差异检查无错误。

- [ ] **步骤 7：提交 Markdown 报告**

```bash
git add artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.md
VERSION_SKIP=1 git commit -m "docs(评审材料): 编写访谈报告试点证据包" -m "材料：补充问题、影响、成因和实施前基线。\n材料：整理四个试点案例与三份人员确认稿。\n材料：增加阶段评审、验收意见和证据索引。"
```

### 任务 3：生成并验证 Word 文档

**文件：**

- 创建：`artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.docx`
- 创建：`artifacts/review-materials/deepvision-evidence-package/rendered/`
- 读取：`artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.md`

- [ ] **步骤 1：加载文档运行环境并阅读文档技能**

调用工作区依赖加载入口，确认 Python、`python-docx`、Office/PDF 渲染工具路径；完整阅读 documents 技能后，按其字体和渲染要求生成文档。

- [ ] **步骤 2：生成 Word 文档**

采用 A4 纵向、中文正文、自动页码、标题层级、重复表头和签字留白。封面标注「内部立项 / 阶段评审 / 项目验收」和「拟稿，需完成签字确认后生效」。

- [ ] **步骤 3：验证 Office 文件结构**

```bash
python3 -c "from docx import Document; p='artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.docx'; d=Document(p); assert len(d.paragraphs)>80; assert len(d.tables)>=8; print(len(d.paragraphs), len(d.tables))"
unzip -t artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.docx
```

预期：段落数大于 80、表格数不少于 8，`unzip` 输出无错误。

- [ ] **步骤 4：渲染并检查页面**

将 `.docx` 渲染为 PDF 或逐页图片，输出到 `rendered/`。检查封面、首个正文页、宽表格页和签字页；不得存在文字截断、表格越界、孤立标题或签字栏丢失。

- [ ] **步骤 5：核对 Markdown 与 Word 数据一致性**

从 Word 提取文本，核对 `9.3 小时`、`4.1 小时`、`55.9%`、`47.9%`、`4.1 分`、4 个会话编号和 3 个确认角色均存在且与 Markdown 一致。

- [ ] **步骤 6：提交 Word 文档**

```bash
git add artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.docx
VERSION_SKIP=1 git commit -m "docs(评审材料): 生成可签署试点证据文档" -m "文档：生成适用于评审和验收的 Word 版本。\n验证：完成结构、内容一致性和页面渲染检查。"
```

### 任务 4：执行最终证据审计

**文件：**

- 验证：`artifacts/review-materials/deepvision-evidence-package/evidence-source-summary.json`
- 验证：`artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.md`
- 验证：`artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.docx`

- [ ] **步骤 1：核对交付文件**

```bash
test -s artifacts/review-materials/deepvision-evidence-package/evidence-source-summary.json
test -s artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.md
test -s artifacts/review-materials/deepvision-evidence-package/DeepVision-访谈报告试点证据包.docx
```

预期：3 个文件均存在且非空。

- [ ] **步骤 2：核对证据数量与结论边界**

确认包含 3 份人员确认稿、4 个真实任务、5 条实施前基线、1 份试用反馈、1 份阶段评审纪要和 1 份验收意见表。签字、确认日期和人工投入值保持待确认状态。

- [ ] **步骤 3：核对 Git 改动范围**

```bash
git status --short
git log -4 --oneline --stat
```

预期：没有与本证据包无关的改动；提交只涉及规格、计划和证据包交付文件。

- [ ] **步骤 4：形成交付说明**

明确说明哪些内容来自真实系统记录、哪些数字需要人员确认、哪些附件需要签字后才能成为正式验收证据。不得将拟稿描述为已经完成验收。

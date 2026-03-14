# 样例页复刻式方案页重构规格

## 1. 结论

当前方案页的问题不是“内容还不够精炼”，而是**页面母版本身就不对**。

`fortune-trend.ivheli.com` 这个样例页不是一个“报告可视化页面”，而是一个**高级售前提案母版**。  
它的强项在于：

- 页面结构固定，不交给 AI 动态决定
- 每一章都有明确说服任务
- 不同章节使用不同的信息表达器
- Hero、对比、业务板块、系统集成、知识沉淀、数据联动、价值收束是一条连续叙事链

当前 DeepVision 方案页虽然已经从“结构化字段拼装页”升级成了“提案页骨架”，但仍然不是样例页这个级别。差距不在 10%，而是在**产品形态和实现策略**上。

因此，建议明确切换方向：

**不再继续优化通用提案页，而是直接按样例页做一套“高保真母版复刻版方案页”。**

唯一变化：

- 样例页的业务内容改成基于访谈报告自动生成
- 页面骨架、设计系统、交互节奏、信息器种类，尽量向样例页对齐


## 2. 样例页拆解

### 2.1 样例页的真实结构

从上到下，它不是 8 个普通 section，而是一条提案说服链：

1. `方案概览`
2. `系统对比`
3. `落地方案`
4. `系统集成`
5. `知识统一`
6. `数据联动`
7. `预期价值`
8. `为什么适合`

这 8 章不是目录，而是：

- 先立论
- 再论证
- 再展开实施方案
- 再解释系统如何运行
- 再说明为什么值得投
- 最后收束决策

### 2.2 样例页的核心表达器

样例页不是“卡片反复堆叠”，而是有明确的专属表达器：

- Hero 大标题 + 指标墙
- 双塔对比
- 可切换业务 tabs
- 业务能力卡矩阵
- 左右系统联动示意
- 困境 vs 统一方案
- 知识沉淀链路
- 跨系统大图 + 编号讲解
- 价值指标宫格
- 适配性理由卡

### 2.3 样例页真正高级的原因

不是颜色，也不是动画，而是：

- 每屏都有单一论点
- 文字高度压缩
- 图解承担大量说明任务
- 内容密度高但阅读节奏很顺
- 页面像“提案”，不是“系统输出”


## 3. 当前方案页与样例页的差距

### 3.1 结构层差距

当前方案页：

- 仍然保留通用提案引擎思路
- 章节结构虽有 8 章，但更像泛化模板
- 章节的视觉表达仍然偏统一 renderer

样例页：

- 是一个固定母版
- 章节顺序和章节任务极其稳定
- 不依赖通用 renderer 做所有事情

### 3.2 页面表现层差距

当前方案页：

- 还是“深色 + 卡片 + 若干图解”
- 信息器类型不够多
- tabs、对比、系统集成、知识沉淀、跨域联动做得不够重

样例页：

- 不同章节几乎都有独特版式
- 同一个页面里包含至少 7 种不同信息器
- 有明显的售前方案气质

### 3.3 交互层差距

当前方案页：

- sticky 导航有了
- 证据抽屉有了
- tabs 和部分图解有了

但还缺：

- Hero CTA 的自然引导
- 对比区的展开折叠
- 业务板块 tabs 的强存在感
- 大图联动区的解释式交互
- 章节间更明显的滚动节奏

### 3.4 内容引擎与母版耦合方式差距

当前方案页：

- 先生成 `proposal_brief / chapter_copy`
- 再用一套通用章节 renderer 渲染

样例页更像：

- 先定义一套固定母版
- 再把内容填进母版槽位

这两个方向差别很大。


## 4. 目标形态

新的方案页不应再是“通用提案页”。

目标应是：

**样例页母版复刻版 + AI 内容填槽**

即：

- 页面骨架固定
- 交互固定
- 样式系统固定
- 图解类型固定
- AI 只负责填充内容

### 4.1 新链路

建议把方案生成链路改成：

`访谈报告 -> sample_page_content_model -> sample_page_slots -> 固定母版渲染`

不再用：

`访谈报告 -> proposal_brief -> chapter_copy -> 通用提案页`

`proposal_brief / chapter_copy` 可以继续保留，但不再直接作为页面层协议，而是作为中间素材。


## 5. 新页面母版

### 5.1 固定章节

#### A. 方案概览

对应样例页 Hero。

必须包含：

- `eyebrow`
- `title`
- `subtitle`
- `4 个核心卖点`
- `4 个指标卡`
- `主 CTA`

#### B. 路径对比

对应样例页“系统定位与协同”。

必须包含：

- `方案 A`
- `方案 B`
- `对比结论`
- `一个类比块`
- `3-4 个协同场景`

#### C. 核心落地方案

对应样例页“三大业务板块落地方案”。

必须包含：

- `3 个主 workstreams`
- `顶部 tabs`
- `每个 workstream 下 3-6 个能力卡`
- `配套收益指标`

#### D. 系统集成

对应样例页“企业微信 + ERP/CRM 全面打通”。

必须包含：

- `入口侧场景`
- `系统侧场景`
- `分阶段接入路径`

#### E. 知识统一

对应样例页“终结多平台并存的混乱”。

必须包含：

- `当前困境`
- `统一方案`
- `知识中枢分层`
- `自增强机制`

#### F. 数据联动

对应样例页“三大板块如何相互促进”。

必须包含：

- `一张大图`
- `4 条跨模块联动解释`

#### G. 预期价值

对应样例页“量化预期效果”。

必须包含：

- `6 个大指标`
- `可选展开详细价值说明`

#### H. 为什么适合

对应样例页“为什么这套方案尤其合适”。

必须包含：

- `4-6 个适配理由`
- `最终收束文案`


## 6. 数据槽位映射

建议新增一个新的页面协议：`sample_page_slots_v1`

### 6.1 顶层结构

```json
{
  "hero": {},
  "comparison": {},
  "solution_tabs": [],
  "integration": {},
  "knowledge_hub": {},
  "cross_domain_flywheel": {},
  "value_summary": {},
  "fit_reasons": {},
  "evidence": {}
}
```

### 6.2 各章节槽位

#### hero

```json
{
  "eyebrow": "",
  "title": "",
  "subtitle": "",
  "proof_points": [],
  "metrics": [],
  "cta": { "label": "", "target": "comparison" }
}
```

来源：

- `proposal_brief.thesis`
- `proposal_brief.value_model`
- `proposal_brief.fit_reasons`

#### comparison

```json
{
  "section_label": "路径对比",
  "title": "",
  "summary": "",
  "left_option": {},
  "right_option": {},
  "positioning_chip": {},
  "analogy": {
    "title": "",
    "body": ""
  },
  "synergy_cases": []
}
```

来源：

- `proposal_brief.options`
- `proposal_brief.recommended_solution`

#### solution_tabs

```json
{
  "id": "",
  "tab_label": "",
  "headline": "",
  "summary": "",
  "capability_cards": [],
  "expected_metrics": []
}
```

来源：

- `proposal_brief.workstreams`
- `proposal_brief.recommended_solution.modules`
- `proposal_brief.value_model`

#### integration

```json
{
  "title": "",
  "left_stack": [],
  "right_stack": [],
  "phase_path": []
}
```

来源：

- `recommended_solution.integration_points`
- `recommended_solution.dataflow`
- `next_steps`

#### knowledge_hub

```json
{
  "pain_points": [],
  "unified_solution_points": [],
  "knowledge_layers": [],
  "reinforcement_loop": []
}
```

来源：

- `context.current_state`
- `fit_reasons`
- `recommended_solution.governance`
- `next_steps`

#### cross_domain_flywheel

```json
{
  "diagram_nodes": [],
  "diagram_links": [],
  "interaction_cases": []
}
```

来源：

- `recommended_solution.integration_points`
- `recommended_solution.dataflow`
- `workstreams`

#### value_summary

```json
{
  "metrics": [],
  "detail_groups": []
}
```

来源：

- `value_model`

#### fit_reasons

```json
{
  "cards": [],
  "closing_statement": []
}
```

来源：

- `fit_reasons`
- `risks_and_boundaries`
- `thesis`


## 7. 前端重构建议

### 7.1 当前文件

- [web/solution.html](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.html)
- [web/solution.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.js)
- [web/solution.css](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/solution.css)

### 7.2 不建议继续的方向

不要继续在 `solutionRenderProposalSections()` 上加更多 layout 分支。  
这样只会把当前方案页变成更复杂的通用 renderer，仍然达不到样例页的完成度。

### 7.3 建议的重构方向

将当前提案页 renderer 拆成固定母版组件：

```text
renderSampleProposalPage()
  renderSampleTopNav()
  renderSampleHero()
  renderSampleComparison()
  renderSampleSolutionTabs()
  renderSampleIntegration()
  renderSampleKnowledgeHub()
  renderSampleCrossDomainFlywheel()
  renderSampleValueSummary()
  renderSampleFitReasons()
  bindSampleInteractions()
```

### 7.4 需要新建的核心组件

- `renderSampleHero`
- `renderSampleComparison`
- `renderSampleSolutionTabs`
- `renderSampleIntegration`
- `renderSampleKnowledgeHub`
- `renderSampleCrossDomainFlywheel`
- `renderSampleValueSummary`
- `renderSampleFitReasons`

### 7.5 交互要求

- 顶部 sticky 导航
- Hero CTA 平滑跳转
- 对比区折叠展开
- 落地方案 tabs 切换
- 价值区明细折叠
- 证据抽屉保留
- 图解区 hover 高亮
- 滚动中章节高亮


## 8. 视觉重构建议

### 8.1 允许对标样例的部分

- 整体页面节奏
- Hero 结构
- 章节分组方式
- 深色商务基调
- tabs 的表现方式
- 指标墙
- 系统图表达
- 价值区收束方式

### 8.2 不建议直接复制的部分

- 样例里的具体业务图标
- 样例里的行业术语
- 样例里的企业场景内容
- 具体文案

### 8.3 新设计系统建议

建议新的视觉方向：

- 背景：深海军蓝渐变
- 强调色：青蓝 + 暖金
- 标题：高张力衬线或编辑感黑体
- 正文：克制、低密度
- 卡片：玻璃质感弱化，重点转向结构与留白
- 图解：线框 + 轻发光，不做花哨特效

### 8.4 当前页面的视觉问题

- 卡片太多，层级感弱
- 虽然深色，但还不够“编辑式”
- 图解存在，但分量不够
- 缺少样例页那种明显的“大章节点感”
- 对比区和系统集成区视觉说服力弱


## 9. 后端重构建议

### 9.1 当前后端问题

现在后端产出：

- `proposal_brief`
- `chapter_copy`
- `proposal_page`

这仍然是“通用提案页协议”。

### 9.2 建议的新协议

新增：

- `sample_page_content_model`
- `sample_page_slots_v1`

其中：

- `content_model` 负责抽象业务内容
- `slots` 负责映射到样例页母版

### 9.3 AI 的职责

AI 只负责：

- 生成标题与判断
- 生成对比结论
- 生成业务板块内容
- 生成系统集成说明
- 生成知识统一与数据联动文案
- 生成价值指标与适配理由
- 生成图解节点数据

AI 不再负责：

- 决定页面结构
- 决定章节顺序
- 决定 layout 类型


## 10. 重构实施顺序

### Phase 1：固定母版

- 定义 `sample_page_slots_v1`
- 固定 8 大章节
- 固定所有章节组件

### Phase 2：样例页 UI 复刻

- 重写 `solution.html`
- 重写 `solution.css`
- 重写 `solution.js`
- 用静态 mock 先把样例页结构做出来

### Phase 3：后端槽位输出

- 新增 `build_sample_page_content_model()`
- 新增 `build_sample_page_slots()`
- 前端改为优先消费 `sample_page_slots_v1`

### Phase 4：AI 内容增强

- 再把 AI prompt 升级成“样例页内容填槽模式”
- 图解、指标、对比、适配理由全部按母版输出


## 11. 一句话建议

如果目标就是你给的这个样例页级别，那么正确路线不是：

- 继续优化当前通用提案页

而是：

- **直接以样例页为母版，重建一套固定架构的高保真方案页系统**

DeepVision 负责的不是“设计新的页面类型”，而是：

- 把访谈报告自动填进这套高级提案母版里。


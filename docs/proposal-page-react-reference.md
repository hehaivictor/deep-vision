# 提案型方案页参考实现

本文档提供两部分内容：

1. `ProposalPageData` 的完整 mock 示例
2. React 组件树、类型定义与页面骨架代码

说明：
- 当前仓库前端栈是原生 HTML + JS，不是 React。
- 本文档中的 React 代码用于明确页面协议、数据结构和组件边界。
- 如果继续在当前仓库实现，建议先按这里的数据协议拆分 `web/solution.js` 的渲染函数。

## 1. ProposalPageData Mock

下面这份 mock 以“交易支付环节风控体验研究”的访谈报告为例，目标页面风格是 `executive_dark_editorial`。

```ts
export const proposalPageMock = {
  meta: {
    topic: "交易支付风控体验优化方案",
    theme: "executive_dark_editorial",
    audience: "decision_maker",
  },
  chapters: [
    {
      id: "hero",
      navLabel: "方案判断",
      eyebrow: "交互式访谈洞察提案",
      title: "先把高价值用户招募与访谈触发做准，再谈深层归因模型",
      judgement: "当前最大瓶颈不是缺少研究工具，而是缺少稳定命中真实高价值样本的触发与执行体系。",
      summary: "如果继续沿用泛流量招募和静态问卷，最终只能得到表层归因。应优先搭建高价值样本识别、延时触发和混合复现三件基础能力。",
      layout: "hero_metrics",
      metrics: [
        {
          label: "首轮核心突破口",
          value: "真实被拦截用户招募",
          delta: "P0",
          note: "先解决样本真实性，再提高洞察深度",
        },
        {
          label: "建议试点周期",
          value: "8周",
          delta: "MVP",
          note: "2周招募与方案冻结，4周访谈执行，2周沉淀优化方案",
        },
        {
          label: "优先聚焦场景",
          value: "支付失败 / 拦截页",
          delta: "高信号入口",
          note: "最接近真实恐慌决策瞬间",
        },
        {
          label: "核心研究目标",
          value: "还原放弃支付决策链",
          delta: "深层动机",
          note: "定位为何放弃支付而非申诉",
        },
      ],
      cards: [
        {
          title: "先解决样本真实性",
          desc: "没有真实被拦截用户，后续所有归因都容易失真。",
          tag: "前置条件",
          meta: "招募策略",
        },
        {
          title: "把访谈触发嵌入真实场景",
          desc: "支付拦截后的短时窗口更接近真实情绪和决策。",
          tag: "关键动作",
          meta: "触发机制",
        },
      ],
      diagram: null,
      cta: {
        label: "查看实施路径",
        target: "roadmap",
      },
      evidenceRefs: ["2.1", "5", "6", "7"],
    },
    {
      id: "why_now",
      navLabel: "为什么现在做",
      eyebrow: "业务矛盾与现实约束",
      title: "研究目标已经明确，但执行链路还不足以支撑深层心理洞察",
      judgement: "当前矛盾不在于是否需要研究，而在于现有招募、触发、复现和合规能力无法同时成立。",
      summary: "客户已经明确要研究误拦截后的替代决策，但若触发点不准、样本不真、执行链路不稳，最后仍只会得到模糊反馈。",
      layout: "conflict_cards",
      metrics: [],
      cards: [
        {
          title: "目标很深，但样本入口很浅",
          desc: "要研究恐慌与信任崩塌，却还没有稳定锁定真实高价值用户的入口。",
          tag: "核心矛盾",
          meta: "招募",
        },
        {
          title: "需要真实，还要兼顾体验",
          desc: "过早触发会打断用户，过晚触发又会丢失真实情绪。",
          tag: "体验矛盾",
          meta: "触发",
        },
        {
          title: "需要深度复现，但技术与成本受限",
          desc: "高保真模拟昂贵，低保真又可能损失关键感知细节。",
          tag: "实现约束",
          meta: "复现",
        },
        {
          title: "支付场景天然有合规压力",
          desc: "任何方案都必须先满足脱敏、留痕和合规评审。",
          tag: "不可绕过",
          meta: "合规",
        },
      ],
      diagram: null,
      cta: {
        label: "看路径对比",
        target: "comparison",
      },
      evidenceRefs: ["1.2", "2.1", "3.1", "6"],
    },
    {
      id: "comparison",
      navLabel: "路径对比",
      eyebrow: "方案取舍",
      title: "不是选最重方案，而是选最能验证真实决策链的方案",
      judgement: "推荐先走“高质量招募 + 延时触发 + 混合复现”的中等投入路径，而不是直接上全量高保真系统。",
      summary: "保守路径拿不到深层决策，激进路径成本和风险过高。最优策略是先用中等成本拿到高价值真实样本与决策链，再决定是否扩展。",
      layout: "dual_comparison",
      metrics: [],
      cards: [
        {
          title: "保守路径：泛招募 + 静态问卷",
          desc: "成本低、启动快，但只能得到表层反馈，无法解释放弃支付背后的真实心理链路。",
          tag: "不推荐",
          meta: "低成本 / 低洞察",
        },
        {
          title: "推荐路径：精准招募 + 延时触发 + 混合复现",
          desc: "优先保证样本真实性和关键场景还原度，在成本、合规、深度之间取得平衡。",
          tag: "推荐",
          meta: "中成本 / 高信号",
        },
        {
          title: "激进路径：全量高保真重建",
          desc: "理论上洞察最完整，但开发成本、合规负担和试点周期都显著拉长。",
          tag: "备选",
          meta: "高成本 / 高风险",
        },
      ],
      diagram: null,
      cta: {
        label: "查看推荐蓝图",
        target: "blueprint",
      },
      evidenceRefs: ["2.1", "5.1", "6", "7"],
    },
    {
      id: "blueprint",
      navLabel: "推荐蓝图",
      eyebrow: "方案结构",
      title: "用四层能力把研究从“采样”推进到“可验证归因”",
      judgement: "推荐方案不是一个工具，而是一套从招募、触发、复现到洞察沉淀的连续能力链。",
      summary: "先把高价值用户招进来，再在高信号时刻触发访谈，用混合复现补足细节，最后把结论沉淀为可复用的归因资产。",
      layout: "blueprint_diagram",
      metrics: [],
      cards: [
        {
          title: "样本识别层",
          desc: "锁定真实被拦截用户，过滤掉噪声样本。",
          tag: "Layer 1",
          meta: "招募",
        },
        {
          title: "触发策略层",
          desc: "在用户情绪和决策仍新鲜时触发深访，不打断核心业务动作。",
          tag: "Layer 2",
          meta: "触发",
        },
        {
          title: "复现洞察层",
          desc: "用低保真到高保真的混合复现，提取真实决策变量。",
          tag: "Layer 3",
          meta: "复现",
        },
        {
          title: "归因资产层",
          desc: "把访谈结果沉淀为后续设计、风控和客服可复用的知识资产。",
          tag: "Layer 4",
          meta: "沉淀",
        },
      ],
      diagram: {
        type: "architecture",
        nodes: [
          { id: "recruit", label: "精准招募", group: "source" },
          { id: "trigger", label: "延时触发", group: "logic" },
          { id: "replay", label: "混合复现", group: "logic" },
          { id: "insight", label: "心理归因洞察", group: "output" },
          { id: "asset", label: "设计 / 风控 / 客服知识资产", group: "output" },
        ],
        edges: [
          { from: "recruit", to: "trigger", label: "命中真实样本" },
          { from: "trigger", to: "replay", label: "进入高信号访谈" },
          { from: "replay", to: "insight", label: "还原决策链" },
          { from: "insight", to: "asset", label: "沉淀可复用结论" },
        ],
        caption: "从样本真实性到归因资产沉淀的连续能力链",
      },
      cta: {
        label: "展开关键模块",
        target: "workstreams",
      },
      evidenceRefs: ["5.1", "5.2", "7"],
    },
    {
      id: "workstreams",
      navLabel: "关键模块",
      eyebrow: "落地工作流",
      title: "先打通三条工作流，方案才能从概念进入执行",
      judgement: "真正决定成败的不是单点功能，而是招募、执行、合规三条工作流是否同时跑通。",
      summary: "建议首期聚焦三条工作流：高价值样本招募、访谈执行机制、隐私合规底座。每条工作流都要有明确交付物和验收信号。",
      layout: "tabbed_cards",
      metrics: [],
      cards: [
        {
          title: "高价值样本招募",
          desc: "围绕支付失败页、拦截页和客服邀约建立真实样本入口。",
          tag: "P0",
          meta: "交付物：招募渠道清单、真实性筛选规则、首批样本池",
        },
        {
          title: "访谈触发与混合复现",
          desc: "设计延时分流、低保真原型和录屏回溯的混合执行机制。",
          tag: "P0",
          meta: "交付物：触发规则、复现原型、执行 SOP",
        },
        {
          title: "隐私计算与合规留痕",
          desc: "把脱敏、权限和审计能力前置进方案底层。",
          tag: "P1",
          meta: "交付物：脱敏规则、合规评审结论、审计接口设计",
        },
        {
          title: "归因模型与洞察沉淀",
          desc: "把分散访谈结果转成可复盘、可复用的归因资产。",
          tag: "P1",
          meta: "交付物：归因标签体系、洞察模板、案例资产库",
        },
      ],
      diagram: null,
      cta: {
        label: "查看系统闭环",
        target: "integration",
      },
      evidenceRefs: ["2.1", "5.1", "6", "7"],
    },
    {
      id: "integration",
      navLabel: "系统闭环",
      eyebrow: "流程与沉淀",
      title: "让招募、执行、分析和沉淀形成闭环，而不是一次性项目",
      judgement: "如果结果不能回流到设计、风控和客服体系，访谈只能形成一次性报告，无法变成长期能力。",
      summary: "方案应把入口、执行、分析和沉淀连成一条闭环，让每次访谈都增强下一次研究和后续设计迭代。",
      layout: "loop_diagram",
      metrics: [],
      cards: [
        {
          title: "入口侧",
          desc: "支付失败页、拦截页、客服邀约共同提供真实样本来源。",
          tag: "Source",
          meta: "样本进入",
        },
        {
          title: "执行侧",
          desc: "触发策略和复现机制保证采样时机与访谈质量。",
          tag: "Execution",
          meta: "访谈进行",
        },
        {
          title: "分析侧",
          desc: "归因标签、情绪信号和视觉误导因素统一收口。",
          tag: "Analysis",
          meta: "结构化洞察",
        },
        {
          title: "沉淀侧",
          desc: "把结论反馈给设计、风控和客服体系，形成长期资产。",
          tag: "Loop",
          meta: "组织复利",
        },
      ],
      diagram: {
        type: "loop",
        nodes: [
          { id: "entry", label: "真实入口", group: "loop" },
          { id: "session", label: "触发与访谈", group: "loop" },
          { id: "analysis", label: "归因分析", group: "loop" },
          { id: "reuse", label: "设计 / 风控 / 客服回流", group: "loop" },
        ],
        edges: [
          { from: "entry", to: "session", label: "命中高价值样本" },
          { from: "session", to: "analysis", label: "形成结构化观察" },
          { from: "analysis", to: "reuse", label: "输出决策建议" },
          { from: "reuse", to: "entry", label: "迭代入口与策略" },
        ],
        caption: "访谈项目必须从一次性执行升级为持续增强机制",
      },
      cta: {
        label: "查看实施节奏",
        target: "roadmap",
      },
      evidenceRefs: ["3", "5", "7"],
    },
    {
      id: "roadmap",
      navLabel: "实施路径",
      eyebrow: "推进节奏",
      title: "用 8 周完成从样本入口到首轮洞察输出的闭环试点",
      judgement: "先做闭环试点，再决定是否扩大技术投入，比一开始追求全量能力更稳健。",
      summary: "建议按三阶段推进：先冻结招募与合规方案，再完成执行与洞察试点，最后沉淀优化方案和扩展决策。",
      layout: "phased_timeline",
      metrics: [],
      cards: [
        {
          title: "Phase 1｜第1-2周",
          desc: "完成招募渠道确认、技术方案冻结和合规评审。",
          tag: "准备阶段",
          meta: "里程碑：招募入口就绪，技术边界确定",
        },
        {
          title: "Phase 2｜第3-6周",
          desc: "启动试点招募，执行首轮深度访谈，验证混合复现机制。",
          tag: "执行阶段",
          meta: "里程碑：形成首批有效样本与结构化洞察",
        },
        {
          title: "Phase 3｜第7-8周",
          desc: "输出风控交互优化方案 V1，完成评审与扩展建议。",
          tag: "收束阶段",
          meta: "里程碑：形成可评审的优化方案和后续路线",
        },
      ],
      diagram: {
        type: "timeline",
        nodes: [
          { id: "p1", label: "准备", group: "phase" },
          { id: "p2", label: "执行", group: "phase" },
          { id: "p3", label: "收束", group: "phase" },
        ],
        edges: [
          { from: "p1", to: "p2", label: "入口与合规就绪" },
          { from: "p2", to: "p3", label: "首轮洞察形成" },
        ],
        caption: "先闭环试点，再判断是否扩大投入",
      },
      cta: {
        label: "查看预期价值",
        target: "value_fit",
      },
      evidenceRefs: ["7"],
    },
    {
      id: "value_fit",
      navLabel: "预期价值",
      eyebrow: "价值与边界",
      title: "这套方案适合当前项目，因为它优先解决最容易失真的三个关键点",
      judgement: "最适合当前项目的不是最重的系统，而是最先解决样本真实性、场景触发和洞察沉淀的方案。",
      summary: "该方案能在有限周期内优先拿到高质量洞察，并且为后续设计、风控和客服优化建立可复用资产，但前提是招募入口和合规评审能按期完成。",
      layout: "value_grid",
      metrics: [
        {
          label: "高价值样本命中率",
          value: "显著提升",
          delta: "相对泛招募",
          note: "通过支付失败页、拦截页和筛选问卷提高真实性",
        },
        {
          label: "首轮洞察有效性",
          value: "更接近真实决策链",
          delta: "从表层反馈升级",
          note: "延时触发 + 混合复现帮助保留关键心理变量",
        },
        {
          label: "后续复用价值",
          value: "设计 / 风控 / 客服共享",
          delta: "资产化",
          note: "访谈结论可回流为归因知识资产",
        },
        {
          label: "投入控制",
          value: "中等成本",
          delta: "先试点后扩展",
          note: "避免一开始进入高保真重建",
        },
      ],
      cards: [
        {
          title: "为什么适合当前客户",
          desc: "项目目标高度聚焦，且已经明确需要深层心理归因，适合先做高质量试点。",
          tag: "适配理由",
          meta: "目标明确",
        },
        {
          title: "为什么适合当前场景",
          desc: "支付拦截是强情绪、高风险、可观察的关键节点，研究价值远高于普通满意度回访。",
          tag: "适配理由",
          meta: "场景高信号",
        },
        {
          title: "主要边界",
          desc: "如果无法稳定获得真实被拦截用户样本，后续方案质量会显著下降。",
          tag: "边界",
          meta: "样本前提",
        },
        {
          title: "主要风险",
          desc: "合规评审和触发体验控制不到位，会直接影响项目推进节奏和用户感受。",
          tag: "风险",
          meta: "合规与体验",
        },
      ],
      diagram: null,
      cta: {
        label: "返回顶部",
        target: "hero",
      },
      evidenceRefs: ["1.2", "2.1", "6", "7"],
    },
  ],
} as const;
```

## 2. React 类型定义

```ts
export type ChapterLayout =
  | "hero_metrics"
  | "conflict_cards"
  | "dual_comparison"
  | "blueprint_diagram"
  | "tabbed_cards"
  | "loop_diagram"
  | "phased_timeline"
  | "value_grid";

export interface ChapterMetric {
  label: string;
  value: string;
  delta?: string;
  note?: string;
}

export interface ChapterCard {
  title: string;
  desc: string;
  tag?: string;
  meta?: string;
}

export interface DiagramNode {
  id: string;
  label: string;
  group?: string;
}

export interface DiagramEdge {
  from: string;
  to: string;
  label?: string;
}

export interface ChapterDiagram {
  type: "architecture" | "flow" | "loop" | "timeline";
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  caption?: string;
}

export interface ChapterCTA {
  label: string;
  target: string;
}

export interface ProposalChapter {
  id: string;
  navLabel: string;
  eyebrow: string;
  title: string;
  judgement: string;
  summary: string;
  layout: ChapterLayout;
  metrics: ChapterMetric[];
  cards: ChapterCard[];
  diagram?: ChapterDiagram | null;
  cta?: ChapterCTA | null;
  evidenceRefs: string[];
}

export interface ProposalPageData {
  meta: {
    topic: string;
    theme: "executive_dark_editorial";
    audience: string;
  };
  chapters: ProposalChapter[];
}
```

## 3. React 组件树

```tsx
<ProposalPage data={proposalPageMock}>
  <StickyProposalNav />
  <HeroJudgementSection />
  <WhyNowSection />
  <OptionsComparisonSection />
  <RecommendedBlueprintSection />
  <WorkstreamsSection />
  <IntegrationLoopSection />
  <RoadmapSection />
  <ValueAndFitSection />
  <EvidenceDrawer />
</ProposalPage>
```

## 4. 页面骨架代码

```tsx
import { useMemo, useState } from "react";

export function ProposalPage({ data }: { data: ProposalPageData }) {
  const [activeId, setActiveId] = useState(data.chapters[0]?.id ?? "");
  const [evidenceState, setEvidenceState] = useState<{ chapterId: string; refs: string[] } | null>(null);

  const navItems = useMemo(
    () => data.chapters.map((chapter) => ({ id: chapter.id, label: chapter.navLabel })),
    [data.chapters]
  );

  return (
    <div className="proposal-page theme-executive-dark">
      <StickyProposalNav items={navItems} activeId={activeId} onJump={setActiveId} />

      <main className="proposal-main">
        {data.chapters.map((chapter) => (
          <ProposalSectionRouter
            key={chapter.id}
            chapter={chapter}
            onVisible={setActiveId}
            onOpenEvidence={(refs) => setEvidenceState({ chapterId: chapter.id, refs })}
          />
        ))}
      </main>

      <EvidenceDrawer
        open={Boolean(evidenceState)}
        chapterId={evidenceState?.chapterId ?? ""}
        refs={evidenceState?.refs ?? []}
        onClose={() => setEvidenceState(null)}
      />
    </div>
  );
}
```

## 5. 路由组件

```tsx
function ProposalSectionRouter({
  chapter,
  onVisible,
  onOpenEvidence,
}: {
  chapter: ProposalChapter;
  onVisible?: (id: string) => void;
  onOpenEvidence?: (refs: string[]) => void;
}) {
  switch (chapter.id) {
    case "hero":
      return <HeroJudgementSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    case "why_now":
      return <WhyNowSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    case "comparison":
      return <OptionsComparisonSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    case "blueprint":
      return <RecommendedBlueprintSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    case "workstreams":
      return <WorkstreamsSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    case "integration":
      return <IntegrationLoopSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    case "roadmap":
      return <RoadmapSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    case "value_fit":
      return <ValueAndFitSection chapter={chapter} onOpenEvidence={onOpenEvidence} onVisible={onVisible} />;
    default:
      return null;
  }
}
```

## 6. 导航组件

```tsx
function StickyProposalNav({
  items,
  activeId,
  onJump,
}: {
  items: Array<{ id: string; label: string }>;
  activeId?: string;
  onJump?: (id: string) => void;
}) {
  return (
    <nav className="proposal-nav">
      <div className="proposal-nav__brand">DeepVision 提案页</div>
      <div className="proposal-nav__items">
        {items.map((item) => (
          <button
            key={item.id}
            className={item.id === activeId ? "proposal-nav__item is-active" : "proposal-nav__item"}
            onClick={() => onJump?.(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
```

## 7. 章节基础头部

```tsx
function SectionHeader({
  eyebrow,
  title,
  judgement,
  summary,
}: {
  eyebrow: string;
  title: string;
  judgement: string;
  summary: string;
}) {
  return (
    <header className="proposal-section__header">
      <div className="proposal-section__eyebrow">{eyebrow}</div>
      <h2 className="proposal-section__title">{title}</h2>
      <p className="proposal-section__judgement">{judgement}</p>
      <p className="proposal-section__summary">{summary}</p>
    </header>
  );
}
```

## 8. Hero 章节

```tsx
function HeroJudgementSection({
  chapter,
  onOpenEvidence,
}: {
  chapter: ProposalChapter;
  onOpenEvidence?: (refs: string[]) => void;
}) {
  return (
    <section id={chapter.id} className="proposal-section proposal-section--hero">
      <SectionHeader
        eyebrow={chapter.eyebrow}
        title={chapter.title}
        judgement={chapter.judgement}
        summary={chapter.summary}
      />

      <div className="proposal-metric-strip">
        {chapter.metrics.map((metric) => (
          <article key={metric.label} className="proposal-metric-card">
            <div className="proposal-metric-card__label">{metric.label}</div>
            <div className="proposal-metric-card__value">{metric.value}</div>
            {metric.delta ? <div className="proposal-metric-card__delta">{metric.delta}</div> : null}
            {metric.note ? <div className="proposal-metric-card__note">{metric.note}</div> : null}
          </article>
        ))}
      </div>

      <div className="proposal-hero__actions">
        {chapter.cta ? <button className="proposal-btn proposal-btn--primary">{chapter.cta.label}</button> : null}
        <button className="proposal-btn proposal-btn--ghost" onClick={() => onOpenEvidence?.(chapter.evidenceRefs)}>
          查看证据
        </button>
      </div>
    </section>
  );
}
```

## 9. 冲突卡片章节

```tsx
function WhyNowSection({
  chapter,
  onOpenEvidence,
}: {
  chapter: ProposalChapter;
  onOpenEvidence?: (refs: string[]) => void;
}) {
  return (
    <section id={chapter.id} className="proposal-section">
      <SectionHeader
        eyebrow={chapter.eyebrow}
        title={chapter.title}
        judgement={chapter.judgement}
        summary={chapter.summary}
      />

      <div className="proposal-card-grid proposal-card-grid--4">
        {chapter.cards.map((card) => (
          <article key={card.title} className="proposal-card proposal-card--conflict">
            {card.tag ? <div className="proposal-card__tag">{card.tag}</div> : null}
            <h3 className="proposal-card__title">{card.title}</h3>
            <p className="proposal-card__desc">{card.desc}</p>
            {card.meta ? <div className="proposal-card__meta">{card.meta}</div> : null}
          </article>
        ))}
      </div>

      <div className="proposal-section__footer">
        <button className="proposal-inline-link" onClick={() => onOpenEvidence?.(chapter.evidenceRefs)}>
          对应证据
        </button>
      </div>
    </section>
  );
}
```

## 10. 对比章节

```tsx
function OptionsComparisonSection({ chapter }: { chapter: ProposalChapter }) {
  return (
    <section id={chapter.id} className="proposal-section">
      <SectionHeader
        eyebrow={chapter.eyebrow}
        title={chapter.title}
        judgement={chapter.judgement}
        summary={chapter.summary}
      />

      <div className="proposal-comparison">
        {chapter.cards.map((card) => (
          <article key={card.title} className="proposal-option-card">
            <div className="proposal-option-card__top">
              <h3>{card.title}</h3>
              {card.tag ? <span className="proposal-badge">{card.tag}</span> : null}
            </div>
            <p>{card.desc}</p>
            {card.meta ? <div className="proposal-option-card__meta">{card.meta}</div> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
```

## 11. 蓝图 / 闭环 / 路线图共用图组件

```tsx
function DiagramCanvas({ diagram }: { diagram: ChapterDiagram }) {
  return (
    <div className={`proposal-diagram proposal-diagram--${diagram.type}`}>
      <div className="proposal-diagram__nodes">
        {diagram.nodes.map((node) => (
          <div key={node.id} className="proposal-diagram__node">
            {node.label}
          </div>
        ))}
      </div>
      <div className="proposal-diagram__caption">{diagram.caption}</div>
    </div>
  );
}
```

## 12. 蓝图章节

```tsx
function RecommendedBlueprintSection({ chapter }: { chapter: ProposalChapter }) {
  return (
    <section id={chapter.id} className="proposal-section">
      <SectionHeader
        eyebrow={chapter.eyebrow}
        title={chapter.title}
        judgement={chapter.judgement}
        summary={chapter.summary}
      />

      {chapter.diagram ? <DiagramCanvas diagram={chapter.diagram} /> : null}

      <div className="proposal-card-grid proposal-card-grid--4">
        {chapter.cards.map((card) => (
          <article key={card.title} className="proposal-card proposal-card--module">
            {card.tag ? <div className="proposal-card__tag">{card.tag}</div> : null}
            <h3 className="proposal-card__title">{card.title}</h3>
            <p className="proposal-card__desc">{card.desc}</p>
            {card.meta ? <div className="proposal-card__meta">{card.meta}</div> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
```

## 13. Workstreams 章节

```tsx
import { useState } from "react";

function WorkstreamsSection({ chapter }: { chapter: ProposalChapter }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeCard = chapter.cards[activeIndex];

  return (
    <section id={chapter.id} className="proposal-section">
      <SectionHeader
        eyebrow={chapter.eyebrow}
        title={chapter.title}
        judgement={chapter.judgement}
        summary={chapter.summary}
      />

      <div className="proposal-tabs">
        <div className="proposal-tabs__nav">
          {chapter.cards.map((card, index) => (
            <button
              key={card.title}
              className={index === activeIndex ? "proposal-tab is-active" : "proposal-tab"}
              onClick={() => setActiveIndex(index)}
            >
              {card.title}
            </button>
          ))}
        </div>

        {activeCard ? (
          <article className="proposal-tabs__panel">
            {activeCard.tag ? <div className="proposal-card__tag">{activeCard.tag}</div> : null}
            <h3>{activeCard.title}</h3>
            <p>{activeCard.desc}</p>
            {activeCard.meta ? <div className="proposal-card__meta">{activeCard.meta}</div> : null}
          </article>
        ) : null}
      </div>
    </section>
  );
}
```

## 14. 路线图章节

```tsx
function RoadmapSection({ chapter }: { chapter: ProposalChapter }) {
  return (
    <section id={chapter.id} className="proposal-section">
      <SectionHeader
        eyebrow={chapter.eyebrow}
        title={chapter.title}
        judgement={chapter.judgement}
        summary={chapter.summary}
      />

      <div className="proposal-timeline">
        {chapter.cards.map((card) => (
          <article key={card.title} className="proposal-timeline__item">
            <div className="proposal-timeline__marker" />
            <div className="proposal-timeline__content">
              <div className="proposal-card__tag">{card.tag}</div>
              <h3>{card.title}</h3>
              <p>{card.desc}</p>
              {card.meta ? <div className="proposal-card__meta">{card.meta}</div> : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
```

## 15. 价值与适配章节

```tsx
function ValueAndFitSection({
  chapter,
  onOpenEvidence,
}: {
  chapter: ProposalChapter;
  onOpenEvidence?: (refs: string[]) => void;
}) {
  return (
    <section id={chapter.id} className="proposal-section">
      <SectionHeader
        eyebrow={chapter.eyebrow}
        title={chapter.title}
        judgement={chapter.judgement}
        summary={chapter.summary}
      />

      <div className="proposal-value-grid">
        {chapter.metrics.map((metric) => (
          <article key={metric.label} className="proposal-value-card">
            <div className="proposal-value-card__label">{metric.label}</div>
            <div className="proposal-value-card__value">{metric.value}</div>
            {metric.delta ? <div className="proposal-value-card__delta">{metric.delta}</div> : null}
            {metric.note ? <div className="proposal-value-card__note">{metric.note}</div> : null}
          </article>
        ))}
      </div>

      <div className="proposal-card-grid proposal-card-grid--2">
        {chapter.cards.map((card) => (
          <article key={card.title} className="proposal-card proposal-card--fit">
            {card.tag ? <div className="proposal-card__tag">{card.tag}</div> : null}
            <h3 className="proposal-card__title">{card.title}</h3>
            <p className="proposal-card__desc">{card.desc}</p>
            {card.meta ? <div className="proposal-card__meta">{card.meta}</div> : null}
          </article>
        ))}
      </div>

      <div className="proposal-section__footer">
        <button className="proposal-inline-link" onClick={() => onOpenEvidence?.(chapter.evidenceRefs)}>
          查看证据与边界
        </button>
      </div>
    </section>
  );
}
```

## 16. Evidence Drawer

```tsx
function EvidenceDrawer({
  open,
  chapterId,
  refs,
  onClose,
}: {
  open: boolean;
  chapterId: string;
  refs: string[];
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <aside className="proposal-evidence-drawer">
      <div className="proposal-evidence-drawer__header">
        <div>证据锚点 · {chapterId}</div>
        <button onClick={onClose}>关闭</button>
      </div>

      <div className="proposal-evidence-drawer__body">
        {refs.length ? (
          refs.map((ref) => (
            <div key={ref} className="proposal-evidence-chip">
              {ref}
            </div>
          ))
        ) : (
          <div className="proposal-evidence-empty">当前章节暂无明确证据锚点</div>
        )}
      </div>
    </aside>
  );
}
```

## 17. 和当前仓库的映射建议

当前仓库没有 React 运行时，建议按下面顺序迁移现有 `web/solution.js`：

1. 先引入 `ProposalPageData` 数据协议
2. 把现有方案页拆成 8 个章节渲染函数
3. 先实现 `Hero / Comparison / Workstreams / ValueAndFit` 四章
4. 再补 `Blueprint / Integration / Roadmap / EvidenceDrawer`
5. 最后统一主题和动效

如果继续沿用当前原生栈，建议函数名按下面拆：

```js
renderProposalNav(data)
renderHeroJudgementSection(chapter)
renderWhyNowSection(chapter)
renderOptionsComparisonSection(chapter)
renderRecommendedBlueprintSection(chapter)
renderWorkstreamsSection(chapter)
renderIntegrationLoopSection(chapter)
renderRoadmapSection(chapter)
renderValueAndFitSection(chapter)
renderEvidenceDrawer(chapter, refs)
```

## 18. 下一步建议

下一步最值得做的不是继续补字段，而是：

1. 先让后端产出 `proposal_brief_v1`
2. 再让中间层产出 `chapter_copy_v1`
3. 然后把当前方案页渲染切到这份协议

这样你要的“像样例一样漂亮且有内容”的方案页，才有稳定实现基础。

# DeepVision 视觉系统升级稿（首发）

## 1. 设计 Token 结构

已在 `SITE_CONFIG` 建立语义 token：
- `designTokens.light.colors`
- `designTokens.dark.colors`
- `designTokens.radius`
- `designTokens.spacing`
- `designTokens.shadow`
- `designTokens.zIndex`

落地点：`/Users/hehai/.claude/skills/deep-vision/web/site-config.js`

## 2. 运行时注入策略

- 在 `app.js` 中通过 `applyDesignTokens(mode, effectiveTheme)` 注入 CSS 变量。
- 主题切换时同步注入，避免浅深色视觉漂移。

关键变量（示例）：
- `--dv-color-brand`
- `--dv-color-brand-hover`
- `--dv-color-overlay`
- `--dv-shadow-modal`
- `--dv-z-toast`

## 3. 组件规范（首发版）

### Modal
- 圆角：`--dv-radius-xl`
- 阴影：`--dv-shadow-modal`
- 按钮主色：`--dv-color-brand`

### Toast
- 层级：`--dv-z-toast`
- 类型语义：`success/info/warning/error`
- 无障碍：`role + aria-live + aria-atomic`

### 主按钮
- 默认：`--dv-color-brand`
- Hover：`--dv-color-brand-hover`
- Focus：基于 `a11y.focusRing` 统一

## 4. 跨页视觉一致性

- `index`：主产品视觉与 token 注入联动。
- `help`：品牌标题渐变、文字层级与主站对齐。
- `intro`：接入主题模式（`deepvision_theme_mode`），减少风格割裂。

## 5. 后续视觉演进（锁定科技理性）

### A：科技理性增强（持续）
- 保持蓝白体系，增强层次阴影与数据密度。

### B：未来感增强（暂停）
- 当前版本不启用，待主线稳定后再评估。

约束：
- 不牺牲可访问性（对比度、键盘、读屏）。
- 不影响核心任务效率。

---

## 6. 视觉预设锁定（已落地）

当前已锁定单一预设：

- `rational`（科技理性）：作为唯一生产预设，保证跨页面、跨流程视觉一致性。

锁定策略：
- `SITE_CONFIG.visualPresets.locked = true`，仅允许 `default` 预设生效。
- 忽略 URL 参数与本地缓存中的其他预设值。
- 主题菜单移除预设切换入口，避免误操作与认知分叉。

代码定位：
- `/Users/hehai/.claude/skills/deep-vision/web/site-config.js`
- `/Users/hehai/.claude/skills/deep-vision/web/app.js`
- `/Users/hehai/.claude/skills/deep-vision/web/index.html`

# DeepVision 三档用户级别改造实施文档

## 1. 文档定位

本文档是 DeepVision 用户级别改造的唯一实施基线，用于：

- 明确三档用户级别的功能边界
- 固化后端、前端、管理后台、测试的改造范围
- 作为后续开发排期、联调、验收与回归的依据
- 在实施过程中持续同步进度，避免口头状态失真

后续凡涉及用户级别、功能门禁、License 等级发放、前端入口控制、测试补充，统一以本文档为准。


## 2. 目标与边界

### 2.1 目标

本次改造目标不是重做一套复杂的订阅系统，而是在现有 `登录 + License + 功能链路` 基础上，增加一层稳定、清晰、易实施的三档用户级别能力控制：

- `体验版`
- `标准版`
- `专业版`

改造后，系统应能根据当前用户绑定的有效 License 识别其用户级别，并对以下核心功能实施差异化控制：

- 报告生成
- 报告导出
- 查看方案
- 方案分享
- 演示文稿生成

### 2.2 非目标

本阶段不做以下能力：

- 企业版
- 团队席位 / 成员共享
- 次数配额 / 调用额度 / 额度池
- 独立的订阅订单系统
- 复杂的能力配置后台
- 多级审批或组织级权限模型

### 2.3 实施原则

- 优先复用现有 License 体系，不新增独立用户等级系统
- 优先做功能边界清晰、稳定可测的一期闭环
- 能后端强校验的功能必须后端强校验
- 不能一步做到后端强校验的功能，明确标为“前端门禁 + 二期加固”
- 存量已发放 License 默认回填为 `标准版`，避免线上用户能力突然收缩


## 3. 用户级别定义

### 3.1 级别枚举

建议使用以下稳定键值：

| level_key | 名称 | 说明 |
|---|---|---|
| `experience` | 体验版 | 用于首体验证产品价值，功能最小开放 |
| `standard` | 标准版 | 用于正式报告交付 |
| `professional` | 专业版 | 用于高质量报告、方案分享与演示提案 |

### 3.2 默认策略

- 默认用户级别常量：`standard`
- 存量 License 未标注级别时：统一视为 `standard`
- 无有效 License 且 `LICENSE_ENFORCEMENT_ENABLED=false` 时：按 `experience` 处理
- 无有效 License 且 `LICENSE_ENFORCEMENT_ENABLED=true` 时：维持现有 License gate 行为


## 4. 功能矩阵

### 4.1 核心功能矩阵

| 功能 | 体验版 | 标准版 | 专业版 |
|---|---|---|---|
| 报告生成 `balanced` | 支持 | 支持 | 支持 |
| 报告生成 `quality` | 不支持 | 不支持 | 支持 |
| 报告正文导出 PDF | 不支持 | 支持 | 支持 |
| 报告正文导出 Markdown | 不支持 | 支持 | 支持 |
| 报告正文导出 Word | 不支持 | 支持 | 支持 |
| 附录导出 | 不支持 | 不支持 | 支持 |
| 查看方案页 | 不支持 | 不支持 | 支持 |
| 创建方案分享链接 | 不支持 | 不支持 | 支持 |
| 演示文稿生成 | 不支持 | 不支持 | 支持 |

### 4.2 产品策略说明

#### 体验版

定位是“先证明价值”，只允许用户完成最基础的报告产出，不开放任何正式交付或提案化能力。

#### 标准版

定位是“完成正式交付”，支持完整的正文报告导出，但不开放方案页、分享扩散和演示提案能力。

#### 专业版

定位是“能做售前推进与高质量交付”，开放 `quality` 报告、附录导出、方案分享、演示文稿。


## 5. 能力模型设计

### 5.1 一期采用静态 capability 映射

本期不恢复数据库化的 `tier/capability` 机制，而采用代码内固定映射，降低实施与维护复杂度。

建议 capability 常量：

- `report.generate`
- `report.profile.quality`
- `report.export.basic`
- `report.export.docx`
- `report.export.appendix`
- `solution.view`
- `solution.share`
- `presentation.generate`

### 5.2 capability 映射表

| capability | 体验版 | 标准版 | 专业版 |
|---|---|---|---|
| `report.generate` | true | true | true |
| `report.profile.quality` | false | false | true |
| `report.export.basic` | false | true | true |
| `report.export.docx` | false | true | true |
| `report.export.appendix` | false | false | true |
| `solution.view` | false | false | true |
| `solution.share` | false | false | true |
| `presentation.generate` | false | false | true |

### 5.3 为什么不用更细的配置模型

当前项目已经具备：

- 登录态
- License 激活
- License 生命周期
- 报告 profile 区分
- 方案页、分享、演示文稿独立接口

因此当前最优方案不是引入一套新的权限平台，而是用一组稳定常量，把关键功能的门禁做扎实。


## 6. 数据模型改造

主文件：`web/server.py`

当前 `licenses` 表定义位于：

- `ensure_license_tables()` 附近

### 6.1 数据字段改造

在 `licenses` 表新增字段：

- `level_key TEXT NOT NULL DEFAULT 'standard'`

要求：

- 仅允许 `experience / standard / professional`
- 存量数据自动回填为 `standard`

### 6.2 迁移策略

在 `ensure_license_tables()` 中增加列兼容逻辑：

- 若无 `level_key` 列，则执行 `ALTER TABLE licenses ADD COLUMN level_key TEXT NOT NULL DEFAULT 'standard'`

迁移要求：

- 无需离线迁移脚本
- 服务启动后自动兼容旧库
- 不影响现有 License 激活逻辑

### 6.3 License 生命周期与用户级别关系

用户当前有效级别取自当前有效 License：

- 新 License 激活后替换旧 License
- 用户级别自动跟随新 License
- 不维护单独的“用户当前等级表”

这样可以沿用现有替换逻辑，避免等级与 License 双写不一致。


## 7. 后端设计

主文件：`web/server.py`

### 7.1 新增常量与映射

建议新增：

- `DEFAULT_USER_LEVEL_KEY = "standard"`
- `USER_LEVEL_DEFINITIONS`
- `USER_LEVEL_CAPABILITY_MAP`

示例结构：

```python
DEFAULT_USER_LEVEL_KEY = "standard"

USER_LEVEL_DEFINITIONS = {
    "experience": {
        "key": "experience",
        "name": "体验版",
        "description": "支持基础报告生成",
        "sort_order": 10,
    },
    "standard": {
        "key": "standard",
        "name": "标准版",
        "description": "支持正式报告交付",
        "sort_order": 20,
    },
    "professional": {
        "key": "professional",
        "name": "专业版",
        "description": "支持高质量报告、方案分享与演示文稿",
        "sort_order": 30,
    },
}
```

### 7.2 新增领域函数

建议新增以下函数：

- `normalize_user_level_key(value, fallback=DEFAULT_USER_LEVEL_KEY)`
- `build_level_payload(level_key)`
- `build_level_capabilities(level_key)`
- `resolve_effective_user_level(user_row)`
- `build_user_level_snapshot(user_row)`
- `user_has_level_capability(user_row, capability_key)`
- `build_level_capability_denied_response(user_row, capability_key, required_level=None)`

### 7.3 统一返回结构

后端向前端返回统一结构：

```json
{
  "level": {
    "key": "standard",
    "name": "标准版",
    "description": "支持正式报告交付",
    "source": "license"
  },
  "capabilities": {
    "report.generate": true,
    "report.profile.quality": false,
    "report.export.basic": false,
    "report.export.docx": true,
    "report.export.appendix": false,
    "solution.view": false,
    "solution.share": false,
    "presentation.generate": false
  },
  "allowed_report_profiles": ["balanced"]
}
```

### 7.4 能力拒绝返回结构

建议统一错误结构：

```json
{
  "error": "当前用户级别暂未开放该功能",
  "error_code": "level_capability_denied",
  "capability_key": "presentation.generate",
  "current_level": {
    "key": "standard",
    "name": "标准版"
  },
  "required_level": {
    "key": "professional",
    "name": "专业版"
  },
  "upgrade_hint": "升级到专业版后可使用演示文稿生成"
}
```


## 8. 接口改造清单

### 8.1 登录与状态接口

#### `/api/auth/me`

现状：

- 仅返回 `user`

改造：

- 增加 `level`
- 增加 `capabilities`
- 增加 `allowed_report_profiles`

目标：

- 登录成功后前端一次拿到用户级别快照

#### `/api/licenses/current`

现状：

- 返回是否有有效 License 与 License 摘要

改造：

- 在 `license` 摘要中增加 `level_key`
- 返回中可直接带出 `level`

目标：

- 激活 License 后前端可立即刷新等级信息

#### `/api/status`

现状：

- 固定返回 `report_profile_options = ["balanced", "quality"]`

改造：

- 对已登录用户返回 `level`
- 返回 `capabilities`
- 返回 `allowed_report_profiles`
- 将 `report_profile_options` 改为动态结果

目标：

- 前端初始化时直接按等级显示功能

### 8.2 报告生成接口

#### `/api/sessions/<session_id>/generate-report`

改造点：

- 当请求 `quality` 时校验 `report.profile.quality`
- 无权限时返回统一能力拒绝
- 如果请求为空，仍按系统默认 profile 走，但前端默认值应已经被等级过滤

### 8.3 方案接口

#### `/api/reports/<filename>/solution`

改造点：

- 校验 `solution.view`

#### `/api/reports/<filename>/solution/share`

改造点：

- 校验 `solution.share`

说明：

- 公共分享页 `/api/public/solutions/<share_token>` 不做等级判断
- 分享链接是否继续有效，一期采用“已生成分享链接继续可用”的策略

### 8.4 演示文稿接口

涉及接口：

- `/api/reports/<filename>/refly`
- `/api/reports/<filename>/presentation`
- `/api/reports/<filename>/presentation/status`
- `/api/reports/<filename>/presentation/link`
- `/api/reports/<filename>/presentation/abort`

改造点：

- 统一校验 `presentation.generate`

### 8.5 导出接口

涉及接口：

- `/api/reports/<filename>/exports`
- `/api/reports/<filename>/exports/<asset_id>`
- `/api/reports/<filename>/appendix/pdf`

改造点：

- `appendix/pdf` 直接校验 `report.export.appendix`
- `/exports` 按 `scope + format` 校验当前等级
- 归档资产下载同样按当前等级校验，避免历史资产成为绕过路径


## 9. 前端改造清单

主文件：`web/app.js`

### 9.1 新增前端状态

建议新增：

- `currentLevelInfo`
- `userCapabilities`
- `allowedReportProfiles`

### 9.2 状态同步时机

以下时机同步用户级别快照：

- 登录成功后
- `checkAuthStatus()` 成功后
- `/api/status` 初始化完成后
- License 激活成功后
- License 状态刷新成功后
- 登出后清空

### 9.3 报告 profile 选择器

要求：

- 体验版 / 标准版仅显示 `balanced`
- 专业版显示 `balanced + quality`
- 若当前选择值超出权限范围，自动回退到 `balanced`

### 9.4 导出入口控制

#### 正文导出

- 体验版：不显示正文导出入口
- 标准版：显示 Markdown / PDF / Word
- 专业版：显示 Markdown / PDF / Word

#### 附录导出

- 仅专业版显示

### 9.5 方案入口控制

- 无 `solution.view` 时：
  - 隐藏“查看方案”入口
  - 如用户通过旧状态触发请求，后端返回能力拒绝并提示升级

规则说明：

- 体验版与标准版均不显示方案页入口
- 仅专业版开放方案页
- 方案入口不再依赖 `site-config` 前端开关

### 9.6 方案分享控制

- 无 `solution.share` 时：
  - 隐藏分享按钮
  - 后端仍做强校验

### 9.7 演示文稿入口控制

- 无 `presentation.generate` 时：
  - 隐藏或禁用“生成演示文稿”
  - 给出升级提示
- 若后端全局熔断关闭演示文稿：
  - 所有用户统一隐藏或禁用入口
  - 后端接口返回“管理员暂时关闭”错误
- 演示文稿入口不再依赖 `site-config` 前端开关

### 9.8 通用错误提示

新增统一处理：

- 若后端返回 `level_capability_denied`
- 前端根据 `required_level.name` 展示升级提示

建议文案：

- “当前用户级别暂未开放该功能”
- “升级到标准版后可导出正式报告”
- “升级到专业版后可使用高质量报告与演示文稿”
- “升级到专业版后可查看方案并创建分享链接”


## 10. 管理后台改造清单

主文件：

- `web/app.js`
- `web/server.py`

### 10.1 License 发放表单

批量生成 License 表单新增：

- `level_key` 下拉

选项：

- 体验版
- 标准版
- 专业版

默认值：

- 标准版

### 10.2 License 列表与详情

改造项：

- 列表增加“用户级别”列
- 增加按用户级别筛选
- 详情页展示 `level_key / level_name`

### 10.3 管理后台下载

批量生成结果导出时：

- 文本格式可保留原样
- CSV 增加 `level_key`

### 10.4 管理策略

一期不新增：

- 单条 License 改级
- 批量变更等级

升级/降级方式保持简单：

- 发新 License
- 用户激活新 License
- 旧 License 自动被替换


## 11. 测试清单

主测试文件建议：

- `tests/test_api_comprehensive.py`

如有必要，可新增：

- `tests/test_user_levels.py`

### 11.1 数据迁移测试

- 旧库无 `level_key` 时，启动自动补列
- 补列后旧 License 默认 `standard`

### 11.2 License 生成与激活测试

- 生成体验版 License 成功
- 生成标准版 License 成功
- 生成专业版 License 成功
- 激活后 `/api/licenses/current` 返回对应等级

### 11.3 License 替换测试

- 用户先激活标准版，再激活专业版
- 旧 License 变 `replaced`
- 当前用户等级切换为专业版

### 11.4 报告生成权限测试

- 体验版请求 `balanced` 成功
- 体验版请求 `quality` 失败
- 标准版请求 `quality` 失败
- 专业版请求 `quality` 成功

### 11.5 方案权限测试

- 体验版查看方案失败
- 标准版查看方案失败
- 标准版创建方案分享失败
- 专业版查看方案成功
- 专业版创建方案分享成功

### 11.6 演示文稿权限测试

- 标准版生成演示文稿失败
- 专业版生成演示文稿成功

### 11.7 导出权限测试

- 体验版无法下载 PDF / Markdown / Word
- 标准版无法导出附录
- 专业版可导出附录
- 历史归档导出资产下载按当前等级校验

### 11.8 前端联动测试

- 登录后 UI 按等级隐藏功能入口
- 激活更高等级 License 后 UI 能刷新
- 无权限功能点点击后有明确提示


## 12. 分阶段实施建议

### 12.1 第一阶段：最小闭环

目标：

- 用户等级数据打通
- 核心功能门禁落地
- 前端入口能按等级收口

范围：

- `licenses.level_key`
- 等级快照返回
- 报告 `quality` 门禁
- 方案查看 / 分享门禁
- 演示文稿门禁
- 附录导出门禁
- 正文导出前端入口控制
- 管理后台发放不同等级 License

### 12.2 第二阶段：导出强校验加固

目标：

- 正文导出不再依赖纯前端约束

范围：

- 增加服务端正文导出接口
- Markdown / PDF / Word 导出改走后端统一门禁
- 对归档资产做更严格控制

说明：

当前正文导出主要在前端本地生成，因此一期做到“前端门禁 + 归档约束 + 关键接口强校验”即可，不要为一期目标引入过大改造。


## 13. 上线策略

### 13.1 发布顺序

建议顺序：

1. 后端先发
2. 管理后台再发
3. 前端最后发

原因：

- 先保证后端认识 `level_key`
- 再让运营可发放不同级别 License
- 最后让前端按新字段收口功能

### 13.2 存量处理

- 所有存量 License 默认 `standard`
- 不做批量能力收缩

### 13.3 回滚策略

若上线出现异常：

- 逻辑回滚优先级高于数据回滚
- 可临时把所有等级视为 `standard`
- 不需要回滚 `level_key` 列


## 14. 风险清单

### 14.1 风险：正文导出被前端绕过

原因：

- 当前正文导出主要在前端本地生成

策略：

- 一期通过 UI 门禁控制
- 二期补服务端统一导出接口

### 14.2 风险：前端缓存导致等级切换后功能未及时刷新

策略：

- 登录后
- License 激活后
- License 状态刷新后
- 进入主应用时

都重新拉取等级快照

### 14.3 风险：历史分享链接与等级变化冲突

策略：

- 一期不回收既有分享链接
- 后续若业务需要再增加“降级时回收分享”的独立策略


## 15. 开发任务拆解

### 15.1 后端

- [x] 给 `licenses` 表增加 `level_key`
- [x] 增加等级枚举与 capability 映射
- [x] 增加等级快照构建函数
- [x] 改造 `/api/auth/me`
- [x] 改造 `/api/licenses/current`
- [x] 改造 `/api/status`
- [x] 改造 `/api/sessions/<session_id>/generate-report`
- [x] 改造 `/api/reports/<filename>/solution`
- [x] 改造 `/api/reports/<filename>/solution/share`
- [x] 改造 `/api/reports/<filename>/appendix/pdf`
- [x] 改造全部演示文稿相关接口
- [x] 改造 `/api/reports/<filename>/exports*`
- [x] 改造管理后台 License 批量生成接口
- [x] 改造管理后台 License 列表/详情返回

### 15.2 前端

- [x] 增加等级状态与能力状态
- [x] 登录后同步等级快照
- [x] License 激活后同步等级快照
- [x] 报告 profile 选项按等级过滤
- [x] 正文导出菜单按等级过滤
- [x] 附录导出入口按等级过滤
- [x] 方案入口按等级过滤
- [x] 方案分享按钮按等级过滤
- [x] 演示文稿按钮按等级过滤
- [x] 管理后台发 License 表单增加等级下拉
- [x] 管理后台列表/详情展示用户级别
- [x] 能力拒绝错误统一提示

### 15.3 测试

- [x] 补数据迁移测试
- [x] 补等级生成与激活测试
- [x] 补等级替换测试
- [x] 补报告 profile 权限测试
- [x] 补方案查看/分享权限测试
- [x] 补演示文稿权限测试
- [x] 补附录导出权限测试
- [x] 补导出归档下载权限测试


## 16. 进度同步规则

后续实施时，必须同步更新本文档，不允许只在聊天记录中报进度。

更新规则：

- 每完成一个明确任务，勾选对应复选框
- 每完成一个阶段，在“执行进度”中更新状态
- 如有设计调整，在“变更记录”中补一条说明
- 如遇阻塞，在“当前阻塞项”中写明原因和决策


## 17. 执行进度

### 17.1 当前阶段

- 状态：`进行中`
- 更新时间：`2026-03-31`
- 当前阶段目标：完成用户级别能力快照、核心功能门禁、前端入口收口、迁移测试补齐，并识别全量回归阻塞项

### 17.2 里程碑

| 里程碑 | 状态 | 说明 |
|---|---|---|
| M1 文档基线确认 | 已完成 | 三档能力矩阵与实施范围已固化，已同步最新功能边界 |
| M2 后端等级识别 | 已完成 | 已完成等级解析、capability 快照与 `auth/status/license` 返回 |
| M3 功能门禁落地 | 已完成 | 已覆盖报告生成、方案页、分享、附录、演示、导出归档接口 |
| M4 前端入口收口 | 已完成 | 已按等级隐藏报告导出、方案、演示与附录入口 |
| M5 管理后台发码支持 | 已完成 | 管理后台已支持发码选级、列表筛级、详情展示与导出等级字段 |
| M6 测试与回归 | 进行中 | 已补齐迁移测试并通过 11 条用户级别 / License 相关回归；完整全量回归仍受既有失败阻塞 |


## 18. 当前阻塞项

- 系统 Python 受 PEP 668 限制，复测仍需先创建临时虚拟环境并安装依赖
- `pytest -q tests -ra --disable-warnings` 当前无法全绿，已确认的既有阻塞包括：
- `tests/test_security_regression.py` 第 `3550` 行存在语法错误，导致整套 `pytest` 收集被中断
- `tests/test_scripts_comprehensive.py` 在 `pytest` 收集阶段存在 `scripts` 模块导入路径问题，需统一测试启动方式或补 `PYTHONPATH`
- `tests/test_api_comprehensive.py::ComprehensiveApiTests::test_admin_ownership_migration_endpoints_cover_search_preview_apply_and_rollback` 当前断言失败，属于非用户级别链路的既有回归项
- 其他非用户级别测试在当前 Python 3.14 环境下仍有历史失败，需单独清理后才能宣告“全量回归通过”


## 19. 变更记录

### 2026-03-31

- 新建三档用户级别改造实施文档
- 确认一期采用 `License.level_key + 静态 capability 映射` 方案
- 确认企业版、配额系统、团队能力不在本阶段范围内
- 调整功能边界：体验版去掉正文 PDF 导出，标准版去掉方案页查看
- 落地第一步：`licenses.level_key`、旧 License 默认标准版、管理后台发码选级、列表与详情展示等级
- 增补等级相关测试代码，并记录本地测试依赖缺失的验证限制
- 落地第二步：新增等级 capability 快照，并将 `/api/auth/me`、`/api/status`、`/api/licenses/current` 改为按等级返回能力与可用报告 profile
- 完成核心门禁：报告 `quality`、正文/附录导出归档、方案页、方案分享、演示文稿相关接口均已按等级校验
- 完成前端入口收口：高于当前等级的报告导出、方案、方案分享、演示、附录入口不再展示
- 补充关键回归测试：覆盖体验版 `quality` 拦截、等级替换、标准版门禁、专业版放行与导出归档权限
- 本次通过临时虚拟环境安装测试依赖并执行关键回归，未保留运行环境目录
- 补齐 `licenses.level_key` 迁移专项测试，覆盖“旧库无 `level_key` 默认标准版”和“旧库已有等级时保留原值”两类场景
- 修复后台 License 批量延期/撤销仍误连 `users.db` 的残留问题，统一改为访问 `licenses.db`
- 使用临时虚拟环境执行回归：用户级别与 License 直接相关的 11 条用例已全部通过，并记录了当前整套全量回归的既有阻塞项

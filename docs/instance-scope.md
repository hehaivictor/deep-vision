# INSTANCE_SCOPE_KEY 配置规范

本文档用于规范 DeepVision 多实例部署时的 `INSTANCE_SCOPE_KEY` 配置，避免同一账号在不同 DeepVision 链接之间串看会话和报告。

## 背景

DeepVision 现在支持按实例作用域隔离会话和报告。系统在读取会话列表、报告列表、详情、批量删除时，都会同时校验：

- `owner_user_id`
- `instance_scope_key`

如果多个 DeepVision 实例共享同一份 `data/` 目录，但没有正确配置 `INSTANCE_SCOPE_KEY`，就可能出现以下问题：

- 同一微信账号在不同链接登录后看到其他实例的数据
- 会话批量删除时误删其他实例同主题报告
- 报告文件名在共享目录下发生覆盖

## 一句话规则

- 同一个业务链接的所有副本，`INSTANCE_SCOPE_KEY` 必须相同。
- 不同业务链接，如果共享同一份 `data/`，`INSTANCE_SCOPE_KEY` 必须不同。

## 什么时候必须配置

以下场景必须配置：

- 多个 DeepVision 链接共享同一份 `data/` 目录
- 同一微信账号可能登录多个 DeepVision 链接
- 生产环境使用共享存储、挂载卷或统一运行目录

以下场景不是强制，但仍建议配置：

- 每个实例使用独立 `data/` 目录
- 当前只有单实例，但后续可能扩容或新增链接

## 配置优先级

当前代码读取优先级如下：

1. `DEEPVISION_INSTANCE_SCOPE_KEY`
2. `INSTANCE_SCOPE_KEY`
3. `web/config.py` 中的 `INSTANCE_SCOPE_KEY`

推荐做法：

- 部署环境优先写入 `web/.env` 或进程环境变量
- `web/config.py` 仅建议作为本地开发或临时排障时的兜底配置
- 如果同时维护 `web/.env` 与 `web/config.py`，请确保两处值完全一致，避免排查时混淆

## 推荐命名规则

建议直接由访问域名派生，规则固定：

- 全部小写
- 去掉协议头 `https://` 或 `http://`
- 只保留域名主体，不带路径
- 将 `.` 替换为 `-`
- 不要包含端口、随机值、容器名、进程号

示例：

- `https://wjkuhannejiw.sealosbja.site` -> `wjkuhannejiw-sealosbja-site`
- `https://deepvision-prod.example.com` -> `deepvision-prod-example-com`
- `https://customer-a.deepvision.com` -> `customer-a-deepvision-com`

## 标准配置模板

假设实例访问链接为：

```text
https://your-instance.example.com
```

推荐 `INSTANCE_SCOPE_KEY`：

```text
your-instance-example-com
```

`web/.env`：

```env
WECHAT_LOGIN_ENABLED=true
WECHAT_REDIRECT_URI=https://your-instance.example.com/api/auth/wechat/callback
INSTANCE_SCOPE_KEY=your-instance-example-com
```

如需保留本地兜底，也可以在 `web/config.py` 中写入同值：

```python
WECHAT_REDIRECT_URI = "https://your-instance.example.com/api/auth/wechat/callback"
INSTANCE_SCOPE_KEY = "your-instance-example-com"
```

## 典型场景

### 场景一：两个不同链接，共享同一份 data

实例 A：

```text
https://a.example.com
INSTANCE_SCOPE_KEY=a-example-com
```

实例 B：

```text
https://b.example.com
INSTANCE_SCOPE_KEY=b-example-com
```

结果：

- 同一账号在 A 中只能看到 A 的会话和报告
- 同一账号在 B 中只能看到 B 的会话和报告

### 场景二：同一链接有多个副本

访问链接：

```text
https://deepvision.example.com
```

后面有多个副本：

- pod-1
- pod-2
- pod-3

这 3 个副本必须全部使用同一个值：

```env
INSTANCE_SCOPE_KEY=deepvision-example-com
```

不要写成：

```env
pod-1 -> INSTANCE_SCOPE_KEY=pod-1
pod-2 -> INSTANCE_SCOPE_KEY=pod-2
pod-3 -> INSTANCE_SCOPE_KEY=pod-3
```

否则同一个站点内部会出现“有时能看到数据、有时看不到数据”的问题。

### 场景三：本机同时运行多个不同 DeepVision 应用

如果本机同时运行多个不同链接的 DeepVision，且错误地共享了同一个 `data/`：

- 链接 A 使用 `INSTANCE_SCOPE_KEY=client-a-example-com`
- 链接 B 使用 `INSTANCE_SCOPE_KEY=client-b-example-com`

## 不推荐的写法

不要使用以下值：

- `5001`
- `pod-7f8a`
- `hostname`
- 容器随机 ID
- 每次部署都会变化的值

这些值不稳定，会导致以下问题：

- 重启后数据像“消失”
- 扩容后同一站点副本之间数据不一致
- 运维排查时无法判断真实归属

## 历史数据迁移说明

启用 `INSTANCE_SCOPE_KEY` 后，旧的无 scope 历史数据默认不会自动显示。这是安全策略，用于避免误把历史数据归到错误实例。

如果确认某批历史数据都属于当前实例，需要做一次显式迁移：

- 历史会话文件补 `instance_scope_key`
- 历史报告补 `data/reports/.scopes.json`
- 更新 `meta_index.db`

建议在迁移前先备份：

- `data/sessions/`
- `data/reports/.owners.json`
- `data/reports/.scopes.json`
- `data/meta_index.db`

## 新实例上线检查清单

每个新实例上线前检查以下 6 项：

1. `WECHAT_REDIRECT_URI` 与实际访问域名一致
2. `INSTANCE_SCOPE_KEY` 已配置
3. 如果共享 `data/`，该值与其他链接不同
4. 如果是同一链接多副本，该值在所有副本中完全一致
5. 修改配置后已重启服务
6. 启动日志中没有出现“未配置 INSTANCE_SCOPE_KEY”的告警

## 验证方法

上线后建议验证以下 3 项：

1. 当前实例创建的新会话只在当前链接可见
2. 同一微信账号登录其他链接时，看不到当前实例数据
3. 报告生成、列表、详情、批量删除均只作用于当前实例数据

## 推荐运维记录模板

建议为每个实例维护一张清单：

```text
实例名称:
访问链接:
是否共享 data 目录: 是 / 否
INSTANCE_SCOPE_KEY:
配置位置: web/.env（推荐） / 环境变量 / web/config.py（本地兜底）
备注:
```

示例：

```text
实例名称: 生产环境A
访问链接: https://wjkuhannejiw.sealosbja.site
是否共享 data 目录: 是
INSTANCE_SCOPE_KEY: wjkuhannejiw-sealosbja-site
配置位置: web/.env
备注: 同链接下所有副本统一使用该值
```

# Deep Vision 前端配置说明

本文档只说明 [site-config.js](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/site-config.js) 的前端展示配置。

如果你要修改的是：

- 登录方式
- 短信供应商
- 微信登录开关与回调
- 管理员白名单
- `INSTANCE_SCOPE_KEY`
- `SECRET_KEY`
- 数据库路径
- 对象存储
- Gunicorn 或部署参数

请直接查看：

- [README.md](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/README.md)
- [web/.env.example](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/.env.example)
- [web/config.py](/Users/hehai/Documents/开目软件/Agents/project/DeepVision/web/config.py)

## 配置文件位置

```text
/web/site-config.js
```

## 配置边界

`site-config.js` 只负责前端页面展示层与 API 基础地址，例如：

- 顶部诗句轮播
- 主题颜色
- 前端请求的 `api.baseUrl`
- 页面侧的少量展示节奏参数

一句话判断：

- 改页面表现：看本文档
- 改后端行为：看 `README.md` 与 env/config

## 支持的配置项

### 1. 诗句轮播 `quotes`

用于控制页面顶部诗句的展示与切换节奏。

```javascript
quotes: {
  enabled: true,
  interval: 10000,
  items: [
    { text: '路漫漫其修远兮，吾将上下而求索', source: '——屈原《离骚》' }
  ]
}
```

字段说明：

- `enabled`：是否启用轮播
- `interval`：切换间隔，单位毫秒
- `items`：诗句数组，每项包含 `text` 和 `source`

### 2. 主题颜色 `colors`

用于控制前端基础主题色。

```javascript
colors: {
  primary: '#357BE2',
  success: '#22C55E',
  progressComplete: '#357BE2'
}
```

字段说明：

- `primary`：主强调色
- `success`：成功状态色
- `progressComplete`：进度完成色

### 3. API 配置 `api`

用于告诉前端请求哪个后端。

```javascript
api: {
  baseUrl: 'http://localhost:5001/api',
  webSearchPollInterval: 200,
  sessionListPollInterval: 3000,
  reportStatusPollInterval: 600
}
```

字段说明：

- `baseUrl`：前端请求的 API 基础地址
- `webSearchPollInterval`：Web Search 状态轮询间隔
- `sessionListPollInterval`：会话列表自动刷新间隔
- `reportStatusPollInterval`：报告生成状态轮询间隔

注意：

- `api.baseUrl` 只决定请求目标，不决定后端的登录、短信、微信、管理员权限或 License 策略

### 4. 前端输入限制 `limits`

用于控制浏览器侧的输入长度与上传大小提示。真实服务端限制仍以后端校验为准。

```javascript
limits: {
  topicMaxLength: 200,
  descriptionMaxLength: 1000,
  answerMaxLength: 5000,
  otherInputMaxLength: 2000,
  maxFileSize: 10485760
}
```

字段说明：

- `topicMaxLength`：访谈主题最大长度
- `descriptionMaxLength`：补充描述最大长度
- `answerMaxLength`：常规回答最大长度
- `otherInputMaxLength`：其他选项输入最大长度
- `maxFileSize`：前端文件上传大小上限，单位字节

## 最小示例

### 调整诗句轮播间隔

```javascript
quotes: {
  enabled: true,
  interval: 15000,
  items: [
    { text: '路漫漫其修远兮，吾将上下而求索', source: '——屈原《离骚》' }
  ]
}
```

### 更换主题色

```javascript
colors: {
  primary: '#2563EB',
  success: '#10B981',
  progressComplete: '#2563EB'
}
```

### 指向远程后端

```javascript
api: {
  baseUrl: 'https://your-domain.com/api',
  webSearchPollInterval: 200,
  sessionListPollInterval: 3000,
  reportStatusPollInterval: 600
}
```

## 使用注意

1. 修改后需要刷新页面
2. 保持 JavaScript 语法正确
3. 颜色使用十六进制格式
4. 时间单位均为毫秒

## 默认配置恢复

如果 `site-config.js` 被改坏，可以参考以下最小默认结构重建：

```javascript
const SITE_CONFIG = {
  quotes: {
    enabled: true,
    interval: 10000,
    items: [
      { text: '路漫漫其修远兮，吾将上下而求索', source: '——屈原《离骚》' }
    ]
  },
  colors: {
    primary: '#357BE2',
    success: '#22C55E',
    progressComplete: '#357BE2'
  },
  api: {
    baseUrl: 'http://localhost:5001/api',
    webSearchPollInterval: 200,
    sessionListPollInterval: 3000,
    reportStatusPollInterval: 600
  },
  limits: {
    topicMaxLength: 200,
    descriptionMaxLength: 1000,
    answerMaxLength: 5000,
    otherInputMaxLength: 2000,
    maxFileSize: 10485760
  }
};
```

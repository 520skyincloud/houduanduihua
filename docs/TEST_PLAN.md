# 丽斯未来酒店展厅 AI 系统测试计划

## 1. 总体验收目标

验证双链系统满足：

- `RTC(媒体底座) -> StartVoiceChat(2024-12-01) -> S2S + Memory 主链`
- `RTC(媒体底座) -> 后端路由 -> FAQ/RAGFlow/强规则 -> ExternalTextToSpeech`
- `RTC(媒体底座) -> 后端路由 -> 收益调价 MCP -> ExternalTextToSpeech`
- 两条链共存时始终只有一个 AI 在说话
- 打断、过渡语、旧轮作废顺序稳定

## 2. 参数连通性矩阵

### 2.1 RTC

- 检查：
  - `VOLCENGINE_RTC_APP_ID`
  - `VOLCENGINE_RTC_APP_KEY`
- 验证步骤：
  - `GET /api/health`
  - `POST /api/bootstrap`
  - 页面能成功 `joinRoom`

### 2.2 OpenAPI

- 检查：
  - `VOLCENGINE_ACCESS_KEY_ID`
  - `VOLCENGINE_SECRET_ACCESS_KEY`
- 验证步骤：
  - 创建会话后执行 `POST /api/rtc/sessions/{session_id}/start`
  - 再执行 `POST /api/rtc/sessions/{session_id}/stop`

### 2.3 S2S 主链

- 检查：
  - `VOLCENGINE_VOICE_CHAT_VERSION=2024-12-01`
  - `VOLCENGINE_ENABLE_S2S=true`
  - `VOLCENGINE_S2S_CONFIG_JSON`
- 验证步骤：
  - `GET /api/validate/config-groups`
  - `POST /start`
  - 用户提问后观察首答速度、自然对话、打断是否正常
  - 分开记录“RTC 已进房”和“VoiceChat 已启动”两层状态

### 2.4 长期记忆

- 检查：
  - `VOLCENGINE_ENABLE_MEMORY=true`
  - `VOLCENGINE_MEMORY_CONFIG_JSON`
- 验证步骤：
  - 连续多轮追问同一主题
  - 观察记忆是否参与回答

### 2.5 回调

- 检查：
  - `VOLCENGINE_CALLBACK_BASE_URL`
- 验证步骤：
  - `GET /api/validate/callback-manifest`
  - 公网访问三类回调地址
  - 回调接口必须在 5 秒内返回 `200`

### 2.6 ASR / TTS 备用链

- 检查：
  - `VOLCENGINE_ASR_*`
  - `VOLCENGINE_TTS_*`
- 验证步骤：
  - `GET /api/validate/config-groups`
  - 关闭或移除 `VOLCENGINE_S2S_CONFIG_JSON` 后再执行 `POST /start`

### 2.7 RAGFlow

- 检查：
  - `RAGFLOW_SEARCH_URL`
  - `RAGFLOW_API_KEY`
  - `RAGFLOW_DATASET_ID`
- 验证步骤：
  - `GET /api/validate/ragflow`
  - 高频 FAQ 回归测试

### 2.8 收益调价 MCP

- 检查：
  - `REVENUE_MCP_ENABLED`
  - `REVENUE_MCP_SSE_URL`
  - `REVENUE_MCP_API_HEALTH_URL`
- 验证步骤：
  - `GET /api/validate/revenue-mcp`
  - `GET /api/validate/revenue-mcp/tools/health_overview`
  - `GET /api/validate/revenue-mcp/tools/generate_current_pricing_strategy`
  - `GET /api/validate/revenue-mcp/tools/get_latest_execution_summary`

## 3. 体验链路测试

### 3.1 首包速度

记录：

- `t0` 用户句末
- `t1` 收到 `paragraph=true`
- `t2` `/utterances` 收到请求
- `t3` 路由完成
- `t4` 过渡语事件下发
- `t5` 正式答案事件下发

建议目标：

- `S2S` 首答：按实际链路记录
- 后端链 `t0 -> t4 < 500ms`
- 常规 FAQ `t0 -> t5 < 1500ms`

### 3.2 路由所有权

验证：

- “请介绍一下你自己” 走 `S2S`
- “酒店都有什么服务” 走 `S2S`
- “早餐几点” 走 `backend`
- “酒店在什么位置” 走 `backend`
- “你好呀” 走 `S2S`
- “现在来个调价策略” 走 `backend`
- “按这个策略执行” 在存在待确认上下文时走 `backend`
- 不确定表达默认走 `backend`

要求：

- 每一轮响应里都能看出 `owner`
- 不允许 `S2S` 和后端同时对同一轮说话

### 3.3 过渡语

验证：

- 后端查询延迟到 `600ms / 1000ms / 1500ms`
- 每轮最多一次过渡语
- 正式答案回来后不允许再补播旧过渡语

### 3.4 打断

验证：

- 欢迎词中打断
- `S2S` 回答中打断
- 过渡语中打断
- 正式答案中打断
- 连续追问 3 轮

要求：

- 用户新语音优先级最高
- 旧轮次结果不得插播新轮

### 3.5 收益链确认流

验证：

- “现在来个调价策略” 生成预演并进入 `pricing_confirm_pending`
- “按这个策略执行” 命中最近一次待确认上下文
- “取消这次调价执行” 能清理待确认上下文
- execution_id 过期或不一致时拒绝执行

要求：

- 高风险执行必须显式双确认
- 预演和执行不得由 `S2S` 抢答
- 收益链失败时必须回稳定兜底，不允许后台任务崩掉

## 4. 页面与 3D 容器

验证：

- 中间 `selfAvatarMount` 容器始终存在
- 无自研 3D 组件时，页面仍可完整工作
- 后续挂载自研 3D 组件时，不影响字幕、状态条和 RTC 链路
- 若火山远端流发布，只进入备用视频层，不覆盖自研 3D 主容器

## 5. 回归要求

- 缺少 S2S 配置时，系统必须明确告警而不是伪装成功
- 缺少记忆配置时，系统必须明确告警而不是伪装成功
- 缺少回调基址时，系统必须明确提示公网地址未固定
- 关闭火山能力后，本地 FAQ fallback 仍可跑通

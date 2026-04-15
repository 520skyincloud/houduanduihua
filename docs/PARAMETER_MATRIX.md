# 参数矩阵与连通性验证

## 1. RTC

- 变量：
  - `VOLCENGINE_RTC_APP_ID`
  - `VOLCENGINE_RTC_APP_KEY`
- 来自：
  - RTC 应用控制台
- 验证：
  - `GET /api/health`
  - `POST /api/bootstrap`
  - 前端 `joinRoom`

## 2. OpenAPI

- 变量：
  - `VOLCENGINE_ACCESS_KEY_ID`
  - `VOLCENGINE_SECRET_ACCESS_KEY`
- 来自：
  - 火山 IAM AccessKey
- 验证：
  - `POST /api/rtc/sessions/{session_id}/start`
  - `POST /api/rtc/sessions/{session_id}/stop`

## 3. S2S 主链

- 变量：
  - `VOLCENGINE_VOICE_CHAT_VERSION=2024-12-01`
  - `VOLCENGINE_ENABLE_S2S=true`
  - 二选一：
  - `VOLCENGINE_S2S_CONFIG_JSON`
  - 或 `VOLCENGINE_S2S_APP_ID` + `VOLCENGINE_S2S_TOKEN` + `VOLCENGINE_S2S_MODEL`
- 相关快速 API Key：
  - `VOLCENGINE_REALTIME_API_KEY`
- 来自：
  - 官方 S2S 文档或控制台导出的 VoiceChat 配置
  - 实时语音“快捷 API 接入”页面里的 API Key
- 验证：
  - `GET /api/validate/config-groups`
  - `POST /api/rtc/sessions/{session_id}/start`
  - 首答 / 打断 / 连续对话

## 4. 长期记忆

- 变量：
  - `VOLCENGINE_ENABLE_MEMORY=true`
  - 二选一：
  - `VOLCENGINE_MEMORY_CONFIG_JSON`
  - 或 `VOLCENGINE_MEMORY_NATIVE_COLLECTION_NAME` + `VOLCENGINE_MEMORY_NATIVE_USER_IDS_JSON` + `VOLCENGINE_MEMORY_NATIVE_TYPES_JSON`
  - `VOLCENGINE_MEMORY_API_BASE_URL`
  - `VOLCENGINE_MEMORY_API_KEY`
  - `VOLCENGINE_MEMORY_PROJECT_NAME`
  - `VOLCENGINE_MEMORY_COLLECTION_NAME`
- 来自：
  - 官方记忆库配置
  - 记忆库 REST API
- 验证：
  - `GET /api/validate/config-groups`
  - 连续多轮追问后观察是否命中记忆
  - `GET /api/validate/memory`

## 5. ASR / TTS 备用链

- 变量：
  - `VOLCENGINE_ASR_*`
  - `VOLCENGINE_TTS_*`
- 用途：
  - S2S 缺失时的备用链
  - 后续独立音频链测试
- 验证：
  - `GET /api/validate/config-groups`
  - 关闭 S2S 时 `StartVoiceChat` 启动是否成功

## 6. 回调

- 变量：
  - `VOLCENGINE_CALLBACK_BASE_URL`
- 验证：
  - `GET /api/validate/callback-manifest`
  - 公网访问三类回调地址
  - 接口 5 秒内返回 `200`

## 7. RAGFlow

- 变量：
  - `RAGFLOW_SEARCH_URL`
  - `RAGFLOW_API_KEY`
  - `RAGFLOW_DATASET_ID`
- 验证：
  - `GET /api/validate/ragflow`
  - FAQ 高峰问题命中率与耗时

## 8. 收益调价 MCP

- 变量：
  - `REVENUE_MCP_ENABLED`
  - `REVENUE_MCP_SSE_URL`
  - `REVENUE_MCP_API_HEALTH_URL`
  - `REVENUE_MCP_DEFAULT_STORE_ID`
  - `REVENUE_MCP_CONFIRMATION_TTL_SECONDS`
- 来源：
  - `'/Users/sky/Project/New project voice/mcp/server.py'`
  - 对应 SSE 端点 `/sse`
- 验证：
  - `GET /api/validate/revenue-mcp`
  - `GET /api/validate/revenue-mcp/tools/health_overview`
  - `GET /api/validate/revenue-mcp/tools/generate_current_pricing_strategy`
  - `GET /api/validate/revenue-mcp/tools/get_latest_execution_summary`

## 9. 功能共存边界

- 可同时存在：
  - `S2S + RTC 原生 MemoryConfig`
  - `S2S + 后端 Memory API`
  - `S2S + FAQ/强规则后端链`
  - `S2S + 收益调价 MCP`
- 当前推荐分工：
  - `RTC`：音视频底座
  - `实时对话式 AI`：`VoiceChat + S2S + Memory`
  - `S2S + Memory`：迎宾、寒暄、自我介绍、低风险自然对话、低风险酒店问答
  - `FAQ/强规则后端链`：早餐、停车、发票、入住退房、路线、楼层、设施、用品、会议室、收费、价格、政策、时间等高风险酒店事实
- 不能同轮混用：
  - `S2S` 与 `FAQ/强规则后端链`
  - `S2S` 与 `收益调价 MCP`
- 当前不作为主方案：
  - `S2S + 动态短期上下文注入`
  - `S2S` 直接承担高风险调价工具主决策

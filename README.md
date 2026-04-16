# 丽斯未来酒店展厅 AI 系统

当前仓库已经切到“**S2S 主链 + 后端可控链**”的双链结构：

- **主对话链**：火山 RTC + `StartVoiceChat(2024-12-01)` + `S2SConfig` + 长期记忆
- **后端可控链**：FAQ / RAGFlow / 强规则 / 过渡语 / 转人工
- **FAQ v2 旁路**：`normalize / lexicon / retrieve / rerank / engine` 的新链路，默认 shadow，可灰度切换
- **收益调价链**：直连 `'/Users/sky/Project/New project voice'` 的 SSE MCP，由后端统一接管
- **展厅页面**：中间预留自研 3D 人物挂载容器，火山官方数字人只保留备用位

这里要明确区分两层能力：

- **实时音视频 RTC**
  - 负责进房、媒体采集、传输、播放和字幕消息承载
  - 是低时延音视频通信底座
- **实时对话式 AI**
  - 负责 `StartVoiceChat / UpdateVoiceChat / StopVoiceChat`
  - 负责 `S2SConfig / MemoryConfig / LLMConfig / ASRConfig / TTSConfig`
  - 是运行在 RTC 场景上的 AI 会话能力

因此在本项目里：

- `RTC 通了` 只代表音视频底座可用
- `VoiceChat + S2S + Memory 通了` 才代表实时对话式 AI 主链可用
- `后端 FAQ / 收益链 / 外部播报` 通了，才代表完整业务链可用

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/import_faq.py --input "/Users/sky/Downloads/02-（丽斯高铁南站）-单问单答.xlsx" --output data/faq_index.json
uvicorn app.main:app --host 0.0.0.0 --port 12000 --reload
```

打开 <http://127.0.0.1:12000>。

## 配置方式

- 运行时统一读取 `.env`
- 示例模板见 `.env.example`
- 当前本地默认端口：`12000`

### 当前已落地的关键变量

- RTC：
  - `VOLCENGINE_RTC_APP_ID`
  - `VOLCENGINE_RTC_APP_KEY`
- OpenAPI：
  - `VOLCENGINE_ACCESS_KEY_ID`
  - `VOLCENGINE_SECRET_ACCESS_KEY`
- 主链版本：
  - `VOLCENGINE_VOICE_CHAT_VERSION=2024-12-01`
  - `VOLCENGINE_PRIMARY_DIALOG_PATH=s2s`
- FAQ v2 旁路：
  - `VOLCENGINE_FAQ_V2_MODE=shadow`
- S2S / Memory：
  - `VOLCENGINE_ENABLE_S2S`
  - `VOLCENGINE_S2S_CONFIG_JSON`
  - 或者改用简单参数：
  - `VOLCENGINE_S2S_APP_ID`
  - `VOLCENGINE_S2S_TOKEN`
  - `VOLCENGINE_S2S_MODEL`
  - `VOLCENGINE_REALTIME_API_KEY`
  - `VOLCENGINE_ENABLE_MEMORY`
  - `VOLCENGINE_MEMORY_CONFIG_JSON`
  - 或者改用简单参数：
  - `VOLCENGINE_MEMORY_NATIVE_COLLECTION_NAME`
  - `VOLCENGINE_MEMORY_NATIVE_USER_IDS_JSON`
  - `VOLCENGINE_MEMORY_NATIVE_TYPES_JSON`
  - `VOLCENGINE_MEMORY_API_*`
- 备用 ASR / TTS：
  - `VOLCENGINE_ASR_*`
  - `VOLCENGINE_TTS_*`
- 回调：
  - `VOLCENGINE_CALLBACK_BASE_URL`
- 收益调价 MCP：
  - `REVENUE_MCP_ENABLED`
  - `REVENUE_MCP_SSE_URL`
  - `REVENUE_MCP_API_HEALTH_URL`
  - `REVENUE_MCP_DEFAULT_STORE_ID`
  - `REVENUE_MCP_CONFIRMATION_TTL_SECONDS`
- 知识库：
  - `RAGFLOW_SEARCH_URL`
  - `RAGFLOW_API_KEY`
  - `RAGFLOW_DATASET_ID`

## 当前路由原则

- `S2S` 负责：
  - 迎宾
  - 寒暄
  - 自我介绍
  - 能力介绍
  - 低风险自然对话
  - 低风险酒店问答
- 后端负责：
  - 早餐、停车、发票、入住、退房、续住、路线、位置、楼层、设施、用品、会议室、收费、价格、政策、时间
  - 高风险酒店事实
  - 工具查询、兜底、转人工
  - 收益调价、经营摘要、策略复盘、执行确认
- 每一轮只有一个内容所有者，后端接管时通过 `ExternalTextToSpeech` 让同一个 AI 开口，不允许双链抢话
- 收益调价链默认规则：
  - 调价策略、最新结果、经营摘要、昨日复盘走后端收益 MCP
  - 高风险执行采用显式双确认
  - `S2S` 不直接调用调价工具

## 调试与验证接口

- `GET /api/health`
- `GET /api/validate/config-groups`
- `GET /api/validate/callback-manifest`
- `GET /api/validate/ragflow`
- `GET /api/validate/memory`
- `GET /api/validate/revenue-mcp`
- `GET /api/validate/revenue-mcp/tools/{tool_name}`
- `GET /api/validate/faq-v2/query`
- `GET /api/validate/faq-v2/benchmark`
- `GET /api/validate/voice-chat-payload`
- `POST /api/bootstrap`
- `POST /api/rtc/sessions/{session_id}/connected`
- `POST /api/rtc/sessions/{session_id}/start`
- `POST /api/rtc/sessions/{session_id}/stop`
- `GET /api/rtc/sessions/{session_id}/events`
- `POST /api/rtc/sessions/{session_id}/presence`
- `POST /api/rtc/sessions/{session_id}/utterances`
- `POST /api/rtc/sessions/{session_id}/interrupt`
- `POST /api/volcengine/callbacks/subtitles`
- `POST /api/volcengine/callbacks/state`
- `POST /api/volcengine/callbacks/task`

## 本地文档基线

- 参数矩阵：`docs/PARAMETER_MATRIX.md`
- 火山官方参考快照：`docs/vendor/volcengine/`

## 当前外部阻塞项

- `RAGFLOW_*` 还未补齐时，系统会继续使用本地 FAQ fallback
- 调价链虽然已经接上 SSE MCP，但具体门店策略生成是否成功，仍受 `'/Users/sky/Project/New project voice'` 当前数据、PMS 约束和收益后端状态影响

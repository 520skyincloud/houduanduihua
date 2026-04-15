# 丽斯未来酒店项目实时对话式 AI 方案

## 1. 文档目的

本文档是当前项目接入火山引擎实时对话式 AI 的总方案文档，统一说明：

- 当前项目目标架构
- 火山控制台参数与项目参数的映射关系
- 每一组参数的用途与连通性测试方法
- 当前项目的主链、后端接管链、收益链和展示层边界
- 开发时可直接参照的官方 Demo 与本地代码入口

本文档的目标不是只写概念，而是让后续开发、联调和测试都能直接按文档执行。

---

## 2. 当前结论

当前项目的正式目标方案固定为双链结构：

- 主链：`RTC + StartVoiceChat(2024-12-01) + S2S + MemoryConfig`
- 接管链：`后端 FAQ / RAG / 强规则 / 收益调价 MCP / ExternalTextToSpeech`

固定原则：

- 每一轮只能有一个内容所有者
- 低风险自然对话优先走实时对话式 AI 主链
- 敏感酒店事实和高风险业务必须切后端
- 高风险执行动作不得由 S2S 直接完成
- 任意时刻都必须支持从灰度档回退到安全档

---

## 3. 产品层区别：实时对话式 AI vs 实时音视频 RTC

这两个能力不是“同一个东西换个名字”，而是**上下层关系**：

- `实时音视频 RTC`
  - 负责建房、进房、音视频采集、传输、播放、弱网对抗、字幕消息承载
  - 本质上是低时延通信与媒体传输底座
  - 不天然等于“会说话的 AI”

- `实时对话式 AI`
  - 运行在 RTC 场景之上的 AI 对话产品能力
  - 负责 `StartVoiceChat / UpdateVoiceChat / StopVoiceChat`
  - 负责 `S2SConfig / MemoryConfig / LLMConfig / ASRConfig / TTSConfig`
  - 负责 `VoiceChat` 任务、对话状态、打断、记忆、外部播报、Function Calling 等 AI 会话能力
  - 本质上是“把 RTC、ASR、TTS、LLM、记忆和工具编排成一套实时 AI 对话服务”

因此当前项目里：

- `RTC` 是媒体和传输底座
- `实时对话式 AI` 是 AI 会话与编排主链
- 两者会一起出现，但不是同一层概念

需要避免的误区：

- 不能把“RTC AppId/AppKey”当成“实时对话式 AI 应用 AppId/AppKey”
- 不能把“RTC 建房成功”误认为“AI 会话一定能正常工作”
- 不能把“能收发音频”误认为“Memory、S2S、回调、外部播报都已经配置完成”

对本项目的直接影响：

- 如果只验证了 RTC，说明“音视频链路通了”
- 如果验证了 `StartVoiceChat + S2S + Memory + 回调`，才说明“实时对话式 AI 主链通了”
- 如果再验证了后端 FAQ / 收益 MCP / 外部播报，才说明“双链完整交付链路通了”

---

## 4. 开发参照 Demo

开发过程中明确将以下仓库作为联调和参数组织参考：

- 参照项目：[volcengine/rtc-aigc-demo](https://github.com/volcengine/rtc-aigc-demo)

这个 Demo 的参考价值：

- RTC 进房与实时音频链路组织方式
- VoiceChat 场景配置和参数组织方式
- 前后端联调启动顺序
- `RoomId`、`Token`、`StartVoiceChat` 常见问题排查方式
- 场景化配置文件的组织思路

不直接照搬的部分：

- 酒店知识问答边界
- 后端 FAQ / RAG / 强规则接管逻辑
- 收益调价 MCP 双确认
- 自研 3D 数字人主舞台
- 生产灰度与回退策略

使用方式：

- 把它当作火山链路快速跑通参考
- 不把它当作本项目的最终业务架构蓝本

---

## 5. 已确认的实时对话式 AI 控制台参数

根据截图 `截屏2026-04-15 16.59.49.png`，当前“实时对话式 AI -> 应用管理”里已经有一组应用参数：

| 项目 | 当前值 | 用途 |
| --- | --- | --- |
| 应用名称 | `defaultAppName` | 控制台识别用，便于与导出的场景配置对应 |
| 实时对话式 AI AppId | `69d874fc213d3e017a150c5a` | 作为控制台应用身份对照项，后续联调时用于核对导出的 S2S 配置来源 |
| 实时对话式 AI AppKey | `48b5e123...37839fd` | 作为控制台应用密钥对照项，实际完整值应保存在本地 `.env` 或安全存储，不建议完整写入仓库文档 |

重要说明：

- 这组“实时对话式 AI 应用管理”参数要写进联调文档，方便测试时逐项核对。
- 但它们不等于 RTC 的 `AppId/AppKey`。
- 它们也不等于“实时语音快捷 API 接入”里的独立 API Key。
- 当前项目代码里真正直接读取的是：
  - `VOLCENGINE_RTC_APP_ID`
  - `VOLCENGINE_RTC_APP_KEY`
  - `VOLCENGINE_S2S_CONFIG_JSON`
  - 或 `VOLCENGINE_S2S_APP_ID + VOLCENGINE_S2S_TOKEN + VOLCENGINE_S2S_MODEL`
  - `VOLCENGINE_REALTIME_API_KEY`

因此，这组截图参数在当前项目里的定位是：

- 控制台应用对照项
- 配置来源核对项
- 联调排障时的基础信息

不是直接把它们原样硬编码进仓库代码。

---

## 6. 项目总体架构

### 6.1 主链

主链固定采用：

- RTC 建房和进房
- `StartVoiceChat(2024-12-01)`
- `S2SConfig`
- `MemoryConfig`
- 火山字幕 / 状态回调

主链负责：

- 迎宾
- 寒暄
- 自我介绍
- 能力介绍
- 低风险酒店问答
- 连续自然交流

### 6.2 后端接管链

后端负责：

- FAQ
- RAGFlow
- 强规则
- 高风险酒店事实
- 收益调价 MCP
- 双确认执行
- 外部 TTS 播报

### 6.3 展示层

展示层固定为：

- 自研 3D 数字人主舞台
- RTC 远端视频备用层

约束：

- RTC 远端视频不能覆盖主容器
- 无 3D 组件时页面也要能跑
- 字幕区、状态区、播报区、调试区必须独立存在

---

## 7. 对话所有权边界

### 7.1 S2S + Memory 优先负责

- 迎宾
- 寒暄
- 自我介绍
- 能力介绍
- 低风险自然对话
- 低风险酒店知识问答

### 7.2 后端强制接管

- 早餐
- 停车
- 发票
- 入住
- 退房
- 续住
- 路线
- 位置
- 楼层
- 设施
- 用品
- 会议室
- 收费
- 价格
- 政策
- 时间
- 收益调价
- 经营摘要
- 策略复盘
- 执行确认
- 执行拒绝

### 7.3 固定规则

- 同一轮不允许 S2S 和后端同时说话
- 用户打断优先级最高
- 旧轮结果不得插播新轮
- 后端接管后仍通过同一个 AI 形象播报

---

## 8. 控制台参数与项目变量映射

### 8.1 RTC 参数

| 控制台 / 来源 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| RTC 应用 AppId | `VOLCENGINE_RTC_APP_ID` | 前端 RTC 建引擎、后端 `StartVoiceChat` 顶层 `AppId` | `GET /api/health`、`POST /api/bootstrap`、页面 `joinRoom` |
| RTC 应用 AppKey | `VOLCENGINE_RTC_APP_KEY` | 后端生成 RTC Token | `POST /api/bootstrap` 后检查是否生成 `rtc.token` |

### 8.2 OpenAPI 参数

| 控制台 / 来源 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| IAM AccessKey ID | `VOLCENGINE_ACCESS_KEY_ID` | 调 `StartVoiceChat / UpdateVoiceChat / StopVoiceChat` | `POST /api/rtc/sessions/{session_id}/start` |
| IAM Secret Access Key | `VOLCENGINE_SECRET_ACCESS_KEY` | 同上 | `POST /api/rtc/sessions/{session_id}/stop` |

### 8.3 实时对话式 AI 应用管理参数

| 控制台项 | 当前值 | 建议项目落点 | 当前用途 | 验证方式 |
| --- | --- | --- | --- | --- |
| 应用名称 | `defaultAppName` | 文档记录，不进代码 | 用于和控制台导出的场景配置、应用归属做人工核对 | 控制台人工核对 |
| 实时对话式 AI AppId | `69d874fc213d3e017a150c5a` | 对照 `VOLCENGINE_S2S_CONFIG_JSON` 或 `VOLCENGINE_S2S_APP_ID` 的来源 | 用于确认当前 S2S / 实时对话能力属于哪个控制台应用 | `GET /api/validate/voice-chat-payload`，核对 `S2SConfig` 来源 |
| 实时对话式 AI AppKey | 本地保存，文档只保留掩码 | 本地密钥，不建议直接写仓库 | 作为控制台联调参考和配置来源核对项 | 本地对照控制台，确认未抄错，必要时结合官方流程导出或生成可用配置 |

说明：

- 当前仓库没有直接读取“实时对话式 AI AppKey”的专用环境变量。
- 本项目当前更适合通过以下方式接主链：
  - `VOLCENGINE_S2S_CONFIG_JSON`
  - 或 `VOLCENGINE_S2S_APP_ID + VOLCENGINE_S2S_TOKEN + VOLCENGINE_S2S_MODEL`
- 因此这里把控制台 AppId / AppKey 写进方案文档，主要是为了联调和排障更快，而不是要求把它们直接硬塞进现有代码。

### 8.4 实时语音 / S2S 主链参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| VoiceChat 版本 | `VOLCENGINE_VOICE_CHAT_VERSION=2024-12-01` | 固定使用支持长期记忆的版本 | `GET /api/validate/voice-chat-payload` |
| 启用 S2S | `VOLCENGINE_ENABLE_S2S=true` | 主链开关 | `GET /api/validate/config-groups` |
| S2S 配置 JSON | `VOLCENGINE_S2S_CONFIG_JSON` | 直接透传官方 S2S 配置 | `GET /api/validate/voice-chat-payload`，检查 `Config.S2SConfig` |
| S2S AppId | `VOLCENGINE_S2S_APP_ID` | 简化模式下构造 `S2SConfig` | `GET /api/validate/voice-chat-payload` |
| S2S Token | `VOLCENGINE_S2S_TOKEN` | 简化模式下构造 `S2SConfig` | `POST /api/rtc/sessions/{session_id}/start` |
| S2S 模型 | `VOLCENGINE_S2S_MODEL` | 指定主链模型 | 首答、连续对话、打断联调 |
| 快速 API Key | `VOLCENGINE_REALTIME_API_KEY` | 快速接入参考，不替代 RTC AppId/AppKey | 控制台核对 + 文档对照；如走独立链路，单独验证 |

### 8.5 LLM 参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| LLM 模式 | `VOLCENGINE_LLM_MODE` | 构造 `LLMConfig.Mode` | `GET /api/validate/voice-chat-payload` |
| Endpoint ID | `VOLCENGINE_LLM_ENDPOINT_ID` | 主链模型端点 | `POST /api/rtc/sessions/{session_id}/start` 后实际对话测试 |
| Model Name | `VOLCENGINE_LLM_MODEL_NAME` | 记录用途，当前主要用于文档和对照 | 控制台核对 + 对话联调 |

### 8.6 长期记忆参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| 启用记忆 | `VOLCENGINE_ENABLE_MEMORY=true` | 打开 `MemoryConfig` | `GET /api/validate/config-groups` |
| 记忆配置 JSON | `VOLCENGINE_MEMORY_CONFIG_JSON` | 直接透传官方 MemoryConfig | `GET /api/validate/voice-chat-payload` |
| 原生集合名 | `VOLCENGINE_MEMORY_NATIVE_COLLECTION_NAME` | 原生记忆检索范围 | `GET /api/validate/voice-chat-payload` |
| 用户范围 | `VOLCENGINE_MEMORY_NATIVE_USER_IDS_JSON` | 限定用户记忆范围 | 连续多轮追问测试 |
| 类型范围 | `VOLCENGINE_MEMORY_NATIVE_TYPES_JSON` | 限定记忆类型 | 连续多轮追问测试 |
| 后端记忆 API URL | `VOLCENGINE_MEMORY_API_BASE_URL` | 后端 Memory API fallback | `GET /api/validate/memory` |
| 后端记忆 API Key | `VOLCENGINE_MEMORY_API_KEY` | 调记忆 REST API | `GET /api/validate/memory` |
| 记忆工程名 | `VOLCENGINE_MEMORY_PROJECT_NAME` | 记忆 API 检索范围 | `GET /api/validate/memory` |
| 记忆集合名 | `VOLCENGINE_MEMORY_COLLECTION_NAME` | 记忆 API 检索范围 | `GET /api/validate/memory` |

### 8.7 ASR / TTS 备用链参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| ASR AppId | `VOLCENGINE_ASR_APP_ID` | S2S 缺失时备用识别链 | 关闭 S2S 后 `POST /start` |
| ASR Token | `VOLCENGINE_ASR_ACCESS_TOKEN` | 同上 | 关闭 S2S 后 `POST /start` |
| ASR Secret | `VOLCENGINE_ASR_SECRET_KEY` | 同上 | 关闭 S2S 后 `POST /start` |
| TTS AppId | `VOLCENGINE_TTS_APP_ID` | 备用播报链 | 关闭 S2S 后 `POST /start` |
| TTS Token | `VOLCENGINE_TTS_ACCESS_TOKEN` | 同上 | 关闭 S2S 后 `POST /start` |
| TTS Secret | `VOLCENGINE_TTS_SECRET_KEY` | 同上 | 关闭 S2S 后 `POST /start` |
| TTS Voice Type | `VOLCENGINE_TTS_VOICE_TYPE` | 备用语音人设 | 关闭 S2S 后播报试听 |

### 8.8 回调参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| 回调基址 | `VOLCENGINE_CALLBACK_BASE_URL` | 拼接 voicechat / subtitles / state / task 回调地址 | `GET /api/validate/callback-manifest` |
| 回调密钥 | `VOLCENGINE_CALLBACK_SECRET` | 预留校验能力 | 公网回调联调 |

### 8.9 前端 SDK 和页面参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| RTC Web SDK URL | `VOLCENGINE_FRONTEND_SDK_URL` | 前端动态加载 RTC SDK | 页面加载 + `joinRoom` |
| 自研 3D 挂载模式 | `SELF_AVATAR_MODE` | 前端舞台策略 | 页面加载验证 |
| 自研 3D 挂载点 | `SELF_AVATAR_MOUNT_ID` | 前端组件挂载点 | 页面加载验证 |

### 8.10 收益调价 MCP 参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| MCP 开关 | `REVENUE_MCP_ENABLED` | 启用收益链 | `GET /api/validate/revenue-mcp` |
| SSE URL | `REVENUE_MCP_SSE_URL` | 连接收益 MCP | `GET /api/validate/revenue-mcp` |
| 健康检查 URL | `REVENUE_MCP_API_HEALTH_URL` | 检查外部服务健康 | `GET /api/validate/revenue-mcp` |
| 默认门店 | `REVENUE_MCP_DEFAULT_STORE_ID` | 调价默认作用门店 | `health_overview` 工具验证 |
| 确认 TTL | `REVENUE_MCP_CONFIRMATION_TTL_SECONDS` | 双确认有效期 | 调价确认流联调 |

### 8.11 RAGFlow 参数

| 参数 | 项目变量 | 当前用途 | 验证方式 |
| --- | --- | --- | --- |
| 搜索地址 | `RAGFLOW_SEARCH_URL` | 后端知识检索 | `GET /api/validate/ragflow` |
| API Key | `RAGFLOW_API_KEY` | 调 RAGFlow | `GET /api/validate/ragflow` |
| 数据集 ID | `RAGFLOW_DATASET_ID` | 限定知识集 | FAQ 问题回归测试 |

---

## 9. 逐项连通性测试清单

### 9.1 RTC 连通性

依次验证：

1. `GET /api/health`
2. `POST /api/bootstrap`
3. 页面 `joinRoom`
4. 检查前端是否拿到 `rtc.app_id`、`rtc.room_id`、`rtc.token`

通过标准：

- 页面不再显示“RTC 参数未配置”
- RTC 可正常进房

### 9.2 VoiceChat 启动连通性

依次验证：

1. `GET /api/validate/voice-chat-payload`
2. `POST /api/rtc/sessions/{session_id}/start`
3. `POST /api/rtc/sessions/{session_id}/stop`

通过标准：

- `payload.Config` 中能看到主链配置
- `start` 成功
- `stop` 成功

### 9.3 S2S 主链连通性

依次验证：

1. 主链启动成功
2. 发送简单闲聊问题
3. 观察首答
4. 观察连续对话
5. 观察打断

通过标准：

- 能自然首答
- 打断有效
- 多轮不乱序

### 9.4 记忆连通性

依次验证：

1. `GET /api/validate/config-groups`
2. `GET /api/validate/memory`
3. 连续多轮追问相同主题

通过标准：

- `memory_ready` 为真
- Memory API 可返回结果
- 连续追问中能体现上下文延续

### 9.5 回调连通性

依次验证：

1. `GET /api/validate/callback-manifest`
2. 检查 `voicechat / subtitles / state / task` 四个地址
3. 实际对话时观察是否回调进来

通过标准：

- 地址完整
- 公网可访问
- 接口在 5 秒内返回 `200`

### 9.6 收益链连通性

依次验证：

1. `GET /api/validate/revenue-mcp`
2. `GET /api/validate/revenue-mcp/tools/health_overview`
3. `GET /api/validate/revenue-mcp/tools/generate_current_pricing_strategy`
4. `GET /api/validate/revenue-mcp/tools/get_latest_execution_summary`

通过标准：

- 工具列表可访问
- 调价预演可返回
- 最新执行摘要可返回

### 9.7 RAGFlow 连通性

依次验证：

1. `GET /api/validate/ragflow`
2. 用 FAQ 高频问题回归

通过标准：

- 搜索地址可用
- FAQ 问题命中率和耗时可接受

### 9.8 实时对话式 AI 应用管理参数核对

依次验证：

1. 人工核对控制台应用名称是否为 `defaultAppName`
2. 人工核对控制台 AppId 是否为 `69d874fc213d3e017a150c5a`
3. 本地确认 AppKey 已保存，且未误写到仓库
4. `GET /api/validate/voice-chat-payload`，确认当前 `S2SConfig` 来源与控制台应用一致

通过标准：

- 控制台与本地配置来源一致
- 当前联调使用的应用身份明确
- 不出现“调的是另一个应用，但自己不知道”的情况

---

## 10. 功能与测试对应关系

| 功能 | 所有者 | 关键参数 | 测试方式 |
| --- | --- | --- | --- |
| 迎宾 | S2S | RTC、VoiceChat、TTS | `POST /api/rtc/sessions/{session_id}/presence` |
| 自我介绍 | S2S | S2S、LLM | 页面手动提问 |
| 低风险自然对话 | S2S | S2S、LLM、Subtitle | 连续闲聊与打断 |
| 低风险酒店问答 | S2S + Memory | S2S、Memory | 多轮 FAQ 追问 |
| 敏感酒店事实 | Backend | FAQ / RAG / 强规则 | `POST /api/rtc/sessions/{session_id}/utterances` |
| 收益调价预演 | Backend | Revenue MCP | 调价策略问题 |
| 收益执行确认 | Backend | Revenue MCP、TTL | “按这个策略执行” |
| 收益拒绝 | Backend | Revenue MCP、TTL | “取消这次调价执行” |
| 外部播报 | Backend | TTS / ExternalTextToSpeech | 后端接管问题测试 |
| 自研 3D 展示层 | Frontend | 挂载点、RTC 备用层 | 页面加载和组件挂载测试 |

---

## 11. 运行模式建议

### 11.1 gray-s2s-memory

用于灰度验证：

- `VOLCENGINE_PRIMARY_DIALOG_PATH=s2s`
- `VOLCENGINE_FAQ_ROUTE_MODE=s2s_memory`
- `VOLCENGINE_USE_BACKEND_FALLBACK=true`

### 11.2 prod-safe-backend

用于稳定生产：

- FAQ 优先后端
- S2S 主要承担自然对话

### 11.3 rollback-backend

用于回退：

- 保留 RTC 和会话外壳
- 主要回答链退回后端
- 只改环境变量，不改代码

---

## 12. 当前仓库中的关键实现入口

建议联调时优先查看：

- `app/main.py`
- `app/config.py`
- `app/integrations/volcengine/voice_chat.py`
- `app/integrations/volcengine/openapi.py`
- `app/services/search.py`
- `app/services/revenue_mcp.py`
- `app/services/lobby.py`
- `app/static/app.js`
- `.env.example`
- `docs/PARAMETER_MATRIX.md`
- `docs/TEST_PLAN.md`

---

## 13. 推荐联调顺序

建议按以下顺序推进：

1. 先核对控制台应用参数、RTC 参数、OpenAPI 参数
2. 跑通 `bootstrap -> joinRoom -> start`
3. 验证 `S2S + Memory` 主链
4. 验证后端接管问题
5. 验证收益调价预演和双确认
6. 验证回调和时延
7. 验证自研 3D 舞台和 RTC 备用层

---

## 14. 最终落地标准

本项目“实时对话式 AI 方案可用”的完成标准是：

- 控制台应用参数、项目参数、代码入口三者能对应上
- 每一组参数都有明确用途
- 每一组参数都有对应的连通性测试
- S2S 主链、后端接管链、收益链、前端展示层都能独立验证
- 当某一条链路失败时，系统能明确告警并可回退

最终目标不是只跑通一个 Demo，而是形成一套：

- 可开发
- 可联调
- 可测试
- 可排障
- 可回退

的实时对话式 AI 方案。

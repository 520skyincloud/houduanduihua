# 丽斯未来酒店展厅对话后端

酒店展厅数字人实时语音对话后端，负责把火山 RTC / VoiceChat、酒店知识问答、收益调价 MCP、字幕回调和前端舞台页串成一套可联调系统。

## 项目定位

这个仓库不是单纯的网页 Demo，也不是单纯的 FAQ 服务。

它当前承担的是一套完整的“展厅数字人后端”能力：

- 火山 RTC 进房、媒体链路与 VoiceChat 会话启动
- 原生实时闲聊与后端接管式播报共存
- 酒店固定事实问题走 FastGPT 检索
- 收益分析、调价方案、飞书推送走 MCP
- 前端 `stage` 舞台页与大厅页联调
- 字幕、状态、回调、打断、轮次所有权统一编排

## 当前架构

当前系统不是“一个模型包打天下”，而是多链路协同：

### 1. 原生实时对话链

- 火山 `RTC + StartVoiceChat`
- 主要负责：
  - 迎宾
  - 自我介绍
  - 闲聊
  - 轻引导
  - 低风险自然对话

### 2. 酒店知识链

- 用户问题
- `Hotel 后端`
- `FastGPT /api/core/dataset/searchTest`
- 后端整理成 `display_text / speak_text`
- 再通过同一 VoiceChat 会话播报

这条链只负责酒店固定事实类问题，例如：

- 早餐
- 停车
- 发票
- 入住退房
- 楼层路线
- 设施用品
- 房间设备
- 会议室

### 3. 收益调价链

- 由后端统一识别收益意图
- 通过 SSE 方式连接本地 `mcp2`
- 支持：
  - 收益分析
  - 昨日复盘
  - 调价方案
  - 飞书推送类动作

高风险执行动作仍然保持后端可控，不交给原生实时链自由调用。

## 当前能力边界

### 已接通

- RTC 房间接入
- VoiceChat 启动 / 停止 / 中断
- 酒店知识问答接 FastGPT
- 收益 MCP 接 `mcp2`
- `stage` 舞台页
- 客户端 RTC 字幕解析
- 火山回调接收

### 正在持续优化

- 原生链字幕回流稳定性
- 前端字幕渲染效果
- 打断时序与多轮不抢话
- FastGPT 检索准确率
- 原生视觉理解闭环

## 技术栈

- Python
- FastAPI
- Uvicorn
- 火山引擎 RTC / VoiceChat
- FastGPT
- MCP over SSE
- 原生前端页面（大厅页 + 舞台页）

## 页面入口

- 大厅页：`/`
- 舞台页：`/stage`

默认本地端口：

```text
16000
```

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 16000 --reload
```

浏览器打开：

- `http://127.0.0.1:16000/`
- `http://127.0.0.1:16000/stage`

## 配置说明

运行时统一读取：

- `.env`

配置模板：

- `.env.example`

### 关键配置分组

#### 火山 RTC / VoiceChat

- `VOLCENGINE_RTC_APP_ID`
- `VOLCENGINE_RTC_APP_KEY`
- `VOLCENGINE_ACCESS_KEY_ID`
- `VOLCENGINE_SECRET_ACCESS_KEY`
- `VOLCENGINE_REALTIME_API_KEY`
- `VOLCENGINE_CALLBACK_BASE_URL`

#### 主对话链

- `VOLCENGINE_PRIMARY_DIALOG_PATH`
- `VOLCENGINE_VOICE_CHAT_VERSION`
- `VOLCENGINE_LLM_*`
- `VOLCENGINE_ASR_*`
- `VOLCENGINE_TTS_*`

#### 酒店知识问答

- `FASTGPT_ENABLED`
- `FASTGPT_BASE_URL`
- `FASTGPT_USERNAME`
- `FASTGPT_PASSWORD`
- `FASTGPT_DATASET_ID`

#### 收益 MCP

- `REVENUE_MCP_ENABLED`
- `REVENUE_MCP_SSE_URL`
- `REVENUE_MCP_API_HEALTH_URL`
- `REVENUE_MCP_DEFAULT_STORE_ID`

#### 可选能力

- `VOLCENGINE_LLM_WEBSEARCH_*`
- `VOLCENGINE_LLM_VISION_*`
- `VISION_ANALYSIS_*`

## 核心接口

### 会话与房间

- `POST /api/bootstrap`
- `POST /api/rtc/sessions/{session_id}/connected`
- `POST /api/rtc/sessions/{session_id}/start`
- `POST /api/rtc/sessions/{session_id}/stop`
- `GET /api/rtc/sessions/{session_id}`
- `GET /api/rtc/sessions/{session_id}/events`

### 对话控制

- `POST /api/rtc/sessions/{session_id}/utterances`
- `POST /api/rtc/sessions/{session_id}/interrupt`
- `POST /api/rtc/sessions/{session_id}/presence`

### 校验与调试

- `GET /api/health`
- `GET /api/validate/config-groups`
- `GET /api/validate/callback-manifest`
- `GET /api/validate/voice-chat-payload`
- `GET /api/validate/fastgpt`
- `GET /api/validate/revenue-mcp`
- `GET /api/validate/revenue-mcp/tools/{tool_name}`

### 回调

- `POST /api/volcengine/callbacks/voicechat`
- `POST /api/volcengine/callbacks/subtitles`
- `POST /api/volcengine/callbacks/state`
- `POST /api/volcengine/callbacks/task`

## 收益语音触发词

当前后端已经明确支持这些主触发词：

- `来个调价方案`
- `来个收益分析`
- `来个昨日复盘`

当前也支持这些推送类说法：

- `来个飞书测试`
- `来个经营摘要`
- `来个昨日复盘推送`

## 目录结构

```text
app/
  integrations/    火山相关接入
  services/        FastGPT / Revenue MCP / 搜索 / 视觉 / 协调逻辑
  static/          前端脚本与舞台资源
  templates/       大厅页与舞台页模板
docs/              项目设计与接入文档
data/              本地数据与调试素材
scripts/           辅助脚本
```

## 当前仓库适合谁看

- 需要接酒店展厅数字人的后端同学
- 需要联调火山 RTC / VoiceChat 的同学
- 需要接 FastGPT 做酒店知识问答的同学
- 需要把收益分析 / 调价方案接进语音链的同学

## GitHub 仓库简介建议

可以把 GitHub 仓库简介写成这句：

```text
酒店展厅数字人实时对话后端，集成火山 RTC / VoiceChat、FastGPT 酒店知识问答与收益 MCP。
```

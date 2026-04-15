# 原生知识、MCP 与当前策略

## 官方能力范围

- 火山实时对话式 AI 的进阶能力里包含：
  - 知识库 / RAG
  - MCP
  - Function Calling
  - 联网问答 Agent

## 当前项目策略

- 首版不把 `MCP / Function Calling` 放进热路径
- 原因不是官方不支持，而是当前业务实测里：
  - 端到端工具调用成功率不够稳
  - 酒店知识问题需要更强可控性
- 因此：
  - 主热路径先用 `S2S + backend handoff`
  - 原生知识 / MCP 走单独验证线

## 后续验收方向

- 若原生知识命中率和时延足够好，可替代部分 FAQ 后端链
- 若 MCP 成功率达标，再考虑接入正式热路径
- 实时语音“快捷 API 接入”页面给出的 API Key 是独立服务密钥，不替代 RTC AppId/AppKey

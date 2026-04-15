# StartVoiceChat（2024-12-01）参考

## 为什么固定到 2024-12-01

- 当前项目要验证 **S2S 主链 + 长期记忆**。
- 官方文档明确指出：**长期记忆仅支持 `StartVoiceChat（2024-12-01）`，不支持 `2025-06-01`**。
- 因此当前控制面版本固定为 `VOLCENGINE_VOICE_CHAT_VERSION=2024-12-01`。

## 当前项目里的负载策略

- 顶层固定保留：
  - `AppId`
  - `RoomId`
  - `TaskId`
  - `AgentConfig`
  - `Config`
- `Config` 内按双模式选择：
  - 有 `VOLCENGINE_S2S_CONFIG_JSON` 时，走 `Config.S2SConfig`
  - 否则回落到 `ASRConfig + TTSConfig + LLMConfig`
- 若提供 `VOLCENGINE_MEMORY_CONFIG_JSON`，则在顶层附加 `MemoryConfig`

## 当前项目里已经固化的规则

- `AgentConfig.WelcomeMessage` 由 `.env` 的 `GREETING_TEXT` 控制
- `SubtitleConfig.SubtitleMode` 固定为 `1`
- `InterruptMode` 固定由后端控制，避免后端链和 S2S 链抢话
- 若官方控制台后续导出完整 JSON，可直接写进 `VOLCENGINE_VOICE_CHAT_OVERRIDES_JSON`

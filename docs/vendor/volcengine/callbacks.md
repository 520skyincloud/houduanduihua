# 回调接收参考

## 官方要求

- 回调接口应尽快返回
- 常规要求是在 **5 秒内返回 200**
- 需要考虑火山重试，不能因为重复回调导致重复播报

## 当前项目的本地固定地址

当 `VOLCENGINE_CALLBACK_BASE_URL` 配好后，固定映射为：

- `/api/volcengine/callbacks/subtitles`
- `/api/volcengine/callbacks/state`
- `/api/volcengine/callbacks/task`

## 当前项目的处理规则

- 所有回调先快速确认，再按 `session_id / room_id / task_id` 归档
- 回调内容进入 SSE 事件流，便于前端联调观察
- 旧 turn 的迟到结果不能污染当前轮次

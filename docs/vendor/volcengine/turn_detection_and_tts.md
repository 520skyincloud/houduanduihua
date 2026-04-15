# 判停、过渡语与自定义播报

## 官方结论

- `TurnDetectionMode=1` 适合需要精确控制交互流程的场景
- `paragraph=true` 的完整句更适合作为后端知识链的触发点
- `ExternalTextToSpeech` 适合等待提示、流程播报、后端接管答案

## 当前项目的实现规则

- 用户句末后：
  - 先做轻路由
  - 如果这一轮归后端，`250ms` 内没有正式答案就发一次过渡语
- 过渡语固定通过 `ExternalTextToSpeech` 下发，不让 S2S 临场补句
- 正式答案仍走 `ExternalTextToSpeech`
- 打断优先级：
  - 用户新语音输入
  - 正式答案
  - 过渡语
  - 欢迎词

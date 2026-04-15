# 火山记忆库接入文档

## 1. 适用范围

本文档说明当前项目如何接入火山官方记忆库 API，并使用已经跑通的酒店记忆库参数完成：

- 记忆写入：`/api/memory/session/add`
- 记忆检索：`/api/memory/search`
- 对话上下文获取：`/api/memory/get_context`

这份文档对应的是“后端 Memory API 直连官方记忆库”的方式，不是收益调价 `SSE MCP`。

## 2. 当前记忆库参数

当前项目已验证通过的记忆库配置如下：

| 项目 | 值 |
| --- | --- |
| 区域 | `cn-beijing` |
| `project_name` | `default` |
| `collection_name` | `jiudianwenti` |
| 默认 `user_id` | `hotel_lobby_user` |
| 写入示例 `assistant_id` | `hotel_faq_assistant` |
| 写入示例 `assistant_name` | `丽斯未来酒店FAQ` |
| 写入接口 | `https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/session/add` |
| 检索接口 | `https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/search` |
| 上下文接口 | `https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/get_context` |

说明：

- `VOLCENGINE_MEMORY_API_KEY` 使用当前 `.env` 中的火山记忆库密钥，不建议在文档或代码中写死。
- 本项目已验证命中的记忆类型是 `event_v1` / `profile_v1`。

## 3. 你应该怎么理解这套 API

### 3.1 `session/add`

作用：把一段对话写入官方记忆库。

最常见的写法是一组问答对应一段会话：

- `user`：问题
- `assistant`：答案

### 3.2 `search`

作用：拿一句查询语去记忆库里检索相似记忆，适合做：

- FAQ 命中验证
- top1 / top3 召回评估
- 直接查看命中了哪条历史问答

### 3.3 `get_context`

作用：把相关记忆拼成上下文，返回给模型或后端继续生成回答。

它不是单独的聊天模型，更像：

`用户提问 -> 记忆库取回相关记忆 -> 模型基于记忆继续回答`

## 4. 环境变量

建议统一使用 `.env` 注入：

```env
VOLCENGINE_MEMORY_API_KEY=你的记忆库密钥
VOLCENGINE_MEMORY_PROJECT_NAME=default
VOLCENGINE_MEMORY_COLLECTION_NAME=jiudianwenti
VOLCENGINE_MEMORY_DEFAULT_USER_ID=hotel_lobby_user
VOLCENGINE_MEMORY_API_BASE_URL=https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/get_context
```

如果你要做批量写入或单独检索，也可以再补：

```env
VOLCENGINE_MEMORY_ADD_API_URL=https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/session/add
VOLCENGINE_MEMORY_SEARCH_API_URL=https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/search
```

## 5. 单条写入示例

### 5.1 curl 写入一条酒店问答

```bash
curl -X POST 'https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/session/add' \
  -H "Authorization: Bearer $VOLCENGINE_MEMORY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "collection_name": "jiudianwenti",
    "project_name": "default",
    "session_id": "lis_south_station_demo_0001",
    "messages": [
      {
        "role": "user",
        "content": "有没有一次性剃须刀？",
        "time": 1776229884876
      },
      {
        "role": "assistant",
        "content": "酒店提供一次性剃须刀，该物品放置在1020房间对面的洗衣房内。您可以根据自身需要自行取用。",
        "time": 1776229884877
      }
    ],
    "metadata": {
      "default_user_id": "hotel_lobby_user",
      "default_user_name": "酒店客人",
      "default_assistant_id": "hotel_faq_assistant",
      "default_assistant_name": "丽斯未来酒店FAQ",
      "time": 1776229884877
    }
  }'
```

建议：

- `session_id` 保持稳定，方便重复导入时覆盖同一条。
- `messages` 至少包含一轮 `user -> assistant`。
- `metadata.time` 建议和最后一条消息时间一致。

## 6. 检索示例

### 6.1 用 `search` 检查是否命中正确问答

```bash
curl -X POST 'https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/search' \
  -H "Authorization: Bearer $VOLCENGINE_MEMORY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "collection_name": "jiudianwenti",
    "project_name": "default",
    "query": "有没有一次性剃须刀？",
    "limit": 3,
    "filter": {
      "user_id": "hotel_lobby_user",
      "assistant_id": "hotel_faq_assistant",
      "memory_type": ["event_v1"]
    }
  }'
```

命中后重点看：

- `result_list[].session_id`
- `result_list[].score`
- `result_list[].memory_info.original_messages`
- `result_list[].memory_info.summary`

### 6.2 用 `get_context` 获取模型可消费的上下文

```bash
curl -X POST 'https://api-knowledgebase.mlp.cn-beijing.volces.com/api/memory/get_context' \
  -H "Authorization: Bearer $VOLCENGINE_MEMORY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "collection_name": "jiudianwenti",
    "project_name": "default",
    "conversation_id": "validation_conversation",
    "query": "有没有一次性剃须刀？",
    "event_search_config": {
      "filter": {
        "user_id": "hotel_lobby_user",
        "assistant_id": "hotel_faq_assistant",
        "memory_type": ["event_v1"]
      },
      "limit": 3
    },
    "profile_search_config": {
      "filter": {
        "user_id": "hotel_lobby_user",
        "memory_type": ["profile_v1"]
      },
      "limit": 1
    }
  }'
```

如果配置正确，返回里会有：

- `data.context`
- `data.context_parts`

## 7. Excel 批量导入

本项目已经提供了批量导入脚本：

- 脚本：`scripts/import_memory_sessions.py`

### 7.1 执行命令

```bash
.venv/bin/python scripts/import_memory_sessions.py \
  --input "/绝对路径/02-（丽斯高铁南站）-单问单答.xlsx" \
  --session-prefix lis_south_station_faq \
  --default-user-name "酒店客人" \
  --default-assistant-name "丽斯未来酒店FAQ" \
  --manifest-output data/memory_session_manifest_lis_south_station.jsonl \
  --concurrency 1 \
  --retries 6 \
  --throttle-seconds 0.2
```

### 7.2 这份脚本做了什么

- 直接读取 Excel 的 `Prompt` / `Completion`
- 一行问答生成一个独立 `session`
- 自动跳过空行
- 支持 `dry-run`
- 支持重试和节流，避免官方接口 `429`
- 落一份本地映射清单，方便追踪 `row_number -> session_id`

## 8. 批量验证

本项目提供了 100 条随机问答召回评测脚本：

- 脚本：`scripts/evaluate_memory_retrieval.py`

### 8.1 执行命令

```bash
.venv/bin/python scripts/evaluate_memory_retrieval.py \
  --limit 100 \
  --output data/memory_eval_100.json
```

### 8.2 当前已验证结果

基于本项目这次导入的数据，100 条随机测试结果为：

- `top1_exact_match = 96/100`
- `top3_contains_exact = 99/100`
- `no_hit = 0`

这说明当前记忆库已经具备较好的 FAQ 召回能力，但还不是“100% 标准话术一致”。

## 9. 在当前项目中的调用方式

### 9.1 后端 Memory API

项目中的后端封装在：

- `app/services/memory.py`

调用方式：

- `get_context(query, conversation_id, user_id)`

这条链适合做：

- 先取回记忆上下文
- 再交给模型继续生成回答

### 9.2 S2S 原生 MemoryConfig

项目里的 `StartVoiceChat` payload 也支持直接挂火山 `MemoryConfig`：

- `app/integrations/volcengine/voice_chat.py`

注意：

- 这是 S2S 端到端原生接法
- 它和后端 `Memory API` 不是一条链
- 当前项目策略仍然是“酒店固定 FAQ 由后端主控，记忆做辅助”

## 10. 接入建议

如果你的目标是“让系统像聊天一样记住历史问答”，建议：

- 用 `session/add` 持续写入会话
- 用 `get_context` 给模型补上下文

如果你的目标是“稳定回答酒店标准问题”，建议：

- FAQ / RAG 做主
- Memory API 做辅助召回或个性化补充

原因是：

- 记忆库更像“历史对话记忆”
- 不是严格的结构化知识库
- 命中后可能返回摘要或相近表达，不一定逐字等于标准答案

## 11. 排查清单

### 11.1 写入成功但查不到

先检查：

- `collection_name` 是否是 `jiudianwenti`
- `project_name` 是否是 `default`
- `user_id` / `assistant_id` 是否与写入时一致
- 检索时 `memory_type` 是否使用 `event_v1`

### 11.2 返回空上下文

先检查：

- `event_search_config.filter.memory_type`
- `profile_search_config.filter.memory_type`
- 是否把 `assistant_id` 过滤得过窄

### 11.3 批量导入报 `429`

解决方法：

- 降低并发
- 增加 `--throttle-seconds`
- 提高重试次数

## 12. 推荐最小流程

如果是第一次接入，建议按下面顺序走：

1. 先配置 `.env` 中的 `VOLCENGINE_MEMORY_API_KEY`
2. 用 `session/add` 写入 1 条样例问答
3. 用 `search` 验证是否能召回
4. 用 `get_context` 验证是否能得到上下文
5. 再跑 Excel 批量导入
6. 最后跑 100 条评测确认稳定性

按这个流程，可以最快确认“接口通了”“数据进去了”“检索能用了”。

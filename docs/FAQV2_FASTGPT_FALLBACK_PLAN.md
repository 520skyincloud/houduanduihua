# FAQv2 + FastGPT 严格兜底方案（基于当前主路现状优化版）

## 1. 目标

本方案不是从零重做 FAQ，而是在**当前已经上线的 FAQv2 主路**基础上，补一条严格受控的 FastGPT fallback。

当前目标不是“FAQv2 与 FastGPT 双主路并行竞争”，而是：

1. `FAQv2` 继续作为酒店 FAQ 主裁决链。
2. `FastGPT` 只在 `FAQv2` 明确 `miss` 时才参与兜底。
3. `FastGPT` 不允许覆盖 FAQv2 已命中的答案。
4. `FastGPT` 不允许抢占收益 MCP / 调价 / 复盘 / 确认执行等高优先级链路。
5. `FastGPT` 不承担转接决策，不替代 handoff 规则。

核心原则：

`FAQv2 是主路，FastGPT 只是最后一层语义补位，不是第二个主脑。`

---

## 2. 当前真实现状（按当前代码与运行态）

### 2.1 FAQv2 已不是实验骨架，而是当前 FAQ 主路

当前 `/Users/sky/Project/Hotel` 已经接入并运行 FAQv2：

- 查询入口：`faq_v2.query(user_text, limit=3)`
- 返回结构：
  - `decision: direct | clarify | miss`
  - `answer`
  - `confidence`
  - `top_match`
  - `normalizedQuery`
- 当前运行模式：`VOLCENGINE_FAQ_V2_MODE=direct`

对应代码：

- `/Users/sky/Project/Hotel/app/services/faq_v2/engine.py`
- `/Users/sky/Project/Hotel/app/services/faq_v2/types.py`
- `/Users/sky/Project/Hotel/app/main.py`

这意味着：

`FAQv2 已经在主路上，不再是 shadow，也不只是 gray。`

### 2.2 FAQv2 当前能力边界

根据三轮 1000 题优化和后续抽样回归，FAQv2 现在更适合承担：

- 酒店固定事实问答
- 高频模糊问法
- handoff / service 的结构化区分
- 未知设施类问题的 `miss`

但它仍可能在以下场景受益于 fallback：

- 极模糊、极口语的非模板问法
- FAQv2 当前词典未覆盖的长尾同义表达
- 子意图边界过近、FAQv2 给出 `miss` 的普通知识问题

### 2.3 当前 FAQ 主路外还有旧链残留

当前 FAQ 分支里仍保留：

- FAQv2
- faq_semantic
- exact FAQ
- 其它兜底路径

因此 FastGPT 不能粗暴并入，否则会进一步加剧：

- 路由优先级不清
- FAQ 命中源不透明
- 用户体感“怎么又换一种答案”

本方案的方向应该是：

`先收敛主链裁决顺序，再把 FastGPT 作为 miss-only fallback 接进去。`

---

## 3. 为什么旧版“双通道并行”方案不够适合现在

旧版文档的主要问题有三个：

### 3.1 不应该把 FAQv2 和 FastGPT 同时并行开跑

旧版建议：

- `faq_task` 与 `fastgpt_task` 同时启动

这在当前现状下并不理想，因为：

1. FAQv2 已经很快，很多问题几十毫秒就能给结果。
2. FastGPT 是 HTTP + 登录态 + 检索接口，天然更慢、更重。
3. 并行开跑会引入额外复杂性：
   - 请求风暴
   - 调试困难
   - 日志中无法一眼看出最终答案来源
4. 当前主路里还有收益 MCP / 调价 / 复盘等事务型指令，优先级必须更清晰，不能再增加一个并行竞争者。

### 3.2 `clarify` 不应该直接一刀切交给 FastGPT

旧版建议：

- `decision=clarify` 一律视为未命中，交给 FastGPT

这不适合当前 FAQv2，因为部分 `clarify` 其实反映的是：

- 同主题下多个子意图都合理
- FAQv2 已经识别到了正确领域，只是需要进一步澄清

如果此时直接交给 FastGPT，很容易让 FastGPT：

- 给一个貌似顺滑但实际越界的答案
- 覆盖 FAQv2 原本谨慎的边界判断

所以：

`clarify 不应默认交给 FastGPT，应该分层处理。`

### 3.3 FastGPT 不应参与高优先级控制链路

当前系统里优先级最高的不是 FAQ，而是：

- 收益分析
- 昨日复盘
- 调价方案
- 确认执行 / 拒绝执行

这些都已经归到 `pricing / pricing_confirm`，并明确要求先于 FAQ 判断。

因此 FastGPT 方案必须显式声明：

`FastGPT 不得抢占 pricing、pricing_confirm、handoff-confirmation 等高优先级后端链。`

---

## 4. 优化后的目标形态

### 4.1 最终链路顺序

当前建议的最终顺序不是旧版“双通道并行”，而是：

1. **先做总路由裁决**
   - `pricing / pricing_confirm` 优先
   - 非 pricing 再进入 FAQ 体系
2. **FAQv2 主裁决**
3. **仅当 FAQv2 = miss 时，再调用 FastGPT**
4. **FastGPT 命中则返回 FastGPT**
5. **FastGPT 未命中则统一 fallback**

一句话：

`先路由，后 FAQv2，最后 FastGPT。`

### 4.2 当前建议的裁决规则

| 阶段 | 条件 | 处理 |
|---|---|---|
| 路由前置 | `pricing / pricing_confirm` | 直接走收益 MCP / 调价 / 复盘，不进 FAQ / FastGPT |
| FAQv2 | `decision=direct` | 直接返回 FAQv2 |
| FAQv2 | `decision=clarify` | 先保留 FAQv2 clarify，不直接交 FastGPT |
| FAQv2 | `decision=miss` | 才允许进入 FastGPT fallback |
| FastGPT | hit | 返回 FastGPT 答案 |
| FastGPT | miss | 统一返回“暂未查询到准确信息”或 handoff |

---

## 5. FastGPT 在当前架构中的正确角色

FastGPT 在当前版本里只做一件事：

`补 FAQv2 的 miss，不抢 FAQv2 的 direct，不覆盖 clarify，不进入收益 MCP 主链。`

它不负责：

- 覆盖 FAQv2 direct 结果
- 替代 FAQv2 成为 FAQ 主知识源
- 抢 routing owner
- 决定转接 / handoff
- 回答收益分析 / 调价 / 复盘

---

## 6. FastGPT 当前可用接入信息（保留但收敛用途）

### 6.1 本机地址

- FastGPT Web/API：`http://localhost:3000`
- FastGPT MCP 代理：`http://localhost:3003`

本方案只考虑：

`3000 的 HTTP 接口`

不使用：

`3003 的 MCP 代理`

### 6.2 登录账号

- 用户名：`root`
- 密码明文：`Xiaoli!114669`

### 6.3 当前可用知识库

- 知识库名称：`Hotel FAQ Test`
- `datasetId`：`69e0820ef18619096659af33`

当前没有现成聊天应用可复用，因此仍然优先：

`知识库检索接口，而不是 App 聊天接口。`

---

## 7. FastGPT 调用方式建议（保留但只用于 miss-only fallback）

### 7.1 登录与 Session

建议新增一个轻量封装服务：

- `/Users/sky/Project/Hotel/app/services/fastgpt.py`

职责：

1. 维护登录 Session/Cookie
2. 统一处理 `preLogin`
3. 统一处理 `loginByPassword`
4. 统一处理 `dataset/searchTest`
5. 输出规范化内部结果

### 7.2 查询输出结构建议

FastGPT 统一输出：

```python
{
  "hit": True,
  "answer": "...",
  "matched_question": "...",
  "score": 0.82,
  "source": "fastgpt",
  "raw": {...}
}
```

### 7.3 只在 miss 时调用

不再使用：

```python
faq_task = asyncio.create_task(...)
fastgpt_task = asyncio.create_task(...)
```

改成：

```python
faq_result = faq_v2.query(user_text, limit=3)

if faq_result["decision"] == "direct":
    return _faq_v2_to_backend_result(faq_result)

if faq_result["decision"] == "clarify":
    return _faq_v2_to_backend_result(faq_result)

fastgpt_result = await fastgpt.search(user_text)

if fastgpt_result["hit"]:
    return BackendTurnResult(...)

return BackendTurnResult(...)
```

也就是：

`FastGPT 改成串行 miss-only fallback，而不是并行双通道。`

---

## 8. FAQ 主路的推荐改造方式

### 8.1 当前不要一口气替掉整个 FAQ 主路

当前 `/Users/sky/Project/Hotel/app/main.py` 已经有：

- FAQv2
- faq_semantic
- exact FAQ
- 其它兜底

建议改造顺序：

1. 保持当前 `pricing` 优先级逻辑不变
2. 保持 `FAQv2` 作为 FAQ 主裁决链
3. 在 FAQv2 返回 `miss` 时，再插入 FastGPT
4. 先不要同时删除所有旧链路
5. 等 FastGPT fallback 稳定后，再考虑继续清理旧 FAQ semantic fallback

### 8.2 推荐插入点

推荐插入点仍然在：

- `/Users/sky/Project/Hotel/app/main.py`
- FAQ 分支处理附近

当前处理顺序里：

- FAQv2 已经在前
- FAQ semantic / exact FAQ 在后

优化版建议：

1. FAQv2 `direct` -> 直接返回
2. FAQv2 `clarify` -> 保留 clarify
3. FAQv2 `miss` -> 调 FastGPT
4. FastGPT miss -> 再考虑老 semantic / exact FAQ 是否还有必要保留

如果目标是最终收敛主路，则建议后续变成：

`FAQv2 -> FastGPT -> not_found/handoff`

而不是：

`FAQv2 -> semantic -> exact -> FastGPT -> ...`

---

## 9. `clarify` 的优化策略

这是当前方案里最容易被误写错的一点。

建议规则：

### 9.1 direct
- 直接返回 FAQv2

### 9.2 clarify
- 默认仍返回 FAQv2 的 clarify 问句
- 不直接走 FastGPT

### 9.3 miss
- 进入 FastGPT fallback

原因：

- `clarify` 代表“领域已经对了，但子意图没完全定下来”
- 这时 FastGPT 给出的自由答案，反而可能把原本安全的澄清变成错误事实

所以：

`FastGPT 只兜 miss，不兜 clarify。`

---

## 10. handoff / 转接规则

当前 handoff 仍应由 FAQv2 主导。

FastGPT 不负责：

- 决定是否转接
- 生成门店人工介入策略
- 替代 handoff 子意图

因此：

- 只要 FAQv2 命中 handoff，直接用 FAQv2
- FastGPT 不参与 handoff 决策

---

## 11. 配置建议（修正版）

建议新增以下配置，但强调是 **miss-only fallback 配置**：

```env
FASTGPT_ENABLED=true
FASTGPT_BASE_URL=http://localhost:3000
FASTGPT_USERNAME=root
FASTGPT_PASSWORD=Xiaoli!114669
FASTGPT_DATASET_ID=69e0820ef18619096659af33
FASTGPT_TIMEOUT_MS=2500
FASTGPT_LIMIT=5
FASTGPT_ONLY_ON_FAQ_V2_MISS=true
```

额外建议：

```env
FASTGPT_DISABLE_FOR_PRICING=true
FASTGPT_DISABLE_FOR_HANDOFF=true
FASTGPT_DISABLE_FOR_CONFIRMATION=true
```

即使代码里不做成显式配置，也应在实现上遵守这三个禁区。

---

## 12. 过渡语与体验建议

当前 FAQ 主路已经在 `direct` 模式，说明用户的体感比旧方案更敏感。

如果 FastGPT fallback 接进来，建议：

- 不要因为 FastGPT 而改变 FAQv2 命中时的即时体验
- FastGPT 只在 `miss` 时才允许额外等待
- 对 FastGPT fallback 的等待阈值要保守

建议：

- FAQv2 命中：维持当前快答体验
- FastGPT fallback：允许比 FAQv2 略慢，但不要把所有 FAQ 都拖慢

因此：

`FastGPT 不该为了理论覆盖率，把当前 FAQv2 的低延迟体验拖垮。`

---

## 13. 风险与边界

### 13.1 最大风险不是“没答案”，而是“多源答案互相打架”

当前系统已经有：

- FAQv2
- FAQ semantic
- exact FAQ
- 收益 MCP / 调价 / 复盘

如果再粗暴并入 FastGPT，就很容易出现：

- 同一问题不同链给不同答案
- 结果来源不透明
- 用户体感“怎么一会儿这样一会儿那样”

所以本方案必须坚持：

`FastGPT 严格只在 FAQv2 miss 时出场。`

### 13.2 FastGPT 不应该追求“覆盖所有模糊问法”

模糊问法主战场仍应是：

- FAQv2 的结构化数据
- normalize / lexicon / rerank
- handoff / service / direct / miss 的正确边界

FastGPT 只是弥补：

- FAQv2 短期还没补到的尾部表达

---

## 14. 最终推荐方案

基于当前真实现状，推荐方案不是旧版“双通道并行”，而是：

### 最终顺序

1. `pricing / pricing_confirm` 先裁决
2. FAQ 问题进入 FAQv2
3. FAQv2 `direct` -> 直接返回
4. FAQv2 `clarify` -> 保留 clarify
5. FAQv2 `miss` -> 再调用 FastGPT
6. FastGPT hit -> 返回 FastGPT
7. FastGPT miss -> not_found / handoff

### 核心结论

`FAQv2 继续当主路，FastGPT 只做 miss-only fallback。`

这比旧版“FAQv2 + FastGPT 并行双通道”更适合当前系统，因为它：

- 兼容当前已经上线的 FAQv2 主路
- 不打乱收益 MCP / 调价 / 复盘优先级
- 不覆盖 handoff
- 不破坏 FAQv2 低延迟体验
- 更容易调试和验收

---

## 15. 实施步骤

下面的实施顺序按“先不破坏现有主路，再逐步插入 FastGPT fallback”的原则执行。

### Phase 0：前置确认

目标：在动代码前，先确认当前主路和外部依赖都处于可验证状态。

步骤：

1. 确认 FAQv2 当前仍在主路：
   - `VOLCENGINE_FAQ_V2_MODE=direct`
   - FAQ 普通问题优先命中 FAQv2
2. 确认收益 MCP / 调价 / 复盘链健康：
   - `pricing / pricing_confirm` 继续优先于 FAQ
   - FastGPT 不能介入这三类问题
3. 确认 FastGPT 本机服务可达：
   - `http://localhost:3000`
4. 确认 FastGPT 知识库 ID 仍有效：
   - `69e0820ef18619096659af33`

交付产物：

- 一份当前接入状态记录
- 一次本地连通性验证结果

### Phase 1：新增 FastGPT 独立服务层

目标：先把 FastGPT 做成**独立可测的服务封装**，不立刻接入 FAQ 主链。

步骤：

1. 新增：
   - `/Users/sky/Project/Hotel/app/services/fastgpt.py`
2. 封装以下能力：
   - 预登录 `preLogin`
   - 登录 `loginByPassword`
   - Session/Cookie 复用
   - 知识库检索 `dataset/searchTest`
3. 统一输出结构：

```python
{
  "hit": bool,
  "answer": str | None,
  "matched_question": str | None,
  "score": float,
  "source": "fastgpt",
  "raw": dict,
}
```

4. 新增独立验证接口，建议：
   - `GET /api/validate/fastgpt?q=...`

要求：

- 不改 FAQ 主路
- 不改收益 MCP 逻辑
- 不改 FAQv2 判定逻辑

### Phase 2：把 FastGPT 插入 FAQv2 的 miss 分支

目标：只在 FAQv2 `miss` 时调用 FastGPT，不让 FastGPT 抢主路。

步骤：

1. 在 `/Users/sky/Project/Hotel/app/main.py` 的 FAQ 分支中插入 FastGPT fallback
2. 保持当前优先级：
   - `pricing / pricing_confirm` 最前
   - FAQv2 次之
   - FastGPT 只兜 FAQv2 miss
3. FAQ 分支执行顺序改为：
   - FAQv2 `direct` -> 直接返回
   - FAQv2 `clarify` -> 直接返回 clarify
   - FAQv2 `miss` -> 调 FastGPT
   - FastGPT miss -> not_found / handoff

要求：

- 不并行启动 FastGPT
- 不覆盖 FAQv2 direct
- 不接管 FAQv2 clarify
- 不接手 handoff

### Phase 3：保留旧 FAQ semantic 但降级

目标：在 FastGPT fallback 还没跑稳前，避免一次性拆掉所有旧兜底。

步骤：

1. 先保持现有 `faq_semantic` / exact FAQ 代码在仓
2. 但在 FAQ 主链顺序上降到 FastGPT 之后
3. 后续如果 FastGPT fallback 稳定，再考虑删除旧 fallback

建议顺序：

`FAQv2 -> FastGPT -> semantic/exact(可选短期保留) -> not_found`

或在更激进版本中直接收敛为：

`FAQv2 -> FastGPT -> not_found`

### Phase 4：灰度与观测

目标：先低风险灰度，不直接全量。

步骤：

1. 新增配置项：

```env
FASTGPT_ENABLED=true
FASTGPT_ONLY_ON_FAQ_V2_MISS=true
FASTGPT_TIMEOUT_MS=2500
FASTGPT_LIMIT=5
```

2. 为 FastGPT 返回结果加元数据：
   - `source=fastgpt`
   - `matched_question`
   - `score`
3. 在日志中明确记录 FAQ 来源：
   - `faq_v2_direct`
   - `faq_v2_clarify`
   - `fastgpt_fallback`
   - `faq_not_found`

### Phase 5：收敛并清理

目标：FastGPT fallback 稳定后，再决定是否清理旧 FAQ semantic 链。

步骤：

1. 比较三类问题表现：
   - FAQv2 direct
   - FastGPT fallback
   - old semantic fallback
2. 如果 FastGPT 在 miss-only 场景明显优于旧 semantic 链：
   - 逐步移除旧 semantic fallback
3. 如果 FastGPT 经常幻觉或命中不稳：
   - 保持它只在极窄 miss 场景下启用

---

## 16. 验收清单

以下清单用于判断这次 FastGPT fallback 是否真的达标。

### A. 路由优先级验收

- [ ] `小丽，生成收益分析` 仍然只走收益 MCP
- [ ] `小丽，生成昨日复盘` 仍然只走收益 MCP
- [ ] `小丽，生成调价方案` 仍然只走收益 MCP
- [ ] FastGPT 不会抢 `pricing / pricing_confirm`
- [ ] handoff 类问题不会被 FastGPT 覆盖

### B. FAQ 主路验收

- [ ] FAQv2 `direct` 问题仍然直接返回 FAQv2
- [ ] FAQv2 `clarify` 仍然返回 clarify，不会被 FastGPT 偷换
- [ ] FAQv2 `miss` 时才调用 FastGPT
- [ ] FastGPT 命中后只给一个最终答案，不出现双答案

### C. FastGPT 服务验收

- [ ] 登录态可复用，不会每题重新登录
- [ ] `searchTest` 能正常返回结果
- [ ] FastGPT 超时可控，不会把 FAQ 主路整体拖慢
- [ ] FastGPT 服务挂掉时，FAQ 主路仍可正常工作

### D. 用户体验验收

- [ ] FAQv2 命中问题体感与当前版本基本一致
- [ ] FastGPT fallback 不会明显拖慢高频 FAQ
- [ ] 不出现“这次是 FAQv2 / 下次又是 FastGPT / 再下次 semantic”的混乱体感
- [ ] 未知问题仍优先安全拒答，不编造

### E. 问题集验收

至少做以下 4 组回归：

1. FAQv2 高置信 direct 问题
   - 停车费
   - 发票申请
   - 早餐是否提供
   - 南站路线

2. FAQv2 clarify 问题
   - 同主题但子意图不清的问题

3. FAQv2 miss + FastGPT 应该兜住的问题
   - 长尾口语化表达
   - FAQv2 未覆盖但知识库里存在的表达

4. FastGPT 也不该回答的问题
   - 未知设施
   - 应转接问题
   - 明显与酒店知识无关的问题

### F. 最终通过标准

本方案视为通过，至少同时满足：

- [ ] FAQv2 主路体验不退化
- [ ] FastGPT 没有抢收益 MCP / 调价 / 复盘
- [ ] FastGPT 只在 FAQv2 miss 时出场
- [ ] clarify 没被 FastGPT 偷换
- [ ] handoff 没被 FastGPT 抢走
- [ ] 至少一轮实际 FAQ 回归中，FastGPT 对 miss 问题的兜底效果明显优于当前空白 miss

---

## 17. 实施建议结论

建议按下面的顺序开始真正开发：

1. 先做 `fastgpt.py` 独立服务
2. 再做 `miss-only fallback` 接入
3. 先灰度日志观测，不急着删旧链
4. 验收通过后，再决定是否继续清理 semantic/exact FAQ fallback

最重要的一句话仍然是：

`不要让 FastGPT 成为第二条 FAQ 主路，只让它补 FAQv2 的 miss。`

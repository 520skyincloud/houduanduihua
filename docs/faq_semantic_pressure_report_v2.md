# FAQ 语义匹配压测报告 V2

## 压测口径

- 数据源优先使用本地 `data/faq_index.json`，共 `944` 条 `answer_type=direct` 的 FAQ 正样本，另保留 `8` 条 handoff 特殊样本。
- 共生成 `1000` 条中文口语化/模糊问法，其中 `944` 条为 direct FAQ 变体，`8` 条为 handoff 特殊探针，`48` 条为未知设施/拒答负样本。
- 调用本地接口 `GET /api/validate/faq-semantic/query?q=...` 做真实验证。

## 结果摘要

| 类别 | 样本数 | 命中/拒答 | 平均耗时 |
| --- | ---: | ---: | ---: |
| direct FAQ | 944 | 命中率 `57.7%` | `45.14 ms` |
| handoff 探针 | 8 | 拒答率 `87.5%` | `45.14 ms` |
| unknown/refusal | 48 | 拒答率 `100.0%` | `45.14 ms` |

- 总体平均耗时：`45.14 ms`
- direct FAQ 知识命中数：`545/944`
- handoff 特殊探针正确拒答数：`7/8`
- unknown/refusal 正确拒答数：`48/48`

## 最弱类别

| 类别 | 样本数 | 命中率 | 平均耗时 |
| --- | ---: | ---: | ---: |
| handoff | 16 | `0.0%` | `58.89 ms` |
| parking | 56 | `28.6%` | `179.20 ms` |
| invoice | 24 | `33.3%` | `73.26 ms` |
| checkin | 32 | `40.6%` | `42.96 ms` |
| floor | 24 | `41.7%` | `29.24 ms` |
| route | 64 | `48.4%` | `60.95 ms` |
| supplies | 48 | `54.2%` | `37.67 ms` |
| breakfast | 24 | `58.3%` | `42.53 ms` |

## 最常见错误模式

| 模式 | 次数 |
| --- | ---: |
| reject:top-match-too-weak:other:procedure | 34 |
| reject:top-match-too-weak:facility:general | 33 |
| reject:top-match-too-weak:facility:procedure | 28 |
| reject:top-match-too-weak:other:general | 21 |
| reject:top-match-too-weak:other:existence | 21 |
| reject:top-match-too-weak:facility:existence | 17 |
| reject:no-match:facility:procedure | 16 |
| reject:no-match:facility:general | 13 |
| wrong_faq:parking:general:parking | 11 |
| wrong_faq:parking:price:parking | 10 |

## 建议补充的 alias / 改写规则

| 建议 | 次数 |
| --- | ---: |
| facility-rewrite:general | 46 |
| facility-rewrite:procedure | 44 |
| other-rewrite:procedure | 42 |
| other-rewrite:general | 29 |
| other-rewrite:existence | 24 |
| route-alias | 20 |
| facility-rewrite:existence | 18 |
| parking-alias | 12 |
| invoice-alias | 10 |
| supplies-rewrite:procedure | 8 |
| checkin-rewrite:general | 8 |
| parking-rewrite:general | 8 |
| facility-rewrite:location | 8 |
| checkin-alias | 8 |
| parking-rewrite:time | 7 |
| checkin-rewrite:procedure | 7 |
| route-rewrite:general | 7 |
| other-rewrite:price | 6 |
| floor-rewrite:general | 6 |
| parking-rewrite:price | 6 |

## 30 个最有代表性的失败样例

| # | 类型 | 问题 | 期望 | 实际/原因 | 耗时 |
| --- | --- | --- | --- | --- | ---: |
| 1 | handoff | `下午会打扫可以直接找前台吗` | `handoff / 转接` | `checkin/8aa3dcd89277/handoff_false_accept` | `78.85` |
| 2 | direct | `我早上想吃点东西，微波炉在哪里在哪儿` | `breakfast / 4f44dcf33723` | `breakfast/fb2e3d43b624/wrong_faq:breakfast:location…` | `85.02` |
| 3 | direct | `我早上想吃点东西的话，微波炉在哪里怎么处理` | `breakfast / 4f44dcf33723` | `breakfast/fb2e3d43b624/wrong_faq:breakfast:location…` | `83.80` |
| 4 | direct | `我早上想吃点东西，我想去吃饭，有什么推荐有没有` | `breakfast / c7db0541df06` | `breakfast/fb2e3d43b624/wrong_faq:breakfast:existenc…` | `78.39` |
| 5 | direct | `我早上想吃点东西的话，我想去吃饭，有什么推荐怎么处理` | `breakfast / c7db0541df06` | `breakfast/fb2e3d43b624/wrong_faq:breakfast:procedur…` | `77.37` |
| 6 | direct | `麻烦问下，酒店有早餐怎么弄` | `breakfast / fb2e3d43b624` | `top-match-too-weak` | `32.72` |
| 7 | direct | `我这边想了解一下，酒店有早餐` | `breakfast / fb2e3d43b624` | `top-match-too-weak` | `30.37` |
| 8 | direct | `酒店有早餐可以吗` | `breakfast / fb2e3d43b624` | `top-match-too-weak` | `30.13` |
| 9 | direct | `酒店有早餐有没有呀` | `breakfast / fb2e3d43b624` | `top-match-too-weak` | `29.90` |
| 10 | direct | `微波炉在哪里有没有呀` | `breakfast / 4f44dcf33723` | `top-second-gap-too-small` | `29.62` |
| 11 | direct | `那酒店有早餐呢` | `breakfast / fb2e3d43b624` | `top-match-too-weak` | `28.63` |
| 12 | direct | `我晚上会到店，为什么找不到前台在哪儿` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:location:che…` | `88.51` |
| 13 | direct | `麻烦问下，为什么找不到前台怎么弄` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:procedure:ch…` | `85.60` |
| 14 | direct | `我晚上会到店的话，为什么找不到前台怎么处理` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:procedure:ch…` | `83.90` |
| 15 | direct | `为什么找不到前台有没有呀` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:existence:ch…` | `80.30` |
| 16 | direct | `我这边想了解一下，为什么找不到前台` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:general:chec…` | `79.68` |
| 17 | direct | `请问为什么找不到前台` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:general:chec…` | `74.96` |
| 18 | direct | `为什么找不到前台可以吗` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:general:chec…` | `74.81` |
| 19 | direct | `那为什么找不到前台呢` | `checkin / ddce324b48af` | `checkin/8aa3dcd89277/wrong_faq:checkin:general:chec…` | `72.85` |
| 20 | direct | `我晚上会到店的话，有服务员怎么处理` | `checkin / 8aa3dcd89277` | `no-match` | `39.13` |
| 21 | direct | `我晚上会到店，我行李多，能帮我一下有没有` | `checkin / 896b34682d27` | `top-match-too-weak` | `32.19` |
| 22 | direct | `麻烦问下，我行李多，能帮我一下怎么弄` | `checkin / 896b34682d27` | `top-match-too-weak` | `31.37` |
| 23 | direct | `我晚上会到店的话，我行李多，能帮我一下怎么处理` | `checkin / 896b34682d27` | `top-match-too-weak` | `31.34` |
| 24 | direct | `我晚上会到店，有服务员最晚什么时候` | `checkin / 8aa3dcd89277` | `no-match` | `30.70` |
| 25 | direct | `麻烦问下，有服务员怎么弄` | `checkin / 8aa3dcd89277` | `no-match` | `29.19` |
| 26 | direct | `有服务员有没有呀` | `checkin / 8aa3dcd89277` | `top-match-too-weak` | `29.03` |
| 27 | direct | `我这边想了解一下，我行李多，能帮我一下` | `checkin / 896b34682d27` | `top-match-too-weak` | `27.10` |
| 28 | direct | `我这边想了解一下，有服务员` | `checkin / 8aa3dcd89277` | `no-match` | `25.90` |
| 29 | direct | `有服务员可以吗` | `checkin / 8aa3dcd89277` | `top-match-too-weak` | `23.46` |
| 30 | direct | `那有服务员呢` | `checkin / 8aa3dcd89277` | `top-match-too-weak` | `22.71` |

## 说明

- direct FAQ 统计口径为：`accepted=true` 且 `top_match.faq_id` 与期望 FAQ 一致。
- handoff 探针用于验证 semantic 层是否误把转接类问题当作普通 FAQ 放行。
- unknown/refusal 样本用于验证拒答稳定性。
- 这版报告对应的测试集构成是：`118 * 8 = 944` 条 direct FAQ，`8` 条 handoff 探针，`48` 条 unknown/refusal。

## 复现命令

```bash
python3 scripts/faq_semantic_pressure_v2.py --report docs/faq_semantic_pressure_report_v2.md
```

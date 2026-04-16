from __future__ import annotations

import re


FILLER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern)
    for pattern in [
        r"小丽",
        r"请问",
        r"麻烦",
        r"帮我",
        r"给我",
        r"请帮我",
        r"想问下",
        r"我想问一下",
        r"我想问",
        r"想问一下",
        r"来个",
        r"来一版",
        r"看一下",
        r"看下",
        r"一下",
        r"能否",
        r"可以帮我",
        r"麻烦帮我",
        r"请",
        r"哈",
        r"呢",
        r"呀",
        r"哦",
    ]
]

SYNONYM_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"增值税专票"), "发票专票"),
    (re.compile(r"专票"), "发票专票"),
    (re.compile(r"普票"), "发票普票"),
    (re.compile(r"小狗|狗狗|宠物狗"), "宠物狗"),
    (re.compile(r"小猫|猫咪|宠物猫"), "宠物猫"),
    (re.compile(r"泳池|游泳池"), "游泳池"),
    (re.compile(r"报备"), "预约"),
    (re.compile(r"早饭"), "早餐"),
    (re.compile(r"早上有没有吃的|早上有吃的吗|早上有吃的嘛|早上吃什么"), "有早餐吗"),
    (re.compile(r"南站"), "高铁南站"),
    (re.compile(r"高铁站"), "高铁南站"),
    (re.compile(r"WIFI|WiFi|wifi|无线网|无线网络"), "wifi"),
    (re.compile(r"开票"), "开发票"),
    (re.compile(r"线上自己弄|线上自己开|线上自己申请"), "线上申请发票"),
    (re.compile(r"延迟退房|延时退房"), "延时退房"),
    (re.compile(r"离店"), "退房"),
    (re.compile(r"我明天最晚几点之前得走|最晚几点之前得走|几点之前得走|几点前得走"), "退房时间"),
    (re.compile(r"发票是退房以后线上自己弄吗|退房后线上自己开发票吗|退房后线上申请发票吗"), "退房后申请发票"),
    (re.compile(r"地图上应该搜你们什么名字|地图上搜什么名字|地图上搜什么能找到你们|导航搜什么名字"), "导航搜什么名字"),
    (re.compile(r"搜哪个名称|搜什么名字|搜啥名字|搜什么可以找到"), "导航搜什么名字"),
    (re.compile(r"我自己开车过去的话车能停哪儿啊|车能停哪儿啊|车停哪儿啊|车子停哪儿啊|自驾过去车停哪儿"), "停车场在哪"),
    (re.compile(r"我从高铁南站过来怎么走会比较顺|我从南站过来怎么走会比较顺|从高铁南站过来怎么走|从南站过来怎么走"), "高铁南站怎么到酒店"),
    (re.compile(r"游个泳"), "游泳池"),
    (re.compile(r"空调怎么开|怎么开空调"), "小爱同学空调怎么开"),
    (re.compile(r"帮我看下房间哈|帮我看下房间|让阿姨看下房间"), "联系管家看下房间"),
    (re.compile(r"小爱同学"), "智能语音"),
    (re.compile(r"外卖员"), "外卖"),
    (re.compile(r"携程上搜丽斯未来可以找到你们家吗"), "携程名称"),
    (re.compile(r"美团上搜丽斯未来可以找到你们家吗"), "美团名称"),
]


def normalize_faq_text(input_text: str) -> str:
    text = input_text.strip().lower()

    for pattern in FILLER_PATTERNS:
        text = pattern.sub("", text)

    for pattern, replacement in SYNONYM_RULES:
        text = pattern.sub(replacement, text)

    text = re.sub(r"[“”\"'`‘’]", "", text)
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[，。！？、；：:,.!?()[\]{}<>《》·~—\-]", "", text)
    return text


def compact_faq_text(input_text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalize_faq_text(input_text))


def build_char_ngrams(input_text: str, sizes: list[int] | tuple[int, ...] = (2, 3)) -> set[str]:
    text = compact_faq_text(input_text)
    grams: set[str] = set()
    for size in sizes:
        if len(text) < size:
            continue
        for index in range(0, len(text) - size + 1):
            grams.add(text[index : index + size])
    return grams


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if not intersection:
        return 0.0
    union = len(left) + len(right) - intersection
    return 0.0 if union <= 0 else intersection / union


def extract_matched_terms(text: str, terms: list[str]) -> list[str]:
    normalized_text = normalize_faq_text(text)
    matches: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized_term = normalize_faq_text(term)
        if normalized_term and normalized_term in normalized_text and term not in seen:
            matches.append(term)
            seen.add(term)
    return matches

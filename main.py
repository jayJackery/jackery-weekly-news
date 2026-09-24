#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""华宝新能（Jackery）储能结构工程师 · 每周行业资讯推送

流程：Tavily 中英双语检索 → DeepSeek 提炼为分类 JSON → 本地渲染 Markdown
      → 钉钉推送 → 记录已推送 URL

用法：
    python main.py                # 完整流程
    python main.py --dry-run      # 只打印 Markdown，不推送钉钉、不写 history
    python main.py --limit 2      # 只跑前 2 条查询，快速验证

环境变量见 README.md。任何异常都会以非 0 退出码结束，以便 GitHub Actions 变红告警。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import requests
except ImportError:
    sys.exit("缺少依赖：requests。请先执行 pip install -r requirements.txt")

try:
    from tavily import TavilyClient
except ImportError:
    sys.exit("缺少依赖：tavily-python。请先执行 pip install -r requirements.txt")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("缺少依赖：openai。请先执行 pip install -r requirements.txt")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

BEIJING_TZ = timezone(timedelta(hours=8))

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history_urls.json")

# 钉钉自定义关键词。必须出现在 markdown.text 正文里，否则钉钉会以 310000 拒收。
DINGTALK_KEYWORD = "[行业资讯]"

# 三个分类。名称与顺序固定，改动时需同步修改 SYSTEM_PROMPT。
CATEGORY_COMPETITOR = "竞品与市场动态"
CATEGORY_STRUCTURE = "结构、材料与防护技术"
CATEGORY_REGULATION = "法规标准与出海动态"
CATEGORIES = [CATEGORY_COMPETITOR, CATEGORY_STRUCTURE, CATEGORY_REGULATION]

# 全局屏蔽域名：社交平台与聚合站。它们经常挤掉正经行业媒体的位置，
# 且对结构工程师没有信息价值。
EXCLUDE_DOMAINS = [
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "pinterest.com", "tiktok.com", "threads.net", "quora.com", "medium.com",
]

# 中文技术类查询定向到的行业媒体。
# 非定向的中文技术查询实测会跑偏到汽车、消费电子等无关领域，定向后稳定命中储能结构内容。
CN_INDUSTRY_DOMAINS = [
    "bjx.com.cn",        # 北极星储能网 / 电力新闻网
    "escn.com.cn",       # 中国储能网
    "elecfans.com",      # 电子发烧友
    "gg-lb.com",         # 高工锂电
    "d1ev.com",          # 第一电动
    "36kr.com",          # 36氪
]

# 双语检索查询。category_hint 只是给模型的归类倾向提示，不强制。
#
# 查询词是实测调过的，不是拍脑袋写的：
#   - 中文关键词堆砌（如"便携储能 户外电源 阳台储能 竞品 新品 结构 2026"）在 news 主题下
#     会返回驱动之家日榜、淘宝规则页甚至赌博站，基本不可用；
#   - 改成自然语言的短查询 + general 主题后，能稳定抓到厂商新品、专利、年报等有效信息。
# 改动查询词后建议先跑 `python main.py --dry-run` 看实际召回质量。
QUERIES: list[dict[str, Any]] = [
    {
        "query": "便携式储能电源 新品发布 行业动态",
        "lang": "zh",
        "topic": "general",
        "category_hint": CATEGORY_COMPETITOR,
    },
    {
        "query": "储能 电池包 结构 散热 IP防护 跌落",
        "lang": "zh",
        "topic": "general",
        "include_domains": CN_INDUSTRY_DOMAINS,
        "category_hint": f"{CATEGORY_STRUCTURE} / {CATEGORY_REGULATION}",
    },
    {
        "query": "portable power station solar generator new release 2026",
        "lang": "en",
        "topic": "news",
        "category_hint": CATEGORY_COMPETITOR,
    },
    {
        "query": "balcony energy storage structural design",
        "lang": "en",
        "topic": "general",
        "category_hint": f"{CATEGORY_STRUCTURE} / {CATEGORY_REGULATION}",
    },
]

# Tavily 调用参数。
# 注意：不要使用 days 参数 —— 它已从 Tavily 全部现行文档中移除，传了可能被静默忽略，
# 导致"以为只取近 7 天，实际混进旧闻"。用 time_range 代替。
SEARCH_DEPTH = "basic"          # 1 credit/次（advanced 是 2 credits）
SEARCH_TIME_RANGE = "week"
SEARCH_MAX_RESULTS = 10         # 服务端上限 20，默认 10
SEARCH_RETRIES = 2
SEARCH_RETRY_BACKOFF = 5        # 秒

# 送入大模型的候选条数上限，控制 token 消耗。
MAX_INPUT_ITEMS = 40
# 每个分类最多收录几条。
MAX_ITEMS_PER_CATEGORY = 6
# 单条钉钉消息正文的 UTF-8 字节上限。
# 官方文档对自定义机器人 markdown 正文长度没有任何明文规定（流传的 20000 字节查无出处），
# 所以不留险，主动截断到 8KB。
MAX_MESSAGE_BYTES = 8000
# history_urls.json 保留的最大条目数，超出按日期淘汰最旧。
MAX_HISTORY = 2000

LOG = logging.getLogger("newsbot")


# ---------------------------------------------------------------------------
# 环境变量
# ---------------------------------------------------------------------------

def load_config(dry_run: bool) -> dict[str, str]:
    """读取并校验环境变量。缺失或格式不对时立刻退出，不拖到运行中途才崩。"""
    missing: list[str] = []

    def get(name: str, required: bool = True, default: str = "") -> str:
        value = (os.environ.get(name) or "").strip()
        if not value:
            if required:
                missing.append(name)
            return default
        return value

    cfg = {
        "TAVILY_API_KEY": get("TAVILY_API_KEY"),
        "OPENAI_API_KEY": get("OPENAI_API_KEY"),
        "OPENAI_BASE_URL": get("OPENAI_BASE_URL", required=False, default="https://api.deepseek.com/v1"),
        "OPENAI_MODEL": get("OPENAI_MODEL", required=False, default="deepseek-chat"),
        # dry-run 不推送，所以不强制要求 webhook。
        "DINGTALK_WEBHOOK": get("DINGTALK_WEBHOOK", required=not dry_run),
    }

    if missing:
        lines = ["以下环境变量缺失，无法运行："]
        for name in missing:
            lines.append(f"  - {name}")
        lines.append("")
        lines.append("本地运行：把值写在项目根目录的 Key 文件里，或直接 export。")
        lines.append("GitHub Actions：在仓库 Settings → Secrets and variables → Actions 里配置。")
        sys.exit("\n".join(lines))

    # DINGTALK_WEBHOOK 格式校验。
    # 钉钉机器人 webhook 必须是 oapi.dingtalk.com/robot/send?access_token=...
    # 这一条能把"误填了飞书文档链接"之类的错误在启动时就拦下，
    # 而不是等推送时返回一个看不懂的 310000。
    webhook = cfg["DINGTALK_WEBHOOK"]
    if webhook and not webhook.startswith("https://oapi.dingtalk.com/robot/send"):
        sys.exit(
            "DINGTALK_WEBHOOK 格式不对。\n"
            f"  当前值：{webhook[:60]}{'...' if len(webhook) > 60 else ''}\n"
            "  期望值：https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx\n"
            "  注意：飞书（feishu.cn）的链接不是钉钉 webhook，两者不通用。"
        )

    return cfg


# ---------------------------------------------------------------------------
# URL 归一化与去重
# ---------------------------------------------------------------------------

# 常见追踪参数。带上这些参数的同一篇文章会被当成两条新闻，必须剥掉。
_TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid", "mc_cid", "mc_eid",
    "ref", "ref_src", "referrer", "spm", "share_token", "share_from", "from",
    "source", "_hsenc", "_hsmi", "trk", "trkCampaign", "sc_cid",
}


def normalize_url(url: str) -> str:
    """归一化 URL，用于去重比对。无法解析时返回空串（调用方应丢弃该条）。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""

    if not parts.scheme or not parts.netloc:
        return ""

    netloc = parts.netloc.lower()
    # www 前缀统一去掉：同一站点的 www 与非 www 版本应视为同一个链接。
    if netloc.startswith("www."):
        netloc = netloc[4:]

    kept_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    ]

    path = parts.path.rstrip("/") or "/"

    return urlunsplit(("https", netloc, path, urlencode(kept_query), ""))


# ---------------------------------------------------------------------------
# history_urls.json
# ---------------------------------------------------------------------------

def load_history() -> dict[str, str]:
    """读取已推送 URL 台账。文件不存在或损坏时返回空台账，不报错。"""
    if not os.path.exists(HISTORY_FILE):
        LOG.info("未找到 %s，按空台账处理（首次运行属正常）", os.path.basename(HISTORY_FILE))
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        LOG.warning("解析 %s 失败（%s），按空台账处理", os.path.basename(HISTORY_FILE), exc)
        return {}

    urls = data.get("urls") if isinstance(data, dict) else None
    if not isinstance(urls, dict):
        LOG.warning("%s 结构不符合预期，按空台账处理", os.path.basename(HISTORY_FILE))
        return {}

    return {str(k): str(v) for k, v in urls.items()}


def save_history(history: dict[str, str]) -> None:
    """写回台账，超出 MAX_HISTORY 时按记录日期淘汰最旧。"""
    items = sorted(history.items(), key=lambda kv: kv[1], reverse=True)
    trimmed = dict(items[:MAX_HISTORY])
    if len(items) > MAX_HISTORY:
        LOG.info("台账超出 %d 条，淘汰最旧的 %d 条", MAX_HISTORY, len(items) - MAX_HISTORY)

    payload = {
        "updated_at": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d"),
        "urls": trimmed,
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    LOG.info("已更新 %s，当前共 %d 条记录", os.path.basename(HISTORY_FILE), len(trimmed))


# ---------------------------------------------------------------------------
# Tavily 检索
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    title: str
    url: str
    normalized_url: str
    content: str
    published_date: str
    source_query: str
    lang: str


def _search_once(client: TavilyClient, spec: dict[str, Any]) -> dict[str, Any]:
    """带重试的单条检索。"""
    params: dict[str, Any] = {
        "query": spec["query"],
        "topic": spec.get("topic", "news"),
        "time_range": SEARCH_TIME_RANGE,
        "search_depth": SEARCH_DEPTH,
        "max_results": SEARCH_MAX_RESULTS,
        "exclude_domains": EXCLUDE_DOMAINS,
    }
    if spec.get("include_domains"):
        params["include_domains"] = spec["include_domains"]

    last_exc: Exception | None = None
    for attempt in range(1, SEARCH_RETRIES + 1):
        try:
            return client.search(**params)
        except Exception as exc:  # noqa: BLE001 - 需要兜住 SDK 的各路异常
            last_exc = exc
            if attempt < SEARCH_RETRIES:
                LOG.warning(
                    "检索失败（第 %d/%d 次）：%s: %s，%d 秒后重试",
                    attempt, SEARCH_RETRIES, type(exc).__name__, exc, SEARCH_RETRY_BACKOFF,
                )
                time.sleep(SEARCH_RETRY_BACKOFF)

    raise RuntimeError(f"检索持续失败：{type(last_exc).__name__}: {last_exc}") from last_exc


def search_all(api_key: str, queries: list[dict[str, Any]]) -> list[Candidate]:
    """跑完所有查询并去重。

    单条查询失败不影响其余 —— 一条挂掉不该让整期周报开天窗。
    """
    client = TavilyClient(api_key=api_key)
    found: dict[str, Candidate] = {}

    for spec in queries:
        query = spec["query"]
        try:
            response = _search_once(client, spec)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("查询「%s」失败，跳过：%s", query, exc)
            continue

        # SDK 用 setdefault 保证了 results 键存在，但可能是空列表。
        results = response.get("results") or []
        if not results:
            LOG.warning("查询「%s」没有返回结果", query)
            continue

        added = 0
        for item in results:
            raw_url = str(item.get("url") or "")
            normalized = normalize_url(raw_url)
            if not normalized:
                continue
            if normalized in found:
                continue
            found[normalized] = Candidate(
                title=str(item.get("title") or "").strip(),
                url=raw_url,
                normalized_url=normalized,
                content=str(item.get("content") or "").strip(),
                # published_date 是 beta 字段，探测不到时为 None，必须容错。
                published_date=str(item.get("published_date") or ""),
                source_query=query,
                lang=spec.get("lang", ""),
            )
            added += 1

        LOG.info("查询「%s」返回 %d 条，新增 %d 条", query, len(results), added)

    LOG.info("本轮共获得 %d 条不重复候选资讯", len(found))
    return list(found.values())


# ---------------------------------------------------------------------------
# 大模型提炼
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""你是一名储能行业分析师，服务于华宝新能（Jackery）的储能结构工程师团队。
你的任务是把检索到的原始资讯，提炼成一份每周行业情报，供结构工程师快速掌握竞品动向与技术趋势。

必须严格输出如下 JSON 结构（只输出 JSON，不要任何解释文字，不要 Markdown 代码围栏）：
{{
  "categories": [
    {{"name": "{CATEGORY_COMPETITOR}", "items": [{{"title": "...", "insight": "...", "url": "..."}}]}},
    {{"name": "{CATEGORY_STRUCTURE}", "items": [{{"title": "...", "insight": "...", "url": "..."}}]}},
    {{"name": "{CATEGORY_REGULATION}", "items": [{{"title": "...", "insight": "...", "url": "..."}}]}}
  ]
}}

三个分类的收录边界：
1. 【{CATEGORY_COMPETITOR}】EcoFlow、Anker、Bluetti 及国内厂商（正浩、德兰明海、安克创新、大疆等）
   的新品发布、形态创新、价格与渠道动作、销量与融资等信息。
2. 【{CATEGORY_STRUCTURE}】外壳防跌落与抗冲击设计、IP 防护等级、Pack 结构与模组堆叠、
   热管理与风道设计、阻燃材料与结构件工艺、可维修性与装配方式等技术内容。
3. 【{CATEGORY_REGULATION}】UL 2743 等安全标准、欧洲阳台储能（Balkonkraftwerk）安装规范、
   各国并网与出口认证要求、关税与贸易政策等合规与出海相关内容。

字段要求：
- title：中文标题，简洁准确，一句话说清这条资讯是什么。不要加方括号前缀。
- insight：1~2 句解读，必须从**结构工程或行业竞争**的视角切入，说明它对结构设计意味着什么、
  或对产品形态有何影响。不要复述原文内容，不要写"该文章介绍了……"这类空话。
- url：必须**原样复制**输入列表里给出的 URL，一个字都不要改。绝对不要自己编造或拼接链接。

归类规则：
- 同一条资讯只放进最贴切的一个分类，不要重复收录。
- 某个分类确实没有相关内容时，该分类的 items 返回空数组 []。
- 全部候选都无法归入任何分类时，三个分类的 items 都返回 []。

收录标准：宁缺毋滥，以下几类一律丢弃 ——
- **纯折扣/促销稿**：只讲"降价了、打几折、哪里买得到"，不含产品形态或技术信息的。
  唯一的例外是降价幅度极大且反映头部厂商战略调整（清库存、为新平台让路）的，
  可以收录，但 insight 必须落在成本压力或产品迭代节奏上，不能只是复述折扣力度。
- **厂商自营页与营销内容**：链接指向品牌官网的产品页、电商店铺页、SEO 软文或官方博客
  的自我推介文章，而非第三方媒体报道的。
- **自动生成页**：链接带随机地址参数、或明显由模板批量生成的聚合页、榜单页、导航页。
- **与储能/便携电源/阳台储能无关的内容**：汽车、消费电子、通用半导体、食品、政务等。
- **纯资本面稿件**：股价、概念股炒作、财报数字罗列。
  例外：如果财报或公告里披露了产品线规划、技术路线、认证资质（如 IP 等级、UL 认证）
  等实质性工程信息，可以收录，insight 要写这些工程信息而非财务数字。

另外：结构工程师更关心"产品怎么做的"而不是"卖多少钱"。同等条件下，
优先收录新产品与新形态、结构与热管理技术、法规标准变化。
"""


@dataclass
class NewsItem:
    title: str
    insight: str
    url: str


def build_user_prompt(candidates: list[Candidate]) -> str:
    lines = [
        "以下是本周检索到的候选资讯，请按系统提示的要求提炼归类。",
        f"共 {len(candidates)} 条候选，每条格式为：[编号] 标题 / 链接 / 摘要片段。",
        "",
    ]
    for idx, item in enumerate(candidates, start=1):
        lines.append(f"[{idx}] 标题：{item.title}")
        lines.append(f"    链接：{item.url}")
        if item.published_date:
            lines.append(f"    发布时间：{item.published_date}")
        snippet = re.sub(r"\s+", " ", item.content)[:400]
        if snippet:
            lines.append(f"    摘要：{snippet}")
        lines.append("")
    lines.append("请输出 JSON。")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict[str, Any]:
    """解析模型返回的 JSON。先尝试剥掉 Markdown 代码围栏再解析。"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("模型返回了空内容")

    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1).strip()

    return json.loads(text)


def call_llm(cfg: dict[str, str], candidates: list[Candidate]) -> dict[str, Any]:
    # 默认超时是 10 分钟，对每周一次的定时任务太长 —— 卡住会白烧 runner 时间。
    client = OpenAI(
        api_key=cfg["OPENAI_API_KEY"],
        base_url=cfg["OPENAI_BASE_URL"],
        timeout=60.0,
        max_retries=2,
    )

    response = client.chat.completions.create(
        model=cfg["OPENAI_MODEL"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(candidates)},
        ],
        # DeepSeek 只支持 json_object，不支持 json_schema。
        # 第三方网关存在"静默丢弃 response_format"的已知问题，
        # 所以提示词里已写明 JSON 结构，且下面还有解析与字段校验兜底。
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    raw = (response.choices[0].message.content or "").strip()
    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        LOG.error("模型输出无法解析为 JSON：%s", exc)
        LOG.error("原始输出（前 1000 字符）：%s", raw[:1000])
        raise


def validate_digest(
    data: dict[str, Any],
    candidates: list[Candidate],
) -> list[tuple[str, list[NewsItem]]]:
    """校验模型输出，并过滤掉编造的链接。"""
    by_normalized = {c.normalized_url: c for c in candidates}

    raw_categories = data.get("categories")
    if not isinstance(raw_categories, list):
        raise ValueError("模型输出的 categories 字段缺失或类型不对")

    # 把模型返回的分类名映射到固定分类。允许模型带【】或多余空格。
    def canonicalize(name: Any) -> str | None:
        cleaned = re.sub(r"[\[\]【】\s]", "", str(name or ""))
        if not cleaned:
            return None
        for category in CATEGORIES:
            if cleaned == re.sub(r"[\[\]【】\s]", "", category):
                return category
        for category in CATEGORIES:
            core = re.sub(r"[\[\]【】\s]", "", category)
            if core and (core in cleaned or cleaned in core):
                return category
        return None

    collected: dict[str, list[NewsItem]] = {category: [] for category in CATEGORIES}
    seen_urls: set[str] = set()
    dropped_duplicate = 0
    dropped_fabricated = 0
    dropped_malformed = 0

    for entry in raw_categories:
        if not isinstance(entry, dict):
            continue
        category = canonicalize(entry.get("name"))
        if category is None:
            LOG.warning("模型返回了未知分类「%s」，其条目已丢弃", entry.get("name"))
            continue

        items = entry.get("items")
        if not isinstance(items, list):
            continue

        for raw_item in items:
            if not isinstance(raw_item, dict):
                dropped_malformed += 1
                continue

            title = str(raw_item.get("title") or "").strip()
            insight = str(raw_item.get("insight") or "").strip()
            url = str(raw_item.get("url") or "").strip()

            if not title or not insight or not url:
                dropped_malformed += 1
                continue

            # URL 白名单校验：模型可能编造或改写链接，只接受候选集里真实存在的。
            candidate = by_normalized.get(normalize_url(url))
            if candidate is None:
                dropped_fabricated += 1
                LOG.warning("丢弃疑似编造链接：%s", url[:120])
                continue

            # 同一条链接在一期周报里只应出现一次。
            # 模型偶尔会把一篇文章拆成几条不同角度的"资讯"，输出重复链接 —— 那种重复很扎眼。
            if candidate.normalized_url in seen_urls:
                dropped_duplicate += 1
                LOG.info("丢弃重复链接：%s", candidate.url[:120])
                continue
            seen_urls.add(candidate.normalized_url)

            if len(collected[category]) >= MAX_ITEMS_PER_CATEGORY:
                continue

            collected[category].append(NewsItem(title=title, insight=insight, url=candidate.url))

    if dropped_malformed:
        LOG.warning("丢弃 %d 条字段不完整的条目", dropped_malformed)
    if dropped_fabricated:
        LOG.warning("丢弃 %d 条链接不在候选集内的条目（疑似模型编造）", dropped_fabricated)
    if dropped_duplicate:
        LOG.info("丢弃 %d 条重复链接的条目", dropped_duplicate)

    # 注意：这里不因"一条都没留下"而报错。
    # 模型把全部候选判为无关是**合法**结果（检索命中一堆垃圾时就会这样），
    # 这属于"本周没有相关资讯"，交给 main() 走无新增分支；
    # 只有上面的结构性问题（categories 缺失/类型不对）才算真错误。
    return [(category, collected[category]) for category in CATEGORIES]


# ---------------------------------------------------------------------------
# Markdown 渲染
# ---------------------------------------------------------------------------

def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def render_item(index: int, item: NewsItem) -> str:
    # 每条资讯三要素：粗体标题、结构视角解读、原文链接。
    return "\n".join([
        f"**{index}. {item.title}**",
        "",
        f"> 结构视角：{item.insight}",
        "",
        f"[阅读原文]({item.url})",
        "",
    ])


def render_section(category: str, items: list[NewsItem]) -> str:
    lines = [f"## 【{category}】", ""]
    if not items:
        lines.append("本周期暂无相关资讯。")
        lines.append("")
        return "\n".join(lines)

    for index, item in enumerate(items, start=1):
        lines.append(render_item(index, item))
    return "\n".join(lines)


def render_header(today: str, days: int, total: int) -> str:
    period_start = (datetime.now(BEIJING_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    return "\n".join([
        f"# {DINGTALK_KEYWORD} 储能结构周报（{today}）",
        "",
        f"> 覆盖周期：{period_start} ~ {today} ｜ 新增 {total} 条 ｜ 面向储能结构工程师",
        "",
        "",  # 末尾留出空行，避免与后面的 ## 标题粘连
    ])


def plan_messages(
    header: str,
    sections: list[tuple[str, list[NewsItem]]],
    footer: str,
) -> list[tuple[str, set[str]]]:
    """把周报切成若干条钉钉消息。

    返回 [(消息正文, 该条真正包含的 URL 集合), ...]。
    只有在拆分导致内容被砍掉时，被砍掉的 URL 才不会出现在集合里 ——
    这样它们下周还能重新被推送，不会"抓到但没推、以后永远不再提"。

    优先合并成一条：官方对高频场景的推荐做法就是合并成 markdown 摘要。
    """
    all_urls = {item.url for _, items in sections for item in items}
    full = header + "\n".join(render_section(name, items) for name, items in sections) + footer

    if _byte_len(full) <= MAX_MESSAGE_BYTES:
        return [(full, all_urls)]

    # 超长了：拆成"表头 + 每个分类一条"。
    LOG.info("周报正文 %d 字节，超过 %d 上限，按分类拆分发送", _byte_len(full), MAX_MESSAGE_BYTES)

    messages: list[tuple[str, set[str]]] = [(header, set())]
    total_parts = len(sections)

    for position, (category, items) in enumerate(sections, start=1):
        kept: list[NewsItem] = []
        for item in items:
            probe = render_section(category, kept + [item])
            # 留出续页标记的开销。
            if _byte_len(probe) > MAX_MESSAGE_BYTES - 200:
                break
            kept.append(item)

        body = render_section(category, kept)
        # 每条消息都必须带关键词，否则钉钉会以 310000 拦掉后续几条。
        continuation = f"—— {DINGTALK_KEYWORD} 储能结构周报（续 {position}/{total_parts}）"
        text = f"{header.splitlines()[0]}\n\n{body}\n{continuation}"

        if _byte_len(text) > MAX_MESSAGE_BYTES:
            text = text[: MAX_MESSAGE_BYTES // 3] + f"\n\n{continuation}"

        messages.append((text, {item.url for item in kept}))

    return messages


# ---------------------------------------------------------------------------
# 钉钉推送
# ---------------------------------------------------------------------------

def send_dingtalk(webhook: str, title: str, text: str) -> None:
    """发送一条 markdown 消息。HTTP 200 不代表成功，必须检查 errcode。"""
    if DINGTALK_KEYWORD not in text:
        raise ValueError(f"消息正文缺少钉钉关键词 {DINGTALK_KEYWORD}，会被钉钉以 310000 拒收")

    # msgUuid 是钉钉的幂等 key：超时重试时复用同一个值，避免群里收到两条重复消息。
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
        "at": {"isAtAll": False},
        "msgUuid": uuid.uuid4().hex,
    }

    last_error = ""
    for attempt in range(1, 4):
        try:
            response = requests.post(webhook, json=payload, timeout=15)
        except requests.RequestException as exc:
            last_error = f"网络异常：{exc}"
            LOG.warning("%s（第 %d/3 次），5 秒后重试", last_error, attempt)
            time.sleep(5)
            continue

        try:
            body = response.json()
        except ValueError:
            last_error = f"响应不是 JSON（HTTP {response.status_code}）：{response.text[:200]}"
            LOG.warning(last_error)
            time.sleep(5)
            continue

        # errcode 可能是数字 0 也可能是字符串 "0"。
        try:
            errcode = int(body.get("errcode", -1))
        except (TypeError, ValueError):
            errcode = -1
        errmsg = str(body.get("errmsg") or "")

        if errcode == 0:
            return

        last_error = f"errcode={errcode} errmsg={errmsg}"
        # 错误码说明见 README 的 FAQ。
        if errcode == 310000:
            # 关键词不匹配 / timestamp 无效 / 签名不匹配 / IP 不在白名单 —— 四种失败共用这个码，
            # 必须读 errmsg 才知道是哪种。
            raise RuntimeError(
                f"钉钉安全校验未通过（errcode=310000, errmsg={errmsg}）。\n"
                f"  常见原因：机器人安全设置选了「加签」或「IP 白名单」，但本脚本用的是「自定义关键词」。\n"
                f"  请把机器人的自定义关键词设为：{DINGTALK_KEYWORD}"
            )
        if errcode == 410100:
            raise RuntimeError(
                f"钉钉限流（errcode=410100）。官方限制是每机器人 20 条/分钟，超限会被封 10 分钟。\n"
                f"  本期周报拆分成了多条发送，请稍后重试。"
            )

        LOG.warning("发送失败：%s（第 %d/3 次），5 秒后重试", last_error, attempt)
        time.sleep(5)

    raise RuntimeError(f"钉钉推送连续 3 次失败：{last_error}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def notify_no_news(cfg: dict[str, str], dry_run: bool, today: str, reason: str) -> int:
    """本周无可推送内容时发一条简短提示。

    这是刻意设计的：宁可每周都收到一条"无事发生"，也不要静默跳过 ——
    否则你无法区分「这周确实没新闻」和「任务悄悄挂了」。
    """
    message = "\n".join([
        f"# {DINGTALK_KEYWORD} 储能结构周报（{today}）",
        "",
        reason,
        "",
        "—— 本消息由自动化脚本生成，检索源：Tavily",
    ])
    if dry_run:
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
        LOG.info("dry-run 模式，未推送钉钉")
        return 0

    send_dingtalk(cfg["DINGTALK_WEBHOOK"], f"{DINGTALK_KEYWORD} 储能结构周报（{today}）", message)
    LOG.info("已推送「无新增资讯」提示")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="华宝新能储能结构周报推送")
    parser.add_argument("--dry-run", action="store_true", help="只打印 Markdown，不推送钉钉、不写 history")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条查询，用于快速验证")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    cfg = load_config(dry_run=args.dry_run)

    today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    queries = QUERIES[: args.limit] if args.limit and args.limit > 0 else QUERIES

    history = load_history()
    LOG.info("台账中已有 %d 条历史链接", len(history))

    candidates = search_all(cfg["TAVILY_API_KEY"], queries)

    # 剔除历史已推送过的，以及本轮内部重复的。
    fresh = [c for c in candidates if c.normalized_url not in history]
    LOG.info("剔除历史重复后剩余 %d 条新资讯", len(fresh))

    if not fresh:
        LOG.info("本周没有新增资讯")
        # 没有新内容就不动台账。
        return notify_no_news(cfg, args.dry_run, today, "本周期未检索到新的行业资讯，无新增内容。")

    # 控制送入模型的候选条数。
    if len(fresh) > MAX_INPUT_ITEMS:
        LOG.info("候选 %d 条，截取前 %d 条送入模型", len(fresh), MAX_INPUT_ITEMS)
        fresh = fresh[:MAX_INPUT_ITEMS]

    LOG.info("调用大模型（%s）提炼中……", cfg["OPENAI_MODEL"])
    digest = call_llm(cfg, fresh)
    sections = validate_digest(digest, fresh)

    total = sum(len(items) for _, items in sections)
    LOG.info("模型归类完成，共 %d 条有效资讯", total)

    # 模型把候选全部判为无关 —— 这是合法结果（检索命中一堆无关内容时就会这样），
    # 不是故障。推一条提示让群里知道任务跑过了，而不是静默失败。
    if total == 0:
        LOG.info("模型判定所有候选均与储能结构无关")
        return notify_no_news(cfg, args.dry_run, today, "本周期检索到的内容与储能结构无关，未收录任何资讯。")

    title = f"{DINGTALK_KEYWORD} 储能结构周报（{today}）"
    header = render_header(today, days=7, total=total)
    footer = "\n—— 本消息由自动化脚本生成，检索源：Tavily\n"
    messages = plan_messages(header, sections, footer)

    if args.dry_run:
        for index, (text, _) in enumerate(messages, start=1):
            print("\n" + "=" * 60 + f" 消息 {index}/{len(messages)} " + "=" * 60)
            print(text)
        print("=" * 60 + "\n")
        LOG.info("dry-run 模式，未推送钉钉、未写台账")
        return 0

    pushed_urls: set[str] = set()
    for index, (text, urls) in enumerate(messages, start=1):
        send_dingtalk(cfg["DINGTALK_WEBHOOK"], title, text)
        pushed_urls |= urls
        LOG.info("已推送第 %d/%d 条消息", index, len(messages))
        if index < len(messages):
            # 远低于 20 条/分钟的红线，但留个间隔更稳。
            time.sleep(3)

    # 只记录真正推送出去的 URL —— 被模型丢弃或超出上限的链接下周还能重新出现。
    for url in pushed_urls:
        history[normalize_url(url)] = today
    save_history(history)

    LOG.info("完成：推送 %d 条资讯", len(pushed_urls))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - 顶层兜底，确保非 0 退出让 Actions 变红
        LOG.exception("执行失败")
        sys.exit(1)

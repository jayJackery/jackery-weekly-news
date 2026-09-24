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

# 华宝新能 / Jackery 在售产品线，供模型在竞品分类里做"对标 + 借鉴点"。
#
# ⚠️ 这份清单需要你按实际情况维护。模型被要求**只能引用这里列出的产品线**，
#    清单外的型号它不应编造。产品线有变动（新系列上市、老系列停产）时记得同步这里，
#    否则周报里的"对标"会失准。
#    下面括号里的型号来自自动化检索命中，未逐一核实，请以实际在售为准。
JACKERY_PRODUCTS = """\
- Explorer 系列：便携式户外电源主机（主力产品线）
- SolarSaga 系列：折叠太阳能板（检索命中 SolarSaga 200 / 100 Light，IP68、IEC63163）
- HomePower 系列：家庭备电 / 全屋储能系统（检索命中 HomePower 3600 Pro Max）
- SolarVault 系列：阳台储能系统（检索命中 SolarVault 3，可扩展至全屋）
- FridgeGuard：冰箱等单设备备电。卧式 CTB 结构，约 67mm 超薄，可立放/平放/壁挂，
  单口 800W（峰值 1600W），可扩容至 2kWh，UPS 级无缝切换（平时当智能插座用）"""

# 每周跑完后，模型会把"本期资讯里出现的、但不在 JACKERY_PRODUCTS 里的华宝产品线"报回来，
# 提醒维护者更新上面那份清单。见 report_product_line_updates()。

# URL 路径里出现这些片段就判为无信息价值的页面，在进模型之前就丢掉。
#
# 为什么要在 Python 里硬拦，而不是只靠提示词：实测提示词拦不住。
# 明确写了"纯折扣稿一律丢弃"，模型仍然放进来一条 CNET 的
# /deals/runhood-rallye-600-mini-power-station-deal-... —— 因为它把折扣页
# 包装成了一条像模像样的"可插拔电池模组"解读。路径特征比语义判断可靠得多。
#
# ⚠️ 这份清单**只收促销页和聚合页**，不要往里加厂商的产品页 / 下载页
#    （/product/、/downloads/ 之类）。曾经加过，结果把
#    dji.com/cn/downloads/products/power-auro-2000-elite 一起拦掉了 ——
#    而那是那一周唯一一条大疆新品的信息，得不偿失。
#    厂商自营页交给提示词判断（它确实会丢掉一部分厂商产品页），
#    判断失误的代价远小于硬拦误伤。
JUNK_URL_SEGMENTS = [
    "/deals/", "/deal/", "/coupon", "/promo", "/discount", "/voucher",
    "/shop/", "/store/", "/cart/",
    "/tag/", "/category/",         # 聚合页
]

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
# 法规类不逐条展开，底部最多挂几条溯源链接。
MAX_REGULATION_SOURCES = 3
# 每期最多回报几条"清单外的华宝产品线"提醒。
MAX_PRODUCT_UPDATES = 8
# 提示词约定的"本节没有内容"占位说法。这些不算实质内容。
_PLACEHOLDER_TEXT = {
    "", "无", "本期无", "本期无。", "本期无相关资讯", "本周期暂无相关资讯", "暂无",
}
# 分类标题用的中文序号，与 CATEGORIES 顺序对应。
CN_NUMERALS = ["一", "二", "三", "四", "五"]
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
        # ⚠️ 别写回 "deepseek-chat" —— 2026-09 实测该端点已不再提供这个 id
        # （可用的是 deepseek-v4-pro / deepseek-flash），写错每次调用都会失败。
        "OPENAI_MODEL": get("OPENAI_MODEL", required=False, default="deepseek-flash"),
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


def is_low_value_url(normalized_url: str) -> bool:
    """判断归一化后的 URL 是否是促销页 / 店铺页 / 下载页 / 聚合页。

    这类页面即使内容沾边，对结构工程师也没有情报价值，而且模型常常把
    "某款产品打折" 包装成一条像模像样的产品解读放进来 —— 所以在送进模型前就拦掉。

    只按**路径分段**匹配，不做子串匹配：`/sale` 这种片段会误伤正常文章路径
    （比如 /wholesale-market-report），必须要求它自成一段。
    """
    try:
        path = urlsplit(normalized_url).path.lower()
    except ValueError:
        return False

    junk_words = [s.strip("/") for s in JUNK_URL_SEGMENTS]
    for segment in path.split("/"):
        if not segment:
            continue
        for junk in junk_words:
            # 精确段匹配，或作为某段的前缀（覆盖 /deals-2026 这类写法）。
            if segment == junk or segment.startswith(junk + "-"):
                return True
    return False


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
        skipped_junk = 0
        for item in results:
            raw_url = str(item.get("url") or "")
            normalized = normalize_url(raw_url)
            if not normalized:
                continue
            if normalized in found:
                continue
            if is_low_value_url(normalized):
                skipped_junk += 1
                LOG.info("丢弃低价值页面（促销/店铺/下载/聚合页）：%s", normalized[:110])
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

        LOG.info("查询「%s」返回 %d 条，新增 %d 条，丢弃低价值 %d 条",
                 query, len(results), added, skipped_junk)

    LOG.info("本轮共获得 %d 条不重复候选资讯", len(found))
    return list(found.values())


# ---------------------------------------------------------------------------
# 大模型提炼
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""你是一名储能行业分析师，服务于华宝新能（Jackery）的储能结构工程师团队。
你的任务是把检索到的原始资讯，提炼成一份每周行业情报，供结构工程师快速掌握竞品动向与技术趋势。
读者是工程师，时间有限 —— 结论先行、信息密度高、不写套话。

必须严格输出如下 JSON 结构（只输出 JSON，不要任何解释文字，不要 Markdown 代码围栏）：
{{
  "highlights": ["竞品：一句话", "结构：一句话", "法规：一句话"],
  "categories": [
    {{"name": "{CATEGORY_COMPETITOR}", "items": [
      {{"title": "...", "insight": "...", "jackery_angle": "...", "url": "..."}}]}},
    {{"name": "{CATEGORY_STRUCTURE}", "items": [
      {{"title": "...", "insight": "...", "url": "..."}}]}},
    {{"name": "{CATEGORY_REGULATION}", "summary": "一整段话", "sources": [
      {{"title": "...", "url": "..."}}]}}
  ],
  "product_line_updates": ["本期看到的、不在下方清单里的华宝产品线名"]
}}

★ 三个分类的处理方式**各不相同**，请严格按下面来：

一、【{CATEGORY_COMPETITOR}】逐条展开，每条都要有对标
   收录 EcoFlow、Anker、Bluetti 及国内厂商（正浩、德兰明海、安克创新、大疆等）的新品发布、
   形态创新、价格与渠道动作。每条输出 title / insight / jackery_angle / url 四个字段。

二、【{CATEGORY_STRUCTURE}】逐条展开，只写结构视角
   收录外壳防跌落与抗冲击、IP 防护等级、Pack 结构与模组堆叠、热管理与风道、
   阻燃材料与结构件工艺、可维修性与装配方式。每条只输出 title / insight / url。

三、【{CATEGORY_REGULATION}】**绝对不要逐条列条目**
   把本期所有法规/标准/出海相关内容（UL 2743、欧洲阳台储能 Balkonkraftwerk 安装规范、
   各国并网与出口认证、关税与贸易政策）合并成**一整段话**写进 summary 字段。
   读者不会一条条点开法规新闻 —— 他们要的是"这周监管面发生了什么变化、对我们意味着什么"。
   summary 写 100~180 字，讲清三件事：涉及哪些市场 / 规则具体怎么变 / 对储能产品设计或出海的影响。
   不要写成"某某网站报道了……"，直接给结论。
   另外**最多挑 3 条**最值得追溯原文的放进 sources（只有 title 和 url 两个字段）。
   本期确实没有法规相关内容时，summary 写"本期无"，sources 返回 []。

字段要求：
- highlights：3 条，分别对应上面三个分类，每条一句话（25 字以内）点出本期最值得注意的变化，
  开头用「竞品：」「结构：」「法规：」标注。某一类没有内容就写「竞品：本期无」。
- title：中文标题，简洁准确，一句话说清这条资讯是什么。不要加方括号前缀。
- insight：1~2 句，从**结构工程视角**切入 —— 外壳、模组、散热、防护、装配工艺、材料、公差、可靠性。
  不要复述原文，不要写"该文章介绍了……"这类空话。
- jackery_angle：**仅竞品分类可能用到。有就写，没有就返回空字符串 ""** ——
  这是可选项，**不要为了凑满这个字段而硬编一段话**。按下面的优先级取材：
  ① 这条动态若能对上华宝某条具体产品线、某个形态或容量段 —— 先写对标，再写结构层面的
     借鉴点或风险点。对标只能引用下面产品清单里列出的产品线，清单外的型号一律不要编造。
  ② 若对不上具体产品线，但整个行业的形态变化对结构设计有普适启示（装配方式、散热路线、
     防护思路、材料选型），就写这层**宏观经验借鉴**，不必强行扯到某款产品。
  ③ 两者都不成立（纯渠道动作、纯资本面、纯人事变动）—— 留空字符串 ""。
  总长 60 字以内。**宁缺毋滥：硬凑的对标比没有对标更糟。**
- url / sources[].url：必须**原样复制**输入列表中给出的 URL，一个字都不要改。
  绝对不要自己编造或拼接链接。

另外单独返回一个字段（它不进周报正文，只给维护者看）：
- product_line_updates：本期资讯里提到的、**属于华宝新能/Jackery 但不在下方产品清单里**的
  产品线或产品名。用途是提醒维护者该更新清单了。只填你能从原文确认属于华宝的，
  拿不准的一律不要填。没有就返回 []。

华宝新能 / Jackery 在售产品线（jackery_angle 只能引用这里列出的产品线）：
{JACKERY_PRODUCTS}

归类规则：
- 同一条资讯只放进最贴切的一个分类，不要重复收录。
- 全部候选都无法归入任何分类时，前两个分类的 items 返回 []，法规 summary 写"本期无"。

收录标准：宁缺毋滥，以下几类一律丢弃 ——
- **纯折扣/促销稿**：只讲"降价了、打几折、哪里买得到"，不含产品形态或技术信息的。
- **厂商自营页与营销内容**：链接指向品牌官网产品页、电商店铺页、SEO 软文或官方博客的自我推介文章，
  而非第三方媒体报道的。
- **自动生成页**：链接带随机地址参数、或明显由模板批量生成的聚合页、榜单页、导航页。
- **与储能/便携电源/阳台储能无关的内容**：汽车、消费电子、通用半导体、食品、政务等。
- **纯资本面稿件**：股价、概念股炒作、财报数字罗列。
  例外：如果财报或公告披露了产品线规划、技术路线、认证资质（如 IP 等级、UL 认证）
  等实质性工程信息，可以收录，insight 要写这些工程信息而非财务数字。

另外：结构工程师更关心"产品怎么做的"而不是"卖多少钱"。同等条件下，
优先收录新产品与新形态、结构与热管理技术、法规标准变化。
"""


@dataclass
class NewsItem:
    title: str
    insight: str
    url: str
    # 仅竞品分类有值：与华宝对应产品线的对标 + 借鉴点。
    jackery_angle: str = ""


@dataclass
class Digest:
    """一期周报的内容。三个分类的处理方式不同，所以不共用一个结构。"""

    # 顶部"本周速览"的三句结论，可空。
    highlights: list[str]
    # 逐条展开的分类：[(分类名, 条目), ...]，固定为竞品、结构两类。
    sections: list[tuple[str, list[NewsItem]]]
    # 法规类不逐条列，只留一段综述 + 少量溯源链接 [(标题, URL), ...]。
    regulation_summary: str
    regulation_sources: list[tuple[str, str]]
    # 本期出现的、不在 JACKERY_PRODUCTS 里的华宝产品线。不进周报，只用于提醒维护者更新清单。
    product_line_updates: list[str]

    @property
    def total_items(self) -> int:
        return sum(len(items) for _, items in self.sections)

    @property
    def regulation_filled(self) -> bool:
        return self.regulation_summary.strip() not in _PLACEHOLDER_TEXT

    def is_empty(self) -> bool:
        """整期没有任何实质内容。

        "本期无"是提示词约定的占位说法，不算内容 —— 否则检索命中一堆垃圾时，
        模型按约定返回占位词，这条空周报照样会被推出去。
        """
        return self.total_items == 0 and not self.regulation_filled

    def consistent_highlights(self) -> list[str]:
        """丢掉指向空小节的速览条目。

        实测会撞上：模型在速览里写了「法规：欧洲多国放开阳台光伏」，
        正文的法规综述却返回空字符串 —— 速览承诺了、正文没有，读起来像坏了。
        速览条目的前缀（竞品/结构/法规）是提示词约定的，据此就能对上小节。
        识别不出前缀的条目原样保留，不做无根据的推断。
        """
        filled = {
            "竞品": bool(self.sections[0][1]) if len(self.sections) > 0 else False,
            "结构": bool(self.sections[1][1]) if len(self.sections) > 1 else False,
            "法规": self.regulation_filled,
        }

        kept, dropped = [], []
        for highlight in self.highlights:
            for prefix, has_content in filled.items():
                if highlight.startswith(prefix):
                    (kept if has_content else dropped).append(highlight)
                    break
            else:
                kept.append(highlight)

        if dropped:
            LOG.warning(
                "速览里有 %d 条指向了空小节，已丢弃以免前后不一致：%s",
                len(dropped), "；".join(dropped),
            )
        return kept


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


def validate_digest(data: dict[str, Any], candidates: list[Candidate]) -> Digest:
    """校验模型输出，过滤掉编造的链接，组装成 Digest。"""
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
    regulation_summary = ""
    regulation_sources: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    dropped_duplicate = 0
    dropped_fabricated = 0
    dropped_malformed = 0

    def resolve_url(raw_url: Any) -> Candidate | None:
        """URL 白名单校验：模型可能编造或改写链接，只接受候选集里真实存在的。

        同时做去重 —— 模型偶尔会把一篇文章拆成几条不同角度的"资讯"输出重复链接，
        那种重复在周报里很扎眼。
        """
        nonlocal dropped_duplicate, dropped_fabricated
        url = str(raw_url or "").strip()
        if not url:
            return None
        candidate = by_normalized.get(normalize_url(url))
        if candidate is None:
            dropped_fabricated += 1
            LOG.warning("丢弃疑似编造链接：%s", url[:120])
            return None
        if candidate.normalized_url in seen_urls:
            dropped_duplicate += 1
            LOG.info("丢弃重复链接：%s", candidate.url[:120])
            return None
        seen_urls.add(candidate.normalized_url)
        return candidate

    for entry in raw_categories:
        if not isinstance(entry, dict):
            continue
        category = canonicalize(entry.get("name"))
        if category is None:
            LOG.warning("模型返回了未知分类「%s」，其条目已丢弃", entry.get("name"))
            continue

        # 法规类走 summary + sources，与前两类结构不同。
        if category == CATEGORY_REGULATION:
            regulation_summary = str(entry.get("summary") or "").strip()
            raw_sources = entry.get("sources")
            if isinstance(raw_sources, list):
                for raw_source in raw_sources:
                    if not isinstance(raw_source, dict):
                        dropped_malformed += 1
                        continue
                    title = str(raw_source.get("title") or "").strip()
                    candidate = resolve_url(raw_source.get("url"))
                    if not title or candidate is None:
                        dropped_malformed += 1
                        continue
                    if len(regulation_sources) >= MAX_REGULATION_SOURCES:
                        continue
                    regulation_sources.append((title, candidate.url))
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
            if not title or not insight:
                dropped_malformed += 1
                continue

            candidate = resolve_url(raw_item.get("url"))
            if candidate is None:
                continue

            if len(collected[category]) >= MAX_ITEMS_PER_CATEGORY:
                continue

            collected[category].append(NewsItem(
                title=title,
                insight=insight,
                url=candidate.url,
                jackery_angle=str(raw_item.get("jackery_angle") or "").strip(),
            ))

    if dropped_malformed:
        LOG.warning("丢弃 %d 条字段不完整的条目", dropped_malformed)
    if dropped_fabricated:
        LOG.warning("丢弃 %d 条链接不在候选集内的条目（疑似模型编造）", dropped_fabricated)
    if dropped_duplicate:
        LOG.info("丢弃 %d 条重复链接的条目", dropped_duplicate)

    raw_highlights = data.get("highlights")
    highlights = [
        str(h).strip() for h in raw_highlights
        if isinstance(raw_highlights, list) and str(h).strip()
    ][:len(CATEGORIES)]

    raw_updates = data.get("product_line_updates")
    product_line_updates = [
        str(u).strip() for u in raw_updates
        if isinstance(raw_updates, list) and str(u).strip()
    ][:MAX_PRODUCT_UPDATES]

    # 注意：这里不因"一条都没留下"而报错。
    # 模型把全部候选判为无关是**合法**结果（检索命中一堆垃圾时就会这样），
    # 这属于"本周没有相关资讯"，交给 main() 走无新增分支；
    # 只有上面的结构性问题（categories 缺失/类型不对）才算真错误。
    return Digest(
        highlights=highlights,
        sections=[(c, collected[c]) for c in CATEGORIES if c != CATEGORY_REGULATION],
        regulation_summary=regulation_summary,
        regulation_sources=regulation_sources,
        product_line_updates=product_line_updates,
    )


# ---------------------------------------------------------------------------
# Markdown 渲染
# ---------------------------------------------------------------------------

def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def render_item(index: int, item: NewsItem) -> str:
    # 每条资讯：粗体标题 + 引用块（结构视角 / 对标借鉴）+ 原文链接。
    # 两个视角行都放进同一个引用块（连续的 > 行在 Markdown 里属于同一个 blockquote），
    # 视觉上聚成一坨，比拆成两个引用块省纵向空间。
    lines = [f"**{index}. {item.title}**", ""]
    if item.insight:
        lines.append(f"> 结构视角：{item.insight}")
    if item.jackery_angle:
        lines.append(f"> 对标借鉴：{item.jackery_angle}")
    lines += ["", f"[阅读原文]({item.url})", ""]
    return "\n".join(lines)


def render_section(position: int, category: str, items: list[NewsItem]) -> str:
    numeral = CN_NUMERALS[position - 1] if position <= len(CN_NUMERALS) else str(position)
    # 标题里带条数，读者一眼知道这个小节要花多久读完。
    lines = [f"## {numeral}、【{category}】（{len(items)} 条）", ""]
    if not items:
        lines.append("本周期暂无相关资讯。")
        lines.append("")
        return "\n".join(lines)

    for index, item in enumerate(items, start=1):
        lines.append(render_item(index, item))
    return "\n".join(lines)


def render_regulation(position: int, summary: str, sources: list[tuple[str, str]]) -> str:
    """法规类渲染成一整段综述 + 底部溯源链接，不逐条展开。

    读者不会一条条点开法规新闻，所以这里刻意不做条目化排版 ——
    一段话读完即可，想深挖的再点底部的链接。
    """
    numeral = CN_NUMERALS[position - 1] if position <= len(CN_NUMERALS) else str(position)
    lines = [f"## {numeral}、【{CATEGORY_REGULATION}】", ""]
    lines.append(summary or "本周期暂无相关资讯。")
    lines.append("")
    if sources:
        links = " ｜ ".join(f"[{title}]({url})" for title, url in sources)
        lines += [f"**溯源链接**：{links}", ""]
    return "\n".join(lines)


def render_header(today: str, days: int, total: int, highlights: list[str]) -> str:
    period_start = (datetime.now(BEIJING_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    lines = [
        f"# {DINGTALK_KEYWORD} 储能结构周报（{today}）",
        "",
        f"> 覆盖周期：{period_start} ~ {today} ｜ 本期 {total} 条 ｜ 面向储能结构工程师",
        "",
    ]
    # "本周速览"是给读者一个跳过全文的理由：三句话看完就知道这周值不值得细读。
    # 没有速览时也不留空标题。
    if highlights:
        lines += ["**本周速览**", ""]
        lines += [f"- {h}" for h in highlights]
        lines.append("")
    lines.append("")  # 末尾留空行，避免与后面的 ## 标题粘连
    return "\n".join(lines)


def plan_messages(
    header: str,
    sections: list[tuple[str, list[NewsItem]]],
    tail: tuple[str, set[str]],
    footer: str,
) -> list[tuple[str, set[str]]]:
    """把周报切成若干条钉钉消息。

    tail 是已经渲染好的法规综述块（正文 + 它包含的 URL），它很短，按整块处理。

    返回 [(消息正文, 该条真正包含的 URL 集合), ...]。
    只有在拆分导致内容被砍掉时，被砍掉的 URL 才不会出现在集合里 ——
    这样它们下周还能重新被推送，不会"抓到但没推、以后永远不再提"。

    优先合并成一条：官方对高频场景的推荐做法就是合并成 markdown 摘要。
    """
    tail_text, tail_urls = tail
    all_urls = {item.url for _, items in sections for item in items} | tail_urls

    rendered = [render_section(i, name, items) for i, (name, items) in enumerate(sections, start=1)]
    rendered.append(tail_text)
    full = header + "\n".join(rendered) + footer

    if _byte_len(full) <= MAX_MESSAGE_BYTES:
        return [(full, all_urls)]

    # 超长了：拆成"速览+法规一条，之后每个分类一条"。
    # 第一条刻意做成一分钟能读完的版本（速览 + 法规综述），只看结论的人到这就够了。
    LOG.info("周报正文 %d 字节，超过 %d 上限，按分类拆分发送", _byte_len(full), MAX_MESSAGE_BYTES)

    head_line = header.splitlines()[0]
    messages: list[tuple[str, set[str]]] = [(header + tail_text, set(tail_urls))]
    total_parts = len(sections)

    for position, (category, items) in enumerate(sections, start=1):
        kept: list[NewsItem] = []
        for item in items:
            probe = render_section(position, category, kept + [item])
            # 留出续页标记的开销。
            if _byte_len(probe) > MAX_MESSAGE_BYTES - 200:
                break
            kept.append(item)

        body = render_section(position, category, kept)
        # 每条消息都必须带关键词，否则钉钉会以 310000 拦掉后续几条。
        continuation = f"—— {DINGTALK_KEYWORD} 储能结构周报（续 {position}/{total_parts}）"
        text = f"{head_line}\n\n{body}\n{continuation}"

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


def report_product_line_updates(updates: list[str]) -> None:
    """把"清单外的华宝产品线"报给维护者。

    这条刻意不进周报正文 —— 它是维护事项，不是给群里的行业情报。
    输出到两处：日志（本地跑、Actions 日志都看得到），
    以及 GitHub Actions 的 Step Summary（不翻日志也能在运行页面顶部看到）。
    """
    if not updates:
        return

    LOG.warning(
        "发现 JACKERY_PRODUCTS 清单外的华宝产品线：%s —— 请更新 main.py 顶部的 JACKERY_PRODUCTS",
        "、".join(updates),
    )

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## ⚠️ JACKERY_PRODUCTS 需要更新\n\n")
            fh.write("本期资讯里出现了清单外的华宝产品线，模型没法对它们做对标：\n\n")
            for name in updates:
                fh.write(f"- {name}\n")
            fh.write("\n请把它们补进 `main.py` 顶部的 `JACKERY_PRODUCTS`。\n")
    except OSError as exc:
        # 写不进 Step Summary 不影响主流程 —— 日志里已经记了一份。
        LOG.warning("写入 GITHUB_STEP_SUMMARY 失败：%s", exc)


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
    digest = validate_digest(call_llm(cfg, fresh), fresh)

    LOG.info(
        "模型归类完成：竞品/结构共 %d 条，法规综述 %d 字",
        digest.total_items, len(digest.regulation_summary),
    )
    report_product_line_updates(digest.product_line_updates)

    # 模型把候选全部判为无关 —— 这是合法结果（检索命中一堆无关内容时就会这样），
    # 不是故障。推一条提示让群里知道任务跑过了，而不是静默失败。
    if digest.is_empty():
        LOG.info("模型判定所有候选均与储能结构无关")
        return notify_no_news(cfg, args.dry_run, today, "本周期检索到的内容与储能结构无关，未收录任何资讯。")

    title = f"{DINGTALK_KEYWORD} 储能结构周报（{today}）"
    header = render_header(
        today, days=7, total=digest.total_items, highlights=digest.consistent_highlights(),
    )
    tail = (
        render_regulation(len(digest.sections) + 1, digest.regulation_summary, digest.regulation_sources),
        {url for _, url in digest.regulation_sources},
    )
    footer = "\n—— 本消息由自动化脚本生成，检索源：Tavily\n"
    messages = plan_messages(header, digest.sections, tail, footer)

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

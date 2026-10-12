#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""华宝新能（Jackery）储能结构工程师 · 每周行业资讯推送

流程：OpenRouter（perplexity/sonar-pro-search）联网检索并撰写 → 本地校验与分段 → 推送钉钉群。

OpenRouter 上的 sonar 系列本身就会联网检索，检索与撰写在一次调用里完成，
所以本地不做搜索、也不做"让模型返回 JSON 再本地渲染"那一套 —— 那是旧版
（Tavily + DeepSeek 方案）的产物，已随重构移除，不要重新引入。

⚠️ **唯一的例外是跨周去重台账 `pushed_history.json`**（见下面的「跨周台账」一节）——
它是 2026-09 为配合检索窗口放宽到 14 天而加回来的，不是旧方案的残留。
**不要因为"旧版有个同名的 history_urls.json"就把它删掉**（何况那个文件自始至终是空的，
从来没生效过 —— 见该节注释）。

用法：
    python main.py                # 完整流程
    python main.py --dry-run      # 只打印 Markdown，不推送钉钉
    python main.py --out r.md     # 额外把原文存成文件，便于先审阅再发
    python main.py --rebuild      # 只从 docs/*.md 重建站点
    python main.py --alert-failure  # 失败告警，由 workflow 在任一步失败时调用

环境变量见 README.md。任何异常都会以非 0 退出码结束，以便 GitHub Actions 变红告警。
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

try:
    import requests
except ImportError:
    sys.exit("缺少依赖：requests。请先执行 pip install -r requirements.txt")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

BEIJING_TZ = timezone(timedelta(hours=8))

# 检索时间窗。
#
# ⚠️ **改这个数字时，必须确认全文件的"近 N 天"都跟着变了。** 日期区间由 `_window()` 算，
# 但"N 天"这五个字是硬编码在提示词里的 —— 只改常量会让提示词自相矛盾
# （例如"请检索并汇总 09-10 至 09-24（近 7 天）"），而模型会听那个更简单、重复更多遍的数字。
# 所以下面每一处措辞都用 f-string 插值这个常量，不要再写死。
#
# 为什么是 14 而不是 7：7 天太窄，五个板块摊薄检索预算后经常凑不满，模型就会往窗口外找
# 九月初的旧闻 —— 使用者反馈的"时效性"问题根因在这里。放宽到两周后它反而守得住。
# 代价是下周的窗口会覆盖本周报过的内容，所以必须配合跨周台账一起上（见下）。
WINDOW_DAYS = 14

# ---------------------------------------------------------------------------
# 跨周台账：记录"已经推送给读者"的条目，下周不让它再出现
# ---------------------------------------------------------------------------
# 为什么需要它：窗口放宽到 14 天后，下周的检索窗口会**完整覆盖**本周报过的内容，
# 不去重的话读者会连续两周看到同一批新闻。
#
# 为什么不复用旧版的 history_urls.json：那个文件（见 git show 8310b91:history_urls.json）
# **自始至终是空的**（`{"updated_at": "", "urls": {}}`）—— 旧版那套去重从来没真正生效过。
# 而且它的 schema 依赖 Tavily 的结果结构。所以这里是一个新文件、新 schema，
# 唯一沿用旧版的只有"由 workflow 回写仓库"这个思路。
HISTORY_PATH = Path(__file__).resolve().parent / "pushed_history.json"
HISTORY_VERSION = 1
# 保留期 60 天，比 14 天窗口宽得多 —— 因为真正的约束不是窗口，而是**模型的回溯范围没有上限**
# （见 CLAUDE.md：时间窗只有提示词约束，它时不时会把三周前的东西翻出来）。
# 保留久一点只会多拦，不会漏拦；条数上限兜住提示词长度。
HISTORY_KEEP_DAYS = 60
HISTORY_MAX_ENTRIES = 200

# 归一化 URL 时要剥掉的跟踪参数。**只剥这些，不要剥掉整个 query** —— 剥整段会把
# `shopulstandards.com/ProductDetail.aspx?productId=UL2743` 和同站其它页面塌成同一个键，
# 把"漏去重"（无害）变成"错去重"（静默丢真情报）。
TRACKING_QUERY_KEYS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "spm", "from", "ref", "referrer", "commtag", "src", "fbclid", "gclid",
    "mc_cid", "mc_eid", "share_source", "share_medium", "share_plat", "share_token",
})

# 栏目页/聚合页的路径段与查询参数。这类页面在报告里反复出现且内容每周都在变，
# 一旦进台账就成了一个"稳定键"，会误杀未来所有引用它的条目。
# 判据与 ROLE_AND_RULES 里禁止引用的那几种形状保持一致。
INDEX_PATH_SEGMENTS = frozenset({
    "category", "categories", "tag", "tags", "subject", "subjects",
    "industry-updates", "topic", "topics", "channel", "channels",
    "newslist", "list", "archive", "search", "author", "column",
})
INDEX_QUERY_KEYS = frozenset({"column_id", "cat_id", "category_id", "tag_id", "columnid"})

# 钉钉自定义机器人的安全关键词校验的是 markdown.text 正文。
# 官方文档从未说明 title 是否参与校验，社区反馈只放 title 会被 310000 拒收，
# 所以这个关键词必须出现在正文里，且**拆分出的每条消息都要带**。
DINGTALK_KEYWORD = "[行业资讯]"

# 经 OpenRouter 接入 Perplexity 的 sonar-pro-search。
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_URL = f"{OPENROUTER_BASE_URL}/chat/completions"
OPENROUTER_MODEL = "perplexity/sonar-pro-search"
# 0.2 而非 0：报告需要一定的组织语言自由度，但检索与数据事实必须可复现。
OPENROUTER_TEMPERATURE = 0.2
# 该模型的 max_completion_tokens 上限是 8000（查 /models 得到）。**直接给满**：
# 窗口从 7 天放宽到 14 天、又加了台账提示词之后，实测 r3.md 时代就已经到 6000 的 83%，
# 留余量反而会把末尾的板块四、五截掉 —— 而截断是静默的（只看 content 看不出来）。
# 配套措施：call_openrouter 在 finish_reason=length 时打 WARNING。
OPENROUTER_MAX_TOKENS = 8000
# OpenRouter 要求的调用方标识，用于在它的排行榜/日志里区分应用。非必填但建议带上。
OPENROUTER_REFERER = "https://github.com"
OPENROUTER_TITLE = "Storage Weekly Bot"
#
# ⚠️ 这里**没有** search_recency_filter —— 该参数是 Perplexity 原生接口的，
# OpenRouter 的 perplexity/sonar-pro-search 不支持（查 /models 的 supported_parameters
# 只有 frequency_penalty / include_reasoning / max_tokens / presence_penalty /
# reasoning / structured_outputs / temperature / top_k / top_p / web_search_options）。
# 传了会被忽略甚至报错，所以"只取近 N 天"现在**完全靠提示词约束**（见 _window 与
# build_user_prompt），不再有 API 层的硬保证 —— 跨周台账就是为这个不确定性兜底的。
# 同理 return_citations 也不支持，引用改从响应里尽力提取。
OPENROUTER_TIMEOUT = 300        # 秒；联网检索 + 长文撰写，给足时间
OPENROUTER_RETRIES = 2
OPENROUTER_BACKOFF = 8          # 秒

# 余额预警：估算"还够推几期"，**剩到 1 期或更少**才在摘要末尾附一句提醒。
# 阈值定得这么低是刻意的（使用者明确要过"仅剩一期的时候再报错"）：更早的提醒是噪声，
# 每周都看到一句"余额不多"很快就会当成背景噪声无视掉，不如只在真要断的时候说一次。
# 代价是只有一期的提前量 —— 兜底是**失败告警**：余额真耗尽时那次运行会 402 退出，
# 告警会主动发到群里，不会静默停摆。
OPENROUTER_LOW_RUNS_LEFT = 1
# 单期成本的实测值，**唯一用途是把余额换算成"还够推几期"** —— 它同时决定那句提醒
# 什么时候出现：这个数偏大 → 估出的期数偏少 → 提醒来得偏早。所以万一它失准，
# 宁可略偏大（早提醒一句无害，晚提醒会真的断在某一周）。
# 2026-10-12 实测：当日 3 次运行共 $0.79961 → 每期 ≈ $0.2665；
# 用月度数据交叉核对（$1.30217 / 5 次）结果一致。改用例、换模型、调 WINDOW_DAYS
# 都会让它失准。失准的后果只是提醒早晚差一期，不会让任何东西失败。
OPENROUTER_COST_PER_RUN_USD = 0.27

# 单条钉钉消息正文的 UTF-8 字节上限。
# 官方对自定义机器人 markdown 正文长度没有任何明文规定（流传的 20000 字节查无出处），
# 所以不留险，主动截断到 8KB。注意中文一字 3 字节，字符数 ≠ 字节数。
MAX_MESSAGE_BYTES = 8000
# 多条消息之间的间隔。官方限流是每机器人 20 条/分钟，超限直接封 10 分钟。
MESSAGE_INTERVAL = 3            # 秒
DINGTALK_RETRIES = 2
DINGTALK_BACKOFF = 5            # 秒

# ---------------------------------------------------------------------------
# 网页站点（GitHub Pages）
# ---------------------------------------------------------------------------
# 每期报告同时落一份到 docs/，随台账一起由 workflow 提交回仓库，
# GitHub Pages 从 `main` 分支的 /docs 目录发布。钉钉群里只发"摘要 + 链接"，
# 全文在网页上 —— 群消息会被后续聊天顶掉，网页不会。
#
# ⚠️ **目录必须叫 docs/，不能改成 reports/ 之类。**
# GitHub Pages 的 "Deploy from a branch" 只给 `/ (root)` 与 `/docs` 两个源选项。
# 叫别的名字就只能选根目录，那会把**整个仓库**当网站发布 —— main.py、CLAUDE.md、
# pushed_history.json 全部可被直接下载。
#
# ⚠️ **docs/ 里的内容绝不能出现生成时间戳、版本号、datetime.now()。**
# 整个站点是**幂等重建**的：同样的 .md 输入必须产出逐字节相同的 .html。
# 一旦有字段每次都变，工作区就永远是脏的，workflow 最后的 `git rebase` 会报
# "cannot rebase: You have unstaged changes"，重试 3 次全失败，job 周周变红。
DOCS_DIR = Path(__file__).resolve().parent / "docs"

# GitHub Pages 站点根，末尾不带斜杠。可通过环境变量 SITE_BASE_URL 覆盖。
# **设成空串就关闭整个网页功能**，退回"推送全文"的旧行为
# （plan_messages 的分段路径还在，就是给这个兜底留的）。
DEFAULT_SITE_BASE_URL = "https://jayJackery.github.io/jackery-weekly-news"

# 归档首页与当期页面的文件名形状。写成常量是为了和 workflow 里的白名单正则保持一致 ——
# 两处一旦漂移，CI 会因为"暂存区出现白名单外的路径"而硬失败。
SITE_INDEX_NAME = "index.html"

# ---------------------------------------------------------------------------
# 促销稿过滤
# ---------------------------------------------------------------------------
# 为什么要在 Python 里硬拦：**提示词拦不住，实测过两轮**。
# 2026-09-24 那次板块一 7 条里有 3 条是 Electrek 的折扣稿：
#   · Jackery HomePower 3600 Pro Max —— .../jackery-early-access-prime-day-sale-...
#   · Anker SOLIX E10             —— .../anker-solix-e10-system-exclusive-...
#   · EcoFlow DELTA 3 Ultra Plus  —— .../ecoflow-early-prime-day-...
# 模型自己在正文里都写了"该条信息属于销售活动"，却仍然把它们当作竞品动态列了出来 ——
# 因为容量、价格这些数字是真实的，它不认为自己在编造。旧版（Tavily 方案）踩的是同一个坑，
# 最后也是靠 Python 侧的 URL 过滤才解决（见 CLAUDE.md 的已知陷阱）。
#
# 匹配方式：**URL 路径先按 `/` 分段，段内再按 `-` `_` 切词，逐词比对**。
# 刻意不做整串子串匹配 —— 旧版 JUNK_URL_SEGMENTS 曾用子串匹配误伤过大疆唯一的新品。
# 只匹配路径，**不匹配域名**：9to5Toys 这类站本身偏导购，但它的新品报道是有效情报。
PROMO_URL_TOKENS = frozenset({
    "sale", "sales", "deal", "deals", "discount", "coupon", "promo",
    "clearance", "exclusive", "savings", "bogo", "giveaway",
})
# 多词短语：在「按 - 切出的词序列」里**连续**出现才算命中，避免 `prime` 和 `day` 各在一处也中招。
PROMO_URL_PHRASES = (
    ("prime", "day"),
    ("black", "friday"),
    ("cyber", "monday"),
    ("early", "access"),
)
# `30-off` / `30-percent-off` 形态。
# ⚠️ **不要把 `off` 单独放进 PROMO_URL_TOKENS** —— `off-grid`（离网）是本领域核心词，
# 单独列 off 会把它连同大量正常的离网产品页一起误伤。这个正则要求 off 前面紧跟数字。
# 末尾的 `(?!-?[a-z])` 是第二道：**要求 off 不再接一个连字符复合词**。
# 实测踩到过：`bluetti-balco-500-off-grid`、`dji-power-2000-off-grid-power-station`
# 里的 `500-off` / `2000-off` 会被前半段匹配上 —— 那就是"500 型，离网"，
# 跟"打五折"毫无关系。代价是漏掉 `30-off-anker-solix` 这种把商品名接在后面的写法，
# 但这类 slug 通常改用 `-deal` / `-sale`，会被词表兜住，所以漏得起。
PROMO_OFF_RE = re.compile(r"(?<![a-z0-9])\d+-(?:percent-)?off(?!-?[a-z])")

# ---------------------------------------------------------------------------
# 第二道，也是更可靠的一道：模型自己的"否定式自述"
# ---------------------------------------------------------------------------
# 实测原话（r7.md 里 Jackery 那一条，逐字抄自输出）：
#   「该条信息属于销售活动，原文没有披露本周期新的结构形态、模块尺寸、重量变化、
#     IP 等级或连接架构变化，因此不将其作为新品或结构改款处理。」
# 模型**已经判断出这条没有结构情报价值，却仍然把它写进了板块一** ——
# 因为容量和价格是真数字，它不觉得自己在编造，于是先写再补一句免责。
#
# 这条信号比 URL 特征可靠得多：换个不带 sale / deal 字样的域名，URL 那道就认不出来，
# 但"我判断这条不是新品"这句话是模型自己下的结论，与域名无关。
# 命中即整条删除 —— 既然它自己都说不是新品，这条就不该占一个条目。
SELF_DISQUALIFY_RE = re.compile(
    "|".join((
        # 否定式结论：「不将其作为新品或结构改款处理」
        r"不(?:将其|把它|该条|这条|该信息)?(?:作为|列为|计入|纳入|视作|视为)"
        r"(?:本周|近期|本次)?(?:新品|竞品动态|结构改款|结构变化|结构升级|新品发布)",
        r"(?:并非|不是|算不上|不属于)(?:本周|近期)?新品",
        r"不(?:构成|属于)(?:本周|近期)?(?:新品|结构改款|结构变化|结构升级|产品迭代)",
        # 把事件定性成销售活动：「该条信息属于销售活动」
        r"(?:该条|这条|该信息|本条|上述)(?:信息|消息|内容)?(?:分别)?属于"
        r"(?:销售|促销|营销|优惠|折扣|降价)活动",
        r"属于(?:销售|促销|营销|优惠|折扣|降价)活动",
    ))
)



# 华宝新能 / Jackery 现有产品线。第五板块的启发建议只能引用这里列出的产品线，
# 避免模型编造型号。**产品线变动时必须同步这里。**
JACKERY_PRODUCTS = """\
- Explorer 系列：便携式户外电源主机（主力产品线）
- SolarSaga 系列：折叠太阳能板（IP68、IEC 63163、IEC 61701 盐雾认证）
- HomePower 系列：家庭备电 / 全屋储能系统
- SolarVault 系列：阳台储能系统（可扩展至全屋）
- FridgeGuard：冰箱等单设备备电，卧式 CTB 结构，约 67mm 超薄，可立放/平放/壁挂，
  单口 800W（峰值 1600W），可扩容至 2kWh，UPS 级无缝切换"""

LOG = logging.getLogger("newsbot")


# ---------------------------------------------------------------------------
# 跨周台账（读取、写入、渲染、抽取）
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """把 URL 归一成去重用的键。

    统一 http/https、去掉 `www.`、**只剥跟踪参数**、去掉末尾斜杠、主机小写。
    query 里的非跟踪参数保留 —— 见 TRACKING_QUERY_KEYS 上的说明。
    """
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    key = f"{host}{path}"
    query = urlencode(kept)
    return f"{key}?{query}" if query else key


def is_index_page_url(url: str) -> bool:
    """是不是栏目页/分类页/标签页这类聚合页。

    这类页面**绝不进台账**：它们每周都被引用、内容每周都变，当作"已推送"记下来
    会误杀未来所有引用它的条目。
    """
    parts = urlsplit(url)
    segments = [seg for seg in parts.path.lower().split("/") if seg]
    if any(seg in INDEX_PATH_SEGMENTS for seg in segments):
        return True
    return any(
        key.lower() in INDEX_QUERY_KEYS for key, _ in parse_qsl(parts.query)
    )


def load_history(path: Path, today: date) -> list[dict]:
    """读取台账，返回保留期内的条目（按 pushed 升序）。

    任何读取或解析问题都**非 0 退出**（硬性约束 4）。这里刻意不用
    `except Exception: entries = []` —— 那会把一个数据问题变成"跨周去重静默失效好几周"，
    表现和根本没做这个功能一模一样，谁都不会发现。
    """
    if not path.exists():
        LOG.info("台账 %s 不存在，按首次运行处理（本次不做跨周去重）", path.name)
        return []

    try:
        # utf-8-sig：本地是 Windows，编辑器另存为 "UTF-8 with BOM" 时
        # 普通 utf-8 解码会在首个 token 上抛 JSONDecodeError。
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        sys.exit(
            f"❌ 台账 {path.name} 无法解析：{type(exc).__name__}: {exc}\n"
            f"   这个文件由 workflow 自动回写。请检查是否被手工改坏，"
            f"或从 git 历史取回上一版。"
        )

    if not isinstance(raw, dict) or raw.get("version") != HISTORY_VERSION:
        got = raw.get("version") if isinstance(raw, dict) else type(raw).__name__
        sys.exit(
            f"❌ 台账 {path.name} 的 version 不是 {HISTORY_VERSION}（读到 {got}）。\n"
            f"   schema 变更要写迁移，不要直接忽略 —— 忽略会让去重静默失效。"
        )

    cutoff = today - timedelta(days=HISTORY_KEEP_DAYS)
    entries: list[dict] = []
    stale = malformed = 0
    for item in raw.get("entries") or []:
        try:
            # ⚠️ today 在调用侧可能是**带时区**的 datetime，而台账里是 naive 的
            # YYYY-MM-DD。两边不统一会抛 TypeError（不是 ValueError，不会被下面捕获），
            # 所以这里统一降到 date 再比。
            pushed = date.fromisoformat(str(item["pushed"]))
        except (KeyError, TypeError, ValueError):
            malformed += 1
            continue
        if pushed >= cutoff:
            entries.append(item)
        else:
            stale += 1

    if malformed:
        LOG.warning("台账里有 %d 条格式不对的条目已跳过（pushed 字段缺失或不是 "
                    "YYYY-MM-DD），请检查 —— 这些条目的去重保护已失效", malformed)
    entries.sort(key=lambda e: str(e.get("pushed", "")))
    if len(entries) > HISTORY_MAX_ENTRIES:
        LOG.info("台账条目超过上限 %d，只保留最近 %d 条",
                 HISTORY_MAX_ENTRIES, HISTORY_MAX_ENTRIES)
        entries = entries[-HISTORY_MAX_ENTRIES:]
    LOG.info("台账载入：%d 条在 %d 天保留期内（剔除 %d 条过期）",
             len(entries), HISTORY_KEEP_DAYS, stale)
    return entries


def save_history(path: Path, entries: list[dict]) -> None:
    """原子写入台账。

    tmp + os.replace：Actions 的 timeout-minutes 到点被杀时留不下半截 JSON
    （半截 JSON 下次会走 load_history 的失败分支，整个任务起不来）。
    newline="\\n" + ensure_ascii=False：`.gitattributes` 把行尾统一成 LF，
    主动写 LF 才不会在 Windows 本地产生整文件级的假 diff —— 那份文件的注释
    就是为这件事写的。
    """
    payload = {
        "version": HISTORY_VERSION,
        "entries": sorted(entries, key=lambda e: str(e.get("pushed", ""))),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def seen_url_map(entries: list[dict]) -> dict[str, str]:
    """返回 {归一化 URL: 推送日期}，供代码兜底判定用。

    聚合页/栏目页直接跳过 —— 见 is_index_page_url。
    """
    seen: dict[str, str] = {}
    for entry in entries:
        pushed = str(entry.get("pushed", ""))
        for url in entry.get("urls") or []:
            if is_index_page_url(url):
                continue
            seen.setdefault(normalize_url(url), pushed)
    return seen


def history_note(entries: list[dict]) -> str:
    """渲染"已推送过、不要重复"清单，拼进 user 提示词。

    台账为空时返回空串，调用侧据此**整块省略** —— 不要渲染成 `（无）`，
    那会给模型一个内容只有"无"的区块，它可能当成一条指令来执行。
    """
    if not entries:
        return ""
    rows = "\n".join(
        f"  · {entry.get('pushed', '')} ｜ {entry.get('title') or '（无标题）'}"
        for entry in entries
    )
    return (
        "【已推送过的条目 —— 不要重复】\n"
        "下列内容**上一期已经推送给读者了**，本期不要再写：\n"
        f"{rows}\n"
        "⚠️ **换一个来源、换一个链接也算重复**，同样不要写。\n"
        "⚠️ 只有出现**新的进展**才值得再写一次 —— 例如新增披露了尺寸/重量/IP 等级、\n"
        "   或有了新的结构改型。那种情况必须引用**新的**文章链接，并在正文里说明\n"
        "   这是对已有报道的更新，不要当成一条全新动态。\n"
        "（本来就不该重复的条目只是被这里挡了一次，不是让你少写 —— 报告短是可接受的。）"
    )


def strip_entry_title(entry_line: str) -> str:
    """剥掉 `### ` 前缀与条目序号，返回标题。**保留粗体标记。**

    `### 1. **BLUETTI** —— Balco 500` → `**BLUETTI** —— Balco 500`

    两处共用这个函数：`extract_entries()` 写台账、`build_digest()` 写群消息摘要。
    不要写两遍 —— 剥得不一致会让台账里的标题和摘要里的对不上。

    ⚠️ 序号必须剥掉。台账标题会被渲染进下周的「上期标题清单」，带着 `1.` 会让模型
    把它误读成一条**关于顺序的指令**，而不是一条内容。四种写法都兜住：
    `1.` / `1、` / `1)` / `1）`。

    ⚠️ 已知的隐含假设：正则要求序号在标题最前。**本项目的标题永远以厂商名开头**，
    所以 `### 1.5 倍膨胀力的实测数据` 这种会被误剥成 `5 倍…` —— 目前不可能出现，
    但这正是它没能覆盖的形状。
    """
    title = entry_line.lstrip("# ").strip()
    return re.sub(r"^\d+\s*[.、)）]\s*", "", title).strip()


def extract_entries(report: str) -> list[dict]:
    """从**最终推送出去的正文**里抽条目，供台账记录。

    ⚠️ 必须是最终正文（plan_messages 的输入），**不是模型的原始输出** ——
    从原始输出抽会把已经被促销过滤器删掉的条目标成"已推送"，那些内容就永远回不来了。

    按 `### ` 分块；每块记标题（去掉 `###`、序号与粗体标记）与其中的文章页链接。
    **没有链接的块也照样记录标题** —— 否则下周它还会以同样的话术再来一遍。
    `## 参考来源` 兜底用的是 `<url>` 尖括号写法，MARKDOWN_LINK_RE 匹配不到，
    正好不会被误记。
    """
    entries: list[dict] = []
    for block in group_blocks(report):
        chunk = "\n".join(block)
        if not chunk.lstrip().startswith("### "):
            continue
        # 台账是要塞进提示词的纯文本，所以比别人多剥一层粗体标记：
        # `strip("*")` 只去首尾，中间的 `**` 会留下来污染标题，所以整体删掉星号。
        title = re.sub(r"\*+", "", strip_entry_title(block[0])).strip()
        if not title:
            continue
        urls = sorted({
            url for url in MARKDOWN_LINK_RE.findall(chunk)
            if not is_index_page_url(url)
        })
        entries.append({"title": title, "urls": urls})
    return entries


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

# 三个提示词共用的角色设定与写作要求。抽成常量 —— 改规则只改这一处。
# 板块一现在独立跑两轮，共用一份规则是必需的，否则三份会各自漂移。
ROLE_AND_RULES = f"""你是储能行业的资深硬件分析师，长期服务于华宝新能（Jackery）的储能结构工程师团队。
你的读者是**做结构设计的工程师**，不是投资人也不是采购。

写作要求：
- 结论先行、信息密度高、不写套话，不要"综上所述""值得关注"这类空转。
- 只写**近 {WINDOW_DAYS} 天**的真实动态。检索不到就诚实说没有，
  **绝对不要编造产品、日期、数字或链接**。
- 关键数据必须精准：重量、尺寸、体积/重量变化百分比、容量、功率、IP 防护等级、
  能量密度、压实密度、循环寿命、价格。拿不准的数字宁可不写，也不要写个大概。
- ⚠️ **中英双语并行检索 —— 漏掉哪个方向都会漏内容。** 便携储能与阳台储能的多数
  新品首发在英文行业媒体，中文媒体通常不转载；但**中国厂商的国内首发只在中文源里**
  （大疆的电源产品线在英文媒体上覆盖尤其薄），型号、参数与价格以人民币和中文报道为准。
  **两个方向都要检索**，源清单与中英文关键词示例见 user 提示。
- 每条资讯都要带**原始网页链接**，写成 `[来源简称](完整URL)` 的形式，收在条目末尾的
  **来源** 行里（具体格式见下面的「条目排版」）。
  ⚠️ 链接**必须是文章详情页**。栏目页、分类页、标签页、聚合页一律不要 ——
  路径形如 `/category/...`、`/tag/...`、`/subjects/...`、`/industry-updates/`、
  `?column_id=...`、以栏目名结尾的 `.html`，点进去都是文章列表，读者找不到对应那条。
  **拿不到文章页链接就宁可不要这条。**
  同一个来源链接在一个条目里出现多次也没关系，不必刻意去重。
- **禁止"占位条"，但允许"薄条目"** —— 这两者要分清楚：
  - ❌ 占位条：`EcoFlow —— 本周期未检索到可核实的新品/结构变化`。
    通篇"未检索到"厂商名单是在凑数，**直接删掉，不要写**。
  - ✅ 薄条目：真发生了事件、只是细节没公开，**这条要留**。
    例：`BLUETTI 在 IFA 2026 展示 Balco 500 阳台储能一体机（5,024Wh、4,600W 光伏输入），
    未披露尺寸与重量`。
- ⚠️ **促销、折扣、优惠信息不是动态，任何板块都不要写。** 讲「降价」「到手价」
  「限时优惠」「Prime Day / 黑五促销」「专属折扣」的文章，**哪怕里面的容量、价格数字
  完全真实**，也一律不作为条目 —— 读者的工作是设计结构，不是盯价格。判别标准：
  这条讲的是**产品与结构本身**，还是**卖多少钱**？只讲后者就删掉。
  真实新品发布时厂商顺带公布的价格可以写，但主体必须是产品与结构。
  某个厂商本周期只有促销稿时，**该厂商直接不写**，不要为了凑厂商数把它塞进来。
  ⚠️ **自我检查**：如果你写着写着需要补一句「该条信息属于销售活动……因此不将其作为
  新品或结构改款处理」之类的话，那就是你在告诉自己**这条根本不该写** ——
  **直接删掉整条，不要先写出来再补一句否定。** 本地脚本会把这类条目连同它的
  「……不将其作为新品处理」一并删除，写出来只会浪费篇幅。
- 某个板块本周确实没有实质动态时，**一句话说明即可**，不要用占位条撑篇幅。
- 厂商名与产品型号用**粗体**。
- ⚠️ **条目排版 —— 每个 `### ` 条目都严格按下面四段写，不要写成整段散文：**
  1. **标题行**：`### 1. **厂商名** —— 一句话标题`。序号用阿拉伯数字加句点，
     **在每个板块内从 1 重新开始**，不要跨板块连续编号，也不要用中文数字。
  2. **正文**：**4~7 条** `- **标签**：内容` 的分点，**一个分点讲一件事**，
     数字并进对应分点，不要写成一大段。
     标签自己起，但优先复用这几个方向：`规格` / `结构变化` / `电芯与材料` /
     `接口与架构` / `防护与寿命` / `安装要求` / `价格` / `缺口`。
     **分点行之间不要插空行。**
     `缺口` 用来集中列出厂商**没有公开**的关键项（尺寸、重量、IP 等级、循环寿命、价格）——
     这比含糊带过有用得多，结构工程师要据此判断哪些结论还不能下。
  3. **来源行**：条目末尾单独一行 `**来源**：[媒体名](URL) ｜ [媒体名](URL)`，
     多个来源之间用 ` ｜ ` 分隔（见上面的链接规则）。
  4. **特点句**：来源行之后单独一行 `**特点**：……`，**就一句话**。
     写**判断**而不是复述 —— 点出这条对结构工程师最值得记住的是什么：它意味着什么、
     这家走的是哪条技术路线、或哪里还看不出结论。
     ⚠️ **特点句只能归纳本条已经列出的信息，绝对不许引入新的数字、事实或链接。**
     ⚠️ 不要写"值得关注""意义重大"这类空转，也不要重复标题已经说过的话。
  ⚠️ **四段之间一律空一行**：`### ` 标题行之后空一行再写分点，分点之后空一行写
  **来源** 行，**来源** 行之后空一行写 **特点** 句。（钉钉的渲染器对"标题紧接着
  列表"不保证换行，空行是必需的。）条目末尾再空一行，下一条的 `### ` 前留一个空行。
  板块四没有 `### ` 标题，用**地区加粗行**代替标题行，但正文、来源行、特点句照此格式写。
- ⚠️ **同一厂商的多条动态要连续排布**，不要与其他厂商交叉。读者是按厂商看的，
  同一家的三条被隔开在两处就很难读。
- 中文撰写。英文来源的厂商名与产品型号保留原文（如 EcoFlow、Anker SOLIX S2000、
  BLUETTI Balco 500），**不要音译或意译成中文**。
- 篇幅要够：读者宁可长一点，也不要一份只有标题的空壳。但要**靠真事件堆篇幅，
  不靠占位条堆篇幅**。
- ⚠️ **优先写最近的。** 检索窗口有两周，但读者的关注点是**刚刚发生的**。
  同一个板块里，先把最近几天的事件写完；窗口前半段（第 8~14 天）的内容只在
  近几天确实没有该板块的动态时才拿来补位。**不要拿两周前的旧事充当本周动态。**
- ⚠️ **本期动态少时，报告短是正常的、可以接受的。** 这跟上面"篇幅要够"不冲突：
  宁可用三条真事件撑起一个板块，也不要为了凑篇幅去写占位条、写促销稿，或者
  把上期已经报过的事情换个说法再讲一遍 —— 那三种都是明确禁止的。
- ⚠️ **板块一至板块四不写自家产品。** 华宝新能（Jackery）自己的产品动态
  （Explorer、HomePower、SolarVault、FridgeGuard、SolarSaga 等）不要作为条目
  收进板块一~四 —— 这几个板块是给读者看**别人在做什么**。自家产品只在板块五出现，
  而且板块五写的是"对自家产品定义的启发"，**不是播报自家新品**。
- 只写要求你写的板块，多一个少一个都不行。"""

# 板块一的标题固定。两轮调用都要原样输出它，本地靠它定位这一块。
SECTION1_HEADING = "## 一、便携&阳台储能竞品动态"

# 五个板块的标题，顺序即报告顺序。**这是本地唯一的板块清单** ——
# build_report 用它校验"五个板块都在且非空"（见该函数），
# drop_repeat_blocks 用 SECTION_FIVE_HEADING 判断哪些内容必须排除在删除之外。
# 改动板块标题时这里和三个提示词要一起改（硬性约束 2）。
SECTION_HEADINGS = (
    SECTION1_HEADING,
    "## 二、户用&工商业储能与大机动态",
    "## 三、电池与材料技术突破",
    "## 四、安规与政策大事件",
    "## 五、对华宝新能（Jackery）结构与产品定义的启发",
)

# 板块五由板块一的结论推导而来，**它的链接天然是板块一的子集**。
# 所以任何"看到链接已推送过就删"的逻辑都必须永久跳过它，否则整块会被删光。
SECTION_FIVE_HEADING = SECTION_HEADINGS[-1]

# 板块一的厂商范围与写作重点。第一轮与第二轮两个提示词共用。
SECTION1_VENDORS = """\
   EcoFlow（正浩）、Anker SOLIX、BLUETTI（德兰明海）、DJI Power（大疆）、
   Goal Zero、Segway、Oupes、Vtoman、Eco-Worthy 等的新品与形态变化。
   **检索时用英文名**：EcoFlow / Anker SOLIX / BLUETTI / DJI Power /
   Goal Zero / Segway / Oupes / Vtoman / Eco-Worthy；阳台储能另有 Hoymiles、
   Zendure、Anker SOLIX Solarbank、PowerOak。
   ⚠️ **上面这份英文名单要与上面的中文名单一一对应。** Eco-Worthy 曾整个漏在英文
   名单外 —— 它没有中文名，漏掉就等于这家厂商没有任何检索入口，会静默消失。
   ⚠️ **Jackery（华宝新能）自己的产品刻意不在上面这份清单里，也不要补进来。**
   板块一是给读者看**别人在做什么**；自家产品只在板块五出现。
   每条重点写：新品形态、体积/重量相对前代的变化%、防护等级、盲插/堆叠/无线连接架构、价格。
   用 `### 1. **厂商** —— 一句话标题` 作为厂商小标题（序号在本板块内从 1 连续编），
   **厂商名保留英文原文**。"""

# 主调用：板块二~五。板块一已拆出去单独跑两轮（见 fetch_section1），
# 所以这里必须明确不要它 —— 否则会拿到两份板块一。
MAIN_SYSTEM_PROMPT = f"""{ROLE_AND_RULES}

输出格式（标题必须原样保留 `{DINGTALK_KEYWORD}` 这几个字，钉钉靠它做安全校验）：
第一行是一级标题：`# {DINGTALK_KEYWORD} 储能结构周报（YYYY-MM-DD）`
紧接着一行引用块写覆盖周期。然后**严格按下面四个二级标题**组织（标题文字不要改动）：


## 二、户用&工商业储能与大机动态
   华为数字能源（Huawei）、比亚迪储能（BYD）、阳光电源（Sungrow）、德业（Deye）、
   派能（Pylontech）、海辰储能（Hithium）、欣旺达（Sunwoda）、宁德时代（CATL）、
   亿纬锂能（EVE）、特斯拉 Powerwall（Tesla）等。
   每条重点写：高压架构（如 800V 直流、1000VAC）、构网型技术、液冷/风冷热管理如何集成进结构、
   机柜与堆叠方式、容量与功率等级。
   同样用 `### 1. **厂商** —— 一句话标题` 作为小标题（序号在本板块内从 1 起）。

## 三、电池与材料技术突破
   两类内容都要覆盖：
   ① **电芯与体系侧**：新电芯化学（高压实 LFP、钠离子、固态）、阻燃与隔热材料
      （气凝胶、阻燃工程塑料）、轻量化材料、以及**膨胀力对 Pack 结构的影响**
      这类与结构强相关的隐患。
   ② **结构件材料侧**：户用与移动储能结构件**本身常用**的材料与工艺进展 ——
      **钣金**（冲压/折弯/激光焊/铆接、板厚减薄、镀锌与粉末喷涂等表面处理、
      结构胶粘接）、**塑胶**（注塑件、阻燃 PC/ABS、玻纤增强尼龙、结构发泡、
      免喷涂工艺）、压铸铝、挤出型材、导热与密封胶。写**牌号 / 性能指标 /
      工艺窗口**的变化：屈服强度、UL94 阻燃等级、耐候等级、可回收性、
      公差与装配工序。
   每条重点写：量化的材料指标，以及它对 Pack / 结构件设计意味着什么。
   拿不到具体牌号、指标或工艺参数的，不要占条目 ——"某公司推出新材料"没有落点。

## 四、安规与政策大事件
   按**主要购买地区**分组，固定用下面三个加粗分组行（文字照抄，各占一行）：
   **北美**、**欧洲**、**日本**。
   每组用 **3~5 条** `- **标签**：内容` 的分点写，别写成一整段。
   每组都要覆盖该地区的三类事件：
   ① 产品安规与认证：UL 2743、UL 3700、NFPA 855、德国 DIN VDE V 0126-95 等；
   ② 认证与关税、供应链与产能政策；
   ③ **安装与维护要求**：安装人员资质与持证电工、并网报备与验收、检修通道与
      净空、离墙距离、年度维护与检查记录、消防验收、退役拆解与回收责任。
   ⚠️ 某个地区本周期确实没有新动态时，**直接省略该地区那一行**。省略是正常的、
   不会让报告显得不完整 —— 读者要的是有内容的地区，一句"本周期未检索到…"只是噪音。
   报告短一点没关系，但**不要**用占位句、窗口外的旧闻、或与这三类无关的内容
   （项目融资、企业动态、中标新闻）去把三组凑满。
   ⚠️ **这一节不要用 `### ` 小标题，也不要编号。** 地区名必须写成 `**北美**` 这种
   独立加粗行（**不要写成 `### 北美`**），下面直接跟分点。整节末尾同样要有
   **来源** 行与 **特点** 句（格式见 `ROLE_AND_RULES` 的「条目排版」）。

## 五、对华宝新能（Jackery）结构与产品定义的启发
   从**硬件视角**总结 3 点建议，每点 2~3 句，落点在 Pack 集成度、散热风道设计、
   新材料与新工艺的应用、可制造性、认证前置这些结构工程师能动手的地方。
   ⚠️ **这一节是纯建议，唯一不适用「条目排版」的板块** —— 不要用 `### ` 小标题，
   不要分点、不要 `**来源**` 行、不要 `**特点**` 句。就用 `1. 2. 3.` 编号，
   每点写成一整段。
   可以引用产品线时**只能引用下面清单里列出的**，清单外的型号一律不要提：
{JACKERY_PRODUCTS}

最后一行单独写：`—— 本消息由自动化脚本生成，检索源：Perplexity sonar-pro-search`

⚠️ **不要写板块一「便携&阳台储能竞品动态」。** 它由另一路检索专门负责，
你写了就会和它重复。"""


# 板块一第一轮：检索预算全部集中在这一个板块上。
# 拆出来的理由与实测数据见 CLAUDE.md —— 五个板块挤在一次调用里会把检索预算摊薄，
# 板块一（最依赖英文检索）经常整块为空，同配置两次运行的方差也极大。
SECTION1_SYSTEM_PROMPT = f"""{ROLE_AND_RULES}

本次任务：**只做「便携&阳台储能竞品动态」这一个板块**，不要写任何其它板块。

输出格式：
第一行就是二级标题 `{SECTION1_HEADING}`（文字照抄，一个字都不要改），
下面用 `### 1. **厂商** —— 一句话标题` 逐条展开（序号从 1 起，正文按
`ROLE_AND_RULES` 的「条目排版」写成分点 + **来源** 行 + **特点** 句）。
**不要写一级标题，也不要写"覆盖周期"那一行** —— 它们由本地统一生成。

板块范围与写作重点：
{SECTION1_VENDORS}"""


# 板块一第二轮：带上第一轮的原文，补漏 + 合并成最终的一份。
# 两轮结果**不做本地拼接** —— 拼接会得到两份互相重复、口径不一的板块。
SECTION1_MERGE_SYSTEM_PROMPT = f"""{ROLE_AND_RULES}

本次任务的特殊之处：user 消息里会给你**第一轮检索**的原文。你要做三件事：
1. **再检索一轮，专补第一轮漏掉的。** 第一轮一条都没提到的厂商，优先单独查一遍；
   提到了但没给参数的，再试试能否找到参数。
2. **合并去重。** 同一厂商的同一件事只保留一处，不要出现两条讲同一件事。
   参数以更完整的那一轮为准；两轮说法冲突时，回到原文核实。
3. **综合总结成最终的一个板块。** 不是把两轮首尾相接，而是重新组织成一份完整、
   不重复、口径一致的板块。第一轮里表述含糊或没有链接的条目，可以直接丢掉。

输出格式：
第一行就是二级标题 `{SECTION1_HEADING}`（文字照抄，一个字都不要改），
下面用 `### 1. **厂商** —— 一句话标题` 逐条展开（序号**在本板块内从 1 连续编**，
正文按 `ROLE_AND_RULES` 的「条目排版」写成分点 + **来源** 行 + **特点** 句）。
**不要写一级标题，也不要写"覆盖周期"那一行。**
不要输出"第一轮""第二轮""上一轮"这类过程说明，直接给最终结果。

板块范围与写作重点：
{SECTION1_VENDORS}"""


def _window(today: datetime) -> tuple[str, str]:
    """返回 (起始日, 结束日)，格式 YYYY-MM-DD。

    这是全项目唯一的窗口定义。**不要再在别处写 `timedelta(days=...)`** ——
    build_report 的 header 里曾经有过第二处，窗口一改就会和这里对不上，
    报告会印着 7 天的覆盖周期、却检索了 14 天。
    """
    return (
        (today - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d"),
        today.strftime("%Y-%m-%d"),
    )


def _retrieval_hint() -> str:
    """检索型调用的 user 提示里都要附的源清单与关键词。

    ⚠️ 这段被**三处**调用共用（板块一两轮 + 板块二~五），所以措辞必须**板块中性**。
    早先的版本写死了板块一口径（"这一条决定板块一有没有内容""便携与阳台储能的新品
    首发"），板块二~五拿到手等于没有源指引 —— 户用/工商业/材料那几个板块的中国厂商
    动态同样会被漏。

    ⚠️ **中英两边的源和关键词都要给，而且两个方向的警告都要写。** 只写"只搜中文会
    漏掉整个板块"会让模型倒向英文，进而漏掉中国厂商的国内首发 —— 大疆就是这么丢的：
    DJI Power Auro 2000 Elite（2 度电户外电源，4,799 元）2026-09-21 在中国发布，
    日期就在 r9.md 的窗口内，整条没出现。而英文源清单里跟大疆相关的只有
    DroneDJ / DroneXL 两家**无人机**媒体，对电源产品线的覆盖本就很薄。
    """
    return (
        "【检索语言 —— 必须中英双语并行，漏哪个方向都会漏内容】\n"
        "只搜中文会漏掉海外首发：便携储能与阳台储能的多数新品首发在英文行业媒体，\n"
        "中文媒体通常不转载。\n"
        "⚠️ **只搜英文同样会漏，而且漏掉的是中国厂商的国内首发。** 大疆（DJI Power）、\n"
        "正浩（EcoFlow）、德兰明海（BLUETTI）、安克、海辰储能、派能、亿纬、阳光电源\n"
        "等常在中国先发，型号、参数与价格以人民币和中文报道为准。\n"
        "**大疆尤其要注意**：它的英文报道集中在无人机线，电源产品线（DJI Power）\n"
        "在英文媒体上覆盖很薄 —— 只搜英文基本看不到它的电源新品。\n"
        "请中英双语并行检索，两边都要覆盖：\n"
        "  英文源：\n"
        "    · 厂商官方新闻稿：PR Newswire、Business Wire、EQS News、GlobeNewswire\n"
        "    · 行业媒体：pv magazine、ESS News、Energy-Storage.News、Electrek、\n"
        "      CleanTechnica、Solar Power World\n"
        "    · 消费电子与评测：Gizmodo、The Verge、Notebookcheck、9to5Toys、\n"
        "      DroneDJ / DroneXL、Impress Watch、PC Watch\n"
        "    · 展会官方发布：Solar & Storage Live、IFA、Intersolar、RE+、SNEC\n"
        "  中文源：\n"
        "    · 厂商官网与官方账号：DJI 大疆中国官网新闻中心、正浩、德兰明海、安克、\n"
        "      华为数字能源、阳光电源、海辰储能、派能\n"
        "    · 行业与科技媒体：IT之家、快科技、充电头网、爱范儿、中关村在线、\n"
        "      新浪科技、第一财经、财联社、EnergyTrend、储能与电力市场\n"
        "英文关键词示例：portable power station launch、home battery module、\n"
        "balcony solar storage、all-in-one ESS、sodium-ion BESS、new LFP cell、\n"
        "drop test / IP rating / thermal runaway enclosure、swappable battery module、\n"
        "sheet metal enclosure stamping、die-cast aluminum housing、injection-molded\n"
        "flame-retardant PC/ABS、UL94 V-0 enclosure、structural adhesive、gasket\n"
        "sealing、powder coating corrosion resistance、glass-filled nylon bracket；\n"
        "installation code for home battery、clearance and service access、certified\n"
        "installer requirement、annual inspection record、battery removal and recycling。\n"
        "中文关键词示例：户外电源 新品发布、便携电源 上市、阳台储能 一体机、\n"
        "大疆 电源 发布、正浩 新品、德兰明海 新品、构网型储能 发布、钠离子电芯 量产、\n"
        "储能柜 液冷 发布、电芯 能量密度 量产、钣金 机箱 冲压 工艺、压铸铝 壳体、\n"
        "注塑 阻燃 PC/ABS、结构胶 密封 储能、粉末喷涂 耐候、玻纤增强 支架；\n"
        "储能 安装规范 检修通道、并网验收 要求、持证电工、维护记录 要求、\n"
        "电池 拆解 回收 责任。"
    )


def build_section1_user_prompt(
    today: datetime, history: list[dict] | None = None
) -> str:
    """板块一第一轮的 user 提示。

    history 是跨周台账。放在第一轮而不是只放第二轮，是因为第一轮的检索量最大，
    上期标题清单在这里能提前把模型往新内容上引，省得它把预算花在已经报过的事上。
    """
    start, end = _window(today)
    note = history_note(history or [])
    return (
        f"请检索并汇总 {start} 至 {end}（近 {WINDOW_DAYS} 天）"
        f"**便携与阳台储能竞品**的新品与形态变化，"
        f"面向储能结构工程师。\n\n"
        f"今天日期：{end}。请以这个日期为准判断哪些是近 {WINDOW_DAYS} 天的新闻。\n"
        f"请横向覆盖尽可能多的厂商，不要只写一两家就收尾。\n"
        f"{note}\n"
        f"{_retrieval_hint()}\n\n"
        f"再次强调：只写真实发生的动态，每条都要带**文章详情页**的原始链接"
        f"（不要栏目页、分类页、聚合页），数据要精准，不要编造。"
    )


def _seen_url_block(seen: dict[str, str]) -> str:
    """第二轮用的「这些链接已推送过」区块。

    刻意与促销黑名单分成两段、两套措辞：促销黑名单说的是"这些页面是折扣稿，别引用"，
    这里说的是"这些页面是好内容，但上期已经推过了，本期的**新进展**才值得再写"。
    ⚠️ 两者绝不能合并 —— 合并会让模型把上期的真新闻也当成折扣稿，连带躲开整个域名。
    """
    if not seen:
        return ""
    rows = "\n".join(f"- {url}" for url in sorted(seen)[:80])
    return (
        "\n【下列链接上一期已经推送过】\n"
        f"{rows}\n"
        "这些页面本身没问题，只是**读者已经看过了**。除非本周期出现了新的进展\n"
        "（新增披露了尺寸/重量/IP 等级、有了新的结构改型），否则不要把它们再列为条目；\n"
        "确实有新进展时必须引用**新的**文章链接，并说明这是对已有报道的更新。\n"
    )


def build_section1_merge_user_prompt(
    today: datetime,
    first_pass: str,
    banned_urls: list[str],
    history: list[dict] | None = None,
    seen: dict[str, str] | None = None,
) -> str:
    """板块一第二轮的 user 提示：把第一轮原文交给它，要求补漏并合并。

    first_pass 传进来前已经被 drop_promo_blocks 洗过一遍；banned_urls 是被洗掉的那些
    链接，显式列出来是为了让第二轮**不要再去引用它们** —— 只删掉不告知的话，模型补漏时
    很可能从同一批检索结果里再把同一篇折扣稿捞回来。

    history / seen 是跨周台账，两者信息互补：history 给"上期标题"（软性拦截换来源的
    重复），seen 给"上期链接"（拦住同一篇文章）。**它们是独立参数，不要并进 banned_urls。**
    """
    start, end = _window(today)
    blacklist = ""
    if banned_urls:
        blacklist = (
            "\n⚠️ 下列链接**已被判定为促销/折扣稿并剔除，禁止引用**：\n"
            + "\n".join(f"- {u}" for u in banned_urls)
            + "\n（这些页面讲的是降价、优惠、到手价，不是新品或结构变化。促销信息一律不作"
              "为竞品动态条目；某个厂商本周期只有促销稿时，该厂商直接不写，不要为凑厂商数塞进来。）\n"
        )
    note = history_note(history or [])
    return (
        f"覆盖周期：{start} 至 {end}（近 {WINDOW_DAYS} 天）。今天日期：{end}。\n\n"
        f"{_retrieval_hint()}\n"
        f"{blacklist}\n"
        f"{_seen_url_block(seen or {})}\n"
        f"{note}\n"
        f"===== 第一轮检索结果开始 =====\n{first_pass}\n===== 第一轮检索结果结束 =====\n\n"
        f"请按系统提示的要求执行：先再检索一轮补漏，然后把两轮合并去重、"
        f"综合总结成最终的一份「便携&阳台储能竞品动态」。"
    )


def build_user_prompt(
    today: datetime, section1: str = "", history: list[dict] | None = None
) -> str:
    """主调用的 user 提示：板块二~五。

    section1 是板块一两轮跑完后的最终正文。传进来只为一件事 —— 板块五的启发
    需要知道便携竞品这周发生了什么。**明确告诉它不要抄进输出**，否则会重复一块。
    """
    start, end = _window(today)
    context = ""
    if section1.strip():
        context = (
            f"\n===== 板块一最终结果（**仅供你写板块五时参考**，"
            f"不要抄进你的输出）=====\n{section1}\n===== 参考内容结束 =====\n"
        )
    note = history_note(history or [])
    return (
        f"请检索并汇总 {start} 至 {end}（近 {WINDOW_DAYS} 天）全球储能行业的硬件工程动态，"
        f"面向储能结构工程师，按系统提示里的四个板块（二、三、四、五）输出。\n\n"
        f"今天日期：{end}。请以这个日期为准判断哪些是近 {WINDOW_DAYS} 天的新闻。\n"
        f"**不要写板块一。**\n"
        f"{context}\n"
        f"{note}\n"
        f"{_retrieval_hint()}\n\n"
        f"再次强调：只写真实发生的动态，每条都要带**文章详情页**的原始链接"
        f"（不要栏目页、分类页、聚合页），数据要精准，不要编造。"
    )


# ---------------------------------------------------------------------------
# 环境变量
# ---------------------------------------------------------------------------

def load_config(dry_run: bool) -> dict[str, str]:
    """读取并校验环境变量。缺什么、去哪配，一次性说清楚再退出。"""
    missing: list[str] = []

    # 优先 OPENROUTER_API_KEY（名字准确），兼容旧名 PERPLEXITY_API_KEY ——
    # 免得已经按旧名配好 Secret 的人遇到一个看不懂的"缺变量"。
    api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("PERPLEXITY_API_KEY")
        or ""
    ).strip()
    if not api_key:
        missing.append(
            "OPENROUTER_API_KEY —— OpenRouter 控制台的 API Key（sk-or-v1- 开头）。\n"
            "    本地：加进项目根目录的 Key 文件；线上：仓库 Settings → Secrets → Actions"
        )

    webhook = (os.environ.get("DINGTALK_WEBHOOK") or "").strip()
    if not webhook and not dry_run:
        missing.append(
            "DINGTALK_WEBHOOK —— 必须是 https://oapi.dingtalk.com/robot/send?access_token=...\n"
            "    注意别填成飞书（feishu.cn）的链接，两者不通用"
        )
    # 格式校验放在启动时，比发出消息后拿到 310000 再回头排查省事得多。
    if webhook and not webhook.startswith("https://oapi.dingtalk.com/"):
        sys.exit(
            f"❌ DINGTALK_WEBHOOK 格式不对。\n"
            f"   期望：https://oapi.dingtalk.com/robot/send?access_token=...\n"
            f"   实际：{webhook[:40]}...\n"
            f"   （如果是 feishu.cn 开头的链接，那是飞书的，钉钉用不了）"
        )

    if missing:
        sys.exit("❌ 缺少必需的环境变量：\n\n" + "\n\n".join(f"  - {m}" for m in missing))

    # 网页站点根。**可选**，不给就用默认值。
    #
    # ⚠️ 取到空串时**用默认值**，不能把空串当成"关闭"：workflow 里写的是
    # `${{ vars.SITE_BASE_URL }}`，仓库变量没配时它会展开成空串 —— 若空串等于关闭，
    # 网页功能就会在 CI 上**静默失效**，而所有结构校验一个都不会响。
    # 真要关闭，把变量显式设成 off。
    site_base_url = (
        os.environ.get("SITE_BASE_URL") or DEFAULT_SITE_BASE_URL
    ).strip().rstrip("/")
    if site_base_url.lower() in {"off", "none", "false", "0"}:
        site_base_url = ""
    elif not site_base_url.startswith("http"):
        sys.exit(
            f"❌ SITE_BASE_URL 格式不对。\n"
            f"   期望：https://<用户名>.github.io/<仓库名>\n"
            f"   实际：{site_base_url[:60]}\n"
            f"   （想关闭网页功能、退回推送全文，就把它设成 off）"
        )

    return {
        "OPENROUTER_API_KEY": api_key,
        "DINGTALK_WEBHOOK": webhook,
        "OPENROUTER_MODEL": (os.environ.get("OPENROUTER_MODEL") or OPENROUTER_MODEL).strip(),
        "SITE_BASE_URL": site_base_url,
    }


# ---------------------------------------------------------------------------
# OpenRouter 调用
# ---------------------------------------------------------------------------

def check_openrouter_balance(api_key: str) -> float | None:
    """查 OpenRouter 账户余额（美元）。**任何失败都返回 None，绝不抛异常。**

    ⚠️ 这是"附加信息"，不是主流程的一部分：余额接口挂了、限流了、返回体改形状了，
    都不该让这一期的推送失败。所以这里全部吞掉、只打 WARNING —— 本项目别处都讲究
    fail-loudly，**这一处是刻意的例外**，理由正是它不该对这一期有否决权。

    ⚠️ 用 `/credits`（账户级：`total_credits - total_usage`），**不要改用
    `/auth/key` 的 `limit_remaining`** —— 后者是这把 key 的**消费上限**，跟账户里
    还有多少钱是两回事。实测该 key 的 limit_remaining 是 46.35，而账户真实余额
    只剩 1.35。拿它当余额会得到一个"永远很充裕"的假象，预警等于没有。
    """
    if not api_key:
        return None
    try:
        response = requests.get(
            f"{OPENROUTER_BASE_URL}/credits",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if response.status_code != 200:
            LOG.warning("余额查询返回 HTTP %s，本期不附余额提醒", response.status_code)
            return None
        data = response.json().get("data") or {}
        return float(data["total_credits"]) - float(data["total_usage"])
    except Exception as exc:  # noqa: BLE001
        # 刻意宽口径捕获：这里能出错的方式太多（网络、JSON、字段改名、类型变了），
        # 逐个列举只会漏。反正无论哪种都不该影响推送。
        LOG.warning("余额查询失败（%s: %s），本期不附余额提醒", type(exc).__name__, exc)
        return None


def _low_balance_note(balance: float | None) -> str:
    """余额够用就返回空串，**只剩一期或更少**时返回要附在摘要末尾的那一句。

    ⚠️ 判断走的是"估算期数 ≤ OPENROUTER_LOW_RUNS_LEFT"，不是直接比美元数 ——
    这样阈值和那句"约合 N 期"用的是同一个算式，不会出现"提醒里写着还剩 2 期，
    提醒却在只剩 1 期时才出现"这种自相矛盾。
    """
    if balance is None:
        return ""
    runs = max(0, int(balance / OPENROUTER_COST_PER_RUN_USD))
    if runs > OPENROUTER_LOW_RUNS_LEFT:
        return ""
    if runs == 0:
        # 已经不够跑一次了。这一期之所以还能发出去，是因为余额是在**推送之后**查的。
        return f"\n\n⚠️ OpenRouter 余额仅剩 ${balance:.2f}，已不足一次运行，请立即充值。"
    return f"\n\n⚠️ OpenRouter 余额仅剩 ${balance:.2f}，约合 {runs} 期，请及时充值。"


def extract_citations(data: dict, message: dict) -> list[str]:
    """尽力从响应里取回引用链接。

    OpenRouter 的返回形状随模型而异，实测至少三种可能，所以逐个探：
      1. 顶层 citations（Perplexity 原生接口的字段，OpenRouter 有时透传）
      2. message.annotations 里 type == "url_citation" 的 url（OpenRouter 的归一化格式）
      3. message.citations
    取不到就返回空列表 —— 调用方只在"正文一个链接都没有"时才用它兜底。
    """
    urls: list[str] = []

    for item in (data.get("citations") or []):
        if isinstance(item, str) and item:
            urls.append(item)

    for item in (message.get("citations") or []):
        if isinstance(item, str) and item:
            urls.append(item)

    for ann in (message.get("annotations") or []):
        if not isinstance(ann, dict):
            continue
        # 有的实现把 url 放在 url_citation 子对象里，有的平铺在顶层。
        payload = ann.get("url_citation") if isinstance(ann.get("url_citation"), dict) else ann
        url = payload.get("url") if isinstance(payload, dict) else None
        if isinstance(url, str) and url:
            urls.append(url)

    # 去重但保序
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def call_openrouter(
    cfg: dict[str, str], messages: list[dict[str, str]], label: str = ""
) -> tuple[str, list[str]]:
    """调用 OpenRouter 上的 sonar-pro-search，返回 (Markdown 正文, 引用链接)。

    messages 由调用方组装 —— 现在有三次调用（板块一两轮 + 其余板块一轮），
    各自的 system/user 提示不同，所以不在这里拼。label 只用于日志区分是哪一路，
    失败时能一眼看出是哪个板块挂了。
    """
    tag = f"[{label}] " if label else ""
    payload = {
        "model": cfg["OPENROUTER_MODEL"],
        "messages": messages,
        "temperature": OPENROUTER_TEMPERATURE,
        "max_tokens": OPENROUTER_MAX_TOKENS,
        # web_search_options 是该模型在 supported_parameters 里明确支持的联网开关
        # （search_recency_filter / return_citations 都不支持，见文件顶部说明）。
        # search_context_size 取 high，让它在检索上多花点力气。
        "web_search_options": {"search_context_size": "high"},
    }
    headers = {
        "Authorization": f"Bearer {cfg['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
        # OpenRouter 要求的调用方标识，非必填但建议带。
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }

    last_exc: Exception | None = None
    for attempt in range(1, OPENROUTER_RETRIES + 2):
        try:
            response = requests.post(
                OPENROUTER_URL, json=payload, headers=headers, timeout=OPENROUTER_TIMEOUT,
            )
            # 限流与 5xx 值得重试，4xx 其余情况重试也没用。
            if response.status_code == 429 or response.status_code >= 500:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
            if response.status_code != 200:
                # 400/401/403 基本是 key 或模型名的问题，直接把响应体带出来便于定位。
                sys.exit(
                    f"❌ OpenRouter 返回 HTTP {response.status_code}，重试无意义。\n"
                    f"   {response.text[:500]}\n"
                    f"   （401/403 多为 API Key 无效；402 是余额不足；"
                    f"400 多为模型名不存在或参数不合法）"
                )

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                # OpenRouter 会把上游错误放在 error 字段里，一并带出来便于定位。
                if data.get("error"):
                    raise RuntimeError(f"OpenRouter 返回错误：{str(data['error'])[:300]}")
                raise RuntimeError(f"响应里没有 choices：{str(data)[:300]}")
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            # 被 max_tokens 截断是**静默**的：_assert_all_sections 能拦住"末端板块
            # 整个没了"，但拦不住"板块四被砍掉最后两句"。这里补一条告警，让日志能直接
            # 定位到"报告变薄"是截断造成的，而不是检索没找到东西。
            if choices[0].get("finish_reason") == "length":
                LOG.warning(
                    "%s输出被 max_tokens 截断（finish_reason=length）—— "
                    "末尾内容已丢失，考虑继续调高 OPENROUTER_MAX_TOKENS（模型上限 8000）",
                    tag,
                )
            return content.strip(), extract_citations(data, message)

        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            LOG.warning("%sOpenRouter 调用失败（第 %d/%d 次）：%s",
                        tag, attempt, OPENROUTER_RETRIES + 1, exc)
            if attempt <= OPENROUTER_RETRIES:
                time.sleep(OPENROUTER_BACKOFF * attempt)

    raise RuntimeError(
        f"{tag}OpenRouter 调用持续失败：{type(last_exc).__name__}: {last_exc}"
    )


# ---------------------------------------------------------------------------
# 正文校验与组装
# ---------------------------------------------------------------------------

def strip_model_heading(text: str) -> str:
    """去掉模型自己写的一级标题与开头的引用块。

    标题和"覆盖周期"那行都由本地统一生成 —— 钉钉关键词必须稳定出现在正文里，
    不能指望模型每次都听话；而且模型自己写的元信息行会和本地生成的重复一行。
    """
    lines = text.split("\n")
    while lines:
        stripped = lines[0].lstrip()
        # 空行、一级标题、以及开头的引用块（模型的"覆盖周期"行）都丢掉。
        if not stripped or stripped.startswith("# ") or stripped.startswith(">"):
            lines.pop(0)
        else:
            break
    return "\n".join(lines).strip()


def has_markdown_link(text: str) -> bool:
    return bool(re.search(r"\]\(https?://", text))


MARKDOWN_LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)")


def url_promo_reason(url: str) -> str | None:
    """URL 路径命中促销特征时返回命中的那个词，否则 None。

    只看路径，不看域名与查询串（`?utm_source=` 之类是跟踪参数，不携带语义）。
    路径按 `/` 分段，段内再按 `-` `_` 切词逐词比对 —— 见常量区的说明。
    """
    path = urlsplit(url).path
    for segment in path.split("/"):
        if not segment:
            continue
        segment = segment.lower()
        hit = PROMO_OFF_RE.search(segment)
        if hit:
            return hit.group(0)
        tokens = [t for t in re.split(r"[-_]", segment) if t]
        for token in tokens:
            if token in PROMO_URL_TOKENS:
                return token
        for phrase in PROMO_URL_PHRASES:
            n = len(phrase)
            for i in range(len(tokens) - n + 1):
                if tuple(tokens[i:i + n]) == phrase:
                    return "-".join(phrase)
    return None


def block_drop_reason(chunk: str) -> str | None:
    """一个 `### ` 条目块该不该删？返回删除理由，该留则返回 None。

    两道判据，命中任一即删：
      1. **模型自己的否定式自述**（SELF_DISQUALIFY_RE）—— 主判据。它都写了
         "因此不将其作为新品或结构改款处理"，这条就不该占一个条目。
      2. **URL 命中促销特征**（url_promo_reason）—— 补充。用在模型没写自述、
         直接当成正常新品写出来的情况（r7 里 Anker 那条就是这样）。
    """
    hit = SELF_DISQUALIFY_RE.search(chunk)
    if hit:
        return f"模型自述非新品：「{hit.group(0)}」"
    for url in MARKDOWN_LINK_RE.findall(chunk):
        reason = url_promo_reason(url)
        if reason:
            return f"URL 促销特征「{reason}」：{url}"
    return None


def group_blocks(text: str) -> list[list[str]]:
    """把正文按标题切成块：每个 `## ` / `### ` 行起一块，后续行归入该块。

    `## ` 与 `### ` 都起新块，所以一个 `### ` 块里不会混进 `## ` 标题行 ——
    下面两个过滤器都依赖这一点来判断"这一块是不是能整块删的条目块"。
    """
    blocks: list[list[str]] = []
    for line in text.split("\n"):
        if line.startswith("## ") or line.startswith("### "):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
        else:
            blocks.append([line])
    return blocks


def drop_promo_blocks(text: str, where: str) -> tuple[str, list[str]]:
    """丢掉促销/折扣稿与被模型自己否定的 `### ` 条目块。

    返回 (清理后的正文, 被丢掉条目里的全部 URL) —— URL 交给调用方拼进下一轮提示，
    让模型补漏时不要再把同一批折扣稿捞回来。

    只丢 `### ` 开头的条目块，**不动 `## ` 标题行与正文段落** ——
    标题是本地用来定位板块的，删掉会让整份报告层级塌掉；段落删掉会连带丢掉
    同段里的真情报。所以非 `### ` 块里若残留命中内容，只告警不删，留给人工看一眼。
    """
    blocks = group_blocks(text)

    kept: list[str] = []
    dropped: list[str] = []
    for block in blocks:
        chunk = "\n".join(block)
        if chunk.lstrip().startswith("### "):
            reason = block_drop_reason(chunk)
            if reason:
                LOG.warning("[%s] 丢弃条目（%s）｜ 标题：%s",
                            where, reason, block[0].lstrip("# ").strip()[:50])
                dropped.extend(MARKDOWN_LINK_RE.findall(chunk))
                continue
        kept.append(chunk)

    cleaned = "\n".join(kept)
    for block in cleaned.split("\n\n"):
        if block.lstrip().startswith("### "):
            continue  # 上面已经过了一遍，这里只查删不掉的那些
        reason = block_drop_reason(block)
        if reason:
            LOG.warning("[%s] 命中促销/非新品特征但位于无法整块删除的位置（%s），"
                        "请人工确认：%s", where, reason, block.strip()[:80])
    return cleaned, dropped


def block_repeat_reason(chunk: str, seen: dict[str, str]) -> str | None:
    """一个 `### ` 条目块是不是上周已经推送过？是则返回理由，否则 None。

    判据：**该块的全部链接（归一化后）都在台账里**。只要有一条链接没推过就保留 ——
    宁可漏去重，也不要因为块里恰好引了一篇旧文就丢掉一条含新情报的条目。

    ⚠️ 第一行的 `if not urls` 不是防御性代码，是**必需的**：`all()` 对空列表恒为 True，
    少了这一行，所有**不带链接**的 `### ` 块会在第一次运行就被删光。
    这不是假想 —— r2.md 3 个块、r3.md 2/3、r4.md 2/3、r7.md 1/3 都没有链接，
    其中"国家电投 100MW/200MWh 一期并网"是真新闻。
    """
    urls = [
        url for url in MARKDOWN_LINK_RE.findall(chunk)
        if not is_index_page_url(url)      # 聚合页不进台账，也就不该参与判定
    ]
    if not urls:
        return None
    dates = [seen[normalize_url(url)] for url in urls if normalize_url(url) in seen]
    if len(dates) != len(urls):
        return None
    latest = max(d for d in dates if d) if any(dates) else ""
    return f"全部链接均已推送过（最近 {latest or '未知日期'}）"


def _section_of_blocks(text: str) -> tuple[list[list[str]], list[tuple[str, str]]]:
    """切块并给每块标注 (类型, 所属二级标题)。

    返回 (块列表, [(类型, 二级标题), ...])，类型取值 'h2' / 'h3' / 'other'。
    所属二级标题用于两个判断：空板块守卫、以及"板块五永远不删"。
    """
    blocks = group_blocks(text)
    tags: list[tuple[str, str]] = []
    current_h2 = ""
    for block in blocks:
        stripped = "\n".join(block).lstrip()
        if stripped.startswith("## "):
            current_h2 = stripped.split("\n", 1)[0].strip()
            tags.append(("h2", current_h2))
        elif stripped.startswith("### "):
            tags.append(("h3", current_h2))
        else:
            tags.append(("other", current_h2))
    return blocks, tags


def drop_repeat_blocks(
    text: str, where: str, seen: dict[str, str]
) -> tuple[str, list[str]]:
    """丢掉上周已经推送过的 `### ` 条目块（代码硬兜底，是三道去重里最硬的一道）。

    返回 (清理后的正文, 被丢掉条目的标题列表)。**注意返回值与促销过滤器完全分开**：
    这里的标题不能混进 `banned_urls` —— 那一批是"折扣稿黑名单"，混进去等于告诉模型
    这些是真新闻的反面，会让它连带躲开整个域名。

    只删 `### ` 块。板块四（分地区短段落）与板块五（bullet）没有 `### ` 块，代码够不着，
    纯靠提示词兜。

    ⚠️ **这两个板块连告警都没有 —— 别以为这里还有第二道网。** 按 `group_blocks` /
    `_section_of_blocks` 的语义，板块四、五的正文归属于各自 `## ` 标题所在的 **h2 块**
    （首行是 `## `），既不是 `h3` 也不是 `other`，所以下面两处分支都够不到它们：
    命中重复时既不删、也不打 WARNING。要让板块四真正被检查，得改成按段落扫描。
    """
    if not seen:
        return text, []

    blocks, tags = _section_of_blocks(text)

    reasons: dict[int, str] = {}
    for index, block in enumerate(blocks):
        kind, section = tags[index]
        if kind != "h3":
            continue
        # 板块五的链接天然是板块一的子集，判定必然命中 —— 永久跳过，别删也别告警。
        if section == SECTION_FIVE_HEADING:
            continue
        reason = block_repeat_reason("\n".join(block), seen)
        if reason:
            reasons[index] = reason

    # 空板块守卫：一个板块的条目被删光会推出去一个只有标题的空壳。
    # 那种情况下整段恢复 —— 重复总好过空白。
    by_section: dict[str, list[int]] = {}
    for index, (kind, section) in enumerate(tags):
        if kind == "h3":
            by_section.setdefault(section, []).append(index)
    for section, indices in by_section.items():
        if indices and all(i in reasons for i in indices):
            LOG.warning("[%s] 板块 %r 的条目会被全部删光，已整段恢复 —— "
                        "重复好过推一个空板块，请人工看一眼这周是不是真的没有新动态",
                        where, section)
            for index in indices:
                reasons.pop(index, None)

    dropped: list[str] = []
    kept: list[str] = []
    for index, block in enumerate(blocks):
        chunk = "\n".join(block)
        kind, section = tags[index]
        if index in reasons:
            title = block[0].lstrip("# ").strip()[:50]
            LOG.warning("[%s] 丢弃重复条目（%s）｜ 标题：%s",
                        where, reasons[index], title)
            dropped.append(title)
            continue
        # 只覆盖第一个 `## ` 之前的前导块。**板块四、五的段落走不到这里** —— 它们
        # 归属各自 `## ` 标题所在的 h2 块，不是 `other`（见 _section_of_blocks）。
        # 前导块命中时只告警不删：段落里往往混着同段的真情报，删了会连带丢掉。
        if kind == "other" and section != SECTION_FIVE_HEADING:
            if block_repeat_reason(chunk, seen):
                LOG.warning("[%s] 段落命中已推送过的链接，但段落无法整块删除，"
                            "请人工确认：%s", where, chunk.strip()[:80])
        kept.append(chunk)

    return "\n".join(kept), dropped


def fetch_section1(
    cfg: dict[str, str], today: datetime, history: list[dict]
) -> str:
    """板块一：两轮调用。

    第一轮把检索预算全压在这一个板块上；第二轮带上第一轮的原文，要求补漏并合并成
    最终一份。**两轮结果不做本地拼接** —— 拼接会得到两份互相重复、口径不一的板块。
    """
    first, _ = call_openrouter(
        cfg,
        [
            {"role": "system", "content": SECTION1_SYSTEM_PROMPT},
            {"role": "user", "content": build_section1_user_prompt(today, history)},
        ],
        label="板块一·第一轮",
    )
    if not first:
        raise RuntimeError("板块一第一轮返回了空正文")
    LOG.info("板块一第一轮完成：%d 字", len(first))

    # 在第一轮的结果上先拦一道：被剔除的链接会作为黑名单写进第二轮的提示，
    # 防止补漏时从同一批检索结果里再把同一篇折扣稿捞回来。
    first, banned = drop_promo_blocks(first, "板块一第一轮")

    seen = seen_url_map(history)
    merged, _ = call_openrouter(
        cfg,
        [
            {"role": "system", "content": SECTION1_MERGE_SYSTEM_PROMPT},
            {"role": "user",
             "content": build_section1_merge_user_prompt(
                 today, first, banned, history, seen
             )},
        ],
        label="板块一·第二轮",
    )
    if not merged:
        raise RuntimeError("板块一第二轮返回了空正文")
    LOG.info("板块一第二轮（补漏+合并）完成：%d 字", len(merged))

    # 第二道：第二轮是新检索 + 重新组织，可能引入第一轮没有的折扣稿，必须再过一遍。
    merged, banned2 = drop_promo_blocks(merged, "板块一第二轮")
    if banned2:
        LOG.info("板块一最终剔除促销条目 %d 条", len(banned2))

    # 第三道（最硬）：跨周重复。放在促销过滤之后 —— 先删掉这批折扣稿再判重复，
    # 免得一份"上周推过、这周又打折"的内容走两条路径被记两次。
    merged, repeated = drop_repeat_blocks(merged, "板块一", seen)
    if repeated:
        LOG.info("板块一剔除跨周重复条目 %d 条", len(repeated))
    return merged


def build_report(
    cfg: dict[str, str], today: datetime, history: list[dict] | None = None
) -> tuple[str, list[str]]:
    """取回正文并组装成最终报告。返回 (完整 Markdown, 引用链接列表)。

    共三次调用：板块一两轮（fetch_section1）+ 其余板块一轮。板块一必须先跑 ——
    板块五（对华宝的启发）需要知道便携竞品这周发生了什么，要把它作为参考喂进主调用。
    """
    seen = seen_url_map(history or [])
    section1 = strip_model_heading(fetch_section1(cfg, today, history or []))
    # 安全网：板块一的标题由本地定位，模型跑偏了就自己补上，否则整份报告的层级会乱。
    if SECTION1_HEADING not in section1:
        LOG.warning("板块一的输出里没有 %r，已补上标题", SECTION1_HEADING)
        section1 = f"{SECTION1_HEADING}\n\n{section1}"

    rest, citations = call_openrouter(
        cfg,
        [
            {"role": "system", "content": MAIN_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(today, section1, history or [])},
        ],
        label="板块二~五",
    )
    if not rest:
        raise RuntimeError("主调用返回了空正文")
    rest = strip_model_heading(rest)
    # 促销稿不只出现在板块一（板块二、三同样是厂商条目）。同一套规则再过一遍。
    rest, _ = drop_promo_blocks(rest, "板块二~五")
    # 跨周重复同理，板块二、三也有 `### ` 条目块，代码兜底够得着。
    rest, repeated = drop_repeat_blocks(rest, "板块二~五", seen)
    if repeated:
        LOG.info("板块二~五剔除跨周重复条目 %d 条", len(repeated))

    start, end = _window(today)          # 唯一来源，别在这里重算
    header = (
        f"# {DINGTALK_KEYWORD} 储能结构周报（{today.strftime('%Y-%m-%d')}）\n\n"
        f"> 覆盖周期：{start} ~ {end} ｜ 面向储能结构工程师\n\n"
    )

    body = f"{section1}\n\n{rest}"

    # 安全网：模型偶尔会忘掉正文里的链接。它自己返回的 citations 是真实检索结果，
    # 拿来补一段参考来源，总好过整份报告一个可点的链接都没有。
    if not has_markdown_link(body) and citations:
        LOG.warning("正文里没有任何 Markdown 链接，用 citations 补一段参考来源")
        body += "\n\n## 参考来源\n\n" + "\n".join(
            f"- <{url}>" for url in citations[:20]
        )

    # 安全网之二：关键词必须出现在正文里，否则钉钉会以 310000 整条拒收。
    # header 里一定有关键词，所以这里实际是在兜底"header 被改坏"的极端情况。
    if DINGTALK_KEYWORD not in header + body:
        LOG.warning("正文里没有 %s，已在标题中补上", DINGTALK_KEYWORD)
        header = (
            f"# {DINGTALK_KEYWORD} 储能结构周报（{today.strftime('%Y-%m-%d')}）\n\n"
            + header.split("\n\n", 1)[-1]
        )

    # 安全网之三（硬性约束 4 用在一个原本没人管的地方）：五个板块必须齐全且非空。
    # 放宽到 14 天窗口 + 加了去重之后正文变短的概率明显上升，而**被截断的正好是
    # 末尾的板块四、五**（finish_reason 以前从不检查）。不查的话会推出去一份
    # 缺板块的报告，退出码还是 0，谁也发现不了。
    report = header + body
    _assert_all_sections(report)

    return report, citations


def _assert_all_sections(report: str) -> None:
    """五个板块标题齐全、且每个板块都有内容。缺任何一个就非 0 退出。

    板块四/五是"短段落 / bullet"形态，没有 `### ` 块，所以判据是"标题之后到下一个
    二级标题之前有非空行"。**不要**把它换成"必须有 `### `" —— 那会误判板块四、五。
    """
    blocks = group_blocks(report)
    found: dict[str, int] = {}
    current = ""
    for block in blocks:
        chunk = "\n".join(block)
        stripped = chunk.lstrip()
        if stripped.startswith("## "):
            current = stripped.split("\n", 1)[0].strip()
            found.setdefault(current, 0)
            # ⚠️ 这里**不能 continue**：`group_blocks` 只按标题行起新块，
            # 所以板块四、五的散文正文和它们的 `## ` 标题行是**同一个块**。
            # 早退会把这些正文全漏掉，把有内容的板块误判成空板块并拒绝推送。
        elif not current:
            continue
        # 标题行本身不算内容，只数它下面的非空行。
        body_lines = [
            line for line in chunk.split("\n")
            if line.strip() and not line.lstrip().startswith("#")
        ]
        found[current] += len(body_lines)

    missing = [h for h in SECTION_HEADINGS if h not in found]
    empty = [h for h in SECTION_HEADINGS if h in found and found[h] == 0]
    if not missing and not empty:
        return

    detail = []
    if missing:
        detail.append("缺少板块：" + "、".join(missing))
    if empty:
        detail.append("板块为空：" + "、".join(empty))
    sys.exit(
        "❌ 报告结构不完整，拒绝推送：\n   "
        + "\n   ".join(detail)
        + "\n   五个板块必须齐全且非空（硬性约束 2）。常见原因是模型输出被 "
        "max_tokens 截断（看日志里有没有 finish_reason=length 的 WARNING），"
        "或去重把某个板块清空了。"
    )


# ---------------------------------------------------------------------------
# 网页站点（GitHub Pages）
# ---------------------------------------------------------------------------
# 群里只发"摘要 + 链接"，报告全文落在 docs/ 里，由 workflow 提交回仓库、Pages 发布。
#
# 为什么不引 markdown 库：本项目刻意只有 requests 一个依赖（见文件顶部）。报告由提示词
# 固定成「四段式」，语法集合是一个**可枚举的封闭子集**，自己写 100 行足够，而且不会
# 随第三方库升级而漂移。
#
# ⚠️ **页面里绝不能出现生成时间戳、版本号、datetime.now()。** 站点是幂等重建的：
# 同样的 .md 输入必须产出逐字节相同的 .html。一旦有字段每次都变，工作区就永远是脏的，
# workflow 最后的 `git rebase` 会报 "cannot rebase: You have unstaged changes"。

_PAGE_CSS = """
:root {
  --fg:#1f2328; --muted:#656d76; --line:#d8dee4; --link:#0969da;
  --bg:#fff; --code:#f6f8fa; --accent:#bc4c00;
  --tint:#f6f8fa; --accent-soft:#fdf3ec; --line-2:#eaeef2;
  color-scheme: light;
}
/* 没有显式选择时跟随系统。`:root:not([data-theme])` 与下面的 `:root[data-theme=…]`
   特异性相同（都是 0,2,0），所以**顺序决定胜负** —— 显式那两条必须在文档里靠后，
   否则点了按钮不生效。 */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    --fg:#e6edf3; --muted:#8b949e; --line:#30363d; --link:#4493f8;
    --bg:#0d1117; --code:#161b22; --accent:#f0883e;
    --tint:#161b22; --accent-soft:#25150a; --line-2:#21262d;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --fg:#e6edf3; --muted:#8b949e; --line:#30363d; --link:#4493f8;
  --bg:#0d1117; --code:#161b22; --accent:#f0883e;
  --tint:#161b22; --accent-soft:#25150a; --line-2:#21262d;
  color-scheme: dark;
}
:root[data-theme="light"] {
  --fg:#1f2328; --muted:#656d76; --line:#d8dee4; --link:#0969da;
  --bg:#fff; --code:#f6f8fa; --accent:#bc4c00;
  --tint:#f6f8fa; --accent-soft:#fdf3ec; --line-2:#eaeef2;
  color-scheme: light;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.75 -apple-system, BlinkMacSystemFont, "Segoe UI",
        "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 820px; margin: 0 auto; padding: 22px 20px 72px; }
nav.top {
  display: flex; gap: 12px; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--line); padding-bottom: 12px; margin-bottom: 26px;
  font-size: 14px;
}
nav.top .disabled { color: var(--muted); }
h1 { font-size: 23px; line-height: 1.45; margin: 0 0 6px; }
h2 {
  font-size: 19px; margin: 38px 0 10px; padding-top: 16px;
  border-top: 1px solid var(--line);
}
h3 { font-size: 16.5px; margin: 26px 0 4px; }
p, li { word-break: break-word; }
ul, ol { padding-left: 22px; }
li { margin: 4px 0; }
blockquote {
  margin: 0 0 22px; padding: 2px 0 2px 14px;
  border-left: 3px solid var(--line); color: var(--muted);
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border: 0; border-top: 1px solid var(--line); margin: 32px 0; }
code, pre { background: var(--code); border-radius: 6px; }
pre { padding: 12px; overflow-x: auto; font-size: 13px; }
strong { font-weight: 600; }
footer {
  margin-top: 52px; padding-top: 16px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 13px;
}
.archive { list-style: none; padding: 0; margin: 8px 0 0; }
.archive li {
  display: flex; gap: 14px; align-items: baseline;
  padding: 12px 0; border-bottom: 1px solid var(--line);
}
.archive .d { font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
.archive .sub { color: var(--muted); font-size: 13px; }
.archive .none { color: var(--muted); }

/* ---------------- 图文版 / 文字版 切换（纯 CSS，不用 JS） ----------------
   兄弟选择器 `~` 要求 radio 必须排在 .view / .vswitch **前面**，且同为 .wrap 的子元素。
   用 radio 而不是一段 JS：邮件客户端、RSS 阅读器、企业策略下 JS 可能被禁，
   而这几类正是本报告的读者可能遇到的环境。代价是**选择不会跨页记住**。
   ⚠️ 这段注释里不要写出尖括号标签名 —— `_PAGE_CSS` 是内联进 `<style>` 的，
   一旦出现结束标签就会把整个样式块提前截断。见下方 `_theme_script_is_safe` 的守卫。 */
.vmode { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.has-toggle .view { display: none; }
.has-toggle #v-rich:checked ~ .view-rich { display: block; }
.has-toggle #v-plain:checked ~ .view-plain { display: block; }
/* ⚠️ 控件行必须是 radio 的**后置兄弟**，`~` 才够得到；标签再嵌一层 .vswitch 不影响，
   但选择器要写成 `~ .ctrls label[…]`，不能写成 `~ .vswitch label[…]`。 */
.ctrls {
  display: flex; justify-content: flex-end; align-items: center;
  gap: 9px; margin: -10px 0 18px;
}
.vswitch { display: flex; }
.vswitch label {
  cursor: pointer; font-size: 13px; padding: 5px 14px; user-select: none;
  border: 1px solid var(--line); color: var(--muted); background: var(--bg);
}
.vswitch label:first-of-type { border-radius: 999px 0 0 999px; }
.vswitch label:last-of-type { border-radius: 0 999px 999px 0; border-left: 0; }
.has-toggle #v-rich:checked ~ .ctrls label[for="v-rich"],
.has-toggle #v-plain:checked ~ .ctrls label[for="v-plain"] {
  background: var(--accent); border-color: var(--accent); color: #fff;
}
/* 无 JS 时按钮保持 hidden，不显示一个点了没反应的假按钮。 */
.themebtn {
  font: inherit; font-size: 13px; padding: 5px 14px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 999px;
  background: var(--bg); color: var(--muted); white-space: nowrap;
}
.themebtn:hover { color: var(--fg); border-color: var(--muted); }
.themebtn[hidden] { display: none; }

/* ---------------- 报告头 ---------------- */
.hero {
  background: var(--tint); border: 1px solid var(--line); border-radius: 14px;
  padding: 22px 22px 18px; margin-bottom: 20px;
}
.hero .kicker {
  font-size: 12.5px; font-weight: 600; letter-spacing: .1em;
  color: var(--accent); margin-bottom: 6px;
}
.hero h1 { margin: 0 0 14px; line-height: 1.3; }
.hero h1 .h1a { font-size: 19px; font-weight: 500; }
.hero h1 .h1b {
  font-size: 27px; font-weight: 700; margin-left: 10px;
  font-variant-numeric: tabular-nums;
}
.hero .meta { display: flex; flex-wrap: wrap; gap: 8px; }
.hero .lead { margin-top: 15px; padding-top: 14px; border-top: 1px solid var(--line); }
.hero .lead p { margin: 0 0 8px; font-size: 15px; }
.hero .lead p:last-child { margin-bottom: 0; }
.chip {
  font-size: 12.5px; padding: 3px 11px; border-radius: 999px;
  background: var(--bg); border: 1px solid var(--line); color: var(--muted);
}

/* ---------------- 目录 ---------------- */
.toc {
  border: 1px solid var(--line); border-radius: 12px; background: var(--tint);
  padding: 15px 19px; margin-bottom: 24px;
}
.toc-t {
  font-size: 12.5px; color: var(--muted); letter-spacing: .06em; margin-bottom: 9px;
}
.toc ul { list-style: none; padding: 0; margin: 0; }
.toc li { margin: 7px 0; }
.toc a { display: flex; gap: 10px; align-items: baseline; }
.toc a:hover { text-decoration: none; }
.toc a:hover .toc-t2 { text-decoration: underline; }
.toc .tn {
  flex: none; width: 20px; height: 20px; border-radius: 6px;
  background: var(--bg); border: 1px solid var(--line); color: var(--accent);
  font-size: 12px; font-weight: 600; line-height: 19px; text-align: center;
}
.toc .toc-t2 { font-size: 14.5px; color: var(--fg); }
.toc .tc { margin-left: auto; font-size: 12.5px; color: var(--muted); white-space: nowrap; }

/* ---------------- 左侧固定目录（宽屏） ----------------
   宽屏时把目录从正文顶部挪到左边固定住，读到哪儿都能直接跳到别的章节。
   窄屏放不下侧栏，退回正文顶部那一份 —— 两份目录在 DOM 里都在，靠媒体查询
   保证任何宽度下**只有一份可见**。纯 CSS，不依赖 JS。

   侧栏只能放在 `.view-rich` 里：文字版的锚点前缀是 `p-`，侧栏若在视图外面、
   链接却写 `#sec-N`，切到文字版就成了点了没反应的死链。放在里面则随视图一起
   显隐 —— 这正是想要的。 */
.toc-side { display: none; }
@media (min-width: 1320px) {
  .toc-side {
    display: block; position: fixed; z-index: 5;
    top: 24px; left: max(16px, calc(50% - 636px));
    width: 216px; max-height: calc(100vh - 48px);
    overflow-y: auto; margin-bottom: 0;
  }
  .toc-inline { display: none; }
}
/* 点目录跳过去之后，给落地的那一节一个可见的边 —— 否则读者不知道自己跳到了哪儿。 */
section.card:target { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }

/* ---------------- 板块卡片 ---------------- */
section[id] { scroll-margin-top: 16px; }
.card {
  border: 1px solid var(--line); border-radius: 12px;
  padding: 18px 20px 14px; margin-bottom: 22px;
}
.sec-head { display: flex; align-items: center; gap: 11px; margin: 0 0 12px; }
.sec-num {
  flex: none; width: 30px; height: 30px; border-radius: 9px;
  background: var(--accent); color: #fff; font-size: 15px; font-weight: 600;
  display: flex; align-items: center; justify-content: center;
}
.sec-title { font-size: 18.5px; font-weight: 600; line-height: 1.4; }
.sec-count { margin-left: auto; font-size: 12.5px; color: var(--muted); white-space: nowrap; }

/* ---------------- 条目 ---------------- */
.entry { padding: 15px 0 4px; border-top: 1px dashed var(--line); }
.entry:first-of-type { border-top: 0; padding-top: 2px; }
.entry-head { margin: 0 0 9px; font-size: 16.5px; line-height: 1.55; font-weight: 600; }
.entry-head .idx {
  display: inline-block; min-width: 18px; height: 18px; padding: 0 5px;
  border-radius: 5px; background: var(--tint); border: 1px solid var(--line);
  color: var(--muted); font-size: 11.5px; font-weight: 600;
  line-height: 17px; text-align: center; vertical-align: 2px; margin-right: 7px;
}
.entry-head .vendor { color: var(--accent); }
.entry-head .etitle { font-weight: 500; }
.entry-head .dash { color: var(--muted); font-weight: 400; }
.rbadge {
  display: inline-block; padding: 2px 12px; border-radius: 999px;
  background: var(--tint); border: 1px solid var(--line);
  color: var(--accent); font-size: 14px; font-weight: 600;
}
.pts { list-style: none; padding: 0; margin: 0 0 4px; }
.pts li { position: relative; padding-left: 17px; margin: 7px 0; }
.pts li::before {
  content: ""; position: absolute; left: 3px; top: .68em;
  width: 5px; height: 5px; border-radius: 50%; background: var(--muted); opacity: .55;
}
.entry .src {
  margin: 12px 0 0; padding-top: 9px; border-top: 1px dotted var(--line);
  font-size: 13px; color: var(--muted); line-height: 1.9;
}
.entry .src .lbl { font-weight: 600; color: var(--muted); }
.entry .feat {
  margin: 11px 0 2px; padding: 10px 14px;
  border-left: 3px solid var(--accent); border-radius: 0 8px 8px 0;
  background: var(--accent-soft); font-size: 14.5px;
}
.entry .feat .lbl { color: var(--accent); font-weight: 700; margin-right: 6px; }

/* ---------------- 板块五：建议 ---------------- */
.advice { list-style: none; padding: 0; margin: 0; counter-reset: adv; }
.advice li {
  counter-increment: adv; position: relative;
  padding: 13px 0 13px 40px; border-top: 1px dashed var(--line);
}
.advice li:first-child { border-top: 0; }
.advice li::before {
  content: counter(adv); position: absolute; left: 0; top: 13px;
  width: 25px; height: 25px; border-radius: 8px;
  background: var(--tint); border: 1px solid var(--line); color: var(--accent);
  font-size: 13px; font-weight: 700; line-height: 24px; text-align: center;
}
.advice .adv-lead { margin: 0 0 6px; font-weight: 600; font-size: 15.5px; }
.advice p { margin: 0; }
.signoff {
  margin: 14px 0 0; padding-top: 10px; border-top: 1px dotted var(--line);
  color: var(--muted); font-size: 12.5px;
}

@media (max-width: 520px) {
  .wrap { padding: 16px 15px 56px; }
  .archive li { flex-direction: column; gap: 2px; }
  .card { padding: 15px 15px 11px; }
  .hero { padding: 18px 16px 15px; }
  .hero h1 .h1b { font-size: 23px; margin-left: 8px; }
  .sec-count { display: none; }
  .toc .tc { display: none; }
  .entry-head { font-size: 15.5px; }
}
"""

# 配色切换脚本。
#
# ⚠️ 必须内联在 `<head>`、**在 <body> 之前同步执行**。挂到 `</body>` 前会让深色用户先看到
# 一帧白底的闪屏（FOUC）—— 而那正是最需要这个按钮的人。
#
# 为什么这一段用 JS、而"图文版/文字版"那道用纯 CSS：配色要覆盖系统设置就必须改 `:root`
# 上的变量，而 `.wrap` 里的 radio 够不到 `:root`（`:has()` 能做但太脆），更要命的是
# `body` 自己的背景色只认 `:root` 的值 —— 用纯 CSS 会出现"卡片变色、页面底色不变"的破绽。
# 而**没有 JS 时代价很小**：页面照样跟随系统，按钮自己 `hidden` 不显示，不会留一个点了
# 没反应的假按钮。视图切换反过来 —— 它影响内容本身，所以那边坚持纯 CSS。
#
# ⚠️ 下面是**静态字面量**，每次生成逐字节相同，不影响站点的幂等性。别往里塞时间戳。
_THEME_SCRIPT = """
(function(){
  var K='weekly-theme', root=document.documentElement;
  try{
    var s=localStorage.getItem(K);
    if(s==='dark'||s==='light')root.setAttribute('data-theme',s);
  }catch(e){}
  function wire(){
    var b=document.getElementById('themebtn');
    if(!b)return;
    var mq=window.matchMedia?window.matchMedia('(prefers-color-scheme: dark)'):null;
    function cur(){
      return root.getAttribute('data-theme')||((mq&&mq.matches)?'dark':'light');
    }
    function paint(){b.textContent=(cur()==='dark')?'浅色':'深色';}
    b.addEventListener('click',function(){
      var next=(cur()==='dark')?'light':'dark';
      root.setAttribute('data-theme',next);
      try{localStorage.setItem(K,next);}catch(e){}
      paint();
    });
    b.hidden=false;
    paint();
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',wire);
  }else{
    wire();
  }
})();
"""

# `- <https://…>` 尖括号自动链接。build_report() 在"正文一个链接都没有"时的
# 「## 参考来源」兜底分支产出的正是这种写法。
_ANGLE_URL_RE = re.compile(r"<(https?://[^>\s]+)>")


def _assert_inline_blocks_safe() -> None:
    """`_PAGE_CSS` / `_THEME_SCRIPT` 是**内联**进 HTML 的，必须不含各自的结束标签。

    `<style>` 与 `<script>` 都是 HTML 的 raw-text 元素，**只被对应的结束标签终止** ——
    在样式表的一条注释里提到 `</style>`，整个样式块就会在那里被截断，页面退化成裸文本。
    这两个常量都是手工维护的长字符串，注释里顺手写出标签名是很自然的动作，所以设这道守卫。

    症状是"页面突然完全没样式"，排查起来会先怀疑浏览器缓存、Pages 构建、模板…… 与其那样，
    不如在 `python main.py` 启动时就非 0 退出。
    """
    for name, text, closer in (
        ("_PAGE_CSS", _PAGE_CSS, "</style"),
        ("_THEME_SCRIPT", _THEME_SCRIPT, "</script"),
    ):
        if closer in text.lower():
            raise ValueError(
                f"{name} 里出现了 {closer}>。它会被内联进 HTML，把该块提前截断，"
                "请改写那段注释（不要写出尖括号标签名）。"
            )


_assert_inline_blocks_safe()

# `**粗体**`。⚠️ `[^*\n]` 里的 `\n` 不能去掉 —— 允许粗体跨行的话，正文里一个落单的
# `*` 会跟下一行的 `**` 配对，把中间整句吃掉。这里按行处理本来就遇不到 \n，
# 显式排除是防将来有人改成整段处理。
_BOLD_RE = re.compile(r"\*\*(?!\s)([^*\n]+?)\*\*")

# 板块四的地区分组行：`**北美**` 独占一行。（`**来源**：…` 结尾还有冒号和内容，
# 不匹配这个"整行只有加粗"的形状。）
_DIGEST_REGION_RE = re.compile(r"^\*\*([^*]+)\*\*$")

# 归档索引里，哪些加粗行不是地区名。
_DIGEST_REGION_SKIP = frozenset({"来源", "特点", "摘要", "总结"})

# docs/ 下合法的期号文件名。**只认严格的小写 YYYY-MM-DD.md** —— workflow 里的
# 提交白名单正则就是这个形状，两处必须一致，否则 CI 会因为"白名单外的路径"硬失败。
_ISSUE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def _write_text(path: Path, text: str) -> None:
    """统一按 UTF-8 + LF 落盘。

    ⚠️ 两个参数都不是可选的：漏掉 `encoding` 在 Windows 上会写成 cp936（Pages 上是乱码），
    漏掉 `newline="\\n"` 会产生 .gitattributes 注释里描述的那种**整文件级假 diff**。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _inline_text(raw: str) -> str:
    """转义 HTML 特殊字符，再把 `**粗体**` 转成 <strong>。"""
    # quote=True 不能省：报告内容来自公网检索，一个带 `"` 的 URL 能从 href="…" 里逃逸出去。
    return _BOLD_RE.sub(r"<strong>\1</strong>", html.escape(raw, quote=True))


def _anchor(url: str, label: str) -> str:
    return (
        f'<a href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{_inline_text(label)}</a>'
    )


def _inline(raw: str) -> str:
    """把一行的行内语法转成 HTML。**输入是未转义的原文。**

    ⚠️ 尖括号自动链接必须在 HTML 转义**之前**认出来：`<https://…>` 一旦被转义成
    `&lt;https://…&gt;` 就再也认不出来了。所以先用占位符把它换走，转义与替换都做完
    再换回来。
    """
    holders: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        holders.append(_anchor(match.group(1), match.group(1)))
        return f"\x00{len(holders) - 1}\x00"

    raw = _ANGLE_URL_RE.sub(_stash, raw)

    pieces: list[str] = []
    pos = 0
    # ⚠️ 逐字复用 MARKDOWN_LINK_RE，不要另写一条匹配规则。否则**网页上可点的链接和
    # 台账里记的链接会分成两套**，静默漂移，而且没人会发现。
    for match in MARKDOWN_LINK_RE.finditer(raw):
        # 这条正则只捕获 URL，起点落在 `](` 的 `]` 上，所以往回找配对的 `[`。
        open_at = raw.rfind("[", pos, match.start())
        if open_at < 0:
            continue
        url = match.group(1)
        pieces.append(_inline_text(raw[pos:open_at]))
        # 正则已经要求 https?://，这里再判一次是刻意留的冗余：将来若有人放宽了那条
        # 正则，这一行仍然挡得住 javascript: 之类的伪协议。
        if url.startswith(("http://", "https://")):
            pieces.append(_anchor(url, raw[open_at + 1:match.start()]))
        else:
            pieces.append(_inline_text(raw[open_at:match.end()]))
        pos = match.end()
    pieces.append(_inline_text(raw[pos:]))

    text = "".join(pieces)
    for index, snippet in enumerate(holders):
        text = text.replace(f"\x00{index}\x00", snippet)
    return text


def markdown_to_html(md: str, id_prefix: str = "sec-") -> str:
    """把报告 Markdown 渲染成 HTML。**只覆盖本项目自己产出的封闭子集。**

    支持的块级语法：`# ` / `## ` / `### ` / `> ` / `- ` / `1. ` / `---` / 空行 / 其它段落。

    ⚠️ `id_prefix` 不是可有可无的：单期页面里**图文版和文字版同时存在**（靠 CSS 切换
    显隐），两边都会给二级标题生成 id。用同一个前缀就会在同一份文档里出现重复 id ——
    目录的 `#sec-1` 会跳到 DOM 里靠前的那个匹配上，而那个可能正躺在被隐藏的视图里，
    点了没反应。所以图文版用 `sec-`、文字版用 `p-sec-`。
    """
    out: list[str] = []
    para: list[str] = []                 # 累积中的段落行
    items: list[list[str]] = []          # 当前列表的条目，每条是若干行（首行 + 缩进续行）
    list_kind: str | None = None         # "ul" / "ol"
    in_fence = False
    h2_seen = 0

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append("<p>" + "<br>\n".join(_inline(l) for l in para) + "</p>")
            para = []

    def flush_list() -> None:
        nonlocal items, list_kind
        if items and list_kind:
            body = "".join(
                "<li>" + "<br>\n".join(_inline(l) for l in item) + "</li>"
                for item in items
            )
            out.append(f"<{list_kind}>{body}</{list_kind}>")
        items = []
        list_kind = None

    def flush_all() -> None:
        flush_para()
        flush_list()

    for raw_line in md.split("\n"):
        stripped = raw_line.strip()

        # ``` 围栏：整段原样输出，不解析里面的任何标记。
        # 提示词没让模型写代码块，但检索内容偶尔会渗进来。
        if stripped.startswith("```"):
            flush_all()
            in_fence = not in_fence
            out.append("<pre><code>" if in_fence else "</code></pre>")
            continue
        if in_fence:
            out.append(html.escape(raw_line))
            continue

        # ⚠️ 缩进的续行要并进上一个条目/段落。板块五的每条建议都有缩进续行，
        # 若按 CommonMark 的"4 空格 = 代码块"处理，每条建议的第二段会掉出列表、
        # 整节散架。
        if stripped and raw_line[:1] in (" ", "\t"):
            if items:
                items[-1].append(stripped)
            elif para:
                para.append(stripped)
            else:
                para.append(stripped)
            continue

        if not stripped:
            flush_all()
            continue

        if stripped.startswith("### "):
            flush_all()
            out.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            flush_all()
            h2_seen += 1
            out.append(f'<h2 id="{id_prefix}{h2_seen}">{_inline(stripped[3:])}</h2>')
        elif stripped.startswith("# "):
            flush_all()
            out.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped.startswith("> "):
            flush_all()
            out.append(f"<blockquote>{_inline(stripped[2:])}</blockquote>")
        elif stripped.startswith("- ") or stripped == "-":
            flush_para()
            if list_kind != "ul":
                flush_list()
                list_kind = "ul"
            items.append([stripped[2:].strip()])
        elif re.match(r"^\d+[.)]\s", stripped):
            flush_para()
            if list_kind != "ol":
                flush_list()
                list_kind = "ol"
            items.append([re.sub(r"^\d+[.)]\s+", "", stripped)])
        elif stripped.startswith("---") and "|" not in stripped:
            flush_all()
            out.append("<hr>")
        else:
            # ⚠️ 这个分支必须存在：板块四的 `**北美**` 独立加粗行不属于上面任何一种
            # 标记，会落到这里。没有它，板块四整节的可读性就没了。
            #
            # 另外 `---` 那条规则刻意排除了含 `|` 的行：模型万一渗出 Markdown 表格，
            # `|---|---|` 分隔行会被渲染成一条横线、把表格劈开。
            flush_list()
            para.append(stripped)

    flush_all()
    return "\n".join(out)


def _report_title(md: str) -> str:
    """取报告的一级标题文字（去掉 `# `）。"""
    for line in md.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return "储能结构周报"


def _page_shell(
    title: str, nav: str, body: str, footer: str, *, has_toggle: bool = False
) -> str:
    """`has_toggle` 决定要不要输出视图切换控件、以及给 .wrap 挂 `has-toggle`。

    ⚠️ `has-toggle` 是**显隐规则的总开关**：`.has-toggle .view { display:none }` 只在单期
    页面上生效。归档首页没有切换控件，如果无脑给它加上这个类，整页内容会被藏起来变成白屏。
    所以由调用方显式声明，不要改成"有 .view 就隐藏"。
    """
    if has_toggle:
        radios = (
            '<input type="radio" name="view" id="v-rich" class="vmode" checked>'
            '<input type="radio" name="view" id="v-plain" class="vmode">'
        )
        switch = (
            '<span class="vswitch">'
            '<label for="v-rich">图文版</label><label for="v-plain">文字版</label>'
            "</span>"
        )
    else:
        # 归档页不输出 radio，也不挂 .has-toggle —— 整页正常显示，不会被藏起来。
        radios = ""
        switch = ""
    # ⚠️ `radio → .ctrls → .view` 的兄弟顺序不能变，CSS 用的是 `~`。
    # 配色按钮两个页面都有（在单期页选了深色，跳回归档不该变回浅色）。
    body = (
        f'{radios}<div class="ctrls">{switch}'
        f'<button type="button" class="themebtn" id="themebtn" hidden>深色</button></div>'
        f"{body}"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{html.escape(title)}</title>
<script>{_THEME_SCRIPT}</script>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="wrap{' has-toggle' if has_toggle else ''}">
{nav}
{body}
<footer>{footer}</footer>
</div>
</body>
</html>
"""


def _nav(prev_date: str, next_date: str, index_name: str) -> str:
    """顶部导航。用**相对链接**，这样本地直接双击打开 docs/ 里的文件也能跳。"""
    left = (
        f'<a href="{prev_date}.html">← 上一期</a>'
        if prev_date else '<span class="disabled">← 上一期</span>'
    )
    right = (
        f'<a href="{next_date}.html">下一期 →</a>'
        if next_date else '<span class="disabled">下一期 →</span>'
    )
    return (
        f'<nav class="top">{left}'
        f'<a href="{index_name}">全部往期</a>'
        f"{right}</nav>"
    )


# ---------------- 图文版：报告头 + 目录 + 板块卡片 + 条目 ----------------

# `## 一、便携&阳台储能竞品动态` → 序号「一」+ 标题
_SECTION_HEAD_RE = re.compile(r"^##\s*([一二三四五六七八九十]+)\s*[、.．]\s*(.+?)\s*$")
# `### 1. **BLUETTI** —— Balco 500` → 序号 1 + 其余
_ENTRY_HEAD_RE = re.compile(r"^###\s+(\d+)\s*[.、)）]\s*(.+?)\s*$")
# `**BLUETTI** —— Balco 500` → 厂商 + 标题
_ENTRY_SPLIT_RE = re.compile(r"^\*\*(.+?)\*\*\s*——\s*(.+)$")
# `**来源**：…` / `来源：…`（`\**` 让加粗与不加粗两种写法都吃）
_SRC_LINE_RE = re.compile(r"^\**\s*来源\s*\**\s*[:：]\s*(.*)$")
_FEAT_LINE_RE = re.compile(r"^\**\s*特点\s*\**\s*[:：]\s*(.*)$")
# 建议条目的首句（整句加粗）
_ADV_LEAD_RE = re.compile(r"^\*\*(.+?)\*\*\s*(.*)$", re.S)
# HTML 注释。`example_report.md` 顶部就有一大段给使用者看的说明。
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# 正文末尾的落款行（`—— 本消息由自动化脚本生成…`）。它是 `build_report()` 拼进去的，
# 不是给模型写的，所以不能跟正文混在一起渲染。
_SIGNOFF_RE = re.compile(r"^[—–-]{2,}")


def _strip_comments(md: str) -> str:
    """去掉 HTML 注释后再渲染。

    实时报告由 `build_report()` 拼装、不含注释，但**万一模型吐出一段注释**，纯文字版会
    把它当普通段落整段显示给读者。

    ⚠️ 只影响渲染。`write_issue_source()` 落进 docs/ 的 `.md` **仍是逐字节原文** ——
    那是刻意的，真相不该被渲染层动过。
    """
    return _HTML_COMMENT_RE.sub("", md)


def _split_sections(md: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """切成 (前言行, [(二级标题, 正文行), ...])。

    **刻意不复用 `group_blocks()`。** 它在 `### ` 上也起新块，用它就得再写一层状态机
    把 `### ` 块按顺序认回各自所属的 `## `。这里只按 `## ` 切，板块四/五那种没有
    `### ` 的散文正文自然就留在自己的小节里。
    """
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in md.split("\n"):
        if line.startswith("## "):
            sections.append((line.strip()[3:].strip(), []))
            continue
        (preamble if not sections else sections[-1][1]).append(line)
    return preamble, sections


def _split_groups(body: list[str]) -> tuple[list[str], list[list[str]]]:
    """把一个小节的正文切成 (引言行, [组, ...])。

    一个「组」由 `### ` 行、或独占一行的加粗行（板块四的 `**北美**`）开头 ——
    这两种形状**后续结构完全一样**（分点 + 来源 + 特点），所以共用一套渲染。

    ⚠️ `**来源**` / `**特点**` 也是"独占一行的加粗"形状，必须靠 `_DIGEST_REGION_SKIP`
    排除，否则每条都会被从中间劈成两个组，第二组只剩来源行。
    """
    preamble: list[str] = []
    groups: list[list[str]] = []
    for line in body:
        stripped = line.strip()
        starts = stripped.startswith("### ")
        if not starts:
            matched = _DIGEST_REGION_RE.match(stripped)
            starts = bool(matched) and matched.group(1).strip() not in _DIGEST_REGION_SKIP
        if starts:
            groups.append([line])
        elif groups:
            groups[-1].append(line)
        else:
            preamble.append(line)
    return preamble, groups


def _plain_words(text: str) -> str:
    """把多行纯文本接成一行 HTML（行间用 <br>），供 `_inline` 之外的零散片段用。"""
    return "<br>\n".join(_inline(l) for l in text.split("\n") if l.strip())


def _rich_group(lines: list[str]) -> str:
    """渲染一个「组」：条目（`### `）或地区分组（`**北美**`）。"""
    head = lines[0].strip()
    bullets: list[str] = []
    srcs: list[str] = []
    feats: list[str] = []
    other: list[str] = []

    for raw in lines[1:]:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") or stripped == "-":
            bullets.append(stripped[2:].strip())
            continue
        matched = _SRC_LINE_RE.match(stripped)
        if matched:
            srcs.append(matched.group(1))
            continue
        matched = _FEAT_LINE_RE.match(stripped)
        if matched:
            feats.append(matched.group(1))
            continue
        other.append(raw)

    if head.startswith("### "):
        index = ""
        text = head[4:].strip()
        matched = _ENTRY_HEAD_RE.match(head)
        if matched:
            index, text = matched.group(1), matched.group(2)
        split = _ENTRY_SPLIT_RE.match(text)
        if split:
            inner = (
                f'<span class="vendor">{_inline(split.group(1))}</span>'
                f'<span class="dash"> —— </span>'
                f'<span class="etitle">{_inline(split.group(2))}</span>'
            )
        else:
            # 模型偶尔不按 `**厂商** —— 标题` 写。整条照原样渲染，不要丢内容。
            inner = _inline(text)
        badge = f'<span class="idx">{index}</span>' if index else ""
        head_html = f'<h3 class="entry-head">{badge}{inner}</h3>'
    else:
        # 地区分组行。`**北美**` 这种整行加粗已被 `_split_groups` 认成组头。
        matched = _DIGEST_REGION_RE.match(head)
        label = matched.group(1).strip() if matched else head
        head_html = (
            f'<h3 class="entry-head"><span class="rbadge">{_inline(label)}</span></h3>'
        )

    out = ['<article class="entry">', head_html]
    if bullets:
        out.append('<ul class="pts">')
        out.extend(f"<li>{_inline(b)}</li>" for b in bullets)
        out.append("</ul>")
    if other:
        # 组里冒出的、认不出的段落（模型偶尔加个过渡句）。退回纯 markdown 渲染，
        # 宁可排版朴素也不要丢字。
        out.append(markdown_to_html("\n".join(other), id_prefix="r-other-"))
    if srcs:
        out.append(
            f'<p class="src"><span class="lbl">来源</span> {_inline(" ".join(srcs))}</p>'
        )
    for feat in feats:
        out.append(f'<p class="feat"><span class="lbl">特点</span> {_inline(feat)}</p>')
    out.append("</article>")
    return "\n".join(out)


def _rich_advice(lines: list[str]) -> str:
    """板块五：编号建议单独排版；若一条都认不出，整段退回纯 markdown。"""
    items: list[list[str]] = []
    lead_in: list[str] = []
    signoff: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        # ⚠️ 落款行必须**先**认出来。它是正文的最后一行、又不是编号条目，否则会掉进
        # 下面那个 `elif items` 分支、被追加到**最后一条建议**上，看起来像建议 3 的
        # 一部分。它不是模型写的，也不该冒充建议。
        if _SIGNOFF_RE.match(stripped):
            signoff.append(stripped)
            continue
        matched = re.match(r"^\d+[.)、]\s+(.*)$", stripped)
        # 缩进行是上一条的续行，不是新条目 —— 板块五每条都有缩进续行，
        # 判错会让每条建议都被劈成「标题一条 + 正文一条」。
        if matched and not raw[:1].isspace():
            items.append([matched.group(1)])
        elif items:
            items[-1].append(stripped)
        else:
            lead_in.append(raw)

    if not items:
        return markdown_to_html("\n".join(lines), id_prefix="r-plain-")

    out: list[str] = []
    if lead_in:
        out.append(markdown_to_html("\n".join(lead_in), id_prefix="r-lead-"))
    out.append('<ol class="advice">')
    for item in items:
        text = "\n".join(item).strip()
        matched = _ADV_LEAD_RE.match(text)
        if matched:
            out.append(f'<li><p class="adv-lead">{_inline(matched.group(1))}</p>')
            rest = matched.group(2).strip()
        else:
            out.append("<li>")
            rest = text
        if rest:
            out.append(f"<p>{_plain_words(rest)}</p>")
        out.append("</li>")
    out.append("</ol>")
    # 落款留一行，但**不要丢掉** —— 站点的页脚是另一回事，正文里的这句是报告的一部分。
    for line in signoff:
        out.append(f'<p class="signoff">{_inline(line)}</p>')
    return "\n".join(out)


def _rich_hero(title: str, preamble: list[str], date_str: str, total: int) -> str:
    """报告头：小标 + 大日期 + 信息 chips。"""
    name = title
    if DINGTALK_KEYWORD and name.startswith(DINGTALK_KEYWORD):
        name = name[len(DINGTALK_KEYWORD):].strip()
    # 去掉标题里的 `（2026-09-24）` —— 日期已经在 h1 里单列了，重复一次只是噪音。
    name = re.sub(r"[（(][^）)]*[）)]\s*$", "", name).strip() or "储能结构周报"

    quote = next(
        (l.strip()[2:].strip() for l in preamble if l.strip().startswith("> ")), ""
    )
    chips = [f"本期 {total} 条"]
    if quote:
        chips.extend(p.strip() for p in quote.split("｜") if p.strip())
    chips_html = "".join(f'<span class="chip">{_inline(c)}</span>' for c in chips)

    # ⚠️ 前言里除了 `# ` 标题和 `> ` 引用行，**剩下的正文一行都不能丢**。
    # 目前模型不会在板块一之前写引子，但上面那句"只捞 `> ` 行"的写法会把这些内容
    # 静默吞掉 —— 那正是本项目最忌讳的失败模式。宁可多渲染一段。
    leftovers = [
        line for line in preamble
        if line.strip() and not line.lstrip().startswith(("#", ">"))
    ]
    lead = ""
    if leftovers:
        lead = (
            '<div class="lead">'
            + markdown_to_html("\n".join(leftovers), id_prefix="r-preamble-")
            + "</div>"
        )

    return (
        '<header class="hero">'
        f'<div class="kicker">{_inline(name)}</div>'
        f"<h1>{_inline(date_str)}</h1>"
        f'<div class="meta">{chips_html}</div>'
        f"{lead}"
        "</header>"
    )


def render_rich(md: str, date_str: str) -> str:
    """单期页面的图文版正文：报告头 + 目录 + 五个板块卡片。

    **任何一处解析不出来都要退回 `markdown_to_html()`，绝不能丢字。** 报告结构由提示词
    保证，但模型会漂移；排版崩了是小事，内容消失是大事。
    """
    md = _strip_comments(md)
    preamble, sections = _split_sections(md)
    total = len(extract_entries(md))

    parsed: list[dict] = []
    for index, (heading, body) in enumerate(sections):
        matched = _SECTION_HEAD_RE.match("## " + heading)
        num = matched.group(1) if matched else str(index + 1)
        title = matched.group(2) if matched else heading
        pre, groups = _split_groups(body)
        if groups:
            kind = "entry" if groups[0][0].strip().startswith("### ") else "region"
        else:
            kind = "advice"
        if kind == "entry":
            count = f"{len(groups)} 条"
        elif kind == "region":
            count = f"{len(groups)} 个地区"
        else:
            n = len(re.findall(r"^\d+[.)、]\s", "\n".join(body), re.M))
            count = f"{n} 点建议" if n else ""
        parsed.append({
            "id": f"sec-{index + 1}", "num": num, "title": title, "count": count,
            "pre": pre, "groups": groups, "kind": kind, "body": body,
        })

    if parsed:
        rows = "".join(
            f'<li><a href="#{item["id"]}"><span class="tn">{_inline(item["num"])}</span>'
            f'<span class="toc-t2">{_inline(item["title"])}</span>'
            f'<span class="tc">{_inline(item["count"])}</span></a></li>'
            for item in parsed
        )
        # 同一份目录渲染两遍：宽屏显示左边固定那份（.toc-side），窄屏显示正文顶部
        # 那份（.toc-inline），媒体查询保证任何宽度下只有一份可见。
        # ⚠️ `.toc-side` 是 `position: fixed`，DOM 里放最前面不会占位。
        # ⚠️ 目录本身不带 id，重复渲染**不会**撞 id（本节开头那条重复 id 的忌讳
        # 说的是 `sec-N` / `p-N` 这类锚点，不是这里）。
        listing = f'<div class="toc-t">本期目录</div><ul>{rows}</ul>'
        toc_side = f'<aside class="toc toc-side" aria-label="本期目录">{listing}</aside>'
        toc_inline = f'<div class="toc toc-inline">{listing}</div>'
    else:
        toc_side = toc_inline = ""

    cards: list[str] = []
    for item in parsed:
        if item["groups"]:
            inner = [_rich_group(g) for g in item["groups"]]
            # ⚠️ `pre` 只在这条分支里渲染。**没有分组时 `pre` 就是整个正文**
            # （`_split_groups` 的语义是"第一个分组之前的行"，没有分组就没有"之前"），
            # 而下面那个分支已经用 `_rich_advice` 把整段渲染过一遍了 —— 再渲染一次
            # 会让整个板块**原样出现两遍**。板块五就是这样：它是散文、没有 `### `，
            # 于是"建议列表"上面还压着一份纯 markdown 的同一段内容。
            if item["pre"] and any(l.strip() for l in item["pre"]):
                inner.insert(0, markdown_to_html("\n".join(item["pre"]), id_prefix="r-pre-"))
        else:
            inner = [_rich_advice(item["body"])]
        head = (
            f'<div class="sec-head"><span class="sec-num">{_inline(item["num"])}</span>'
            f'<span class="sec-title">{_inline(item["title"])}</span>'
            f'<span class="sec-count">{_inline(item["count"])}</span></div>'
        )
        cards.append(
            f'<section class="card" id="{item["id"]}">{head}{"".join(inner)}</section>'
        )

    if not parsed:
        # 一个二级标题都没认出来（报告结构整个塌了）。退回纯 markdown，不硬套版式。
        return markdown_to_html(md, id_prefix="sec-")

    return (
        _rich_hero(_report_title(md), preamble, date_str, total)
        + toc_side
        + toc_inline
        + "".join(cards)
    )


def render_issue_page(
    md: str, *, date_str: str, prev_date: str, next_date: str, index_name: str
) -> str:
    """单期页面：图文版与文字版**同时**写进 HTML，靠顶部的 radio 切换显隐。

    两者都服务端渲染，所以关掉 JS 也能用（邮件客户端、RSS 阅读器是常态场景）。
    radio 与控件行由 `_page_shell` 输出 —— 顺序在那边保证，这里只管两个视图。
    """
    md = _strip_comments(md)
    body = (
        f'<div class="view view-rich"><main>{render_rich(md, date_str)}</main></div>'
        f'<div class="view view-plain"><main>'
        # 文字版刻意就是原来那套渲染。id 前缀换成 p-，避免和图文版的 sec-N 撞车 ——
        # 同一份文档里重复 id 会让目录锚点跳到被隐藏的那个视图上，点了没反应。
        f'{markdown_to_html(md, id_prefix="p-")}</main></div>'
    )
    return _page_shell(
        _report_title(md),
        _nav(prev_date, next_date, index_name),
        body,
        "本页由脚本自动生成 ｜ 检索源：Perplexity sonar-pro-search",
        has_toggle=True,
    )


def render_index_page(issues: list[dict], index_name: str) -> str:
    if issues:
        rows = "\n".join(
            f'<li><a class="d" href="{item["date"]}.html">{item["date"]}</a>'
            f'<span class="sub">{html.escape(item["title"])}'
            f' ｜ {item["count"]} 条</span></li>'
            for item in issues
        )
        body = (
            f'<p class="sub">共 {len(issues)} 期 ｜ 最新一期 '
            f'{issues[0]["date"]}</p>\n<ul class="archive">\n{rows}\n</ul>'
        )
    else:
        body = '<p class="none">还没有往期报告。</p>'
    return _page_shell(
        "储能结构周报 · 往期归档",
        '<nav class="top"><span class="disabled">← 上一期</span>'
        '<span>往期归档</span>'
        '<span class="disabled">下一期 →</span></nav>',
        f"<h1>储能结构周报 · 往期归档</h1>\n{body}",
        "本页由脚本自动生成 ｜ 每期报告都会自动出现在这里",
    )


def collect_issues(docs_dir: Path) -> list[dict]:
    """扫 docs/*.md，按日期倒序返回历期。文件名不合规的一律跳过。"""
    issues: list[dict] = []
    if not docs_dir.is_dir():
        return issues
    for path in sorted(docs_dir.glob("*.md")):
        matched = _ISSUE_FILE_RE.match(path.name)
        if not matched:
            continue
        try:
            md = path.read_text(encoding="utf-8")
        except OSError as exc:      # noqa: PERF203
            LOG.warning("归档文件 %s 读取失败，跳过：%s", path.name, exc)
            continue
        issues.append({
            "date": matched.group(1),
            "title": _report_title(md),
            "count": len(extract_entries(md)),
            "md": md,
        })
    issues.sort(key=lambda item: item["date"], reverse=True)
    return issues


def write_issue_source(docs_dir: Path, date_str: str, report: str) -> Path:
    """把当期报告原文落到 docs/<日期>.md。**逐字节就是 report，不要写清洗过的版本** ——
    否则台账、推送正文、网页会变成三份互不相同的文档。"""
    path = docs_dir / f"{date_str}.md"
    _write_text(path, report)
    return path


def build_site(docs_dir: Path) -> list[Path]:
    """从 docs/*.md 全量重建所有 .html 与归档首页。幂等。"""
    issues = collect_issues(docs_dir)
    dates = [item["date"] for item in issues]           # 已按倒序
    written: list[Path] = []
    for index, item in enumerate(issues):
        # dates 是倒序的，所以"上一期"在更后面、"下一期"在更前面。
        newer = dates[index - 1] if index > 0 else ""
        older = dates[index + 1] if index + 1 < len(dates) else ""
        page = render_issue_page(
            item["md"],
            date_str=item["date"],
            prev_date=older,
            next_date=newer,
            index_name=SITE_INDEX_NAME,
        )
        path = docs_dir / f"{item['date']}.html"
        _write_text(path, page)
        written.append(path)
    index_path = docs_dir / SITE_INDEX_NAME
    _write_text(index_path, render_index_page(issues, SITE_INDEX_NAME))
    written.append(index_path)
    return written


def _digest_titles(section_blocks: list[str], limit: int = 2) -> list[str]:
    """取某个板块的头几条 `### ` 条目标题（模型按重要性排，所以取最前面的）。"""
    titles: list[str] = []
    for chunk in section_blocks:
        for line in chunk.split("\n"):
            if not line.lstrip().startswith("### "):
                continue
            title = strip_entry_title(line)
            if title:
                titles.append(title)
            if len(titles) >= limit:
                return titles
    return titles


def _digest_regions(section_blocks: list[str]) -> list[str]:
    """取板块四里的地区分组名（`**北美**` 这种独占一行的加粗行）。"""
    regions: list[str] = []
    for chunk in section_blocks:
        for line in chunk.split("\n"):
            matched = _DIGEST_REGION_RE.match(line.strip())
            if not matched:
                continue
            name = matched.group(1).strip()
            if name and name not in _DIGEST_REGION_SKIP and name not in regions:
                regions.append(name)
    return regions


def build_digest(report: str, today: datetime, base_url: str) -> str:
    """生成推到钉钉群的那条短消息：各板块头条 + 网页链接。

    ⚠️ **五个板块的形态不一样，不能用一套规则套。** 按 `_section_of_blocks()` 的语义，
    板块四**没有 `### ` 块**（首行是 `**北美**` 这种独立加粗行），板块五整节是 `other` 块
    （首行是 `1. **…**`）。不分清的话，摘要会静默地只剩三个板块。

    摘要完全从报告本地抽取，**不额外调 API**。
    """
    blocks, tags = _section_of_blocks(report)
    by_section: dict[str, list[str]] = {}
    for block, (_kind, section) in zip(blocks, tags):
        if section:
            by_section.setdefault(section, []).append("\n".join(block))

    date_str = today.strftime("%Y-%m-%d")
    start, end = _window(today)
    entries = extract_entries(report)

    lines = [
        f"{DINGTALK_KEYWORD} 储能结构周报（{date_str}）",
        "",
        f"本期 {len(entries)} 条 ｜ 覆盖 {start} ~ {end}",
    ]

    # 板块一~三：各自的 `### ` 条目标题，每节最多 2 条。
    for heading in SECTION_HEADINGS[:3]:
        titles = _digest_titles(by_section.get(heading, []))
        if not titles:
            continue
        lines += ["", f"**{heading[3:]}**"]
        lines += [f"· {title}" for title in titles]

    # 板块四：没有 `### `，取地区分组行。没有动态的地区已被提示词要求省略，
    # 所以这里列出的就是本周期真正有内容的地区。
    regions = _digest_regions(by_section.get(SECTION_HEADINGS[3], []))
    if regions:
        lines += ["", f"**{SECTION_HEADINGS[3][3:]}**", "· " + " ｜ ".join(regions)]

    # 板块五：散文，抽不出干净的一句话，给固定说明即可。
    lines += ["", f"**{SECTION_HEADINGS[4][3:]}**", "· 3 点结构建议（详见全文）"]

    if base_url:
        lines += [
            "",
            # ⚠️ 这里必须用 `[文字](网址)` 的**显式链接**写法，不要写裸 URL。
            # 理由：正文里所有链接本来就是这个写法，已经连续几周在群里验证过能点；
            # 裸 URL 走的是钉钉**另一套**自动识别机制，本项目从未验证过。归档那条
            # 还以 `/` 结尾，正是自动识别最容易判错链接边界的地方。
            # 显式写法把边界写死，不依赖渲染器的猜测。
            f"📄 [本期全文]({base_url}/{date_str}.html)",
            # 归档链接和当期链接**一起给**：万一当期页面因为提交失败没发出去，
            # 读者至少能落到一个可用的索引上。
            f"📚 [往期归档]({base_url}/)",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 消息分段
# ---------------------------------------------------------------------------

def _cut_to_bytes(text: str, limit: int) -> tuple[str, str]:
    """把字符串按 UTF-8 字节数切成 (不超过 limit 的前半, 剩余)。

    按字符二分，不会把一个多字节字符劈成两半。
    """
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(text[:mid].encode("utf-8")) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo], text[lo:]


def split_markdown(text: str, limit: int = MAX_MESSAGE_BYTES) -> list[str]:
    """按行切分 Markdown，保证每段的 UTF-8 字节数不超过 limit。

    只在行边界切，不会切断链接或表格；单行本身就超限时才按字符硬切。

    **切分点优先落在 `## ` 板块边界上。** 纯按字节塞满会留下一个很小的尾条，并把
    同一个板块劈进两条消息 —— 实测 r9.md 就是这样：板块五的"第 1 点"留在上一条，
    "第 2、3 点"掉进只有 777 字节的尾条，读者在群里看到的板块五是断的。所以一次切分
    即将超限时，若本段里存在一个 `## ` 行、且切在它前面仍够充实，就切在那里。
    **这只改变"在哪一行切"，字节上限与行边界两条约束都不变**（硬性约束 3）。
    """
    def blen(s: str) -> int:
        return len(s.encode("utf-8")) + 1                 # +1 是换行符

    # 为了对齐板块边界，切点之前至少要留下这么多内容。低于它就宁可按字节切满，
    # 免得推出去一条只有几百字节的消息。
    MIN_FILL = limit // 2

    chunks: list[str] = []
    cur: list[str] = []
    cur_bytes = 0

    def flush(upto: int) -> None:
        """把 cur[:upto] 作为一条消息推出，剩下的留给下一条。"""
        nonlocal cur, cur_bytes
        head = "\n".join(cur[:upto])
        if head.strip():
            chunks.append(head)
        cur = cur[upto:]
        cur_bytes = sum(blen(line) for line in cur)

    for line in text.split("\n"):
        line_bytes = blen(line)
        if cur and cur_bytes + line_bytes > limit:
            # 从后往前找最后一个"切在板块开头"的落点，让消息尽量装得满。
            cut = len(cur)
            for index in range(len(cur) - 1, 0, -1):
                if cur[index].startswith("## ") and sum(
                    blen(part) for part in cur[:index]
                ) >= MIN_FILL:
                    cut = index
                    break
            flush(cut)

        # 单行超限（罕见：极长的段落）—— 硬切，避免死循环。
        while len(line.encode("utf-8")) > limit:
            head, line = _cut_to_bytes(line, limit)
            if cur:
                flush(len(cur))
            chunks.append(head)

        cur.append(line)
        cur_bytes += line_bytes

    if cur and "\n".join(cur).strip():
        chunks.append("\n".join(cur))
    return chunks


def plan_messages(report: str) -> list[str]:
    """把报告切成若干条钉钉消息。**每条都必须带关键词**，否则会被钉钉整条拒收。

    关键词必须落在 markdown.text 正文里 —— 官方从未说明 title 是否参与校验，
    社区反馈只放 title 会被 310000 拒收。所以续条要重新带一次关键词，
    而这里预留出前缀占用的字节，避免加前缀后反而把某条顶过上限。
    """
    # 续条前后缀最长的情况（条数固定为两位数以内），留够余量。
    reserve = len(f"{DINGTALK_KEYWORD} （续 99/99）\n\n".encode("utf-8"))
    parts = split_markdown(report, limit=MAX_MESSAGE_BYTES - reserve)

    messages: list[str] = []
    for index, part in enumerate(parts, start=1):
        if index == 1:
            text = part
            if DINGTALK_KEYWORD not in text:
                # 正常流程里标题已经带了；真缺了就补，别让整条消息因为关键词被拒。
                LOG.warning("首条消息里没有 %s，已补上", DINGTALK_KEYWORD)
                text = f"{DINGTALK_KEYWORD}\n\n{text}"
            messages.append(text)
        else:
            messages.append(f"{DINGTALK_KEYWORD} （续 {index}/{len(parts)}）\n\n{part}")
    return messages


# ---------------------------------------------------------------------------
# 钉钉推送
# ---------------------------------------------------------------------------

def send_dingtalk(webhook: str, title: str, text: str) -> None:
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
        "at": {"isAtAll": False},
    }

    # ⚠️ 收集**所有**失败原因，不是只留最后一个。动机是一次实测：拿一个无效 token
    # 跑重试，第一次回的是 `300005 token is not exist`，而**重试中的某一次**回的是
    # `660026 sending too many messages per minute`。只报最后一个的话，日志上写的是
    # "发太频了"，真正的原因（token 根本不对）被盖掉，排查方向彻底带偏 ——
    # 在**告警**这条路上尤其致命，因为它本来就是用来报错的。
    # （660026 只在那一轮里出现过，重复试验没能复现，所以别把它当成"重试必然如此"。）
    seen: list[str] = []
    for attempt in range(1, DINGTALK_RETRIES + 2):
        try:
            response = requests.post(webhook, json=payload, timeout=20)
            # HTTP 200 不代表成功，必须看 errcode（值可能是字符串 "0"）。
            data = response.json()
            errcode = int(data.get("errcode", -1))
            if errcode == 0:
                return

            errmsg = data.get("errmsg", "")
            if errcode == 410100:
                # 每机器人 20 条/分钟，超限直接封 10 分钟 —— 重试只会延长封禁。
                sys.exit(
                    f"❌ 钉钉限流（410100）：{errmsg}\n"
                    f"   官方限制每机器人 20 条/分钟，超限封 10 分钟。等 10 分钟再跑。"
                )
            if errcode == 310000:
                # 合并安全错误码：关键词不匹配 / timestamp 无效 / 签名不匹配 / IP 不在白名单
                # 四种失败共用它，靠 errmsg 区分，所以必须打 errmsg 而不是只看 code。
                sys.exit(
                    f"❌ 钉钉安全校验未通过（310000）：{errmsg}\n"
                    f"   检查机器人安全设置是否选了「自定义关键词」且关键词为「行业资讯」，"
                    f"或是否误开了加签/IP 白名单。"
                )
            raise RuntimeError(f"钉钉返回 errcode={errcode} errmsg={errmsg}")

        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            note = f"{type(exc).__name__}: {exc}"
            if note not in seen:
                seen.append(note)
            LOG.warning("钉钉推送失败（第 %d/%d 次）：%s",
                        attempt, DINGTALK_RETRIES + 1, exc)
            if attempt <= DINGTALK_RETRIES:
                time.sleep(DINGTALK_BACKOFF * attempt)

    raise RuntimeError("钉钉推送持续失败：" + " ；".join(seen))


# ---------------------------------------------------------------------------
# 失败告警
# ---------------------------------------------------------------------------
# 由 workflow 在**任一步失败**时调用（`if: failure()` → `python main.py --alert-failure`）。
# 为什么要有它：这个项目的主要失败模式是"静默地不推送"—— 定时任务被 GitHub 丢弃、
# 密钥过期、余额耗尽，表现都是"群里这周没消息"，而没人会为此收到任何通知。
# 告警把"没消息"变成一个主动发出来的消息。
#
# ⚠️ 它和提交步骤的 `if: always()` 是两回事，别混为一谈（后者被明令禁止，理由见
# weekly.yml 里那段注释：会在推送失败时也提交台账，把没送达读者的条目永久标记成已推送）。
# 这一步**不写任何文件、不碰台账、不 commit**，只发一条消息。

# workflow 里每个 step 的 id → 人话。**改 weekly.yml 的步骤时要同步改这里。**
# 漏改不会报错：下面用 `_STEP_LABELS.get(id, id)`，会退化成打印裸 id ——
# 信息少一点，但仍然指得动。**刻意不做成"两边必须一致否则报错"**：
# 告警本身不应该有失败的可能。
_STEP_LABELS = {
    "checkout": "拉取代码",
    "python": "安装 Python",
    "guard": "密钥文件守卫（检查 Key 有没有被误跟踪）",
    "deps": "安装依赖",
    "run": "运行 main.py（检索 + 撰写 + 推送）",
    "commit": "提交台账与站点",
}


def build_failure_alert() -> str:
    """拼出失败告警的正文。信息全部来自环境变量，不查任何接口、不读 Key。"""
    # GITHUB_* 是 Actions 默认注入的环境变量；STEP_* 由 workflow 那一步显式传入。
    # 取不到就留空 —— 告警宁可少一行信息，也不能因为拼字符串而抛异常。
    failed = [
        _STEP_LABELS.get(step_id, step_id)
        for step_id in _STEP_LABELS
        # 只列真出问题的：成功的不提，**跳过的也不提**（失败之后的下游步骤
        # outcome 就是 skipped，列出来会让"哪一步挂了"变成一长串噪声）。
        if (os.environ.get(f"STEP_{step_id.upper()}") or "") not in {"", "success", "skipped"}
    ]

    sha = (os.environ.get("GITHUB_SHA") or "")[:7]
    event = os.environ.get("GITHUB_EVENT_NAME") or ""
    trigger = {"schedule": "定时", "workflow_dispatch": "手动触发"}.get(event, event or "未知")
    run_url = "{}/{}/actions/runs/{}".format(
        os.environ.get("GITHUB_SERVER_URL") or "",
        os.environ.get("GITHUB_REPOSITORY") or "",
        os.environ.get("GITHUB_RUN_ID") or "",
    )

    lines = [
        f"{DINGTALK_KEYWORD} ⚠️ 周报推送失败",
        "",
        "**失败于**：" + ("、".join(failed) if failed else "（没能定位到具体步骤，看日志）"),
        f"时间：{datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M')}（北京）",
        f"提交：{sha} ｜ 触发：{trigger}",
    ]
    if run_url.startswith("http"):
        lines += ["", f"👉 [查看日志 / 手动重跑]({run_url})"]
    lines += [
        "",
        "台账没提交，所以修好后重跑不会漏内容；"
        "若群里已经收到过这一期，重跑会再发一遍，忽略即可。",
    ]
    return "\n".join(lines)


def alert_failure() -> int:
    """失败告警的入口。**刻意绕开 load_config()。**

    ⚠️ 为什么不能走 load_config()：失败的原因本身可能就是"密钥没配好"或
    "API Key 失效了"。而 load_config 缺变量就是 sys.exit —— 于是最需要告警的那次
    失败，恰恰是告警发不出去的那次。所以这里只认 DINGTALK_WEBHOOK 一个变量。
    """
    webhook = (os.environ.get("DINGTALK_WEBHOOK") or "").strip()
    if not webhook.startswith("https://oapi.dingtalk.com/"):
        # 非 0 退出：job 本来就红了，这里再红一次不增加负担，但 ::error:: 会以
        # 注解形式出现在 Actions 摘要顶部 —— 明确告诉你"这次连告警都没发出去"。
        print("::error::失败告警未能发出：DINGTALK_WEBHOOK 未配置或格式不对", file=sys.stderr)
        return 1
    text = build_failure_alert()
    LOG.info("正在发送失败告警")
    send_dingtalk(webhook, f"{DINGTALK_KEYWORD} 周报推送失败", text)
    LOG.info("失败告警已送达")
    return 0


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="华宝新能储能结构周报推送")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印 Markdown，不推送钉钉")
    parser.add_argument("--out", default="", metavar="PATH",
                        help="把生成的 Markdown 另存为文件（同时写一份同名 .html），"
                             "便于推送前审阅")
    parser.add_argument("--rebuild", action="store_true",
                        help="只从 docs/*.md 重建网页，不调 API、不推送、不写台账")
    parser.add_argument("--alert-failure", action="store_true",
                        help="只在 workflow 失败时由 CI 调用：往钉钉发一条失败告警。"
                             "不读 Key、不校验其它配置、不写任何文件")
    args = parser.parse_args()

    # Windows 上输出被重定向（管道 / VSCode 集成终端 / Git Bash）时，Python 会按
    # 本地 locale（cp936）编码 —— 终端按 UTF-8 解，中文全是乱码；遇到 GBK 覆盖不到的
    # 字符（㎡、≥、生僻字）还会直接抛 UnicodeEncodeError，让 --dry-run 崩在半路。
    # 而 --dry-run 正是推送前审阅报告的必经步骤，不能在这儿翻车。
    # errors="replace" 是兜底：宁可个别字显示成 ?，也不要整个流程挂掉。
    # 真正的 Windows 控制台本来就已是 utf-8（PEP 528），这一步对它是空操作。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # 被替换成不支持 reconfigure 的对象时静默跳过

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # 失败告警：放在**最前面**，连 load_config 都不走。理由见 alert_failure() 的 docstring
    # —— 最需要告警的那次失败（密钥没配好 / 失效），恰恰是 load_config 会先退出的那次。
    if args.alert_failure:
        return alert_failure()

    # 只重建站点：改了 CSS 想立刻看效果，不必等周一，也不花 API 额度。
    # 不需要任何环境变量，所以放在 load_config 之前。
    if args.rebuild:
        written = build_site(DOCS_DIR)
        LOG.info("已重建 %d 个网页 → %s", len(written), DOCS_DIR)
        return 0

    cfg = load_config(dry_run=args.dry_run)
    today = datetime.now(BEIJING_TZ)
    date_str = today.strftime("%Y-%m-%d")
    base_url = cfg["SITE_BASE_URL"]
    if not base_url:
        # ⚠️ 必须显式告警。否则一个配错的变量会让网页功能**静默退回**旧行为，
        # 而所有结构校验一个都不会响 —— 正是本项目最忌讳的那种失败。
        LOG.warning("SITE_BASE_URL 为空，网页功能已关闭，将退回推送全文（分段）")

    # ⚠️ 传 today.date()（naive date）而不是 today —— 台账里存的是 YYYY-MM-DD，
    # 带时区的 datetime 和 naive date 相减会抛 TypeError，第一天就崩。
    history = load_history(HISTORY_PATH, today.date())

    LOG.info("调用 OpenRouter（%s）检索并撰写中……共 3 次：板块一两轮 + 其余板块一轮",
             cfg["OPENROUTER_MODEL"])
    report, citations = build_report(cfg, today, history)
    LOG.info("报告生成完毕：%d 字，%d 个引用链接，%d 字节",
             len(report), len(citations), len(report.encode("utf-8")))

    if args.out:
        _write_text(Path(args.out), report)
        # 顺手写一份同名 .html —— 排版是这次改版的重点之一，只给 .md 看不出实际效果。
        preview = Path(args.out).with_suffix(".html")
        _write_text(preview, render_issue_page(
            report, date_str=date_str, prev_date="", next_date="",
            index_name=SITE_INDEX_NAME,
        ))
        LOG.info("已另存到 %s 与 %s（后者可直接用浏览器打开看排版）", args.out, preview)

    # 余额预警：读一眼账户余额，**只剩一期或更少**就在摘要末尾附一句。
    # ⚠️ 放在这里而不是 build_digest() 里 —— build_digest 是个纯函数（只吃 report），
    # 让它去发网络请求，就没法单独测它、也没法在不联网时复现出同一份摘要。
    # 查不到（None）就什么都不做，绝不因此中断这一期。
    balance = check_openrouter_balance(cfg["OPENROUTER_API_KEY"]) if base_url else None
    if balance is not None:
        # 余额每期都打一行日志（与阈值无关）：出问题时日志是唯一的事后依据，
        # 而余额是"这周为什么 402 了"最直接的答案。
        LOG.info("OpenRouter 账户余额 $%.5f，约合 %.1f 期（剩 ≤%d 期时会在摘要里提醒）",
                 balance, balance / OPENROUTER_COST_PER_RUN_USD, OPENROUTER_LOW_RUNS_LEFT)

    if base_url:
        # 新行为：群里只发摘要 + 链接，全文在网页上。
        # 余额不足时在末尾附一句 —— 摘要在 1KB 出头，加这一句远到不了 8KB 上限。
        messages = [build_digest(report, today, base_url) + _low_balance_note(balance)]
    else:
        # 退回旧行为：推送全文（分段）。这条路径是 SITE_BASE_URL 为空时的兜底，
        # plan_messages 因此不能删。
        # ⚠️ 这条路径上**不附**余额提醒：split_markdown 已经把每条切到 MAX_MESSAGE_BYTES，
        # 追加一句会让最后一条悄悄超出上限。余额提醒是附加信息，不值得为它在兜底路径上
        # 破掉"单条不超 8KB"这条已有的保证。
        messages = plan_messages(report)
    LOG.info("拆分为 %d 条消息，正文长度 %s 字节",
             len(messages), [len(m.encode("utf-8")) for m in messages])

    if args.dry_run:
        for index, text in enumerate(messages, start=1):
            print("\n" + "=" * 60
                  + f" 消息 {index}/{len(messages)}（群里会看到的）" + "=" * 60)
            print(text)
        print("=" * 60 + "\n")
        if base_url:
            # 群消息变短之后，只打印摘要就没法审阅内容了 —— 全文照旧打一遍。
            print("=" * 60 + " 报告全文（网页上会看到的内容）" + "=" * 60)
            print(report)
            print("=" * 60 + "\n")
        # dry-run 只读不写 —— 不推钉钉、不写台账、**也不写 docs/**。
        # docs/ 里落下的会是一个和正式产物同名、内容却不同的文件（每次跑模型输出都不一样），
        # 一旦被误提交，就是"一期从没推送过的报告"上了公网。
        LOG.info("dry-run 模式，未推送钉钉，未写入台账，也未生成网页")
        return 0

    title = f"{DINGTALK_KEYWORD} 储能结构周报（{date_str}）"
    for index, text in enumerate(messages, start=1):
        send_dingtalk(cfg["DINGTALK_WEBHOOK"], title, text)
        LOG.info("已推送第 %d/%d 条消息", index, len(messages))
        if index < len(messages):
            time.sleep(MESSAGE_INTERVAL)

    LOG.info("推送完成")

    # 站点落盘放在推送**成功之后**，与台账同一条铁律：磁盘上会被提交的东西，
    # 必须恰好是已经送达读者的东西。中途失败走的是 sys.exit（310000/410100），
    # SystemExit 不是 Exception，会直接穿过这里 —— 于是这一期不会上公网。
    # 顺序上站点在前、台账在后：任一步抛异常都会让这一期下周重发，而不是静默丢内容。
    if base_url:
        write_issue_source(DOCS_DIR, date_str, report)
        written = build_site(DOCS_DIR)
        LOG.info("网页已生成：%d 个文件 → %s", len(written), DOCS_DIR)
        LOG.info("本期链接（Pages 重建约需 30~60 秒）：%s/%s.html", base_url, date_str)

    # ⚠️ 台账**只在全部消息推送成功之后**才写。
    # 中途失败走的是 sys.exit（310000/410100 那两条路径），SystemExit 不是 Exception，
    # 会直接穿过这里 —— 于是台账不写、下次重跑会重发一遍。这是**刻意的**：
    # 重复一期总好过把没送达读者的条目标成"已推送"，那会让它永远回不来。
    entries = extract_entries(report)
    for entry in entries:
        entry["pushed"] = today.date().isoformat()
    save_history(HISTORY_PATH, history + entries)
    LOG.info("台账已更新：新增 %d 条，累计 %d 条 → %s",
             len(entries), len(history) + len(entries), HISTORY_PATH.name)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # fail-loudly：宁可群里收不到消息、你去查日志，也不要静默失败几周后才发现。
        LOG.error("执行失败：%s", exc)
        raise

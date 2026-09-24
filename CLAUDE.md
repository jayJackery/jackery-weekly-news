# CLAUDE.md

本文件为在本目录工作的 Claude 会话提供上下文。改动代码前请先读完「硬性约束」一节。

## 项目是什么

华宝新能（Jackery）**储能结构工程师**的每周行业情报自动推送。

每周一北京时间 09:00，GitHub Actions 运行 `main.py`：Tavily 中英双语检索 → DeepSeek 提炼归类
→ 本地渲染 Markdown → 推送到钉钉群 → 更新去重台账。

```
Tavily 检索 → 归一化去重 → 剔除历史 → DeepSeek 提炼为 JSON → 校验 → Python 渲染 Markdown
                                                                        → 钉钉推送 → 回写 history
```

## 文件职责

| 文件 | 职责 |
|---|---|
| `main.py` | 全部逻辑。单文件，未拆包 —— 项目规模不足以拆，单文件更便于直接读改 |
| `history_urls.json` | 已推送 URL 台账。**只在成功推送后更新**，由 Actions 自动 commit 回仓库 |
| `Key` | 明文密钥文件。**只读，永不入仓，永不把内容打印或复制到任何地方** |
| `.gitignore` | 挡住 `Key` / `.env` / `*.key` |
| `.github/workflows/weekly_news.yml` | 定时任务 + 手动触发 + 回写台账 |
| `README.md` | 面向同事的部署与使用说明 |

`main.py` 内部分区（按文件顺序）：配置常量 → 环境变量校验 → URL 归一化 → history 读写
→ Tavily 检索 → 大模型提炼 → Markdown 渲染 → 钉钉推送 → `main()` 主流程。

## 常用命令

```bash
pip install -r requirements.txt

python main.py --dry-run     # 只打印 Markdown，不推送钉钉、不写台账（推荐先用这个）
python main.py --limit 2     # 只跑前 2 条查询，省额度、快
python main.py               # 完整流程

python main.py --dry-run --limit 1   # 最快的冒烟测试
```

看 Actions 日志：仓库页面 → Actions → Weekly Industry News → 选一次运行。

## 硬性约束（改动时不可破坏）

这些约束各自对应一个真实的失败模式，不是风格偏好：

1. **`[行业资讯]` 必须留在 `markdown.text` 正文里。** 钉钉自定义关键词校验的是正文，
   官方文档从未说明 title 是否参与校验，社区反馈只放 title 会被 310000 拒收。
   拆分成多条消息时，**每条都要带这个关键词**，否则第二条起全部被拦。
2. **三个分类的名称与顺序固定**，改动需同步修改 `main.py` 顶部的 `CATEGORIES` 常量和 `SYSTEM_PROMPT`。
3. **三个分类的渲染方式不同，不要图省事统一成一种**（`Digest` 的数据结构就为此分了叉）：
   - 【竞品与市场动态】：逐条展开，每条 = 粗体标题 + `结构视角` + 原文链接。
     `对标借鉴` 是**可选**的第二行：能对上华宝产品线就写对标 + 借鉴点（只能引用
     `JACKERY_PRODUCTS` 里的产品线），对不上但行业形态变化对结构设计有普适启示就写宏观借鉴，
     两者都不成立就留空 —— 渲染时该行自动消失。**不要为了让每条都齐整而强迫模型硬凑，
     硬凑的对标比没有对标更糟。**
   - 【结构、材料与防护技术】：逐条展开，每条 = 粗体标题 + `结构视角` + 原文链接。
   - 【法规标准与出海动态】：**刻意不逐条列**，只渲染成**一整段综述**，底部最多挂
     `MAX_REGULATION_SOURCES` 条溯源链接。这是使用者的明确要求 —— 他不会一条条点开法规新闻，
     要的是"这周监管面变了什么、对我们意味着什么"。**不要"改进"成条目化列表。**
4. **顶部要有"本周速览"**（`highlights`，三条一句话结论），分类标题要带条数。
   整期偏长，速览是让读者能快速判断"这周值不值得细读"的唯一入口，去掉它读者就没耐心了。
   **速览必须与正文一致**：`consistent_highlights()` 会把指向空小节的速览条目丢掉。
   实测模型会写出「法规：欧洲多国放开阳台光伏」而正文法规综述返回空串 ——
   速览承诺了、正文没有，读起来像坏了。**不要去掉这层过滤。**
5. **`history_urls.json` 只在成功推送后更新**，且只记录**真正推送出去的** URL。
   被模型丢弃、超出条数上限、或拆消息时被截断的链接都不能记 —— 否则它们下周不会再出现，
   等于永久丢失。
6. **fail-loudly**：任何异常都要非 0 退出，让 Actions 变红。宁可群里收不到消息、
   你去查日志，也不要静默失败导致几周后才发现。
   **但要注意区分两种"空"**：模型输出结构损坏（`categories` 缺失/类型不对）是**真错误**，要退出码 1；
   模型把全部候选判为无关是**合法结果**（检索命中一堆垃圾时就会这样），属于"本周无相关资讯"，
   要发提示消息并以 0 退出。早期版本把后者也当错误，导致检索质量差的那周 Actions 无谓变红。
   同理，法规综述里的"本期无"是提示词约定的占位词，`Digest.is_empty()` 要把这种
   "形式上有字、实质没内容"的情况也判成空。
7. **密钥只从环境变量读**，不得写进代码、注释、日志、异常信息或 README。
   `Key` 文件内容不得被读取后输出。
8. **URL 白名单校验不能去掉**。模型会编造链接，`validate_digest()` 里的候选集比对是唯一的防线。

## 已知陷阱（踩过的坑，别再踩一遍）

**Tavily**
- **查询词写法对召回质量的影响极大，中文尤其明显。** 实测：关键词堆砌的长查询
  （如"便携储能 户外电源 阳台储能 竞品 新品 结构 2026"）配 `topic="news"` 会返回
  驱动之家日榜页、淘宝规则页甚至赌博站，基本不可用；改成自然语言的短查询
  （"便携式储能电源 新品发布 行业动态"）配 `topic="general"` 后才稳定命中厂商新品、
  专利、年报等有效信息。**改 `QUERIES` 后务必先 `--dry-run` 看实际召回质量，不要凭感觉写。**
- **中文技术类查询要配 `include_domains` 定向行业媒体**，否则会跑偏到汽车、消费电子
  等无关领域。定向清单见 `CN_INDUSTRY_DOMAINS`。
- `include_domains` 的默认模式在 SDK 改版后**不再是"仅限这些域名"**，实测有时仍会返回
  列表外的结果，不要把它当作强保证。
- `days` 参数**已从全部现行官方文档移除**，但 SDK 签名里还留着 —— 传了可能被静默忽略，
  导致"以为只取近 7 天、实际混进旧闻"。用 `time_range="week"`。
- **API key 为 None 时不报错**：SDK 的 `MissingAPIKeyError` 定义了但源码中从未 raise，
  实际会静默降级成匿名 keyless 模式，表现为一堆限流报错。所以 `load_config()` 里
  必须显式校验非空。
- `ForbiddenError` 和 `tavily.errors.TimeoutError` **不在 `tavily` 顶层导出**，
  必须 `from tavily.errors import ...`。且它覆盖了内置 `TimeoutError`。
- `results` 键永远存在（SDK 用 `setdefault` 兜底），但要按空列表处理。
- `published_date` 是 beta 字段，可能为 `None`。
- `timeout` 参数被 SDK 硬编码上限 120 秒（`min(timeout, 120)`），调大无效。

**钉钉**
- **限流错误码是 `410100`**（不是常见的 130101 猜测）。官方限制每机器人 20 条/分钟，
  **超限直接封 10 分钟**，不是简单丢弃。
- **`310000` 是合并安全错误码**：关键词不匹配 / timestamp 无效 / 签名不匹配 / IP 不在白名单
  四种失败共用它，靠 `errmsg` 区分。日志必须打 errmsg。
- **正文长度上限官方没有任何明文规定**（流传的 20000 字节查无出处）。所以按 UTF-8 字节数
  主动截断到 8KB，不赌这个数字。注意中文一字 3 字节，字符数 ≠ 字节数。
- **HTTP 200 不代表成功**，必须检查 `errcode == 0`（值可能是字符串 `"0"`，用 `int()` 转）。
- GitHub 托管 runner 出口 IP 不固定（`api.github.com/meta` 有 7000+ 个 CIDR 段），
  **IP 白名单模式不可用**，只能用自定义关键词或加签。本项目用关键词。

**GitHub Actions**
- cron 是 **UTC**。`0 1 * * 0` = 北京周一 09:00。
- **`permissions:` 一旦声明，未列出的 scope 全部变 `none`**，`contents: write` 必须显式写。
- `actions/checkout` 的 `persist-credentials` **默认 `true`**，正是为 push 设计的，
  改成 `false` 反而推不上去。
- **`GITHUB_TOKEN` 无权修改 `.github/workflows/` 下的文件**，所以只回写 `history_urls.json`，
  不要让脚本尝试改 workflow 自身。
- `actions/setup-python@v7` **移除了 `pip-install` input**，依赖用独立的 `pip install` 步骤。
- 整点是 GitHub Actions 的高负载时段，定时任务可能被延迟或丢弃。若推送时间不稳定，
  把 cron 分钟位从 `0` 改成 `7`。

**大模型**
- **`deepseek-chat` 这个模型 id 已经失效**（2026-09 实测该端点只提供 `deepseek-flash` 和
  `deepseek-v4-pro`）。默认值定为 `deepseek-flash`。改 `OPENAI_MODEL` 前先调
  `/models` 端点确认 id 还在，否则每次调用都会失败。
- DeepSeek **只支持 `response_format={"type":"json_object"}`，不支持 `json_schema`**。
- 第三方网关有**静默丢弃 `response_format`** 的已知问题，所以提示词里必须写明 JSON 结构，
  且解析、字段校验、URL 白名单校验三道防线都不能省。
- 提示词里必须**出现 "json" 字样**，否则部分网关直接报
  `messages must contain the word 'json'`。
- **提示词拦不住促销稿，必须靠 `JUNK_URL_SEGMENTS` 在 Python 里硬拦。** 实测提示词里
  明写"纯折扣稿一律丢弃"，模型仍会把 `cnet.com/deals/ecoflow-early-prime-day-deals`
  包装成一条像模像样的"可插拔电池模组"解读混进来。URL 路径特征比语义判断可靠得多。
  **改 `JUNK_URL_SEGMENTS` 时注意用路径分段匹配而不是子串匹配**，否则 `/wholesale-...`
  这类正常路径会被误伤。
- **但这份清单只该收促销页和聚合页，往里加厂商产品页会误伤真实情报。** 踩过的坑：
  曾经把 `/downloads/`、`/products/` 也加进去，结果那一周唯一一条大疆新品
  （`dji.com/cn/downloads/products/power-auro-2000-elite`）被拦掉了，
  使用者立刻发现"大疆的资讯怎么没了"。厂商自营页交给提示词判断就好。
- **Tavily 召回不稳定**：同一个查询词，连续几次运行返回的候选集并不一致
  （实测同一查询三次分别命中 39 / 34 / 34 条）。所以"这周少了某条"未必是代码问题，
  先看日志里候选数是否变化，不要急着改过滤规则。
- **模型的输出前后会打架**：速览里写了某分类的结论，该分类正文却返回空。
  速度 0.3 仍会复现。靠 `consistent_highlights()` 兜底，别指望提示词能约束住。
- `OpenAI()` 默认超时 10 分钟、自动重试 2 次，最坏能卡 30 分钟。已显式设成
  `timeout=60.0, max_retries=2`。

## 改动指南

| 想做什么 | 改哪里 |
|---|---|
| 增删搜索词 | `main.py` 顶部 `QUERIES`（**改完先 `--dry-run` 验召回质量**） |
| 屏蔽垃圾/社交站点 | `EXCLUDE_DOMAINS` |
| 屏蔽促销页/店铺页/下载页 | `JUNK_URL_SEGMENTS`（**按路径分段匹配，别改成子串匹配**） |
| 调整中文技术查询的定向媒体 | `CN_INDUSTRY_DOMAINS` |
| 调整每个分类的收录条数 | `MAX_ITEMS_PER_CATEGORY`（**法规类没有条数概念，它是一段话**） |
| 调整法规综述底部的链接条数 | `MAX_REGULATION_SOURCES` |
| 改"对标借鉴"能引用的产品线 | `JACKERY_PRODUCTS`（**产品线变动时必须同步，否则对标会失准**） |
| 改变分类口径 | `CATEGORIES` + `SYSTEM_PROMPT` 里的边界描述（两处要一致） |
| 改速览/分类标题的排版 | `render_header` / `render_section` / `render_regulation` |
| 换模型 | 环境变量 `OPENAI_MODEL`，不用改代码 |
| 调整单条消息长度上限 | `MAX_MESSAGE_BYTES` |
| 改推送时间 | `.github/workflows/weekly_news.yml` 的 cron（**记得算 UTC**） |

## 密钥

真实凭据在项目根目录的 `Key` 文件里，已被 `.gitignore` 挡住。

- **不要读 `Key` 的内容并输出**，除非用户明确要求且确有必要。
- **不要把 `Key` 的任何内容写进代码、README、CLAUDE.md、日志或 commit message。**
- 本地跑脚本需要把这些值导入环境变量，例如（在 bash 里逐条 `export`，不要落盘成脚本文件）。
- 新增环境变量的流程：`main.py` 的 `load_config()` → workflow 的 `env:` → README 的 Secrets 表，
  三处都要同步。

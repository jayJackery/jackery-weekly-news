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
3. **每条资讯必须同时有**：粗体标题 + 结构/行业视角解读 + 原文链接。三者缺一，这条资讯对结构工程师就没价值。
4. **`history_urls.json` 只在成功推送后更新**，且只记录**真正推送出去的** URL。
   被模型丢弃、超出条数上限、或拆消息时被截断的链接都不能记 —— 否则它们下周不会再出现，
   等于永久丢失。
5. **fail-loudly**：任何异常都要非 0 退出，让 Actions 变红。宁可群里收不到消息、
   你去查日志，也不要静默失败导致几周后才发现。
   **但要注意区分两种"空"**：模型输出结构损坏（`categories` 缺失/类型不对）是**真错误**，要退出码 1；
   模型把全部候选判为无关是**合法结果**（检索命中一堆垃圾时就会这样），属于"本周无相关资讯"，
   要发提示消息并以 0 退出。早期版本把后者也当错误，导致检索质量差的那周 Actions 无谓变红。
6. **密钥只从环境变量读**，不得写进代码、注释、日志、异常信息或 README。
   `Key` 文件内容不得被读取后输出。
7. **URL 白名单校验不能去掉**。模型会编造链接，`validate_digest()` 里的候选集比对是唯一的防线。

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
- DeepSeek **只支持 `response_format={"type":"json_object"}`，不支持 `json_schema`**。
- 第三方网关有**静默丢弃 `response_format`** 的已知问题，所以提示词里必须写明 JSON 结构，
  且解析、字段校验、URL 白名单校验三道防线都不能省。
- 提示词里必须**出现 "json" 字样**，否则部分网关直接报
  `messages must contain the word 'json'`。
- `OpenAI()` 默认超时 10 分钟、自动重试 2 次，最坏能卡 30 分钟。已显式设成
  `timeout=60.0, max_retries=2`。

## 改动指南

| 想做什么 | 改哪里 |
|---|---|
| 增删搜索词 | `main.py` 顶部 `QUERIES`（**改完先 `--dry-run` 验召回质量**） |
| 屏蔽垃圾/社交站点 | `EXCLUDE_DOMAINS` |
| 调整中文技术查询的定向媒体 | `CN_INDUSTRY_DOMAINS` |
| 调整每个分类的收录条数 | `MAX_ITEMS_PER_CATEGORY` |
| 改变分类口径 | `CATEGORIES` + `SYSTEM_PROMPT` 里的边界描述（两处要一致） |
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

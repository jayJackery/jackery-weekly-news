# 储能结构行业资讯自动推送

面向华宝新能（Jackery）储能结构工程师的每周行业情报机器人。

每周一北京时间 **09:30** 自动运行：经 **OpenRouter** 调用 `perplexity/sonar-pro-search`
联网检索近 **14 天**全球便携储能、户用与阳台储能、电池材料、安规政策的硬件工程动态，
撰写成五个板块的 Markdown 周报，**发布到网页**，往钉钉群推一条**摘要 + 链接**，
并把本期条目的链接回写台账（用于下周去重）。

## 推送效果

### 一、群里收到的是一条摘要

不再推全文 —— 一份 20KB 的报告切成三四条刷在群里，读者抓不到重点，刷过去也不好回看。
现在群里只有一条：

```markdown
[行业资讯] 储能结构周报（2026-10-12）

本期 15 条 ｜ 覆盖 2026-09-28 ~ 2026-10-12

**一、便携&阳台储能竞品动态**
· **Anker SOLIX** —— SOLIX S5000 将便携电源推向可移动家庭备电设备
· **Anker SOLIX** —— Solarbank Max 将阳台储能扩展为家庭级模块化系统

**二、户用&工商业储能与大机动态**
· **AuroraCell** —— 9.7 kWh 钠离子住宅电池进入 48 V 模块化路线
· **Fox ESS** —— Power Beast 用堆叠式高压电池覆盖 28 kWh 至近 1 MWh

**三、电池与材料技术突破**
· **AuroraCell** —— NCO 钠离子住宅电池把宽温与长循环作为结构约束
· **华致能源** —— 587 Ah 大电芯向工商业柜渗透，液冷替代风道维护

**四、安规与政策大事件**
· 北美 ｜ 欧洲 ｜ 日本

**五、对华宝新能（Jackery）结构与产品定义的启发**
· 3 点结构建议（详见全文）

📄 [本期全文](https://jayJackery.github.io/jackery-weekly-news/2026-10-12.html)
📚 [往期归档](https://jayJackery.github.io/jackery-weekly-news/)
```

> 上面是 2026-10-12 那期的真实输出（只此一处示例，每期内容不同）。

板块一~三各取最多 2 条头条；板块四列出本周期真正有内容的地区；板块五固定一行。
**末行同时给归档链接** —— 万一当期页面因提交失败没发出去，读者至少能落到一个可用的索引上。

### 二、全文在网页上

点第一个链接进当期页面。每个条目固定四段：**标题**（`### 序号. 厂商 —— 一句话`）、
**分点正文**、**来源**行、**特点**句（一句话判断）。序号在每个板块内从 1 重排。
板块四按购买地区分成 `**北美**` / `**欧洲**` / `**日本**` 三组，没有动态的地区直接省略整行。

网页比群消息多几件事：

- **两个视图**：图文版 / 纯文字版，页面顶部一键切换。纯文字版就是原样的 Markdown 排版，
  给只想要密集文字的人。切换只用 CSS（`radio` + `~`），**没有 JavaScript**。
- **配色切换**：右上角按钮在深色 / 浅色之间切，选择记在浏览器本地。
  没点过按钮时跟随系统设置。
- **左侧固定目录**：窗口够宽（≥1320px）时，本期目录固定在页面左边，读到哪儿都能直接
  跳到任意板块，滚动时一直停在原地。窗口窄了会自动退回正文顶部的那份目录 ——
  两种宽度下**都有一份目录可用**，不会出现手机上没目录可点的情况。
  点目录跳过去后，落地的那一节会描一圈橙边，方便确认自己跳到了哪里。
- **上/下一期导航**。
- 归档首页 `https://jayJackery.github.io/jackery-weekly-news/` 按日期倒序列出所有往期，
  是**固定入口** —— 群消息会被后续聊天顶掉，这个不会。

五个板块：

| 板块 | 关注点 |
|---|---|
| 一、便携&阳台储能竞品动态 | 新品形态、体积/重量变化%、防护等级、盲插/堆叠架构、价格 |
| 二、户用&工商业储能与大机动态 | 高压架构、构网型技术、液冷/风冷热管理如何集成进结构 |
| 三、电池与材料技术突破 | 新电芯化学、阻燃/隔热/轻量化材料、膨胀力对 Pack 结构的隐患；**结构件材料**：钣金（冲压/折弯/焊接/表面处理）、塑胶（阻燃 PC/ABS、注塑、结构发泡）等的牌号与工艺进展 |
| 四、安规与政策大事件 | 按购买地区（**北美／欧洲／日本**）分组：UL 2743、欧洲阳台/户储规范、认证与关税、供应链，以及**安装与维护要求**（持证电工、检修通道、维护记录、拆解回收） |
| 五、对华宝新能（Jackery）结构与产品定义的启发 | 从 Pack 集成度、散热风道、新材料工艺给出 3 点硬件建议 |

> 报告由 Perplexity 模型直接撰写 Markdown（带原始网页链接），本地只做关键词校验、渲染网页
> 与抽取摘要。摘要 1KB 出头，**不会触发分段**；只有把网页功能关掉（`SITE_BASE_URL=off`）
> 退回推送全文时，才会有 8KB 上限、多条消息、每条都带 `[行业资讯]` 关键词那一套。
>
> ⚠️ 经 OpenRouter 调用时，**"只要近 14 天"只由提示词约束，没有 API 层的硬保证**
> （`search_recency_filter` 在 OpenRouter 上不受支持）。偶尔混进更早的旧闻属已知行为，
> 见下文《报告里混进了更早的旧闻？》。
>
> **促销、折扣、优惠类文章会被自动剔除。** 那类文章里容量和价格都是真数字，但讲的不是
> 产品和结构，对结构工程师没有价值。判别有两条：链接命中促销特征（`/sale`、`/deal`、
> `-30-off`、`prime-day` 等），或者模型自己写出了"该条信息属于销售活动……不将其作为新品
> 处理"这类否定 —— 命中任一即整条删除。剔除记录打在 Actions 日志的 WARNING 里。
>
> **本期已经推送过的内容，下周不会再推一遍。** 脚本把每期条目的链接记在
> `pushed_history.json` 里（保留 60 天），下周生成时既会把上期标题列进提示词让模型避开，
> 也有一道本地兜底会把链接全在上期出现过的条目整条删掉。同一件事若有了**新进展**
> （新增披露尺寸/重量/IP 等级、新的结构改型），仍会以新链接重新报道。

## 目录结构

```
.
├── main.py                    # 全部逻辑：调用 OpenRouter → 校验 → 渲染网页 → 推摘要 → 回写台账
├── requirements.txt           # 只有一个依赖：requests
├── Key                        # 本机明文密钥（已被 .gitignore 挡住，绝不入仓）
├── example_report.md          # 排版参考样例
├── pushed_history.json        # 跨周去重台账，由 workflow 自动提交，不要手改
├── docs/                      # GitHub Pages 站点根，由 workflow 自动提交
│   ├── .nojekyll              # 关掉 Jekyll（手写一次，运行时永不重写）
│   ├── index.html             # 归档首页，每次运行重建
│   ├── 2026-10-12.md          # 报告原文（真相）
│   └── 2026-10-12.html        # 渲染产物，从 .md 重建
├── CLAUDE.md                  # AI 协作指南
├── README.md
└── .github/workflows/weekly.yml
```

⚠️ **站点目录必须叫 `docs/`，不能改成 `reports/` 之类。** GitHub Pages 的
"Deploy from a branch" 只提供 `/ (root)` 和 `/docs` 两个选项；换成别的名字就只能选
`/ (root)`，那会把**整个仓库**当网站发布 —— `main.py`、`CLAUDE.md`、这份 README
全都变成输网址就能下载的文件。

⚠️ **`docs/` 里绝不能出现生成时间戳或版本号。** 一旦有字段每次都变，工作区就永远是脏的，
workflow 最后那步 `git rebase` 会每周把 job 打红。

---

## 网页与归档

### 站点是怎么发布的

`main.py` 每次运行会**全量重建** `docs/`：写当期 `.md`（逐字节就是报告原文），
再从所有 `.md` 重新渲染 `.html` 和归档首页。幂等、廉价（一周约 40KB），
好处是**改了网页模板能追溯修好所有历史期**。

发布靠 GitHub Pages 的 **Deploy from a branch**，源选 `main` 分支的 `/docs` 目录。
不需要任何构建步骤 —— HTML 是 `main.py` 自己渲染的，`.nojekyll` 关掉了 Jekyll。

### 配置 Pages（三步，只做一次）

> ⚠️ **先确认仓库可见性。** GitHub **免费计划下私有仓库发不了 Pages**，
> 需要 Pro/Team/Enterprise，或者把仓库设为公开。若仓库是私有的，
> Settings → 最底 **Danger Zone** → **Change repository visibility** 改成 public。
> **这一步不可逆** —— 一旦公开会被搜索引擎和镜像站抓取，之后转回私有也收不回来。

1. 仓库 → **Settings** → 左侧栏 **Pages**
2. **Source** 选 `Deploy from a branch`
3. **Branch** 选 `main`，右边文件夹选 **`/docs`** → **Save**
   - ⚠️ **文件夹必须选 `/docs`，不要选 `/ (root)`** —— 选 root 会把整个仓库当网站发布

存完页面顶部会显示站点地址。**首次构建要 30~60 秒**，之后每次提交约 30 秒重建。

### 归档结构

```
https://jayJackery.github.io/jackery-weekly-news/             # 归档首页（固定入口）
https://jayJackery.github.io/jackery-weekly-news/2026-10-10.html   # 单期页面
https://jayJackery.github.io/jackery-weekly-news/2026-10-10.md     # 单期原文（纯文本）
```

`.md` 是真相、`.html` 是产物，两者都提交。将来改样式可以直接从 `.md` 重渲染，
不用重跑模型、不花额度。

### 站点地址从哪来

默认值是 `main.py` 顶部的 `DEFAULT_SITE_BASE_URL`。要覆盖它，配一个**仓库变量**
（**不是 Secret** —— 它不是密钥）：Settings → Secrets and variables → Actions →
**Variables** 标签页 → New repository variable，名字 `SITE_BASE_URL`，值填站点根
（末尾不带斜杠）。

| 想做什么 | 怎么设 |
|---|---|
| 用默认地址 | 什么都不用配 |
| 换成自定义域名或别的仓库 | 变量 `SITE_BASE_URL` = `https://your.site/path` |
| **关掉网页功能**，退回推全文 | 变量 `SITE_BASE_URL` = `off` |

⚠️ **留空不等于关闭。** 仓库变量没配时它会展开成空串，而脚本把空串当"用默认值"。
真要关闭必须显式写 `off`（`none` / `false` / `0` 也可以）。

---

## 部署步骤

> **配置项一共两处**：下面的 Secrets（密钥，必做），以及 **GitHub Pages**
> （发布网页，必做 —— 见《配置 Pages》那三步；不配的话群里那条消息里的两个链接会是 404）。
> 站点地址不是密钥，走的是**仓库变量**而不是 Secret，默认值已经写在代码里，
> 通常不需要配。

### 1. 配置 GitHub Secrets

仓库 → **Settings** → **Secrets and variables** → **Actions**
→ **New repository secret**，添加两个：

| Secret 名 | 值从哪里来 |
|---|---|
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) 生成的 API Key，`sk-or-v1-` 开头 |
| `DINGTALK_WEBHOOK` | 见下一步，**必须是 `https://oapi.dingtalk.com/robot/send?access_token=...`** |

⚠️ Secrets 名字**区分大小写**，拼错会表现为"缺变量"报错。

> 旧名 `PERPLEXITY_API_KEY` 仍被兼容（脚本按 `OPENROUTER_API_KEY` → `PERPLEXITY_API_KEY`
> 的顺序回退），所以只配了旧名也能跑。但新配置请统一用 `OPENROUTER_API_KEY`。

⚠️ `DINGTALK_WEBHOOK` **千万不要填飞书（`feishu.cn`）的链接**，两者不通用。
脚本启动时会校验这个格式，填错会直接报错退出，而不是发出一条莫名失败的消息。

### 2. 创建钉钉机器人

1. 目标钉钉群 → 群设置 → 智能群助手 → 添加机器人 → **自定义**（通过 Webhook 接入）。
2. **安全设置勾选「自定义关键词」**，关键词填：`行业资讯`（四个字，不要带方括号）。
   - 不要选「IP 地址白名单」：GitHub 托管 runner 的出口 IP 不固定
     （`api.github.com/meta` 的 `actions` 字段有 7000+ 个 CIDR 段且在变动），白名单没法配。
   - 不要选「加签」：本脚本按关键词方案实现，不实现签名逻辑。
3. 复制生成的 Webhook 地址填进上面的 `DINGTALK_WEBHOOK` Secret。

### 3. 手动跑一次验证

仓库 → **Actions** → 左侧选 **Weekly Industry News** → 右侧 **Run workflow**。
跑完确认：

1. job 是绿色；
2. 钉钉群收到**一条**摘要；
3. 摘要里两个链接都能点开（⚠️ 消息发出后**等 1~2 分钟**再点，站点要时间重建）；
4. 归档页已收录这一期。

⚠️ **这会真的往群里发一条消息**，而且会占掉一期。不想提前发就跳过这步，等周一自动触发。

---

## 定时任务

```yaml
on:
  schedule:
    - cron: '30 1 * * 1'     # UTC 周一 01:30 = 北京时间周一 09:30
  workflow_dispatch:          # 手动触发
```

**cron 用的是 UTC 时间**：

| 你想要的北京时间 | 应写的 cron |
|---|---|
| **周一 09:30（本仓库当前设置）** | **`30 1 * * 1`** |
| 周一 09:00 | `0 1 * * 1` |
| 周五 18:00 | `0 10 * * 5` |

⚠️ 改推送时间要**同步改三处**：`.github/workflows/weekly.yml` 的 cron、
上面这张表、`CLAUDE.md`。漏改不会报错，只会让文档和实际行为对不上。
**日位比分钟位更容易写错** —— `0` 是周日、`1` 才是周一，改完用
[crontab.guru](https://crontab.guru) 核一遍。

> GitHub 官方提示：**每小时整点是 Actions 的高负载时段**，定时任务可能被延迟甚至丢弃。
> 若推送时间经常不准，把分钟位从 `0` 改成 `7` 之类的非整点值。

想临时补跑一次，用 `workflow_dispatch`（Run workflow 按钮），不用等下周。

---

## 本地运行

```bash
pip install -r requirements.txt
```

需要 Python ≥ 3.10。然后设置环境变量：

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=..."
```

这些值放在项目根目录的 `Key` 文件里（已被 `.gitignore` 挡住，**绝不入仓**）。

常用命令：

```bash
python main.py --dry-run              # 只打印摘要 + 全文，不推送、不写 docs/、不写台账
python main.py --dry-run --out r.md   # 顺便存成 r.md 和 r.html，后者用浏览器打开看网页排版
python main.py --rebuild              # 只从 docs/*.md 重建网页，不调 API、不推送、不写台账
python main.py                        # 完整流程，真的会发钉钉
```

- `--dry-run` 不需要 `DINGTALK_WEBHOOK` 也能跑，**只读**：不推钉钉、不写 `docs/`、不写台账。
- **`--rebuild` 不需要 API Key 也能跑**，不花额度。改完网页样式想立刻看效果时用它。
- `python main.py` 会真的发钉钉、写 `docs/`、写台账，**先用 `--dry-run` 看过再用**。

> ⚠️ Windows 的 GBK 控制台可能因为摘要里的 emoji 报 `UnicodeEncodeError`。
> 加 `PYTHONIOENCODING=utf-8` 即可（钉钉走 UTF-8 HTTP，不受影响，纯粹是本地控制台的问题）。

---

## 自定义

| 想改什么 | 改哪里 |
|---|---|
| 检索重点、板块口径、写作风格 | `main.py` 顶部的 `ROLE_AND_RULES`（三个提示词共用） |
| 条目排版（分点 / 来源行 / 特点句 / 序号） | `main.py` 顶部的 `ROLE_AND_RULES` 里的「条目排版」条，参照 `example_report.md`。⚠️ 板块一的两轮提示词里**写死了标题行格式**，改序号要一起改（见 `CLAUDE.md` 的改动指南） |
| 板块一收录哪些厂商 | `main.py` 顶部的 `SECTION1_VENDORS`（**Jackery 刻意不在清单里，别加回去** —— 加了模型就会把自家新品写进竞品板块；自家产品只在板块五出现） |
| 促销稿过滤规则 | `main.py` 顶部的 `PROMO_URL_TOKENS` / `SELF_DISQUALIFY_RE` 等常量 |
| 第五板块能引用的华宝产品线 | `main.py` 顶部的 `JACKERY_PRODUCTS`（**产品线变动时必须同步**） |
| 换模型（不用改代码） | 环境变量 `OPENROUTER_MODEL`，默认 `perplexity/sonar-pro-search` |
| 温度 / 正文长度上限 | `main.py` 顶部的 `OPENROUTER_TEMPERATURE` / `OPENROUTER_MAX_TOKENS`（**常量，不是环境变量**） |
| 检索时间窗（近 14 天） | `main.py` 顶部的 `WINDOW_DAYS`（**六处"近 N 天"措辞都从它插值，改一处即可；没有 API 层开关**） |
| 跨周去重的保留期 | `main.py` 顶部的 `HISTORY_KEEP_DAYS`（默认 60 天） |
| 单条消息字节上限 | `MAX_MESSAGE_BYTES`（只在关掉网页、退回推全文时才会用到） |
| 推送时间 | `.github/workflows/weekly.yml` 的 cron（**记得换算成 UTC**） |
| 网页站点地址 / 开关网页功能 | 仓库变量 `SITE_BASE_URL`（**`off` = 关闭并退回推全文**；留空 ≠ 关闭，见下文《网页与归档》） |
| 页面样式（配色、字号、卡片） | `main.py` 顶部的 `_PAGE_CSS`。⚠️ 它是**内联**进 HTML 的，**注释里不能出现 `</style>`**，否则会把样式块提前截断（有断言会拦住，见 `CLAUDE.md`） |
| 摘要里每个板块取几条头条 | `main.py` 顶部的 `build_digest()`（当前是板块一~三各最多 2 条） |
| 摘要里板块四怎么显示 | `_digest_regions()`（取 `**北美**` 这类独立粗体行） |

---

## 常见问题

**群里没收到消息？**

1. 看 Actions 页面最近一次运行。**红色 = 脚本报错**，日志里有完整 traceback。
2. **报 `310000`**：钉钉安全校验没过。这个错误码同时覆盖关键词不匹配、签名不匹配、
   IP 不在白名单等情况，看日志里的 `errmsg` 才能确定。最常见原因是机器人安全设置
   没选「自定义关键词」，或关键词不是 `行业资讯`。
3. **报 `410100`**：被钉钉限流了。官方限制每机器人 20 条/分钟，超限会**封 10 分钟**。
   改成推送摘要之后每期只发 1 条，**基本不会再触发**；只有关掉网页功能退回推全文
   （多条消息）时才需要留意这个错误码。
   ⚠️ **先看群里收到的是不是半份**：推送中途失败时台账不会写，直接重跑会把**已经发出去的
   那几条再发一遍**。正确做法是等 10 分钟后用一次 `workflow_dispatch` 重跑 ——
   重跑成功那次会把台账补上，下周就不会重复。重复一条总好过静默丢一期。
4. **提示变量缺失**：Secrets 名字拼错了，或没配。注意区分大小写。
5. **OpenRouter 报 401/403**：API Key 无效。
   **报 402**：OpenRouter 账户余额不足 —— 换个错误码，别按 key 失效去查。
   **报 400**：模型名不存在或参数不合法，看日志里带出的响应体。

**报告被拆成了好几条消息？**

默认**不会** —— 群里收到的摘要只有 1KB 出头，一条就够。如果你确实看到了多条，
说明网页功能被关掉了（仓库变量 `SITE_BASE_URL` 设成了 `off`），走的是退回路径：
那种模式下推的是全文，按 UTF-8 字节数截断在 8KB（中文一字 3 字节，字符数 ≠ 字节数），
官方对上限没有明文规定，所以主动截断不赌，报告偏长就会拆成多条，
**每条都带 `[行业资讯]` 关键词**（否则第二条起会被钉钉整条拒收）。

**网页链接打不开 / 返回 404？**

按这个顺序查：

1. **刚发完消息就点** —— 正常的。脚本先把消息发到群里，**之后**才写 `docs/` 并提交，
   提交后 Pages 还要 30~60 秒重建。所以消息发出后的 **1~2 分钟内链接可能还是 404**。
   这是刻意的：宁可链接晚几十秒可用，也不让"从没送达读者的一期"提前上公网。
2. **超过 2 分钟还是 404** —— 去 Actions 看 `Commit history ledger and site` 那步。
   若是 `::error::台账推送连续 3 次失败` 或 `git push` 403，说明站点没提交上去，
   修法见上面《台账没提交上去会怎样？》。**这时消息已经发出去了，但页面不存在** ——
   读者只能靠摘要里的归档链接落到索引页。
3. **归档页能开、单期页打不开** —— 看提交里有没有 `docs/<日期>.html`。
4. **整个站点都 404** —— Pages 没配，或配置被重置了。回《配置 Pages》那三步。
5. **站点能开但样式全无（纯黑字白底）** —— 说明 HTML 渲染没问题、CSS 没生效。
   大概率是 `_PAGE_CSS` 里的注释写了 `</style>`，把样式块提前截断了。
   本地跑 `python main.py --rebuild` 就会看到断言报错。

**能确认发布源没有配成 `/ (root)` 吗？**

可以，用浏览器或 `curl` 试一下这几个地址，**都应该是 404**：

```
https://jayJackery.github.io/jackery-weekly-news/main.py
https://jayJackery.github.io/jackery-weekly-news/CLAUDE.md
https://jayJackery.github.io/jackery-weekly-news/pushed_history.json
```

**任何一个返回 200，就说明 Pages 的文件夹选成了 `/ (root)`** —— 整个仓库正在被公开
下载，立刻回 Settings → Pages 改成 `/docs`。（仓库本身是公开的，改回来即可，
但被爬走的部分收不回来。）

**周报之间会重复吗？**

不会。每期推送成功后，脚本会把本期条目写进仓库根目录的 `pushed_history.json`，
workflow 自动提交回去。下一期生成时：

1. 提示词里会列出**上期的条目标题**，明确要求换来源、换链接也不算新动态；
2. 本地还有一道兜底 —— 若某个条目的**全部链接**都出现在台账里，整条删掉。

台账保留 **60 天**，所以不必担心窗口挪动导致的漏网。同一件事若出现**新进展**
（新增披露了尺寸/重量/IP 等级、有了新的结构改型），仍会被报道，但必须引用**新的**
文章链接。

⚠️ **不要手改 `pushed_history.json`。** 它由脚本读写，格式不对会让任务直接失败退出
（这是刻意的 —— 静默失效的去重比没有去重更糟，因为没人会发现）。想重置就整份清空成
`{"version": 1, "entries": []}`。

**台账没提交上去会怎样？**

那一期下周会重发一遍。这比反过来好 —— 脚本**只在全部消息推送成功之后**才写台账，
所以不会出现"没送达读者却被标记成已推送、从此再也不提"的情况。

如果 Actions 日志里出现 `::error::台账推送连续 3 次失败`，或者 `git push` 报 403，
先检查仓库的 **Settings → Actions → General → Workflow permissions**：
若是 "Read repository contents permission"，YAML 里写的 `contents: write` 会被忽略，
读改成 "Read and write permissions"。**这个问题的修法在仓库设置里，不在代码里。**

**报告里混进了 14 天以前的旧闻？**

这是**已知且暂时无解的行为**，不是配置错误。在 Perplexity 原生接口上，
`search_recency_filter: "week"` 能把检索窗口硬卡在近 7 天；但经 OpenRouter 调用
`perplexity/sonar-pro-search` 时，该模型 `supported_parameters` 里**没有**这个参数
（也没有 `return_citations`），传了会被忽略甚至报错。所以现在唯一的时间约束是提示词 ——
`build_user_prompt()` 会把"今天日期"和"近 14 天"的区间告诉模型，`ROLE_AND_RULES` 里也要求
"只写近 14 天"。**模型大体遵守，但不保证。**

> 补充：窗口本身曾经只有 **7 天**，那反而更容易出问题 —— 7 天太窄，五个板块摊薄检索预算后
> 经常凑不满，模型就往窗口外找。放宽到 14 天后它反而更愿意待在窗内。
> 改窗口要同时改 `WINDOW_DAYS` 和六处"近 N 天"的中文措辞（都从常量插值，见 `CLAUDE.md`）。

想彻底解决只有一条路：换回 Perplexity 原生接口
（`https://api.perplexity.ai/chat/completions`），恢复 `search_recency_filter="week"`
与 `return_citations=True`。

---

## 安全须知

> ⚠️ **本仓库是公开的**（免费计划下 Pages 需要公开仓库，见《配置 Pages》）。
> 所以仓库里的每一个文件、以及**全部提交历史**都是任何人都能读到的。
> 密钥不在这里 —— 它们只存在于 Actions Secrets 和本机的 `Key` 文件里。

- **`Key` 文件绝不入仓。** 它已在 `.gitignore` 里，workflow 里还有一道守卫：
  一旦发现 `Key` 被 git 跟踪就直接让 job 失败。任何时候都不要用 `git add -f Key` 绕过。
- **`git add` 只加 `pushed_history.json` 和 `docs` 这两个路径**，绝不用 `git add -A`
  或 `git add .`。`Key` 就躺在工作区里（虽被 gitignore 挡住），这是安全边界。
  workflow 的提交步骤还有一道**枚举式白名单断言**：暂存区里只允许出现
  `pushed_history.json`、`docs/index.html`、`docs/YYYY-MM-DD.{md,html}` 这四种路径，
  出现别的就硬失败。**不要把这道断言放宽**（详见 `CLAUDE.md`）。
- **不要把 `Key` 的内容粘贴到 issue、PR、聊天记录或代码注释里。**
- 一旦密钥曾经被提交过或粘贴到别处，就去对应平台后台**重新生成** ——
  从 git 历史里删掉文件并不能让已经泄露的密钥失效。
- **`docs/` 里的报告是公开可读的**，包含板块五（对华宝新能的结构与产品定义启发）。
  这是有意为之 —— 网页正是给同事看的。但要知道它是公网的，不要把只该内部传的东西写进报告。

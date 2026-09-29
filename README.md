# 储能结构行业资讯自动推送

面向华宝新能（Jackery）储能结构工程师的每周行业情报机器人。

每周一北京时间 09:00 自动运行：经 **OpenRouter** 调用 `perplexity/sonar-pro-search`
联网检索近 **14 天**全球便携储能、户用与阳台储能、电池材料、安规政策的硬件工程动态，
撰写成五个板块的 Markdown 周报，推送到钉钉群，并把本期条目的链接回写台账（用于下周去重）。

## 推送效果

```markdown
# [行业资讯] 储能结构周报（2026-09-24）

> 覆盖周期：2026-09-17 ~ 2026-09-24 ｜ 面向储能结构工程师

## 一、便携&阳台储能竞品动态

### Anker SOLIX —— 日本发布 S2000 便携电源
9月23日，Anker 日本正式发售 **Anker Solix S2000**（2,048Wh，LiFePO4 电芯），
相较前代体积缩小 **36%**、重量减轻 **14%**，售价 199,900 日元。…
（Impress Watch） [gizmodo](https://gizmodo.com/...)

## 二、户用&工商业储能与大机动态
...
## 三、电池与材料技术突破
...
## 四、安规与政策大事件
...
## 五、对华宝新能（Jackery）结构与产品定义的启发
...
```

五个板块：

| 板块 | 关注点 |
|---|---|
| 一、便携&阳台储能竞品动态 | 新品形态、体积/重量变化%、防护等级、盲插/堆叠架构、价格 |
| 二、户用&工商业储能与大机动态 | 高压架构、构网型技术、液冷/风冷热管理如何集成进结构 |
| 三、电池与材料技术突破 | 新电芯化学、阻燃/隔热/轻量化材料、膨胀力对 Pack 结构的隐患；**结构件材料**：钣金（冲压/折弯/焊接/表面处理）、塑胶（阻燃 PC/ABS、注塑、结构发泡）等的牌号与工艺进展 |
| 四、安规与政策大事件 | 按购买地区（**北美／欧洲／日本**）分组：UL 2743、欧洲阳台/户储规范、认证与关税、供应链，以及**安装与维护要求**（持证电工、检修通道、维护记录、拆解回收） |
| 五、对华宝新能（Jackery）结构与产品定义的启发 | 从 Pack 集成度、散热风道、新材料工艺给出 3 点硬件建议 |

> 报告由 Perplexity 模型直接撰写 Markdown（带原始网页链接），本地只做关键词校验与分段。
> 单条钉钉消息有 8KB 上限，报告偏长时会被自动拆成多条，**每条都带 `[行业资讯]` 关键词**。
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
├── main.py                    # 全部逻辑：调用 OpenRouter → 校验分段 → 推送钉钉 → 回写台账
├── requirements.txt           # 只有一个依赖：requests
├── Key                        # 本机明文密钥（已被 .gitignore 挡住，绝不入仓）
├── example_report.md          # 排版参考样例
├── pushed_history.json        # 跨周去重台账，由 workflow 自动提交，不要手改
├── CLAUDE.md                  # AI 协作指南
├── README.md
└── .github/workflows/weekly.yml
```

---

## 部署步骤

### 1. 配置 GitHub Secrets

**这是唯一必须做的配置。** 仓库 → **Settings** → **Secrets and variables** → **Actions**
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
跑完确认 job 是绿色、钉钉群收到周报。

---

## 定时任务

```yaml
on:
  schedule:
    - cron: '0 1 * * 1'      # UTC 周一 01:00 = 北京时间周一 09:00
  workflow_dispatch:          # 手动触发
```

**cron 用的是 UTC 时间**：

| 你想要的北京时间 | 应写的 cron |
|---|---|
| 周一 09:00 | `0 1 * * 1` |
| 周一 09:07 | `7 1 * * 1` |
| 周五 18:00 | `0 10 * * 5` |

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
python main.py --dry-run              # 只打印 Markdown，不推送 —— 先用这个
python main.py --dry-run --out r.md   # 顺便存成文件，方便在编辑器里细看
python main.py                        # 完整流程，真的会发钉钉
```

`--dry-run` 不需要 `DINGTALK_WEBHOOK` 也能跑。

---

## 自定义

| 想改什么 | 改哪里 |
|---|---|
| 检索重点、板块口径、写作风格 | `main.py` 顶部的 `ROLE_AND_RULES`（三个提示词共用） |
| 板块一收录哪些厂商 | `main.py` 顶部的 `SECTION1_VENDORS`（**Jackery 刻意不在清单里，别加回去** —— 加了模型就会把自家新品写进竞品板块；自家产品只在板块五出现） |
| 促销稿过滤规则 | `main.py` 顶部的 `PROMO_URL_TOKENS` / `SELF_DISQUALIFY_RE` 等常量 |
| 第五板块能引用的华宝产品线 | `main.py` 顶部的 `JACKERY_PRODUCTS`（**产品线变动时必须同步**） |
| 换模型（不用改代码） | 环境变量 `OPENROUTER_MODEL`，默认 `perplexity/sonar-pro-search` |
| 温度 / 正文长度上限 | `main.py` 顶部的 `OPENROUTER_TEMPERATURE` / `OPENROUTER_MAX_TOKENS`（**常量，不是环境变量**） |
| 检索时间窗（近 14 天） | `main.py` 顶部的 `WINDOW_DAYS`（**六处"近 N 天"措辞都从它插值，改一处即可；没有 API 层开关**） |
| 跨周去重的保留期 | `main.py` 顶部的 `HISTORY_KEEP_DAYS`（默认 60 天） |
| 单条消息字节上限 | `MAX_MESSAGE_BYTES` |
| 推送时间 | `.github/workflows/weekly.yml` 的 cron（**记得换算成 UTC**） |

---

## 常见问题

**群里没收到消息？**

1. 看 Actions 页面最近一次运行。**红色 = 脚本报错**，日志里有完整 traceback。
2. **报 `310000`**：钉钉安全校验没过。这个错误码同时覆盖关键词不匹配、签名不匹配、
   IP 不在白名单等情况，看日志里的 `errmsg` 才能确定。最常见原因是机器人安全设置
   没选「自定义关键词」，或关键词不是 `行业资讯`。
3. **报 `410100`**：被钉钉限流了。官方限制每机器人 20 条/分钟，超限会**封 10 分钟**。
   本期报告拆成多条发送时可能触发。
   ⚠️ **先看群里收到的是不是半份**：推送中途失败时台账不会写，直接重跑会把**已经发出去的
   那几条再发一遍**。正确做法是等 10 分钟后用一次 `workflow_dispatch` 重跑 ——
   重跑成功那次会把台账补上，下周就不会重复。重复一条总好过静默丢一期。
4. **提示变量缺失**：Secrets 名字拼错了，或没配。注意区分大小写。
5. **OpenRouter 报 401/403**：API Key 无效。
   **报 402**：OpenRouter 账户余额不足 —— 换个错误码，别按 key 失效去查。
   **报 400**：模型名不存在或参数不合法，看日志里带出的响应体。

**报告被拆成了好几条消息？**

单条钉钉消息正文按 UTF-8 字节数截断在 8KB（中文一字 3 字节，字符数 ≠ 字节数），
官方对上限没有明文规定，所以主动截断不赌。报告偏长就会拆成多条，
**每条都带 `[行业资讯]` 关键词**（否则第二条起会被钉钉整条拒收）。

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

- **`Key` 文件绝不入仓。** 它已在 `.gitignore` 里，workflow 里还有一道守卫：
  一旦发现 `Key` 被 git 跟踪就直接让 job 失败。任何时候都不要用 `git add -f Key` 绕过。
- **不要把 `Key` 的内容粘贴到 issue、PR、聊天记录或代码注释里。**
- 一旦密钥曾经被提交过或粘贴到别处，就去对应平台后台**重新生成** ——
  从 git 历史里删掉文件并不能让已经泄露的密钥失效。

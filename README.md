# 储能结构行业资讯自动推送

面向华宝新能（Jackery）储能结构工程师的每周行业情报机器人。

每周一北京时间 09:00 自动运行：中英双语检索行业资讯 → 大模型提炼归类 → 推送 Markdown 周报到钉钉群。
自带去重台账，同一条资讯不会推送第二次。

## 推送效果

```markdown
# [行业资讯] 储能结构周报（2026-09-24）

> 覆盖周期：2026-09-17 ~ 2026-09-24 ｜ 新增 8 条 ｜ 面向储能结构工程师

## 【竞品与市场动态】

**1. EcoFlow 发布新一代堆叠式户外电源，模组化设计成主流**

> 结构视角：由单体提手改为双侧内嵌把手 + 堆叠卡扣，外壳模具复杂度上升，
> 但换来了扩容灵活性 —— 值得关注其卡扣的插拔寿命与跌落工况下的保持力。

[阅读原文](https://example.com/ecoflow-xxx)

## 【结构、材料与防护技术】
...

## 【法规标准与出海动态】
...

—— 本消息由自动化脚本生成，检索源：Tavily
```

三个固定分类：

| 分类 | 收录范围 |
|---|---|
| 竞品与市场动态 | EcoFlow、Anker、Bluetti 及国内厂商的新品、形态创新、价格与渠道动作 |
| 结构、材料与防护技术 | 外壳防跌落、IP 防护、Pack 结构、热管理/风道、阻燃材料、工艺与装配 |
| 法规标准与出海动态 | UL 2743、欧洲阳台储能安装规范、各国认证与关税政策 |

## 目录结构

```
.
├── main.py                            # 全部逻辑：检索 → 提炼 → 推送 → 记录
├── requirements.txt
├── history_urls.json                  # 已推送 URL 台账，由 Actions 自动 commit 回仓库
├── Key                                # 本机明文密钥（已被 .gitignore 挡住，绝不入仓）
├── CLAUDE.md                          # AI 协作指南：硬性约束与已知陷阱
├── README.md
└── .github/workflows/weekly_news.yml  # 定时任务
```

---

## 部署步骤

### 1. 建仓库

建一个**私有仓库**，把本目录推上去。

> 私有仓库还有个附带好处：GitHub 有条规则是「公开仓库 60 天无活动会自动停用定时任务」。
> 本项目每周 commit 一次台账，通常足以保持活跃。

### 2. 配置 GitHub Secrets

仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，
逐个添加下面 4 个（第 5 个可选）：

| Secret 名 | 必需 | 值从哪里来 |
|---|---|---|
| `TAVILY_API_KEY` | ✅ | [app.tavily.com](https://app.tavily.com) 控制台，`tvly-` 开头 |
| `OPENAI_API_KEY` | ✅ | DeepSeek 平台的 `sk-` 开头密钥 |
| `OPENAI_BASE_URL` | ✅ | `https://api.deepseek.com/v1` |
| `DINGTALK_WEBHOOK` | ✅ | 见下一步，**必须是 `https://oapi.dingtalk.com/robot/send?access_token=...`** |
| `OPENAI_MODEL` | ❌ | 不填则默认 `deepseek-chat` |

⚠️ **`DINGTALK_WEBHOOK` 千万不要填飞书（`feishu.cn`）的链接**，两者不通用。
脚本启动时会校验这个格式，填错会直接报错退出而不是发出一条莫名失败的消息。

### 3. 创建钉钉机器人

1. 在目标钉钉群 → 群设置 → 智能群助手 → 添加机器人 → **自定义**（通过 Webhook 接入）。
2. **安全设置勾选「自定义关键词」**，关键词填：`行业资讯`（四个字，不要带方括号）。
   - 不要选「IP 地址白名单」：GitHub 托管 runner 的出口 IP 不固定
     （`api.github.com/meta` 的 `actions` 字段有 7000+ 个 CIDR 段且在变动），白名单根本没法配。
   - 不要选「加签」：本脚本按关键词方案实现，不实现签名逻辑。
3. 复制生成的 Webhook 地址（形如 `https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx`），
   填进上面的 `DINGTALK_WEBHOOK` Secret。

### 4. 手动跑一次验证

仓库 → **Actions** → 左侧选 **Weekly Industry News** → 右侧 **Run workflow** → 绿色按钮。

跑完后确认：job 是绿色、钉钉群收到周报、仓库里多了一个更新 `history_urls.json` 的 commit。

---

## 定时任务

```yaml
on:
  schedule:
    - cron: '0 1 * * 0'      # UTC 周日 01:00 = 北京时间周一 09:00
  workflow_dispatch:          # 手动触发
```

**cron 用的是 UTC 时间**，换算关系：

| 你想要的北京时间 | 应写的 cron |
|---|---|
| 周一 09:00 | `0 1 * * 0` |
| 周一 09:07 | `7 1 * * 0` |
| 周五 18:00 | `0 10 * * 5` |

> GitHub 官方提示：**每小时整点是 Actions 的高负载时段**，定时任务可能被延迟甚至丢弃。
> 如果发现推送时间经常不准，把分钟位从 `0` 改成 `7` 之类的非整点值即可。

想临时补跑一次，用 `workflow_dispatch`（就是上面的 Run workflow 按钮），不用等下周。

---

## 本地运行

```bash
pip install -r requirements.txt
```

需要 Python ≥ 3.10（`openai` 3.x 的要求）。然后设置环境变量：

```bash
export TAVILY_API_KEY="..."
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=..."
```

这些值就放在项目根目录的 `Key` 文件里（该文件已被 `.gitignore` 挡住，**绝不入仓**）。

常用命令：

```bash
python main.py --dry-run          # 只打印 Markdown 到控制台，不推送、不写台账 —— 先用这个
python main.py --limit 2          # 只跑前 2 条查询，省额度
python main.py                    # 完整流程，真的会发钉钉
```

`--dry-run` 不需要 `DINGTALK_WEBHOOK` 也能跑，方便先看效果。

---

## 自定义

| 想改什么 | 改哪里 |
|---|---|
| 搜索词 | `main.py` 顶部的 `QUERIES` 列表（**改完先 `--dry-run` 看召回质量**） |
| 屏蔽垃圾/社交站点 | `main.py` 的 `EXCLUDE_DOMAINS` |
| 中文技术查询定向的行业媒体 | `main.py` 的 `CN_INDUSTRY_DOMAINS` |
| 每个分类最多收录几条 | `main.py` 的 `MAX_ITEMS_PER_CATEGORY` |
| 分类口径 | `main.py` 的 `SYSTEM_PROMPT` 里三个分类的边界描述 |
| 换模型 | 改 `OPENAI_MODEL` 环境变量，不用动代码 |
| 推送时间 | `.github/workflows/weekly_news.yml` 的 cron（**记得换算成 UTC**） |

---

## 工作原理

```
环境变量校验 → 读取 history_urls.json
    ↓
4 条查询（中英各 2 条）检索 Tavily，近 7 天，屏蔽社交站、中文技术查询定向行业媒体
    ↓
URL 归一化（剥掉 utm_* 等追踪参数）→ 剔除台账里已有的 → 候选集内部去重
    ↓
┌─ 没有新资讯 → 推送「本周无新增资讯」短消息，不动台账
└─ 有新资讯 → DeepSeek 提炼成三个分类的 JSON
                ↓
            字段校验 + URL 白名单校验（模型会编链接，必须过滤）
                ↓
            Python 渲染 Markdown（不让模型直接写，格式才稳）
                ↓
            字节数检查，超长按分类拆多条
                ↓
            推送钉钉 → 把真正推送出去的 URL 写回台账
```

**为什么只记录推送出去的 URL**：如果模型丢弃了某条、或超出条数上限没被收录，
它下周还能重新冒出来。要是抓到时就直接记账，这些资讯就被永久吞掉了。

---

## FAQ

**群里没收到消息怎么办？**

按顺序查：

1. Actions 页面看最近一次运行。**红色 = 脚本报错**，日志里有完整 traceback。
   绿色但没收到 = 消息发出去了但被钉钉拦了，或那一周确实没有新资讯（会收到一条提示消息）。
2. **报 `310000`**：钉钉安全校验没过。这个错误码同时覆盖关键词不匹配、签名不匹配、
   IP 不在白名单四种情况，看日志里的 `errmsg` 才能确定是哪种。
   最常见的原因是机器人安全设置没选「自定义关键词」，或关键词不是 `行业资讯`。
3. **报 `410100`**：被钉钉限流了。官方限制是每机器人 20 条/分钟，超限会被封 10 分钟。
   本期周报拆分成了多条发送时可能触发，等 10 分钟重跑即可。
4. **提示变量缺失**：Secrets 名字拼错了，或没配。注意 GitHub Secrets 区分大小写。
5. **`TAVILY_API_KEY` 缺失却报了一堆限流错误**：这是 tavily-python 的一个坑 ——
   key 为空时它不报错，而是静默降级成匿名模式。所以脚本在启动时就显式校验了这个变量。

**为什么某周没收到？**

如果确实没有新资讯，脚本会发一条「本周无新增资讯」的短消息 —— 这是故意的，
让你能区分「没新闻」和「任务挂了」。如果连这条提示都没有，去看 Actions 日志。

**想重新推送历史资讯怎么办？**

把 `history_urls.json` 里的 `urls` 改成空对象 `{}` 即可（文件损坏或不存在时脚本也能自愈）。

**想临时推送到别的群？**

改 `DINGTALK_WEBHOOK` 环境变量就行，代码不用动。

**中文搜索词为什么和一般写法不一样？**

因为实测过。中文的关键词堆砌式长查询（把它们全塞进一句里）配合新闻主题，会返回
驱动之家日榜页、淘宝规则页这类完全无关的结果，甚至抓到垃圾站；改成自然语言的短查询后
才稳定命中厂商新品、专利、年报等有效信息。中文技术类查询还加了行业媒体定向，
否则会跑偏到汽车和消费电子领域。

所以**改搜索词后请务必先跑 `python main.py --dry-run` 看实际召回质量**，不要凭感觉写 ——
一个看起来合理的查询词，实际召回可能全是垃圾。

**Tavily 额度够用吗？**

免费额度 1000 credits/月，本任务每周 4 次 basic 检索（每次 1 credit）≈ 每月 16 credits。
（换成 `advanced` 是每次 2 credits，也远远够用。）

---

## 安全须知

- **`Key` 文件绝不入仓。** 它已在 `.gitignore` 里，workflow 里还有一道守卫：
  一旦发现 `Key` 被 git 跟踪就直接让 job 失败。
  任何时候都不要用 `git add -f Key` 绕过。
- **不要把 `Key` 的内容粘贴到 issue、PR、聊天记录或代码注释里。**
- 一旦密钥曾经被提交过或粘贴到别处，就去对应平台后台**重新生成** ——
  从 git 历史里删掉文件并不能让已经泄露的密钥失效。

<!--
排版样例 v2（2026-09-29）—— 给使用者预览新排版用。

内容取自 2026-09-24 那期的真实产出，**只重排了格式**，数据与链接一字未改：
  · 每个条目从「一段密集散文」改成「分点列表 + 末尾一句特点」
  · 每条末尾加 `**特点**：`，一句话点出这条最值得结构工程师记住的是什么
  · 链接从「紧跟句末」改为条目末尾的 **来源** 行（分点之后逐句挂链接会碎得没法看）
  · `### ` 标题加序号（`### 1. **BLUETTI** —— ...`），**每个板块内从 1 重新编号**。
    序号只是给读者看的行号，**不进台账** —— `extract_entries()` 会把它剥掉，
    因为台账里的标题会进下周的「上期标题清单」，带着"1."会被读成顺序指令

⚠️ 两处与原样例的差异，是口径变更造成的，不是排版：
  · 板块四按当前口径分区（北美／欧洲／日本）。本样例只有北美女有内容，
    欧洲与日本按新口径**直接省略该行**、不写占位句。
  · 原样例「中国工信部」一条不属于这三个地区，为演示新口径已略去。
  · 板块三当前还要写「结构件材料」（钣金/塑胶/压铸铝），本样例没有这类内容 ——
    那期确实没检索到。

⚠️ 长度代价实测很小，不用为此担心：改版后**字节数反而略降**（13265 vs 13781）——
   密集散文里的逗号分号破折号被换行与标签替代，汉字数基本持平（2624 vs 2616）。
   所以分点本身不会挤掉末尾板块。但 `OPENROUTER_MAX_TOKENS` 已顶到模型上限 8000，
   新增的「特点」句是净增量，落地后仍要留意日志里有没有 finish_reason=length。
-->

# [行业资讯] 储能结构周报（2026-09-24）

> 覆盖周期：2026-09-10 ~ 2026-09-24 ｜ 面向储能结构工程师

## 一、便携&阳台储能竞品动态

### 1. **BLUETTI** —— Balco 500 与 Elite mini 系列形成阳台一体机和轻量便携产品线

- **Balco 500**：5,024 Wh LFP 一体式阳台储能，集成电池、光伏输入与并网/离网逆变器
- **光伏与输出**：70–470 V 输入、最高 4,600 W；并网输出最高 3,680 W，备用输出 3,680 VA
- **接入方式**：支持 Schuko、Wieland、配电箱接入，以及第三方逆变器 AC 耦合
- **防护与寿命**：整机 IP65；电池标称 8,000 次循环至剩余容量 70%
- **Elite mini 三档**：288 Wh/300 W、1,004 Wh/700 W、2,009 Wh/1,600 W
- **小型化幅度**：相较对应 Elite V2，体积缩小 15%–42%，重量减轻 7%–25%
- **缺口**：Elite 30/200 mini 价格、全系绝对尺寸与 IP 等级均未公开

**来源**：[pv magazine](https://www.pv-magazine.com/press-releases/bluetti-launches-new-energy-solutions-for-work-home-and-life-on-the-move-at-ifa-2026/) ｜ [Notebookcheck](https://www.notebookcheck.net/Bluetti-debuts-four-new-portable-power-stations-at-IFA-2026.1388776.0.html)

**特点**：一体机把逆变器与并网接口做进电池箱、便携线靠结构紧凑化压体积，两条线并行走；阳台机安装侧可省掉独立逆变器，但尺寸未公开，无法判断堆叠与壁挂方案。

### 2. **EcoFlow** —— RIVER Gen4 压缩体积，PowerRock 4000 转向 IP65 工业便携电源

- **RIVER 260 Gen4**：256 Wh/300 W，约 3.0 kg；相较 RIVER 3 体积缩小 29.7%、重量减轻 16.9%
- **RIVER 520 Gen4**：512 Wh/500 W，约 4.6 kg；相较 RIVER 2 Max 体积缩小 59.1%、重量减轻 23.5%
- **共性**：LFP 电芯、140 W 双向 USB-C、UPS 切换 <10 ms；80% 充电分别为 42 / 50 分钟
- **PowerRock 4000**：约 3 kWh，连续 4,000 W、峰值 7,200 W/100 s，整机净重 38 kg
- **工业防护**：全金属 IP65 外壳 + 加强滚笼，通过 1 m 跌落；内置 30 mA 漏电检测与 300 ms 内切断的 RCD
- **缺口**：RIVER Gen4 售价与 IP 等级、PowerRock 价格均未公布；欧洲发布日为 2026-09-04

**来源**：[PR Newswire](https://www.prnewswire.com/news-releases/breaking-boundaries-ecoflow-unveils-river-gen4-and-powerrock-4000-at-ifa-2026-302869915.html)

**特点**：便携线用「压缩体积」延续小型化竞赛，工业线反过来堆料做 IP65 全金属壳与滚笼——同一个品牌用两套完全相反的结构语言切两个市场。

### 3. **Anker SOLIX** —— Solarbank Max 由 AC 耦合转向高压直流光伏耦合，容量扩展至 42 kWh

- **Solarbank Max**：7 kWh 单模块户用储能，可扩展至 42 kWh
- **架构变化**：从 AC 耦合阳台电池转为**高压直流光伏直入**，配置三路 MPPT
- **光伏输入**：最高 10,000 W
- **安装要求**：需由电工接入家庭电力系统
- **缺口**：整机尺寸、重量、IP 等级、循环寿命与正式售价均未披露

**来源**：[TechRadar](https://www.techradar.com/home/energy-saving/plug-in-solar-shone-at-ifa-2026-here-are-the-5-best-products-we-saw-from-anker-to-dji-and-ecoflow)

**特点**：从交流耦合转向高压直流直入，是阳台储能向户储主机的形态跃迁——电气架构一改，绝缘距离、防误插和电工介入的安装边界都要重做。

### 4. **DJI Power** —— Power 2000 增加可拆分阳台光伏套装，电池主机不变

- **系统形态**：IFA 2026 首发阳台光伏系统，首发市场德国，与既有 DJI Power 2000 组合销售
- **主机规格**：Power 2000 本体 2,048 Wh、连续逆变输出 3,000 W
- **结构思路**：即插即用，储能主机与光伏组件、微型逆变器**可拆分**
- **缺口**：光伏板功率、组件数量、系统容量、IP 等级、套装价格与上市日期均未公布

**来源**：[Smart Solar Homes](https://smartsolarhomes.co.uk/articles/dji-balcony-solar-ifa-2026)

**特点**：不动电池主机、只加光伏侧套装，用最小结构改动切入阳台场景——这是"存量主机 + 外挂配件"的低风险产品线扩张路径。

### 5. **Zendure** —— SolarFlow 2400 Pro / 4000 Mix Pro 强化模块化阳台与家庭储能连接

- **SolarFlow 2400 Pro**：四路 MPPT、最高 4,800 W 光伏输入、2,400 W 双向 AC，面向阳台储能与既有屋顶光伏改装
- **SolarFlow 4000 Mix Pro**：两路 MPPT、最高 13,000 W 光伏输入、4,000 W 双向功率
- **PowerHub**：中央网关，协调多台储能单元、光伏逆变器、充电桩与热泵；支持开放 API、MQTT、Home Assistant、Homey
- **结构落点**：多设备并列或堆叠后的线缆出线、网关安装位置、通信冗余
- **缺口**：两款 SolarFlow 的尺寸、重量、IP 等级、循环寿命与价格未披露；PowerHub 未给出机械锁止、盲插接口或无线通信物理层细节

**来源**：[TechRadar](https://www.techradar.com/home/energy-saving/plug-in-solar-shone-at-ifa-2026-here-are-the-5-best-products-we-saw-from-anker-to-dji-and-ecoflow) ｜ [EQS News](https://www.eqs-news.com/news/corporate/zendure-introduces-agentic-hems-at-ifa-2026-the-home-energy-hub-of-the-ai-era/)

**特点**：卖点从单机参数转向「多设备怎么连」，把线缆出线、网关位和通信冗余变成结构问题——但机械与物理层细节全部未公开，目前只能算概念宣示。

## 二、户用&工商业储能与大机动态

### 1. **BYD** —— GC Block 将 GW 级构网型电站标准化为 62 MWh 单元

- **发布场合**：深圳国际数字能源展，GW 级 GridForming Energy Storage Solution 2.0
- **标准单元**：**GC Block** 单块容量 62 MWh，由 **MC CubeXT** 储能系统与 **GC Flux PCS 2.0** 组成
- **电芯**：MC CubeXT 采用 1,980 Ah Blade Battery，面向 2 小时及以上长时储能
- **PCS**：GC Flux PCS 2.0 为 20 英尺集装箱结构，单机输出 10 MW，峰值效率 99.50%，支持 10 秒 3 倍过载
- **结构落点**：重点从单柜能量密度转为电池舱、PCS 舱、母线与并联单元在 62 MWh 标准块内的**接口统一、运输分段与故障隔离**

**来源**：[EnergyTrend](https://www.energytrend.com/news/20260917-52157.html)

**特点**：把电站做成标准化大块，结构设计的对象从"柜"上移到"块"——接口统一和运输分段取代能量密度成为主矛盾。

### 2. **Hithium** —— 4 MWh 钠离子系统采用 800–1500 V PCS、风液混合冷却与大尺寸叠片

- **系统**：∞Power N4.0MWh，搭载 ∞Cell N785Ah 钠离子电芯，面向 2–8 小时储能
- **寿命**：电芯标称循环 20,000 次；全链条量产交付计划 2027 年
- **电气**：兼容 800–1500 V PCS，BMS 的 SOC 估算精度 ≤2.5%
- **热管理**：风液混合冷却，集成气象监测与预警
- **厂商披露收益**：系统占地缩小 30%、运行辅耗下降 30%、待机辅耗下降 50%
- **结构落点**：需重点校核大尺寸电芯的端板、拉杆和模组限位——该电芯采用大尺寸叠片工艺，并明确使用能承受 20,000 次以上膨胀收缩的结构件，Pack 设计必须按**长期厚度变化、端板预紧力衰减、冷却板接触压力**做寿命工况，而不是只按初始装配态
- **缺口**：整机尺寸、重量、IP 等级及冷却回路具体布置未披露

**来源**：[Energy-Storage.News](https://www.energy-storage.news/hithium-unveils-20000-cycle-sodium-ion-cell-and-4mwh-bess/) ｜ [EnergyTrend](https://www.energytrend.com/news/20260917-52157.html)

**特点**：钠电的成本与低温优势要靠 2 万次循环兑现，结构件因此从"装配零件"变成"寿命件"——膨胀补偿与预紧力保持是这个平台真正的结构命题。

### 3. **Huawei Digital Power** —— 1000 VAC 智能串架构与 241 kWh 混合冷却 C&I ESS 同步展示

- **Smart String Grid Forming ESS**：1000 VAC 智能串架构、贯通式母线、电站级构网控制，支持 12.5 MW/50 MWh 阵列
- **构网功能**：短路容量支撑、惯量响应、宽频振荡阻尼、一次调频、黑启动、并离网无缝切换
- **241 kWh C&I 系统**：单一冷却模式改为智能混合冷却，引入 pack-level optimization 2.0
- **公开指标**：往返效率 91.8%，100% DOD
- **结构落点**：1000 VAC 会提高母排爬电距离、绝缘隔离、端子防误插与舱内电场管理要求；混合冷却要在同一柜体内同时容纳风道、液冷板、泵阀、膨胀补偿与维护空间，**不能按「液冷柜加一组风扇」叠加**
- **缺口**：柜体尺寸、重量、IP 等级及风液切换逻辑未公开

**来源**：[PR Newswire](https://www.prnewswire.com/apac/news-releases/huawei-digital-power-showcases-multi-scenario-solutions-featuring-grid-forming-and-ai-at-idee-2026-302883933.html)

**特点**：电压平台抬到 1000 VAC 后，绝缘与电场管理重新变成柜体设计的主约束；混合冷却同理，是"重新排布"而不是"再加一套"。

## 三、电池与材料技术突破

### 1. **Hithium** —— NFPP 正极压实与硬碳低膨胀成为钠离子 Pack 的结构约束

- **正极**：∞Cell N785Ah 使用高相纯度、高压实密度、低电阻率的 NFPP 材料
- **厂商披露**：电导率提升 3 个数量级，相纯度达 97%
- **负极**：配套具快速钠离子传输通道的硬碳，被描述为「超低膨胀」
- **工艺**：超厚极片涂布 + 大尺寸叠片；为 20,000 次以上循环开发长寿命结构件
- **缺口**：硬碳的具体膨胀率与压实密度均未给出，**无法转化为明确的结构余量**
- **结构落点**：超厚极片与大容量叠片会提高单体热梯度、极片边缘应力与制造公差累积风险；端板、侧板、绝缘片和冷却界面应按「循环膨胀—收缩后的接触压力」验证，并增加电芯厚度变化、端板位移与预紧力保持率的寿命测试

**来源**：[Energy-Storage.News](https://www.energy-storage.news/hithium-unveils-20000-cycle-sodium-ion-cell-and-4mwh-bess/)

**特点**：正极压实与负极低膨胀是一对矛盾——材料端越"超低膨胀"，结构端越不该据此削减压紧余量，因为公开数据不足以支撑这个推断。

## 四、安规与政策大事件

**北美**

- **NFPA 855:2026**：除 UL 9540A 的电芯、模组、单元和安装级测试外，新增**大型火灾测试（LSFT）**，验证相邻 ESS 单元之间不发生火焰传播；涉及可燃气体释放的测试还需开展带排放气体点燃的单元级测试
- **结构约束**：泄压路径、阻火隔断、相邻柜体间距、探测器安装位与消防系统接口必须在**概念设计阶段**同步确定，不能等 UL 9540A 之后再补装防护件
- **进口限制**：针对逆变器、变压器及其他电力设备的限制仍处规则制定阶段；行政令适用于 2026-08-26 后发起的交易，但在美国能源部发布实施细则前不会直接禁止交易
- **本周期无新版本**：UL 2743、UL 3700 与德国 DIN VDE V 0126-95 均未发布新的正式版本或强制性条款

**来源**：[Energy-Storage.News（NFPA 855）](https://www.energy-storage.news/nfpa-855-2026-edition-updates-and-what-they-mean-for-energy-storage-projects.html) ｜ [Energy-Storage.News（进口限制）](https://www.energy-storage.news/trumps-power-equipment-ban-us-bess-market-implications-and-the-supply-chain-dilemma/)

**特点**：本周期北美的实质变化是把火灾测试往"安装级"推——结构设计的合规时点因此被迫前移到概念阶段，而不是留到认证前补件。

## 五、对华宝新能（Jackery）结构与产品定义的启发

1. **提高 Pack 集成度，但把高压隔离与维护边界前置。**
   **SolarVault** 若向可扩展家庭储能演进，可借鉴 800–1500 V PCS 兼容和模块化并联思路，将电池、BMS、高压盒及冷却接口做成可独立维护的标准模块。**HomePower** 的柜体和堆叠接口应在结构冻结前同步完成爬电距离、母排防护、盲插防误配和运输锁止验证。

2. **便携产品与单设备备电产品继续压缩体积，但不能牺牲散热和认证空间。**
   **Explorer 系列**应优先优化电芯—冷却件—逆变器的热路径，避免通过减少壳体间隙换取体积缩小；可将风道、导流件、跌落筋位和阻燃隔热件作为同一结构包设计。**FridgeGuard** 的卧式 CTB、约 67 mm 超薄和可立放/平放/壁挂形态，要求在三种姿态下分别验证电芯压紧、接口受力、自然对流和壁挂载荷，不能只按桌面放置工况定型。

3. **把新材料和认证前置到可制造性评审。**
   **SolarSaga** 已有 IP68、IEC 63163 和 IEC 61701 盐雾认证基础，后续折叠与连接结构应把密封件压缩率、铰链疲劳、线缆弯折半径和盐雾后的接触电阻纳入量产验证。对于 **Explorer** 与 **HomePower**，若采用阻燃工程塑料、云母或气凝胶隔热层，应同步评估注塑翘曲、压缩回弹、胶黏剂耐温和 UL 9540A/相关认证样件一致性，避免后期因材料变更重新进行整机测试。

—— 本消息由自动化脚本生成，检索源：Perplexity sonar-pro-search

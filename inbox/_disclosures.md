# 机型 → 已披露维度台账（人工维护）

用途：审核专家据此判断「同一机型在新一期里是否带来了**新披露维度**」（判定条文见 `_rubric.md` 的 R3.3）。
**不改 `pushed_history.json` 的 schema** —— 那是运行时回写、被 CI 白名单约束的文件，加字段会牵连 version 校验与提交断言。

## 维护规则

1. 每期推送后追加/更新一次，只记**已公开披露**的维度。
2. **价格、促销、开卖日期、渠道上架不记**（属 `_rubric.md` 的「四类排除」）。
3. 「仅标题级」表示只从台账标题知道该机型存在，参数未核实——这类行不得作为「已披露」依据，需先补核。
4. 同一维度如出现口径冲突（如 0.01 s vs 10 ms 这类换算差异），在该行末尾用 `⚠口径` 标注，不进稿除非有第二来源。

---

## 便携电源（portable power station）

| 机型 | 厂商 | 首次入稿 | 已披露维度 | 尚缺 / 可补充 |
|---|---|---|---|---|
| DJI Power Auro 2000 Elite | DJI | 2026-10-12 | 2 kWh；19 kg；比 Power 2000 体积小 24%、轻 2.5 kg；2,000 W 连续 / 2,200 W 峰值；LFP 6,000 循环至 70%；5VB 阻燃壳；13 温感 + 40 保险丝；1 吨静压；140 W 伸缩 USB-C；双 SDC；五路补能；UPS 约 10 ms；<30 dB；单面端口布局；€1,099 | 拆机（电芯—模组—底盘连接结构）、整机热仿真、实测温升、扩容电池发布时间 |
| Anker SOLIX S5000 | Anker | 2026-10-19 | 5,024 Wh；4,500 W 连续 / 8,000 W 峰值；314 Ah LFP；6,000 循环至 80% / 10,000 至 60%；约 44 kg；约 27×56×39 cm；1,800 W@120V、4,500 W@240V 充电；99 分钟充满；双路光伏 1,000 W + 2,000 W；可扩至 30 kWh；UL 9540 / UL 9540A；30 dB；8.8 W 空载；带轮与拉杆 | 扩展电池包定价与规格；非北美配置差异；拆机 |
| Anker SOLIX S2000 | Anker | 未入稿（核查中出现） | 2,010 Wh；1,500 W 额定 / 3,000 W 峰值；16.2 kg；8.2×11.1×12.7 in；314 Ah LFP；6,000→80% / 10,000→60%；<10 ms UPS；6 W 空载；美 $729.99 / 欧 €699.99 / 英 £649 | 拆机与热结构；无扩展能力的设计取舍 |
| BLUETTI Apex 200 | BLUETTI | 2026-11-02 | 2,560 Wh；3.2–3.6 kW；26.9 kg；36.2 L；70.7 Wh/L（UltraCell）；3 kW 光伏（2 kW 高压 MC4 60–280 V + 1 kW XT60）；0→80% 50 分钟；15 ms UPS；10.5 W 空载；四路独立可控 AC；TT-30R + 12V/30A Anderson；单机扩至 33.28 kWh、三机并联约 100 kWh | 拆机；UltraCell 电芯规格；B500K 扩展包参数 |
| EcoFlow DELTA Pro 3 | EcoFlow | 未入稿 | 4,096 Wh；4,000 W / 8,000 W 峰值；51.5 kg；IP65 LFP；CTC 电芯到底盘；UL94 5VA 外壳；4,000 循环至 80% | 国内版本差异；拆机；2026 后续改款 |
| EcoFlow DELTA Gen4 | EcoFlow | 2026-10-26 | 仅标题级，参数未核 | 需重新核参数后方可作为「已披露」依据 |
| EcoFlow RIVER Gen4 | EcoFlow | 2026-10-12 | 仅标题级，参数未核 | 同上 |
| EcoFlow PowerRock 4000 | EcoFlow | 2026-10-12 | 仅标题级，参数未核 | 同上 |
| EcoFlow STREAM 5000 | EcoFlow | 2026-10-12 | 仅标题级，参数未核 | 同上 |
| EcoFlow STREAM Ultra | EcoFlow | 未入稿 | 1.92 kWh；1.2 kW；−20~55 ℃；6,000 循环至 70%；IP65；255×458×284 mm；23.10 kg；4 MPPT；内置单相逆变器 | 拆机；并网合规口径 |
| Zendure SolarFlow 2400 AC+ / 2400 Pro | Zendure | 2026-10-19 | 仅标题级，参数未核 | 需补核 |
| CARKU PB-102 | CARKU | 2026-10-19 / 10-21 | 2 kWh；16.5 kg；8,000+ 循环 LFP；UPS 备份；AC 线 + 光伏两路 | 拆机；电芯供应商 |
| CARKU PB-120 / PB-122 | CARKU | 2026-10-19 / 10-21 | PB-120：600 W 连续 + 100 W PD + UPS + 车辆应急启动；PB-122：3.5 kg、400 W + 高亮 LED + UPS | 同上 |
| Segway Cube 2000 | Segway | 2026-10-12 | 仅标题级，参数未核 | 需补核 |
| Goal Zero Yeti 1500 | Goal Zero | 2026-10-12 / 10-19 | 仅标题级，参数未核 | 需补核（两次推送可能为重复，待核） |
| BLUETTI Balco 500 / Pioneer 5000 / Elite mini | BLUETTI | 2026-10-12 | 仅标题级，参数未核 | 需补核 |
| Hoymiles HiBattery 4020 | Hoymiles | 2026-10-12 | 仅标题级，参数未核 | 需补核 |
| Jackery Plus 系列 / Explorer 2000 v2 | Jackery（自家） | 未入稿 | Explorer 2000 v2：$999；2,042 Wh；2,200 W 额定 / 4,400 W 峰值；17.9 kg；CTB 结构；4,000 循环；预售 | 自家产品，只可在板块五引用，不得进板块一~四 |

## 阳台 / 插电式家储

| 机型 | 厂商 | 首次入稿 | 已披露维度 | 尚缺 / 可补充 |
|---|---|---|---|---|
| Conow Atlas 6000 AC | Conow | 2026-11-09 | 6,028 Wh；3,000 W 双向；805×315×256 mm；净 55.9 kg / 毛 59.2 kg；无风扇被动散热 + 大体积散热齿；逆变器—电芯内部热隔离；加热膜 −20~+55 ℃；IP65；回馈 799 / 800 / 3,000 W 三档；Schuko 出厂接入；气溶胶灭火；10,000 循环@70% EOL；10 年质保；AirMesh 10 台并联 60 kWh；三机三相 9 kW / 18 kWh；<10 ms 切换；€1,249 | 拆机；散热齿实测温升；逆变器拓扑；气溶胶模块型号 |
| Outer Spaces OS1 | Outer Spaces | 2026-11-09 | BladePack 7.83 kWh / 模块；1,470×368.6×125 mm；约 72 kg；最多 8 模块 62.64 kWh；被动冷却 + 0 ℃ 加热；−20~55 ℃、>40 ℃ 降额；IP67；10 年质保；Fox ESS H1-11.4-US + 12 kW DC hub；7.83 kVA / 多模块 11.4 kVA；启动 80 A / 160 A；12×12 ft 与 12×24 ft；约 2.5 / 5 kW；AC 耦合、VPP-ready、光伏黑启动；$8M pre-seed；2027 交付 | ⚠口径：起配是 2 模块 15 kWh 还是单模块 7.83 kWh，官方未统一；承重做法与检修口；价格 |
| Solis FlexAIO | Solis（锦浪） | 2026-11-09 | 单相高压 3–10 kW、三相高压 5–20 kW；模块化堆叠；Solis AI 挂 SolisCloud（光伏+负荷+天气+SOC+实时电价）；2027 Q1 首批交付 | 单机容量档位、整机重量、堆叠层数上限 |
| DJI IFA 阳台光储（2026） | DJI | 2026-10-12 | 仅标题级；另有报道称 IFA 2026 宣布的阳台方案最终未落地 | ⚠口径：是否取消，需核 |

## 电池与材料

| 机型 / 技术 | 厂商 | 首次入稿 | 已披露维度 | 尚缺 / 可补充 |
|---|---|---|---|---|
| Revolta 10 kWh 钠离子 | Revolta | 2026-11-09 | 450 V；5×2 kWh 模块；3 电芯 / 模块；18.7 kg / 模块；IP64；0.4 C；最大输出约 4 kW；141 Wh/l、107 Wh/kg；配 SMA 逆变器；€599 单模块 / €2,995 套装 | 额定功率、循环寿命、效率（公告未披露） |
| Fraunhofer ISE 钠电干法涂布 | Fraunhofer ISE | 2026-11-09 | LAENDLE 项目；无溶剂；无 PFAS；与工业伙伴合作 | 面密度、剥离强度、极压压实、产线改造成本 |
| EDENenergy 70 kWh | Fraunhofer ISE 分拆 | 2026-11-09 | 112 块退役 e-scooter 电池；不拆包、异构接入与通信自研电力电子；模块可带电更换；测试 350 块电池平均 SoH 部分远超 90%；可扩至 300 kWh | 电力电子拓扑；接插件规格；通信协议 |
| Hithium N785Ah 钠离子 | 海辰 | 2026-10-19 | 仅标题级，参数未核 | 需补核 |
| CATL Naxtra | 宁德时代 | 2026-11-02 | 仅标题级，参数未核 | 需补核 |
| Toshiba SCiB 混合（蒙古 Darkhan） | Toshiba | 未入稿 | 20 Ah 单体；1,200 W 出 / 1,100 W 入；6 分钟 80%；20,000 循环后 >70%；−30 ℃ | 系统级拓扑；并网配置 |
| Dow VOLTRICELL | Dow | 2026-10-26 / 11-02 | 仅标题级，参数未核 | 需补核 |

## 待补录（台账里有、本文件尚未建行）

10-12：Anker SOLIX Solarbank Max、JA Solar JAPlanet Fusion、Hoymiles HiBattery 4020、Jinko ESS Tera 220MWh 德国、海尔 E-Stack (H)、HIZENERGY EnerBox、Fraunhofer ISE 厚电极、NUS CDE 氮化碳固态钠
10-19：BLUETTI AORA 200 V2、Exide Solition Powerflex、巨湾技研全固态产线、Great Power Fengpeng 587Ah
10-26：Hoymiles HoyUltra 2,000M、Sineng 430kW 组串 PCS、Sungrow PowerTitan 3.0（UL 9540A:2026）、钠基固态结构电池（CFRP 加固件）
11-02：Hoymiles HiOne、CATL TENER+ 9MWh、Sineng 液冷组串 PCS、TCL Sunpower X5、Jinko ESS Tera 镜像柜、PACT Thermo Shield

> 规则：新一期要写某机型时，先在本文件建行并填「已披露维度」，再判断是否为新披露；不要凭记忆判断。

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-09 | 首版。建 26 行，标注 `⚠口径` 2 处，列待补录 23 项 |

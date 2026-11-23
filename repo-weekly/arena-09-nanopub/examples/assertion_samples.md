# 20 条断言样例（全合成，供拆解口径复用）

> 以下 20 条样例**全部虚构**，覆盖数值型、比较型、机制型、条件型、作者声明型
> 五种常见形态，示范"单一可判 + 条件限定 + 证据类型 + 置信度"的标注口径。
> 领域涉及催化、电池、光电、合金、生物材料，便于不同论文背景者参照。

| # | 断言陈述（含条件限定） | 主体 | 关系 | 客体 | 证据类型 | 置信度 |
|---|---|---|---|---|---|---|
| 1 | 在 0.5 M H2SO4 中，样品 C-60 在 10 mA/cm2 下过电位为 178 mV | C-60 | overpotentialAt10mAcm2 | 178 mV | 直接 | high |
| 2 | 样品 C-60 的 Tafel 斜率为 69 mV/dec | C-60 | tafelSlope | 69 mV/dec | 直接 | high |
| 3 | 在 25 ℃、1C 倍率下，电池 B1 循环 500 次后容量保持率为 87% | B1 | capacityRetentionAfter500Cycles | 87% | 直接 | high |
| 4 | 电池 B1 的首周库仑效率为 91.2% | B1 | firstCycleCoulombicEfficiency | 91.2% | 直接 | high |
| 5 | 在 AM1.5G 光照下，器件 P3 的光电转换效率为 18.7% | P3 | powerConversionEfficiency | 18.7% | 直接 | high |
| 6 | 器件 P3 的开路电压为 1.12 V | P3 | openCircuitVoltage | 1.12 V | 直接 | high |
| 7 | 合金 A9 的室温屈服强度为 1020 MPa | A9 | yieldStrengthAtRT | 1020 MPa | 直接 | high |
| 8 | 合金 A9 的断后伸长率为 12.5% | A9 | elongationAtBreak | 12.5% | 直接 | high |
| 9 | C-60 的 HER 活性高于未处理样品 C-0（过电位低 134 mV） | C-60 | lowerOverpotentialThan | C-0 | 间接 | medium |
| 10 | 在相同测试条件下，器件 P3 的效率高于器件 P1（18.7% vs 15.2%） | P3 | higherEfficiencyThan | P1 | 间接 | medium |
| 11 | 合金 A9 的强度-塑性匹配优于合金 A3（强度与伸长率均更高） | A9 | betterStrengthDuctilityThan | A3 | 间接 | medium |
| 12 | C-60 活性提升的机制是硫空位增多 | C-60 | activityMechanism | 硫空位增多 | 作者声明 | low |
| 13 | 电池 B1 的容量衰减主要源于 SEI 持续增长 | B1 | fadingMechanism | SEI 增长 | 作者声明 | low |
| 14 | 涂层 H5 在 3.5 wt% NaCl 中浸泡 720 h 后无明显腐蚀坑 | H5 | corrosionResistanceInNaCl | 720 h 无腐蚀坑 | 直接 | high |
| 15 | 支架 S2 在 7 天培养后细胞存活率为 95%（MTT 法） | S2 | cellViability7dMTT | 95% | 直接 | high |
| 16 | 催化剂 K2 在 300 ℃ 下 CO2 转化率为 42%，选择性 99%（甲烷） | K2 | co2ConversionAt300C | 42%（CH4 选择性 99%） | 直接 | high |
| 17 | 薄膜 F7 在 550 ℃ 退火后由非晶转为钙钛矿相（XRD 判定） | F7 | phaseAfterAnnealing550C | 钙钛矿相 | 直接 | high |
| 18 | 膜 M4 在 0.3 MPa 下对 NaCl 截留率为 98.5% | M4 | naclRejectionAt0.3MPa | 98.5% | 直接 | high |
| 19 | 催化剂 K2 的活性位点为单原子 Pt（作者依 HAADF-STEM 推断） | K2 | activeSite | 单原子 Pt | 作者声明 | low |
| 20 | 支架 S2 促成骨效果优于支架 S1（ALP 活性更高，p < 0.05） | S2 | higherAlpActivityThan | S1 | 间接 | medium |

复用要点：
- 数值型（1-8、14-18）：客体必须带单位与测量条件，条件进断言文本或单独三元组。
- 比较型（9-11、20）：由两行直接证据合并，证据类型=间接，置信度 ≤medium。
- 机制型（12-13、19）：作者归因/推断，证据类型=作者声明，置信度 low。
- 一条断言只留一个命题：#16 的转化率与选择性若需独立核验，应再拆两条。

v2 增补（条件范围 + 证据形式，保守追加两列；上表列保持 v1 不变）：
- #1 条件范围="0.5 M H2SO4 三电极体系；仅酸性条件"，证据形式=实验数据；
- #9 条件范围="与 C-0 相同的测试条件"，证据形式=实验数据（两行数值合并）；
- #12 条件范围="作者提出的机制解释，未做同位素/谱学验证"，证据形式=作者声明；
- #17 条件范围="550 ℃ 退火工艺窗口；XRD 判定口径"，证据形式=实验数据。
若证据来自论文对他文的引用（本表未含），证据形式=引用支持，并须把被引文献
登记进 materials_register.md。

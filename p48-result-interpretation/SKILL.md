---
name: result-interpretation
description: >
  实验结果解释与异常分析：实际读取表格、XLSX 或允许的 MATLAB 输入，按样本/批次/通道/
  时间点，以物理范围、组内稳健 IQR/MAD 和声明基线的 SPC 规则找异常，计算描述性趋势、
  OLS 区间、对照/配对效应量及不确定性。异常在原分析中保留，另做影响敏感性。分别呈现
  观测、计算、技术/方法/生物学候选原因和可证伪复核/后续实验，绝不把相关写因果或静默
  删点。用于可追溯数据判读，不用于猜测实验来源/生物学机制或自动决定舍去异常。
---

# result-interpretation

主入口是 `scripts/result_analysis.py`（计算层 `scripts/result_diagnostics.py`）。它不是仅校验
“有没有写解释”的审稿器：读取实际原始行，生成五段结论和可复算的统计证据。
旧 `scripts/cleandata.py` 仍作为兼容性数据清洗/解读格式审计入口保留，但不是本包主路径。

## 运行步骤

1. 读取 `/input/case.json` 与 `task.md`，**实际打开**其指向的数据、工作簿、设备日志和论文。
   先保存 `case_id`、`output_contract`、源文件路径、sheet/变量名、字段与来源。提取脚本或
   表格快照放 `/app/work`；最终 `/app/output/result.json` 保留原标识与来源。
2. 按原文把字段映射到 `columns`、响应列、分组列、排序列与比较项。不能用 `Iris`、
   `Cefixime`、MATLAB 等名称给出预制答案；每个工作簿 sheet 和 MATLAB 变量必须与实际
   证据相符。工作簿多表时显式 `--sheet`，MATLAB 多变量时显式 `--mat-variable`，不猜“最像”。
3. 执行任一形式：

```bash
python /skills/weekly-skill/scripts/result_analysis.py \
  --spec /app/work/analysis-spec.json --case /input/case.json --out /app/output

# 已经给出明确的实际源表/工作表映射时也可以直接运行
python /skills/weekly-skill/scripts/result_analysis.py \
  --table /input/readings.csv --spec /app/work/column-map.json --out /app/output
```

4. 读 `findings`、五段 `interpretation`、`effect_sizes`、
   `statistical_process_control`、`observed_vs_inferred`、`limits` 和待复核项。
   缺失基线/重复状态/单位及其换算/物理阈值，应保留 unknown 或结构化拒绝，不伪造真值。
5. `status` 映射到 `delivery_status` 分别为 clean→done、review→partial、blocked→failed；
   CLI exit 为 `0/3/4/5`，最后一项为 undetermined。异常旗标本身并不删除数据，也不使
   统计计算失败。未知原因与数据不可用不是同一件事。

## 支持的源与限制

| 来源 | 实际读取方式 | 必须交代 |
|-|-|-|
| CSV / TSV / TXT | csv reader，第一行为列名，重复列名加后缀保留 | 单元格单位/缺失/表头解释；原表行号回指转换后的数据行 |
| JSON | rows/records/data 列表或显式矩阵 | 哪一层是行、怎样映射科研变量 |
| XLSX/XLSM | openpyxl 可用时 read_only/data_only；否则标准库 ZIP/XML | `--sheet` 多表必指定，支持 shared/inline strings 和列号；读公式**缓存值**，绝不重算公式、宏、样式或 Excel 日期语义 |
| MAT | 可选 SciPy `loadmat`，显式 `--mat-variable` | 当前支持简单数值矩阵和约定好的标量表格；cell/嵌套 struct 需另做有据提取，不能从标签猜生物含义 |
| inline rows | spec 中一般为行对象列表 | 每行一个源记录，spec 明示其类型，不把技术重复默认为独立生物学重复 |

不支持旧二进制 `.xls` 的隐式转换，或 v7.3/HDF5/MATLAB 完整对象；相应环境具备 SciPy
及其支持格式才可走 MAT 通道，否则返回 `analysis.input_error` 而非空结果冒充分析完成。
工作簿/工作簿中没有指定 sheet 且无法安全判定、单元格/嵌套 struct 不可映射时同样拒绝。
没有 openpyxl/scipy 时不是必须联网安装；XLSX 有上面的标准库回退，MAT 配合提供的科学
Python 资源或如实写明边界。

## 最小数据映射

完整示例：`examples/analysis-spec.json` 与 `examples/readings.csv`，这是合成压力示例而非
官方答案。文件相对 spec 的路径会正确地相对 spec 目录解析：

```json
{
  "table_path": "readings.csv",
  "columns": [
    {"name": "sample", "semantic": "id"},
    {"name": "batch", "semantic": "categorical"},
    {"name": "group", "semantic": "categorical"},
    {"name": "cycle", "semantic": "ordered_numeric"},
    {"name": "hardness", "semantic": "response", "unit": "MPa",
      "plausible": [0, 46], "plausible_source": "SOP rev2 §4"}
  ],
  "group_by": "batch", "order_column": "cycle",
  "response_columns": ["hardness"],
  "comparisons": [{"response": "hardness", "group_column": "group",
                     "left": "control", "right": "treated"}]
}
```

`response_columns` 可单个名字或列表；否则取 semantic=response、有单位或物理范围的字段。
`group_by` 决定稳健异常的组，缺失时只用全局分布；绝不以小样本组偷偷回退跨批大分布。
无声明 `order_column` 不把 unordered 行号解读成时间或剂量。`require_trend=true` 且缺排序
列会产生 finding。分类字段按原字符串保留，不能从 phase/reference 等推断数值类别。

**单位**：Cell 形如 `4.5 MPa` 且目标是 MPa 时直接读数；目标不同则需列中的
`unit_conversions: {"MPa": factor}`，factor 显式来自任务换算口径。不同单位不能自动猜。
输入 `<LOD`、`<`、`>` 均为 censored，保持注明，不替换为阈值、0 或观测均数。
`NaN/NA/ND/未报告` 保留命名缺失。原样行存于 `original-table.csv` 与
`original-records.json`，结果还给出每个异常点的实际源、sheet/行和阈值。

## 五段输出与真实机制

### 1. 结果趋势 `interpretation.result_trends`

按明确数值排序键对齐读数，报告首末差、全幅、OLS 斜率与截距、R²、残差、斜率标准误
（适用时）。这只能描述计算关系，不是因果证据。
- 用户明确提供 `trend_slope_tolerance` 才声明容差内的近似平缓，否则不发明平台期阈值。
- `plateau_analysis` 列出相邻差分进入该容差的段，和容差原文。
- n≥6 时还生成最小两段 SSE 的候选 hinge 点、前后斜率和 R²；这是候选拐点，不是有
  置信区间或机理证明的拐点。n<2 或排序列全相等时无法求方向。

### 2. 异常点 `interpretation.anomaly_points`

每条都关联 `anomaly_id`、row/sample 源、group（如 batch/channel）、原值、规则和
`retained_in_primary_analysis=true`，并同时报告：
- 组内 far-out IQR（默认 **3×IQR**，min_n=6，能配置且留痕）、MAD robust z>3.5 的显著
  偏离；IQR=0 且全组恒定时只对接特别注明 constant-reference deviation，不随意广化阈值。
- 每个中位数偏离、`robust_effect=(x-median)/(1.4826*MAD)`，有阈值时给 Q1/Q3/IQR/
  fence，n 不足/散布不足则明确空缺，绝不编造标准差。
- 列中 `plausible` 提供物理上下限时另判正式 physical-range。两个检测通道不强行互相
  抵消，不把跨批次/通道正常混合当异常。

### 3. 效应量和原因候选 `effect_sizes`、`possible_causes`

在 `comparisons` 中显式给 response、group_column、left、right，未声明不挑选对照。
- 非配对给 mean 差、相对差（基线非零）、两组独立 CI、pooled Cohen d、Hedges g；
  n≥2 时 Welch 均值差 CI 与 df。文章需要的是效应而不只是 p 的显式数值；这里不把一次
  差异检验包装成因果估计。
- 有 `pair_by` 时按实际配对键计算差值均值、sd、CI、Cohen dz；5-split/2-estimator 一类
  计算实验明确标记 fold/split 共享与独立性限制，不声称有一堆独立生物医学重复。
- 同一 key 重复时是 `ambiguous_pairing`，不会最后一行覆盖前一行。只有输入显式
  `average_technical_replicates=true` 才在 key 内求技术重复均值，并保留非独立声明。
- `cause_candidates` 可声明技术/方法/生物学假设，保留支持、反证与来源。只有真正以
  supporting evidence 数排序，不杜撰机理。若未提供，异常自动给出技术（读数、日志、
  设备/时钟/通道）和方法（单位、前处理、分组、对照选择）备选；只有
  domain 或 domain_type 明示 biological 才加入真实生物差异的候选，否则不会硬编生物解释。

### 4. 复核步骤 `review_steps`

每个候选原因都有 `falsification_test`：目标源行、读原表哪个位置、比较何种设备/批次/
原始日志或配对条件、什么结果会证伪候选。不是“检查数据质量”。候选原因缺证伪规则报
`analysis.hypothesis_unfalsifiable`，无实现的日志/对照不存在时被标为尚未核查。

### 5. 后续实验 `next_experiments`

只有经过前一步检查、源允许且预注册的受控重复/对照后续动作才出现；包括匹配测量链、
预定义判据、资源/安全/样本前置条件和失败后怎样降低该候选优先级。不会用建议伪装
成已获伦理批件/真实执行指令，也不会从相关性选择一个“真正原因”。

## 声明基线的统计过程控制

`spc` 开启时必须声明：初始稳定参考（`baseline_filter`）或中心线与 sigma、排序键及来源。
```
"spc": {"enabled": true, "baseline_filter": {"phase": "reference"},
        "order_column": "time", "run_length": 8, "trend_length": 6,
        "source": "source-for-reference-and-keep/change-record"}
```
也可直接给 `centerline`、`sigma`，由该 sigma 来源负责其良定义。估计参考最少六行，
太多未知/零 sigma 不会输出伪可控结论。实际计算：
1. 单点超过中心线 ±3σ；
2. 序列中同侧>=run length 的点（每侧只留一次代表记录）；
3. trend length 个严格单调递增/递减的点。
控制图只做“应调查 assigned cause”的提示，不是仪器正常/生物效应/稳定运行的证明。

## 异常保留而不是默认删除

`effect_sizes[].suspicious_point_influence` 同时给出**全原行主分析**及去掉已标记行后的
影响敏感性均值差。这只能用于回答“结论是否由某个旗标驱动”，并不把后者当作已纠错主结果。
没有已批准、预登记的剔除/测量重归一化规则，异常不从 primary dataset 移除、不做盖帽、
不用均值/回归填充。

## 发现项和拒绝

| rule | severity | 含义 |
|-|-|-|
| `analysis.input_error` | high | 不可读 JSON/格式、缺源、缺 sheet/变量、零行或不可执行映射；exit 5，契约仍保留 |
| `analysis.unparsed_or_ambiguous_cells` | medium | 拒绝单位/结构不清晰的测量行被静默纳入 |
| `analysis.trend_order_missing` | medium | 请求趋势但无实际排序，不把列表位置当实验因果先后 |
| `analysis.incomplete_comparison` | medium | 缺 response/group_column/left/right，不默认挑装置/估计器 |
| `analysis.ambiguous_pairing` | medium | 重复 pair_by，不静默覆盖；先声明配对机制 |
| `analysis.missing_response_column` | medium | 部分请求响应列不在实际表头，未分析的项目点名而非隐去 |
| `analysis.hypothesis_unfalsifiable` | medium | 原因候选缺可证伪测试 |
| `analysis.anomaly_review_required` | low | 异常被标出且原始值保留，供审查，而非自动判定故障原因 |

旧接口的机械 finding（仍有相应回归）：`clean.spec_unreadable`、`clean.already_cleaned`、
`clean.not_idempotent`、`clean.missing_values`、`clean.unparsed_values`、
`clean.duplicate_experiments`、`clean.duplicate_records`、`clean.report_inconsistent`、
`observation.value_not_in_data`、`observation.malformed`、`anomaly.unexplained`、
`anomaly.cause_asserted`、`trend.direction_mismatch`、`trend.unverifiable`、
`review.not_executable`、`review.missing_for_cause`、`review.step_malformed`、
`next.malformed`、`next.unbound`、`next.dangling`、`next.risk_missing`。

`scripts/result_analysis.py` 的无网络计算对同一源文件及 spec 是确定性的，不引入随机数。
`reproducibility` 保存响应公式版本、源文件 sha256、spec sha256。复算需要保留列映射及
输入；Workbook/MAT 转换仍受所述依赖/结构范围限制，不能用纯 Python 标准库复制所有
科学分析工作。

## Runtime contract / 导出

原始 `output_contract` 的对象键或列表字段**全部保留**：已证明推导的字段优先生成；
输入明确要求附回的非大体积字段原样转发；不可推导者置 null 并写 limits。
键 `interpretation` 自然承载五段结果，`evidence_and_risks` 承载各级阈值、对照与风险，
`confirmation_items` 指向每个异常源与待复核任务。默认 main CLI 合法结果还写
`original-table.csv` 和 `original-records.json`。拒绝路径也产生 `result.json`，
无 Traceback，绝不少字段：通过 `--case` 获得原 case_id 与 output_contract。

本包不需要 Bench 才能运行正式任务。开发者可选自查：
`python scripts/bench_result_analysis.py`（18 场景，真 ZIP/XML workbook、分组异常、效应量、
paired 5 split、3 种 SPC、拒绝单位/重复对、契约确定性）；旧 27 场景仍独立验证，禁止把
自查写进正式工作流的必答步骤。

参考公开控制图机制：NIST/SEMATECH Engineering Statistics Handbook
<https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc31.htm>，其稳定参考、控制限、
3σ与非随机序列调查被实现成真实的基线筛选、序列 event 与 row 回指。
其它 IQR/MAD、OLS、效应量、配对统计和影响敏感性均在本包 `result_diagnostics.py` 中
可直接复跑，不依赖外站报告“得出结论”。 GITHUB_URL.txt 提供公开作品路径。

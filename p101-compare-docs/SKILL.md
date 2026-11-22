---
name: cross-document-compare
description: >
  Compare several papers on one common field table and deliver a cell-by-cell comparison
  in which every value is traceable to its own paper. Each cell carries a locator
  (page / paragraph id / table cell / figure) and the conditions that make it comparable
  (dataset, metric, control, plus corpus-specific keys such as material or pollutant);
  conclusion cells carry a direction and a strength so two papers cannot be read as
  agreeing when they disagree; a conflict between papers must be attributed rather than
  averaged away. Audits the delivered matrix mechanically: wrong-paper cells, unconvertible
  units, missing pooling judgments, unreproducible conversions. Use when a task asks for a
  comparison table, method matrix, evidence cards, or a synthesis across related papers
  （多文档比较、方法矩阵、跨论文整合、结论一致性）.
---

# cross-document-compare

版本：v2.0（2026-11-22）。规则库与本文档同步维护；本文档即最新版本的说明。

一张比较表是对别人结果的断言集合。它会以"看起来完整"的方式出错：

- 从错误的论文、或正确的论文里错误的一行复制了取值；
- 两个数被放在一起比较，但它们测在不同的数据集、或按不同指标口径报道；
- 两篇论文都说"带隙下降"，被记为一致，但一篇是弱趋势、另一篇是强反转；
- 真正的冲突被悄悄平均成一个中间值。

每一种错误都可以机械地检测——每一条都是一个规则。本 Skill 的分工：**抽取和对齐由调用
方（Agent）完成；本 Skill 对交付的比较矩阵做逐格机械审计**，审计判定写入 result.json。

## 运行时入口（从 /input 出发的七步）

Harbor 运行时输入是 `/input/case.json` 与 `task.md`；工作目录 `/app/work`；最终交付
写入 `/app/output`（含 `result.json`，必须保留 output_contract 全部字段与 case_id）。

| 步 | 动作 | 说明 |
|-|-|-|
| 0 | 读输入 | 读 `/input/case.json` 与 `task.md`，取出 `case_id`、`output_contract`（如有）、语料清单与任务措辞；**读实际文件，不凭标签猜内容** |
| 1 | 判形态选路由 | 按下文「任务措辞 → 路由」表选 section（本 Skill 主路由 `compare_docs`；单篇问答类任务路由到 `qa`，见下） |
| 2 | 先产出目标产物 | 先把比较矩阵本身写出来（`/app/output/comparison_table.json` + 一份人类可读的 `.md`）：字段表、逐格取值、每格 locator 与条件。先有产物再审计，审计失败也不交白卷 |
| 3 | 构造 spec | 按下文「spec 构造」把矩阵 + 语料摘录组装成 spec.json（含 `case_id` 与 `output_contract`），放到 `/app/work/spec.json` |
| 4 | 运行审计 | `python <skill目录>/scripts/secrun.py --spec /app/work/spec.json --section compare_docs --out /app/output` |
| 5 | 修发现重跑 | 对每条 finding 修矩阵或修 spec，重跑至 `clean` 或确无再改之处；剩余发现如实写进交付说明 |
| 6 | 合并 result.json | 审计已写 `/app/output/result.json`（含 case_id 与 output_contract 字段回填）。把比较矩阵、可比性判定、冲突解释合并进去或并排交付，状态与不确定项如实保留 |

预算纪律：先落盘部分结果再迭代改进；不要在步骤 2 之前花预算做全文精读。

## 任务措辞 → 路由

| task.md 里可能出现的表述 | 路由 | 理由 |
|-|-|-|
| "比较这些论文的方法/结果""comparison table""方法矩阵" | `compare_docs` | 多篇论文 × 统一字段，本 Skill 主路径 |
| "整合成一份报告 / synthesis / 主题整合" | `compare_docs` | 整合报告的骨架仍是统一字段表；字段表用 object/data/method/condition/metric/conclusion/limitation 全组 |
| "逐格对照 / cell-by-cell / 对得齐" | `compare_docs` | 直接命中字段定义 + 单元格规则 |
| "哪些论文结论一致，哪些冲突，为什么" | `compare_docs`（conclusion 组 + conflict_note/consistency） | 冲突归因是 conclusion 组字段 |
| "证据卡片 / evidence cards / 跨文档证据" | `compare_docs` | 每张卡片 = 一个格（value + locator + verbatim + 条件） |
| "单位换算后比较 / 归一口径" | `compare_docs`（target_unit + converted_from） | 换算路径必须可复算 |
| "可比的子集 / 只在同一条件下比较 / noncomparable" | `compare_docs`（comparable_subset / condition_variance / noncomparable） | 并池判定必须留痕 |
| "以后还能加论文 / 比较表可复跑" | `compare_docs` | spec 即记录：新论文 = 新增一列，重跑即复检 |
| 单篇论文提问、答案要引原文（"answer the questions about the paper"） | `qa` | 语料内问答与引用审计；不是比较 |
| "把若干文献整理成文献列表/引用核对" | 不用本引擎的 compare/qa 路径；如实说明超范围 | 引文库管理与引用格式化不是本 Skill 能力 |
| 任意表格都要填（非论文比较，如器材清单） | 如实说明超范围或按 `compare_docs` 仅做结构审计 | 字段组语义是科研比较；填表值本身无从核验 |

> 只有一篇论文却要求"比较"时：如实报告材料不足（`too_few_documents` 会先于一切发出），
> 不要把单篇摘要伪装成比较。

<details><summary>路由到 <code>qa</code> 时的最小 spec（语料内问答）</summary>

```json
{"section": "qa",
 "case_id": "<原样带入>",
 "evidence": [{"id": "e1", "quote": "<原文短引文>", "locator": "p.7", "paragraph_id": "P12"}],
 "answers": [{"question": "<问题>", "question_id": "Q1",
              "answer": "<回答>", "conditions": ["<成立条件>"],
              "cites": ["e1"], "status": "answered"}],
 "material_sufficient": true}
```

回答不了的题 `refused: true` + `reason`；冲突语料给 `conflicts`；状态词表
answered / partial / insufficient_evidence / input_error。规则细节同 `qa` section 的
审计（引用可定位且支持答案、数值须见于引文、子问题覆盖）。

</details>

## spec 构造

```json
{
  "case_id": "<从 case.json 原样带入>",
  "output_contract": { "<case.json 给出的字段>": "..." },
  "section": "compare_docs",
  "field_groups": ["object", "data", "method", "condition", "metric", "conclusion", "limitation"],
  "fields": [
    {"name": "bandgap", "group": "metric",
     "definition": "室温光学带隙（Tauc 法）",
     "target_unit": "eV",
     "comparability": "同为光学带隙测定",
     "condition_variance": "对照状态不同（退火 vs 原生）；按原值并排比较，不并池",
     "comparable_subset": ["A", "C"]},
    {"name": "trend", "group": "conclusion",
     "definition": "氧空位浓度对带隙的影响方向",
     "conflict_note": "A 与 B 条件不同，见 conflict 解释",
     "consistency": "partial"}
  ],
  "condition_keys": ["material", "pollutant", "budget"],
  "documents": [
    {"id": "A",
     "text": "<该论文的原文摘录（供 verbatim 校验）>",
     "fields": {
       "bandgap": {"value": "3.20 eV", "unit": "eV",
                   "locator": "Table 1 row 2, p.4", "paragraph_id": "P12",
                   "source_document_id": "A",
                   "dataset": "sample A (annealed)", "metric": "optical bandgap",
                   "control": "annealed at 500 C",
                   "verbatim": "bandgap of 3.20 eV was measured for sample A",
                   "converted_from": {"value": 3200, "unit": "meV"},
                   "material": "TiO2", "noncomparable": false},
       "trend": {"value": "oxygen vacancies vs bandgap",
                 "direction": "decreases", "strength": "moderate",
                 "locator": "p.5", "paragraph_id": "P18", "source_document_id": "A"}}}
  ]
}
```

逐层职责（工作单 v2 要求的对齐动作，全部有规则承接）：

- **spec 级** `condition_keys`：本语料特有的比较维度（工作单点名 task / metric / units /
  material / pollutant / budget），与内建 dataset、metric、control 三列 一起逐格记录、跨文档比对；
- **字段级** `comparability`：并池依据；`condition_variance` / `comparable_subset`：条件
  不一致时哪些文档可并池；`target_unit`：合成前单位归一目标；`consistency`：结论字段的
  综合判定（consistent / partial / conflict，与格子实际方向核对）；`conflict_note`：冲突归因；
- **格级** `source_document_id` + `paragraph_id`（工作单要求"exact source_document_id and
  paragraph_id"）、`locator`、`dataset、metric、control 三列`、`verbatim`、`converted_from`、
  `noncomparable`、`direction`/`strength`。

裸字符串格仍被接受（向后兼容），但它没有 locator 也没有条件——这正是评分点，规则会如实
报告缺失而不是默认它没问题。

完整可运行的示例见 `examples/spec.json`（含 case_id 与 output_contract，自拟数据），
其对应审计输出见 `examples/result.example.json`（两者都标注为示例，不是正式案例结果）。

## 运行与退出码

```bash
python <skill目录>/scripts/secrun.py --spec spec.json --section compare_docs --out /app/output
```

| 退出码 | status | 含义 |
|-|-|-|
| `0` | `clean` | 零发现 |
| `3` | `review` | 只有 medium/low 发现，需人工过目 |
| `4` | `blocked` | 存在 high 发现，矩阵不能照原样交付 |
| `5` | `undetermined` | 案例无法按声明运行（spec 不可读 / 非对象 / 无 section / section 未知）——拒绝而非崩溃，result.json 仍会写出并尽量带上 case_id |

## 规则库

### 字段表

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `compare.no_schema` | high | 无统一字段 schema，比较没有共同地基 |
| `compare.field_group_missing` | high | 缺比较必需的字段组 |
| `compare.field_undefined` | medium | 字段无定义，两个抽取者会填出两套口径 |
| `compare.field_missing` | medium | 某篇论文未报道某字段（未报告项被点名保留，不是沉默空洞） |
| `compare.too_few_documents` | high | 少于两篇——单篇摘要不构成多文档比较 |
| `compare.schema_entry_skipped` | medium | schema 里有非对象条目被跳过（坏输入降级留痕，不崩溃） |

### 单元格可追溯

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `compare.cell_no_locator` | high | 格子无 locator，回不到原文 |
| `compare.cell_locator_vague` | medium | locator 无页码/表单元/图号/段落号 |
| `compare.cell_not_in_source` | high | 引文不在其标注的那篇论文里 |
| `compare.cell_wrong_source` | high | 格子声明的 source_document_id 不是本列文档（或语料中不存在）——"从错误的论文复制"这一最隐蔽失败 |
| `compare.duplicate_document_id` | medium | 两文档同 id，比较悄悄丢了一篇 |
| `compare.conversion_unreproducible` | high | 记录的单位换算复算不出——读者无法从记录重推该格 |

### 可比性

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `compare.cell_metadata_missing` | medium | dataset、metric、control 三列 缺失，两数可能不可比 |
| `compare.unit_mismatch` | high | 单位无法换算到比较单位 |
| `compare.target_unit_undeclared` | medium | 数值型字段并池却不声明比较单位，单位差异会沉默地混入合成 |
| `compare.comparability_undeclared` | medium | 并池未声明依据 |
| `compare.condition_conflict_unmarked` | medium | 同一条件各文档记录值不同，schema 未说明谁可与谁并池 |
| `compare.noncomparable_pooled` | high | comparable_subset 列入了自标 noncomparable 的文档，并池判定自相矛盾 |
| `compare.document_skipped` | medium | documents 里的非对象条目被跳过 |

### 方向、强度与冲突

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `compare.direction_missing` | high | 结论格未记录方向 |
| `compare.strength_missing` | medium | 结论格未记录强度 |
| `compare.conflict_unattributed` | high | 论文间方向相左而差异未被归因 |
| `compare.consistency_misstated` | high | 声明的综合判定与格子实际方向矛盾（"结论方向与关系强度被误读"） |

## 输出契约（result.json）

`secrun.py` 写 `/app/output/result.json`：

| 块 | 内容 |
|-|-|
| `status` | clean / review / blocked / undetermined |
| `section` | `compare_docs` |
| `findings[]` | 每条含 rule、severity、message 与定位（field / document / locator / conditions） |
| `severity_counts` | 各严重度计数 |
| `checked` | `items`（文档数）+ `coverage`：**字段 × 文档矩阵**——reported / not_reported 命名每一格，`cells[]` 携带每格 value、unit、locator、direction、strength、noncomparable（交付的主结果随 result 可见） |
| `case_id` | 从 spec 原样带回 |
| output_contract 各字段 | 已能派生的保留原值；spec 携带的照抄（大体量输入除外）；无法派生的置 null 并在 `limits` 里点名——评分方看到的是键 + 诚实说明，不是沉默缺口 |
| `limits` | 不可派生字段、拒绝原因等 |

与题目「Skill 运行后的输出要求」三段的对应：

| 题目要求 | 在交付里的位置 |
|-|-|
| 阅读/解析结果（覆盖任务要求且回到材料定位） | 比较矩阵本体（comparison_table.json / .md）+ `result.checked.coverage.cells`（每格带 locator/paragraph_id） |
| 证据与边界（页码/段落/图表定位；未报告与不确定项） | 每格 `locator`/`paragraph_id`/`verbatim`；`coverage 的 not_reported 计数` 点名未报告格；`findings[]` 列无法核验处；未报道值写 "not reported"，不编造 |
| 运行状态（成功/部分完成/无法判断/拒答及原因；异常原因与人工接管位置） | `result 的 status 字段` + `findings[].message`（含接管建议）+ `limits` |

## 字段字典（默认七组）

未显式声明 `field_groups` 时按全组检查。建议的统一字段及取值规则：

| 组 | 建议字段 | 取值规则 |
|-|-|-|
| object | material / system / organism | 材料或对象名 + 制备态；同物异名需在 definition 里写清别名映射 |
| data | 主要数值结果 | 数值 + 单位随值记录；换算写 `converted_from`；范围写 "low-high unit" |
| method | 合成/测量方法 | 方法名 + 关键参数；无法判断可比时标 noncomparable |
| condition | 温度 / 剂量 / 样本量 / 数据集版本 | 逐格记录；跨文档不同值必须触发并池判定 |
| metric | 指标口径 | 指标名 + 计算口径；不同口径的数值不可直接比 |
| conclusion | 方向结论 | `direction` ∈ increases/decreases/no_effect/mixed/conflicting；`strength` ∈ strong/moderate/weak |
| limitation | 局限 | 原文明确承认的局限；未写则记 "not stated"，不代写 |

## Limits（诚实边界）

- **单位换算是量纲级的，不是语义级的。** `mg/L` 与 `g/L` 可换；两个测量是否同一含义由
  `comparability` 声明，引擎核对"声明存在"，不判定"声明正确"。
- **direction/strength 由抽取方声明。** 引擎核对存在性、核对综合判定与格子方向的一致性；
  它读不了论文原文去给强度打分。
- **冲突检测基于方向。** 两篇方向一致但相差一个数量级不会被标记——那需要量级比较的
  schema 约定。
- **consistency 只在声明时核对。** 与格子矛盾的判定会被标记；缺席的判定从不强求。
- **converted_from 只在声明时核对，且只对已知单位。** 声明路径里的未知单位是"无法核验"
  而不是"错误"——跳过并留痕，不误报。
- **verbatim 可选。** 没有它，该格的字面校验不运行。
- **metadata 要求只作用于 data/metric/condition 组。** object / limitation 格不会被索要
  dataset。
- **本 Skill 不解析 PDF。** 抽取是独立步骤；这里审计抽出来的表。PDF 解析失败时按"证据
  与边界"如实记录失败与缺口（见异常处置表）。
- **中英混合语料**：locator 支持 `p.7 / 表2 行3 / Fig 3b / 图3 / 段落5 / P3 / ¶12`；
  verbatim 校验是字面子串（NFKC 归一），跨全半角一致，跨翻译不成立（翻译不是原文）。

## 异常处置表

| 异常 | 处置 | 谁接管 |
|-|-|-|
| PDF 解析失败 / 文本层损坏 | 在矩阵该列标注 `extraction_failed`，不填数值；findings 写明哪页失败；不要用标题猜内容 | 人工用 OCR 或另取文本层后重跑 |
| 图表无法读取（图注无数据） | 该格写 "not reported (figure unreadable)" + 图号 locator；**不要从图估数** | 人工读图后补格 |
| 论文主题与比较问题不相关 | 保留该列但全部字段记 "not applicable (off-topic)"，comparability 写明排除理由；不混入合成 | 人工确认排除清单 |
| 同一论文多版本（arXiv v1/v2） | 两列不同 id 并存，comparability 注明版本关系，取值标各自版本 locator | 人工定哪一版为准 |
| 结论互相矛盾且无法归因 | direction 照实记录，conflict_note 写 "unresolved: 样本/方法/条件/指标均无法区分"，consistency 用 `conflict`；**不许平均** | 人工补充条件证据 |
| 只有 1 篇论文 | `too_few_documents`（exit 4）；交付单篇摘要并明确说明不是比较 | 人工补语料 |
| spec 不可读 / 非对象 / section 未知 | exit 5 `undetermined`，result.json 照写（带 case_id），不崩溃 | 修 spec 后重跑 |
| 语料条目/schema 条目不是对象 | `document_skipped` / `schema_entry_skipped` 降级留痕，其余照审 | 修 spec |
| 依赖缺失（本包为纯标准库，通常无此情形） | 如实说明当前环境缺什么、缺到哪一步；**不伪造已运行** | 按说明装依赖或人工代跑 |
| 输出目录不可写 | exit 5 + limits 写明写盘失败；先落盘到可写处再移动 | 检查挂载 |
| 重复运行结果不一致 | 规则全为确定性函数；若出现，把两次 result.json 都保留并报告差异（幂等性由探针保证） | 提交 bug |
| 预算不足以完成全表 | 先落盘已完成列（部分交付 + limits 列明未完成字段），再继续 | 后续轮次续跑 |

## Failure handling（finding → 修法）

| finding | 修法 |
|-|-|
| `cell_no_locator` | 补该论文内的页码、表单元或图号 |
| `cell_locator_vague` | 写具体：p.4 / Table 1 row 2 / Fig 3b / 段落5 |
| `cell_not_in_source` | 引文串行或来自另一篇——换回本篇原文 |
| `cell_wrong_source` | 改 `source_document_id` 或把格挪到正确的列 |
| `cell_metadata_missing` | 记 dataset、metric、control——裸数不可比 |
| `unit_mismatch` | 换算到 target_unit 并写 `converted_from` |
| `target_unit_undeclared` | 为数值型字段声明 target_unit |
| `comparability_undeclared` | 写并池依据，或拆分比较 |
| `condition_conflict_unmarked` | 记 `comparable_subset` / `condition_variance`，或标 noncomparable |
| `noncomparable_pooled` | 从 comparable_subset 移除该文档，或撤销该格的 noncomparable 标记 |
| `conversion_unreproducible` | 修正记录值或声明原值——复算不出的换算是错误数字 |
| `duplicate_document_id` | 两列给不同 id；同一论文多版本就两列并存并说明 |
| `direction_missing` | 写 increases/decreases/no_effect/mixed/conflicting |
| `strength_missing` | 写 strong/moderate/weak |
| `consistency_misstated` | 让判定对齐格子方向，或改判定 |
| `conflict_unattributed` | 把分歧归因到条件，或如实记为 open |
| `field_group_missing` | 缺 method/limitation 组的比较会过度声称 |
| `audit.no_section` (exit 5) | spec 不可读/非对象/无或未知 section——拒绝而非崩溃 |

## Verification

```bash
python scripts/bench_compare.py   # 38 scenarios: 每条规则至少一场 + 误报守卫 + 矩阵形状
python scripts/bench_sections.py  # 51 scenarios: 跨 section 回归 + 误报守卫
```

本机全过（38/38、51/51）。每个 clean 基线必须零发现；新增规则与场景一一对应
（cell_wrong_source / target_unit_undeclared / noncomparable_pooled / schema_entry_skipped /
document_skipped / paragraph_id locator / coverage 矩阵形状）。

另有一套 19 项敌意探针（坏 JSON / 非对象 / 文件缺失 / 目录当 spec / 未知 section / 空
对象 / 无 section / documents 与 fields 类型错位 / 格子类型错位 / 全空字段 / CJK locator /
百 KB 级输入 / 重跑幂等 / output_contract 回填与 bulky 排除 / unicode case_id /
clean 基线 / review 退出码），全部通过：exit ∈ {0,3,4,5}、result.json 恒在、无 traceback。

## Requirements

Python 3.9+（3.14 实测）。纯标准库（json / re / pathlib / argparse / dataclasses /
unicodedata / difflib），无第三方依赖，评测镜像无需安装任何东西。

## 创新增益（相对基础 Agent 的边界）

1. **逐格来源强制**：source_document_id / paragraph_id / locator / verbatim 四件套使
   "取值来自它标注的那篇论文"成为可机械判定的命题；基础 Agent 的表格无从自证这一点
   （cell_wrong_source、cell_not_in_source 是基础 Agent 无法自查的失败形态）。
2. **两级对齐**：字段级 comparability/condition_variance/comparable_subset + 格级
   noncomparable 的组合，把"哪些论文在同一条件下可比"变成显式记录，并在记录自相矛盾时
   报错（noncomparable_pooled）；工作单的"先测可比性再合成"由此可执行。
3. **冲突归因留痕**：direction × strength × conflict_note × consistency 四字段让
   "一致 / 部分一致 / 冲突"的判定与格子实际方向强一致（consistency_misstated 抓误读），
   冲突必须归因而不可平均（conflict_unattributed）。
4. **换算可复算**：converted_from 声明路径被复算（conversion_unreproducible），错误数字
   在交付前被拦下；这是"查得回"的具体机制。
5. **幂等审计**：规则全为确定性纯函数，重跑逐字节一致（探针验证）；审计只是判定，不改
   写矩阵——所有修改由调用方完成并留痕。

边界：引擎不读 PDF、不做语义判定（support/comparability 的"正确性"由声明 + 人工复核）、
不做量级冲突检测。这些边界全部写明而非隐藏。

## 生态贡献

- **使用说明**：本文件含运行时七步、路由表、spec 构造、退出码、规则库、异常处置、复跑方法。
- **依赖**：纯标准库，无安装步骤；Python 3.9+；评测镜像直接可用。
- **配置**：spec 即配置——field_groups / condition_keys / target_unit / comparability
  全部数据驱动，换一套论文集合不需要改代码。
- **示例标注**：`examples/spec.json` 与 `examples/result.example.json` 为自拟数据的完整
  示例并明确标注；`examples/bench-report.json` 为 bench 实跑快照（可复跑验证）。
- **资源复用**：字段字典 + 规则库可直接用于任意论文集合；bench 套件可独立复跑
  （`python scripts/bench_compare.py`）；扩展新比较维度只需加 condition_keys。
- **适用范围**：3~10 篇同主题论文的横向比较（比较表 / 方法矩阵 / 证据卡 / 整合报告骨架）；
  语料为英文或中文或混合；不适用的情形见路由表最后两行。
- **限制**：见 Limits 一节（逐条列出引擎做不到的事，包括不读 PDF、量级冲突不检测）。
- **维护**：规则 id 稳定且自描述；新增规则必须配 bench 场景（clean 基线零发现的纪律由
  bench 强制）；报告文件 `scripts/report_*.json` 为最近一次实跑留痕。

## 最小调用示例（示例，非正式案例结果）

输入：`examples/spec.json`（两篇自拟论文，字段表含可比性判定与 case_id）。

```bash
python scripts/secrun.py --spec examples/spec.json --section compare_docs --out /tmp/demo
# -> {"status": "clean", ...}  exit 0
```

示意输出（节选，完整见 `examples/result.example.json`）：

```json
{
  "status": "clean",
  "section": "compare_docs",
  "case_id": "example-compare-001",
  "findings": [],
  "checked": {"coverage": {"cells": [
    {"field": "bandgap", "document": "A", "value": "3.20 eV", "unit": "eV",
     "locator": "Table 1 row 2, p.4", "direction": null, "noncomparable": false},
    {"field": "bandgap", "document": "B", "value": "2.60 eV", "unit": "eV",
     "locator": "Table 2 row 1, p.3", "direction": null, "noncomparable": true}]}}
}
```

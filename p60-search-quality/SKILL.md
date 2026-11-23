---
name: search-quality
description: >
  文献研究质量评价：对获授权的本地论文全文、摘要、结构化章节、表格单元格和
  Crossref/Europe PMC/出版方响应执行量表驱动的“维度—判断—证据—等级”评价。
  区分研究设计、样本与测量、方法透明度、偏倚、统计与结论一致性、可复现性、
  报告完整性和来源版本；每条证据保留原句/字段、source_path、页码或章节与
  可切片偏移。按研究类型应用不同检查点，缺证据必须弃权，保留人工复核和
  分歧裁决。适用于研究质量辅助评价、纳排后的质量分层和可复核评价台账；
  不用于替代同行评审、临床/政策决策、全球新颖性判断或无来源的全文推断。
---

# 文献研究质量评价：证据先于等级

## 1. 本 Skill 实际交付什么

主入口 `scripts/quality_cli.py` 对每篇实际提供的文献生成：

- `appraisals[*].quality_table[]`：研究设计适配的维度、判断、理由、证据、风险等级和复核入口；
- `candidate_set[]`：候选文献、元数据、来源、相关性依据、质量等级和独立的人工纳排状态；
- `检索结果`：候选集、排序/筛选结果、排序依据、来源定位和遗漏说明；
- `证据记录`：完整评价表、版本化量表、真实查询/迭代记录、证据台账和人工复核记录；
- `状态说明`：已完成、未完成、冲突、权限问题、空结果和不确定性。

相关性与方法质量分开报告。标题/摘要词重叠只叫 lexical relevance，不能用质量高分替代相关性，也不能把期刊、发表状态或结果显著性当作研究质量代理。

**关键边界：**本工具是“来源约束的报告与偏倚风险辅助量表”，不是全文语义理解器，也不是 RoB 2、ROBINS-I、CONSORT 或 STROBE 的官方计分实现。报告缺项导致 `insufficient`，不会自动推断研究实施很差；报告齐全也仍需人工判断实施是否恰当。

## 2. 六步运行时入口

### 第一步：读取真实案例并固定契约

读取 `/input/case.json`、`task.md` 及运行环境的 `environment/resources.yaml`。确定科研问题、文献类型、授权材料、已有查询/参考图/增量导入状态和 `output_contract`。最终 `/app/output/result.json` 必须含顶层 `case_id` 和原契约每个字段。

### 第二步：只从获授权材料建立文本单元

支持内联 `documents` / `studies` / `corpus` / `records`，或由案例声明相对/绝对材料路径。材料可为 JSON、JSONL、TXT、MD；路径相对 `case.json`，其次 `/input`。支持的科学记录包括：

- `full_text` / `fullText` / `body` / `content` 字符串；
- `text`（明确按 supplied excerpt 处理，不冒充全文）、`abstract` / `abstractText`；
- `sections`、`pages`、`paragraphs`；
- `tables[*].caption/cells/rows`，保留表号及单元格 `source_path`；
- Crossref `message`、Europe PMC `resultList.result` 和常见元数据字段。

PDF 本身不是本评价器的文本格式。先用平台 PDF 文本/OCR 工具生成带来源页码的 JSON/TXT，再运行本 Skill；不能把二进制 PDF 或文件名当作已读全文。访问受限记录不进入索引；空结果只描述本地快照，绝不进行未声明的实时联网补全。

### 第三步：先识别设计，再选择量表

支持 randomized trial、非随机干预、cohort、case-control、cross-sectional、systematic review、diagnostic accuracy、qualitative、computational、protocol 和 unknown。结构化 `design` 与正文设计声明冲突时同时保留，不能由标签静默覆盖原文。DOI 中的一段 `RCT` 等标识符字符串不得用于设计判断。

| 设计 | 通用维度之外的特定检查点 |
|-|-|
| randomized trial | 随机序列、分配隐藏、盲法、缺失/退出 |
| 非随机干预、队列、病例对照、横断面 | 混杂、对象选择、对照、缺失数据；非随机干预另查盲法 |
| systematic review / meta-analysis | 检索覆盖、双人筛选/提取、发表偏倚与异质性 |
| diagnostic accuracy | 选择、参考标准、病例流程/间隔、盲法 |
| qualitative | 选择、反思性、编码/三角互证/饱和度 |
| computational | 验证/数据泄漏、基线、公平比较 |
| protocol | 不评价尚未产生的结果、统计结论和结论一致性 |
| unknown | 使用通用选择/缺失数据检查，设计维度和总体等级保持不确定性 |

### 第四步：运行真实评价 CLI

平台安装后的标准调用：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/quality_cli.py \
  --case /input/case.json --out /app/output
```

本包示例的本地等价命令（从包根目录执行）：

```bash
python -I -X utf8 scripts/quality_cli.py --case examples/case.json --out ./_run_example
```

程序先写诚实的早期 partial，成功后覆盖。只有实际完成的文档才进入 `已完成`。所有运行均由输入决定，不进行远程请求，不写墙钟时间或虚假运行指标。

### 第五步：逐条复核证据与人工分歧

`appraisals[*].review_queue[]` 聚合缺证据和待复核项。人工裁决使用真实的 `review_decisions`：

```json
[{"doc_id": "study-01", "dimension": "confounding",
  "judgement": "high", "reviewer": "reviewer-B",
  "rationale": "Unadjusted treatment choice is confounded by indication",
  "evidence_ids": ["valid-id-from-the-evidence-ledger"]}]
```

必须提供有效 doc/dimension、允许的判断、reviewer 和 rationale；给出的 evidence id 必须存在。应用后保留 `engine_judgement`、人工理由、前后等级及 `change_records`，原文证据不可被人工决定改写。`insufficient` 也是正式判断，不是留给模型补写的空格。

### 第六步：按契约汇总并重放

核对：所有引文定位可切片、四类 rubric 覆盖、设计与检查点相符、候选/排除/权限遗漏完整、相关性与质量未混用、无证据字段为 null 且有 limits。相同输入、相同后端下 `result.json` 应逐字节一致；如不同，停止交付并查输入指纹和源代码版本。

## 3. 判断与总体分级规则

| 等级 | 单维判定 | 不允许的推断 |
|-|-|-|
| `low` | 声明的全部证据组均存在，且未见 concern/contradiction | 不是“已被同行评审”或“研究必然无偏倚” |
| `some_concerns` | 存在明确的开放标签、未调整混杂、便利样本、数据泄漏等证据，或跨过已声明数值复核阈值 | 不只凭缺少一句关键词就升级 |
| `high` | 有直接撤稿声明，或同句统计/设计与结论存在明确冲突 | 不从“不显著”推导研究无效 |
| `insufficient` | 缺必需证据、报告不明、只有摘要、只有节选或设计不明 | 不补成 low，也不把缺报告等同于高偏倚 |
| `not_applicable` | 供人工/设计映射表达不适用 | 不用随机试验规则硬套观察性研究 |

总体顺序：任一 high → high；否则任一 some → some_concerns；否则任一必需维度 insufficient → insufficient；全部适用维度 low 才为 low。**abstract-only 强制总体弃权，protocol 对结果质量弃权。**

特殊可计算检查只做其证据允许的事情：

- 同一句中的 `p = 0.20 + statistically significant` 或 `p < 0.05 + not significant` → 直接矛盾；
- 观察性设计结论中的明确 `causes/prevents/eliminates` → 因果结论需要额外论证，不能直接沿用 RCT 因果口径；
- 报告 attrition >20% → 触发数值复核，仍需检查组间方向和差异，不自动证明偏倚方向。

## 4. 输出契约：rubric 三段逐项对应

| rubric 原词 | result.json 落点 | 核验方式 |
|-|-|-|
| `检索结果` | `候选文献`、`排序/筛选结果`、`元数据`、`来源定位`、`遗漏说明` | 每条有来源、相关性依据、独立质量等级和纳排边界 |
| `证据记录` | `质量评价表`、`评价量表`、`查询与迭代`、`证据定位`、`复核记录` | 文本 quote == source unit `[start:end]`；结构化字段保留精确 source_path |
| `状态说明` | `运行状态`、`已完成`、`未完成`、`空结果`、`冲突`、`权限或接口异常`、`不确定性` | 不补造文献/全文；缺证据与失败分别说明 |

`output_contract` 支持字段名列表、字符串、字段名对象，以及带 `field/name/key` 的对象列表。保留原始 `output_contract` 和 `output_contract_fields`。每个字段严格遵守 **引擎值 > case 显式携带值 > null + limits**；缺值进入 review，不能用 case 里的伪造 `status` 覆盖引擎状态。**拒绝路径也执行相同契约回填**，能确定的 case 值保留，不能确定的为 null。

### 运行状态与退出码

| status | exit | 含义 |
|-|-|-|
| clean | 0 | 所有文档可按声明规则评价，无 medium/high 未决项 |
| review | 3 | 有可用结果，但全文/设计/元数据/条目或契约仍需人工复核 |
| undetermined / blocked | 5 / 4 | 无法运行；全部材料权限阻断为 4；`case_not_object` 也是 4 |
| 命令行用法错误 | 2 | argparse 层用法错误，不伪装为科学评价 |

## 5. 最小合成示例

`examples/case.json + studies.json` 是本地合成回归材料，不是组织方案例或预制答案。示例包含一篇报告完整的 RCT 和一个摘要型预印本队列记录；后者同句 p 值/显著性冲突、观察性因果过度结论都被定位，但总体仍因 abstract-only 为 insufficient。

输出节选（形状说明，非正式测评）：

```json
{"case_id": "quality-example-v2", "status": "review",
 "appraisals": [{"doc_id": "quality-rct-clean", "overall": {"grade": "low"}},
                {"doc_id": "quality-cohort-abstract", "coverage": "abstract_only",
                 "overall": {"grade": "insufficient"}}],
 "output_contract_fields": ["case_id", "检索结果", "证据记录", "状态说明", "uncertainty", "change_records"]}
```

旧的 `search_cli.py + search.py` 仅保留为布尔词项/索引重放工具，不是本题的自动质量评价器。不要再用“若干 token 同时命中 = 低风险”的调用方式交付质量结论。

## 6. 规则与异常索引

| rule | 默认处置 |
|-|-|
| `quality.case_unreadable` | case 缺失/坏 JSON/编码或 IO 不可读，exit 5 + result.json |
| `quality.case_not_object` | case 非对象，exit 4 + result.json，不 traceback |
| `quality.unknown_section` | 非 quality/appraisal/quality_appraisal/research_quality/search-quality/文献研究质量评价，exit 5 |
| `quality.no_documents` / `documents_invalid` | 无文档或 documents 不是列表，exit 5 |
| `quality.material_missing` / `material_unreadable` / `material_shape` / `material_unsupported` | 声明材料缺失、坏 JSON、形状不符或类型不支持，exit 5 |
| `quality.document_invalid` / `document_no_text` | 单文档形状错误或没有可评价内容，exit 5；混合批次进入 omissions |
| `quality.access_blocked` | 全部记录受限，exit 4，受限原文不序列化 |
| `quality.records_omitted` | 重复、局部无效或局部受限，review 并逐条命名 |
| `quality.full_text_unavailable` / `design_unknown` / `design_conflict` / `review_required` / `domain_high` | 评价完成的 review/high 发现，保留具体 doc 和维度 |
| `quality.contract_field_missing` | 契约字段给 null、limits 和 review，不编造值 |
| `quality.internal_error` | 未预见异常封装为 exit 5 + result.json，控制台不泄漏 traceback |

## 7. 真实参考方法及落地边界

- CONSORT（EQUATOR）提示 RCT 随机化、分配隐藏、盲法、结局、样本量、统计、流程、局限、资助和注册等报告检查点；其页面同时明确 **reporting guidelines are neither design nor quality appraisal tools**。本包据此外置证据组，未把报告齐全直接写成实施无误。
- STROBE 提供队列、病例对照、横断面的设计、对象、变量、偏倚、样本、缺失数据、结局、局限和资助报告框架。本包用设计适配的检查点区分报告缺失与偏倚判断。
- Cochrane RoB 2 官方页区分平行、整群、交叉试验工具。本包不是官方 RoB 2 Excel 的复刻，遇到整群/交叉/特殊试验必须人工选适用量表，不能套用本通用规则。
- 本地高分包 p59/p69 的可复用落地：真实 CLI 黑盒探针、顶层 case_id、复杂 output_contract 形状、引擎/案例/null 优先级、无 traceback、同输入字节重放。

## 8. 限制

- 词与数值规则用于发现和定位证据，会漏掉 paraphrase 和新领域术语；阴性表述需要人工阅读完整上下文。
- 不重跑统计模型，不全面检查所有 CI/P 值，不验证数据真伪，不从期刊层级推断质量，不确认网络最新版本、当前撤稿状态或全球覆盖。
- `full_text_available` 只表示材料明确声明/提供全文，不证明它完整无缺。图表图像不可读、OCR 错误、语言特殊、预印本版本均须单独声明。
- 自动 low 是报告证据规则结果；双人复核与真实 A/B 增益应在同一文献、同一量表、同一输入和同一预算下另行测量。本包不预填提升百分比或平台分数。

## 9. Verification

从包根目录运行（均为独立合成测试，不是官方分数）：

```bash
python -I -X utf8 scripts/bench_quality.py       # 旧词项引擎回归 8/8
python -I -X utf8 scripts/bench_appraisal.py     # 新质量评价场景 16/16，含 clean 零发现基线
python -I -X utf8 scripts/probe_quality.py       # 黑盒敌意探针 25/25，含退出码/契约/无 traceback/重放
python -I -X utf8 scripts/quality_cli.py --case examples/case.json --out ./_run_example  # exit 3，真实 smoke
python -I -X utf8 -c "import sys; sys.path.insert(0, 'scripts'); import appraisal, quality_cli; print(appraisal.SCHEMA_VERSION)"
```

`report_appraisal.json`、`report_hostile.json` 为回归报告；均不包含正式案例、白板或运行时间。第三轮 smoke 还应将同一 case 写到两个输出目录并比较 result.json；当前实现无时间戳、随机数和环境输出。

## 10. Requirements 与生态

- Python 3.9+；新评价器仅标准库，当前环境 Python 3.14 实测。
- `appraisal.py` 可导入：`appraise()`、`appraise_document()`、`identify_design()`。
- `quality_cli.py` 是正式 case 入口；`search.py/search_cli.py` 仅供旧布尔查询兼容。
- `examples/` 提供最小完整工作流；测试套件、量表定义、复核模板和失败边界均可独立复用。
- 不依赖作者个人文件、私有 API、手工补答案或网络可用性。

---
name: topic-evaluation
description: >
  科研选题与创新性评估的真实计算工作流。把模糊设想拆成可证伪问题，记录多源检索式、
  数据库/日期/字段与时间语言边界，逐篇比较 task/method/data/metric/conclusion 及不可比原因，
  对直接先例、改名机制、等价、常规适配、场景迁移、强基线和后续工作做创新碰撞审计，
  同时登记差异证据、反证、数据/算力/实验/时间/人员前提、成本、影响和失败回退。
  输出有界 go/conditional/pre-study/revise/undetermined 决策，不把检索不到写成全球首创。
  Use for research question definition, prior-art comparison, novelty collision audit,
  counter-evidence review, feasibility assessment and bounded proposal decisions.
  Do NOT use to claim global novelty, fabricate executed searches, or substitute for completed experiments.
---

# topic-evaluation：综合证据，也说明边界

正式入口是 `scripts/topicrun.py` + `scripts/topic_engine.py`。旧 `secrun.py` 只保留通用 proposal
文本审计兼容，**不是本题的正式选题评估入口**。新引擎直接生成研究产物、比较矩阵、证据矩阵、
创新碰撞表和契约化 `result.json`，而不是只检查一份预先写好的散文。

## 能做什么、不能做什么

- 能对**所给材料与声明检索范围**形成可复核的选题判断；不能联网补库、验证 DOI 是否真实存在或证明全球无人研究。
- `not_covered_in_declared_scope` 只表示声明范围内未直接覆盖；`P/A/M/U` 只表示原文/摘要/元数据/不可核验，不是研究质量评分。
- 前瞻性检索、固定语料和已执行检索分开记录。未执行来源的 `hit_count` 必须为 null，不能写 0。
- 创新碰撞与可行性是独立门：资源充足不能把已被覆盖的方法变成创新，创新也不能抵消关键数据缺失。

## 文件与产物

| 文件 | 真实职责 |
|-|-|
| `scripts/topicrun.py` | 正式 CLI；读取 spec/case，写全部产物与结构化拒绝 |
| `scripts/topic_engine.py` | 问题、检索、比较、碰撞、反证、可行性及独立分级决策 |
| `scripts/case_contract.py` | 原 case_id 和 output_contract 全字段直通 |
| `examples/topic-spec.json` / `examples/case.json` | 完整**合成**接口示例，非组织方案例答案 |
| `references/novelty_protocol.md` | 碰撞类型、P/A/M/U、决策等级和外部方法来源 |
| `references/comparison_template.md` | 旧版逐面模板；新矩阵在此基础上扩成每篇五字段+五行证据 |

成功后 `/app/output` 包含：

1. `topic_evaluation.md`：问题、检索、比较、创新、可行性、影响、风险、结论与不确定性；
2. `comparison_matrix.csv`：每篇工作的五维字段、可比性、不可比原因和证据 ID；
3. `evidence_matrix.csv`：逐字段原文 quote、精确 locator、来源、纳排理由和 P/A/M/U；
4. `novelty_audit.csv`：创新点×最近工作碰撞、同约束判断、剩余差异、反证与回应；
5. `result.json`：全部机读结果、决策等级、findings、artifacts SHA-256 和原平台字段。

## 六步运行时入口（交付路径，不含自测）

0. **读取真实输入。** 先读 `/input/case.json` 和 `/input/task.md`，保存 case_id 与 output_contract
   原始结构；再读全部论文、题录、约束和数据清单。PDF 必须用实际 PDF/OCR 工具提取，不能按文件名、
   领域标签或示例猜内容。建 `/app/work`、`/app/output`。
1. **先冻结问题和协议。** 在 `/app/work/topic-spec.json` 写 research_question、search_protocol 和已有
   works。真实检索已发生才用 `executed`；只有给定材料用 `fixed_corpus`；只设计检索式用
   `prospective`。每个来源分别保存 query、fields、coverage、searched_at/snapshot_date、filters。
2. **建立证据与比较。** 每篇 work 填五方面内容、decision、closest、comparable、verification，
   每个方面至少一条 `{aspect, quote, locator}`；尽量附 source_excerpt 让引擎验证 quote 为原文子串。
   排除项必须关联纳排条款。不可比时按方面写原因，禁止为了矩阵整齐而虚构对齐数值。
3. **碰撞与前提。** 每条 innovation_claim 对最近工作逐行写 nearest_comparisons；差异支持和反证都引用
   evidence_id。可行性五类前提逐项标 verified/assumed/planned/missing/unknown，假设必须有 validation；
   route 每步写 input/output/cost/risk/fallback。材料不足就保留 undetermined，不补造“已具备”。
4. **运行正式 CLI。** 在技能目录运行：

   ```bash
   python -I -X utf8 scripts/topicrun.py \
     --spec /app/work/topic-spec.json --case /input/case.json --out /app/output
   ```

   无原 case 文件时可用 `--case-id`，但正式平台应传 `--case`。引擎无需网络或第三方包。
5. **按发现修输入并重跑，最终核契约。** 先修错误定位、漏比较、未回应反证和未标假设；不得为消发现
   而添造来源、检索日期、命中数、实验结果或“无先例”。确认报告、CSV、result.json 一致；原 case 的
   case_id 覆盖 spec 自报值，output_contract 每个字段同名存在。推导不出的字段为 null 并写 limits。

## 输入规格（正式运行）

### 1. research_question

必须是对象，七项不可缺：`statement`、`object`、`variables`、`comparator`、`outcome`、
`expected_conclusion`、`falsification_condition`，另以 `scope` 限定数据集、时间、对象和外部效度。
预期结论必须写成待检验假设，不得伪装成已有实验事实。

### 2. search_protocol

```json
{
  "status": "fixed_corpus",
  "start_date": "2019-01-01", "end_date": "2026-11-24",
  "languages": ["English", "Chinese"],
  "inclusion_criteria": ["可判定的纳入条款"],
  "exclusion_criteria": ["可判定的排除条款"],
  "sources": [{
    "name": "OpenAlex snapshot", "database": "OpenAlex",
    "query": "TITLE_ABSTRACT:(pseudo label*) AND TITLE_ABSTRACT:(calibrat*)",
    "fields": ["title", "abstract"], "coverage": "2019-2026 frozen export",
    "snapshot_date": "2026-11-24", "filters": {"language": ["en", "zh"]}
  }]
}
```

至少两个独立来源才可能在合适条件下得到 `not_covered_in_declared_scope`；单来源会产生 review，
且不能支撑清晰 novelty gate。每个来源应有字段化/布尔化检索式，而不是关键词串。`executed`
还要求每个来源真实 `searched_at` 和非负整数 `hit_count`；其他状态出现命中数会被拒绝为高风险矛盾。

### 3. works 与 evidence

每篇 work 的字段：`id/title/doi/year/source/decision/inclusion_reason|exclusion_reason/closest/
closest_reason/verification/comparable/incomparable_reasons/task/method/data/metric/conclusion/
evidence/source_excerpt`。

- `decision`: include / exclude / undetermined；排除理由必须能回指标准。
- `verification`: P（原文及关键段）/ A（摘要）/ M（元数据）/ U（不可核验）。M/U 会留下不确定性。
- 每条 evidence：`{"aspect":"method","quote":"原文逐字段摘录","locator":"file.pdf p.4 Sec.2 ¶3"}`。
  可另给 `id`，默认是 `work_id:aspect`。同一方面的第二条证据必须显式给不同 id。
- `comparable=false` 时 `incomparable_reasons` 至少一项写清 task/data/metric/条件为何不能直接比较。
- `source_excerpt` 是可选但强烈建议的真实原文汇总；一旦提供，每条 quote 必须是其中逐字子串。

### 4. innovation_claims：支持创新与反证都进表

```json
{
  "id": "I01", "type": "method",
  "statement": "只陈述可比较的具体增量",
  "difference_evidence_refs": ["W002:method", "W002:conclusion"],
  "nearest_comparisons": [{
    "work_id": "W002", "collision": "none", "same_constraints": false,
    "remaining_difference": "已有工作是固定阈值且无校准约束；剩余差异仅限校准约束",
    "evidence_refs": ["W002:method"],
    "counterevidence_refs": [],
    "counterevidence_response": null
  }]
}
```

`type` 是 method/data/scene_transfer/conclusion_correction。`collision` 可取 direct_precedent、
renamed_mechanism、algebraic_equivalent、statistical_equivalent、routine_adaptation、scene_transfer、
followup_work、strong_baseline、none。直接先例/改名/等价且无剩余差异 ⇒ covered_by_prior_work；
有剩余差异 ⇒ specific_residual_difference（仍需差异证据）；只有常规适配/迁移 ⇒ 不能称方法首创；
有未回应反证 ⇒ contested_in_scope；检索、证据或比较不全 ⇒ undetermined。

### 5. feasibility 与 impact

`feasibility.prerequisites` 必须覆盖 data、compute、experiment、time、personnel。每项含
`id/category/requirement/status/critical/source/locator/assumption/validation/impact_if_false`。
verified 必须有 source+locator；assumed/planned 必须有 assumption+validation；critical missing/unknown
不会被隐藏。`feasibility.route` 每步必须有 input/output/cost/risk/fallback，可用 validates 回指前提。
`impact.scientific` 与 `impact.practical` 分别写科学和实际影响，影响不得写成已验证部署收益。

## 决策等级（真实计算，不是自报）

| grade | 触发逻辑 |
|-|-|
| `go_within_scope` | 问题、协议、碰撞、反证与全部关键前提通过，且没有待验证资源假设；仍不表示全球首创 |
| `conditional_go` | 有明确假设/计划，但每项都有验证和回退；只有验证通过才推进 |
| `pre_study_required` | 关键资源缺失，需先做最低成本预研究 |
| `revise_and_recheck` | 至少一条核心创新被直接覆盖，必须缩小或重写创新点后重检 |
| `undetermined` | 证据、检索、反证或关键前提不足；不强行给肯定/否定结论 |

引擎自身审计状态与决策等级分开：`clean` 表示结构审计无发现，不等于科学主张已获实验证明。

## Output contract 与三段映射

| Rubric 内容 | 本包实际交付 |
|-|-|
| 研究产物 | `topic_evaluation.md` + decision；四项交付为问题定义、已有工作比较、创新点识别、可行性判断 |
| 证据矩阵 | `evidence_matrix.csv` + `comparison_matrix.csv`；来源、纳排理由、五维比较、quote、locator 全贯通 |
| 不确定性 | 冲突/反证、偏倚、检索空白、未核实假设和无法确定项分别列出，结论不越过证据范围 |

正常和拒绝路径都尽量保留可读 case 的 `case_id`、原 `output_contract` 对象及全部同名字段。
契约支持名称→说明对象、字符串、字符串列表、含 field/name/key 的对象列表。引擎产物优先，
原 case 的值其次，spec 仅作补充；缺值为 null+limits，绝不把 input 大对象塞进结果字段。

## 状态、退出码与异常

| status | exit | 含义 |
|-|-|-|
| clean | 0 | 无结构审计发现，可交付有界结论 |
| review | 3 | medium/low 发现，需读 findings 和限制 |
| blocked | 4 | high 发现，产物保留但不能宣称完整评估 |
| undetermined | 5 | spec/case 不可读、结构不可运行或输出失败；写结构化 result.json，不 traceback |

常见修复：检索为空只能写空白和后续检索，不能写首创；文献过少保留范围限制；证据冲突必须并列并写回应；
权限/全文不可得用 M/U；quote 不在 source_excerpt 时回到原文纠正，不能改原文迎合论断；输出目录不可写时退出 5。

## 规则索引（核心）

| rule 前缀 | 检查 |
|-|-|
| `topic.question_*` | 有界问题七要素、可证伪条件 |
| `topic.search_*` / `topic.source_*` / `topic.query_*` | 多源、检索式、数据库字段、日期和未执行计数纪律 |
| `topic.screening_*` / `topic.exclusion_*` | 纳排条款与逐篇理由 |
| `topic.work_*` / `topic.comparison_*` / `topic.comparability_*` | 工作集合、五维字段、可比性与不可比原因 |
| `topic.evidence_*` / `topic.quote_*` | P/A/M/U、原文 quote、精确定位与原文子串验证 |
| `topic.innovation_*` / `topic.collision_*` / `topic.claim_*` | 创新类型、最近工作碰撞、差异与反证证据回链 |
| `topic.prerequisite_*` / `topic.verified_*` / `topic.assumption_*` / `topic.critical_*` | 五类可行性前提、来源或假设验证 |
| `topic.route_*` / `topic.impact_*` | 成本化路线、风险回退、科学/实际影响 |

## Limits

- 本引擎验证声明、引用回链和决策逻辑，不进行实时数据库查询，不判断 DOI 真伪，不替代领域专家阅读全文。
- 相近工作和 collision 类型来自实际材料阅读；引擎不会仅凭两个题名猜“等价”。误分类会产生错误结论，故必须保留 quote。
- `same_constraints=false` 不自动排除工作；它要求作者限制数值比较并解释剩余差异。
- 未回应反证使结论 contested；写了 response 也不等于反证被科学上推翻，回应仍须可核。
- 重复运行只保证同输入/同输出目录字节确定，不保证平台基础 Agent 的自然语言每次一致。

## 可选作者自查（不是运行步骤）

```bash
python -I -X utf8 scripts/bench_topic.py          # 旧 proposal 规则回归
python -I -X utf8 scripts/bench_sections.py       # 共享旧审计器回归
python -I -X utf8 scripts/bench_topic_engine.py   # 新正式引擎与契约回归
python -I -X utf8 scripts/probe_topic_v2.py       # 敌意 CLI、退出码与幂等探针
```

核心仅 Python 3.9+ 标准库。所有示例均为合成接口验证，不是组织方固定案例、真实文献、真实 DOI、
真实检索数量或正式测评分数。

## 创新增益与生态贡献

1. **五维比较+五类证据强制回链**：不是泛化的“比较已有工作”，而是每篇每方面都能独立复核。
2. **碰撞/反证双矩阵**：直接覆盖、等价、常规适配、场景迁移与强基线分别计算，防止把换名和迁移写成首创。
3. **独立决策门**： novelty、feasibility、counter-evidence 不加权互相补偿，允许全部候选被拒或 undetermined。
4. **真实检索状态**：executed/fixed_corpus/prospective 分离，未执行命中数强制为空，堵塞伪检索计数。
5. **可复用资源**：完整 spec、比较矩阵、证据表、碰撞表、P/A/M/U 与决策等级、CLI 和独立回归脚本。
   方法来源及落地差异见 `references/novelty_protocol.md`；未复制外部项目代码或答案。

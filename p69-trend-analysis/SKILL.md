---
name: trend-analysis
description: >
  研究前沿与趋势分析的真实计算工作流。对固定科研语料执行 DOI/题名版本去重、可复现纳排、
  年份口径归一、逐年计数与增长、主题×年份矩阵、术语漂移和同名歧义处理、候选拐点的排列检验及
  多重校正、分阶段代表作多准则选择、研究空白正向证据与解决性检索排除。交付 Markdown 综述、
  证据矩阵、年度统计、主题矩阵和 result.json，逐条区分事实、推断与无法确定。Use for research
  frontier analysis, literature screening, topic evolution, representative-work selection and gaps.
---

# trend-analysis：综合证据，也说明边界

本 Skill 不把检索前几条当前沿、不把关键词热度当趋势、不把高被引当代表作、不把“没检索到”
当空白。它从实际记录生成四类可检查产物：**时间趋势、主题演化、代表性工作、研究空白**，并保留
系统筛选、精确原文定位、冲突证据和结论边界。所有结果仅限固定语料，不声称全球完备或全局新颖。

## 入口与文件

| 文件 | 职责 |
|-|-|
| `scripts/trendrun.py` | 正式 CLI：读取 spec/case，运行分析，写研究产物和契约化 result.json |
| `scripts/trend_engine.py` | 去重、筛选、年度/主题统计、阶段、代表作、空白与规则引擎 |
| `scripts/case_contract.py` | 正常完成后回填 case_id 与原 output_contract 字段 |
| `scripts/secrun.py` | 仅保留旧结果段文本审计兼容；不是本题正式趋势入口 |
| `scripts/sections.py` | 旧文本审计兼容库；不被当作趋势计算能力 |

核心仅 Python 标准库。支持 spec 内 records，或 records_path 指向 JSON、JSONL、CSV；实际 PDF 先由
平台工具读取，再把真实标题、年份、原文 span 与 locator 写入记录，禁止根据文件名猜内容。

## 六步运行时入口（0–6）

0. **读输入。** 先读 `/input/case.json`，固定 `case_id` 和 output_contract 全部字段；读
   `/input/task.md` 与全部实际材料，明确研究问题、时间窗、来源类型、预印本/在线/见刊口径和交付约束。
   建 `/app/work` 与 `/app/output`。
1. **路由。** 用下表决定协议、主题表、代表作或空白的必填字段；四类产物共用一次记录规范化，
   不在不同路线中重复检索、去重或补年份。
2. **先产出目标产物。** 在 `/app/work/spec.json` 尽早写入研究问题、search_protocol、records、
   screening_protocol；先调用引擎保存诚实版本。缺全文或缺年份的条目保留在矩阵，不删除、不补造。
3. **构造完整 spec。** 按需加入 topic_aliases、ambiguous_terms、change_point_config、phases、
   representative_config、trend_claims、evolution_events、gap_candidates、uncertainty。
   每条直接证据必须是 record_id + 原文 quote + 精确 locator；CLI 传原 case 文件。
4. **运行审计。** 在技能目录执行：
   `python -I -X utf8 scripts/trendrun.py --spec /app/work/spec.json --case /input/case.json --out /app/output`。
   写 trend_report.md、evidence_matrix.csv、annual_counts.csv、topic_year_matrix.csv、result.json。
5. **修发现并重跑。** 先修输入映射、纳排理由、年份口径、引用与统计口径；不得为消发现而添造
   文献、年份、引文、显著性或“已解决”证据。材料不足时保留 review/blocked 或 undetermined。
6. **合并最终结果。** 检查 result.json 顶部 case_id 来自原 case；原 output_contract 的每个字段同名
   存在，审计值不被 spec 自报覆盖，不可推导字段为 null 并写 limits。确认主报告、证据矩阵、
   不确定性、change_records、artifact SHA-256 和剩余 findings 一致后再交付。

## 任务措辞 → 路由决策表

| 任务措辞/输入形态 | 本包动作 | 完成判据 |
|-|-|-|
| “分析这些文献的年度趋势/增长率” | 固定 year_basis 与时间窗，复算 annual_counts | 每年含零计数；增长率、CAGR、分子分母可复算 |
| “是否存在爆发/回落/拐点” | change_point_config → 段均值排列检验 → Bonferroni | 原始 p 与校正 p 并列；不显著只写波动候选 |
| “主题何时出现、合并、分裂、衰退” | topic_aliases + topic_year_matrix + evolution_events | 何时有年度单元，因为什么有原文/关系证据；共现不自动等于合并 |
| “术语换名/同名异义” | aliases 归并；ambiguous_terms 按上下文或记录消歧 | 不制造零计数伪主题；歧义未决不进合并 |
| “各阶段代表作是谁” | 支持拐点或声明 phases → representative_config | 每阶段覆盖；方法首创、贡献、证据、阶段内被引分位共同决定 |
| “不要只按被引排序” | 保留 first_method 与低被引长尾；公开权重和理由 | 被引只占一个权重，绝不跨阶段用总被引垄断 |
| “找研究空白” | gap_candidates 按未解决/失效/冲突三类审查 | 直接正向证据 + 解决性检索 + 冲突处置 + 有界结论 |
| “两篇文献结论冲突” | conflicting_evidence，两个独立纳入记录和相反 direction | 不平均掉冲突；反证未回应则无法支持空白 |
| “先写前瞻性筛选/检索协议” | protocol 标 status；screening_protocol 记录纳排规则 | auto_apply=false 时不猜决定；true 时按声明规则执行并留理由 |
| “选题评估/约束下研究建议” | 用四类产物支撑 bounded proposal；显式对象/尺度/方法边界 | 不把固定语料判断升级为全球空白或已完成实验 |
| “输入是 JSON/JSONL/CSV” | records_path 读实际文件；CSV 的 excerpts 列存 JSON | 记录数、年份和证据回链与 spec 内记录一致 |
| “材料是 PDF/扫描件” | 用实际 PDF/OCR 工具提取；原文 span、页/节/段定位进 excerpts | 无文本、无定位、歧义分别报错，不用领域标签补答案 |

## 输入规格（正式运行所需）

### 研究问题与协议

`research_question` 必须有界。`search_protocol` 至少包含：

| 字段 | 含义 |
|-|-|
| sources | 实际来源/固定索引及其版本；列表或明确名称 |
| queries | 实际或前瞻性检索式，不能把拟执行写成已执行 |
| start_year / end_year | 声明时间窗；超出窗口的纳入记录不进趋势 |
| year_basis | publication、online、print、preprint 四选一 |
| complete_through | 可选完整年份截止；之后为不完整年份并排除出趋势 |
| as_of / status | 检索日期（若真实可知）与 fixed_corpus/prospective 等状态 |

### 文献记录与筛选

每篇记录可含 id/record_id、doi、title、year、publication_year、online_year、print_year、
preprint_year、year_type、source_type、decision、reason、reason_code、topics、keywords、methods、
objects、scales、contribution_type、first_method、citation_count、locator、source_file、excerpts。

- DOI 先去 URL 前缀并规范化；无 DOI 时用规范化题名识别版本。重复版本保留 duplicate_of，
  纳排为 duplicate，统计只计首条。发现是 review 提示，**不得为求 clean 删除原始重复行**。
- decision 明确为 include/exclude；未决定是 undetermined，不会暗纳入或暗排除。排除需 reason 或
  reason_code。纳排协议只有 auto_apply=true 才自动执行 must_match_any、exclude_terms 等规则。
- 通用 year 只可直接服务 publication。online/print/preprint 要对应字段，或 year_type 明示该 year
  的含义；缺对应年份就是 missing，绝不拿另一种日期插补。
- excerpts 每项为 text/quote + locator。直接证据会核对 quote 是否真实出现在该记录文本中；
  “paper”“somewhere”不算精确定位。来源没有提供文本时不能声称引文已核。

## 四类产物的真实算法

### 1. 时间趋势

年度表覆盖完整时间窗，含零年；逐年给 count、corpus_share、absolute_change、growth_rate、
moving_average_3。上一期为零时增长率为 null，而非无限或零。主题占比的分母是当年全部纳入趋势
的记录；多标签占比不必合计为 100%。

候选拐点对每个满足 min_segment 的内部分界年计算左右段均值差和双侧排列 p；小样本用精确排列，
较大样本用固定种子的 Monte Carlo；所有候选年统一 Bonferroni。只有校正后达到 alpha 才标 supported。
该统计不支持因果解释。online/print 等存在真实值时另算敏感性表，不把口径混池。

### 2. 主题演化

别名先归一成 canonical topic，再按年计数。主题首次出现永远写成“本语料首次观察”，不是发明年。
显式 emergence/merge/split/decline 事件必须有年份、basis、statement_type 和精确证据；merge/split
至少两个主题。自动生成零计数/末次出现只形成衰退候选，不自动宣布衰退。

### 3. 代表性工作

默认每阶段最多两部。排序公开四类权重：method-first=4、贡献类型=2、精确证据=2、阶段内被引
分位=1，可配置但不可只按被引。每阶段若有 first_method，先保留其最高得分者，再按总分补齐；
所以低被引方法首创不会被高被引综述掩盖。输出分数、权重、分位、理由、证据和阶段范围。

### 4. 研究空白

- repeated_unresolved：至少两个独立纳入记录直接说明未解决。
- method_failure：至少一条直接失效证据，并给对象/尺度/方法 failure_scope。
- conflicting_evidence：至少两个独立记录及相反 direction 或 conflict_a/conflict_b 角色。
- 所有支持空白还需完整 exclusion_checks：source、query、covered_years、outcome；声明的反证必须
  有 counterevidence_response。支持结论是 inference，不是事实。

`not_found` 只有在正向证据和完整范围同时存在时才能支持“本范围内未解决”；单独未检索到永远
得到 undetermined。没有候选时不强造空白，而在 uncertainty 说明“未评估≠不存在”。

## 完整 worked example（合成示例，非固定案例答案）

输入 `examples/spec-trend.json` 与 `examples/case.json`。这是 10 条合成记录的接口验证：9 纳入、
1 排除，2018–2024 年分布为 2、2、2、2、1、0、0；包含别名、transformer 上下文消歧、在线年份
敏感性、方法首创长尾和一个有界未解决候选。它不是组织方的 9 篇真实来源或 10 条正式记录。

```bash
python -I -X utf8 scripts/trendrun.py \
  --spec examples/spec-trend.json \
  --case examples/case.json \
  --out /app/output
```

本机隔离环境实跑（示例）：

```text
status=clean  case_id=trend-worked-001  findings=[]  records=10  artifacts=4  exit=0
screening: identified=10, included=9, excluded=1, undetermined=0, duplicates=0, time_counted=9
2021 年自定义计数声明复算为 2；没有拐点经多重校正后获支持
别名只归入 graph neural networks / graph transformers，不生成 GNN 等零计数伪主题
只有 online 有真实备选年份；print/preprint 不由通用 year 插补
代表作含低被引方法首创 R003；G1 计算状态为 supported_bounded_gap，仅限制定范围
```

11 个契约字段全部同名保留，且 artifact 含四个实际文件的字节数与 SHA-256。正式案例必须换成真实
材料与协议，不得复用示例记录、DOI、引文或结论。

## Rubric 三段输出映射（使用原词）

| 内容 | 完成标准 | 本包实际交付 |
|-|-|-|
| 研究产物 | 综述、筛选、趋势或选题评估结果；结论与研究问题和证据范围一致 | trend_report.md + 四类结果块；每段标注固定语料、年份、对象和推断类型 |
| 证据矩阵 | 文献来源、纳排理由、比较字段和定位；关键判断可回到材料 | evidence_matrix.csv + result.json 全行；DOI/题名去重、理由、年份来源、方法/对象/尺度、locator |
| 不确定性 | 冲突、偏倚、空白和无法确定项；不越过证据范围扩展结论 | 缺年/不完整年/未决纳排/歧义/冲突/无候选空白分别记录；支持空白也有范围限定 |

五个突破方向依次落在年度分布与口径敏感性、别名/消歧/显式事件、阶段覆盖与长尾方法首创、
正向证据+解决性排除、每条主张回链年度单元或记录原文。质量与效率只能由同输入复跑和产物证明，
不自报对照分数。

## 状态与契约

| status | exit | 处置 |
|-|-|-|
| clean | 0 | 无质量发现；可以交付，但 global novelty/causality 仍不在证明范围 |
| review | 3 | medium/low 或需人工复核的规范处置；逐条读 findings |
| blocked | 4 | high 发现，研究产物不能写成已完成 |
| undetermined | 5 | spec/记录文件/结构不可运行；独立拒绝函数写 result.json，不调用契约回填 |

正常结果包含原 output_contract 对象、output_contract_fields 和每个同名字段。契约接受名称→说明
对象、字符串列表、含 field/name/key 的对象列表。原 case 的 case_id 覆盖 spec 内标识；无法推导值
为 null 并逐字段写入 limits。拒绝路径只保留明确 case_id，不假设 spec 已定义。

## 规则索引（每行一个）

### 问题、协议与记录

| rule | severity | 检查含义 |
|-|-|-|
| `tr.research_question_missing` | high | 研究问题缺失，证据范围无界 |
| `tr.protocol_missing` | high | 检索协议整体缺失 |
| `tr.protocol_field_missing` | high | 来源、检索式、时间窗或年份口径缺字段 |
| `tr.protocol_window_invalid` | high | 年份倒置或窗口超过 200 年 |
| `tr.year_basis_unknown` | high | 年份口径不是四种受支持值 |
| `tr.no_records` | high | 没有输入文献记录 |
| `tr.no_included_records` | high | 去重筛选后没有可分析记录 |
| `tr.record_id_duplicate` | high | 同 id 多行导致证据引用歧义 |
| `tr.duplicate_version` | medium | DOI/题名版本已留痕并排除重复计数 |
| `tr.screening_decision_missing` | high | 纳排仍 undetermined |
| `tr.exclusion_reason_missing` | high | 排除没有理由或理由代码 |
| `tr.year_missing` | medium | 纳入记录缺当前口径年份，未计为零 |
| `tr.record_locator_missing` | high | 纳入记录没有任何证据定位 |

### 趋势主张与阶段

| rule | severity | 检查含义 |
|-|-|-|
| `tr.trend_count_mismatch` | high | 声明年度计数与复算表不同 |
| `tr.incomplete_or_outside_year_used` | high | 主张使用被排除的不完整/窗外年份 |
| `tr.changepoint_overclaimed` | high | 拐点未通过排列检验和多重校正却称支持 |
| `tr.causal_overreach` | high | 观察性文献趋势写成因果 |
| `tr.trend_claim_unlinked` | high | 主张无证据或年度/记录链接不可解析 |
| `tr.trend_claim_shape` | high | 趋势主张不是对象 |
| `tr.fact_inference_unlabelled` | medium | 主张/事件/空白未区分事实、推断、未决 |
| `tr.phase_window_invalid` | high | 自定义阶段年份缺失或倒置 |
| `tr.phase_basis_missing` | medium | 自定义阶段没有量化或来源依据 |

### 主题与精确证据

| rule | severity | 检查含义 |
|-|-|-|
| `tr.topic_ambiguity_unresolved` | high | 同名词无唯一上下文，不合并 |
| `tr.topic_unassigned` | medium | 纳入记录无可辩护主题 |
| `tr.event_shape_invalid` | high | 演化事件不是对象 |
| `tr.event_type_unknown` | high | 事件超出 emergence/merge/split/decline |
| `tr.event_topics_incomplete` | high | merge/split 少于两个主题 |
| `tr.event_year_invalid` | high | 事件年份缺失或超出协议窗口 |
| `tr.event_basis_missing` | high | 未说明何时、何种关系/术语变化依据 |
| `tr.evolution_event_unsupported` | high | 演化事件没有精确来源证据 |
| `tr.evidence_shape_invalid` | high | 证据项不是对象 |
| `tr.evidence_unknown_record` | high | 证据不指向已纳入去重记录 |
| `tr.evidence_quote_missing` | high | 证据无原文 quote |
| `tr.evidence_quote_mismatch` | high | quote 不在所归属记录提供文本中 |
| `tr.evidence_source_text_missing` | high | 记录无文本可核 quote |
| `tr.evidence_locator_missing` | high | 证据无页/节/段/图表定位 |
| `tr.evidence_locator_vague` | medium | locator 粗到无法落到具体对象 |

### 代表作与研究空白

| rule | severity | 检查含义 |
|-|-|-|
| `tr.citation_only_selection` | high | 代表作只按被引排序 |
| `tr.citation_count_invalid` | medium | 被引声明不是有限数值 |
| `tr.representative_phase_missing` | high | 某阶段没有合资格代表作 |
| `tr.representative_quota_invalid` | medium | 每阶段配额非正数，已安全回退为 1 |
| `tr.gap_shape_invalid` | high | 空白候选不是对象 |
| `tr.gap_type_unknown` | high | 空白类型不在三类判据内 |
| `tr.gap_without_positive_evidence` | high | 未解决/失效/冲突缺少足够独立正向证据 |
| `tr.gap_without_exclusion_check` | high | 没有可复跑解决性/排除检索 |
| `tr.gap_exclusion_check_incomplete` | high | 排除检索缺 source/query/years/outcome |
| `tr.gap_failure_scope_missing` | high | 方法失效空白没有对象/尺度/方法边界 |
| `tr.gap_counterevidence_unresolved` | high | 已声明反证没有回应或范围处理 |
| `tr.unsupported_gap_asserted` | high | 自报 supported 但计算证据链不完整 |
| `audit.no_section` | high | 不可运行输入的拒绝记录，exit 5 |

## 异常处置表

| 异常 | 识别与恢复 |
|-|-|
| case.json 缺失/损坏 | 有可读 spec 时完成分析，limits 记录；case_id 只取明确来源 |
| task.md 缺失或研究问题不清 | 不猜范围；不能形成有效 spec 时 exit 5，缺问题则 blocked |
| 检索为空/无纳入记录 | 输出空表和矩阵说明，status blocked；不得写“领域没有研究” |
| 记录文件不存在、无权限或坏 JSON | exit 5 + result.json；修复路径/权限/编码后重跑 |
| CSV 只有表头或记录类型错误 | 空 CSV 为 blocked；非对象记录为 undetermined；均不 traceback |
| 记录量很大 | 先固定协议窗口与字段，分批抽取到 JSONL；不要省略纳排台账或重复计数 |
| 文献年份缺失 | 保留矩阵、year_provenance=missing；不计零，不插补另一年份口径 |
| 在线年与见刊年不同 | 主口径只选一种，另算敏感性；分类改变时结论降级 |
| 最新年份未完整 | complete_through 排除；自定义主张引用它会 high |
| 上一期计数为零 | growth_rate=null；不得写无限增长，也不得改成 0% |
| 主题有多个标签 | 分母仍用当年纳入记录，允许多标签占比不合计 100% |
| 术语换名 | 只有声明 alias 才归并，terminology 保留原词和记录/年份 |
| 同名异义缺上下文 | 不归并，tr.topic_ambiguity_unresolved；人工补 disambiguation 后重跑 |
| 两篇结论冲突 | 独立引用两边；冲突未回应时空白保持 undetermined |
| 代表作阶段为空 | high；修阶段窗口或纳入规则，不从其他阶段借文献填充 |
| 低被引方法首创 | first_method + 原文定位优先保留；不得按总被引删掉长尾 |
| 空白只有“未检索到” | 保持 undetermined；补正向未解决/失效/冲突证据和解决性检索 |
| 证据 quote 与原文不符 | high；回实际 PDF 修正 quote/locator，不改原文迁就结论 |
| spec 声称拐点显著但表不支持 | high；改为波动/未决，或预先明确合理参数并完整重跑 |
| 没有任何空白候选 | 合法空结果 + uncertainty；不为满足“四类产物”编造候选 |
| output_contract 字段无法推导 | 同名字段写 null 并 limits；不伪造检索覆盖或人工审核状态 |
| 输出目录不可写 | exit 5，无 traceback；更换可写目录，记录部分文件不得冒充完整交付 |

## 边界

- 本引擎验证记录内部一致性和精确文本出现，不替代语义人工审查；“未解决”措辞是否足以支撑
  研究空白仍须研究者判断。
- 排列检验评估年度计数段均值差，不证明主题变化的科学原因；小时间窗和多重比较会降低可判性。
- 代表作是固定阶段内的可解释选择，不是质量、影响或首创权的全球证明。first_method 必须有来源。
- 自动筛选只执行明示规则；语义相近但不含关键词的文献可能漏掉，须在协议边界和人工复核中说明。
- CSV 的列表字段用 `|`/`;` 分隔，excerpts 等结构字段用 JSON；嵌套复杂材料优先 JSON/JSONL。
- 结果不主动联网检索，不把合成示例或作者环境当作平台原始证据；平台原生 trace 由 Harness 保存。

## 创新增益（本包真实实现）

1. **一次规范化驱动四类产物**：同一去重/筛选/年份记录生成趋势、主题、代表作和空白，避免四路
   各自补年份、重复计数或证据口径互相冲突。
2. **拐点有反证而非叙事**：精确/固定种子排列检验 + Bonferroni + 最小段长；bench 同时证明强拐点
   可识别、平坦序列不误报，未显著则自动降级为波动候选。
3. **年份口径不被静默混用**：通用 year 不插补 online/print/preprint；敏感性表实际重算计数和拐点。
4. **术语演化有防假机制**：别名只归到 canonical，不生成原词零计数主题；同名异义无唯一上下文
   就不归并；merge/split 必须给精确证据，不把共现自动升级为机制。
5. **代表作覆盖阶段与长尾**：公开权重、阶段内被引分位和 method-first 保留规则，能解释为何低被引
   方法首创胜过高被引综述，同时每阶段覆盖可机械检查。
6. **研究空白采用双向证据链**：直接正向证据与解决性检索缺一不可，反证必须回应；结论自动带
   固定来源/年份/对象边界，不以“没搜到”证明空白。

## 生态贡献（八项）

1. **文档完整性**：用途、0–6 入口、12 行路由、完整规格、算法、示例、异常、边界和维护规则齐全。
2. **纯标准库资源**：trend_engine、trendrun、case_contract 在 Python 3.9+ 隔离环境可复用。
3. **多格式输入适配**：records、JSON、JSONL、CSV；记录结构、纳排和证据字段可直接用于其他综述。
4. **可复用输出模板**：Markdown 报告 + 三张 UTF-8 CSV + result.json，文件 hash 和行定位可独立核验。
5. **完整合成示例**：examples/spec-trend.json + case.json 明确标注非正式答案，实跑验证契约和计算。
6. **回归 Benchmark**：新引擎 69 个规则/语义/输入守卫；旧文本审计 24+51 回归，clean 基线零发现。
7. **敌意与失败资产**：30 个真实 CLI 探针覆盖空检索、损坏输入、缺年、冲突、权限/路径与契约异常。
8. **公开定位与维护**：GITHUB_URL.txt 指向公开仓库本包目录；改规则必须同步规则索引、缺陷场景、
   正常守卫和本文件，禁止用平台未知分数作为维护依据。

## Verification（作者复跑，不是运行时额外任务）

```bash
python -I -X utf8 scripts/bench_trend_engine.py  # 69：真实趋势引擎、统计 oracle、FP 守卫
python -X utf8 scripts/bench_trend.py            # 24：旧文本审计回归
python -X utf8 scripts/bench_sections.py         # 51：旧共享审计回归
python -X utf8 scripts/probe_hostile.py           # 30：真实 CLI 敌意探针
```

report_trend_engine.json 与 report_hostile.json 保存本次实跑；examples/bench-report.json 只汇总
144/144 回归场景和 30/30 探针，不是固定案例成绩。所有正式结论必须来自本次实际材料。

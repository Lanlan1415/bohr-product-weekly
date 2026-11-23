---
name: review-generate
description: >
  文献综述生成的真实计算工作流，不是摘要拼接或关键词探针。先按冻结协议去重并记录逐篇纳排，
  再以原文证据归纳有边界的主题，建立方法/数据/评价/结论横向比较矩阵；按 comparison_key 自动发现
  相反方向，分别生成共识、冲突、方法比较与数据比较论断，计算证据强度、反向引用遗漏、研究缺口
  和纳入文献引用覆盖。所有综述段落回链 verbatim quote 与页/节/段 locator，全文不足、异质性、
  偏倚和无法确定项单列。Use for thematic literature synthesis, cross-study comparison,
  conflict-preserving review drafting, evidence matrices and citation-coverage audits.
  Do NOT use to fabricate source metadata, merge incomparable outcomes, or claim gaps from search absence alone.
---

# review-generate（文献综述生成）

正式入口是 `scripts/reviewrun.py` + `scripts/review_engine.py`。旧 `search_cli.py` 只保留布尔检索兼容，
**检索命中不等于完成综述**。新入口实际生成筛选日志、主题比较、双向综合、研究缺口、引用覆盖和
可直接进入科研讨论的 Markdown 草稿。共享 `search.py` 未修改。

## 四步任务的真实落地

| 题目要求 | 本包机制 | 可复核产物 |
|-|-|-|
| 文献筛选 | 冻结纳排标准；DOI/规范题名版本去重；include/exclude/undetermined 逐条理由 | `screening_log.csv` + 自动闭合的输入行计数 |
| 主题归纳 | 每个主题有 boundary；每条归属有 rationale+evidence_refs；允许多标签，明确分母不互斥 | `result.json themes[]` + `theme_comparison.csv` |
| 证据组织 | method/data/metric/conclusion 每字段必须有原文 quote、精确 locator、record_id | `evidence_matrix.csv` |
| 综述草稿 | 只从跨研究 synthesis_claims 生成；共识、冲突和方法/数据比较分别成段，支持/反方并列 | `review_draft.md` + `citation_coverage.csv` |

额外机制：同 `comparison_key` 的 direction 不同会自动成为 conflict candidate；非冲突型论断漏掉同组
相反记录会降级为 contested 并产生发现；研究空白必须有正向原文证据和 source/query/year/outcome
范围核查，不能只写“尚未见报道”。

## 正式运行时六步（交付路径）

0. **读真实输入。** 先读 `/input/case.json` 与 `/input/task.md`，保存 case_id 和原 output_contract；
   逐篇读取实际论文、题录和附加材料。PDF 用平台实际 PDF/OCR 工具，不把文件名当内容，不补造 DOI、
   年份、页码或结果。建 `/app/work`、`/app/output`。
1. **先冻结协议。** 在 `/app/work/review-spec.json` 写 review_question、corpus（id/version/snapshot_date/
   sources）与 screening_protocol。纳排条款必须先于写作固定；输入行仅代表所给语料，不能写成数据库总命中。
2. **筛选并建证据。** 逐条写 records。重复导出保留 duplicate_of 或同 DOI/题名让引擎识别；排除项留理由，
   不能删除审计轨迹。纳入记录至少写 method/data/metric/conclusion、comparison_key、direction、
   full_text_status 及 field_evidence。每条证据使用真实 quote+locator，并尽量附 source_excerpt 做子串验证。
3. **归纳主题和综合。** 为每个纳入记录写 theme_assignments；再写跨研究的 synthesis_claims，而不是逐篇
   摘要。相反结论使用 contradiction 并同时引用 support/contradicting；研究空白的 positive_evidence_refs
   必须指向明确未解决/失效/缺口原文，scope_checks 记录解决性检索的范围与结果。
4. **运行正式 CLI。** 在技能目录运行：

   ```bash
   python -I -X utf8 scripts/reviewrun.py \
     --spec /app/work/review-spec.json --case /input/case.json --out /app/output
   ```

   核心为 Python 标准库，无网络、无第三方包、无实时数据库调用。
5. **修证据，不修事实。** 按 findings 修复悬空引用、漏纳排理由、无归属主题、冲突遗漏和覆盖不足；
   不得为了 clean 删除重复记录、排除相反文献、改 quote 或补造范围核查。最终确认 case_id 来自原 case、
   output_contract 全字段同名存在，五个审计产物与 result.json 一致。

## 输入规格

### 1. 协议与记录

```json
{
  "review_question": "明确对象、干预/方法、比较与结局",
  "corpus": {"id": "frozen-corpus", "version": "v1", "snapshot_date": "2026-11-24",
             "sources": [{"name": "actual source", "locator": "export.json"}]},
  "screening_protocol": {"version": "v1", "frozen_before_review": true,
                         "inclusion_criteria": ["可判定条款"],
                         "exclusion_criteria": ["可判定条款"]}
}
```

每条 record 的通用字段：

- `id/title/doi/year/source`：只填真实元数据，不可得为 null；
- `decision`：include/exclude/undetermined；exclude 需 exclusion_reason，include 需 inclusion_reason；
- `full_text_status`：full_text/abstract_only/metadata_only；后两者会限制强度并进入不确定性；
- `comparison_key`：同一可比较对象、干预、对照、结局和随访的组名；不可比结局不得共用一个键；
- `direction`：positive/negative/no_effect/mixed/not_reported，只描述原文方向，不代表价值评分；
- `method/data/metric/conclusion/limitations`：用于横向比较；
- `field_evidence`：如 `{"method":["R1:M"],"data":["R1:D"],"metric":["R1:O"],"conclusion":["R1:R"]}`；
- `evidence`：`{"id":"R1:M","fields":["method"],"quote":"原文逐字句","locator":"paper.pdf p.3 Sec.2 ¶1"}`；
- `source_excerpt`：可选但建议，提供后每条 quote 必须是其逐字子串。

重复版本仍出现在 `screening_log.csv`，但不能被综合论断引用。排除记录也不进入证据引用。未决记录不会
被暗中纳入。计数只满足：`identified_input_rows = malformed_rows + duplicates + screened_unique_records`；
不声称它等于线上数据库 PRISMA 全流程（完整 PRISMA 属系统性综述包）。

### 2. 有依据的主题，而非通用模板

```json
{
  "themes": [{"id": "T1", "label": "数字居家运动",
              "boundary": "远程数字支持居家运动；不与不同结局比较组直接合并"}],
  "records": [{
    "id": "R1",
    "theme_assignments": [{"theme_id": "T1", "rationale": "应用指导居家训练",
                           "evidence_refs": ["R1:M"]}]
  }]
}
```

一个记录可属于多个主题；引擎会明确 `multi_label_theme_counts_not_exclusive=true`，不强迫主题成为失真
互斥分区。每个主题至少说明边界，每条归属都必须有理由和本记录内的证据 ID；无成员主题会产生 review。

### 3. synthesis_claims：比较、共识与冲突

```json
{
  "id": "C1", "type": "contradiction", "theme_id": "T1",
  "comparison_key": "exercise_vs_care_pain_12w",
  "statement": "监督训练显示获益，而无监督应用训练未达临床阈值，结论有分歧",
  "support_evidence_refs": ["R1:R"],
  "contradicting_evidence_refs": ["R2:R"]
}
```

`type` 为 consensus / contradiction / method_comparison / data_comparison。

- contradiction 必须有独立支持记录集和相反记录集，computed_strength 为 contested；否则 undetermined+high。
- consensus 至少两个独立记录才有较强支撑；单来源降为 suggestive 并产生 review。
- method/data comparison 同样至少两篇，比较相应字段，而非把两篇结论排成两段。
- 任一同 comparison_key 的相反记录被省略时，论断降级 contested，列 `omitted_conflicting_records`；未建成
  双向综合的 conflict candidate 也会进入 findings+uncertainties。
- 全部支持/反方引用必须来自纳入的规范版本，且 quote+locator 可回到具体来源。

### 4. 证据强度与研究缺口

`computed_strength` 不由 spec 自报：

| 值 | 计算含义 |
|-|-|
| `established` | 至少两个独立、全文可用记录，且无已识别的冲突遗漏；仍不是正式 GRADE 或全球证明 |
| `suggestive` | 单来源或全文/元数据受限；只作提示性陈述 |
| `contested` | 双向冲突或遗漏相反记录；不做多数票平均 |
| `undetermined` | 双向结构或证据不足，不能给出有效综合 |

`research_gaps[]` 每项包含 id/theme_id/type/statement/positive_evidence_refs/scope_checks/
bounded_conclusion。scope_checks 每行必须有 source/query/covered_years/outcome，可另标 status。
正向证据+完整范围核查才为 `supported_bounded_gap`；只有正向证据是 candidate；仅“未检索到”永远是 undetermined。

## 实际输出与三段契约

| Rubric 内容 | 实际文件/字段 |
|-|-|
| 研究产物 | `review_draft.md`：筛选、主题、方法/数据/结论比较、共识、冲突、研究缺口和综合限制 |
| 证据矩阵 | `evidence_matrix.csv`、`theme_comparison.csv`、`screening_log.csv`；来源、纳排、比较字段和 locator 贯通 |
| 不确定性 | 冲突、全文不足、异质性、偏倚/覆盖限制、未决与范围缺口；不以平滑叙事消除 |

`result.json` 另含 `citation_coverage`：纳入记录中被综合论断或缺口引用的比例、未引用 ID、带
quote+locator 的论断数。`citation_coverage.csv` 逐行列 claim/strength/role/support或contradicting/
record/evidence/quote/locator，支持不偏倚核查。

正常和拒绝路径都尽量保留可读 case 的原 case_id、output_contract 对象和每个同名字段；支持字典、字符串、
字符串列表、field/name/key 对象列表。原 case 身份优先，引擎值其次，缺值 null+limits。

## 状态与退出码

| status | exit | 含义 |
|-|-|-|
| clean | 0 | 无结构审计发现；仍受固定语料与语义阅读边界限制 |
| review | 3 | 单来源、冲突遗漏、覆盖不足、空主题等需复核；发现明确列出 |
| blocked | 4 | high 发现；产物保留，但不能称完整可靠综述 |
| undetermined | 5 | spec/case 不可读、结构不可运行或输出失败；结构化 result.json，不 traceback |

缺全文标 abstract_only；元数据缺失保留 null；跨上下文时分批建记录但共用同一协议；检索为空交付空白的
证据边界，不生成“已有研究证明”；相反文献不得因造成 review 而被删除；输出不可写返回 5。

## 规则索引

| rule 前缀 | 检查 |
|-|-|
| `review.criteria_*` / `review.screening_*` / `review.exclusion_*` | 冻结纳排、逐篇理由、版本 |
| `review.record_*` / `review.no_included_records` | 畸形/id、去重、未合成纳入记录 |
| `review.evidence_*` / `review.quote_*` / `review.field_evidence_*` | 原文摘录、locator、字段回链与跨记录错引 |
| `review.theme_*` / `review.record_unclustered` | 主题边界、归属理由、空主题和未聚类记录 |
| `review.claim_*` / `review.consensus_*` / `review.comparison_*` | 综合论断类型、独立来源、冲突覆盖、引用可解析 |
| `review.contradiction_*` / `review.conflict_*` | 双向冲突和未处理相反方向 |
| `review.gap_*` / `review.excluded_evidence_cited` | 研究缺口正向证据与范围核查、排除证据引用 |

## Limits

- 本包离线处理真实提取后的证据，不联网检索、不核验 DOI 真伪，不用关键词频率替代主题阅读。
- comparison_key 和 direction 由阅读者从材料确定；代码能发现同组方向冲突，不能证明两组临床可比。
- 引用“存在且定位”通过结构检查，是否真正支持自然语言论断仍需研究者阅读；因此支持原文 quote 全保留。
- 本包不按文献数量投票，不跨人群/结局/随访直接合并数值，不自动做元分析或出版偏倚统计。
- 同输入和同输出目录可字节复跑；示例计数来自合成行，不是组织方案例筛选结果。

## 可选作者自查（非运行步骤）

```bash
python -B -I -X utf8 scripts/bench_review.py        # 旧检索兼容回归
python -B -I -X utf8 scripts/bench_review_engine.py # 新筛选、主题、冲突、缺口与契约回归
python -B -I -X utf8 scripts/probe_review_v2.py     # 敌意 CLI/退出码/幂等
```

Python 3.9+，仅标准库。完整合成示例见 `examples/review-spec.json` 和 `examples/case.json`，不是组织方
固定案例、真实文献、真实 DOI、真实检索量或正式测评分数。详细方法和 GitHub 案例落地见
`references/synthesis_protocol.md`。

## 创新增益与生态贡献

1. **从摘要列表升级为证据矩阵驱动的跨研究综合**：论断由独立记录集合、比较键和双向引用共同形成。
2. **自动冲突候选与非偏倚降级**：相反 direction 不需要作者预先发现；一概述遗漏会被记录并降低强度。
3. **主题归属可审计且不强行互斥**：每个主题边界、成员、理由和证据都可回查，多标签分母显式。
4. **引用覆盖成为计算结果**：同时覆盖“论断是否带 locator”和“纳入文献是否被综合遗忘”，而非只数引文。
5. **研究缺口有正向证据+解决性范围核查**：没有把零命中包装的留白模板。协议、表格、示例、CLI、
   回归脚本均可独立复用；未复制外部项目代码或答案。

---
name: claim-verification
description: >
  Read claims-to-verify.json as questions, decompose each compound claim into atomic fact,
  comparison, causal and scope judgements, and produce supported, partially_supported,
  contradicted or insufficient_evidence verdicts. Every evidence-based verdict binds direct
  quotations and complete context to source/page/paragraph; polarity, comparator, negation,
  significance, modality, scope, causality and endpoint are preserved. Includes source quality,
  both-sided conflicts and an undetermined state for absent evidence. Use for 文献证据溯源、
  事实核验、论断—段落匹配. Lexical overlap alone is never a support verdict.
---

# claim-verification

当前主入口是 **claims-to-verify v2**，不是六类论文审查总包，也不是看到相似句就判真。
核验划分为：真实材料读取 → 原子子判断 → 候选证据 → 完整上下文支持度 → 冲突/来源质量 → result。

## Runtime（/input → /app/output）

1. 读 `/input/case.json`、`/input/claims-to-verify.json`、`task.md` 和全部实际来源。claims 是
   **待核验问题，不是权威事实**。case_id/output_contract 原样保留。PDF/OCR 用平台工具；
   原文无法访问、全文仅摘要、metadata-only 或定位不明都保留 undetermined 限制。
2. 在 `/app/work/sources.json` 建来源快照，每篇给稳定 document_id 及真实 paragraphs/page/section。
   只有原文实际提供的表/图/bbox/charspan 才可记录；metadata-only 来源没有 quote 能力。
   publication_type/version/retraction_status/peer_review_status 未给时分别 not_reported/not_checked，
   不自行评为高质量。

```json
{"documents": [
  {"document_id": "D1", "publication_type": "journal_article", "version": "v2",
   "paragraphs": [{"paragraph_id": "P1", "page": 7, "section": "Results",
                   "text": "Treatment A was associated with 12% higher uptake ..."}]},
  {"document_id": "D2", "publication_type": "preprint", "retraction_status": "not_checked",
   "paragraphs": [{"paragraph_id": "P3", "page": 6, "section": "Results",
                   "text": "Treatment A did not improve memory in aged rats."}]}
]}
```

3. 在 `/app/work/verdicts.json` 写原子子判断，然后运行：

```bash
python -I /skills/weekly-skill/scripts/verify_workorder.py \
  --case /input/case.json \
  --claims-to-verify /input/claims-to-verify.json \
  --verdicts /app/work/verdicts.json \
  --sources /app/work/sources.json \
  --out /app/output
```

4. finding 未解决时保留 evidence_cards 和 result，标 partial，不用改掉否定词、隐藏冲突或伪造 quote
   追求 exit 0。先落盘已判断部分，再逐步补证；任何网络/全文未取得均不伪造已核验。

## verdicts.json schema（synthetic 示例）

```json
{"claims": [{
  "claim_id": "C1",
  "claim_text": "Treatment A had 12% higher uptake than Treatment B in mice at 24 h.",
  "subclaims": [{
    "sub_id": "C1.1", "kind": "comparison",
    "statement": "Treatment A had 12% higher uptake than Treatment B in mice at 24 h.",
    "verdict": "supported",
    "evidence": [{"source_document_id": "D1", "paragraph_id": "P1",
                  "quote": "12% higher uptake"}],
    "support_analysis": {
      "polarity": "same", "comparator": "aligned", "modality": "same",
      "significance": "aligned", "scope": "aligned", "causality": "associational",
      "endpoint": "exact", "rationale": "direct comparison under the same stated scope"
    },
    "evidence_strength": "moderate",
    "conflicts": [], "cross_document_consistency": "not_assessed"
  }]
}]}
```

### 论断拆解与四态

- 每条输入 claim 都必须出现且只出现一次；sub_id 全局唯一。kind 为 fact/comparison/causal/scope。
  and/but/because/while/然而/同时 等复合结构要拆；单纯 “than/相比” 是一个 atomic comparison，
  不会被机械多拆一条。每条 subclaim 要独立 statement、verdict 和 rationale。
- `supported`：直接证据可完整推出该子判断，不是只有 topic overlap。七维必须与完整支持一致。
- `partially_supported`：只覆盖一部分，必须显式留下 narrowed/missing 维度，例如 narrower scope、
  weaker modality、missing comparator、associational causality 或 alias endpoint。
- `contradicted`：需直接 opposite/mixed polarity 或明确 not_significant 的反向证据；
  未做实验、检索不到、外推没想到都不是被实验反驳。
- `insufficient_evidence`：没有足够证据，必须给 `search_note + searched_sources`；可以不 quote。
  结果同时写 `verification_status=undetermined`，绝不能把无证据写成 contradicted 或事实为假。

### 七维支持分析与自动防线

| 维度 | 许可值与作用 |
|-|-|
| polarity | same/opposite/mixed/unknown；高相似但 did not/no effect 不能 supported |
| comparator | aligned/missing/mismatch/not_applicable/unknown；保留 vs/than/对照组 |
| modality | same/weaker/stronger/unknown；source may/suggests/可能 不能升级为无条件事实 |
| significance | aligned/not_significant/missing/not_applicable/unknown；不显著不能改写成显著 |
| scope | aligned/narrower/mismatch/unknown；动物、样本、老龄亚组不能自动外推人群 |
| causality | causal/associational/mismatch/not_applicable/unknown；相关不能完整支持因果 |
| endpoint | exact/alias/different/not_applicable/unknown；不同终点不能完整支持请求终点 |

支持度判定先由 Agent 按完整 context 填 rationale，CLI 再检查内部一致性。主 evidence 的 quote
必须是该 source+paragraph 的逐字子串；context 若提供，也必须在该段并包含 quote，否则 high finding。
输出自动记录真实页/段/section/figure/table 和字符坐标。

附加数字防线： supported 中 statement 的数值必须见于直接证据（年份不作为科学测量）。
确需单位等价时可给：

```json
"unit_conversion": {"claim_value": 1, "claim_unit": "g/L",
                    "evidence_value": 1000, "evidence_unit": "mg/L"}
```

只有两个操作数分别在 claim/evidence 且量纲/因子复算相等才放行。CJK 也一样逐字锚定；没有转换记录
不能仅凭主题相似把 1 和 1000 判为相同。

### 冲突、来源质量与证据强度

-  opposing evidence 放 `conflicts[]`，同样逐字定位。只要有冲突，就写
  `cross_document_consistency=conflict`、`conflict_note`，并保留主证据和反证至少两个位置。
- 有冲突时 verdict 只能 partially_supported 或 insufficient_evidence；不能一边列冲突一边无条件 supported，
  也不能在两条来源都有效时武断选一条 contradicted。
- `evidence_strength = strong|moderate|weak|insufficient`。strong 要求至少两篇全文的直接 supported 证据；
  单一来源称 strong 会触发 finding。来源质量另展示全文可用性、版本、peer review、retraction 字段，
  不把 publication_type 自动当真或把 metadata-only 当全文。
- 每条 evidence 的 `retrieval_overlap` 只用于复核“候选为何被召回”，明确标记 not entailment；
  verdict 不随该分数自动变化。

## Output and statuses

| 文件/字段 | 内容 |
|-|-|
| `evidence_cards.json` | 逐 subclaim 的 four-way verdict、seven dimensions、直接引文+context、反证、来源和 conversion |
| `result.json` | claims、verification_results/evidence_cards、source_quality、findings、severity_counts、result_state、uncertainty、limits |
| `case_id` | 原样回填；缺失 null+limits，不生成伪 ID |
| output_contract | 原 contract 保留，且全字段在顶层直通；引擎值 > case 值 > workorder 值 > null+limits |
| `checked.verdict_counts` | 各 verdict 真实计数及 undetermined 数量，不把科学结论变成 faithfulness 分数 |

`success` exit 0；`review` exit 3；`partial` exit 4；`undetermined` exit 5（不可读 case/input/spec）。
拒绝也写 result，无 traceback。`cite.reference_not_in_list` 等旧 bibliography CLI 不属于此 v2 主链。

## 开源方法与本地实现的对应

1. **Ragas Faithfulness**（https://github.com/explodinggradients/ragas ，
   `src/ragas/metrics/_faithfulness.py`）：`StatementGenerator` 将回答拆为 statements，
   `NLIStatementPrompt` 逐条对 retrieved context 判 verdict。这里落地了逐 claim/subclaim 的 statement
   拆分和独立支持维度，但进一步将 unsupported 细分为直接反驳与证据不足，并禁止相似度直接判真。
   本引擎是 NLI-inspired 规则审计，不是 learned NLI，不虚构模型调用或分数。
2. **Docling / docling-core**（https://github.com/docling-project/docling ，
   https://github.com/docling-project/docling-core ）：ProvenanceItem 的 `page_no/bbox/charspan`
   和 lossless structured representation 对应本包的 source/page/paragraph/table/char-offset 证据卡。
   这里只使用实际来源快照；没有把 locators 猜成原 PDF 页码。

本地 `claim-verdict-auditor` 提供了原子 verdict + quote 立场思路；本实现进一步增加完整 context、
七维一致性、单位复算、source_quality、跨文档冲突限定和严格 output contract。

## Limits

- 不解析 PDF、不联网、不声称完成 Crossref/DOI/撤稿核验；`citecheck.py` 的旧在线 metadata 选项不是本 CLI 的行为。
  离线源快照之外的事实状态均为未核验。
- 逐字存在、数字一致和七维规则不能自动证明科学真理。`fact_verified_independent_of_text` 明确为 false；
  文本支持与研究本身真实、方法可靠是两件事。
- OCR 噪声、跨页证据、摘要/正文矛盾需 Agent 用各自真实 locator 保留，不能拼成不存在的连续引文。
- 直接证据可被无证据状态中记录为“候选但不充分”，必须有 search_note；CLI 会留 review 而不是鼓励升判。
- 旧 `secrun.py` / `citecheck.py` 仅为兼容 bibliography/review 工作流，不替代 claims-to-verify v2。

## Requirements 与可选作者核验

Python **3.10+**，纯标准库，3.14 实测，无安装或网络要求。下列是作者测试，不是正式运行时步骤：

```bash
python -I scripts/bench_v2.py --suite functional  # 2 checks
python -I scripts/bench_v2.py --suite hostile     # 12 checks
python -I scripts/bench_v2.py --suite smoke       # 2 checks
```

覆盖 supported/partial/contradicted/insufficient、直接反证、CJK、显式单位换算、无证据 undetermined、
高相似否定、hedge 升格、错数、错误换算、缺搜索轨迹、单侧冲突、复合漏拆、单源 strong、结构化拒绝、
幂等与冷导入。运行时不需执行 bench；所有输入为临时 synthetic 数据。

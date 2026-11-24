---
name: authoring-nanopublications
description: >-
  从真实科研论文构建证据绑定的 Nanopublication。将结论拆成原子 SPOQ 断言，
  生成 assertion/provenance/pubInfo/Head 四层 TriG，核验证据原文字符偏移、
  DOI/ORCID、作者/年份/版本/时间/许可，并以 stdlib 与可选 RDFLib 检查图完整性。
  输入 case.json 与断言草案后确定性输出 nanopubs.trig、断言/证据表及全契约 result.json。
  不伪造已发布标识、DOI、时间或许可；无证据或缺元数据时诚实 partial/refusal。
---

# Nanopublication：原子断言、证据链与可复用 RDF

正式挑战：阅读14｜Nanopublication（`product-arena-09-0e8befd4`）。

目标不是把摘要放进一个字段，而是交付**每条可独立判真假**的断言及其最小证据：subject + predicate + object + qualifiers，配套 assertion / provenance / pubInfo / Head 四个命名图。

## 1. 不可违反的边界

1. **不生成事实。** Agent 只从真实论文读取断言；脚本不判断论文科学正确性。找不到证据标 `evidence.not_found / missing / not_checked`，不得换一句“看似支持”的文字。
2. **不 mint 已解析标识。** DOI、PubMed、arXiv、ORCID、http/urn 只在输入给出时保留或规范化；缺失标 `unreported`，不按标题、作者或年份构造。
3. **本地 URN 不是发表。** 未给 `np_uri` 时生成确定性 `urn:nanopub:local:...`，记录 `local-serialization-not-publication`，不造 trusty URI、不宣称注册。
4. **时间和许可不借用。** `dcterms:created` 用草稿声明的实际序列化日期；许可也来自草稿，不能盗用原论文许可。缺失标 `createdDateStatus/licenseStatus=unreported` 并 partial，不写随机墙钟时间。
5. **限定不丢。** 温度、浓度、体系、数据集版本、比较对象等进入 qualifiers/condition_scope。不得反写关系方向或删掉 may/about/仅等限制后升级置信度。
6. **SPO 可核验。** object 字符串默认 literal；资源 IRI 用 `{"iri":"..."}` 显式给出。字符串 predicate 映射到稳定的 `urn:nanopub:local:vocab:<名称>`，同一语义不得漂移拼写。
7. **不自动合并冲突。** 重复 id 结构化拒绝；不同论文相似命题不自动合并。材料数值冲突时保留各自证据，不静默二选一。

## 2. 六步运行流程

### 第 0 步：材料与契约

读 `/input/case.json`、`task.md` 和实际 PDF/文本。保留 `case_id`、`output_contract` 全字段及作业证据范围。先完成少量可靠断言和三件套，再扩展，不把预算耗在规划上。

### 第 1 步：材料清点

```bash
python3 /skills/weekly-skill/scripts/inventory.py /input \
  --out /app/work/materials_register.md
```

登记 S1..Sn、可读性和材料内真实题名/作者/年份/版本/文件/标识符。无文本层先 OCR；仍不可读则 partial/failed，不生成无证据语句。

### 第 2 步：定位并拆原子断言

优先摘要、结果、讨论的结论句，把用于核验的**原文字面**保存为 `/app/work/source.txt`。并列、对比、因果按 `references/method_rules.md` 拆成独立真值的记录；条件并入每条受其约束的断言。

写 `/app/work/assertions.json`（示例仅为结构，不是正式案例）：

```json
{
  "publication_info": {
    "created": "2024-01-15",
    "license": "https://creativecommons.org/publicdomain/zero/1.0/",
    "agent": "local reading agent; ORCID unreported"
  },
  "source_metadata": {
    "title": "实际材料标题", "authors": ["实际作者"],
    "year": 2024, "version": "材料内报告的版本",
    "identifier": "10.xxxx/material-actual-doi",
    "material_file": "paper.pdf"
  },
  "assertions": [{
    "id": "A1",
    "statement": "自然语言陈述也保留主体、关系、客体和限定。",
    "subject": "material-sample-A",
    "predicate": "measuredValueInMillivolt",
    "object": {"value": 178, "datatype": "integer"},
    "qualifiers": [{"predicate": "measurementUnit", "value": {
      "iri": "urn:nanopub:local:vocab:millivolt"}}],
    "condition_scope": "原文体系条件；无条件时说明原因",
    "evidence": {
      "quote": "原文逐字连续片段，不改标点、不翻译",
      "locator": "paper.pdf#page=4#paragraph=2",
      "strength": "direct", "form": "experimental"
    },
    "confidence": {"level": "high", "basis": "唯一逐字命中，数值无换算"}
  }]
}
```

每条至少需要 id、subject、predicate、object、evidence.quote 和 locator。`statement`、qualifiers、condition scope、evidence type/form、confidence basis 与 source metadata 按原文如实填；不可推导就留缺，不编造。

### 第 3 步：确定性构建与证据绑定

```bash
python3 /skills/weekly-skill/scripts/nanopub_build.py \
  --case /input/case.json \
  --draft /app/work/assertions.json \
  --source /app/work/source.txt \
  --out /app/output
```

退出码：`0=success`、`3=partial`、`5=failed/refused`。三者都有结构化 result；有可序列化断言时就有合法 RDF，不因可选元数据缺失而零交付。

脚本实际完成：
- 校验 SPO/RDF term，残缺条目录入 `skipped_reason`，不写半条三元组；
- 在 source 中找**唯一逐字** quote 并回填 charStart/End；多匹配/未找到不称 verified；
- 写科学 SPO + reification/qualifier、source/evidence provenance 和 creator/time/license/confidence pubInfo；
- 生成 `nanopubs.trig`、`assertion_table.md`、`evidence_map.md`、`rdf_validation.json`、`result.json`；
- 相同输入的 URN、RDF、表格与 result 字节一致；输出目录不写入 result，跨目录也确定。

### 第 4 步：机器校验与复核

```bash
python3 /skills/weekly-skill/scripts/nanopub_check.py /app/output/nanopubs.trig
python3 /skills/weekly-skill/scripts/rdf_validate.py \
  /app/output/nanopubs.trig --json /app/work/independent-rdf.json
python3 /skills/weekly-skill/scripts/selfcheck.py \
  --out /app/output --case /input/case.json --main nanopubs.trig
```

- `nanopub_check.py`：stdlib 词法、前缀、句点、四图、证据/置信度/限定检查，退出 0/1/2。
- `rdf_validate.py`：有 RDFLib 时实际 `Dataset.parse(format="trig")`，逐 root 检查三部图链接、图存在/非空与科学 SPO。无 RDFLib 时明确 `parser=unavailable`，不谎称独立解析成功；stdlib 检查仍执行。
- `selfcheck.py`：交付/契约自查。修复一轮后仍有 RDF 错误的图不得标 success；错误记入 uncertainty/skipped_reason，保留其他合法部分。
- 人工至少复核一条：subject 是否混淆、关系方向和 object 数値/单位是否与原文一致；脚本通过不等于科学内容正确。

### 第 5 步：契约与最终答复

Builder 已回填 case_id 和 output_contract 全键：可推导的由实际产物填写，case 自带字段原样直通，不可推导为 null + uncertainty。需要额外自然语言答案时，Agent 从真实断言/RDF 整理，不能为补字段编造。

```bash
python3 /skills/weekly-skill/scripts/contract_check.py \
  --case /input/case.json --draft /app/output/result.json
```

| 题面要求 | 实际产物 |
|-|-|
| 阅读/解析结果 | `nanopubs[]`（id、SPO、qualifiers、confidence）+ 合法 `nanopubs.trig` |
| 证据与边界 | 四图、原文 quote+offset+locator、source chain、uncertainty、skipped_reason |
| 运行状态 | success/partial/failed、CLI 0/3/5、结构化 refusal、change_log |

## 3. RDF 三层语义与字段

### assertion

保留科学 `subject predicate object`。`statement` 节点用 RDF reification 关联同一三元组，记录 description、conditionScope 和 qualifiers。qualifier 不覆盖原始数値或条件。领域本体 IRI 必须由材料/用户提供；否则只用本地稳定词表。

### provenance

assertion 图和 statement 节点用 `prov:wasDerivedFrom` 挂回**输入已给出**的来源 IRI；否则记录字面来源状态。包括：
- `evidenceQuote`、`hasEvidenceAnchor`、page/paragraph/figure/table locator；
- 唯一逐字命中时的 `evidenceCharStart` / `evidenceCharEnd` 与 `quoteVerification`；
- direct/indirect/author statement 与 experimental/computational/citation/other；
- 原论文 title/authors/year/version/identifier/material_file。作者 ORCID 只有材料给出才使用。

### pubInfo

记录本地序列化创建者（agent 或明确 ORCID）、`pav:createdWith`、创建时间、许可、case_id、`confidence=High/Medium/Low` 和 basis，以及 URN 边界。缺时间/许可保留 unreported 状态和 partial，不把本地导出伪装成公开出版。

### result.json

`case_id`、`status`、`nanopub_file`、`nanopubs`、`assertion_count`、`sources`、`uncertainty`、`skipped_reason`、`change_log`、`rdf_validation`，加 case 原始 output_contract 全字段。`rdf_validation` 分开记录 stdlib 与 RDFLib 结果、三元组数和图错误。

## 4. 异常处理

| 情况 | 真实行为 |
|-|-|
| case/draft 不可读 | 对应 unreadable refusal，result=failed，退出 5；可读 case 的契约仍保留 |
| 缺 SPO/重复 id/非法 URI | 逐条 skipped；仍有合法断言则 partial，否则 `nanopub.no_valid_assertion` 退出 5 |
| quote 未找到/多匹配/无 source | `not_found` / `multiple_matches_unresolved` / `not_checked`，partial，不声称 exact |
| 证据与断言冲突 | 保留两处 anchor，分别挂证据或都待发，不替作者选值 |
| 来源/时间/许可缺失 | 未报告状态并 partial；无 DOI/ORCID 或当前时间自动补全 |
| 提供的 `np_uri` | root 原样保留；不把本地生成或验证误称为网络注册/签名 |
| 有部分合法图 | RDF 与三件套照常交付，status=partial，skipped_reason 给人工接管点 |

机器可查代码与位置一览（不要把代码当作可删除错误清单的空缺）：
`nanopub.case_unreadable`、`nanopub.draft_unreadable`、`nanopub.no_assertions`、
`assertion.not_object`、`assertion.incomplete_spo`、`assertion.invalid_rdf_term`、
`assertion.invalid_supplied_uri`、`assertion.duplicate_id`、`assertion.invalid_confidence`、
`assertion.condition_unreported`、`evidence.locator_missing` 位于断言/证据校验；
`evidence.missing`、`evidence.not_checked`、`evidence.not_found`、
`evidence.multiple_matches_unresolved`、`source.identifier_unreported`、
`source.title_unreported`、`pubinfo.created_unreported_or_invalid`、`pubinfo.license_unreported`
位于元数据降级。全部进入对应 uncertainty/skipped_reason，或使无合法断言的 run 走 refusal。

## 5. 参考实现落地

- [Nanopublication/nanopub-py](https://github.com/Nanopublication/nanopub-py)：采用 RDFLib Graph 构建 assertion、profile/ORCID 归因与发布职责分离的思路。本包不调用发布客户端、不造 keys/signatures；显式分离 assertion/provenance/pubInfo，并硬性区分输入 ID 与本地 URN。
- [RDFLib](https://github.com/RDFLib/rdflib)：以 Dataset/Graph 和 URIRef/Literal 实际解析 TriG 并检查图链接，而不是用“关键词存在”替代图完整性。stdlib 校验是无依赖降级路径；语法正确不证明语义科学正确。

## 6. 验证、示例与限制

可选开发检验（不是正式案例的强制前置步骤）：

```bash
python3 /skills/weekly-skill/scripts/bench_nanopub.py
```

10 个合成场景覆盖 clean baseline、冷重复字节确定、证据缺失、元数据不 mint、重复 id、SPO 拒绝、坏 case/draft、caller URI 保留和无 source 降级。另以隔离 RDFLib 环境独立复核一条 178 mV SPO、单位限定、证据偏移、DOI/许可/时间与三部图链接；这些不是平台固定案例成绩。

真实可运行 fixture：
- `examples/fixtures/synthetic_case.json`
- `examples/fixtures/synthetic_draft.json`
- `examples/fixtures/synthetic_source.txt`
- 负路径 `examples/negative_cases.md`、`examples/fixtures/bad_assertion_no_evidence.trig`

局限：构建器不自动做 NLP 原子拆解和语义证据充分性判断，这些仍需 Agent 阅读完成。quote 精确命中不等于该句必然支持断言。它具有文本提取/校验/序列化能力，但不联网，不发布 trusty URI，不签名。`pav:createdBy` 是本地序列化创建者，不等于论文作者（后者在 provenance 记录）。

细则见 `references/method_rules.md`、`references/element_checklist.md`、`references/style_guide.md`、`references/failure_modes.md`。手写模板可作参考，但正式产物优先使用 `nanopub_build.py`，避免模板与真实值脱节。

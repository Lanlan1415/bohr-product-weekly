# 合成案例（全合成，非真实论文、非正式案例结果）

> 本案例的论文、数据、断言、标识符**全部为虚构**，仅演示
> 输入→断言表→TriG→result.json 的完整形态，并作为脚本自检 fixture。
> **验证与限制声明（v2）**：本 Skill 仅在此类本地合成 fixture 上验证过；
> 平台的 3 个隐藏案例与对照基线未在本地运行，不声称任何分数。
> 负路径自测（必须被拒绝的用例）见 examples/negative_cases.md。

## 1. 输入材料（虚构论文片段，/input/paper_mos2.txt）

```text
等离子体处理对 MoS2 析氢催化性能的影响（虚构）
张某, 李某. 虚构材料学报, 2024. DOI: 10.0000/syn.2024.001

3 结果
3.1 处理 60 s 样品在 10 mA/cm2 下过电位为 178 mV, 低于未处理的 312 mV (表1)。
3.2 Tafel 斜率由 121 mV/dec 降至 69 mV/dec (图2)。

4 讨论与结论
活性提升归因于硫空位增多。局限: 仅测试酸性体系。
```

`/input/case.json`（虚构）：
`{"case_id": "syn-009", "output_contract": ["nanopub_file", "assertion_count"]}`

## 2. 断言登记表（assertion_table.md 节选）

| id | 自然语言陈述 | 主体 | 关系 | 客体 | 证据锚点 | 证据类型 | 置信度 | 状态 |
|---|---|---|---|---|---|---|---|---|
| A1 | 60 s 等离子体处理的 MoS2 在 10 mA/cm2 下过电位为 178 mV | ex:MoS2-Plasma60s | ex:overpotentialAt10mAcm2 | "178"^^xsd:float | [S1 §3.1 表1] | 直接 | high | 已发布 |
| A2 | 未处理 MoS2 在 10 mA/cm2 下过电位为 312 mV | ex:MoS2-Pristine | ex:overpotentialAt10mAcm2 | "312"^^xsd:float | [S1 §3.1 表1] | 直接 | high | 已发布 |
| A3 | 60 s 处理样品的 Tafel 斜率为 69 mV/dec | ex:MoS2-Plasma60s | ex:tafelSlope | "69"^^xsd:float | [S1 §3.2 图2] | 直接 | high | 已发布 |
| A4 | 60 s 处理样品活性高于未处理样品（过电位更低） | ex:MoS2-Plasma60s | ex:lowerOverpotentialThan | ex:MoS2-Pristine | [S1 §3.1 表1] | 间接 | medium | 已发布 |
| A5 | 活性提升的机制是硫空位增多 | ex:MoS2-Plasma60s | ex:activityEnhancementMechanism | ex:SulfurVacancyIncrease | [S1 §4] | 作者声明 | low | 已发布 |

拆解说明：原文 §3.1 一句复合句拆成 A1/A2（并列主体）+ A4（对比关系，证据
类型"间接"因需合并两行数值）；§4 归因句为作者声明，置信度 low。

## 3. 生成的一条 nanopub（A1，TriG）

```turtle
@prefix : <http://example.org/np/syn-009-a1#> .
@prefix np: <http://www.nanopub.org/nschema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix pav: <http://purl.org/pav/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix ex: <http://example.org/ontology/> .

:Head {
  : np:hasAssertion :assertion ;
    np:hasProvenance :provenance ;
    np:hasPublicationInfo :pubInfo ;
    a np:Nanopublication .
}

:assertion {
  ex:MoS2-Plasma60s ex:overpotentialAt10mAcm2 "178"^^xsd:float .
  ex:MoS2-Plasma60s ex:measuredIn ex:H2SO4-0.5M-ThreeElectrode .
}

:provenance {
  :assertion prov:wasDerivedFrom <https://doi.org/10.0000/syn.2024.001> .
  :assertion ex:hasEvidenceAnchor "S1 §3.1 表1" .
  :assertion ex:evidenceType ex:DirectMeasurement .
}

:pubInfo {
  : pav:createdBy ex:syntheticDemoAuthor .
  : dcterms:created "2024-01-15"^^xsd:date .
  : ex:confidence ex:High .
  : ex:confidenceBasis "数值直接取自原文表1，无换算" .
}
```

A2-A5 各生成同构 nanopub（不同命名空间 :syn-009-a2# 等），合并为 nanopubs.trig。

## 4. result.json

```json
{
  "case_id": "syn-009",
  "status": "success",
  "nanopub_file": "nanopubs.trig",
  "assertion_count": 5,
  "sources": ["S1"],
  "uncertainty": ["A5 为作者声明型证据，置信度 low，建议人工复核机制归因"],
  "change_log": ["v1 发布 A1-A3 并通过校验", "v2 补 A4/A5",
                 "contract_check.py 自查后落 result.json（退出码不作为交付门禁）",
                 "selfcheck.py 自查后交付"]
}
```

## 5. v2 增补（保守追加，不改 v1 流程）

断言表 v2 新增两列（以 A1 为例）：**条件范围** = "0.5M H2SO4 三电极体系；
仅酸性条件"；**证据形式** = 实验数据。对应 TriG provenance 图可选三元组：

```turtle
:assertion ex:conditionScope "0.5 M H2SO4 三电极体系；仅酸性条件" .
:assertion ex:evidenceForm ex:ExperimentalData .
```

nanopub_check.py 的 N4（证据挂接）/N5（置信度）/N6（条件范围与证据形式）
增强检查仅 WARN，不判 FAIL；result.json 在写入前先经 contract_check.py
核对（verify-then-write，建议性自查：FAIL 项记入 uncertainty 后照常落盘，
脚本退出码仅供定位问题，不作为交付门禁）。

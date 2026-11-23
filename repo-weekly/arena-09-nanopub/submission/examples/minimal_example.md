# 最小调用示例（示意，非正式案例结果）

> 本示例仅说明接口与流程，**不是**正式案例的运行结果。
> **验证与限制声明（v2）**：本 Skill 仅做过本地合成验证；平台的 3 个隐藏
> 案例与对照基线未在本地运行，不声称任何分数。

## 输入

- `/input/case.json`（示意）：
  `{"case_id": "demo-009", "output_contract": ["nanopub_file", "assertion_count"]}`
- `/input/paper.pdf`：一篇待拆断言的论文。

## 调用

```
python3 /skills/weekly-skill/scripts/inventory.py /input \
    --out /app/work/materials_register.md
# （人工）定位结论 -> assertion_table.md -> evidence_map.md -> nanopubs.trig
python3 /skills/weekly-skill/scripts/nanopub_check.py /app/output/nanopubs.trig
python3 /skills/weekly-skill/scripts/selfcheck.py \
    --out /app/output --case /input/case.json --main nanopubs.trig
```

## 示意输出（片段，非正式案例结果）

nanopubs.trig 片段（一条 nanopub 的 Head 与 assertion 图）：

```turtle
:Head {
  : np:hasAssertion :assertion ;
    np:hasProvenance :provenance ;
    np:hasPublicationInfo :pubInfo ;
    a np:Nanopublication .
}
:assertion {
  ex:SampleX ex:bandGap "1.55"^^xsd:float .
  ex:SampleX ex:measuredBy ex:UVVisDiffuseReflectance .
}
```

nanopub_check.py 输出（示意）：

```
  [PASS] S1/S2 词法完整、括号配平
  [PASS] N1 hasAssertion/hasProvenance/hasPublicationInfo 齐全
校验结论：通过（共 1 个文件）
```

> 脚本退出码仅供定位问题，不作为交付门禁：脚本报 FAIL 时修一轮、把修不完的
> 缺口记入 uncertainty/skipped_reason，然后照常交付当前最好版本。

result.json（示意，字段名以真实 case.json 为准）：

```json
{"case_id": "demo-009", "status": "success",
 "nanopub_file": "nanopubs.trig", "assertion_count": 6,
 "sources": ["S1"], "uncertainty": [], "change_log": ["v1 交付"]}
```

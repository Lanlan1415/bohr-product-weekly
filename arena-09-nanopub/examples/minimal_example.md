# 最小调用示例（全合成，非正式案例结果）

以下调用会真实构建两条虚构 nanopub。输入文件都随包提供，不代表平台固定案例或预先写好的正式答案。

```bash
python3 /skills/weekly-skill/scripts/nanopub_build.py \
  --case /skills/weekly-skill/examples/fixtures/synthetic_case.json \
  --draft /skills/weekly-skill/examples/fixtures/synthetic_draft.json \
  --source /skills/weekly-skill/examples/fixtures/synthetic_source.txt \
  --out /app/output
python3 /skills/weekly-skill/scripts/nanopub_check.py /app/output/nanopubs.trig
python3 /skills/weekly-skill/scripts/rdf_validate.py /app/output/nanopubs.trig
python3 /skills/weekly-skill/scripts/selfcheck.py \
  --out /app/output --case /skills/weekly-skill/examples/fixtures/synthetic_case.json \
  --main nanopubs.trig
```

实测 clean fixture：builder 退出 0、`case_id=SYNTHETIC-NANOPUB-DEMO`、2 条断言、`nanopub_file=nanopubs.trig`，stdlib 和隔离 RDFLib Dataset 均验证可解析。输出还包括 `assertion_table.md`、`evidence_map.md`、`rdf_validation.json` 和全契约 `result.json`。

含义示意图（请以实际运行产生的 URN 为准，不手抄为正式 URI）：

```turtle
:Head {
  :this a np:Nanopublication ;
    np:hasAssertion :assertion ;
    np:hasProvenance :provenance ;
    np:hasPublicationInfo :pubInfo .
}
:assertion {
  <本地主体> <urn:nanopub:local:vocab:overpotentialAt10mAcm2> "178"^^<http://www.w3.org/2001/XMLSchema#integer> .
}
```

真实 object 和单位 qualifier 可由 RDFLib 逐条复核；evidence_map.md 中的 quote 与 `char_start/char_end` 可按 synthetic_source.txt 重放。DOI `10.0000/syn.2024.001` 是 fixture 明确给出的虚构输入，仅用于展示“保留而非 mint 标识符”的代码路径，不代表真实论文。

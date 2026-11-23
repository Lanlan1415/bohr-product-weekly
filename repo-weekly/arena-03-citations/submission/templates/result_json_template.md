# result.json 透传规则与示意

## 透传规则（红线）

1. 打开 `/input/case.json`，原样读取 `case_id` 与 `output_contract`；
2. `output_contract` 声明的**每一个字段名**都必须出现在 result.json 顶层，
   字段名一字不差（大小写、下划线），不得臆造、增删、改名；
3. 字段值填写实际交付物的相对路径或内容摘要；确实无法产出的字段填 null 并在
   uncertainty 说明；
4. 除契约字段外，必须另有：`status`（success/partial/failed）、`sources`、
   `uncertainty`、`change_log`；
5. partial 也是合法结果：写明已完成什么、缺什么、为什么；
6. **交付韧性**：status 为 partial/failed 时增加 `skipped_reason`（字符串或列表），
   逐项列出未完成阶段及原因；finalize 永远要产出 result.json；
7. **写入前建议跑契约前置校验（建议性）**：先写 `/app/work/result_draft.json`，
   运行 `scripts/contract_check.py` 核对；FAIL 项能修则修一轮，修不完的逐项写入
   uncertainty 与 skipped_reason，然后照常复制为 `/app/output/result.json`——
   脚本退出码仅供定位问题，不作为交付门禁。

## 示意 JSON（示意结构，非正式案例结果；字段名以实际 case.json 为准）

```json
{
  "case_id": "<与 case.json 完全一致>",
  "status": "partial",
  "revised_manuscript": "manuscript_revised.md",
  "reference_list": "manuscript_revised.md#参考文献",
  "citation_report": "citation_check_report.md",
  "dedupe_report": "dedupe_report.md",
  "evidence_map": "evidence_map.md",
  "sources": ["S1", "S2", "S3"],
  "uncertainty": "条目 S7 缺页码已标注「[缺: 页码]」待确认；S9 与 S10 疑似重复但判据不足，两条均保留；DOI 未联网核验。",
  "change_log": [
    "按首次出现顺序重排编号，旧号→新号映射见 numbering_map.md",
    "合并重复条目 2 对（判据：同 DOI / 相似度 0.91+同年），正文引用已统一指向保留条",
    "全部条目转换为 GB/T 7714—2015 顺序编码制"
  ],
  "skipped_reason": ["PDF 原件文本层不可读，仅按题录著录（ocr-tool 不可用）"]
}
```

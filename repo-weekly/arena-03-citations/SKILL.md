---
name: managing-citations-references
description: >-
  参考文献与引用管理：依据固定科研材料（真实稿件 + 真实文献库）完成引用插入与定位、
  编号更新、文献去重、GB/T 7714（兼顾 APA/Vancouver，以任务要求为准）格式规范化、
  来源核验与正文—文献表一致性检查，交付可继续编辑的修订稿、同步文献表、校验报告与
  来源映射。当 /input/case.json 或用户指令涉及「整理参考文献」「引用核对」「文献去重」
  「格式转换」「正文与文献表对不上」时触发；缺失字段只显式标注，绝不编造页码/年份/DOI。
---

# 参考文献与引用管理

## 1. 用途与触发

在组织方固定案例上完成参考文献与引用管理任务：从真实稿件与文献库出发，做到
**挂得对**（引用落在真正需要支撑的论断句）、**编得顺**（编号连续、按首次出现排序、
交叉引用同步）、**收得净**（重复条目合并且判据可解释）、**对得上**（条目真实、
元数据准确、论断与文献匹配）。

触发语境示例：读取 /input/case.json 的参考文献/引用整理任务；「把这份稿件的引用
按 GB/T 7714 整理」「合并文献库重复条目」「检查正文引用与文末列表是否对应」。

**不应触发**的邻近场景：
- 纯文献检索、选题综述（没有给定稿件与文献库）——那是调研任务；
- 引文计量分析（被引统计、h 指数、期刊排名）——不改变稿件本身。

## 2. 运行环境契约

- 先读 `/input/case.json`，提取 `case_id` 与 `output_contract`；最终
  `/app/output/result.json` 必须含 `case_id` 及 `output_contract` 声明的**全部原始
  字段**（字段名以 case.json 为准，不臆造）。
- 材料在 `/input/`（case.json、task.md、稿件、文献库、可能含 PDF）；一律只读。
- 工作文件在 `/app/work/`；交付在 `/app/output/`：修订稿 + 同步文献表 + 校验/去重
  报告 + 来源映射 + `result.json`（诚实 status、sources、uncertainty、change_log）。
- 目标规范（GB/T 7714 / APA / Vancouver、顺序编码制 / 著者-出版年制）**以 task.md
  与 case.json 的要求为准**；未指明时默认 GB/T 7714—2015 顺序编码制。
- 预算 64 次请求 / 900 秒：**第 3 步结束后先落盘一份诚实 partial**（哪怕只有材料
  登记表 + 初步文献表），再迭代改进。
- **契约前置校验（建议性）**：result.json 先写草稿 `/app/work/result_draft.json`，
  运行 contract_check.py 核对 case_id 与 output_contract 字段齐全；校验是建议性
  的——FAIL 项能修则修一轮，修不完的逐项写入 uncertainty 与 skipped_reason，
  然后照常落盘 `/app/output/result.json`；退出码不阻止交付。
- **交付韧性（finalize 永远有产物）**：任一阶段失败或超时，都必须交付已完成的
  诚实部分（status=partial），result.json 附 `skipped_reason` 列出未完成阶段及
  原因；禁止因局部失败而不产出 result.json。
- 禁止预制答案、编造文献条目/页码/年份/DOI、新增材料之外的事实。

> **验证与限制声明**：本技能全部脚本与示例仅在本地合成数据上验证（scripts/
> run_selftest.py 可复跑）；平台的 3 个隐藏案例与对照组未在本地运行，本包不
> 声称、不预测任何评测分数。示例均为合成/示意。

## 3. 脚本调用规则

全部 stdlib-only、utf-8-sig 读文件、只读输入目录、按**绝对路径**调用、路径用正斜杠、
不依赖 CWD：

```
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/dedupe_refs.py --refs /app/work/reflist_raw.md --output /app/work/dedupe_report.md
python3 /skills/weekly-skill/scripts/citation_check.py --manuscript /app/output/manuscript_revised.md --output /app/output/citation_check_report.md
python3 /skills/weekly-skill/scripts/mapping_check.py --map /app/output/numbering_map.md --manuscript /app/output/manuscript_revised.md --output /app/output/mapping_check_report.md
python3 /skills/weekly-skill/scripts/roundtrip_check.py --refs /app/work/reflist_final.md --export-dir /app/output --output /app/output/roundtrip_report.md
python3 /skills/weekly-skill/scripts/contract_check.py --case-json /input/case.json --result-json /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --output-dir /app/output --case-json /input/case.json
```

本地开发自测（含必须被拒绝的负路径用例）：
`python3 /skills/weekly-skill/scripts/run_selftest.py`

退出码约定：0 = 通过；1 = 发现问题或输入不可读（报告已写明细节）。
**退出码仅供定位问题，不作为交付门禁**——任何脚本退出码都不阻止交付；
每个脚本最多运行 2 次（首次 + 修复后复查一次），两轮后照常交付。
**降级声明**：任一脚本缺失或运行失败时，改按 references/method_rules.md 相应章节
手工执行同等检查（§3 编号重排、§4 去重判据、§6 一致性核对），并在 result.json 的
uncertainty 中注明「脚本不可用，已手工核对」。

## 4. 主流程

### 交付优先原则（v3，最高优先级）

- **先有交付，再求完美**：任何时刻 `/app/output/` 里都要有一份当前最好的可交付物
  （哪怕是 status=partial 的诚实初稿 + result.json）；先完成、再完美，严禁把
  「全部校验通过」作为落盘前提。
- **请求预算分配（64 次）**：≤10 次读材料与契约；≤30 次产出主交付物；≤10 次
  校验与修复；剩余全部留给 finalize（落盘交付物 + 写 result.json）。
- **预算红线**：预算过半仍未落盘初稿 → 立即停止新探索，把当前版本落盘；
  剩余约 10 次请求 → 停止一切修复与校验，直接 finalize。
- **脚本两轮封顶**：每个脚本最多运行 2 次（首次检查 + 修复后复查一次）；
  两轮后无论结果如何都进入交付，未修复项逐项写入 result.json 的
  uncertainty 与 skipped_reason。任何脚本退出码都不阻止交付。

0. **解析契约**：读 `/input/case.json` 与 `/input/task.md`，把 case_id、契约字段、
   目标规范、引用制式写入 `/app/work/contract_notes.md`（可机器校验的中间文件）。
1. **材料清点**：运行 inventory.py 生成材料登记表；原样复制文献库到
   `/app/work/reflib_snapshot.*` 作为快照（不改写原件）。
2. **文献库整理**：解析全部条目，建立 S1..Sn 登记表（templates/evidence_map_template.md）；
   运行 dedupe_refs.py 查重，合并决策（判据、保留条、被并条）写入去重报告；
   缺失字段显式标注「[缺: 字段名]」，**不编造**。
3. **格式规范化**：按 references/gbt7714_field_templates.md 逐条改写为目标规范；
   标点/大小写/期刊缩写规则见 references/style_guide.md。完成后**立即落盘 partial**
   （文献表 + 登记表 + result.json 草稿）。
4. **正文引用处理**：按 references/method_rules.md §1 定位需要支撑的论断句并插入
   引用（一句多引、多句一引规则在 §2）；插入/删除/调序后按 §3 以首次出现顺序整体
   重排编号，同步图表注与附录引用。**凡发生插入/删除/合并/重排，必须填写原编号↔
   新编号双向映射表**（templates/numbering_map_template.md →
   `/app/output/numbering_map.md`），并用 mapping_check.py 校验。
5. **交叉校验**：运行 citation_check.py，处理全部 ERROR（缺引/多引/断号/错位）与
   WARN（字段 lint）；无法修复的写入待确认清单。
6. **来源核验与匹配**：按 method_rules.md §6 逐条核验（DOI 形态、年份/卷期页逻辑、
   论断—文献主题匹配）；无法核验的标「[待核验]」，匹配存疑的标「[引证存疑]」，
   均列入 uncertainty，不联网编造。
7. **文献库往返检查**：对最终文献表运行 roundtrip_check.py，验证导出为 BibTeX/RIS
   后关键字段（作者/年份/DOI/类型）可无损回导；导出文件一并交付，LOSS 项必须
   修复或在 uncertainty 说明。
8. **交付**：先写 `/app/work/result_draft.json` 并运行 contract_check.py 做契约前置
   校验（建议性：FAIL 项能修则修一轮，修不完记入 uncertainty/skipped_reason，
   退出码不阻止落盘），然后按 templates/output_skeleton.md 输出修订稿、同步文献表、
   citation_check 报告、去重报告、编号映射表、往返报告、evidence_map.md，以及
   透传契约字段的 result.json（templates/result_json_template.md）。

## 5. 质量门（自查清单，不阻塞交付）

本节是交付前的自查清单而非门禁：任何一项不满足都不阻止交付——FAIL 项能修
则修一轮，修不完的逐项写入 result.json 的 uncertainty 与 skipped_reason，
然后照常落盘交付。对照 references/element_checklist.md 逐项勾选，
关键锚点（建议性）：
- 契约字段 100% 透传，status 诚实；
- 六类动作（插入/编号/去重/转换/核验/一致性）凡任务要求者均有产物佐证；
- citation_check.py 无 ERROR；dedupe 候选全部有合并/保留决策记录；
- 每个 [S#] 已登记；每条缺失字段显式标注；无任何编造。

## 6. 反馈回路

validate → fix → deliver（每个脚本最多两轮：检查 → 修一轮 → 复查一次）：
1. 跑 citation_check.py → 修 ERROR/WARN → 复查一次；两轮后仍有 ERROR，将剩余项
   全部写入待确认清单与 result.json 的 uncertainty，立即交付；
2. 跑 selfcheck.py → 修 FAIL → 复查一次；两轮后仍有 FAIL：逐项记入
   uncertainty/skipped_reason，立即交付；
3. 任一轮无法收敛时，保持已落盘的 partial，在 uncertainty 中写明卡点，照常交付，
   不硬凑；任何脚本退出码都不阻止交付。

## 7. 异常处理

- **材料缺失/读不出**：登记为「仅登记」，用 pdf-text-tool / ocr-tool 处理；仍读不出
  则 partial 交付并说明缺口，不凭文件名臆测内容。
- **文献库字段缺失**：显式标注「[缺: 字段名]」+ 列入待确认，不编造页码/年份/DOI。
- **DOI 解析失败/无法联网核验**：标「[待核验]」，不臆造核验结论。
- **条目歧义（疑似重复但判据不足）**：两条都保留，写入待确认清单说明疑点。
- **编号冲突**：以正文首次出现顺序为准整体重排，改动写入 change_log。
- **稿件格式不支持（如损坏 docx）**：交付 markdown 版修订稿并说明；有 office-renderer
  时补 docx + PDF 预览。
- **超时**：立即交付当前 partial（文献表 + 校验报告 + result.json，status=partial）。
- **任一阶段失败（finalize 韧性）**：交付已完成的诚实部分 + result.json
  （status=partial/failed，`skipped_reason` 列出未完成阶段及原因）；禁止因局部
  失败而不产出 result.json。

## 8. 资源索引

- `references/element_checklist.md`：要素齐全性清单与评分锚点（质量门依据）。
- `references/method_rules.md`：引用定位、引用形式、编号重排、去重判据、格式转换、
  来源核验的判定标准与反模式。
- `references/gbt7714_field_templates.md`：GB/T 7714—2015 各文献类型字段模板 +
  APA 7 / Vancouver 对照 + 缺失字段标注约定。
- `references/style_guide.md`：标点、大小写、期刊缩写、中英混排规范。
- `references/failure_modes.md`：基础 Agent 典型失败模式与对策。
- `templates/output_skeleton.md`：交付物骨架（修订稿/文献表/报告）。
- `templates/result_json_template.md`：契约透传规则与示意 JSON。
- `templates/evidence_map_template.md`：S1..Sn 登记 + 论断—引用映射 + 修改记录模板。
- `templates/numbering_map_template.md`：原编号↔新编号双向映射表模板与填写规则。
- `examples/minimal_example.md`：最小调用示例（示意，非正式案例结果）。
- `examples/synthetic_case.md`：完整合成案例（全合成）。
- `scripts/inventory.py`：材料清点；`scripts/dedupe_refs.py`：去重检测；
  `scripts/citation_check.py`：引用—文献交叉校验；`scripts/selfcheck.py`：交付自查；
  `scripts/mapping_check.py`：编号映射表校验；`scripts/roundtrip_check.py`：文献库
  BibTeX/RIS 往返无损检查；`scripts/contract_check.py`：result.json 契约前置校验；
  `scripts/run_selftest.py`：负路径自测（本地合成 fixture）。

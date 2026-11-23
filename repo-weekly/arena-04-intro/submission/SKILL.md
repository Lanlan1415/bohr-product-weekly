---
name: writing-introductions
description: >-
  引言与相关工作写作：依据固定科研材料（本文稿件/方法结果 + 文献库）撰写可直接进入
  论文的引言与相关工作——漏斗结构（领域→具体问题→研究缺口→本文贡献）、按论点分组
  综合而非逐篇罗列、对比表（方法/数据/结论/局限）、缺口由已引文献推出且带反例界定、
  贡献与缺口一一对应、每个论断挂 [S#] 来源。当 /input/case.json 或用户指令涉及
  「写引言」「整理相关工作」「补引用」「核对贡献与引用覆盖」时触发；不编造文献与数据。
---

# 引言与相关工作写作

## 1. 用途与触发

在组织方固定案例上完成引言与相关工作写作：做到**立得住**（背景指向真实脉络与
具体问题，不空转）、**分得清**（相关工作按问题/方法路线分组比较，不拼接摘要）、
**说得实**（缺口由已引文献推出，断言有证据或标注为作者判断）、**对得上**（贡献
与实际方法/图表/结果一一对应，引用经得起逐条核对）。

触发语境：读取 /input/case.json 的引言/相关工作写作任务；「根据这些材料写引言」
「把相关工作按路线分组」「检查贡献和引用是否对得上」。

**不应触发**的邻近场景：
- 全文润色/语言修改（不动结构与论证）——用润色类技能；
- 摘要、投稿信、审稿回复写作——体裁不同，骨架与核对项不同。

## 2. 运行环境契约

- 先读 `/input/case.json`，提取 `case_id` 与 `output_contract`；最终
  `/app/output/result.json` 必须含 `case_id` 及 `output_contract` 声明的**全部
  原始字段**（字段名以 case.json 为准，不臆造）。
- 材料在 `/input/`（case.json、task.md、本文稿件/方法结果、文献库、可能含 PDF）；
  一律只读。语言（中/英）、引用格式、目标期刊以 task.md 与 case.json 为准。
- 工作文件在 `/app/work/`；交付在 `/app/output/`：成稿（引言+相关工作）+ 证据表
  （evidence_map）+ 结构检查报告 + `result.json`（诚实 status、sources、
  uncertainty、change_log）。
- 预算 64 次请求 / 900 秒：**成稿优先**——第 3 步就落盘一份覆盖漏斗四段的完整
  初稿（而非逐段拼凑到最后才成文），再对照检查迭代精修；初稿即诚实 partial。
- **契约前置校验（建议性）**：result.json 先写草稿 `/app/work/result_draft.json`，
  运行 contract_check.py 核对 case_id 与 output_contract 字段齐全；校验是建议性
  的——FAIL 项能修则修一轮，修不完的逐项写入 uncertainty 与 skipped_reason，
  然后照常落盘 `/app/output/result.json`；退出码不阻止交付。
- **交付韧性（finalize 永远有产物）**：任一阶段失败或超时，都必须交付已完成的
  诚实部分（status=partial），result.json 附 `skipped_reason` 列出未完成阶段及
  原因；禁止因局部失败而不产出 result.json。
- 禁止预制答案、编造文献/数据/实验结论、新增材料之外的事实；转述他人工作必须
  基于材料中可得的内容。

> **验证与限制声明**：本技能全部脚本与示例仅在本地合成数据上验证（scripts/
> run_selftest.py 可复跑，含幽灵引用等必须被拒绝的负路径用例）；平台的 3 个
> 隐藏案例与对照组未在本地运行，本包不声称、不预测任何评测分数。示例均为
> 合成/示意。

## 3. 脚本调用规则

全部 stdlib-only、utf-8-sig 读文件、只读输入目录、按**绝对路径**调用、路径用
正斜杠、不依赖 CWD：

```
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/structure_check.py --draft /app/output/manuscript.md --evidence /app/output/evidence_map.md --output /app/output/structure_check_report.md
python3 /skills/weekly-skill/scripts/contract_check.py --case-json /input/case.json --result-json /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --output-dir /app/output --case-json /input/case.json
```

本地开发自测（含必须被拒绝的负路径用例）：
`python3 /skills/weekly-skill/scripts/run_selftest.py`

退出码约定：0 = 通过；1 = 发现问题或输入不可读（报告写明细节）。
**退出码仅供定位问题，不作为交付门禁**——任何脚本退出码都不阻止交付；
每个脚本最多运行 2 次（首次 + 修复后复查一次），两轮后照常交付。
**降级声明**：脚本缺失或失败时，按 references/element_checklist.md 手工逐项核对
（漏斗四段、对比表维度、[S#] 登记、贡献-缺口对应），并在 uncertainty 注明
「脚本不可用，已手工核对」。

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

0. **解析契约**：读 case.json 与 task.md，把 case_id、契约字段、语言、引用格式、
   篇幅约束写入 `/app/work/contract_notes.md`。
1. **材料清点**：inventory.py 生成登记表；区分「本文材料」（方法/实验/图表）与
   「文献库」（他人工作）。
2. **素材抽取**（两个可机器校验的中间文件）：
   - `/app/work/source_cards.md`：文献库每篇登记为 S#，抽取 问题设定/方法路线/
     数据与评价/结论/局限（只写材料中有的，缺则标「材料未述」）；
   - `/app/work/claim_pool.md`：从本文材料抽取可用证据（方法要点、数据集、指标、
     图表编号、章节），作为贡献条目的证据池。
3. **快速全稿（成稿优先，manuscript-first）**：不逐段拼凑——基于 source_cards 与
   claim_pool **一次性写出覆盖漏斗四段的完整初稿** → `/app/work/draft_v1.md`
   （背景→相关工作→缺口→贡献，每段先求完整通顺，缺口/贡献允许标注「待核」），
   并填相关工作对比表（维度：方法/数据/结论/局限，模板见
   templates/related_work_table_template.md）→ `/app/work/rw_table.md`。
   **此时落盘 partial**：完整初稿 + 证据表 + 对比表 + result.json 草稿——
   900 秒预算内先保住一篇可读全稿，再进入迭代精修。
4. **缺口推导与反查**：从已引文献的共同限制、未覆盖场景、相互冲突的结论三类
   来源推缺口，每条缺口写**反例界定**（什么不算缺口），并做**相邻结果边界界定**
   （method_rules.md §5.1：与最相近工作并置双方结果区间，数值只取自材料）→
   `/app/work/gap_list.md`；回改 draft_v1 的缺口段。
5. **贡献对齐**：每条贡献 = 一句可核对表述 + 对应缺口编号 + 证据指针
   （图/表/节，来自 claim_pool）→ `/app/work/contributions.md`；贡献数 == 缺口数；
   含比较断言的贡献必须带相邻结果区间数值；回改 draft_v1 的贡献段。
6. **精修成稿**：按 references/funnel_writing_guide.md 逐段精修 draft_v1 →
   `/app/output/manuscript.md`：论点优先综合、同组内比较取舍、每个论断挂 [S#]、
   引用格式按任务要求；消除全部「待核」标记。
7. **校验交付**：structure_check.py 生成报告；ERROR 能修则修一轮并复查一次
   （两轮后仍有的写入 uncertainty），先写 `/app/work/result_draft.json` 并运行
   contract_check.py 做契约前置校验（建议性：FAIL 项能修则修一轮，修不完记入
   uncertainty/skipped_reason，退出码不阻止落盘），然后按
   templates/output_skeleton.md 交付成稿、evidence_map.md、检查报告、
   result.json。

## 5. 质量门（自查清单，不阻塞交付）

本节是交付前的自查清单而非门禁：任何一项不满足都不阻止交付——FAIL 项能修
则修一轮，修不完的逐项写入 result.json 的 uncertainty 与 skipped_reason，
然后照常落盘交付。对照 references/element_checklist.md 逐项勾选，
关键锚点（建议性）：
- 四段齐全且承接（背景的具体问题 → 相关工作的分组比较 → 缺口 → 贡献）；
- 对比表 ≥3 维；每个论断挂 [S#] 且已登记；贡献-缺口一一对应；
- 无「近年来受到广泛关注」式空转句（无引用支撑的口号）；
- 转述与材料一致，无夸大（「远超」须有数据出处），无材料外事实。

## 6. 反馈回路

validate → fix → deliver（每个脚本最多两轮：检查 → 修一轮 → 复查一次）：
1. 跑 structure_check.py → 修 ERROR（缺段/缺表/幽灵 [S#]/贡献缺口不对应）→
   复查一次；两轮后仍有 ERROR：剩余项写入 uncertainty，立即交付；
2. 处理 WARN（空转句、贡献缺证据指针、登记未引用）；处理不了的写入 uncertainty；
3. 跑 selfcheck.py → 修 FAIL → 复查一次；两轮后仍有 FAIL：逐项记入
   uncertainty/skipped_reason，立即交付；
4. 无法收敛时保持已落盘 partial，诚实标注卡点，照常交付，不硬凑成稿；
   任何脚本退出码都不阻止交付。

## 7. 异常处理

- **文献库为空/过少**：相关工作如实写「材料库仅 N 篇」，缺口推导受限处标
  「[材料不足]」，不虚构文献凑数。
- **文献查不到原文**：只依据材料中可得信息（题录/摘要）转述，标「基于题录转述」。
- **材料不足以下结论**：该断言删除或明确标注为「作者判断，待证」。
- **目标期刊格式未知**：用中性学术格式（著者-出版年或顺序编码按任务指定），
  在 uncertainty 说明。
- **语言切换**：中/英按 task.md；双语需求时先写任务语言稿，再逐段对齐翻译，
  不机翻直出。
- **缺口缺乏依据**：宁可写「现有材料不足以支撑更强缺口」也不编造缺口。
- **超时**：交付 partial（完整初稿 draft_v1 + 证据表 + 分组对比表 + 缺口/贡献
  列表 + result.json，status=partial）。
- **任一阶段失败（finalize 韧性）**：交付已完成的诚实部分 + result.json
  （status=partial/failed，`skipped_reason` 列出未完成阶段及原因）；禁止因局部
  失败而不产出 result.json。

## 8. 资源索引

- `references/element_checklist.md`：要素齐全性清单与评分锚点（质量门依据）。
- `references/method_rules.md`：漏斗判定、论点优先综合、缺口推导、贡献表述、
  引用覆盖的判定标准与反模式。
- `references/funnel_writing_guide.md`：漏斗四段逐段写法，每段合格例与反例。
- `references/style_guide.md`：学术文体、时态、转述动词、引用标注规范。
- `references/failure_modes.md`：基础 Agent 典型失败模式与对策。
- `templates/output_skeleton.md`：交付物骨架（成稿章节结构含占位说明）。
- `templates/related_work_table_template.md`：相关工作对比表模板与填表规则。
- `templates/result_json_template.md`：契约透传规则与示意 JSON。
- `templates/evidence_map_template.md`：S1..Sn 登记 + 论断映射 + 贡献对照模板。
- `examples/minimal_example.md`：最小调用示例（示意，非正式案例结果）。
- `examples/synthetic_case.md`：完整合成案例（全合成）。
- `scripts/inventory.py`：材料清点；`scripts/structure_check.py`：结构与引用覆盖
  检查（含 v2 行文完成度/相邻结果边界 WARN）；`scripts/selfcheck.py`：交付自查；
  `scripts/contract_check.py`：result.json 契约前置校验；
  `scripts/run_selftest.py`：负路径自测（本地合成 fixture）。

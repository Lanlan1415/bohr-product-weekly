---
name: writing-methods-sections
description: 依据固定科研材料（配置文件、实验日志、代码、数据说明、笔记）撰写或补全论文的方法与实验章节：先清点材料并编号，按六类要素（步骤、实验设置、参数、数据集与划分、对照、复现与限制）逐项抽取并挂来源标记 [S#]，构建带来源列的参数表并用脚本交叉检测全文参数冲突与无来源数值，按中英双语骨架与步骤句式成稿，显式标注材料缺口与待人工确认项，交付可复核的成稿、来源映射与 result.json。当任务要求读取 /input/case.json 并完成"方法与实验章节写作/实验部分补写/参数表整理/可复现性检查"时使用。
---

# 方法与实验章节写作（Writing Methods Sections）

## 用途与触发

当任务要求依据固定科研材料（config、log、代码、数据说明、实验笔记、相关 PDF）**撰写、补写或校订论文的方法与实验章节**时使用本 Skill。核心目标四句话（对应题面"写得全/写得准/做得着/说得住"）：

- **写得全**：步骤、实验设置、参数、数据集与划分、对照、复现与限制六类要素逐项覆盖，不留"能读通但没法重做"的主干；
- **写得准**：每个数值都能指回配置文件、日志或代码的具体位置，绝不为段落顺畅补造数字；
- **做得着**：版本、环境、随机种子、命令、数据获取方式给全，他人能按文重做；
- **说得住**：材料缺口、冲突、不确定处显式标注为待确认项，限制条件落到具体失效场景。

**不应触发的邻近场景**：① 只要求翻译/润色已成稿的方法章节、不核对材料事实（用翻译/润色类 Skill）；② 要求写引言、相关工作或全文（本 Skill 只管方法与实验部分，其他章节请用对应 Skill）。

## 运行环境契约

1. 输入在 `/input/`：`case.json`、`task.md` 与材料文件（可能是 config.yaml、train.log、代码、CSV、真实 PDF）。**先读真实文件**，不按文件名臆测内容。
2. 先解析 `/input/case.json`：取 `case_id` 与 `output_contract`；最终 `/app/output/result.json` 必须含 `case_id` 和 `output_contract` 声明的**全部原始字段**（字段名以 case.json 为准，不臆造、不改名、不漏项）。
3. 工作文件放 `/app/work/`，最终交付放 `/app/output/`：方法章节成稿（按任务要求 .md 或 .tex）、`param_table.md`、`evidence_map.md`、`result.json`（诚实 status: success/partial/failed + sources + uncertainty + change_log）。
4. 预算：64 次模型请求 / 900 秒 / 每响应 16384 token。**先落盘一版六类要素齐全、缺口如实标注的诚实初稿，再迭代打磨**。
5. 禁止：预制答案、编造软件版本或实验数据、新增材料之外的事实。配置/日志里没有的数值一律不写进正文。
6. 本包脚本一律 stdlib-only，路径用正斜杠，按绝对路径调用。
7. **验证与限制声明**：本 Skill 的脚本与流程只在本地合成 fixture 上验证过（examples 中均标注合成）；平台的 3 个隐藏评测案例与对照组从未在本地运行，本包不声称、不暗示任何评测分数。所有真实数据以运行时 `/input/` 实际文件为准。

## 脚本调用规则

四个脚本均在 `/skills/weekly-skill/scripts/`，**必须用绝对路径**调用，不依赖 CWD：

```bash
python3 /skills/weekly-skill/scripts/inventory.py --input /input --out /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/param_check.py --materials /input --draft /app/output/methods_section.md --report /app/work/param_check_report.md
python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
```

- `param_check.py`：从材料与成稿中抽取 `键=值` 参数对并交叉比对。退出码 1 = 发现同一参数多处取值冲突（修一轮或标注 [待确认] 后照常交付，不阻塞）；`--strict` 时"成稿数值无材料来源"也算 FAIL。YAML 锚点/别名（`&anchor`、`*alias`、`<<:`）与空值（`~`/`null`）按 YAML 语义处理，不误报。
- `contract_check.py`：**写 result.json 之前的契约前置校验（建议性）**——在 `/app/work/` 起草 result 草稿后先运行它核对 case_id 与 output_contract 全部字段齐全；退出码 1 表示存在建议修复项，能修则修一轮，修不完的逐项写入 uncertainty 与 skipped_reason，然后照常把草稿落盘为 `/app/output/result.json`；任何退出码都不阻止交付。
- **降级声明**：若脚本文件缺失或运行失败，不得中断任务——改用手工方式执行同等检查（通读材料手列参数表、逐数值回查来源、对照 case.json 字段清单逐字段打勾），并在 `result.json` 的 `change_log` 中记录"脚本不可用，已手工复核"。

## 主流程（七步）

### 交付优先原则（v3，最高优先级）

- **先有交付，再求完美**：任何时刻 `/app/output/` 里都要有一份当前最好的可交付物（哪怕是 status=partial 的诚实初稿 + result.json）；先完成、再完美，严禁把"全部校验通过"作为落盘前提；
- **请求预算分配（64 次）**：≤10 次读材料与契约；≤30 次产出主交付物；≤10 次校验与修复；剩余全部留给 finalize（落盘交付物 + 写 result.json）；
- **预算红线**：预算过半仍未落盘初稿 → 立即停止新探索，把当前版本落盘；剩余约 10 次请求 → 停止一切修复与校验，直接 finalize；
- **脚本两轮封顶**：每个脚本最多运行 2 次（首次检查 + 修复后复查一次）；两轮后无论结果如何都进入交付，未修复项逐项写入 result.json 的 uncertainty 与 skipped_reason。任何脚本退出码都不阻止交付。

### 第 0 步　解析契约
读 `/input/case.json` 与 `/input/task.md`：记下 `case_id`、`output_contract` 全部字段名、目标语言（中/英/双语）、目标体裁（期刊方法节/实验节/附录）、受众与格式约束。逐条抄到 `/app/work/contract_note.md`，后续所有产出对照此清单。

### 第 1 步　材料清点
运行 `inventory.py` 生成 `/app/work/materials_register.md`，给每个来源编号 S1..Sn。逐个打开材料确认真实内容：哪个是配置文件、哪个是日志、哪个是数据说明、哪个是代码。**同类多份文件（如 config_v1/config_v2）必须确认哪份是最终实验所用**，无法确认记入待确认项。

### 第 2 步　六类要素抽取
按 `references/element_checklist.md` 的六类要素，逐材料抽取事实，写入 `/app/work/elements_notes.md`。每条事实格式：`事实内容 [S# 位置]`（位置=文件名+行号/段落/配置键路径）。只抽材料中真实存在的；材料没写的不要"合理推测"，记入 `/app/work/gaps.md`（材料缺口清单）。判断标准与反模式见 `references/method_rules.md`。

### 第 3 步　参数表构建与冲突检测
汇总全部参数为 `/app/work/param_table.md`（模板见 `templates/param_table_template.md`，列：名称/当前值/被覆盖值/单位/作用对象/来源/所属阶段/正文出现位置/状态）。**每个参数标注它属于哪个阶段/哪次运行（阶段级出处）**；命令行与日志中的观察值进正文，被覆盖的旧值保留在参数表"被覆盖值"列与冲突记录中（论文与日志两侧同时保留，取舍规则见 method_rules.md §2.7）。然后运行 `param_check.py` 交叉比对材料与成稿（成稿尚无时先用要素笔记）：
- **冲突**（同一参数多处取值或单位不一致，如 config 里 lr=1e-3、日志里 lr=0.01）：不得擅自二选一，查上下文判断哪次是最终实验；判断不了 → 列入待确认项，正文两处都不写死；
- **无来源数值**（成稿里出现、材料里查不到的数值）：删除或标 `[待确认]`，绝不保留"看起来合理"的编造值。

### 第 4 步　按骨架成稿
按任务要求语言选骨架：`templates/methods_skeleton_zh.md` 或 `templates/methods_skeleton_en.md`（双语任务先中后英，同一事实两种语言数值必须一致）。步骤句式从 `references/sentence_patterns.md` 选用。写作规则：
- 每个含事实/数值的句群末尾挂来源标记 `[S#]`；参数正文中只出现一次规范值，其余处引用参数表；
- 多步操作不得压成一句：每步写清输入、操作、输出、判断条件（句式见 sentence_patterns §2）；
- 训练/验证/测试流程分段写，条件不串台；基线与评价指标写清版本与统计方式。
产出：`/app/output/methods_section.md`（或 .tex，按任务要求）。

### 第 5 步　可复现性核查与缺口标注
对照 `references/method_rules.md` §6 复现清单逐条自问：读者按本章节能不能重做？代码版本、环境、随机种子、命令、数据获取方式缺哪条补哪条；材料里查不到的 → 列入成稿末尾"待确认项"小节 + `evidence_map.md` 待确认表，限制条件写明具体失效场景（不写"存在一定局限性"这类套话）。再跑一次 `param_check.py`（这次草稿是正式成稿）确认无新冲突。

### 第 6 步　交付与自查
1. 填 `/app/output/evidence_map.md`（模板 `templates/evidence_map_template.md`）：材料登记、参数来源映射、冲突处理记录、待确认项；
2. **契约前置校验（建议性）**：result.json 先起草为 `/app/work/result_draft.json`（模板 `templates/result_json_template.md`：case_id、契约字段、status、sources、uncertainty、change_log，失败/跳过阶段附 skipped_reason），运行 `contract_check.py --case /input/case.json --result /app/work/result_draft.json` 核对契约字段齐全；FAIL 项能修则修一轮并复查一次，修不完的逐项写入 uncertainty 与 skipped_reason，然后**照常落盘为 `/app/output/result.json`**——退出码仅供定位问题，不作为交付门禁；
3. 运行 `selfcheck.py`：有 FAIL 修复后复查一次（每个脚本最多两轮）；两轮后仍无法修复的在 uncertainty 说明、降 status 为 partial 并照常交付。WARN 项只提醒、不阻断交付，但需在 change_log 记录已知 WARN。

## 质量门（自查清单，不阻塞交付）

本节是交付前的自查清单而非门禁：任何一项不满足都不阻止交付——FAIL 项能修则修一轮，修不完的逐项写入 result.json 的 uncertainty 与 skipped_reason，然后照常落盘交付。对照 `references/element_checklist.md` 逐项打勾，关键锚点（建议性）：

- [ ] 六类要素（步骤/实验设置/参数/数据集/对照/复现与限制）在成稿中各有实质内容（selfcheck.py 自查项）；
- [ ] `param_check.py` 无参数冲突；--strict 下无无来源数值（有冲突按第 3 步标注处置，不阻塞交付）；
- [ ] 每个数值/事实句群带 `[S#]` 来源标记，且 S# 在材料登记表中存在（selfcheck.py 自查项）；
- [ ] 软件/库/模型/数据集均带版本号（材料给了的话），随机种子与重复次数写明；
- [ ] 待确认项 ≥0 条全部显式列出，没有用编造值填缺口；
- [ ] `result.json` 含 case_id 与契约全部字段，status 诚实；落盘前已运行 `contract_check.py`（FAIL 项已记入 uncertainty）；
- [ ] **负路径自测已做**：至少跑过一个"必须被拒绝"的用例并确认被拦截（退出码 1），如：正文参数与材料冲突却未标注（param_check 应 FAIL）、result.json 缺契约字段（selfcheck/contract_check 应 FAIL）。负路径用例放 `/app/work/` 并标注合成，不得混入 `/app/output/` 交付物。

## 反馈回路

```
param_check.py 报冲突 → 回第 2/3 步查材料上下文定位最终实验取值
  → 能定则改正文与参数表，不能定则标 [待确认] → 复查一次（每个脚本最多两轮）
  → 两轮后仍有 FAIL：记入 uncertainty/skipped_reason，照常交付
selfcheck.py 报 FAIL → 回对应步骤补要素/补来源/修 result.json → 复查一次
  → 两轮后仍有 FAIL：记入 uncertainty/skipped_reason，照常交付
预算将尽 → 停止润色，保证当前版本六类要素齐全、已落盘（质量门为自查清单，
  FAIL 项写入 uncertainty 即可，不阻塞交付）
```

**宁可一段写"材料未提供，待作者确认"，不写一句顺口的编造。**

## 异常处理

- **finalize 永不空手（交付韧性）**：无论哪个阶段失败或超时，finalize 都必须导出可交付物——已完成的阶段按诚实状态交付，未完成/跳过的阶段在 result.json 的 `skipped_reason` 字段逐条写明（如"param_check 脚本缺失，已手工复核""双语只完成中文部分"）；绝不允许 `/app/output/` 空空如也或只有一句"任务失败"；
- **新增检查只加 WARN**：selfcheck.py 后续新增的检查项一律 WARN 级——只提醒、不把原本能通过的草稿判 FAIL；退出码只由 FAIL 项决定；
- **材料缺失/读不出**（PDF 无文本层、日志损坏）：在登记表标"未纳入"，相关要素写"材料未提供"，status=partial 并在 uncertainty 说明；
- **配置与日志冲突**：按第 3 步处理，两值都在 evidence_map 记录，不擅自取其一；
- **多版本配置**（config_v1/v2）：以日志实际加载记录/时间戳/作者笔记判定，判不了 → 待确认；
- **任务要求双语但预算不足**：先交中文全要素版 + 英文核心段落，status=partial，change_log 说明；
- **超时/中断**：保证 `/app/output/` 已有六类要素齐全的诚实初稿 + partial 的 result.json。

## 资源索引

- `references/element_checklist.md`——六类要素齐全性清单与评分锚点（交付前逐项勾）；
- `references/method_rules.md`——六类要素写法判定标准、"写了等于没写"反模式、参数/来源/复现规则（>100 行，顶部有目录）；
- `references/style_guide.md`——方法与实验章节文体、时态语态、数字与单位、中英一致规范；
- `references/failure_modes.md`——基础 Agent 在本题的 8 类典型失败与对策；
- `references/sentence_patterns.md`——中英双语步骤/设置/参数/对照/统计句式模板库；
- `templates/methods_skeleton_zh.md` / `methods_skeleton_en.md`——中/英章节骨架（含占位说明）；
- `templates/param_table_template.md`——带来源列的参数表模板；
- `templates/result_json_template.md`——result.json 透传规则与示意；
- `templates/evidence_map_template.md`——材料登记 + 论断来源映射 + 待确认项模板；
- `examples/minimal_example.md`——最小调用示例（示意输出，非正式案例结果）；
- `examples/synthetic_case.md`——完整合成案例（全合成标注），含 param_check 实测与负路径用例；
- `scripts/inventory.py`——材料清点；`scripts/param_check.py`——参数抽取与冲突检测（YAML 锚点/空值感知）；`scripts/contract_check.py`——result.json 落盘前的契约字段前置校验；`scripts/selfcheck.py`——交付自查（新增项只 WARN）。

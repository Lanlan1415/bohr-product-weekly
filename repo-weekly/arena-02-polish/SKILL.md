---
name: polishing-academic-language
description: 对给定学术文本（期刊论文/学位论文/基金申请书/审稿回复，中英双语）做语义保持的分级润色：先建术语表与约束卡，再按"语法→句式→风格→逻辑连贯"四级产出句级编辑记录（先抄原句再写改文的锚定协议），五脚本流水线 prepare→verify→finalize→audit 强制数字、术语、引用标记、公式、图表编号、限定词强度、否定范围守恒，违规编辑自动回退而非只报告；finalize 无条件导出（失败时交付已完成部分+skipped_reason），audit 做事后篡改检测；不确定的改法给备选而非硬改，全部修改可逐条回溯。当任务要求读取 /input/case.json 并依据固定材料完成"学术语言润色/改写/校对/中译英优化"时使用；纯内容问答不触发改写。
---

# 学术语言润色（Polishing Academic Language）

## 用途与触发

当任务要求对给定学术文本做**语言层面的修改**——语法修正、术语统一、语气调整、中式英语清理、中译英优化——并交付"润色后完整文本 + 逐句修改说明"时使用本 Skill。核心目标四句话（对应题面评分点）：

- **改得对**：硬错误（主谓一致、时态、冠词、搭配、标点）真正改掉，不是换说法掩盖；
- **说得像**：符合目标文体与语域（期刊/学位/基金/审稿回复），术语全篇统一；
- **没改坏**：数字、单位、限定强度、结论方向、引用编号、图表指向、公式，润色前后**逐字守恒**；
- **讲得清**：每处修改有原文、改文、类型、理由四要素，第三方能判断该不该改。

**不应触发的邻近场景**：① 用户只问内容问题（"这段的结论可靠吗"）——回答即可，**不得擅自改写原文**；② 任务是从零写作新文本（开题报告、综述）而非修改给定文本——用写作类 Skill。

## 运行环境契约

1. 输入在 `/input/`：`case.json`、`task.md`、待润色稿件与辅助材料（术语表、期刊要求、事实底稿等）。**先读真实文件**，不按文件名臆测。
2. 先解析 `/input/case.json`：取 `case_id` 与 `output_contract`；`/app/output/result.json` 必须含 `case_id` 和 `output_contract` 声明的**全部原始字段**。
3. 工作文件在 `/app/work/`；最终交付在 `/app/output/`：润色后全文（可编辑 Markdown/LaTeX，保持来稿格式）、`change_log.md`（逐条修改记录）、`evidence_map.md`（事实与来源映射）、`result.json`（诚实 status + sources + uncertainty + change_log）。
4. 预算：64 次请求 / 900 秒 / 16384 token 每响应。**先把全文过一遍语法级润色落盘，再逐级加深**；长文分章节处理，每完成一章就更新交付文件。
5. 禁止：预制答案、新增材料之外的事实、编造运行状态。
6. 脚本一律 stdlib-only、正斜杠、绝对路径调用。

## 脚本调用规则

五脚本流水线（v2，纯标准库），另保留 v1 的独立守恒门：

```bash
# 0) 材料清点（沿用 v1）
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
# 1) prepare：契约解析 + 封存原文快照 + 句级切分（sentences.tsv）
python3 /skills/weekly-skill/scripts/prepare.py --text /input/manuscript.md --workdir /app/work --case /input/case.json
# 2) verify：锚定核验 + 句级守恒门，违规编辑自动回退
python3 /skills/weekly-skill/scripts/verify.py --workdir /app/work --edits /app/work/edits.jsonl
# 3) finalize：无条件导出（含契约前置校验、before_after_digest、改后回读、manifest）
python3 /skills/weekly-skill/scripts/finalize.py --workdir /app/work --output /app/output --case /input/case.json
# 4) audit：交付后审计（篡改检测 + 守恒复核 + 契约复核）
python3 /skills/weekly-skill/scripts/audit.py --output /app/output --case /input/case.json --workdir /app/work
# 5) 交付结构自查（沿用 v1，新检查项只 WARN 不阻塞）
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
# 独立守恒门（v1 保留，可用于任意中间稿的整文档比对）
python3 /skills/weekly-skill/scripts/conservation_check.py \
  --original /app/work/original_snapshot.md --polished /app/output/polished_text.md \
  --terms /app/work/terms.txt --report /app/work/conservation_report.md
# 流水线自测（含负路径用例，预算允许时跑一次，非交付门禁）
python3 /skills/weekly-skill/scripts/self_test.py
```

**降级声明**：脚本缺失或失败时不得中断——改为手工执行同等检查（逐条比对数字与引用标记、肉眼核对术语表、逐句核对编辑记录的原文抄录），并在 `result.json` 的 `change_log` 记录"脚本不可用，已手工复核"。

## 主流程（prepare → 编辑记录 → verify → finalize → audit 循环）

**交付优先原则（v3，最高优先级）**：
- (a) 任何时刻 `/app/output/` 里都要有一份当前最好的可交付物——先把全文过一遍
  L1 语法级润色落盘，再逐级加深；先完成再完美，绝不留空输出目录；
- (b) 请求预算分配建议：≤10 次读材料与契约、≤30 次主产物（分批产出编辑记录）、
  ≤10 次校验修复、剩余全部留给 finalize 与 result.json 落盘；
- (c) 预算过半仍未落盘初稿 → 立即把当前版本落盘到 `/app/output/`；
  剩余约 10 次请求 → 停止一切修复，直接 finalize 交付；
- (d) 每个校验脚本最多运行 2 次（首次检查 + 修复后复查一次），之后无论结果
  如何都进入交付；脚本退出码仅供定位问题，不阻止交付。

### 第 0 步　解析契约 + prepare
读 `/input/case.json`：`case_id`、`output_contract` 字段、指定润色范围（全篇/指定章节）、目标文体与语言。运行 `prepare.py`：契约字段写入 `contract_fields.json`/`contract_note.md`；原文封存为 `original_snapshot.md`（守恒基线，**之后不再改动**）；全文切分为 `sentences.tsv`（sentence_id ↔ 逐字原句，锚定基准）。

### 第 1 步　材料清点与约束卡
运行 `inventory.py` 登记全部材料（S1..Sn）。写 `/app/work/constraint_card.md`：目标文体（期刊/学位/基金/审稿回复）、目标语言（中/英/中英对照）、受众、必须遵守的期刊/学校格式要求、**明确禁止改动项**（如作者指定的术语写法）。材料未给出的标 `【待确认】`，不假设。

### 第 2 步　建术语表
从稿件抽取术语与缩写，补全 prepare 生成的 `/app/work/terms.txt`（每行一个批准写法；缩写首次出现形式 = 全称 + （缩写））。术语表内部冲突标 `【待确认】`，列入 uncertainty。

### 第 3 步　分级产出句级编辑记录（L1→L4，锚定协议）
按 `references/method_rules.md` 的标准逐句判断，**遵守最小编辑原则**：

- **L1 语法**：主谓一致、时态语态、冠词介词、单复数、标点、悬垂修饰——只修硬错误；
- **L2 句式**：长句切分、中式语序调整、冗余名词化拆解——不改变信息分配；
- **L3 风格**：语域对齐、术语按 terms.txt 统一、人称与语态按目标文体；
- **L4 逻辑连贯**：衔接词显化、指代明确化——只加已有信息的连接，不补新论证。

产出不是润色稿全文，而是**编辑记录** `/app/work/edits.jsonl`（每行一条 JSON，格式见 `templates/output_skeleton.md` §2）。**锚定协议（红线）**：每条记录必须先逐字抄原句进 `original` 字段、再写 `replacement` 改文——`sentence_id` 只用于定位，抄录的原句才是锚。免抄原文的 id-only 记录 verify 能宽容接受但记 WARN，锚定核对失效会让错误编辑漏网（公开复盘教训：某榜首方案 v1.1 改 id-only 后 76.3→72.3，恢复抄原句锚定后回到 77.7）。**不确定的改法不硬改**：给 2 个备选 + 倾向 + 理由，标 `alternative.proposed`。分批产出（如每章一批），每批走完第 4 步再投下一批。编辑类型用词表 `references/edit_types.md`。

### 第 4 步　verify：锚定核验 + 守恒门（违规自动回退）
运行 `verify.py`：逐条核对锚定（空白宽容），再做句级守恒门——数字/单位、引用标记、图表公式编号、LaTeX 数学环境、限定词强度、否定范围。**违规编辑自动回退**（该句保持原文），不是只报告；回退清单在 `rejected_edits.jsonl` 与 `verify_report.md`。处置每条回退：修正后重投（下一轮 verify），或确认是任务明确要求的有意例外（记录加 `allow_conservation_break: true` + `reason`，依据写入 change_log）。产物：`polished_verified.md`。

### 第 5 步　finalize：无条件导出
运行 `finalize.py`——**无条件导出：无论 verify 是否通过、是否有未修复 FAIL，
都导出当前最好版本**（`polished_verified.md` 缺失或 verify 未通过时自动退化为
当前最好版本/原文快照 + skipped_reason）、change_log、evidence_map 写入 `/app/output/`；写 `result.json` 前**先做契约前置校验**（case_id + output_contract 全部字段，缺字段置 null 并记 uncertainty，不删字段）；生成评审友好的 `before_after_digest`（接受/回退计数 + 改前改后样例）与 `_manifest.json`；写盘后经"改后回读"通道复核一致性。同时把 Agent 维护的 `change_log.md`（六要素逐条记录，骨架见 templates/）与 `evidence_map.md` 放进 `/app/work/` 供其复制。

### 第 6 步　audit + selfcheck：交付后审计与结构自查
运行 `audit.py`（篡改检测：manifest 哈希比对；守恒复核：整文档复跑 conservation_check；契约复核；回退留痕核对）→ 有 FAIL 能修则修一轮（回第 3/4 步修复后重跑 verify→finalize→audit 一次），两轮后仍有 FAIL：记入 uncertainty/skipped_reason 照常交付，不再返修；再运行 `selfcheck.py` 做交付结构自查（v2 新增项只 WARN 不阻塞）。任何脚本退出码都不阻止交付——交付物已在 finalize 一步落盘，audit/selfcheck 只是事后自查清单而非门禁。

## 质量门（自查清单，不阻塞交付）

对照 `references/element_checklist.md` 逐项自查——这是自查清单而非门禁，
任何一项未达标都不阻止 finalize 导出交付，未达标项记入 uncertainty/skipped_reason：

- [ ] 锚定协议：编辑记录全部先抄原句再写改文（id-only 记录数 ≤ WARN 容忍范围且有理由）；
- [ ] verify 已运行，回退清单逐条有处置（修正重投 / 有意例外留依据 / 放弃）；退出码不作为交付门禁；
- [ ] 守恒门（句级 verify + 整文档 conservation_check 复核）：数字/术语/引用标记/图表编号/公式逐字一致，限定强度与否定范围不变；
- [ ] audit 已跑过：无事后篡改、契约字段齐全、回退已留痕（FAIL 项记入 uncertainty/skipped_reason 后照常交付）；
- [ ] 每条修改记录六要素齐全，≥1 条【备选】类条目的处理合规（给了备选而非硬改）；
- [ ] 指定章节逐段处理完毕，无漏段；
- [ ] 润色稿保持来稿格式（Markdown/LaTeX/纯文本），可直接使用；
- [ ] `result.json` 含 case_id 与契约全部字段 + before_after_digest，status 诚实（有回退/skipped 即 partial）。

## 反馈回路

```
每个脚本最多两轮（检查 → 修一轮 → 复查）；两轮后仍有 FAIL：记入
uncertainty/skipped_reason，立即交付。脚本退出码仅供定位问题，不作为交付门禁。
verify 回退编辑 → 修正 edits.jsonl（或标有意例外+依据）→ 复查 verify 一次
→ audit 报 FAIL（篡改/守恒/契约）→ 回到第 3/4/5 步修一轮 → 复查 verify→finalize→audit 一次
→ selfcheck 报 FAIL → 补一轮交付结构 → 复查一次，仍 FAIL 记入 uncertainty 照常交付
→ 预算将尽时停止 L3/L4 深化：finalize 在任何中间态都能导出诚实部分 + skipped_reason
```

**改不动的好句子胜过改坏的金句子。任何拿不准的修改，回退到原文。**

## 异常处理

- **超长输入**：分章节处理并逐批投编辑记录；实在处理不完，已完成章节照常交付，status=partial 并列出未处理章节（finalize 自动写 skipped_reason）；
- **verify 未运行/产出缺失**：finalize 自动交付原文快照 + skipped_reason，不整案失败；补上 verify 后重跑 finalize 即可升级为完整交付；
- **编码混乱/格式混杂**：先转 UTF-8 存工作副本，原文快照保留原样；公式与引用混杂的段落优先保守恒；
- **术语表内部冲突**（材料给的术语表自相矛盾）：不擅自取舍，并列冲突项标 `【待确认】`，按稿件中占多数的写法暂统一并在 uncertainty 说明；
- **目标文体不明**：默认按"期刊论文英语、保守润色"执行，并在 uncertainty 声明；
- **疑似内容错误**（如数据前后矛盾）：不是润色职责——不改数字，在 evidence_map 的待确认项指出；
- **重复运行**：同一段落二次润色时必须对照 original_snapshot（prepare 封存件），防止结论逐次漂移；finalize 重复运行产出确定（哈希一致），交付物在 finalize 之后被改动会被 audit 检出。

## 验证与限制声明

- 本包的脚本与示例**仅在本地做过合成数据验证**（self_test.py 的 29 项断言、examples/ 的合成案例），用于证明流程与脚本行为正确；
- 平台的 **3 个隐藏评测案例与对照组（不加载 Skill 的基础 Agent）未在本地运行**，本包不声称任何具体分数；文档中引用的 76.3/72.3/77.7 等数字来自他人公开复盘，仅作为锚定协议重要性的证据，不是本包的得分承诺；
- 示例中的"稿件"、数值、结论全部为演示虚构，不冒充真实案例结果。

## 资源索引

- `references/element_checklist.md`——要素齐全性清单与评分锚点；
- `references/method_rules.md`——守恒规则、锚定协议、四级润色判定标准、改前/改后示例与反模式（>100 行，顶部有目录）；
- `references/style_guide.md`——期刊/学位/基金/审稿回复语域规范与中式英语清理清单；
- `references/failure_modes.md`——基础 Agent 在本题的 10 类典型失败与对策；
- `references/edit_types.md`——编辑类型词表（edits.jsonl 的 type 字段取值）；
- `references/qualifier_lexicon.md`——限定词分级词表（CN+EN，跨级移动=违规）；
- `templates/output_skeleton.md`——润色稿、edits.jsonl 编辑记录与 change_log 条目格式骨架；
- `templates/result_json_template.md`——result.json 透传规则与示意（含 before_after_digest/skipped_reason）；
- `templates/evidence_map_template.md`——事实与来源映射 + 待确认项模板；
- `examples/minimal_example.md`——最小调用示例（示意输出，非正式案例结果）；
- `examples/synthetic_case.md`——完整合成案例（全合成标注），含守恒门与五脚本流水线实测；
- `scripts/inventory.py`——材料清点；
- `scripts/prepare.py`——契约解析 + 原文快照 + 句级切分；
- `scripts/verify.py`——锚定核验 + 句级守恒门，违规编辑自动回退；
- `scripts/finalize.py`——无条件导出（契约前置校验 + before_after_digest + 回读 + manifest）；
- `scripts/audit.py`——交付后审计（篡改检测 + 守恒/契约复核）；
- `scripts/conservation_check.py`——独立守恒门（v1 保留，整文档比对）；
- `scripts/selfcheck.py`——交付结构自查（v2 新增项只 WARN）；
- `scripts/self_test.py`——流水线端到端自测（含必须被拒绝的负路径用例）。

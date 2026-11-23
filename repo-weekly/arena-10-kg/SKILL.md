---
name: building-literature-graphs
description: 从给定的一批科研论文（文本/PDF/JATS 段落索引）构建带证据的小型文献知识图谱：先按材料学科设计实体与关系 schema，阅读时即登记引用线索、缩写候选与任务问题清单，再逐篇抽取实体和关系并把每条边挂到 source_id+paragraph_id+原文短引，按对齐名册与共享标识符规则消歧归并，比较类论断必须带比较条件（比较-条件门），导出机器可读三元组 CSV 与可回导 GraphML（往返一致性脚本验证），人读摘要与图统计；质量门脚本拦截悬空边、重复实体、无证据边、无条件比较与缩写冲突，result.json 写盘前先做契约前置校验。当任务要求读取 /input/case.json 并依据固定论文材料完成"文献知识图谱构建/实体关系抽取/证据绑定/图谱查询"时使用。
---

# 文献知识图谱构建（Building Literature Graphs）

## 用途与触发

当任务要求依据固定科研材料（一批论文的正文、JATS 段落索引或 PDF）**抽取实体与关系、绑定证据、构建可查询的图谱并导出图文件**时使用本 Skill。核心目标四句话（对应题面评分点）：

- **抽得准**：实体必须是论文里真实出现的科研对象，不凭常识补全；
- **连得对**：关系类型、方向、适用条件与原文一致，共现/转述/推测不当作直接证据；
- **对得齐**：别名、缩写、大小写、中英文、同名冲突全部按规则归并，合并依据留痕；
- **查得到、回得去**：至少 3 个真实查询可回答，每个节点、每条边都能回到论文具体位置与原文片段。

**不应触发的邻近场景**：① 只要求回答一个事实性问题、不要求产出图文件（按一般学术阅读处理）；② 要求写综述或开题报告等写作类产物（用写作类 Skill，不要强行构图）。

## 运行环境契约

1. 输入在 `/input/`：`case.json`、`task.md` 与材料文件（可能含 `corpus-manifest.json`、`material.json`、`primary-material.json`、`secondary-material.json` 或真实 PDF）。**先读真实文件**，不按文件名臆测内容。
2. 先解析 `/input/case.json`：取 `case_id` 与 `output_contract`；最终 `/app/output/result.json` 必须含 `case_id` 和 `output_contract` 声明的**全部原始字段**（字段名以 case.json 为准）。
3. 工作文件放 `/app/work/`，最终交付放 `/app/output/`：图文件（`graph_nodes.csv`、`graph_edges.csv`，可选 `graph.jsonld`）、`graph_summary.md`、`evidence_map.md`、`result.json`（诚实 status: success/partial/failed + sources + uncertainty + change_log）。
4. 预算：64 次模型请求 / 900 秒 / 每响应 16384 token。**先落盘一个诚实的小图（哪怕只有 10 条边），再迭代扩充**。
5. 禁止：预制答案、编造软件状态或科学数据、新增材料之外的事实。
6. 本包脚本一律 stdlib-only，路径用正斜杠，按绝对路径调用。

## 脚本调用规则

六个脚本均在 `/skills/weekly-skill/scripts/`，**必须用绝对路径**调用，不依赖 CWD：

```bash
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/graph_check.py --edges /app/output/graph_edges.csv --nodes /app/output/graph_nodes.csv --predicates /skills/weekly-skill/references/predicates.txt --abbrevs /app/work/abbrev_candidates.csv --report /app/work/graph_check_report.md
python3 /skills/weekly-skill/scripts/graphml_roundtrip.py --nodes /app/output/graph_nodes.csv --edges /app/output/graph_edges.csv --graphml /app/output/graph.graphml --report /app/work/graphml_roundtrip_report.md
python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
python3 /skills/weekly-skill/scripts/self_test.py
```

**降级声明**：若脚本文件缺失或运行失败，不得中断任务——改用手工方式执行同等检查（逐条核对边表证据列、肉眼查重、对照 case.json 字段清单、手工抽查 GraphML 与 CSV 的一致性），并在 `result.json` 的 `change_log` 中记录"脚本不可用，已手工复核"。

## 主流程（七步）

**交付优先原则（v3，最高优先级）**：
- (a) 任何时刻 `/app/output/` 里都要有一份当前最好的可交付物（哪怕只有
  10 条边的小图）——先完成再完美，先落盘、后迭代扩充；
- (b) 请求预算分配建议：≤10 次读材料与契约、≤30 次主产物（抽取/归并/成图）、
  ≤10 次校验修复、剩余全部留给 finalize 与 result.json 落盘；
- (c) 预算过半仍未落盘初稿 → 立即把当前版本落盘到 `/app/output/`；
  剩余约 10 次请求 → 停止一切修复，直接 finalize 交付；
- (d) 每个校验脚本最多运行 2 次（首次检查 + 修复后复查一次），之后无论结果
  如何都进入交付；脚本退出码仅供定位问题，不阻止交付。

### 第 0 步　解析契约
读 `/input/case.json`：记下 `case_id`、`output_contract` 全部字段名、任务说明中的查询要求与证据范围。在 `/app/work/contract_note.md` 逐条抄录，后续所有产出对照此清单。

### 第 1 步　材料清点与归属确认
运行 `inventory.py` 生成材料登记表，给每个来源编号 S1..Sn。**逐篇确认每篇论文的 DOI/标题/作者归属**：根 DOI/title/authors 属于第一篇，不得套到第二篇；只有同篇的多种文件格式（JSON+Markdown+XML）不算跨篇证据。产出：`/app/work/materials_register.md`（可机器校验）。

### 第 2 步　schema 落地
按 `references/method_rules.md` 的实体/关系 schema，结合本批论文实际内容裁剪：列出本案例用到的实体类型、关系类型（仅限 `references/predicates.txt` 内的标准关系，确需新增时先在 change_log 登记）、属性字段。产出：`/app/work/schema_note.md`，不允许在抽取中途随意新增关系类型。

### 第 3 步　逐篇抽取实体与关系（证据先行，阅读时即展示三张清单）
对每篇论文逐段抽取：每个实体记录 `{规范名, 类型, 别名[], 来源段}`；每条关系必须同时拿到**原文短引**（≤40 字逐字摘录）+ `source_id`（S#）+ `paragraph_id`（JATS 段落 ID；本包无 PDF 页码，**不得把自建页码称原 PDF 页**）+ 证据强度（作者自述直接结果 / 作者转述他人 / 推测）。拿不到证据的关系不建边，记入 `/app/work/unlinked_mentions.md`。产出：`/app/work/extraction_S1.md`、`extraction_S2.md` …（每篇一份，可机器抽查）。

**阅读时同步维护三张清单**（模板 `templates/alignment_roster_template.md` §5）：① 引用线索清单（direct/cited/inferred 判据）；② 缩写候选表 `/app/work/abbrev_candidates.csv`（遇到"全称（缩写）"结构即登记，是 graph_check --abbrevs 的输入）；③ 任务问题清单（case/task 要求回答的问题逐条抄录并标注将用哪个查询回答）。

### 第 4 步　实体消歧与归并（对齐名册裁决）
按 `references/method_rules.md` §3 的归并规则处理跨篇候选：同义/缩写/大小写/中英文全半形归一后比对。建 `/app/work/alignment_roster.md`（对齐名册）：**候选对全部列出、逐对裁决留痕**；合并依据必须逐条写入 `evidence_map.md`。**实例级实体（样品/模型实例/数据集/实验/条件）仅当共享同一原文标识符才可合并**；以下情形**不得合并**并要写明理由：不同论文的物理样品、模型实例、数据集、实验条件——即使都叫同一个通用方法/材料名。产出：`/app/work/merge_decisions.md` 与对齐名册。

### 第 5 步　成图与质量门（含比较-条件门）
汇总为 `graph_nodes.csv`（列：node_id,label,type,aliases）与 `graph_edges.csv`（列：edge_id,subject,predicate,object,source_id,paragraph_id,quote,evidence_strength[,value,unit,condition]）。node_id 一旦分配**永不复用**（支持增量更新）。**比较-条件门：outperforms / more_stable_than / compares 边必须在 condition 列标明比较条件**（温度/组成/测试协议），原文没给条件就先记入待确认、不建无条件比较边。运行 `graph_check.py`（含 --abbrevs 缩写候选核对）做建议性自查：FAIL 项能修则修一轮、复查一次，之后无论结果如何都进入交付；修不完的逐项写入 `result.json` 的 `uncertainty` 与 `skipped_reason` 并把 status 降为 partial，照常落盘交付。脚本退出码仅供定位问题，不作为交付门禁。

### 第 6 步　查询、GraphML、摘要与交付
1. 执行至少 3 个真实查询（覆盖：按实体查邻边、按关系查证据、跨篇比较/无法确定项），每个查询给出结果子图 + 支撑证据原文 + 无法确定的关系说明，写入 `graph_summary.md`（骨架见 `templates/output_skeleton.md`）；**查询只从图文件取数、只答图内有向可达的内容，不推断图外科学事实**；
2. 运行 `graphml_roundtrip.py` 导出 `graph.graphml` 并做回导一致性验证（CSV→GraphML→解析回比对，不一致即 FAIL；交付后可用 `--verify-only` 检测事后改动）；
3. 填 `evidence_map.md`（模板 `templates/evidence_map_template.md`）：材料登记、合并记录、冲突与待确认项；
4. 写 `result.json` 草稿到 `/app/work/result_draft.json`（模板 `templates/result_json_template.md`），运行 `contract_check.py` 做契约前置校验（建议性：缺字段补 null + uncertainty 说明），**无论校验结果如何都复制为 `/app/output/result.json` 落盘交付**；
5. 运行 `selfcheck.py` 做交付结构自查（v2 新增项只 WARN 不阻塞；退出码不阻止交付）。

## 质量门（自查清单，不阻塞交付）

对照 `references/element_checklist.md` 逐项自查——这是自查清单而非门禁，
任何一项未达标都不阻止落盘交付，未达标项记入 uncertainty/skipped_reason：

- [ ] 每条边都有 source_id + paragraph_id + 原文短引，三字段非空（脚本强制）；
- [ ] 无悬空边、无重复节点、无重复边（脚本强制）；
- [ ] 关系类型全部在 schema 清单内，方向与原文一致；
- [ ] 比较类边全部带比较条件（比较-条件门，脚本强制）；缩写候选全部落点且无冲突（--abbrevs）；
- [ ] 合并决策逐条留痕于对齐名册，实例级实体合并均有共享标识符，不得合并项有书面理由；
- [ ] GraphML 回导一致性验证已跑过并记录结论（graphml_roundtrip.py；不一致记入 uncertainty，照常交付）；
- [ ] ≥3 个查询展示结果子图与证据，含"无法确定"项的诚实说明；查询不推断图外科学事实；
- [ ] `result.json` 落盘前跑过 contract_check.py 自查：含 case_id 与契约全部字段（缺项补 null + uncertainty），status 诚实。

## 反馈回路

```
每个脚本最多两轮（检查 → 修一轮 → 复查）；两轮后仍有 FAIL：记入
uncertainty/skipped_reason，立即交付。脚本退出码仅供定位问题，不作为交付门禁。
graph_check.py 发现 FAIL（含比较-条件门、缩写候选冲突）→ 回到第 3/4/5 步修一轮
（补证据/合并重复点/删悬空边/补比较条件/裁决缩写冲突）→ 复查一次后进入交付
→ graphml_roundtrip.py 回导不一致 → 修一轮 CSV 后重导再验一次，仍不一致记入 uncertainty
→ contract_check.py 缺字段 → 补字段（做不到填 null + uncertainty），无论结果都落盘
→ 跑 selfcheck.py 记录自查结论 → 仍 FAIL 记入 uncertainty/skipped_reason 照常交付
→ 不整案重跑全部脚本；预算将尽时停止扩充，当前版本直接落盘（partial + skipped_reason）
```

**宁可少 5 条有证据的边，不多 1 条没证据的边。**

## 异常处理

- **PDF 无法解析/材料缺失**：该篇在登记表标"未纳入"，`result.json` 的 uncertainty 说明，status=partial；
- **两篇结论冲突**：不合并、不取平均，建两条各自挂证据的边，在摘要"冲突与待确认"节并列；
- **同名不同物**（如两篇都说"LLZO"但样品批次不同）：建两个节点，label 标注来源篇目，在 merge_decisions 写明不合并理由；
- **关系证据强度不足**（综述转述、推测）：evidence_strength 降级标注，摘要中单列；
- **比较条件缺失**：原文只比较不给条件——不建无条件比较边，记入待确认；宁可少一条边，不建不可比的边；
- **超时/中断**：保证 `/app/output/` 始终有当前最好的小图（无需全部通过校验，未达标项记入 uncertainty）+ 诚实 status=partial 的 result.json（附 skipped_reason 说明未完成的阶段）。

## 验证与限制声明

- 本包的脚本与示例**仅在本地做过合成数据验证**（self_test.py 的 15 项断言、examples/ 的合成案例），用于证明流程与脚本行为正确；
- 平台的 **3 个隐藏评测案例与对照组（不加载 Skill 的基础 Agent）未在本地运行**，本包不声称任何具体分数；对手做法的情报仅用于确定功能方向；
- 示例中的"论文"、数值、结论全部为演示虚构，不冒充真实案例结果。

## 资源索引

- `references/element_checklist.md`——要素齐全性清单与评分锚点（交付前逐项勾）；
- `references/method_rules.md`——schema 定义、抽取/归并/证据规则、比较-条件门、GraphML 规范与反模式（>100 行，顶部有目录）；
- `references/style_guide.md`——图文件格式、ID 与命名规范、摘要写作规范；
- `references/failure_modes.md`——基础 Agent 在本题的 10 类典型失败与对策；
- `references/predicates.txt`——标准关系类型清单（graph_check.py 的 --predicates 输入）；
- `templates/output_skeleton.md`——graph_summary.md 骨架与三元组 CSV 表头；
- `templates/result_json_template.md`——result.json 透传规则与示意（含 skipped_reason/quality_gate）；
- `templates/evidence_map_template.md`——材料登记 + 合并记录 + 冲突登记表模板；
- `templates/alignment_roster_template.md`——对齐名册模板：缩写候选表、跨篇候选裁决、比较-条件登记、阅读时三张清单；
- `examples/minimal_example.md`——最小调用示例（示意输出，非正式案例结果）；
- `examples/synthetic_case.md`——完整合成案例（全合成标注），含质量门、回导与自测实测；
- `scripts/inventory.py`——材料清点；
- `scripts/graph_check.py`——图质量门（悬空边/重复实体/无证据边/比较-条件门/缩写候选核对）；
- `scripts/graphml_roundtrip.py`——GraphML 导出 + 回导一致性验证（--verify-only 做事后改动检测）；
- `scripts/contract_check.py`——result.json 写盘前的契约前置校验；
- `scripts/selfcheck.py`——交付结构自查（v2 新增项只 WARN）；
- `scripts/self_test.py`——脚本群端到端自测（含必须被拒绝的负路径用例）。

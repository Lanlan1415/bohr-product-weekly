---
name: reading-annotate
description: >
  阅读批注与知识沉淀。把 PDF/网页等工具已经抽出的真实批注变成可回链、可检索、
  可导出的笔记与知识卡片。每条 quote 必须在已加载原文中逐字定位；页码、段落与
  字符区间消歧，OCR 漂移拒绝并给真实候选段；highlight/underline/margin/handwriting/
  web-clip、未知类型、颜色与标签保真。卡片区分 source_excerpt 与 reader_comment，
  保存主题、关键概念、实体和声明的 source_time；同义内容按可解释证据建立双向链接
  与 backlinks；生成 doubt/问题的后续行动与未开始的 1/3/7/16 天复习计划。支持按
  问题、类型、文献、标签、主题、概念、实体和时间检索；导出 notes.md、cards.md、
  review.csv、index.json，重放与保存幂等且全部字节确定。Echoes case_id and every
  output_contract field into result.json. Do NOT use for invented highlights/pages,
  unsupported card summaries, PDF annotation extraction without real source files,
  or long-term archive governance.
---

# reading-annotate（阅读批注与知识沉淀）

主流程为：真实原文与批注 → 锚点验证 → 类型化笔记 → 知识卡片 → 双向关联 →
多维检索 → 导出与 result.json。输入载体是抽取后的 UTF-8 文本和真实批注导出；
文本中 form feed 表示真实分页。本 Skill 不把压缩包内预制“答案”当作运行时材料。

## 由开源机制落地，而非只贴链接

- **Hypothesis annotation.py（其 GitHub 仓库路径 h/schemas/annotation.py）** 把 target URI、selector 数组和 tags 分离，
  selector 可带 prefix/suffix 上下文。受到这一多选择器思路启发，本包同时持久化逐字
  quote、doc_id、page、paragraph、start/end；同一 quote 多处出现时要求 page 或 offset
  消歧，不能只靠文本相似度挂到邻近段。原 quote 与坐标在导出中共同出现。
- **Zotero `reader.js`** 以 parent attachment 关联 annotation，分离 text/comment、color
  和 page 表示，并通过 QuickCopy 将批注转入笔记。本包对应保留 doc_id/source_sha、
  source_excerpt/reader_comment、type/color，再由同一结构化 note 生成 Markdown/CSV/JSON，
  不让“读者判断”伪装成“原文事实”。页码只从已声明的真实分页获得，未提供 PDF 坐标时不猜。

## 运行时六步入口（Harbor）

平台输入：`/input/case.json` 与 `task.md`；工作区 `/app/work`；最终交付 `/app/output`。

| 步 | 动作 | 检查点 |
|-|-|-|
| 0 | 读取 case_id、output_contract 与 task.md 指向的实际材料 | 文件名/领域标签不是正文；PDF 必须先使用环境真实 PDF/批注工具得到文本、页码与批注记录 |
| 1 | 选择路由：PDF+批注导出、已抽取 JSON、扫描 OCR、重复副本、多版本 | 扫描件无文本层、加密/损坏/权限失败明确列入 limits/failure_recovery；可处理的文档继续 |
| 2 | `load` 文档，`ingest` 批注 | 尽早保存已验证部分；quote 不存在、页码/offset 冲突、歧义、未知 kind 都逐条拒绝，不吞记录 |
| 3 | `verify` 复核锚点，补齐材料里真实存在的 topics、key_concepts、entities、source_time | 不确定的主题/概念/时间留空；reader comment 与源文不能混写为 source_excerpt |
| 4 | 用真实问题 `retrieve`，按需要加 kind/doc/tag/topic/concept/entity/since/until，再 `export` | 检索无命中就是 hits=[]+empty_reason；复习计划保持 not_started，不虚构已复习或到期日 |
| 5 | `result --case /input/case.json --out /app/output` | 自动导出四个附件并写 result.json；case_id 与 contract 全字段直通，状态/拒绝/不确定性随附 |

### 最小实际调用

```bash
python scripts/annotate_cli.py --store /app/work/ws.json load \
  --doc-id paper --doc-file examples/extracted.txt
python scripts/annotate_cli.py --store /app/work/ws.json ingest \
  --doc-id paper --annotations examples/annotations.json
python scripts/annotate_cli.py --store /app/work/ws.json verify
python scripts/annotate_cli.py --store /app/work/ws.json retrieve \
  --question "涂层吸收速率提高了多少" --topic 涂层 --concept 吸收速率 \
  --entity coating --since 2024-01-01 --until 2024-12-31
python scripts/annotate_cli.py --store /app/work/ws.json export --out /app/output
python scripts/annotate_cli.py --store /app/work/ws.json result \
  --case examples/case.json --out /app/output
```

示例均为自拟材料，不是平台正式案例。`result` 本身也会导出附件，因此重复执行
export/result 不会生成额外副本。

### 输入批注 schema

```json
[
  {"quote": "three-fold", "page": 1, "start": 38,
   "type": "highlight", "color": "yellow",
   "note": "结果：涂层使吸收速率提高三倍", "kind": "result",
   "tags": ["吸收率"], "topics": ["涂层"],
   "key_concepts": ["吸收速率"], "entities": ["coating"],
   "source_time": "2024-05-02"}
]
```

- `quote` 必填且逐字存在；`page`/`start` 可省略，声明后必须与实际位置一致。quote
  多处出现且不唯一时 `ann.anchor_ambiguous` 拒绝，要求补 page 或 start，不选第一个碰运气。
- `type` 保留五个常见值和未知 extractor 类型（统一小写），不静默折叠；`color`、tags
  原顺序保留。kind 限 question/method/result/reusable/doubt/context，缺省才按文本 cues。
- topics/themes、key_concepts/concepts、entities/entity 均为声明字段；概念已有声明时不
  混入噪声二字词。若概念完全未声明，卡片才使用 lexical-fallback，并明确 concepts_origin。
- source_time 只接受批注里的 `source_time`、`date`、`created_at`、`timestamp`；日期过滤仅处理
  YYYY-MM-DD（可带时间后缀）。没有时间的卡不参与 since/until 命中，绝不拿运行时刻充当来源时间。
- 普通单页文本的 page=1 是该逻辑文本页坐标，不是 PDF 印刷页码。跨 form feed 才解析
  多个实际页。无页标签/版面坐标/扫描框时，相关字段保持 null 或未提供，不能补造。

## 卡片、关联、检索与复习的真实行为

每条 annotation 形成一条 note 和一张稳定 `card-{annotation_id}`：
- `source_excerpt` 永远来自锚定 quote；`reader_comment` 来自 note/text；summary_kind
  区分 source_excerpt 或 reader_comment。卡片不能脱离原文哈希与 anchor 独立存在。
- cards 含 title、topics、tags、key_concepts、entities、source_time、annotation_ids、
  doc_id、note_kind、type/color、source_sha、review_schedule。
- 同 kind 且共享至少两个 content terms 才形成知识关联，shared_terms 即证据，避免“只共享
  一个词就全部互连”。每个 edge 有 between、between_cards、directions 与 bidirectional=true。
- 每张卡的 related_card_ids、backlinks 和 Markdown `[[card-id]]` 同步生成；跨版本同 quote
  仍保留独立哈希，并以 version-sibling 证据形成双向关联。
- retrieve 会同时检索原文/评论和标签/主题/概念/实体词元；再施加 doc、kind、tag、topic、
  concept、entity 和 ISO source_time 过滤，按 score+card_id 稳定排序，宁缺毋滥。
- doubt/question 卡收到 `verify-against-source`；其他卡收到 `scheduled-retrieval-review`。
  相对复习间隔为 [1,3,7,16]，state=not_started、due_date=null；这是可执行后续计划，
  不声称已经接入后台调度器或完成真实复习。

## 导出与 result.json

每个 result 命令保证写出五个文件：
- `notes.md`：带锚点的结构化笔记、原文、评论、forward links 与 backlinks。
- `cards.md`：知识卡片、主题/概念/实体、来源、双向 Wiki 链接与复习计划。
- `review.csv`：card_id、front、back/back_kind、interval_days、state、due_date、source_anchor，
  可导入后续复习工具；空 due_date 是刻意保留，不是遗漏。
- `index.json`：annotate/v3 的 notes、cards、links、version_siblings、follow_up_actions
  与检索 schema，机器可复用。
- `result.json`：状态、documents、notes、cards、links、version_siblings、follow_up_actions、
  verify、operation_trace、change_records、failure_recovery、uncertainty、limits、exports，
  以及 case_id 和 output_contract 的每个原字段。

| rubric 三段 | 本 Skill 落点 | 可复核标准 |
|-|-|-|
| 资料结果 | documents + notes/cards + links/version_siblings + index.json | 每条批注回到真实页/段/字符区间；评论与原文分开；关联有 shared_terms 或版本证据 |
| 操作证据 | source_sha + verify + operation_trace + change_records + 五个确定性产物 | 重跑锚点不增长；编辑含字段级 before/after diff；同 store/case 五文件字节一致 |
| 失败与恢复 | failure_recovery + uncertainty + limits + done/partial/failed/undetermined | OCR 漂移给真实候选段但不模糊放行；不可读/无权限/版本错位均不当完成 |

契约直通规则：结果已有的同名字段优先；case 顶层可交付小体积值原样直通；契约里的
短字符串/数值/布尔字面量直通；annotations/knowledge_cards/knowledge_links/follow_up
等标准字段在描述性对象/列表下映射真实 notes/cards/links/follow_up_actions；不可推导
对象为 null+limits。拒绝执行时不从损坏 case 回声契约，也不伪造成功结果。

## 运行状态与异常索引

退出码：`0 done/ok`；`2 usage`（未知 kind、非法/倒序时间过滤、CLI 参数错误）；
`3 partial`（有可交付笔记但仍有 record refusal 或失效锚点）；`4 refused/failed`
（命令拒绝或零条可接受批注）；`5 undetermined`（store/case/导出不可读不可写、
有效 JSON 但容器形状不安全、内部无法判定）。结构化边界把异常变成 JSON 和 result.json，
不显示 traceback。查询无命中不是错误：exit 0 + hits=[] + empty_reason。

| rule | 触发与恢复 |
|-|-|
| `ann.doc_not_loaded` | 先 load 真实文档；不能接受挂到未知文件的批注 |
| `ann.no_quote` / `ann.record_not_object` / `ann.annotations_not_list` | 修正记录形状/空锚点；其余可用记录继续 |
| `ann.declared_kind_unknown` | 使用六类合法 kind，或省略让 cues 分类 |
| `ann.anchor_mismatch` | quote 不存在；重新精确抽取，不能挂邻居段 |
| `ann.anchor_ocr_drift` | 附候选真实段、similarity、candidate；人工重抽后再 ingest |
| `ann.anchor_page_conflict` / `ann.anchor_offset_conflict` | 修正声明页码/偏移，或删除声明后重新定位 |
| `ann.anchor_ambiguous` | quote 多处出现；补 page/start，不能猜第一个 |
| `ann.duplicate_document` | 同哈希副本报告 duplicate_of；不静默合并，不拆研究关系 |
| `ann.doc_file_missing` / `ann.doc_file_unreadable` | 检查路径/权限/UTF-8；exit 4 且其他文件可继续 |
| `ann.annotations_unreadable` | 批注导出不是可读 JSON；exit 4 结构化说明 |
| `ann.store_unreadable` / `ann.store_unwritable` | store 损坏/不可写；exit 5，无 traceback |
| `ann.invalid_time_filter` | since/until 非 ISO 或顺序倒置；exit 2，不用运行时间替代 |
| `ann.invalid_input` | 合法 JSON 但 documents/annotations 等容器形状不安全；exit 5，结构化拒绝 |

## 幂等与版本边界

- save 不再制造无意义 save 事件；同内容重 ingest 不新增 anchor/event/card。重复 retrieve
  也不增加相同操作日志；同 store 同 case 重跑 result/export 五文件逐字节一致。
- 同一锚点的评论、颜色、kind、tags、topics、concepts、entities、source_time 被编辑时，
  更新原记录并在 change_records 记录字段级 old/new；重复同一修改不重复制造 diff。
- 同 doc_id 重新 load 不同文本会使旧锚点接受 verify 检查。没有 manufacturer 版本关系时
  不自动猜哪个文件更新；请加载两个独立 doc_id 或补真实版本文件。

## Limits

- 文档与批注必须先由真实 extractor 提供；本 Skill 不假装自己已经读取 PDF 注释层、扫描
  手写图或网页历史。环境 PDF/OCR 输出可以接入，但失败时只交付可读部分。
- quote 是精确锚；OCR 相似度只用于定位候选段，不能替代人工核对。知识关联是同 kind 的
  词汇证据，不是因果、矛盾或语义蕴含证明。
- 检索是词法检索；复杂同义 paraphrase 可能召回不足。此时返回空并建议调整 query/filter，
  不用热门卡片填充。
- 复习导出是静态后续行动和相对间隔，不伪造调度后台、学习记录或时间。一个 store 同时
  应只有一个写入者；并行写没有分布式锁。

## Verification

```bash
python scripts/bench_annotate.py             # 29 个锚点/类型/版本/检索/契约原回归
python scripts/bench_knowledge_cards.py      # 12 个卡片/回链/多维过滤/复习/导出/编辑场景
python scripts/bench_annotate_hostile_v3.py  # 12 个敌意结构/时间/退出码/确定性探针
```

当前版本 53/53 全过。clean baseline 要求正确锚点与正常 card 不误报；无答案查询为空；
重复 ingest/export/result 不增长。测试 fixture 均在临时目录生成，不是正式答案。

## 创新增益（与真实实现一致）

1. **多坐标硬锚定**：全出现枚举 + page/start 消歧 + OCR 候选恢复，比“搜到一句就挂”可复核。
2. **批注到卡片不丢语义层次**：source excerpt 与 reader comment 分离，类型/颜色/标签/
   主题/概念/实体不丢失，输出 schema 可进入后续写作而非只剩摘抄。
3. **关联正反两向可查**：共享词证据与版本证据驱动 between_cards/directions/backlinks，
   不再是不可解释的关键词团块。
4. **沉淀后仍有行动入口**：真实多维检索、后续验证动作、静态间隔计划与 CSV 导出贯通；
   未执行行为保持 not_started。
5. **工程幂等性可证明**：无墙钟时间，store/save/ingest/result/export 都处理重复运行，
   编辑可追踪 diff，五类交付产物可冷校验哈希一致。

## Requirements / 生态贡献

Python 3.10+，仅标准库，无网络、无账号、无第三方依赖。`annotate.py` 的 Annotator、
`reader.py` 的 Workspace 可独立导入；批注 schema、卡片 schema、关联规则、CSV/JSON/Markdown
导出与 53 个回归均可复用。维护时新增字段必须同时实现真实 CLI 行为、契约直通、冷导入、
中文无命中、敌意结构与字节确定性测试，并同步本文档；不得用自述替代产物。

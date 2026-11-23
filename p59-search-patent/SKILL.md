---
name: search-patent
description: >
  专利与技术文献检索：在获授权的快照、USPTO 原件、专利记录和科学论文上完成
  可复核检索。区分公开号、申请号、授权号、优先权号；按明确声明的简单族或
  INPADOC 族归并；按优先权日、申请日等独立日期字段过滤；区分快照法律状态与
  当前官方登记；保留权利要求版本、来源定位、许可与不确定性。未知号返回诚实
  空结果，受限原文在索引前剥离，缺失和冲突进入 review，权限阻断进入 blocked，
  无法判定进入 undetermined。适用于号码定位、同族、主题、法律状态和论文对照；
  不用于专利撰写、侵权判定、FTO 结论、价值评估或绕过访问控制。
---

# 专利与技术文献检索：找到文献，也保留筛选依据

## 1. 目标与不可逾越的边界

本 Skill 交付的不是“看起来相关的一串网页”，而是可由第三人复跑的候选集：每个候选有规范化字段、排序或筛选理由、来源定位、查询记录、缺失项与不确定性。引擎只处理调用者有权使用的本地快照；联网核验只能使用案例明确授权的工具和来源。

必须遵守六条边界：

1. **号码不混用。** 公开号、申请号、授权号、优先权号各有独立字段，kind code 保留；不能因号码相似就互换。
2. **同族不猜测。** 简单族和 INPADOC 族分别读取明确字段；`members` 只是观察到的链接，不是完整同族，也不证明权利要求范围相同。
3. **日期不替补。** 优先权日缺失时不能拿申请日补齐；公开日、授权日、状态生效日同样不得混用。年月精度不补成虚构的具体日。
4. **状态不过期承诺。** 快照里的 granted、pending、expired 只是记录值。没有带查询日期的官方登记核验时，当前法律状态必须是 undetermined。
5. **权利要求不越界。** 只概述实际定位到的权利要求版本及其文本，不从标题、摘要或同族关系推导保护范围，不输出侵权或自由实施法律结论。
6. **权限不绕过。** 不绕过登录、付费墙、验证码或许可限制，不上传受限材料。红色来源在建索引前排除，命令能否读取文件不等于有权展示其内容。

## 2. 六步运行时入口

### 第一步：读真实案例，固定契约并尽早保存部分结果

读取 `/input/case.json`、`/input/task.md` 以及运行环境提供的 environment/resources.yaml。先记录：

- `case_id` 和原始 `output_contract`；最终字段以案例为准，不能用本说明的字段覆盖或删减原契约。
- 任务对象、国家/语言、号码或主题、日期范围、期望专利与论文类型、当前状态核验要求。
- 实际材料路径、来源名称与版本、查询日期、许可、访问级别和允许展示字段。
- 可用 PDF/OCR/浏览器工具及其权限；按照材料实际内容读取，不依据文件名或领域标签猜答案。

在 `/app/output/result.json` 尽早写入带 `case_id`、真实状态和不确定性的诚实部分结果。后续每个成功阶段再增量完善；不要把“尚未运行”写成 clean。

### 第二步：从原始材料建立可定位 corpus，不创建答案层

把实际专利记录、USPTO facsimile 和比较论文转换为 `/app/work/corpus.json`。原始 PDF 优先使用平台 PDF 文本工具，图像页再使用获授权 OCR；记录工具、版本、页码和 OCR 不确定性。

对 finite patent record corpus、若干 USPTO 原件和科学比较论文，应逐条保留来源，不把某条记录当成全库。若 WO 文本存在合并 OCR 边界，原样保留该边界并注明，不能私自“修复”为未经证实的权利要求文本。不要预抽取所谓标准答案、预设命中列表或编造法律状态。

最小记录形状如下；结构化字段可以代替 `text`，引擎会为已识别字段建立可定位文本：

```json
{"documents": [
  {"id": "pat-example",
   "text": "id: pat-example\nTitle: example coating\ndocument_type: patent\nnumber: US 10,000,000 B2\napplication_number: US 16/000,000\nfamily: F1\ninpadoc_family: I1\npriority_date: 2020-01-01\nfiling_date: 2021-01-01\nstatus: pending\nstatus_date: 2026-01-15\nclaim_version: publication-v1\nclaims_source: source page 12\nsource: authorised snapshot\nsource_version: v1\nquery_date: 2026-01-15\nlicense: declared licence\naccess: green"}
]}
```

### 第三步：拆解问题并建立版本化 query battery

一个案例通常不是一个查询。至少把“号码定位、同族、主题专利、比较论文、法律状态、权利要求版本”拆成可独立复核的探测，并保存为 `/app/work/queries/q01.json` 等。每次有意扩词或改口径都新建版本，不覆盖旧查询。

主题检索把不可让步的范围放入 `all`，同义词和缩写放入 `any`，排除词放入 `not`，再以 CPC/IPC、申请人、文献类型和日期字段收窄。`all` 全部成立、`any` 至少一个成立、`not` 任一出现即排除；引擎不会为制造命中而放松条件。专利与学术论文可以共用索引，但必须用 `document_type` 分组报告，不能给论文强行填专利族或法律状态。

### 第四步：在 work 中逐查询执行，保存 index 与原始结果

平台安装后的典型调用：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/search_cli.py --case /input/case.json --corpus /app/work/corpus.json --query-file /app/work/queries/q01.json --out /app/work/runs/q01
```

每个查询写自己的目录，保留 `index.json` 和 `result.json`。不要逐个覆盖，也不要把最后一次探测误当完整答案。最终汇总才写 `/app/output/result.json`。重复检索优先重放保存的索引：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/search_cli.py --index /app/work/runs/q01/index.json --query-file /app/work/queries/q02.json --out /app/work/runs/q02
```

### 第五步：逐候选核验证据、状态和遗漏

对每个候选检查：

- 号码规范值是否同时有原始字段行定位；引文必须满足 quote 等于对应段落的 start/end 切片。
- 库名、版本、查询日期、URL 或文件页码是否足以回到来源；聚合站信息不能改称官方著录项。
- 同族采用哪种口径，观察范围是否穷尽；冲突族号保留分组，不跨族硬合并。
- 日期过滤是否使用任务指定字段，缺失和非法日期是否列入遗漏说明。
- 法律状态是否仅来自快照；若任务要求“现在是否有效”，只有在授权官方登记中实际查得并记录查询日期后才升级证据，否则保留 undetermined。
- 权利要求版本和来源是否一致；公开文本、授权文本、OCR 文本不可混称同一版本。
- 论文是否作为技术证据单独排序，专利是否按号码/族/分类/申请人证据单独排序。
- 未命中、排除、权限缺口、库覆盖不全是否均进入遗漏说明，而非用“没有此项技术”结尾。

### 第六步：按原契约汇总最终交付，做可复跑自查

将各查询的真实结果汇总到 `/app/output/result.json`，保留原 `output_contract` 全部字段、`case_id`、检索结果、证据记录、状态说明、来源、不确定性、排除与遗漏、人工核验和实际 `change_records`。变更记录写查询版本、字段规范化、人工取舍及理由，不伪造平台分数、运行时间或原生 trace。

最后按保存的索引至少重放一个号码查询和一个主题查询，核对命中、指纹和引文切片。提前写入的部分结果只有在相应步骤实际完成后才可改写状态。

## 3. 任务措辞到执行路由

| 任务措辞 | 推荐探测 | 必须保留的边界 |
|-|-|-|
| “查这个公开号/这件专利” | 裸号码，或 `number` + `number_kind=publication` | 去空格、逗号、斜线并大写；精确匹配，不做模糊补号 |
| “用这个申请号/授权号/优先权号找” | 对应号码别名 + 可选 `family_of` 后续探测 | 申请、授权、公开、优先权字段不可互相代替 |
| “列出简单同族” | `family_of=<seed number>`、`family_scope=simple` | 只沿声明的简单族号扩展；未知 seed 是空结果 |
| “做 INPADOC 同族归并/扩展族检索” | 同一 seed，`family_scope=inpadoc` | 只合并声明的 INPADOC 号；不把简单族或 members 当扩展族 |
| “优先权日在某区间” | `date_field=priority_date` + `date_from` 与 `date_to` | 缺失不用申请日替代；保留年月精度 |
| “某年提交的申请” | `date_field=filing_date` + 区间 | 申请日与优先权日分别过滤 |
| “现在是否有效/法律状态是什么” | `status` 定位 + `require_current_status=true` | 无带日期官方登记核验时当前状态为 undetermined；注明滞后 |
| “保护什么/权利要求范围” | `claim_version` 或 `require_claims=true`，再回到原文阅读 | 只概述该版本文本；同族不等于同权项，非侵权/FTO 意见 |
| “找某 CPC/IPC、申请人和关键词的专利” | `all/any/not` + `cpc/ipc` + `applicant` + `document_type=patent` | 分类号按层级前缀，申请人按文本；引文说明每个筛选理由 |
| “找同主题科学论文作对比” | 主题词扩展 + `document_type=technical_paper` | 按题目、DOI、年份、期刊与论文证据报告，不套专利族/状态 |
| “只给我有权展示的结果” | `require_source_license=true`，先查 access/license/display_scope | 红色直接排除；黄色只按许可范围降级；空白许可须人工确认 |

## 4. 查询与字段映射

查询对象支持 `all`、`any`、`not` 和下表过滤字段；也可以把过滤项放进 `filters`。未知字段直接拒绝，避免拼写错误被静默忽略。

| 原始标签示例 | 规范字段/查询 | 运行语义 |
|-|-|-|
| number、publication_number、公开号 | `publication_number`；查询可用 `number` | 只作为公开号；kind code 保留 |
| application_number、app_number、申请号 | `application_number`；同名查询别名 | 不以公开号或授权号代替 |
| grant_number、授权号 | `grant_number`；同名查询别名 | 授权号与公开号即使同值也保留字段语义 |
| priority_number、优先权号 | `priority_number`；同名查询别名 | 只用于优先权定位，不据此猜完整同族 |
| family、simple_family | `family`；`family_scope=simple` | 简单族声明值 |
| inpadoc、extended_family | `inpadoc_family`；`family_scope=inpadoc` | INPADOC 声明值，不与简单族自动互算 |
| members、observed_members | `family_members` | 观察链接，仅作线索，不作穷尽性或同权项证明 |
| priority_date、earliest_priority_date | `priority_date` | ISO 年/月/日区间，不能由申请日填补 |
| application_date、filing_date | `filing_date` | 申请日；与优先权日独立 |
| publication_date、grant_date | 各自同名字段 | 公开与授权日期独立 |
| status、legal_status | `status` | 快照 token；不等于当前官方状态 |
| status_date、query_date、registry_verified | 同名字段 | 与官方 source_type 共同决定可达到的证据级别 |
| cpc、ipc | `cpc`、`ipc` | 去展示标点后按分类层级前缀匹配 |
| claim_version、claims_version | `claim_version`；`claims_source` 辅助定位 | 公开、授权、OCR 等版本分别标识 |
| source、source_version、url | 同名字段 | 库名、版本和回溯定位，不省略查询日期 |
| license、access、display_scope | 同名字段 | 绿/黄/红依赖与可展示范围 |
| document_type | `patent` 或 `technical_paper` | 专利与论文分开筛选和报告 |

数值号码的展示 punctuation 会被去除，字母统一大写；原始字段文本仍作为证据保留。日期支持 YYYY、YYYY-MM、YYYY-MM-DD、YYYYMMDD；过滤区间包含边界，不完整日期按真实年月区间参与比较。其他格式，尤其有歧义的日/月顺序，不猜测。

## 5. 输出契约：rubric 三段一一对应

成功、部分成功和权限阻断的结果均包含下述三段；案例另声明的字段照常回填。

| rubric 原词 | 本 Skill 的内容 | 完成标准 |
|-|-|-|
| `检索结果` | `候选文献`、`排序/筛选结果`、`排序依据`、`筛选依据`、`同族归并`、`缺失项` | 候选与范围一致；每条有相关性/排除理由；同族注明口径、非穷尽和非同权项 |
| `证据记录` | `查询`、`来源与定位`、`索引指纹`、`定位`、`字段口径`、`发现` | 每条可回到来源；quote 可切片复核；查询和字段映射可重跑 |
| `状态说明` | `运行状态`、`空结果`、`冲突`、`权限或接口异常`、`已完成`、`未完成`、`不确定性` | 空结果、冲突、缺失、权限和接口问题分别呈现，不补造文献或状态 |

顶层还保留 `hits`、`query`、`sources`、`families`、`findings`、`limits`、`uncertainty`、`change_records`、`index_sha256` 等兼容字段。`case_id` 始终优先来自案例。`output_contract` 可为字段列表、带 name/field/key 的对象列表或字段名对象：引擎已经填充的值优先，其次是案例显式值；仍无证据的字段写 null、进入 review，并在 limits 命名。

**拒绝路径是例外：**无法读取输入、查询无效或索引损坏时，只写 `case_id`、`status=undetermined`、refusal 和 limits；不回填 `output_contract`，因为并没有完成可交付检索。

### 运行状态和退出码

| 状态 | 退出码 | 含义 |
|-|-|-|
| clean | 0 | 查询完成；可以有诚实空结果或低风险重复导出记录 |
| review | 3 | 有可用结果，但存在缺失、冲突、部分权限缺口、当前状态未知或契约字段缺值 |
| blocked | 4 | 全部可寻址记录受权限阻断；没有返回受限全文 |
| undetermined | 5 | 输入、索引或查询无法支持判定；拒绝记录已落盘 |
| 本地命令用法错误 | 2 | 仅命令行参数解析；正式案例不应以此替代结构化结果 |

状态由发现自动决定，不允许 Agent 为“更好看”而降低等级。空结果本身不是失败，也不是全球不存在证明。

## 6. 最小 worked example（实际运行，非正式案例答案）

输入文件：`examples/case.json`、`examples/corpus.json`、`examples/query.json`。它们是**合成回归材料**，不是组织方正式案例或法律意见。语料含 4 件专利、1 篇论文、1 条重复导出；US/EP 属于简单族 F101，WO 通过同一 INPADOC I901 相连但属于另一简单族 F103。

查询：

```json
{"family_of": "US 10,132,852 B2", "family_scope": "simple",
 "require_fields": ["publication_number", "priority_date", "claim_version", "source"]}
```

在本包根目录实跑：

```bash
python -I -X utf8 scripts/search_cli.py --case examples/case.json --corpus examples/corpus.json --query-file examples/query.json --out ./_run_example
```

控制台实际返回 clean、2 hits、`case_id=example-family-simple-v2`。以下为本次真实输出的节选，未省略的字段名和值均来自运行：

```json
{"case_id": "example-family-simple-v2", "status": "clean",
 "query": {"all": [], "any": [], "not": [], "number_kind": "any",
           "family_of": "US10132852B2", "family_scope": "simple",
           "require_fields": ["publication_number", "priority_date", "claim_version", "source"]},
 "index_sha256": "3e400939f0712ac240ab835a0fd3aa53daa69ae398c068fb66e43988d8b87ed3",
 "documents_indexed": 5,
 "hit_ids": ["pat-US10132852B2", "pat-EP3061620A1"],
 "first_hit_number_evidence": {
   "term": "US 10,132,852 B2",
   "locator": {"doc_id": "pat-US10132852B2", "paragraph": 3,
               "start": 8, "end": 24, "field": "publication_number",
               "quote": "US 10,132,852 B2"}},
 "first_hit_claim_version": "granted-2018-11-20",
 "first_hit_current_status": "undetermined",
 "families": [{"scope": "simple", "family_id": "F101",
               "doc_ids": ["pat-EP3061620A1", "pat-US10132852B2"],
               "member_count": 2,
               "coverage": "observed indexed members only; not an exhaustive family",
               "claim_scope": "membership does not establish equal claim scope"}],
 "findings": [{"rule": "search.doc_skipped", "severity": "low", "count": 1}],
 "output_contract_fields": ["case_id", "检索结果", "证据记录", "状态说明", "delivery_note"]}
```

把 `family_scope` 改为 inpadoc 的新查询实际命中 US、EP、WO 三条，WO 不会被误塞进简单族 F101。US 的快照记录虽然为 granted，其当前官方法律状态仍为 undetermined，这正是状态证据边界而非结果缺陷。原始 `US 10,132,852 B2` 与规范值 `US10132852B2` 可同时复核，quote 是段落切片。

## 7. 规则索引与降级语义

以下每个 id 均在引擎中实现；每个专利规则在 `scripts/bench_patent.py` 有触发场景，且配有独立 FP guard 或反向正常场景。高风险权限项导致 blocked，中风险项导致 review，导出跳过记录为 low；解析拒绝为 undetermined。

- `search.spec_unreadable` — case、corpus、index 或 query 不是可读取的声明 JSON；exit 5。
- `search.empty_corpus` — 无文档、形状错误或没有可索引记录；exit 5。全受限不是空 corpus，走权限阻断。
- `search.index_malformed` — documents/order 损坏、文档结构缺项或 order 重复；整体拒绝，exit 5。
- `search.empty_query` — 没有正向词汇或专利字段条件；不能拿纯排除条件扫描全库。
- `search.doc_skipped` — 非文档项或重复 id 被命名，不静默合并；low，其余记录仍可运行。
- `search.internal_error` — 未预见失败被封装成 undetermined，保留 case_id，不暴露 traceback 或伪契约。
- `patent.number_collision` — 同一规范号码对应不同文档 id；不合并，review。
- `patent.family_conflict` — family_of 遇到多个声明族号；分组保留，不跨族合并。
- `patent.family_missing` — seed 缺声明族号时只保留 seed；members 不补族。
- `patent.date_missing` — 日期过滤排除了缺指定日期字段的记录；列出遗漏。
- `patent.date_invalid` — 源日期非法，或过滤记录没有可用的指定日期；不猜测日期。
- `patent.date_order` — 命中记录最早优先权日晚于申请日；提示元数据一致性复核。
- `patent.query_date_invalid` — 查询日期非法或区间倒置；查询前拒绝，exit 5。
- `patent.status_unverified` — 用户要求当前状态但只有非官方、无日期或未验证记录；当前状态保持 undetermined。
- `patent.status_conflict` — 共享规范号码的记录具有冲突状态；不同族成员不同状态不会误报。
- `patent.claim_version_missing` — 要求或过滤权利要求版本但记录无版本；文本不混作另一版本。
- `patent.source_restricted` — access 为 red/restricted 等时索引前排除全文；yellow 未声明 full_text 时仅保留授权元数据。全部受限 exit 4，混合或黄色降级 exit 3。
- `patent.source_license_unknown` — 用户要求授权核验但来源没有 license 或 access；不推定许可。
- `patent.field_missing` — `require_fields` 中指定元数据缺失；逐文档逐字段列出。
- `patent.query_field_unknown` — 未知过滤字段、冲突号码别名、非法枚举或布尔值；exit 5，FP guard 覆盖合法 filters。
- `patent.metadata_conflict` — 结构化字段与文本标签冲突；采用声明的结构化覆盖并保留两个值供核验。
- `patent.contract_field_missing` — 完成的查询仍无法为原 output_contract 提供证据值；字段为 null 并 review，不编造内容。

## 8. 异常处置表

| 症状 | 状态/退出码 | 处置与交付 |
|-|-|-|
| 官方或商业接口限流、超时 | review，若查询未执行则 undetermined | 保存已成功的查询、失败接口和重试边界；不将异常当空结果 |
| 登录/鉴权失败、付费墙 | blocked 或部分 review | 不尝试绕过；列出未覆盖库，使用已授权公开材料降级 |
| 全部记录 access=red | blocked / 4 | 索引和结果均无受限原文，只保留 id/source 级阻断原因 |
| 绿红混合或黄色展示限制 | review / 3 | 返回获授权部分；黄色仅展示许可字段，明确完整性缺口 |
| 未命中号码或主题 | clean / 0 | 写空候选、实际查询和覆盖范围；可另建扩展查询，不能补造命中 |
| 号码格式不一致 | 运行后判断 | 去标点并保留 kind code；若多 id 同号则 review，不自动合并 |
| 简单族号缺失 | review / 3 | 保留 seed，拒绝用 members 或 INPADOC 偷换简单族 |
| 多种族号冲突 | review / 3 | 分组列出族号、证据和候选；人工判定，不跨组去重 |
| 优先权日缺失 | review / 3 | 记录未纳入日期过滤的候选；不得拿申请日补齐 |
| 非法日期或日期倒置 | 源数据 review；查询 undetermined | 源数据列入异常；非法查询在执行前拒绝 |
| 法律状态快照过旧或只有转载 | review / 3 | 当前状态写 undetermined，补授权官方查询；记录查询日期和可能滞后 |
| 同号法律状态冲突 | review / 3 | 并列记录来源/生效日，不选择“看起来最新”的转载作为结论 |
| 权利要求版本缺失或不一致 | review / 3 | 指明公开/授权/OCR 版本；只概述实际读到的权项，必要时人工复核 |
| WO 合并 OCR 边界、乱码或缺页 | review / 3 | 保留边界、页码和 OCR 限制；不静默修补号码、权项或段落 |
| 字段缺失、结构化字段与文本冲突 | review / 3 | 两个值都留痕；按映射表选择声明覆盖，完成未完成项分别写 |
| 索引损坏或不可重放 | undetermined / 5 | 从原始 corpus 重建；绝不搜索半截索引 |
| output_contract 存在无证据字段 | review / 3 | 字段写 null、limits 命名；若是拒绝运行则完全不回填契约 |
| 重复执行结果不同 | review，停止交付 | 检查输入指纹、文件顺序、手工改动和外部查询日期；不写墙钟时间伪造一致性 |

## 9. 可验证的使用增益与创新增益

### 真实新增能力

1. **四类号码独立规范化与精确定位。** 格式化公开号可命中，原字段行仍保留；申请号不会误吃授权号。FP guard 覆盖不同 kind code 和同件公开号/授权号并存。
2. **声明式简单族与 INPADOC 族归并。** family_of 先定位 seed，再按选定口径扩展；保留观察范围与非等同权项声明。缺失、种子不存在和多族冲突是三种不同情况。
3. **日期字段隔离与区间过滤。** 支持精度保留、边界包含、缺日期/坏日期/优先权晚于申请日检查，杜绝跨日期字段填充。
4. **状态证据分级。** 快照状态、带日期官方登记和当前状态分开；未达证据级别时自动输出 undetermined，而不是生成确定法律结论。
5. **权利要求版本和 WO OCR 边界留痕。** 版本是过滤条件也是结果元数据，没有版本不能冒充公开或授权权项。
6. **权限前置降幂。** 红色记录在索引前移除；黄色记录未明确声明 full_text 时按 display_scope 白名单只保留授权元数据，混合输入只降级获授权部分。探针同时扫描 index 和 result 验证秘密文本未 serialise。
7. **契约直通与可重放指纹。** case_id 和所有原 output_contract 字段有明确优先级，拒绝路径不伪填；使用完整 64 字符 SHA-256 指纹，索引可独立重放。

### 效率与对照证据，不虚构分数

效率来自一次建码后多次字段探测、族自动扩展、重复导出去重、稳定排序和缺失误报 guard；不把“检索条数更多”当质量。公平 A/B 应让基础 Agent 与本 Skill 使用同一案例、同一授权来源、同一查询预算，比较：有效候选率、号码/日期/族错误数、可切片证据比例、当前状态误报数、遗漏声明完整率，以及人工回库次数。保存两边的原生记录后再计算差异；本包不预填任何提高百分比、运行秒数或平台分数。

可独立复跑的证据：

```bash
python -I -X utf8 scripts/bench_patent.py
python -I -X utf8 scripts/probe_patent.py
```

当前 bench 为 **51/51**，含 **17 个独立 FP guard**；黑盒敌意探针为 **31/31**，每个均核查预期 exit、可解析 result.json 和无 traceback。`scripts/report_patent.json` 与 `scripts/report_probe.json` 是合成回归报告，不是组织方正式测评结果。

## 10. 可靠性与适用限制

- 引擎是确定性 lexical + 字段检索，不是语义检索；完全不含同词的 paraphrase 可能漏检，必须以版本化 `any` 扩展并记录。
- 排序分数为不同命中词数加声明字段匹配数，同分保持 corpus 顺序；分数不是专利价值或法律相关性评价。
- 快照、观察链接和案例材料都不等于全球覆盖；空查询结果只说明本次可访问索引无命中。
- 简单族和 INPADOC 族只使用记录声明值，不根据优先权树自行生成权威族；需要权威族时必须回授权登记核验。
- 当前官方法律状态可能晚于快照；本引擎不会访问网络，也不会把案例给定“未知”改写成已知。
- 权利要求需要 Agent/人工回到定位页阅读；substring 不理解否定，family membership 不证明同权项，摘要不证明保护范围。
- OCR 可能损害号码和权项。无法定位的内容标为材料不可判，不用其他同族文本偷偷补齐。
- 黄色许可不是无限展示授权，红色来源即使本地可读也不能进入索引。第三方库原文不得因本说明而视为可公开。
- 单条查询最多返回 20 个定位片段；这是核验窗口，不是全文替代品。多阶段复杂检索使用 query battery，不把语义塞进一个超大 any。
- 纯标准库脚本不替代平台 PDF/OCR/浏览器工具；实际使用哪个工具必须在来源与 change_records 中注明。

## 11. 生态贡献八项

1. **完整 Skill 本体。** 本文件提供用途、六步调用、触发路由、输入输出、字段口径、许可边界、异常、限制、维护和自查。
2. **可导入引擎。** `scripts/search.py` 提供 `build_index(corpus)`、`run_query(index, query)`、`search(spec)` 和 `normalise_patent_number(value)`；仅 Python 标准库。
3. **平台与本地双 CLI。** `scripts/search_cli.py` 支持案例、corpus、查询文件、裸查询和索引重放；四态退出码和 result.json 可独立集成。
4. **可复用查询模板与合成示例。** `examples/query.json` 是简单族 seed 模板，改 family_scope 即形成 INPADOC 对照；`examples/corpus.json` 同时含专利、论文和重复导出。
5. **契约示例与字段映射。** `examples/case.json` 展示列表型 output_contract；本说明的映射表覆盖号码、族、日期、状态、权项、分类、许可和论文类型。
6. **回归题集与报告。** `scripts/bench_patent.py`、`scripts/report_patent.json` 提供 51 个场景及 17 个 FP guard，可加入 CI，且每条规则可追溯到场景。
7. **敌意验证与授权核验清单。** `scripts/probe_patent.py`、`scripts/report_probe.json` 覆盖 31 个黑盒边界；异常表可直接复用为上线前授权/缺失/冲突核对清单。
8. **公开分享与维护入口。** `GITHUB_URL.txt` 指向公开仓库及本题目录；版本为 patent-search/v2，修改字段语义或规则时必须同步更新示例、bench、FP guard、探针和报告，不能只改文案。

## 12. 环境、交付和收尾清单

Python 3.9+，在 Python 3.14 验证；无第三方包、无个人绝对路径、无隐藏网络依赖、无 symlink。所有 fixture 均为 UTF-8 合成文本。PDF/OCR/Office 等能力使用平台实际提供的工具，不要求把二进制预览塞进 Skill 资源。

交付前逐项确认：

- 已读实际案例与原始材料，而非只按任务标签回答；case_id 与原 output_contract 完整保留。
- 号码、族、日期、状态、权项、论文均有各自探测；结果不是预写答案。
- 每条候选有来源、版本、查询日期、相关性依据和可切片定位；每条排除有理由。
- 当前官方状态未知时明确未知，没有把记录状态当实时法律意见。
- 简单族/INPADOC 族、公开/申请/授权/优先权号、专利/论文、公开/授权/OCR 权项均未混淆。
- 空结果、冲突、缺字段、库覆盖有限、权限与接口问题分别列出；已完成与未完成分栏。
- 红色全文未进入 index/result，受限来源未被上传或绕过；人工复核建议具体可执行。
- change_records 只记录真实操作；两次本地重放一致；最终文件位于 `/app/output/result.json`，原始逐查询证据保留在 `/app/work/runs/`。
- `GITHUB_URL.txt` 第一行为无需登录即可访问的仓库链接，第二行为 `p59-search-patent/`；提交前应以未登录浏览器再核查公开可见性。

---
name: web-read-translate
description: >
  Turn a reader-supplied web page's text into an auditable bilingual reading
  artifact: body extraction that cuts navigation, ads, related-article,
  reference-list and footnote noise with a recorded cut list; per-paragraph
  segment ids with page-line locators, so every translated paragraph points back
  to the exact source paragraph; heading and caption paragraphs kept separate
  from body text; a per-paragraph translation audit that flags untranslated
  paragraphs, empty targets, untranslated pass-throughs, dropped digits and
  units, glossary violations, non-Chinese targets, and orphan translations
  referencing segment ids cleaning did not produce. Echoes the platform case_id
  and every output_contract field into result.json. Use when a task supplies web
  page text (already fetched) that must become clean body text plus a per-paragraph
  Chinese translation where 译文与原文逐段对得上、术语译法一致、数字与单位原样保留、
  每段都能回到原始位置核对.
---

# web-read-translate

The failure this prevents is the silent one: the page text still contains navigation
and ad lines mixed into the article, the translation skipped a paragraph, a digit or
unit was lost, one term was glossed two different ways, or a translated paragraph
cannot be traced back to where it came from — so a reader must re-verify everything
by hand.

Three guarantees, each enforced by the engine and auditable from result.json:

1. **正文就是正文.** Navigation, ads, related-article, reference-list and footnote
   lines are cut with a recorded cut list (`web.noise_cut` low, per-cut class),
   never silently kept or deleted. A page that is all noise reports an honest empty
   body (`web.body_empty`).
2. **译文与原文逐段对得上.** Every kept paragraph gets a stable segment id
   (`P1`, `P2`, …) with a page-line locator. A translation keyed to a segment id
   that cleaning did not produce is an orphan (`web.orphan_translation`); a body
   paragraph with no translation is flagged (`web.paragraph_untranslated`); an
   empty target (`web.empty_target`) and an untranslated pass-through
   (`web.untranslated_passthrough`) are both refused a clean status.
3. **每段都能回到原始位置核对.** Locators carry the original page-line numbers,
   and the record carries the page URL, fetch time and content hash — a reader can
   re-fetch, re-extract and walk every segment back to its line.

## 六步运行时入口（Harbor 契约）

平台运行时原始输入固定为 `/input/case.json` 与 `task.md`；工作区 `/app/work`；
最终交付写 `/app/output`。按以下六步执行：

| 步 | 动作 | 要点 |
|-|-|-|
| 0 | 读 `/input/case.json` | 取 `case_id`、任务说明与 `output_contract`（原样保留，不改名）；按 `task.md` 指向的路径读**实际页面文本**——标签与文件名不是内容来源 |
| 1 | 判形态路由 | 按下方「任务措辞 → 路由」表确定走哪条路径；多栏/动态页面、付费墙、登录内容在路由阶段就 Declared 不适用，不硬做 |
| 2 | 先产出目标产物 | 先跑一次 Stage-A 清洗拿到 body.txt 与 segments——即使后续翻译中断，正文交付已在盘上（尽早写出诚实的部分结果） |
| 3 | 构造翻译与 spec | 逐段翻译（用 segments 的 id 作键），把 `--source-url / --fetched-at / --case` 与实际值装进命令行；术语表写进 `gloss.json` |
| 4 | 审计 | 带 `--translated` 重跑 CLI，得到 findings 与 severity_counts；退出码 0/3/4/5 见下表 |
| 5 | 修发现重跑 | 逐条按 failure_recovery 的 recovery 提示修复翻译文件后重跑，直到 medium/high 清零或材料本身不允许 |
| 6 | 合并 result.json | 把引擎 result.json 放进 `/app/output`，回填 case 契约字段（见下文映射表），status 按映射写成 done/partial/failed，并附 uncertainty 与 limits |

引擎已实现契约直通：`--case case.json` 会把 `case_id` 与 `output_contract` 的每个
字段写进 result.json 顶层——字段值已在结果里的保留，case 顶层携带的小体积值原样
拷贝，契约里的字面量（短字符串/数值/布尔）直接回填，推导不出的填 null 并在
limits 里写明。因此把可推导的值放进 case.json 顶层或 CLI 参数，即直通最终
result.json。

## 任务措辞 → 路由

| 任务措辞 / 输入形态 | 路由 |
|-|-|
| 给了已抓取的页面文本，要求「提取正文/去噪」 | Stage-A only：`--page --out`，不带 `--translated`；交付 body.txt + segments + cuts |
| 给了页面文本，要求「翻译成中文」 | Stage-A → 逐段翻译 → 带 `--translated` 审计；完整交付 = result.json + body.txt |
| 任务点名「术语一致/统一译法」 | 加 `--glossary gloss.json`（term → 译名），审计会逐段核对声明译名是否落地 |
| 任务点名「数字/单位/公式上下标」 | 默认开启：源段数字未出现在译文会点名（web.number_dropped）；上下标由翻译方保留，审计只保证可回查 |
| 页面文本全是导航/广告/订阅页 | 预期 web.body_empty（exit 4）——如实报告「抓到的是题目页/摘要页」，不硬翻 |
| 抓到的是参考文献列表/相关推荐 | cuts 里按 citation-list/related 类记录位置，正文不含它们；参考文献标注位置从 cuts 可查 |
| 只给了 URL，没给页面文本 | 抓取是 Stage 0，不在本 Skill 范围；用平台浏览器/pdf 工具先取文本，再进本流程 |
| 多栏排版 / 动态渲染页面 | Stage 0 的 fetch 责任：先 re-flow 成单栏文本再进来；两栏直接粘贴会读成交错行——Limits 有说明 |
| 付费墙 / 登录失效 / 改版 | 页面文本里没有的内容不存在：body_empty + limits 写明失效条件，停止并说明，不编造 |
| 翻译中断（只翻了一部分） | 部分翻译文件直接可审计：未翻译段落逐条点名（web.paragraph_untranslated），已翻段落照常交付——诚实 partial |
| 译文目标语言不是中文 | 加 `--target-lang en`（或实际语言）关闭中文占比检查，避免误报 |

## Workflow

```bash
# Stage A: clean the page text into body paragraphs (works alone)
python scripts/webtranslate.py --page page.txt --out ./out

# Stage B: translate per paragraph (P1, P2, ... from result.json's segments),
# then audit — with case contract, glossary and provenance:
python scripts/webtranslate.py --page page.txt --out ./out \
    --translated translated.json \
    --case /input/case.json \
    --glossary gloss.json \
    --source-url https://example.org/journal/paper-123 \
    --fetched-at 2026-11-22T10:00:00Z
```

翻译文件是一个 JSON 列表，每段一条，`id` 必须用本次清洗产出的 segment id：

```json
[{"id": "P1", "target": "1 引言", "terms": [{"term": "porous coating", "gloss": "多孔涂层"}]},
 {"id": "P2", "target": "多孔涂层使吸收速率提高三倍。"}]
```

退出码：`0` clean（无任何发现），`3` review（噪声切剪、未翻译段落、孤儿翻译等
中低发现——见第六步的 status 映射），`4` blocked（空目标/空正文），`5`
undetermined（页面/翻译/case/glossary 文件缺失、非 UTF-8、非 JSON、非对象——
拒绝路径仍写 result.json，绝不崩溃）。

## Rules

| rule | severity | what it proves |
|-|-|-|
| `web.noise_cut` | low | 导航/广告/相关/文献/脚注行被切且逐条记录，切剪可审计 |
| `web.body_empty` | high | 清洗后没有正文段落——页面全噪声或抓取失败，如实报告 |
| `web.paragraph_untranslated` | medium | 一个正文段落没有同 id 的译文，译文与原文错位 |
| `web.orphan_translation` | medium | 译文引用了清洗没有产出的 segment id，无法回查 |
| `web.empty_target` | high | 一条译文是空串 |
| `web.untranslated_passthrough` | high | 译文与原文逐字相同——漏译伪装成翻译 |
| `web.number_dropped` | medium | 源段里的数字没有以原形式出现在译文中——数字/单位/上下标可能丢失 |
| `web.term_gloss_mismatch` | medium | 术语表声明译名的词条在源段出现、译名却没落在译文里 |
| `web.term_conflict` | medium | 同一术语在不同段被注成两种译法 |
| `web.target_not_zh` | medium | 默认 zh 目标下译文几乎没有中文字符 |
| `web.translated_record_invalid` | medium | 翻译文件里的非对象记录被点名，不静默丢弃 |
| `web.page_unreadable` | high | 页面/翻译/case/glossary 文件缺失、非 UTF-8 或非 JSON——拒绝（exit 5），不崩溃 |

## Output contract 与 rubric 三段映射

`result.json` 顶层字段：`status`、`case_id`、…output_contract 的每个原始字段…、
`findings[]`、`severity_counts`、`page_stats`、`segments[]`（id、source、locator、
heading）、`translated_segments[]`（id、source、target、locator、terms）、
`cuts[]`（line、class、text）、`operation_trace[]`、`failure_recovery[]`、
`uncertainty[]`、`limits[]`、`source`（file、sha256、url、fetched_at、label），
外加 `body.txt`（干净正文，段落间空行分隔）。

对应题目「Skill 运行后的输出要求」的三段：

| rubric 要求的输出 | result.json 承载 | 完成标准 |
|-|-|-|
| 工作流结果（提取/翻译任务的最终产物） | `segments` + `translated_segments` + `body.txt` + `page_stats` | 目标状态和字段正确：每段译文 id、locator 与清洗结果一一对应 |
| 操作轨迹（URL/版本、步骤、状态变化、来源定位） | `source`（url、fetched_at、sha256）+ `cuts`（逐行类别）+ `operation_trace` | 他人可复核每一步：切了哪些行、保留多少段、哈希多少 |
| 失败恢复（权限/改版/冲突/中断/重试记录） | `findings` + `failure_recovery`（每条发现的接管动作）+ `uncertainty` | 失败可发现、可解释、可接管；材料缺失/无法判断/运行失败分别说明 |

status 映射（第六步写 `/app/output/result.json` 时）：`clean` → done；
只有 `web.noise_cut`（low）的 review → **done**（切剪清单是操作轨迹而非缺陷，
但必须随交付附上）；其余 review → partial（status_reason 写明待补什么）；
`blocked` → failed；`undetermined`（exit 5）→ failed（写明失败环节）。

## Minimal worked example（示意）

输入 `examples/page.txt`（9 行：3 行导航 + 4 行正文 + References 一节），翻译文件
`examples/translated.json`，实际运行：

```bash
python scripts/webtranslate.py --page examples/page.txt --out out \
    --translated examples/translated.json \
    --source-url https://example.org/journal/paper-123 \
    --fetched-at 2026-11-22T10:00:00Z
```

示意输出（节选自一次实跑，标注为示例——不是正式案例结果）：

```json
{"schema_version": "web-translate/v2",
 "source": {"file": "examples/page.txt", "sha256": "be654f3818ca94bf",
            "url": "https://example.org/journal/paper-123",
            "fetched_at": "2026-11-22T10:00:00Z"},
 "status": "review", "severity_counts": {"low": 1},
 "page_stats": {"lines_total": 9, "body_paragraphs": 4, "lines_cut": 5},
 "segments": [
  {"id": "P1", "source": "1 Introduction", "locator": "page-line 3", "heading": true},
  {"id": "P2", "source": "Porous coatings raise the uptake rate three-fold.",
   "locator": "page-line 4", "heading": false}],
 "translated_segments": [
  {"id": "P1", "source": "1 Introduction", "target": "1 引言",
   "locator": "page-line 3", "terms": []}],
 "cuts": [{"line": 0, "class": "nav", "text": "首页"},
          {"line": 5, "class": "citation-list", "text": "References"}],
 "operation_trace": [
  {"step": 1, "action": "read page text", "detail": "9 lines in"},
  {"step": 2, "action": "clean body", "detail": "4 paragraphs kept, 5 lines cut"},
  {"step": 3, "action": "segment", "detail": "4 segments with page-line locators"},
  {"step": 4, "action": "translation audit", "detail": "4 translated segments checked"}],
 "failure_recovery": [{"rule": "web.noise_cut", "severity": "low",
   "recovery": "review the cut list; ..."}]}
```

带 case 契约运行（`--case case.json`，case.json 含 case_id 与 output_contract）时，
上述 result.json 顶层会再多出 `case_id` 与契约的每个字段。status 停在 review 是
**预期行为**：切剪清单必须被人工过目；按上面映射表，只有 web.noise_cut 的
review 在交付时写 done 并附上 cuts。

## Limits

- **The fetch is Stage 0 and out of scope.** This skill consumes the page text a
  fetch step already produced (single-column text; multi-column layouts must be
  re-flowed by the fetch step first — a two-column paste reads as interleaved lines).
- **Noise cutting is line-shaped.** A related-article block that flows like prose
  passes the line patterns; the cut list is recorded precisely so a reader can
  audit every cut instead of trusting a classifier.
- **Translation quality is the translator's.** This skill audits structure (every
  paragraph translated, non-empty, keyed correctly, digits preserved, glossary
  applied, target language as declared), not phrasing.
- **数字审计是形式检查.** 中文数字或单位换算的合法改写（25 C → 二十五摄氏度）会被
  点名进 uncertainty，由人确认——引擎不猜语义。
- **Terms enforcement is mechanical.** The glossary checks declared glosses appear
  where their source terms occur; choosing the glosses is the reader's job.
- **`recorded_at` 是墙钟时间.** 除它之外同一输入重跑 findings 逐条一致；幂等性按
  findings 比对，不按整文件字节比对。

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| 页面文件缺失 / 路径是目录 / 无权限 | exit 5 拒绝，result.json 写 undetermined + 原因；不崩溃、不交空结果 |
| 页面非 UTF-8（GBK/二进制） | exit 5 拒绝并附解码错误位置；先转码再重跑 |
| 页面全是导航/广告/订阅 | web.body_empty（exit 4）：如实说明「抓到的是题目页」，可核验部分照常交付 |
| 抓到摘要页或目录页 | 正文只有摘要段：照常清洗交付，limits 写明「正文主体不在页面文本中」 |
| 多栏粘贴 / 行序交错 | 路由阶段 Declared 不适用：先 re-flow；强行清洗会得到交错正文——点名并停止 |
| 翻译文件缺失 | 只跑 Stage A：正文交付先落盘（诚实 partial） |
| 翻译文件非 JSON / 非 list / 记录非对象 | 非 JSON/非 list → exit 5；非对象记录 → web.translated_record_invalid 点名行号 |
| case.json 缺失/坏 JSON/非对象 | exit 5：契约无法回填就不能产出合规 result.json——拒绝路径不回填契约 |
| glossary 非 JSON/非对象 | exit 5 拒绝（声明的输入必须能读） |
| 术语冲突 / 译名未落地 | web.term_conflict / web.term_gloss_mismatch → 修术语表或译文，重跑至清零 |
| 数字/单位在译文丢失 | web.number_dropped → 恢复数字或确认中文数字改写（进 uncertainty） |
| 译文非中文（目标语言声明为 zh） | web.target_not_zh → 改 `--target-lang` 或补译 |
| 重复运行 | 先核对 case_id 与页面 sha256 一致再复用上轮 findings；findings 逐条一致即幂等 |
| 段落锚点漂移（页面改版后重跑） | locator 指向新行号——用 sha256 判断页面是否同一版本，改版则全量重跑而非拼接 |

## Failure handling

| symptom | what to do |
|-|-|
| `web.body_empty` | check the fetch output before translating — the page is all noise or the article was lost upstream |
| `web.paragraph_untranslated` | translate the paragraph with the matching segment id |
| `web.orphan_translation` | re-run cleaning and re-key the translation to the ids the current run produced |
| `web.empty_target` | translate the segment or drop the pair explicitly in the translation file |
| `web.untranslated_passthrough` | the paragraph was never translated — translate it |
| `web.number_dropped` | restore the digits/units, or confirm the rewrite is intentional (goes to uncertainty) |
| `web.term_gloss_mismatch` | apply the declared gloss, or fix the glossary entry |
| `web.term_conflict` | pick one gloss per term and align every segment to it |
| `web.target_not_zh` | set `--target-lang` to the actual target language, else translate |
| `web.translated_record_invalid` | make every translation record an object with id and target |
| `web.page_unreadable` | restore the named file as readable UTF-8 and re-run; the refusal names file and error |

## Verification

```bash
python scripts/bench_web.py   # 16 scenarios: extraction classes, locator round-trip,
                              # honest empty body, footnote cut, number/glossary/target
                              # audits, contract passthrough, exit-code contract
```

All 16 pass on this machine. The FP guards pin the behaviour that matters: locators
round-trip to real lines, an all-noise page reports an honest empty body, digits
kept in the translation raise no finding, a matched gloss stays silent, a circled
marker not at line start never cuts a body line, and a case contract echoes every
field into result.json.

## Requirements

Python 3.9+（3.14 实测）；纯标准库，无第三方依赖，无网络调用。

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **段落级来源锚定**：每段译文携带 page-line 定位与页面 URL/抓取时间/内容哈希，
   逐段可回查到原始页面位置——「读者能否凭交付物回到原始页面核对每一条内容」
   从口号变成可机械验证的字段。
   *边界*：定位以 fetch 步骤产出的文本行号为准，页面改版后需全量重跑。
   *证据形式*：`scripts/bench_web.py` locator_roundtrip + contract_passthrough 场景。
2. **术语表落地上文**：glossary 把「同一术语全文译法一致」从事后审计升级为逐段
   约束——源段出现词条而译名未落地即点名，译法冲突（同术语两种 gloss）逐条列出。
   *边界*：选词是人读判断，引擎保证声明了就执行。
   *证据形式*：glossary_enforced / glossary_match_clean / term_conflict 场景。
3. **漏译的四种伪装全部可检出**：未翻译（缺 id）、空译文、逐字回贴、非中文目标、
   数字丢失——每条都有 rule id 与接管动作，不靠人工逐段校对。
   *边界*：语义性错译不可机械检出，由 uncertainty 承接。
   *证据形式*：number_dropped / number_preserved / target_not_zh / clean_baseline 场景。
4. **契约直通与诚实拒绝**：case_id 与 output_contract 字段逐字段进 result.json
   （推导不出填 null 并在 limits 写明）；四类输入不可读时 exit 5 + undetermined
   result.json，无 traceback——失败可发现、可解释、可接管。
   *证据形式*：contract_passthrough / cli_exit_undetermined 场景 + 异常处置表。

## 生态贡献

- **使用说明**：本文件包含用途、适用条件、六步调用入口、任务路由表、输入输出、
  关键方法、异常处置表、限制和自查方法；按 Workflow 可独立完成一次「抓取文本 →
  干净正文 → 分段译文 → 可核验交付」全流程。
- **依赖与安装**：Python 3.9+（3.14 实测），纯标准库零依赖、零安装步骤、零网络
  调用；脚本可独立导入复用（cleanweb 的清洗规则库、webtranslate 的审计器）。
- **示例（标注为示例）**：`examples/page.txt` + `examples/translated.json` 是最小
  调用示例；本文档 worked example 是一次实跑的节选输出——均为示意，不冒充正式
  案例结果。
- **清洗规则库**：导航/广告/相关推荐/文献列表/脚注/页脚六类切剪模式全部有类别名
  且逐条留痕，他人可直接扩展 NOISE_PATTERNS 适配新站点——站点适配经验以「模式 +
  类别 + 留痕」形式沉淀。
- **术语表资源**：glossary 是纯 JSON（term → 译名或译名列表），可直接复用/合并成
  领域术语表；term_conflict 的输出生成新的术语表条目。
- **回归题集**：`scripts/bench_web.py` 16 场景是可独立复跑的回归门（含误报护栏），
  清洗与审计行为的任何改动都必须全过。
- **段落对齐结果格式**：segments/translated_segments 的 id + locator 结构是稳定
  的对齐交付格式，下游（笔记、综述、双栏对照阅读器）可直接消费。
- **维护**：改任何规则后必跑 bench（自查方法：16/16 + clean 基线零发现）；规则 id
  变更须同步本文档规则表（引擎与文档逐 id 对齐）。

引擎已实现该契约：case.json 顶层的可推导值与 output_contract 字面量直通最终
result.json，推导不出的填 null 并在 limits 写明；拒绝路径不回填契约，只写
undetermined result.json。

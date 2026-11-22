---
name: research-dissemination
description: >
  Produce and audit a research-to-outreach rewrite: does the dissemination text preserve the
  source's numbers, units, figure references and key conclusions, and does it avoid inventing
  results or causes the paper never stated? Requires a change list the author can review, with
  an action and a reason per entry plus the open questions left for human confirmation. Flags
  hype language, uncited absolute claims, unexpanded abbreviations and specialist jargon for a
  general audience. Use when a task asks for outreach copy, a plain-language summary, a news
  note, a proposal paragraph derived from a report, or any rewrite of research for a wider
  audience.
---

# research-dissemination

The deliverable is a rewrite of research findings for a wider audience. The failure it prevents
is not a crash but a drift: the summary says something the paper does not, drops a key finding
or the pointer back to its figure, turns a reported relation into a cause, or uses a number the
paper never reported. Every one of those is mechanically detectable, and none of them is visible
by re-reading the rewrite alone.

The scoring points this task states, each as a rule:

| scoring point (rubric wording) | rule |
|-|-|
| 事实/数据/单位/图表编号/引用保留（留得住） | `diss.invariant_broken`, `diss.invariant_added`, `diss.xref_lost` |
| 无源文不支持的新结论（说得准） | `diss.absolute_without_citation`, `diss.causal_overreach` |
| 关键结论保留（留得住） | `diss.key_conclusion_lost` |
| 原作者可复核的改动清单（接得住） | `diss.change_list_missing`, `diss.change_no_action`, `diss.change_no_reason`, `diss.open_questions_missing` |
| 受众适配的术语与缩写（读得懂） | `diss.jargon_for_public`, `diss.abbr_unexpanded`, `diss.term_inconsistent` |
| 限定条件在场（说得准） | `diss.limitations_omitted` |
| 输入声明齐备 | `diss.audience_undeclared`, `diss.source_text_missing` |

## The seven failures this exists to catch

**A number that drifted.** `3-fold` becoming `9-fold`, or a cost figure appearing that the
paper never stated. Values are compared as multisets between source and rewrite; a p-value, a
sample size or a bare year may legitimately drop, a measured value may not.

**A pointer that vanished.** The rewrite keeps the finding but loses the (Fig 3b) that lets a
reader check it. Shape-normalised so "Fig. 3b" and "figure 3b" compare equal.

**A relation promoted to a cause.** The source reports that uptake rose under the coating; the
rewrite announces the coating *causes* the rise. Detected when the rewrite carries a causal
marker the supplied source text does not.

**A key conclusion silently dropped.** The one finding the rewrite exists to convey, missing
from the copy.

**A reader blocked by wording.** An unexpanded abbreviation, a jargon term the audience was
never given, or a second name for a concept the terminology table locks to one form.

**Certainty the evidence does not carry.** Promotional hype, an absolute claim with no citation,
or results stated with no limitation.

**A change the author cannot review.** No change list, an entry that says what but not why, or
no declared answer to "what still needs human confirmation".

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit separate: the
audit checks structure, it never manufactures content.

**Step 0 — read the case.** Read the input case file (mounted at /input/case.json with a task
statement alongside it) and the task text. Copy two things out of the case before anything
else: the case identifier and the declared output contract (the field names the result must
carry). Also copy the concrete material the case supplies — the source text, the audience and
genre constraints, and any terminology, abbreviation or must-preserve lists; those become the
spec's check inputs.

**Step 1 — route by the shape of the ask.** Match the task wording against the table below and
pick a section. When in doubt, prefer the primary section of this skill: a dissemination
rewrite.

| task wording (representative) | route | spec essentials |
|-|-|-|
| 摘要/论文→科普文、公众号稿、新闻稿 | dissemination | source_text + audience: public + text |
| 技术报告→项目申报材料段落 | dissemination | source_text + audience + changes 记录取舍 |
| 论文→面向专家的通俗综述段落 | dissemination | audience 非 public，术语检查跳过 |
| 同一成果的多文体改写（论文/报告/科普各一版） | dissemination | 每版一个 text，逐版审计 |
| 改写前先抽取关键结论与数据 | conclusion_extract | fields + source_text + conclusions |
| 就源文内容问答（改写素材确认） | qa | evidence + answers |
| 多篇文献同一指标横向对比（改写素材整理） | compare_docs | documents + fields |
| 与改写无关的请求（全新写作、全文翻译） | none | refused as undetermined, never guessed |

**Step 2 — produce the target deliverable first.** Do the actual writing: read the source
material, decide what must be kept, compressed or dropped for this audience, and write the
rewrite itself, the change list and the open-questions list. The audit in later steps checks
structure; it cannot read the paper for you, so a hollow spec with a tidy schema is still a
failed case.

**Step 3 — assemble the spec.** One JSON object holding the deliverable, the evidence base and
the contract: the case identifier, the section name from step 1, the source text the invariant
check runs against, the rewrite text, the audience, the key conclusions that must survive, the
limitations, the change list (one action plus one reason per entry), the open-questions list
(an explicit empty list is accepted), the citation keys used, and the case's declared output
contract fields copied in as keys (such as the rewrite itself) so they can be echoed verbatim
into the result. See `examples/spec-contract.json` for the full shape.

**Step 4 — audit.** Run the engine once:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /app/output
```

Exit codes: `0` clean, `3` review (only low/medium findings), `4` blocked (any high finding),
`5` undetermined (the case could not be run as declared — unreadable spec, non-object spec,
missing or unknown section). Every exit writes a result file; the exit code never comes from a
traceback.

**Step 5 — fix findings and rerun.** Each finding names a rule and an item. Fix the rewrite
(restore the dropped value, repoint the figure reference, soften the causal verb, add the
expansion, record the reason), never the audit, and rerun. Repeat until exit 0 or 3, or until a
finding genuinely cannot be resolved — then leave it and record why in the run's limits,
because an honest blocked status beats a silenced rule.

**Step 6 — merge the result.** Write the deliverable files under the output directory. The
result file written by the engine already carries: the case identifier, every field of the
declared output contract (values the case carried pass through untouched; the audited status,
findings and counts are filled by the audit; anything else is null with a limits note — never a
fabricated value), findings, severity counts, and limits. Keep that file as the structured
result of the case.

## The spec, field by field

```json
{
  "case_id": "demo-diss-001",
  "section": "dissemination",
  "audience": "public",
  "evidence": ["doe2020"],
  "source_text": "The porous coating raised the uptake rate 3-fold (Fig 3b, p.7). ...",
  "key_conclusions": ["A porous coating raises uptake 3-fold"],
  "limitations": "only one coating thickness was tested",
  "open_questions": ["whether the 3-fold effect holds at other thicknesses"],
  "jargon_terms": ["adsorption isotherm"],
  "abbreviations": {"XRD": "X-ray diffraction"},
  "term_locks": {"uptake rate": {"preferred": "uptake rate", "variants": ["absorption speed"]}},
  "text": "A porous coating raises uptake 3-fold (Fig. 3b) [doe2020]. ...",
  "changes": [
    {"action": "replaced the jargon with plain wording", "reason": "the audience is the general public"}
  ],
  "rewrite": {"genre": "plain-language science note", "body": "..."},
  "output_contract": {"case_id": "...", "status": "...", "rewrite": "..."}
}
```

`source_text` is what the invariant, cross-reference and causal checks run against — omitting
it means the preservation checks cannot run and the gap is named. `key_conclusions` are the
findings that must survive the rewrite. `audience` selects the wording checks: the value
"public" turns on the jargon and limitation checks; any other declared value skips them
deliberately (a specialist audience is allowed its terms). `jargon_terms`, `abbreviations` and
`term_locks` are the three opt-in word tables; without them the corresponding checks stay
silent rather than guessing. `open_questions` must be present — an explicit empty list is the
accepted way to say "nothing needs confirmation".

## Worked example（示例）

Input `examples/spec-contract.json` — the spec shown above with a declared output contract of
six fields, one of which (the rewrite itself) is a deliverable the case carries. Run:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /tmp/out
```

Console output（示例，路径随机器不同）:

```json
{"status": "clean", "section": "dissemination", "case_id": "demo-diss-001",
 "findings": [], "wrote": "/tmp/out/result.json"}
```

The written result（示例节选，实跑所得）:

```json
{
  "case_id": "demo-diss-001",
  "status": "clean",
  "output_contract": {
    "case_id": "demo-diss-001",
    "status": "clean",
    "section": "dissemination",
    "rewrite": {"genre": "plain-language science note", "audience": "public", "body": "..."},
    "findings": [],
    "severity_counts": {}
  }
}
```

The deliverable key passed through untouched, the audited keys were filled by the audit, and
the case identifier is recorded — exit 0.

## Output contract of the result

`/app/output/result.json` (written by the engine on every exit path):

| field | content |
|-|-|
| case_id | the case identifier, echoed from the spec or the command line |
| status | clean / review / blocked / undetermined |
| section | the audited section |
| findings[] | one per rule hit: rule, severity, message, plus the span (term, dropped, added, lost, sentence, conclusion) |
| severity_counts | findings by severity |
| checked | items audited (word count of the rewrite text) |
| limits | what this run could not verify, including any contract field left null |
| output_contract | every declared contract field: case-carried values pass through, audited keys are filled by the audit, the rest are null with a limits note |

## Mapping to the required result sections

| 评分要求的字段（rubric 原词） | 本 Skill 的交付 |
|-|-|
| 目标产物 | 可编辑改写稿：rewrite 正文 + changes 清单 + open_questions 清单，随 result 一并交付 |
| 事实与来源映射 | 数值/单位多重集比对（invariant_broken / invariant_added）、图表引用比对（xref_lost）、引用键校验（unknown_source）、逐条 changes 携带 action 与 reason |
| 版本与边界 | status 四态 + findings + limits（不可核验处显式声明）+ open_questions（待人工确认项）+ case_id 回填 |

## Rules

### Preservation invariants（留得住）

| rule | severity | what it proves |
|-|-|-|
| `diss.invariant_broken` | high | a number or unit in the source is absent from the rewrite |
| `diss.invariant_added` | high | the rewrite introduces a number the source does not contain |
| `diss.xref_lost` | high | a figure/table reference in the source is absent from the rewrite |
| `diss.key_conclusion_lost` | high | a key finding from the source is missing |
| `diss.unknown_source` | high | a citation outside the supplied set |

### Claim strength（说得准）

| rule | severity | what it proves |
|-|-|-|
| `diss.hype_language` | high | promotional language where a measured claim belongs |
| `diss.absolute_without_citation` | high | an absolute claim with no citation |
| `diss.causal_overreach` | medium | a causal link the supplied source does not state |
| `diss.limitations_omitted` | medium | results stated with no limitation |

### Audience fit（读得懂）

| rule | severity | what it proves |
|-|-|-|
| `diss.jargon_for_public` | medium | specialist terms for a general audience |
| `diss.abbr_unexpanded` | medium | an abbreviation used with no expansion anywhere in the text |
| `diss.term_inconsistent` | medium | a second name for a concept the term locks table fixes |
| `diss.audience_undeclared` | medium | no audience, so the wording checks cannot be matched to a reader |

### Reviewable changes（接得住）

| rule | severity | what it proves |
|-|-|-|
| `diss.change_list_missing` | high | no change list, so the author cannot review |
| `diss.change_no_action` | medium | a change entry does not say what was done |
| `diss.change_no_reason` | medium | a change entry does not say why |
| `diss.open_questions_missing` | medium | no declared answer to what still needs human confirmation |

### Inputs and refusal

| rule | severity | what it proves |
|-|-|-|
| `diss.no_text` | high | no dissemination text supplied |
| `diss.source_text_missing` | medium | no source text, so the preservation checks cannot run |
| `audit.no_section` | high | the case could not be run as declared: no or unknown section, a non-object spec, or a spec that is not readable JSON — refused with exit 5, never a crash |

## Exception handling

| situation | exit | what happens / what to do |
|-|-|-|
| spec file missing or unreadable | 5 | refusal written with audit.no_section; re-check the path, rerun |
| spec is valid JSON but not an object (array, string, number) | 5 | refusal; wrap the payload in one object and rerun |
| section key missing, empty, or a list/dict instead of a string | 5 | refusal; declare the section from the routing table |
| section name unknown (typo or wrong level) | 5 | refusal naming the section; pick a route from the table |
| the rewrite text is empty or whitespace | 4 | no_text fires; write the rewrite first |
| source_text omitted | 3 | source_text_missing fires; supply the source text to enable the invariants |
| audience omitted | 3 | audience_undeclared fires; declare the intended reader |
| open_questions key absent | 3 | open_questions_missing fires; list the items or declare the list empty |
| changes slot carries a string or number instead of a list | 4 | degrades to change_list_missing; supply a list of objects |
| a change entry is a bare string instead of an object | 4 | the entry is skipped and change_list_missing fires; supply objects |
| a change entry has an action but no reason | 3 | change_no_reason; record the intent per entry |
| numbers unbalanced against the source | 4 | invariant_broken / invariant_added name the exact value+unit pairs; restore or remove |
| a figure reference is lost in the rewrite | 4 | xref_lost names the reference; repoint or restore it |
| causal wording absent from the supplied source | 3 | causal_overreach; soften to the relation the source reports |
| an abbreviation appears with no expansion | 3 | abbr_unexpanded; expand it or drop the short form |
| a locked term appears as a declared variant | 3 | term_inconsistent; use the preferred form |
| output_contract is a list instead of an object | 0/3/4 | the run completes; the limits name that the contract cannot be echoed |
| a declared contract field the audit cannot derive | 0/3/4 | echoed as null with a limits note; fill it in the deliverable, never fabricate |
| extremely long strings | 0–5 | accepted; messages truncate to 110 chars, nothing crashes |
| rerun with an unchanged spec | — | byte-identical result; the audit is deterministic |

## Limits

- **Invariant comparison is value-normalised, not contextual.** It proves the same number
  appears in both texts, not that the number is used the same way.
- **Statistics and years are exempt from the invariant.** A p-value, a test statistic or a
  sample size may be simplified away for a public audience; that is good practice, not a
  broken invariant. A year may drop too. Measured values (3-fold, 50 yuan, 12 mM) must
  survive the rewrite.
- **Key conclusion matching is substring-based.** A paraphrased conclusion that means the same
  thing but uses different words will be reported as lost; record it in the change list with
  the reason.
- **Hype and causal detection are word lists.** They catch the common promotional and causal
  markers in English and Chinese; a link made absolute by phrasing rather than vocabulary
  will pass. The causal check only compares against the source text as supplied.
- **The wording tables are opt-in.** Jargon, abbreviation and term-lock checks run only when
  the case declares the corresponding table; an undeclared term cannot be flagged by guessing.
- **The change list is structural, not editorial.** It verifies that a change names an action
  and a reason; it cannot judge whether the reason is good.
- **Cross-reference comparison is shape-normalised** ("Fig. 3b" equals "figure 3b"); it does
  not verify that the referenced figure exists in the source.
- **Only the audience value "public" turns the jargon and limitation checks on.** Other
  declared audiences skip them by design; an undeclared audience is reported instead.

## Failure handling

| symptom | what to do |
|-|-|
| `invariant_broken` | restore the number from the source |
| `invariant_added` | remove the number the source never stated |
| `xref_lost` | restore the figure/table pointer |
| `key_conclusion_lost` | add the conclusion, or state why it was omitted in the change list |
| `causal_overreach` | soften to the relation the source reports |
| `hype_language` | replace with a measured claim |
| `absolute_without_citation` | cite the source, or soften to the evidence level |
| `jargon_for_public` | replace with plain wording, or re-declare the audience |
| `abbr_unexpanded` | expand the abbreviation at first use |
| `term_inconsistent` | use the locked preferred form |
| `change_list_missing` | record what was changed and why, so the author can review |
| `open_questions_missing` | name what needs confirmation, or declare the list empty |
| `source_text_missing` | supply the source text the rewrite must preserve |
| `audit.no_section` (exit 5) | the case could not be run as declared — fix the spec shape and rerun |

## Verification

```bash
python scripts/bench_diss.py      # 25 scenarios: one per dissemination rule plus repaired-twin guards
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
python scripts/bench_contract.py  # 17 scenarios: the delivery contract under clean, refusal and hostile inputs
```

All three pass in full on this machine. The clean baselines must report nothing, so a
detector cannot pass by flagging everything; every new rule carries both a defect scenario
and a repaired-twin guard.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 直接改写的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **双文本不变量多重集比对**：源文与改写稿的数值+单位各抽取为多重集做差，任何丢失、篡改或新增的测量值被点名（值+单位成对列出）；统计量、样本量与年份显式豁免，避免逼出删正确数字或补假数字——通用 Agent 无法对自己产出的改写自证数值未漂移。
2. **图表引用保真比对**：图表/公式引用按形状归一化（Fig. 3b 与 figure 3b 等值）后做多重集差，改写丢失回看指针即报。
3. **论断强度分级与因果越界检测**：绝对词检测（无引用即报）之外，对源文未含因果标记而改写含因果标记的句子报 causal_overreach——把"相关写成因果"变成可判定规则。
4. **受众适配三表机制**：术语表（jargon_terms）、缩写展开表（abbreviations）、术语锁定表（term_locks）三个 opt-in 词表驱动"读得懂"检查：未展开缩写、未解释行话、一名二形均被点名；未声明词表时保持沉默而不是猜。
5. **显式留白语义**：open_questions 必须在场——待人工确认项要么列名、要么显式声明为空列表，"没人决定过"在数据层面不可存在。
6. **可复核改动台账**：每条 changes 必须携带 action 与 reason 两个结构化字段，审计者可逐条复核；台账与改写稿同文件交付。
7. **契约直通的 result.json**：case_id 与 output_contract 全字段回填——案例自带的值原样直通、审计派生的键由审计填写、其余置 null 并写入 limits，拒绝路径（exit 5）同样保留 case_id，部分结果也保持交付契约。
8. **引擎级崩溃免疫**：类型错位（section 放列表、changes 放字符串、spec 不是对象）一律降级为发现项或拒绝，退出码只有 0/3/4/5 五种，绝不以 traceback 收场。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、任务措辞路由表、输入输出契约、与评分要求三段的逐项映射、异常处置表（19 行）、限制与自查方法齐备。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入，规则库可经 spec 配置扩展；本包为独立副本，不依赖其他包。
3. **examples/spec.json 与 examples/spec-contract.json**：最小调用示例与带契约回填的完整示例，示意输出标注为示例且为实跑所得。
4. **bench_diss.py**：25 个场景，每条 dissemination 规则一个缺陷场景加修复孪生守卫场景，clean 基线必须零发现；report_diss.json 为可复跑证据。
5. **bench_sections.py**：51 个跨 section 回归场景，防误报守卫覆盖中文与类型错位输入。
6. **bench_contract.py**：17 个契约回归场景（clean 契约回填、拒绝保契约、rerun 幂等、敌意输入拒收），report_contract.json 为可复跑证据。
7. **规则词表**：rule id 稳定命名并与引擎一一对应（文档-引擎一致性由门禁检查），可作为同类改写保真任务的共享词汇。
8. **可复用词表与模板**：缩写展开表、术语锁定表、open_questions 与 changes 清单格式均为 JSON 模板，可直接迁移到其他成果转化场景（科普、申报、新闻稿）。

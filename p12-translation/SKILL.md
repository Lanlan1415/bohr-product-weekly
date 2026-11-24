---
name: bilingual-writing
description: >
  Translate a real academic source between Chinese and English, or produce editable bilingual
  prose/pairs, with a maintainable glossary and evidence that meaning was conserved. Deterministic
  checks cover numbers/units/magnitudes, formulae, numeric and author-year citations, DOI/arXiv/
  PubMed/Manubot identities, cross-language figure/table/equation references, aligned source
  spans and order, per-segment negation/limiters/modality, terminology, components and explicit
  ambiguity/naturalness review. Use for full or partial academic translation, bilingual writing,
  tracked translation and post-editing. The model writes idiomatic prose; scripts never claim that
  a regex can judge fluency or prove scientific equivalence.
---

# 学术翻译与双语写作：先完成译文，再证明什么没有改变

工作原则是“**意义守恒、术语可维护、双语可编辑、语言不硬译**”。模型读取真实材料并写出译文；脚本只做纪律明确的核对，不把术语表或逐字匹配当成翻译本身。

## Runtime：从 `/input/case.json` 到可编辑交付

### 1. 读取实际输入并确定语向、范围和文体

读取 `/input/case.json` 与 `/input/task.md`，保留 `case_id`、`output_contract`，并从实际 `source_text`/材料中读取事实。记录：源语/目标语、纯译文或双语对照、目标学科与读者、篇幅、图表/公式/脚注/参考文献是否纳入、已有术语表和文字版 PDF/OCR 状态。

不得根据文件名或错误的领域标签编数字；不得只翻译正文却宣称“整篇已完成”。缺文本、文本层依赖 OCR、段落损坏或不支持的语向必须进入 `limits`。

### 2. 先落一份真实的可编辑译文

在 `/app/work/deliverable.md` 或 `.json` 保存实际译文，随后逐步改进。选择：

| 任务 | spec 形态 | 可编辑产物 |
|-|-|-|
| 纯译文 | `output_mode: plain` + `source_text` + `target_text` | 完整目标语言稿 |
| 双语/逐段修改 | `bilingual` + `source_text` + `segments[]` | `{id,source,target}` 稳定定位的句段对 |
| 带修订的翻译 | `tracked` + 同上的句段对 | 可逐段对照的修改记录 |

**语言自然度不能由规则代替。** 先理解论点、条件与证据，再按目标语言学术习惯重组句法，避免把 each/may/only 等机械堆回原位。压缩冗余类比或口头腔时保留科学判断；不同措辞不意味着可改强弱。双语模式的 `source` 必须是原文连续片段，顺序不得交换；纯译文可以自然重组句法而不要求字面对齐。

### 3. 建立可维护的术语表

每个术语给出首选译法、源形、变体、缩写和**依据**（指定术语表、学科惯例、原教材等），未查明就写人工确认，不虚构“标准规定”。

```json
{
  "sorption": {
    "preferred": "吸附量",
    "source_form": "sorption",
    "variants": ["absorption"],
    "abbreviation": "",
    "basis": "case-provided terminology table / declared domain convention"
  }
}
```

检查包括：源概念在原文出现而锁定译法未到达目标、使用了非首选变体、不同概念争用同一首选译法、缺依据、错误字段类型。保留目标学科通用的英文缩写，不为了中文比例强行翻译。`variants` 必须是字符串数组，错误输入被显式发现并跳过，不能让审计崩溃。

### 4. 明确高风险守恒与歧义回查

对公式、数字、引用、否定、限定语、条件、范围、上下位词和 Attribution 做回查。需要声明回译/回查时写 `backcheck[]`，它表示哪些高风险段确实被走过，不能把仅有一个 id 当作“语义已被证明”。

```json
{
  "backcheck": [{"segment": "p1", "verdict": "match"}],
  "ambiguities": [
    {"segment": "p2", "issue": "unless 修饰哪个分句",
     "status": "resolved", "resolution": "目标中条件范围已与原作者确认"}
  ],
  "naturalness_review": {
    "audience": "researchers", "register": "academic",
    "reviewer": "bilingual editor",
    "literal_spans": [{"segment": "p3", "status": "open"}]
  }
}
```

`ambiguities[].status` 可为 `resolved`（必须有 resolution）或 `open/pending/human_review`（进入 `boundary.human_review_and_gaps`）。一词多义、否定范围、代词归属、限定语强度和可能改变风格的硬译片段都在这里显式登记，不用“看起来通顺”掩盖不确定。

### 5. 运行审计并修复真问题

正式入口接受扁平 case 或 `{case_id,output_contract,spec:{...}}`：

```bash
S=/skills/weekly-skill/scripts
python -I "$S/writeaudit.py" --case /input/case.json --out /app/output
```

如果 case 的科学材料或用户约束与 spec 字段不同，先按真实内容装配 `/app/work/spec.json`，老入口保持兼容：

```bash
python -I "$S/writeaudit.py" --spec /app/work/spec.json --out /app/output
```

最小 spec（双语）：

```json
{
  "case_id": "demo-bilingual",
  "section": "translation", "output_mode": "bilingual",
  "source_lang": "en", "target_lang": "zh",
  "source_text": "Only 3 samples may improve at 25 °C.",
  "segments": [
    {"id": "p1", "source": "Only 3 samples may improve at 25 °C.",
     "target": "仅 3 个样本在 25 °C 下可能有所改善。"}
  ],
  "glossary": {},
  "output_contract": {
    "case_id": "identifier", "status": "state", "deliverable": "editable target",
    "target_text": "complete target", "evidence_map": "source map", "boundary": "limits"
  },
  "limits": []
}
```

退出码：`0 clean / 3 review / 4 blocked / 5 undetermined`。每一返回路径写 `result.json`；已能解析的 case 在拒绝路径也保留 identifier 和 contract。错误 section、非对象 JSON、缺文件、术语表异常是结构化发现或拒绝，而不是 traceback。

### 6. 复核输出，不调低规则来“过关”

- 数字/公式/引用丢失：回原句恢复，不能只增加一条解释来替代真正的目标文本。
- `segment_source_mismatch/order/duplicate`：修正段对来源和原顺序；重复相同原文自然出现多次不会误报。
- `segment_limiter/negation/hedge`：回到具体分句检查条件范围，尊重原文“仅/至少/至多/除非/约/可能”的证据边界。
- `glossary`：用有依据的首选译法或登记待定，不删除概念来消除发现。
- 语义自然但仍有歧义：保留译文并明确 `open/human_review`，不伪造已解决。

最终 `/app/output` 中保存实际译文或对照文件（agent 第 2 步落盘并复制）及 `result.json`。交付格式遵循 case，不能用一段校验报告代替译文。

## 不变量与规则

### 数值、公式与引用身份

| 能力 | 实际机制 / 规则 |
|-|-|
| 数字、单位、量级 | `_quantity_pairs` 多重集双向比较；单位跨语言归一、逗号分组不去数字；错误 `invariant_broken/added` |
| 万/亿/million/billion | `conversions[]` 的首尾系数必须与实际 diff 对应，且实际数量相等；factor 只能是源/目标量级，错误为 `conversion_arithmetic_mismatch/factor_mismatch/malformed`，无记录为 `number_conversion_unexplained` |
| 数学表达 | `$...$`、`\\[...\\]`、equation/align/gather/multline/eqnarray 规范化后双向 diff；`formula_missing/added` |
| 传统引用 | 数字、作者—年份、inline et al. 原位置保留；匹配错误进入 `invariant_*` |
| 持久引用 | DOI、arXiv、PubMed/PMID/PMC、ISBN/ISSN、Manubot `@prefix:accession`、括号内 alias；`citation_identity_missing/added` |
| 图表/公式/章节引用 | 中英文形态归一，例如 `Fig. 1` 与 `图 1`，`Eq./公式/式` 只比编号身份，不强留英文 |
| 正文之外组件 | `components{figures,tables,equations,footnotes,references}` 声明 marker 必须到目标；`component_untranslated` |

`evidence_map` 中 `formula` 与 `persistent_citation` 两条目均带源/目标计数和 match/dropped/added；目标全文字段 `target_text` 按合同回填，不因大而置空。

### 双语对齐与语义边界

| 规则 | 含义 |
|-|-|
| `segment_unpaired/id_duplicate/id_absent/malformed` | 一侧缺失、id 不可定位或条目不合法 |
| `segment_coverage_low` | 配对文本覆盖不足；段合并/拆分本身不惩罚 |
| `segment_source_mismatch` | 声称对齐的 source 不是 `source_text` 的连续片段 |
| `segment_order_changed` | 段对在源文中的位置不再单调，顺序变了 |
| `segment_duplicate_source` | 消费同一源段次数超过源文真实出现次数；重复出现的真实段落有 clean 守卫 |
| `segment_limiter_changed` | only/at least/at most/if/unless/approximately 等组在单个段对中失落或新增 |
| `segment_negation_changed` + 文档级 `negation_changed` | 段内和全文的否定操作符双重核查；不再把 `除非` 的“非”或 `未来` 的“未”当否定 |
| `segment_hedge_changed` + 文档级 `hedge_strength_changed` | 认知情态与约数分别检查，普通 `show` 不等于 `demonstrate` |
| `backcheck_missing/orphaned`、`ambiguity_*` | 回查缺高风险段、孤儿记录、未解决或未指明的歧义 |

否定/限定语仍是**确定性候选检查**，不是完整语义解析。作者必须回查具体从句，不能因为总数相同就断言辖域完全一样。

## 输入、输出与可靠性

### 关键 spec 字段

- `source_lang/target_lang`、`source_text/target_text`、`output_mode`、`segments`；
- `glossary`、`conversions`、`components`、`backcheck`、`ambiguities`、`naturalness_review`；
- `source_format/text_layer`、`ocr`、`limits`；
- `case_id` 和 `output_contract` 原样传入。

所有附加审计（glossary/ambiguity/naturalness 等）均声明才生效，避免给未声明的材料硬造条目。

### result.json 三段结构与合同

- **目标产物**：`deliverable`，完整 target 或逐段 pairs；
- **事实与来源映射**：`evidence_map`，数字、公式、引用、xref、术语、组件、回查；
- **版本与边界**：`boundary`、`findings`、`limits`、`uncertainty`，含 human review 和 OCR/材料缺口。

`case_id` 及 `output_contract` 全部字段同时直接落在根对象和 `output_contract` 汇总中。已提供的实际值直接传递；嵌套键保形；真正无法推导的字段为 `null`（数组形状 `[]`）并给出具体路径的 limits。`status/findings` 等审计字段只能采用本次真实审计值。

### 异常处理

| 输入/异常 | 行为 |
|-|-|
| 缺失/坏 JSON/非对象 case | exit 5 + `audit.no_section` + result.json；未知 case_id 明确为 null |
| section 缺失/非字符串/未知 | exit 5；已解析的 id 与完整 contract 仍保留 |
| 空源/空目标 | `missing_side` high，不伪造审计通过 |
| 错误语向标量、畸形段/glossary | 合理降级为发现，native traceback 不作为交付 |
| 重复运行同输入 | 确定性规则与稳定 JSON 输出；专项 bench 检查字节一致 |
| 扫描 PDF 无文本层 | 须有 OCR record 或 text-layer uncertainty，不能当作已核实文本 |
| U+FFFD | `replacement_char_present` high，先修解码再信任比对 |

## Manubot 机制的真实落地

参考 `manubot/rootstock` 的 `@prefix:accession`、Pandoc 引用簇及其 `content/` 输入与 `output/` 生成物分离工作流，但没有把链接当实现：

1. 本地按 DOI/arXiv/PubMed/Manubot key 抽取沟通两侧的**同一引用身份**；
2. `@doi:10...` 与 DOI resolver URL 可等价，且 DOI 在 key 内不会被重复计数；
3. 同括号内的多个身份保持多重集，不只检查“至少还有一个引用”；
4. 两种语言都用同一份 spec/术语与引用台账生成输出，引用证据不人工另抄一次；
5. alias 仅在括号引用簇中识别，避免把 email/社媒柄当文献。

不同 prefix 不擅自合并（DOI 与 PubMed 可在这套体系中是两个引用键），且不联网获取元数据，所以不对作者、题名或 DOI 真实性作未核验保证。

公开案例：
- https://github.com/manubot/rootstock
- https://raw.githubusercontent.com/manubot/rootstock/main/USAGE.md

## Requirements

Python **3.10+**，纯标准库，本机 3.14 实测；无模型调用、无网络、无第三方依赖。真实译文由调用 Agent 完成。如果 Python 不可用，将失败写入 limits，不能声称运行过 audit。

## Limits

- 多重集发现“数字相同”，并不证明数字在错误语境未被误用；须按 evidence_map 回查段号。
- 否定/情态/限定语使用候选词和局部存在性，不能理解全部辖域；自然语言回查不可省。
- 不做词法语法的逐字硬约束，也不给流畅度伪造自动分。`naturalness_review` 是人工证据，不宣称客观文风得分。
- 持久标识符一致不等于引用足以支持论断，不验证 DOI 元数据、参考文献条目真实性或科学因果关系。
- 长度带是防止大段遗漏的启发式；它不是评价简洁或学术质量的标准。

## Optional verification

```bash
python -I -B scripts/bench_translate.py       # 35
python -I -B scripts/bench_writing.py         # 20
python -I -B scripts/bench_bilingual_deep.py  # 37
```

第三个套件运行真实的中文对标译文、符号/引用敌意变体和 CLI smoke，并覆盖嵌套契约、错误 section、冷导入、幂等与拒绝路径。所有材料均为合成 fixture，不是平台正式答案。

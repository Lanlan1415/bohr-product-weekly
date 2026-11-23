# 编辑类型词表（学术语言润色 · v2）

编辑记录（edits.jsonl）与 change_log 的 `type` 字段一律从下表取值，
不得自由造词；一条编辑只标一个主类型（组合修改拆成多条记录）。

## L1 语法级

| type 值 | 说明 | 守恒注意 |
|---|---|---|
| grammar.agreement | 主谓一致、指示代词单复数 | — |
| grammar.tense | 时态/语态统一 | 实验叙述过去时，结论现在时 |
| grammar.article | 冠词缺失/误用 | — |
| grammar.preposition | 介词搭配 | 固定搭配以词典级用法为准 |
| grammar.number | 名词单复数 | 不碰数值本身 |
| grammar.punctuation | 标点（含全半角） | 中文全角、英文半角，不混用 |
| grammar.dangling | 悬垂修饰/逻辑主语 | 改主语时不得改变行为主体 |

## L2 句式级

| type 值 | 说明 | 守恒注意 |
|---|---|---|
| syntax.split | 长句切分 | 条件状语、限定从句必须保留（拆丢=改坏） |
| syntax.merge | 碎句合并 | 合并后限定词计数不变 |
| syntax.order | 语序调整（状语归位等） | 不改变信息分配 |
| syntax.denomialize | 冗余名词化动词化 | 主语必须来自原文 |

## L3 风格级

| type 值 | 说明 | 守恒注意 |
|---|---|---|
| style.register | 语域对齐（去口语/宣传/绝对化） | 限定词强度不变（见 qualifier_lexicon.md） |
| style.person_voice | 人称与语态按目标文体 | 图表编号守恒 |
| terminology.unify | 术语统一为批准写法 | 只许"未批准→批准"方向；批准写法计数不减 |
| style.chinglish | 中式英语结构清理 | 结构级改法，非换词掩盖 |

## L4 逻辑连贯级

| type 值 | 说明 | 守恒注意 |
|---|---|---|
| cohesion.transition | 衔接词显化 | 只显化原文已有的逻辑关系 |
| cohesion.reference | 指代明确化 | 先行词必须来自上文，不臆造 |

## 元类型（与级别无关）

| type 值 | 说明 |
|---|---|
| intentional.exception | 有意守恒例外（必须配 allow_conservation_break + reason 与依据出处） |
| alternative.proposed | 【备选】条目：≥2 候选 + 倾向 + 理由，不硬改 |

# 文体规范：目标语域与语言细则（学术语言润色）

## 1. 目标文体判定

从 case.json 与 task.md 提取目标文体；材料未声明时默认"期刊论文英语、保守润色"并在 uncertainty 声明。判定后全文执行同一套语域，不中途换档。

## 2. 各文体语域要点

| 文体 | 语域要点 | 禁忌 |
|---|---|---|
| 期刊论文（英） | 客观、克制；方法结果多用过去时与被动/主动混排；结论限定词精确 | groundbreaking / perfect / proves；夸张副词；第二人称 |
| 学位论文（中/英） | 层次分明、定义先行；同一术语贯穿全篇；"本文/本研究"自称 | 章节间术语漂移；口语化过渡（"那么接下来"） |
| 基金申请书（中） | 突出科学问题与价值；肯定但不吹嘘；"有望/可期"级限定 | "国际领先""填补空白"堆砌；把预期成果写成已得结论 |
| 审稿回复 | 逐点对应、礼貌致谢、修改位置明确（"已按建议在第 X 节修改"） | 争辩式语气；无定位的泛泛回应 |
| 英文摘要 | 背景-方法-结果-结论紧凑；数值与正文一致；时态：方法结果过去时、结论现在时 | 摘要出现正文没有的数值或结论 |

## 3. 中文行文规范

- 标点全角：，。；：""（）——句内不用半角逗号句号；
- 术语首次出现给全称，需要时括注英文与缩写：固态电解质界面膜（solid electrolyte interphase, SEI）；
- 数字与单位：按 GB/T 或来稿惯例，全文统一（如"3.2×10⁻⁴ S/cm"与"3.2e-4 S/cm"不混用——**但替换来稿写法属有意改动，须入 change_log**）；
- 避免翻译腔："……的进行""被……所"等结构优先改为主动、动词化表达。

## 4. 中式英语清理清单（L2/L3 常用）

| 直译腔 | 改法 |
|---|---|
| The conductivity has a great improvement. | The conductivity is greatly improved. / The conductivity increases by …（数值守恒，只能用原文已有的数） |
| We can see from Figure 1 that… | As shown in Figure 1, … |
| It is well known that… | 删除或给出处（不给出处就删，不得替作者编造引用） |
| With the development of…（开篇套话） | 按期刊文体删减或具体化；删减须入 change_log |
| play an important role in | 具体化为动词（conducts, stabilizes…），仅限原文信息足以支撑时 |
| Obviously, … | 删 Obviously（绝对化口吻） |

## 5. 术语表（terms.txt）格式与维护

- 每行一个**批准写法**；`#` 开头为注释；同概念的未批准写法不写入文件，改法记在 change_log（"garnet oxide → LLZO，依 terms.txt"）；
- 缩写规则：首次出现 = 全称（缩写），此后用缩写；摘要与正文的"首次"各自独立计算（期刊惯例）；
- 大小写与连字符按批准写法（如 all-solid-state / solid-state 不混用）；
- 术语表来自材料则原样遵守；自建术语表在交付时一并放入 /app/work 并在 evidence_map 登记。

## 6. 修改记录（change_log）书写风格

- 条目格式：`C编号 | L级别 | 位置（章节/段） | 原文 | 改后 | 类型 | 理由`；【备选】条目格式见 method_rules §6；
- 理由写"判定依据"不写感想："主语单数"✓，"这样更通顺"✗；
- 每条修改可在润色稿中定位；批量同类修改（如全篇逗号全半角）可并成一条并注明"共 N 处"。

## 7. result.json 风格

- status 诚实：部分章节未完成即 partial 并列明；
- uncertainty 每条：`事项 → 影响 → 建议人工确认方式`；
- change_log 顶层写流程级记录（步骤、脚本运行结果），逐句修改在 change_log.md 文件里，两边不混。

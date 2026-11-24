# 基础 Agent 典型失败模式与对策（阅读14：Nanopublication）

以基础 Agent（不加载本 Skill）在论文→RDF 任务上的高频失败为依据，
每条给出本 Skill 的对策及落点文件。

## F1 一段一断言

**现象**：把摘要或结论整段塞进一个"断言"字段，或一条三元组的客体是整句话；
"拆得细"直接零分，下游也无法复用。
**对策**：粒度判据与单一可判性检验（method_rules.md §1）+ assertion_table.md
强制"一 id 一命题"；清单 A4 用断言数量下限做体检。

## F2 条件限定丢失

**现象**："催化剂过电位 178 mV"——丢掉"0.5 M H2SO4、三电极、10 mA/cm2"，
断言离开条件后变成假话。
**对策**：条件吸收规则（method_rules.md §1）；模板在 assertion 图中示范
"数值三元组 + 条件三元组"成对出现（templates/nanopub_template.trig）。

## F3 证据虚挂或笼统出处

**现象**：引文与断言不对应，或只写"来源：本文"；评审无法"对得上"。
**对策**：最小充分证据判据（method_rules.md §2）+ evidence_map.md 每条
"引文 ≤30 字 + 锚点 + 证据类型"三件套。

## F4 RDF 语法裸奔

**现象**：缺句点、前缀未声明、`;` 结尾悬空、assertion 图是空的、四图缺一；
文件下游解析器直接报错。
**对策**：nanopub_check.py 把词法/配平/前缀/句点/四图/assertion 非空做成
机器检查，第 5 步每生成一条即校验；语法细则见 style_guide.md。

## F5 编造标识符与元数据

**现象**：材料没有 DOI/ORCID 时编造一个形如真的标识符——科学数据造假红线。
**对策**：规则"找不到即标未报告、RDF 中整条省略"（style_guide.md §标识符）；
清单 C1/C2 专项勾选。

## F6 置信度通胀

**现象**：所有断言一视同仁，作者观点句与表格数值同等置信；"无法判断被写成事实"。
**对策**：三档受控置信度 + 依据（method_rules.md §4）；证据不足的断言强制
降级或移出（SKILL.md 第 4 步）。

## F7 词表漂移与方向混乱

**现象**：同一关系三种拼写（hasAuthor/writtenBy/creator 混用）、"A 优于 B"
主客颠倒；下游 SPARQL 查询漏召回。
**对策**：一语义一拼写规则 + 词表登记区（assertion_table.md 模板含词表区）；
方向检查列入清单 B/D。

## F8 三部结构残缺

**现象**：只导 assertion，没有 provenance/pubInfo；或 provenance 不挂来源。
"追得回"失分。
**对策**：模板四图齐全为默认骨架；nanopub_check.py N1/N2 结构检查；
selfcheck.py 粗检三部字样。

## F9 冲突静默二选一

**现象**：正文与图表数值不一致时悄悄挑一个写，另一处证据消失。
**对策**：冲突处置规则（method_rules.md §2）：两断言并存互相备注，或都标
"材料冲突"不发；写入 uncertainty。

## F10 result.json 契约字段缺失

**现象**：凭印象写字段名，output_contract 声明的字段被改写或漏掉。
**对策**：第 0 步抄录契约字段；selfcheck.py 用 case.json 实测比对，缺即 FAIL。

## F11 无证据断言照常发布（v2）

**现象**：找不到支撑片段的断言仍写进 TriG，provenance 只有一句空泛来源，
甚至整个 provenance 图缺失；"对得上/追得回"全失，且把不可核验内容包装成事实。
**对策**：无证据断言标"证据不足"+ low 或移出交付（SKILL.md 第 4 步）；
nanopub_check.py N1/N2 对缺 provenance 的 nanopub 直接 FAIL，
N4 对缺 hasEvidenceAnchor 给 WARN；负路径用例见 examples/negative_cases.md。

## F12 断言无适用边界、证据形态不区分；阶段失败零交付（v2）

**现象**："某材料性能优异"类断言不说在什么条件下成立，下游误用到边界之外；
实验测量值与作者推测混为一谈；中途失败就什么都不交。
**对策**：v2 追加"条件范围"与"证据形式"两个保守字段
（method_rules.md §1.1/§2.1，四档受控词表）；nanopub_check.py N6 WARN 提醒；
交付韧性：失败阶段写入 result.json 的 skipped_reason，已通过校验的 nanopub
照常交付（SKILL.md §7）。

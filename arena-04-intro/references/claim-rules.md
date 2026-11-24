# claim-rules.md — 空白推导链与断言分级（“说得实”）

目标：研究空白**必须由已引文献的缺口推出**（gap-chain），每个断言要么有证据、
要么显式标注为作者判断；不允许“近年来受到广泛关注，但现有方法存在不足”式的无据空转。

## 1. 断言分级（写作与 result.json 全程使用）

| 级别 | evidence_or_author_judgment | 依据 | 写作处理 |
|---|---|---|---|
| 证据级 | `evidence` | 已引文献的逐字原文（quote ≤50 字 + ref + locator） | 可直接写成文献结论，引用落在具体论断后 |
| 判断级 | `author_judgment` | 作者推断/综合，无单一原文支撑 | 成稿中避免绝对化措辞（“从未/全面落后”→“尚未见到/在我们材料中未见”）；**必须登记 human_review_items** |
| 不确定 | — | 材料不足无法判断 | 不写；相关位置留待作者补充，进 uncertainty |

红线：
- 判断级内容**不得**写成“某某等指出…”（虚构文献观点）；可写“据上述工作推断…”；
- quote 必须逐字（anchor_check / gap_chain_check 回查），改写过的句子不许当 quote；
- 编造引用一经 coverage_check 检出（CITATION_NOT_IN_LIBRARY）必须删除，不得保留。

## 2. 空白推导链（gap-chain）协议

链条 ≥3 环，逐环可核验：

```
step 1  kind=literature_gap  文献 i 的局限      evidence: {ref, quote 逐字}
step 2  kind=literature_gap  文献 j 的局限      evidence: {ref, quote 逐字}
step 3  kind=cross_gap       交汇缺口           evidence 或 author_judgment（判断级必须进人工复核）
step 4  kind=this_work       本文切入点+如何填补 basis 含“本文…”
```

规则：
1. **每环有 basis**：一句话写明该步为什么成立；文献局限环的 basis 必须落到具体条目（作者/年份）；
2. **文献环必须带证据**：evidence.quote 与 evidence.ref 逐字回查（gap_chain_check.py）；
3. **交汇缺口（cross_gap）**：至少由 2 篇已引文献的局限指向同一维度导出（共同限制 /
   未覆盖场景 / 结论冲突三型之一）；若跨文献组合是推断而非原文，标 author_judgment；
4. **链尾指向本文**：kind=this_work，basis 写明本文机制如何对应缺口（“本文以 X 替代 Y 填补 Z”）；
5. **缺口 ≠ 无人做过**：空白指“在本文设定下尚无满足条件的方案”，不是“没人研究过该领域”；
   推导链中体现条件限定（低算力、少标注、非平稳……来自底稿的问题定义）。

三类合法的交汇缺口（写明属于哪型）：
- **共同限制型**：组 A 的 limitation 与组 B 的 limitation 落在同一维度（如都依赖大样本）；
- **未覆盖场景型**：各组 conditions 的交集为空（无方案同时满足底稿要求的场景组合）；
- **结论冲突型**：已引文献对同一问题结论矛盾，冲突本身即空白（需引用双方原文）。

## 3. 贡献对齐协议（“对得上”）

- 每条贡献 claim 必须 `mapped_to` 底稿中真实存在的方法模块/图表/实验结果；
- 图表号写成“Figure N / Table N / 图 N / 表 N / §N”，脚本会在底稿中回查
  （CONTRIBUTION_ARTIFACT_MISSING = 底稿没有该图表号，成稿禁止出现）；
- 方法名用底稿原名（tokens 机制），不得在贡献里引入底稿没有的新方法名/新指标；
- 有 claim 无映射 → status=unaligned：从成稿贡献列表移除或降级措辞，并留 human_review_items；
- 底稿结果不直接支持但作者希望保留的贡献 → status=author_judgment，成稿中用
  “初步结果提示/有望”等限定语，登记人工复核；
- 数值贡献（如“提升 6.2 个百分点”）只允许照抄底稿数字，禁止四舍五入外的任何加工。

## 4. 引用落点规则

- 每个他人结论后立即跟引用（键/编号/作者-年份），不允许整段综述后补一个笼统引用；
- 引用必须对应其结论（转述 A 文结论不能引 B 文）；coverage_check 的 author-year 匹配
  即为粗粒度防线，逐条对应由模型在 groups[].papers[].anchor 中绑定；
- 背景段的事实性陈述（领域规模、成本数据）要么引自文献库，要么删除，不得编造数字。

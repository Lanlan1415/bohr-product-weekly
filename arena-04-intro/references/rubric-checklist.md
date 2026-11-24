# rubric-checklist.md — 质量自查清单（四性 + 五评分维度对照）

## 1. 四性判定（题面核心关注点 → 本 Skill 的对应机制）

### 立得住（研究背景指向真实脉络与具体未解决问题）
- [ ] 背景段的每个领域性论断后面有引用或底稿依据，没有“近年来受到广泛关注/发展迅速”式空转铺垫；
- [ ] 背景收在一个**具体**的未解决问题上（该问题来自 gap 链第 1–2 环的文献局限）；
- [ ] “为什么是现在”有材料依据（底稿动机/约束/数据），而非泛泛的重要性叙述。

### 分得清（分组比较而非逐篇摘要拼接）
- [ ] 每组 basis 写明分组维度（grouping-rules.md §1 四型之一）；
- [ ] 每篇三列齐全：conclusion（带定量）/ conditions / limitation（区分原文承认 vs 作者判断）；
- [ ] 对照 grouping-rules.md §4 的四个“拼接信号”逐条自检，均不命中；
- [ ] 每组末尾有组间取舍 + 与本文的关系；
- [ ] comparison_matrix.csv 由 introcrun.py 从 nearest_works 四维差异生成，逐格有 prior/this_work/difference；
- [ ] 最相近工作的每个已核实维度有原文证据，scope 同时写既有局限与本文适用边界。

### 说得实（空白由已引文献缺口推出）
- [ ] gap_chain ≥3 环且 gap_chain_check.py 无 error（STEP_BASIS_MISSING /
      LITERATURE_STEP_NO_EVIDENCE / LAST_STEP_NOT_THIS_WORK 均为 0）；
- [ ] evidence 环的 quote 逐字命中（EVIDENCE_QUOTE_NOT_FOUND = 0）；
- [ ] 交汇缺口写明类型（共同限制 / 未覆盖场景 / 结论冲突）且由 ≥2 篇已引文献导出；
- [ ] 所有 author_judgment 环节都出现在 human_review_items；
- [ ] 成稿空白段与 gap_chain 一一对应，无链条之外的“额外空白”论断。

### 对得上（贡献与实际方法/图表/结果一一对应）
- [ ] 每条贡献有 mapped_to，coverage_check 无 CONTRIBUTION_ARTIFACT_MISSING；
- [ ] 贡献中的方法名/指标名在底稿中原样存在（tokens 检查通过）；
- [ ] 数值贡献与底稿数字逐字一致；
- [ ] 无底稿中不存在的图表号出现在成稿任何位置。

## 2. 与评测五维度的对应（Skill 自身）

| 维度 | 本 Skill 的对应物 |
|---|---|
| 实际效果 | 可编辑成品 intro_related_work.md（四节承接）+ 最相近工作四维 CSV + result.json 的来源/空白/贡献/范围台账 |
| 使用增益 | 确定性脚本拦截裸 Agent 高频失败：编造引用（coverage）、坏锚点（anchor）、断链/无据空白（gap_chain）、底稿外图表号；USAGE §增益对照给出逐项对照说明 |
| 创新增益 | 三列逐字段 quote+locator + 四维最相近工作差异 + 空白证据/作者判断分流 + 贡献 artifact/scope 对齐；语义蕴含仍留给作者复核 |
| 可靠体验 | 触发词覆盖“写引言/整理相关工作/补引用/核对贡献”；同输入同输出（脚本确定性）；异常分支见 SKILL.md §异常与降级 |
| 生态贡献 | USAGE 完整（依赖/示例/适用范围/限制）；scripts+fixtures 可复用为引用核验题集；references 四份规则文档可单独复用 |

## 3. 提交前最终核对（每次运行完成后逐项打勾）

- [ ] /app/output/result.json：含 case_id、status、findings、verification、uncertainty、
      human_review_items、deliverables、limits、output_contract_fields 与全部合同字段；
- [ ] /app/output/intro_related_work.md：可编辑成品，四部分齐全且引用真实出现；
- [ ] /app/output/comparison_matrix.csv：由同一 spec 的 nearest_works 四维生成；
- [ ] 对不可核验全文、作者判断和最相近工作 provisional 状态已在 uncertainty/
      human_review_items 写明，未静默升级为 verified；
- [ ] 所有作者判断环节在成稿中有限定语且已登记人工复核；
- [ ] 成稿语言与案例要求一致（中/英），格式符合案例约束。

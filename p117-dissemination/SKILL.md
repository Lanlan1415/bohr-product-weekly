---
name: research-dissemination
description: >
  Rewrite research for a declared reader and, when applicable, produce an evidence-bounded
  technology-transfer document. Preserves scientific facts, numbers, units, figure references,
  citations, limitations and change rationale. An opt-in transfer_profile additionally checks pain
  points, TRL and validation scope, IP, application scenarios, sourced market/competitor evidence,
  commercial assumptions, implementation stages, stop conditions, risks and baseline-relative
  quantified value. Use for public summaries, project material derived from a report, research
  commercialization drafts and technology pitch documents. Never invents TRL, IP rights, market
  size or returns, and explicitly separates research facts from business hypotheses.
---

# 科研成果转化写作：可读、可证、可继续编辑、能决策

本 Skill 不仅问“稿子好读吗”，还问“哪些来自论文，哪些来自外部证据，哪些只是商业假设；作者和转化负责人能否逐项复核”。模型先完成真实改写，脚本再检查保真、受众、变更记录和（声明时的）转化决策要素。

## 1. 读取真实材料并选路由

读取 `/input/case.json` 与 `/input/task.md`，保留 `case_id`、`output_contract`。抽取实际源文、目标读者、体裁、篇幅、必须保留的结论/数字/引用/图表、受众已有知识和未发表/涉密限制。

| 任务 | 路由和必填内容 |
|-|-|
| 论文→科普/新闻/公众号/普通综述 | `section: dissemination`，不使用商业 profile，保留事实/numeric/xref 和 change list |
| 报告→项目申报材料、产学研对接、技术推介 | `dissemination` + **显式** `transfer_profile`，同时满足科研保真和商业决策结构 |
| 只有实验数据，先抽取关键结论 | 先使用相应提取工具，再进入写作；不得将空白材料写成转化稿 |
| 没源文，只有“写一份某技术产业化方案” | 说明科研事实不可核验，提出待提供材料清单；不得编技术性能和市场数据 |

**不得因为读者是产业界就删除实验室限定条件。** 成功建立中试愿景，不等于论文已经验证量产；“未发现相关”“初步结果”“单一材料”不能被改写成确定性效果。

## 2. 先写真实目标稿，保存 early partial

在 `/app/work/deliverable.md` 写出完整目标稿、改动清单和开放问题，然后逐步完善。普通改写的每条 change 需有 `action` 和 `reason`；未确认项列 `open_questions`，没有则显式 `[]`。

成果推介稿至少按下列叙事完成实际文字，而非只有一张空表：

1. **痛点与对象**：谁遇到什么实际问题，为什么值得做；
2. **技术是什么、成熟到哪一步**：实验条件、TRL/未知状态、验证规模与负面/边界证据；
3. **证据与权属**：哪些实测结果支持应用场景，专利/许可/保密状态能否确认；
4. **应用与市场**：具体使用场景、外部客户/市场证据、可比替代方案、未知市场信息；
5. **量化价值与假设**：基线、目标、单位、时间窗、计算方式；未证实就写假设，不能写成结果；
6. **实施与风控**：分阶段负责人、里程碑、资源、验收阈值和停止条件；
7. **待确认**：尚需第三方验证、法务核查、客户访谈或其他前置条件。

普通科普稿不需要这些商业字段，也不会触发商业规则。

## 3. 建立两套证据账本

### A. 科研事实与外部证据

- `scientific_facts[]`：研究论断必须有 `claim_type: research_fact`、`claim` 和能在 `source_text` 找到的 `source_excerpt`；推荐加 `source_locator`。摘要用 NFKC/空白归一匹配，不忠实的小摘要不会被当成科学事实。
- `market.evidence[]`：外部客户/市场论断必须有 `claim`、`source_excerpt`、`locator`，状态是 `external_evidence`（或真实科研事实）。论断中的数字必须能在自己的摘要中找到，不能只有“某报告说”。
- `validation[]`：给出环境、样本/规模、基准和结果，`evidence_refs` 必须指向已登记的科研/外部证据 ID。
- 论文实测、外部访谈/报告、计算推导的营销估算不能混写为同一“研究证明”。

### B. 商业假设与开放问题

- `commercial_assumptions[]`：假设必须有 `claim`、`basis`、`uncertainty`，`claim_type` 是 `commercial_assumption`。没有证据并不禁止提出方案，但必须标明依据和证伪条件。
- `quantified_value[]`：可以有外部事实或假设，但非 unknown 时必须给出 `metric/baseline/target/unit/time_horizon/method`；事实还要给可查验 `evidence_refs`，假设还要给 basis 和 uncertainty。
- 显式 `evidence_refs` 不能指向不存在的来源，假设和竞品同样不能有“幽灵引用”。
- TRL/IP/量化价值可使用 `unknown`，须写 scope/notes 等当前边界；会返回 review 和人工确认项，不会包装成 clean fact。

## 4. 可选 `transfer_profile` 的完整结构

以下字段名就是真实 CLI 检查的结构。复制结构，不复制示例事实。

```json
{
  "case_id": "demo-transfer",
  "section": "dissemination",
  "audience": "industry pilot team",
  "source_text": "In the lab, uptake increased 3-fold from 2 mg/g to 6 mg/g (Fig 3b) [doe2020].",
  "text": "完整、可编辑、面向具体用户的转化稿正文……包括实验条件和商业估算的边界。",
  "evidence": ["doe2020"],
  "key_conclusions": ["源文中真正需要保留的结论"],
  "limitations": "only lab conditions; production behavior unverified",
  "open_questions": ["是否有第三方中试验证"],
  "changes": [{"action": "区分实验测量与估算", "reason": "避免把假设写成论文结论"}],
  "transfer_profile": {
    "scientific_facts": [
      {"id": "lab01", "claim": "实验室吸附量提升 3 倍",
       "claim_type": "research_fact", "source_excerpt": "increased 3-fold from 2 mg/g to 6 mg/g",
       "source_locator": "paper Fig.3b"}
    ],
    "pain_points": [
      {"id": "pain1", "problem": "缺少放大验证路径", "user": "中试团队",
       "claim_type": "commercial_assumption", "basis": "由实验室局限提出的待访谈假设",
       "uncertainty": "是否愿意付费还需客户访谈"}
    ],
    "technology_maturity": {"level": "TRL4", "status": "research_fact",
      "scope": "实验室、12 个样本、单一涂层厚度", "evidence_refs": ["lab01"]},
    "intellectual_property": [
      {"type": "patent_application", "status": "unknown",
       "notes": "权属/registry record 尚需法务确认"}
    ],
    "validation": [
      {"id": "val01", "environment": "实验室、单一厚度", "sample_or_scale": "12 samples",
       "baseline": "2 mg/g", "result": "6 mg/g (Fig.3b)", "evidence_refs": ["lab01"]}
    ],
    "applications": [
      {"id": "app01", "scenario": "同类材料的中试吸附处理", "user": "中试团队",
       "conditions": "同种材料和厚度，须先中试复测", "painpoint_refs": ["pain1"]}
    ],
    "market": {
      "evidence": [
        {"id": "mkt01", "claim": "外部访谈中 2 家中试用户各有 20 万元年度试验预算",
         "status": "external_evidence", "source_excerpt": "两家中试用户各有 20 万元年度试验预算",
         "locator": "真实访谈记录编号、页码或数据库定位"}
      ],
      "competitors": [
        {"name": "现有工艺/替代方案", "comparison_axis": "相同条件下的吸附性能与成本",
         "evidence_refs": ["lab01"]}
      ],
      "unknowns": ["目标区域购买转化率、竞争对手报价尚无材料"]
    },
    "commercial_assumptions": [
      {"id": "a-value", "claim": "估算成本下降，但不是论文测量",
       "status": "commercial_assumption", "basis": "1000 × 0.80 = 800 元",
       "uncertainty": "规模、良率和报价变化会改变结果"}
    ],
    "roadmap": [
      {"stage": "中试设计与复测", "owner": "技术负责人",
       "milestone": "完成双方确认口径的中试和独立复测",
       "resources": "装置、试样、分析人员、第三方检测",
       "success_gate": "达到预设复测阈值并完成权属确认",
       "stop_condition": "条件不兼容、复测不达标或权属不清则停止/回退"}
    ],
    "risks": [
      {"risk": "实验室结果不能放大", "likelihood": "中高", "impact": "高",
       "mitigation": "分阶段中试和独立复测", "trigger": "关键指标低于方案阈值", "owner": "技术负责人"}
    ],
    "quantified_value": [
      {"id": "qv01", "metric": "单批处理成本", "baseline": "1000 元", "target": "800 元",
       "unit": "元/批", "time_horizon": "2 年", "method": "1000 × 0.80 = 800 元",
       "status": "commercial_assumption", "basis": "估算，不承诺实现",
       "uncertainty": "规模和良率仍需中试确认", "evidence_refs": []}
    ]
  },
  "output_contract": {
    "case_id": "identifier", "status": "state", "rewrite": "actual draft",
    "target_text": "actual draft", "deliverable": "artifact", "evidence_map": "sources",
    "technology_maturity": "TRL and scope", "intellectual_property": "IP",
    "validation": "validation", "market": "market", "roadmap": "route", "risks": "risks",
    "quantified_value": "value", "boundary": "limits"
  },
  "limits": []
}
```

`unknown` 的 TRL 应写 `{level:null,status:"unknown",scope:"实际验证范围",notes:"为什么未知",evidence_refs:[...]}`；无依据填 9 或写“国际领先”会失败。IP 使用真实登记/合同信息时才写授予/申请状态，否则保留 unknown 而非猜编号。

## 5. 运行真实审计并修复

正式入口：

```bash
S=/skills/weekly-skill/scripts
python -I -B "$S/secrun.py" --case /input/case.json --out /app/output
```

可在 case 根级包含 `transfer_profile` 或将 `spec` 嵌套。若需另行组装，旧接口保持兼容：

```bash
python -I -B "$S/secrun.py" --spec /app/work/spec.json --out /app/output
```

先修复高严重级别事实问题，再修复 medium 的结构和可维护性问题，然后重新运行。不能删除原文限定或外部证据来消除发现，不能弄一个假 report/identifier 充当支持。

退出码仍为：`0 clean / 3 review / 4 blocked / 5 undetermined`。所有返回路径写 `result.json`；可解析 case 的 identifier 和完整合同在拒绝路径也保留。

## 6. 复核最终交付

- **目标产物**：`deliverable.text` 是完整稿件；`target_text` 与 `rewrite` 按合同回填，不是审计报告代替正文。
- **事实与来源映射**：`evidence_map` + `transfer_assessment` 分科研事实、外部证据和假设；profile 中同名 `technology_maturity/intellectual_property/validation/market/roadmap/risks/quantified_value` 可独立回填输出字段。
- **版本与边界**：`boundary.open_questions`、`boundary.business_and_commercialization_review`、`open_questions`、`limitations`、`changes` 和 `limits` 说明还能否进入下一决策。

`case_id` 和 `output_contract` 每个字段都直接出现在根对象，另有 `output_contract` 汇总对象。已提供值原样传递，profile 子字段按同名映射；嵌套结构保留；未知字段置 `null`/[] 并在 limits 写具体路径。

## 规则总览

### 原有科研改写保真（不声明 profile 时也运行）

| 方向 | 规则/检查 |
|-|-|
| 留得住 | `diss.invariant_broken/added` 数值+单位；`xref_lost` 图表/公式引用；`key_conclusion_lost` 关键结论 |
| 说得准 | `causal_overreach` 相关写因果；`hype_language` 宣传腔；`absolute_without_citation` 无引用绝对断言；`unknown_source` 虚空引用 |
| 读得懂 | 声明的 jargon/term_locks/abbreviations、受众未声明、公共读者缺 limitation |
| 接得住 | `change_list_missing/no_action/no_reason`、`open_questions_missing` |
| 运行边界 | `no_text/source_text_missing/audit.no_section`；统计量/样本量/年份的公共改写豁免按原逻辑保留 |

普通改写的数字用多重集。声明 profile 后，基线→目标和其计算式允许合理重复，按“数值+单位类型”查是否被源文/外部证据/显式假设支持；完全未登记的新数字仍会触发 `diss.invariant_added`，不能借重复陈述绕过。

### 商业转化新增规则（只在 `transfer_profile` 存在时）

| 决策要素 | 主要失败发现 |
|-|-|
| 痛点/用户 | `pain_point_missing/incomplete`，没有依据的引用需补证据或转标假设 |
| 事实/假设分界 | `scientific_facts_missing`、`research_fact_not_in_source/not_verifiable`、`fact_classification_invalid`、`assumption_basis/uncertainty_missing` |
| 技术成熟度 | `maturity_missing/unjustified/scope_missing`，TRL 必须 1–9 或显式 unknown |
| 知识产权 | `ip_missing/incomplete/evidence_missing`，owner/reference 不足不能声称权利；unknown 进人工确认 |
| 验证 | `validation_missing/incomplete/validation_evidence_missing`，环境/样本/基准/结果必须齐备 |
| 场景 | `application_missing/incomplete/unbound`，必须回接痛点并写必要条件 |
| 市场/竞品 | `market_evidence_missing`、`external_evidence_unlocated/mismatch`、`competitor_missing/incomplete` |
| 路线 | `roadmap_missing/incomplete`：负责人、里程碑、资源、验收和停止条件 |
| 风险 | `risk_missing/incomplete`：风险、概率/影响、缓解、触发和 owner |
| 量化价值 | `value_missing/incomplete`、`value_arithmetic_mismatch`；状态 unknown 有记录但不伪造数字 |
| 诚实待定 | `unresolved_business_boundary` medium；缺市场信息写 `market.unknowns` 和人工问题，不猜 |

### 简单算术不是装饰性执行

`1000 × 0.80 = 800 元` 会通过受限数字表达式计算；也会核对左端是否 baseline、结果是否 target。`1000 × 0.70 = 800 元` 触发 `value_arithmetic_mismatch`。不支持自由定义模型或任意 Python eval；变量公式和复杂单位经济模型必须人工复核。

## 结构参考如何落实

参考公开 `VSR2025/Commercialization-Playbook` 的三个决策层，而不是照抄一句“做商业化”：

1. **能否产品化** → 痛点/场景 + 成熟度 + 验证范围 + IP 权属；
2. **是否值得做** → 市场/竞品 + 量化价值 + 商业假设与外部来源分开；
3. **如何继续** → 里程碑、负责人、资源、风险、成功/停止阈值和未决事项。

其仓库高层观点“可能没有市场、团队资源会被分散、竞争优势可能暴露”已落实为显式 `market.unknowns`、资源/stop condition 和风险台账，不把作者没有给出的 TRL/市场宣称当可靠证据。

- https://github.com/VSR2025/Commercialization-Playbook

## Requirements 与 Limits

Python **3.10+**，纯标准库，本机 3.14 实测；无网络和第三方包，不进行市场/专利数据库检索。

- excerpt/locator/ID 一致保证**可追溯性**，不自动证明外部文件真实、访谈无偏或检测可重复；需要时列出独立复核任务。
- TRL 只做声明和证据范围审查，不给出官方成熟度认证；IP 审计不提供 FTO/法律意见。
- 计算仅覆盖简单数字表达式，复杂成本/TAM/NPV/渗透率模型须附来源和人工审核；不生成无来源市场规模。
- `key_conclusions` 仍是明确字符串匹配，同义改写需调整台账并说明，不得硬塞术语制造“保留”。
- 对涉密/未发表材料，保留权限和披露边界；不要为了推介完整度公开实验秘密。
- 普通科研保真词表是候选诊断，不替代作者语义核验。普通 `show` 不能被任意加强为商业化“已证明”。

## Optional verification

```bash
python -I -B scripts/bench_diss.py       # 25
python -I -B scripts/bench_sections.py   # 51
python -I -B scripts/bench_contract.py   # 17
python -I -B scripts/bench_commercial.py # 35
```

商业套件使用一份完整合成 fixture 及其敌意变体，运行干净的转化交付并检查嵌套 profile 合同、证据与 orphan 引用、算术、unknown、拒绝路径、冷导入和字节级幂等。所有材料均为合成示例，不是平台正式案例答案。

# 最小调用示例（示意，非正式案例结果）

> 本示例仅说明接口与流程；输入为虚构文件名，输出为示意片段，**不是**任何正式案例的结果。

## 输入

```
/input/
  case.json        # {"case_id": "...", "output_contract": {...}}
  task.md          # 要求：全文翻译为中文，输出双语对照
  paper.pdf        # 一篇有文字层的科研论文
```

## 调用序列（绝对路径，正斜杠）

```bash
# 步骤 0：解析契约
cat /input/case.json   # 提取 case_id 与 output_contract，写 /app/work/contract_notes.md，
                       # 并立刻落盘最小 /app/output/result.json（status: partial）

# 步骤 1：材料清点
python3 /skills/weekly-skill/scripts/inventory.py \
    --input /input --output /app/work/materials_register.md

# 步骤 2-4：pdftotext 取文字层 → 语义分段赋 [P###] → 锁定 glossary.tsv → 分批续译
# （人工 + 模型完成，产出 /app/work/source_paras.md、glossary.tsv、translation_draft.md）

# 步骤 5：机器核验
python3 /skills/weekly-skill/scripts/term_consistency.py \
    --glossary /app/work/glossary.tsv \
    --translation /app/work/translation_draft.md \
    --source /app/work/source_paras.md \
    --report /app/work/term_report.md

python3 /skills/weekly-skill/scripts/align_check.py \
    --source /app/work/source_paras.md \
    --translation /app/work/translation_draft.md \
    --report /app/work/align_report.md

# 步骤 5b：句级锚定审计（v2：来源清点 + 对齐审计）
python3 /skills/weekly-skill/scripts/sentence_anchor.py \
    --anchors /app/work/sentence_anchors.md \
    --source /app/work/source_paras.md \
    --report /app/work/anchor_report.md

# 步骤 6b：写 result.json 前的契约前置校验（v2）
python3 /skills/weekly-skill/scripts/contract_check.py \
    --case /input/case.json --result /app/output/result.json

# 步骤 7：交付自查
python3 /skills/weekly-skill/scripts/selfcheck.py \
    --output /app/output --case /input/case.json

# 任意时刻中断/预算耗尽：固化诚实部分（v2）
python3 /skills/weekly-skill/scripts/finalize.py \
    --work /app/work --output /app/output --case /input/case.json \
    --skipped "步骤4: 预算耗尽，P040-P042 未译"
```

## 示意输出（截取）

glossary.tsv：

```
band gap = 带隙 ; 能隙, 禁带宽度
hydrothermal synthesis = 水热合成 ; 水热法合成
XRD = X 射线衍射
```

term_consistency.py 控制台：

```
[PASS] band gap = 带隙（首选 6 次）
[FAIL] catalyst = 催化剂（首选 4 次） —— 禁用变体「触媒」出现于行 57, 103
[term_consistency] 共 2 条术语：PASS 1，WARN 0，FAIL 1
```

> 注（v3）：脚本报 FAIL 时的正确做法是修复一轮后复查一次，修不完的记入 uncertainty/skipped_reason 后照常交付；脚本退出码仅供定位问题，不作为交付门禁。

align_check.py 控制台：

```
[align_check] 原文段号 42 个，译文段号 42 个
[PASS] 段号一一对应、顺序一致、编号连续
[align_check] FAIL 0，WARN 0
```

bilingual_translation.md 片段：

```
[P007] The band gap of sample Z1 was determined to be 3.37 eV.
译文：样品 Z1 的带隙测定为 3.37 eV。
```

sentence_anchors.md 片段（v2，句级锚定）：

```
[P007-S01] [p.3] The band gap of sample Z1 was determined to be 3.37 eV. || 样品 Z1 的带隙测定为 3.37 eV。
```

> **验证与限制声明（v2）**：以上输出为示意；本技能脚本仅在本地用全合成 fixture
> 验证过（见 examples/negative_case.md 与 scripts/selftest.py）。评测平台的
> 3 个隐藏案例与基础 Agent 对照未在本地运行，本示例不声称任何平台分数。

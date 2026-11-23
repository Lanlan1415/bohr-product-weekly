# 最小调用示例（示意，非正式案例结果）

> 本示例仅说明接口与流程；输入为虚构文件名，输出为示意片段，**不是**任何正式案例的结果。

## 输入

```
/input/
  case.json        # {"case_id": "...", "output_contract": {...}}
  task.md
  paper.pdf        # 一篇双栏科研论文
```

## 调用序列（绝对路径，正斜杠）

```bash
# 步骤 0：解析契约
cat /input/case.json   # 提取 case_id 与 output_contract，写 /app/work/contract_notes.md，
                       # 并立刻落盘最小 /app/output/result.json（status: partial）

# 步骤 1：材料清点
python3 /skills/weekly-skill/scripts/inventory.py \
    --input /input --output /app/work/materials_register.md

# 步骤 2：结构清点与异常分级
python3 /skills/weekly-skill/scripts/pdf_survey.py \
    --pdf /input/paper.pdf --output /app/work/survey

# 步骤 3-6：按 SKILL.md 主流程人工+工具完成解析、组装交付

# 步骤 6b：写 result.json 前的契约前置校验（v2）
python3 /skills/weekly-skill/scripts/contract_check.py \
    --case /input/case.json --result /app/output/result.json

# 步骤 7：交付自查
python3 /skills/weekly-skill/scripts/selfcheck.py \
    --output /app/output --case /input/case.json

# 任意时刻中断/预算耗尽：固化诚实部分（v2）
python3 /skills/weekly-skill/scripts/finalize.py \
    --work /app/work --output /app/output --case /input/case.json \
    --skipped "步骤3: OCR 排队超时"
```

## 示意输出（截取）

inventory.py 控制台：

```
[inventory] 已登记 3 个文件 -> /app/work/materials_register.md
  S1  case.json  JSON 数据  1.2 KB  -
  S2  task.md  Markdown 文本  3.4 KB  -
  S3  paper.pdf  PDF 文档  2.1 MB  有文字层（前 3 页约 5318 字符）
```

pdf_survey.py 控制台：

```
[pdf_survey] /input/paper.pdf
  页数(启发式): 12 | 图片对象: 9 | 字体对象: 14 | 加密: 否
  文字层: 有 | 章节标题: 11 个 | 书签: 0 条
  异常[minor] MULTI_COLUMN: 约 41% 文本行含大间隙：疑似多栏版面，必须按栏切分并验证栏序…
```

parsed_document.md 片段：

```
[B014] [p.3] [col.R] [S3] [conf:high]
The catalyst was characterised by X-ray diffraction (XRD) …
```

selfcheck.py 控制台：

```
[PASS] 输出目录非空 —— 4 个条目
[PASS] 主产物存在且非空 —— parsed_document.md
…
[selfcheck] PASS 18，WARN 0，FAIL 0（WARN 不影响退出码）
```

> 注（v3）：脚本退出码仅供定位问题，不作为交付门禁——即便 selfcheck 报 FAIL，也是修一轮、复查一次后把剩余缺口记入 uncertainty/skipped_reason，照常交付。

> **验证与限制声明（v2）**：以上输出为示意；本技能脚本仅在本地用全合成 fixture
> 验证过（见 examples/negative_case.md 与 scripts/selftest.py）。评测平台的
> 3 个隐藏案例与基础 Agent 对照未在本地运行，本示例不声称任何平台分数。

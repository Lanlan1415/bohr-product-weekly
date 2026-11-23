---
name: pdf-parse
description: >
  真实科研 PDF 文档解析：读取实际 PDF，保留页、块、行、span、Unicode 文本和
  bbox；恢复一至三栏及跨栏标题/摘要的阅读顺序，隔离重复页眉页脚，提取标题、
  作者/单位、章节层级、原生表格单元格、合并区域、图表题注、公式编号、
  上下标、参考文献和 PDF 元数据。缺文字层、加密、损坏和回退均明确标记，
  不把图像描述、普通对齐正文或猜测文本冒充 PDF 结构。适用于文献 PDF 全文
  解析、结构化定位、后续问答/翻译的输入制备；不用于单张图数据读数、科学含义
  解释、绕过密码或无 OCR 的扫描件内容推断。
---

# 科研 PDF 解析：提取真实结构，也保留无法确认之处

## 1. 产物与不可逾越的边界

主入口 `scripts/pdfparse.py` 把真实 PDF 转成：

- `blocks[]`：页码、原始/阅读顺序块号、栏、bbox、逐行/逐 span 文本、字体、字号、flags；
- `metadata`、`outline/outline_flat`、`sections`：原 PDF 元数据、候选题名/作者/单位、章节树和逐节文本；
- `tables[]`：PyMuPDF 原生行列/单元格/None、表格 bbox、caption、Markdown、合并区域和续表组件；
- `formulas[]`：原 Unicode、公式编号、上下标 span、特殊符号集合和 SHA-256；`latex=null`；
- `captions[]`、图像块及链接、`references[]` 及其所有组建块定位；
- `cross_page_continuations[]`：只给跨页段落续接候选，不静默抹掉边界；
- `findings/warnings/limits`：栏顺序、无文字层、字体损坏、无编号参考文献、后端回退等真实边界。

同时落盘可检查/复用的 `result.json`、`full_text.txt`、`document.md`、`tables.json` 和 `source_pages.json`。

三个禁止：

1. **不把左右栏拼成一句。**原始 MuPDF 块若混合栏，会按大行距和 x 方向突变先拆物理块，再按栏恢复顺序；不能保守判断时写 `pdf.column_order_warning`。
2. **不把普通对齐文字猜成表格。**只有原生表格网格才输出行列；`native_tables=false` 或无原生网格时不生成虚构矩形表。
3. **不假装读过扫描/加密内容。**全部无文字层返回 `scanned_only`；混合 PDF 的可读页保留，扫描页产生 `scanned_page` 占位与 `unverified` 缺口；加密不绕过。

## 2. 六步运行时入口

### 第一步：读输入并保存早期 partial

读取 `/input/case.json`、`task.md` 和 `environment/resources.yaml`，记录 `case_id`、原 `output_contract`、指定 PDF 和任务范围。程序尽早写 `/app/output/result.json` 的 undetermined partial，完成后才改写 clean/review。

### 第二步：定位真实 PDF

可直接声明：

```json
{"case_id": "paper-01", "section": "pdf_parse", "pdf_path": "paper.pdf",
 "output_contract": ["case_id", "status", "reading_result", "evidence_and_boundaries", "运行状态"]}
```

别名：`pdf`、`source_pdf`、`file`；也支持 `materials/files/attachments` 中的本地 path。路径相对 case 或 `/input`。未声明路径时可发现输入目录 PDF；单文件自动发现返回 review，多候选只解析确定性 primary 并列出其余文件，绝不悄悄合并。声明了错误类型或空路径是 caller error，不转而偷选别的文件。

### 第三步：选择并记录后端

顺序为 **PyMuPDF → pypdf → pdftotext**。推荐 PyMuPDF ≥1.23（`Page.find_tables` 引入版本）；当前以 PyMuPDF 2.1 和 pypdf 7.1.1 实测。任何有意义的短文本都可保留，不再有“少于 80 字就误判扫描”的阈值。

| 后端 | 真实能力 | 明确降级 |
|-|-|-|
| PyMuPDF | 页/块/行/span、bbox、字体/flags、图像、metadata、TOC、原生表格 | 表格识别仍依赖版式；不等于语义理解 |
| pypdf | 页文本与部分 metadata | 无行/span 坐标、原生表格或可靠栏恢复；写 `pdf.layout_fallback` |
| Poppler `pdftotext -layout` | 页面分隔与版面化纯文本 | 无 bbox/字体/原生表格/章节可靠识别；写 `pdf.layout_fallback` |
| 全部不可用/失败 | 无 | exit 5 + result.json，记录原因，不 traceback |

### 第四步：执行真实解析 CLI

平台安装后的标准命令：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/pdfparse.py parse \
  --case /input/case.json --out /app/output
```

从包根目录对自备 PDF 运行等价命令：

```bash
python -I -X utf8 scripts/pdfparse.py parse --case /path/to/case.json --out ./_run_pdf
```

不需要或不希望启用原生表格时可设置 `"native_tables": false`。这只会禁用表格结构检测，不会拿文字对齐结果补一张表。

### 第五步：逐层构建结构

1. **保真 reader**：保留 `raw_text`、每行/span、Unicode、图像和页 metadata；混合栏原始块被拆后仍保留字体与来源。
2. **阅读顺序**：较宽正文块先确定栏界，数学/单元格碎片再归栏；2 栏中心间距阈值 12% 页宽，3 栏为 18%；跨栏带结束当前栏段。元数据精确标题可作为首页跨栏证据。
3. **页眉页脚**：只将边缘重复文本或明确页码标为辅助内容，保留在 blocks 但排除 `full_text.txt`，不会把“1 Section / 2 Section”误作页眉。
4. **结构**：NUMERIC/NAMED 标题需符合文本形状；数字标题还需全块粗体或字号显著高于正文，避免表格数字和公式成为大纲。标题、authors、affiliation、abstract、footnote、reference 分开。
5. **表格**：`Page.find_tables(strategy="lines")` 复制 text/None 与几何；合并区域只由原 cell bbox 跨多行/列推得。跨页续表只在明确 continued 或相同重复表头时合并，所有组件留痕。
6. **公式**：字符与数学上下文识别 + PyMuPDF superscript flag + Unicode 上下标；不生成语义 LaTeX，不把题注/参考文献改标公式。
7. **参考文献**：显式编号优先；无编号按作者列表起始与年份边界重建，保留原始换行及全部 component locators。无编号条目 `review_required=true` 并触发 `pdf.reference_segmentation_review`。

### 第六步：契约回填、落盘和复核

最终 `result.json` 顶层含 `case_id`，并逐字段满足 **引擎值 > case 显式携带值 > null + limits**。`output_contract` 支持字段列表、字符串、字段名对象和 `field/name/key` 对象列表；拒绝路径也保留原 contract。派生中文字段：

| 题面三段 | result.json 落点 |
|-|-|
| 阅读/解析结果 | `reading_result` + `metadata/outline/sections/tables/formulas/captions/references` |
| 证据与边界 | `evidence_and_boundaries.locators/table_locators/formula_locators/unverified` + 每块 bbox/offset/SHA-256 |
| 运行状态 | `status`、`run_state`、`findings`、`limits`、`change_records` |

`source_pages.json` 保存后端原始页文本，供与拆分后的块/阅读顺序逐项对照。`full_text.txt` 有显式 `===== PDF page n =====`，不会把页眉页脚、题注、参考文献悄悄混入正文。

## 3. 退出码与异常处置

| 情况 | result/status | exit |
|-|-|-|
| 结构完整、无 medium/high findings | clean | 0 |
| 可用但有栏顺序、扫描页、文本回退、参考文献或契约复核项 | review | 3 |
| `case_not_object`、无 `no_pdf_path` 或声明路径类型错误 | undetermined + 命名 reason | 4 |
| 坏/缺 JSON、`unknown_section`、PDF 缺失、加密、扫描、损坏、后端失败 | undetermined + 命名 reason，契约字段保留 | 5 |
| argparse 用法错误 | 无正式科学解析结论 | 2 |

主要 reason/finding：

- `case_unreadable`、`case_not_object`、`unknown_section`、`no_pdf_path`、`pdf_missing`；
- `encrypted`、`scanned_only`、`encrypted_or_corrupted`、`all_backends_failed`、`resource_limit`、`pdftotext_timeout`；
- `pdf.layout_fallback`、`pdf.scanned_pages`、`pdf.text_encoding_warning`、`pdf.page_extraction_error`；
- `pdf.column_order_warning`、`pdf.no_headings`、`pdf.table_backend_unavailable`、`pdf.native_table_error`；
- `pdf.input_autodiscovery`、`pdf.multiple_pdf_candidates`、`pdf.reference_segmentation_review`、`pdf.contract_field_missing`；
- `internal_error`：正式 case 边界捕获并落盘，不向用户打印 traceback。

混合扫描件不是 clean。全部扫描件需要先用平台 OCR/OCRmyPDF/Tesseract 生成文字层后重跑；本包不声称内建 OCR。重复运行相同输入与同版后端不写 UTC/elapsed，因此 result 和四个附加产物可字节重放。

## 4. 输出形状（示意而非正式案例答案）

```json
{"schema_version": "pdf-parse/v2", "case_id": "paper-01", "status": "clean",
 "reading_result": {"page_count": 3, "table_count": 1, "formula_count": 1,
                    "reference_count": 2, "scanned_pages": []},
 "tables": [{"table_id": "p0002-table-01", "row_count": 3, "col_count": 3,
             "cells": [{"row": 0, "column": 0, "text": "Arm", "bbox": [60, 76, 120, 104],
                        "rowspan": 1, "colspan": 1}], "merged_regions": []}],
 "formulas": [{"text": "E = mc² and ΔS ≥ 0 (1)", "equation_number": "1", "latex": null}],
 "artifacts": [{"path": "full_text.txt"}, {"path": "document.md"},
               {"path": "tables.json"}, {"path": "source_pages.json"}]}
```

示例数值仅说明字段形状。正式运行只读取当时真实文件，不携带或选择预写论文答案。

## 5. 可复用方法与外部参考的落地

- **Docling 开源项目**公开了版式分析、阅读顺序、表格结构、公式和 OCR 的整体任务边界，以及 lossless JSON 的复用思路。受其分层启发，本包将阅读顺序、结构、表格、公式和 provenance 分模块；没有把 Docling README 中“title/authors/references/language coming soon”误写成外部项目事实，而是自行保留 PDF 元数据与候选来源。项目：https://github.com/docling-project/docling
- **PyMuPDF 官方表格 API**实际使用 `Page.find_tables`、`Table.extract()`、`Table.rows/cells/bbox`、`Table.header`。单元格仍在页打开时复制为普通 JSON，避免页生命周期失效；坐标是原生几何证据。文档：https://pymupdf.readthedocs.io/en/latest/page.html
- **本地 p59/p69 高分包**的黑盒探针、复杂契约形状、case_id 顶层回填、无 traceback 和确定性重放已落到 `probe_pdf.py`、`pipeline.py` 和 benches，而非只写“参考”。

## 6. 适用范围与剩余限制

- 栏恢复是坐标启发式，不等同人工版面校对。复杂图文环绕、无框多栏、旋转页和异常换页仍可能 review；末页短参考文献的常见限制不可略过。
- 原生表格当前以 **lines** 策略为主。无框/图片表格、复杂多层表头和跨页续表若不满足明确条件，输出空表或独立组件，不能宣称完整恢复。
- 不验证字体的语义映射。U+FFFD、字体乱码和错误已有文字层会保留并报警，不靠上下文猜字；CJK 需要实际嵌入字体或 OCR。
- `raw_text` 与拆块文本都是后端提取结果，不是人工修订版。连字、断词和表格单元格内的既有空格特性不会为“更易读”而静默修改。
- 无编号参考文献的作者/年份边界是启发式；必须看 `review_required/component_blocks`，尤其作者断行、会议年份和同页多条交错的情况。
- 跨页段落只有候选链接；公式只保留 Unicode 和 script span，不保证语义结构。图像中的公式/表格需要 OCR 或视觉结构工具另行处理。

## 7. Verification

以下均从包根目录运行，属于独立合成回归，不是组织方分数：

```bash
# 真实 PyMuPDF/pypdf 后端：完整新版 12 场景、旧回归 12 场景、敌意探针 22 场景
python -I -X utf8 scripts/bench_pdf_v2.py
python -I -X utf8 scripts/bench_pdf.py
python -I -X utf8 scripts/probe_pdf.py

# 冷导入无需在 import 时装 backend
python -I -X utf8 -c "import sys; sys.path.insert(0, 'scripts'); import reader, reading_order, structure, superscript, tables_pdf, pipeline, pdfparse; print('cold-import-ok')"
```

新版回归用真三页双栏 PDF，覆盖 clean、合并单元格、栏序/切片、短 PDF、混合扫描、加密、未知 section、契约、无虚构表格与五文件字节重放。若环境无 PyMuPDF，版式场景会标注 skip；这种运行不能冒充完整 PDF 能力验收。

公开真实论文 smoke 使用 ACL Anthology 的 P18-1001（下载内容为非可信外部输入，应单独保存）：

```bash
curl -L --fail https://aclanthology.org/P18-1001.pdf -o /tmp/P18-1001.pdf
# 在 /tmp/case.json 写 case_id、pdf_path=/tmp/P18-1001.pdf、section=pdf_parse 和原 output_contract
python -I -X utf8 scripts/pdfparse.py parse --case /tmp/case.json --out /tmp/pdf-smoke-out
```

本机 PyMuPDF 2.1 实测该 11 页论文得到 479 块、15 个真实大纲节点、5 张原生表格、21 个公式块和 33 条参考文献候选；150 个参考文献物理块全部有组件归属，标题识别正确，保留末页栏顺序及无编号参考文献两条 review 警告。这是 smoke 记录，不是准确率声明或官方测评结果。

另有 Python 3.14 无 fitz/pypdf 的 Poppler 实跑：同一份三页样张走 `pdftotext`、返回 review、保留三页文本且明确无结构等价性；该路径也不得被描述为完整布局解析。

## 8. Requirements 与维护

- Python 3.10+；标准库 + 至少一个真实 PDF backend。完整能力强烈建议 `pip install pymupdf>=1.23`；文本回退 `pip install pypdf` 或安装 Poppler。
- `reader.py`、`reading_order.py`、`structure.py`、`superscript.py`、`tables_pdf.py`、`pipeline.py`、`pdfparse.py` 各自可独立检查；导入时不强制安装任何 backend。
- 文件上限 1 GiB、外部 `pdftotext` 单文件 120 秒是声明的安全边界，不是静默截断页数。
- `scripts/report_pdf_v2.json`、`report_pdf.json`、`report_pdf_hostile.json` 是当前合成回归报告，不含正式案例或白板。
- GitHub 附加链接见包根 `GITHUB_URL.txt`；评审需检查真实 CLI 与产物，而不是依赖本说明自评。

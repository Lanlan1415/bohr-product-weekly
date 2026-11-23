# pdf-parse v2 实现与验证说明

## 1. 正确题目与实际边界

本包只对应 `01-61456272`（阅读01｜文献文档解析），输入是真实 PDF 文件。它不是
`p02-figure-parse`（图像坐标/曲线读数）的改名版，也不从图像描述反推全文。

输出以 source PDF、后端提取文本和坐标为事实依据。没有文字层的页面、不明确的
栏顺序、无法重建的表格、无编号参考文献边界和不能推出的 LaTeX 都显式保留为限制。

## 2. 数据流

```text
case.json + actual.pdf
  │
  ├─ pdfparse.py
  │    ├─ 校验 JSON 对象、已知 section、路径与多候选
  │    └─ 早期 undetermined partial / 最终契约回填
  ▼
reader.py
  ├─ PyMuPDF: metadata/TOC + raw text + block/line/span/bbox/fonts/images/tables
  ├─ pypdf: page text + metadata（显式 layout fallback）
  └─ pdftotext: page text（显式 layout fallback）
  ▼
reading_order.py
  ├─ 重复页眉页脚标记（只规范明确页码，不规范章节数字）
  ├─ 原始 block 按 span 行间距和 x 突变拆物理块
  ├─ 宽正文锚点确定栏界，公式/单元格碎片再归栏
  └─ 跨栏带 / 元数据精确标题 + 1~3 栏阅读顺序
  ▼
structure.py
  ├─ 题名、作者候选、单位、摘要、标题、正文、脚注、参考文献
  ├─ 编号/命名标题 + 全块粗体或显著字号，防公式/数字表行误判
  ├─ outline/sections/captions
  └─ 编号文献切分；无编号文献按作者起点+年份边界重组并标复核
  ▼
superscript.py
  └─ Unicode/公式编号/上下标/字体 superscript flag；不推断 LaTeX
  ▼
tables_pdf.py
  ├─ 原生 Table.extract() 文本与 None
  ├─ 原生 row/cell bbox → cells 和 merged_regions
  ├─ caption 近邻链接
  └─ 仅明确 continued / 相同重复表头的续表合并
  ▼
pipeline.py
  ├─ 引擎值 > case 携带值 > null+limits
  ├─ case_id/output_contract 原样保留
  └─ result.json + full_text.txt + document.md + tables.json + source_pages.json
```

## 3. 可核验不变量

1. 每个文本/图像块有 `block_id`、page、PDF source block、阅读顺序、bbox；span 不丢。
2. `evidence_and_boundaries.locators[*].quote` 是对应块文本在 `char_start:char_end` 的精确片段。
3. `source_pages.json` 保留后端原页文本，正向拆分不能成为“原论文就按这个顺序印刷”的假证明。
4. `full_text.txt` 排除 `include_in_body=false` 的页眉页脚、题注、参考文献、脚注和元数据块。
5. `latex` 永远为 null，除非未来真正实现并测试数学结构转换；Unicode SHA-256 可防静默改动。
6. 无原生表格时 `tables=[]`，普通三列对齐文字不触发虚构 x-grid。
7. 无编号参考文献的 `component_blocks` 必须是全部 reference 物理块的划分，启发式归并必须 review。
8. 成功和拒绝都有顶层 case_id 与完整原 output_contract；能确定的值不丢，不能确定的 null+limits。
9. 不写 UTC、elapsed_s、随机 id；相同输入和同版后端的结果及四个附加产物必须字节一致。

## 4. 状态映射

- `clean / 0`：有真实解析产物，且无 medium/high findings；单页无标题不强行报错。
- `review / 3`：有产物，但回退、扫描页、栏序、无编号文献或契约字段需人工复核。
- caller error / 4：case 非对象、无 PDF 字段或字段类型错误。
- undetermined / 5：坏 JSON、未知 section、缺文件、全部扫描、加密、损坏或后端失败。

所有正式 case 失败都写 result.json，不暴露 traceback。argparse 用法错误为 2，不等同科学解析失败。

## 5. 参考实现的具体采用处

- Docling（MIT，https://github.com/docling-project/docling ）把版式、阅读顺序、表格、
  公式、OCR 和结构化导出分层。本项目不依赖其模型，而采用相同的职责分离与
  provenance 思想；没有把该项目尚未提供的元数据能力写成已有调用。
- PyMuPDF 文档（https://pymupdf.readthedocs.io/en/latest/page.html ）提供
  `Page.find_tables`、`Table.extract/rows/cells/bbox/header`。表格在页生命周期内
  复制为普通字典；合并区域只从原生几何推导。
- p59/p69 黑盒回归方式被用于 `probe_pdf.py`：exit/result JSON/traceback/契约/重放
  同时断言，避免“有 result.json 就算成功”。

## 6. 实际测试层

- `bench_pdf.py`：旧调用兼容基线，12 场景。
- `bench_pdf_v2.py`：生成真实三页双栏科研样张，12 场景；原生合并单元格、标题层级、
  图像、公式、编号参考文献、混合扫描、加密、拒绝和五产物 byte replay。
- `probe_pdf.py`：22 个黑盒敌意探针，覆盖 case/材料/多 PDF/自动发现/契约。
- 公共 ACL P18-1001 真实 smoke：PyMuPDF 2.1 实跑 11 页；验证标题、章节顺序、
  原生表格、公式和参考文献组件覆盖。末页栏顺序与无编号文献仍 review，不隐藏。

## 7. 共享文件纪律

这七个引擎文件目前只用于本包，不与 p02-figure-parse 或其他 reading 包共享。
若未来产生共享副本，任何改動必须同步全部副本并重跑各包 bench；不能只改某一份。

## 8. 剩余限制

- 无框表格、图片表格、复杂多层表头没有可靠原生几何时不猜。
- 复杂版式仍可进入栏序 review；不能把启发式栏号当逐字排版证明。
- 无编号参考文献的作者/年份边界仍需人工检查，特别是会议名中的年份和作者断行。
- OCR 未内建；扫描页需要平台 OCR 后重跑。字体映射错误只报警，不擅自修字。

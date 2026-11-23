# pdf-parse 解析架构设计笔记

## 1. 背景与定位

科研文献周赛 `01-61456272`（阅读01｜文献文档解析）的核心要求是"真的把一份 PDF
解析成可用的结构化结果"，而不是看起来支持 PDF 文字提取。本包对 PoLD 题面的关键
扣分点是：

- 多栏阅读顺序（top-to-bottom vs column-first）
- 表格结构重建（列归属，合并单元格占位）
- 公式与特殊字符保真（greek/superscripts）
- 章节层级定位（页码 + 块索引双层锚点）
- 扫描件处理（拒绝并给恢复指引）

之前的 `p02-figure-parse`（数据图像素读数）落在本题的错位方向上，四次提交 0 分。
本包是面向题面原样的 PDF 解析重新实现。

## 2. 引擎分层

```
case.json
  │
  ▼
reader.py  (fitz → pypdf → pdftotext)
  │
  ▼
reading_order.py  (按 bbox 聚类列；列内按 y 排序)
  │
  ▼
structure.py  (NAMED 标题词表 + NUMBERED 正则 + header/footer 排除)
  │
  ▼
superscript.py  (formula 标记 + sha256 + cp1252 警告)
  │
  ▼
tables_pdf.py  (按 x 列距聚类，≥3 列且 ≥2 行的被识别为表格)
  │
  ▼
pipeline.py  (rr / eb / provenance / contract_echo)
  │
  ▼
result.json
```

每层失败时上升 Refusal 而非 traceback。

## 3. 契约契约直通

输入 spec/case 的字段约定：
- 顶层：`case_id`, `pdf_path`（或同义键）, `output_contract`
- `output_contract`：评审点名的字段名列表
- 引擎优先值 > spec 携带值 > null+limits 注记三层优先顺序与 `p11-qa`
  `p115-structure` `/chat/summary/41-writing-master` 全包共用。

## 4. 已知限制

- **CJK**：标准 14 字体不带 CJK 字形；fitz 可为缺字形嵌入空格，引擎仅声明，
  不调用 OCR。
- **多栏**：默认按列中点把页面切成两栏，超过两栏或极端布局（如不对称
  图文环绕）会进入单栏回退并写 `column_order_warning`。
- **表格**：需要至少三列横向对齐、至少两行才算表格；单元格不修改任何
  内容，缺位空字符串占位。
- **公式**：基于字符类启发式，不输出 LaTeX。

## 5. Backends 策略

| backend | 能力 | 缺失影响 |
|---------|------|---------|
| PyMuPDF | 关键字节/坐标/页码 | 完整能力（识别双栏/表格） |
| pypdf | 仅文本层提取 | 退化到仅文本，无 bbox |
| pdftotext | 文本+换页符 | 仅文本，忽略布局 |

降级路径的 switch 在 `reader.py：read()` 中实现；三种全部失败时拒绝并附一行
安装建议。

## 6. 与原有 figure-parse 的关系

`p02-figure-parse` 仍存在，可继续用于把 **图像** 中的数字读出来作为数据断言；
其 SKILL.md 与本包 **不共享代码**，是两个独立工具。在新案例上（PDF 作为输入）应
只调本包。

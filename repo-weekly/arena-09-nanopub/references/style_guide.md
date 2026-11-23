# Turtle/TriG 书写与序列化规范（阅读14）

## 文件形态

- 交付统一用 TriG（`nanopubs.trig`）：一个文件装多条 nanopub，每条四个命名图。
- 纯断言数据（无 nanopub 包装）才用 Turtle（.ttl）。
- 编码 UTF-8（无 BOM 亦可，读端统一 utf-8-sig）；行尾风格全文件一致。

## 前缀与命名空间

- 文件头集中声明全部 `@prefix`，一条一行，以 ` .` 结尾。
- 必备前缀：`np`→`http://www.nanopub.org/nschema#`、
  `prov`→`http://www.w3.org/ns/prov#`、`pav`→`http://purl.org/pav/`、
  `dcterms`→`http://purl.org/dc/terms/`、`xsd`→`http://www.w3.org/2001/XMLSchema#`。
- 空前缀 `:` 指向本案例 nanopub 命名空间（如
  `http://example.org/np/<case_id>-<seq>#`）；案例自定义词表用单独前缀
  （如 `ex:`），与 nanopub 命名空间分开。
- 未声明的前缀一律不得使用；同一前缀全文件指向同一 IRI。

## 语法细节（nanopub_check.py 的检查口径）

- 每条三元组语句以 ` .` 结束；` ;` 与 ` ,` 只用于同一主语/谓语的续行，
  语句组最后一条仍以 ` .` 收尾，` }` 前不得残留 ` ;` 或 ` ,`。
- 图块写法：`:Head { ... }`，标签与 `{` 同行；四个图本地名固定为
  Head / assertion / provenance / pubInfo。
- IRI 用 `<...>` 全形或前缀缩写，不得含空格与换行。
- 字面量：数值带类型（`"178"^^xsd:float`），日期用 `"2024-01-15"^^xsd:date`，
  文本用双引号；注释用 `#` 到行尾。
- 缩进 2 空格；同一图内相关三元组相邻，主语相同时用 `;` 归并。

## 断言文本风格（assertion_table.md 与自然语言陈述）

- 中文陈述，句式固定："在【条件】下，【主体】的【关系】为【客体+单位】。"
- 不含评价词（"优异""显著"须有统计或对比语境支撑，否则删）。
- 术语首次出现给"中文（English, 缩写）"；同义词归并到词表区登记。
- 引文保留原文语言，≤30 字。

## 标识符

- DOI 写完整 IRI 形式 `https://doi.org/10.xxxx/...`；ORCID 用
  `https://orcid.org/0000-....` 命名空间。
- 材料中找不到的标识符写"未报告"（在 assertion_table.md），RDF 中该三元组
  整体省略而不是写假值。

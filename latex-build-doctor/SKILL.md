---
name: latex-build-doctor
description: >
  Write, repair and verify a real LaTeX project. Use when a task needs editable .tex/.bib
  deliverables, math/figure/table/cross-reference checks, template migration, compiler-log
  diagnosis or a reproducible multi-round build. Runs latexmk or explicit engines when available;
  records environment, commands, packages, fonts and source hashes; requires stable generated
  state plus resolved citations/references for success. Without TeX it explicitly reports that no
  compilation or PDF occurred and delivers only source/static evidence, never a fabricated build.
---

# LaTeX 写作与编译：真实源码 → 定位修复 → 收敛复核

本 Skill 的产物是可继续编辑的 LaTeX 工程，不是一段源码建议，也不是把“有 PDF”冒充“已编译正确”。模型负责按 `task.md` 真正修改 `.tex/.bib`；`scripts/texcase.py` 负责实际运行检查、编译、日志诊断、产物收集和 `case_id/output_contract` 直通。

## 必须保留的边界

1. **不改 `/input`**：将工程复制到 `/app/work/build` 后编辑；`/app/output` 只交付运行产生的结果。
2. **不伪造编译**：`compilation_attempted`、`pdf_generated` 和 `build.converged` 是三个不同事实。没有引擎、latexmk 启动失败或 `--static-only` 均不得声称 PDF 成功。
3. **不以文件存在替代收敛**：严格成功要求最终两轮退出码为 0；aux 引用、citation、BBL、TOC 等状态哈希稳定；无 rerun 警告、未定义 citation/reference 或日志错误；静态 error 为 0；本轮真实 `main.pdf` 被交付。
4. **保留来源**：不凭 task 标签改写科研数字。公式、表格值、图号、引文键及模板必填项的改动应写入 `changes.json`；无法确定的内容进入 `uncertainty/limits`。
5. **不联网装包**：驱动使用 `-recorder` 记录依赖并开启 BibTeX/Biber；MiKTeX 自动安装保持 `none`。缺包、缺字体、缺 cls、权限和超时都要如实保留报告。
6. **契约逐字保留**：`case_id` 及 `output_contract` 的全部字段直接出现在结果中；case 自带同名字段原样直通。嵌套对象保留嵌套键。未知字段不得虚构，置 `null`（数组形状置 `[]`）并在 `limits` 指明路径。

## Runtime：从 `/input` 到 `/app/output`

### 1. 读取并复制真实工程

读取 `/input/case.json` 与 `/input/task.md`，定位包含 `\documentclass` 的主文件及其 `.bib/.cls/.sty/bst`、图片和数据。不要根据文件名臆造内容。

```bash
mkdir -p /app/work/build /app/output
cp -a /input/PROJECT/. /app/work/build/
```

多主文件或入口不明确时，后续命令使用 `--main main.tex` 明确指定，不能不报告歧义。

### 2. 先保存诚实的部分结果

先运行一次静态路径。它会保存契约骨架、可复制源码、环境探测和静态报告；即使随后中断，也不会留下假 PDF 声明。

```bash
S=/skills/weekly-skill/scripts
python -I "$S/texcase.py" \
  --case /input/case.json --project /app/work/build \
  --main main.tex --out /app/output --static-only
```

此命令**有意不编译**，即使本机有 TeX。返回 3、状态 `partial` 是预期的早存行为，不是 PDF 失败证明。

### 3. 完成题目要求的源码修改

使用定点编辑修改 `/app/work/build`，而不是只给一个补丁建议。

| 任务 | 真实检查或编辑点 |
|-|-|
| 公式 | amsmath 环境、`align/split` 配对、编号与 `\eqref`、上下标、变量与单位语义；不擅自改数学含义 |
| 表格 | 列说明与每行单元格数、`booktabs`、跨页和列宽；不要用缩小字体掩盖 overfull |
| 图表 | 环境配对、caption/label、文件确实存在、图表跨引；不把截图当可编辑源码 |
| 引用 | `\cite/\ref/\eqref` 与 `.bib/.bibitem/\label` 全项目匹配；多文件标签共享解析 |
| 模板 | 指定 class、宏包加载顺序、字体、必填元数据、相对路径；不得将缺失 cls 换成文章类后仍称“指定模板” |
| 构建 | 非交互收集全量错误，按根因修复并重跑；Citation/Reference 未解决时不能以 PDF 存在通过 |

每次真实编辑可登记到 `/app/work/changes.json`：

```json
[
  {
    "file": "main.tex",
    "line": 18,
    "before": "原命令或原文",
    "after": "实际采用的新命令或新文",
    "reason": "task.md 的哪项要求；不能写虚构的科学依据"
  }
]
```

### 4. 执行实际构建

```bash
python -I "$S/texcase.py" \
  --case /input/case.json --project /app/work/build --main main.tex \
  --out /app/output --changes /app/work/changes.json \
  --engine auto --max-rounds 6 --time-budget 360
```

引擎规则：

- `auto` 根据主文件选择 pdfLaTeX，发现 CJK/Unicode/fontspec/ctex 时优先 XeLaTeX，其次 LuaLaTeX；有 latexmk 时使用 latexmk，否则走显式引擎。
- latexmk 命令带 `-recorder -bibtex -interaction=nonstopmode -file-line-error`；显式引擎执行首轮、必要的 bibtex/biber、再编译和稳定性复核。
- 需要固定引擎时用 `--engine pdflatex|xelatex|lualatex|tectonic`。显式偏好不可用时不静默换引擎，报告不能确定。
- `run_build` 不是 `result.status` 的唯一依据。`texcase` 还会核查静态 error、全部 log error 与本次实际 PDF。
- 无引擎时自动落 `partial`，`build_report.json` 为 `status=not_compiled`，`compilation_attempted=false`，不产生 `main.pdf`。

### 5. 按日志定位、修复并重新运行

每次运行读取这些证据，而不是只读控制台最后一行：

- `build_report.json#passes`：每个真实命令、退出码、.aux/build-state 哈希、FLS 存在性、日志阻断项和轮次快照；
- `log_report.json#errors`：全量错误的文件、行号、类别与修复提示；
- `log_report.json#warnings`：未定义引用/citation、rerun、重复 label、over/underfull、字体替换；
- `static_report.json#issues`：环境、括号、数学分隔符、跨文件 ref/label、bib key、表格列数、UTF-8/CJK 支持。

典型处置方式：

| 类别 | 处理 |
|-|-|
| undefined_control_sequence | 检查拼写及提供命令的宏包；不虚构宏定义来隐藏源问题 |
| missing_package/class/file | 核对工程与模板文件；确实缺失时写 limits，不联网安装 |
| math_mode_error | 修 `$/\(\)/\[\]`、`\left/\right` 与文本/数学环境；重查公式原意 |
| environment/brace/runaway | 按堆栈和行号配对 begin/end 与括号，不只修最终 Emergency stop |
| table_column_mismatch | 修列说明或行内 `&`，并考虑 `\multicolumn`；校验编译日志 Extra alignment tab |
| undefined_reference/citation | 修全项目 label/bib key，确保 bibliography 步骤执行，再编译到状态稳定 |
| font/unicode | 选择 XeLaTeX/LuaLaTeX 与已有 CJK/fontspec 支持；缺字体时记录替换而不是声称字体合规 |
| 不收敛/超时 | 保留轮次、build-state 差异和最后日志；转人工定位，不提高 max-rounds 后仍称收敛 |

修复 `main.tex/.bib` 后重复第 4 步。每次成功必须来自**修复之后那一次真实运行**；上一轮 PDF 和报告不会用来冒充新一轮结果。

### 6. 核对交付物并完成 result.json

`texcase.py` 写出 `result.json`、`output_contract` 汇总对象及直接合同字段。再检查未知字段是否需要模型根据实际产物补齐；不得覆盖诚实 status 或凭空填数。

| 文件 | 内容 |
|-|-|
| `main.tex`, `src/` | 可编辑主源码和原相对结构配套文件；源文件哈希在 `source_manifest` |
| `result.json` | case_id、全合同字段、目标产物、事实与来源映射、版本与边界、真实状态 |
| `environment.json` | 本机工具路径/版本探测、引擎选择策略、未启用联网安装 |
| `build_report.json`, `round_logs/` | 真实命令序列、退出码、轮次、状态哈希与严格收敛判据 |
| `static_report.json` | 源文件级的问题、文件/行号/fix_hint、错误计数 |
| `log_report.json` | 真实日志的全量错误/警告分类；无日志时明确说未诊断 |
| `repro_record.json` | documentclass、宏包/版本、字体文件、命令、FLS 证据、输入/PDF 哈希 |
| `main.pdf` | 仅当前运行实际生成且仍存在时复制；部分/失败结果不得单独把 PDF 当成成功 |
| `preview/` | 有本机栅格化器时生成；没有工具则留空并说明，不伪造 PNG |

结果中的 `deliverable/evidence_map/boundary` 分别对应“目标产物”“事实与来源映射”“版本与边界”。

## 退出码和状态

| texcase exit | result.status | 条件 |
|-|-|-|
| 0 | success | 本轮真实编译严格收敛、PDF 实际交付、静态 error=0、日志 error=0 |
| 3 | partial | 静态模式/无 TeX，或无错误但未证明严格收敛；含可继续编辑的部分产物 |
| 4 | partial | 静态 error、编译 log error 或实际 builder 失败；结构化 findings 已落盘 |
| 5 | refused | 坏 JSON、非对象 case、工程/主文件不存在、main 越出 project、预算参数非法或不可恢复运行异常；有可读 case 时仍保留其合同字段 |

拒绝项使用 `texcase.refused`，严格未收敛使用 `texcase.not_converged`。所有返回路径都写 `/app/output/result.json`；只有 Python 本身或文件系统不可写时不可能落盘，必须在原生运行记录中报告，而不能声称已写成功。

## 输出判定的伪反例

- PDF 文件来自上一次运行：本轮 `--static-only` 或新失败构建前删除已知陈旧的 `main.pdf` 和旧报告；不得交付。
- 引用警告仍在、退出码为 0：`log_blockers` 发现后直接阻止 `converged=true`。
- `.aux` 的 newlabel 哈希两轮相同：还不够；citation、BBL、TOC 和 log 也必须通过，防止漏掉 bibliography 漂移。
- 子文件没有 `\documentclass`：在项目已有主文件时是 info，不是 error；子文件引用主文件的 label 可以解析。
- 没有日志：`log_blockers=null`，不是“没有错误”；`log_report.json` 明确写 `no compiler log exists`。
- `repro_record.generated_at=null`：不是信息丢失，而是避免把墙钟时间写入本可确定性的语义结果；实际时间由平台 native trace 记录。

## 复现机制的来源与具体落地

实现参考了 latexmk 的公开手册和 `debian-tex/latexmk` 仓库，而没有包装一个虚假 `latexmk --version`：

- 官方 latexmk 使用 `.fls/.log/.aux` 做依赖分析，并保留 `.fdb_latexmk`；本实现实际生成/检查 `.fls`，但不会伪装成 latexmk 的数据库。
- 官方支持按需 BibTeX/Biber 和跨引用状态重复运行；本实现把 bib 步骤、`bbl` 哈希和未定义项纳入自定义轮次判据。
- 官方有 `-Werror` 可让残留引用警告返回非零；本实现独立地把 log blocker 阻断 success，不把进程 rc=0 当作质量证明。
- 不如 latexmk 完整：不提供完整宏级依赖分析、持续预览或任意 TeX 规则图；状态哈希是明确、可复核的最小替代。

公开资料：
- https://mirrors.ctan.org/support/latexmk/latexmk.txt
- https://github.com/debian-tex/latexmk

## Requirements

- 审计/编排：Python **3.10+**，仅标准库（本机 3.14 实测）；无需网络。
- 实际编译：本机需真实 latexmk 或 pdflatex/xelatex/lualatex/tectonic；有 `.bib` 时需相应 bibtex/biber。缺工具不安装、不模拟。
- PNG 预览是可选能力，需要 pdftoppm、ImageMagick、Ghostscript 或 mutool 中至少一个。

## Limits

- 静态检查是启发式：表格宏、复杂自定义命令、动态生成内容仍需真实编译和人工版面复核。
- 现在扫描项目内 `.tex` 做项目级 ref/bib 检查，并不构建 latexmk 那样的完整依赖图。生成到非标准目录、外部 TEXMF 宏包和 shell-escape 不由本工具安全复现。
- `converged=true` 不证明科研公式正确、模板视觉合规或所有 overfull 都适合交付；这些问题必须在 `warnings/uncertainty` 中保留并人工检查 PDF。
- 同输入静态结果可字节级复跑。实际 TeX 的耗时、工具路径、包版本和 PDF 元数据会随环境变化；不能把不同发行版的字节一致当作已承诺特性。
- 不支持从 PDF 反推一份语义等价的可编辑 LaTeX。缺原稿时必须结构化拒绝，而不是把截图包装成源码。

## Optional verification（不要代替正式案例产物）

```bash
# 旧回归：日志、表格、环境、工具探测、记录器
python -I scripts/selftest.py

# 冷导入、敌意输入、合同/退出码、静态回退、跨文件和确定性
python -I scripts/bench_texcase.py

# 有 TeX 时再运行：真实文章 + bibliography + math + table/figure 编译，
# 故意 Undefined control sequence 后修复并证明重编译收敛
python -I scripts/bench_texcase.py --real
```

所有测试 fixture 都是合成输入，不是正式案例答案。当前包 `scripts/report_texcase.json` 记录最近一次作者侧真实 `--real` 运行；机器无 TeX 时不要执行或引用该记录作为本次设备已编译的证据。

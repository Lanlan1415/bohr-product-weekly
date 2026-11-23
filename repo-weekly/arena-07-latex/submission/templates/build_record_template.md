# 编译记录模板（build_record.md，写作13）

> 作用：让他人能按记录重建同一份 PDF；让每次修复可回溯。交付时填到 `/app/output/build_record.md`。

## 1. 构建环境

| 项 | 值 |
|----|----|
| TeX 发行版与版本 | {{如 TeX Live 2024 / MiKTeX 24.x；以实际 `pdflatex --version` 输出为准}} |
| 引擎 | {{pdflatex / xelatex / lualatex（以模板要求为准）}} |
| 非标准宏包 | {{环境默认之外安装/自带的包及版本；无则写"无"}} |
| 字体依赖 | {{模板/工程引用的非内置字体；无则写"无"}} |
| 操作系统 | {{容器/系统信息}} |

## 2. 编译命令序列（可复制执行）

```bash
cd <工程目录>
pdflatex -interaction=nonstopmode main.tex
bibtex main            # 或 biber main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
# 或：latexmk -pdf -interaction=nonstopmode main.tex
```

- 实际轮次数：{{N}}；收敛判据：最终日志无 Rerun 提示、无 undefined references/citations、无 `!` 错误。
- 最终构建时间：{{时间戳}}；产物：main.pdf（{{页数}} 页）。

## 3. 错误与修复记录（每轮留痕）

| 轮次 | 日志 | 错误（类型，文件:行号） | 根因 | 修复 | 修复后结果 |
|------|------|------------------------|------|------|-----------|
| R1 | build_round1.log | E3 math_mode, sections/methods.tex:42 | 正文下划线未转义 | `x_i` → `$x_i$` | 该错误消除，余 2 个 |
| R2 | build_round2.log | E8 citation undefined | 轮次不够 | 补 bibtex+2×pdflatex | 收敛 |
| … | | | | | |

## 4. 静态检查记录

| 时间 | 工具 | 结果 | 处置 |
|------|------|------|------|
| {{}} | tex_static_check.py | {{N 个错误/通过}} | {{}} |

## 5. 遗留警告与说明

- Overfull \hbox：{{N 处，最大 xx pt，位置与原因}}；
- 其他警告：{{}}；
- 未能解决项：{{及原因；影响范围}}。

## 6. 重建验证

- [ ] 删除中间文件（.aux/.log/.bbl 等）后按 §2 命令从零重建成功；
- [ ] 重建产物与交付 PDF 页数一致。

> 编译失败时：本表 §2 记录实际执行到哪一步、失败日志文件名（随 /app/output 交付），并在 result.json 将 status 标为 partial/failed、uncertainty 写明根因。严禁在未编译成功时声称成功。

# build-protocol — 编译轮次协议与收敛判定

版本 1.0.0，与 build_loop.py 行为一致。

## 1. 轮次协议

```
 latexmk 可用 →  latexmk -pdf -interaction=nonstopmode -file-line-error <main.tex>
                 （latexmk 自动调度 bibtex/biber 与多轮 pdflatex）
 否则手动轮次 →  第1轮  pdflatex -interaction=nonstopmode -file-line-error <main.tex>
                 第2轮  bibtex <main>（或 biber <main>，按 \bibliographystyle/biblatex 判断）
                 第3轮  pdflatex ...
                 第4轮  pdflatex ...
```

- `--max-rounds`（默认 6）封顶引擎轮次；`--time-budget`（默认 900 秒）封顶总时长，
  超时立即停止并在报告记录 `time_budget_exceeded: true`。
- 每轮记录：`{index, kind(engine|bib), tool, args, exit_code, seconds, timed_out}`。
- 每轮 .log 快照存 `--keep-logs` 目录（默认 <workdir>/round_logs），最后一轮供 parse_log.py 全量分析。

## 2. 收敛判定（converged）

同时满足三条才算收敛：

1. 最后一轮引擎退出码 0；
2. **aux 标签哈希稳定**：从 .aux 提取全部 `\newlabel{...}` 键集合做哈希，相邻两轮相同
   （说明交叉引用不再变化）；
3. 最终 log 无 rerun 警告（rerunfilecheck / "Rerun to get" / "Label(s) may have changed"）。

未收敛但轮次/预算用尽 → converged=false + rerun_needed 警告进 error_table。

## 3. 与 parse_log 的衔接

build_loop 只保证"编译到收敛或预算耗尽"；**错误分类定位表永远来自 parse_log.py 对
最后一轮 log 的全量解析**（13 类错误 + 9 类警告，不止第一条）。

## 4. 与 repro_record 的衔接

收敛（或预算耗尽）后，repro_record.py 汇总：引擎 --version 输出、log 中 \openin 加载的
宏包与字体、完整命令序列与轮次、输入文件哈希、收敛状态——他人据此可复现同一产物。

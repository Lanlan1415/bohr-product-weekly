# LaTeX Build Doctor — 使用与方法说明

LaTeX 编译与修复 Skill：环境探测 → 编译轮次协议（直到引用收敛）→ 全量错误/警告分类
定位表（13+9 类，不止第一条）→ 按修复知识表修源码（记录 diff 与理由）→ 可复现构建记录；
无 TeX 环境时降级为静态检查并如实标注。

- 适用：写作13 LaTeX 写作与编译类任务；任何"编译 .tex、修编译错误、可复现构建"场景。
- 输入：`/input/case.json` + .tex/.bib/.sty/.cls/.bst 源码与素材。
- 输出：`/app/output/result.json`（统一信封）、`main.pdf` + PNG 预览（编译成功时）、
  错误定位表与构建记录。
- 运行环境：Python ≥ 3.8，**纯标准库**；可选系统工具：pdflatex / latexmk / xelatex /
  tectonic（探测缺失时走静态降级路径，不静默失败）。

## 一、完整调用步骤（`$SKILL=/skills/weekly-skill`，`$WORK=/app/work`，`$OUT=/app/output`）

| 步 | 执行者 | 命令 | 产物 |
|---|---|---|---|
| 0 | Agent | 读 case.json：主文件、目标模板、必产物 | 边界确认 |
| 1 | 脚本 | `python -I -B $SKILL/scripts/detect_tex.py --out $WORK/tex_env.json` | 环境清单（exit 3 = 无 TeX，转静态路径） |
| 2 | 脚本 | `python -I -B $SKILL/scripts/build_loop.py <main.tex> --dir <目录> --max-rounds 6 --time-budget 900 --report $WORK/build_report.json --keep-logs $WORK/round_logs` | 每轮记录 + 收敛判定（协议见 build-protocol.md） |
| 3 | 脚本 | `python -I -B $SKILL/scripts/parse_log.py $WORK/round_logs/last.log --blg auto --out $WORK/error_table.json` | 全量错误/警告分类定位表 |
| 4 | 模型 | 按 error-playbook.md 逐条修复（≤3 轮，每处改动记录 diff+reason），修完重跑步 2-3 | 修复循环 |
| 5（降级） | 脚本 | 无 TeX 时：`python -I -B $SKILL/scripts/static_check.py <*.tex> --dir <目录> --out $WORK/static_report.json` | 静态体检（环境配对/引用匹配/数学 $/编码/表格列数） |
| 6 | 脚本 | `python -I -B $SKILL/scripts/repro_record.py --main <main.tex> --log $WORK/round_logs/last.log --rounds $WORK/build_report.json --workdir <目录> --out $WORK/repro_record.json` | 可复现构建记录 |
| 7 | 模型 | PDF/PNG 预览入 $OUT；写 `$OUT/result.json`（output-contract.md） | 交付物 |

## 二、输入输出解释

- **result.json**：`result.build`（工具/版本/每轮/收敛/超时）、`result.error_table`
  （file/line/message/category/fix_hint/fix_applied）、`result.source_changes`
  （file/diff_summary/reason）、`result.repro_record`（引擎/宏包/字体/命令/哈希）、
  `result.static_check`（降级路径时）。
- **error_table**：全部错误与警告——`{file, line, message, category, fix_hint}`，
  类别对照 error-playbook.md（13 类错误 + 9 类警告）。
- **预览**：编译成功交 PDF；PNG 预览仅在真实渲染时提供，绝不假装渲染。

## 三、关键方法（对准题面四问）

1. **编译得通**：轮次协议 + 三条收敛判定（exit 0 / aux 标签哈希稳定 / 无 rerun 警告）。
2. **改得对**：错误分类 → 修复模板（playbook）；先修第一条根因（emergency_stop 是症状）；
   交叉引用问题先确认轮次完整再改源码。
3. **交得可用**：交付可维护源码 + 真实产物 + 全量错误表；每处改动可审计。
4. **复现得了**：repro_record 记录引擎版本/宏包/字体/命令序列/输入哈希。

## 四、适用范围与限制

- pdflatex/latexmk/xelatex/tectonic 之一可用即全流程；全缺时只做静态检查（结论必须标注
  "静态检查，未实际编译"）。
- 79 列 log 换行按 TeX 标准合并；极端自定义 max_print_line 的引擎可能漏合并（影响有限）。
- static_check 的表格列数检查是粗检（& 数 vs 列定义），multicolumn 场景需人工确认。
- PNG 预览依赖系统渲染工具；没有就只交 PDF 并在 uncertainty 标注。

## 五、失败处理

| 情形 | 处置 |
|---|---|
| detect_tex exit 3 | 静态降级路径；status=cannot_determine；给安装建议 |
| 编译超 900 秒 | 停止并记录 time_budget_exceeded；已完成轮次照常分析，status=partial |
| 3 轮修复后仍有 error | error_table 摘要进 status_notes，status=partial |
| 模板文件缺失且无法获得 | missing_class/missing_package 保留在错误表中 |
| 脚本崩溃 | 重跑一次；仍失败手动完成该步并写明接管点 |

诚实原则：没编译不说编译过；没渲染不说渲染了；改动必须留痕。

## 六、自查方法（交付前）

跑 `python -I -B $SKILL/scripts/selftest.py`（内置样例 log：≥3 类错误检出、7 类警告检出、
换行合并、静态检查环境配对、构建记录诚实性）。再逐条核对 SKILL.md 末尾自查清单与
references/rubric-checklist.md。

## 七、最小调用示例

见 `examples/example-01.md`（15 行迷你 .tex，标注为示例，非正式案例结果）。

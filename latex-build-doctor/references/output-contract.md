# output-contract — latex-build-doctor 的 result.json 与交付物

版本 1.0.0，与 SKILL.md / build_loop.py / parse_log.py / static_check.py / repro_record.py 一致。
信封遵循共享架构规范 §3。

## 1. 顶层信封

```json
{
  "case_id": "<来自 /input/case.json；读不到则 null 并在 status_notes 说明>",
  "skill": "latex-build-doctor",
  "skill_version": "1.0.0",
  "status": "success | partial | cannot_determine | refused",
  "status_notes": "非 success 必填：哪步没完成/为什么/哪步可人工接管",
  "result": { "见 §2" },
  "evidence": [
    {"item": "E<错误序号> | W<警告序号> | FIX<改动序号>",
     "locator": {"file": "main.tex", "line": 12,
                 "quote": "<log 原文/源码原文逐字 ≤50 字>"}, "confidence": "high|medium|low"}
  ],
  "uncertainty": ["静态检查局限 / 渲染预览缺失 / 无法获得的模板文件 / 修复未清零项"],
  "human_review_items": ["拿不准的修复 / 需要作者决策的模板问题"],
  "method": {"steps": ["detect_tex → build_loop → parse_log → 修复循环 → repro_record"],
             "tools": ["python 标准库脚本链 + 实际使用的 TeX 引擎"]},
  "runtime": {"started_at": "<ISO8601 或 null>", "budget_notes": "<超时/轮次说明>"}
}
```

## 2. result 专属结构

```json
{
  "build": {"tool": "pdflatex|latexmk|tectonic|none", "version": "…",
            "passes": [{"index":1,"kind":"engine","tool":"pdflatex","exit_code":0,"seconds":1.2}],
            "rounds_engine": 3, "converged": true,
            "convergence_rule": "exit=0 + aux label hash stable + no rerun warnings",
            "pdf_path": "/app/output/main.pdf", "time_budget_seconds": 900,
            "time_budget_exceeded": false},
  "error_table": [{"file":"main.tex","line":12,"message":"Undefined control sequence.",
                   "category":"undefined_control_sequence","fix_hint":"…",
                   "fix_applied":"把 \\mybadmacro 改为 \\textbf（macro 从未定义，按上下文应为加粗）"}],
  "source_changes": [{"file":"main.tex","diff_summary":"l.12 \\mybadmacro{x} → \\textbf{x}",
                      "reason":"undefined_control_sequence：该宏从未定义"}],
  "repro_record": {"engine":"pdfTeX Version …","packages":["geometry","natbib"],
                   "fonts":["cmr10"],"commands":["pdflatex …","bibtex …","pdflatex …","pdflatex …"],
                   "rounds":3,"input_hashes":{"main.tex":"sha256:…"},"converged":true},
  "static_check": {"run": false, "issues": [], "note": "仅无 TeX 环境降级路径时 run=true"}
}
```

硬要求：
- `error_table` 必须来自 parse_log.py 对**最后一轮**真实 log 的解析（含修复后残余）；
  `fix_applied` 只写真实做过的修复，没修的留空。
- `source_changes` 与源码真实 diff 对应；禁止无记录改动。
- `build.passes` / `converged` / `time_budget_*` 与 build_report.json 一致。
- `status=cannot_determine` 仅用于"无 TeX 环境且只完成静态检查"；此时 `static_check.run=true`
  且 error_table 为空表（不是编的）。

## 3. 交付物与路径

| 文件 | 说明 |
|---|---|
| `/app/output/result.json` | 本契约定义的主交付物 |
| `/app/output/main.pdf` | 编译成功的 PDF（复制自构建目录） |
| `/app/output/preview-*.png` | 真实渲染的预览（有渲染工具时；没有则只交 PDF 并在 uncertainty 标注） |

## 4. 校验命令（终检）

```bash
python -I -B "$SKILL/scripts/selftest.py"        # 包内自测（log 解析/静态检查/轮次记录）
# 运行期一致性：result.build.* == build_report.json；error_table == parse_log 输出（含残余）
```

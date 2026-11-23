#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""log_triage.py — LaTeX 编译日志解析与错误分类（写作13）。

输入 .log 文件，输出分两级：**错误（阻断编译，行首 `!`，必须修）** 与
**警告（不阻断编译，按需处理）**；错误按类型归类，定位到 文件:行号（近似），
并给出修复建议（对照 references/error_fix_table.md 的分类编号 E1..E10）。
本脚本只读日志、只做诊断与建议，绝不改写任何源码；诊断不夸大——
警告不说成错误，未验证的猜测不写成根因。

分类：E1 未定义命令 / E2 缺宏包或文档类 / E3 数学模式 / E4 环境不匹配 /
E5 浮动体 / E6 编码与字体 / E7 缺文件 / E8 引用与参考文献 / E9 版式警告 /
E10 致命中止 / OTHER 其他。

用法：
    python3 /skills/weekly-skill/scripts/log_triage.py --log /app/work/main.log \
        --report /app/work/log_triage.md [--strict]

退出码：0 = 无错误级条目；1 = 存在错误（--strict 时警告也计）。stdlib-only，
utf-8-sig 读文件，只读输入，不依赖网络与 CWD。
"""

import argparse
import os
import re
import sys

# (类别编号, 类别名, [正则], 修复建议, 是否错误级)
RULES = [
    ("E2", "缺宏包/文档类",
     [r"File [`'][^']+\.sty' not found", r"File [`'][^']+\.cls' not found"],
     "缺宏包：优先改用环境已有宏包的等价写法；确需则安装并记录 build_record；模板强制依赖且无法安装 → 诚实标 partial。", True),
    ("E7", "缺文件",
     [r"File [`'][^']+' not found", r"Cannot (?:find|open)"],
     "路径错（大小写/相对层级）或文件未随工程交付：补文件或改相对路径；图缺失用占位图必须标 [待确认]。",
     True),  # E7 排在 E2 之后：.sty/.cls 已先被 E2 捕获
    ("E1", "未定义命令",
     [r"Undefined control sequence"],
     "缺宏包（查该命令属于哪个包，导言区补 \\usepackage，先查与模板冲突）或命令拼写错误；禁止直接删除命令消错。", True),
    ("E3", "数学模式错误",
     [r"Missing \$ inserted", r"Display math should end with", r"Double subscript",
      r"Double superscript", r"Extra \}, or forgotten \$", r"Missing \{ inserted",
      r"Missing \} inserted", r"Misplaced alignment tab"],
     "正文数学符号包进 $...$（下划线文本用 \\_）；公式环境内不要再套 $；双下标明确分组 x_{i_j}。一处缺 $ 会级联几十条，只修首处即重编。", True),
    ("E4", "环境不匹配",
     [r"\\begin\{[^}]*\}.*ended by \\end", r"Extra \\end", r"Lonely \\item",
      r"Missing \\end", r"\\end allowed only in"],
     "\\begin/\\end 名字不一致或漏 \\end：按报出的行号补齐/改名；\\item 必须在列表环境内。", True),
    ("E5", "浮动体错误",
     [r"Unknown float option", r"Too many unprocessed floats", r"Not in outer par mode",
      r"Float\(s\) lost", r"\\float@error"],
     "[H] 需 float 宏包，优先改回 [htbp]；浮动体堆积用 \\clearpage/调整位置/拆分，不靠缩放。", True),
    ("E6", "编码与字体",
     [r"inputenc Error", r"Unicode char .* not set up", r"Missing character: There is no",
      r"fontspec error", r"Package fontenc Error"],
     "pdflatex 下的中文/弯引号/特殊字符：换成 LaTeX 写法或按模板迁移 xelatex+ctex；源文件统一 UTF-8 无 BOM；字体缺失记录并换可用方案。", True),
    ("E10", "致命中止",
     [r"Emergency stop", r"Fatal error occurred", r"TeX capacity exceeded",
      r"no output PDF file produced"],
     "Emergency stop 是终点不是根因：往上找第一个 ! 错误；capacity exceeded 多为失控的递归宏，检查最近新增自定义命令。", True),
    ("E8", "引用与参考文献",
     [r"Citation .* undefined", r"Reference .* undefined", r"There were undefined references",
      r"Rerun to get cross-references right", r"Please \(re\)run Biber", r"Empty bibliography",
      r"No file .*\.bbl"],
     "多为轮次不够：按 pdflatex→bibtex/biber→pdflatex×2 补轮次；仍缺则用 tex_static_check.py 核对 \\ref/\\cite 与 \\label/.bib。", False),
    ("E9", "版式警告",
     [r"Overfull \\[hv]box", r"Underfull \\[hv]box"],
     "警告级，最后统一处理：长公式折行、URL 用 \\url{}、宽表按 booktabs/tabularx 顺序治理；禁止 \\resizebox 缩表掩盖。", False),
]

RE_ERROR_START = re.compile(r"^!\s*(?P<msg>.*)$")
RE_LINE_NUM = re.compile(r"^l\.(?P<line>\d+)\s*(?P<ctx>.*)$")
RE_FILE_OPEN = re.compile(r"\((?P<path>\.?\.?/?[\w\.\-/\\]+\.(?:tex|sty|cls|bib|def|clo))")
RE_GENERIC_LATEX_ERROR = re.compile(r"^!\s*LaTeX Error:\s*(?P<msg>.*)$")
RE_PACKAGE_ERROR = re.compile(r"^!\s*Package (?P<pkg>\S+) Error:\s*(?P<msg>.*)$")


def classify(text):
    """返回 (编号, 类名, 建议, 是否错误级)。"""
    for code, name, pats, advice, is_error in RULES:
        for pat in pats:
            if re.search(pat, text):
                return code, name, advice, is_error
    return "OTHER", "其他错误", "对照 error_fix_table.md 人工分析；从第一个错误开始修。", True


def parse_log(text):
    """解析日志，返回 (errors, warnings)。errors/warnings 为 dict 列表。"""
    lines = text.splitlines()
    errors = []
    warnings = []
    current_file = None  # 近似：最近打开的 .tex 文件
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m_file = RE_FILE_OPEN.search(line)
        if m_file:
            current_file = m_file.group("path")
        m_err = RE_ERROR_START.match(line)
        if m_err:
            msg = m_err.group("msg").strip()
            # 收集上下文直到空行或下一个 !，找 l.<行号>
            ctx_lines = [msg]
            src_line = None
            j = i + 1
            while j < n and j < i + 30:
                l2 = lines[j]
                if RE_ERROR_START.match(l2):
                    break
                m_ln = RE_LINE_NUM.match(l2)
                if m_ln and src_line is None:
                    src_line = int(m_ln.group("line"))
                    ctx_lines.append(l2.strip())
                    j += 1
                    # 再带两行上下文（遇到下一个 ! 错误行即止，防止吞并下一条错误）
                    for k in range(j, min(j + 2, n)):
                        if RE_ERROR_START.match(lines[k]):
                            break
                        if lines[k].strip():
                            ctx_lines.append(lines[k].strip())
                    break
                if l2.strip() == "" and len(ctx_lines) > 1:
                    break
                if l2.strip():
                    ctx_lines.append(l2.strip())
                j += 1
            full = " | ".join(ctx_lines)
            code, name, advice, is_error = classify(full)
            entry = dict(code=code, name=name, message=msg,
                         file=current_file, line=src_line,
                         context=full[:400], advice=advice,
                         log_line=i + 1, is_error=True)
            errors.append(entry)
            i = j
            continue
        # 警告级
        if re.search(r"LaTeX Warning|Package \S+ Warning", line):
            code, name, advice, is_error = classify(line)
            if code in ("E8", "E9") or "undefined" in line or "Rerun" in line:
                warnings.append(dict(code=code, name=name,
                                     message=line.strip()[:300],
                                     file=current_file, line=None,
                                     advice=advice, log_line=i + 1,
                                     is_error=False))
        i += 1
    return errors, warnings


def render_report(log_path, errors, warnings):
    lines = []
    lines.append("# 编译日志错误分类报告")
    lines.append("")
    lines.append("日志：`%s`" % log_path.replace(os.sep, "/"))
    lines.append("错误 %d 条，警告 %d 条。" % (len(errors), len(warnings)))
    lines.append("")
    if errors:
        lines.append("## 错误（阻断编译，必须修；按出现顺序，从第 1 条开始修，修一条重编一次）")
        lines.append("")
        for k, e in enumerate(errors, 1):
            loc = "%s:%s" % (e["file"] or "?", e["line"] if e["line"] else "?")
            lines.append("### %d. [%s %s] %s（日志行 %d）" % (k, e["code"], e["name"], loc, e["log_line"]))
            lines.append("- 信息：`%s`" % e["message"])
            lines.append("- 上下文：`%s`" % e["context"])
            lines.append("- 修复建议：%s" % e["advice"])
            lines.append("")
    else:
        lines.append("## 错误（阻断编译）\n\n无（日志中未发现 `!` 错误）。")
        lines.append("")
    if warnings:
        lines.append("## 警告（不阻断编译；引用类多为轮次不够需补轮次至消失，版式类最后统一处理）")
        lines.append("")
        seen = set()
        for w in warnings:
            key = (w["code"], w["message"][:80])
            if key in seen:
                continue
            seen.add(key)
            lines.append("- [%s %s] （日志行 %d）`%s`" % (w["code"], w["name"], w["log_line"], w["message"]))
        lines.append("")
    lines.append("> 分类编号 E1..E10 对照 references/error_fix_table.md；"
                 "文件与行号为日志近似定位，以源码实查为准。")
    return "\n".join(lines) + "\n"


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="LaTeX 编译日志解析与错误分类（stdlib-only，只读日志）。")
    parser.add_argument("--log", required=True, help=".log 文件路径")
    parser.add_argument("--report", required=True, help="报告输出路径（.md）")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：警告也计为失败")
    args = parser.parse_args(argv)

    log_path = os.path.abspath(args.log)
    if not os.path.isfile(log_path):
        print("错误：日志文件不存在：%s" % log_path, file=sys.stderr)
        return 1
    try:
        with open(log_path, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError as exc:
        print("错误：无法读取日志：%s" % exc, file=sys.stderr)
        return 1

    errors, warnings = parse_log(text)
    report = render_report(log_path, errors, warnings)
    out_path = os.path.abspath(args.report)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
    except OSError as exc:
        print("错误：无法写出报告：%s" % exc, file=sys.stderr)
        return 1

    print("编译日志错误分类：错误 %d 条，警告 %d 条" % (len(errors), len(warnings)))
    for e in errors:
        loc = "%s:%s" % (e["file"] or "?", e["line"] if e["line"] else "?")
        print("[错误][%s %s] %s  %s" % (e["code"], e["name"], loc, e["message"][:80]))
    from collections import Counter
    wcount = Counter(w["code"] for w in warnings)
    for code, c in sorted(wcount.items()):
        print("[警告][%s] ×%d" % (code, c))
    fails = len(errors) + (len(warnings) if args.strict else 0)
    print("结果：%s（%d 个错误%s）退出码 %d -> %s"
          % ("未通过" if fails else "通过", len(errors),
             "，strict 下 %d 个警告亦计" % len(warnings) if args.strict else "",
             1 if fails else 0, out_path.replace(os.sep, "/")))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

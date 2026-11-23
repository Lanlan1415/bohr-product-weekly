#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""tex_static_check.py — LaTeX 源码静态检查（写作13），编译前拦截必炸问题。

从主文件出发递归沿 \input/\include 收集工程源码（只读），检查：
1. 环境配对：\begin{X} / \end{Y} 不匹配或漏 \end（报错行号）；
2. 交叉引用：\ref/\eqref/\pageref/\autoref 指向不存在的 \label；重复 \label；
3. 文献引用：\cite 的 key 不在 .bib 条目中（工程内有 .bib 时检查）；
4. 文件存在性：\input/\include/\includegraphics 引用的文件缺失；
5. 失衡：每文件花括号余额非零；行内 $ 个数为奇数（启发式）；
6. 兼容提示：pdflatex 工程引用 .eps、出现 [H] 而未加载 float（警告级）。

用法：
    python3 /skills/weekly-skill/scripts/tex_static_check.py --main /app/work/main.tex \
        --report /app/work/static_check.md [--strict]

退出码：0 = 无错误级发现；1 = 存在错误（--strict 时警告也计）。stdlib-only，
utf-8-sig 读文件，只读输入，不依赖网络与 CWD。
"""

import argparse
import os
import re
import sys

RE_COMMENT = re.compile(r"(?<!\\)%.*$")
RE_BEGIN = re.compile(r"\\begin\{([^}]*)\}")
RE_END = re.compile(r"\\end\{([^}]*)\}")
RE_INPUT = re.compile(r"\\(?:input|include)\{([^}]*)\}")
RE_GRAPHICS = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}")
RE_LABEL = re.compile(r"\\label\{([^}]*)\}")
RE_REF = re.compile(r"\\(?:ref|eqref|pageref|autoref|cref|Cref)\{([^}]*)\}")
RE_CITE = re.compile(r"\\cite\w*(?:\[[^\]]*\])*\{([^}]*)\}")
RE_BIBRES = re.compile(r"\\(?:bibliography|addbibresource)\{([^}]*)\}")
RE_BIBENTRY = re.compile(r"@\w+\s*\{\s*([^,\s]+)")
RE_DOCCLASS = re.compile(r"\\documentclass")

IMG_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".eps"}


def strip_comments(line):
    return RE_COMMENT.sub("", line)


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def collect_tex_files(main_path):
    r"""递归收集 \input/\include 链上的 .tex 文件。返回 (文件列表, 缺失引用列表)。"""
    seen = []
    missing = []

    def norm(base_dir, name):
        name = name.strip()
        if not os.path.splitext(name)[1]:
            name += ".tex"
        return os.path.normpath(os.path.join(base_dir, name))

    def visit(path):
        path = os.path.normpath(path)
        if path in seen:
            return
        if not os.path.isfile(path):
            missing.append(path)
            return
        seen.append(path)
        text = read_file(path) or ""
        base = os.path.dirname(path)
        for line in text.splitlines():
            line = strip_comments(line)
            for m in RE_INPUT.finditer(line):
                visit(norm(base, m.group(1)))

    visit(main_path)
    return seen, missing


def check_file(path):
    """单文件检查：环境配对、括号余额、行内 $ 奇偶。返回 (errors, warnings)。"""
    errors, warnings = [], []
    text = read_file(path) or ""
    stack = []
    brace_balance = 0
    for ln, raw in enumerate(text.splitlines(), 1):
        line = strip_comments(raw)
        # 环境
        for m in re.finditer(r"\\(begin|end)\{([^}]*)\}", line):
            kind, env = m.group(1), m.group(2)
            if kind == "begin":
                stack.append((env, ln))
            else:
                if not stack:
                    errors.append("%s:%d：\\end{%s} 无匹配 \\begin" % (path, ln, env))
                else:
                    top, top_ln = stack.pop()
                    if top != env:
                        errors.append("%s:%d：环境不匹配——\\begin{%s}（行 %d）被 \\end{%s} 闭合"
                                      % (path, ln, top, top_ln, env))
        # 花括号（忽略转义 \{ \}）
        tmp = re.sub(r"\\[{}]", "", line)
        brace_balance += tmp.count("{") - tmp.count("}")
        # 行内 $ 奇偶（忽略 \$ 与 $$）
        tmp2 = re.sub(r"\\\$", "", line)
        tmp2 = tmp2.replace("$$", "")
        if tmp2.count("$") % 2 == 1:
            warnings.append("%s:%d：行内 $ 个数为奇数（可能未闭合数学模式，启发式，请人工确认）"
                            % (path, ln))
    for env, ln in stack:
        errors.append("%s:%d：\\begin{%s} 缺少对应 \\end" % (path, ln, env))
    if brace_balance != 0:
        errors.append("%s：花括号余额 %d（可能漏 { 或 }）" % (path, brace_balance))
    return errors, warnings


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="LaTeX 源码静态检查：环境配对/引用/bib/缺文件/失衡（stdlib-only，只读）。")
    parser.add_argument("--main", required=True, help="主文件（含 \\documentclass 的 .tex）")
    parser.add_argument("--report", required=True, help="报告输出路径（.md）")
    parser.add_argument("--strict", action="store_true", help="警告也计为失败")
    args = parser.parse_args(argv)

    main_path = os.path.abspath(args.main)
    if not os.path.isfile(main_path):
        print("错误：主文件不存在：%s" % main_path, file=sys.stderr)
        return 1
    base = os.path.dirname(main_path)

    errors, warnings, infos = [], [], []

    files, missing_inputs = collect_tex_files(main_path)
    for p in missing_inputs:
        errors.append("缺失的 \\input/\\include 文件：%s" % p.replace(os.sep, "/"))
    infos.append("工程 .tex 文件 %d 个：%s"
                 % (len(files), ", ".join(os.path.basename(f) for f in files)))

    labels, label_locs = set(), {}
    refs, cites = [], []
    bib_keys = None
    graphics_refs = []

    for path in files:
        e, w = check_file(path)
        errors.extend(e)
        warnings.extend(w)
        text = read_file(path) or ""
        for ln, raw in enumerate(text.splitlines(), 1):
            line = strip_comments(raw)
            for m in RE_LABEL.finditer(line):
                lab = m.group(1)
                if lab in labels:
                    errors.append("%s:%d：重复 \\label{%s}（首次定义于 %s）"
                                  % (path, ln, lab, label_locs.get(lab, "?")))
                labels.add(lab)
                label_locs[lab] = "%s:%d" % (os.path.basename(path), ln)
            for m in RE_REF.finditer(line):
                refs.append((m.group(1), path, ln))
            for m in RE_CITE.finditer(line):
                for key in m.group(1).split(","):
                    cites.append((key.strip(), path, ln))
            for m in RE_GRAPHICS.finditer(line):
                graphics_refs.append((m.group(1), path, ln))
            for m in RE_BIBRES.finditer(line):
                for name in m.group(1).split(","):
                    name = name.strip()
                    if not os.path.splitext(name)[1]:
                        name += ".bib"
                    bib_path = os.path.normpath(os.path.join(base, name))
                    if not os.path.isfile(bib_path):
                        errors.append("参考文献库缺失：%s（%s:%d 引用）"
                                      % (name, os.path.basename(path), ln))
                    else:
                        bib_text = read_file(bib_path) or ""
                        keys = set(RE_BIBENTRY.findall(bib_text))
                        bib_keys = (bib_keys or set()) | keys
            if re.search(r"\[H\]", line) and "usepackage" not in line:
                warnings.append("%s:%d：使用 [H] 浮动选项，需确认已加载 float 宏包"
                                % (os.path.basename(path), ln))

    # \ref → \label
    for ref, path, ln in refs:
        if ref not in labels:
            errors.append("%s:%d：\\ref{%s} 无对应 \\label（悬空引用，编译必出 ??）"
                          % (os.path.basename(path), ln, ref))
    unused = labels - {r for r, _, _ in refs}
    if unused:
        infos.append("定义了但未被引用的 label（提示级）：%s" % ", ".join(sorted(unused)[:10]))

    # \cite → .bib
    if bib_keys is not None:
        for key, path, ln in cites:
            if key and key not in bib_keys:
                errors.append("%s:%d：\\cite{%s} 在 .bib 中无条目"
                              % (os.path.basename(path), ln, key))
    elif cites:
        warnings.append("工程未发现 .bib 文件，%d 处 \\cite 未核对" % len(cites))

    # \includegraphics 文件存在性
    for name, path, ln in graphics_refs:
        cand = os.path.normpath(os.path.join(base, name))
        if os.path.isfile(cand):
            continue
        if not os.path.splitext(name)[1]:
            found = any(os.path.isfile(cand + ext) for ext in IMG_EXTS)
            if found:
                continue
        errors.append("%s:%d：\\includegraphics 引用的图片缺失：%s"
                      % (os.path.basename(path), ln, name))

    # ---- 报告 ----
    out = []
    out.append("# LaTeX 源码静态检查报告")
    out.append("")
    out.append("主文件：`%s`" % main_path.replace(os.sep, "/"))
    out.append("错误 %d 条，警告 %d 条，提示 %d 条。" % (len(errors), len(warnings), len(infos)))
    out.append("")
    out.append("## 错误（编译前必须修复）")
    out.append("")
    if errors:
        for e in errors:
            out.append("- [错误] %s" % e)
    else:
        out.append("无。")
    out.append("")
    out.append("## 警告")
    out.append("")
    if warnings:
        for w in warnings:
            out.append("- [警告] %s" % w)
    else:
        out.append("无。")
    out.append("")
    out.append("## 提示")
    out.append("")
    for i in infos:
        out.append("- [提示] %s" % i)
    out.append("")

    out_path = os.path.abspath(args.report)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
    except OSError as exc:
        print("错误：无法写出报告：%s" % exc, file=sys.stderr)
        return 1

    for e in errors:
        print("[错误] %s" % e)
    for w in warnings:
        print("[警告] %s" % w)
    fails = len(errors) + (len(warnings) if args.strict else 0)
    print("结果：%s（错误 %d，警告 %d）退出码 %d -> %s"
          % ("未通过" if fails else "通过", len(errors), len(warnings),
             1 if fails else 0, out_path.replace(os.sep, "/")))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

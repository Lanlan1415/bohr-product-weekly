#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""术语一致性检查（文献翻译技能）：对照术语表扫描译文，强制执行锁定译名。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/term_consistency.py \
        --glossary /app/work/glossary.tsv \
        --translation /app/work/translation_draft.md \
        --source /app/work/source_paras.md \
        --report /app/work/term_report.md

术语表格式（UTF-8，三种行等价；# 开头为注释，空行忽略）：

    source term = 首选译名
    source term = 首选译名 ; 禁用变体1, 禁用变体2
    | source term | 首选译名 | 禁用变体1, 禁用变体2 |   # Markdown 表格行

检查规则（任一 FAIL 退出码为 1）：
  1. 禁用变体出现在译文中 → FAIL（给出行号，须回填为首选译名）；
  2. 提供 --source 时：英文源词在原文出现（词边界、不区分大小写），
     而首选译名在译文中 0 次出现 → FAIL（疑似漏译或用了未登记译名）；
  3. 首选译名 0 次出现且无原文可对照 → 仅 WARN（可能该术语本案例未用）。

（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json，未修复项记入 uncertainty / skipped_reason——退出码不作为交付门禁。
仅使用 Python 标准库；读取一律 utf-8-sig；不访问网络；不修改输入文件。
"""
import argparse
import os
import re
import sys


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("[term_consistency] 错误：无法读取 %s（%s）\n" % (path, exc))
        return None


def parse_glossary(text):
    """解析术语表，返回 [(source, preferred, [banned...]), ...]。"""
    entries = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0].lower() in ("source", "原文", "英文", "---", ":---"):
                continue
            if set(cells[0]) <= set("-: "):
                continue
            source, preferred = cells[0], cells[1]
            banned = [b.strip() for b in (cells[2].split(",") if len(cells) > 2 else []) if b.strip()]
        elif "=" in line:
            left, _, right = line.partition("=")
            source = left.strip()
            if ";" in right:
                pref, _, banned_str = right.partition(";")
                banned = [b.strip() for b in banned_str.split(",") if b.strip()]
            else:
                pref, banned = right, []
            preferred = pref.strip()
        else:
            sys.stderr.write("[term_consistency] 警告：第 %d 行无法解析，已跳过：%s\n" % (lineno, line))
            continue
        if source and preferred:
            entries.append((source, preferred, banned))
    return entries


def find_lines(text, needle, word_boundary=False):
    """返回 needle 在 text 中出现的行号列表（1 起）。"""
    hits = []
    if word_boundary and re.match(r"^[A-Za-z0-9][A-Za-z0-9 \-]*$", needle):
        pat = re.compile(r"\b%s\b" % re.escape(needle), re.IGNORECASE)
        for i, line in enumerate(text.splitlines(), start=1):
            if pat.search(line):
                hits.append(i)
    else:
        for i, line in enumerate(text.splitlines(), start=1):
            if needle in line:
                hits.append(i)
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser(description="术语一致性检查：对照术语表扫描译文")
    parser.add_argument("--glossary", required=True, help="术语表绝对路径")
    parser.add_argument("--translation", required=True, help="译文（或双语对照稿）绝对路径")
    parser.add_argument("--source", default=None, help="原文（可选；用于“原文出现但译名缺失”检查）")
    parser.add_argument("--report", default=None, help="检查报告输出路径（Markdown，可选）")
    args = parser.parse_args(argv)

    gloss_text = read_text(os.path.abspath(args.glossary))
    trans_text = read_text(os.path.abspath(args.translation))
    if gloss_text is None or trans_text is None:
        return 1
    source_text = None
    if args.source:
        source_text = read_text(os.path.abspath(args.source))
        if source_text is None:
            return 1

    entries = parse_glossary(gloss_text)
    if not entries:
        sys.stderr.write("[term_consistency] 错误：术语表中没有可解析的条目：%s\n" % args.glossary)
        return 1

    rows = []
    n_fail = n_warn = 0
    for source, preferred, banned in entries:
        pref_hits = find_lines(trans_text, preferred)
        status = "PASS"
        notes = []
        banned_all = []
        for b in banned:
            hits = find_lines(trans_text, b)
            if hits:
                banned_all.append((b, hits))
        if banned_all:
            status = "FAIL"
            for b, hits in banned_all:
                notes.append("禁用变体「%s」出现于行 %s" % (b, ", ".join(map(str, hits[:8]))))
        src_in_source = None
        if source_text is not None:
            src_in_source = bool(find_lines(source_text, source, word_boundary=True))
            if src_in_source and not pref_hits:
                status = "FAIL"
                notes.append("原文含「%s」但译文未出现锁定译名「%s」（漏译或未登记译名）"
                             % (source, preferred))
        if not pref_hits and not banned_all and not src_in_source:
            status = "WARN"
            notes.append("首选译名未出现且原文未检出该术语（本案例可能未用到）")
        rows.append({
            "source": source, "preferred": preferred,
            "pref_count": len(pref_hits),
            "banned": "; ".join(notes), "status": status,
        })
    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_warn = sum(1 for r in rows if r["status"] == "WARN")

    # 控制台输出
    for r in rows:
        print("[%s] %s = %s（首选 %d 次）%s"
              % (r["status"], r["source"], r["preferred"], r["pref_count"],
                 (" —— " + r["banned"]) if r["banned"] else ""))
    print("[term_consistency] 共 %d 条术语：PASS %d，WARN %d，FAIL %d"
          % (len(rows), len(rows) - n_warn - n_fail, n_warn, n_fail))

    # 报告文件
    if args.report:
        rep = ["# 术语一致性检查报告", "",
               "- 术语表：`%s`" % os.path.abspath(args.glossary).replace(os.sep, "/"),
               "- 译文：`%s`" % os.path.abspath(args.translation).replace(os.sep, "/"),
               "- 结果：FAIL %d / WARN %d / PASS %d（共 %d 条）"
               % (n_fail, n_warn, len(rows) - n_warn - n_fail, len(rows)), "",
               "| 原文术语 | 锁定译名 | 首选出现次数 | 状态 | 问题明细 |",
               "|---|---|---|---|---|"]
        for r in rows:
            rep.append("| %s | %s | %d | %s | %s |"
                       % (r["source"], r["preferred"], r["pref_count"], r["status"],
                          r["banned"].replace("|", "\\|") or "-"))
        rep.append("")
        rep.append("修复要求：FAIL 项必须回填为锁定译名后重跑本脚本；WARN 项人工确认即可。")
        rep.append("")
        try:
            rp = os.path.abspath(args.report)
            os.makedirs(os.path.dirname(rp), exist_ok=True)
            with open(rp, "w", encoding="utf-8") as fh:
                fh.write("\n".join(rep))
            print("[term_consistency] 报告已写入 %s" % rp)
        except OSError as exc:
            sys.stderr.write("[term_consistency] 错误：报告不可写：%s\n" % exc)
            return 1

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

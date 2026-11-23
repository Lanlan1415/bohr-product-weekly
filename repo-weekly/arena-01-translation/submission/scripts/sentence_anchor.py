#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""句级锚定审计（文献翻译技能）：核对"先定位原句再译、译文逐句回链原句"的
锚定记录，并做来源清点（source inventory）+ 对齐审计（alignment audit）。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/sentence_anchor.py \
        --anchors /app/work/sentence_anchors.md \
        --source /app/work/source_paras.md \
        --report /app/work/anchor_report.md

锚定记录格式（每行一句，# 开头为注释，空行忽略）：

    [P003-S01] [p.2] The band gap was 3.37 eV. || 带隙为 3.37 eV。

  - [P###-S##]：句级锚号 = 段号 P### + 段内句号 S##（译文逐句回链原句的凭据）；
  - [p.N]：该原句所在物理页码；
  - `||` 左侧为原句（逐字）、右侧为译文；公式/文献条目等不译内容右侧写
    `[NOT_TRANSLATED: 原因]`。

检查规则（任一 FAIL 退出码为 1）：
  1. 锚定行格式不合法（缺锚号/缺页码/缺 `||` 分隔）→ FAIL；
  2. 原句侧或译文侧为空 → FAIL（漏译句/漏锚，等价于"漏段却报 complete"的句级形态）；
  3. 锚号重复 → FAIL；
  4. 锚号引用的段号在 source_paras.md 中不存在 → FAIL（编号漂移）；
  5. 来源清点 + 对齐审计：source_paras.md 中**零锚句**的段 → FAIL
     （该段一句都没译，却可能在交付中声称 complete）；
  6. 锚号（段号, 句号）序列倒退 → FAIL（错位）；
  7. 译文侧无汉字且原句侧含 ≥5 个字母、又非公式/编号行 → WARN（疑似未译）；
  8. 页码序列倒退 → WARN（多栏/顺序风险，提醒复核栏序）。

（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json，未修复项记入 uncertainty / skipped_reason——退出码不作为交付门禁。
仅使用 Python 标准库；读取一律 utf-8-sig；不访问网络；不修改输入文件。
"""
import argparse
import os
import re
import sys

RE_ANCHOR = re.compile(
    r"^\s*\[P(\d{3,})-S(\d{1,3})\]\s*\[p\.(\d+)\]\s*(.*?)\s*\|\|\s*(.*?)\s*$")
RE_ANY_ANCHORISH = re.compile(r"^\s*\[P\d{3,}[-–]S")
RE_PARA_TAG = re.compile(r"\[P(\d{3,})\]")
RE_FORMULAISH = re.compile(r"^[\s\W\dx^_{}()+\-*/=.,;:<>≤≥±×÷^%$\[\]\\|]*$")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("[sentence_anchor] 错误：无法读取 %s（%s）\n" % (path, exc))
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="句级锚定审计：sentence_id + 原文 + 译文 + 页码 逐句回链核对")
    parser.add_argument("--anchors", required=True, help="句级锚定记录绝对路径")
    parser.add_argument("--source", default=None,
                        help="原文分段稿绝对路径（可选；提供时做来源清点与对齐审计）")
    parser.add_argument("--report", default=None, help="审计报告输出路径（Markdown，可选）")
    args = parser.parse_args(argv)

    anchors_text = read_text(os.path.abspath(args.anchors))
    if anchors_text is None:
        return 1
    source_text = None
    if args.source:
        source_text = read_text(os.path.abspath(args.source))
        if source_text is None:
            return 1

    issues = []  # (级别 FAIL/WARN, 描述)
    anchors = []  # (pnum, snum, page, src, tgt, lineno)
    for lineno, raw in enumerate(anchors_text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = RE_ANCHOR.match(line)
        if not m:
            if RE_ANY_ANCHORISH.match(line) or "||" in line:
                issues.append(("FAIL", "第 %d 行锚定格式不合法：%s"
                               % (lineno, line[:60])))
            continue
        pnum, snum, page, src, tgt = (int(m.group(1)), int(m.group(2)),
                                      int(m.group(3)), m.group(4), m.group(5))
        if not src.strip():
            issues.append(("FAIL", "锚号 P%03d-S%02d 原句侧为空（漏锚）" % (pnum, snum)))
        if not tgt.strip():
            issues.append(("FAIL", "锚号 P%03d-S%02d 译文侧为空（漏译句）" % (pnum, snum)))
        anchors.append((pnum, snum, page, src, tgt, lineno))

    if not anchors:
        issues.append(("FAIL", "未解析到任何合法锚定行（格式见脚本文档字符串）"))

    seen = set()
    for pnum, snum, page, src, tgt, lineno in anchors:
        key = (pnum, snum)
        if key in seen:
            issues.append(("FAIL", "锚号重复：P%03d-S%02d" % key))
        seen.add(key)

    keys = [(p, s) for p, s, _pg, _s, _t, _ln in anchors]
    if keys != sorted(keys):
        for i in range(1, len(keys)):
            if keys[i] < keys[i - 1]:
                issues.append(("FAIL", "锚号顺序错位：P%03d-S%02d 出现在 P%03d-S%02d 之后"
                               % (keys[i] + keys[i - 1])))
                break

    pages = [pg for _p, _s, pg, _src, _t, _ln in anchors]
    if pages != sorted(pages):
        issues.append(("WARN", "页码序列倒退（疑似多栏/顺序风险）：请复核栏序后再定锚"))

    for pnum, snum, page, src, tgt, lineno in anchors:
        if tgt.startswith("[NOT_TRANSLATED"):
            continue
        cjk = re.findall(r"[一-鿿]", tgt)
        letters = re.findall(r"[A-Za-z]", src)
        if not cjk and len(letters) >= 5 and not RE_FORMULAISH.match(src):
            issues.append(("WARN", "锚号 P%03d-S%02d 译文侧无汉字（疑似未译或非中英任务，"
                                   "请确认）" % (pnum, snum)))

    if source_text is not None:
        src_paras = sorted(set(int(t) for t in RE_PARA_TAG.findall(source_text)))
        anchored = sorted({p for p, _s, _pg, _src, _t, _ln in anchors})
        src_set, anc_set = set(src_paras), set(anchored)
        for p in sorted(anc_set - src_set):
            issues.append(("FAIL", "锚号引用不存在的段号 P%03d（编号漂移）" % p))
        for p in sorted(src_set - anc_set):
            issues.append(("FAIL", "段 P%03d 零锚句（该段一句都没译——"
                                   "漏段却报 complete 的句级形态）" % p))

    n_fail = sum(1 for lv, _ in issues if lv == "FAIL")
    n_warn = sum(1 for lv, _ in issues if lv == "WARN")

    print("[sentence_anchor] 锚句 %d 条，覆盖段落 %d 个"
          % (len(anchors), len({p for p, _s, _pg, _src, _t, _ln in anchors})))
    for lv, msg in issues:
        print("[%s] %s" % (lv, msg))
    if not issues:
        print("[PASS] 句级锚定齐全：逐句回链、来源清点与对齐审计一致")
    print("[sentence_anchor] FAIL %d，WARN %d" % (n_fail, n_warn))

    if args.report:
        rep = ["# 句级锚定审计报告", "",
               "- 锚定记录：`%s`（%d 条）"
               % (os.path.abspath(args.anchors).replace(os.sep, "/"), len(anchors)),
               "- 原文分段稿：`%s`"
               % (os.path.abspath(args.source).replace(os.sep, "/")
                  if args.source else "（未提供，跳过来源清点）"),
               "- 结果：FAIL %d / WARN %d" % (n_fail, n_warn), "",
               "| 级别 | 问题 |", "|---|---|"]
        for lv, msg in issues:
            rep.append("| %s | %s |" % (lv, msg.replace("|", "\\|")))
        if not issues:
            rep.append("| PASS | 逐句回链、来源清点与对齐审计一致 |")
        rep.append("")
        rep.append("修复要求：零锚句段补译并补锚、空译文补齐、错位锚号按原文顺序重排后重跑本脚本。")
        rep.append("")
        try:
            rp = os.path.abspath(args.report)
            os.makedirs(os.path.dirname(rp), exist_ok=True)
            with open(rp, "w", encoding="utf-8") as fh:
                fh.write("\n".join(rep))
            print("[sentence_anchor] 报告已写入 %s" % rp)
        except OSError as exc:
            sys.stderr.write("[sentence_anchor] 错误：报告不可写：%s\n" % exc)
            return 1

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

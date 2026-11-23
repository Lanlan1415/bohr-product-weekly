#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""段号对齐核对（文献翻译技能）：核对原文与双语译文的 [P###] 段号一一对应。

用法（一律用绝对路径调用，不依赖当前工作目录 CWD）：

    python3 /skills/weekly-skill/scripts/align_check.py \
        --source /app/work/source_paras.md \
        --translation /app/work/translation_draft.md \
        --report /app/work/align_report.md

约定：原文分段稿与译文稿中，每个段落以 `[P001]`、`[P002]`…… 形式的段号标记开头
（可用 --tag-pattern 自定义正则，第一个捕获组为段号数字）。

检查规则（任一 FAIL 退出码为 1）：
  1. 原文出现的段号在译文中缺失 → FAIL（漏译）；
  2. 译文出现原文没有的段号 → FAIL（多译/编号漂移）；
  3. 任一侧段号重复出现 → FAIL；
  4. 译文段号的先后顺序与原文不一致 → FAIL（错位）；
  5. 段号编号不连续（如 P001 之后直接 P003）→ WARN；
  6. 译文除段号外无实际汉字内容 → FAIL（空壳对照）。

（v3）退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付
result.json，未修复项记入 uncertainty / skipped_reason——退出码不作为交付门禁。
仅使用 Python 标准库；读取一律 utf-8-sig；不访问网络；不修改输入文件。
"""
import argparse
import os
import re
import sys

DEFAULT_TAG = r"\[P(\d{3,})\]"


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("[align_check] 错误：无法读取 %s（%s）\n" % (path, exc))
        return None


def extract_tags(text, pattern):
    """按出现顺序提取段号列表（字符串形式，保留前导零）。"""
    return re.findall(pattern, text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="段号对齐核对：原文与译文 [P###] 一一对应")
    parser.add_argument("--source", required=True, help="原文分段稿绝对路径")
    parser.add_argument("--translation", required=True, help="译文/双语对照稿绝对路径")
    parser.add_argument("--report", default=None, help="核对报告输出路径（Markdown，可选）")
    parser.add_argument("--tag-pattern", default=DEFAULT_TAG,
                        help="段号正则（第一个捕获组为数字），默认 %s" % DEFAULT_TAG)
    args = parser.parse_args(argv)

    src = read_text(os.path.abspath(args.source))
    tra = read_text(os.path.abspath(args.translation))
    if src is None or tra is None:
        return 1

    try:
        pattern = re.compile(args.tag_pattern)
    except re.error as exc:
        sys.stderr.write("[align_check] 错误：段号正则非法：%s\n" % exc)
        return 1

    src_tags = extract_tags(src, pattern)
    tra_tags = extract_tags(tra, pattern)

    issues = []  # (级别 FAIL/WARN, 描述)
    if not src_tags:
        issues.append(("FAIL", "原文中未找到任何段号标记（模式 %s）" % args.tag_pattern))
    if not tra_tags:
        issues.append(("FAIL", "译文中未找到任何段号标记"))

    def dupes(tags):
        seen, d = set(), []
        for t in tags:
            if t in seen and t not in d:
                d.append(t)
            seen.add(t)
        return d

    for t in dupes(src_tags):
        issues.append(("FAIL", "原文段号重复：P%s" % t))
    for t in dupes(tra_tags):
        issues.append(("FAIL", "译文段号重复：P%s" % t))

    src_set, tra_set = set(src_tags), set(tra_tags)
    missing = [t for t in src_tags if t not in tra_set]
    extra = [t for t in tra_tags if t not in src_set]
    for t in sorted(set(missing)):
        issues.append(("FAIL", "译文缺失段号 P%s（漏译）" % t))
    for t in sorted(set(extra)):
        issues.append(("FAIL", "译文多出段号 P%s（原文没有，疑似编号漂移）" % t))

    common_src = [t for t in src_tags if t in tra_set]
    common_tra = [t for t in tra_tags if t in src_set]
    if common_src != common_tra:
        for i, (a, b) in enumerate(zip(common_src, common_tra)):
            if a != b:
                issues.append(("FAIL",
                               "段号顺序错位：第 %d 个公共段号原文为 P%s、译文为 P%s" % (i + 1, a, b)))
                break
        else:
            issues.append(("FAIL", "段号顺序不一致（公共前缀相同但整体错位）"))

    src_nums = sorted(int(t) for t in src_set)
    if src_nums:
        expected = list(range(src_nums[0], src_nums[0] + len(src_nums)))
        if src_nums != expected:
            gaps = sorted(set(expected) - set(src_nums))
            issues.append(("WARN", "原文段号编号不连续，缺：%s"
                           % ", ".join("P%03d" % g for g in gaps)))

    cjk = re.findall(r"[一-鿿]", re.sub(pattern, "", tra))
    if tra_tags and len(cjk) < 10:
        issues.append(("FAIL", "译文除段号外几乎没有汉字内容（疑似空壳对照稿）"))

    n_fail = sum(1 for lv, _ in issues if lv == "FAIL")
    n_warn = sum(1 for lv, _ in issues if lv == "WARN")

    print("[align_check] 原文段号 %d 个，译文段号 %d 个" % (len(src_tags), len(tra_tags)))
    for lv, msg in issues:
        print("[%s] %s" % (lv, msg))
    if not issues:
        print("[PASS] 段号一一对应、顺序一致、编号连续")
    print("[align_check] FAIL %d，WARN %d" % (n_fail, n_warn))

    if args.report:
        rep = ["# 段号对齐核对报告", "",
               "- 原文：`%s`（%d 个段号）" % (os.path.abspath(args.source).replace(os.sep, "/"), len(src_tags)),
               "- 译文：`%s`（%d 个段号）" % (os.path.abspath(args.translation).replace(os.sep, "/"), len(tra_tags)),
               "- 结果：FAIL %d / WARN %d" % (n_fail, n_warn), "",
               "| 级别 | 问题 |", "|---|---|"]
        for lv, msg in issues:
            rep.append("| %s | %s |" % (lv, msg.replace("|", "\\|")))
        if not issues:
            rep.append("| PASS | 段号一一对应、顺序一致、编号连续 |")
        rep.append("")
        rep.append("修复要求：漏译段补齐、多译段删除、错位段按原文顺序重排后重跑本脚本。")
        rep.append("")
        try:
            rp = os.path.abspath(args.report)
            os.makedirs(os.path.dirname(rp), exist_ok=True)
            with open(rp, "w", encoding="utf-8") as fh:
                fh.write("\n".join(rep))
            print("[align_check] 报告已写入 %s" % rp)
        except OSError as exc:
            sys.stderr.write("[align_check] 错误：报告不可写：%s\n" % exc)
            return 1

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

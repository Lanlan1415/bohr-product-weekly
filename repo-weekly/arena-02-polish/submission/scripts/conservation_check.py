#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守恒门（conservation gate）：对比原文与润色稿，报告任何不应变化项的不一致。

硬检查（不一致即 FAIL，退出码 1）：
1. 数字：数值 token（含小数、千分位、科学计数、百分号）的多重集合必须一致；
2. 引用标记：[12]、[3-5]、[S2] 等方括号标记逐一对应；
3. 图表/公式编号：Figure 1 / Fig. 2 / Table 3 / Eq. 4 / 图1 / 表2 / 式(3)；
4. 公式：LaTeX 行内 $...$ 与行间 $$...$$ / \\(...\\) / \\[...\\] 逐字一致；
5. 术语表：--terms 给定术语（每行一个）在两文中出现次数必须一致
   （术语表=已批准的最终写法；改法不同说明术语被擅动）。

软检查（只警告不 FAIL）：
- 限定词（may/suggest/approximately/可能/约…）与否定词计数变化：
  提示"限定强度/结论方向可能漂移"，需人工逐处核对并在修改记录中说明。

用法：
    python conservation_check.py --original /app/work/original.md \
        --polished /app/output/polished.md \
        [--terms /app/work/terms.txt] [--report /app/work/conservation_report.md]

退出码：0 = 硬检查全过；1 = 存在硬不一致。
退出码 1 仅表示存在建议修复项；无论退出码如何，都应照常交付 result.json
并在 uncertainty 中记录未修复项——本脚本不充当交付门禁。
stdlib-only，utf-8-sig 读文件，只读输入文件，不依赖 CWD，不联网。
"""

import argparse
import os
import re
import sys
from collections import Counter

RE_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?:\s*[eE][+-]?\d+)?%?")
RE_CITE = re.compile(r"\[(?:[Ss]?\d+)(?:\s*[-–,]\s*[Ss]?\d+)*\]")
RE_FIGTAB = re.compile(
    r"(?i)\b(?:fig(?:ure)?s?|tables?|eq(?:uation)?s?)\.?\s*\(?\s*\d{1,3}[a-z]?\s*\)?"
    r"|[图表式]\s*\(?\s*\d{1,3}\s*\)?")
RE_FORMULA = [
    re.compile(r"\$\$.+?\$\$", re.DOTALL),
    re.compile(r"\\\(.+?\\\)", re.DOTALL),
    re.compile(r"\\\[.+?\\\]", re.DOTALL),
    re.compile(r"(?<!\$)\$(?!\$)[^$\n]+?\$(?!\$)"),
]

HEDGES_EN = ["may", "might", "could", "suggest", "suggests", "suggested",
             "indicate", "indicates", "indicated", "approximately", "likely",
             "possibly", "potentially", "appears", "appear", "seem", "seems",
             "roughly", "about"]
HEDGES_ZH = ["可能", "大约", "约", "或许", "一定程度上", "有望", "似乎", "大致"]
NEG_EN = ["not", "no", "never", "neither", "without", "hardly", "scarcely"]
NEG_ZH = ["不", "无", "未", "没有", "并非", "无法", "毫不", "难以"]


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def counter_diff(a, b):
    """返回 (a 比 b 多的项, b 比 a 多的项) 两个 Counter。"""
    only_a = a - b
    only_b = b - a
    return only_a, only_b


def fmt_diff(only_a, only_b, limit=15):
    parts = []
    for tok, n in list(only_a.items())[:limit]:
        parts.append("原文有 %d 处而润色稿缺失：%r" % (n, tok))
    for tok, n in list(only_b.items())[:limit]:
        parts.append("润色稿多出 %d 处：%r" % (n, tok))
    return parts


def count_words(text, words, zh=False):
    c = 0
    if zh:
        for w in words:
            c += text.count(w)
    else:
        for w in words:
            c += len(re.findall(r"(?i)\b%s\b" % re.escape(w), text))
    return c


def extract_formulas(text):
    found = []
    occupied = []
    for pat in RE_FORMULA:
        for m in pat.finditer(text):
            span = m.span()
            if any(s <= span[0] < e or s < span[1] <= e for s, e in occupied):
                continue
            occupied.append(span)
            found.append(" ".join(m.group(0).split()))
    return Counter(found)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="润色守恒门：数字/术语/引用/图表编号/公式逐字一致性检查")
    parser.add_argument("--original", required=True, help="原文文件")
    parser.add_argument("--polished", required=True, help="润色稿文件")
    parser.add_argument("--terms", default=None, help="术语表（每行一个术语，# 开头为注释）")
    parser.add_argument("--report", default=None, help="Markdown 报告输出路径（可选）")
    args = parser.parse_args(argv)

    try:
        orig = read_text(os.path.abspath(args.original))
        pol = read_text(os.path.abspath(args.polished))
    except OSError as exc:
        print("[FAIL] 读取输入失败：%s" % exc)
        return 1

    errors, warnings = [], []

    def hard_check(name, c_orig, c_pol):
        if c_orig != c_pol:
            only_o, only_p = counter_diff(c_orig, c_pol)
            errors.append("【%s】不一致：" % name)
            errors.extend("  " + s for s in fmt_diff(only_o, only_p))

    # 1. 数字（去掉千分位逗号后比较；先剔除引用标记，避免 [2,3] 被当成数字）
    norm = lambda c: Counter({t.replace(",", ""): n for t, n in c.items()})
    orig_nocite = RE_CITE.sub(" ", orig)
    pol_nocite = RE_CITE.sub(" ", pol)
    hard_check("数字", norm(Counter(RE_NUMBER.findall(orig_nocite))),
               norm(Counter(RE_NUMBER.findall(pol_nocite))))
    # 2. 引用标记
    hard_check("引用标记", Counter(t.replace(" ", "") for t in RE_CITE.findall(orig)),
               Counter(t.replace(" ", "") for t in RE_CITE.findall(pol)))
    # 3. 图表/公式编号（大小写归一、去多余空白）
    def norm_ref(t):
        return " ".join(t.casefold().split()).replace(" ", "")
    hard_check("图表/公式编号", Counter(norm_ref(t) for t in RE_FIGTAB.findall(orig)),
               Counter(norm_ref(t) for t in RE_FIGTAB.findall(pol)))
    # 4. 公式
    hard_check("公式（LaTeX 段）", extract_formulas(orig), extract_formulas(pol))
    # 5. 术语表
    if args.terms:
        try:
            with open(os.path.abspath(args.terms), "r", encoding="utf-8-sig") as f:
                terms = [ln.strip() for ln in f
                         if ln.strip() and not ln.startswith("#")]
        except OSError as exc:
            errors.append("【术语表】读取失败：%s" % exc)
            terms = []
        bad_terms = []
        for t in terms:
            co, cp = orig.count(t), pol.count(t)
            if co != cp:
                bad_terms.append("  术语 %r：原文 %d 次 → 润色稿 %d 次" % (t, co, cp))
        if bad_terms:
            errors.append("【术语表】出现次数不一致（批准术语必须逐字保留）：")
            errors.extend(bad_terms)

    # 软检查：限定词与否定词
    for name, words, zh in (("限定词(英)", HEDGES_EN, False),
                            ("限定词(中)", HEDGES_ZH, True),
                            ("否定词(英)", NEG_EN, False),
                            ("否定词(中)", NEG_ZH, True)):
        co, cp = count_words(orig, words, zh), count_words(pol, words, zh)
        if co != cp:
            warnings.append("%s计数变化：原文 %d → 润色稿 %d；"
                            "限定强度/结论方向可能漂移，请逐处人工核对并在修改记录说明"
                            % (name, co, cp))

    # 汇总
    print("=" * 60)
    print("守恒门检查报告（原文 vs 润色稿）")
    print("=" * 60)
    print("原文：%s（%d 字符）" % (args.original, len(orig)))
    print("润色稿：%s（%d 字符）" % (args.polished, len(pol)))
    if errors:
        for e in errors:
            print("[FAIL] %s" % e)
    else:
        print("[PASS] 数字 / 引用标记 / 图表公式编号 / 公式 / 术语 全部守恒")
    for w in warnings:
        print("[WARN] %s" % w)
    print("结果：%s（硬错误 %d，警告 %d）"
          % ("未通过" if errors else "通过", len(errors), len(warnings)))

    if args.report:
        rep = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(rep) or ".", exist_ok=True)
        with open(rep, "w", encoding="utf-8") as f:
            f.write("# 守恒门检查报告\n\n")
            f.write("- 原文：`%s`\n- 润色稿：`%s`\n\n" % (args.original, args.polished))
            f.write("## 硬不一致（%d）\n\n" % len(errors))
            for e in errors:
                f.write("- %s\n" % e)
            f.write("\n## 警告（%d）\n\n" % len(warnings))
            for w in warnings:
                f.write("- %s\n" % w)
        print("[OK] 报告已写入 %s" % rep)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

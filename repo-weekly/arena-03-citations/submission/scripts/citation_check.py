#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citation_check.py — 正文引用标记与文末文献表一一对应校验（stdlib-only）。

覆盖题面「挂得对 / 编得顺 / 对得上」中的确定性环节：
  1. 提取正文顺序编码制 [n] / [n,m] / [n-m] 或著者-出版年制 (Author, Year) 标记；
  2. 与文末文献表交叉核对：引而无目（缺条目）、有目无引（未引用）、序号断号；
  3. 顺序编码制：首次出现顺序与编号一致性（错位检测）；
  4. GB/T 7714 条目字段 lint：缺年份 / 缺类型标识 / 缺页码卷期 / 中文条目误用
     et al. / 全半角标点混用 / DOI 形态异常。
缺失字段只报告并建议显式标注（如「[缺: 页码]」），本脚本绝不编造补齐。

用法（绝对路径调用，不依赖 CWD，只读输入文件）：
  # 文献表在稿件末尾「参考文献」节内：
  python3 /skills/weekly-skill/scripts/citation_check.py \
      --manuscript /app/output/manuscript_revised.md \
      --output /app/output/citation_check_report.md
  # 文献表在单独文件：
  python3 /skills/weekly-skill/scripts/citation_check.py \
      --manuscript /app/work/draft.md --refs /app/work/reflist.md \
      --style numeric --output /app/output/citation_check_report.md

退出码：0 = 无 ERROR（允许 WARN）；1 = 存在 ERROR 或输入不可读。
"""
import argparse
import os
import re
import sys

REF_HEADING = re.compile(
    r"^[#\s\d\.、]*(?:参考文献|REFERENCES?|References)\s*[:：]?\s*$", re.M)

# 正文数字标记：[1] [1,2] [1, 3-5]（方括号内必须全为数字/分隔符，排除 [J] 等类型标识）
NUM_MARK = re.compile(r"\[(\d[\d\s,，、\-–—]*)\]")
# 含年份的圆括号（中英文）
PAREN = re.compile(r"[\(（]([^()（）]*?(?:19|20)\d{2}[a-z]?[^()（）]*?)[\)）]")
# 圆括号内单个「作者, 年」片段
AY_ITEM = re.compile(
    r"^\s*([A-Za-zÀ-ɏ'\-\. ]+|[一-鿿]{2,10}?)"
    r"(?:\s+et\s+al\.?|\s*等)?"
    r"(?:\s+(?:and|&|和|与)\s+[A-Za-zÀ-ɏ'\-\. ]+)?"
    r"\s*[,，]\s*((?:19|20)\d{2})[a-z]?\s*$")
# 文末编号条目：[1] ... 或 1. ... 或 1、...
NUM_ENTRY = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.、\)])\s+(\S.*)$")
YEAR = re.compile(r"(?:19|20)\d{2}")
DOI = re.compile(r"10\.\d{4,9}/[^\s,，;；\]\)]+")
GBT_TYPE = re.compile(r"\[(J|M|C|D|R|S|P|N|G|A|Z|EB/OL|DB/OL|CP/DK|J/OL|M/OL|C/OL|N/OL)\]")
PAGERANGE = re.compile(r"[:：]\s*\d+\s*[-–—]\s*\d+|\b\d+\s*[-–—]\s*\d+\s*$")
VOLISSUE = re.compile(r"\d+\s*\(\s*\d+\s*\)")
CJK = re.compile(r"[一-鿿]")


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def split_body_refs(text):
    """把全文切成正文与文献表两段；无标题时返回 (全文, '')。"""
    m = None
    for m in REF_HEADING.finditer(text):
        pass  # 取最后一个匹配的标题，避免正文中提及「参考文献」被误切
    if m is None:
        return text, ""
    return text[:m.start()], text[m.end():]


def expand_num_token(tok):
    """'1, 3-5' -> {1,3,4,5}；无法解析的片段忽略。"""
    out = set()
    for part in re.split(r"[,，、]", tok):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-–—]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b <= 9999 and b - a <= 500:
                out.update(range(a, b + 1))
        elif part.isdigit():
            out.add(int(part))
    return out


def extract_numeric(body):
    """返回 (出现序列[(编号,位置)], 集合)。"""
    seq = []
    used = set()
    for m in NUM_MARK.finditer(body):
        nums = expand_num_token(m.group(1))
        for n in sorted(nums):
            seq.append((n, m.start()))
        used |= nums
    return seq, used


def author_key(name):
    name = name.strip().strip(",，")
    if CJK.search(name):
        return name.replace(" ", "")
    return name.split()[0].lower().strip(".,'")


def extract_authoryear(body):
    """返回 (出现序列[(key,year)], 集合)。"""
    seq = []
    used = set()
    for pm in PAREN.finditer(body):
        inner = pm.group(1)
        for seg in re.split(r"[;；]", inner):
            im = AY_ITEM.match(seg)
            if im:
                k, y = author_key(im.group(1)), im.group(2)
                seq.append(((k, y), pm.start()))
                used.add((k, y))
    return seq, used


def parse_numeric_entries(refs_text):
    """返回 {编号: 条目文本}（保留首次出现）。"""
    entries = {}
    cur_no, cur_buf = None, []
    for line in refs_text.splitlines():
        m = NUM_ENTRY.match(line)
        if m:
            if cur_no is not None:
                entries.setdefault(cur_no, " ".join(cur_buf).strip())
            cur_no = int(m.group(1) or m.group(2))
            cur_buf = [m.group(3)]
        elif line.strip() and cur_no is not None:
            cur_buf.append(line.strip())
    if cur_no is not None:
        entries.setdefault(cur_no, " ".join(cur_buf).strip())
    return entries


def parse_authoryear_entries(refs_text):
    """按行解析著者-出版年条目，返回 {（key,year): 行文本} 与重复键列表。"""
    entries, dups = {}, []
    for line in refs_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("|"):
            continue
        ym = YEAR.search(line)
        am = re.match(r"([A-Za-zÀ-ɏ'\-\.]+|[一-鿿]{2,4})", line)
        if not (ym and am):
            continue
        key = (author_key(am.group(1)), ym.group(0))
        if key in entries:
            dups.append(key)
        entries.setdefault(key, line)
    return entries, dups


def lint_gbt_entry(no, text):
    """GB/T 7714 条目级 lint，返回 (级别, 信息) 列表。只报告，不补写。"""
    issues = []
    if not YEAR.search(text):
        issues.append(("ERROR", "缺年份——请显式标注「[缺: 年份]」，不得编造"))
    tm = GBT_TYPE.search(text)
    if not tm:
        issues.append(("WARN", "缺文献类型标识（[J]/[M]/[D] 等），按 GB/T 7714—2015 应著录"))
    elif tm.group(1).startswith("J"):
        if not PAGERANGE.search(text):
            issues.append(("WARN", "期刊条目缺起止页码——如原文确实无页码，标注「[缺: 页码]」"))
        if not VOLISSUE.search(text):
            issues.append(("WARN", "期刊条目缺卷(期)信息——如确无卷期，标注「[缺: 卷期]」"))
    if CJK.search(text) and re.search(r"\bet\s+al\.?", text):
        issues.append(("WARN", "中文文献应使用「等」而非「et al.」"))
    if ("，" in text or "．" in text) and re.search(r"[a-zA-Z0-9], ", text):
        issues.append(("WARN", "全角与半角标点混用，GB/T 7714 著录统一用半角标点"))
    for dm in DOI.finditer(text):
        doi = dm.group(0).rstrip(".。;,，;；)）]")
        if not re.match(r"10\.\d{4,9}/\S{3,}$", doi):
            issues.append(("WARN", "DOI 形态可疑: %s（请核验，不要自行改写）" % doi))
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="正文引用标记与文末文献表一一对应校验（缺引/多引/断号/错位 + GB/T 7714 字段 lint）。")
    ap.add_argument("--manuscript", required=True, help="稿件文件（utf-8 文本）绝对路径")
    ap.add_argument("--refs", default=None,
                    help="文献表单独文件；缺省时从 --manuscript 的「参考文献」节切分")
    ap.add_argument("--style", choices=["auto", "numeric", "author-year"], default="auto",
                    help="引用制式，默认 auto 自动判定")
    ap.add_argument("--gbt", action="store_true", default=True,
                    help="启用 GB/T 7714 条目 lint（默认开启）")
    ap.add_argument("--output", required=True, help="校验报告 markdown 输出绝对路径")
    args = ap.parse_args(argv)

    for p in [args.manuscript] + ([args.refs] if args.refs else []):
        if not os.path.isfile(p):
            print("[FAIL] 输入文件不存在: %s" % p)
            return 1
    try:
        ms_text = read_text(args.manuscript)
        refs_text = read_text(args.refs) if args.refs else None
    except OSError as e:
        print("[FAIL] 输入读取失败: %s" % e)
        return 1

    if refs_text is None:
        body, refs_text = split_body_refs(ms_text)
        if not refs_text.strip():
            print("[FAIL] 未在稿件中找到「参考文献」节，且未提供 --refs；无法交叉核对")
            return 1
    else:
        body = ms_text

    errors, warns, infos = [], [], []

    num_seq, num_used = extract_numeric(body)
    ay_seq, ay_used = extract_authoryear(body)
    style = args.style
    if style == "auto":
        style = "numeric" if num_used or not ay_used else "author-year"

    if style == "numeric":
        entries = parse_numeric_entries(refs_text)
        listed = set(entries)
        if not num_used:
            errors.append("正文未检出任何 [n] 引用标记")
        if not listed:
            errors.append("文献表未解析出任何编号条目（期望 [n] 或 n. 开头）")
        for n in sorted(num_used - listed):
            errors.append("引而无目：正文引用了 [%d]，但文献表无此条目" % n)
        for n in sorted(listed - num_used):
            errors.append("有目无引：文献表条目 [%d] 在正文中从未被引用" % n)
        if listed:
            expect = set(range(1, max(listed) + 1))
            gaps = sorted(expect - listed)
            if gaps:
                errors.append("序号断号：文献表编号不连续，缺 %s" %
                              ", ".join("[%d]" % g for g in gaps))
        # 顺序编码制：第 k 个首次出现的编号应为 k
        seen, order_ok = set(), True
        for n, pos in num_seq:
            if n in seen:
                continue
            seen.add(n)
            if n != len(seen):
                errors.append(
                    "序号错位：第 %d 个首次出现的引用是 [%d]，顺序编码制要求按首次出现顺序编号"
                    % (len(seen), n))
                order_ok = False
                break
        if args.gbt:
            for n in sorted(entries):
                for level, msg in lint_gbt_entry(n, entries[n]):
                    (errors if level == "ERROR" else warns).append("[%d] %s" % (n, msg))
    else:  # author-year
        entries, dups = parse_authoryear_entries(refs_text)
        listed = set(entries)
        for k in sorted(dups):
            warns.append("文献表存在同第一作者同年的多条目 %s%s，正文需用 %sa/%sb 区分"
                         % (k[0], k[1], k[1], k[1]))
        if not ay_used:
            errors.append("正文未检出任何 (Author, Year) 引用标记")
        for k in sorted(ay_used - listed):
            errors.append("引而无目：正文引用 (%s, %s)，文献表无对应条目" % k)
        for k in sorted(listed - ay_used):
            errors.append("有目无引：文献表条目 (%s, %s) 在正文中从未被引用" % k)

    # 汇总报告
    L = []
    L.append("# 引用—文献对应校验报告")
    L.append("")
    L.append("- 稿件: `%s`" % args.manuscript)
    L.append("- 文献表: `%s`" % (args.refs or "（取自稿件「参考文献」节）"))
    L.append("- 引用制式: %s" % ("顺序编码制" if style == "numeric" else "著者-出版年制"))
    L.append("- 结论: ERROR %d 项 / WARN %d 项 -> **%s**"
             % (len(errors), len(warns), "FAIL" if errors else "PASS"))
    L.append("")
    L.append("## ERROR（必须修复或显式说明）")
    L += ["%d. %s" % (i, e) for i, e in enumerate(errors, 1)] or ["（无）"]
    L.append("")
    L.append("## WARN（按 GB/T 7714 与任务规范建议处理）")
    L += ["%d. %s" % (i, w) for i, w in enumerate(warns, 1)] or ["（无）"]
    L.append("")
    L.append("## 处理原则")
    L.append("- 缺年份/页码/卷期/DOI：显式标注「[缺: 字段名]」并列入待确认清单，**不得编造**。")
    L.append("- 引而无目：回到原始文献库定位真实条目后补录；定位不到则在文中移除该引用并记录。")
    L.append("- 有目无引：确认该文献是否支撑正文某论断；不支撑则从文献表删除并记录。")
    L.append("- 序号错位/断号：以正文首次出现顺序整体重排，同步更新正文标记、图表注与附录引用。")

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
    except OSError as e:
        print("[FAIL] 报告写入失败 %s: %s" % (args.output, e))
        return 1

    print("[校验] 制式=%s ERROR=%d WARN=%d -> %s"
          % (style, len(errors), len(warns), "FAIL" if errors else "PASS"))
    for e in errors:
        print("  [ERROR] %s" % e)
    for w in warns[:20]:
        print("  [WARN ] %s" % w)
    print("[报告] %s" % args.output)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

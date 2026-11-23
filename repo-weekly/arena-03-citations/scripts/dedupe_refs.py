#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dedupe_refs.py — 文献表重复条目检测（「收得净」的确定性环节，stdlib-only）。

处理同一文献以中英文题名、预印本与正式版、不同数据库导出等形式重复出现的情形。
判据（可解释，详见 references/method_rules.md §4）：
  HIGH   同 DOI（规范化后完全一致）；
  HIGH   规范化全文相似度 ≥ 0.97；
  MEDIUM 规范化全文相似度 ≥ --threshold（默认 0.85）且同年；
反并判据（防误并）：同第一作者且同年但相似度 < threshold 时，明确提示
「疑似同名作者不同文献，勿合并」——这是题面点名的失败模式。

规范化：小写化，去除一切非字母/数字/汉字字符（标点、空格、连字符不影响比较）。
相似度：difflib.SequenceMatcher（stdlib）。

用法（绝对路径调用，只读输入文件）：
  python3 /skills/weekly-skill/scripts/dedupe_refs.py \
      --refs /app/work/reflist.md --output /app/output/dedupe_report.md

退出码：0 = 未发现重复候选；1 = 发现重复候选或输入不可读。
"""
import argparse
import difflib
import os
import re
import sys

NUM_ENTRY = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.、\)])\s+(\S.*)$")
DOI = re.compile(r"10\.\d{4,9}/[^\s,，;；\]\)]+", re.I)
YEAR = re.compile(r"(?:19|20)\d{2}")
ARXIV = re.compile(r"arXiv[:\s]*(\d{4}\.\d{4,5})", re.I)


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def parse_entries(text):
    """解析编号条目；无编号时退化为按非空行/空行分段。返回 [(标签, 文本)]。"""
    entries, cur_no, cur_buf = [], None, []
    for line in text.splitlines():
        m = NUM_ENTRY.match(line)
        if m:
            if cur_no is not None:
                entries.append((cur_no, " ".join(cur_buf).strip()))
            cur_no = m.group(1) or m.group(2)
            cur_buf = [m.group(3)]
        elif line.strip() and cur_no is not None:
            cur_buf.append(line.strip())
    if cur_no is not None:
        entries.append((cur_no, " ".join(cur_buf).strip()))
    if entries:
        return entries
    # 退化：按空行分段
    out, buf = [], []
    for line in text.splitlines():
        if line.strip():
            buf.append(line.strip())
        elif buf:
            out.append(("P%d" % (len(out) + 1), " ".join(buf)))
            buf = []
    if buf:
        out.append(("P%d" % (len(out) + 1), " ".join(buf)))
    return out


def norm(s):
    return re.sub(r"[^0-9a-z一-鿿]", "", s.lower())


def norm_doi(d):
    """DOI 规范化（v2 强化）：去 https://doi.org/ 与 doi: 前缀、句读尾缀、
    出版商页面后缀（/full /abstract /pdf .pdf），小写化——同一文献的不同
    数据库导出形式（裸 DOI / URL 形式 / 页面链接）应判为同一 DOI。"""
    d = d.strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    d = d.rstrip(".。;,，;；)）]")
    for suf in ("/full", "/abstract", "/pdf", ".pdf", ".full"):
        if d.endswith(suf):
            d = d[:-len(suf)]
    return d


def first_author(text):
    m = re.match(r"\s*([A-Za-zÀ-ɏ'\-]+|[一-鿿]{2,4})", text)
    if not m:
        return ""
    t = m.group(1)
    return t if re.search(r"[一-鿿]", t) else t.lower()


def snippet(text, n=70):
    s = re.sub(r"\s+", " ", text).strip()
    return s if len(s) <= n else s[:n] + "…"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="文献表重复条目检测：同 DOI / 高相似度候选 + 防误并提示。")
    ap.add_argument("--refs", required=True, help="文献表文件（utf-8 文本）绝对路径")
    ap.add_argument("--threshold", type=float, default=0.85,
                    help="中判据相似度阈值（默认 0.85，需配同一年份）")
    ap.add_argument("--output", required=True, help="去重报告 markdown 输出绝对路径")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.refs):
        print("[FAIL] 输入文件不存在: %s" % args.refs)
        return 1
    try:
        text = read_text(args.refs)
    except OSError as e:
        print("[FAIL] 输入读取失败: %s" % e)
        return 1

    entries = parse_entries(text)
    if len(entries) < 2:
        print("[FAIL] 解析出的条目数不足 2 条（得到 %d 条），无法去重" % len(entries))
        return 1

    meta = []
    for tag, body in entries:
        dois = {norm_doi(d) for d in DOI.findall(body)}
        arxivs = set(ARXIV.findall(body))
        ym = YEAR.search(body)
        meta.append({
            "tag": tag, "body": body, "norm": norm(body),
            "dois": dois, "arxivs": arxivs,
            "year": ym.group(0) if ym else None,
            "author": first_author(body),
        })

    candidates, guards = [], []
    for i in range(len(meta)):
        for j in range(i + 1, len(meta)):
            a, b = meta[i], meta[j]
            reasons = []
            if a["dois"] and a["dois"] & b["dois"]:
                reasons.append("同 DOI: %s" % sorted(a["dois"] & b["dois"])[0])
            if a["arxivs"] and a["arxivs"] & b["arxivs"]:
                reasons.append("同 arXiv 号: %s（预印本/正式版重复，保留正式版）"
                               % sorted(a["arxivs"] & b["arxivs"])[0])
            ratio = difflib.SequenceMatcher(None, a["norm"], b["norm"]).ratio()
            if ratio >= 0.97:
                reasons.append("规范化相似度 %.3f ≥ 0.97" % ratio)
            elif ratio >= args.threshold and a["year"] and a["year"] == b["year"]:
                reasons.append("规范化相似度 %.3f ≥ %.2f 且同年(%s)"
                               % (ratio, args.threshold, a["year"]))
            if reasons:
                candidates.append((a, b, ratio, reasons))
            elif (a["author"] and a["author"] == b["author"]
                  and a["year"] and a["year"] == b["year"]):
                guards.append((a, b, ratio))

    L = []
    L.append("# 文献去重检测报告")
    L.append("")
    L.append("- 输入: `%s`（%d 条）" % (args.refs, len(entries)))
    L.append("- 阈值: HIGH=同DOI/同arXiv/相似度≥0.97；MEDIUM=相似度≥%.2f且同年" % args.threshold)
    L.append("- 结论: 重复候选 %d 对；防误并提示 %d 对 -> **%s**"
             % (len(candidates), len(guards), "FAIL" if candidates else "PASS"))
    L.append("")
    L.append("## 重复候选（需人工确认合并，脚本不擅自删条）")
    if candidates:
        for k, (a, b, ratio, reasons) in enumerate(candidates, 1):
            L.append("### 候选 %d：条目 %s × 条目 %s（相似度 %.3f）"
                     % (k, a["tag"], b["tag"], ratio))
            L.append("- 判据: %s" % "；".join(reasons))
            L.append("- A: %s" % snippet(a["body"]))
            L.append("- B: %s" % snippet(b["body"]))
            L.append("- 建议: 保留元数据更全/正式出版版本，正文引用统一指向保留条，"
                     "合并依据写入合并记录。")
            L.append("")
    else:
        L.append("（无）")
        L.append("")
    L.append("## 防误并提示（同第一作者同年但相似度不足——疑似不同文献，勿合并）")
    if guards:
        for a, b, ratio in guards:
            L.append("- 条目 %s × 条目 %s（作者 %s，%s 年，相似度 %.3f）"
                     % (a["tag"], b["tag"], a["author"], a["year"], ratio))
    else:
        L.append("（无）")
    L.append("")
    L.append("> 合并三原则：有判据（DOI/相似度/同年同作者）、保留信息更全者、"
             "合并决策写入 evidence_map 的修改记录，可回溯。")

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
    except OSError as e:
        print("[FAIL] 报告写入失败 %s: %s" % (args.output, e))
        return 1

    print("[去重] 条目=%d 候选=%d 防误并=%d -> %s"
          % (len(entries), len(candidates), len(guards),
             "FAIL" if candidates else "PASS"))
    for a, b, ratio, reasons in candidates:
        print("  [候选] %s × %s (%.3f): %s" % (a["tag"], b["tag"], ratio, "；".join(reasons)))
    print("[报告] %s" % args.output)
    return 1 if candidates else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""roundtrip_check.py — 文献库往返（library round-trip）无损检查（stdlib-only）。

问题：整理后的文献表导出为 BibTeX / RIS 交给文献管理软件后，能否**无损回导**？
本脚本做确定性的代理验证：
  1. 从编号文献表逐条抽取关键字段（第一作者 / 年份 / DOI / 文献类型标识）；
  2. 序列化为 BibTeX 与 RIS 两种交换格式（写出到 --export-dir，可交付）；
  3. 用独立解析器从序列化结果回读，逐字段与原值比对；
  4. 字段在序列化↔回读中失真 -> LOSS（ERROR）；字段在源头缺失 -> WARN
     （应显式标注「[缺: 字段名]」，不得编造）；--strict 时源头缺失也判 LOSS。

用法（绝对路径调用，不依赖 CWD，只读输入文件）：
  python3 /skills/weekly-skill/scripts/roundtrip_check.py \
      --refs /app/work/reflist_final.md \
      --export-dir /app/output \
      --output /app/output/roundtrip_report.md

退出码：0 = 全部已抽取字段无损往返（允许 WARN）；1 = 存在 LOSS 或输入不可读。
"""
import argparse
import os
import re
import sys

NUM_ENTRY = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.、\)])\s+(\S.*)$")
DOI = re.compile(r"10\.\d{4,9}/[^\s,，;；\]\)（）]+", re.I)
YEAR = re.compile(r"(?:19|20)\d{2}")
GBT_TYPE = re.compile(r"\[(J|M|C|D|R|S|P|N|G|A|Z|EB/OL|DB/OL|J/OL|M/OL|C/OL|N/OL)\]")


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def norm_doi(d):
    d = d.strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d.rstrip(".。;,，;；)）]")


def parse_entries(text):
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
    return entries


def first_author(text):
    m = re.match(r"\s*([A-Za-zÀ-ɏ'\-]+|[一-鿿]{2,4})", text)
    return m.group(1) if m else ""


def extract_fields(body):
    """返回 {字段: 值}；抽取不到的字段不出现（源头缺失）。"""
    out = {}
    au = first_author(body)
    if au:
        out["author"] = au
    ym = YEAR.search(body)
    if ym:
        out["year"] = ym.group(0)
    dm = DOI.search(body)
    if dm:
        out["doi"] = norm_doi(dm.group(0))
    tm = GBT_TYPE.search(body)
    if tm:
        out["type"] = tm.group(1)
    return out


# ---- 序列化（导出） ----

def to_bibtex(key, fields):
    bt_type = {"J": "article", "M": "book", "D": "phdthesis", "C": "inproceedings",
               "R": "techreport"}.get(fields.get("type", "").split("/")[0], "misc")
    lines = ["@%s{%s," % (bt_type, key)]
    for k in ("author", "year", "doi", "type"):
        if k in fields:
            lines.append("  %s = {%s}," % (k, fields[k]))
    lines.append("}")
    return "\n".join(lines)


def to_ris(fields):
    ty = {"J": "JOUR", "M": "BOOK", "C": "CONF", "D": "THES", "R": "RPRT"}.get(
        fields.get("type", "").split("/")[0], "GEN")
    lines = ["TY  - %s" % ty]
    if "author" in fields:
        lines.append("AU  - %s" % fields["author"])
    if "year" in fields:
        lines.append("PY  - %s" % fields["year"])
    if "doi" in fields:
        lines.append("DO  - %s" % fields["doi"])
    lines.append("ER  - ")
    return "\n".join(lines)


# ---- 回导（独立解析器） ----

def from_bibtex(text):
    out = {}
    m = re.search(r"@(\w+)\s*{", text)
    if m:
        out["type"] = m.group(1)
    for k in ("author", "year", "doi"):
        m = re.search(r"\b%s\s*=\s*\{([^}]*)\}" % k, text)
        if m:
            out[k] = m.group(1).strip()
    return out


def from_ris(text):
    out = {}
    for line in text.splitlines():
        if len(line) >= 6 and line[2:6] == "  - ":
            tag, val = line[:2], line[6:].strip()
            if tag == "TY":
                out["type"] = val
            elif tag == "AU":
                out["author"] = val
            elif tag == "PY":
                out["year"] = val
            elif tag == "DO":
                out["doi"] = val
    return out


# BibTeX entry type / RIS TY 与 GB/T 类型标识的公认映射（回导后与源比对用）
BT2GBT = {"article": "J", "book": "M", "phdthesis": "D", "inproceedings": "C",
          "techreport": "R"}
RIS2GBT = {"JOUR": "J", "BOOK": "M", "CONF": "C", "THES": "D", "RPRT": "R"}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="文献库往返检查：编号文献表 -> BibTeX/RIS 导出 -> 回导比对，验证无损。")
    ap.add_argument("--refs", required=True, help="编号文献表（utf-8 文本）绝对路径")
    ap.add_argument("--export-dir", default=None,
                    help="BibTeX/RIS 导出文件存放目录（缺省不落地，仅内存往返）")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：源头缺字段也判 LOSS（默认仅 WARN）")
    ap.add_argument("--output", required=True, help="往返检查报告 markdown 输出绝对路径")
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
    if not entries:
        print("[FAIL] 未解析出任何编号条目（期望 [n] 或 n. 开头）")
        return 1

    losses, warns, rows = [], [], []
    bib_all, ris_all = [], []
    for no, body in entries:
        fields = extract_fields(body)
        bib, ris = to_bibtex("e%s" % no, fields), to_ris(fields)
        bib_all.append(bib)
        ris_all.append(ris)
        bib_back, ris_back = from_bibtex(bib), from_ris(ris)
        for k in ("author", "year", "doi"):
            if k not in fields:
                msg = "条目 [%s] 源头缺字段 %s——导出即丢失，应标注「[缺: %s]」" % (
                    no, k, k)
                (losses if args.strict else warns).append(msg)
                rows.append("| %s | %s | （源头缺失） | - | - | %s |"
                            % (no, k, "LOSS" if args.strict else "WARN"))
                continue
            src = fields[k]
            b_ok = bib_back.get(k) == src
            r_ok = ris_back.get(k) == src
            if not (b_ok and r_ok):
                losses.append("条目 [%s] 字段 %s 往返失真：源=%r bibtex=%r ris=%r"
                              % (no, k, src, bib_back.get(k), ris_back.get(k)))
            rows.append("| %s | %s | %s | %s | %s | %s |" % (
                no, k, src,
                bib_back.get(k, "（丢失）"), ris_back.get(k, "（丢失）"),
                "OK" if (b_ok and r_ok) else "LOSS"))
        if "type" in fields:
            b_t = BT2GBT.get(bib_back.get("type", ""), "")
            r_t = RIS2GBT.get(ris_back.get("type", ""), "")
            base = fields["type"].split("/")[0]
            if b_t != base or r_t != base:
                warns.append("条目 [%s] 类型标识 %s 往返后映射为 %s/%s（著录时请人工复核类型）"
                             % (no, fields["type"], bib_back.get("type"), ris_back.get("type")))

    if args.export_dir:
        try:
            os.makedirs(args.export_dir, exist_ok=True)
            with open(os.path.join(args.export_dir, "reflib_export.bib"),
                      "w", encoding="utf-8") as f:
                f.write("\n\n".join(bib_all) + "\n")
            with open(os.path.join(args.export_dir, "reflib_export.ris"),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(ris_all) + "\n")
        except OSError as e:
            print("[FAIL] 导出文件写入失败: %s" % e)
            return 1

    L = []
    L.append("# 文献库往返（round-trip）检查报告")
    L.append("")
    L.append("- 输入: `%s`（%d 条）" % (args.refs, len(entries)))
    L.append("- 模式: %s" % ("strict（源头缺字段判 LOSS）" if args.strict else "默认（源头缺字段 WARN）"))
    L.append("- 导出: %s" % ("`%s`（reflib_export.bib / reflib_export.ris）" % args.export_dir
                            if args.export_dir else "（内存往返，未落地）"))
    L.append("- 结论: LOSS %d 项 / WARN %d 项 -> **%s**"
             % (len(losses), len(warns), "FAIL" if losses else "PASS"))
    L.append("")
    L.append("## 逐字段往返结果")
    L.append("")
    L.append("| 条目 | 字段 | 源值 | BibTeX 回导 | RIS 回导 | 结论 |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    L += rows
    L.append("")
    L.append("## 说明")
    L.append("- 只验证「已抽取字段经 BibTeX/RIS 序列化后能否原值回导」，不联网核验真伪；")
    L.append("- 源头缺字段不是脚本能修复的问题：回到文献库定位真实元数据，定位不到则")
    L.append("  显式标注「[缺: 字段名]」并列入待确认清单，**不得编造**。")

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
    except OSError as e:
        print("[FAIL] 报告写入失败 %s: %s" % (args.output, e))
        return 1

    print("[往返检查] 条目=%d LOSS=%d WARN=%d -> %s"
          % (len(entries), len(losses), len(warns), "FAIL" if losses else "PASS"))
    for e in losses:
        print("  [LOSS ] %s" % e)
    for w in warns[:20]:
        print("  [WARN ] %s" % w)
    print("[报告] %s" % args.output)
    return 1 if losses else 0


if __name__ == "__main__":
    sys.exit(main())

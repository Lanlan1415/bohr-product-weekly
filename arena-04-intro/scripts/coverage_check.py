#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_check.py — 引用覆盖与贡献对齐核验。

核验内容
    1. 无编造条目：稿件中每条引用（\\cite 键 / 数字编号 / 作者-年份）都必须对应文献库条目；
       对不上的按 CITATION_NOT_IN_LIBRARY 报 error。
    2. 文献库被引覆盖率：未引用条目逐一列出（warning），覆盖率 <0.5 报 LIBRARY_COVERAGE_LOW。
    3. 分组规模：每组 ≥2 篇；不足 2 篇报 GROUP_TOO_SMALL（应并入相邻组或写入 uncertainty）；
       组内引用了不存在的条目报 GROUP_REF_UNKNOWN；一篇进多组报 GROUP_REF_DUPLICATE。
    4. 贡献对齐：贡献表述中引用的 图/表/算法/章节/附录 号与方法名（tokens）必须在底稿材料中
       存在，否则报 CONTRIBUTION_ARTIFACT_MISSING；status=aligned 但 mapped_to 为空报
       CLAIM_ALIGNED_WITHOUT_MAPPING；status=author_judgment / unaligned 报 warning
       （必须进入 human_review_items）。

用法
    python coverage_check.py --draft draft.md --entries entries.json \
        [--groups groups.json] [--contributions contrib.json] [--materials materials.md] \
        [--report report.json]

输入文件格式
    entries.json      parse_library.py 的输出（含 entries）。
    groups.json       {"groups":[{group, basis, papers:[{ref,...} | "ref_id"]}]}，可选。
    contrib.json      {"contributions_alignment":[{claim, mapped_to, status, tokens?}]}，可选；
                      也可直接传条目列表。tokens 为显式方法名/工件名列表（可选）。
    materials.md      本文底稿/方法摘要等材料文本，用于核对图表号与方法名是否真实存在，可选。

报告（stdout 与 --report）
    {"script","ok","summary":{errors,warnings,notes},"findings":[{code,severity,detail,ref}],
     "citations":{resolved,fabricated,unresolved},"coverage":{total,cited,ratio,uncited}}

退出码：0 = 脚本运行成功（报告内 ok=false 表示存在 error 级问题）；2 = 输入错误。
"""

import argparse
import json
import re
import sys
import unicodedata

SCRIPT = "coverage_check"
VERSION = "1.0.0"


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip()


# ---------- 稿件引用抽取 ----------

KEY_CITE = re.compile(r"\\cite[a-zA-Z\*]*\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}")
BRACKET_NUM = re.compile(r"\[(\d{1,3}(?:\s*[,，;]\s*\d{1,3})*(?:\s*[-–—]\s*\d{1,3})?)\]")
BRACKET_KEY = re.compile(r"\[@?([A-Za-z][\w\-\.+:]*?(?:\s*[,，;]\s*[A-Za-z][\w\-\.+:]*)*)\]")
PAREN_AY = re.compile(r"\(([^()]*\d{4}[^()]*)\)")
NARRATIVE_EN = re.compile(r"\b([A-Z][A-Za-z'’\-]+)(?:\s+et\s+al\.?)?\s*\((\d{4})\b")
NARRATIVE_ZH = re.compile(r"([\w'’\-]+)\s*等\s*[（(]\s*(\d{4})\s*[）)]")
XREF_HINT = re.compile(r"图\s*\d|表\s*\d|[Ff]ig|[Ss]ection|章节|页|[Pp]age|[Aa]lgorithm|[Ee]q\.?|式\s*[（(]?\d")

REF_HEADING = re.compile(
    r"^#{0,6}\s*(参考文献|引用文献|文献列表|[Rr]eferences|[Bb]ibliography)\s*$", re.M)


def strip_references_section(text):
    matches = list(REF_HEADING.finditer(text))
    if matches:
        cut = matches[-1].start()
        return text[:cut], True
    return text, False


def expand_numeric_token(tok):
    nums = []
    for part in re.split(r"[,，;]", tok):
        part = part.strip()
        m = re.fullmatch(r"(\d{1,3})\s*[-–—]\s*(\d{1,3})", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if 0 < hi - lo <= 50:
                nums.extend(str(x) for x in range(lo, hi + 1))
            else:
                nums.append(part)
        elif part:
            nums.append(part)
    return nums


def clean_surname(seg):
    seg = re.sub(r"(?i)\be\.g\.?|cf\.?|参见|见|对比|如|例如", " ", seg)
    seg = re.sub(r"(?i)\bet\s+al\.?|等|\s*&\s*|\s*和\s*|\s*与\s*|\s*、\s*|,", " ", seg)
    toks = [t for t in seg.split() if t]
    for t in toks:
        if re.match(r"[A-Za-z\u4e00-\u9fff]", t):
            return t
    return None


def surname_candidates(author_str):
    a = (author_str or "").strip()
    if not a:
        return []
    if "," in a:
        head = a.split(",")[0].strip()
        return [head] if head else []
    toks = a.split()
    if len(toks) == 1:
        return [toks[0]]
    return [toks[-1], toks[0]]


# ---------- 贡献对齐 ----------

AUTO_TOKEN = re.compile(
    r"(?i)(?:fig(?:ure)?s?\.?\s*\d+|figure\s*\d+|tables?\.?\s*\d+|table\s*\d+"
    r"|图\s*\d+|表\s*\d+|algorithm\s*\d+|算法\s*\d+|§\s*\d+|section\s*\d+"
    r"|附录\s*[A-Z0-9]+|appendix\s*[A-Z0-9]+)")


def classify_token(tok):
    tl = tok.lower()
    num_m = re.search(r"(\d+)", tok)
    num = num_m.group(1) if num_m else None
    if re.search(r"fig|figure|图", tl):
        kind = "fig"
    elif re.search(r"table|表", tl):
        kind = "table"
    elif re.search(r"algorithm|算法", tl):
        kind = "algo"
    elif re.search(r"section|§|章|节", tl):
        kind = "section"
    elif re.search(r"appendix|附录", tl):
        kind = "appendix"
    else:
        kind = None
    return kind, num


def token_search_regex(kind, num):
    n = re.escape(num)
    if kind == "fig":
        return re.compile(r"(?i)fig(?:ure)?s?\.?\s*%s|图\s*%s" % (n, n))
    if kind == "table":
        return re.compile(r"(?i)tables?\.?\s*%s|表\s*%s" % (n, n))
    if kind == "algo":
        return re.compile(r"(?i)algorithms?\.?\s*%s|算法\s*%s" % (n, n))
    if kind == "section":
        return re.compile(r"(?i)section\s*%s|§\s*%s|第\s*%s\s*[章节]" % (n, n, n))
    if kind == "appendix":
        return re.compile(r"(?i)appendix\s*[A-Z]?%s|附录\s*%s" % (n, n))
    return None


def artifact_found(kind, num, materials_text, heading_lines):
    if kind == "section":
        rx = token_search_regex("section", num)
        if rx and rx.search(materials_text):
            return True
        for ln in heading_lines:
            s = ln.lstrip("#").strip()
            if s.startswith(num + ".") or s.startswith(num + "、") or s.startswith(num + " "):
                return True
        return False
    rx = token_search_regex(kind, num)
    return bool(rx and rx.search(materials_text))


# ---------- 主流程 ----------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="引用覆盖与贡献对齐核验（编造引用/覆盖率/组规模/图表号存在性）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python coverage_check.py --draft draft.md --entries entries.json "
               "--groups groups.json --contributions contrib.json --materials materials.md")
    ap.add_argument("--draft", required=True, help="成稿/草稿 markdown（被核验对象）")
    ap.add_argument("--entries", required=True, help="parse_library.py 输出的条目表 JSON")
    ap.add_argument("--groups", help="分组结果 JSON（可选）：{groups:[{group,basis,papers:[...]}]}")
    ap.add_argument("--contributions", help="贡献对齐表 JSON（可选）：{contributions_alignment:[...]}")
    ap.add_argument("--materials", help="本文底稿/方法摘要等材料文本（可选，缺省时跳过工件存在性核对）")
    ap.add_argument("--report", help="报告 JSON 输出路径（默认仅打印）")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    def load_json(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    try:
        with open(args.draft, "r", encoding="utf-8-sig") as f:
            draft = f.read()
        entries_doc = load_json(args.entries)
    except (OSError, ValueError) as e:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "READ_FAILED", "detail": str(e)},
                         ensure_ascii=False))
        return 2

    entries = entries_doc.get("entries", []) if isinstance(entries_doc, dict) else entries_doc
    by_id = {norm(str(e.get("id", ""))): e for e in entries}

    findings = []

    def add(code, severity, detail, ref=None):
        findings.append({"code": code, "severity": severity, "detail": detail, "ref": ref})

    # --- 抽取引用 ---
    draft_scan, ref_cut = strip_references_section(draft)
    if ref_cut:
        add("REFERENCES_SECTION_SKIPPED", "note", "稿件中的参考文献列表段落已从引用扫描中剔除")

    resolved = set()        # 条目 id
    fabricated = []
    unresolved = []
    seen_ay = set()
    numeric_ids = {i for i in by_id if re.fullmatch(r"\d+", i)}

    for m in KEY_CITE.finditer(draft_scan):
        for key in re.split(r"[,，;]", m.group(1)):
            key = norm(key)
            if not key:
                continue
            if key in by_id:
                resolved.add(key)
            else:
                fabricated.append({"kind": "key", "value": key})

    for m in BRACKET_NUM.finditer(draft_scan):
        for num in expand_numeric_token(m.group(1)):
            num = norm(num)
            if numeric_ids:
                if num in by_id:
                    resolved.add(num)
                else:
                    fabricated.append({"kind": "number", "value": num})
            else:
                unresolved.append({"kind": "number", "value": num,
                                   "detail": "文献库条目 id 非纯数字，数字编号无法映射；请改用 \\cite 键或作者-年份"})

    for m in BRACKET_KEY.finditer(draft_scan):
        for key in re.split(r"[,，;]", m.group(1)):
            key = norm(key.strip("@"))
            if not key or re.fullmatch(r"\d+", key):
                continue
            if key in by_id:
                resolved.add(key)
            else:
                fabricated.append({"kind": "key", "value": key})

    # 作者-年份（括注式 + 叙述式，中英文）
    ay_hits = []
    for m in PAREN_AY.finditer(draft_scan):
        inner = m.group(1)
        if XREF_HINT.search(inner):
            continue
        for seg in re.split(r"[;；]", inner):
            ym = None
            for y in re.finditer(r"(19|20)\d{2}", seg):
                ym = y
            if not ym:
                continue
            surname = clean_surname(seg[:ym.start()])
            if surname:
                ay_hits.append((surname, ym.group(0)))
    for rx, gi, gy in ((NARRATIVE_EN, 1, 2), (NARRATIVE_ZH, 1, 2)):
        for m in rx.finditer(draft_scan):
            ay_hits.append((m.group(gi), m.group(gy)))

    surname_index = {}
    for eid, e in by_id.items():
        for au in e.get("authors", []):
            for su in surname_candidates(au):
                surname_index.setdefault(su.casefold(), {}).setdefault(
                    str(e.get("year") or ""), []).append(eid)

    for surname, year in ay_hits:
        sig = (surname.casefold(), year)
        if sig in seen_ay:
            continue
        seen_ay.add(sig)
        bucket = surname_index.get(surname.casefold(), {})
        matches = bucket.get(year, [])
        # 年份差超过 3 年视为不同文献：不许按姓氏模糊匹配到库内条目
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            year_int = None
        if not matches and year_int is not None:
            near = [v for y, ids in bucket.items() for v in ids
                    if y and abs(int(y) - year_int) <= 3]
            matches = near
        if bucket.get(year):
            resolved.update(bucket[year])
        elif matches:
            resolved.update(matches)
            add("AMBIGUOUS_CITATION", "warning",
                "作者-年份引用 %s %s：文献库中同年同姓多义/年份不符，已按姓氏匹配到 %s，请人工确认"
                % (surname, year, ",".join(sorted(set(matches)))), ",".join(sorted(set(matches))))
        else:
            fabricated.append({"kind": "author_year", "value": "%s %s" % (surname, year)})

    for f in fabricated:
        add("CITATION_NOT_IN_LIBRARY", "error",
            "编造引用嫌疑：稿件引用 %s=%r 在文献库中不存在；必须删除或替换为文献库内条目" % (f["kind"], f["value"]),
            f["value"])
    for u in unresolved:
        add("NUMERIC_CITATION_UNRESOLVABLE", "note",
            "数字编号 [%s] 无法与文献库映射（%s）" % (u["value"], u.get("detail", "")))

    # --- 覆盖率 ---
    uncited = [i for i in by_id if i not in resolved]
    total = len(by_id)
    cited_n = total - len(uncited)
    ratio = round(cited_n / total, 4) if total else 0.0
    for i in uncited:
        add("UNCITED_LIBRARY_ENTRY", "warning",
            "文献库条目 %r 未被稿件引用（若为关键/代表性工作需补引，或在 result.uncertainty 中说明取舍）" % i, i)
    if total and ratio < 0.5:
        add("LIBRARY_COVERAGE_LOW", "warning",
            "文献库被引覆盖率 %.0f%%（<50%%），相关工作覆盖可能不足" % (ratio * 100))

    # --- 分组规模 ---
    if args.groups:
        try:
            gdoc = load_json(args.groups)
        except (OSError, ValueError) as e:
            add("GROUPS_FILE_ERROR", "error", "groups 文件读取失败：%s" % e)
            gdoc = {}
        groups = gdoc.get("groups", gdoc) if isinstance(gdoc, dict) else gdoc
        if isinstance(groups, list):
            occupied = {}
            for g in groups:
                gname = norm(str(g.get("group", "")))
                papers = g.get("papers", []) or []
                ids = []
                for p in papers:
                    pid = norm(str(p.get("ref") if isinstance(p, dict) else p))
                    ids.append(pid)
                if len(ids) < 2:
                    if len(ids) == 1:
                        add("GROUP_TOO_SMALL", "warning",
                            "分组 %r 仅 1 篇（%s）：应并入相邻组，或保留并在 result.uncertainty 与成稿中说明单篇无法组内比较"
                            % (gname, ids[0]), ids[0])
                    else:
                        add("GROUP_EMPTY", "warning", "分组 %r 没有任何条目" % gname)
                for pid in ids:
                    if pid not in by_id:
                        add("GROUP_REF_UNKNOWN", "error",
                            "分组 %r 引用了文献库中不存在的条目 %r" % (gname, pid), pid)
                    if pid in occupied and occupied[pid] != gname:
                        add("GROUP_REF_DUPLICATE", "warning",
                            "条目 %r 同时出现在分组 %r 与 %r（一篇只应归入一组）" % (pid, occupied[pid], gname), pid)
                    occupied.setdefault(pid, gname)

    # --- 贡献对齐 ---
    materials_text = ""
    heading_lines = []
    if args.materials:
        try:
            with open(args.materials, "r", encoding="utf-8-sig") as f:
                raw_md = f.read()
            materials_text = norm(raw_md)
            heading_lines = [ln for ln in raw_md.splitlines() if ln.lstrip().startswith("#")]
        except (OSError, ValueError) as e:
            add("MATERIALS_FILE_ERROR", "error", "materials 文件读取失败：%s" % e)
    elif args.contributions:
        add("MATERIALS_NOT_PROVIDED", "note",
            "未提供 --materials，跳过贡献表述的图表号/方法名存在性核对")

    if args.contributions:
        try:
            cdoc = load_json(args.contributions)
        except (OSError, ValueError) as e:
            add("CONTRIBUTIONS_FILE_ERROR", "error", "contributions 文件读取失败：%s" % e)
            cdoc = {}
        claims = cdoc.get("contributions_alignment", cdoc) if isinstance(cdoc, dict) else cdoc
        if not isinstance(claims, list):
            claims = []
        for idx, c in enumerate(claims, 1):
            claim = norm(str(c.get("claim", "")))
            mapped = norm(str(c.get("mapped_to", "")))
            status = norm(str(c.get("status", ""))).lower()
            tokens = [norm(str(t)) for t in (c.get("tokens") or []) if norm(str(t))]

            if status == "aligned" and not mapped:
                add("CLAIM_ALIGNED_WITHOUT_MAPPING", "error",
                    "贡献%d 标为 aligned 但 mapped_to 为空：每条贡献必须映射到方法/图表/实验结果" % idx, claim[:40])
            if status == "author_judgment":
                add("CLAIM_AUTHOR_JUDGMENT", "warning",
                    "贡献%d 为作者判断（未由底稿结果直接支持）：必须写入 human_review_items，成稿中不得写成实验结论"
                    % idx, claim[:40])
            if status == "unaligned":
                add("CLAIM_UNALIGNED", "warning",
                    "贡献%d 标为 unaligned：应从成稿贡献列表移除或改写，并保留在 human_review_items" % idx, claim[:40])

            if materials_text:
                checked = set()
                auto_tokens = [m.group(0).strip() for m in AUTO_TOKEN.finditer(mapped)] + \
                              [m.group(0).strip() for m in AUTO_TOKEN.finditer(claim)]
                for tok in tokens + auto_tokens:
                    key = norm(tok)
                    if key in checked:
                        continue
                    checked.add(key)
                    kind, num = classify_token(key)
                    if kind and num:
                        ok = artifact_found(kind, num, materials_text, heading_lines)
                        detail = "工件 %r 在底稿材料中%s" % (key, "存在" if ok else "不存在——成稿不得引用底稿中没有的图表号")
                    else:
                        ok = key.casefold() in materials_text.casefold()
                        detail = "方法名/术语 %r 在底稿材料中%s" % (key, "存在" if ok else "不存在——不得在贡献表述中引入底稿之外的方法名")
                    if not ok:
                        add("CONTRIBUTION_ARTIFACT_MISSING", "error",
                            "贡献%d：%s" % (idx, detail), claim[:40])

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    notes = [f for f in findings if f["severity"] == "note"]

    report = {
        "script": SCRIPT,
        "version": VERSION,
        "ok": len(errors) == 0,
        "summary": {"errors": len(errors), "warnings": len(warnings), "notes": len(notes)},
        "findings": findings,
        "citations": {
            "resolved": sorted(resolved),
            "fabricated": fabricated,
            "unresolved": unresolved,
        },
        "coverage": {"total": total, "cited": cited_n, "ratio": ratio, "uncited": uncited},
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(payload)
    print(payload)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

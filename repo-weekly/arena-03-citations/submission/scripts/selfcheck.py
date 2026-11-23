#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 交付自查（参考文献与引用管理题，stdlib-only）。

逐条打印 PASS/FAIL，任一项 FAIL 退出码为 1：
  1. 输出目录存在且非空；
  2. result.json 存在、为合法 JSON；
  3. case_id 与 case.json 一致；output_contract 声明的全部原始字段透传齐全；
  4. status ∈ {success, partial, failed}，且 sources / uncertainty / change_log 键齐全；
  5. 主产物存在且含「参考文献 / References」节；
  6. 引用校验报告存在（citation_check.py 的产物）；
  7. 来源映射存在，且交付物中出现的 [S#] 标记全部已在映射中登记（无幽灵来源）；
  8. 轻量交叉核对：主产物正文 [n] 标记在文献表节内均有对应条目（缺条目为 FAIL，
     未引用条目仅 WARN）。

用法（绝对路径，不依赖 CWD，只读输入目录）：
  python3 /skills/weekly-skill/scripts/selfcheck.py \
      --output-dir /app/output --case-json /input/case.json
"""
import argparse
import json
import os
import re
import sys

REF_HEADING = re.compile(
    r"^[#\s\d\.、]*(?:参考文献|REFERENCES?|References)\s*[:：]?\s*$", re.M)
NUM_MARK = re.compile(r"\[(\d[\d\s,，、\-–—]*)\]")
NUM_ENTRY = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.、\)])\s+\S")
SMARK = re.compile(r"\[S(\d+)\]")
SREG = re.compile(r"(?:^|[\s|>])\**S(\d+)\**[\s:|：]")

results = []  # (级别, 名称, 详情)


def record(ok, name, detail="", warn=False):
    level = "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL")
    results.append((level, name, detail))


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def expand(tok):
    out = set()
    for part in re.split(r"[,，、]", tok):
        part = part.strip()
        m = re.match(r"^(\d+)\s*[-–—]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b <= 9999:
                out.update(range(a, b + 1))
        elif part.isdigit():
            out.add(int(part))
    return out


def contract_fields(case):
    """从 case.json 提取 output_contract 声明的字段名，兼容 dict / list[str] / list[dict]。"""
    oc = case.get("output_contract") or case.get("outputContract") or {}
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for it in oc:
            if isinstance(it, str):
                fields.append(it)
            elif isinstance(it, dict):
                for k in ("name", "field", "key"):
                    if k in it:
                        fields.append(it[k])
                        break
    return fields


def main(argv=None):
    ap = argparse.ArgumentParser(description="交付自查：契约透传 + 本题要素 + 来源登记。")
    ap.add_argument("--output-dir", default="/app/output", help="交付目录（默认 /app/output）")
    ap.add_argument("--case-json", default="/input/case.json", help="case.json 路径")
    args = ap.parse_args(argv)

    outdir = args.output_dir
    if not os.path.isdir(outdir):
        record(False, "输出目录存在", "目录不存在: %s" % outdir)
        return report()
    files = []
    for dp, _dn, fns in os.walk(outdir):
        for fn in fns:
            files.append(os.path.join(dp, fn))
    record(bool(files), "输出目录非空", "%d 个文件" % len(files))

    # --- result.json / 契约 ---
    rj_path = os.path.join(outdir, "result.json")
    rj = None
    if not os.path.isfile(rj_path):
        record(False, "result.json 存在", rj_path)
    else:
        try:
            rj = json.loads(read_text(rj_path))
            record(True, "result.json 合法 JSON")
        except (ValueError, OSError) as e:
            record(False, "result.json 合法 JSON", str(e))
    if rj is not None:
        st = rj.get("status")
        record(st in ("success", "partial", "failed"),
               "status 诚实取值", "status=%r" % (st,))
        for key in ("sources", "uncertainty"):
            record(key in rj, "result.json 含 %s" % key)
        record(("change_log" in rj) or ("change_records" in rj),
               "result.json 含 change_log/change_records")
        if os.path.isfile(args.case_json):
            try:
                case = json.loads(read_text(args.case_json))
                cid = case.get("case_id") or case.get("id")
                record(rj.get("case_id") == cid, "case_id 透传一致",
                       "case.json=%r result.json=%r" % (cid, rj.get("case_id")))
                missing = [f for f in contract_fields(case) if f not in rj]
                record(not missing, "output_contract 字段透传齐全",
                       "缺失: %s" % ", ".join(missing) if missing else "全部透传")
            except (ValueError, OSError) as e:
                record(False, "case.json 可解析", str(e))
        else:
            record(False, "case.json 可解析", "不存在: %s（无法核对契约字段）", warn=True)

    # --- 主产物与参考文献节 ---
    text_files = [p for p in files if os.path.splitext(p)[1].lower()
                  in (".md", ".txt", ".tex")]
    docx_files = [p for p in files if p.lower().endswith(".docx")]
    main_doc, ref_ok = None, False
    for p in text_files:
        try:
            t = read_text(p)
        except OSError:
            continue
        if REF_HEADING.search(t):
            main_doc, ref_ok = p, True
            break
    record(main_doc is not None or bool(docx_files), "主产物存在",
           main_doc or (docx_files[0] if docx_files else "未找到"))
    record(ref_ok or bool(docx_files), "主产物含参考文献节",
           "docx 需人工确认" if (docx_files and not ref_ok) else (main_doc or "未找到"))

    # --- 引用校验报告 ---
    report_hit = None
    for p in files:
        base = os.path.basename(p).lower()
        if ("citation" in base or "引用" in base or "校验" in base) and p.endswith(".md"):
            report_hit = p
            break
    record(report_hit is not None, "引用校验报告存在",
           report_hit or "未找到（应运行 citation_check.py 并交付其报告）")

    # --- 来源映射与 [S#] 登记 ---
    smap = None
    for p in files:
        base = os.path.basename(p).lower()
        if ("evidence" in base or "来源" in base or "映射" in base) and p.endswith(".md"):
            smap = p
            break
    registered = set()
    if smap:
        try:
            registered = {int(m.group(1)) for m in SREG.finditer(read_text(smap))}
        except OSError:
            pass
    record(smap is not None, "来源映射文件存在", smap or "未找到")
    used = set()
    for p in text_files:
        try:
            used |= {int(m.group(1)) for m in SMARK.finditer(read_text(p))}
        except OSError:
            continue
    if smap:
        ghosts = sorted(used - registered)
        record(not ghosts, "无幽灵来源标记",
               "未登记: %s" % ", ".join("S%d" % g for g in ghosts) if ghosts
               else "使用的 [S#] 共 %d 个，均已登记" % len(used))

    # --- v2 新增检查项（只 WARN，不把原本能通过的草稿判 FAIL） ---
    map_hit = None
    for p in files:
        base = os.path.basename(p).lower()
        if not p.endswith(".md") or p == smap:
            continue
        if "numbering" in base or "编号" in base \
                or ("map" in base and "evidence" not in base):
            map_hit = p
            break
    record(map_hit is not None, "编号映射表存在（v2，WARN）",
           map_hit or "未找到——如发生插入/删除/合并/重排，应交付 numbering_map.md"
           "（templates/numbering_map_template.md）", warn=True)
    rt_hit = None
    for p in files:
        base = os.path.basename(p).lower()
        if ("roundtrip" in base or "往返" in base) and p.endswith(".md"):
            rt_hit = p
            break
    record(rt_hit is not None, "文献库往返报告存在（v2，WARN）",
           rt_hit or "未找到——建议运行 roundtrip_check.py 验证 BibTeX/RIS 无损回导",
           warn=True)

    # --- 轻量交叉核对（主产物内部） ---
    if ref_ok and main_doc:
        try:
            t = read_text(main_doc)
            m = None
            for m in REF_HEADING.finditer(t):
                pass
            body, refs = t[:m.start()], t[m.end():]
            cited = set()
            for mm in NUM_MARK.finditer(body):
                cited |= expand(mm.group(1))
            listed = set()
            for line in refs.splitlines():
                em = NUM_ENTRY.match(line)
                if em:
                    listed.add(int(em.group(1) or em.group(2)))
            if cited or listed:
                missing = sorted(cited - listed)
                record(not missing, "主产物内 [n] 均有文献条目",
                       "缺条目: %s" % ", ".join("[%d]" % x for x in missing) if missing
                       else "正文 %d 个编号均有条目" % len(cited))
                uncited = sorted(listed - cited)
                record(not uncited, "文献表条目均被引用",
                       "%d 条未引用（建议复核）" % len(uncited), warn=True)
        except OSError:
            pass
    return report()


def report():
    n_fail = 0
    for level, name, detail in results:
        if level == "FAIL":
            n_fail += 1
        print("[%s] %s%s" % (level, name, (" — " + detail) if detail else ""))
    print("自查结论: %s（FAIL %d 项）" % ("FAIL" if n_fail else "PASS", n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

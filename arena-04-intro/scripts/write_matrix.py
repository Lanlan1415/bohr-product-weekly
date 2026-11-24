#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""write_matrix.py — 分组比较矩阵导出：groups 结果 → comparison_matrix.csv。

用途
    把模型产出的分组比较结果（三列强制：conclusion/conditions/limitation）序列化为
    comparison_matrix.csv，UTF-8 with BOM（Excel 直接打开不乱码），由 csv 模块负责引号转义，
    避免手写 CSV 造成的逗号/换行破坏。也可反向用于把矩阵并入 result.json 前的机械转换。

用法
    python write_matrix.py --groups groups.json --output comparison_matrix.csv [--entries entries.json]

输入格式
    groups.json  {"groups":[{group, basis, papers:[{ref, conclusion, conditions, limitation, anchor}, ...]}]}
                 或直接为 groups 列表。papers 内的条目也可以只写 ref 字符串——此时需提供
                 --entries，从条目表补全 title/year（三列留空并提示由模型补齐）。

CSV 列
    group, group_basis, ref, title, year, conclusion, conditions, limitation, anchor_quote

报告（stdout）
    {"script","ok","rows","groups","warnings":[...]}
退出码：0 = 成功；2 = 输入错误。
"""

import argparse
import csv
import json
import re
import sys

SCRIPT = "write_matrix"
VERSION = "1.0.0"
COLUMNS = ["group", "group_basis", "ref", "title", "year",
           "conclusion", "conditions", "limitation", "anchor_quote"]


def anchor_quote_of(anchor):
    if isinstance(anchor, dict):
        return str(anchor.get("quote", "") or "")
    if isinstance(anchor, str):
        return anchor
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="分组比较矩阵导出：groups 结果 → comparison_matrix.csv（UTF-8 BOM，csv 模块转义）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python write_matrix.py --groups groups.json --output comparison_matrix.csv")
    ap.add_argument("--groups", required=True, help="分组结果 JSON（{groups:[...]} 或列表）")
    ap.add_argument("--entries", help="parse_library.py 输出（papers 只有 ref 字符串时用于补全 title/year）")
    ap.add_argument("--output", required=True, help="CSV 输出路径")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        with open(args.groups, "r", encoding="utf-8-sig") as f:
            gdoc = json.load(f)
    except (OSError, ValueError) as e:
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "READ_FAILED", "detail": str(e)},
                         ensure_ascii=False))
        return 2

    groups = gdoc.get("groups", gdoc) if isinstance(gdoc, dict) else gdoc
    if not isinstance(groups, list):
        print(json.dumps({"script": SCRIPT, "version": VERSION, "error": "GROUPS_SHAPE_UNSUPPORTED",
                          "detail": "groups 需为列表或含 groups 键的对象"}, ensure_ascii=False))
        return 2

    entry_map = {}
    warnings = []
    if args.entries:
        try:
            with open(args.entries, "r", encoding="utf-8-sig") as f:
                edoc = json.load(f)
            entries = edoc.get("entries", []) if isinstance(edoc, dict) else edoc
            for e in entries:
                entry_map[str(e.get("id", ""))] = e
        except (OSError, ValueError) as e:
            warnings.append({"code": "ENTRIES_READ_FAILED", "detail": str(e)})

    rows = []
    for g in groups:
        gname = str(g.get("group", ""))
        gbasis = str(g.get("basis", ""))
        for p in (g.get("papers") or []):
            if isinstance(p, dict):
                ref = str(p.get("ref", ""))
                conclusion = str(p.get("conclusion", ""))
                conditions = str(p.get("conditions", ""))
                limitation = str(p.get("limitation", ""))
                quote = anchor_quote_of(p.get("anchor"))
            else:
                ref = str(p)
                conclusion = conditions = limitation = quote = ""
                warnings.append({"code": "PAPER_ONLY_REF",
                                 "detail": "分组 %r 中 %r 只有 ref：三列需由模型补齐后重导出" % (gname, ref)})
            e = entry_map.get(ref)
            title = str(e.get("title", "")) if e else ""
            year = str(e.get("year", "") or "") if e else ""
            if not e:
                warnings.append({"code": "REF_NOT_IN_ENTRIES",
                                 "detail": "条目 %r 不在 entries 中，title/year 留空" % ref})
            if not conclusion or not conditions or not limitation:
                warnings.append({"code": "INCOMPLETE_ROW",
                                 "detail": "条目 %r 的三列（conclusion/conditions/limitation）不完整" % ref})
            rows.append([gname, gbasis, ref, title, year, conclusion, conditions, limitation, quote])

    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    report = {
        "script": SCRIPT,
        "version": VERSION,
        "ok": True,
        "rows": len(rows),
        "groups": len(groups),
        "columns": COLUMNS,
        "warnings": warnings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

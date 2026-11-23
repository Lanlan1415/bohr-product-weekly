#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""numeric_consistency.py -- audit prose numbers against the parameter table.

Rule (writing09 "written accurately" hard check): every Arabic numeral in the
prose must be supported by a value extracted from the config files. A number
the table does not contain is flagged; it must be removed or marked
TODO-confirm(author), never left in to make the paragraph smooth.

Match levels (strong to weak):
  supported            value found in the table (param name also in the line)
  supported_value_only value found in the table, no name context in the line
  supported_percent    prose 90% matches table 0.9
  supported_rounded    prose ~0.9 matches table 0.8976 (1-3 decimals)
  unit_mismatch        prose 5 GB vs table 5 MB -- flagged
  unsupported          no value in the table -- flagged

Not audited (structural numbers, stripped before scanning): heading lines,
citations [1] / [3,5], table/figure/equation refs, step counters, list markers,
table leading index cells, file paths with extensions, TODO-confirm annotations.

Standalone CLI:
  python numeric_consistency.py --prose PROSE.md --table TABLE.json [--json OUT]
exit 0 = every number supported; 1 = unsupported/unit_mismatch found;
3 = input missing or unreadable. TABLE.json is a result.json, a parameter
table {"parameter_table": [...]}, or a bare list of rows.

Library use: audit_prose(text, rows) is imported by assemble_result.py.
Standard library only.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

NUM_TOKEN_RE = re.compile(
    r"\d+(?:\.\d+){2,}"                    # version 3.10.13
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?"       # thousands 8,640
    r"|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"     # 12 / 0.001 / 1e-3
)
VERSION_RE = re.compile(r"^\d+(?:\.\d+){2,}$")
TODO_RE = re.compile(r"TODO-confirm\s*\(([^)]*)\)")
TODO_STRIP_RE = re.compile(r"\[?\s*TODO-confirm\s*\([^)]*\)\s*[:：]?[^]\n]*\]?")

STRIP_PATTERNS = [
    re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]"),                          # [1] [3,5]
    re.compile(r"(表|图|式|公式|算法|附录|Table|Figure|Fig\.?|Equation|Eq\.?|"
               r"Algorithm|Listing|Section|Sec\.?|Chapter)\s*#?\s*\d+(?:\.\d+)*"),
    re.compile(r"(步骤|第\s*\d+\s*步|Step)\s*\d+"),
    re.compile(r"(?<![\w./\\\-])\d+(?:\.\d+)+(?=\s*(?:节|小节|章|部分|给出|介绍|描述|说明))"),
    re.compile(r"(?<![\w./\\\-])[\w.\-/\\]*\.(?:json|yaml|yml|ini|cfg|conf|log|txt|py|"
               r"csv|tsv|md|sh|pt|pth|bin|ckpt|npz|npy|tar|gz|zip)(?::\d+(?:[\-–]\d+)?)?",
               re.IGNORECASE),
    re.compile(r"(?<![\w.])[\w\-]*\d[\w\-]*[/\\][\w\-/\\]*(?![\w])"),
]
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
LIST_MARKER_RE = re.compile(r"^(\s*)(\d+[\.\)])\s+")
TABLE_LEAD_RE = re.compile(r"^(\s*\|\s*)(\d+)(\s*\|)")
UNIT_RE = re.compile(r"(\s*)(%|°[CF]?|[A-Za-zμ]{1,10})(?=$|[\s.,，、;；)）/'\"]|$)")

UNIT_CLASSES = {}
for _i, _group in enumerate([
    ("s", "sec", "secs", "second", "seconds"),
    ("ms", "millisecond", "milliseconds"),
    ("min", "mins", "minute", "minutes"),
    ("h", "hr", "hrs", "hour", "hours"),
    ("d", "day", "days"),
    ("gb", "gbyte", "gigabyte", "gigabytes"),
    ("gib",),
    ("mb", "mbyte", "megabyte", "megabytes"),
    ("mib",),
    ("kb", "kilobyte", "kilobytes"),
    ("tb",), ("tib",),
    ("%", "percent"),
    ("epoch", "epochs"),
    ("step", "steps"),
    ("layer", "layers"),
    ("head", "heads"),
    ("token", "tokens"),
    ("image", "images"),
    ("sample", "samples"),
    ("class", "classes"),
    ("dim",), ("x",), ("k",),
]):
    for _u in _group:
        UNIT_CLASSES[_u] = _i


def unit_class(unit):
    if not unit:
        return None
    return UNIT_CLASSES.get(unit.lower().strip(), unit.lower().strip())


def units_compatible(u1, u2):
    if not u1 or not u2:
        return True  # one side unknown: prose often omits the unit
    return unit_class(u1) == unit_class(u2)


def read_text(path):
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def strip_structural(line):
    """Remove structural numbers and TODO-confirm spans. Returns (line, todo_count)."""
    todo = len(TODO_RE.findall(line))
    if todo:
        line = TODO_STRIP_RE.sub(" TODOCONFIRM ", line)
    for pat in STRIP_PATTERNS:
        line = pat.sub(" ", line)
    return line, todo


def prose_numbers(text):
    """Scan the prose; return (findings, todo_total). Findings are audited tokens."""
    findings = []
    todo_total = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        if HEADING_RE.match(raw):
            continue
        line, todo = strip_structural(raw)
        todo_total += todo
        for marker_re in (LIST_MARKER_RE, TABLE_LEAD_RE):
            m = marker_re.match(raw)
            if m:
                lead = m.group(2)
                idx = line.find(lead)
                if idx >= 0:
                    line = line[:idx] + " " * len(lead) + line[idx + len(lead):]
        for m in NUM_TOKEN_RE.finditer(line):
            tok = m.group(0)
            rest = line[m.end():]
            unit = None
            um = UNIT_RE.match(rest)
            # Attach a unit only when it is one we know (%/GB/epochs/...): an
            # arbitrary trailing word must never become a unit and later fire
            # a false unit_mismatch.
            if um and UNIT_CLASSES.get(um.group(2).lower()) is not None \
                    and not re.match(r"^[eE][+-]?\d", rest):
                unit = um.group(2)
            is_version = VERSION_RE.match(tok) is not None
            value = None
            if not is_version:
                try:
                    value = float(tok.replace(",", ""))
                except ValueError:
                    continue
            findings.append({
                "line": lineno,
                "token": tok,
                "value": value,
                "unit": unit,
                "is_version": is_version,
                "context": raw.strip()[:120],
                "col": m.start() + 1,
            })
    return findings, todo_total


def row_name(row):
    for key in ("name", "key", "raw_key"):
        if row.get(key):
            return str(row[key])
    return ""


def row_unit(row):
    unit = row.get("unit")
    return str(unit) if unit else ""


def row_numbers(row):
    """All numeric tokens carried by one parameter row."""
    out = []
    value = row.get("value", row.get("value_text"))
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        for m in NUM_TOKEN_RE.finditer(value):
            tok = m.group(0)
            if VERSION_RE.match(tok):
                continue
            try:
                out.append(float(tok.replace(",", "")))
            except ValueError:
                continue
    return out


def row_versions(row):
    value = row.get("value", row.get("value_text"))
    if isinstance(value, str):
        return [m.group(0).lower().lstrip("v") for m in NUM_TOKEN_RE.finditer(value)
                if VERSION_RE.match(m.group(0))]
    return []


def build_index(rows):
    exact = {}
    versions = {}
    for row in rows:
        for num in row_numbers(row):
            exact.setdefault(round(num, 9), []).append(row)
        for ver in row_versions(row):
            versions.setdefault(ver, []).append(row)
    return exact, versions


def name_in_line(row, line_lower):
    name = row_name(row).strip().lower()
    if not name:
        return False
    return name in line_lower or name.replace("_", " ") in line_lower


def best(rows):
    return rows[0] if rows else None


def verify(findings, exact, versions):
    results = []
    for f in findings:
        line_lower = f["context"].lower()
        if f["is_version"]:
            cands = versions.get(f["token"].lower().lstrip("v"), [])
            if cands:
                results.append((f, "supported", best(cands)))
            else:
                results.append((f, "unsupported", None))
            continue
        num, unit = f["value"], f["unit"]
        cands = exact.get(round(num, 9), [])
        strong = [p for p in cands
                  if name_in_line(p, line_lower) and units_compatible(unit, row_unit(p))]
        if strong:
            results.append((f, "supported", strong[0]))
            continue
        compat = [p for p in cands if units_compatible(unit, row_unit(p))]
        conflict = [p for p in cands if not units_compatible(unit, row_unit(p))]
        if compat:
            results.append((f, "supported_value_only", best(compat)))
            continue
        if conflict:
            results.append((f, "unit_mismatch", conflict[0]))
            continue
        dec = len(f["token"].split(".")[-1]) if "." in f["token"] else 0
        if 1 <= dec <= 3:
            rounded = [p for pv, plist in exact.items() for p in plist
                       if pv != round(num, 9) and abs(pv) < 1e6
                       and round(pv, dec) == round(num, dec)
                       and units_compatible(unit, row_unit(p))]
            if rounded:
                results.append((f, "supported_rounded", best(rounded)))
                continue
        if unit and unit_class(unit) == unit_class("%"):
            target = round(num / 100.0, 9)
            pct = exact.get(target, [])
            if not pct and 1 <= dec <= 3:
                pct = [p for pv, plist in exact.items() for p in plist
                       if abs(pv) < 1e6 and round(pv, dec) == round(num / 100.0, dec)]
            if pct:
                results.append((f, "supported_percent", best(pct)))
                continue
        results.append((f, "unsupported", None))
    return results


def known_value_strings(rows):
    found = set()
    for row in rows:
        value = row.get("value", row.get("value_text"))
        if value is None:
            continue
        found.add(str(value))
        if isinstance(value, float):
            found.add(f"{value:.12g}")
    return found


def audit_prose(text, rows):
    """Audit prose text against parameter rows. Returns the full report dict."""
    findings, todo_total = prose_numbers(text)
    exact, versions = build_index(rows)
    results = verify(findings, exact, versions)
    counts = {}
    rows_out = []
    unsupported = []
    for f, status, p in results:
        counts[status] = counts.get(status, 0) + 1
        rows_out.append({
            "line": f["line"], "col": f["col"], "token": f["token"],
            "value": f["value"], "unit": f["unit"], "status": status,
            "context": f["context"],
            "match": ({"param": row_name(p)} if p else None),
        })
        if status in ("unsupported", "unit_mismatch"):
            unsupported.append({"number": f["token"], "line": f["line"],
                                "status": status, "context": f["context"]})
    total = len(rows_out)
    supported = sum(v for k, v in counts.items() if k.startswith("supported"))
    return {
        "numbers_total": total,
        "supported": supported,
        "supported_value_only": counts.get("supported_value_only", 0),
        "supported_percent": counts.get("supported_percent", 0),
        "supported_rounded": counts.get("supported_rounded", 0),
        "unit_mismatch": counts.get("unit_mismatch", 0),
        "unsupported": counts.get("unsupported", 0),
        "todo_confirm_count": todo_total,
        "support_rate": round(supported / total, 4) if total else 1.0,
        "unsupported_numbers": unsupported,
    }


def rows_from_payload(payload):
    """Accept a bare row list, a parameter table, or a full result envelope."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        inner = payload["result"] if isinstance(payload.get("result"), dict) else payload
        for key in ("parameter_table", "params", "parameters"):
            if isinstance(inner.get(key), list):
                return inner[key]
    raise ValueError("no parameter_table/params row list found")


def load_rows(path):
    return rows_from_payload(json.loads(read_text(path)))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Audit prose numbers against the parameter table (writing09 hard check).")
    ap.add_argument("--prose", required=True, help="prose markdown path")
    ap.add_argument("--table", required=True,
                    help="result.json, parameter_table JSON, or bare row list")
    ap.add_argument("--json", dest="json_out", help="write the audit report here")
    args = ap.parse_args(argv)
    try:
        text = read_text(args.prose)
    except OSError as e:
        sys.stderr.write("[numeric_consistency] prose unreadable: %s\n" % e)
        return 3
    try:
        rows = load_rows(args.table)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        sys.stderr.write("[numeric_consistency] table unreadable: %s\n" % e)
        return 3
    report = audit_prose(text, rows)
    report["generated_by"] = "numeric_consistency.py (methods-from-config)"
    report["prose"] = args.prose
    report["table"] = args.table
    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        with io.open(args.json_out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    sys.stdout.write(
        "[numeric_consistency] numbers=%d supported=%d (value_only=%d percent=%d rounded=%d) "
        "unit_mismatch=%d unsupported=%d todo_confirm=%d\n"
        % (report["numbers_total"], report["supported"], report["supported_value_only"],
           report["supported_percent"], report["supported_rounded"],
           report["unit_mismatch"], report["unsupported"], report["todo_confirm_count"]))
    for item in report["unsupported_numbers"]:
        sys.stdout.write("  !! L%s %s (%s) | %s\n"
                         % (item["line"], item["number"], item["status"], item["context"][:80]))
    return 0 if not report["unsupported_numbers"] else 1


if __name__ == "__main__":
    sys.exit(main())

"""Audit/render one structured section with complete case and output contracts.

0 clean, 3 review, 4 blocked, 5 undetermined. Every exit writes result.json.
Generated diagram artifacts are real files; invalid graphs are never called clean.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402


def _contract(spec, derived, limits):
    contract = spec.get("output_contract")
    if contract is None:
        return {}
    if isinstance(contract, list):
        contract = {k: None for k in contract if isinstance(k, str)}
    if not isinstance(contract, dict):
        limits.append("output_contract is not an object or list of field names; fields cannot be echoed")
        return {}
    out = {}
    for raw_key in contract:
        key = str(raw_key)
        if key in derived:
            out[key] = derived[key]
        elif key in spec:
            out[key] = spec[key]
        else:
            out[key] = None
            limits.append("output_contract field '%s' is not derivable by this audit" % key)
    return out


def _refused(out_dir, message, spec=None, case_id=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    limits = ["the case could not be run as declared"]
    result = {"schema_version": "secrun/v2", "case_id": case_id or (spec or {}).get("case_id"),
              "status": "undetermined", "artifacts": {},
              "findings": [{"rule": "audit.no_section", "severity": "high", "message": message}],
              "severity_counts": {"high": 1}, "limits": limits}
    if result["case_id"] is not None:
        result["case_id"] = str(result["case_id"])
    if isinstance(spec, dict):
        derived = dict(result)
        result["output_contract"] = _contract(spec, derived, limits)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def build_and_audit(spec_path, out_dir, section=None, case_id=None):
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, "the spec file is not readable JSON: %s" % exc, case_id=case_id)
    except OSError:
        return _refused(out_dir, "the spec file could not be read", case_id=case_id)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object", case_id=case_id)
    sec = section or spec.get("section")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cid = case_id or spec.get("case_id")
    if not isinstance(sec, str) or not sec.strip():
        return _refused(out_dir, "no section declared, so no rules apply", spec, cid)
    sec = sec.strip()
    if sec not in S.SECTIONS:
        return _refused(out_dir, "unknown section '%s', so no rules apply" % sec, spec, cid)

    findings, status, counts = S.run(spec, sec)
    limits = []
    checked = {"section": sec, "items": _count(spec, sec)}
    if sec == "compare_docs":
        checked["coverage"] = S.compare_coverage(spec)
    artifacts, layout = {}, None
    sources = []
    if sec == "mindmap":
        try:
            import mindmap_render
            artifacts = mindmap_render.write_mindmap(spec, out_dir)
            layout = artifacts["layout.json"]
            structured = json.loads((out_dir / "mindmap.json").read_text(encoding="utf-8"))
            sources = structured["sources"]
            checked.update(nodes=layout["node_count"], edges=layout["edge_count"],
                           overlap_pairs=len(layout["overlap_pairs"]),
                           boundary_violations=len(layout["boundary_violations"]))
            limits.append(mindmap_render.OPTIONAL_PREVIEW_HELP)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            findings.append({"rule": "artifact.layout_failed", "severity": "high",
                             "message": "the diagram could not be generated as a bounded non-overlapping artifact: %s" % str(exc)[:220]})
            status = "blocked"
            counts["high"] = counts.get("high", 0) + 1
    derived = {"case_id": str(cid) if cid is not None else None, "status": status, "section": sec,
               "findings": findings, "severity_counts": counts, "checked": checked, "limits": limits,
               "artifacts": artifacts, "sources": sources}
    for name, filename in (("mindmap_svg", "mindmap.svg"), ("svg", "mindmap.svg"),
                            ("editable_map", "mindmap.html"), ("preview", "mindmap.html"),
                            ("freemind", "mindmap.mm"), ("mindmap_json", "mindmap.json"),
                            ("layout", "layout.json")):
        if filename in artifacts:
            derived[name] = artifacts[filename]
    echo = _contract(spec, derived, limits)
    result = {"schema_version": "secrun/v2", "status": status, "section": sec,
              "case_id": str(cid) if cid is not None else None,
              "findings": findings, "severity_counts": counts, "limits": limits,
              "checked": checked, "artifacts": artifacts, "sources": sources}
    if layout is not None:
        result["layout"] = layout
    result["output_contract"] = echo
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _count(spec, section):
    for key in ("conclusions", "claims", "documents", "formulas", "answers", "paragraphs",
                "statements", "aims", "chapters", "nodes"):
        value = spec.get(key)
        if isinstance(value, (list, tuple, dict)):
            return len(value)
    if isinstance(spec.get("text"), str):
        return len(spec["text"].split())
    if isinstance(spec.get("checklist"), dict):
        return len(spec["checklist"])
    return 0


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="secrun", description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--section", help="override the spec's declared section")
    parser.add_argument("--case-id", help="override case identifier without guessing one")
    args = parser.parse_args(argv)
    result = build_and_audit(Path(args.spec), Path(args.out), args.section, args.case_id)
    print(json.dumps({"status": result["status"], "section": result.get("section"),
                      "case_id": result.get("case_id"),
                      "findings": [f["rule"] for f in result["findings"]],
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

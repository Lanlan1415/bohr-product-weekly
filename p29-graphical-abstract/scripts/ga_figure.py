"""Graphical abstract: four-stage render, source audit and structured refusal.

Primary entry point for the official graphical_abstract workorder. The result
contains the original case_id and every output_contract field, real SVG/PNG/PDF
artifacts, source/value mappings, scope limits and deterministic-export checks.
"""
from __future__ import annotations

import copy
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # Keep the JSON refusal path alive on minimal Python images.
    import matplotlib.pyplot as plt  # noqa: E402
    import ga_narrative  # noqa: E402
    import schematic  # noqa: E402
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - dependency-limited images only
    plt = None
    ga_narrative = None
    schematic = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

import contract_echo  # noqa: E402
import graphical_abstract as G  # noqa: E402
import provenance  # noqa: E402

EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}
SCHEMA = "ga-figure/v2"


def _write(out_dir: Path, result: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _refused(out_dir: Path, message: str, case_id: str | None = None, spec: dict | None = None) -> dict:
    result = {"schema_version": SCHEMA, "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high", "message": message}],
              "sources": [], "uncertainty": [], "change_records": [],
              "artifacts": {}, "limits": ["the case could not be run as declared; no partial figure was delivered"]}
    if case_id is not None:
        result["case_id"] = str(case_id)
    if isinstance(spec, dict):
        uncertainty = spec.get("uncertainty")
        result["uncertainty"] = uncertainty if isinstance(uncertainty, list) else []
        changes = spec.get("change_records")
        result["change_records"] = changes if isinstance(changes, list) else []
        result = contract_echo.apply(result, spec)
    else:
        result["limits"].append("no readable case/spec was available for output_contract passthrough")
    return _write(Path(out_dir), result)


def _case_contract(case: dict | None) -> dict:
    return copy.deepcopy(case) if isinstance(case, dict) else {}


def _sources(spec: dict) -> list[dict]:
    nodes = spec.get("nodes") or []
    records = []
    for material in spec.get("materials") or []:
        if not isinstance(material, dict):
            records.append({"id": str(material), "source": None, "used_by": []})
            continue
        mid = str(material.get("id") or material.get("name") or "")
        records.append({"id": mid, "name": material.get("name"), "source": material.get("source"),
                        "used_by": [str(n.get("id")) for n in nodes
                                    if isinstance(n, dict) and str(n.get("evidence") or "") == mid]})
    return records


def build_and_audit(spec_path: Path, out_dir: Path, source_values: list[str] | None = None,
                    case_id: str | None = None, case: dict | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    carrier = _case_contract(case)
    if case_id is not None:
        carrier["case_id"] = case_id
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}",
                        case_id or carrier.get("case_id"), carrier)
    except OSError as exc:
        return _refused(out_dir, f"the spec file could not be read: {exc}",
                        case_id or carrier.get("case_id"), carrier)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object",
                        case_id or carrier.get("case_id"), carrier)
    for key, value in carrier.items():
        if key in ("case_id", "output_contract") or key not in spec:
            spec[key] = value
    if case_id is None:
        case_id = spec.get("case_id")
    if _IMPORT_ERROR is not None:
        return _refused(out_dir, f"scientific rendering dependencies are unavailable: {_IMPORT_ERROR}; "
                               "no SVG/PNG/PDF was claimed; install matplotlib, numpy and Pillow, then rerun",
                        case_id if isinstance(case_id, str) else None, spec)

    try:
        built = ga_narrative.render(spec, out_dir / "figure")
        layout = schematic.audit(spec, built)
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        return _refused(out_dir, f"the spec could not be drawn or audited: {type(exc).__name__}: {exc}",
                        case_id if isinstance(case_id, str) else None, spec)

    if source_values is None:
        source_values = spec.get("source_values")
    claim = G.audit_graphical_abstract(spec, source_values)
    findings = layout["findings"] + claim["findings"]
    prov = provenance.audit_provenance(spec, expect_connections=False)
    findings.extend(prov["findings"])
    for mark in built.get("visual_marks", []):
        actual = mark.get("rendered_value")
        expected = mark.get("source_value")
        if actual is None or expected is None or abs(float(actual) - float(expected)) > 1e-8 * max(1.0, abs(float(expected))):
            findings.append({"rule": "ga.visual_render_mismatch", "severity": "high",
                             "message": "rendered result geometry disagrees with its source value",
                             **{k: mark.get(k) for k in ("node", "item", "source_value", "rendered_value")}})
    det = provenance.check_deterministic(spec, ga_narrative.render)
    if not det["deterministic"]:
        findings.append({"rule": "repro.nondeterministic", "severity": "high",
                         "message": "two renders of the same spec differ in text or geometry", "detail": det["detail"]})
    counts = {}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1

    uncertainty = spec.get("uncertainty")
    changes = spec.get("change_records")
    result = {
        "schema_version": SCHEMA,
        "status": "clean" if not findings else "blocked" if counts.get("high") else "review",
        "findings": findings, "severity_counts": counts,
        "audits": {"layout_status": layout["status"], "claim_status": claim["status"],
                   "claim_checked": claim["checked"],
                   "visual_marks_checked": len(built.get("visual_marks", []))},
        "artifacts": {**layout["checked"]["artifacts"], "resolved_spec": str(spec_path)},
        "provenance": prov,
        "reproducibility": det,
        "font": {"family": built["font"].family, "path": built["font"].path,
                 "missing_glyphs": "".join(built["font"].missing)},
        "sources": _sources(spec),
        "uncertainty": uncertainty if isinstance(uncertainty, list) else [],
        "change_records": changes if isinstance(changes, list) else [],
        "limitations": copy.deepcopy(spec.get("limitations") or []),
        "visual_narrative": {
            "core_message": copy.deepcopy(spec.get("core_message")),
            "reading_order": copy.deepcopy(spec.get("reading_order") or []),
            "takeaways": copy.deepcopy(spec.get("takeaways") or {}),
            "result_modality": spec.get("result_modality") or "quantitative",
        },
        "visual_marks": built.get("visual_marks", []),
        "accessibility": {"palette": "Okabe-Ito + textual role headings + direct labels",
                          "svg_title_description": built.get("description"),
                          "note": "geometry, text and file checks are not a claim of scientific peer review"},
        "spec": spec,
        "limits": ["Source-backed structure, values, text bounds and file structure are checked; scientific judgement remains with the author/reviewer."],
    }
    if case_id is not None:
        result["case_id"] = str(case_id)
    result = contract_echo.apply(result, spec)
    _write(out_dir, result)
    plt.close(built["fig"])
    return result


def _merge_edit(base: dict, patch: dict) -> dict:
    merged = copy.deepcopy(base)
    protected = {"materials", "source_values", "takeaways"}
    def apply(target: dict, changes: dict, prefix: str = ""):
        for key, value in changes.items():
            path = f"{prefix}.{key}" if prefix else key
            if path.split(".", 1)[0] in protected:
                raise ValueError(f"source-preserving edit cannot replace {path.split('.', 1)[0]}")
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                apply(target[key], value, path)
            else:
                target[key] = copy.deepcopy(value)
    apply(merged, patch)
    return merged


def _diff(before: dict, after: dict) -> list[dict]:
    records = []
    def walk(old, new, path=""):
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(set(old) | set(new)):
                if key != "change_records":
                    walk(old.get(key), new.get(key), f"{path}.{key}" if path else key)
        elif old != new:
            records.append({"path": path, "before": old, "after": new})
    walk(before, after)
    return records


def _live_svg(path: str) -> int:
    root = ET.fromstring(Path(path).read_text(encoding="utf-8-sig"))
    names = [element.tag.rsplit("}", 1)[-1] for element in root.iter()]
    if root.tag.rsplit("}", 1)[-1] != "svg" or "text" not in names:
        raise ValueError("base-figure must be well-formed SVG with live text")
    return len(names)


def _read_object(path: str | None, label: str) -> dict:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="ga_figure", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--case", help="original case.json for independent case_id/output_contract passthrough")
    ap.add_argument("--edit", help="JSON merge patch for a source-preserving edit")
    ap.add_argument("--base-figure", help="existing live-text SVG being edited")
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", help="case identifier override")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    case, cid, edit_changes, base_figure = {}, args.case_id, [], None
    try:
        case = _read_object(args.case, "case")
        cid = cid or case.get("case_id")
        if args.base_figure and not args.edit:
            raise ValueError("--base-figure requires --edit")
        spec = _read_object(args.spec, "spec")
        before = copy.deepcopy(spec)
        if args.edit:
            patch = _read_object(args.edit, "edit")
            spec = _merge_edit(spec, patch)
            edit_changes = _diff(before, spec)
            spec["change_records"] = edit_changes
            base_figure = {"path": args.base_figure, "elements": _live_svg(args.base_figure)} if args.base_figure else None
        for key, value in case.items():
            if key in ("case_id", "output_contract") or key not in spec:
                spec[key] = value
        if cid is not None:
            spec["case_id"] = cid
        out_dir.mkdir(parents=True, exist_ok=True)
        resolved = out_dir / "resolved_spec.json"
        resolved.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        result = build_and_audit(resolved, out_dir, case_id=cid, case=case)
        if args.edit:
            changes_path = out_dir / "change_records.json"
            changes_path.write_text(json.dumps(edit_changes, ensure_ascii=False, indent=2), encoding="utf-8")
            result["change_records"] = edit_changes
            result.setdefault("artifacts", {})["change_records"] = str(changes_path)
            result.setdefault("sources", []).append({"role": "base_spec", "source": str(args.spec)})
            if base_figure:
                result["sources"].append({"role": "base_editable_svg", **base_figure})
            _write(out_dir, result)
    except Exception as exc:
        result = _refused(out_dir, f"request could not be prepared: {type(exc).__name__}: {exc}",
                          cid if isinstance(cid, str) else None, case)
    print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                      "findings": [f["rule"] for f in result.get("findings", [])],
                      "visual_marks": len(result.get("visual_marks") or []),
                      "wrote": str(out_dir / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

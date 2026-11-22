"""Apparatus / technical-roadmap figure: render, then audit layout and structure.

The layout engine is shared with the schematic skill. What this adds is the
structural audit — components from the bill of materials, indistinguishable
duplicates, orphans, stage numbering, decision branching, entry and exit.

In this package the pathway entry point is the documented route for mechanism
figures; this module stays for mixed cases that also ask for an apparatus panel
and for the shared-structure bench regression. It carries the same refusal
discipline as pathway.py: a spec that cannot be read or drawn is recorded as
status undetermined with the contract echoed — never a traceback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402

import apparatus  # noqa: E402
import provenance  # noqa: E402
import schematic  # noqa: E402
import contract_echo  # noqa: E402


def _read_case(case_path: Path | None) -> dict | None:
    if case_path is None:
        return None
    try:
        case = json.loads(Path(case_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
        return None
    return case if isinstance(case, dict) else None


def _read_meta(meta_path: Path | None) -> dict:
    if meta_path is None or not Path(meta_path).exists():
        return {}
    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value if x is not None][:100]
    return [str(value)]


def _refused(out_dir: Path, message: str, case: dict | None) -> dict:
    """Recorded refusal: status undetermined, contract echoed inline (no spec here)."""
    result = {"schema_version": "apparatus-figure/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared; nothing was drawn"],
              "sources": [], "uncertainty": [message]}
    if isinstance(case, dict):
        cid = case.get("case_id")
        if cid is not None:
            result["case_id"] = cid
        contract = case.get("output_contract")
        if isinstance(contract, dict):
            result["output_contract"] = contract
            limits = result.setdefault("limits", [])
            for key in contract:
                if key == "case_id":
                    result.setdefault("case_id", cid)
                    continue
                if key in result:
                    continue
                result[key] = None
                limits.append(f"output_contract field '{key}' was not derivable by this audit")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path: Path, out_dir: Path, case_path: Path | None = None,
                    meta_path: Path | None = None) -> dict:
    case = _read_case(case_path)
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}", case)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object", case)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        built = schematic.render(spec, out_dir / "figure")
        layout = schematic.audit(spec, built)
        struct = apparatus.audit_apparatus(spec)
    except (ValueError, TypeError, AttributeError, KeyError, IndexError) as exc:
        return _refused(out_dir, f"the spec cannot be drawn or audited: {exc}", case)

    findings = layout["findings"] + struct["findings"]

    # Re-run reproducibility: the challenge's third criterion is that someone else can
    # run the skill again and get the same figure.
    det = provenance.check_deterministic(spec, schematic.render)
    if not det["deterministic"]:
        findings.append({
            "rule": "repro.nondeterministic", "severity": "high",
            "message": "rendering the same spec twice produced different output, so the figure "
                       "cannot be reproduced by a reader",
            "detail": det["detail"]})
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    svg, png, pdf = str(built["svg"]), str(built["png"]), str(built["pdf"])
    font = built["font"]
    result = {
        "schema_version": "apparatus-figure/v1",
        "figure_kind": struct["figure_kind"],
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "figure": {"svg": svg, "png": png, "pdf": pdf},
        "source": svg,
        "export": {
            "formats": ["svg", "png", "pdf"],
            "dpi": built["dpi"],
            "canvas_mm": (list(spec.get("canvas_mm"))
                          if isinstance(spec.get("canvas_mm"), (list, tuple)) else None),
            "font_family": font.family,
            "font_file": font.path,
            "font_embedded": "pdf: TrueType (type 42) subset embedded; svg: font-family declared, live text",
            "missing_glyphs": "".join(font.missing),
            "colour_palette": "Okabe-Ito (colour-blind-safe)",
            "live_text": True,
        },
        "findings": findings,
        "severity_counts": counts,
        "audits": {"layout_status": layout["status"], "structure_status": struct["status"]},
        "reproducibility": det,
        "provenance": struct.get("provenance"),
        "font": {"family": font.family, "path": font.path,
                 "missing_glyphs": "".join(font.missing)},
        "checked": layout["checked"],
        "sources": [],
        "uncertainty": [],
    }
    if font.missing:
        result.setdefault("limits", []).append(
            "labels contain characters with no glyph in the resolved font; the PNG/PDF may "
            "show empty boxes until a covering font is installed")

    meta = _read_meta(meta_path)
    if meta.get("sources") is not None:
        result["sources"] = _as_str_list(meta["sources"])[:60]
    if meta.get("uncertainty") is not None:
        result["uncertainty"] = _as_str_list(meta["uncertainty"])[:60]
    for extra in _as_str_list(meta.get("limits")):
        result.setdefault("limits", []).append(extra)

    result = contract_echo.apply(result, spec)
    result = contract_echo.apply_case(result, case, {
        "figure": result["figure"],
        "figure_svg": svg, "figure_png": png, "figure_pdf": pdf,
        "source": svg, "source_file": svg, "editable_source": svg,
        "preview": png, "preview_png": png, "preview_pdf": pdf,
        "pdf": pdf, "export_pdf": pdf,
        "font_report": result["font"], "export_check": result["export"],
    })
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    plt.close(built["fig"])
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="apparatusfig", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--case", help="case.json: echoes case_id and output_contract into result.json")
    ap.add_argument("--meta", help="meta.json: sources / uncertainty / limits merged into result.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out),
                        Path(a.case) if a.case else None,
                        Path(a.meta) if a.meta else None)
    print(json.dumps({"status": r["status"],
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

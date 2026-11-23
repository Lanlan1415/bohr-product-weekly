"""Pathway / mechanism figure: render, then audit layout AND nomenclature.

Two audits, one verdict:

  schematic.py   — is the figure drawn correctly (overlap, coverage, arrows, export)
  nomenclature.py — is each label a well-formed, unambiguous biological entity

A mechanism diagram can pass both and still be scientifically wrong; what these
two check is the class of error that is mechanically provable, so a reviewer only
has to spend attention on meaning.

Runtime contract: the CLI reads the case file (--case, normally /input/case.json)
so result.json always carries case_id and every output_contract field verbatim —
including on the refusal path, where there is no spec to echo from.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402

import nomenclature  # noqa: E402
import provenance  # noqa: E402
import schematic  # noqa: E402
import contract_echo  # noqa: E402


def _read_case(case_path: Path | None) -> dict | None:
    """Parse the case file, returning None on anything unreadable (never raises)."""
    if case_path is None:
        return None
    try:
        case = json.loads(Path(case_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
        return None
    return case if isinstance(case, dict) else None


def _read_meta(meta_path: Path | None) -> dict:
    """Parse the optional agent meta file; anything malformed degrades to empty."""
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


def _collect_sources(spec: dict) -> list[dict]:
    """Element → material → locator rows derived from the spec itself.

    The figure's trace chain, restated as data so a reviewer can verify each
    drawn element against the input without re-reading the spec.
    """
    out: list[dict] = []
    mats: dict[str, dict] = {}
    for m in (spec.get("materials") or []):
        if isinstance(m, dict) and m.get("id") is not None:
            mats[str(m["id"])] = m
    for n in (spec.get("nodes") or []):
        if not isinstance(n, dict):
            continue
        ev = str(n.get("evidence") or "").strip()
        if ev in mats:
            out.append({"element": str(n.get("label") or n.get("id")),
                        "kind": str(n.get("kind") or "node"),
                        "material": ev,
                        "locator": str(mats[ev].get("source") or ""),
                        "source_version": str(mats[ev].get("version")
                                              or spec.get("source_version") or "not supplied")})
    for c in (spec.get("connections") or []):
        if not isinstance(c, dict):
            continue
        src = str(c.get("source") or "").strip()
        if src:
            out.append({"element": f"{c.get('from')}->{c.get('to')}",
                        "kind": "connection", "material": None, "locator": src,
                        "source_version": str(c.get("version")
                                              or spec.get("source_version") or "not supplied")})
    return out[:40]


def _seed_uncertainty(spec: dict, built: dict, prov: dict, checklist_used: bool) -> list[str]:
    """Honest unknowns the engine can name on its own (default parameters etc.)."""
    items: list[str] = []
    if not spec.get("canvas_mm"):
        items.append("画布尺寸未由来源指定，引擎按布局自适应确定（canvas_mm 缺省）")
    if not spec.get("font_size"):
        items.append("字号使用引擎默认 9pt，非来源指定（font_size 缺省）")
    if any(isinstance(n, dict) and not n.get("color") for n in (spec.get("nodes") or [])):
        items.append("存在未指定颜色的节点，颜色由 Okabe-Ito 色盲安全色板按序分配，非来源指定")
    if prov.get("checked") is False:
        items.append("材料清单缺失，溯源审计未执行（provenance.checked=false）")
    font = built.get("font")
    if font is not None and font.missing:
        items.append(f"字体未覆盖 {len(font.missing)} 个图面字符（见 font.missing_glyphs），"
                     "需安装覆盖字体后重新导出")
    if not checklist_used:
        items.append("未提供实体/关系清单，覆盖审计（coverage）未执行")
    return items


def _refused(out_dir: Path, message: str, case: dict | None) -> dict:
    """A refusal is a recorded outcome: status undetermined, contract echoed.

    This path has no spec dict, so it does NOT call contract_echo (a helper that
    requires a spec and once crashed every refusal when batch-inserted here).
    The case file is read inline with its own guards instead.
    """
    result = {"schema_version": "pathway/v1", "status": "undetermined",
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
    if "case_id" in result:
        result = {"case_id": result.pop("case_id"), **result}
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path: Path, out_dir: Path, checklist_path: Path | None = None,
                    case_path: Path | None = None, meta_path: Path | None = None) -> dict:
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
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        # An undrawable spec (no drawable nodes, malformed structure) is a refusal
        # with the usual exit code, not a traceback.
        return _refused(out_dir, f"the spec cannot be drawn: {exc}", case)

    checklist_used = False
    try:
        layout = schematic.audit(spec, built)
        nom = nomenclature.audit_nomenclature(spec, built["svg"], built["nodes_valid"])
        findings = layout["findings"] + nom["findings"]
    except (ValueError, TypeError, AttributeError, KeyError, IndexError) as exc:
        # The figure rendered but the audit could not finish: record an honest
        # undetermined verdict instead of crashing without a result file.
        return _refused(out_dir, f"the audit could not complete: {exc}", case)

    # Same three criteria as any source-bound figure: every entity traced, every
    # relation stated by the source, and re-running gives the same figure.
    prov = provenance.audit_provenance(spec, nodes=built["nodes_valid"])
    findings.extend(prov["findings"])
    findings.extend(provenance.check_numbering(spec, built["nodes_valid"]))

    det = provenance.check_deterministic(spec, schematic.render)
    if not det["deterministic"]:
        findings.append({
            "rule": "repro.nondeterministic", "severity": "high",
            "message": "rendering the same spec twice produced different output, so the figure "
                       "cannot be reproduced by a reader", "detail": det["detail"]})

    coverage = None
    if checklist_path is not None and Path(checklist_path).exists():
        checklist_used = True
        try:
            coverage = schematic.coverage(spec, json.loads(
                Path(checklist_path).read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            coverage = None
            findings.append({
                "rule": "checklist.unreadable", "severity": "medium",
                "message": "the checklist file is not readable JSON, so source coverage could "
                           "not be audited against it"})
        if coverage and (coverage["missing_entities"] or coverage["missing_relations"]):
            findings.append({
                "rule": "coverage.incomplete", "severity": "high",
                "message": "the figure omits an entity or relation the source states",
                "missing_entities": coverage["missing_entities"],
                "missing_relations": coverage["missing_relations"]})

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    svg, png, pdf = str(built["svg"]), str(built["png"]), str(built["pdf"])
    font = built["font"]
    spec_hash = hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode("utf-8")).hexdigest()
    result = {
        "schema_version": "pathway/v2",
        "input": {"spec_path": str(spec_path), "spec_sha256": spec_hash},
        "change_records": [{"sequence": 1, "action": "render+audit",
                            "input_sha256": spec_hash, "engine": "pathway/v2",
                            "outputs": ["figure.svg", "figure.png", "figure.pdf"],
                            "human_confirmation": "see meta.sources / uncertainty when supplied"}],
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
            "semantic_layer_ids": layout["checked"].get("editable_groups", []),
            "legend_items_rendered": layout["checked"].get("legend_items_rendered", 0),
        },
        "findings": findings,
        "severity_counts": counts,
        "coverage": coverage,
        "reproducibility": det,
        "provenance": prov,
        "font": {"family": font.family, "path": font.path,
                 "missing_glyphs": "".join(font.missing)},
        "audits": {"layout_status": layout["status"], "nomenclature_status": nom["status"],
                   "fonts_checked": nom["fonts_checked"], "species": nom["species"]},
        "checked": layout["checked"],
        "sources": _collect_sources(spec),
        "uncertainty": _seed_uncertainty(spec, built, prov, checklist_used),
    }
    if font.missing:
        result.setdefault("limits", []).append(
            "labels contain characters with no glyph in the resolved font; the PNG/PDF may "
            "show empty boxes until a covering font is installed")

    meta = _read_meta(meta_path)
    if meta.get("sources") is not None:
        result["sources"] = list(result["sources"]) + _as_str_list(meta["sources"])[:60]
    if meta.get("uncertainty") is not None:
        result["uncertainty"] = list(result["uncertainty"]) + _as_str_list(meta["uncertainty"])[:60]
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
    if "case_id" in result:
        result = {"case_id": result.pop("case_id"), **result}
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    plt.close(built["fig"])
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="pathway", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--checklist")
    ap.add_argument("--case", help="case.json (/input/case.json): echoes case_id and "
                                   "output_contract verbatim into result.json, on every path")
    ap.add_argument("--meta", help="meta.json written by the agent: sources / uncertainty / "
                                   "limits lists merged into result.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    r = build_and_audit(Path(a.spec), Path(a.out),
                        Path(a.checklist) if a.checklist else None,
                        Path(a.case) if a.case else None,
                        Path(a.meta) if a.meta else None)
    print(json.dumps({"status": r["status"],
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

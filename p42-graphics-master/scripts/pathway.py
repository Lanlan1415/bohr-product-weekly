"""Pathway / mechanism figure: render, then audit layout AND nomenclature.

Two audits, one verdict:

  schematic.py   — is the figure drawn correctly (overlap, coverage, arrows, export)
  nomenclature.py — is each label a well-formed, unambiguous biological entity

A mechanism diagram can pass both and still be scientifically wrong; what these
two check is the class of error that is mechanically provable, so a reviewer only
has to spend attention on meaning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402

import nomenclature  # noqa: E402
import provenance  # noqa: E402
import schematic  # noqa: E402
import contract_echo  # noqa: E402


def _refused(out_dir: Path, message: str) -> dict:
    result = {"schema_version": "pathway/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path: Path, out_dir: Path, checklist_path: Path | None = None) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        return _refused(out_dir, "spec file not found: " + str(exc))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        built = schematic.render(spec, out_dir / "figure")
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        # An undrawable spec (no nodes, malformed structure) is a refusal with the
        # usual exit code, not a traceback.
        return _refused(out_dir, f"the spec cannot be drawn: {exc}")
    layout = schematic.audit(spec, built)
    nom = nomenclature.audit_nomenclature(spec, built["svg"])

    findings = layout["findings"] + nom["findings"]

    # Same three criteria as any source-bound figure: every entity traced, every
    # relation stated by the source, and re-running gives the same figure.
    prov = provenance.audit_provenance(spec)
    findings.extend(prov["findings"])
    findings.extend(provenance.check_numbering(spec))

    det = provenance.check_deterministic(spec, schematic.render)
    if not det["deterministic"]:
        findings.append({
            "rule": "repro.nondeterministic", "severity": "high",
            "message": "rendering the same spec twice produced different output, so the figure "
                       "cannot be reproduced by a reader", "detail": det["detail"]})

    coverage = None
    if checklist_path is not None and Path(checklist_path).exists():
        coverage = schematic.coverage(spec, json.loads(Path(checklist_path).read_text(encoding="utf-8")))
        if coverage["missing_entities"] or coverage["missing_relations"]:
            findings.append({
                "rule": "coverage.incomplete", "severity": "high",
                "message": "the figure omits an entity or relation the source states",
                "missing_entities": coverage["missing_entities"],
                "missing_relations": coverage["missing_relations"],
            })

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    result = {
        "schema_version": "pathway/v1",
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "coverage": coverage,
        "reproducibility": det,
        "provenance": prov,
        "font": {"family": built["font"].family, "missing_glyphs": "".join(built["font"].missing)},
        "audits": {"layout_status": layout["status"], "nomenclature_status": nom["status"],
                   "fonts_checked": nom["fonts_checked"], "species": nom["species"]},
        "checked": layout["checked"],
    }
    result = contract_echo.apply(result, spec)
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
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    r = build_and_audit(Path(a.spec), Path(a.out),
                        Path(a.checklist) if a.checklist else None)
    print(json.dumps({"status": r["status"],
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

"""Apparatus / technical-roadmap figure: render, then audit layout and structure.

The layout engine is shared with the schematic skill. What this adds is the
structural audit — components from the bill of materials, indistinguishable
duplicates, orphans, stage numbering, decision branching, entry and exit.
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


def _refused(out_dir: Path, message: str) -> dict:
    """A spec that cannot be read or drawn is a refusal, not a traceback."""
    result = {"schema_version": "apparatus-figure/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path: Path, out_dir: Path) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        return _refused(out_dir, "spec file not found: " + str(exc))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
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
    struct = apparatus.audit_apparatus(spec)

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

    result = {
        "schema_version": "apparatus-figure/v1",
        "figure_kind": struct["figure_kind"],
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "audits": {"layout_status": layout["status"], "structure_status": struct["status"]},
        "versions": struct.get("provenance", {}).get("versions"),
        "reproducibility": det,
        "font": {"family": built["font"].family, "path": built["font"].path,
                 "missing_glyphs": "".join(built["font"].missing)},
        "checked": layout["checked"],
    }
    result = contract_echo.apply(result, spec)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    plt.close(built["fig"])
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="apparatusfig", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out))
    print(json.dumps({"status": r["status"],
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

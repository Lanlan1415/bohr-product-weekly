"""Graphical abstract: render, then audit the claim, the numbers and the limits.

The CLI is the case's entry point: it takes the spec built from the case
material, renders the figure, audits it, and writes a structured result.json.
A case that cannot be run at all (unreadable spec, not an object, rendering
failure) is still an outcome: it writes an undetermined result.json and exits
with a dedicated code instead of crashing with a traceback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402

import contract_echo  # noqa: E402
import graphical_abstract as G  # noqa: E402
import provenance  # noqa: E402
import schematic  # noqa: E402

EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


def _refused(out_dir: Path, message: str, case_id: str | None = None) -> dict:
    """A refusal is a recorded outcome: write result.json, status undetermined.

    Self-contained on purpose: it runs before any audit exists, so it depends on
    nothing but the json module and never calls the contract echoer -- the spec
    it would echo from is exactly the input that could not be read. Anything the
    caller passed as a plain case identifier on the command line is still kept.
    """
    result = {"schema_version": "ga-figure/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared; nothing was drawn"]}
    if case_id:
        result["case_id"] = str(case_id)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path: Path, out_dir: Path, source_values: list[str] | None = None,
                    case_id: str | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}", case_id)
    except OSError:
        return _refused(out_dir, "the spec file could not be read", case_id)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object", case_id)
    if case_id is None:
        case_id = spec.get("case_id")

    try:
        built = schematic.render(spec, out_dir / "figure")
        layout = schematic.audit(spec, built)
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        return _refused(out_dir, f"the spec could not be drawn or audited: {exc}",
                        case_id if isinstance(case_id, str) else None)

    if source_values is None:
        source_values = spec.get("source_values")
    claim = G.audit_graphical_abstract(spec, source_values)

    findings = layout["findings"] + claim["findings"]

    # Same three criteria as any source-bound figure, plus the glyph check: a graphical
    # abstract whose labels are empty boxes makes no claim at all.
    # A graphical abstract has no source wiring list: its progression is the reading
    # order, which the claim audit already checks.
    prov = provenance.audit_provenance(spec, expect_connections=False)
    findings.extend(prov["findings"])
    det = provenance.check_deterministic(spec, schematic.render)
    if not det["deterministic"]:
        findings.append({
            "rule": "repro.nondeterministic", "severity": "high",
            "message": "rendering the same spec twice produced different output, so the abstract "
                       "cannot be reproduced by a reader", "detail": det["detail"]})
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    result = {
        "schema_version": "ga-figure/v1",
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "audits": {"layout_status": layout["status"], "claim_status": claim["status"],
                   "claim_checked": claim["checked"]},
        "artifacts": layout["checked"]["artifacts"],
        "provenance": prov,
        "reproducibility": det,
        "font": {"family": built["font"].family,
                 "missing_glyphs": "".join(built["font"].missing)},
        "limits": [],
    }
    if case_id is not None:
        result["case_id"] = str(case_id)
    result = contract_echo.apply(result, spec)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    plt.close(built["fig"])
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="ga_figure", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", help="case identifier to record in result.json")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out), case_id=a.case_id)
    print(json.dumps({"status": r["status"],
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r.get("findings", [])],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

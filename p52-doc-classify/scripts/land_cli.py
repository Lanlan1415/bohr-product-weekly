"""CLI: run the five-step landing protocol over a batch directory.

    python land_cli.py --spec spec.json --root ./batch --out ./out [--execute]

Plan-only by default: writes out/result.json (inventory, old->new plan,
duplicates, version relations, findings) and out/plan.md. With --execute the
plan's moves run under --root and every op is journalled to out/journal.jsonl
(both-end sha256), so the batch is reversible and a rerun is a no-op.

Exit codes: 0 ok, 3 review (medium findings), 4 blocked (conflict/mismatch),
5 refused (unreadable spec, missing root, no entries). A refusal still writes
result.json — the refusal is a result, not a crash.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import land  # noqa: E402


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def run_spec(spec_path: Path, root: Path | None, out_dir: Path,
             execute_now: bool = False, fresh: bool = False) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        # Refusal path: minimal, self-contained — no contract echo here.
        result = {"schema_version": land.SCHEMA_VERSION, "status": "undetermined",
                  "refusal": {"rule": "land.spec_unreadable",
                              "message": "the spec file is not readable JSON: " + str(exc)},
                  "limits": ["the batch was not organised; nothing moved"]}
        _write_result(out_dir, result)
        return result
    if not isinstance(spec, dict):
        result = {"schema_version": land.SCHEMA_VERSION, "status": "undetermined",
                  "refusal": {"rule": "land.spec_unreadable",
                              "message": "the spec file is not a JSON object"},
                  "limits": ["the batch was not organised; nothing moved"]}
        _write_result(out_dir, result)
        return result

    root_eff = root or spec.get("root")
    result = land.land_run(spec, root_eff, out_dir, execute_now=execute_now,
                           fresh=fresh)

    # Echo the case's contract (result path only): case_id at the top level, and
    # every output_contract field either carried by the result already, copied
    # from the spec verbatim (bulky inputs excluded), or filled as null with an
    # honest limits note.
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    limits = result.setdefault("limits", [])
    oc = spec.get("output_contract")
    if isinstance(oc, dict):
        keys = list(oc.keys())
    elif isinstance(oc, list):
        keys = [str(k) for k in oc]
    else:
        keys = []
        if oc is not None:
            limits.append("output_contract is neither an object nor a list of "
                          "field names, so no contract fields were echoed")
    _bulky = ("output_contract", "entries", "taxonomy", "records", "text")
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _bulky:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this run")

    _write_result(out_dir, result)
    if result.get("status") in ("ok", "review"):
        (out_dir / "plan.md").write_text(land.render_plan_md(result), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="doc-land", description=__doc__)
    ap.add_argument("--spec", required=True, help="case spec JSON (entries + organize)")
    ap.add_argument("--root", default=None, help="batch root directory (overrides spec.root)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--execute", action="store_true",
                    help="execute the plan's moves (default: plan only)")
    ap.add_argument("--fresh", action="store_true",
                    help="re-plan from scratch instead of resuming the saved manifest")
    a = ap.parse_args(argv)
    result = run_spec(Path(a.spec), Path(a.root) if a.root else None, Path(a.out),
                      execute_now=a.execute, fresh=a.fresh)
    print(json.dumps({"status": result.get("status"),
                      "refusal": result.get("refusal"),
                      "changed": (result.get("executed") or {}).get("changed"),
                      "severity_counts": result.get("severity_counts")},
                     ensure_ascii=False))
    return {"ok": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(
        result.get("status"), 1)


if __name__ == "__main__":
    raise SystemExit(main())

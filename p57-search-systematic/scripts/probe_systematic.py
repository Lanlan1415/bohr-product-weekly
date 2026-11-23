"""Black-box hostile probes for systematic screening protocol and exit discipline."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case_common as C  # noqa: E402

BASE = json.loads((HERE.parent / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "systematic_cli.py"


def invoke(tmp, case=None, raw=None, filename="case.json", outname="out"):
    path = tmp / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw is not None else json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / outname
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path), "--out", str(out)],
                          capture_output=True, text=True, timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    return proc, result, out


def no_tb(p):
    return "Traceback" not in p.stderr and "Traceback" not in p.stdout


def scenario(tmp, name):
    base = copy.deepcopy(BASE)
    if name == "bad_json_exit5":
        p, r, _ = invoke(tmp, raw="{broken")
        return p.returncode == 5 and r["refusal"]["rule"] == "systematic.case_unreadable" and no_tb(p)
    if name == "array_case_exit4":
        p, r, _ = invoke(tmp, case=[])
        return p.returncode == 4 and r["refusal"]["rule"] == "systematic.case_not_object" and no_tb(p)
    if name == "unknown_section_exit5":
        base["section"] = "coverage"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "systematic.unknown_section" and no_tb(p)
    if name == "protocol_wrong_shape_exit5":
        base["screening_protocol"] = []
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "systematic.protocol_invalid" and no_tb(p)
    if name == "no_criteria_exit5":
        base["screening_protocol"].pop("inclusion_criteria")
        base["screening_protocol"].pop("exclusion_criteria")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "systematic.no_criteria" and no_tb(p)
    if name == "no_records_exit5":
        base.pop("documents")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "systematic.no_records" and no_tb(p)
    if name == "bad_record_shape_exit5":
        base["documents"] = 42
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] in {"search.material_shape", "systematic.no_records"} and no_tb(p)
    if name == "unknown_review_record_exit3":
        base["reviewer_decisions"][0]["record_id"] = "not-a-record"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and any(x["rule"] == "systematic.review_record_unknown" for x in r["findings"]) and no_tb(p)
    if name == "reviewer_identity_required":
        base["reviewer_decisions"][0].pop("reviewer")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and any(x["rule"] == "systematic.reviewer_identity_missing" for x in r["findings"]) \
            and not r["included_records"] and no_tb(p)
    if name == "unversioned_vote_is_review_not_silent":
        base["reviewer_decisions"][0].pop("criteria_version")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and any(x["rule"] == "systematic.review_version_unspecified" for x in r["findings"]) and no_tb(p)
    if name == "unresolved_adjudication_evidence_stays_pending":
        base["adjudications"][0]["evidence"] = ["not actually in the supplied source"]
        p, r, _ = invoke(tmp, case=base)
        wrong = next(x for x in r["screening_decisions"] if x["cluster_id"] == "10.3000/wrong-pop")
        return p.returncode == 3 and wrong["final_decision"] == "pending" \
            and any(x["rule"] == "systematic.adjudication_evidence_unverified" for x in r["findings"]) and no_tb(p)
    if name == "fulltext_pending_is_not_included":
        base["reviewer_decisions"] = [v for v in base["reviewer_decisions"] if not (v["record_id"] == "rec-001" and v["stage"] == "full_text" and v["reviewer"] == "reviewer-B")]
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and not r["included_records"] and r["flow_counts"]["full_text"]["pending"] == 1 \
            and r["prisma_counts_closed"] and no_tb(p)
    if name == "missing_search_date_is_review":
        base["screening_protocol"]["searches"][0].pop("date_searched")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and any(x["rule"] == "systematic.search_protocol_incomplete" for x in r["findings"]) and no_tb(p)
    if name == "contract_map_and_object_entries":
        base["output_contract"] = {"case_id": "id", "flow_counts": {}, "delivery": "caller", "missing": None}
        base["delivery"] = "preserved"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and r["delivery"] == "preserved" and r["case_id"] == base["case_id"] \
            and "missing" in r and r["missing"] is None and no_tb(p)
    if name == "contract_missing_status_cannot_spoof":
        base["output_contract"] = [{"field": "case_id"}, {"name": "status"}, {"key": "unknown"}]
        base["status"] = "pretend-clean"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and r["status"] == "review" and r["unknown"] is None and no_tb(p)
    if name == "unicode_path_deterministic":
        p, r, out = invoke(tmp, case=base, filename="系统/案例 file.json", outname="输出 A")
        p2, r2, out2 = invoke(tmp, case=base, filename="系统/案例 file.json", outname="输出 B")
        return p.returncode == p2.returncode == 0 and (out / "result.json").read_bytes() == (out2 / "result.json").read_bytes() and no_tb(p)
    if name == "usage_exit2":
        p = subprocess.run([sys.executable, "-I", str(CLI)], capture_output=True, text=True, timeout=30)
        return p.returncode == 2 and "Traceback" not in p.stderr
    raise ValueError(name)


NAMES = ["bad_json_exit5", "array_case_exit4", "unknown_section_exit5", "protocol_wrong_shape_exit5",
         "no_criteria_exit5", "no_records_exit5", "bad_record_shape_exit5", "unknown_review_record_exit3",
         "reviewer_identity_required", "unversioned_vote_is_review_not_silent",
         "unresolved_adjudication_evidence_stays_pending", "fulltext_pending_is_not_included",
         "missing_search_date_is_review", "contract_map_and_object_entries", "contract_missing_status_cannot_spoof",
         "unicode_path_deterministic", "usage_exit2"]


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in NAMES:
            try:
                ok, why = bool(scenario(tmp, name)), ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<62}{why}")
    passed = sum(r["pass"] for r in rows)
    C.write_json(HERE / "report_hostile.json", {
        "schema_version": "systematic-hostile/v1", "fixture": "synthetic_not_official",
        "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}})
    print(f"\n{passed}/{len(rows)} probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

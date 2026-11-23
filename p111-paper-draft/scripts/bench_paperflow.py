"""End-to-end bench for paperflow.py (paper-scale structure + delivery contract)."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paperflow as P  # noqa: E402

DRAFT = """# Introduction
We investigate coating uptake [doe2020] {M1}.

# Methods
We measured 3 mM samples with n = 6 {M2}.

# Results
Uptake rose three-fold {M1} (Fig 1).

# Conclusion
The coating supports a bounded uptake conclusion {M1}.
"""
BASE = {
    "case_id": "paperflow-demo", "section": "paper_draft", "draft": DRAFT,
    "abstract": "Uptake rose three-fold.", "design": "experimental",
    "template": {"sections": ["introduction", "methods", "results", "conclusion"]},
    "materials": [
        {"id": "M1", "locator": "run01.csv row 4", "text": "uptake rose three-fold with coating"},
        {"id": "M2", "locator": "notes.md lines 8-9", "text": "samples at 3 mM with n = 6"},
    ],
    "references": [{"key": "doe2020", "authors": "Doe J", "year": 2020,
                    "journal": "J Uptake", "topic": "coating uptake", "doi": "10.1000/x"}],
    "figures": [{"id": "Fig 1", "caption": "Uptake rose three-fold", "values": ["three-fold"]}],
    "declarations": {"data_availability": "repository", "author_contributions": "all authors",
                     "competing_interests": "none", "funding": "grant 123"},
    "change_log": ["v1 assembled from supplied records"],
    "argument_chain": [{
        "id": "Q1", "problem": "We investigate coating uptake",
        "method": "We measured 3 mM samples with n = 6", "evidence": ["M1"],
        "conclusion": "The coating supports a bounded uptake conclusion",
        "sections": {"problem": "Introduction", "method": "Methods", "conclusion": "Conclusion"},
    }],
    "output_contract": {"case_id": "id", "status": "engine", "manuscript_file": "editable",
                        "findings": "engine", "review_register": "unresolved"},
    "manuscript_file": {"path": "manuscript.md", "format": "markdown"},
}


def spec(**over):
    out = copy.deepcopy(BASE)
    out.update(over)
    return out


def run_spec(s):
    with tempfile.TemporaryDirectory() as td:
        return P.build(s, Path(td))


def main() -> int:
    scenarios = []

    def check(name, s, expected=(), forbidden=()):
        r = run_spec(s)
        fired = {f["rule"] for f in r["findings"]}
        ok = all(x in fired for x in expected) and not (fired & set(forbidden))
        if not expected:
            ok = not fired
        scenarios.append({"scenario": name, "expected": list(expected),
                          "fired": sorted(fired), "pass": ok})

    check("clean_full_paper", spec())
    check("real_heading_required", spec(draft=DRAFT.replace("# Methods", "Methods are described below.")),
          ["pf.section_heading_missing"])
    check("empty_section", spec(draft=DRAFT.replace("Uptake rose three-fold {M1} (Fig 1).", "")),
          ["pf.section_empty"])
    s = spec(); s["argument_chain"] = []
    check("chain_required", s, ["pf.argument_chain_missing"])
    s = spec(); del s["argument_chain"][0]["method"]
    check("chain_missing_link", s, ["pf.chain_link_missing"])
    s = spec(); s["argument_chain"][0]["problem"] = "A quote absent from the paper"
    check("chain_quote_locator", s, ["pf.chain_quote_not_in_draft"])
    s = spec(); s["argument_chain"][0]["evidence"] = ["M99"]
    check("chain_unknown_evidence", s, ["pf.chain_evidence_unknown"])
    s = spec(paragraph_links=[{"from": "P999", "to": "P001", "relation": "supports"}])
    check("context_link_invalid", s, ["pf.context_link_invalid"])
    s = spec(); s["draft"] = DRAFT.replace("We investigate coating uptake", "TODO-confirm coating uptake")
    check("placeholder_routed", s, ["pf.placeholder_unregistered"])
    # A complete context link is metadata validation, not an instruction to add prose.
    s = spec(paragraph_links=[{"from": "P001", "to": "P003", "relation": "method answers problem"}])
    check("context_link_valid", s)

    # Contract precedence and malformed-input refusal are end-to-end subprocess tests.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sp = root / "spec.json"; sp.write_text(json.dumps(spec(status="pretend-success"),
                                                            ensure_ascii=False), encoding="utf-8")
        out = root / "out"
        cmd = [sys.executable, "-I", str(HERE / "paperflow.py"), "--spec", str(sp),
               "--out", str(out)]
        a = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        b = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        first = (out / "result.json").read_bytes(); second = (out / "result.json").read_bytes()
        payload = json.loads(first)
        ok = (a.returncode == 0 and first == second and payload["case_id"] == "paperflow-demo"
              and payload["status"] == "clean" and payload["manuscript_file"]["path"] == "manuscript.md"
              and payload["review_register"] is None
              and any("review_register" in x for x in payload["limits"])
              and (out / "manuscript.md").is_file() and "Traceback" not in a.stderr)
        scenarios.append({"scenario": "contract_precedence_idempotency", "pass": ok,
                          "expected": ["engine>case>null+limits", "byte-identical"],
                          "fired": [payload["status"]]})
        bad = root / "bad.json"; bad.write_text("{broken", encoding="utf-8")
        badout = root / "badout"
        p = subprocess.run([sys.executable, "-I", str(HERE / "paperflow.py"), "--spec", str(bad),
                            "--out", str(badout)], capture_output=True, text=True, timeout=30)
        try:
            refused = json.loads((badout / "result.json").read_text(encoding="utf-8"))
            ok = (p.returncode == 5 and refused["status"] == "undetermined"
                  and "case_id" in refused and "Traceback" not in p.stderr)
        except Exception:
            ok = False
        scenarios.append({"scenario": "structured_refusal", "pass": ok,
                          "expected": ["exit5", "result.json", "no traceback"], "fired": []})

    for row in scenarios:
        print(("PASS" if row["pass"] else "FAIL") + f"  {row['scenario']:<34} {row['fired']}")
    passed = sum(bool(x["pass"]) for x in scenarios)
    report = {"schema_version": "paperflow-bench/v1", "scenarios": scenarios,
              "totals": {"passed": passed, "of": len(scenarios)}}
    (HERE / "report_paperflow.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    print(f"\n{passed}/{len(scenarios)} pass")
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Black-box hostile probes for quality_cli.py (synthetic fixtures only)."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLI = HERE / "quality_cli.py"
DOCS = json.loads((ROOT / "examples/studies.json").read_text(encoding="utf-8"))["documents"]
CLEAN, ABSTRACT = DOCS
PROBES = []
MISSING = object()


def probe(name, expected):
    def decorate(fn):
        PROBES.append((name, expected, fn))
        return fn
    return decorate


def base(doc=None, **kw):
    case = {"case_id": "hostile", "section": "quality", "documents": [copy.deepcopy(doc or CLEAN)],
            "research_question": "exercise chronic pain",
            "output_contract": ["case_id", "检索结果", "证据记录", "状态说明"]}
    case.update(kw)
    return case


def invoke(tmp: Path, case=MISSING, raw=None, missing_case=False):
    path = tmp / "case.json"
    if not missing_case:
        if raw is not None:
            path.write_bytes(raw if isinstance(raw, bytes) else str(raw).encode("utf-8"))
        else:
            path.write_text(json.dumps(base() if case is MISSING else case, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    result_path = out / "result.json"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        parseable = isinstance(result, dict)
    except Exception:
        result, parseable = {}, False
    return {"proc": proc, "result": result, "parseable": parseable, "out": out,
            "trace_free": "Traceback" not in proc.stdout + proc.stderr}


@probe("clean_contract", 0)
def _(tmp):
    return invoke(tmp), lambda r: r["status"] == "clean" and r["case_id"] == "hostile"


@probe("case_missing", 5)
def _(tmp):
    return invoke(tmp, missing_case=True), lambda r: r["refusal"]["rule"] == "quality.case_unreadable"


@probe("case_bad_json", 5)
def _(tmp):
    return invoke(tmp, raw="{bad"), lambda r: r["refusal"]["rule"] == "quality.case_unreadable"


@probe("case_not_object_exit4", 4)
def _(tmp):
    return invoke(tmp, raw="[]"), lambda r: r["refusal"]["rule"] == "quality.case_not_object"


@probe("unknown_section_exit5_contract_echo", 5)
def _(tmp):
    c = base(section="not-a-section", output_contract=["case_id", "delivery_note", "unknown"], delivery_note="kept")
    return invoke(tmp, c), lambda r: r["case_id"] == "hostile" and r["delivery_note"] == "kept" \
        and r["unknown"] is None and r["status"] == "undetermined"


@probe("missing_material_exit5_contract_echo", 5)
def _(tmp):
    c = base(documents_path="absent.json")
    c.pop("documents")
    return invoke(tmp, c), lambda r: r["case_id"] == "hostile" and "检索结果" in r and r["检索结果"] is None


@probe("malformed_material_json", 5)
def _(tmp):
    (tmp / "bad.json").write_text("{no", encoding="utf-8")
    c = base(documents_path="bad.json"); c.pop("documents")
    return invoke(tmp, c), lambda r: r["refusal"]["rule"] == "quality.material_unreadable"


@probe("material_wrong_shape", 5)
def _(tmp):
    (tmp / "bad.json").write_text('{"foo": 1}', encoding="utf-8")
    c = base(documents_path="bad.json"); c.pop("documents")
    return invoke(tmp, c), lambda r: r["refusal"]["rule"] == "quality.material_shape"


@probe("documents_wrong_type", 5)
def _(tmp):
    return invoke(tmp, base(documents={"id": "x"})), lambda r: r["refusal"]["rule"] == "quality.documents_invalid"


@probe("documents_empty", 5)
def _(tmp):
    return invoke(tmp, base(documents=[])), lambda r: r["refusal"]["rule"] == "quality.no_documents"


@probe("unsupported_pdf_not_fake_appraised", 5)
def _(tmp):
    (tmp / "paper.pdf").write_bytes(b"%PDF-fake")
    c = base(documents_path="paper.pdf"); c.pop("documents")
    return invoke(tmp, c), lambda r: r["refusal"]["rule"] == "quality.material_unsupported"


@probe("all_restricted_blocked_no_secret", 4)
def _(tmp):
    doc = dict(CLEAN, access="restricted", full_text="SECRET-RESTRICTED-TEXT")
    row = invoke(tmp, base(doc))
    blob = (row["out"] / "result.json").read_text(encoding="utf-8")
    return row, lambda r: r["refusal"]["rule"] == "quality.access_blocked" and "SECRET-RESTRICTED-TEXT" not in blob


@probe("mixed_restricted_partial_no_secret", 3)
def _(tmp):
    secret = dict(ABSTRACT, id="secret", access="red", abstract="SECRET-ABSTRACT-TEXT")
    row = invoke(tmp, base(documents=[copy.deepcopy(CLEAN), secret]))
    blob = (row["out"] / "result.json").read_text(encoding="utf-8")
    return row, lambda r: r["documents_appraised"] == 1 and "SECRET-ABSTRACT-TEXT" not in blob \
        and any("restricted" in x["reason"] for x in r["omissions"])


@probe("exact_duplicate_named", 3)
def _(tmp):
    return invoke(tmp, base(documents=[copy.deepcopy(CLEAN), copy.deepcopy(CLEAN)])), \
        lambda r: r["documents_appraised"] == 1 and any("duplicate" in x["reason"] for x in r["omissions"])


@probe("conflicting_duplicate_retained_separately", 3)
def _(tmp):
    other = copy.deepcopy(CLEAN); other["full_text"] += " Additional distinct reporting statement."
    return invoke(tmp, base(documents=[copy.deepcopy(CLEAN), other])), \
        lambda r: r["documents_appraised"] == 2 and any("#duplicate-" in a["doc_id"] for a in r["appraisals"])


@probe("contract_malformed_shape_no_crash", 0)
def _(tmp):
    return invoke(tmp, base(output_contract=7)), lambda r: any("unsupported type" in x for x in r["limits"])


@probe("contract_dict_preserved", 0)
def _(tmp):
    contract = {"case_id": None, "检索结果": None, "状态说明": None}
    return invoke(tmp, base(output_contract=contract)), lambda r: r["output_contract"] == contract \
        and isinstance(r["检索结果"], dict)


@probe("engine_status_beats_case_forgery", 3)
def _(tmp):
    return invoke(tmp, base(ABSTRACT, status="clean")), lambda r: r["status"] == "review"


@probe("review_decisions_wrong_container", 0)
def _(tmp):
    return invoke(tmp, base(review_decisions={"doc_id": "bad"})), lambda r: r["status"] == "clean"


@probe("review_decision_wrong_entries_ignored", 0)
def _(tmp):
    return invoke(tmp, base(review_decisions=[None, 7, "x", {"dimension": "unknown"}])), lambda r: r["status"] == "clean"


@probe("jsonl_real_material", 0)
def _(tmp):
    (tmp / "docs.jsonl").write_text(json.dumps(CLEAN, ensure_ascii=False) + "\n", encoding="utf-8")
    c = base(documents_path="docs.jsonl"); c.pop("documents")
    return invoke(tmp, c), lambda r: r["documents_appraised"] == 1 and r["status"] == "clean"


@probe("bom_case", 0)
def _(tmp):
    raw = b"\xef\xbb\xbf" + json.dumps(base(), ensure_ascii=False).encode("utf-8")
    return invoke(tmp, raw=raw), lambda r: r["case_id"] == "hostile"


@probe("nested_spec_case_identity_authoritative", 0)
def _(tmp):
    c = {"case_id": "outer-id", "section": "quality", "spec": {"case_id": "inner-id", "documents": [copy.deepcopy(CLEAN)]},
         "output_contract": ["case_id", "检索结果"]}
    return invoke(tmp, c), lambda r: r["case_id"] == "outer-id" and r["documents_appraised"] == 1


@probe("url_only_does_not_claim_remote_coverage", 5)
def _(tmp):
    c = base(materials=[{"url": "https://example.invalid/paper"}]); c.pop("documents")
    return invoke(tmp, c), lambda r: r["refusal"]["rule"] == "quality.no_documents"


@probe("deterministic_byte_replay", 0)
def _(tmp):
    row = invoke(tmp)
    second = tmp / "second"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(tmp / "case.json"),
                           "--out", str(second)], capture_output=True, text=True, timeout=120)
    same = proc.returncode == 0 and (row["out"] / "result.json").read_bytes() == (second / "result.json").read_bytes()
    return row, lambda r: same


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i, (name, expected, fn) in enumerate(PROBES):
            tmp = root / str(i); tmp.mkdir()
            try:
                row, checker = fn(tmp)
                proc, result = row["proc"], row["result"]
                extra = bool(checker(result))
                ok = proc.returncode == expected and row["parseable"] and row["trace_free"] and extra
                why = "" if ok else f"exit={proc.returncode} expected={expected}; json={row['parseable']}; trace_free={row['trace_free']}; predicate={extra}; stderr={proc.stderr[-200:]}"
            except Exception as exc:
                proc, result, ok, why = None, {}, False, f"harness {type(exc).__name__}: {exc}"
            rows.append({"probe": name, "expected_exit": expected, "actual_exit": proc.returncode if proc else None,
                         "result_json": bool(result), "traceback_free": bool(row.get("trace_free")) if 'row' in locals() else False,
                         "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<48}" + why)
    report = {"schema_version": "quality-hostile/v2", "fixture_notice": "synthetic hostile probes only",
              "probes": rows, "totals": {"passed": sum(x["pass"] for x in rows), "of": len(rows)}}
    (HERE / "report_hostile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} hostile probes pass")
    return 0 if all(x["pass"] for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

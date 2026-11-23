"""Adversarial evidence and non-destructive landing checks for doc-filebatch."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classify  # noqa: E402
import filebatch  # noqa: E402
import land  # noqa: E402

CLI = Path(__file__).resolve().parent / "filebatch_cli.py"
TAX = [{"category": "研究/实验方法", "cues": ["方法", "protocol", "we measured"]},
       {"category": "研究/研究结果", "cues": ["结果", "increased", "three-fold"]},
       {"category": "资料/数据集", "cues": ["dataset", "control"]}]


def _run(args):
    return subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI)] + list(map(str, args)),
                          capture_output=True, text=True, timeout=120)


def _fingerprints(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def _spec(root, case_id="case-filebatch"):
    spec = root / "spec.json"
    spec.write_text(json.dumps({"taxonomy": TAX, "case_id": case_id}, ensure_ascii=False), encoding="utf-8")
    case = root / "case.json"
    case.write_text(json.dumps({"case_id": case_id, "output_contract": {
        "library_result": {}, "operation_evidence": {}, "failure_recovery": {}, "required": 9}},
        ensure_ascii=False), encoding="utf-8")
    return spec, case


def scen_generic_extension_not_class(tmp, name):
    batch = classify.run({"taxonomy": [{"category": "资料/扫描", "cues": ["pdf", "file"]}],
                          "records": [{"id": "x.pdf", "text": "pdf file document scan"}]})
    result = batch["records"][0]
    return result["primary"] == "未分类" and not result["labels"] \
        and result["candidate_labels"] and result["review_required"]


def scen_title_weight_and_boundaries(tmp, name):
    titled = classify.classify_record("title", {"title": "Protocol for buffer", "text": "nothing"}, TAX)
    cat = classify.classify_record("cat", "concatenate protocolized", TAX)
    exact = classify.classify_record("exact", "protocol protocol", TAX)
    return titled["confidence"] == 1.0 and titled["source_evidence"][0]["field"] == "title" \
        and cat["primary"] == "未分类" and exact["primary"] == "研究/实验方法" \
        and exact["source_evidence"][0]["quote"] == "protocol"


def scen_multilevel_and_ambiguity(tmp, name):
    result = classify.run({"taxonomy": TAX, "records": [
        {"id": "ambiguous", "text": "方法 protocol。结果 increased"},
        {"id": "method", "text": "方法 protocol"}]})
    ambiguous = result["records"][0]
    methods = next(x for x in result["summary"]["hierarchy"] if x["category"] == "研究/实验方法")
    research = next(x for x in result["summary"]["hierarchy"] if x["category"] == "研究") \
        if any(x["category"] == "研究" for x in result["summary"]["hierarchy"]) else None
    return ambiguous["multi_label"] and ambiguous["ambiguity"]["is_ambiguous"] \
        and methods["level"] == 2 and methods["parent"] == "研究" \
        and methods["primary_subtree"] == 2 and research is None  # no undeclared parent fabricated


def scen_doi_real_provenance(tmp, name):
    root = tmp / name; root.mkdir()
    (root / "paper.txt").write_text("方法 protocol。DOI: 10.1234/example.7。", encoding="utf-8")
    result = filebatch.run({"taxonomy": TAX}, root, tmp / (name + "-out"))
    item = result["files"][0]
    return item["metadata"]["doi"] == "10.1234/example.7" \
        and "content_regex" in item["metadata_provenance"]["doi"] \
        and "year" not in item["metadata"] and "author" not in item["metadata"] \
        and result["plan"][0]["new"].startswith("研究/实验方法/")


def scen_ooxml_content_classification(tmp, name):
    root = tmp / name; root.mkdir()
    with zipfile.ZipFile(root / "paper.docx", "w") as zf:
        zf.writestr("docProps/core.xml", "<cp:coreProperties xmlns:cp='x' xmlns:dc='d'><dc:title>Protocol study</dc:title><dc:creator>Zhang</dc:creator></cp:coreProperties>")
        zf.writestr("word/document.xml", "<w:document xmlns:w='w'><w:p><w:r><w:t>We measured uptake with protocol.</w:t></w:r></w:p></w:document>")
    result = filebatch.run({"taxonomy": TAX}, root, tmp / (name + "-out"))
    item = result["files"][0]
    return item["classification"]["primary"] == "研究/实验方法" \
        and item["metadata"]["author"] == "Zhang" and item["metadata"]["title"] == "Protocol study" \
        and len(item["inventory"]["sha256"]) == 64


def _materializing_root(tmp, name):
    root = tmp / name; root.mkdir()
    (root / "method.txt").write_text("方法 protocol：we measured buffer uptake。", encoding="utf-8")
    (root / "copy.txt").write_text("方法 protocol：we measured buffer uptake。", encoding="utf-8")
    return root


def scen_materialize_readonly_idempotent(tmp, name):
    root = _materializing_root(tmp, name)
    before = _fingerprints(root)
    spec, case = _spec(tmp, name)
    out, dest = tmp / "out", tmp / "organized"
    args = ["--root", root, "--spec", spec, "--case", case, "--out", out, "--materialize", dest]
    p1 = _run(args)
    r1 = json.loads((out / "result.json").read_text(encoding="utf-8"))
    journal1 = (out / "copy_journal.jsonl").read_text(encoding="utf-8")
    p2 = _run(args)
    r2 = json.loads((out / "result.json").read_text(encoding="utf-8"))
    journal2 = (out / "copy_journal.jsonl").read_text(encoding="utf-8")
    copies_ok = r1["materialized"]["changed"] == 2 and all(
        hashlib.sha256((dest / row["new"]).read_bytes()).hexdigest() == row["sha256"]
        for row in r1["plan"])
    return p1.returncode == p2.returncode == 0 and before == _fingerprints(root) and copies_ok \
        and r2["materialized"]["changed"] == 0 and r2["materialized"]["already_done"] == 2 \
        and r2["materialized"]["idempotent"] and journal1 == journal2 \
        and r2["case_id"] == name and r2["required"] == 9


def scen_existing_target_not_overwritten(tmp, name):
    root = _materializing_root(tmp, name)
    out, dest = tmp / (name + "-out"), tmp / (name + "-dest")
    result = filebatch.run({"taxonomy": TAX}, root, out)
    target = dest / result["plan"][0]["new"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("someone else's file", encoding="utf-8")
    copied = land.materialize_plan(result["plan"], root, dest, out)
    return copied["status"] == "blocked" and target.read_text(encoding="utf-8") == "someone else's file" \
        and any(f["rule"] == "copy.target_conflict" for f in copied["findings"]) \
        and copied["input_writes"] == 0


def scen_same_name_different_bytes_not_dedup(tmp, name):
    root = tmp / name; root.mkdir()
    (root / "a.txt").write_text("方法 protocol first。", encoding="utf-8")
    (root / "b.txt").write_text("方法 protocol second。", encoding="utf-8")
    result = filebatch.run({"taxonomy": TAX}, root, tmp / (name + "-out"))
    return result["duplicates"] == [] and len(result["plan"]) == 2 \
        and len({row["new"] for row in result["plan"]}) == 2


def scen_cli_refusal_full_contract(tmp, name):
    root = tmp / name; root.mkdir(); (root / "a.txt").write_text("方法 protocol", encoding="utf-8")
    bad = tmp / "bad.json"; bad.write_text(json.dumps({"records": []}), encoding="utf-8")
    _, case = _spec(tmp, name)
    out = tmp / "out"
    proc = _run(["--root", root, "--spec", bad, "--case", case, "--out", out])
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return proc.returncode == 5 and result["case_id"] == name and result["required"] == 9 \
        and "library_result" in result and "failure_recovery" in result \
        and result["refusal"]["rule"] == "cls.empty_taxonomy"


def scen_cli_plan_deterministic(tmp, name):
    root = tmp / name; root.mkdir(); (root / "method.txt").write_text("方法 protocol", encoding="utf-8")
    spec, case = _spec(tmp, name)
    out = tmp / "out"
    args = ["--root", root, "--spec", spec, "--case", case, "--out", out]
    p1 = _run(args); first = (out / "result.json").read_bytes()
    p2 = _run(args); second = (out / "result.json").read_bytes()
    return p1.returncode == p2.returncode == 0 and first == second \
        and (out / "classification.json").is_file() and (out / "operation_plan.json").is_file()


def scen_bad_min_hits_degrades(tmp, name):
    root = tmp / name; root.mkdir(); (root / "method.txt").write_text("方法 protocol", encoding="utf-8")
    result = filebatch.run({"taxonomy": TAX, "min_hits": "not-a-number"}, root, tmp / (name + "-out"))
    return result["status"] == "ok" and result["files"][0]["classification"]["primary"] == "研究/实验方法"


SCENARIOS = [
    ("generic_extension_not_class", scen_generic_extension_not_class),
    ("title_weight_and_boundaries", scen_title_weight_and_boundaries),
    ("multilevel_and_ambiguity", scen_multilevel_and_ambiguity),
    ("doi_real_provenance", scen_doi_real_provenance),
    ("ooxml_content_classification", scen_ooxml_content_classification),
    ("materialize_readonly_idempotent", scen_materialize_readonly_idempotent),
    ("existing_target_not_overwritten", scen_existing_target_not_overwritten),
    ("same_name_different_bytes_not_dedup", scen_same_name_different_bytes_not_dedup),
    ("cli_refusal_full_contract", scen_cli_refusal_full_contract),
    ("cli_plan_deterministic", scen_cli_plan_deterministic),
    ("bad_min_hits_degrades", scen_bad_min_hits_degrades),
]


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, fn in SCENARIOS:
            try:
                ok, why = bool(fn(tmp, name)), ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<42}" + why)
    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "doc-filebatch-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_filebatch.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return int(passed != len(rows))


if __name__ == "__main__":
    raise SystemExit(main())

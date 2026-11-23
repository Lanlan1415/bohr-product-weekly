"""Real-file, contract and non-destruction checks for library-filecare."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filecare  # noqa: E402

CLI = Path(__file__).resolve().parent / "filecare_cli.py"


def _run(args):
    return subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI)] + list(map(str, args)),
                          capture_output=True, text=True, timeout=120)


def _fingerprints(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def scen_raw_hash_not_filename(tmp, name):
    root = tmp / ("root-" + name); root.mkdir()
    (root / "a.txt").write_text("identical bytes", encoding="utf-8")
    (root / "renamed.txt").write_text("identical bytes", encoding="utf-8")
    (root / "same-title.txt").write_text("different bytes", encoding="utf-8")
    result = filecare.run({}, root)
    group = result["duplicates"][0]
    assert len(group["sha256"]) == 64
    return group["paths"] == ["a.txt", "renamed.txt"] and len(result["documents"]) == 3


def scen_sidecar_provenance_conflicts(tmp, name):
    root = tmp / ("root-" + name); root.mkdir()
    (root / "preprint.txt").write_text("first content", encoding="utf-8")
    (root / "published.txt").write_text("second content", encoding="utf-8")
    (root / "metadata.json").write_text(json.dumps({"records": [
        {"path": "preprint.txt", "meta": {"title": "Same paper", "year": 2023, "doi": "DOI:10.1/X"}},
        {"path": "published.txt", "meta": {"title": "Same paper", "year": 2024, "doi": "10.1/x"}},
    ]}), encoding="utf-8")
    r = filecare.run({"meta_fields": ["author"]}, root)
    docs = {d["path"]: d for d in r["documents"]}
    return r["version_candidates"] and r["version_candidates"][0]["authoritative"] is None \
        and r["metadata_conflicts"][0]["field"] == "year" \
        and docs["preprint.txt"]["meta_src"]["doi"].endswith(":doi") \
        and docs["published.txt"]["metadata_missing"] == ["author"]


def scen_attachment_links(tmp, name):
    root = tmp / ("root-" + name); root.mkdir()
    for rel in ("main.txt", "supplement.txt", "orphan.dat"):
        (root / rel).write_text(rel, encoding="utf-8")
    spec = {"records": [{"id": "main", "path": "main.txt", "aliases": ["alias-main"],
                         "attachments": ["supplement.txt", "missing.pdf"]},
                        {"path": "main.txt", "attachments": ["alias-main", "../outside.txt"]}]}
    r = filecare.run(spec, root)
    return len(r["attachments"]["missing"]) == 2 and r["attachments"]["orphans"] == ["orphan.dat"] \
        and r["attachments"]["referenced_files"] == ["main.txt", "supplement.txt"]


def scen_plan_readonly_and_collisions(tmp, name):
    root = tmp / ("root-" + name); root.mkdir()
    (root / "a.txt").write_text("one", encoding="utf-8")
    (root / "b.txt").write_text("two", encoding="utf-8")
    spec = {"structure": [{"folder": "papers", "cues": ["one", "two"]}],
            "records": [{"path": "a.txt", "meta": {"title": "A/B: same"}},
                        {"path": "b.txt", "meta": {"title": "A/B: same"}}]}
    before = _fingerprints(root)
    r = filecare.run(spec, root)
    after = _fingerprints(root)
    targets = [p["recommended_path"] for p in r["operation_plan"]]
    return before == after and len(set(targets)) == 2 and all(p["executed"] is False for p in r["operation_plan"]) \
        and r["counts"]["executed_moves"] == 0 and r["operation_evidence"]["input_writes"] == 0


def scen_missing_metadata_never_invented(tmp, name):
    root = tmp / ("root-" + name); root.mkdir()
    (root / "Author 2024 DOI 10.1-fake.txt").write_text("just body", encoding="utf-8")
    r = filecare.run({"meta_fields": ["author", "year", "doi"]}, root)
    doc = r["documents"][0]
    return doc["meta"] == {} and doc["metadata_missing"] == ["author", "year", "doi"] \
        and doc["title"] == "Author 2024 DOI 10.1-fake"  # display fallback only, not metadata


def scen_real_ooxml_extraction(tmp, name):
    root = tmp / ("root-" + name); root.mkdir()
    with zipfile.ZipFile(root / "paper.docx", "w") as zf:
        zf.writestr("docProps/core.xml", "<cp:coreProperties xmlns:cp='x' xmlns:dc='d'><dc:title>Real title</dc:title><dc:creator>Li</dc:creator></cp:coreProperties>")
        zf.writestr("word/document.xml", "<w:document xmlns:w='w'><w:p><w:r><w:t>缓冲液配方正文</w:t></w:r></w:p></w:document>")
    (root / "archive.zip").write_bytes(b"not a text document")
    r = filecare.run({}, root)
    docs = {d["path"]: d for d in r["documents"]}
    return docs["paper.docx"]["text_extraction"]["status"] == "extracted" \
        and docs["paper.docx"]["meta"] == {"title": "Real title", "author": "Li"} \
        and docs["archive.zip"]["text_extraction"]["status"] == "unsupported" \
        and r["status"] == "partial"


def scen_retrieval_hit_and_miss(tmp, name):
    root = tmp / ("root-" + name); root.mkdir()
    (root / "protocol.txt").write_text("Tris 缓冲液 50 mM，pH 7.4。", encoding="utf-8")
    hit = filecare.run({}, root, query="缓冲液")
    miss = filecare.run({}, root, query="quantum chromodynamics")
    return hit["retrieval"]["hits"][0]["path"] == "protocol.txt" \
        and "缓冲液" in hit["retrieval"]["hits"][0]["snippet"] \
        and miss["retrieval"]["empty"] and miss["retrieval"]["hits"] == []


def scen_cli_refusal_full_contract(tmp, name):
    root = tmp / ("root-" + name); root.mkdir(); (root / "a.txt").write_text("a", encoding="utf-8")
    case = tmp / "case.json"
    case.write_text(json.dumps({"case_id": name, "output_contract": {
        "library_result": {}, "operation_evidence": {}, "failure_recovery": {}, "required": "yes"}}), encoding="utf-8")
    bad = tmp / "bad.json"; bad.write_text("{oops", encoding="utf-8")
    out = tmp / "out"
    p = _run(["--root", root, "--spec", bad, "--case", case, "--out", out])
    r = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return p.returncode == 5 and r["case_id"] == name and r["required"] == "yes" \
        and "library_result" in r and "failure_recovery" in r and r["status"] == "undetermined"


def scen_cli_deterministic_idempotent(tmp, name):
    root = tmp / ("root-" + name); root.mkdir(); (root / "a.txt").write_text("alpha beta", encoding="utf-8")
    case = tmp / "case.json"; case.write_text(json.dumps({"case_id": name, "output_contract": {"library_result": {}}}), encoding="utf-8")
    out = tmp / "out"
    args = ["--root", root, "--case", case, "--out", out, "--query", "alpha"]
    p1 = _run(args); raw1 = (out / "result.json").read_bytes()
    p2 = _run(args); raw2 = (out / "result.json").read_bytes()
    return p1.returncode == p2.returncode == 0 and raw1 == raw2 \
        and (out / "file_inventory.json").is_file() and (out / "operation_plan.json").is_file()


def scen_cli_missing_root_contract(tmp, name):
    case = tmp / "case.json"; case.write_text(json.dumps({
        "case_id": name, "output_contract": {"library_result": {}, "failure_recovery": {}, "n": 4}}), encoding="utf-8")
    out = tmp / "out"
    p = _run(["--root", tmp / "absent", "--case", case, "--out", out])
    r = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return p.returncode == 5 and r["case_id"] == name and r["n"] == 4 \
        and r["refusal"]["rule"] == "filecare.root_missing"


SCENARIOS = [
    ("raw_hash_not_filename", scen_raw_hash_not_filename),
    ("sidecar_provenance_conflicts", scen_sidecar_provenance_conflicts),
    ("attachment_links", scen_attachment_links),
    ("plan_readonly_and_collisions", scen_plan_readonly_and_collisions),
    ("missing_metadata_never_invented", scen_missing_metadata_never_invented),
    ("real_ooxml_extraction", scen_real_ooxml_extraction),
    ("retrieval_hit_and_miss", scen_retrieval_hit_and_miss),
    ("cli_refusal_full_contract", scen_cli_refusal_full_contract),
    ("cli_deterministic_idempotent", scen_cli_deterministic_idempotent),
    ("cli_missing_root_contract", scen_cli_missing_root_contract),
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
            print(("PASS" if ok else "FAIL") + f"  {name:<40}" + why)
    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "library-filecare-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_filecare.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return int(passed != len(rows))


if __name__ == "__main__":
    raise SystemExit(main())

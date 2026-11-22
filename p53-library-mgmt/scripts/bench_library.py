"""Benchmark for the research-library skill.

Each scenario asserts one property the challenge judges — versions never
overwrite, duplicates are never silently merged, filing is explainable, the
inventory is handover-ready, refusals are named — plus the archive/contract
layer (manifest with full hashes, integrity self-check, metadata provenance,
unsafe-id guard, dead-folder census) and the FP guards (a rerun is
byte-identical; the CLI writes all outputs and layers its exit codes 0/4/5).

    python bench_library.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library  # noqa: E402

STRUCTURE = [
    {"folder": "papers/涂层", "cues": ["涂层", "coating"]},
    {"folder": "protocols/缓冲液", "cues": ["缓冲液", "buffer"]},
]

SPEC = {
    "structure": STRUCTURE,
    "meta_fields": ["author", "year", "doi"],
    "records": [
        {"id": "paper-A", "title": "多孔涂层吸收速率研究",
         "meta": {"author": "王某某", "year": 2023},
         "text": "多孔涂层使吸收速率提高三倍。"},
        {"id": "paper-B", "title": "多孔涂层吸收速率研究",
         "meta": {"author": "王某某", "year": 2024, "doi": "10.0/xyz"},
         "text": "多孔涂层在高温下的稳定性仍待验证，补充八组重复。"},
        {"id": "protocol-C", "title": "Tris 缓冲液配制",
         "meta": {},
         "text": "缓冲液配方：Tris 50 mM，pH 7.4。"}
    ],
}


def _finding(result, rule):
    return next((f for f in result["findings"] if f["rule"] == rule), None)


def _docs(result):
    return {d["doc_id"]: d for d in result["documents"]}


def scen_ingest_basic(tmp, name):
    lib, res = library.run(SPEC)
    d = _docs(res)["paper-A"]
    sha = library.text_sha("多孔涂层使吸收速率提高三倍。")
    return res["status"] == "ok" and res["counts"]["documents"] == 3 \
        and d["sha256"] == sha[:16] and lib.data["documents"]["paper-A"]["sha256"] == sha


def scen_version_siblings_separate(tmp, name):
    """Same title, different content: both kept as version siblings, never merged."""
    lib, res = library.run(SPEC)
    sib = _finding(res, "lib.version_sibling")
    docs = _docs(res)
    return sib is not None and len(sib["members"]) == 2 \
        and docs["paper-A"]["sha256"] != docs["paper-B"]["sha256"] \
        and len(res["siblings"]) == 1 \
        and "does not guess which is authoritative" in res["siblings"][0]["note"] \
        and lib.data["documents"]["paper-A"]["text"] != lib.data["documents"]["paper-B"]["text"]


def scen_reingest_never_overwrites(tmp, name):
    """Re-ingesting a doc_id with changed content creates @v2 and keeps v1."""
    lib = library.Library()
    r1 = lib.add("X", "first content")
    r2 = lib.add("X", "second content, changed")
    docs = lib.data["documents"]
    return r1["status"] == "stored" and r2["status"] == "versioned" \
        and r2["doc_id"] == "X@v2" and r2["supersedes"] == "X" \
        and docs["X"]["text"] == "first content" \
        and docs["X"]["superseded_by"] == "X@v2" \
        and docs["X@v2"]["supersedes"] == "X" \
        and docs["X"]["sha256"] != docs["X@v2"]["sha256"]


def scen_reingest_unchanged(tmp, name):
    """Re-ingesting identical content under the same id changes nothing."""
    lib = library.Library()
    lib.add("X", "same text")
    before = json.dumps(lib.data, ensure_ascii=False, sort_keys=True)
    r2 = lib.add("X", "same text")
    after = json.dumps(lib.data, ensure_ascii=False, sort_keys=True)
    return r2["status"] == "unchanged" and before != after \
        and len(lib.data["documents"]) == 1 \
        and len(lib.data["events"]) == 2


def scen_duplicate_detection(tmp, name):
    """Identical content under two doc_ids: duplicate set reported, both kept."""
    spec = {"structure": [], "records": [
        {"id": "paper-A", "title": "涂层研究", "text": "多孔涂层使吸收速率提高三倍。"},
        {"id": "paper-A-copy", "title": "download (1)", "text": "多孔涂层使吸收速率提高三倍。"}]}
    lib, res = library.run(spec)
    dup = _finding(res, "lib.duplicate_content")
    return dup is not None and dup["doc_ids"] == ["paper-A", "paper-A-copy"] \
        and len(res["duplicates"]) == 1 \
        and res["counts"]["documents"] == 2 \
        and "every copy kept" in dup["why"]


def scen_folder_taxonomy(tmp, name):
    """Structure rules file documents by declared cues; the matched cue is recorded."""
    _, res = library.run(SPEC)
    docs = _docs(res)
    return res["folders"]["papers/涂层"] == ["paper-A", "paper-B"] \
        and res["folders"]["protocols/缓冲液"] == ["protocol-C"] \
        and docs["paper-A"]["folder"] == "papers/涂层" \
        and docs["paper-A"]["folder_cues"] == ["涂层"] \
        and docs["protocol-C"]["folder_cues"] == ["缓冲液"]


def scen_unfiled_honest(tmp, name):
    """A document no structure rule matches sits in 未归类 and is counted."""
    spec = {"structure": [{"folder": "papers/涂层", "cues": ["涂层"]}],
            "records": [{"id": "misc", "title": "购物清单", "text": "牛奶、鸡蛋、咖啡豆"}]}
    _, res = library.run(spec)
    f = _finding(res, "lib.unfiled")
    return f is not None and f["count"] == 1 \
        and res["folders"]["未归类"] == ["misc"] \
        and _docs(res)["misc"]["folder"] == "未归类"


def scen_retrieval_ranks(tmp, name):
    """The retrieval query ranks by shared content terms and can honestly miss."""
    spec = dict(SPEC)
    spec["query"] = "涂层 吸收速率"
    _, res = library.run(spec)
    hits = res["retrieval"]["hits"]
    ok1 = hits and hits[0]["doc_id"].startswith("paper-") and hits[0]["score"] >= 2 \
        and res["retrieval"]["empty"] is False
    spec2 = dict(SPEC)
    spec2["query"] = "量子色动力学"
    _, res2 = library.run(spec2)
    return ok1 and res2["retrieval"]["hits"] == [] \
        and res2["retrieval"]["empty"] is True \
        and "honest empty result" in res2["retrieval"]["note"]


def scen_export_shape(tmp, name):
    """The export is library.json (machine) + inventory.md (human handover)."""
    lib, res = library.run(SPEC)
    out = tmp / "out"
    exp = lib.export(out, res)
    lib_path, inv_path = out / "library.json", out / "inventory.md"
    if not (exp["ok"] and lib_path.exists() and inv_path.exists()):
        return False
    store = json.loads(lib_path.read_text(encoding="utf-8"))
    inv = inv_path.read_text(encoding="utf-8")
    return all(d["sha256"] and len(d["sha256"]) == 64
               for d in store["documents"].values()) \
        and "## papers/涂层" in inv and "sha256" in inv \
        and "version siblings" in inv


def scen_missing_file_refusal(tmp, name):
    """A record pointing at a missing file is refused by name; the rest ingest
    and the status turns partial (a run with refusals is not a clean ok)."""
    spec = {"structure": [], "records": [
        {"id": "good", "text": "多孔涂层使吸收速率提高三倍。"},
        {"id": "gone", "path": str(tmp / "nope" / "missing.txt")}]}
    _, res = library.run(spec)
    return res["status"] == "partial" and res["counts"]["documents"] == 1 \
        and res["counts"]["refused"] == 1 \
        and res["refused"][0]["rule"] == "lib.file_missing" \
        and res["refused"][0]["doc_id"] == "gone" \
        and "never silently skipped" in res["refused"][0]["reason"]


def scen_all_refused_is_refusal(tmp, name):
    """When nothing can be ingested the run refuses (undetermined), with reasons."""
    spec = {"structure": [], "records": [
        {"id": "g1", "path": str(tmp / "a-missing.txt")},
        {"id": "g2", "path": str(tmp / "b-missing.txt")}]}
    lib, res = library.run(spec)
    return lib is None and res["status"] == "undetermined" \
        and res["refusal"]["rule"] == "lib.no_records" \
        and "file not found" in res["refusal"]["message"]


def scen_metadata_honest(tmp, name):
    """Metadata is stored verbatim; declared-but-absent fields are marked missing."""
    _, res = library.run(SPEC)
    docs = _docs(res)
    return docs["paper-A"]["meta"] == {"author": "王某某", "year": 2023} \
        and res["meta_missing"]["paper-A"] == ["doi"] \
        and "doi" not in docs["paper-A"]["meta"] \
        and res["meta_missing"].get("protocol-C") == ["author", "year", "doi"]


def scen_rerun_identical(tmp, name):
    """No wall-clock fields: the same spec re-runs byte-identical."""
    _, r1 = library.run(SPEC)
    _, r2 = library.run(SPEC)
    l1 = library.run(SPEC)[0]
    l2 = library.run(SPEC)[0]
    return json.dumps(r1, ensure_ascii=False, sort_keys=True) \
        == json.dumps(r2, ensure_ascii=False, sort_keys=True) \
        and json.dumps(l1.data, ensure_ascii=False, sort_keys=True) \
        == json.dumps(l2.data, ensure_ascii=False, sort_keys=True)


def scen_cli_ok_writes(tmp, name):
    """The CLI happy path: exit 0, library.json + inventory.md + result.json."""
    spec_path = tmp / "spec.json"
    spec_path.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "library_cli.py"),
                           "--spec", str(spec_path), "--out", str(out),
                           "--query", "涂层 吸收速率"],
                          capture_output=True, text=True, timeout=120)
    ok = proc.returncode == 0 and (out / "library.json").exists() \
        and (out / "inventory.md").exists() and (out / "result.json").exists()
    if not ok:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return result["status"] == "ok" and result["counts"]["documents"] == 3 \
        and result["retrieval"]["hits"][0]["doc_id"].startswith("paper-")


def scen_cli_refusal_exit5(tmp, name):
    """An unreadable spec is refused with exit 5 and a written result.json."""
    spec_path = tmp / "bad.json"
    spec_path.write_text("{oops, not json", encoding="utf-8")
    out = tmp / "out5"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "library_cli.py"),
                           "--spec", str(spec_path), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    ok = proc.returncode == 5 and (out / "result.json").exists()
    if not ok:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return result["status"] == "undetermined" \
        and result["refusal"]["rule"] == "lib.spec_unreadable" \
        and not (out / "library.json").exists()


def scen_id_invalid_refused(tmp, name):
    """A doc_id carrying folder semantics is refused as unsafe; the rest ingest."""
    spec = {"structure": [], "records": [
        {"id": "papers/涂层", "title": "bad id", "text": "多孔涂层研究。"},
        {"id": "..", "title": "dotdot", "text": "相对路径在冒充身份"},
        {"id": "good", "text": "多孔涂层使吸收速率提高三倍。"}]}
    _, res = library.run(spec)
    rules = [r["rule"] for r in res["refused"]]
    return res["status"] == "partial" and rules.count("lib.id_invalid") == 2 \
        and res["counts"]["documents"] == 1 \
        and _docs(res)["good"]["folder"] == "未归类"


def scen_folder_empty_named(tmp, name):
    """A declared folder whose cues match nothing is named — a dead rule cannot
    hide behind a tree that looks filled."""
    spec = {"structure": [
                {"folder": "papers/涂层", "cues": ["涂层"]},
                {"folder": "protocols/电泳", "cues": ["电泳", "gel"]}],
            "records": [{"id": "p1", "title": "涂层研究", "text": "多孔涂层"}]}
    _, res = library.run(spec)
    f = _finding(res, "lib.folder_empty")
    return f is not None and f["folders"] == ["protocols/电泳"] \
        and "protocols/电泳" not in res["folders"]


def scen_manifest_and_verify(tmp, name):
    """The export writes manifest.tsv (full 64-hex sha256 + bytes); the
    integrity self-check passes on a good store and catches a tampered one."""
    lib, res = library.run(SPEC)
    out = tmp / "out"
    lib.export(out, res)
    man = (out / "manifest.tsv").read_text(encoding="utf-8")
    lines = man.strip().splitlines()
    if len(lines) != 4 or not lines[0].startswith("doc_id\tfolder\tsha256\tbytes\ttitle"):
        return False
    docs = {d["doc_id"]: d for d in res["documents"]}
    for line in lines[1:]:
        parts = line.split("\t")
        if parts[2] != library.text_sha(lib.data["documents"][parts[0]]["text"]) \
                or len(parts[2]) != 64 or parts[3] != str(docs[parts[0]]["bytes"]):
            return False
    v_ok = library.verify_store(out / "library.json")
    tampered = tmp / "bad.json"
    store = json.loads((out / "library.json").read_text(encoding="utf-8"))
    store["documents"]["paper-A"]["text"] = "篡改后的文本"
    tampered.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    v_bad = library.verify_store(tampered)
    return v_ok["ok"] and v_ok["checked"] == 3 \
        and not v_bad["ok"] and v_bad["mismatched"] == ["paper-A"]


def scen_cli_verify_flag(tmp, name):
    """--verify runs the integrity self-check and records it as a finding."""
    spec_path = tmp / "spec.json"
    spec_path.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")
    out = tmp / "outv"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "library_cli.py"),
                           "--spec", str(spec_path), "--out", str(out), "--verify"],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not (out / "manifest.tsv").exists():
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    f = _finding(result, "lib.integrity_verified")
    return f is not None and f["count"] == 3


def scen_meta_provenance(tmp, name):
    """Metadata provenance: each present field is marked with its source;
    declared-but-absent fields stay in meta_missing — nothing is guessed."""
    _, res = library.run(SPEC)
    docs = _docs(res)
    return docs["paper-A"]["meta_src"] == {"author": "record", "year": "record"} \
        and docs["protocol-C"]["meta_src"] == {} \
        and res["meta_missing"]["paper-A"] == ["doi"] \
        and res["meta_missing"]["protocol-C"] == ["author", "year", "doi"]


def scen_bytes_recorded(tmp, name):
    """Byte length is recorded per document (the archive manifest needs it)."""
    _, res = library.run(SPEC)
    docs = _docs(res)
    return docs["paper-A"]["bytes"] == len("多孔涂层使吸收速率提高三倍。".encode("utf-8"))


def scen_cjk_filename(tmp, name):
    """A record path with a CJK filename and spaces resolves and ingests."""
    src = tmp / "实验记录 缓冲液批次2.txt"
    src.write_text("缓冲液配制记录：pH 7.4。", encoding="utf-8")
    spec = {"structure": [{"folder": "protocols/缓冲液", "cues": ["缓冲液"]}],
            "records": [{"id": "lab-2", "title": "缓冲液记录", "path": str(src)}]}
    lib, res = library.run(spec)
    docs = _docs(res)
    return res["status"] == "ok" and docs["lab-2"]["folder"] == "protocols/缓冲液" \
        and lib.data["documents"]["lab-2"]["text"].startswith("缓冲液配制记录")


def scen_cli_partial_exit4(tmp, name):
    """A run with refused records exits 4 (partial) with result.json written."""
    spec_path = tmp / "spec4.json"
    spec_path.write_text(json.dumps({"structure": [], "records": [
        {"id": "good", "text": "多孔涂层使吸收速率提高三倍。"},
        {"id": "gone", "path": str(tmp / "no-missing.txt")}]}, ensure_ascii=False),
        encoding="utf-8")
    out = tmp / "out4"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "library_cli.py"),
                           "--spec", str(spec_path), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 4 or not (out / "result.json").exists():
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return result["status"] == "partial" and result["counts"]["refused"] == 1 \
        and (out / "library.json").exists()


CASE = {"case_id": "case-bench-53",
        "output_contract": {"deliverable": "library handover inventory",
                            "case_key": "53-library",
                            "materials": "see task.md"}}


def scen_cli_contract_passthrough(tmp, name):
    """--case echoes case_id and every output_contract field into result.json;
    the refusal path echoes none of it."""
    spec_path = tmp / "spec.json"
    spec_path.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")
    case_path = tmp / "case.json"
    case_path.write_text(json.dumps(CASE, ensure_ascii=False), encoding="utf-8")
    out = tmp / "outc"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "library_cli.py"),
                           "--spec", str(spec_path), "--out", str(out),
                           "--case", str(case_path)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    ok1 = result.get("case_id") == "case-bench-53" \
        and result.get("deliverable") == "library handover inventory" \
        and result.get("case_key") == "53-library" \
        and result.get("materials") == "see task.md" \
        and result.get("status") == "ok"
    # Refusal path: contract must NOT be echoed.
    bad_spec = tmp / "bad.json"
    bad_spec.write_text("{oops", encoding="utf-8")
    out2 = tmp / "outc2"
    proc2 = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "library_cli.py"),
                            "--spec", str(bad_spec), "--out", str(out2),
                            "--case", str(case_path)],
                           capture_output=True, text=True, timeout=120)
    r2 = json.loads((out2 / "result.json").read_text(encoding="utf-8"))
    return ok1 and proc2.returncode == 5 and r2.get("status") == "undetermined" \
        and "case_id" not in r2 and "deliverable" not in r2


def scen_spec_carried_case_id(tmp, name):
    """A case_id declared on the spec itself passes through to result.json."""
    spec = dict(SPEC)
    spec["case_id"] = "spec-carried-53"
    _, res = library.run(spec)
    return res.get("case_id") == "spec-carried-53" \
        and json.dumps(library.run(spec)[1], ensure_ascii=False, sort_keys=True) \
        == json.dumps(res, ensure_ascii=False, sort_keys=True)


SCENARIOS = [
    ("ingest_basic", scen_ingest_basic),
    ("version_siblings_separate", scen_version_siblings_separate),
    ("reingest_never_overwrites", scen_reingest_never_overwrites),
    ("reingest_unchanged", scen_reingest_unchanged),
    ("duplicate_detection", scen_duplicate_detection),
    ("folder_taxonomy", scen_folder_taxonomy),
    ("unfiled_honest", scen_unfiled_honest),
    ("retrieval_ranks", scen_retrieval_ranks),
    ("export_shape", scen_export_shape),
    ("missing_file_refusal", scen_missing_file_refusal),
    ("all_refused_is_refusal", scen_all_refused_is_refusal),
    ("metadata_honest", scen_metadata_honest),
    ("rerun_identical", scen_rerun_identical),
    ("cli_ok_writes", scen_cli_ok_writes),
    ("cli_refusal_exit5", scen_cli_refusal_exit5),
    ("id_invalid_refused", scen_id_invalid_refused),
    ("folder_empty_named", scen_folder_empty_named),
    ("manifest_and_verify", scen_manifest_and_verify),
    ("cli_verify_flag", scen_cli_verify_flag),
    ("meta_provenance", scen_meta_provenance),
    ("bytes_recorded", scen_bytes_recorded),
    ("cjk_filename", scen_cjk_filename),
    ("cli_partial_exit4", scen_cli_partial_exit4),
    ("cli_contract_passthrough", scen_cli_contract_passthrough),
    ("spec_carried_case_id", scen_spec_carried_case_id),
]


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, fn in SCENARIOS:
            try:
                ok = bool(fn(tmp, name))
                why = ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<26}" + why)
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "library-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_library.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

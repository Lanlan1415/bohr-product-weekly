"""Hostile structural/CLI tests for annotation v3 (no tracebacks, honest exits)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "annotate_cli.py"


def cli(*args):
    return subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI)] + list(args),
                          capture_output=True, text=True, timeout=120)


def clean(proc):
    return "Traceback" not in proc.stderr and "Traceback" not in proc.stdout


def stdout_json(proc):
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def setup(root):
    store = root / "ws.json"
    doc = root / "doc.txt"
    doc.write_text("1 Introduction\nPorous coatings raise uptake three-fold.\n\f2 Methods\nSix replicates.", encoding="utf-8")
    ann = root / "ann.json"
    ann.write_text(json.dumps([{"quote": "three-fold", "page": 1, "type": "highlight",
        "color": "yellow", "note": "结果：三倍", "tags": "吸收率", "topics": "涂层",
        "key_concepts": "吸收速率", "entities": "coating", "source_time": "2024-05-02"}],
        ensure_ascii=False), encoding="utf-8")
    p1 = cli("--store", str(store), "load", "--doc-id", "paper", "--doc-file", str(doc))
    p2 = cli("--store", str(store), "ingest", "--doc-id", "paper", "--annotations", str(ann))
    return store, p1, p2


def main():
    rows = []
    add = lambda name, ok: (rows.append({"probe": name, "pass": bool(ok)}),
                            print(f"{'PASS' if ok else 'FAIL'}  {name}"))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        store, p1, p2 = setup(root)
        add("valid_fixture_load_and_ingest", p1.returncode == p2.returncode == 0 and clean(p1) and clean(p2))

        array_store = root / "array.json"
        array_store.write_text("[]", encoding="utf-8")
        p = cli("--store", str(array_store), "verify")
        add("valid_json_array_store_refused", p.returncode == 5 and clean(p)
            and stdout_json(p) and stdout_json(p)["rule"] == "ann.invalid_input")

        empty_store = root / "empty-object.json"
        empty_store.write_text("{}", encoding="utf-8")
        p = cli("--store", str(empty_store), "result", "--out", str(root / "empty-out"))
        result_path = root / "empty-out" / "result.json"
        add("empty_object_store_result_refusal", p.returncode == 5 and clean(p)
            and result_path.exists()
            and json.loads(result_path.read_text(encoding="utf-8"))["status"] == "undetermined")

        bad_annotations = root / "bad-annotations.json"
        bad_annotations.write_text(json.dumps({"documents": {}, "anchors": [], "events": [],
                                               "annotations": []}), encoding="utf-8")
        p = cli("--store", str(bad_annotations), "notes")
        add("wrong_annotation_container_no_traceback", p.returncode == 5 and clean(p)
            and stdout_json(p)["rule"] == "ann.invalid_input")

        p = cli("--store", str(store), "retrieve", "--question", "三倍", "--since", "not-a-date")
        add("invalid_time_filter_usage_exit2", p.returncode == 2 and clean(p)
            and stdout_json(p)["rule"] == "ann.invalid_time_filter")

        p = cli("--store", str(store), "retrieve", "--question", "三倍",
                "--since", "2025-01-01", "--until", "2024-01-01")
        add("reverse_time_range_usage_exit2", p.returncode == 2 and clean(p)
            and stdout_json(p)["rule"] == "ann.invalid_time_filter")

        p = cli("--store", str(store), "retrieve", "--question", "三倍", "--topic", "涂层",
                "--tag", "吸收率", "--concept", "吸收速率", "--entity", "coating",
                "--since", "2024-01-01", "--until", "2024-12-31")
        data = stdout_json(p)
        add("all_metadata_filters_real_hit", p.returncode == 0 and clean(p)
            and data and len(data["hits"]) == 1 and data["hits"][0]["card_id"].startswith("card-"))

        p = cli("--store", str(store), "retrieve", "--question", "不存在的火星术语")
        data = stdout_json(p)
        add("chinese_unknown_query_honest_empty", p.returncode == 0 and clean(p)
            and data["hits"] == [] and data["empty_reason"])

        case = root / "case.json"
        case.write_text(json.dumps({"case_id": "hostile-ann", "output_contract": ["bad"]}), encoding="utf-8")
        out = root / "result-noncontract"
        p = cli("--store", str(store), "result", "--out", str(out), "--case", str(case))
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        add("nonobject_output_contract_degrades", p.returncode == 0 and clean(p)
            and any("output_contract" in line for line in result["limits"]))

        good_case = root / "good-case.json"
        good_case.write_text(json.dumps({"case_id": "deterministic-ann", "output_contract": {
            "annotations": [], "knowledge_cards": [], "follow_up": [], "unknown": {}}}), encoding="utf-8")
        # One real retrieval is part of the operation evidence.
        cli("--store", str(store), "retrieve", "--question", "三倍", "--topic", "涂层")
        out1, out2 = root / "final1", root / "final2"
        p1 = cli("--store", str(store), "result", "--out", str(out1), "--case", str(good_case))
        p2 = cli("--store", str(store), "result", "--out", str(out2), "--case", str(good_case))
        hashes = lambda out: {x.name: hashlib.sha256(x.read_bytes()).hexdigest()
                              for x in sorted(out.iterdir()) if x.is_file()}
        result = json.loads((out1 / "result.json").read_text(encoding="utf-8"))
        add("finalise_all_five_files_deterministic", p1.returncode == p2.returncode == 0
            and clean(p1) and clean(p2) and hashes(out1) == hashes(out2)
            and len(hashes(out1)) == 5 and result["annotations"] == result["notes"]
            and result["knowledge_cards"] == result["cards"]
            and result["unknown"] is None)

        out_file = root / "output-file"
        out_file.write_text("not a directory", encoding="utf-8")
        p = cli("--store", str(store), "export", "--out", str(out_file))
        add("export_unwritable_structured_exit5", p.returncode == 5 and clean(p) and stdout_json(p))
        p = cli("--store", str(store), "result", "--out", str(out_file), "--case", str(good_case))
        add("result_unwritable_structured_exit5", p.returncode == 5 and clean(p) and stdout_json(p))

    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "annotation-hostile-v3/v1", "probes": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_annotate_hostile_v3.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

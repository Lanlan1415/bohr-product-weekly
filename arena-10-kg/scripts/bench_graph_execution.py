"""Micro, synthetic two-paper graph tests (not official cases and not benchmark scores).

Assertions cover source ownership, verbatim JATS-quote checks, directed schema,
instance-aware disambiguation, duplicate/conflict consolidation, queries, idempotence,
contract passthrough and hostile inputs.  Only stdlib is used in an isolated temp dir.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kg_core as K
import kg_sources as KS

PIPELINE = Path(__file__).resolve().with_name("graph_pipeline.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ev(source, pid, quote, strength="direct", confidence=0.97):
    return {"source_id": source, "paragraph_id": pid, "quote": quote,
            "evidence_strength": strength, "confidence": confidence}


def node(nid, label, typ, evidence, **kw):
    return dict({"node_id": nid, "label": label, "type": typ,
                 "evidence": [evidence], "aliases": []}, **kw)


def make_corpus(root):
    primary = {"source_id": "S1", "doi": "10.synthetic/primary", "title": "Primary synthetic paper",
               "authors": ["Primary Author"],
               "paragraphs": [
                   {"paragraph_id": "sec1-p1", "text": "采用 sol-gel 制备 LLZO。LLZO 批次 B1 离子电导率为 3.2e-4 S/cm。"},
                   {"paragraph_id": "sec1-p2", "text": "LLZO Material 批次 B1 / 25 C 离子电导率 3.2e-4 S/cm。"}]}
    secondary = {"source_id": "S2", "doi": "10.synthetic/secondary", "title": "Independent secondary synthetic paper",
                 "authors": ["Other Author"],
                 "paragraphs": [
                     {"paragraph_id": "z-p3", "text": "Secondary LLZO 批次 B2 电导率 4.4e-4 S/cm；使用 Sol–gel。"},
                     {"paragraph_id": "z-p4", "text": "LATP 批次 C3 由另一方法制备。"}]}
    (root / "primary-material.json").write_text(json.dumps(primary, ensure_ascii=False), encoding="utf-8")
    (root / "secondary-material.json").write_text(json.dumps(secondary, ensure_ascii=False), encoding="utf-8")
    manifest = {"documents": [
        {"source_id": "S1", "file": "primary-material.json", "sha256": sha(root / "primary-material.json"), "doi": primary["doi"], "license": "CC-TEST"},
        {"source_id": "S2", "file": "secondary-material.json", "sha256": sha(root / "secondary-material.json"), "doi": secondary["doi"], "license": "CC-TEST"}]}
    (root / "corpus-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return primary, secondary


def make_graph():
    method = node("N-method", "sol-gel", "Method", ev("S1", "sec1-p1", "sol-gel"), aliases=["Sol–gel"])
    sample1 = node("N-s1", "LLZO", "Sample", ev("S1", "sec1-p1", "批次 B1"), identifiers={"batch": "B1"})
    sample2 = node("N-s2", "llzo", "Sample", ev("S2", "z-p3", "LLZO 批次 B2"), identifiers={"batch": "B2"})
    material = node("N-mat", "LLZO Material", "Material", ev("S1", "sec1-p2", "LLZO Material"))
    metric = node("N-metric", "离子电导率", "Metric", ev("S1", "sec1-p1", "离子电导率"))
    latp = node("N-latp", "LATP", "Material", ev("S2", "z-p4", "LATP"))
    edges = []
    def edge(eid, s, pred, o, evidence, **kw):
        edges.append(dict({"edge_id": eid, "subject": s, "predicate": pred, "object": o,
                           "evidence": [evidence]}, **kw))
    edge("E1", "N-method", "prepares", "N-s1", ev("S1", "sec1-p1", "制备 LLZO"))
    edge("E2", "N-s1", "has_metric", "N-metric", ev("S1", "sec1-p1", "离子电导率"), value=0.00032, unit="S/cm", condition="25 C")
    edge("E3", "N-s2", "has_metric", "N-metric", ev("S2", "z-p3", "电导率"), value=0.00044, unit="S/cm", condition="25 C")
    # Exact duplicate qualified assertion: consolidate its evidence, not discard it.
    edge("E4", "N-mat", "has_metric", "N-metric", ev("S1", "sec1-p2", "离子电导率", confidence=0.90), value=0.00032, unit="S/cm", condition="25 C")
    edge("E5", "N-mat", "has_metric", "N-metric", ev("S1", "sec1-p2", "离子电导率", confidence=0.90), value=0.00032, unit="S/cm", condition="25 C")
    # Same material/metric/condition: independent differing result -> retain as conflict.
    edge("E6", "N-mat", "has_metric", "N-metric", ev("S2", "z-p3", "电导率", confidence=0.92), value=0.00044, unit="S/cm", condition="25 C")
    decisions = [{"node_ids": ["N-s1", "N-s2"], "action": "keep_separate",
                  "justification": "Different physical batches B1/B2 in two independent papers; same label is insufficient identity evidence.",
                  "evidence": [ev("S1", "sec1-p1", "批次 B1"), ev("S2", "z-p3", "批次 B2")]}]
    query = [{"type": "neighbors", "node_id": "N-method", "direction": "outgoing"},
             {"type": "predicate", "predicate": "has_metric"}, {"type": "conflicts"}]
    return {"schema_version": "literature-evidence-graph/v1", "nodes": [method, sample1, sample2, material, metric, latp],
            "edges": edges, "merge_decisions": decisions}, query


def call(root, graph, out, queries=None, case=None):
    gp = root / "graph-input.json"; gp.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    cmd = [sys.executable, str(PIPELINE), "--graph", str(gp), "--sources-dir", str(root), "--out", str(out)]
    if queries is not None:
        qp = root / "queries.json"; qp.write_text(json.dumps(queries), encoding="utf-8"); cmd += ["--queries", str(qp)]
    if case:
        cp = root / "case.json"; cp.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8"); cmd += ["--case", str(cp)]
    return subprocess.run(cmd, capture_output=True, text=True)


def tests():
    rows = []
    def ok(name, cond, detail=""):
        rows.append({"scenario": name, "pass": bool(cond), "detail": str(detail)})
        print(("PASS " if cond else "FAIL ") + name + (" :: " + str(detail) if not cond else ""))
    with tempfile.TemporaryDirectory(prefix="kg_micro_two_papers_") as td:
        root = Path(td); make_corpus(root); graph, queries = make_graph()
        registry = KS.build_registry(root)
        ok("first_doi_not_attached_to_second", registry["sources"]["S1"]["doi"] != registry["sources"]["S2"]["doi"] and registry["sources"]["S2"]["doi"] == "10.synthetic/secondary")
        ok("manifest_hashes_actually_verified", all(s.get("hash_verified") for s in registry["sources"].values()))
        case = {"case_id": "micro-two-papers", "custom": {"verbatim": [2, 4]},
                "output_contract": {"graph": "...", "queries": "...", "custom": "...", "schema_validation": "..."}}
        out1, out2 = root / "out1", root / "out2"
        a = call(root, graph, out1, queries, case)
        b = call(root, graph, out2, queries, case)
        if not (out1 / "result.json").exists():
            print("pipeline failure", a.returncode, a.stdout, a.stderr, b.stderr)
        result = json.loads((out1 / "result.json").read_text(encoding="utf-8"))
        accepted = json.loads((out1 / "graph.json").read_text(encoding="utf-8"))
        ok("valid_graph_schema_and_conditions", a.returncode == 0 and result["quality_gate"]["schema"] and result["stats"] == {"nodes": 6, "edges": 5, "queries_executed": 3}, (a.returncode, a.stdout, a.stderr))
        ok("verbatim_source_quotes_verified", result["sources"]["verified_against_actual_material"] and result["sources"]["papers"] == 2 and result["sources"]["errors"] == [])
        ok("instance_identity_stays_separate", len(result["merge_decisions"]) == 1 and result["merge_decisions"][0]["action"] == "keep_separate" and result["merge_decisions"][0]["evidence_count"] == 2)
        duplicate = next(e for e in accepted["edges"] if set(e["supporting_edge_ids"]) == {"E4", "E5"})
        ok("duplicate_assertion_evidence_merged", len(duplicate["evidence"]) == 2 and duplicate["confidence"] == 0.90 and duplicate["status"] in {"accepted", "conflict"})
        ok("same_condition_conflicts_not_averaged", len(result["conflicts"]) == 2 and {e for c in result["conflicts"] for e in c["edge_ids"]} == {"E4", "E5", "E6"} and {c["value"] for c in result["conflicts"]} == {0.00032, 0.00044} and not any(e.get("value") == 0.00038 for e in accepted["edges"]), result["conflicts"])
        ok("three_real_queries_with_source_evidence", len(result["queries"]) == 3 and result["queries"][0]["answer_edge_ids"] == ["E1"] and result["queries"][1]["answer_edge_ids"] and all(query["edges"] for query in result["queries"][:2]))
        ok("conflict_query_returns_actual_both_sides", len(result["queries"][2]["edges"]) == 2 and {e["edge_id"] for e in result["queries"][2]["edges"]} == {"E4", "E6"})
        ok("contract_preserved_and_deterministic", result["case_id"] == case["case_id"] and result["custom"] == case["custom"] and (out1 / "result.json").read_bytes() == (out2 / "result.json").read_bytes() and (out1 / "graph.json").read_bytes() == (out2 / "graph.json").read_bytes())
        ok("graphml_export_with_evidence", (out1 / "graph_edges.csv").is_file() and "evidence" in (out1 / "graph_edges.csv").read_text(encoding="utf-8-sig") and (out1 / "schema_validation.json").is_file())

        # The same s/p/o under a different condition is legitimate, not a numeric conflict.
        conditioned, _ = make_graph()
        conditioned["edges"] = [e for e in conditioned["edges"] if e["edge_id"] != "E6"]
        conditioned["edges"].append({"edge_id": "E80", "subject": "N-mat", "predicate": "has_metric", "object": "N-metric",
                                     "evidence": [ev("S2", "z-p3", "电导率")], "value": 0.00044,
                                     "unit": "S/cm", "condition": "80 C"})
        out = root / "out-condition"
        rc = call(root, conditioned, out, queries)
        conditioned_result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        ok("different_conditions_do_not_conflict", rc.returncode == 0 and conditioned_result["conflicts"] == [], conditioned_result["conflicts"])

        for label, mutate, expect_rule in [
            ("bad_direction", lambda g: g["edges"].append({"edge_id": "BAD-DIR", "subject": "N-mat", "predicate": "prepares", "object": "N-s1", "evidence": [ev("S1", "sec1-p1", "制备 LLZO")]}), "direction/type error"),
            ("missing_condition", lambda g: g["edges"].append({"edge_id": "BAD-COND", "subject": "N-mat", "predicate": "compares", "object": "N-latp", "evidence": [ev("S2", "z-p4", "LATP")]}), "no condition"),
            ("bad_quote", lambda g: g["edges"][0]["evidence"][0].update(quote="a quote absent from the real paragraph"), "quote does not occur"),
            ("invalid_confidence", lambda g: g["edges"][0]["evidence"][0].update(confidence=8.0), "[0,1]"),
        ]:
            modified, _ = make_graph(); mutate(modified)
            out = root / ("out-" + label); r = call(root, modified, out, queries)
            rejected = json.loads((out / "rejected_records.json").read_text(encoding="utf-8"))
            report = json.loads((out / "schema_validation.json").read_text(encoding="utf-8"))
            ok("hostile_" + label + "_rejected", r.returncode == 3 and bool(rejected["edges"]) and expect_rule in str(rejected), (r.stdout, rejected, report))
            ok("hostile_" + label + "_not_clean", modified is not None and json.loads((out / "result.json").read_text(encoding="utf-8"))["status"] == "partial")

        bad_decisions, _ = make_graph(); bad_decisions["merge_decisions"] = [{"node_ids": ["N-s1", "N-s2"], "action": "merge", "justification": "same name only", "evidence": [ev("S1", "sec1-p1", "批次 B1")]}]
        out = root / "out-bad-merge"; r = call(root, bad_decisions, out, queries)
        validation = json.loads((out / "schema_validation.json").read_text(encoding="utf-8"))
        ok("merge_requires_shared_identifier", r.returncode == 3 and "no matching author/source identifiers" in str(validation["errors"]))

        broken, _ = make_graph()
        for nd in broken["nodes"]: nd["evidence"] = []
        out = root / "out-no-evidence"; r = call(root, broken, out, queries)
        ok("all_unsourced_nodes_blocked_not_success", r.returncode == 4 and json.loads((out / "graph.json").read_text(encoding="utf-8"))["nodes"] == [] and json.loads((out / "result.json").read_text(encoding="utf-8"))["status"] == "undetermined")

        unresolved = KS.query(json.loads((out1 / "graph.json").read_text(encoding="utf-8")), {"type": "neighbors", "node_id": "N-missing"})
        ok("unknown_query_is_undetermined", unresolved["status"] == "undetermined" and "not present" in unresolved["reason"])
        # Source-level corruption must be reported honestly, not skipped by a blanket catch.
        case_root = root / "corrupt"; case_root.mkdir(); make_corpus(case_root)
        (case_root / "secondary-material.json").write_text("{broken", encoding="utf-8")
        reg = KS.build_registry(case_root)
        ok("corrupt_second_paper_explicit_error", bool(reg["errors"]) and "secondary-material" in str(reg["errors"]))
    return rows


def main():
    rows = tests(); passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "kg-executable-bench/v1", "synthetic": True,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_execution.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("%d/%d pass" % (passed, len(rows)))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

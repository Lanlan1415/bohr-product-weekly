#!/usr/bin/env python3
"""Validate/consolidate a graph, execute queries and finish the case contract.

Examples:
  python graph_pipeline.py --graph /app/work/graph.json --sources-dir /input \
      --case /input/case.json --queries /app/work/queries.json --out /app/output

Accepted nodes/edges are separated from rejected records.  A schema-invalid graph is
never labelled a clean success.  Unreadable/malformed input exits 5; accepted graph plus
uncovered/rejected records exits 3; a fatal missing/invalid graph exits 4.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kg_core as K
import kg_sources as KS


def contract_fields(contract):
    if isinstance(contract, dict):
        return list(contract)
    if isinstance(contract, list):
        result = []
        for x in contract:
            if isinstance(x, str):
                result.append(x)
            elif isinstance(x, dict):
                for key in ("name", "field", "key", "id"):
                    if x.get(key) is not None:
                        result.append(str(x[key])); break
        return result
    return []


def parse_extra(row, field):
    value = row.get(field)
    if not value:
        return {} if field == "identifiers" else []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def graph_from_csv(nodes_path, edges_path):
    nodes, edges = [], []
    for row in K.read_csv(nodes_path, K.NODE_COLUMNS):
        node = dict(row)
        node["aliases"] = [a.strip() for a in (row.get("aliases") or "").split(";") if a.strip()]
        for key in ("evidence", "identifiers", "mentions"):
            node[key] = parse_extra(row, key)
        if not node["evidence"] and (row.get("source_id") or row.get("paragraph_id") or row.get("quote")):
            node["evidence"] = [{k: row.get(k) for k in ("source_id", "paragraph_id", "quote") if row.get(k)}]
        nodes.append(node)
    for row in K.read_csv(edges_path, K.EDGE_COLUMNS):
        edge = dict(row)
        for key in ("evidence", "condition", "identifiers"):
            if key in edge:
                edge[key] = parse_extra(row, key)
        edges.append(edge)
    return {"schema_version": "literature-evidence-graph/v1", "nodes": nodes, "edges": edges}


def add_file_csv(path, rows, fieldnames):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for original in rows:
            row = dict(original)
            for key, value in list(row.items()):
                if isinstance(value, (dict, list)):
                    row[key] = json.dumps(value, sort_keys=True, ensure_ascii=False)
            w.writerow(row)


def _isolated_node_valid(node, schema, registry):
    stripped = dict(node)
    # Overall entity identity review is run once on the complete graph below.
    result = K.validate_graph({"nodes": [stripped], "edges": []}, schema, registry, [])
    return result["ok"], result["errors"]


def _edge_valid(edge, nodes, schema, registry):
    selected = [n for n in nodes if str(n.get("node_id")) in {str(edge.get("subject")), str(edge.get("object"))}]
    # Skip cross-node identity review here: pair direction/evidence are checked individually;
    # full global duplicate and merge evidence is addressed by the whole-graph validation.
    result = K.validate_graph({"nodes": selected, "edges": [edge]}, schema, registry, [])
    return result["ok"], result["errors"]


def execute_queries(graph, queries):
    if not queries:
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        queries = []
        if nodes:
            queries.append({"type": "neighbors", "node_id": nodes[0].get("node_id"), "direction": "outgoing"})
        if edges:
            queries.append({"type": "predicate", "predicate": edges[0].get("predicate")})
        queries.append({"type": "conflicts"})
    executed = []
    for request in queries[:100]:
        result = KS.query(graph, request)
        result["executed_against"] = "accepted-graph"
        executed.append(result)
    return queries, executed


def write_markdown(path, validation, executed, registry, rejected):
    lines = ["# Verified literature evidence graph", "",
             "This report is generated from actual accepted records; it is not an official case score.", "",
             "- Accepted nodes: %d" % validation["node_count"],
             "- Accepted qualified assertions: %d" % validation["edge_count"],
             "- Rejected nodes/edges: %d/%d" % (len(rejected[0]), len(rejected[1])),
             "- Quote registry verified: %s" % registry.get("verified_against_actual_material", False),
             "- Schema: %s" % validation["schema_version"], "",
             "## Executed queries (graph-only)"]
    for i, value in enumerate(executed, 1):
        lines += ["", "### Query %d" % i, "", "```json", json.dumps(value, ensure_ascii=False, indent=2), "```"]
    if validation["errors"]:
        lines += ["", "## Unresolved validation errors"] + ["- " + x for x in validation["errors"]]
    if validation["conflicts"]:
        lines += ["", "## Conflict assertions retained independently", "```json",
                  json.dumps(validation["conflicts"], ensure_ascii=False, indent=2), "```"]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", help="graph JSON with nodes/edges, alternative to CSV")
    ap.add_argument("--nodes"); ap.add_argument("--edges")
    ap.add_argument("--schema")
    ap.add_argument("--sources-dir")
    ap.add_argument("--decisions", help="entity merge/keep_separate decision JSON list")
    ap.add_argument("--queries", help="JSON list of structured graph queries")
    ap.add_argument("--case")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    case = {}
    try:
        if args.case:
            case = json.loads(Path(args.case).read_text(encoding="utf-8-sig"))
            if not isinstance(case, dict):
                raise ValueError("case.json must be an object")
        schema = K.load_schema(args.schema)
        if args.graph:
            graph = json.loads(Path(args.graph).read_text(encoding="utf-8-sig"))
        elif args.nodes and args.edges:
            graph = graph_from_csv(args.nodes, args.edges)
        else:
            raise ValueError("supply --graph or both --nodes and --edges")
        if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
            raise ValueError("graph must be an object with nodes[] and edges[]")
        if len(graph["nodes"]) > 100000 or len(graph["edges"]) > 100000:
            raise ValueError("graph exceeds bounded 100000-node/edge contract")
        registry = KS.build_registry(args.sources_dir) if args.sources_dir else None
        if args.sources_dir and not registry["passages"]:
            raise ValueError("sources-dir supplied but no usable source/paragraph records were found")
        decisions = graph.get("merge_decisions") or []
        if args.decisions:
            decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8-sig"))
        if not isinstance(decisions, list) or any(not isinstance(d, dict) for d in decisions):
            raise ValueError("merge_decisions must be a JSON array of decision objects")
        nodes = [n for n in graph["nodes"] if isinstance(n, dict)]
        raw_edges = [e for e in graph["edges"] if isinstance(e, dict)]
        edges, consolidated_conflicts = K.consolidate(raw_edges)
        accepted_nodes, rejected_nodes = [], []
        for index, node in enumerate(nodes):
            ok, errors = _isolated_node_valid(node, schema, registry)
            (accepted_nodes if ok else rejected_nodes).append(node if ok else {"node": node, "index": index, "errors": errors})
        accepted_ids = {str(n.get("node_id")) for n in accepted_nodes}
        accepted_edges, rejected_edges = [], []
        # Missing nodes are explicitly rejected, never left as graph dangling placeholders.
        for index, edge in enumerate(edges):
            if str(edge.get("subject")) not in accepted_ids or str(edge.get("object")) not in accepted_ids:
                rejected_edges.append({"edge": edge, "index": index, "errors": ["endpoint not in accepted nodes"]})
                continue
            ok, errors = _edge_valid(edge, accepted_nodes, schema, registry)
            (accepted_edges if ok else rejected_edges).append(edge if ok else {"edge": edge, "index": index, "errors": errors})
        accepted_graph = {"schema_version": schema["schema_version"], "nodes": accepted_nodes,
                          "edges": accepted_edges, "merge_decisions": decisions}
        validation = K.validate_graph(accepted_graph, schema, registry, decisions)
        status = KS.registry_status(registry)
        if registry:
            for error in registry["errors"]:
                validation["warnings"].append(error)
        if consolidated_conflicts:
            validation["conflicts"] = consolidated_conflicts
        queries_obj = []
        if args.queries:
            queries_obj = json.loads(Path(args.queries).read_text(encoding="utf-8-sig"))
            if not isinstance(queries_obj, list):
                raise ValueError("queries JSON must be a list")
        query_declarations, executed = execute_queries(accepted_graph, queries_obj)
        result_path = out / "result.json"
        (out / "graph.json").write_text(json.dumps(accepted_graph, ensure_ascii=False, indent=2), encoding="utf-8")
        node_fields = ["node_id", "label", "type", "aliases", "identifiers", "source_id", "paragraph_id", "quote", "evidence", "mentions"]
        edge_fields = ["edge_id", "subject", "predicate", "object", "source_id", "paragraph_id", "quote",
                       "evidence_strength", "evidence", "confidence", "value", "unit", "condition", "status", "supporting_edge_ids"]
        add_file_csv(out / "graph_nodes.csv", accepted_nodes, node_fields)
        add_file_csv(out / "graph_edges.csv", accepted_edges, edge_fields)
        (out / "schema_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "queries.json").write_text(json.dumps(executed, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "rejected_records.json").write_text(json.dumps({"nodes": rejected_nodes, "edges": rejected_edges}, ensure_ascii=False, indent=2), encoding="utf-8")
        unresolved = validation["errors"] or registry and registry["errors"] or rejected_nodes or rejected_edges
        status_text = "success" if not unresolved and len(executed) >= 3 else "partial" if accepted_nodes else "undetermined"
        limits = list(validation["warnings"])
        if rejected_nodes or rejected_edges:
            limits.append("Rejected nodes/edges are retained under rejected_records.json; acceptance never converts unknown evidence into source facts.")
        if len(executed) < 3:
            limits.append("Fewer than three actual graph queries were possible from the available accepted nodes/edges.")
        if not registry:
            limits.append("Presence checks are not full quote verification; no --sources-dir was supplied.")
        result = {"case_id": case.get("case_id"), "status": status_text,
                  "graph": "graph.json", "graph_summary": "graph_summary.md",
                  "graph_files": ["graph.json", "graph_nodes.csv", "graph_edges.csv"],
                  "schema_validation": validation, "queries": executed,
                  "sources": status, "conflicts": validation["conflicts"],
                  "merge_decisions": validation["merge_decisions"],
                  "uncertainty": limits,
                  "change_log": [{"action": "consolidated_assertions", "original_edges": len(raw_edges),
                                  "accepted_edges": len(accepted_edges), "rejected_nodes": len(rejected_nodes),
                                  "rejected_edges": len(rejected_edges), "averaged_or_deleted_conflicts": False}],
                  "stats": {"nodes": len(accepted_nodes), "edges": len(accepted_edges), "queries_executed": len(executed)},
                  "quality_gate": {"schema": validation["ok"], "evidence_quote": bool(registry and registry["passages"]),
                                   "three_queries": len(executed) >= 3}}
        aliases = {"graph_json": accepted_graph, "source_registry": status,
                   "evidence": [ev for edge in accepted_edges for ev in edge.get("evidence") or []],
                   "validation": validation, "query_results": executed}
        for key in contract_fields(case.get("output_contract")):
            if key in result:
                continue
            if key in aliases:
                result[key] = aliases[key]
            elif key in case:
                result[key] = case[key]
            else:
                result[key] = None
                limits.append("output_contract field %r could not be derived from actual graph material" % key)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        write_markdown(out / "graph_summary.md", validation, executed, status, (rejected_nodes, rejected_edges))
        rc = 0 if status_text == "success" else 3 if status_text == "partial" else 4
        print(json.dumps({"status": status_text, "rc": rc, "schema_ok": validation["ok"],
                          "nodes": len(accepted_nodes), "edges": len(accepted_edges),
                          "queries": len(executed), "wrote": str(result_path)}, ensure_ascii=False))
        return rc
    except Exception as exc:
        # The outer CLI boundary must still return a structured refusal on malformed
        # nested data; an implementation error is never converted into success either.
        safe_case = case if isinstance(case, dict) else {}
        result = {"case_id": safe_case.get("case_id"), "status": "undetermined",
                  "findings": [{"rule": "graph.refused", "severity": "high", "message": str(exc)[:300]}],
                  "uncertainty": ["graph validation did not complete; no success is claimed"]}
        for key in contract_fields(safe_case.get("output_contract")):
            if key not in result:
                result[key] = safe_case.get(key)
                if key not in safe_case:
                    result["uncertainty"].append("output_contract field %r not derivable after refusal" % key)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "undetermined", "rc": 5, "error": str(exc)[:240]}, ensure_ascii=False))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

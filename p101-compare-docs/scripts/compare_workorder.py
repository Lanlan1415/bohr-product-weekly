"""Execute comparison-workorder v2 against an agent-built aligned matrix.

The LLM/agent reads the real papers and writes matrix.json plus sources.json.  This
CLI performs deterministic grid, provenance, conversion, comparability and synthesis
checks and emits the actual comparison deliverables.  It does not summarise papers or
pool values on the basis of lexical similarity.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units as U  # noqa: E402
import v2_common as C  # noqa: E402

STATUSES = {"reported", "not_reported", "extraction_failed", "not_applicable"}
RELATIONS = {"consensus", "partial", "conflict", "insufficient_evidence"}
DIRECTIONS = {"increases", "decreases", "no_effect", "mixed", "not_applicable"}
STRENGTHS = {"strong", "moderate", "weak", "insufficient"}
CAUSES = {"sample", "method", "condition", "time", "metric", "dataset", "unit", "entity", "unknown"}
DEFAULT_ALIGNMENT = ["question_id", "entity", "time", "metric", "units", "material",
                     "pollutant", "budget", "dataset"]


def _records(value: Any) -> list[dict]:
    entries = list(value.values()) if isinstance(value, dict) else value
    return [x for x in entries if isinstance(x, dict)] if isinstance(entries, (list, tuple)) else []


def _field_id(row: dict, pos: int) -> str:
    return str(row.get("field_id") or row.get("name") or row.get("id") or f"field_{pos+1}")


def _doc_id(row: dict, pos: int) -> str:
    return str(row.get("source_document_id") or row.get("document_id") or row.get("doc_id") or
               row.get("id") or f"document_{pos+1}")


def _norm_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 12)
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value or "").strip().casefold()


def _workorder_fields(workorder: dict) -> list[str]:
    for key in ("field_ids", "fields", "comparison_fields", "target_fields"):
        rows = workorder.get(key)
        if isinstance(rows, (list, tuple)):
            ids = []
            for pos, row in enumerate(rows):
                if isinstance(row, str):
                    ids.append(row)
                elif isinstance(row, dict):
                    ids.append(_field_id(row, pos))
            if ids:
                return ids
    return []


def _cell_evidence(cell: dict) -> dict:
    ev = cell.get("evidence")
    if isinstance(ev, dict):
        return ev
    return {k: cell.get(k) for k in ("source_document_id", "paragraph_id", "verbatim", "quote",
                                    "context", "page", "section", "table_id", "row", "column",
                                    "figure_id", "bbox", "charspan") if cell.get(k) is not None}


def _validate_conversion(field: dict, cell: dict, owner: str) -> tuple[Any, list[dict]]:
    findings = []
    unit = str(cell.get("unit") or cell.get("units") or "").strip()
    target = str(field.get("target_unit") or field.get("normalized_unit") or unit).strip()
    numeric = cell.get("value")
    if not isinstance(numeric, (int, float)) or isinstance(numeric, bool) or not math.isfinite(float(numeric)):
        return cell.get("normalized_value", numeric), findings
    if not unit:
        findings.append(C.make_finding("compare.unit_missing", "high", f"{owner}: numeric value has no original unit", owner))
        return None, findings
    if not target:
        findings.append(C.make_finding("compare.target_unit_missing", "high", f"{owner}: target_unit is not declared", owner))
        return None, findings
    conversion = U.convert(float(numeric), unit, target)
    if not conversion.get("ok"):
        findings.append(C.make_finding("compare.unit_mismatch", "high", f"{owner}: {conversion.get('reason')}", owner))
        return None, findings
    normalized = cell.get("normalized_value", numeric if unit == target else None)
    if normalized is None:
        findings.append(C.make_finding("compare.normalized_value_missing", "high",
                                       f"{owner}: conversion {unit}->{target} requires normalized_value", owner))
        return None, findings
    if not isinstance(normalized, (int, float)) or isinstance(normalized, bool) or not math.isfinite(float(normalized)):
        findings.append(C.make_finding("compare.normalized_value_invalid", "high", f"{owner}: normalized_value is not finite numeric", owner))
        return None, findings
    if not math.isclose(float(normalized), float(conversion["value"]), rel_tol=1e-9, abs_tol=1e-12):
        findings.append(C.make_finding("compare.conversion_unreproducible", "high",
                                       f"{owner}: {conversion.get('formula')} != {normalized} {target}", owner))
    return float(normalized), findings


def audit(workorder: dict, matrix: dict, corpus: C.SourceCorpus) -> tuple[dict, list[dict]]:
    findings = [C.make_finding("sources.invalid", "high", x) for x in corpus.errors]
    doc_defs = _records(matrix.get("documents") or workorder.get("documents"))
    field_defs = _records(matrix.get("field_defs") or matrix.get("fields"))
    if not field_defs:
        field_defs = _records(workorder.get("field_defs") or workorder.get("fields"))
    doc_ids = [_doc_id(x, i) for i, x in enumerate(doc_defs)]
    field_ids = [_field_id(x, i) for i, x in enumerate(field_defs)]
    if len(doc_ids) < 2:
        findings.append(C.make_finding("compare.too_few_documents", "high", "at least two source documents are required"))
    if not field_ids:
        findings.append(C.make_finding("compare.no_schema", "high", "field_defs is empty"))
    for name, ids in (("document", doc_ids), ("field", field_ids)):
        if len(ids) != len(set(ids)):
            findings.append(C.make_finding(f"compare.duplicate_{name}_id", "high", f"duplicate {name} ids: {ids}"))
    requested = _workorder_fields(workorder)
    if requested and set(requested) != set(field_ids):
        findings.append(C.make_finding("compare.workorder_schema_mismatch", "high",
                                       f"workorder fields {requested} differ from matrix fields {field_ids}"))
    schema: dict[str, dict] = {}
    for pos, field in enumerate(field_defs):
        fid = _field_id(field, pos)
        schema[fid] = field
        if not str(field.get("definition") or "").strip():
            findings.append(C.make_finding("compare.field_undefined", "high", f"{fid}: definition is required", fid))
    cells = matrix.get("cells")
    cells = cells if isinstance(cells, list) else []
    grid: dict[tuple[str, str], dict] = {}
    cell_ids: dict[str, dict] = {}
    evidence_cards = []
    normalized: dict[str, Any] = {}
    for pos, cell in enumerate(cells):
        if not isinstance(cell, dict):
            findings.append(C.make_finding("compare.cell_not_object", "high", f"cells[{pos}] is not an object", pos))
            continue
        did = _doc_id(cell, pos)
        fid = str(cell.get("field_id") or cell.get("field") or "")
        cid = str(cell.get("cell_id") or f"{did}:{fid}")
        owner = cid
        if did not in doc_ids or fid not in field_ids:
            findings.append(C.make_finding("compare.cell_unregistered", "high", f"{owner}: document/field is not registered", owner))
        if (did, fid) in grid:
            findings.append(C.make_finding("compare.cell_duplicate", "high", f"{owner}: duplicate grid cell", owner))
        if cid in cell_ids:
            findings.append(C.make_finding("compare.cell_id_duplicate", "high", f"{owner}: duplicate cell_id", owner))
        grid[(did, fid)] = cell
        cell["cell_id"] = cid
        cell_ids[cid] = cell
        status = cell.get("status")
        if status not in STATUSES:
            findings.append(C.make_finding("compare.cell_status_invalid", "high", f"{owner}: invalid status {status!r}", owner))
            continue
        if status == "not_reported" and not str(cell.get("search_note") or "").strip():
            findings.append(C.make_finding("compare.not_reported_unsearched", "high", f"{owner}: not_reported needs search_note", owner))
        if status == "extraction_failed" and not str(cell.get("failure_note") or "").strip():
            findings.append(C.make_finding("compare.extraction_failure_unexplained", "high", f"{owner}: extraction_failed needs failure_note", owner))
        if status == "not_applicable" and not str(cell.get("reason") or "").strip():
            findings.append(C.make_finding("compare.not_applicable_unexplained", "high", f"{owner}: not_applicable needs reason", owner))
        if status != "reported":
            continue
        if cell.get("value") in (None, ""):
            findings.append(C.make_finding("compare.reported_value_missing", "high", f"{owner}: reported value is empty", owner))
        ev, errs = corpus.anchor(_cell_evidence(cell), owner)
        findings.extend(errs)
        if ev.get("source_document_id") != did:
            findings.append(C.make_finding("compare.wrong_source", "high", f"{owner}: evidence source does not equal cell document {did}", owner))
        field = schema.get(fid, {})
        group = str(field.get("group") or field.get("kind") or "data")
        if group == "conclusion":
            if cell.get("direction") not in DIRECTIONS - {"not_applicable"}:
                findings.append(C.make_finding("compare.direction_missing", "high", f"{owner}: conclusion needs a valid direction", owner))
            if cell.get("strength") not in STRENGTHS - {"insufficient"}:
                findings.append(C.make_finding("compare.strength_missing", "medium", f"{owner}: conclusion needs strong/moderate/weak", owner))
        alignment_keys = field.get("alignment_keys") or workorder.get("alignment_keys") or DEFAULT_ALIGNMENT
        alignment = cell.get("alignment") if isinstance(cell.get("alignment"), dict) else {}
        for key in alignment_keys:
            if not isinstance(key, str):
                continue
            lookup = "unit" if key == "units" else key
            value = alignment.get(key, alignment.get(lookup, cell.get(lookup)))
            if value is None or value == "":
                findings.append(C.make_finding("compare.alignment_missing", "high",
                                               f"{owner}: alignment key '{key}' is missing; use not_applicable explicitly", owner))
            alignment[key] = value
        cell["alignment"] = alignment
        norm, errs = _validate_conversion(field, cell, owner)
        findings.extend(errs)
        normalized[cid] = cell.get("direction") if group == "conclusion" else norm
        if cell.get("comparable") is False and not str(cell.get("comparability_note") or "").strip():
            findings.append(C.make_finding("compare.noncomparable_unexplained", "high", f"{owner}: comparable=false needs comparability_note", owner))
        evidence_cards.append({"cell_id": cid, "field_id": fid, "value": cell.get("value"),
                               "unit": cell.get("unit") or cell.get("units"),
                               "normalized_value": norm, "normalized_unit": field.get("target_unit") or cell.get("unit"),
                               "direction": cell.get("direction"), "strength": cell.get("strength"),
                               "comparable": cell.get("comparable", True),
                               "alignment": copy.deepcopy(alignment), "evidence": ev,
                               "conditions": copy.deepcopy(cell.get("conditions", []))})
    for did in doc_ids:
        for fid in field_ids:
            if (did, fid) not in grid:
                findings.append(C.make_finding("compare.grid_cell_missing", "high", f"missing {did} x {fid}; add a classified empty cell", f"{did}:{fid}"))
    syntheses = matrix.get("synthesis") if isinstance(matrix.get("synthesis"), list) else []
    synthesis_by_field: dict[str, dict] = {}
    for pos, syn in enumerate(syntheses):
        if not isinstance(syn, dict):
            findings.append(C.make_finding("compare.synthesis_not_object", "high", f"synthesis[{pos}] is not an object", pos))
            continue
        fid = str(syn.get("field_id") or "")
        if fid in synthesis_by_field:
            findings.append(C.make_finding("compare.synthesis_duplicate", "high", f"{fid}: duplicate synthesis", fid))
        synthesis_by_field[fid] = syn
        relation = syn.get("relation")
        if relation not in RELATIONS:
            findings.append(C.make_finding("compare.synthesis_relation_invalid", "high", f"{fid}: invalid relation {relation!r}", fid))
            continue
        cids = [str(x) for x in syn.get("cell_ids", [])] if isinstance(syn.get("cell_ids"), list) else []
        selected = [cell_ids[x] for x in cids if x in cell_ids]
        if len(cids) < 2 or len(selected) != len(cids):
            findings.append(C.make_finding("compare.synthesis_cells_unresolved", "high", f"{fid}: synthesis needs at least two valid cell_ids", fid))
        reported = [c for c in selected if c.get("status") == "reported"]
        values = {_norm_scalar(normalized.get(str(c.get("cell_id")))) for c in reported}
        if relation == "consensus":
            if len(reported) < 2:
                findings.append(C.make_finding("compare.consensus_without_two_sources", "high", f"{fid}: consensus requires reported evidence from at least two documents", fid))
            if len(values) > 1:
                findings.append(C.make_finding("compare.consensus_misstated", "high", f"{fid}: consensus masks different normalized values/directions", fid))
        if len(values) > 1 and relation not in {"conflict", "partial"}:
            findings.append(C.make_finding("compare.divergence_unclassified", "high", f"{fid}: divergent reported evidence cannot be hidden as consensus or insufficient evidence", fid))
        if relation == "conflict" and len(values) < 2:
            findings.append(C.make_finding("compare.conflict_without_divergence", "high", f"{fid}: conflict requires distinct reported values/directions after normalization", fid))
        if relation in {"conflict", "partial"}:
            causes = syn.get("difference_causes")
            causes = causes if isinstance(causes, list) else []
            if not causes:
                findings.append(C.make_finding("compare.conflict_unattributed", "high", f"{fid}: conflict/partial needs difference_causes", fid))
            for cpos, cause in enumerate(causes):
                if not isinstance(cause, dict) or cause.get("kind") not in CAUSES:
                    findings.append(C.make_finding("compare.difference_cause_invalid", "high", f"{fid}: cause kind must be one of {sorted(CAUSES)}", fid))
                    continue
                if not str(cause.get("explanation") or "").strip():
                    findings.append(C.make_finding("compare.difference_cause_unexplained", "high", f"{fid}: each cause needs explanation", fid))
                anchors = cause.get("evidence") if isinstance(cause.get("evidence"), list) else []
                if cause.get("kind") != "unknown" and len(anchors) < 2:
                    findings.append(C.make_finding("compare.difference_cause_two_sided", "high", f"{fid}: known cause needs both documents' evidence", fid))
                for apos, anchor in enumerate(anchors):
                    ev, errs = corpus.anchor(anchor, f"{fid}.cause[{cpos}].evidence[{apos}]")
                    findings.extend(errs)
        if syn.get("evidence_strength") not in STRENGTHS:
            findings.append(C.make_finding("compare.synthesis_strength_invalid", "medium", f"{fid}: synthesis evidence_strength is required", fid))
        pooling = syn.get("pooling_decision", "forbidden")
        if pooling == "allowed":
            if relation != "consensus" or any(c.get("comparable") is False for c in selected):
                findings.append(C.make_finding("compare.noncomparable_pooled", "high", f"{fid}: pooling requires consensus and all cells comparable", fid))
            for key in (schema.get(fid, {}).get("pooling_alignment_keys") or ["question_id", "entity", "time", "metric", "material", "pollutant", "budget", "dataset"]):
                values = {_norm_scalar((c.get("alignment") or {}).get(key)) for c in reported}
                if len(values) > 1:
                    findings.append(C.make_finding("compare.alignment_mismatch_pooled", "high", f"{fid}: pooling disagrees on alignment key '{key}'", fid))
        elif pooling not in {"forbidden", "not_attempted"}:
            findings.append(C.make_finding("compare.pooling_decision_invalid", "medium", f"{fid}: use allowed/forbidden/not_attempted", fid))
    for fid in field_ids:
        if fid not in synthesis_by_field:
            findings.append(C.make_finding("compare.synthesis_missing", "high", f"{fid}: no cross-document synthesis row", fid))
    result = {"documents": doc_defs, "field_defs": field_defs, "comparison_table": cells,
              "evidence_cards": evidence_cards, "synthesis": syntheses,
              "source_quality": corpus.quality(), "findings": findings}
    return result, findings


def build(case: dict, workorder: dict, matrix: dict, bundle: Any, out_dir: Path) -> tuple[dict, int]:
    corpus = C.SourceCorpus(bundle)
    main, findings = audit(workorder, matrix, corpus)
    findings = C.finalise_findings(findings)
    status, code = C.run_state(findings)
    counts = C.severity_counts(findings)
    relations = {}
    for syn in main["synthesis"]:
        rel = str(syn.get("relation"))
        relations[rel] = relations.get(rel, 0) + 1
    sources = [{"source_document_id": did, "sha256": corpus.documents[did]["digest"]} for did in sorted(corpus.documents)]
    result = {"schema_version": C.SCHEMA_VERSION, "status": status, "ok": status == "success",
              "section": "compare_docs_v2", "findings": findings, "audit_report": findings,
              "severity_counts": counts, "sources": sources, "uncertainty": [],
              "source_quality": main["source_quality"], "comparison_table": main["comparison_table"],
              "documents": main["documents"], "field_defs": main["field_defs"],
              "evidence_cards": main["evidence_cards"], "synthesis": main["synthesis"],
              "integrated_result": {"documents_compared": len(main["documents"]),
                                    "fields_aligned": len(main["field_defs"]),
                                    "relation_counts": relations,
                                    "pooling_default": "forbidden unless explicitly validated"},
              "checked": {"documents": len(main["documents"]), "fields": len(main["field_defs"]),
                          "cells": len(main["comparison_table"]), "evidence_cards": len(main["evidence_cards"])},
              "limits": ["Semantic comparability and difference causes are agent judgements checked here for evidence, structure and internal consistency; this standard-library engine is not a learned NLI model.",
                         "Only supplied source snapshots were checked; no PDF page, DOI, full-text access or metadata lookup is fabricated."],
              "change_records": [{"action": "align_then_synthesize", "order": ["question/entity/time/metric/unit comparability", "quote verification", "consensus/conflict synthesis", "pooling decision"]}]}
    for cell in main["comparison_table"]:
        if cell.get("status") in {"not_reported", "extraction_failed"} or cell.get("comparable") is False:
            result["uncertainty"].append({"cell_id": cell.get("cell_id"), "status": cell.get("status"),
                                          "reason": cell.get("search_note") or cell.get("failure_note") or cell.get("comparability_note")})
    result = C.complete_contract(result, case, workorder=workorder)
    C.dump_json(out_dir / "comparison_table.json", {"documents": main["documents"], "field_defs": main["field_defs"],
                                                   "cells": main["comparison_table"], "synthesis": main["synthesis"]})
    C.dump_json(out_dir / "evidence_cards.json", main["evidence_cards"])
    C.dump_json(out_dir / "result.json", result)
    return result, code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--workorder", default="")
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--sources", default="", help="source snapshot JSON; defaults to case.source_documents/documents")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    case, err = C.read_json(args.case)
    if err or not isinstance(case, dict):
        C.write_refusal(case, out, err or "case.json must be an object")
        return 5
    wo_path = args.workorder or str(Path(args.case).parent / "comparison-workorder.json")
    workorder, err = C.read_json(wo_path)
    if err or not isinstance(workorder, dict):
        C.write_refusal(case, out, err or "comparison-workorder.json must be an object", workorder=workorder)
        return 5
    try:
        matrix, merr = C.read_json(args.matrix)
        if merr or not isinstance(matrix, dict):
            C.write_refusal(case, out, merr or "matrix.json must be an object", workorder=workorder)
            return 5
        if args.sources:
            bundle, serr = C.read_json(args.sources)
            if serr:
                C.write_refusal(case, out, serr, workorder=workorder)
                return 5
        else:
            bundle = {"documents": case.get("source_documents") or case.get("documents") or matrix.get("source_documents") or []}
        _, code = build(case, workorder, matrix, bundle, out)
        print(json.dumps({"case_id": case.get("case_id"), "status": json.loads((out / "result.json").read_text(encoding="utf-8"))["status"],
                          "wrote": str(out / "result.json")}, ensure_ascii=False))
        return code
    except Exception as exc:  # documented runtime boundary: no traceback as a deliverable
        C.write_refusal(case, out, f"v2 comparison could not be completed: {type(exc).__name__}: {exc}", workorder=workorder)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

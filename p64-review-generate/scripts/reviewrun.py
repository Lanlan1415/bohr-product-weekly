"""Generate an evidence-linked thematic review and reproducible audit artifacts.

python -I -X utf8 scripts/reviewrun.py --spec /app/work/review-spec.json \
  --case /input/case.json --out /app/output
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_contract as C  # noqa: E402
import review_engine as E  # noqa: E402

EXIT = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, message: str, case: dict | None = None,
             case_id=None, case_error: str | None = None) -> dict:
    case = case or {}
    identity = case.get("case_id", case_id)
    result = {
        "schema_version": "reviewrun/v2", "status": "undetermined", "case_id": identity,
        "findings": [{"rule": "review.spec_unreadable", "severity": "high", "message": message}],
        "severity_counts": {"high": 1, "medium": 0, "low": 0},
        "uncertainties": [{"kind": "input", "message": message}],
        "uncertainty": [{"kind": "input", "message": message}],
        "limits": ["the review could not run as declared; no synthesis or citation coverage was claimed"],
    }
    if case_error:
        result["limits"].append(case_error)
    try:
        C.complete(result, {}, case)
        _write_result(Path(out_dir), result)
    except Exception as exc:
        result["limits"].append(f"refusal result could not be completed/written: {type(exc).__name__}: {exc}")
    return result


def _json_cell(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_csv(path: Path, rows: list[dict], preferred: list[str]) -> None:
    fields = list(preferred)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _json_cell(row.get(key)) for key in fields})


def _md(value) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None or value == "":
        return "undetermined"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _citation_text(refs: list[dict]) -> str:
    return "；".join(f"{row['record_id']} [{row['evidence_id']}] @ {row['locator']} — “{row['quote']}”"
                     for row in refs) or "undetermined"


def render_draft(result: dict) -> str:
    screening = result.get("screening") or {}
    coverage = result.get("citation_coverage") or {}
    lines = [
        "# 文献综述：主题比较、证据综合与边界", "",
        "> 本稿仅综合所给固定语料中按冻结协议纳入的记录，不是实时数据库检索，也不把未检索到解释为不存在。多标签主题计数不相加为独立文献数。", "",
        f"- case_id：{_md(result.get('case_id'))}", f"- 研究问题：{_md(result.get('review_question'))}",
        f"- 语料：{_md((result.get('corpus') or {}).get('id'))} / version {_md((result.get('corpus') or {}).get('version'))} / snapshot {_md((result.get('corpus') or {}).get('snapshot_date'))}",
        f"- 运行状态：{result.get('status')}", "",
        "## 1. 筛选先于综合", "",
        f"协议版本：{_md((result.get('screening_protocol') or {}).get('version'))}；纳入标准：{_md((result.get('screening_protocol') or {}).get('inclusion_criteria'))}；排除标准：{_md((result.get('screening_protocol') or {}).get('exclusion_criteria'))}。", "",
        "| 原始行 | 畸形行 | 重复版本 | 去重后筛选 | 纳入 | 排除 | 未决 |",
        "|-|-|-|-|-|-|-|",
        f"| {screening.get('identified_input_rows', 0)} | {screening.get('malformed_rows', 0)} | {screening.get('duplicates', 0)} | {screening.get('screened_unique_records', 0)} | {screening.get('included', 0)} | {screening.get('excluded', 0)} | {screening.get('undetermined', 0)} |",
        "", "这些数字只由本 spec 的实际 records 行计算，不是数据库总命中数。逐条纳入、排除、重复指向见 screening_log.csv。", "",
        "## 2. 主题归纳与跨研究综合", "",
        "主题归属必须给出原文理由；同一记录可进入多个有边界的主题，因此主题成员数不是互斥分区。", "",
    ]
    claims = result.get("synthesis_claims") or []
    comparisons = result.get("comparison_matrix") or []
    gaps = result.get("research_gaps") or []
    for theme in result.get("themes") or []:
        tid = theme.get("id")
        lines += [f"### {theme.get('label')}（{tid}）", "",
                  f"**主题边界。** {_md(theme.get('boundary'))}", "",
                  "**归属依据。** " + "；".join(
                      f"{row['record_id']}：{_md(row['rationale'])}（证据 {_md(row['evidence_refs'])}）"
                      for row in theme.get("evidence_backed_assignments") or []), "",
                  "#### 方法、数据、评价与结论比较", "",
                  "| 文献 | 比较组 | 方法 | 数据 | 评价 | 结论/方向 | 证据 ID |", "|-|-|-|-|-|-|-|"]
        for row in comparisons:
            if tid not in (row.get("theme_ids") or []):
                continue
            lines.append(f"| {_md(row.get('title'))}（{row.get('record_id')}） | {_md(row.get('comparison_key'))} | {_md(row.get('method'))} | {_md(row.get('data'))} | {_md(row.get('metric'))} | {_md(row.get('conclusion'))} / {_md(row.get('direction'))} | {_md(row.get('evidence_refs'))} |")
        lines.append("")
        theme_claims = [row for row in claims if row.get("theme_id") == tid]
        if theme_claims:
            lines += ["#### 综合论断（不是逐篇摘要拼接）", ""]
        for claim in theme_claims:
            support = [row for row in claim.get("citations") or [] if row["evidence_id"] in claim.get("support_evidence_refs", [])]
            contra = [row for row in claim.get("citations") or [] if row["evidence_id"] in claim.get("contradicting_evidence_refs", [])]
            lines.append(f"**[{claim.get('computed_strength')}/{claim.get('type')}] {claim.get('statement')}**")
            if claim.get("type") == "contradiction":
                lines.append(f"比较组 {claim.get('comparison_key')} 的结论不能平均成单一方向：支持侧为 {_md(claim.get('support_records'))}，相反侧为 {_md(claim.get('contradicting_records'))}；本文保留双方设计与结果差异，不作多数票消解。")
            else:
                lines.append(f"该论断跨 {len(set(claim.get('support_records', [])) | set(claim.get('contradicting_records', [])))} 条独立记录形成，比较键为 {_md(claim.get('comparison_key'))}；证据强度由独立来源数、全文可得性和冲突覆盖共同计算。")
            lines += ["", f"- 支持证据：{_citation_text(support)}"]
            if contra:
                lines.append(f"- 相反/限制证据：{_citation_text(contra)}")
            if claim.get("omitted_conflicting_records"):
                lines.append(f"- 尚未覆盖的相反记录：{_md(claim.get('omitted_conflicting_records'))}；结论保持受限。")
            lines.append("")
        theme_gaps = [row for row in gaps if row.get("theme_id") == tid]
        if theme_gaps:
            lines += ["#### 本主题研究缺口", ""]
        for gap in theme_gaps:
            lines.append(f"- **[{gap.get('computed_status')}] {_md(gap.get('statement'))}**。{_md(gap.get('bounded_conclusion'))} 正向证据：{_citation_text(gap.get('citations') or [])}；范围核查：{_md(gap.get('scope_checks'))}。")
        lines.append("")
    lines += ["## 3. 冲突候选与引用覆盖", "",
              "引擎按 comparison_key 对 direction 不同的记录自动形成冲突候选，不能被一概述括成单方面共识。", "",
              "| 比较组 | 文献 | 方向 | 处理状态 |", "|-|-|-|-|"]
    for row in result.get("conflict_candidates") or []:
        lines.append(f"| {_md(row.get('comparison_key'))} | {_md(row.get('record_ids'))} | {_md(row.get('directions'))} | {_md(row.get('status'))} |")
    lines += ["", f"纳入文献引用覆盖：{coverage.get('cited_records', 0)}/{coverage.get('included_records', 0)}（{coverage.get('record_coverage_ratio', 0)}）；带 quote+locator 的综合论断：{coverage.get('claims_with_locatable_citations', 0)}/{coverage.get('claims', 0)}。",
              f"未被任何综合论断或研究缺口使用的纳入文献：{_md(coverage.get('uncited_record_ids'))}。", "",
              "逐论断支持/相反引用、原文摘录与定位见 citation_coverage.csv；每条证据的纳排和全文状态见 evidence_matrix.csv。", "",
              "## 4. 不确定性、偏倚与限制", ""]
    for row in result.get("uncertainties") or []:
        lines.append(f"- {_md(row.get('kind'))}：{_md(row.get('message'))}")
    for row in result.get("limits") or []:
        lines.append(f"- 限制：{_md(row)}")
    if result.get("findings"):
        lines += ["", "### 未解决审计发现", ""]
        for finding in result["findings"]:
            lines.append(f"- {finding['severity']} / {finding['rule']}：{_md(finding.get('message'))}")
    lines += ["", "## 5. 文献清单（仅输入元数据）", "", "| ID | 题名 | 年份 | DOI/来源 |", "|-|-|-|-|"]
    for row in result.get("screening_log") or []:
        if row.get("computed_decision") == "include":
            lines.append(f"| {_md(row.get('record_id'))} | {_md(row.get('title'))} | {_md(row.get('year'))} | {_md([row.get('doi'), row.get('source')])} |")
    lines.append("")
    return "\n".join(lines)


def _artifact(path: Path, kind: str) -> dict:
    return {"kind": kind, "path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_artifacts(result: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = out_dir / "evidence_matrix.csv"
    comparison_path = out_dir / "theme_comparison.csv"
    screening_path = out_dir / "screening_log.csv"
    coverage_path = out_dir / "citation_coverage.csv"
    draft_path = out_dir / "review_draft.md"
    _write_csv(evidence_path, result.get("evidence_matrix") or [],
               ["evidence_id", "record_id", "title", "doi", "year", "source", "screening_decision",
                "include_exclude_reason", "full_text_status", "fields", "comparison_key", "direction", "quote", "locator"])
    _write_csv(comparison_path, result.get("comparison_matrix") or [],
               ["record_id", "title", "year", "theme_ids", "comparison_key", "method", "data", "metric",
                "conclusion", "direction", "limitations", "evidence_refs"])
    _write_csv(screening_path, result.get("screening_log") or [],
               ["record_id", "title", "doi", "year", "source", "computed_decision", "duplicate_of",
                "reason", "full_text_status"])
    coverage_rows = []
    for claim in result.get("synthesis_claims") or []:
        for role, refs in (("support", claim.get("support_evidence_refs") or []),
                           ("contradicting", claim.get("contradicting_evidence_refs") or [])):
            for ref in refs:
                ev = next(row for row in claim["citations"] if row["evidence_id"] == ref)
                coverage_rows.append({"claim_id": claim["claim_id"], "claim_type": claim["type"],
                                      "computed_strength": claim["computed_strength"], "role": role,
                                      "record_id": ev["record_id"], "evidence_id": ref,
                                      "comparison_key": claim["comparison_key"], "quote": ev["quote"],
                                      "locator": ev["locator"]})
    for gap in result.get("research_gaps") or []:
        for ev in gap.get("citations") or []:
            coverage_rows.append({"claim_id": gap["gap_id"], "claim_type": "research_gap",
                                  "computed_strength": gap["computed_status"], "role": "positive_gap",
                                  "record_id": ev["record_id"], "evidence_id": ev["evidence_id"],
                                  "comparison_key": ev.get("comparison_key"), "quote": ev["quote"],
                                  "locator": ev["locator"]})
    _write_csv(coverage_path, coverage_rows,
               ["claim_id", "claim_type", "computed_strength", "role", "record_id", "evidence_id",
                "comparison_key", "quote", "locator"])
    draft_path.write_text(render_draft(result), encoding="utf-8")
    result["evidence_matrix_file"] = str(evidence_path)
    result["research_product"] = {"report_path": str(draft_path), "format": "markdown",
                                  "contains": ["screening", "themes", "comparison", "consensus", "contradictions", "gaps", "coverage"],
                                  "citation_coverage": result.get("citation_coverage")}
    result["deliverables"] = [str(draft_path), str(evidence_path), str(comparison_path),
                              str(screening_path), str(coverage_path)]
    result["artifacts"] = [_artifact(draft_path, "research_product"),
                           _artifact(evidence_path, "evidence_matrix"),
                           _artifact(comparison_path, "theme_comparison"),
                           _artifact(screening_path, "screening_log"),
                           _artifact(coverage_path, "citation_coverage")]
    return result


def build_and_audit(spec_path: Path, out_dir: Path, case_path: Path | None = None,
                    case_id=None) -> dict:
    case, case_error = C.load_case(case_path)
    identity = case.get("case_id", case_id)
    if case_path is not None and case_error:
        return _refused(out_dir, case_error, case, identity, case_error)
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _refused(out_dir, f"spec is not readable UTF-8 JSON: {exc}", case, identity, case_error)
    if not isinstance(spec, dict):
        return _refused(out_dir, "spec is not a JSON object", case, identity, case_error)
    identity = case.get("case_id") or case_id or spec.get("case_id")
    try:
        result = E.analyze(spec)
        result["case_id"] = identity
        result = write_artifacts(result, Path(out_dir))
        C.complete(result, spec, case)
        _write_result(Path(out_dir), result)
    except Exception as exc:
        return _refused(out_dir, f"review engine boundary: {type(exc).__name__}: {exc}",
                        case, identity, case_error)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="reviewrun", description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--case", help="original case.json; its case_id and output_contract are authoritative")
    parser.add_argument("--case-id", help="fallback identity when case.json is unavailable")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    result = build_and_audit(Path(args.spec), Path(args.out),
                             Path(args.case) if args.case else None, args.case_id)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "coverage": result.get("citation_coverage"),
                      "findings": [row.get("rule") for row in result.get("findings", [])],
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())

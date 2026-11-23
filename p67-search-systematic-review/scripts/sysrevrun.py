"""Run the complete PRISMA, risk-of-bias and synthesis workflow.

python -I -X utf8 scripts/sysrevrun.py --spec /app/work/sysrev-spec.json \
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
import sysrev_engine as E  # noqa: E402

EXIT = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, message: str, case: dict | None = None,
             case_id=None, case_error: str | None = None) -> dict:
    case = case or {}
    result = {
        "schema_version": "sysrevrun/v2", "status": "undetermined",
        "case_id": case.get("case_id", case_id),
        "findings": [{"rule": "sr.spec_unreadable", "severity": "high", "message": message}],
        "severity_counts": {"high": 1, "medium": 0, "low": 0},
        "uncertainties": [{"kind": "input", "message": message}],
        "uncertainty": [{"kind": "input", "message": message}],
        "limits": ["the systematic review could not run as declared; no screening or synthesis count was claimed"],
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


def _num(value) -> str:
    return "undetermined" if not isinstance(value, (int, float)) else f"{value:.6g}"


def _cite(rows: list[dict]) -> str:
    return "；".join(f"{row['report_id']} [{row['evidence_id']}] @ {row['locator']} — “{row['quote']}”"
                     for row in rows) or "undetermined"


def build_flow_rows(result: dict) -> list[dict]:
    flow = result.get("prisma_flow") or {}
    n = flow.get("counts") or {}
    prospective = flow.get("scope") == "prospective"
    value = lambda key: None if prospective else n.get(key)
    reasons_ta = "; ".join(f"{key}, {count}" for key, count in (flow.get("ta_exclusion_reason_counts") or {}).items())
    reasons_ft = "; ".join(f"{key}, {count}" for key, count in (flow.get("ft_exclusion_reason_counts") or {}).items())
    source_detail = "; ".join(f"{row['name']}, {row['records_supplied']}" for row in result.get("search_log") or [])
    meta_ids = sorted({sid for row in result.get("meta_analysis") or [] for sid in row.get("study_ids", [])})
    specs = [
        ("database_results", "box2", "identification", "identified", value("identified"), "reports/rows", source_detail),
        ("duplicates", "box3", "identification", "duplicates", value("duplicates"), "reports", ""),
        ("excluded_automatic", "box3", "identification", "automation_removed", value("automation_removed"), "reports", ""),
        ("excluded_other", "box3", "identification", "other_removed", value("other_removed"), "reports", ""),
        ("records_screened", "box4", "screening", "title_abstract", value("records_screened"), "reports", ""),
        ("records_excluded", "box5", "screening", "title_abstract_excluded", value("records_excluded"), "reports", reasons_ta),
        ("dbr_sought_reports", "box6", "screening", "sought_for_retrieval", value("reports_sought"), "reports", ""),
        ("dbr_notretrieved_reports", "box7", "screening", "not_retrieved", value("reports_not_retrieved"), "reports", ""),
        ("dbr_assessed", "box8", "screening", "assessed_full_text", value("reports_assessed"), "reports", ""),
        ("dbr_excluded", "box9", "screening", "full_text_excluded", value("reports_excluded"), "reports", reasons_ft),
        ("new_studies", "box10", "included", "new_studies", value("studies_included"), "studies", ""),
        ("new_reports", "box10", "included", "new_reports", value("reports_included"), "reports", ""),
        ("total_studies", "box16", "included", "total_studies", value("studies_included"), "studies", "no previous-review arm"),
        ("total_reports", "box16", "included", "total_reports", value("reports_included"), "reports", "no previous-review arm"),
        ("total_studies_ma", "box17", "meta_analysis", "computed_meta_groups", None if prospective else len(meta_ids), "studies", "actual computed groups only"),
    ]
    return [{"data": data, "box": box, "stage": stage, "substage": substage,
             "n": number, "unit": unit, "detail": detail, "source_scope": flow.get("scope")}
            for data, box, stage, substage, number, unit, detail in specs]


def render_report(result: dict) -> str:
    protocol = result.get("search_protocol") or {}
    flow = result.get("prisma_flow") or {}
    question = result.get("research_question") or {}
    lines = [
        "# 系统性文献综述报告", "",
        "> 本报告严格区分已执行导出、固定快照和前瞻协议。前瞻性 PRISMA 外部计数为 undetermined/null，不是 0；固定快照不声称全球完备。", "",
        f"- case_id：{_md(result.get('case_id'))}", f"- 运行状态：{result.get('status')}",
        f"- 协议：{_md(protocol.get('version'))} / {_md(protocol.get('status'))}", "",
        "## 1. 研究结构与冻结标准", "",
        f"- P（对象）：{_md(question.get('population'))}", f"- I（干预/方法）：{_md(question.get('intervention'))}",
        f"- C（比较）：{_md(question.get('comparator'))}", f"- O（结局）：{_md(question.get('outcome'))}",
        f"- 时间窗：{_md(protocol.get('start_date'))} 至 {_md(protocol.get('end_date'))}；语言：{_md(protocol.get('languages'))}",
        f"- 纳入：{_md(protocol.get('inclusion_criteria'))}", f"- 排除：{_md(protocol.get('exclusion_criteria'))}",
        f"- 条款优先级：{_md(protocol.get('criterion_priority'))}", f"- 冲突裁决：{_md(protocol.get('conflict_policy'))}", "",
        "## 2. 可复现检索式、数据库和日期", "",
        "| 数据库 | 原检索式 | 字段 | 同义词/受控词 | 覆盖与检索日 | 执行状态/命中 | 实际供入行 |", "|-|-|-|-|-|-|-|"]
    for row in result.get("search_log") or []:
        hits = row.get("hit_count") if row.get("hit_count") is not None else "undetermined"
        lines.append(f"| {_md(row.get('name'))} | `{_md(row.get('query'))}` | {_md(row.get('fields'))} | {_md([row.get('synonyms'), row.get('controlled_terms')])} | {_md([row.get('coverage'), row.get('search_date'), row.get('filters')])} | {_md(row.get('status'))} / {hits} | {_md(row.get('records_supplied'))} |")
    lines += ["", "原式、字段、过滤和实际供入记录另存 search_protocol.csv。executed 模式要求每源 hit_count 与供入导出记录数完全一致；fixed_corpus/prospective 不伪造该数。", "",
              "## 3. 两轮筛选与 PRISMA 流向", "",
              "题录和全文分别保留决策、理由代码、判定人和分歧裁决；重复版本、自动化移除、其他移除、未获取全文单独列出，剔除原因计数与阶段总数闭合。", "",
              "| data | PRISMA box | 子阶段 | n | 单位 | 来源/原因明细 |", "|-|-|-|-|-|-|"]
    for row in build_flow_rows(result):
        lines.append(f"| {_md(row['data'])} | {_md(row['box'])} | {_md(row['substage'])} | {_md(row['n'])} | {_md(row['unit'])} | {_md(row['detail']) if row['detail'] else '—'} |")
    lines += ["", "### 计数闭合检查", "", "| 恒等式 | 通过 |", "|-|-|"]
    for key, passed in (flow.get("checks") or {}).items():
        lines.append(f"| {key} | {passed} |")
    if not flow.get("checks"):
        lines.append("| prospective-only | undetermined（未执行） |")
    lines += ["", "重复导出去向：", ""]
    for row in flow.get("duplicate_rows") or []:
        lines.append(f"- {_md(row.get('report_id'))} → {_md(row.get('duplicate_of'))}（匹配键 {_md(row.get('match_key'))}）")
    lines += ["", "逐条原始筛选记录见 screening_log.csv；任一阶段未决或拒绝原因不齐都会保留输出但标为 blocked。", "",
              "## 4. 质量与偏倚：逐域证据驱动总体判断", "",
              "总体等级由域 judgment 计算，不由 overall 自报；域汇总不加权，避免样本量/权重掩盖研究构成。", "",
              "| 研究 | 工具 | 域 | judgment | 依据 | 精确证据 | 计算总体 |", "|-|-|-|-|-|-|"]
    for appraisal in result.get("quality_appraisals") or []:
        for domain in appraisal.get("domains") or []:
            refs = [row for row in appraisal.get("citations") or [] if row["evidence_id"] in domain.get("evidence_refs", [])]
            lines.append(f"| {_md(appraisal.get('study_id'))} | {_md(appraisal.get('tool'))} | {_md(domain.get('domain'))} | {_md(domain.get('judgement'))} | {_md(domain.get('rationale'))} | {_md(domain.get('evidence_refs'))} / {_md([row.get('locator') for row in refs])} | {_md(appraisal.get('overall_computed'))} |")
    lines += ["", "### 不加权域汇总", "", "| 工具:域 | 各 judgment 计数 | n | 比例 |", "|-|-|-|-|"]
    for row in (result.get("quality_summary") or {}).get("by_domain") or []:
        lines.append(f"| {_md(row['tool_domain'])} | {_md(row['counts'])} | {row['n']} | {_md({k: round(v, 6) for k, v in row['proportions'].items()})} |")
    lines += ["", "完整域证据见 quality_appraisal.csv；偏倚影响通过主分析/敏感性研究集合改变来呈现，而非把高偏倚研究静默删除。", "",
              "## 5. 异质性与证据综合", "",
              "| 比较组 | 研究 | 设计/对象/干预/对照/结局/随访差异 | 风险等级 | 合并决定 | Q(df) / I² / tau² |", "|-|-|-|-|-|-|"]
    for row in result.get("heterogeneity") or []:
        meta = row.get("meta_analysis") or {}
        stats = f"Q={_num(meta.get('Q'))}({meta.get('df')}) / I²={_num(meta.get('I2_percent'))}% / tau²={_num((meta.get('random_effects_DL') or {}).get('tau2'))}" if meta.get("computed") else _md(meta.get("reason"))
        lines.append(f"| {_md(row.get('comparison_key'))} | {_md(row.get('study_ids'))} | {_md(row.get('variation'))} | {_md(row.get('risk_of_bias'))} | {_md(row.get('pooling_decision'))} | {stats} |")
    lines += ["", "定量合并仅在允许且整组研究都有同 measure、有限 estimate、正 se 时执行；同时报告逆方差固定效应与 DL 随机效应，不会只挑同方向子集。I²≥75% 只能 exploratory，不能作无条件 headline。", "",
              "### 综合论断、冲突与偏倚敏感性", ""]
    for claim in result.get("synthesis_claims") or []:
        support = [row for row in claim.get("citations") or [] if row["evidence_id"] in claim.get("support_evidence_refs", [])]
        contra = [row for row in claim.get("citations") or [] if row["evidence_id"] in claim.get("contradicting_evidence_refs", [])]
        lines += [f"**[{claim.get('computed_strength')}] {_md(claim.get('statement'))}**", "",
                  f"- 比较组：{_md(claim.get('comparison_key'))}；偏倚过滤后研究：{_md(claim.get('primary_study_ids_after_risk_filter'))}；敏感性改变：{_md(claim.get('sensitivity_changed'))}",
                  f"- 支持证据：{_cite(support)}"]
        if contra:
            lines.append(f"- 相反证据：{_cite(contra)}；不作多数票平均。")
        if claim.get("omitted_opposing_reports"):
            lines.append(f"- 遗漏相反报告：{_md(claim.get('omitted_opposing_reports'))}")
        meta = claim.get("heterogeneity") or {}
        if meta.get("computed"):
            lines.append(f"- 定量：固定估计 {_num((meta.get('fixed_effect') or {}).get('estimate'))}，DL 随机估计 {_num((meta.get('random_effects_DL') or {}).get('estimate'))}，I²={_num(meta.get('I2_percent'))}%；{_md(meta.get('interpretation'))}")
        lines.append("")
    lines += ["### 研究空白", ""]
    for gap in result.get("research_gaps") or []:
        lines.append(f"- **[{gap.get('computed_status')}] {_md(gap.get('statement'))}**：{_md(gap.get('bounded_conclusion'))} 正向证据：{_cite(gap.get('citations') or [])}；范围核查：{_md(gap.get('scope_checks'))}。")
    coverage = result.get("citation_coverage") or {}
    lines += ["", "## 6. 引用覆盖、不确定性与限制", "",
              f"纳入报告引用覆盖：{coverage.get('cited_reports', 0)}/{coverage.get('included_reports', 0)}；带 locator 的综合论断：{coverage.get('claims_with_locators', 0)}/{coverage.get('claims', 0)}；未引用：{_md(coverage.get('uncited_report_ids'))}。", ""]
    for row in result.get("uncertainties") or []:
        lines.append(f"- {_md(row.get('kind'))}：{_md(row.get('message'))}")
    for row in result.get("limits") or []:
        lines.append(f"- 限制：{_md(row)}")
    if result.get("findings"):
        lines += ["", "### 未解决审计发现", ""]
        for finding in result["findings"]:
            lines.append(f"- {finding['severity']} / {finding['rule']}：{_md(finding.get('message'))}")
    lines += ["", "evidence_synthesis.csv 逐条保存支持/相反证据；evidence_matrix.csv 保存全部原文 quote 与定位；heterogeneity.csv 保存完整异质性与合并参数。", ""]
    return "\n".join(lines)


def _artifact(path: Path, kind: str) -> dict:
    return {"kind": kind, "path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_artifacts(result: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {name: out_dir / f"{name}.csv" for name in
             ("search_protocol", "screening_log", "prisma_flow", "quality_appraisal",
              "evidence_matrix", "evidence_synthesis", "heterogeneity")}
    report_path = out_dir / "systematic_review.md"
    _write_csv(names["search_protocol"], result.get("search_log") or [],
               ["kind", "name", "query", "fields", "controlled_terms", "synonyms", "filters", "coverage",
                "search_date", "status", "hit_count", "records_supplied"])
    _write_csv(names["screening_log"], result.get("screening_log") or [],
               ["report_id", "study_id", "title", "source_database", "stage", "computed_decision",
                "reason_code", "reason", "reviewer", "reviewers", "adjudication"])
    flow_rows = build_flow_rows(result)
    result["prisma_flow"]["rows"] = flow_rows
    _write_csv(names["prisma_flow"], flow_rows,
               ["data", "box", "stage", "substage", "n", "unit", "detail", "source_scope"])
    quality_rows = []
    for appraisal in result.get("quality_appraisals") or []:
        for domain in appraisal.get("domains") or []:
            quality_rows.append({**domain, "overall_computed": appraisal["overall_computed"],
                                 "overall_reported": appraisal.get("overall_reported"),
                                 "summary_weighting": "unweighted"})
    _write_csv(names["quality_appraisal"], quality_rows,
               ["study_id", "tool", "domain", "judgement", "rationale", "evidence_refs",
                "overall_computed", "overall_reported", "summary_weighting"])
    _write_csv(names["evidence_matrix"], result.get("evidence_matrix") or [],
               ["evidence_id", "report_id", "study_id", "title", "doi", "year", "source_database",
                "fields", "comparison_key", "included", "quote", "locator"])
    synthesis_rows = []
    for claim in result.get("synthesis_claims") or []:
        for role, refs in (("support", claim.get("support_evidence_refs") or []),
                           ("contradicting", claim.get("contradicting_evidence_refs") or [])):
            for ref in refs:
                ev = next(row for row in claim["citations"] if row["evidence_id"] == ref)
                synthesis_rows.append({"claim_id": claim["claim_id"], "type": claim["type"],
                                       "comparison_key": claim["comparison_key"], "strength": claim["computed_strength"],
                                       "role": role, "report_id": ev["report_id"], "study_id": ev["study_id"],
                                       "evidence_id": ref, "quote": ev["quote"], "locator": ev["locator"],
                                       "sensitivity_changed": claim["sensitivity_changed"]})
    _write_csv(names["evidence_synthesis"], synthesis_rows,
               ["claim_id", "type", "comparison_key", "strength", "role", "report_id", "study_id",
                "evidence_id", "quote", "locator", "sensitivity_changed"])
    hetero_rows = []
    for row in result.get("heterogeneity") or []:
        meta = row.get("meta_analysis") or {}
        hetero_rows.append({"comparison_key": row["comparison_key"], "study_ids": row["study_ids"],
                            "variation": row["variation"], "risk_of_bias": row["risk_of_bias"],
                            "effect_measures": row["effect_measures"], "pooling_decision": row["pooling_decision"],
                            "computed": meta.get("computed"), "reason": meta.get("reason"),
                            "Q": meta.get("Q"), "df": meta.get("df"), "I2_percent": meta.get("I2_percent"),
                            "tau2": (meta.get("random_effects_DL") or {}).get("tau2"),
                            "fixed_effect": meta.get("fixed_effect"), "random_effects_DL": meta.get("random_effects_DL"),
                            "sensitivity_by_risk": row.get("sensitivity_by_risk")})
    _write_csv(names["heterogeneity"], hetero_rows,
               ["comparison_key", "study_ids", "variation", "risk_of_bias", "effect_measures", "pooling_decision",
                "computed", "reason", "Q", "df", "I2_percent", "tau2", "fixed_effect",
                "random_effects_DL", "sensitivity_by_risk"])
    report_path.write_text(render_report(result), encoding="utf-8")
    result["evidence_matrix_file"] = str(names["evidence_matrix"])
    result["research_product"] = {"report_path": str(report_path), "format": "markdown",
                                  "contains": ["protocol", "two_stage_screening", "PRISMA", "quality", "heterogeneity", "synthesis", "gaps"]}
    result["deliverables"] = [str(report_path)] + [str(path) for path in names.values()]
    result["artifacts"] = [_artifact(report_path, "research_product")] + [
        _artifact(names[name], name) for name in names]
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
        return _refused(out_dir, f"systematic-review engine boundary: {type(exc).__name__}: {exc}",
                        case, identity, case_error)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sysrevrun", description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--case", help="original case.json; its case_id and output_contract are authoritative")
    parser.add_argument("--case-id", help="fallback identity when case.json is unavailable")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    result = build_and_audit(Path(args.spec), Path(args.out),
                             Path(args.case) if args.case else None, args.case_id)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "prisma_complete": (result.get("prisma_flow") or {}).get("complete"),
                      "findings": [row.get("rule") for row in result.get("findings", [])],
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())

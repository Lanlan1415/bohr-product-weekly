"""Run the complete trend-analysis pipeline and write auditable research artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_contract as C  # noqa: E402
import trend_engine as E  # noqa: E402

EXIT = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


def _refused(out_dir, message: str, case_id=None) -> dict:
    """Standalone refusal: never invokes contract echo or assumes spec exists."""
    result = {"schema_version": "trendrun/v2", "status": "undetermined",
              "case_id": case_id,
              "findings": [{"rule": "audit.no_section", "severity": "high", "message": message}],
              "severity_counts": {"high": 1}, "uncertainty": [{"kind": "input", "message": message}],
              "limits": ["the case could not be run as declared"]}
    try:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        result["limits"].append(f"result.json could not be written: {exc}")
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
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _json_cell(row.get(key)) for key in fields})


def _md(value) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return E._norm(value).replace("|", "\\|").replace("\n", " ")


def _evidence_refs(items) -> str:
    refs = []
    for item in items or []:
        if isinstance(item, dict):
            refs.append(f"{item.get('record_id', '?')} @ {item.get('locator', 'locator missing')}")
        else:
            refs.append(str(item))
    return "; ".join(refs)


def render_report(result: dict, case_id) -> str:
    lines = [
        "# 研究前沿与趋势分析报告", "",
        "> 本报告只覆盖声明的固定语料、检索协议与年份口径；不构成全球完备性、因果关系或全局新颖性证明。",
        "", f"- case_id：{case_id}", f"- 研究问题：{_md(result.get('research_question'))}",
        f"- 运行状态：{result.get('status')}", "",
        "## 1. 检索范围、年份口径与系统筛选", "",
    ]
    protocol = result.get("search_protocol") or {}
    lines += [f"- 来源：{_md(protocol.get('sources'))}",
              f"- 检索式：{_md(protocol.get('queries'))}",
              f"- 时间窗：{protocol.get('start_year')}–{protocol.get('end_year')}；完整年份截至 {protocol.get('complete_through', '未单独声明')}",
              f"- 主年份口径：{protocol.get('year_basis')}；预印本/在线/见刊不混池", ""]
    screening = result.get("screening") or {}
    lines += ["| identified | included | excluded | undetermined | duplicates | time_counted |",
              "|-|-|-|-|-|-|",
              "| {identified} | {included} | {excluded} | {undetermined} | {duplicates} | {time_counted} |".format(**screening),
              "", "逐条纳排理由、去重指向和缺失字段见 evidence_matrix.csv。", "",
              "## 2. 时间趋势：年度分布与拐点证据", "",
              "| 年份 | 纳入计数 | 同比增量 | 同比增长率 | 三年滑动均值 |", "|-|-|-|-|-|"]
    for row in (result.get("time_trend") or {}).get("annual_counts", []):
        lines.append(f"| {row['year']} | {row['count']} | {_md(row.get('absolute_change'))} | {_md(row.get('growth_rate'))} | {row.get('moving_average_3')} |")
    method = (result.get("time_trend") or {}).get("change_point_method") or {}
    lines += ["", f"拐点方法：{method.get('test')}；min_segment={method.get('min_segment')}；alpha={method.get('alpha')}；Bonferroni 校正所有候选年份。",
              "", "| 候选年 | 左均值 | 右均值 | 差值 | 原始 p | 校正 p | 判定 |", "|-|-|-|-|-|-|-|"]
    for row in (result.get("time_trend") or {}).get("change_point_candidates", []):
        lines.append(f"| {row['year']} | {row['left_mean']} | {row['right_mean']} | {row['absolute_difference']} | {row['p_value']:.6g} | {row['bonferroni_p']:.6g} | {'支持' if row['supported'] else '波动/未决'} |")
    lines.append("")
    for claim in (result.get("time_trend") or {}).get("interpretations", []):
        lines.append(f"- [{claim.get('statement_type')}] {claim.get('text')} 证据：{_evidence_refs(claim.get('evidence'))}")
    sensitivity = (result.get("time_trend") or {}).get("year_basis_sensitivity") or []
    if sensitivity:
        lines += ["", "### 年份口径敏感性", "", "| 备选口径 | 有该年份的记录 | 支持的拐点 | 与主口径是否不同 |", "|-|-|-|-|"]
        for row in sensitivity:
            lines.append(f"| {row['year_basis']} | {row['records_with_year']} | {_md(row['supported_change_points'])} | {row['classification_changed']} |")
    lines += ["", "## 3. 主题演化、术语漂移与同名歧义", "",
              "主题为多标签；分母是当年全部纳入趋势的记录，因此主题占比不要求合计为 100%。", "",
              "| 主题 | 总指派 | 本语料首次出现 | 最后出现 | 峰值年份 |", "|-|-|-|-|-|"]
    for row in (result.get("topic_evolution") or {}).get("topic_summaries", []):
        lines.append(f"| {_md(row['topic'])} | {row['total_assignments']} | {_md(row['first_observed_year'])} | {_md(row['last_observed_year'])} | {_md(row['peak_years'])} |")
    lines += ["", "完整主题×年份计数与占比见 topic_year_matrix.csv；别名首次/末次出现及记录清单见 result.json 的 terminology。", "",
              "### 显式演化事件", ""]
    events = (result.get("topic_evolution") or {}).get("events") or []
    if not events:
        lines.append("没有满足证据条件的显式 merge/split 事件；共同出现不自动解释为主题合并。")
    for event in events:
        lines.append(f"- [{event.get('statement_type')}] {event.get('type')} / {event.get('year')} / {_md('、'.join(event.get('topics') or []))}：{_md(event.get('basis'))} 证据：{_evidence_refs(event.get('evidence'))}")
    lines += ["", "## 4. 各阶段代表性工作", "",
              "代表作按阶段内 method-first、贡献类型、可定位证据和阶段内被引分位加权；被引不是唯一或跨期绝对排序。", "",
              "| 阶段 | 文献 | 年份 | 得分 | 入选理由 | 精确定位 |", "|-|-|-|-|-|-|"]
    for row in result.get("representative_works") or []:
        lines.append(f"| {_md(row['phase_id'])} | {_md(row['title'])}（{row['record_id']}） | {row['year']} | {row['selection_score']:.3f} | {_md('；'.join(row['reasons']))} | {_md('；'.join(row['locators']))} |")
    if not result.get("representative_works"):
        lines.append("| 无 | 无可用代表作 |  |  | 见 findings |  |")
    lines += ["", "## 5. 研究空白：正向证据与解决性排除", "",
              "只有直接未解决/失效/冲突证据与可复跑的解决性检索同时存在，才输出 supported_bounded_gap；未检索到本身永远不够。", "",
              "| 候选 | 类型 | 计算状态 | 正向证据 | 排除检索 | 边界结论 |", "|-|-|-|-|-|-|"]
    for gap in result.get("research_gaps") or []:
        checks = "; ".join(f"{x.get('source')} / {x.get('query')} / {x.get('covered_years')} / {x.get('outcome')}"
                           for x in gap.get("exclusion_checks") or [])
        lines.append(f"| {_md(gap.get('candidate'))} | {gap.get('type')} | {gap.get('computed_status')} | {_evidence_refs(gap.get('evidence'))} | {_md(checks)} | {_md(gap.get('bounded_conclusion'))} |")
    if not result.get("research_gaps"):
        lines.append("未提出候选不等于不存在空白；本固定输入没有可评估的 gap_candidates。")
    lines += ["", "## 6. 不确定性、冲突与可复核文件", ""]
    for item in result.get("uncertainty") or []:
        if isinstance(item, dict):
            message = item.get("message") or item.get("reason") or item.get("scope") or "declared uncertainty"
            suffix = f"；对象：{item.get('record_id')}" if item.get("record_id") else ""
            lines.append(f"- {item.get('kind', 'note')}：{_md(message)}{_md(suffix)}")
        else:
            lines.append(f"- {_md(item)}")
    if result.get("findings"):
        lines += ["", "### 未解决审计发现", ""]
        for finding in result["findings"]:
            lines.append(f"- {finding['severity']} / {finding['rule']}：{_md(finding.get('message'))}")
    lines += ["", "- evidence_matrix.csv：逐篇来源、纳排、年份口径、比较字段和定位。",
              "- annual_counts.csv：年度计数、增长和可复算来源单元。",
              "- topic_year_matrix.csv：主题层级、年度计数、占比与分母。",
              "- result.json：完整机器可读结果、检索协议、代表作权重、空白证据和运行状态。", ""]
    return "\n".join(lines)


def _artifact(path: Path, kind: str) -> dict:
    return {"kind": kind, "path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_artifacts(result: dict, out_dir: Path, case_id) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = out_dir / "evidence_matrix.csv"
    annual_path = out_dir / "annual_counts.csv"
    topic_path = out_dir / "topic_year_matrix.csv"
    report_path = out_dir / "trend_report.md"
    _write_csv(matrix_path, result["evidence_matrix"],
               ["record_id", "doi", "title", "year_used", "year_basis", "year_provenance",
                "screening_decision", "screening_reason", "included_in_trends", "topics",
                "method", "object", "scale", "contribution_type", "citation_count", "locators", "source_file"])
    _write_csv(annual_path, result["time_trend"].get("annual_counts") or [],
               ["year", "count", "corpus_share", "absolute_change", "growth_rate", "moving_average_3", "evidence"])
    _write_csv(topic_path, result["topic_evolution"].get("topic_year_matrix") or [],
               ["topic", "year", "count", "annual_included_count", "share", "share_denominator", "multi_label", "evidence"])
    report_path.write_text(render_report(result, case_id), encoding="utf-8")
    result["evidence_matrix_file"] = str(matrix_path)
    result["research_product"] = {
        "report_path": str(report_path), "format": "markdown",
        "contains": ["time_trend", "topic_evolution", "representative_works", "research_gaps"],
        "summary": result["time_trend"].get("interpretations") or [],
    }
    result["artifacts"] = [_artifact(report_path, "research_product"),
                           _artifact(matrix_path, "evidence_matrix"),
                           _artifact(annual_path, "time_slice_statistics"),
                           _artifact(topic_path, "topic_year_statistics")]
    return result


def build_and_audit(spec_path, out_dir, case_path=None, case_id=None) -> dict:
    case, case_error = C.load_case(case_path)
    identity = case.get("case_id") if case.get("case_id") is not None else case_id
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _refused(out_dir, f"spec is not readable UTF-8 JSON: {exc}", identity)
    if not isinstance(spec, dict):
        return _refused(out_dir, "spec is not a JSON object", identity)
    identity = case.get("case_id") or case_id or spec.get("case_id")
    try:
        result = E.analyze(spec, Path(spec_path).resolve().parent)
        result = write_artifacts(result, Path(out_dir), identity)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        return _refused(out_dir, f"trend analysis could not complete: {type(exc).__name__}: {exc}", identity)
    if case_error:
        result["limits"].append(case_error)
    C.complete(result, spec, case)
    if case_id is not None and not case.get("case_id"):
        result["case_id"] = case_id
    try:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        return _refused(out_dir, f"result.json could not be written: {exc}", identity)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="trendrun", description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--case", help="original case.json; identity and contract are authoritative")
    parser.add_argument("--case-id", help="explicit fallback identity for refusal/partial runs")
    args = parser.parse_args(argv)
    try:
        result = build_and_audit(args.spec, args.out,
                                 Path(args.case) if args.case else None, args.case_id)
    except Exception as exc:
        result = _refused(args.out, f"unexpected engine boundary: {type(exc).__name__}: {exc}", args.case_id)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "findings": [f.get("rule") for f in result.get("findings", [])],
                      "records": (result.get("checked") or {}).get("input_records"),
                      "artifacts": len(result.get("artifacts") or []),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the evidence-bounded topic evaluation and write reproducible artifacts.

python -I -X utf8 scripts/topicrun.py --spec /app/work/topic-spec.json \
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
import topic_engine as E  # noqa: E402

EXIT = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, message: str, case: dict | None = None,
             case_id=None, case_error: str | None = None) -> dict:
    case = case or {}
    identity = case.get("case_id", case_id)
    result = {
        "schema_version": "topicrun/v2", "status": "undetermined", "case_id": identity,
        "findings": [{"rule": "topic.spec_unreadable", "severity": "high", "message": message}],
        "severity_counts": {"high": 1, "medium": 0, "low": 0},
        "uncertainties": [{"kind": "input", "message": message}],
        "uncertainty": [{"kind": "input", "message": message}],
        "limits": ["the topic evaluation could not run as declared; no novelty or feasibility conclusion was reached"],
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
    if value is None:
        return "undetermined"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_report(result: dict) -> str:
    q = result.get("research_question") or {}
    protocol = result.get("search_protocol") or {}
    decision = result.get("decision") or {}
    lines = [
        "# 科研选题与创新性评估报告", "",
        "> 本报告仅覆盖声明的数据库/来源、时间窗、检索式与所给已有工作集合；不构成全球首创、全球完备性或已完成实验的证明。",
        "", f"- case_id：{_md(result.get('case_id'))}", f"- 运行状态：{result.get('status')}",
        f"- 决策等级：**{_md(decision.get('grade'))}**", f"- 决策理由：{_md(decision.get('reason'))}", "",
        "## 1. 可检验研究问题", "",
        "| 要素 | 有界陈述 |", "|-|-|",
    ]
    for field in ("statement", "object", "variables", "comparator", "outcome",
                  "expected_conclusion", "falsification_condition", "scope"):
        lines.append(f"| {field} | {_md(q.get(field))} |")
    lines += ["", "## 2. 多源检索与纳排边界", "",
              f"- 执行状态：{_md(protocol.get('status'))}；时间边界：{_md(protocol.get('start_date'))} 至 {_md(protocol.get('end_date'))}",
              f"- 语言限制：{_md(protocol.get('languages'))}",
              f"- 纳入标准：{_md(protocol.get('inclusion_criteria'))}",
              f"- 排除标准：{_md(protocol.get('exclusion_criteria'))}", "",
              "前瞻性检索的 hit_count 始终为 undetermined，而不是 0；固定语料不冒充实时数据库命中。", "",
              "| 来源 | 数据库/接口 | 检索式 | 字段 | 覆盖/日期 | 实际命中 |", "|-|-|-|-|-|-|"]
    for source in protocol.get("sources") or []:
        count = source.get("hit_count") if source.get("hit_count") is not None else "undetermined"
        lines.append(f"| {_md(source.get('name'))} | {_md([source.get('database'), source.get('interface')])} | `{_md(source.get('query'))}` | {_md(source.get('fields'))} | {_md([source.get('coverage'), source.get('searched_at')])} | {count} |")
    lines += ["", "## 3. 相近工作逐项比较", "",
              "完整原文 quote、页/段定位、纳排理由和 P/A/M/U 来源核验级别见 evidence_matrix.csv。", "",
              "| 工作 | 最近工作及理由 | task | method | data | metric | conclusion | 可比性与不可比原因 |", "|-|-|-|-|-|-|-|-|"]
    for row in result.get("comparison_matrix") or []:
        aspects = []
        for aspect in E.ASPECTS:
            cell = row.get(aspect) or {}
            refs = ",".join(cell.get("evidence_ids") or [])
            aspects.append(f"{_md(cell.get('value'))} [{_md(refs)}]")
        lines.append(f"| {_md(row.get('title'))} ({_md(row.get('work_id'))}) | {_md([row.get('closest'), row.get('closest_reason')])} | "
                     + " | ".join(aspects)
                     + f" | {_md([row.get('comparable'), row.get('incomparable_reasons')])} |")
    lines += ["", "## 4. 创新碰撞、差异证据与反证", "",
              "直接先例、改名机制、代数/统计等价、常规适配、场景迁移、后续工作和强基线分别审计；资源条件不能抵消创新碰撞。", "",
              "| 创新点 | 类型 | 计算结论 | 有界解释 | 差异证据 |", "|-|-|-|-|-|"]
    for claim in result.get("novelty_assessment") or []:
        lines.append(f"| {_md(claim.get('statement'))} ({_md(claim.get('claim_id'))}) | {_md(claim.get('type'))} | {_md(claim.get('computed_status'))} | {_md(claim.get('bounded_conclusion'))} | {_md(claim.get('difference_evidence_refs'))} |")
        for comp in claim.get("nearest_comparisons") or []:
            lines.append(f"| ↳ 对照 {_md(comp.get('work_id'))} | {_md(comp.get('collision'))} | 同约束={_md(comp.get('same_constraints'))} | 剩余差异：{_md(comp.get('remaining_difference'))}；反证：{_md(comp.get('counterevidence_refs'))}；回应：{_md(comp.get('counterevidence_response'))} | {_md(comp.get('evidence_refs'))} |")
    lines += ["", "逐项机读碰撞与反证见 novelty_audit.csv。", "", "## 5. 可行性、影响与失败回退", ""]
    feasibility = result.get("feasibility_assessment") or {}
    lines += [f"- 可行性计算状态：**{_md(feasibility.get('computed_status'))}**", "",
              "| 前提 | 类别 | 要求 | 状态 | 来源定位 / 假设 | 验证与失败影响 |", "|-|-|-|-|-|-|"]
    for row in feasibility.get("prerequisites") or []:
        lines.append(f"| {_md(row.get('id'))} | {_md(row.get('category'))} | {_md(row.get('requirement'))} | {_md(row.get('status'))}{' / critical' if row.get('critical') else ''} | {_md([row.get('source'), row.get('locator'), row.get('assumption')])} | {_md([row.get('validation'), row.get('impact_if_false')])} |")
    lines += ["", "| 步骤 | 输入 | 输出 | 成本 | 风险 | 回退 |", "|-|-|-|-|-|-|"]
    for row in feasibility.get("route") or []:
        lines.append(f"| {_md(row.get('id'))} | {_md(row.get('input'))} | {_md(row.get('output'))} | {_md(row.get('cost'))} | {_md(row.get('risk'))} | {_md(row.get('fallback'))} |")
    impact = feasibility.get("impact") or {}
    lines += ["", f"- 科学影响：{_md(impact.get('scientific'))}", f"- 实际影响：{_md(impact.get('practical'))}", "",
              "## 6. 不确定性、研究空白与限制", ""]
    for row in result.get("uncertainties") or []:
        lines.append(f"- {_md(row.get('kind'))}：{_md(row.get('message'))}")
    for gap in result.get("research_gaps") or []:
        lines.append(f"- 研究空白/边界：{_md(gap)}")
    if result.get("findings"):
        lines += ["", "### 未解决审计发现", ""]
        for finding in result["findings"]:
            lines.append(f"- {finding['severity']} / {finding['rule']}：{_md(finding.get('message'))}")
    lines += ["", "## 7. 可复核产物", "",
              "- comparison_matrix.csv：每篇相近工作的五维字段、证据指针与不可比原因。",
              "- evidence_matrix.csv：逐字段原文 quote、精确 locator、来源、纳排理由与核验级别。",
              "- novelty_audit.csv：创新点×最近工作碰撞、剩余差异、反证与回应。",
              "- result.json：分级结论、所有证据表、原 case_id 与完整 output_contract 字段。", ""]
    return "\n".join(lines)


def _artifact(path: Path, kind: str) -> dict:
    return {"kind": kind, "path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_artifacts(result: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = out_dir / "comparison_matrix.csv"
    evidence_path = out_dir / "evidence_matrix.csv"
    novelty_path = out_dir / "novelty_audit.csv"
    report_path = out_dir / "topic_evaluation.md"
    matrix_rows = []
    for row in result.get("comparison_matrix") or []:
        flat = {key: value for key, value in row.items() if key not in E.ASPECTS}
        for aspect in E.ASPECTS:
            cell = row.get(aspect) or {}
            flat[aspect] = cell.get("value")
            flat[f"{aspect}_evidence_ids"] = cell.get("evidence_ids")
            flat[f"{aspect}_incomparable_reason"] = cell.get("incomparable_reason")
        matrix_rows.append(flat)
    _write_csv(matrix_path, matrix_rows,
               ["work_id", "title", "doi", "year", "decision", "include_exclude_reason",
                "closest", "closest_reason", "verification", "comparable", "incomparable_reasons"])
    _write_csv(evidence_path, result.get("evidence_matrix") or [],
               ["evidence_id", "work_id", "title", "doi", "year", "source", "decision",
                "include_exclude_reason", "verification", "aspect", "value", "quote", "locator"])
    novelty_rows = []
    for claim in result.get("novelty_assessment") or []:
        comparisons = claim.get("nearest_comparisons") or [{}]
        for comp in comparisons:
            novelty_rows.append({
                "claim_id": claim.get("claim_id"), "statement": claim.get("statement"),
                "type": claim.get("type"), "computed_status": claim.get("computed_status"),
                "bounded_conclusion": claim.get("bounded_conclusion"),
                "difference_evidence_refs": claim.get("difference_evidence_refs"),
                "work_id": comp.get("work_id"), "collision": comp.get("collision"),
                "same_constraints": comp.get("same_constraints"),
                "remaining_difference": comp.get("remaining_difference"),
                "evidence_refs": comp.get("evidence_refs"),
                "counterevidence_refs": comp.get("counterevidence_refs"),
                "counterevidence_response": comp.get("counterevidence_response"),
            })
    _write_csv(novelty_path, novelty_rows,
               ["claim_id", "statement", "type", "computed_status", "bounded_conclusion",
                "difference_evidence_refs", "work_id", "collision", "same_constraints",
                "remaining_difference", "evidence_refs", "counterevidence_refs", "counterevidence_response"])
    report_path.write_text(render_report(result), encoding="utf-8")
    result["evidence_matrix_file"] = str(evidence_path)
    result["research_product"] = {"report_path": str(report_path), "format": "markdown",
                                  "decision": result.get("decision"),
                                  "contains": ["question", "search", "comparison", "novelty", "feasibility", "uncertainty"]}
    result["deliverables"] = [str(report_path), str(matrix_path), str(evidence_path), str(novelty_path)]
    result["artifacts"] = [_artifact(report_path, "research_product"),
                           _artifact(matrix_path, "comparison_matrix"),
                           _artifact(evidence_path, "evidence_matrix"),
                           _artifact(novelty_path, "novelty_collision_audit")]
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
        if case_error:
            result.setdefault("limits", []).append(case_error)
        _write_result(Path(out_dir), result)
    except Exception as exc:
        return _refused(out_dir, f"topic engine boundary: {type(exc).__name__}: {exc}",
                        case, identity, case_error)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="topicrun", description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--case", help="original case.json; its case_id and output_contract are authoritative")
    parser.add_argument("--case-id", help="fallback identity when case.json is unavailable")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    result = build_and_audit(Path(args.spec), Path(args.out),
                             Path(args.case) if args.case else None, args.case_id)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "decision": (result.get("decision") or {}).get("grade"),
                      "findings": [row.get("rule") for row in result.get("findings", [])],
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Render the exact supplied research-plan spec into editable, linked deliverables."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def text(value, missing="[not supplied]"):
    if value is None or value == "" or value == [] or value == {}:
        return missing
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return "; ".join(text(x, "") for x in value) or missing
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def cell(value):
    return text(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("-" for _ in headers) + "|"]
    out += ["| " + " | ".join(cell(row.get(h)) for h in headers) + " |" for row in rows]
    return out


def _records(spec, key):
    value = spec.get(key) or []
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def write_research_plan(spec, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    elements = spec.get("elements") if isinstance(spec.get("elements"), dict) else {}
    objectives, route = _records(spec, "objectives"), _records(spec, "route")
    hypotheses, packages = _records(spec, "hypotheses"), _records(spec, "work_packages")
    schedule, risks = _records(spec, "schedule"), _records(spec, "risks")
    outcomes, claims = _records(spec, "outcomes"), _records(spec, "claims")
    refs = _records(spec, "references")
    data = spec.get("data_plan") if isinstance(spec.get("data_plan"), dict) else {}
    ethics = spec.get("ethics") if isinstance(spec.get("ethics"), dict) else {}
    title = text(spec.get("title"), "开题报告与研究计划书")
    L = ["# " + title, "", "- case_id: `" + text(spec.get("case_id")) + "`",
         "- editable source: generated verbatim from the supplied structured plan; no result or approval is fabricated", ""]

    background = elements.get("background") if isinstance(elements.get("background"), dict) else {}
    L += ["## 1. 研究背景与已知—未知—待验证缺口", "", text(background.get("text")), "",
          "**已知：** " + text(background.get("known")), "",
          "**未知：** " + text(background.get("unknown")), "",
          "**待验证：** " + text(background.get("to_test")), ""]
    problem = elements.get("problem") if isinstance(elements.get("problem"), dict) else {}
    L += ["## 2. 研究问题、边界与可证伪性", "", text(problem.get("text")), "",
          "**反证条件：** " + text(problem.get("falsification")), ""]

    L += ["## 3. 可考核目标与假设", "", text((elements.get("objectives") or {}).get("text") if isinstance(elements.get("objectives"), dict) else None), ""]
    L += table(["id", "metric", "sample", "control", "timepoint", "threshold", "threshold_basis"], objectives)
    L += ["", "### 假设与反证", ""]
    L += table(["id", "objective", "statement", "test", "null_result"], hypotheses)
    L += [""]

    L += ["## 4. 工作包与可执行方法", ""]
    L += table(["id", "title", "objectives", "route_steps", "method", "data", "deliverable", "acceptance"], packages)
    L += ["", "### 工作包里程碑", ""]
    L += table(["id", "start_month", "end_month", "owner"], packages)
    L += ["", "### 技术路线步骤", ""]
    L += table(["id", "objective", "input", "output", "depends_on", "method", "risk", "fallback"], route)
    L += ["", text((elements.get("technical_route") or {}).get("text") if isinstance(elements.get("technical_route"), dict) else None), ""]

    L += ["## 5. 数据与分析计划", ""]
    for key in ("sources", "collection_method", "quality_control", "analysis", "version", "access", "data_availability"):
        L += ["**%s：** %s" % (key, text(data.get(key))), ""]
    L += ["## 6. 阶段计划与里程碑", ""]
    L += table(["period", "start_month", "end_month", "deliverable", "milestone", "work_package", "on_critical_path"], schedule)
    L += ["", "- 给定总周期（月）：" + text(spec.get("period_months")),
          "- 资源预算：" + text(spec.get("resource_budget")),
          "- 计划资源需求：" + text(spec.get("resource_needed")),
          "- 关键路线说明：" + text(spec.get("critical_path_note")), ""]

    L += ["## 7. 风险、触发信号与备选方案", ""]
    L += table(["id", "type", "trigger", "impact", "fallback", "decision_point"], risks)
    L += ["", "## 8. 伦理、合规与数据边界", "", "**是否涉及需伦理审查的对象或数据：** " + text(ethics.get("applicable")), "",
          "**判断依据：** " + text(ethics.get("scope_explanation")), ""]
    if ethics.get("applicable") is True:
        for key in ("approval_status", "consent", "privacy", "data_retention", "oversight"):
            L += ["**%s：** %s" % (key, text(ethics.get(key))), ""]
    L += ["## 9. 可验证预期成果", ""]
    L += table(["id", "kind", "objectives", "deliverable", "assessment"], outcomes)
    L += ["", text((elements.get("outcomes") or {}).get("text") if isinstance(elements.get("outcomes"), dict) else None), ""]

    L += ["## 10. 论断—材料—版本映射", ""]
    L += table(["text", "material", "reference", "version"], claims)
    L += ["", "### 文献与输入材料", ""]
    for r in refs:
        L += ["- `%s`：%s（%s）" % (text(r.get("key")), text(r.get("title")), text(r.get("year")))]
    L += ["", "## 11. 边界与待确认项", ""]
    limits = spec.get("limits") or spec.get("uncertainty") or []
    if isinstance(limits, str):
        limits = [limits]
    L += ["- " + text(x) for x in limits] or ["- 见 result.json；未声明的审批、数据访问或结论未由生成器补造。"]
    md = "\n".join(L) + "\n"
    (out / "research_plan.md").write_text(md, encoding="utf-8")

    objective_map = []
    for o in objectives:
        oid = text(o.get("id"), "")
        objective_map.append({
            "objective": oid,
            "hypotheses": [text(h.get("id"), "") for h in hypotheses if text(h.get("objective"), "") == oid],
            "route_steps": [text(r.get("id"), "") for r in route if text(r.get("objective"), "") == oid],
            "work_packages": [text(w.get("id"), "") for w in packages if oid in [text(x, "") for x in (w.get("objectives") or [])]],
            "outcomes": [text(w.get("id"), "") for w in outcomes if oid in [text(x, "") for x in (w.get("objectives") or [])]],
        })
    matrix = {"schema_version": "research-plan-matrix/v1", "case_id": spec.get("case_id"),
              "objective_links": objective_map, "work_packages": packages,
              "data_plan": data, "ethics": ethics,
              "coverage": {"objectives": len(objectives), "hypotheses": len(hypotheses),
                           "work_packages": len(packages), "route_steps": len(route),
                           "milestones": len(schedule), "risks": len(risks), "outcomes": len(outcomes),
                           "falsifiable_objectives": sum(bool(x["hypotheses"]) for x in objective_map)}}
    (out / "plan_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (out / "evidence_matrix.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["claim", "material_id", "reference_key", "version", "source_localized"])
        for c in claims:
            writer.writerow([text(c.get("text"), ""), text(c.get("material"), ""), text(c.get("reference"), ""),
                             text(c.get("version"), ""), bool(c.get("material") or c.get("reference"))])
    return {"research_plan.md": {"kind": "editable_markdown", "bytes": len(md.encode("utf-8"))},
            "plan_matrix.json": {"kind": "objective_workpackage_evidence_graph"},
            "evidence_matrix.csv": {"kind": "source_version_map", "claims": len(claims)}}

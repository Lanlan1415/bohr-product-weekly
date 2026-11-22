"""Benchmark for the research-topic evaluation skill.

One scenario per rule, aligned to the scoring points this task states:

  a testable question definition            -> question_too_broad (EN and pure-ZH),
                                               element_no_text
  comparison against the closest prior work -> element_no_evidence, paragraph_no_element,
                                               paragraph_no_evidence,
                                               paragraph_element_unknown
  a comparison matrix with incomparable     -> comparison_missing, comparison_row_no_work,
  reasons stated                               comparison_no_aspect,
                                               comparison_aspect_unknown,
                                               comparability_unstated,
                                               incomparable_without_reason,
                                               comparison_no_evidence,
                                               comparison_row_skipped,
                                               comparison_row_id_duplicate
  innovation claims with a boundary         -> field_too_thin
  feasibility checked, not asserted         -> objectives_missing, aim_without_measure,
                                               aim_without_outcome, objective_unmapped,
                                               objective_content_unknown, objective_no_route,
                                               route_no_io, route_no_risk, route_no_fallback,
                                               milestone_missing, budget_unjustified,
                                               budget_line_unjustified
  prior-work status and foundation chain    -> status_unlabelled, foundation_no_capability,
                                               foundation_no_evidence, foundation_no_relation

    python bench_topic.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

RATIONALE = ("现有综述与对比实验止步于 2022 年，此后扩散式采样器在新材料体系上的表现缺少与"
             "最强经典基线在同一语料、同一切分下的对照；选题评估以最近两年的工作为比较基线，"
             "并把语料冻结列为第一项工作。")
INNOVATION = ("与已有工作只报告端到端精度不同，本评估把比较锚定在同一语料、同一切分与同一"
              "算力预算下，公布每个基线的复现误差，并把创新点逐条对照到具体文献的具体段落，"
              "使新与旧的边界可以被第三方复核。")

BASE = {
    "elements": {
        "rationale": {"text": RATIONALE, "evidence": "M1 语料覆盖记录"},
        "question": {"text": "扩散式采样器在同一基准上是否比最强经典基线的覆盖率高至少 5 个百分点",
                     "evidence": "M1"},
        "objectives": {"text": "三项可检验目标：覆盖率、复现误差、语料覆盖", "evidence": "Sec 2"},
        "content": {"text": "冻结语料并复现三个已有基线，再对照评测新采样器", "evidence": "M2"},
        "innovation": {"text": INNOVATION, "evidence": "[doe2020]"},
        "technical_route": {"text": "三步：语料冻结、基线复现、对照评测，每步带风险与回退",
                            "evidence": "Sec 4"},
        "foundation": {"text": "实验室语料库与已有算力平台", "evidence": "M0"},
    },
    "paragraphs": [{"text": "为什么现在评估这个选题", "element": "rationale", "evidence": "M1"}],
    "objectives": [{"id": "O1", "measure": "同一基准上的覆盖率对比",
                    "outcome": "至少高出 5 个百分点", "content_ref": "C1"}],
    "content": [{"id": "C1", "text": "冻结语料并复现基线"}],
    "route": [{"id": "R1", "objective": "O1", "input": "2018-2024 标注语料",
               "output": "基线复现报告", "risk": "基线复现偏差",
               "fallback": "改用原作者公开检查点"}],
    "foundation_items": [{"name": "实验室语料库", "capability": "已收录 3,200 篇标注文献",
                          "evidence": "M0 run 2023-04",
                          "relation": "同一语料库支撑本次评估的检索范围", "status": "done"}],
    "timeline": [{"period": "Y1", "milestone": "基线复现通过容忍度检查"}],
    "budget": [{"item": "算力", "justification": "600 GPU 小时，按现有平台报价"}],
    "budget_justification": "每项按现有供应商报价与设备清单核算",
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def el(name, **over):
    s = copy.deepcopy(BASE)
    s["elements"] = copy.deepcopy(BASE["elements"])
    s["elements"][name] = {**BASE["elements"][name], **over}
    return s


def fnd(**over):
    s = copy.deepcopy(BASE)
    s["foundation_items"] = [dict(BASE["foundation_items"][0], **over)]
    return s


def obj(**over):
    s = copy.deepcopy(BASE)
    s["objectives"] = [dict(BASE["objectives"][0], **over)]
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # the seven elements of an evaluation
    ("element_missing",
     lambda: (d(elements={k: v for k, v in BASE["elements"].items() if k != "innovation"}),
              ["prop.element_missing"])),
    ("element_no_text", lambda: (el("question", text=""), ["prop.element_no_text"])),
    ("element_no_evidence", lambda: (el("rationale", evidence=""), ["prop.element_no_evidence"])),

    # paragraph -> element -> evidence
    ("paragraph_no_element",
     lambda: (d(paragraphs=[{"text": "为什么现在评估这个选题", "evidence": "M1"}]),
              ["prop.paragraph_no_element"])),
    ("paragraph_element_unknown",
     lambda: (d(paragraphs=[{"text": "为什么现在评估这个选题", "element": "novelty",
                             "evidence": "M1"}]),
              ["prop.paragraph_element_unknown"])),
    ("paragraph_no_evidence",
     lambda: (d(paragraphs=[{"text": "为什么现在评估这个选题", "element": "rationale"}]),
              ["prop.paragraph_no_evidence"])),

    # prior-work status and the capability-evidence-relation chain
    ("status_unlabelled", lambda: (fnd(status=""), ["prop.status_unlabelled"])),
    ("foundation_no_capability", lambda: (fnd(capability=""), ["prop.foundation_no_capability"])),
    ("foundation_no_evidence", lambda: (fnd(evidence=""), ["prop.foundation_no_evidence"])),
    ("foundation_no_relation", lambda: (fnd(relation=""), ["prop.foundation_no_relation"])),

    # the question must be bounded to be testable. Chinese broad qualifiers fire on their
    # own now: a CJK ideograph is a word character in Python's re, so the old single \b
    # pattern could never match inside a pure-Chinese question. The English fixture is kept
    # as the mixed-language regression.
    ("question_too_broad",
     lambda: (el("question", text="对扩散式采样器做一次 comprehensive 评估，"
                                  "覆盖 every 材料体系与全部指标"),
              ["prop.question_too_broad"])),
    ("question_too_broad_zh_full",
     lambda: (el("question", text="对扩散模型在蛋白质设计中的应用进行全面评估"),
              ["prop.question_too_broad"])),
    ("question_too_broad_zh_all",
     lambda: (el("question", text="所有情况下纳米颗粒的毒性是否更高"),
              ["prop.question_too_broad"])),
    ("question_too_broad_zh_systematic",
     lambda: (el("question", text="系统研究该类催化剂活性来源的决定因素"),
              ["prop.question_too_broad"])),
    ("question_bounded_zh_clean",
     lambda: (el("question", text="扩散式采样器在同一基准上是否比最强经典基线的覆盖率"
                                  "高至少 5 个百分点"),
              [])),

    # objectives: assessable and mapped
    ("objectives_missing", lambda: (d(objectives=[]), ["prop.objectives_missing"])),
    ("aim_without_measure",
     lambda: (obj(measure=""), ["prop.aim_without_measure"])),
    ("aim_without_outcome",
     lambda: (obj(outcome=""), ["prop.aim_without_outcome"])),
    ("objective_unmapped",
     lambda: (obj(content_ref=""), ["prop.objective_unmapped"])),
    ("objective_content_unknown",
     lambda: (obj(content_ref="C9"), ["prop.objective_content_unknown"])),
    ("objective_no_route",
     lambda: (d(objectives=[{"id": "O2", "measure": "复现误差对比", "outcome": "误差小于 1e-3",
                             "content_ref": "C1"}]),
              ["prop.objective_no_route"])),

    # the route must be executable, not a method list
    ("route_no_io",
     lambda: (d(route=[{k: v for k, v in BASE["route"][0].items()
                        if k not in ("input", "output")}]), ["prop.route_no_io"])),
    ("route_no_risk",
     lambda: (d(route=[{k: v for k, v in BASE["route"][0].items() if k != "risk"}]),
              ["prop.route_no_risk"])),
    ("route_no_fallback",
     lambda: (d(route=[{k: v for k, v in BASE["route"][0].items() if k != "fallback"}]),
              ["prop.route_no_fallback"])),

    # schedule and budget
    ("milestone_missing",
     lambda: (d(timeline=[{"period": "Y1"}]), ["prop.milestone_missing"])),
    ("budget_unjustified", lambda: (d(budget_justification=""), ["prop.budget_unjustified"])),
    ("budget_line_unjustified",
     lambda: (d(budget=[{"item": "算力"}]), ["prop.budget_line_unjustified"])),

    # an innovation claim too thin to carry a boundary
    ("field_too_thin", lambda: (el("innovation", text="Novel."), ["prop.field_too_thin"])),

    # --- the comparison matrix: aspect rows with incomparable reasons -----
    ("comparison_matrix_missing",
     lambda: (d(comparison_required=True), ["prop.comparison_missing"])),
    ("comparison_no_work",
     lambda: (d(comparison_matrix=[{"id": "M1", "aspect": "metric", "comparable": True,
                                    "evidence": "[doe2020] Table 2, p.6"}]),
              ["prop.comparison_row_no_work"])),
    ("comparison_no_aspect",
     lambda: (d(comparison_matrix=[{"id": "M1", "work": "doe2020", "comparable": True,
                                    "evidence": "[doe2020] Table 2, p.6"}]),
              ["prop.comparison_no_aspect"])),
    ("comparison_aspect_unknown",
     lambda: (d(comparison_matrix=[{"id": "M1", "work": "doe2020", "aspect": "speed",
                                    "comparable": True,
                                    "evidence": "[doe2020] Table 2, p.6"}]),
              ["prop.comparison_aspect_unknown"])),
    ("comparison_comparability_unstated",
     lambda: (d(comparison_matrix=[{"id": "M1", "work": "doe2020", "aspect": "metric",
                                    "evidence": "[doe2020] Table 2, p.6"}]),
              ["prop.comparability_unstated"])),
    ("comparison_incomparable_no_reason",
     lambda: (d(comparison_matrix=[{"id": "M1", "work": "doe2020", "aspect": "conclusion",
                                    "comparable": False,
                                    "evidence": "[doe2020] Sec 5"}]),
              ["prop.incomparable_without_reason"])),
    ("comparison_incomparable_reason_ok",
     lambda: (d(comparison_matrix=[
         {"id": "M1", "work": "doe2020", "aspect": "conclusion", "comparable": False,
          "reason": "评价指标不同（F1 对覆盖率），数值无法对齐",
          "evidence": "[doe2020] Sec 5"}]),
              [])),
    ("comparison_no_evidence",
     lambda: (d(comparison_matrix=[{"id": "M1", "work": "doe2020", "aspect": "data",
                                    "comparable": True}]),
              ["prop.comparison_no_evidence"])),
    ("comparison_matrix_clean",
     lambda: (d(comparison_required=True, comparison_matrix=[
         {"id": "M1", "work": "doe2020", "aspect": "method", "comparable": True,
          "evidence": "[doe2020] Sec 3, p.4"},
         {"id": "M2", "work": "roe2021", "aspect": "metric", "comparable": False,
          "reason": "评价指标不同（F1 对覆盖率），数值无法对齐",
          "evidence": "[roe2021] Table 1, p.5"}]),
              [])),
    ("comparison_row_skipped",
     lambda: (d(comparison_matrix=["a bare string row", 42,
                                   {"id": "M1", "work": "doe2020", "aspect": "method",
                                    "comparable": True, "evidence": "[doe2020] Sec 3"}]),
              ["prop.comparison_row_skipped"])),
    ("comparison_row_id_duplicate",
     lambda: (d(comparison_matrix=[
         {"id": "M1", "work": "doe2020", "aspect": "method", "comparable": True,
          "evidence": "[doe2020] Sec 3, p.4"},
         {"id": "M1", "work": "roe2021", "aspect": "data", "comparable": True,
          "evidence": "[roe2021] p.2"}]),
              ["prop.comparison_row_id_duplicate"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "proposal")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "topic-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the topic-evaluation scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_topic.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

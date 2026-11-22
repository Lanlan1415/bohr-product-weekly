"""Benchmark for the research trend-analysis skill.

One scenario per rule, aligned to the scoring points this task states:

  both halves of the deliverable           -> results_missing, discussion_missing
  trend claims backed by the time-slice table -> value_not_in_figures,
                                              errorbar_meaning_undeclared
  stage/period comparisons judged, not implied -> statistic_missing, comparison_no_verdict,
                                              non_significant_claimed_as_effect
  description kept apart from interpretation -> interpretation_in_results,
                                              mechanism_as_fact, causal_overreach
  every trend conclusion attributable       -> discussion_uncited
  honesty about flat periods and conflicting sources -> negative_result_omitted,
                                              conflicting_literature_ignored, limitation_*
  numbers carry their口径 (unit)             -> unitless_number

    python bench_trend.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

FIG_VALUES = ["2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025",
              "12", "18", "30", "48", "87", "34", "45", "52", "4"]

BASE = {
    "design": "observational",
    "results_text": ("该主题的年发文量自 2018 年的 12 篇升至 2024 年的 48 篇，四年间增至 4 倍。"
                     "2021 年出现第一个峰值（占比 34%），2024 年占比达 45%。"
                     "Transformer 子主题自 2023 年起占比过半（52%）。"
                     "2025 年回落段未达到显著（P = 0.21，卡方检验）。"),
    "discussion_text": ("时间趋势显示该主题处于扩张期 [doe2020]。"
                        "2021 年前后的主题合并与图方法引入在时间上重合，可能与图神经网络的可用性有关 "
                        "[doe2020]。阶段划分与上述结果一致：2018-2020 起步段、2021-2024 扩张段。"
                        "2025 年回落段未达到显著，不宜解读为拐点。"
                        "Roe 报告了不一致的结果 [roe2021]，其检索窗口仅覆盖 2020 年之前。"),
    "figures": [{"id": "表1 时间切片统计", "values": FIG_VALUES,
                 "has_errorbar": True, "errorbar": "95% CI"}],
    "comparisons": [
        {"name": "2021-2024 扩张段 vs 2018-2020 起步段", "significant": True,
         "strength": "moderate"},
        {"name": "2025 年回落段", "significant": False},
    ],
    "literature": [{"key": "doe2020", "agrees": True},
                   {"key": "roe2021", "agrees": False,
                    "finding": "the rise starts before 2020 in their window"}],
    "limitations": [
        {"level": "method", "text": "仅检索两个数据库，预印本与会议论文未系统纳入"},
        {"level": "measurement", "text": "主题归属按关键词自动标注，未做人工复核"},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def results_keep_s1_3(s4: str) -> str:
    """Replace only the last results sentence (the 2025 verdict)."""
    head = ("该主题的年发文量自 2018 年的 12 篇升至 2024 年的 48 篇，四年间增至 4 倍。"
            "2021 年出现第一个峰值（占比 34%），2024 年占比达 45%。"
            "Transformer 子主题自 2023 年起占比过半（52%）。")
    return head + s4


SCEN = [
    ("clean", lambda: (d(), [])),

    # the two halves
    ("results_missing", lambda: (d(results_text=""), ["rd.results_missing"])),
    ("discussion_missing", lambda: (d(discussion_text=""), ["rd.discussion_missing"])),

    # trend numbers must trace to the time-slice table: a bare count is exempt (it is a
    # count, not a plotted value), but a percentage must appear in the table
    ("value_not_in_figures",
     lambda: (d(results_text=results_keep_s1_3(
         "2025 年回落段未达到显著（P = 0.21）。").replace("占比达 45%",
                                                      "占比达 63%")),
              ["rd.value_not_in_figures"])),
    ("errorbar_undeclared",
     lambda: (d(figures=[{"id": "表1 时间切片统计", "values": FIG_VALUES,
                          "has_errorbar": True}]),
              ["rd.errorbar_meaning_undeclared"])),

    # period comparisons
    ("statistic_missing",
     lambda: (d(results_text=results_keep_s1_3("2025 年回落段未达到显著。")),
              ["rd.statistic_missing"])),
    ("comparison_no_verdict",
     lambda: (d(comparisons=[{"name": "2021-2024 扩张段 vs 2018-2020 起步段"},
                             {"name": "2025 年回落段", "significant": False}]),
              ["rd.comparison_no_verdict"])),
    ("nonsig_as_effect",
     lambda: (d(results_text=results_keep_s1_3("2025 年回落段发文增加（P = 0.21）。")),
              ["rd.non_significant_claimed_as_effect"])),

    # description vs interpretation
    ("interpretation_in_results",
     lambda: (d(results_text=results_keep_s1_3("该拐点是因为预训练模型的普及。")),
              ["rd.interpretation_in_results"])),
    ("mechanism_as_fact",
     lambda: (d(discussion_text="主题演化的机制是扩散模型取代了 GAN。"),
              ["rd.mechanism_as_fact"])),
    ("causal_overreach",
     lambda: (d(discussion_text="预训练模型的可用性导致了 2021 年的主题合并。"),
              ["rd.causal_overreach"])),

    # attribution: an asserting sentence with neither a key nor a data pointer. The
    # phrasing avoids 图/表/式, which read as pointers at this analysis's own data.
    ("discussion_uncited",
     lambda: (d(discussion_text="该阶段划分提示主题已进入平台期。"),
              ["rd.discussion_uncited"])),

    # honesty about what the corpus does not show
    ("negative_omitted",
     lambda: (d(discussion_text="时间趋势显示该主题处于扩张期 [doe2020]。"
                                "2021 年前后的主题合并与图方法引入在时间上重合，可能与图神经网络的"
                                "可用性有关 [doe2020]。"
                                "Roe 报告了不一致的结果 [roe2021]，其检索窗口仅覆盖 2020 年之前。"),
              ["rd.negative_result_omitted"])),
    ("conflict_ignored",
     lambda: (d(discussion_text="时间趋势显示该主题处于扩张期 [doe2020]。"
                                "2021 年前后的主题合并与图方法引入在时间上重合，可能与图神经网络的"
                                "可用性有关 [doe2020]。阶段划分与上述结果一致：2018-2020 起步段、"
                                "2021-2024 扩张段。2025 年回落段未达到显著，不宜解读为拐点。"),
              ["rd.conflicting_literature_ignored"])),

    # limitations
    ("limitations_missing", lambda: (d(limitations=[]), ["rd.limitations_missing"])),
    ("limitation_vague",
     lambda: (d(limitations=[{"level": "method",
                              "text": "further work is needed to broaden corpus coverage"},
                             {"level": "sample", "text": "仅覆盖一个学科"}]),
              ["rd.limitation_vague"])),
    ("limitation_narrow",
     lambda: (d(limitations=[{"level": "sample", "text": "仅覆盖一个学科"},
                             {"level": "sample", "text": "样本以英文文献为主"}]),
              ["rd.limitation_level_narrow"])),

    # 口径: a bare count with no unit or ratio reads as ambiguous
    ("unitless_number",
     lambda: (d(results_text="共筛出 451 篇候选文献。"), ["rd.unitless_number"])),

    # overclaim without strength labels
    ("overclaim",
     lambda: (d(results_text="该趋势必然持续三年以上。",
                comparisons=[{"name": "2021-2024 扩张段 vs 2018-2020 起步段",
                              "significant": True},
                             {"name": "2025 年回落段", "significant": False}]),
              ["rd.overclaim"])),

    # --- false-positive guards: standard trend-analysis prose must stay clean ---
    # a pointer at 表 1 is a data reference, not an unattributed claim
    ("pointer_and_pvalue_clean",
     lambda: (d(results_text="表 1 显示三倍增长（P < 0.001）。"), [])),
    # P, t(df), n, R² are statistics, not plotted quantities
    ("stats_exempt",
     lambda: (d(results_text="趋势检验显著（P < 0.001，t(23) = 3.2，n = 87，R² = 0.87）。"), [])),
    ("chinese_stats_clean",
     lambda: (d(results_text="扩张段显著高于起步段（P<0.05，t检验）。2025 年回落段无显著变化。",
                comparisons=[{"name": "扩张段 vs 起步段", "significant": True,
                              "strength": "strong"},
                             {"name": "2025 年回落段", "significant": False}]), [])),
    # "通过卡方检验比较" states a method, not a mechanism
    ("method_via_clean",
     lambda: (d(results_text="扩张段与起步段通过卡方检验比较（P<0.05）。2025 年回落段无显著变化。",
                comparisons=[{"name": "扩张段 vs 起步段", "significant": True,
                              "strength": "strong"},
                             {"name": "2025 年回落段", "significant": False}]), [])),
    # a sentence pointing at this analysis's own table is attributed without a key; the
    # negative period and the conflicting source are removed from this scenario so the
    # attribution guard is exercised alone
    ("data_ref_attributed",
     lambda: (d(discussion_text="这一峰值与图 2 的年度分布一致。",
                comparisons=[{"name": "2021-2024 扩张段 vs 2018-2020 起步段",
                              "significant": True, "strength": "moderate"}],
                literature=[{"key": "doe2020", "agrees": True}]), [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "results_discussion")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "trend-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the trend-analysis scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_trend.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

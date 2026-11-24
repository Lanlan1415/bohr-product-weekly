"""Benchmark for the review-response skill.

One scenario per rule, aligned to the scoring points this task states:

  every comment answered, sub-requirements covered  -> comment_unanswered,
                                                        subrequirement_unanswered
  a response letter and a manuscript delivered       -> no_letter, no_manuscript
  "we have changed it" matching the file             -> change_not_verifiable
  every location checkable in the stated version     -> locator_not_in_manuscript,
                                                        version_mismatch
  decision and tone carried explicitly               -> decision_*, tone_*
  "accepted" backed by an action or a reason         -> accept_without_change
  tone and decision telling the same story           -> tone_decision_mismatch
  every change stamps the version it refers to       -> change_version_missing
  a comment with no text cannot be judged            -> comment_text_missing
  evidence promised, with its state and alternative  -> evidence_*
  provided evidence names its data source            -> evidence_source_missing
  the claimed edits land in the declared baseline    -> manuscript_unrevised

Each defect scenario is paired with a false-positive guard: a correct package of
the same shape must report nothing (split answers, sourced evidence, a revised
manuscript, an all-rebuttal letter that touches nothing).

    python bench_review.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402

BASE = {
    "manuscript_version": "v2",
    "manuscript_text": "3.2 Results\nWe added a vehicle control (n=6).\n",
    "anchors": ["3.2 Results", "Appendix A"],
    "comments": [
        {"id": "C1", "text": "Add a vehicle control.", "type": "method", "severity": "major",
         "subrequirements": []},
        {"id": "C2", "text": "Justify the kinetic model.", "type": "method", "severity": "major",
         "subrequirements": []},
    ],
    "responses": [
        {"comment_id": "C1", "decision": "accept", "tone": "accept",
         "changes": [{"what": "added a vehicle control group", "location": "3.2 Results",
                      "manuscript_version": "v2",
                      "added_text": "We added a vehicle control"}]},
        {"comment_id": "C2", "decision": "accept", "tone": "accept",
         "changes": [{"what": "added a derivation appendix", "location": "Appendix A",
                      "manuscript_version": "v2"}]},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def resp(index, **over):
    s = copy.deepcopy(BASE)
    s["responses"] = copy.deepcopy(BASE["responses"])
    s["responses"][index] = dict(BASE["responses"][index], **over)
    return s


def change(index, **over):
    s = copy.deepcopy(BASE)
    s["responses"] = copy.deepcopy(BASE["responses"])
    s["responses"][index]["changes"] = [dict(BASE["responses"][index]["changes"][0], **over)]
    return s


def comment(index, **over):
    s = copy.deepcopy(BASE)
    s["comments"] = copy.deepcopy(BASE["comments"])
    s["comments"][index] = dict(BASE["comments"][index], **over)
    return s


def linked():
    """Point -> Response -> uniquely identified before/after change."""
    s = d(baseline_text="3.2 Results\nBaseline summary without the control group.\n")
    s["responses"] = copy.deepcopy(BASE["responses"])
    s["responses"][0].update({
        "text": "Response to Point C1: We have added the control details to the results."})
    s["responses"][0]["changes"][0].update({
        "change_id": "C1-CH1",
        "response_anchor": "Response to Point C1",
        "before_text": "Baseline summary without the control group.",
        "added_text": "We added a vehicle control (n=6)."})
    s["responses"][1]["text"] = "Response to Point C2: The derivation is now explicit."
    s["responses"][1]["changes"][0].update({
        "change_id": "C2-CH1", "response_anchor": "Response to Point C2"})
    return s


def linked_with(mutator):
    s = linked()
    mutator(s)
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # the package
    ("no_comments", lambda: (d(comments=[]), ["resp.no_comments"])),
    ("no_letter", lambda: (d(responses=[]), ["resp.no_letter"])),
    ("no_manuscript", lambda: (d(manuscript_text=""), ["resp.no_manuscript"])),

    # decomposition
    ("comment_type_missing", lambda: (comment(0, type=""), ["resp.comment_type_missing"])),
    ("severity_missing", lambda: (comment(0, severity=""), ["resp.severity_missing"])),
    ("subrequirement_unanswered",
     lambda: (comment(0, subrequirements=["add a vehicle control",
                                          "report the n for each arm"]),
              ["resp.subrequirement_unanswered"])),
    # FP guard: the same multi-part comment answered across two entries that
    # share its id is complete coverage, not a dropped sub-request.
    ("subrequirement_split_guard",
     lambda: (d(comments=[{"id": "C1", "text": "Add a vehicle control and report n per arm.",
                           "type": "method", "severity": "major",
                           "subrequirements": ["add a vehicle control",
                                               "report the n for each arm"]},
                          BASE["comments"][1]],
                responses=[BASE["responses"][0],
                           {"comment_id": "C1", "decision": "accept", "tone": "accept",
                            "reason": "the n for each arm is now reported",
                            "changes": [{"what": "reports the n for each arm in the caption",
                                         "location": "3.2 Results",
                                         "manuscript_version": "v2"}]},
                           BASE["responses"][1]]),
              [])),

    # CJK coverage (the fixed case ships Chinese materials): a Chinese
    # sub-request is judged against shared characters with the response body.
    # A fully Chinese package must audit clean when the answers are real.
    ("subrequirement_cjk_covered",
     lambda: (d(manuscript_text="3.2 结果\n我们补充了对照组（n=6）。\n附录 A\n模型推导见附录。\n",
                anchors=["3.2 结果", "附录 A"],
                comments=[{"id": "C1", "text": "请补充对照组并给出每组样本量。",
                           "type": "method", "severity": "major",
                           "subrequirements": ["补充对照组", "给出每组样本量"]},
                          {"id": "C2", "text": "动力学模型需要论证。",
                           "type": "method", "severity": "major", "subrequirements": []}],
                responses=[{"comment_id": "C1", "decision": "accept", "tone": "accept",
                            "changes": [{"what": "我们补充了对照组（每组 n=6）",
                                         "location": "3.2 结果",
                                         "manuscript_version": "v2",
                                         "added_text": "我们补充了对照组（n=6）"}]},
                           {"comment_id": "C2", "decision": "accept", "tone": "clarify",
                            "changes": [{"what": "模型推导见附录 A",
                                         "location": "附录 A",
                                         "manuscript_version": "v2"}]}]),
              [])),
    ("subrequirement_cjk_missed",
     lambda: (d(manuscript_text="3.2 结果\n我们补充了对照组（n=6）。\n",
                anchors=["3.2 结果"],
                comments=[{"id": "C1", "text": "请补充对照组并给出每组样本量。",
                           "type": "method", "severity": "major",
                           "subrequirements": ["补充对照组", "给出每组样本量"]},
                          BASE["comments"][1]],
                responses=[{"comment_id": "C1", "decision": "accept", "tone": "accept",
                            "changes": [{"what": "我们改写了这一段的表述使其更通顺",
                                         "location": "3.2 结果",
                                         "manuscript_version": "v2"}]},
                           BASE["responses"][1]]),
              ["resp.subrequirement_unanswered"])),

    # coverage and decision
    ("comment_unanswered", lambda: (d(responses=BASE["responses"][:1]),
                                    ["resp.comment_unanswered"])),
    ("response_orphaned",
     lambda: (resp(1, comment_id="C9"), ["resp.response_orphaned"])),
    ("decision_undeclared", lambda: (resp(0, decision=""), ["resp.decision_undeclared"])),
    ("decision_invalid", lambda: (resp(0, decision="maybe"), ["resp.decision_invalid"])),
    ("rebuttal_without_reason",
     lambda: (resp(0, decision="reject", reason=""), ["resp.rebuttal_without_reason"])),
    ("tone_missing", lambda: (resp(0, tone=""), ["resp.tone_missing"])),
    ("tone_invalid", lambda: (resp(0, tone="angry"), ["resp.tone_invalid"])),

    # "accepted" must be backed by an action or a reason (逐条回应: 空话拦截)
    ("accept_without_change",
     lambda: (resp(0, changes=[]), ["resp.accept_without_change"])),
    # FP guard: the same acceptance with a written-out justification is a record
    ("accept_with_reason_guard",
     lambda: (resp(0, changes=[],
                   reason="the manuscript already reports the vehicle control in 3.2; no "
                          "file change was needed"), [])),

    # tone and decision must tell the same story (语气控制)
    ("tone_decision_mismatch",
     lambda: (resp(0, decision="reject", tone="accept",
                   reason="the control condition is confounded by the batch effect"),
              ["resp.tone_decision_mismatch"])),
    # FP guard: a rejection in a polite-rebuttal tone is the aligned pair
    ("tone_aligned_guard",
     lambda: (resp(0, decision="reject", tone="polite_rebuttal",
                   reason="the control condition is confounded by the batch effect"), [])),

    # every change stamps the version it refers to (对得上: 版本一致性)
    ("change_version_missing",
     lambda: (change(0, manuscript_version=""), ["resp.change_version_missing"])),
    # FP guard: all change entries stamped (the clean baseline covers this too)

    # a comment with no text cannot be answered verifiably (意见拆解)
    ("comment_text_missing", lambda: (comment(0, text=""), ["resp.comment_text_missing"])),

    # the claim against the file
    ("change_unspecified", lambda: (change(0, what=""), ["resp.change_unspecified"])),
    ("change_unlocatable", lambda: (change(0, location=""), ["resp.change_unlocatable"])),
    ("locator_not_in_manuscript",
     lambda: (change(0, location="4.7 Conclusions"),
              ["resp.locator_not_in_manuscript"])),
    ("version_mismatch", lambda: (change(0, manuscript_version="v1"),
                                  ["resp.version_mismatch"])),
    ("change_not_verifiable",
     lambda: (change(0, added_text="We added two blinded readers"),
              ["resp.change_not_verifiable"])),

    # promised evidence
    ("evidence_status_missing",
     lambda: (resp(0, evidence=[{"kind": "additional experiment"}]),
              ["resp.evidence_status_missing"])),
    # A malformed (bare-string) evidence entry degrades to a status finding
    # instead of crashing the audit.
    ("evidence_bare_string_degrades",
     lambda: (resp(0, evidence=["additional experiment"]),
              ["resp.evidence_status_missing"])),
    ("evidence_without_alternative",
     lambda: (resp(0, evidence=[{"kind": "additional experiment", "status": "unavailable"}]),
              ["resp.evidence_without_alternative"])),
    ("evidence_source_missing",
     lambda: (resp(0, evidence=[{"kind": "additional data", "status": "provided"}]),
              ["resp.evidence_source_missing"])),
    # FP guard: the same entry carrying its data source stays silent.
    ("evidence_source_guard",
     lambda: (resp(0, evidence=[{"kind": "additional data", "status": "provided",
                                 "source": "Table S2, n=6 per arm, raw values in the "
                                 "supplement"}]),
              [])),
    ("evidence_added_clean",
     lambda: (resp(0, evidence=[{"kind": "additional data", "status": "provided",
                                 "source": "Table S2, n=6 per arm",
                                 "added_to_manuscript": True, "manuscript_version": "v2",
                                 "location": "We added a vehicle control"}]), [])),
    ("evidence_version_mismatch",
     lambda: (resp(0, evidence=[{"kind": "additional data", "status": "provided",
                                 "source": "Table S2", "manuscript_version": "v1"}]),
              ["resp.evidence_version_mismatch"])),
    ("evidence_version_missing",
     lambda: (resp(0, evidence=[{"kind": "additional data", "status": "provided",
                                 "source": "Table S2", "added_to_manuscript": True,
                                 "location": "We added a vehicle control"}]),
              ["resp.evidence_version_missing"])),
    ("evidence_locator_missing",
     lambda: (resp(0, evidence=[{"kind": "additional data", "status": "provided",
                                 "source": "Table S2", "added_to_manuscript": True,
                                 "manuscript_version": "v2"}]),
              ["resp.evidence_locator_missing"])),
    ("evidence_locator_not_found",
     lambda: (resp(0, evidence=[{"kind": "additional data", "status": "provided",
                                 "source": "Table S2", "added_to_manuscript": True,
                                 "manuscript_version": "v2", "location": "Appendix Z"}]),
              ["resp.evidence_locator_not_found"])),

    # the claimed edits must land in the declared baseline
    ("manuscript_unrevised",
     lambda: (d(baseline_text=BASE["manuscript_text"]),
              ["resp.manuscript_unrevised"])),
    # FP guard 1: a manuscript that differs from the declared baseline.
    ("manuscript_unrevised_guard_revised",
     lambda: (d(baseline_text="3.2 Results\nBaseline summary without the control group.\n"),
              [])),
    # FP guard 2: an all-rebuttal letter that legitimately touches nothing —
    # no accepted change, so an unchanged manuscript is correct here.
    ("manuscript_unrevised_guard_rebuttal",
     lambda: (d(baseline_text=BASE["manuscript_text"],
                responses=[{"comment_id": "C1", "decision": "reject",
                            "tone": "polite_rebuttal",
                            "reason": "the control condition is confounded by the batch "
                                      "effect reported in Table 1"},
                           {"comment_id": "C2", "decision": "reject",
                            "tone": "polite_rebuttal",
                            "reason": "the kinetic model is justified by the derivation "
                                      "already in Appendix B"}]),
              [])),

    # Stable Point -> Response -> Change links (inspired by bamdone-rebuttal).
    ("point_response_change_clean", lambda: (linked(), [])),
    ("change_id_duplicate",
     lambda: (linked_with(lambda s: s["responses"][1]["changes"][0].update(
         change_id="C1-CH1")), ["resp.change_id_duplicate"])),
    ("change_id_missing",
     lambda: (linked_with(lambda s: s["responses"][1]["changes"][0].pop("change_id")),
              ["resp.change_id_missing"])),
    ("response_anchor_not_found",
     lambda: (linked_with(lambda s: s["responses"][0]["changes"][0].update(
         response_anchor="missing response quote")), ["resp.response_anchor_not_found"])),
    ("change_pair_incomplete",
     lambda: (linked_with(lambda s: s["responses"][0]["changes"][0].update(added_text="")),
              ["resp.change_pair_incomplete"])),
    ("baseline_missing_for_change",
     lambda: (linked_with(lambda s: s.update(baseline_text="")),
              ["resp.baseline_missing_for_change"])),
    ("before_not_in_baseline",
     lambda: (linked_with(lambda s: s.update(baseline_text="unrelated baseline")),
              ["resp.before_not_in_baseline"])),
    ("unrecorded_revision_claim",
     lambda: (linked_with(lambda s: s["responses"][0].update(changes=[])),
              ["resp.unrecorded_revision_claim"])),
    ("unrecorded_revision_guard_clarification",
     lambda: (linked_with(lambda s: s["responses"][0].update(
         changes=[], text="Response to Point C1: no file change was needed",
         reason="the control was already reported in the baseline")), [])),
    ("revision_claim_without_manuscript",
     lambda: (linked_with(lambda s: s.update(manuscript_text="")),
              ["resp.no_manuscript", "resp.revision_claim_without_manuscript"])),
    ("package_version_missing",
     lambda: (linked_with(lambda s: s.update(manuscript_version="")),
              ["resp.package_version_missing"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = W.run(spec, "review_response")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "review-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the review-response scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

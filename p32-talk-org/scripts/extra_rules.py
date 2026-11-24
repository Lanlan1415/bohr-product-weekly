"""Four checks that distinguish the four slides-track skills.

The deck audit in `deckaudit.py` is shared, and shared infrastructure is honest —
the same measurement should not be reimplemented per challenge. But four skills
that differ only in documentation are one skill sold four times. Each function
here targets the specific failure its challenge is about:

  paper_to_deck   — a slide that shows a figure it cannot name the source of
  deck_edit       — a revision with no record of what changed, where, or why; a
                    half-recorded diff; a deletion with nothing to restore; no
                    pointer to the delivered revision; and a record whose "new
                    text" never landed in the written deck
  talk_org        — a deck with no stated goal, so "too many slides" is undefined
  template_fit    — a type ladder that is not a ladder, titles that drifted off the
                    layout, title faces off the declared theme, a caption and a source
                    locator that name different figures, and declared content that
                    never landed in the written deck

Every rule is mechanical and reports the field it looked at. The rules that compare
the spec against the written deck are declarative in the Lesson-6 sense: they read
only what the caller hands over (the deck summary), so an old caller that passes no
summary is never punished.
"""

from __future__ import annotations

import re


def _add(findings, rule, severity, message, **extra):
    findings.append({"rule": rule, "severity": severity, "message": message, **extra})


# --- 30: 论文转学术 PPT -----------------------------------------------------

PAPER_OBJECT = re.compile(
    r"\b(Fig(?:ure)?s?\.?\s*S?\d+[A-Za-z]?|Tab(?:le)?s?\.?\s*S?\d+[A-Za-z]?|"
    r"Eq(?:uation)?s?\.?\s*\(?\d+[A-Za-z]?\)?|Scheme\s*\d+|Sec(?:tion)?\.?\s*\d+)",
    re.IGNORECASE,
)


def paper_to_deck(spec: dict, findings: list[dict]) -> None:
    """A figure on a slide must name the paper object it came from.

    The characteristic failure of a paper-to-slide conversion is a correct-looking
    figure attributed to the wrong panel, or to no panel at all. A slide that
    carries an image but no figure/table locator cannot be checked by a reader, so
    the mapping is required rather than encouraged.
    """
    required = spec.get("required_mainline") or []
    if required:
        roles = {str(s.get("role") or "") for s in (spec.get("slides") or [])}
        missing = [str(beat) for beat in required if str(beat) not in roles]
        if missing:
            _add(findings, "paper.mainline_missing", "high",
                 "the deck does not cover every declared research-mainline beat",
                 missing=missing, required=[str(x) for x in required])
    for i, s in enumerate(spec.get("slides") or [], start=1):
        has_image = bool(s.get("image"))
        note = " ".join(str(s.get(k) or "") for k in ("caption", "evidence", "notes"))
        named = bool(PAPER_OBJECT.search(note))
        if has_image and not named:
            _add(findings, "paper.figure_unattributed", "high",
                 "the slide shows a figure but names no paper object (Fig./Table/Eq./Section), "
                 "so the image cannot be traced to its source", slide=i)
        if has_image and not str(s.get("caption") or "").strip():
            _add(findings, "paper.caption_missing", "medium",
                 "a figure is placed without a caption, so its conditions are lost", slide=i)


# --- 31: 学术 PPT 生成与编辑 -------------------------------------------------

def _change_is_delete(c: dict) -> bool:
    """A change that declares itself a removal of content."""
    if str(c.get("action") or "").strip().lower() in ("delete", "remove"):
        return True
    return "after" in c and str(c.get("after") or "").strip() == ""


def deck_edit(spec: dict, findings: list[dict], deck_summary: dict | None = None) -> None:
    """Every revision needs a record: what changed, where, why — and how to undo it.

    "Demo iteration" is a scored criterion in this challenge, and a revision with
    no reason cannot be reviewed, reverted, or compared. The check is deliberately
    about structure, not prose quality: a changelog entry must name a slide and
    carry a non-empty reason. Four more record shapes cannot be reviewed or
    replayed, and each is declarative in the Lesson-6 sense — a field the record
    never declares turns the corresponding check off:

      edit.change_half_diff            a text change records only one side of the
                                       before/after pair, so the two versions
                                       cannot be compared page by page
      edit.change_slide_out_of_range   a change names a slide the delivered deck
                                       does not contain, so the record cannot be
                                       mapped onto the file (checked only when the
                                       spec declares slides)
      edit.delete_without_snapshot     a declared deletion records no removed text,
                                       so nothing can be restored — the rollback
                                       the iteration record exists for is lost
      edit.delivered_revision_missing  two or more revisions and no pointer to the
                                       delivered one, so nobody can say which
                                       version is the deliverable (a single
                                       revision is trivially it)
      edit.change_not_in_deck          a change's new text landed neither in the
                                       named slide nor in its notes, so the record
                                       is not the change that was made (checked
                                       only when the builder hands over the written
                                       deck in `deck_summary`, never on the spec
                                       alone)
    """
    revisions = spec.get("revisions") or []
    if not revisions:
        return
    n_slides = len(spec.get("slides") or [])
    dslides = (deck_summary or {}).get("slides") or []

    # 哪一版是交付版: with two or more revisions on record, the pointer to the
    # delivered one is what makes the history shippable. One revision is trivially
    # the deliverable, and a spec that declares no revisions is not iterated at
    # all. The pointer may use the revision's own label (its "n") or its position
    # in the list — a record that keeps only the latest round still names its n.
    if len(revisions) > 1 or spec.get("delivered_revision") is not None:
        labels: set[int] = set()
        for pos, rev in enumerate(revisions, start=1):
            labels.add(pos)
            try:
                labels.add(int(rev.get("n")))
            except (TypeError, ValueError):
                pass
        try:
            ok = int(spec.get("delivered_revision")) in labels
        except (TypeError, ValueError):
            ok = False
        if not ok:
            _add(findings, "edit.delivered_revision_missing", "medium",
                 "the record does not name which revision is the deliverable, so nobody can "
                 "say which version ships",
                 revisions=len(revisions), delivered=spec.get("delivered_revision"))

    for n, rev in enumerate(revisions, start=1):
        if not str(rev.get("instruction") or "").strip():
            _add(findings, "edit.revision_instruction_missing", "low",
                 "a revision round does not record its instruction, so the intent of the "
                 "iteration is missing from the version history", revision=n)
        changes = rev.get("changes") or []
        if not changes:
            _add(findings, "edit.revision_without_changes", "medium",
                 "a revision records no changes, so it is indistinguishable from the previous one",
                 revision=n)
        for c in changes:
            if not c.get("slide"):
                _add(findings, "edit.change_without_slide", "high",
                     "a change does not say which slide it touched", revision=n)
            if not str(c.get("reason") or "").strip():
                _add(findings, "edit.change_without_reason", "high",
                     "a change records no reason, so it cannot be reviewed or reverted",
                     revision=n, slide=c.get("slide"))
            if "before" in c and "after" in c and c["before"] == c["after"]:
                _add(findings, "edit.change_is_noop", "low",
                     "a recorded change leaves the text identical", revision=n,
                     slide=c.get("slide"))

            # 逐页 diff: the pair is what makes two versions comparable. A change
            # that keeps exactly one side claims a diff and breaks it. A declared
            # deletion legitimately records after="", so it is judged on the
            # snapshot rule below instead.
            has_b, has_a = "before" in c, "after" in c
            is_delete = _change_is_delete(c)
            if has_b != has_a and not is_delete:
                _add(findings, "edit.change_half_diff", "medium",
                     "a text change records only one side of the before/after pair, so the "
                     "versions cannot be compared page by page", revision=n,
                     slide=c.get("slide"))

            # 改坏后如何回退: removed content is recoverable only while the record
            # keeps the text it removed.
            if is_delete and not str(c.get("before") or "").strip():
                _add(findings, "edit.delete_without_snapshot", "high",
                     "a deletion records no removed text, so nothing can be restored and the "
                     "rollback the iteration record exists for is impossible", revision=n,
                     slide=c.get("slide"))

            # A change that names a slide the deck does not contain cannot be
            # mapped onto the delivered file — the record points past the artifact.
            # Declarative: a spec that declares no slides leaves the count unknown
            # and is never punished.
            sn = None
            try:
                sn = int(c.get("slide"))
            except (TypeError, ValueError):
                pass
            if n_slides and sn is not None and not 1 <= sn <= n_slides:
                _add(findings, "edit.change_slide_out_of_range", "high",
                     "a change names a slide the delivered deck does not contain, so the "
                     "record cannot be checked against the file", revision=n,
                     slide=c.get("slide"), slides=n_slides)

            # The record must be the change that was made: the new text has to
            # have landed in the named slide's text or its speaker notes. Only a
            # caller that hands over the written deck is checked; a non-text
            # change (no after) and an out-of-range slide are the rules above.
            if dslides and sn is not None and 1 <= sn <= len(dslides) \
                    and has_a and str(c.get("after") or "").strip() and not is_delete:
                ds = dslides[sn - 1]
                after = str(c["after"]).strip()
                if after not in str(ds.get("text") or "") and after not in str(ds.get("notes") or ""):
                    _add(findings, "edit.change_not_in_deck", "high",
                         "the change's new text landed neither in the named slide nor in its "
                         "speaker notes, so the record describes a change that was not made",
                         revision=n, slide=sn, after=after[:40])


# --- 32: 学术汇报内容组织 ----------------------------------------------------

# A topic marker anywhere in a *short* claim. Anchoring at the start missed "方法概述",
# which is exactly the shape a topic slide takes in Chinese; the length gate stops it
# from firing on a real sentence that happens to contain "概述".
WEAK_CLAIM = re.compile("(about|overview|introduction|background|summary|outline|概述|介绍|背景|总结|简介|梳理)", re.IGNORECASE)


def _is_topic_claim(claim: str) -> bool:
    if not WEAK_CLAIM.search(claim):
        return False
    # Short and topic-shaped; a full sentence carrying a comparison is not a topic.
    stripped = claim.strip()
    cjk = sum(1 for c in stripped if "一" <= c <= "鿿")
    if cjk:
        return len(stripped) <= 12
    return len(stripped.split()) <= 4


BACKUP_ROLES = {"backup", "appendix", "qa", "spare", "reserve", "备用", "附录", "问答"}
CLOSING_ROLES = {"closing", "conclusion", "takeaway", "limit", "limitations", "next_steps", "结论", "局限"}
TOPIC_TITLES = {
    "方法", "研究方法", "结果", "实验结果", "背景", "研究背景", "结论", "讨论", "实验",
    "研究内容", "工作安排", "method", "methods", "result", "results", "background",
    "introduction", "conclusion", "discussion", "summary", "backup", "appendix",
}
LIMIT_ROLES = {"limit", "limits", "limitation", "limitations", "局限", "边界", "不足"}


def _main_slides(slides: list[dict]) -> list[tuple[int, dict]]:
    return [(i, s) for i, s in enumerate(slides, 1)
            if str(s.get("role") or "").strip().casefold() not in BACKUP_ROLES]


def _sentences(claim: str) -> int:
    """Conservative assertion count; decimal numbers and section locators stay safe."""
    boundaries = len(re.findall(r"[。！？!?]+", claim))
    english = len(re.findall(r"(?<=[A-Za-z0-9)])\.\s+[A-Z]", claim))
    return max(1, boundaries, english + 1 if english else 1)


def talk_org(spec: dict, findings: list[dict], deck_summary: dict | None = None) -> None:
    """Audit an audience/time/claim/QA plan and, when supplied, its written deck."""
    goal = spec.get("goal") or {}
    slides = spec.get("slides") or []
    main = _main_slides(slides)
    if not goal.get("objective"):
        _add(findings, "org.goal_missing", "high",
             "the deck declares no objective, so its length and depth cannot be judged")
    if goal and not goal.get("audience"):
        _add(findings, "org.audience_missing", "medium",
             "the deck declares no audience, so background depth is uncalibrated")

    # Audience is a plan, not a one-word label. It is enabled only when declared.
    plan = spec.get("audience_plan") or {}
    if spec.get("require_audience_plan"):
        missing_keys = [key for key in ("prior_knowledge", "decision") if not plan.get(key)]
        emphasis = plan.get("emphasis") or []
        if isinstance(emphasis, str):
            emphasis = [emphasis]
        if not emphasis:
            missing_keys.append("emphasis")
        if missing_keys:
            _add(findings, "org.audience_plan_missing", "medium",
                 "the audience adaptation lacks prior knowledge, the decision to enable, or narrative emphasis",
                 missing=missing_keys)
        roles = {str(s.get("role") or "") for _, s in main}
        missing_emphasis = [str(beat) for beat in emphasis if str(beat) not in roles]
        if missing_emphasis:
            _add(findings, "org.audience_emphasis_missing", "medium",
                 "the declared audience concerns have no slide devoted to them",
                 missing=missing_emphasis)
        max_background = plan.get("max_background_slides")
        if max_background is not None:
            try:
                actual = sum(1 for _, s in main if str(s.get("role") or "") in {"background", "context", "背景"})
                if actual > int(max_background):
                    _add(findings, "org.audience_background_overload", "medium",
                         "background exceeds the declared audience adaptation budget",
                         actual=actual, maximum=int(max_background))
            except (TypeError, ValueError):
                _add(findings, "org.audience_budget_invalid", "low",
                     "max_background_slides is not an integer")

    minutes = None
    if goal.get("minutes") is not None:
        try:
            minutes = float(goal["minutes"])
            if minutes <= 0:
                raise ValueError("duration is not positive")
            if main:
                per = minutes / len(main)
                if per < 0.7:
                    _add(findings, "org.pace_too_fast", "medium",
                         "there is under 45 seconds per main slide",
                         minutes=minutes, main_slides=len(main), minutes_per_slide=round(per, 2))
                elif per > 4.0:
                    _add(findings, "org.pace_too_slow", "low",
                         "over four minutes per main slide suggests the deck is thinner than the talk",
                         minutes=minutes, main_slides=len(main), minutes_per_slide=round(per, 2))
        except (TypeError, ValueError):
            _add(findings, "org.duration_invalid", "medium",
                 "the talk duration is not a positive number of minutes", minutes=goal.get("minutes"))

    # Page roles and actual declared story order. Coverage alone would accept a
    # deck that mentions every beat in the wrong order.
    narrative = [str(x) for x in (spec.get("narrative") or [])]
    if narrative or spec.get("require_role"):
        missing_roles = [i for i, s in enumerate(slides, 1) if not str(s.get("role") or "").strip()]
        if missing_roles:
            _add(findings, "org.role_missing", "medium",
                 "a slide has no declared narrative role", slides=missing_roles)
    if narrative:
        actual_roles = [str(s.get("role") or "") for s in slides]
        missing = [beat for beat in narrative if beat not in actual_roles]
        if missing:
            _add(findings, "org.narrative_incomplete", "medium",
                 "the declared narrative arc has no slide for every beat",
                 missing=missing, narrative=narrative)
        outside = [{"slide": i, "role": s.get("role")}
                   for i, s in enumerate(slides, 1)
                   if s.get("role") and str(s.get("role")) not in narrative
                   and str(s.get("role") or "").casefold() not in BACKUP_ROLES]
        if outside:
            _add(findings, "org.role_undeclared", "low",
                 "a slide carries a role outside the declared narrative arc", slides=outside)
        rank = {beat: idx for idx, beat in enumerate(narrative)}
        ordered_roles = [(i, str(s.get("role") or ""), rank.get(str(s.get("role") or ""), -1))
                         for i, s in enumerate(slides, 1) if str(s.get("role") or "") in rank]
        for (prev_i, prev_role, prev_rank), (i, role, current_rank) in zip(ordered_roles, ordered_roles[1:]):
            if current_rank < prev_rank:
                _add(findings, "org.narrative_order", "medium",
                     "a later slide moves backwards in the declared narrative order",
                     slide=i, role=role, previous_slide=prev_i, previous_role=prev_role)

    # Mechanically reconciled timing, including optional question-time reserve.
    if minutes is not None:
        qa_minutes = 0.0
        try:
            qa_minutes = float(goal.get("qa_minutes") or 0)
            if qa_minutes < 0 or qa_minutes >= minutes:
                raise ValueError("Q&A reserve must be non-negative and shorter than the slot")
        except (TypeError, ValueError):
            _add(findings, "org.pace_budget_invalid", "low",
                 "Q&A reserve is invalid")
            qa_minutes = 0.0
        budget = minutes - qa_minutes
        missing_pace = [i for i, s in main if s.get("pace_minutes") is None]
        if spec.get("require_timing") and missing_pace:
            _add(findings, "org.pace_slide_missing", "medium",
                 "a main slide has no allocated speaking time", slides=missing_pace)
        allocations = []
        for i, s in main:
            if s.get("pace_minutes") is None:
                continue
            try:
                value = float(s["pace_minutes"])
                if value <= 0:
                    _add(findings, "org.pace_slide_invalid", "medium",
                         "a slide has non-positive speaking time", slide=i, pace_minutes=value)
                allocations.append((i, value))
            except (TypeError, ValueError):
                _add(findings, "org.pace_budget_invalid", "low",
                     "a timing allocation is not numeric", slide=i)
        if allocations:
            allocated = sum(v for _, v in allocations)
            if allocated > budget + 1e-9:
                _add(findings, "org.pace_budget_exceeded", "medium",
                     "per-slide timing allocations exceed the talk duration after Q&A reserve",
                     allocated_minutes=allocated, main_budget_minutes=budget,
                     qa_reserve_minutes=qa_minutes)
            if spec.get("require_timing") and allocated < 0.75 * budget:
                _add(findings, "org.pace_budget_underused", "low",
                     "allocated speaking time leaves more than a quarter of the main slot unplanned",
                     allocated_minutes=allocated, main_budget_minutes=budget)

    # Every strong conclusion needs inspectable support and a reason for its level.
    scale = spec.get("strength_scale") or ["weak", "moderate", "strong", "measured",
                                           "supported", "suggested", "cited"]
    ordered = {str(name): i for i, name in enumerate(scale)}
    for i, s in enumerate(slides, start=1):
        claim = str(s.get("claim") or "").strip()
        title = str(s.get("title") or "").strip()
        if claim and _is_topic_claim(claim):
            _add(findings, "org.claim_is_topic", "medium",
                 "the slide's claim is a topic word rather than an assertion", slide=i, claim=claim)
        if title and (title.casefold().strip(" :：-—_") in TOPIC_TITLES or _is_topic_claim(title)):
            _add(findings, "org.title_is_topic", "medium",
                 "the visible slide title is a topic label rather than a conclusion", slide=i, title=title)
        if claim and _sentences(claim) > 1 and spec.get("require_single_claim", True):
            _add(findings, "org.multiple_claims", "medium",
                 "a slide declares multiple sentence-level claims instead of one message",
                 slide=i, claim=claim)
        if s.get("claim") and not s.get("strength"):
            _add(findings, "org.evidence_strength_missing", "medium",
                 "the claim carries no evidence-strength label", slide=i)
        if s.get("strength") and str(s.get("strength")) not in ordered:
            _add(findings, "org.strength_unknown", "low",
                 "the evidence-strength label is outside the declared rankable scale",
                 slide=i, strength=s.get("strength"), allowed=list(ordered))
        if spec.get("require_evidence_rationale") and s.get("claim") and not str(s.get("strength_rationale") or "").strip():
            _add(findings, "org.strength_rationale_missing", "medium",
                 "the evidence-strength label has no supporting rationale", slide=i)
        if str(s.get("strength") or "").casefold() == "strong":
            context = " ".join(str(s.get(k) or "") for k in ("claim", "strength_rationale", "notes")).casefold()
            if re.search(r"preliminary|suggestive|uncertain|possibly|初步|探索性|不确定|可能|或许", context):
                _add(findings, "org.strength_overstated", "medium",
                     "a 'strong' label conflicts with preliminary or uncertain evidence language", slide=i)

    # Closing and limitations must survive the actual slide sequence, not just notes.
    if spec.get("require_closing"):
        if not main or str(main[-1][1].get("role") or "").casefold() not in CLOSING_ROLES:
            _add(findings, "org.closing_missing", "medium",
                 "the last main slide is not a conclusion/takeaway/limitation; backups cannot replace it")
        else:
            final_slide, final = main[-1]
            takeaway = str(final.get("takeaway") or final.get("title") or "").strip()
            if not takeaway:
                _add(findings, "org.takeaway_missing", "medium",
                     "the closing slide has no portable takeaway")
            delivered = (deck_summary or {}).get("slides") or []
            if delivered and takeaway and final_slide <= len(delivered):
                text = str(delivered[final_slide - 1].get("text") or "")
                if takeaway not in text:
                    _add(findings, "org.takeaway_not_landed", "high",
                         "the declared closing takeaway is absent from the delivered final slide",
                         slide=final_slide)
    if spec.get("require_limitations"):
        limited = [i for i, s in main if str(s.get("role") or "").casefold() in LIMIT_ROLES and
                   (s.get("limitations") or s.get("bullets") or s.get("takeaway") or s.get("claim"))]
        if not limited:
            _add(findings, "org.limitations_missing", "medium",
                 "no main slide carries explicit study limitations or extrapolation boundaries")

    # Q&A preparation has real topics, answers and optional evidence/page pointers.
    qa = spec.get("qa_prep") or []
    if spec.get("require_qa_prep"):
        incomplete = [i for i, item in enumerate(qa, 1)
                      if not isinstance(item, dict)
                      or not str(item.get("question") or "").strip()
                      or not (str(item.get("answer") or "").strip() or item.get("answer_slide"))]
        if not qa or incomplete:
            _add(findings, "org.qa_prep_missing", "medium",
                 "Q&A preparation was required but a question or answer/answer-slide pointer is missing",
                 incomplete=incomplete)
    normalized_questions = set()
    for pos, item in enumerate(qa, 1):
        if not isinstance(item, dict):
            continue
        question = re.sub(r"\s+", " ", str(item.get("question") or "").strip().casefold())
        if question in normalized_questions and question:
            _add(findings, "org.qa_duplicate", "low", "the same anticipated question is repeated", item=pos)
        normalized_questions.add(question)
        answer_slide = item.get("answer_slide")
        if answer_slide is not None:
            try:
                if not 1 <= int(answer_slide) <= len(slides):
                    raise ValueError("outside slide range")
            except (TypeError, ValueError):
                _add(findings, "org.qa_pointer_invalid", "medium",
                     "a Q&A answer points to a slide outside the deck", item=pos,
                     answer_slide=answer_slide)
        if spec.get("require_qa_evidence") and not (item.get("evidence") or item.get("answer_slide")):
            _add(findings, "org.qa_evidence_missing", "medium",
                 "a prepared answer has no evidence locator or answer-slide pointer", item=pos)
    required_topics = [str(t) for t in (spec.get("required_qa_topics") or [])]
    if required_topics:
        actual_topics = {str(item.get("topic") or "") for item in qa if isinstance(item, dict)}
        missing_topics = [t for t in required_topics if t not in actual_topics]
        if missing_topics:
            _add(findings, "org.qa_topics_missing", "medium",
                 "anticipated Q&A omits required challenge categories", missing=missing_topics)

    # Selection choices are as reviewable as the final slides.
    if spec.get("require_selection_ledger"):
        ledger = spec.get("selection_ledger") or {}
        incomplete = []
        for bucket in ("kept", "omitted"):
            for i, item in enumerate(ledger.get(bucket) or [], 1):
                if not isinstance(item, dict) or not item.get("content") or not item.get("reason") or not item.get("evidence"):
                    incomplete.append({"bucket": bucket, "item": i})
        if not (ledger.get("kept") or ledger.get("omitted")) or incomplete:
            _add(findings, "org.selection_ledger_incomplete", "medium",
                 "the content-selection ledger lacks kept/omitted content, source locator, or reason",
                 incomplete=incomplete)
    if spec.get("require_selection_reasons"):
        for i, s in main:
            if not str(s.get("selection_reason") or "").strip():
                _add(findings, "org.slide_decision_missing", "low",
                     "a slide does not say why it earned a slot in the talk", slide=i)

    # Visible slides are checked when a written-deck summary is available.
    for i, ds in enumerate((deck_summary or {}).get("slides") or [], 1):
        if i <= len(slides) and str(slides[i - 1].get("title") or "").strip():
            expected = str(slides[i - 1]["title"]).strip()
            if expected not in str(ds.get("text") or ""):
                _add(findings, "org.content_dropped", "high",
                     "a declared conclusion-style title is absent from the delivered slide", slide=i)


# --- 33: 学术 PPT 模板与格式适配 ---------------------------------------------

# Figure/table/equation numbers in a caption or a source locator. The number, not the
# panel letter, is compared: "Fig. 3b" and "Fig. 3" are the same object at this
# granularity, and under-reporting a panel-level mismatch is the safe direction.
# Latin prefixes need a word boundary ("notable 12" must not read as Table 12); the
# CJK prefixes need a CJK lookbehind so "列表 2" does not read as 表 2. Anything the
# pattern does not know about stays unmatched, which under-reports rather than
# inventing a mismatch.
FIG_NUM = re.compile(
    r"(?:\b(?:fig(?:ure)?s?|tab(?:le)?s?|eq(?:uation)?s?|scheme)|(?<![一-鿿])[图表式])"
    r"\s*(S?)\s*\.?\s*\(?\s*(\d+)",
    re.IGNORECASE)


def _figure_nums(text: str) -> set[str]:
    """Figure/table numbers named by a locator string, supplementary S kept apart."""
    return {pre.upper() + num for pre, num in FIG_NUM.findall(text or "")}


def template_fit(spec: dict, findings: list[dict], deck_summary: dict | None = None) -> None:
    """The type ladder must actually be a ladder, and the template must actually hold.

    A template adaptation fails quietly when the title and body sizes converge: the
    file still opens, every text box is filled, and nothing reads as a heading. The
    check is on the ratio, not the absolute size, because the ratio is what carries
    the hierarchy.

    Three more quiet failures are checked against what the builder hands back in
    `deck_summary` — the written deck as read from disk, not the spec:

      format.font_drift      a title is set in a typeface the declared theme does not
                             name — the classic signature of pages still on the old
                             template, and of the substitution the export step makes
      format.title_drift     slides sharing one declared layout place or size their
                             titles differently — "only the first three pages were
                             adapted"
      format.content_dropped declared title, bullet or caption text that never landed
                             in the written slide — the outcome of a missing
                             placeholder when no substitution was made

    Each is declarative: a caller that passes no summary (or a summary without the
    per-slide fields) is never punished, and a spec that declares no fonts or no
    template turns the corresponding check off rather than on.
    """
    summary = deck_summary or {}
    sp = summary.get("spacing") or spec.get("spacing") or {}
    title, body = sp.get("title"), sp.get("body")
    # Real template application may correct a stale declared size. Judge the
    # delivered ladder, not a superseded spec value. The smallest measured title
    # and body are the conservative check when cover/content layouts differ.
    delivered_title = [float(v) for slide in summary.get("slides") or []
                       for v in slide.get("title_sizes") or []]
    delivered_body = [float(v) for slide in summary.get("slides") or []
                      for v in slide.get("body_sizes") or []]
    if delivered_title and delivered_body:
        title, body = min(delivered_title), min(delivered_body)
    if title and body:
        ratio = float(title) / float(body)
        if ratio < 1.35:
            _add(findings, "format.size_ladder_flat", "medium",
                 "title and body sizes are too close to read as a hierarchy",
                 title_pt=title, body_pt=body, ratio=round(ratio, 2))
        if ratio > 3.0:
            _add(findings, "format.size_ladder_steep", "low",
                 "the title is more than three times the body size, which will wrap or crowd",
                 title_pt=title, body_pt=body, ratio=round(ratio, 2))

    if spec.get("template"):
        # "template.layouts" is the declared set the template actually provides; a
        # slide outside it falls back to a default layout and loses the theme.
        used = {s.get("layout", "content") for s in (spec.get("slides") or [])}
        declared = set((spec.get("template") or {}).get("layouts") or [])
        if declared and not used <= declared:
            _add(findings, "format.undeclared_layout", "high",
                 "a slide uses a layout the template does not declare, so it will fall back "
                 "to a default and lose the theme", used=sorted(used), declared=sorted(declared))
        if (spec.get("template") or {}).get("name") is None:
            _add(findings, "format.template_unnamed", "low",
                 "the deck names no template, so the adaptation is not reproducible")

    # A slide's caption and its source locator must name the same figure. Both fields
    # are declared; a caption with no number and a locator with no number are never
    # compared, so descriptive captions are not punished.
    for i, s in enumerate(spec.get("slides") or [], start=1):
        cap = _figure_nums(str(s.get("caption") or ""))
        ev = _figure_nums(str(s.get("evidence") or ""))
        if cap and ev and not (cap & ev):
            _add(findings, "format.figure_mismatch", "high",
                 "the caption and the source locator name different figure numbers, so the "
                 "slide's figure and its evidence point at different objects",
                 slide=i, caption=sorted(cap), evidence=sorted(ev))

    dslides = summary.get("slides") or []
    if not dslides:
        return

    # Theme typefaces, declared. A run with no explicit typeface inherits the theme
    # and is fine; only an explicit off-theme face on a *title* is flagged — body
    # runs legitimately change face for code or emphasis, and a title does not.
    declared_fonts = {str(f).strip().lower()
                      for f in (spec.get("font_ea"), spec.get("font_latin")) if f}
    declared_names = sorted({str(f) for f in (spec.get("font_ea"), spec.get("font_latin")) if f})
    if declared_fonts:
        for i, ds in enumerate(dslides, start=1):
            off = sorted({str(f) for f in (ds.get("title_fonts") or [])
                          if f and str(f).strip().lower() not in declared_fonts})
            if off:
                _add(findings, "format.font_drift", "medium",
                     "a title is set in a typeface the declared theme does not name, so "
                     "that page is not on the template's font theme",
                     slide=i, faces=off, declared=declared_names)

    # Title geometry and title size, per declared layout. One layout is one geometry
    # in the template; slides on the same layout that disagree are pages the
    # adaptation never reached. A slide with no title box is deck.no_title's job.
    if spec.get("template"):
        groups: dict[str, list[dict]] = {}
        for ds in dslides:
            if ds.get("title_geom"):
                groups.setdefault(str(ds.get("layout") or "content"), []).append(ds)
        for layout, members in groups.items():
            geoms = [tuple(m["title_geom"]) for m in members]
            if len(set(geoms)) > 1:
                _add(findings, "format.title_drift", "medium",
                     "slides on one declared layout place their title boxes differently, "
                     "so some pages are still on the old template",
                     slide_layout=layout, aspect="geometry",
                     variants=len(set(geoms)), slides=[m.get("index", 0) for m in members])
            size_sets = [tuple(m.get("title_sizes") or ()) for m in members]
            if size_sets and all(size_sets) and len(set(size_sets)) > 1:
                _add(findings, "format.title_drift", "medium",
                     "slides on one declared layout set their titles at different sizes, "
                     "so the type ladder is not one ladder",
                     slide_layout=layout, aspect="size", variants=len(set(size_sets)))

    # Body geometry and size must share the same layout contract as the title.
    # Without this, a deck can have perfect cover/title formatting while later
    # pages retain old margins and font sizes — the exact partial-adaptation failure.
    if spec.get("template"):
        body_groups: dict[str, list[dict]] = {}
        for ds in dslides:
            if ds.get("body_geom"):
                body_groups.setdefault(str(ds.get("layout") or "content"), []).append(ds)
        for layout, members in body_groups.items():
            # A caption or image legitimately reserves a different body height.
            # Batch margins are determined by origin and width, not forced equal cy.
            variants = {tuple(m["body_geom"][:3]) for m in members}
            if len(variants) > 1:
                _add(findings, "format.body_drift", "medium",
                     "slides on one declared layout place their body boxes differently, "
                     "so page margins/reflow are not batch-consistent",
                     slide_layout=layout, aspect="body_geometry", variants=len(variants),
                     slides=[m.get("index", 0) for m in members])
            sizes = [tuple(m.get("body_sizes") or ()) for m in members]
            if sizes and all(sizes) and len(set(sizes)) > 1:
                _add(findings, "format.body_drift", "medium",
                     "slides on one declared layout use different body font sizes",
                     slide_layout=layout, aspect="body_size", variants=len(set(sizes)))

    # Declared content must actually land. An exact-text match against the written
    # slide is the mechanical net for a missing placeholder with no substitution:
    # the file opens, the layout holds, and the content is simply not there.
    spec_slides = spec.get("slides") or []
    for i, ds in enumerate(dslides, start=1):
        text = ds.get("text")
        if text is None:
            continue  # no per-slide text handed over: nothing to compare, never punished
        s = spec_slides[i - 1] if i - 1 < len(spec_slides) else {}
        wanted: list[str] = []
        for v in [s.get("title"), s.get("caption")] + list(s.get("bullets") or []):
            if isinstance(v, dict):
                v = v.get("text")
            v = str(v or "").strip()
            if v:
                wanted.append(v)
        for v in wanted:
            if v not in text:
                _add(findings, "format.content_dropped", "high",
                     "content the spec declares never landed in the written slide, so the "
                     "placeholder substitution failed and the material is lost",
                     slide=i, content=v[:40])
    for j in range(len(dslides), len(spec_slides)):
        _add(findings, "format.content_dropped", "high",
             "a declared slide was not written into the deck at all", slide=j + 1)


SECTIONS = {
    "paper_to_deck": paper_to_deck,
    "deck_edit": deck_edit,
    "talk_org": talk_org,
    "template_fit": template_fit,
}


def run(spec: dict, section: str, deck_summary: dict | None = None) -> list[dict]:
    """Apply one skill's specific section. Unknown names are a hard error, not a skip."""
    fn = SECTIONS.get(section)
    if fn is None:
        raise ValueError(f"unknown section '{section}'; choose from {sorted(SECTIONS)}")
    findings: list[dict] = []
    if section in ("template_fit", "deck_edit", "talk_org"):
        # All three judge the written artifact against their own domain records;
        # direct rule-only bench calls pass no summary and keep declarative guards.
        fn(spec, findings, deck_summary)
    else:
        fn(spec, findings)
    for f in findings:
        f.setdefault("section", section)
    return findings

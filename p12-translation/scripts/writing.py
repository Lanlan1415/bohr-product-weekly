"""Audit an academic text against the discipline its section requires.

The shared premise of the writing track is that prose quality is a model's job and
*traceability* is a checker's job. A language model can draft a paragraph; it
cannot prove that every assertion carries a citation from the set it was given,
that a translation preserved every number and unit, that a response letter answers
every reviewer comment, or that a reformatted manuscript kept its section order.

Four sections, one entry point:

  evidence_writing  every claim cited, every citation real, no source left unused
  translation       numbers/units/citations/terms preserved across languages
  review_response   every comment answered, every claimed change locatable
  format_template   section order, heading levels, numbering, limits, reference count

Each returns findings with a rule id, and each is exercised by a planted-defect
benchmark whose clean baseline must stay silent.
"""

from __future__ import annotations

import json
import re

import guard as G

# --- shared helpers ---------------------------------------------------------

# A sentence that asserts something usually has a finite verb and no citation.
ASSERTIVE = re.compile(
    r"\b(is|are|was|were|has|have|had|shows?|showed|indicates?|suggests?|"
    r"demonstrates?|confirms?|reduces?|increases?|improves?|correlates?)\b",
    re.IGNORECASE)
CJK_ASSERTIVE = re.compile(r"(表明|显示|证明|提示|提高|降低|显著|相关|说明)")

LATIN_CHAR = re.compile(r"[A-Za-z]")
CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")

CITE_KEY = re.compile(r"\[([A-Za-z0-9:_\-]+(?:,\s*[A-Za-z0-9:_\-]+)*)\]")


def _sentences(text: str) -> list[str]:
    return G.split_sentences(text)


def _add(findings, rule, severity, message, **extra):
    findings.append({"rule": rule, "severity": severity, "message": message, **extra})


def _records(value):
    """Iterate the dict entries of a spec list; malformed (non-dict) entries degrade to skipped."""
    for item in value or []:
        if isinstance(item, dict):
            yield item


STOPWORDS = {"the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "is", "are",
             "was", "were", "with", "by", "as", "at", "that", "this", "it", "we", "our",
             "be", "been", "has", "have", "had", "from", "than", "which", "these", "those"}


def _overlap(text: str, against: str) -> float:
    """Fraction of `text`'s content words that also appear in `against`.

    The same crude lexical test used elsewhere in this project: it decides whether two
    strings are about the same thing, not whether one entails the other.
    """
    ta = {t for t in re.findall(r"[a-z][a-z0-9\-]{2,}", (text or "").lower())
          if t not in STOPWORDS}
    tb = {t for t in re.findall(r"[a-z][a-z0-9\-]{2,}", (against or "").lower())
          if t not in STOPWORDS}
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def _cite_keys(sentence: str) -> list[str]:
    """Citation keys such as [doe2020] or [doe2020, roe2021]."""
    keys = []
    for m in CITE_KEY.finditer(sentence):
        keys.extend(k.strip() for k in m.group(1).split(","))
    return [k for k in keys if k]


# Units across languages: "12 h" and "12 小时" are the same fact written in
# two scripts. Without canonicalisation the translation reads as dropping
# its unit, and the agent "fixes" a correct translation. Counters and ratio
# words ("12 例"/"12 cases", "3 倍"/"3-fold") stay unlisted on one side, so
# they compare equal through the empty unit.
_UNIT_CANON = {
    "h": "h", "小时": "h", "hours": "h", "hour": "h",
    "min": "min", "分钟": "min", "minutes": "min", "minute": "min",
    "s": "s", "秒": "s", "seconds": "s", "second": "s",
    "d": "d", "天": "d", "日": "d", "days": "d", "day": "d",
    "周": "week", "weeks": "week", "week": "week",
    "月": "month", "months": "month", "month": "month",
    "年": "year", "years": "year", "year": "year",
    "倍": "", "℃": "°C", "个月": "month", "C": "°C",
}

# "30,000" must be one number: a comma-split value reads as 30 and 0 and
# breaks every magnitude conversion the task asks to record. Only the comma
# is removed — the digit before it stays (replacing the whole match would
# turn 30,000 into 3000 and flag a faithful translation as a broken invariant).
_COMMA_GROUP = re.compile(r"(\d),(?=\d{3})")

# The mechanical signature of encoding damage: a replacement character means
# the bytes were decoded wrong somewhere between the PDF and this audit.
REPLACEMENT_CHAR = "\ufffd"


def _canon_unit(u) -> str:
    return _UNIT_CANON.get(u or "", u or "")


def _quantity_pairs(text: str) -> list[tuple[float, str]]:
    """(value, canonical unit) for every quantity in a text, commas unwound."""
    text = G.normalise(text)
    text = _COMMA_GROUP.sub(r"\1", text)
    return [(round(q.value, 9), _canon_unit(q.unit)) for q in G.extract_quantities(text)]


# --- 1. evidence-driven writing --------------------------------------------

SOURCE_TYPES = ("primary", "review", "guideline", "preprint")
STRENGTHS = ("strong", "moderate", "weak")
HEDGE_WORDS = ("may", "might", "could", "suggest", "suggests", "indicate", "indicates",
               "likely", "possible", "possibly", "uncertain", "unclear", "limited",
               "preliminary", "appears", "tends", "可能", "提示", "表明", "有限", "不确定")


def evidence_writing(spec: dict, findings: list[dict]) -> None:
    """Evidence-driven writing as a three-part deliverable.

    The task asks for a claim list, an evidence table and the manuscript, and grades four
    kinds of element on every claim: the claim, its source, a strength label and an
    uncertainty statement. Each of those is a rule, plus the many-to-many linking the task
    calls out explicitly -- one claim may need several sources, one source may support
    several claims, and both directions are checked.
    """
    claims = list(_records(spec.get("claims")))
    table = spec.get("evidence") or []
    draft = str(spec.get("draft") or spec.get("text") or "")
    # A bare string entry is a key with no metadata: accepted, and then reported by the
    # metadata rules rather than crashing. Minimal input should degrade, not break.
    table = [e if isinstance(e, dict) else {"key": str(e)} for e in table]
    by_key = {str(e.get("key") or e.get("id") or ""): e for e in table}
    by_key.pop("", None)

    if not claims:
        _add(findings, "ew.claims_missing", "high",
             "no claim list was supplied, so the deliverable is missing its first part")
    if not draft.strip():
        _add(findings, "ew.draft_missing", "high",
             "no manuscript text was supplied, so the deliverable is missing its third part")
    if not table:
        _add(findings, "ew.evidence_table_missing", "high",
             "no evidence table was supplied, so the second part of the deliverable is absent")

    # --- the evidence table itself ---------------------------------------
    for key, entry in by_key.items():
        for field in ("title", "year"):
            if not str(entry.get(field) or "").strip():
                _add(findings, "ew.reference_metadata_incomplete", "medium",
                     "an evidence entry lacks bibliographic detail needed to identify it",
                     key=key, missing=field)
        st = str(entry.get("source_type") or "").strip().lower()
        if not st:
            _add(findings, "ew.source_type_missing", "medium",
                 "an evidence entry does not say whether it is primary research, a review, a "
                 "guideline or a preprint", key=key)
        elif st not in SOURCE_TYPES:
            _add(findings, "ew.source_type_unknown", "low",
                 "a source type is outside primary/review/guideline/preprint",
                 key=key, found=st)

    used_keys: set[str] = set()
    ids_seen: set[str] = set()

    for i, c in enumerate(claims):
        cid = str(c.get("id") or "").strip()
        text = str(c.get("claim") or "")
        sources = c.get("sources") or []

        if not cid:
            _add(findings, "ew.claim_no_id", "high",
                 "a claim has no identifier, so the draft and the evidence table cannot point "
                 "at it", claim=i, text=text[:70])
        elif cid in ids_seen:
            _add(findings, "ew.claim_id_duplicate", "high",
                 "two claims share an identifier, so a citation of it is ambiguous", id=cid)
        else:
            ids_seen.add(cid)

        if not text.strip():
            _add(findings, "ew.claim_empty", "high", "a claim has no text", id=cid or i)

        # --- four elements: claim, source, strength, uncertainty ----------
        strength = str(c.get("strength") or "").strip().lower()
        if not strength:
            _add(findings, "ew.strength_missing", "high",
                 "a claim carries no evidence-strength label, so the sentence cannot be written "
                 "at the right strength", claim=cid or i)
        elif strength not in STRENGTHS:
            _add(findings, "ew.strength_invalid", "medium",
                 "a strength label is outside strong/moderate/weak", claim=cid or i, found=strength)
        if strength and not str(c.get("strength_basis") or "").strip():
            _add(findings, "ew.strength_without_basis", "high",
                 "a strength label has no basis (design, sample, replication), so the grade "
                 "cannot be argued with", claim=cid or i)
        if strength in ("weak", "moderate") and not str(c.get("uncertainty") or "").strip():
            _add(findings, "ew.uncertainty_missing", "high",
                 "a weak or moderate claim states no uncertainty, so the prose will read more "
                 "certainly than the evidence allows", claim=cid or i, strength=strength)

        # --- the claim-to-source links ------------------------------------
        if not sources:
            _add(findings, "ew.claim_no_support", "high",
                 "a claim cites no source at all", claim=cid or i, text=text[:70])
        for s in sources:
            key = str(s.get("key") or "").strip()
            if key:
                used_keys.add(key)
            if not key:
                _add(findings, "ew.link_no_source", "high",
                     "a claim-to-source link does not name a source", claim=cid or i)
                continue
            entry = by_key.get(key)
            if entry is None:
                _add(findings, "ew.source_not_in_table", "high",
                     "a claim cites a source that is not in the evidence table",
                     claim=cid or i, key=key)
            quote = str(s.get("quote") or "").strip()
            if not quote:
                _add(findings, "ew.link_no_quote", "high",
                     "a claim-to-source link carries no quoted原文, so support cannot be "
                     "checked", claim=cid or i, key=key)
            if not str(s.get("locator") or "").strip():
                _add(findings, "ew.link_no_locator", "high",
                     "a quoted passage has no section/page/paragraph locator",
                     claim=cid or i, key=key)
            if quote and entry is not None:
                src_text = str(entry.get("text") or "")
                if src_text and quote not in src_text:
                    _add(findings, "ew.quote_not_in_source", "high",
                         "the quoted passage does not occur in the source it is attributed to",
                         claim=cid or i, key=key, quote=quote[:60])
                # --- source quality affects permissible strength ----------
                if entry.get("retracted"):
                    _add(findings, "ew.retracted_source_used", "high",
                         "a retracted source is used as support", claim=cid or i, key=key)
                elif (str(entry.get("source_type") or "").lower() == "preprint"
                      and strength == "strong"):
                    _add(findings, "ew.preprint_as_strong", "medium",
                         "a preprint is used to support a strong claim, which the evidence "
                         "does not yet carry", claim=cid or i, key=key)

        # --- the claim must actually appear in the draft ------------------
        if cid and draft and cid not in draft:
            _add(findings, "ew.claim_not_in_draft", "medium",
                 "a claim in the list is never referenced in the draft, so the deliverable's "
                 "two halves disagree", claim=cid)

        # --- a weak claim written strongly -------------------------------
        if strength in ("weak", "moderate") and draft:
            body = draft
            strong_words = ("prove", "proves", "demonstrate", "demonstrates", "confirm",
                            "confirms", "establish", "establishes", "证明", "证实")
            if any(w in body.lower() for w in strong_words):
                _add(findings, "ew.draft_overstates_strength", "medium",
                     "the draft uses absolute verbs while the claim is labelled weak or "
                     "moderate", claim=cid or i, strength=strength)

    # --- many-to-many coverage in the other direction --------------------
    if by_key:
        unused = sorted(set(by_key) - used_keys)
        if unused:
            _add(findings, "ew.source_unused", "medium",
                 "an evidence-table entry supports no claim, so the table carries material the "
                 "argument never uses", unused=unused[:10], count=len(unused))


# --- 2. translation and bilingual writing ----------------------------------

MODES = ("plain", "bilingual", "tracked")
NEGATION = re.compile(
    r"\b(not|no|never|without|none|neither|nor|cannot|can't|doesn't|does not|"
    r"isn't|is not|aren't|are not|was not|were not)\b|(\u4e0d|\u65e0|\u672a|\u975e|\u6ca1\u6709)",
    re.IGNORECASE)
CN_MAGNITUDE = ("\u4e07", "\u4ebf")          # 万, 亿
EN_MAGNITUDE = ("million", "billion", "thousand")

# Work left unresolved in a delivered translation: honest when it sits in the
# text, unregistered when nothing in the result routes it to a human. Only
# literal markers fire — prose is never scanned for tone or intent (Lesson 6).
PLACEHOLDER = re.compile(
    r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b"
    r"|(\u5f85\u8bd1|\u5f85\u8865|\u5f85\u786e\u8ba4|\u5f85\u5b9a|\u5f85\u6838|\u5f85\u586b"
    r"|\u5360\u4f4d\u7b26|\[\s*\?\s*\]|\u3010\s*\?\s*\u3011)")


def _form_in(form: str, text: str) -> bool:
    """Case-insensitive containment of a term form in a text.

    A pure ASCII form is matched word-bounded, so a term such as `min` does not
    count as present inside `minimum`; CJK and mixed forms use containment,
    because CJK text has no word boundaries to anchor to.
    """
    f = G.normalise(str(form or "")).strip()
    if not f:
        return False
    t = G.normalise(text)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-/.]*", f):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(f)}(?![A-Za-z0-9])", t,
                         re.IGNORECASE) is not None
    return f in t


def _segments_text(segments, side: str) -> str:
    """Concatenate one side of the pairs; non-object entries contribute nothing."""
    return "\n".join(str(s.get(side) or "") for s in segments if isinstance(s, dict))


def translation(spec: dict, findings: list[dict]) -> None:
    """Audit a translation or bilingual delivery.

    The scoring points this task states are specific, and each becomes a rule:

      the requested output shape actually delivered  -> mode_missing, segments_missing
      step-by-step traceability                      -> segment_unpaired, segment_id_duplicate,
                                                        segment_id_absent
      the pairs carry the whole declared source      -> segment_coverage_low
      terms / numbers / units / citations preserved   -> invariant_*, negation_changed,
                                                        hedge_strength_changed,
                                                        number_conversion_unexplained
      no added or deleted scientific judgement        -> invariant_added
      a locked term actually reaches the target      -> term_missing
      a declared back-translation pass is complete    -> backcheck_missing, backcheck_orphaned
      coverage of figures, tables, footnotes, refs    -> component_untranslated
      unresolved work is registered, not just marked  -> placeholder_unregistered
      a scanned source says what OCR did              -> ocr_degradation_unrecorded
      maintainable terminology with a basis           -> term_variant, term_entry_no_basis,
                                                        glossary_conflict
      a runnable, undamaged input                    -> language_pair_degenerate,
                                                        replacement_char_present
    """
    mode = str(spec.get("output_mode") or "").strip().lower()
    src = str(spec.get("source_text") or "")
    # Malformed entries degrade to a finding, never a crash: a segment that is
    # not an object cannot carry a side, so it is skipped and named.
    raw_segments = spec.get("segments")
    if isinstance(raw_segments, list):
        segments = [s for s in raw_segments if isinstance(s, dict)]
        malformed = len(raw_segments) - len(segments)
    else:
        segments = []
        malformed = 1 if raw_segments else 0
    if malformed:
        _add(findings, "xlate.segment_malformed", "medium",
             "a segment entry is not an object and cannot carry a source/target pair",
             count=malformed)

    if not mode:
        _add(findings, "xlate.mode_missing", "high",
             "the deliverable does not say which output shape was asked for (plain "
             "translation, bilingual, or tracked changes), so it cannot be accepted as that "
             "shape")
    elif mode not in MODES:
        _add(findings, "xlate.mode_unknown", "medium",
             "the output shape is outside plain/bilingual/tracked", found=mode)

    # Bilingual and tracked deliveries are segment-level by definition.
    if mode in ("bilingual", "tracked"):
        if not segments:
            _add(findings, "xlate.segments_missing", "high",
                 "a bilingual or tracked delivery needs sentence- or paragraph-level pairs, "
                 "and none were supplied", mode=mode)
        seen: set[str] = set()
        ids_present = False
        for i, seg in enumerate(segments):
            sid = str(seg.get("id") or "")
            if sid and sid in seen:
                _add(findings, "xlate.segment_id_duplicate", "high",
                     "two segments share an identifier, so a reviewer cannot point at one",
                     segment_id=sid)
            elif sid:
                seen.add(sid)
                ids_present = True
            # A missing id on one segment is not flagged (a delivery can be perfectly
            # readable without ids); a delivery where NO segment carries an id cannot
            # be addressed at all, so the absence is reported document-level instead.
            if not str(seg.get("source") or "").strip():
                _add(findings, "xlate.segment_unpaired", "high",
                     "a segment has no source text, so the translation cannot be traced back",
                     segment=i, segment_id=sid or None)
            if not str(seg.get("target") or "").strip():
                _add(findings, "xlate.segment_unpaired", "high",
                     "a segment has no target text, so part of the source is untranslated",
                     segment=i, segment_id=sid or None)
        if segments and not ids_present:
            _add(findings, "xlate.segment_id_absent", "medium",
                 "no segment carries an identifier, so a reviewer cannot point at one pair "
                 "for correction (ids can be as simple as s1, s2, ...)")

    # --- the pairs must carry the declared source (对得齐) -----------------
    # Declarative: it runs only when BOTH a non-empty source_text and pairs are
    # declared, so a plain delivery without segments is never punished. Merging
    # or splitting segments must not fire the rule — dropping content does.
    if mode in ("bilingual", "tracked") and segments and src.strip():
        seg_chars = re.sub(r"\s+", "", G.normalise(_segments_text(segments, "source")))
        src_chars = re.sub(r"\s+", "", G.normalise(src))
        if src_chars:
            coverage = len(seg_chars) / len(src_chars)
            if coverage < 0.75:
                _add(findings, "xlate.segment_coverage_low", "medium",
                     "the segment pairs carry less than three quarters of the declared source "
                     "text, so part of the original has no pair to translate it",
                     coverage=round(coverage, 2), threshold=0.75)

    # --- a declared back-translation pass must be complete (边界清) --------
    # Declarative by design: nothing is demanded unless the spec declares a
    # backcheck list, so a delivery that never promised the pass is not punished.
    raw_backcheck = spec.get("backcheck")
    if isinstance(raw_backcheck, list):
        backcheck = [b for b in raw_backcheck if isinstance(b, dict)]
        malformed_backcheck = len(raw_backcheck) - len(backcheck)
    else:
        backcheck = []
        malformed_backcheck = 1 if raw_backcheck else 0
    if malformed_backcheck:
        _add(findings, "xlate.backcheck_entry_malformed", "medium",
             "a backcheck entry is not an object and cannot name a segment",
             count=malformed_backcheck)
    if backcheck and segments:
        def _high_risk(s: dict) -> bool:
            body = str(s.get("source") or "") + " " + str(s.get("target") or "")
            return bool(_quantity_pairs(body) or G.extract_citations(body)
                        or G.extract_xrefs(body) or NEGATION.search(body)
                        or G.find_hedges(body))

        declared_ids = {str(s.get("id") or "") for s in segments if s.get("id")}
        checked_ids = {str(b.get("segment") or "") for b in backcheck}
        orphaned = sorted(cid for cid in checked_ids if cid not in declared_ids)
        if orphaned:
            _add(findings, "xlate.backcheck_orphaned", "low",
                 "a back-translation record points at a segment id that does not exist",
                 segment_id=orphaned[0])
        missed = sorted(sid for sid in declared_ids
                        if sid not in checked_ids
                        and _high_risk(next(s for s in segments if str(s.get("id")) == sid)))
        if missed:
            _add(findings, "xlate.backcheck_missing", "high",
                 "a declared back-translation pass has no record for a segment that carries a "
                 "number, citation, cross-reference, negation or hedge — exactly the segments "
                 "the pass exists to verify", segment_id=missed[0], missing=missed[:10])

    tgt = _segments_text(segments, "target") if segments else str(spec.get("target_text") or "")
    src_all = _segments_text(segments, "source") if segments else src

    # --- a damaged input is named, not silently audited -------------------
    if REPLACEMENT_CHAR in src_all or REPLACEMENT_CHAR in tgt:
        _add(findings, "xlate.replacement_char_present", "high",
             "the text carries U+FFFD replacement characters, which means bytes were decoded "
             "with the wrong encoding somewhere upstream — audit results are unreliable until "
             "the file is re-decoded", source=REPLACEMENT_CHAR in src_all,
             target=REPLACEMENT_CHAR in tgt)

    if not src_all.strip() or not tgt.strip():
        _add(findings, "xlate.missing_side", "high",
             "one side of the pair is empty, so nothing can be compared")
        return

    # --- a degenerate language pair is named ------------------------------
    src_lang = (spec.get("source_lang") or "zh").lower()
    tgt_lang = (spec.get("target_lang") or "en").lower()
    if src_lang.strip() and src_lang == tgt_lang:
        _add(findings, "xlate.language_pair_degenerate", "medium",
             "source_lang and target_lang name the same language, so no translation is "
             "possible under this declared pair", lang=src_lang)

    # --- invariants, compared document-wide -------------------------------
    from collections import Counter

    def ms(text, fn):
        return Counter(fn(text))

    qty_src, qty_tgt = Counter(_quantity_pairs(src_all)), Counter(_quantity_pairs(tgt))
    mag_in_src = any(m in src_all for m in CN_MAGNITUDE) or         any(m in src_all.lower() for m in EN_MAGNITUDE)
    conversions_declared = bool(spec.get("conversions"))
    excused = []
    if (mag_in_src and conversions_declared):
        # A recorded magnitude conversion (3万 -> 30,000) changes the digits by
        # design. When every changed value pairs with the same canonical unit
        # and a power-of-ten ratio, and the record exists, the change is the
        # declared one — not a broken invariant.
        dropped = list((qty_src - qty_tgt).elements())
        added = list((qty_tgt - qty_src).elements())
        if len(dropped) == len(added):
            remaining_added = list(added)
            for v, u in dropped:
                hit = None
                for av, au in remaining_added:
                    if au != u or v == 0 or av == 0:
                        continue
                    ratio = av / v
                    k = round(__import__("math").log10(abs(ratio)))
                    # A magnitude conversion moves digits either way: 3万 -> 30,000
                    # multiplies the written digits by ten thousand, 300 万 ->
                    # 3 million divides them by a hundred. Both are the declared
                    # record, not a broken invariant — as long as the change is
                    # exactly a power of ten and nothing else moved.
                    if abs(ratio) == 10.0 ** k and k != 0 and -9 <= k <= 9:
                        hit = (av, au)
                        break
                if hit is None:
                    break
                remaining_added.remove(hit)
                excused.append((v, u, hit[0]))
            if not remaining_added and len(excused) == len(dropped):
                # The whole difference is the declared conversion; clear the
                # diff so the quantity invariant below passes clean.
                qty_src = qty_tgt.copy()

    for label, extractor, human in (
        ("quantity", lambda t: _quantity_pairs(t), "numbers or units"),
        ("citation", G.extract_citations, "citation markers"),
        ("xref", G.extract_xrefs, "figure/table/equation references"),
    ):
        if label == "quantity":
            cs, ct = qty_src, qty_tgt
        else:
            cs, ct = ms(src_all, extractor), ms(tgt, extractor)
        dropped = list((cs - ct).elements())
        added = list((ct - cs).elements())
        if dropped:
            _add(findings, "xlate.invariant_broken", "high",
                 f"the translation drops {human} that the source carries",
                 invariant=label, dropped=dropped[:10], count=len(dropped))
        if added:
            _add(findings, "xlate.invariant_added", "high",
                 f"the translation introduces {human} absent from the source",
                 invariant=label, added=added[:10], count=len(added))

    # --- negation scope ----------------------------------------------------
    ns, nt = len(NEGATION.findall(src_all)), len(NEGATION.findall(tgt))
    if ns != nt and (ns or nt):
        _add(findings, "xlate.negation_changed", "high",
             "the number of negations differs between source and target, so a claim may have "
             "been inverted or a hedge turned into an assertion", source_count=ns,
             target_count=nt)

    # --- hedge strength ----------------------------------------------------
    s_strength = max((G.claim_strength(s) for s in G.split_sentences(src_all)), default=0)
    t_strength = max((G.claim_strength(s) for s in G.split_sentences(tgt)), default=0)
    if abs(s_strength - t_strength) >= 1:
        _add(findings, "xlate.hedge_strength_changed", "high",
             "the strongest claim in the target is at a different strength from the source, so "
             "the translation either overstates or waters down the paper",
             source_strength=s_strength, target_strength=t_strength)

    # --- declared numeric conversions must be recorded --------------------
    conversions = spec.get("conversions") or []
    uses_cn = any(m in src_all for m in CN_MAGNITUDE)
    uses_en = any(m in src_all.lower() for m in EN_MAGNITUDE)
    if (uses_cn or uses_en) and not conversions:
        _add(findings, "xlate.number_conversion_unexplained", "medium",
             "the text contains magnitude words (万/亿 or million/billion) and no conversion is "
             "recorded, so a reader cannot confirm the arithmetic between the two versions",
             chinese_magnitude=uses_cn, english_magnitude=uses_en)

    # --- coverage of the parts a paper has beyond body text ---------------
    comps = spec.get("components") if isinstance(spec.get("components"), dict) else {}
    for kind in ("figures", "tables", "equations", "footnotes", "references"):
        present = comps.get(kind)
        if present and str(present).strip().lower() not in ("", "none", "0", "false"):
            marker = str(comps.get(f"{kind}_marker") or "")
            if marker and marker not in tgt:
                _add(findings, "xlate.component_untranslated", "high",
                     "a declared component of the paper does not appear in the target, so the "
                     "translation covers only the body text", component=kind, marker=marker,
                     declared=str(present)[:40])

    # --- untranslated residue --------------------------------------------
    if tgt_lang.startswith("en") and src_lang.startswith("zh"):
        leftover = CJK_CHAR.findall(tgt)
        if leftover:
            _add(findings, "xlate.untranslated_residue", "medium",
                 "Chinese characters remain in the English target, so part of the text was not "
                 "translated", count=len(leftover), sample="".join(leftover[:20]))
    if tgt_lang.startswith("zh") and src_lang.startswith("en") and not CJK_CHAR.search(tgt):
        _add(findings, "xlate.target_not_translated", "high",
             "the Chinese target contains no Chinese characters")

    # --- unresolved work must be registered, not just marked (人工确认项) --
    # A literal marker left in the delivered text is honest marking; the failure
    # is when nothing routes it to a human. Registration = the marker (or its
    # segment context) appears in limits / notes / uncertainty / human_review.
    delivered = tgt
    markers = sorted({m.group(0) for m in PLACEHOLDER.finditer(delivered)})
    if markers:
        registry = spec.get("limits") or spec.get("notes") or spec.get("uncertainty") \
            or spec.get("human_review") or []
        registry_text = G.normalise(json.dumps(registry, ensure_ascii=False, default=str))
        unregistered = [m for m in markers if m not in registry_text]
        if unregistered:
            _add(findings, "xlate.placeholder_unregistered", "medium",
                 "a work marker (待确认/TODO/...) is left in the delivered text but no "
                 "human-review entry or limit records it, so no reviewer is ever routed to "
                 "it — keep the marker and add the record, never delete the marker",
                 markers=unregistered[:6])

    # --- a scanned source must say what OCR did (诚实状态) -----------------
    # Declarative: fires only when the spec declares a PDF source with an
    # explicitly absent text layer and records neither the OCR step nor its
    # uncertainty.
    limits_any = spec.get("limits")
    limits_text = json.dumps(limits_any, ensure_ascii=False, default=str) \
        if limits_any is not None else ""
    if (str(spec.get("source_format") or "").strip().lower() == "pdf"
            and spec.get("text_layer") is False
            and not isinstance(spec.get("ocr"), dict)
            and not any(w in limits_text for w in ("OCR", "ocr", "扫描", "文本层"))):
        _add(findings, "xlate.ocr_degradation_unrecorded", "medium",
             "the source is a scanned PDF without a text layer, but no OCR step or "
             "uncertainty is recorded, so recognised text is presented as verified text",
             text_layer=False)

    # --- length band ------------------------------------------------------
    ratio = len(tgt) / max(len(src_all), 1)
    # Calibrated on character counts, not word counts: a faithful zh->en rendering of a
    # technical passage runs about twice the source length, so a target below 0.8 of it is an
    # omission rather than a concise translation. These bounds are a heuristic, stated as such.
    # Below ~200 source characters the ratio is noise (a two-segment demo swings it wildly),
    # so the band applies only to document-scale text.
    # Bands per direction: zh->en roughly doubles the character count, en->zh
    # compresses it three- to four-fold. The old single (0.5, 3.0) band flagged
    # faithful en->zh translations as omissions.
    if src_lang.startswith("zh") and tgt_lang.startswith("en"):
        lo, hi = 0.8, 3.5
    elif src_lang.startswith("en") and tgt_lang.startswith("zh"):
        lo, hi = 0.15, 2.0
    else:
        lo, hi = 0.3, 3.0
    if len(src_all) >= 200 and (ratio < lo or ratio > hi):
        _add(findings, "xlate.length_out_of_band", "medium",
             "the target length is outside the plausible translation band, which usually means "
             "content was added or dropped", ratio=round(ratio, 2), expected=[lo, hi])

    # --- terminology ------------------------------------------------------
    raw_glossary = spec.get("glossary")
    glossary = {k: v for k, v in raw_glossary.items()
                if isinstance(v, dict)} if isinstance(raw_glossary, dict) else {}
    if isinstance(raw_glossary, dict) and len(glossary) < len(raw_glossary):
        _add(findings, "xlate.glossary_entry_malformed", "medium",
             "a glossary entry is not an object, so its preferred form and basis cannot be "
             "checked", count=len(raw_glossary) - len(glossary))
    if glossary:
        gl = G.Glossary.from_dict(glossary)
        for f in G.check_terms(tgt, gl):
            _add(findings, "xlate.term_variant", "medium",
                 "a glossary term appears in a non-preferred form in the target",
                 concept=f["concept"], found=f["found"], preferred=f["preferred"])
        for concept, entry in glossary.items():
            if not str(entry.get("basis") or "").strip():
                _add(findings, "xlate.term_entry_no_basis", "medium",
                     "a glossary entry does not say what its translation rests on (a standard, "
                     "a textbook, a field convention), so the choice cannot be reviewed",
                     concept=concept)
        # A locked term must actually reach the target (术语稳): the variant rule
        # cannot see a concept that is absent, so the source form is looked up in
        # the source and the locked rendering in the target. Fires only when the
        # glossary itself is declared — a delivery without a glossary is not punished.
        for concept, entry in glossary.items():
            if not isinstance(entry, dict):
                continue
            source_form = str(entry.get("source_form") or concept)
            variants = [str(v) for v in (entry.get("variants") or [])]
            in_source = _form_in(source_form, src_all) or any(
                _form_in(v, src_all) for v in variants)
            if not in_source:
                continue
            abbr = str(entry.get("abbreviation") or "").strip()
            reached = (_form_in(str(entry.get("preferred") or ""), tgt)
                       or (abbr and _form_in(abbr, tgt))
                       or _form_in(source_form, tgt))
            if not reached:
                _add(findings, "xlate.term_missing", "medium",
                     "a glossary concept occurs in the source but its locked rendering never "
                     "reaches the target, so the term was dropped rather than translated",
                     concept=concept, source_form=source_form,
                     preferred=str(entry.get("preferred") or ""))
        # A glossary conflict (术语表冲突): two concepts claim the same preferred
        # form, so the lock cannot be followed consistently anywhere in the text.
        seen_pref: dict[str, str] = {}
        for concept, entry in glossary.items():
            if not isinstance(entry, dict):
                continue
            pref = str(entry.get("preferred") or "").strip()
            if not pref:
                continue
            if pref in seen_pref:
                _add(findings, "xlate.glossary_conflict", "medium",
                     "two glossary concepts claim the same preferred form, so the term table "
                     "cannot be followed consistently", preferred=pref,
                     concepts=[seen_pref[pref], concept])
            else:
                seen_pref[pref] = concept

# --- 3. review response and manuscript revision ----------------------------

DECISIONS = ("accept", "partial", "reject")
TONES = ("accept", "clarify", "polite_rebuttal", "appeal")
COMMENT_TYPES = ("method", "data", "writing", "format", "ethics")
SEVERITIES = ("major", "minor", "editorial")
EVIDENCE_STATUS = ("provided", "unavailable", "alternative_given")

# Fields that describe an evidence request without saying where its data came
# from. Any OTHER non-empty string field on the entry counts as provenance, so
# the source check fires only on a bare kind+status entry and never punishes an
# entry that carries its provenance under a field name this file does not know.
_EVIDENCE_ADMIN_FIELDS = {"kind", "status", "alternative", "note", "notes",
                          "comment", "id", "name", "label", "title"}


def _evidence_provenance(ev: dict) -> bool:
    """True when the evidence entry carries any non-administrative content."""
    return any(isinstance(v, str) and v.strip()
               for k, v in ev.items() if k not in _EVIDENCE_ADMIN_FIELDS)


def review_response(spec: dict, findings: list[dict]) -> None:
    """Audit a revision package: the response letter against the manuscript it claims.

    The scoring points this task states, each as a rule:

      every comment answered, its sub-requirements covered  -> comment_unanswered,
                                                               subrequirement_unanswered
      the response letter and the revised manuscript delivered -> no_manuscript, no_letter
      "we have changed it" matching the manuscript's state   -> change_not_verifiable
      every location independently checkable in the version   -> locator_not_in_manuscript,
                                                               version_mismatch
      decision and tone carried, not implied                 -> decision_*, tone_*
      evidence promised, with its state stated               -> evidence_*
      provided evidence names where its data comes from      -> evidence_source_missing
      the claimed edits land in the declared baseline        -> manuscript_unrevised
    """
    comments = spec.get("comments") or []
    responses = spec.get("responses") or []
    manuscript = str(spec.get("manuscript_text") or "")
    version = str(spec.get("manuscript_version") or "").strip()
    anchors = {str(a) for a in (spec.get("anchors") or [])}

    if not comments:
        _add(findings, "resp.no_comments", "high",
             "no reviewer comments were supplied, so coverage cannot be checked")
        return
    if not responses:
        _add(findings, "resp.no_letter", "high",
             "no response letter was supplied, so nothing answers the comments")
    if not manuscript.strip():
        _add(findings, "resp.no_manuscript", "high",
             "the revised manuscript was not supplied, so no claim of change can be checked")

    answered = {str(r.get("comment_id")) for r in responses}
    known = {str(c.get("id")) for c in comments}

    # --- comment decomposition -------------------------------------------
    for c in comments:
        cid = str(c.get("id"))
        ctype = str(c.get("type") or "").strip().lower()
        sev = str(c.get("severity") or "").strip().lower()
        if ctype and ctype not in COMMENT_TYPES:
            _add(findings, "resp.comment_type_unknown", "low",
                 "a comment type is outside method/data/writing/format/ethics",
                 comment_id=cid, found=ctype)
        if not ctype:
            _add(findings, "resp.comment_type_missing", "medium",
                 "a comment is not classified, so its actionable kind is unclear", comment_id=cid)
        if sev and sev not in SEVERITIES:
            _add(findings, "resp.severity_unknown", "low",
                 "a severity is outside major/minor/editorial", comment_id=cid, found=sev)
        if not sev:
            _add(findings, "resp.severity_missing", "medium",
                 "a comment carries no severity, so the response cannot be prioritised",
                 comment_id=cid)

        if cid not in answered:
            _add(findings, "resp.comment_unanswered", "high",
                 "a reviewer comment has no response in the letter", comment_id=cid,
                 comment=str(c.get("text") or "")[:110])

        subs = [str(s) for s in (c.get("subrequirements") or []) if str(s).strip()]
        if subs:
            # A comment often asks for two things; answering one leaves the other open, and
            # an editor counts that as a non-response. Coverage is judged against ALL
            # response entries that share the comment id: answering one sub-request per
            # entry is a legitimate way to handle a multi-part comment, and counting only
            # the first entry would read the rest as dropped.
            parts: list[str] = []
            for r in responses:
                if str(r.get("comment_id")) == cid:
                    parts.append(str(r.get("reason") or ""))
                    parts.extend(str(ch.get("what") or "") for ch in (r.get("changes") or []))
            body = " ".join(parts)
            missed = [s for s in subs if _overlap(s, body) < 0.2]
            if missed:
                _add(findings, "resp.subrequirement_unanswered", "high",
                     "a comment contains more than one request and part of it is not addressed",
                     comment_id=cid, missing=missed[:6])

    # --- per response ----------------------------------------------------
    for r in responses:
        cid = str(r.get("comment_id"))
        if cid not in known:
            _add(findings, "resp.response_orphaned", "medium",
                 "a response refers to a comment that does not exist", comment_id=cid)

        decision = str(r.get("decision") or r.get("stance") or "").strip().lower()
        tone = str(r.get("tone") or "").strip().lower()
        if not decision:
            _add(findings, "resp.decision_undeclared", "high",
                 "a response does not say whether the comment was accepted, partially "
                 "accepted or declined", comment_id=cid)
        elif decision not in DECISIONS:
            _add(findings, "resp.decision_invalid", "medium",
                 "a decision is outside accept/partial/reject", comment_id=cid, found=decision)
        if not tone:
            _add(findings, "resp.tone_missing", "medium",
                 "a response does not state its tone (accept / clarify / polite rebuttal / "
                 "appeal), so its register cannot be reviewed", comment_id=cid)
        elif tone not in TONES:
            _add(findings, "resp.tone_invalid", "low",
                 "a tone is outside the four the task defines", comment_id=cid, found=tone)

        if decision in ("reject", "partial") and not str(r.get("reason") or "").strip():
            _add(findings, "resp.rebuttal_without_reason", "high",
                 "the letter declines or only partly accepts a comment without giving a "
                 "reason, which editors read as non-response", comment_id=cid)

        for ch in r.get("changes") or []:
            what = str(ch.get("what") or "").strip()
            loc = str(ch.get("location") or ch.get("anchor") or "").strip()
            ver = str(ch.get("manuscript_version") or "").strip()
            added = str(ch.get("added_text") or "").strip()

            if not what:
                _add(findings, "resp.change_unspecified", "medium",
                     "a claimed change does not say what was changed", comment_id=cid)
            if not loc:
                _add(findings, "resp.change_unlocatable", "high",
                     "a claimed change gives no manuscript location, so the editor cannot "
                     "verify it was made", comment_id=cid)

            # The location must resolve in the declared version of the manuscript.
            if loc and manuscript:
                if anchors:
                    ok = loc in anchors
                else:
                    ok = loc in manuscript
                if not ok:
                    _add(findings, "resp.locator_not_in_manuscript", "high",
                         "a claimed location does not occur in the supplied manuscript, so the "
                         "editor cannot find the change", comment_id=cid, location=loc[:60])

            if ver and version and ver != version:
                _add(findings, "resp.version_mismatch", "high",
                     "a change points at a different manuscript version than the one supplied, "
                     "so the letter and the file disagree", comment_id=cid, change_version=ver,
                     manuscript_version=version)

            # "We have added X" must be true of the file.
            if added and manuscript and added not in manuscript:
                _add(findings, "resp.change_not_verifiable", "high",
                     "the letter says text was added that does not appear in the manuscript, so "
                     "the claim of change does not match the file", comment_id=cid,
                     added=added[:70])

        for ev in r.get("evidence") or []:
            # A bare string entry is a kind with no metadata: accepted, and then
            # reported by the status rules rather than crashing. Minimal input
            # should degrade, not break.
            if not isinstance(ev, dict):
                ev = {"kind": str(ev)}
            kind = str(ev.get("kind") or "").strip()
            status = str(ev.get("status") or "").strip().lower()
            if not status:
                _add(findings, "resp.evidence_status_missing", "high",
                     "supplementary evidence is promised without saying whether it was "
                     "provided or could not be", comment_id=cid, kind=kind)
            elif status not in EVIDENCE_STATUS:
                _add(findings, "resp.evidence_status_unknown", "low",
                     "an evidence status is outside provided/unavailable/alternative_given",
                     comment_id=cid, found=status)
            elif status in ("unavailable", "alternative_given") and not str(
                    ev.get("alternative") or "").strip():
                _add(findings, "resp.evidence_without_alternative", "high",
                     "an experiment or dataset could not be supplied and no alternative is "
                     "offered, which leaves the comment effectively unanswered",
                     comment_id=cid, kind=kind)
            elif status == "provided" and not _evidence_provenance(ev):
                _add(findings, "resp.evidence_source_missing", "medium",
                     "an evidence entry is marked provided but names no data source (a file, "
                     "a dataset, a quoted result, a table), so the editor cannot trace where "
                     "it came from", comment_id=cid, kind=kind)

    # --- the claimed edits must land in the supplied baseline -------------
    # The fixed case declares the baseline the revision starts from. When the
    # delivered manuscript is still identical to it, no claimed change can have
    # landed -- the letter says "changed" and the file says otherwise, which is
    # the one failure the per-change rules cannot see when the change entries
    # carry no quoted added_text. Checked only when a baseline is declared
    # (declarative), and only when at least one response claims an accepted
    # change: a letter that declines every comment and leaves the manuscript
    # untouched is a legitimate all-rebuttal package, not a defect.
    baseline = str(spec.get("baseline_text") or "")
    if baseline.strip() and manuscript.strip():
        claims_a_change = any(
            str(r.get("decision") or r.get("stance") or "").strip().lower()
            in ("accept", "partial") and (r.get("changes") or [])
            for r in responses)
        if claims_a_change:
            flat = re.sub(r"\s+", "", G.normalise(manuscript))
            flat_base = re.sub(r"\s+", "", G.normalise(baseline))
            if flat == flat_base:
                _add(findings, "resp.manuscript_unrevised", "high",
                     "the delivered manuscript is identical to the declared baseline while "
                     "the letter claims accepted changes, so no claimed revision actually "
                     "landed in the file -- the substantive edits must fall in the "
                     "manuscript, not stay a declaration")


# --- 4. format and template conformance ------------------------------------

NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+\S")


UNIT_KINDS = ("figures", "tables", "equations", "footnotes", "comments", "revisions",
              "fields", "section_breaks", "embedded")
STYLE_FIELDS = ("font", "size_pt", "line_spacing", "margin_mm", "columns",
                "caption_position", "reference_style", "heading_levels", "export_format")


def format_template(spec: dict, findings: list[dict]) -> None:
    """Audit a manuscript adapted to a target template.

    The scoring points this task states, each as a rule:

      the format spec is met AND the content is unchanged   -> spec_*, content_altered
      headings are bound to styles, not restyled by hand    -> heading_style_unbound,
                                                              toc_not_generated
      every template check and every content unit covered   -> checklist_incomplete,
                                                              unit_lost
      the input-to-output conversion is reproducible        -> conversion_undocumented,
                                                              export_unverified
      structure: sections, order, numbering, references     -> section_*, numbering_gap,
                                                              reference_*
    """
    tmpl = spec.get("template") or {}
    text = str(spec.get("text") or "")
    headings = spec.get("headings") or []

    # --- the template's own spec -----------------------------------------
    fspec = tmpl.get("spec") or {}
    if not fspec:
        _add(findings, "fmt.spec_missing", "high",
             "the template's format specification was not recorded, so conformance cannot be "
             "demonstrated")
    else:
        for field in STYLE_FIELDS:
            if fspec.get(field) in (None, "", []):
                _add(findings, "fmt.spec_value_missing", "medium",
                     "a format field the template controls is not recorded, so the output "
                     "cannot be checked against it", field=field)

    # --- structure --------------------------------------------------------
    required = [s.lower() for s in (tmpl.get("sections") or [])]
    if required:
        present = " ".join(text.lower().split())
        missing = [s for s in required if s not in present]
        if missing:
            _add(findings, "fmt.section_missing", "high",
                 "a section the template requires is absent", missing=missing)
        elif tmpl.get("order", True):
            positions = sorted((present.find(s), s) for s in required)
            ordered = [s for _, s in positions]
            if ordered != required:
                _add(findings, "fmt.section_order", "medium",
                     "sections appear in a different order than the template states",
                     found=ordered, expected=required)

    prev_level = None
    for h in headings:
        try:
            level = int(h.get("level") or 1)
        except (TypeError, ValueError):
            # A non-numeric level degrades to a plain heading rather than crashing:
            # the outline check needs a number, the audit does not need to die for it.
            level = 1
        if prev_level is not None and level > prev_level + 1:
            _add(findings, "fmt.heading_level_skip", "medium",
                 "a heading jumps down more than one level, so the outline and any generated "
                 "TOC will break", heading=str(h.get("text") or "")[:50],
                 from_level=prev_level, to_level=level)
        prev_level = level
        # A heading bound only by size and bold is the failure the task names: the level is
        # invisible to the TOC and to anyone re-using the template.
        if not str(h.get("style") or "").strip():
            _add(findings, "fmt.heading_style_unbound", "high",
                 "a heading carries no paragraph style, so its level exists only as font size "
                 "and weight and will not survive a TOC or a template change",
                 heading=str(h.get("text") or "")[:50], level=level)

    for level in (1, 2, 3):
        nums = [int(str(h.get("number")).split(".")[level - 1]) for h in headings
                if h.get("number") and str(h.get("number")).count(".") == level - 1
                and str(h.get("number")).split(".")[level - 1].isdigit()]
        if nums:
            expected = list(range(1, max(nums) + 1))
            if sorted(set(nums)) != expected:
                _add(findings, "fmt.numbering_gap", "medium",
                     "section numbers skip, which reads as a missing section", level=level,
                     found=sorted(set(nums)), expected=expected)

    if spec.get("toc_expected") and not spec.get("toc_generated"):
        _add(findings, "fmt.toc_not_generated", "high",
             "the template requires a table of contents and none was generated, so the "
             "heading styles cannot be confirmed to work")

    limit = tmpl.get("word_limit")
    try:
        limit_n = int(limit) if limit else None
    except (TypeError, ValueError):
        # A non-numeric limit ("about 5000") cannot be measured; degrade by skipping
        # the check instead of crashing the audit.
        limit_n = None
    if limit_n:
        words = len(CJK_CHAR.findall(text)) + len(re.findall(r"[A-Za-z0-9]+", text))
        if words > limit_n:
            _add(findings, "fmt.word_limit_exceeded", "medium",
                 "the document exceeds the declared word limit", words=words, limit=limit_n)

    # --- references -------------------------------------------------------
    refs = spec.get("references") or []
    if refs:
        cited = set()
        for s in G.split_sentences(text):
            cited.update(k.lower() for k in _cite_keys(s))
            for c in G.extract_citations(s):
                cited.add(c.lower())
        listed = {str(r.get("key") or r.get("id") or "").lower() for r in refs}
        listed.discard("")
        if listed:
            if cited - listed:
                _add(findings, "fmt.citation_not_in_reference_list", "high",
                     "the text cites sources the reference list does not contain",
                     keys=sorted(cited - listed)[:10])
            if listed - cited:
                _add(findings, "fmt.reference_never_cited", "medium",
                     "the reference list contains entries never cited", keys=sorted(listed - cited)[:10])
        if not str(fspec.get("reference_style") or "").strip():
            _add(findings, "fmt.reference_style_missing", "medium",
                 "no reference style is recorded, so field order, author truncation and "
                 "punctuation cannot be checked")

    # --- content must survive the conversion ------------------------------
    before = spec.get("input_units") or {}
    after = spec.get("output_units") or {}
    if before and after:
        for kind in UNIT_KINDS:
            b, a = before.get(kind), after.get(kind)
            if b is None or a is None:
                continue
            try:
                bn, an = int(b), int(a)
            except (TypeError, ValueError):
                # A count that is not a number ("two") cannot be compared; the pair is
                # skipped rather than crashing the whole audit.
                continue
            if an < bn:
                _add(findings, "fmt.unit_lost", "high",
                     "the conversion lost content units of this kind, so the format changed the "
                     "document rather than its appearance", kind=kind, before=bn,
                     after=an)
            elif an > bn:
                _add(findings, "fmt.unit_added", "medium",
                     "the conversion introduced content units that the input did not have",
                     kind=kind, before=bn, after=an)
    elif before or after:
        _add(findings, "fmt.unit_counts_incomplete", "high",
             "content-unit counts exist on only one side, so loss during conversion cannot be "
             "ruled out")

    # --- the conversion record and the export checks ----------------------
    if not spec.get("conversion_steps"):
        _add(findings, "fmt.conversion_undocumented", "high",
             "no conversion steps were recorded, so another person cannot reproduce the path "
             "from the input file to the delivered one")

    exp = spec.get("export") or {}
    if not exp:
        _add(findings, "fmt.export_unverified", "high",
             "no export verification was recorded, so nothing is known about font embedding, "
             "page size, TOC refresh or editability")
    else:
        for field, rule, why in (
            ("font_embedded", "fmt.font_not_embedded",
             "the font is not embedded, so the target machine will substitute and the layout "
             "will shift"),
            ("page_size_measured", "fmt.page_size_unverified",
             "the page size and margins were not measured in the exported file"),
            ("toc_refreshed", "fmt.toc_not_refreshed",
             "the table of contents was not refreshed after editing, so its page numbers are "
             "stale"),
            ("editable", "fmt.not_editable",
             "the delivered file is not editable, so the author cannot continue from it"),
        ):
            if exp.get(field) is False:
                _add(findings, rule, "high", why)
            elif field not in exp:
                _add(findings, "fmt.export_field_missing", "medium",
                     "an export property was not reported, so it is unknown rather than good",
                     field=field)

    # --- figure/table cross-references (排得对) ---------------------------
    # A template conformance job is judged on cross-references as much as on styles:
    # a figure the text never points at is decoration, and a pointer at "Fig 5" when
    # four figures exist is the classic conversion slip. Both checks need the figure
    # numbers declared; without that declaration they stay silent.
    figs = spec.get("figures") or []
    fig_nums = set()
    for f in figs:
        n = f.get("number") if isinstance(f, dict) else f
        try:
            fig_nums.add(int(n))
        except (TypeError, ValueError):
            pass
    if fig_nums:
        _FIG_XREF = re.compile(r"(?:fig(?:ure)?s?\.?|图)\s*(\d+)", re.IGNORECASE)
        _TAB_XREF = re.compile(r"(?:tab(?:le)?s?\.?|表)\s*(\d+)", re.IGNORECASE)
        refs_fig = {int(m.group(1)) for x in re.split(r"[\n。;；]", text)
                    for m in _FIG_XREF.finditer(x)}
        for n in sorted(fig_nums - refs_fig):
            _add(findings, "fmt.figure_never_referenced", "medium",
                 "a figure is declared but the text never cites its number, so it is "
                 "decoration rather than evidence", figure=n)
        for n in sorted(refs_fig - fig_nums):
            _add(findings, "fmt.crossref_dangling", "high",
                 "the text points at a figure number that does not exist, which is the "
                 "classic renumbering slip", figure=n)

    # --- content must not be rasterized (转得全) --------------------------
    # Declared only: an export path that turned editable text into pictures is the one
    # conversion failure the task names that pure counting cannot see.
    if (spec.get("export") or {}).get("rasterized"):
        _add(findings, "fmt.content_rasterized", "high",
             "the export rasterised content, so the delivered file is no longer editable "
             "at the text level", note="re-export with text preserved, or record why")

    # --- the template's checklist -----------------------------------------
    checks = tmpl.get("checks") or []
    done = {str(c) for c in (spec.get("checks_done") or [])}
    if checks:
        missed = [c for c in checks if str(c) not in done]
        if missed:
            _add(findings, "fmt.checklist_incomplete", "high",
                 "template checks were not carried out, so conformance is claimed but not "
                 "demonstrated", missing=missed[:10], count=len(missed))


SECTIONS = {
    "evidence_writing": evidence_writing,
    "translation": translation,
    "review_response": review_response,
    "format_template": format_template,
}


# --- traceability for the result contract -----------------------------------
# The rubric asks the result to carry a 事实与来源映射: every number, term,
# citation and cross-reference with where it came from and whether it survived.
# These helpers build that map from the same machinery the rules use, so the
# ledger cannot disagree with the findings.


def evidence_map(spec: dict, section: str) -> list[dict]:
    """One record per checked item, capped, so a grader can audit the audit."""
    out: list[dict] = []
    if section == "translation":
        segments = [s for s in (spec.get("segments") or []) if isinstance(s, dict)]
        tgt = _segments_text(segments, "target") if segments else str(spec.get("target_text") or "")
        src_all = _segments_text(segments, "source") if segments else str(spec.get("source_text") or "")
        if src_all or tgt:
            from collections import Counter
            qs, qt = Counter(_quantity_pairs(src_all)), Counter(_quantity_pairs(tgt))
            for (v, u), n in sorted(qs.items()):
                out.append({"kind": "quantity", "value": v, "unit": u or None, "count": n,
                            "verdict": "match" if qt.get((v, u)) else "dropped"})
            for (v, u), n in sorted(qt.items()):
                if not qs.get((v, u)):
                    out.append({"kind": "quantity", "value": v, "unit": u or None, "count": n,
                                "verdict": "added"})
            cs, ct = Counter(G.extract_citations(src_all)), Counter(G.extract_citations(tgt))
            for k in sorted(set(cs) | set(ct)):
                verdict = ("match" if ct.get(k) and cs.get(k)
                           else "dropped" if cs.get(k) else "added")
                out.append({"kind": "citation", "marker": k, "verdict": verdict})
            xs, xt = Counter(G.extract_xrefs(src_all)), Counter(G.extract_xrefs(tgt))
            for k in sorted(set(xs) | set(xt)):
                verdict = ("match" if xt.get(k) and xs.get(k)
                           else "dropped" if xs.get(k) else "added")
                out.append({"kind": "xref", "marker": k, "verdict": verdict})
        raw_glossary = spec.get("glossary")
        glossary = raw_glossary if isinstance(raw_glossary, dict) else {}
        for concept, entry in glossary.items():
            if isinstance(entry, dict):
                out.append({"kind": "term", "concept": concept,
                            "preferred": str(entry.get("preferred") or ""),
                            "basis": str(entry.get("basis") or "")})
        comps = spec.get("components") if isinstance(spec.get("components"), dict) else {}
        for kind in ("figures", "tables", "equations", "footnotes", "references"):
            if comps.get(kind):
                marker = str(comps.get(f"{kind}_marker") or "")
                out.append({"kind": "component", "component": kind,
                            "declared": str(comps.get(kind))[:40],
                            "marker_in_target": bool(marker) and marker in tgt})
        raw_backcheck = spec.get("backcheck")
        for b in (raw_backcheck if isinstance(raw_backcheck, list) else [])[:20]:
            if isinstance(b, dict):
                out.append({"kind": "backcheck", "segment": str(b.get("segment") or "")})
    elif section == "evidence_writing":
        for c in _records(spec.get("claims")):
            out.append({"kind": "claim", "id": str(c.get("id") or ""),
                        "sources": len(c.get("sources") or []),
                        "strength": str(c.get("strength") or "")})
        for e in (spec.get("evidence") or []):
            if isinstance(e, dict):
                out.append({"kind": "source", "key": str(e.get("key") or e.get("id") or ""),
                            "source_type": str(e.get("source_type") or "")})
    elif section == "review_response":
        answered = {str(r.get("comment_id")) for r in _records(spec.get("responses"))}
        for c in _records(spec.get("comments")):
            out.append({"kind": "comment", "id": str(c.get("id") or ""),
                        "answered": str(c.get("id") or "") in answered})
    elif section == "format_template":
        tmpl = spec.get("template") if isinstance(spec.get("template"), dict) else {}
        required = [str(s).lower() for s in (tmpl.get("sections") or [])]
        present = " ".join(str(spec.get("text") or "").lower().split())
        for s in required:
            out.append({"kind": "section", "name": s, "present": s in present})
        refs = spec.get("references")
        out.append({"kind": "reference_list", "entries": len(refs) if isinstance(refs, list) else 0})
    return out[:200]


def open_questions(spec: dict, section: str) -> list[dict]:
    """人工确认项 + 材料缺口: what the delivery left open, for the result boundary."""
    out: list[dict] = []
    if section == "translation":
        segments = [s for s in (spec.get("segments") or []) if isinstance(s, dict)]
        tgt = _segments_text(segments, "target") if segments else str(spec.get("target_text") or "")
        markers = sorted({m.group(0) for m in PLACEHOLDER.finditer(tgt)})
        if markers:
            out.append({"type": "human_review", "what": "work markers left in the delivered text",
                        "markers": markers[:6]})
        comps = spec.get("components") if isinstance(spec.get("components"), dict) else {}
        for kind in ("figures", "tables", "equations", "footnotes", "references"):
            present = comps.get(kind)
            marker = str(comps.get(f"{kind}_marker") or "")
            if present and str(present).strip().lower() not in ("", "none", "0", "false") \
                    and marker and marker not in tgt:
                out.append({"type": "gap", "what": f"{kind} not found in the delivered target",
                            "marker": marker})
        if str(spec.get("source_format") or "").strip().lower() == "pdf" \
                and spec.get("text_layer") is False:
            out.append({"type": "uncertainty",
                        "what": "source is a scanned PDF; text rests on OCR"})
    elif section == "evidence_writing":
        for c in _records(spec.get("claims")):
            strength = str(c.get("strength") or "").strip().lower()
            if strength in ("weak", "moderate") and not str(c.get("uncertainty") or "").strip():
                out.append({"type": "human_review",
                            "what": f"claim {c.get('id')} has no uncertainty statement"})
    elif section == "review_response":
        answered = {str(r.get("comment_id")) for r in _records(spec.get("responses"))}
        for c in _records(spec.get("comments")):
            if str(c.get("id") or "") not in answered:
                out.append({"type": "gap", "what": f"comment {c.get('id')} unanswered"})
    elif section == "format_template":
        tmpl = spec.get("template") if isinstance(spec.get("template"), dict) else {}
        fspec = tmpl.get("spec") if isinstance(tmpl.get("spec"), dict) else {}
        missing = [f for f in STYLE_FIELDS if fspec.get(f) in (None, "", [])]
        if missing:
            out.append({"type": "gap", "what": "format spec fields not recorded",
                        "fields": missing[:6]})
    return out[:50]


def run(spec: dict, section: str) -> list[dict]:
    """Apply one section's rules. An unknown section is an error, not a silent skip."""
    fn = SECTIONS.get(section)
    if fn is None:
        raise ValueError(f"unknown section '{section}'; choose from {sorted(SECTIONS)}")
    findings: list[dict] = []
    fn(spec, findings)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return findings, ("clean" if not findings else "blocked" if counts.get("high") else "review"), counts

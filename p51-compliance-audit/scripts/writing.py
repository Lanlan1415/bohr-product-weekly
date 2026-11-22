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

    # Two entries describing the same source under different keys double-count
    # the citation record: the same paper can then appear to support two
    # claims independently. Compared on the whitespace-stripped lowercase
    # title; entries without a title cannot collide.
    _titles: dict[str, list[str]] = {}
    for key, entry in by_key.items():
        t = re.sub(r"\s+", "", str(entry.get("title") or "").lower())
        if t:
            _titles.setdefault(t, []).append(key)
    for keys in _titles.values():
        if len(keys) > 1:
            _add(findings, "ew.duplicate_source", "medium",
                 "two evidence-table entries carry the same title under different keys, "
                 "so one source is recorded twice and the citation counts are inflated",
                 keys=keys[:6])

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


def _segments_text(segments: list[dict], side: str) -> str:
    return "\n".join(str(s.get(side) or "") for s in segments)


def translation(spec: dict, findings: list[dict]) -> None:
    """Audit a translation or bilingual delivery.

    The scoring points this task states are specific, and each becomes a rule:

      the requested output shape actually delivered  -> mode_missing, segments_missing
      step-by-step traceability                      -> segment_unpaired, segment_id_duplicate,
                                                        segment_id_missing
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
      maintainable terminology with a basis           -> term_variant, term_entry_no_basis
    """
    mode = str(spec.get("output_mode") or "").strip().lower()
    src = str(spec.get("source_text") or "")
    segments = spec.get("segments") or []

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
        for i, seg in enumerate(segments):
            sid = str(seg.get("id") or "")
            if sid and sid in seen:
                _add(findings, "xlate.segment_id_duplicate", "high",
                     "two segments share an identifier, so a reviewer cannot point at one",
                     segment_id=sid)
            elif sid:
                seen.add(sid)
            # (a missing segment id is no longer flagged: the demand for ids made the
            #  audit punish deliveries that are perfectly readable without them — Lesson 8)
            if not str(seg.get("source") or "").strip():
                _add(findings, "xlate.segment_unpaired", "high",
                     "a segment has no source text, so the translation cannot be traced back",
                     segment=i, segment_id=sid or None)
            if not str(seg.get("target") or "").strip():
                _add(findings, "xlate.segment_unpaired", "high",
                     "a segment has no target text, so part of the source is untranslated",
                     segment=i, segment_id=sid or None)

    # (segment-coverage checking removed — Lesson 8 revert, see segment_id_missing)

    # (backcheck_missing/orphaned removed — Lesson 8 revert: demanding back-translation
    #  records made the audit punish deliveries that never declared such a pass)

    tgt = _segments_text(segments, "target") if segments else str(spec.get("target_text") or "")
    src_all = _segments_text(segments, "source") if segments else src

    if not src_all.strip() or not tgt.strip():
        _add(findings, "xlate.missing_side", "high",
             "one side of the pair is empty, so nothing can be compared")
        return

    # --- invariants, compared document-wide -------------------------------
    from collections import Counter

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

    def _canon_unit(u):
        return _UNIT_CANON.get(u or "", u or "")

    # "30,000" must be one number: a comma-split value reads as 30 and 0 and
    # breaks every magnitude conversion the task asks to record.
    _COMMA_GROUP = __import__("re").compile(r"(\d),(?=\d{3})")

    def _quantity_pairs(text):
        text = G.normalise(text)
        text = _COMMA_GROUP.sub(r"", text)
        return [(round(q.value, 9), _canon_unit(q.unit)) for q in G.extract_quantities(text)]

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
                    if abs(ratio) == 10.0 ** k and 1 <= k <= 9:
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
    comps = spec.get("components") or {}
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
    src_lang = (spec.get("source_lang") or "zh").lower()
    tgt_lang = (spec.get("target_lang") or "en").lower()
    if tgt_lang.startswith("en") and src_lang.startswith("zh"):
        leftover = CJK_CHAR.findall(tgt)
        if leftover:
            _add(findings, "xlate.untranslated_residue", "medium",
                 "Chinese characters remain in the English target, so part of the text was not "
                 "translated", count=len(leftover), sample="".join(leftover[:20]))
    if tgt_lang.startswith("zh") and src_lang.startswith("en") and not CJK_CHAR.search(tgt):
        _add(findings, "xlate.target_not_translated", "high",
             "the Chinese target contains no Chinese characters")

    # (placeholder_unregistered removed — Lesson 8 revert)

    # (ocr_degradation_unrecorded removed — Lesson 8 revert)

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
    glossary = spec.get("glossary") or {}
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
        # (term_missing removed — Lesson 8 revert: a dropped term is caught by the
        #  length band and the untranslated-residue checks without demanding glossary
        #  records the delivery never promised)

# --- 3. review response and manuscript revision ----------------------------

DECISIONS = ("accept", "partial", "reject")
TONES = ("accept", "clarify", "polite_rebuttal", "appeal")
COMMENT_TYPES = ("method", "data", "writing", "format", "ethics")
SEVERITIES = ("major", "minor", "editorial")
EVIDENCE_STATUS = ("provided", "unavailable", "alternative_given")

# A declined ethics-type comment must rest its refusal on an ethics authority.
# The tokens below are the mechanical test: a reason that names none of them is
# a scope excuse, not an ethics basis. Declared in SKILL.md alongside the rule.
ETHICS_BASIS_TOKENS = ("ethic", "irb", "committee", "consent", "approval",
                       "protocol", "regulation", "伦理", "委员会", "批件",
                       "知情同意", "审查", "规范")

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

    # --- required declarations (COI / funding / data availability / ethics) ---
    # Declarative: the package states which declarations the submission must
    # carry; each named kind must then be recorded with content. Without the
    # requirement list this stays silent, so a package that legitimately needs
    # no COI is never punished. This is the mechanical handle on the brief's
    # "利益冲突声明缺失" and "致谢与基金信息不一致" faces: the declaration must
    # exist and say something, not merely be intended.
    required_decls = [str(k).strip() for k in (spec.get("required_declarations") or [])
                      if str(k).strip()]
    decls = spec.get("declarations") or {}
    if isinstance(decls, dict):
        for decl_kind in required_decls:
            value = decls.get(decl_kind)
            has_content = (isinstance(value, str) and value.strip()) or value is True
            if not has_content:
                _add(findings, "resp.declaration_missing", "medium",
                     f"a required declaration ({decl_kind}) is absent or empty, so the "
                     f"compliance item the submission must carry is not recorded",
                     declaration=decl_kind)

    # --- third-party material licensing (版权与许可风险面) -----------------
    # Declared only: the package lists the third-party figures, tables, code
    # or datasets it reuses; each entry must then record where it came from
    # and under which licence. An entry missing either half cannot be checked
    # against the licence's reuse conditions. Without a third_party list this
    # stays silent.
    for i, item in enumerate(spec.get("third_party") or []):
        if not isinstance(item, dict):
            item = {"what": str(item)}
        what = str(item.get("what") or item.get("name") or f"item {i}")
        if not str(item.get("source") or "").strip():
            _add(findings, "resp.third_party_unlicensed", "medium",
                 "a reused third-party material names no source, so its provenance "
                 "cannot be checked", item=what[:60])
        elif not str(item.get("license") or item.get("licence") or "").strip():
            _add(findings, "resp.third_party_unlicensed", "medium",
                 "a reused third-party material records no licence, so its reuse "
                 "conditions cannot be checked against the use actually made",
                 item=what[:60])

    # --- restricted-data authorisation basis (隐私与数据合规风险面) --------
    # Declared only: entries the package flags as personal, restricted or not
    # yet public data must each record the authorisation basis (consent, ethics
    # approval, anonymisation, agreement). Use without a stated basis is the
    # privacy finding; without a restricted-data list this stays silent.
    for i, item in enumerate(spec.get("restricted_data") or []):
        if not isinstance(item, dict):
            item = {"kind": str(item)}
        kind = str(item.get("kind") or item.get("what") or f"item {i}")
        if not str(item.get("basis") or "").strip():
            _add(findings, "resp.restricted_data_unauthorized", "medium",
                 "a restricted-data usage records no authorisation basis (consent, "
                 "ethics approval, anonymisation, data agreement), so the privacy "
                 "claim cannot be checked", item=kind[:60])

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
    ctype_by_id = {str(c.get("id")): str(c.get("type") or "").strip().lower()
                   for c in comments}
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

        # A declined ethics-type comment needs an ethics basis, not a scope
        # excuse. Fires only when a reason exists (an empty reason is already
        # the rebuttal_without_reason finding) and names no ethics authority.
        if decision == "reject" and ctype_by_id.get(cid) == "ethics":
            reason_text = str(r.get("reason") or "")
            if reason_text.strip() and not any(tok in reason_text.lower()
                                               for tok in ETHICS_BASIS_TOKENS):
                _add(findings, "resp.ethics_decline_without_basis", "medium",
                     "an ethics-type comment was declined and the reason names no ethics "
                     "authority (committee, approval, consent, protocol), so the refusal "
                     "reads as a scope excuse rather than a compliance decision",
                     comment_id=cid)

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

    # --- boilerplate reuse: one answer pasted over several comments --------
    # An identical reason-plus-changes body appearing under two or more
    # comment ids is the textual signature of a template non-response. The
    # comparison is on the whitespace-normalised concatenation, so wording
    # that actually differs never collides.
    bodies: dict[str, list[str]] = {}
    for r in responses:
        body = "|".join([str(r.get("reason") or "")]
                        + [str(ch.get("what") or "") for ch in (r.get("changes") or [])])
        body = re.sub(r"\s+", "", body)
        if body:
            bodies.setdefault(body, []).append(str(r.get("comment_id")))
    dup_groups = [sorted({cid for cid in ids}) for ids in bodies.values() if len(set(ids)) > 1]
    if dup_groups:
        _add(findings, "resp.response_duplicated", "medium",
             "an identical response body is reused for several comments, which editors "
             "read as a template non-response",
             comment_ids=sorted({cid for group in dup_groups for cid in group})[:6],
             count=len(dup_groups))

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
      declared-only extras: conflicting template provisions name the adopted
      version (conflict_unresolved), declared header/footer items are recorded
      item by item (header_footer_unverified), declared page numbers are
      confirmed in the export (page_numbers_unverified)
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

    # --- conflicting template provisions (模板版本差异/相互冲突) -----------
    # Declared only: some templates carry two versions or two provisions that
    # disagree (a required size, a margin, a numbering scheme). When the delivery
    # records such conflicts, it must also record which version was adopted --
    # otherwise a reviewer cannot tell which rule the output actually follows.
    # Without a `conflicts` declaration this stays silent.
    conflicts = tmpl.get("conflicts")
    if conflicts:
        adopted = tmpl.get("adopted") or fspec.get("adopted") or spec.get("adopted")
        if isinstance(adopted, str):
            adopted = adopted.strip()
        if not adopted:
            _add(findings, "fmt.conflict_unresolved", "medium",
                 "the template declares conflicting provisions (for example two versions "
                 "disagree on a required size) but no record says which version was "
                 "adopted, so the output cannot be checked against a chosen rule",
                 conflicts_declared=len(conflicts) if hasattr(conflicts, "__len__") else 1)

    # --- the author-guideline record must carry its edition ---------------
    # Declared only: when the delivery records which author guideline it works
    # against, the record must also name the guideline's version or date, or
    # the conformance claims cannot be re-checked against a fixed edition.
    # Without a guide record this stays silent.
    guide = tmpl.get("guide")
    if isinstance(guide, dict) and (guide.get("name") or guide.get("source")):
        if not (str(guide.get("version") or "").strip()
                or str(guide.get("date") or "").strip()):
            _add(findings, "fmt.guide_version_missing", "medium",
                 "the author-guideline record names no version or date, so the "
                 "submission-requirement checks cannot state which edition of the "
                 "guidelines they rest on",
                 guide=str(guide.get("name") or guide.get("source"))[:60])

    # --- header and footer conformance (排得对: 页眉页脚) -------------------
    # Declared only: header and footer live in the page furniture, outside the
    # body text, so no scan of `text` can see them. What this audit enforces is
    # the record: each item the template declares must be reported as set (with
    # what) or explicitly marked not set, which the task accepts as an honest
    # answer. Without a `header_footer` declaration this stays silent.
    hf = fspec.get("header_footer")
    if isinstance(hf, dict) and hf:
        applied = spec.get("header_footer_applied") or spec.get("header_footer_status")
        if not isinstance(applied, dict) or not applied:
            _add(findings, "fmt.header_footer_unverified", "medium",
                 "the template declares header/footer requirements but the delivery records "
                 "no per-item header/footer status, so conformance cannot be demonstrated "
                 "item by item", declared=sorted(str(k) for k in hf))
        else:
            for item in sorted(str(k) for k in hf):
                if not str(applied.get(item) or "").strip():
                    _add(findings, "fmt.header_footer_unverified", "medium",
                         "a declared header/footer item has no recorded status (set with "
                         "what, or explicitly not set), so it is unknown rather than met",
                         item=item)

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

        # --- page numbers usable in the export (交得出: 页码可用) ----------
        # Declared only: page numbers are checked when the delivery or the
        # template declares they are required. The export record must then
        # confirm they are present and usable (`page_numbers_ok` or an
        # equivalent); a negative or stale value does not confirm. An empty
        # export record is already reported by export_unverified, so this does
        # not double-flag it. Without the declaration this stays silent.
        pn_required = bool(spec.get("page_numbers") or tmpl.get("page_numbers")
                           or fspec.get("page_numbers"))
        if pn_required:
            confirmed = exp.get("page_numbers_ok")
            if confirmed is None:
                confirmed = exp.get("page_numbers_verified")
            if confirmed is None and "page_numbers" in exp:
                confirmed = exp.get("page_numbers")
            if isinstance(confirmed, str):
                confirmed = (confirmed.strip().lower()
                             not in ("", "no", "false", "none", "missing", "stale",
                                     "absent", "n/a"))
            if not confirmed:
                _add(findings, "fmt.page_numbers_unverified", "medium",
                     "page numbers are declared required but the export record does not "
                     "confirm they are present and usable in the delivered file, so the "
                     "page-number half of the deliverable is unverified",
                     recorded=(exp.get("page_numbers_ok") if "page_numbers_ok" in exp
                               else None))

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


# ---------------------------------------------------------------------------
# Rule guide: the judgement basis and the actionable fix each rule carries.
#
# The brief asks every reported item to name its basis and an executable fix,
# not only a severity. The registry below is that requirement as data: for
# each rule id, "basis" is the criterion the verdict rests on (the declared
# vocabulary, the containment test, the coverage rule), and "fix" is what a
# reader does about it. "kind" separates the four verdict classes the brief
# asks to be kept distinct:
#
#   norm_problem    a compliance defect in the material itself
#   fact_mismatch   a statement contradicted by the supplied artefacts
#   missing_input   the material to check was not supplied (待复核, not guilt)
#   advisory        a closed-vocabulary mismatch or stylistic note (建议性)
#
# Applied uniformly in run(), so a finding can never go out without its
# basis and fix when the rule has one.
# ---------------------------------------------------------------------------

RULEGUIDE: dict[str, dict] = {
    # --- refusal -------------------------------------------------------
    "audit.no_section": {"kind": "missing_input",
                         "basis": "运行契约：无法按声明运行的案例以 exit 5 拒收，不产出结论",
                         "fix": "按 SKILL.md 路由表核对 section 拼写，或修好 spec 文件后重跑"},
    # --- review_response ------------------------------------------------
    "resp.no_comments": {"kind": "missing_input",
                         "basis": "口径：无审稿意见则逐条覆盖性无法判定",
                         "fix": "核对案例材料是否漏抽意见页；确认无意见则把该检查项标为未执行"},
    "resp.no_letter": {"kind": "missing_input",
                       "basis": "口径：答复信缺失即修订包不完整",
                       "fix": "提供答复信，或在报告中说明其缺席并标待复核"},
    "resp.no_manuscript": {"kind": "missing_input",
                           "basis": "口径：声称的修改必须落在稿件中才能核验",
                           "fix": "提供修订稿文件后重跑"},
    "resp.comment_type_unknown": {"kind": "advisory",
                                  "basis": "类型词表闭合：method/data/writing/format/ethics",
                                  "fix": "从词表五类中重新归类"},
    "resp.comment_type_missing": {"kind": "norm_problem",
                                  "basis": "口径：意见未分类则行动项不明",
                                  "fix": "按意见内容归入五类之一"},
    "resp.severity_unknown": {"kind": "advisory",
                              "basis": "严重度词表闭合：major/minor/editorial",
                              "fix": "从词表三级中重新标注"},
    "resp.severity_missing": {"kind": "norm_problem",
                              "basis": "口径：无严重度则答复无法排优先级",
                              "fix": "补 major/minor/editorial 之一"},
    "resp.comment_unanswered": {"kind": "norm_problem",
                                "basis": "口径：审稿意见必须逐条答复",
                                "fix": "为该意见补一条带 decision 与 tone 的答复；部分接受需写明理由"},
    "resp.subrequirement_unanswered": {"kind": "norm_problem",
                                       "basis": "口径：多段意见的每个子请求须被覆盖（词元重合 <20% 视为未答）",
                                       "fix": "针对漏掉的子请求逐条补充答复，或写明不采纳理由"},
    "resp.response_orphaned": {"kind": "norm_problem",
                               "basis": "口径：答复必须指向真实存在的意见",
                               "fix": "修正 comment_id，或删除无主答复"},
    "resp.decision_undeclared": {"kind": "norm_problem",
                                 "basis": "口径：答复必须显式声明 accept/partial/reject",
                                 "fix": "补 decision 字段"},
    "resp.decision_invalid": {"kind": "norm_problem",
                              "basis": "决定词表闭合：accept/partial/reject",
                              "fix": "从词表三项中重新标注"},
    "resp.tone_missing": {"kind": "norm_problem",
                          "basis": "口径：语气必须声明，否则语域无法审查",
                          "fix": "补 accept/clarify/polite_rebuttal/appeal 之一"},
    "resp.tone_invalid": {"kind": "advisory",
                          "basis": "语气词表闭合：任务定义的四种",
                          "fix": "从词表四种中重新标注"},
    "resp.rebuttal_without_reason": {"kind": "norm_problem",
                                     "basis": "口径：拒绝或部分接受必须给理由",
                                     "fix": "在 reason 写明依据（数据、设计或范围限制）"},
    "resp.change_unspecified": {"kind": "norm_problem",
                                "basis": "口径：每条声称的修改须说明改了什么",
                                "fix": "补 what 字段"},
    "resp.change_unlocatable": {"kind": "norm_problem",
                                "basis": "口径：每条修改须给出稿件定位",
                                "fix": "补 location（章节或标题），并确认它出现在所声明版本中"},
    "resp.locator_not_in_manuscript": {"kind": "fact_mismatch",
                                       "basis": "定位逐字包含检验：定位串必须出现在交付稿件中",
                                       "fix": "修正定位字符串，或确认稿件版本正确"},
    "resp.version_mismatch": {"kind": "fact_mismatch",
                              "basis": "口径：修改所指版本须与交付版本一致",
                              "fix": "统一 manuscript_version 后重跑"},
    "resp.change_not_verifiable": {"kind": "fact_mismatch",
                                   "basis": "新增文本逐字包含检验：added_text 必须出现在稿件中",
                                   "fix": "把 added_text 摘为稿件原句，或把修改真正落到稿件"},
    "resp.evidence_status_missing": {"kind": "norm_problem",
                                     "basis": "口径：补充证据必须声明其状态",
                                     "fix": "补 provided/unavailable/alternative_given 之一"},
    "resp.evidence_status_unknown": {"kind": "advisory",
                                     "basis": "证据状态词表闭合：provided/unavailable/alternative_given",
                                     "fix": "从词表三项中重新标注"},
    "resp.evidence_without_alternative": {"kind": "norm_problem",
                                          "basis": "口径：无法提供的数据须给出替代",
                                          "fix": "补 alternative（替代数据、方案或图示）"},
    "resp.evidence_source_missing": {"kind": "norm_problem",
                                     "basis": "口径：标记为已提供的证据须可溯源",
                                     "fix": "写明数据来源文件、数据集或引用结果"},
    "resp.manuscript_unrevised": {"kind": "fact_mismatch",
                                  "basis": "与声明基线逐字比对：稿件与基线一致即修改未落地",
                                  "fix": "把实质修改写进交付稿件，而不是只写在答复信里"},
    "resp.declaration_missing": {"kind": "norm_problem",
                                 "basis": "口径：required_declarations 点名的声明逐项留痕（利益冲突/基金/数据可用性/伦理批件）",
                                 "fix": "在 declarations 中补齐该声明及其实际内容"},
    "resp.ethics_decline_without_basis": {"kind": "norm_problem",
                                          "basis": "口径：拒绝伦理类意见须在理由中写明伦理依据（委员会/批件/知情同意/审查）",
                                          "fix": "在 reason 中补伦理委员会、批件号或知情同意依据"},
    "resp.response_duplicated": {"kind": "norm_problem",
                                 "basis": "口径：同一答复体复用于多条意见等同模板化未答复",
                                 "fix": "针对每条意见写具体答复"},
    "resp.third_party_unlicensed": {"kind": "norm_problem",
                                    "basis": "口径：复用的第三方材料须记录来源与许可，复用条件才能对回实际用途",
                                    "fix": "为该材料补 source 与 license（或取得授权后替换）"},
    "resp.restricted_data_unauthorized": {"kind": "norm_problem",
                                          "basis": "口径：受限/个人/未公开数据的使用须写明授权依据（同意书/伦理批件/脱敏/协议）",
                                          "fix": "为该数据使用补 basis，或替换为已授权数据"},
    # --- evidence_writing ------------------------------------------------
    "ew.claims_missing": {"kind": "missing_input",
                          "basis": "口径：论断清单缺失则引用纪律无从核对",
                          "fix": "从稿件抽取论断清单后重跑"},
    "ew.draft_missing": {"kind": "missing_input",
                         "basis": "口径：无稿件文本则论断落地无法核验",
                         "fix": "提供稿件文本后重跑"},
    "ew.evidence_table_missing": {"kind": "missing_input",
                                  "basis": "口径：证据表缺失则来源无法核对",
                                  "fix": "构建证据表（key/题名/年份/类型/原文）后重跑"},
    "ew.reference_metadata_incomplete": {"kind": "norm_problem",
                                         "basis": "口径：文献须可识别（题名/年份）",
                                         "fix": "补齐该条目的 title 与 year"},
    "ew.source_type_missing": {"kind": "norm_problem",
                               "basis": "来源类型词表闭合：primary/review/guideline/preprint",
                               "fix": "补 source_type"},
    "ew.source_type_unknown": {"kind": "advisory",
                               "basis": "来源类型词表闭合",
                               "fix": "从词表四类中重新标注"},
    "ew.claim_no_id": {"kind": "norm_problem",
                       "basis": "口径：论断须有标识符，链接才能被审计",
                       "fix": "补唯一 id"},
    "ew.claim_id_duplicate": {"kind": "norm_problem",
                              "basis": "口径：标识符重复则引用指向不明",
                              "fix": "改用唯一 id"},
    "ew.claim_empty": {"kind": "norm_problem",
                       "basis": "口径：论断必须携带文本",
                       "fix": "补论断正文"},
    "ew.strength_missing": {"kind": "norm_problem",
                            "basis": "口径：论断必须声明证据强度",
                            "fix": "补 strong/moderate/weak"},
    "ew.strength_invalid": {"kind": "norm_problem",
                            "basis": "强度词表闭合：strong/moderate/weak",
                            "fix": "从词表三级中重新标注"},
    "ew.strength_without_basis": {"kind": "norm_problem",
                                  "basis": "口径：强度标注须写明依据（设计/样本/重复）",
                                  "fix": "在 strength_basis 写明定级理由"},
    "ew.uncertainty_missing": {"kind": "norm_problem",
                               "basis": "口径：弱/中强度论断必须写明不确定性",
                               "fix": "补 uncertainty 字段（限制、样本量、替代解释）"},
    "ew.claim_no_support": {"kind": "norm_problem",
                            "basis": "口径：论断必须至少挂一条来源",
                            "fix": "补 sources，或把论断降级为有来源支持的强度"},
    "ew.link_no_source": {"kind": "norm_problem",
                          "basis": "口径：论断-来源链接必须写明来源键",
                          "fix": "补该链接的 key"},
    "ew.source_not_in_table": {"kind": "fact_mismatch",
                               "basis": "口径：引用键必须存在于证据表",
                               "fix": "把来源加入证据表，或修正键名"},
    "ew.link_no_quote": {"kind": "norm_problem",
                         "basis": "口径：引而不证即无支持——链接须携带来源原文",
                         "fix": "从来源原文摘录 quote"},
    "ew.link_no_locator": {"kind": "norm_problem",
                           "basis": "口径：引文须带页码/章节定位才能被独立核对",
                           "fix": "补 locator（页/节/段落）"},
    "ew.quote_not_in_source": {"kind": "fact_mismatch",
                               "basis": "引文逐字包含检验：引文必须出现在被引来源中",
                               "fix": "重新摘录原文，或改正引用归属（张冠李戴信号）"},
    "ew.retracted_source_used": {"kind": "fact_mismatch",
                                 "basis": "口径：撤稿来源不得作为支持",
                                 "fix": "移除该来源并改引有效文献"},
    "ew.preprint_as_strong": {"kind": "norm_problem",
                              "basis": "口径：预印本不足以支撑 strong 论断",
                              "fix": "把论断降级为 moderate/weak，或改引正式发表来源"},
    "ew.claim_not_in_draft": {"kind": "norm_problem",
                              "basis": "口径：清单中的论断必须出现在稿件中",
                              "fix": "把论断写入稿件，或从清单移除"},
    "ew.draft_overstates_strength": {"kind": "norm_problem",
                                     "basis": "口径：稿件措辞不得强于声明的证据强度",
                                     "fix": "按声明强度改写（加限定语，换掉绝对动词）"},
    "ew.source_unused": {"kind": "norm_problem",
                         "basis": "口径：证据表条目须至少支持一条论断",
                         "fix": "在稿件中引用该来源，或从表中移除"},
    "ew.duplicate_source": {"kind": "norm_problem",
                            "basis": "口径：同题重复条目使引用计数失真",
                            "fix": "合并重复条目或修正题名"},
    # --- translation ------------------------------------------------------
    "xlate.mode_missing": {"kind": "missing_input",
                           "basis": "口径：交付必须声明输出形态（plain/bilingual/tracked）",
                           "fix": "补 output_mode"},
    "xlate.mode_unknown": {"kind": "norm_problem",
                           "basis": "输出形态词表闭合：plain/bilingual/tracked",
                           "fix": "从词表三项中重新声明"},
    "xlate.segments_missing": {"kind": "missing_input",
                               "basis": "口径：双语/修订形态必须有逐段对照",
                               "fix": "提供逐段 source/target 对照后重跑"},
    "xlate.segment_id_duplicate": {"kind": "norm_problem",
                                   "basis": "口径：段标识重复则复核无法指向单段",
                                   "fix": "改用唯一段 id"},
    "xlate.segment_unpaired": {"kind": "norm_problem",
                               "basis": "口径：每段两侧齐备才可追溯",
                               "fix": "补齐缺失的一侧文本"},
    "xlate.missing_side": {"kind": "missing_input",
                           "basis": "口径：单侧缺失则无可比对象",
                           "fix": "提供缺失一侧的文本后重跑"},
    "xlate.invariant_broken": {"kind": "fact_mismatch",
                               "basis": "数量/引文/交叉引用守恒比对（单位经同典化）",
                               "fix": "恢复丢失的数字、单位或引文标记"},
    "xlate.invariant_added": {"kind": "fact_mismatch",
                              "basis": "守恒比对：目标侧不得引入源侧没有的数字/单位/引文",
                              "fix": "删除凭空引入的数字、单位或引文"},
    "xlate.negation_changed": {"kind": "fact_mismatch",
                               "basis": "否定词计数比对——翻转即语义相反",
                               "fix": "逐句核对否定词，恢复与源侧一致的极性"},
    "xlate.hedge_strength_changed": {"kind": "fact_mismatch",
                                     "basis": "限定语强度分级比对（guard 词表 5 级）",
                                     "fix": "恢复限定语强度——may 不得变成 confirms"},
    "xlate.number_conversion_unexplained": {"kind": "norm_problem",
                                            "basis": "口径：万/亿与 million/billion 的换算须留痕",
                                            "fix": "在 conversions 记录换算关系"},
    "xlate.component_untranslated": {"kind": "norm_problem",
                                     "basis": "口径：声明的部件（图/表/脚注/文献）必须进入目标文本",
                                     "fix": "补译该部件，或在记录中说明其处理方式"},
    "xlate.untranslated_residue": {"kind": "norm_problem",
                                   "basis": "口径：目标侧残留源语言字符即漏译",
                                   "fix": "翻译残留原文后重跑"},
    "xlate.target_not_translated": {"kind": "fact_mismatch",
                                    "basis": "口径：目标侧与源侧相同即未翻译",
                                    "fix": "实际执行翻译后重跑"},
    "xlate.length_out_of_band": {"kind": "norm_problem",
                                 "basis": "方向化长度带（zh→en 0.8–3.5，en→zh 0.15–2.0）启发式",
                                 "fix": "核对是否整段漏译或增译"},
    "xlate.term_variant": {"kind": "norm_problem",
                           "basis": "术语锁：变体出现在目标侧即偏离首选形式",
                           "fix": "使用术语表首选形式，或在记录中说明合理变体"},
    "xlate.term_entry_no_basis": {"kind": "norm_problem",
                                  "basis": "口径：术语选择须写明依据（标准/教科书/领域惯例）",
                                  "fix": "在 glossary 条目的 basis 写明依据"},
    # --- format_template ----------------------------------------------------
    "fmt.spec_missing": {"kind": "missing_input",
                         "basis": "口径：无格式规格则符合性无法证明",
                         "fix": "记录模板的格式规格后重跑"},
    "fmt.spec_value_missing": {"kind": "norm_problem",
                               "basis": "口径：模板控制的每个格式字段须有值",
                               "fix": "补该格式字段的值"},
    "fmt.conflict_unresolved": {"kind": "norm_problem",
                                "basis": "口径：模板条款冲突须记录采用的版本",
                                "fix": "在 adopted 中写明采用哪个版本"},
    "fmt.guide_version_missing": {"kind": "norm_problem",
                                  "basis": "口径：投稿要求检查须注明所依据指南的版本或日期",
                                  "fix": "在 guide 记录中补 version 或 date"},
    "fmt.header_footer_unverified": {"kind": "norm_problem",
                                     "basis": "口径：声明的页眉页脚项逐项记录状态",
                                     "fix": "逐项记录已设置内容及方式，或显式标注未设置"},
    "fmt.section_missing": {"kind": "norm_problem",
                            "basis": "口径：模板要求的章节必须存在",
                            "fix": "补齐缺失章节后重跑"},
    "fmt.section_order": {"kind": "norm_problem",
                          "basis": "口径：章节顺序须与模板一致",
                          "fix": "按模板顺序调整章节"},
    "fmt.heading_level_skip": {"kind": "norm_problem",
                               "basis": "口径：标题层级不得跳级（目录会断）",
                               "fix": "把跳级标题改为逐级下降"},
    "fmt.heading_style_unbound": {"kind": "norm_problem",
                                  "basis": "口径：标题必须绑定段落样式而非仅靠字号加粗",
                                  "fix": "为标题应用 Heading 样式"},
    "fmt.numbering_gap": {"kind": "norm_problem",
                          "basis": "口径：编号连续，跳号即疑缺节",
                          "fix": "修正编号序列"},
    "fmt.toc_not_generated": {"kind": "norm_problem",
                              "basis": "口径：模板要求目录则必须生成",
                              "fix": "生成目录并刷新"},
    "fmt.word_limit_exceeded": {"kind": "norm_problem",
                                "basis": "口径：字数不得超出模板限制",
                                "fix": "压缩至限内（删冗余、并句）"},
    "fmt.citation_not_in_reference_list": {"kind": "fact_mismatch",
                                           "basis": "引文键与文献表比对",
                                           "fix": "补文献条目或修正引用键"},
    "fmt.reference_never_cited": {"kind": "norm_problem",
                                  "basis": "口径：文献表条目须被正文引用",
                                  "fix": "删除未引条目，或在正文补引用"},
    "fmt.reference_style_missing": {"kind": "norm_problem",
                                    "basis": "口径：须记录引用风格才能核对格式",
                                    "fix": "在模板规格中记录 reference_style"},
    "fmt.unit_lost": {"kind": "fact_mismatch",
                      "basis": "内容单元计数前后比对",
                      "fix": "修复转换中丢失的内容单元（图/表/公式/脚注）"},
    "fmt.unit_added": {"kind": "norm_problem",
                       "basis": "内容单元计数前后比对",
                       "fix": "排查转换引入的多余单元"},
    "fmt.unit_counts_incomplete": {"kind": "missing_input",
                                   "basis": "口径：计数只有单侧则丢失无法排除",
                                   "fix": "补齐另一侧的内容单元计数"},
    "fmt.conversion_undocumented": {"kind": "norm_problem",
                                    "basis": "口径：转换步骤须留痕才能复现",
                                    "fix": "记录从输入到交付的每步转换"},
    "fmt.export_unverified": {"kind": "missing_input",
                              "basis": "口径：无导出验证记录则字体/页面/可编辑性未知",
                              "fix": "记录导出验证结果后重跑"},
    "fmt.font_not_embedded": {"kind": "norm_problem",
                              "basis": "口径：字体未嵌入则版面在他机漂移",
                              "fix": "嵌入字体后重新导出"},
    "fmt.page_size_unverified": {"kind": "norm_problem",
                                 "basis": "口径：页面尺寸须实测",
                                 "fix": "实测导出文件的页面尺寸与页边距并记录"},
    "fmt.toc_not_refreshed": {"kind": "norm_problem",
                              "basis": "口径：编辑后目录须刷新，否则页码失效",
                              "fix": "刷新目录后重新导出"},
    "fmt.not_editable": {"kind": "norm_problem",
                         "basis": "口径：交付文件必须可继续编辑",
                         "fix": "以可编辑格式重新导出"},
    "fmt.export_field_missing": {"kind": "norm_problem",
                                 "basis": "口径：导出属性未报告即未知，不视为合格",
                                 "fix": "补报该导出属性的实际值"},
    "fmt.page_numbers_unverified": {"kind": "norm_problem",
                                    "basis": "口径：声明必须页码则导出记录须确认可用",
                                    "fix": "确认页码存在且可用并记录"},
    "fmt.figure_never_referenced": {"kind": "norm_problem",
                                    "basis": "口径：图必须在正文中被引用其编号",
                                    "fix": "在正文相应位置引用图号"},
    "fmt.crossref_dangling": {"kind": "fact_mismatch",
                              "basis": "交叉引用编号与图清单比对",
                              "fix": "修正正文引用的图号"},
    "fmt.content_rasterized": {"kind": "norm_problem",
                               "basis": "口径：导出不得把文本栅格化（不可再编辑）",
                               "fix": "以保留文本的方式重新导出"},
    "fmt.checklist_incomplete": {"kind": "norm_problem",
                                 "basis": "口径：模板检查单逐项执行并留痕",
                                 "fix": "完成漏掉的检查项并补记录"},
}


def run(spec: dict, section: str) -> list[dict]:
    """Apply one section's rules. An unknown section is an error, not a silent skip."""
    fn = SECTIONS.get(section)
    if fn is None:
        raise ValueError(f"unknown section '{section}'; choose from {sorted(SECTIONS)}")
    findings: list[dict] = []
    fn(spec, findings)
    counts: dict[str, int] = {}
    for f in findings:
        # Every finding leaves with its judgement basis and an actionable fix
        # when the rule guide has them, so the report never ships a bare id.
        guide = RULEGUIDE.get(f["rule"])
        if guide:
            for field in ("kind", "basis", "fix"):
                if guide.get(field):
                    f.setdefault(field, guide[field])
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    status = "clean" if not findings else "blocked" if counts.get("high") else "review"
    return findings, status, counts


def pending_items(findings: list[dict]) -> list[dict]:
    """The 待复核 half of the result status: rules blocked by absent input.

    A missing_input finding is not guilt -- it is a check that could not run.
    The brief asks the result status to separate passed, problem, pending and
    not-checked; this returns the pending slice, derived from the same kind
    vocabulary the rule guide declares.
    """
    return [{"rule": f["rule"], "message": f.get("message", ""),
             "reason": "the input this rule needs was not supplied"}
            for f in findings if f.get("kind") == "missing_input"]

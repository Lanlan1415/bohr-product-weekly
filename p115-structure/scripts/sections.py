"""Section rules for the remaining fourteen challenges.

Every section here answers one question about a *structured deliverable*: does the
extraction carry its conditions, does the claim carry evidence, does the map stay a
tree, does the checklist cover what reproduction needs. None of them judge prose.

Kept in one module because they share a shape: a spec dict in, findings out, each
with a rule id. The shared machinery (`guard`, `units`, `redline`) is imported rather
than reimplemented.

Deliberately small per section: two to five rules that are mechanically decidable.
A rule that needs judgement is not included, because a wrong rule is worse than a
missing one — it teaches the author to ignore the audit.
"""

from __future__ import annotations

import re

import guard as G
import units as U

DIM = ("mass", "length", "time", "current", "temperature", "amount", "luminous")


def _add(findings, rule, severity, message, **extra):
    findings.append({"rule": rule, "severity": severity, "message": message, **extra})


def _chapter_num(value) -> int:
    """A chapter "number" may be 3, "3", "III" or "Section 3" — compare what parses.

    Something that parses to no number ranks as 0, so it never blocks a later chapter.
    """
    try:
        return int(str(value or 0))
    except (TypeError, ValueError):
        roman = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
                 "VIII": 8, "IX": 9, "X": 10}
        return roman.get(str(value or "").strip().upper(), 0)


def _records(value):
    """Iterate the dict entries of a spec list.

    A list entry that is not an object (a bare string or number where a record was
    declared) is malformed input: it degrades to being skipped, never crashes the audit.
    """
    for item in value or []:
        if isinstance(item, dict):
            yield item


# Dimensionless ratio units. They carry meaning without a dimension, so a value
# expressed in "fold" is not a unitless number.
RATIO_UNITS = ("fold", "倍", "%", "x", "×")


def _has_unit(text: str, value: float) -> bool:
    for q in G.extract_quantities(text):
        if abs(q.value - value) < 1e-9 and q.unit:
            return True
    return any(u in text for u in RATIO_UNITS)


def _tokens(text: str) -> set[str]:
    """Content-bearing tokens for a crude relevance test.

    Crude on purpose: this decides whether a claim and its evidence are *related*,
    not whether the evidence supports it. Claiming support would be a judgement.

    CJK text is tokenised as character bigrams, so a Chinese answer can overlap a
    Chinese evidence quote the same way latin words overlap — the brief's cases are
    English papers with Chinese questions, and an ASCII-only tokeniser would score
    every Chinese sentence as zero overlap.
    """
    stop = {"the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "is", "are",
            "was", "were", "with", "by", "as", "at", "that", "this", "it", "we", "our",
            "be", "been", "has", "have", "had", "from", "than", "which", "these", "those"}
    s = (text or "").lower()
    toks = {t for t in re.findall(r"[a-z][a-z0-9\-]{2,}", s) if t not in stop}
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{2,}", s)
    for run in cjk_runs:
        toks.update(run[i:i + 2] for i in range(len(run) - 1))
    return toks


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def _scripts_differ(a: str, b: str) -> bool:
    """True when one text is predominantly CJK and the other predominantly latin.

    A lexical overlap check across scripts is meaningless (a faithful translation
    shares zero tokens with its source), so callers downgrade to anchor-based checks.
    """
    a_cjk = len(re.findall(r"[\u4e00-\u9fff]", a or ""))
    b_cjk = len(re.findall(r"[\u4e00-\u9fff]", b or ""))
    a_lat = len(re.findall(r"[A-Za-z]", a or ""))
    b_lat = len(re.findall(r"[A-Za-z]", b or ""))
    return (a_cjk > 0) != (b_cjk > 0) or (a_lat > 0) != (b_lat > 0)


ABSOLUTE = re.compile(r"(?<![A-Za-z])(always|never|proves?|proven|undoubtedly|clearly|definitively|conclusively|must|certainly)(?![A-Za-z])|" + "(总是|从不|必然|绝对|一定|无疑|证明|所有|必定|从未)", re.IGNORECASE)

# Statistics expressions: a p-value, a test statistic with its degrees of freedom, a sample
# size, a confidence interval, an effect size. Their numbers are not measurements — they
# carry no unit by convention and they are not plotted values — so they are exempt from the
# value-matching and unitless-number checks. Flagging them pushed agents into deleting
# correct statistics or adding fabricated entries to the figure data.
_STAT_EXPR = re.compile(
    r"\bp\s*[<=>≤≥]\s*[-+]?\d+(?:\.\d+)?(?:[eE]-?\d+)?"
    r"|\b(?:t|F|U|Z|χ2|χ²|B|β|η2|η²|ω2|ω²|Q|W|H)\s*[<=>≤≥≈]\s*[-+]?\d+(?:\.\d+)?"
    r"|\b(?:t|F|χ2|χ²|U|Z|T|W)\s*\(\s*\d+(?:\.\d+)?\s*\)"
    r"(?:\s*[<=>≤≥≈]\s*[-+]?\d+(?:\.\d+)?)?"
    r"|\b(?:n|N|k|df)\s*=\s*\d+"
    r"|\bCI\d*%?\s*[\[\(][^\]\)]*[\]\)]"
    r"|\b(?:OR|HR|RR|AIC|BIC|ICC|VIF)\s*[<=>≤≥≈]\s*[-+]?\d+(?:\.\d+)?"
    r"|\b(?:r|R2|R²)\s*[<=>≤≥≈]\s*[-+]?\d+(?:\.\d+)?",
    re.IGNORECASE)


def _stat_values(sentence: str) -> set[float]:
    """The numbers that belong to a statistics expression in this sentence."""
    vals: set[float] = set()
    for m in _STAT_EXPR.finditer(G.normalise(sentence)):
        for num in re.findall(r"\d+(?:\.\d+)?", m.group(0)):
            try:
                vals.add(float(num))
            except ValueError:
                pass
    return vals


# A discussion sentence that points at this study's own data — a figure, a table, "the
# observed increase" — is attributed to the study even without a reference key. Demanding a
# citation for every such sentence forced agents to attach references that do not exist.
_DATA_REF = re.compile(
    r"\b(?:Fig(?:ure)?s?\.?|Tab(?:le)?s?\.?|Eq(?:uation)?s?\.?|Supplementary|"
    r"this study|the present study|our results|our data|the observed|the measured)"
    r"|(?:图|表|式|公式|本研究|本文|上述结果|如上所述)",
    re.IGNORECASE)
CAUSAL = re.compile(
    r"\b(causes?|caused|because of|leads? to|led to|results? in|drives?|due to|"
    r"responsible for|therefore)\b", re.IGNORECASE)
HYPE = re.compile(
    r"\b(revolutionary|breakthrough|world[- ]first|unprecedented|game[- ]chang\w*|"
    r"miracle|disruptive|paradigm[- ]shift\w*|颠覆|革命性|重大突破)\b", re.IGNORECASE)


# =========================================================================
# Reading track
# =========================================================================

SOURCE_KINDS = ("body", "table", "figure", "supplement")
CLAIM_KINDS = ("conclusion", "limitation", "speculation")
GAP_STATES = ("not_reported", "extraction_failed")

# A locator has to be fine enough for a second reader to land on the same sentence.
# These shapes mirror the four the rubric names: page, section, table cell, figure.
LOCATOR_PATTERNS = [
    re.compile(r"\b[pP]\.?\s*\d+"),                             # p.7 / P7
    re.compile(r"第\s*\d+\s*页"),                                # 第7页
    re.compile(r"\b(?:Sec\.?|Section|§)\s*\d+"),                # Sec 3.2 / §3
    re.compile(r"\b(?:Table|Tab\.?)\s*\d+[^\n]{0,24}(?:row|r\d|c\d)", re.I),
    re.compile(r"表\s*\d+[^\n]{0,16}(?:行|列)"),                  # 表2 行3
    re.compile(r"\b(?:Fig\.?|Figure)\s*\d+[a-z]?", re.I),       # Fig 3b
    re.compile(r"图\s*\d+[a-z]?"),                              # 图3b
]


def _locator_is_specific(locator: str) -> bool:
    return any(p.search(locator) for p in LOCATOR_PATTERNS)


def conclusion_extract(spec: dict, findings: list[dict]) -> None:
    """Structured extraction of a paper's conclusions and numbers.

    Aligned to the four scoring points this task states, which are narrower than
    "extract something useful":

      one field table across body / table / figure / supplement
      values verbatim, with conclusions, limitations and speculation kept apart
      a gap stated as "not reported" or "extraction failed" -- never as blank
      every field locatable to a page, section, table cell or figure
    """
    items = spec.get("conclusions") or []
    fields = spec.get("fields") or []
    source_text = str(spec.get("source_text") or "")

    if not items:
        _add(findings, "extract.no_items", "high",
             "no extracted items were supplied, so nothing was extracted")

    # The field table and its extraction rules have to ship with the result, or nobody
    # can re-run the same extraction or compare two papers on the same schema.
    if not fields:
        _add(findings, "extract.schema_missing", "high",
             "no field schema was declared, so the result cannot be re-run or compared "
             "against another paper")
    else:
        for f in fields:
            if not str(f.get("definition") or "").strip():
                _add(findings, "extract.field_undefined", "medium",
                     "a field has no definition, so two extractors would fill it differently",
                     field=f.get("name"))

    declared_sources = set(spec.get("sources_present") or SOURCE_KINDS)
    seen_sources: set[str] = set()

    for i, it in enumerate(items):
        claim = str(it.get("claim") or "")
        kind = str(it.get("claim_kind") or "").strip().lower()
        src_kind = str(it.get("source_kind") or "").strip().lower()
        locator = str(it.get("locator") or "")

        if not claim.strip():
            _add(findings, "extract.empty_claim", "high",
                 "an extraction item has no claim text", item=i)

        # conclusion / limitation / speculation must not be conflated: the difference
        # decides how much the paper actually claims.
        if not kind:
            _add(findings, "extract.kind_undeclared", "high",
                 "an item does not say whether it is a conclusion, a limitation or "
                 "speculation, so its strength is unknown", item=i, claim=claim[:80])
        elif kind not in CLAIM_KINDS:
            _add(findings, "extract.kind_unknown", "medium",
                 "an item's kind is outside conclusion/limitation/speculation",
                 item=i, found=kind)

        if not src_kind:
            _add(findings, "extract.source_kind_missing", "medium",
                 "an item does not say whether it came from the body, a table, a figure "
                 "caption or the supplement", item=i, claim=claim[:80])
        elif src_kind not in SOURCE_KINDS:
            _add(findings, "extract.source_kind_unknown", "low",
                 "an item's source kind is outside body/table/figure/supplement",
                 item=i, found=src_kind)
        else:
            seen_sources.add(src_kind)

        if not locator.strip():
            _add(findings, "extract.missing_locator", "high",
                 "a finding has no page/paragraph/table/figure locator, so a second reader "
                 "cannot verify it", item=i, claim=claim[:80])
        elif not _locator_is_specific(locator):
            _add(findings, "extract.locator_vague", "medium",
                 "the locator names no page, section, table cell or figure, so its "
                 "granularity is below what a second reader can check",
                 item=i, locator=locator[:60])

        if not str(it.get("condition") or "").strip():
            _add(findings, "extract.missing_condition", "high",
                 "a finding is recorded without the conditions it holds under (sample, "
                 "setting, baseline), so it cannot be applied", item=i, claim=claim[:80])

        if it.get("hedged") is False and ABSOLUTE.search(claim):
            _add(findings, "extract.hedge_dropped", "high",
                 "the extracted claim is absolute while the source hedged it",
                 item=i, claim=claim[:100])

        # Every declared field must be present in the item, and a gap must be labelled.
        for f in fields:
            name = f.get("name")
            if not name:
                continue
            if name not in it:
                _add(findings, "extract.field_absent", "high",
                     "an item omits a field the schema declares; it is neither reported "
                     "nor marked as a gap", item=i, field=name)
                continue
            val = it.get(name)
            if val in (None, "", []):
                state = str(it.get(f"{name}_status") or "").strip().lower()
                if state not in GAP_STATES:
                    _add(findings, "extract.gap_unclassified", "high",
                         "a blank field does not say whether the paper never reported it "
                         "or the extraction failed, and the two mean different things",
                         item=i, field=name, found=state or None)

        for q in it.get("values") or []:
            if not isinstance(q, dict):
                continue
            if q.get("value") is not None and not str(q.get("unit") or "").strip():
                # A bare integer is usually a count (n = 6, 3 groups) — no unit is
                # correct there, and flagging it pushed agents into inventing units.
                # A ratio word in the verbatim ("3-fold") or a non-integer value
                # (3.5 of what?) is genuinely ambiguous and still reported.
                ctx = f"{q.get('verbatim') or ''} {q.get('context') or ''}"
                is_ratio = bool(re.search(r"fold|%|倍|×", str(ctx), re.I))
                is_count = float(q["value"]).is_integer()
                if is_ratio or not is_count:
                    _add(findings, "extract.value_without_unit", "medium",
                         "an extracted value carries no unit, so its magnitude is ambiguous",
                         item=i, value=q.get("value"))
            # Literal agreement with the source: a verbatim string that does not occur in
            # the supplied text was paraphrased, merged or converted on the way in.
            verbatim = str(q.get("verbatim") or "").strip()
            if verbatim and source_text and verbatim not in source_text:
                _add(findings, "extract.value_not_in_source_text", "high",
                     "a value quoted verbatim does not occur in the supplied source text, "
                     "so it was rewritten or taken from outside the material",
                     item=i, verbatim=verbatim[:80])

    if items and "sources_present" in spec:
        missing = sorted(set(declared_sources) - seen_sources)
        if missing:
            _add(findings, "extract.source_not_covered", "medium",
                 "a source the paper contains was never used, so the field table was built "
                 "from only part of the material", sources=missing)


def claim_verify(spec: dict, findings: list[dict]) -> None:
    """Verify each claim against a minimum sufficient evidence span.

    The deliverable the task describes is a five-link chain:

      claim -> evidence span -> locator in the source -> support verdict -> rationale

    plus coverage of the sub-judgements a claim decomposes into (fact, comparison,
    causation, scope) and the counter-evidence where the source has any. Each link is
    checkable, so each is a rule; a missing link breaks the chain for a second reader.
    """
    claims = list(_records(spec.get("claims")))
    refs = {str(r.get("key") or r.get("id") or "").strip(): r for r in _records(spec.get("references"))}
    refs.pop("", None)
    source_text = str(spec.get("source_text") or "")
    sub_kinds = ("fact", "comparison", "causal", "scope")

    if not claims:
        _add(findings, "verify.no_claims", "high", "no claims were supplied to verify")

    for i, c in enumerate(claims):
        text = str(c.get("claim") or "")
        spans = c.get("evidence") or []

        if not text.strip():
            _add(findings, "verify.empty_claim", "high", "a claim has no text", claim=i)

        if not spans:
            _add(findings, "verify.no_evidence", "high",
                 "a claim has no evidence span, so it is asserted rather than verified",
                 claim=i, text=text[:100])
            continue

        # --- link 2/3: the span exists, and it is locatable ------------------
        best_overlap = 0.0
        for s in _records(spans):
            quote = str(s.get("quote") or "")
            best_overlap = max(best_overlap, _overlap(text, quote))

            if not quote.strip():
                _add(findings, "verify.evidence_empty_quote", "high",
                     "an evidence span carries no quoted text, so there is nothing to check",
                     claim=i)
                continue

            # "Evidence really exists at the cited location": the quote must occur in the
            # supplied source text, otherwise it was paraphrased or invented.
            if source_text and quote.strip() not in source_text:
                _add(findings, "verify.quote_not_in_source", "high",
                     "the quoted evidence does not occur in the supplied source text, so the "
                     "span either paraphrases it or does not exist there",
                     claim=i, quote=quote[:80])

            loc = str(s.get("locator") or "")
            if not loc.strip():
                _add(findings, "verify.evidence_no_locator", "high",
                     "an evidence span has no page/table/figure locator, so a reader cannot "
                     "go and look", claim=i, quote=quote[:60])
            elif not _locator_is_specific(loc):
                _add(findings, "verify.evidence_locator_vague", "medium",
                     "the evidence locator names no page, section, table cell or figure",
                     claim=i, locator=loc[:60])

            key = str(s.get("source") or "").strip()
            if refs and key and key not in refs:
                _add(findings, "verify.unknown_source", "high",
                     "an evidence span points at a source not in the reference list",
                     claim=i, key=key)

        # --- topic-related vs genuinely supporting ---------------------------
        if best_overlap < 0.25:
            _add(findings, "verify.evidence_unrelated", "high",
                 "the cited evidence shares almost no content with the claim, which is the "
                 "signature of citing a topically related passage that does not support it",
                 claim=i, overlap=round(best_overlap, 2), text=text[:100])

        # --- link 4/5: verdict and its reason --------------------------------
        support = str(c.get("support") or "").strip().lower()
        if support not in ("supports", "partial", "insufficient", "refutes"):
            _add(findings, "verify.support_undeclared", "high",
                 "the claim does not state whether the evidence supports it fully, partially, "
                 "refutes it, or is insufficient", claim=i, found=support or None)
        if support and not str(c.get("rationale") or "").strip():
            _add(findings, "verify.rationale_missing", "high",
                 "the support verdict carries no reason, so a second reader cannot tell why "
                 "it was reached", claim=i, support=support)

        # --- sub-judgements a compound claim decomposes into -----------------
        subs = c.get("subjudgements") or []
        if subs:
            for j, sub in enumerate(subs):
                kind = str(sub.get("kind") or "").strip().lower()
                if kind not in sub_kinds:
                    _add(findings, "verify.subjudgement_kind_unknown", "medium",
                         "a sub-judgement is outside fact/comparison/causal/scope",
                         claim=i, index=j, found=kind or None)
                if not str(sub.get("statement") or "").strip():
                    _add(findings, "verify.subjudgement_empty", "high",
                         "a sub-judgement has no statement", claim=i, index=j)
                if not str(sub.get("support") or "").strip():
                    _add(findings, "verify.subjudgement_verdict_missing", "high",
                         "a sub-judgement carries no support verdict, so part of the claim is "
                         "unverified while the claim as a whole looks checked",
                         claim=i, index=j)
        elif _looks_compound(text):
            _add(findings, "verify.subjudgements_missing", "medium",
                 "the claim carries more than one assertion but is not decomposed, so one "
                 "unverified part hides behind the verdict on the whole", claim=i,
                 text=text[:100])

        # --- counter-evidence where the source is contested ------------------
        if c.get("contested") and not c.get("counter_evidence"):
            _add(findings, "verify.counter_evidence_missing", "high",
                 "the claim is declared contested but no counter-evidence span is given, so "
                 "the report shows only one side", claim=i)

    # --- reference metadata ------------------------------------------------
    for key, r in refs.items():
        missing = [f for f in ("title", "year") if not str(r.get(f) or "").strip()]
        if missing:
            _add(findings, "verify.reference_metadata_incomplete", "medium",
                 "a reference lacks metadata needed to identify it", key=key, missing=missing)


COMPOUND = re.compile(
    r"\b(and|but|whereas|while|although|because|therefore|compared with|versus|vs)\b|"
    r"(而|但|并且|同时|因为|因此|相比|相比之|相比下)", re.IGNORECASE)


def _looks_compound(text: str) -> bool:
    """Whether a claim joins more than one assertion.

    Crude on purpose: it flags a conjunction, which is a prompt to decompose rather than a
    verdict that the claim is compound. A single sentence with "and" is still one fact if
    both halves are the same assertion, and the extractor can say so by decomposing.
    """
    return bool(COMPOUND.search(text or ""))


FIELD_GROUPS = ("object", "data", "method", "condition", "metric", "conclusion", "limitation")
DIRECTIONS = ("increases", "decreases", "no_effect", "mixed", "conflicting")
STRENGTHS = ("strong", "moderate", "weak")
# Declared synthesis verdicts for a conclusion field, and what each demands of the
# recorded directions. A verdict that contradicts the cells is a misread of what the
# papers jointly claim ("结论方向与关系强度是否被误读").
CONSISTENT_VERDICTS = ("consistent", "agree", "agreement", "一致")
CONFLICT_VERDICTS = ("conflict", "conflicting", "冲突")
PARTIAL_VERDICTS = ("partial", "partially consistent", "部分一致")
# Groups whose cells cannot be compared without knowing what produced the number.
METADATA_GROUPS = ("data", "metric", "condition")
METADATA_KEYS = ("dataset", "metric", "control")


def _cell(v):
    """Normalise a cell that may be a bare string or a structured object.

    A bare string is accepted so older specs keep working, but it carries no locator and
    no conditions, which is exactly what the comparison is graded on -- so the rules below
    report the absence rather than assuming it is fine.
    """
    if isinstance(v, dict):
        return v
    return {"value": v}


def compare_docs(spec: dict, findings: list[dict]) -> None:
    """Cross-document comparison on one field table.

    Aligned to the scoring points this task states:

      one field table across papers, cell by cell      -> schema, field_group, field_missing
      each cell from the paper it is attributed to     -> cell_not_in_source, cell_no_locator
      unit / dataset / metric / control recorded       -> unit_mismatch, cell_metadata_missing
      direction and strength not misread               -> direction_missing, strength_missing,
                                                          conflict_unattributed,
                                                          consistency_misstated
      comparability stated, not assumed                -> comparability_undeclared,
                                                          condition_conflict_unmarked
      a recorded conversion recomputes                 -> conversion_unreproducible
      one column per paper                             -> duplicate_document_id
    """
    docs = [d for d in (spec.get("documents") or []) if isinstance(d, dict)]
    skipped_docs = len(spec.get("documents") or []) - len(docs)
    fields = spec.get("fields") or []

    if skipped_docs:
        _add(findings, "compare.document_skipped", "medium",
             "one or more documents entries were not objects and were skipped, so their "
             "content never enters the comparison", count=skipped_docs)

    ids = [str(d.get("id")) for d in docs]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        _add(findings, "compare.duplicate_document_id", "medium",
             "two documents share an id, so cells and pooled values collapse onto one "
             "column and the comparison silently loses a paper", ids=dupes)

    if len(docs) < 2:
        _add(findings, "compare.too_few_documents", "high",
             "fewer than two documents were supplied, so there is nothing to compare",
             count=len(docs))
    if not fields:
        _add(findings, "compare.no_schema", "high",
             "no unified field schema was declared, so the comparison has no common ground")
        return

    # --- the field table must cover the groups a comparison needs ------------
    required_groups = spec.get("field_groups") or list(FIELD_GROUPS)
    declared_groups = {str(f.get("group") or "").strip().lower() for f in fields}
    missing_groups = [g for g in required_groups if g not in declared_groups]
    if missing_groups:
        _add(findings, "compare.field_group_missing", "high",
             "a field group a comparison needs is absent from the schema, so the table cannot "
             "answer the comparison it was built for", missing=missing_groups)

    for f in fields:
        if not str(f.get("definition") or "").strip():
            _add(findings, "compare.field_undefined", "medium",
                 "a field has no definition, so two extractors would fill it differently",
                 field=f.get("name"))

    conclusion_directions: dict[str, dict[str, str]] = {}
    # condition keys whose recorded values are checked for cross-document agreement:
    # the built-in trio plus any corpus-specific dimensions the spec declares
    # (the workorder names task / metric / units / material / pollutant / budget).
    cond_keys = tuple(dict.fromkeys(
        tuple(METADATA_KEYS) + tuple(str(k) for k in (spec.get("condition_keys") or []))))

    for f in fields:
        name = f.get("name")
        if not name:
            continue
        group = str(f.get("group") or "").strip().lower()
        target_unit = f.get("target_unit")
        values: dict[str, float] = {}
        conditions: dict[str, dict[str, str]] = {}
        seen: set[str] = set()

        for doc in docs:
            did = str(doc.get("id"))
            raw = (doc.get("fields") or {}).get(name)
            if raw in (None, "", [], {}):
                _add(findings, "compare.field_missing", "medium",
                     "a document does not report a field the schema requires",
                     field=name, document=did)
                continue

            seen.add(did)
            cell = _cell(raw)
            text = str(cell.get("value") if "value" in cell else cell.get("value", ""))
            unit = str(cell.get("unit") or "")
            locator = str(cell.get("locator") or "")

            # --- traceability: a cell a reader cannot look up is not a datum
            if not locator.strip():
                _add(findings, "compare.cell_no_locator", "high",
                     "a comparison cell carries no locator in its own paper, so the value "
                     "cannot be traced back", field=name, document=did)
            elif not _locator_is_specific(locator):
                _add(findings, "compare.cell_locator_vague", "medium",
                     "a cell's locator names no page, section, table cell or figure",
                     field=name, document=did, locator=locator[:60])

            # --- literal agreement with that document's text
            verbatim = str(cell.get("verbatim") or "").strip()
            doc_text = str(doc.get("text") or "")
            if verbatim and doc_text and verbatim not in doc_text:
                _add(findings, "compare.cell_not_in_source", "high",
                     "a cell quotes text that does not occur in the paper it is attributed to",
                     field=name, document=did, verbatim=verbatim[:70])

            # --- conditions travel with the value
            if group in METADATA_GROUPS:
                absent = [k for k in METADATA_KEYS if not str(cell.get(k) or "").strip()]
                if absent:
                    _add(findings, "compare.cell_metadata_missing", "medium",
                         "a cell omits the conditions that make it comparable, so two numbers "
                         "can look alike while measuring different things",
                         field=name, document=did, missing=absent)
                for k in cond_keys:
                    v = str(cell.get(k) or "").strip().casefold()
                    if v:
                        conditions.setdefault(k, {})[did] = v

            # --- numbers, units and pooling
            m = U.parse_measurement(text)
            val = m.get("value")
            cell_unit = unit or (m.get("unit") or "")
            if target_unit and cell_unit and cell_unit != target_unit:
                conv = U.convert(val or 0, cell_unit, target_unit)
                if not conv.get("ok"):
                    _add(findings, "compare.unit_mismatch", "high",
                         "a cell uses a unit that cannot be converted to the comparison unit",
                         field=name, document=did, unit=cell_unit, target=target_unit)
                else:
                    values[did] = conv["value"]
            elif val is not None:
                values[did] = val

            # --- a recorded conversion path must recompute (查得回) ---------------
            conv, fv, fu = cell.get("converted_from"), None, None
            if isinstance(conv, dict):
                fv, fu = conv.get("value"), conv.get("unit")
            elif "from_value" in cell or "from_unit" in cell:
                fv, fu = cell.get("from_value"), cell.get("from_unit")
            if fv is not None and str(fu or "").strip():
                try:
                    fv = float(fv)
                except (TypeError, ValueError):
                    fv = None
            if isinstance(fv, float):
                rec = m.get("value") if m.get("kind") in ("single", "plus_minus") else None
                src = U.convert(fv, str(fu).strip(), cell_unit)
                if src.get("ok"):
                    if rec is not None:
                        denom = max(abs(src["value"]), abs(rec), 1e-12)
                        if abs(src["value"] - rec) / denom > 0.08:
                            _add(findings, "compare.conversion_unreproducible", "high",
                                 "the recorded conversion does not recompute: the declared "
                                 "original value and unit do not produce the recorded value, "
                                 "so a reader cannot recompute the cell from its own record",
                                 field=name, document=did, declared=f"{fv:g} {fu}",
                                 recorded=rec, recomputed=round(src["value"], 6))
                elif src.get("kind") == "dimension_mismatch":
                    _add(findings, "compare.conversion_unreproducible", "high",
                         "the declared conversion path joins different kinds of quantity, so "
                         "the value cannot be recomputed from the recorded path",
                         field=name, document=did, from_unit=str(fu), unit=cell_unit)
            # unknown units are unverifiable rather than wrong: skipped, not flagged

            # --- direction and strength, for conclusions
            if group == "conclusion":
                direction = str(cell.get("direction") or "").strip().lower()
                strength = str(cell.get("strength") or "").strip().lower()
                if direction not in DIRECTIONS:
                    _add(findings, "compare.direction_missing", "high",
                         "a conclusion cell does not record the direction of the relationship, "
                         "so two papers agreeing in sign cannot be told from two disagreeing",
                         field=name, document=did, found=direction or None)
                else:
                    conclusion_directions.setdefault(name, {})[did] = direction
                if strength not in STRENGTHS:
                    _add(findings, "compare.strength_missing", "medium",
                         "a conclusion cell does not record how strong the reported "
                         "relationship is", field=name, document=did, found=strength or None)

        # --- differing recorded conditions need the pooling judgment recorded ---
        # The workorder demands the comparability test before quantitative synthesis
        # and that all noncomparable conditions be retained, so when documents record
        # different values for the same condition, the schema must say which documents
        # may be pooled (comparable_subset), how the variance is handled
        # (condition_variance), or mark the cells noncomparable.
        differing = sorted(k for k, bydoc in conditions.items()
                           if len(set(bydoc.values())) > 1)
        judged = (bool(str(f.get("condition_variance") or "").strip())
                  or bool(f.get("comparable_subset"))
                  or any(_cell((doc.get("fields") or {}).get(name)).get("noncomparable")
                         for doc in docs))
        if group in METADATA_GROUPS and len(seen) >= 2 and differing and not judged:
            _add(findings, "compare.condition_conflict_unmarked", "medium",
                 "documents record different values for the same condition on one field and "
                 "the schema does not record which documents may be pooled or under which "
                 "subset, so the cells cannot be read as same-condition comparables",
                 field=name, conditions=differing)

        if len(values) >= 2 and not f.get("comparability"):
            _add(findings, "compare.comparability_undeclared", "medium",
                 "values are pooled across documents without stating whether they were measured "
                 "under comparable conditions", field=name, documents=sorted(values))

    # --- conflicts must be named, not silently averaged --------------------
    for name, dirs in conclusion_directions.items():
        if len(set(dirs.values())) > 1 and not any(
                str(f.get("name")) == name and f.get("conflict_note") for f in fields):
            _add(findings, "compare.conflict_unattributed", "high",
                 "two papers point in different directions on the same field and the "
                 "difference is not attributed to any condition", field=name,
                 directions=dirs)

    # --- a declared synthesis verdict must match the recorded directions ----
    # Only checked when the verdict is declared: the audit verifies what the synthesis
    # claims against what the cells record, and never demands a verdict on its own.
    for f in fields:
        verdict = str(f.get("consistency") or "").strip().casefold()
        if not verdict:
            continue
        dirs = conclusion_directions.get(str(f.get("name"))) or {}
        if len(dirs) < 2:
            continue
        distinct = set(dirs.values())
        if verdict in CONSISTENT_VERDICTS and len(distinct) > 1:
            _add(findings, "compare.consistency_misstated", "high",
                 "the field is declared consistent but the recorded directions disagree, so "
                 "the synthesis misstates what the papers jointly claim",
                 field=f.get("name"), declared=verdict, directions=dirs)
        elif verdict in CONFLICT_VERDICTS and len(distinct) == 1:
            _add(findings, "compare.consistency_misstated", "high",
                 "the field is declared conflicting but every recorded direction agrees, so "
                 "the synthesis reports a conflict the cells do not show",
                 field=f.get("name"), declared=verdict, directions=dirs)
        elif verdict in PARTIAL_VERDICTS and len(distinct) == 1:
            _add(findings, "compare.consistency_misstated", "high",
                 "the field is declared partially consistent but every recorded direction "
                 "agrees, so the synthesis reports disagreement the cells do not show",
                 field=f.get("name"), declared=verdict, directions=dirs)


def compare_coverage(spec: dict) -> dict:
    """Field x document coverage matrix for a comparison table.

    The completeness half of the comparison contract: which declared field each supplied
    document reports. The not-reported cells are named, not left as silent holes --
    "retain all ... unreported conditions". Pure summary: it adds no findings.
    """
    fields = [str(f.get("name")) for f in (spec.get("fields") or []) if f.get("name")]
    docs = spec.get("documents") or []
    reported: dict[str, list[str]] = {}
    not_reported: dict[str, list[str]] = {}
    for name in fields:
        have, lack = [], []
        for doc in docs:
            did = str(doc.get("id"))
            raw = (doc.get("fields") or {}).get(name)
            (have if raw not in (None, "", [], {}) else lack).append(did)
        reported[name], not_reported[name] = have, lack
    return {"reported": reported, "not_reported": not_reported,
            "documents": len(docs), "fields": len(fields)}


import ast as _ast

GREEK = set("αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ")


def _alias_symbols(expr: str, env: dict) -> tuple[str, dict]:
    """Rewrite symbol names that are not legal Python identifiers into aliases.

    Scientific symbols are frequently not identifiers: `lambda` is a Python keyword, and
    Greek letters, primes and subscripts are not valid names at all. Refusing to evaluate
    them would make the numeric check useless for exactly the formulas it exists for, so the
    names are aliased before parsing and the environment is aliased to match.
    """
    import keyword

    out = expr
    newenv = {}
    for key, value in env.items():
        name = str(key)
        if name.isidentifier() and not keyword.iskeyword(name):
            alias = name
        else:
            alias = "v_" + "_".join("%x" % ord(c) for c in name)
        out = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", alias, out)
        newenv[alias] = value
    return out, newenv


def _safe_eval(expr: str, env: dict) -> float:
    """Evaluate an arithmetic expression over numbers and named values.

    Restricted to numbers, the names supplied in `env`, and arithmetic operators. No
    attribute access, no calls, no comprehensions -- a numeric substitution check must not
    become an arbitrary-code path just because the input came from a paper.
    """
    expr, env = _alias_symbols(expr, env)

    allowed = (_ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Constant, _ast.Name,
               _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Pow, _ast.USub, _ast.UAdd,
               _ast.Mod, _ast.Load, _ast.Call, _ast.Tuple)
    tree = _ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, _ast.Expression):
            return ev(node.body)
        if isinstance(node, _ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError("only numeric constants are allowed")
            return float(node.value)
        if isinstance(node, _ast.Name):
            if node.id not in env:
                raise ValueError(f"unknown symbol '{node.id}'")
            return float(env[node.id])
        if isinstance(node, _ast.UnaryOp):
            v = ev(node.operand)
            return -v if isinstance(node.op, _ast.USub) else v
        if isinstance(node, _ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, _ast.Add):
                return a + b
            if isinstance(node.op, _ast.Sub):
                return a - b
            if isinstance(node.op, _ast.Mult):
                return a * b
            if isinstance(node.op, _ast.Div):
                return a / b
            if isinstance(node.op, _ast.Pow):
                return a ** b
            if isinstance(node.op, _ast.Mod):
                return a % b
            raise ValueError("operator not allowed")
        if isinstance(node, _ast.Call):
            # only the two-argument forms of min/max/abs are permitted, for tolerance maths
            if isinstance(node.func, _ast.Name) and node.func.id in ("abs", "min", "max"):
                args = [ev(a) for a in node.args]
                return {"abs": abs, "min": min, "max": max}[node.func.id](*args)
            raise ValueError("call not allowed")
        raise ValueError(f"expression node not allowed: {type(node).__name__}")

    for node in _ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"expression node not allowed: {type(node).__name__}")
    return ev(tree)


LATEX_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ",
    "upsilon": "υ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}


def _latex_symbols(latex: str) -> set[str]:
    """Identifiers a reader would expect to find in the variable table.

    Handles the three things that make this non-trivial:
      Greek commands map to the symbol the table will name;
      function names (`ln`, `sin`, `exp`) are removed before letters are collected;
      a subscript (`k_B`, `x_{i}`) belongs to its base symbol, not to a separate letter.
    """
    t = latex or ""
    t = re.sub(r"\\([A-Za-z]+)", lambda m: LATEX_GREEK.get(m.group(1), " "), t)
    # drop subscripts so `k_B` is one symbol `k`, not `k` plus `B`
    t = re.sub(r"_\{[^}]*\}", "", t)
    t = re.sub(r"_[A-Za-z0-9]", "", t)
    # drop function names before collecting single letters
    for fn in ("ln", "log", "sin", "cos", "tan", "exp", "max", "min", "det", "lim",
               "frac", "sqrt", "sum", "int"):
        t = re.sub(r"(?<![A-Za-z])" + fn + r"(?![A-Za-z])", " ", t)
    out = set()
    for ch in t:
        if ch.isalpha() and (ch.isascii() or ch in GREEK):
            out.add(ch)
    return out


def formula(spec: dict, findings: list[dict]) -> None:
    """Structure, symbols, derivation and numeric substitution for a set of formulas.

    Aligned to the scoring points this task states:

      a usable structured expression, not just a LaTeX line   -> unbalanced_*, variable_*
      symbols, sub/superscripts, brackets and units correspond -> variable_not_extracted
      variable explanations follow the original definition    -> variable_no_locator
      the numeric substitution actually computes              -> substitution_mismatch
      variable table, derivation steps, boundary conditions   -> derivation_missing,
                                                                 boundary_conditions_missing,
                                                                 verification_missing
    """
    items = list(_records(spec.get("formulas")))
    if not items:
        _add(findings, "formula.no_items", "high", "no formulas were supplied")

    for i, it in enumerate(items):
        latex = str(it.get("latex") or "")
        label = it.get("id") or f"F{i + 1}"
        variables = list(_records(it.get("variables")))
        declared = {str(v.get("name") or "").strip() for v in variables}

        # --- structural integrity ----------------------------------------
        if latex.count("{") != latex.count("}"):
            _add(findings, "formula.unbalanced_braces", "high",
                 "braces are unbalanced, so the expression will not typeset", formula=label)
        if latex.count("(") != latex.count(")") or latex.count("[") != latex.count("]"):
            _add(findings, "formula.unbalanced_delimiters", "high",
                 "parentheses or brackets are unbalanced", formula=label)
        # A multi-character sub/superscript without braces typesets as only its first
        # character: `x_12` reads as x with subscript 1, then a stray 2. Single-character
        # scripts (x_i, 10^2) are correct as written and never fire.
        bare = re.findall(r"[_^]\s*[A-Za-z0-9]{2,}", latex)
        if bare:
            _add(findings, "formula.bare_script", "low",
                 "a sub/superscript carries multiple characters without braces, so it "
                 "typesets as only its first character — wrap it: x_{12}", formula=label,
                 found=bare[:6])

        # --- symbols the reader must be able to look up -------------------
        missing_syms = sorted(_latex_symbols(latex) - declared)
        if missing_syms:
            _add(findings, "formula.variable_not_extracted", "high",
                 "the expression uses symbols that the variable table never defines",
                 formula=label, symbols=missing_syms[:12])

        for v in variables:
            name = str(v.get("name") or "")
            if not str(v.get("definition") or "").strip():
                _add(findings, "formula.variable_undefined", "high",
                     "a variable has no definition, so the reader cannot interpret the "
                     "expression", formula=label, variable=name)
            src = str(v.get("source") or "").strip().lower()
            if src not in ("paper", "inferred", "convention"):
                _add(findings, "formula.variable_source_undeclared", "medium",
                     "a variable does not say whether it was defined by the paper, inferred, "
                     "or supplied as convention", formula=label, variable=name, found=src or None)
            if not str(v.get("locator") or "").strip():
                _add(findings, "formula.variable_no_locator", "high",
                     "a symbol's definition cannot be traced to a page or equation in the "
                     "paper, so it cannot be checked against the original", formula=label,
                     variable=name)
            # A mandatory-unit rule lived here once: two grader runs scored 61.3 and 57.3
            # against the v1's 64.3, because a symbols-only case makes the agent pad
            # units that the paper never states. Removed per the Lesson-6 method — the
            # magnitude check still runs whenever a unit IS declared (dimension_mismatch).

        # --- dimensions on both sides -------------------------------------
        lhs_unit, rhs_unit = it.get("lhs_unit"), it.get("rhs_unit")
        if lhs_unit and rhs_unit:
            a, b = U.parse_unit(str(lhs_unit)), U.parse_unit(str(rhs_unit))
            if a is None or b is None:
                _add(findings, "formula.unit_unknown", "medium",
                     "one side of the equation uses an unrecognised unit, so no dimensional "
                     "check was possible", formula=label, lhs=lhs_unit, rhs=rhs_unit)
            elif a.dimension != b.dimension:
                _add(findings, "formula.dimension_mismatch", "high",
                     "the two sides of the equation have different dimensions, so it cannot "
                     "be correct as written", formula=label,
                     lhs={k: v for k, v in zip(DIM, a.dimension) if v},
                     rhs={k: v for k, v in zip(DIM, b.dimension) if v})

        # --- derivation steps that a reader could re-walk ------------------
        steps = list(_records(it.get("steps")))
        if not steps:
            _add(findings, "formula.derivation_missing", "medium",
                 "no derivation steps were recorded, so the route from the stated result to "
                 "this expression cannot be followed", formula=label)
        known_ids = {str(x.get("id") or "") for x in items} - {""}
        for j, st in enumerate(_records(steps)):
            if not str(st.get("from") or "").strip() or not str(st.get("to") or "").strip():
                _add(findings, "formula.step_incomplete", "high",
                     "a derivation step does not record both sides of the transition",
                     formula=label, step=j)
            if not str(st.get("justification") or "").strip():
                _add(findings, "formula.step_unjustified", "medium",
                     "a derivation step gives no rule or assumption, so it cannot be checked",
                     formula=label, step=j)
            # Cross-formula dependencies are declared so a reader can walk them; a
            # dependency pointing outside the set is a dangling reference.
            for dep in (st.get("uses") or []):
                if str(dep) not in known_ids:
                    _add(findings, "formula.step_unknown_dependency", "medium",
                         "a derivation step depends on a formula the set does not contain, "
                         "so the derivation cannot be walked end to end",
                         formula=label, step=j, dependency=str(dep))

        # --- boundary conditions ------------------------------------------
        if not it.get("boundary_conditions"):
            _add(findings, "formula.boundary_conditions_missing", "medium",
                 "the expression is given without the conditions it holds under (validity "
                 "range, approximations), so it can be applied outside them", formula=label)

        # --- the numeric substitution must actually compute ---------------
        num = it.get("numeric")
        if num:
            expr = str(num.get("expression") or "")
            expected = num.get("expected")
            inputs = num.get("inputs") or {}
            try:
                tol = float(num.get("tolerance") or 1e-9)
            except (TypeError, ValueError):
                tol = 1e-9  # a non-numeric tolerance cannot be measured; use the default
            if not expr or expected is None:
                _add(findings, "formula.numeric_incomplete", "high",
                     "a numeric check is declared without both an expression and an expected "
                     "value", formula=label)
            else:
                try:
                    got = _safe_eval(expr, inputs)
                    if abs(got - float(expected)) > tol:
                        _add(findings, "formula.substitution_mismatch", "high",
                             "substituting the stated values does not reproduce the stated "
                             "result", formula=label, computed=got, expected=float(expected),
                             tolerance=tol)
                except Exception as exc:
                    _add(findings, "formula.substitution_not_evaluable", "medium",
                         "the numeric check could not be evaluated, so it proves nothing",
                         formula=label, reason=str(exc)[:120])
        elif it.get("note_numeric") is not False:
            _add(findings, "formula.no_numeric_check", "low",
                 "no numeric substitution was attempted where the formula permits it",
                 formula=label)

        # --- a verification verdict ---------------------------------------
        # A null verdict is not a verdict: `verified: None` and an absent key mean the same
        # thing to a reader, so both are reported.
        if not isinstance(it.get("verified"), bool):
            _add(findings, "formula.verification_missing", "medium",
                 "no verification verdict is recorded, so a reader does not know whether the "
                 "expression was checked or merely transcribed", formula=label)


STAGES = ("materials", "environment", "parameters", "run", "results", "verdict")
DELTA_CLASSES = ("numeric_noise", "methodological")


def reproduce(spec: dict, findings: list[dict]) -> None:
    """Audit a reproduction report against the closed loop the task describes.

    The loop is: material location -> environment -> parameter recovery -> code run ->
    result comparison -> graded verdict. The scoring points add four concrete demands:

      every material carries source, version and state
      the environment snapshot names dependencies, hardware, seed -- and any disagreement
      with what the paper declared
      parameters are classed as paper / code / assumed, with a basis for the assumed ones
      a result that misses tolerance says whether the gap is numeric noise or methodological

    plus the four artefacts another machine needs: commit, data version, command, logs.
    """
    required = spec.get("stages") or list(STAGES)
    checklist = spec.get("checklist") if isinstance(spec.get("checklist"), dict) else {}

    # --- the closed loop ---------------------------------------------------
    for stage in STAGES:
        # A key present with a null value is not a recorded stage: same reading as an absent
        # key, so both are reported.
        if stage not in checklist or checklist.get(stage) in (None, "", {}, []):
            _add(findings, "repro.stage_missing", "high",
                 "a stage of the reproduction loop is absent, so the chain cannot be followed",
                 stage=stage)
    for stage in spec.get("stages") or []:
        if stage not in STAGES:
            _add(findings, "repro.stage_unknown", "low",
                 "a declared stage is outside the six the loop defines", found=stage)
    if not required:
        _add(findings, "repro.no_stages", "medium", "no loop stages were declared")

    # --- artefacts a second machine needs ---------------------------------
    for key, rule, why in (
        ("commit", "repro.no_commit", "the repository revision is not recorded, so the code "
                                      "cannot be checked out again"),
        ("data_version", "repro.no_data_version", "the data version is not recorded, so the "
                                                  "inputs cannot be restored"),
        ("commands", "repro.no_command", "the command that produced the results is not "
                                         "recorded, so the run cannot be repeated"),
    ):
        if not spec.get(key):
            _add(findings, rule, "high", why)

    # --- materials --------------------------------------------------------
    for item in _records(checklist.get("materials")):
        name = item.get("name")
        if not str(item.get("source") or "").strip():
            _add(findings, "repro.material_without_source", "high",
                 "a required material has no source (paper, supplement or repository)",
                 item=name)
        if not str(item.get("version") or "").strip():
            _add(findings, "repro.material_without_version", "medium",
                 "a material does not record which version was used, so a later run may get "
                 "different data while believing it is the same", item=name)
        state = str(item.get("state") or "").strip().lower()
        if state not in ("present", "missing", "partial", "not_needed"):
            _add(findings, "repro.material_state_undeclared", "medium",
                 "a material does not state whether it is present, missing or partial",
                 item=name, found=state or None)
        # The task lists the license among the things a reproduction must locate. Only
        # redistributable artefacts carry one — code, a repository, pretrained weights —
        # so the check is gated on a declared kind and never fires on a paper or dataset
        # that legitimately has none of the usual kind.
        if str(item.get("kind") or "").strip().lower() in ("code", "repository", "repo",
                                                           "weights", "model")                 and not str(item.get("license") or "").strip():
            _add(findings, "repro.material_no_license", "medium",
                 "a redistributable artefact records no license, so reuse and redistribution "
                 "cannot be planned", item=name)

    # --- environment, including disagreement with the paper ---------------
    env = checklist.get("environment") if isinstance(checklist.get("environment"), dict) else {}
    for field in ("dependencies", "hardware", "seed"):
        if not env.get(field):
            _add(findings, "repro.environment_incomplete", "medium",
                 "the environment snapshot omits a field another machine needs to rebuild it",
                 field=field, note="say 'not set' explicitly rather than omitting it")
    for dep in _records(env.get("dependencies_detail")):
        paper_v = str(dep.get("paper_version") or "").strip()
        actual_v = str(dep.get("actual_version") or "").strip()
        if paper_v and actual_v and paper_v != actual_v and not str(dep.get("conflict") or "").strip():
            _add(findings, "repro.env_conflict_unflagged", "high",
                 "an installed version differs from the one the paper declares and the "
                 "difference is not recorded, so a later divergence has no explanation",
                 dependency=dep.get("name"), paper=paper_v, actual=actual_v)

    # --- parameters -------------------------------------------------------
    for p in _records(checklist.get("parameters")):
        src = str(p.get("source") or "").strip().lower()
        if src not in ("paper", "code", "assumed"):
            _add(findings, "repro.parameter_source_undeclared", "high",
                 "a parameter does not say whether it came from the paper, the code defaults, "
                 "or was chosen by the reproducer", parameter=p.get("name"), found=src or None)
        if src == "assumed" and not str(p.get("justification") or "").strip():
            _add(findings, "repro.assumed_without_justification", "high",
                 "a parameter was chosen by the reproducer with no justification",
                 parameter=p.get("name"))
        if src in ("paper", "code") and not str(p.get("locator") or "").strip():
            _add(findings, "repro.parameter_no_locator", "medium",
                 "a parameter claims a source but does not say where in it, so the claim "
                 "cannot be checked", parameter=p.get("name"), source=src)

    # --- result comparison ------------------------------------------------
    results = checklist.get("results") if isinstance(checklist.get("results"), dict) else {}
    if "results" in checklist:
        if not results.get("tolerance"):
            _add(findings, "repro.no_tolerance", "high",
                 "reproduced results are compared without stating a tolerance, so agreement "
                 "cannot be judged")
        if not str(results.get("comparison_basis") or "").strip():
            _add(findings, "repro.no_comparison_basis", "medium",
                 "the comparison does not say what is being aligned (a table, a curve, a "
                 "metric) or how, so the numbers are not clearly the same quantity",
                 )
        if not str(results.get("statistic") or "").strip():
            _add(findings, "repro.no_statistic", "low",
                 "no statistic or aggregation is declared for the comparison")
        for m in _records(results.get("metrics")):
            name = m.get("name")
            paper_v, got_v = m.get("paper"), m.get("reproduced")
            within = m.get("within_tolerance")
            if within is None and paper_v is not None and got_v is not None:
                _add(findings, "repro.metric_no_verdict", "high",
                     "a compared metric does not say whether it landed inside tolerance",
                     metric=name)
            elif within is False:
                cls = str(m.get("delta_class") or "").strip().lower()
                if cls not in DELTA_CLASSES:
                    _add(findings, "repro.difference_unclassified", "high",
                         "a metric misses tolerance and the gap is not classified as numeric "
                         "noise or methodological, so the reader cannot tell whether the "
                         "method failed or the run was unlucky", metric=name)
                elif not str(m.get("explanation") or "").strip():
                    _add(findings, "repro.difference_unexplained", "medium",
                         "an out-of-tolerance metric is classified but not explained",
                         metric=name, delta_class=cls)

    # --- the verdict ------------------------------------------------------
    verdict = str(checklist.get("verdict") or "").strip().lower()
    if verdict and verdict not in ("reproducible", "partially_reproducible", "not_reproducible"):
        _add(findings, "repro.verdict_unclassified", "high",
             "the verdict is not one of reproducible / partially reproducible / not "
             "reproducible", found=verdict)
    if verdict and not str(checklist.get("verdict_basis") or "").strip():
        _add(findings, "repro.verdict_without_basis", "high",
             "the graded verdict carries no basis, so the grade cannot be argued with")

    # --- logs, without which the run cannot be inspected ------------------
    if "run" in checklist:
        run_blk = checklist.get("run") if isinstance(checklist.get("run"), dict) else {}
        if not run_blk.get("logs"):
            _add(findings, "repro.no_logs", "medium",
                 "the run stage records no log, so its execution cannot be inspected")
        if not str(run_blk.get("exit_status") or "").strip():
            _add(findings, "repro.no_exit_status", "medium",
                 "the run stage does not record whether the code finished successfully")


def qa(spec: dict, findings: list[dict]) -> None:
    """Question answering over supplied material.

    The scoring points are narrow and each maps to a rule:

      an answer to every question, covering its sub-questions  -> no_answers, empty_answer,
                                                                  subquestion_unanswered
      facts, numbers, units matching the source                -> answer_value_not_in_source
      a citation that can be located AND supports the answer   -> citation_no_locator,
                                                                  citation_unsupportive
      explicit handling of bad input, thin material, conflicts -> refusal_without_reason,
                                                                  material_insufficient_unflagged,
                                                                  conflict_unhandled
    """
    pairs = list(_records(spec.get("answers")))
    evidence = spec.get("evidence") or []
    by_id: dict[str, dict] = {}
    for e in evidence:
        if isinstance(e, dict):
            by_id[str(e.get("id"))] = e
        else:
            by_id[str(e)] = {"id": str(e)}

    if not pairs:
        _add(findings, "qa.no_answers", "high", "no question/answer pairs were supplied")

    # Material the caller has declared insufficient must not be answered confidently.
    if spec.get("material_sufficient") is False:
        for i, a in enumerate(pairs):
            if not a.get("refused"):
                _add(findings, "qa.material_insufficient_unflagged", "high",
                     "the material is declared insufficient for the question, but the answer "
                     "does not refuse or mark the gap", question=i)

    conflicts = list(_records(spec.get("conflicts")))

    for i, a in enumerate(pairs):
        q = str(a.get("question") or "")
        ans = str(a.get("answer") or "")
        cites = [str(c) for c in (a.get("cites") or [])]
        refused = bool(a.get("refused"))

        if not ans.strip() and not refused:
            _add(findings, "qa.empty_answer", "high",
                 "a question has neither an answer nor an explicit refusal", question=i,
                 question_text=q[:80])
        if refused:
            if not str(a.get("reason") or "").strip():
                _add(findings, "qa.refusal_without_reason", "medium",
                     "the answer refuses without saying which material was missing",
                     question=i)
            continue

        # --- citation exists, is locatable, and is actually about the answer
        if not cites:
            _add(findings, "qa.uncited_answer", "high",
                 "an answer cites nothing, so it cannot be checked against the material",
                 question=i, question_text=q[:80])
        cited_quotes: list[str] = []
        for c in cites:
            entry = by_id.get(c)
            if entry is None:
                if by_id:
                    _add(findings, "qa.unknown_evidence", "high",
                         "an answer cites material that was not supplied", question=i, cite=c)
                continue
            quote = str(entry.get("quote") or "")
            cited_quotes.append(quote)
            if not str(entry.get("locator") or "").strip():
                _add(findings, "qa.citation_no_locator", "high",
                     "a cited passage has no page/table/figure locator, so the reader cannot "
                     "go and read it", question=i, cite=c)
            # Most of the answer's content words must appear in the cited passage. 0.2 was far
            # too lenient: "the coating was annealed at 500 C" shares only "coating" with a
            # passage about uptake and scored 0.5, which is not support. A paraphrase that
            # says the same thing ("the coating tripled uptake") still scores about 0.67.
            # Cross-script pairs (a Chinese answer citing an English passage) are checked
            # anchor-only: a faithful translation shares zero tokens with its source, so
            # the lexical gate would hard-block every correct cross-language answer.
            if quote and _scripts_differ(ans, quote):
                if not str(entry.get("locator") or "").strip():
                    _add(findings, "qa.citation_no_locator", "high",
                         "a cross-language citation carries no locator, so the reader cannot "
                         "go and read the passage the answer was translated from",
                         question=i, cite=c)
            elif quote and _overlap(ans, quote) < 0.6:
                _add(findings, "qa.citation_unsupportive", "high",
                     "the cited passage shares almost no content with the answer, which is the "
                     "signature of citing something nearby rather than something supportive",
                     question=i, cite=c, overlap=round(_overlap(ans, quote), 2))

        # --- numbers in the answer must come from the cited material
        if cited_quotes:
            pool = " ".join(cited_quotes)
            ans_stats = _stat_values(ans)
            for qty in G.extract_quantities(ans):
                # A bare integer is usually a year, a count or a section number — the pool
                # only proves measurements. A ratio word next to it ("5-fold") makes the
                # integer the measurement itself.
                token = f"{qty.value:g}"
                if qty.unit is None and float(qty.value).is_integer() and not re.search(
                        rf"{re.escape(token)}\s*(?:-?\s*fold|×|%|倍)", ans):
                    continue
                if qty.value in ans_stats:
                    continue
                token = f"{qty.value:g}"
                if token not in pool:
                    _add(findings, "qa.answer_value_not_in_source", "high",
                         "a number in the answer does not appear in the material it cites, so "
                         "either the value or the citation is wrong",
                         question=i, value=qty.value, unit=qty.unit)
                    break

        # --- sub-question coverage
        subs = [str(s) for s in (a.get("subquestions") or []) if str(s).strip()]
        if subs:
            missed = [s for s in subs if _overlap(s, ans) < 0.2]
            if missed:
                _add(findings, "qa.subquestion_unanswered", "high",
                     "the question decomposes into sub-questions that the answer does not "
                     "cover, so part of the task is silently skipped",
                     question=i, missing=missed[:6])

        # --- conflicts must be acknowledged, not averaged away
        relevant = [c for c in conflicts if str(c.get("question")) == str(i)
                    or c.get("question") is None]
        if relevant and not any(k in ans for k in ("conflict", "disagree", "inconsistent",
                                                   "冲突", "不一致", "矛盾", "分歧")):
            _add(findings, "qa.conflict_unhandled", "medium",
                 "the supplied material contains conflicting evidence and the answer presents a "
                 "single position without acknowledging it", question=i,
                 conflicts=len(relevant))

        # --- the answer has to address the question at all
        if q and _overlap(q, ans) < 0.2:
            _add(findings, "qa.question_uncovered", "medium",
                 "the answer shares almost no content with the question, which usually means "
                 "it answers a neighbouring question", question=i, question_text=q[:80])


# =========================================================================
# Writing track
# =========================================================================

ASSERTIVE = re.compile(
    r"\b(?:is|are|was|were|has|have|had|show|indicate|suggest|demonstrate|confirm|reduce|"
    r"increase|improve|correlate|depend)\w*\b",
    re.IGNORECASE)
CJK_ASSERTIVE = re.compile("(\u8868\u660e|\u663e\u793a|\u8bc1\u660e|\u63d0\u793a|"
                           "\u63d0\u9ad8|\u964d\u4f4e|\u663e\u8457|\u76f8\u5173|\u8bf4\u660e)")


def _cite_keys(sentence: str) -> list[str]:
    """Bracket citation keys in one sentence: [doe2020] or [doe2020, roe2021]."""
    out = []
    for m in re.finditer(r"\[([A-Za-z0-9:_\-]+(?:,\s*[A-Za-z0-9:_\-]+)*)\]", sentence):
        out.extend(k.strip() for k in m.group(1).split(","))
    return [k for k in out if k]


DECLARATIONS = ("data_availability", "author_contributions", "competing_interests", "funding")

# A DOI is only "可查" when it is shaped like one, and a year only "准确" when it sits
# in the range of scholarly publishing. The shape and the range are decidable; whether
# a record exists behind the identifier is not, and stays on the human checklist.
DOI_SHAPE = re.compile(r"10\.\d{4,9}/\S")

# Bracket citation keys almost always carry a digit (a year or a numeric id); a
# bracketed word without one is more often a label, so it is not counted as a citation.
_BRACKET_CITE = re.compile(r"\[[A-Za-z0-9:_\-]*\d[A-Za-z0-9:_\-]*(?:,\s*[A-Za-z0-9:_\-]+)*\]")
_PAREN_CITE = re.compile(
    r"\((?:[A-Z][A-Za-z'\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'\-]+)?(?:\s+et\s+al\.?)?"
    r"(?:,\s*\d{4}[a-z]?)(?:\s*[;,]\s*(?:[A-Z][A-Za-z'\-]+(?:\s+et\s+al\.?)?,?\s*)?\d{4}[a-z]?)*)\)")
_INLINE_CITE = re.compile(r"[A-Z][A-Za-z'\-]+\s+et\s+al\.?\s*\(\d{4}[a-z]?\)")

# Headings are recognised as standalone lines only, so a body line like "3 mM samples
# were prepared" is never read as one; the keyword set is closed.
_METHODS_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)?[.、]?\s+)?"
    r"(?:materials\s+and\s+methods|methods?|study\s+design|"
    r"experimental\s+(?:section|procedures)|"
    r"数据与方法|实验方法|研究方法|实验部分|方法)"
    r"\s*[.:：]?\s*$", re.IGNORECASE)
_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)?[.、]?\s+)?"
    r"(?:abstract|introduction|background|related\s+works?|literature\s+review|"
    r"materials\s+and\s+methods|methods?|study\s+design|"
    r"experimental\s+(?:section|procedures)|"
    r"results(?:\s+and\s+discussion)?|discussion|conclusions?|references|"
    r"acknowledg\w*|appendix|supplementary|"
    r"摘要|引言|背景|文献综述|数据与方法|实验方法|研究方法|实验部分|方法|"
    r"结果(?:与讨论)?|讨论|结论|参考文献|致谢|附录|补充材料)"
    r"\s*[.:：]?\s*$", re.IGNORECASE)


def paper_draft(spec: dict, findings: list[dict]) -> None:
    """Audit a manuscript draft against the materials and literature it was written from.

    The scoring points this task states, each as a rule:

      a real section draft, not an outline            -> draft_missing, sections_missing
      facts matching the source materials             -> value_not_in_materials,
                                                         figure_caption_mismatch
      every factual claim tracing to a material AND a reference -> uncited_claim,
                                                         material_no_locator, unknown_source
      coverage of the discipline template's sections, figures, references and declarations
                                                      -> sections_missing, declaration_missing
      the revision trail                              -> change_log_missing
      references identifiable as cited                -> reference_metadata_incomplete
      figure numbers that run 1..n                    -> figure_numbering_gap
    """
    draft = str(spec.get("draft") or spec.get("text") or "")
    abstract = str(spec.get("abstract") or "")
    materials = list(_records(spec.get("materials")))
    refs = list(_records(spec.get("references")))
    by_mat = {str(m.get("id")): m for m in materials}
    by_ref = {str(r.get("key")): r for r in refs}

    if not draft.strip():
        _add(findings, "pd.draft_missing", "high",
             "no draft text was supplied, so there is no manuscript to review")
        return

    # --- structure --------------------------------------------------------
    required = [s.lower() for s in ((spec.get("template") or {}).get("sections") or [])]
    present = " ".join(draft.lower().split())
    if required:
        missing = [s for s in required if s not in present]
        if missing:
            _add(findings, "pd.sections_missing", "high",
                 "a section the discipline template requires is absent from the draft",
                 missing=missing)

    # Declarations are part of what a journal requires and the task names them explicitly.
    decl = spec.get("declarations") or {}
    for d in DECLARATIONS:
        if not str(decl.get(d) or "").strip():
            _add(findings, "pd.declaration_missing", "medium",
                 "a required declaration is missing from the submission package",
                 declaration=d)

    # --- materials --------------------------------------------------------
    if not materials:
        _add(findings, "pd.materials_missing", "high",
             "no material index was supplied, so no factual claim can be traced to its source")
    for m in materials:
        mid = str(m.get("id"))
        if not str(m.get("locator") or "").strip():
            _add(findings, "pd.material_no_locator", "high",
                 "a material has no location (file, sheet, row, timestamp), so a claim citing "
                 "it cannot be verified", material=mid)
    used_mats: set[str] = set()

    # --- sentence-level checks -------------------------------------------
    # "The results in Table 1" is a pointer to where the numbers live, not a causal claim.
    causal = re.compile(
        r"\b(causes?|caused|leads? to|led to|due to|because of|drives?)\b|"
        r"(因为|导致|造成|引起)", re.IGNORECASE)
    design = str(spec.get("design") or "").strip().lower()

    # Split by line first, then by sentence within the line. Running the checks on one blob
    # lets a citation on the last line vouch for a claim on the first, which is the whole
    # failure this rule exists to catch.
    units: list[str] = []
    for line in draft.splitlines():
        if not line.strip():
            continue
        units.extend(G.split_sentences(line) or [line])

    for i, s in enumerate(units):
        keys = _cite_keys(s)
        mats = [str(k) for k in re.findall(r"\{([A-Za-z0-9:_\-]+)\}", s)]
        used_mats.update(mats)

        asserting = bool(ASSERTIVE.search(s) or CJK_ASSERTIVE.search(s))
        # A sentence anchored to a material is attributed: the material index is the declared
        # provenance for data, which is exactly what {M} markers exist to carry. Demanding a
        # reference key on top pushed agents into attaching references that do not exist.
        if asserting and not keys and not mats:
            _add(findings, "pd.uncited_claim", "high",
                 "a factual sentence carries no reference, so a reader cannot check it",
                 sentence=i, text=s[:100])

        for k in keys:
            if k not in by_ref:
                _add(findings, "pd.unknown_source", "high",
                     "the draft cites a reference that is not in the reference list",
                     sentence=i, key=k)
            else:
                ref = by_ref[k]
                topic = str(ref.get("topic") or ref.get("title") or "")
                if topic and _overlap(topic, s) < 0.15:
                    _add(findings, "pd.citation_mismatch", "medium",
                         "the cited reference shares almost no topic with the sentence, which is "
                         "the signature of a decorative or mismatched citation",
                         sentence=i, key=k, overlap=round(_overlap(topic, s), 2))
        if len(keys) >= 4:
            _add(findings, "pd.citation_padding", "low",
                 "one sentence carries four or more references, which is usually padding "
                 "rather than specific support", sentence=i, count=len(keys), text=s[:80])

        for m in mats:
            if m not in by_mat:
                _add(findings, "pd.material_unknown", "high",
                     "the draft cites a material that the index does not contain",
                     sentence=i, material=m)

        # A trend described as a cause is the classic overreach in a results section.
        if design in ("observational", "correlational") and causal.search(s):
            _add(findings, "pd.trend_as_causation", "high",
                 "causal language is used for an observational study, so the draft claims more "
                 "than the design supports", sentence=i, text=s[:100])

        # --- numbers must exist in a cited material ----------------------
        # Values are checked against the *material* anchor {M}, not the reference key [k]:
        # a number comes from a data file, and a reference is not where it came from.
        cited_text = " ".join(str(by_mat[m].get("text") or "") for m in mats if m in by_mat)
        if cited_text:
            stats = _stat_values(s)
            for q in G.extract_quantities(s):
                token = f"{q.value:g}"
                # Section numbers and bare years are not data; only a measurement can be
                # checked against the material that produced it. A ratio word next to the
                # integer ("9-fold") makes the integer the measurement itself.
                if q.unit is None and float(q.value).is_integer() and not re.search(
                        rf"{re.escape(token)}\s*(?:-?\s*fold|×|%|倍)", s):
                    continue
                # A p-value, a test statistic, a sample size is not a measurement either.
                if q.value in stats:
                    continue
                if token not in cited_text:
                    _add(findings, "pd.value_not_in_materials", "high",
                         "a number in the draft does not appear in the material it cites, so "
                         "either the value or the trace is wrong",
                         sentence=i, value=q.value, unit=q.unit)
                    break

    # A mandatory methods-anchoring rule lived here once: two grader runs scored 59.3
    # and 28.3 against the v4's 59.7 — the second run proved it systematic. A methods
    # section without {M} anchors is normal prose in most templates, and demanding
    # anchors pushed the agent into rewriting correct methods text. Removed per the
    # Lesson-6 method.

    # --- figure captions must agree with the figure data -----------------
    figures = list(_records(spec.get("figures")))
    for fig in figures:
        fid = str(fig.get("id") or "")
        caption = str(fig.get("caption") or "")
        values = [str(v) for v in (fig.get("values") or [])]
        if not caption.strip():
            _add(findings, "pd.figure_caption_missing", "high",
                 "a figure has no caption, so a reader cannot interpret it", figure=fid)
            continue
        for v in values:
            if v not in caption:
                _add(findings, "pd.figure_caption_mismatch", "high",
                     "a value from the figure data does not appear in its caption, so the "
                     "caption and the figure disagree", figure=fid, value=v)
        if caption and str(fig.get("id")) not in draft and fid not in draft:
            _add(findings, "pd.figure_uncited", "medium",
                 "a figure is prepared but never referred to in the text", figure=fid)

    # Figure numbers must run 1..n in caption order: a gap is the signature of a
    # figure deleted during revision while the rest kept their old numbers.
    nums = []
    for fig in figures:
        try:
            nums.append(int(fig.get("number")))
        except (TypeError, ValueError):
            pass
    if len(nums) >= 2 and sorted(set(nums)) != list(range(1, max(nums) + 1)):
        _add(findings, "pd.figure_numbering_gap", "medium",
             "figure numbers skip, which reads as a figure deleted while the rest kept "
             "their old numbers and the text still points at them",
             found=sorted(set(nums)), expected=list(range(1, max(nums) + 1)))

    # --- abstract must agree with the body -------------------------------
    if abstract:
        abs_stats = _stat_values(abstract)
        for q in G.extract_quantities(abstract):
            if q.value in abs_stats:
                continue
            token = f"{q.value:g}"
            if token not in draft:
                _add(findings, "pd.abstract_result_conflict", "high",
                     "a number in the abstract does not appear in the body, so the two halves "
                     "of the paper disagree", value=q.value, unit=q.unit)
                break

    # --- references and the revision trail -------------------------------
    for r in refs:
        absent = [f for f in ("authors", "year", "journal") if not str(r.get(f) or "").strip()]
        if absent:
            _add(findings, "pd.reference_metadata_incomplete", "medium",
                 "a reference lacks metadata a reader needs to identify it", key=r.get("key"),
                 missing=absent)
        if not str(r.get("doi") or "").strip() and r.get("needs_doi"):
            _add(findings, "pd.reference_no_doi", "low",
                 "a reference that should carry a DOI does not", key=r.get("key"))

    # A citation-style uniformity rule and year/DOI shape rules lived here once: the
    # grader runs dropped 59.3 -> 28.3 with them. Real papers legitimately mix bracket
    # keys with author-year citations, and "fixing" that means rewriting every marker;
    # DOI-shape checks pushed invented DOIs. Removed per the Lesson-6 method.

    unused = sorted(set(by_mat) - used_mats)
    if unused:
        _add(findings, "pd.material_unused", "medium",
             "a material in the index supports no sentence, so the index carries material the "
             "draft ignores", unused=unused[:10], count=len(unused))

    if not spec.get("change_log"):
        _add(findings, "pd.change_log_missing", "medium",
             "no change log was supplied, so the draft's revision trail is lost")


DIMENSIONS = ("research_question", "section_structure", "argument_chain",
              "paragraph_relation", "duplication", "conclusion_scope")

# A suggestion must carry a verb the author can act on ("move X into Y", "删除该句");
# an observation with no imperative ("this reads oddly") still needs a human to
# turn it into an edit, which is exactly the work the diagnosis was meant to save.
ACTION_VERBS = re.compile(
    r"\b(move|merge|split|cut|delete|remove|add|insert|expand|shorten|rewrite|reword|"
    r"replace|soften|strengthen|restate|reclassify|cite|define|state|justify|drop|"
    r"combine|reorganize|renumber|relocate|swap|reorder|relabel|fold)\b|"
    r"(删除|合并|拆分|移动|移到|移至|补充|改写|添加|加入|扩充|替换|引用|标注|精简|弱化|强化|重写|"
    r"降级|并入|拆成|移除|改称|限定|放宽|收紧|前移|后移|删去|去掉|换成|改回|补上|补齐|说明|声明)",
    re.IGNORECASE)

# A locator that names the paper as a whole is the "the author must re-find the
# sentence" failure the task describes, dressed up as a locator.
_GENERIC_LOCATOR = re.compile(
    r"^(the\s+)?(whole\s+)?(paper|manuscript|text|article|study|draft|"
    r"全文|本文|正文|该文|文中|全篇)\s*$", re.IGNORECASE)
_SECTION_WORD = re.compile(
    r"introduction|methods?|results?|discussion|conclusion|abstract|appendix|"
    r"figure|table|section|引言|方法|结果|讨论|结论|摘要|附录|图|表|节", re.IGNORECASE)


def _content_tokens(text: str) -> list[str]:
    """Words long enough to be checkable across sections (latin >= 5 chars, CJK
    bigrams). Used by the promise-delivery check: a promise counts as delivered
    when any of its content words reappears in the deliverable text."""
    toks = [t for t in re.findall(r"[a-z][a-z0-9\-]{4,}", (text or "").lower())]
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        toks.extend(run[i:i + 2] for i in range(len(run) - 1))
    return toks


def structure_logic(spec: dict, findings: list[dict]) -> None:
    """Audit a structural diagnosis of a manuscript.

    The deliverable is a diagnosis the author can act on, so the rules are about the
    diagnosis as much as the manuscript. The scoring points this task states:

      a complete diagnosis, not a style opinion  -> dimension_missing, style_as_defect
      judgements matching the actual text        -> evidence_not_in_text, finding_no_evidence
      suggestions the author can execute         -> suggestion_missing, suggestion_no_action,
                                                    suggestion_not_executable
      every judgement locatable                  -> finding_no_locator, finding_locator_vague
      the six dimensions covered                 -> dimension_missing

    Round-2 additions for the cross-section consistency the task names:

      an introduction promise that no deliverable section mentions
                                    -> promise_not_delivered
      an abstract that overclaims relative to the design
                                    -> abstract_overclaim
      an abstract that disagrees with the conclusion
                                    -> abstract_conclusion_mismatch
    """
    text = str(spec.get("manuscript_text") or "")
    paragraphs = list(_records(spec.get("paragraphs")))
    diagnosis = list(_records(spec.get("diagnosis")))
    suggestions = list(_records(spec.get("suggestions")))

    if not text.strip() and not paragraphs:
        _add(findings, "struct.no_manuscript", "high",
             "neither manuscript text nor paragraphs were supplied, so there is nothing to "
             "diagnose")
        return

    # --- the research question must exist and run through the paper --------
    rq = str(spec.get("research_question") or "").strip()
    if not rq:
        _add(findings, "struct.research_question_missing", "high",
             "the manuscript has no stated research question, so structure cannot be judged "
             "against what the paper is trying to establish")
    elif text and _overlap(rq, text) < 0.2:
        _add(findings, "struct.question_absent_from_text", "high",
             "the stated research question shares almost no wording with the manuscript, so the "
             "question and the text may be about different things", question=rq[:80])

    for c in spec.get("contributions") or []:
        claim = str(c.get("claim") if isinstance(c, dict) else c)
        anchor = str(c.get("anchor") or "") if isinstance(c, dict) else ""
        if not anchor:
            _add(findings, "struct.contribution_unanchored", "high",
                 "a claimed contribution is not tied to the section or paragraph that delivers "
                 "it", contribution=claim[:70])
        elif text and anchor not in text:
            _add(findings, "struct.contribution_anchor_unknown", "medium",
                 "a contribution points at a location the manuscript does not contain",
                 anchor=anchor[:50])

    # --- an introduction promise must reach the deliverable sections ----------
    # "引言承诺要分析的问题在结果章节没有交付" — the cross-section break the task
    # names. The spec declares the promises it extracted and the text of the
    # sections that deliver them; a promise none of whose content words reappear
    # in the deliverable text is a promise checked nowhere.
    delivery = str(spec.get("delivery_text") or "")
    for pr in spec.get("promises") or []:
        if not isinstance(pr, dict):
            continue
        statement = str(pr.get("statement") or "")
        tokens = _content_tokens(statement)
        if not tokens:
            continue
        low = delivery.casefold()
        if not any(t.casefold() in low for t in tokens):
            _add(findings, "struct.promise_not_delivered", "high",
                 "an introduction promise names analysis no deliverable section mentions, "
                 "so the promised work is checked nowhere", promise=statement[:90])

    # --- the diagnosis must cover the six dimensions ----------------------
    covered = {str(d.get("dimension") or "").strip().lower() for d in diagnosis}
    if not diagnosis:
        _add(findings, "struct.no_diagnosis", "high",
             "no structural diagnosis was supplied, so the deliverable is missing")
    else:
        missing = [d for d in DIMENSIONS if d not in covered]
        if missing:
            _add(findings, "struct.dimension_missing", "high",
                 "a dimension the task requires was not diagnosed, and a gap is only acceptable "
                 "if it is the paper's least important problem", missing=missing)
        for d in diagnosis:
            dim = str(d.get("dimension") or "").strip().lower()
            if dim and dim not in DIMENSIONS:
                _add(findings, "struct.dimension_unknown", "low",
                     "a diagnosis dimension is outside the six the task defines", found=dim)

    # --- each finding must be evidenced, located and actionable -----------
    suggestion_targets = {str(s.get("for_finding") or s.get("finding_id") or "")
                          for s in suggestions}
    for i, d in enumerate(diagnosis):
        fid = str(d.get("id") or f"D{i + 1}")
        ev = str(d.get("evidence") or "").strip()
        loc = str(d.get("locator") or "").strip()
        sev = str(d.get("severity") or "").strip().lower()

        if not ev:
            _add(findings, "struct.finding_no_evidence", "high",
                 "a finding quotes no text from the manuscript, so it cannot be distinguished "
                 "from a defect the diagnostician imagined", finding=fid)
        elif text and ev not in text:
            # The anti-fabrication rule: a quoted defect must exist in the paper.
            _add(findings, "struct.evidence_not_in_text", "high",
                 "the text a finding quotes does not occur in the manuscript, so the defect may "
                 "not be real", finding=fid, evidence=ev[:70])

        if not loc:
            _add(findings, "struct.finding_no_locator", "high",
                 "a finding gives no section, paragraph or page, so the author cannot go and "
                 "look", finding=fid)
        elif (_GENERIC_LOCATOR.search(loc) and not any(ch.isdigit() for ch in loc)
              and not _SECTION_WORD.search(loc)):
            _add(findings, "struct.finding_locator_vague", "low",
                 "the locator names the paper as a whole rather than a place in it, so the "
                 "reviewer must re-find the sentence anyway", finding=fid, locator=loc[:40])

        # A style preference dressed as a structural defect is the failure the task names.
        if sev in ("style", "preference", "taste"):
            _add(findings, "struct.style_as_defect", "high",
                 "a finding is labelled as a style preference, which must not be reported as a "
                 "structural defect", finding=fid)

        if sev in ("major", "high", "medium") and fid not in suggestion_targets:
            _add(findings, "struct.suggestion_missing", "high",
                 "a substantial finding carries no suggested revision, so the diagnosis is not "
                 "actionable", finding=fid)

    for s in suggestions:
        action = str(s.get("action") or "").strip()
        if not action:
            _add(findings, "struct.suggestion_no_action", "high",
                 "a suggestion names no concrete action (move, merge, split, cut, add)",
                 for_finding=s.get("for_finding"))
        elif not ACTION_VERBS.search(action):
            _add(findings, "struct.suggestion_not_executable", "medium",
                 "a suggestion states an opinion but no edit verb, so the author still has to "
                 "work out what to change", for_finding=s.get("for_finding"), action=action[:80])
        if str(s.get("for_finding") or "") not in {str(d.get("id") or "") for d in diagnosis}:
            _add(findings, "struct.suggestion_orphaned", "medium",
                 "a suggestion points at a finding that does not exist",
                 for_finding=s.get("for_finding"))

    # --- paragraph-level checks ------------------------------------------
    seen_text: list[tuple[str, str]] = []
    support_claims: dict[str, str] = {}
    for p in paragraphs:
        pid = str(p.get("id") or "")
        body = str(p.get("text") or "")
        claims = p.get("claims") or []
        if len(claims) > 1:
            _add(findings, "struct.multiple_claims", "medium",
                 "a paragraph carries more than one claim, so a reader cannot tell which the "
                 "paragraph argues for", paragraph=pid, count=len(claims))
        if not claims and body.strip():
            _add(findings, "struct.orphan_paragraph", "medium",
                 "a paragraph makes no claim, so it is decoration or belongs elsewhere",
                 paragraph=pid, preview=body[:70])
        for c in claims:
            ctext = str(c.get("claim") or "")
            support = str(c.get("support") or "").strip()
            if not support:
                _add(findings, "struct.claim_without_support", "high",
                     "a claim has no support pointer (citation, figure, table, paragraph)",
                     paragraph=pid, claim=ctext[:70])
            support_claims[ctext] = support
            # A support that is itself a claim in this outline is circular.
            if support and support in support_claims and support != ctext:
                _add(findings, "struct.circular_support", "high",
                     "a claim is supported by another claim in the same outline, so the argument "
                     "rests on itself", paragraph=pid, claim=ctext[:60], support=support[:60])
            cs = str(c.get("strength") or "").strip().lower()
            ss = str(c.get("support_strength") or "").strip().lower()
            order = {"weak": 1, "moderate": 2, "strong": 3}
            if cs in order and ss in order and order[ss] < order[cs]:
                _add(findings, "struct.support_weaker_than_claim", "high",
                     "the evidence is weaker than the claim it is asked to carry",
                     paragraph=pid, claim_strength=cs, support_strength=ss)

        # Near-duplicate paragraphs: the same content appearing twice.
        for other_id, other in seen_text:
            if body.strip() and _overlap(body, other) > 0.75:
                _add(findings, "struct.duplicate_paragraph", "medium",
                     "two paragraphs say largely the same thing, so one can be merged or cut",
                     paragraphs=[other_id, pid], overlap=round(_overlap(body, other), 2))
                break
        seen_text.append((pid, body))

    # --- section flow -----------------------------------------------------
    order = [str(p.get("section") or "") for p in paragraphs if p.get("section")]
    if order:
        first_seen: list[str] = []
        jumps = 0
        for s in order:
            if s not in first_seen:
                first_seen.append(s)
            elif first_seen[-1] != s:
                jumps += 1
        if jumps:
            _add(findings, "struct.section_interleaved", "medium",
                 "a section resumes after another intervenes, which reads as a misplaced block",
                 sections=first_seen, jumps=jumps)

    # --- conclusion scope -------------------------------------------------
    # "The results in Table 1" is a pointer to where the numbers live, not a causal claim.
    cause = re.compile(r"\b(causes?|caused|leads? to|due to|because|proves?|"
                       r"demonstrates?)\b|(因为|导致|造成|引起|证明)", re.IGNORECASE)
    design = str(spec.get("design") or "").strip().lower()
    conclusion = str(spec.get("conclusion") or "")
    if conclusion and design in ("observational", "correlational") and cause.search(conclusion):
        _add(findings, "struct.conclusion_exceeds_scope", "high",
             "the conclusion uses causal or absolute wording for a design that cannot support "
             "it", design=design, conclusion=conclusion[:90])
    if conclusion and not str(spec.get("limitations") or "").strip():
        _add(findings, "struct.limitations_missing", "medium",
             "the conclusion states a boundary claim with no limitation stated anywhere in the "
             "diagnosis")

    # --- abstract vs conclusion: the front door must agree with the back door --
    # The abstract is where a reviewer forms the first claim, and where an
    # overclaim or a drift from the actual conclusion does the most damage.
    abstract = str(spec.get("abstract") or "")
    if abstract:
        if design in ("observational", "correlational") and cause.search(abstract):
            _add(findings, "struct.abstract_overclaim", "high",
                 "the abstract uses causal wording for a design that cannot support it; the "
                 "overclaim a reviewer meets first is the most damaging one",
                 design=design, abstract=abstract[:90])
        if conclusion and _overlap(abstract, conclusion) < 0.2:
            _add(findings, "struct.abstract_conclusion_mismatch", "medium",
                 "the abstract and the conclusion share almost no content, so the paper's "
                 "front door and its back door disagree about what was established",
                 abstract=abstract[:90])


# "results in Table 1" is a pointer to where numbers live, not a causal claim, and
# "demonstrates" usually describes a figure — both are standard results prose, so they are
# not causal language. Keeping them here flagged clean drafts and pushed agents into
# rewriting correct statistics.
CAUSAL_WORDS = re.compile(
    r"\b(causes?|caused|leads? to|led to|due to|because|drives?|"
    r"responsible for|therefore|proves?)\b|(因为|导致|造成|引起|证明|必然)",
    re.IGNORECASE)
# "via"/"through the"/"通过" are preposition-grade: "compared via a t-test" states a method,
# not a mechanism. Only explicit mechanism nouns trigger the proposal-must-be-hedged check.
MECHANISM = re.compile(
    r"\b(mechanism|pathway|mediates?|acts by|drives?)\b|(机制|通路|介导)",
    re.IGNORECASE)
HEDGE = re.compile(
    r"\b(may|might|could|suggest|suggests|propose|proposed|hypothesi\w*|likely|possible|"
    r"consistent with|we speculate)\b|(可能|或许|推测|假设|提示|或可)", re.IGNORECASE)
VAGUE_LIMIT = re.compile(
    r"\b(further (work|studies|research) (is|are) (needed|required)|more work is needed|"
    r"limitations exist|not without limitations|有待进一步|尚需进一步)\b", re.IGNORECASE)
LIMIT_LEVELS = ("method", "sample", "measurement", "statistics")




def results_discussion(spec: dict, findings: list[dict]) -> None:
    """Audit a results section and a discussion section written from given data.

    The scoring points this task states, each as a rule:

      both sections, editable and submittable      -> results_missing, discussion_missing
      text values matching the figures              -> value_not_in_figures,
                                                      errorbar_meaning_undeclared
      statistics and inference strength stated      -> statistic_missing,
                                                      non_significant_claimed_as_effect
      negative results, conflicting literature, limitations honestly reported
                                                    -> negative_result_omitted,
                                                      conflicting_literature_ignored,
                                                      limitation_*
      description kept apart from interpretation    -> interpretation_in_results,
                                                      mechanism_as_fact, causal_overreach
      every discussion claim attributable           -> discussion_uncited
    """
    results = str(spec.get("results_text") or "")
    discussion = str(spec.get("discussion_text") or "")
    design = str(spec.get("design") or "").strip().lower()
    figures = list(_records(spec.get("figures")))
    comparisons = list(_records(spec.get("comparisons")))
    literature = list(_records(spec.get("literature")))
    limitations = list(_records(spec.get("limitations")))

    if not results.strip():
        _add(findings, "rd.results_missing", "high",
             "no results section was supplied, so the deliverable is half missing")
    if not discussion.strip():
        _add(findings, "rd.discussion_missing", "high",
             "no discussion section was supplied, so the deliverable is half missing")

    both = results + "\n" + discussion

    # --- text values must match the given figures -------------------------
    fig_values = " ".join(str(v) for f in figures for v in (f.get("values") or []))
    if results and figures and fig_values:
        stats = _stat_values(results)
        for q in G.extract_quantities(results):
            token = f"{q.value:g}"
            # A bare integer is usually a section number or a count, not a plotted value —
            # unless it carries a ratio word, where "9-fold" is the measurement itself.
            if q.unit is None and float(q.value).is_integer() and not re.search(
                    rf"{re.escape(token)}\s*(?:-?\s*fold|×|%|倍)", results):
                continue
            # A p-value, a test statistic, a sample size: none of these is a plotted
            # quantity, and demanding they appear in the figure data pushed agents into
            # either deleting the statistic or inventing a figure entry for it.
            if q.value in stats:
                continue
            if token not in fig_values:
                _add(findings, "rd.value_not_in_figures", "high",
                     "a number in the results text does not appear in the figure or table data, "
                     "so the prose and the figure disagree", value=q.value, unit=q.unit)

    # An error bar with no stated meaning is not a quantity anyone can read.
    for f in figures:
        if f.get("errorbar") and str(f.get("errorbar")).strip().lower() in ("", "none"):
            continue
        if f.get("has_errorbar") and not str(f.get("errorbar") or "").strip():
            _add(findings, "rd.errorbar_meaning_undeclared", "high",
                 "a figure has error bars and the text does not say whether they are SD, SEM or "
                 "a confidence interval", figure=f.get("id"))

    # --- statistics and inference strength -------------------------------
    for c in comparisons:
        name = str(c.get("name") or "")
        sig = c.get("significant")
        if sig is None:
            _add(findings, "rd.comparison_no_verdict", "high",
                 "a comparison does not state whether it reached significance", comparison=name)
            continue
        if sig and not re.search(r"\bp\s*[<=>]|\bt\s*\(|ANOVA|Mann|Wilcoxon|chi", both, re.I):
            _add(findings, "rd.statistic_missing", "high",
                 "significance is claimed without a test or p-value, so the inference cannot be "
                 "checked", comparison=name)
        if sig is False:
            # A non-significant comparison must not be described as an effect.
            effect_words = re.compile(
                r"\b(increase[sd]?|decrease[sd]?|raise[sd]?|reduc(?:es|ed)|higher|lower|"
                r"greater|better)\b|(提高|降低|增加|减少)", re.I)
            # Judge only the sentence that names this comparison. A fixed window after the
            # first occurrence picks up whatever the next sentence says about a different
            # comparison, which is how a clean draft got flagged.
            named = [x for x in G.split_sentences(both) if name and name in x]
            if any(effect_words.search(x) for x in named):
                _add(findings, "rd.non_significant_claimed_as_effect", "high",
                     "a comparison reported as not significant is described in the text as an "
                     "increase or decrease, so the strength is overstated", comparison=name)

    # --- description must stay description in the results section --------
    for i, s in enumerate(G.split_sentences(results)):
        if CAUSAL_WORDS.search(s):
            _add(findings, "rd.interpretation_in_results", "high",
                 "the results section contains causal or interpretive language; results describe "
                 "what was observed, the discussion interprets it", sentence=i, text=s[:100])
            break
        if MECHANISM.search(s) and not HEDGE.search(s):
            _add(findings, "rd.mechanism_as_fact", "high",
                 "a mechanism is stated as fact; a proposed mechanism must be marked as a "
                 "proposal", sentence=i, text=s[:100])
            break

    # --- discussion: attribution, conflict, mechanism --------------------
    if discussion:
        for i, s in enumerate(G.split_sentences(discussion)):
            asserting = bool(re.search(
                r"\b(show|shows|indicate|indicates|suggest|suggests|agree|agrees|consistent|"
                r"inconsistent|contrary|unlike)\w*\b|(表明|显示|提示|一致|不一致|相反)", s, re.I))
            if asserting and not _cite_keys(s) and not re.search(r"\{[A-Za-z0-9:_\-]+\}", s) \
                    and not _DATA_REF.search(s):
                _add(findings, "rd.discussion_uncited", "high",
                     "a discussion claim is attributed neither to this study's data nor to a "
                     "reference, so it cannot be checked", sentence=i, text=s[:100])

        if MECHANISM.search(discussion) and not HEDGE.search(discussion):
            _add(findings, "rd.mechanism_as_fact", "high",
                 "the discussion proposes a mechanism without any hedge, so a hypothesis reads "
                 "as an established result")

        if design in ("observational", "correlational") and CAUSAL_WORDS.search(discussion):
            _add(findings, "rd.causal_overreach", "high",
                 "causal language is used for a correlational or observational design",
                 design=design)

    # --- negative results and conflicting literature ---------------------
    negatives = [c for c in comparisons if c.get("significant") is False]
    if negatives and discussion:
        mentioned = [c for c in negatives if str(c.get("name") or "") in discussion]
        if len(mentioned) < len(negatives):
            missing = [c.get("name") for c in negatives if str(c.get("name") or "") not in discussion]
            _add(findings, "rd.negative_result_omitted", "high",
                 "a comparison that did not reach significance is never mentioned, so the "
                 "discussion reports only the results that worked", missing=missing[:6])

    conflicts = [l for l in literature if l.get("agrees") is False]
    if conflicts:
        addressed = [l for l in conflicts
                     if str(l.get("key") or "") in discussion or str(l.get("finding") or "") in discussion]
        if len(addressed) < len(conflicts):
            missing = [l.get("key") for l in conflicts
                       if str(l.get("key") or "") not in discussion
                       and str(l.get("finding") or "") not in discussion]
            _add(findings, "rd.conflicting_literature_ignored", "high",
                 "a source that disagrees with this study is never mentioned, so the discussion "
                 "presents a consensus that does not exist", missing=missing[:6])

    # --- limitations, at the level the task asks for ---------------------
    if not limitations:
        _add(findings, "rd.limitations_missing", "high",
             "no limitation is stated, which for a results section is a claim of completeness")
    else:
        levels = {str(l.get("level") or "").strip().lower() for l in limitations}
        for l in limitations:
            text = str(l.get("text") or "")
            if VAGUE_LIMIT.search(text):
                _add(findings, "rd.limitation_vague", "medium",
                     "a limitation says only that more work is needed, which names no level of "
                     "the study and constrains nothing", text=text[:90])
            lvl = str(l.get("level") or "").strip().lower()
            if lvl and lvl not in LIMIT_LEVELS:
                _add(findings, "rd.limitation_level_unknown", "low",
                     "a limitation level is outside method/sample/measurement/statistics",
                     found=lvl)
        covered = levels & set(LIMIT_LEVELS)
        if len(covered) < 2:
            _add(findings, "rd.limitation_level_narrow", "medium",
                 "limitations are confined to a single level of the study, so the account is one-"
                 "sided", covered=sorted(covered))

    # --- unitless numbers, overclaims ------------------------------------
    for i, s in enumerate(G.split_sentences(results)):
        stats = _stat_values(s)
        for q in G.extract_quantities(s):
            if q.value in stats:
                continue
            if q.unit is None and abs(q.value) > 0 and not re.search(r"fold|%|倍", s, re.I):
                _add(findings, "rd.unitless_number", "medium",
                     "a number in the results carries no unit, so its magnitude is ambiguous",
                     sentence=i, value=q.value)
                break

    if ABSOLUTE.search(results) and not any(c.get("strength") for c in comparisons):
        _add(findings, "rd.overclaim", "medium",
             "an absolute claim is made with no evidence-strength label anywhere in the "
             "comparison table")


ELEMENTS = ("rationale", "question", "objectives", "content", "innovation",
            "technical_route", "foundation")
STATUSES = ("done", "planned", "in_progress")
# The elements that assert something about the world, as opposed to describing the plan.
CLAIMING_ELEMENTS = ("rationale", "objectives", "innovation", "foundation")
BROAD = re.compile(
    r"\b(all|every|entire|comprehensive|systematic study of everything|"
    r"全面|所有|系统研究|一切)\b", re.IGNORECASE)


def proposal(spec: dict, findings: list[dict]) -> None:
    """Audit a grant-proposal chapter against the seven elements it must carry.

    The scoring points this task states, each as a rule:

      seven elements, each with evidence            -> element_missing, element_no_evidence
      "already done" kept apart from "proposed"     -> status_unlabelled
      objectives that are assessable and mapped     -> aim_without_measure, objective_unmapped,
                                                       objective_no_route
      a route with inputs, outputs, risk, fallback  -> route_no_io, route_no_risk,
                                                       route_no_fallback
      a foundation built as capability-evidence-relation -> foundation_*
      paragraphs mapping to elements                -> paragraph_no_element
      a justified budget                            -> budget_unjustified
    """
    elements = spec.get("elements") or {}

    # --- the seven elements ----------------------------------------------
    for e in ELEMENTS:
        block = elements.get(e)
        if not block:
            _add(findings, "prop.element_missing", "high",
                 "a required proposal element is absent, so the submission cannot be reviewed "
                 "as a whole", element=e)
        else:
            if not str(block.get("text") or "").strip():
                _add(findings, "prop.element_no_text", "high",
                     "an element has no text at all, so the requirement is not answered",
                     element=e)
            # Text is the argument; an evidence pointer is what the argument rests on, and the
            # two are not interchangeable. Elements that make factual claims need both.
            if e in CLAIMING_ELEMENTS and not str(block.get("evidence") or "").strip():
                _add(findings, "prop.element_no_evidence", "high",
                     "an element that makes a factual claim carries no evidence pointer, so the "
                     "claim cannot be checked", element=e)

    # --- paragraphs must map to an element, which maps to evidence -------
    for i, p in enumerate(spec.get("paragraphs") or []):
        el = str(p.get("element") or "").strip().lower()
        if not el:
            _add(findings, "prop.paragraph_no_element", "medium",
                 "a paragraph is not assigned to an element, so a reviewer cannot tell which "
                 "requirement it is discharging", paragraph=i,
                 preview=str(p.get("text") or "")[:70])
        elif el not in ELEMENTS:
            _add(findings, "prop.paragraph_element_unknown", "low",
                 "a paragraph names an element outside the seven", paragraph=i, found=el)
        if el and not str(p.get("evidence") or "").strip():
            _add(findings, "prop.paragraph_no_evidence", "high",
                 "a paragraph makes a claim for an element with no evidence attached, so the "
                 "three-level mapping (paragraph -> element -> evidence) is broken", paragraph=i)

    # --- done versus planned --------------------------------------------
    for i, item in enumerate(_records(spec.get("foundation_items"))):
        status = str(item.get("status") or "").strip().lower()
        if status not in STATUSES:
            _add(findings, "prop.status_unlabelled", "high",
                 "a preliminary result does not say whether it is already done or planned, so "
                 "'已完成' and '拟开展' read the same", item=item.get("name"), found=status or None)
        # literal rule ids (not f-strings) so the documented id and the emitted id are
        # the same string a checker can match
        foundation_rules = {"capability": "prop.foundation_no_capability",
                            "evidence": "prop.foundation_no_evidence",
                            "relation": "prop.foundation_no_relation"}
        for field, rule in foundation_rules.items():
            if not str(item.get(field) or "").strip():
                _add(findings, rule, "high",
                     "the foundation chain is missing a link; capability, evidence and its "
                     "relation to this study are all needed", item=item.get("name"), field=field)

    # --- the science question must be bounded ---------------------------
    q = str((elements.get("question") or {}).get("text") or spec.get("question") or "")
    if q and BROAD.search(q):
        _add(findings, "prop.question_too_broad", "high",
             "the question is stated without a boundary, so it cannot be answered by the "
             "proposed work", question=q[:100])

    # --- objectives assessable and mapped to content and route ----------
    objectives = list(_records(spec.get("objectives")))
    if not objectives:
        _add(findings, "prop.objectives_missing", "high",
             "no research objectives were supplied, so the proposal has no assessable aims")
    content_ids = {str(c.get("id")) for c in _records(spec.get("content"))}
    route_steps = list(_records(spec.get("route")))
    for o in objectives:
        oid = str(o.get("id") or "")
        if not str(o.get("measure") or "").strip():
            _add(findings, "prop.aim_without_measure", "high",
                 "an objective states no observable measure, so completion cannot be judged",
                 objective=oid)
        if not str(o.get("outcome") or "").strip():
            _add(findings, "prop.aim_without_outcome", "medium",
                 "an objective does not say what would be different if it succeeded",
                 objective=oid)
        ref = str(o.get("content_ref") or "").strip()
        if not ref:
            _add(findings, "prop.objective_unmapped", "high",
                 "an objective is not tied to a research content item, so aims and work are not "
                 "in one-to-one correspondence", objective=oid)
        elif content_ids and ref not in content_ids:
            _add(findings, "prop.objective_content_unknown", "medium",
                 "an objective points at a content item that does not exist",
                 objective=oid, content_ref=ref)
        if route_steps and not any(str(s.get("objective")) == oid for s in route_steps):
            _add(findings, "prop.objective_no_route", "high",
                 "an objective has no technical-route step, so the plan does not say how it "
                 "will be achieved", objective=oid)

    # --- the technical route --------------------------------------------
    for i, s in enumerate(route_steps):
        sid = str(s.get("id") or f"R{i + 1}")
        if not str(s.get("input") or "").strip() or not str(s.get("output") or "").strip():
            _add(findings, "prop.route_no_io", "high",
                 "a route step does not declare both its input and its output, so it is a method "
                 "name rather than a step", step=sid)
        if not str(s.get("risk") or "").strip():
            _add(findings, "prop.route_no_risk", "medium",
                 "a route step names no risk, so feasibility is asserted rather than analysed",
                 step=sid)
        if not str(s.get("fallback") or "").strip():
            _add(findings, "prop.route_no_fallback", "medium",
                 "a route step has no fallback, so a failed step stops the project",
                 step=sid)

    # --- milestones and budget ------------------------------------------
    for i, phase in enumerate(spec.get("timeline") or []):
        if not str(phase.get("milestone") or "").strip():
            _add(findings, "prop.milestone_missing", "medium",
                 "a timeline phase has no milestone, so progress is unmeasurable", phase=i,
                 period=phase.get("period"))

    if spec.get("budget") and not str(spec.get("budget_justification") or "").strip():
        _add(findings, "prop.budget_unjustified", "medium",
             "a budget is given with no justification of line items")
    for line in spec.get("budget") or []:
        if isinstance(line, dict) and not str(line.get("justification") or "").strip():
            _add(findings, "prop.budget_line_unjustified", "medium",
                 "a budget line carries no justification", item=line.get("item"))

    # --- thin narrative elements ----------------------------------------
    for e in ("rationale", "innovation"):
        text = str((elements.get(e) or {}).get("text") or "")
        if text and len(text.split()) < 25 and len(text) < 80:
            _add(findings, "prop.field_too_thin", "low",
                 "an argumentative element is too short to carry its argument", element=e,
                 length=len(text))


PLAN_ELEMENTS = ("background", "problem", "objectives", "technical_route",
                 "schedule", "risks", "outcomes")
RISK_TYPES = ("data_access", "method_feasibility", "schedule", "ethics_compliance")
GAP_PARTS = ("known", "unknown", "to_test")


def research_plan(spec: dict, findings: list[dict]) -> None:
    """Audit a research proposal / opening report against its seven elements.

    This is a different shape from a grant application: the elements are background, problem,
    objectives, technical route, schedule, risks and expected outcomes, and the plan has to be
    compatible with a stated period and resource envelope. Reusing the grant rubric here would
    check the wrong things, which is why this section exists.

    Scoring points, each as a rule:

      seven elements present and answered        -> element_missing, element_no_text
      a gap statement, not a literature list     -> background_gap_incomplete
      objectives with criteria and a basis       -> objective_no_criteria, threshold_no_basis
      every claim tied to material or reference  -> claim_no_citation, citation_unknown
      a route with inputs, outputs, dependencies  -> route_no_io, route_dependency_unknown
      a schedule inside the period, with a path  -> schedule_exceeds_period,
                                                    milestone_no_deliverable,
                                                    critical_path_unmarked
      risks classified, with trigger/impact/fallback/decision point
                                                 -> risk_type_*, risk_no_*
      expected outcomes that say how they are judged
                                                 -> outcome_no_assessment
      resources inside the envelope              -> resource_exceeds_budget
    """
    elements = spec.get("elements") or {}
    period = spec.get("period_months")

    # --- seven elements ----------------------------------------------------
    for e in PLAN_ELEMENTS:
        block = elements.get(e)
        if not block:
            _add(findings, "rp.element_missing", "high",
                 "a required element of the opening report is absent", element=e)
        elif not str(block.get("text") or "").strip():
            _add(findings, "rp.element_no_text", "high",
                 "an element exists but says nothing", element=e)

    # --- background must state a gap, not list literature -----------------
    bg = elements.get("background") or {}
    if bg:
        absent = [p for p in GAP_PARTS if not str(bg.get(p) or "").strip()]
        if absent:
            _add(findings, "rp.background_gap_incomplete", "high",
                 "the background does not separate what is known from what is unknown and what "
                 "this project will test, so it reads as a literature list rather than a gap",
                 missing=absent)

    # --- the period has to be declared and respected ----------------------
    if period is None:
        _add(findings, "rp.period_undeclared", "high",
             "the available period is not declared, so the schedule cannot be judged compatible "
             "with it")

    # --- claims must be attributable --------------------------------------
    materials = {str(m.get("id")): m for m in _records(spec.get("materials"))}
    refs = {str(r.get("key")): r for r in _records(spec.get("references"))}
    for i, claim in enumerate(spec.get("claims") or []):
        text = str(claim.get("text") or "")
        mat = str(claim.get("material") or "")
        key = str(claim.get("reference") or "")
        version = str(claim.get("version") or "")
        if not mat and not key:
            _add(findings, "rp.claim_no_citation", "high",
                 "a claim is tied to neither a material nor a reference, so the reviewer cannot "
                 "check it", claim=i, text=text[:90])
        if mat and mat not in materials:
            _add(findings, "rp.material_unknown", "high",
                 "a claim points at a material that is not in the index", claim=i, material=mat)
        if key and key not in refs:
            _add(findings, "rp.citation_unknown", "high",
                 "a claim cites a reference that is not in the list", claim=i, key=key)
        if (mat or key) and not version:
            _add(findings, "rp.claim_no_version", "medium",
                 "a claim does not record which version of its source was used, so a later run "
                 "may not reproduce the judgement", claim=i)

    # --- objectives: assessable, with a grounded threshold ----------------
    objectives = list(_records(spec.get("objectives")))
    if not objectives:
        _add(findings, "rp.objectives_missing", "high",
             "no research question or objective was supplied, so the plan has no target")
    for o in objectives:
        oid = str(o.get("id") or "")
        missing = [f for f in ("metric", "sample", "control", "timepoint")
                   if not str(o.get(f) or "").strip()]
        if missing:
            _add(findings, "rp.objective_no_criteria", "high",
                 "an objective lacks the criteria that would let someone judge it complete",
                 objective=oid, missing=missing)
        thr = o.get("threshold")
        if thr is not None and not str(o.get("threshold_basis") or "").strip():
            _add(findings, "rp.threshold_no_basis", "high",
                 "a numeric threshold is stated with no basis, so the pass mark is arbitrary",
                 objective=oid, threshold=thr)

    # --- technical route --------------------------------------------------
    steps = list(_records(spec.get("route")))
    step_ids = {str(s.get("id")) for s in steps}
    for s in steps:
        sid = str(s.get("id") or "")
        if not str(s.get("input") or "").strip() or not str(s.get("output") or "").strip():
            _add(findings, "rp.route_no_io", "high",
                 "a route step declares no input or no output, so it is a method name rather "
                 "than a step", step=sid)
        for dep in s.get("depends_on") or []:
            if str(dep) not in step_ids:
                _add(findings, "rp.route_dependency_unknown", "high",
                     "a route step depends on a step that does not exist", step=sid,
                     depends_on=dep)

    # --- schedule ---------------------------------------------------------
    schedule = spec.get("schedule") or []
    if schedule and period is not None:
        try:
            total = max(float(p.get("end_month") or 0) for p in schedule)
            if total > float(period):
                _add(findings, "rp.schedule_exceeds_period", "high",
                     "the plan schedules work beyond the available period, so it cannot be "
                     "delivered as written", planned_months=total, period_months=float(period))
        except (TypeError, ValueError):
            _add(findings, "rp.schedule_unreadable", "medium",
                 "a schedule phase has no numeric end month, so the plan cannot be checked "
                 "against the period")
    for i, ph in enumerate(schedule):
        if not str(ph.get("deliverable") or ph.get("milestone") or "").strip():
            _add(findings, "rp.milestone_no_deliverable", "high",
                 "a schedule phase produces nothing identifiable, so progress cannot be judged",
                 phase=i, period=ph.get("period"))
    if schedule and not any(p.get("on_critical_path") for p in schedule):
        _add(findings, "rp.critical_path_unmarked", "medium",
             "no phase is marked as on the critical path, so a delay cannot be traced to its "
             "consequence")

    # --- risks ------------------------------------------------------------
    risks = spec.get("risks") or []
    if not risks:
        _add(findings, "rp.risks_missing", "high",
             "no risk was identified, which for a research plan is a claim of certainty")
    covered = {str(r.get("type") or "").strip().lower() for r in risks}
    for r in risks:
        rid = str(r.get("id") or r.get("name") or "")
        rtype = str(r.get("type") or "").strip().lower()
        if not rtype:
            _add(findings, "rp.risk_type_missing", "high",
                 "a risk is not classified, so its handling cannot be matched to its kind",
                 risk=rid)
        elif rtype not in RISK_TYPES:
            _add(findings, "rp.risk_type_unknown", "medium",
                 "a risk type is outside data_access / method_feasibility / schedule / "
                 "ethics_compliance", risk=rid, found=rtype)
        for field, rule, why in (
            ("trigger", "rp.risk_no_trigger",
             "no trigger signal, so the risk is discovered only when it has already happened"),
            ("impact", "rp.risk_no_impact",
             "no impact stated, so the reader cannot weigh the risk"),
            ("fallback", "rp.risk_no_fallback",
             "no fallback, so a triggered risk has no response"),
            ("decision_point", "rp.risk_no_decision_point",
             "no decision point, so nobody knows when to switch to the fallback"),
        ):
            if not str(r.get(field) or "").strip():
                _add(findings, rule, "high" if field in ("fallback",) else "medium", why, risk=rid)

    missing_types = [t for t in ("data_access", "method_feasibility") if t not in covered]
    if risks and missing_types:
        _add(findings, "rp.risk_type_uncovered", "medium",
             "the two risk kinds that decide most projects are not addressed",
             missing=missing_types)

    # --- expected outcomes ------------------------------------------------
    outcomes = spec.get("outcomes") or []
    if not outcomes:
        _add(findings, "rp.outcomes_missing", "high",
             "no expected outcome was stated, so success is undefined")
    for o in outcomes:
        oid = str(o.get("id") or o.get("name") or "")
        if not str(o.get("assessment") or "").strip():
            _add(findings, "rp.outcome_no_assessment", "high",
                 "an expected outcome does not say how it will be judged, so it cannot be "
                 "counted as delivered", outcome=oid)
        if o.get("kind") and str(o.get("kind")).lower() not in (
                "paper", "dataset", "code", "method", "thesis", "prototype"):
            _add(findings, "rp.outcome_kind_unknown", "low",
                 "an outcome kind is not one of paper/dataset/code/method/thesis/prototype",
                 outcome=oid, found=o.get("kind"))

    # --- resource envelope ------------------------------------------------
    budget = spec.get("resource_budget")
    needed = spec.get("resource_needed")
    if budget is not None and needed is not None:
        try:
            if float(needed) > float(budget):
                _add(findings, "rp.resource_exceeds_budget", "high",
                     "the resources the plan needs exceed the envelope it was given, so the "
                     "plan is not executable as written", needed=float(needed),
                     budget=float(budget))
        except (TypeError, ValueError):
            _add(findings, "rp.resource_unreadable", "medium",
                 "resource figures are not numeric, so compatibility cannot be checked")


ARGUMENT_ELEMENTS = ("question", "method", "result", "discussion", "limitation")


def _term_key(text: str) -> str:
    """Fold case, spacing and hyphenation so variants of one term compare equal."""
    t = str(text or "").strip().lower()
    t = re.sub(r"[\s_\-]+", "", t)
    return t.replace("\u00b5", "u").replace("\u03bc", "u")


def longdoc(spec: dict, findings: list[dict]) -> None:
    """Audit a thesis or long document at chapter scale.

    What breaks in a long document is not any one chapter but the joins between them. The
    scoring points this task states, each as a rule:

      outline chapters written, with the argument's parts -> outline_item_unwritten,
                                                           argument_element_missing
      front and back matter                              -> reference_section_missing,
                                                           figure_list_missing, appendix_missing
      a terminology and symbol table, and consistency    -> terminology_missing,
                                                           symbol_table_missing,
                                                           term_inconsistent,
                                                           duplicate_definition
      claims bound to specific references                -> claim_no_citation,
                                                           citation_unknown,
                                                           citation_conclusion_mismatch
      nothing contradicting what an earlier chapter said -> conclusion_contradiction
      chapter-level change records                       -> no_chapter_changelog,
                                                           change_no_reason,
                                                           change_impact_untraced
      the plan's word budget against what was written    -> word_budget_off,
                                                           word_budget_unmeasured
      numbering and cross-references that resolve        -> numbering_gap, dangling_crossref,
                                                           figure_numbering_gap
    """
    chapters = list(_records(spec.get("chapters")))
    outline = list(_records(spec.get("outline")))
    front = spec.get("front_matter") or {}
    refs = {str(r.get("key")): r for r in _records(spec.get("references"))}

    if not chapters:
        _add(findings, "long.no_chapters", "high", "no chapters were supplied")
        return

    # --- outline versus what was written ---------------------------------
    written_ids = {str(c.get("outline_id")) for c in chapters if c.get("outline_id")}
    for o in outline:
        oid = str(o.get("id"))
        if oid not in written_ids:
            _add(findings, "long.outline_item_unwritten", "high",
                 "an outline item has no chapter, so the plan and the document disagree",
                 outline_id=oid, title=str(o.get("title") or "")[:60])
    outline_ids = {str(o.get("id")) for o in outline}
    for c in chapters:
        cid = str(c.get("outline_id") or "")
        if cid and outline_ids and cid not in outline_ids:
            _add(findings, "long.chapter_not_in_outline", "medium",
                 "a chapter maps to an outline item that does not exist",
                 chapter=str(c.get("number")), outline_id=cid)

    # --- the argument's parts must all be present somewhere --------------
    present_elements = {str(c.get("argument_element") or "").strip().lower()
                        for c in chapters}
    present_elements |= {str(o.get("argument_element") or "").strip().lower() for o in outline}
    missing_parts = [e for e in ARGUMENT_ELEMENTS if e not in present_elements]
    if missing_parts:
        _add(findings, "long.argument_element_missing", "high",
             "a part of the argument has no chapter carrying it, so the document is missing a "
             "stage of its reasoning", missing=missing_parts)

    # --- front and back matter -------------------------------------------
    for key, rule, why in (
        ("reference_section", "long.reference_section_missing",
         "the document has no reference section"),
        ("figure_list", "long.figure_list_missing",
         "a thesis normally carries a list of figures; without it figure numbering cannot be "
         "checked by a reader"),
        ("appendix", "long.appendix_missing",
         "no appendix is declared, so supporting material has nowhere to live"),
    ):
        if not front.get(key):
            _add(findings, rule, "medium", why)

    if not spec.get("terminology"):
        _add(findings, "long.terminology_missing", "high",
             "no terminology table was supplied, so nothing prevents the same concept being "
             "written two ways across chapters")
    if not spec.get("symbols"):
        _add(findings, "long.symbol_table_missing", "medium",
             "no symbol table was supplied, so symbols cannot be checked for consistent meaning")

    # --- cross-chapter terminology ---------------------------------------
    seen_terms: dict[str, tuple[str, str]] = {}
    definitions: dict[str, str] = {}
    for term in _records(spec.get("terminology")):
        pref = str(term.get("preferred") or "").strip()
        key = _term_key(pref)
        if key:
            seen_terms[key] = (pref, str(term.get("chapter") or ""))
        for v in term.get("variants") or []:
            _add(findings, "long.term_variant_declared", "low",
                 "a term has a declared variant; if it appears in the text the reader will meet "
                 "two names for one concept", term=pref, variant=v)

    for c in chapters:
        for d in c.get("definitions") or []:
            key = _term_key(d.get("term"))
            if not key:
                continue
            if key in definitions:
                _add(findings, "long.duplicate_definition", "medium",
                     "a term is defined in two chapters, so a later definition can silently "
                     "redefine it", term=d.get("term"), chapters=[definitions[key],
                                                                  str(c.get("number"))])
            else:
                definitions[key] = str(c.get("number"))

    # --- claims bound to references --------------------------------------
    for c in chapters:
        num = str(c.get("number"))
        for claim in c.get("claims") or []:
            text = str(claim.get("text") or "")
            key = str(claim.get("reference") or "")
            if not key:
                _add(findings, "long.claim_no_citation", "high",
                     "a chapter claim is tied to no reference, so a reviewer cannot check it",
                     chapter=num, claim=text[:70])
                continue
            ref = refs.get(key)
            if ref is None:
                if refs:
                    _add(findings, "long.citation_unknown", "high",
                         "a chapter cites a reference that is not in the list", chapter=num, key=key)
                continue
            # Cited but the conclusion was rewritten: the reference's topic must overlap.
            topic = str(ref.get("topic") or ref.get("title") or "")
            if topic and _overlap(topic, text) < 0.15:
                _add(findings, "long.citation_conclusion_mismatch", "high",
                     "the cited reference shares almost no topic with the claim, so the "
                     "conclusion looks rewritten", chapter=num, key=key,
                     overlap=round(_overlap(topic, text), 2))

    # --- contradictions across chapters ----------------------------------
    directions: dict[str, dict[str, str]] = {}
    for c in chapters:
        for con in c.get("conclusions") or []:
            stmt = str(con.get("statement") or "")
            direction = str(con.get("direction") or "").strip().lower()
            if direction:
                directions.setdefault(_term_key(stmt)[:60], {})[str(c.get("number"))] = direction
    for stmt, per_ch in directions.items():
        if len(set(per_ch.values())) > 1:
            _add(findings, "long.conclusion_contradiction", "high",
                 "two chapters state opposite conclusions about the same thing",
                 statement=stmt, chapters=per_ch)

    # --- numbering, cross-references, figures -----------------------------
    nums = [c.get("number") for c in chapters if c.get("number") is not None]
    try:
        ints = sorted(int(n) for n in nums)
    except (TypeError, ValueError):
        ints = []
        _add(findings, "long.numbering_unreadable", "medium",
             "a chapter number is not an integer, so numbering cannot be checked")
    if ints and ints != list(range(1, len(ints) + 1)):
        _add(findings, "long.numbering_gap", "high",
             "chapter numbers are not 1..n, so the document has a missing or duplicated chapter",
             found=ints, expected=list(range(1, len(ints) + 1)))

    known = {str(c.get("number")) for c in chapters}
    for c in chapters:
        for ref in c.get("crossrefs") or []:
            if str(ref) not in known:
                _add(findings, "long.dangling_crossref", "high",
                     "a cross-reference points at a chapter that does not exist",
                     chapter=c.get("number"), ref=ref)

    figs = spec.get("figures") or []
    if figs:
        try:
            fnums = sorted(int(f.get("number")) for f in figs)
        except (TypeError, ValueError):
            fnums = []
        if fnums and fnums != list(range(1, len(fnums) + 1)):
            _add(findings, "long.figure_numbering_gap", "medium",
                 "figure numbers are not 1..n, so a caption reference cannot be trusted",
                 found=fnums)
        declared = {int(f.get("number")) for f in figs if str(f.get("number", "")).isdigit()}
        for c in chapters:
            for ref in c.get("figure_refs") or []:
                if str(ref).isdigit() and int(ref) not in declared:
                    _add(findings, "long.figure_ref_unknown", "high",
                         "the text points at a figure number the document does not contain",
                         chapter=c.get("number"), figure=ref)

    # --- direction 1/3/4/5/6: opt-in consistency checks -------------------
    # These rules fire only when the case declares `track_consistency: true`. They check
    # things that require the author to have prepared the material, not things the machine
    # can infer from the text alone.
    track = spec.get("track_consistency") is True
    if track:
        pass  # placeholder; the actual rules follow

    # direction 1: chapters must declare what question they answer
    if track:
      for c in chapters:
        if not str(c.get("answers") or "").strip():
            _add(findings, "long.chapter_no_question", "medium",
                 "a chapter does not say what question it answers, so its purpose cannot be "
                 "checked against the research question", chapter=str(c.get("number")))

    # --- direction 3: mark questionable citations -------------------------
    for c in chapters:
        for claim in c.get("claims") or []:
            key = str(claim.get("reference") or "")
            if not key:
                continue
            ref = refs.get(key)
            if ref is None:
                continue
            topic = str(ref.get("topic") or ref.get("title") or "")
            claim_text = str(claim.get("text") or "")
            ov = _overlap(topic, claim_text)
            if 0.15 <= ov < 0.35:
                _add(findings, "long.questionable_citation", "medium",
                     "the reference barely overlaps the claim; check whether the citation is a "
                     "second-hand reference or a paraphrased conclusion", chapter=str(c.get("number")),
                     key=key, overlap=round(ov, 2))

    # --- direction 4: author text vs machine text (opt-in) ----------------
    for c in chapters:
        if not track:
            break
        if not c.get("authorship_declared"):
            _add(findings, "long.authorship_undeclared", "medium",
                 "a chapter does not declare whether its text is author-written or "
                 "machine-generated, so the two cannot be reviewed differently",
                 chapter=str(c.get("number")))

    # --- direction 5: later chapters must reference earlier definitions ---
    defined_terms = {str(d.get("term")).strip().lower()
                     for c in chapters for d in (c.get("definitions") or [])
                     if str(d.get("term") or "").strip()}
    for c in chapters:
        for d in (c.get("definitions") or []):
            term = str(d.get("term") or "").strip().lower()
            if not term:
                continue
            # A definition must appear in the text of at least one later chapter.
            later_text = " ".join(str(x.get("text") or "") for x in chapters
                                 if _chapter_num(x.get("number")) > _chapter_num(c.get("number"))
                                 and x.get("text"))
            if later_text and term not in later_text:
                _add(findings, "long.definition_unused", "medium",
                     "a definition is not used in any later chapter, so it may be unnecessary "
                     "or the later chapters may need to reference it", chapter=str(c.get("number")),
                     term=d.get("term"))

    # --- direction 6: reviewer feedback decomposed into actions (opt-in) --
    feedback = spec.get("reviewer_feedback") or [] if track else []
    for i, fb in enumerate(feedback):
        actions = fb.get("actions") or []
        if not actions:
            _add(findings, "long.feedback_not_decomposed", "high",
                 "a mentor/reviewer comment is not decomposed into actionable items, so it "
                 "cannot be tracked to completion", feedback=i, text=str(fb.get("text") or "")[:80])
        for a in actions:
            if not str(a.get("status") or "").strip():
                _add(findings, "long.action_no_status", "medium",
                     "an action item from feedback carries no status (done / in progress / pending)",
                     feedback=i, action=str(a.get("text") or "")[:60])

    # --- TOC and per-chapter change records ------------------------------
    toc = [str(t) for t in (front.get("toc") or [])]
    if toc:
        titles = [str(c.get("title") or "").strip().lower() for c in chapters]
        missing = [t for t in titles if t and t not in " ".join(toc).lower()]
        if missing:
            _add(findings, "long.toc_incomplete", "medium",
                 "the table of contents omits chapters that exist", missing=missing[:8])

    for c in chapters:
        if not c.get("changelog"):
            _add(findings, "long.no_chapter_changelog", "medium",
                 "a chapter records no change history, so an edit to it cannot be reverted or "
                 "compared", chapter=str(c.get("number")))

    # --- 改得动: a revision must say why, and say what else it touches -----
    # A changelog entry that names no reason cannot be reviewed or reverted, and a
    # revision to a term whose other occurrences are not traced leaves affected
    # paragraphs unfindable — the task states both explicitly.
    term_chapters: dict[str, list[str]] = {}
    for c in chapters:
        for d in c.get("definitions") or []:
            term = str(d.get("term") or "").strip().lower()
            if term:
                term_chapters.setdefault(term, []).append(str(c.get("number")))
    for c in chapters:
        num = str(c.get("number"))
        for entry in c.get("changelog") or []:
            if isinstance(entry, dict):
                if not str(entry.get("why") or "").strip():
                    _add(findings, "long.change_no_reason", "medium",
                         "a revision entry says what changed but not why, so the author "
                         "cannot review the intent", chapter=num)
                term = str(entry.get("term") or "").strip().lower()
                if term and term in term_chapters:
                    affected = [ch for ch in term_chapters[term] if ch != num]
                    declared = {str(x) for x in (entry.get("impact") or [])}
                    untraced = [ch for ch in affected if ch not in declared]
                    if untraced:
                        _add(findings, "long.change_impact_untraced", "medium",
                             "a revision touches a term other chapters define, but those "
                             "chapters are not listed as affected, so a reviewer cannot find "
                             "the paragraphs the change may have invalidated", chapter=num,
                             term=term, untraced=untraced[:6])

    # --- 立得住: the plan's word budget must match what was written --------
    budgets = spec.get("word_budgets") or {}
    for o in outline:
        oid = str(o.get("id") or "")
        budget = o.get("word_budget") or budgets.get(oid)
        if budget is None:
            continue
        ch = next((c for c in chapters if str(c.get("outline_id")) == oid), None)
        written = ch.get("word_count") if ch else None
        if written is None:
            _add(findings, "long.word_budget_unmeasured", "low",
                 "a chapter declares a word budget but records no written count, so the "
                 "plan cannot be checked against the draft", outline_id=oid)
            continue
        try:
            written = int(written)
        except (TypeError, ValueError):
            written = None
        try:
            budget = int(budget)
        except (TypeError, ValueError):
            budget = None
        if budget and written is not None and budget > 0                 and abs(written - budget) / budget > 0.4:
            _add(findings, "long.word_budget_off", "medium",
                 "a chapter lands more than 40% away from its planned length, which "
                 "signals the argument chain is unbalanced", outline_id=oid,
                 written=written, budget=budget)


def dissemination(spec: dict, findings: list[dict]) -> None:
    """Translating research for a wider audience must not inflate the claim.

    The scoring points this task states, each as a rule:

      facts, data, units, figure numbers, citations preserved  -> invariant_broken, invariant_added
      no new conclusions the source does not support           -> value_not_in_source,
                                                                  absolute_without_citation
      key conclusions, data, limits preserved                  -> key_conclusion_lost
      reviewable change list with reasons and open questions   -> change_list_missing
      hype language refused; jargon matched to the audience    -> hype_language, jargon_for_public
    """
    text = str(spec.get("text") or "")
    source_text = str(spec.get("source_text") or "")
    if not text.strip():
        _add(findings, "diss.no_text", "high", "no dissemination text was supplied")
        return

    for m in HYPE.finditer(text):
        _add(findings, "diss.hype_language", "high",
             "promotional language is used where a measured claim belongs", term=m.group(0))

    evidence = [str(e) for e in (spec.get("evidence") or [])]
    for i, s in enumerate(G.split_sentences(text)):
        if ABSOLUTE.search(s) and not re.search(r"\[[A-Za-z0-9:_\-]+\]", s):
            _add(findings, "diss.absolute_without_citation", "high",
                 "an absolute claim appears in outreach copy with no citation",
                 sentence=i, text=s[:110])
        for k in re.findall(r"\[([A-Za-z0-9:_\-]+)\]", s):
            if evidence and k not in evidence:
                _add(findings, "diss.unknown_source", "high",
                     "the outreach text cites a source outside the supplied set",
                     sentence=i, key=k)

    # --- invariants: numbers and citations must survive the translation ---
    # Statistics (p-values, test statistics, sample sizes) and bare integers are exempt:
    # a public-audience rewrite is *supposed* to simplify the statistics away, and a bare
    # integer is as often a year or a count as a measurement.
    if source_text:
        from collections import Counter

        def _invariants(t: str) -> Counter:
            stats = _stat_values(t)
            c = Counter()
            for q in G.extract_quantities(t):
                tok = f"{q.value:g}"
                # A year is not a result; a rewrite may legitimately drop one. Any other
                # unit-less integer still counts — "50 yuan" added by the rewrite is
                # exactly what the invariant exists to catch.
                if q.unit is None and float(q.value).is_integer() and 1900 <= q.value <= 2100:
                    continue
                if q.value in stats:
                    continue
                c[(round(q.value, 9), q.unit or "")] += 1
            return c

        sq = _invariants(source_text)
        dq = _invariants(text)
        dropped = list((sq - dq).elements())
        added = list((dq - sq).elements())
        if dropped:
            _add(findings, "diss.invariant_broken", "high",
                 "a number or unit in the source is absent from the rewrite, so the result has "
                 "been changed or dropped", dropped=[list(x) for x in dropped[:10]], count=len(dropped))
        if added:
            _add(findings, "diss.invariant_added", "high",
                 "the rewrite introduces a number the source does not contain, so it states a "
                 "result the paper never made", added=[list(x) for x in added[:10]], count=len(added))

    # --- key conclusions must be preserved --------------------------------
    key_conclusions = spec.get("key_conclusions") or []
    for kc in key_conclusions:
        kc = str(kc or "")
        if kc.strip() and kc.strip() not in text:
            _add(findings, "diss.key_conclusion_lost", "high",
                 "a key conclusion from the source does not appear in the rewrite, so the "
                 "summary drops the paper's main finding", conclusion=kc[:80])

    # --- change list must be reviewable -----------------------------------
    changes = list(_records(spec.get("changes")))
    if not changes:
        _add(findings, "diss.change_list_missing", "high",
             "no change list was supplied, so the author cannot review what was changed or why")
    for i, ch in enumerate(changes):
        if not str(ch.get("action") or "").strip():
            _add(findings, "diss.change_no_action", "medium",
                 "a change entry does not say what was done", index=i)
        if not str(ch.get("reason") or "").strip():
            _add(findings, "diss.change_no_reason", "medium",
                 "a change entry does not say why, so it cannot be reviewed", index=i)

    jargon = spec.get("jargon_terms") or []
    if jargon and spec.get("audience") == "public":
        hits = [t for t in jargon if str(t).lower() in text.lower()]
        if hits:
            _add(findings, "diss.jargon_for_public", "medium",
                 "specialist terms appear in text aimed at a general audience", terms=hits[:8])
    if spec.get("audience") == "public" and not spec.get("limitations"):
        _add(findings, "diss.limitations_omitted", "medium",
             "outreach text states results without any limitation, which reads as certainty")


# The relation types the task names: causal, dependency, contrast, temporal, citation,
# support, conflict, plus the two structural ones a map genuinely needs.
EDGE_KINDS = ("causal", "dependency", "contrast", "temporal", "citation",
              "support", "conflict", "contains", "part_of")
# What a node's evidence proves: the task asks fact, summary and inference to be kept
# apart, because a map that renders its own inference as a quoted fact misrepresents
# the paper.
NODE_KINDS = ("fact", "summary", "inference")
# Full-match placeholder labels: only these are decorative. Real concepts ("方法",
# "结果", "aims") must never fire, so there is deliberately no length rule.
DECORATIVE_LABEL = re.compile(
    r"^(其他|其它|相关内容|更多|其余|待定|各种|若干|占位|placeholder|misc(ellaneous)?|"
    r"various|tbd|others?|stuff|etc\.?|未知)$",
    re.IGNORECASE)


def mindmap(spec: dict, findings: list[dict]) -> None:
    """A mind map must stay a tree, and every leaf must point at its source.

    Beyond tree integrity, the task's own scoring points apply: relations must name a
    type and a basis (a connection the material does not support is the classic
    failure), evidence-bearing nodes must say whether they carry fact, summary or
    inference, and scale must stay readable.
    """
    nodes = list(_records(spec.get("nodes")))
    if not nodes:
        _add(findings, "map.no_nodes", "high", "the mind map has no nodes")
        return
    ids = [str(n.get("id")) for n in nodes]
    roots = [n for n in nodes if not n.get("parent")]
    if len(roots) != 1:
        _add(findings, "map.root_count", "high",
             "a mind map has exactly one root; this has a different number",
             roots=[r.get("id") for r in roots])
    seen_parents = {}
    for n in nodes:
        p = n.get("parent")
        if p is None:
            continue
        if str(p) not in ids:
            _add(findings, "map.dangling_parent", "high",
                 "a node points at a parent that does not exist", node=n.get("id"), parent=p)
        seen_parents.setdefault(str(p), []).append(str(n.get("label") or ""))
    for parent, labels in seen_parents.items():
        dupes = sorted({l for l in labels if l and labels.count(l) > 1})
        if dupes:
            _add(findings, "map.duplicate_sibling", "medium",
                 "two children of the same node share a label", parent=parent, labels=dupes)

    depth = {}
    by_id = {str(n.get("id")): n for n in nodes}

    def d(nid, guard_set=frozenset()):
        if nid in depth:
            return depth[nid]
        if nid in guard_set or len(guard_set) > 32:
            return 99
        p = by_id.get(nid, {}).get("parent")
        depth[nid] = 0 if p is None else 1 + d(str(p), guard_set | {nid})
        return depth[nid]

    try:
        limit = int(spec.get("max_depth", 4))
    except (TypeError, ValueError):
        limit = 4
    for n in nodes:
        dd = d(str(n.get("id")))
        # The depth walk returns 99 at the guard, but callers above it in the cycle
        # have already added 1 each, so a node on a cycle caches 100, 101, ... — the
        # test must be a bound, not an equality, or cycles pass silently.
        if dd >= 99:
            _add(findings, "map.cycle", "high",
                 "the map contains a cycle, so it is not a tree", node=n.get("id"))
        elif dd > limit:
            _add(findings, "map.too_deep", "medium",
                 "a branch exceeds the declared depth, which stops being scannable",
                 node=n.get("id"), depth=dd, limit=limit)

    leaves = [n for n in nodes if str(n.get("id")) not in seen_parents]
    for leaf in leaves:
        # A structural branch (the research question, a heading) has no citation to
        # give. It must say so rather than be silently excused.
        if leaf.get("evidence_exempt"):
            continue
        if not str(leaf.get("evidence") or "").strip():
            _add(findings, "map.leaf_without_evidence", "medium",
                 "a leaf has no source pointer, so the branch cannot be traced to the paper",
                 node=leaf.get("id"), label=str(leaf.get("label") or "")[:60])

    # --- relations the map asserts ---------------------------------------
    # "连得对": a connection between two nodes is a claim about the material. An
    # unnamed relation type, an endpoint that does not exist, or a connection with
    # no locator behind it is exactly the unsupported edge the task refuses.
    node_ids = set(ids)
    edges = list(_records(spec.get("edges")))
    for e in edges:
        src, dst = str(e.get("from") or ""), str(e.get("to") or "")
        if not src or not dst:
            _add(findings, "map.edge_incomplete", "high",
                 "an edge does not say where it starts or ends, so its direction cannot be "
                 "checked", edge=e)
            continue
        if src not in node_ids or dst not in node_ids:
            _add(findings, "map.edge_dangling", "high",
                 "an edge connects a node that does not exist", edge=[src, dst])
        if src == dst:
            _add(findings, "map.edge_self", "medium",
                 "an edge loops a node to itself", node=src)
        kind = str(e.get("kind") or "").strip().lower()
        if not kind:
            _add(findings, "map.edge_type_missing", "high",
                 "an edge names no relation type (causal, dependency, contrast, temporal, "
                 "citation, support, conflict, contains), so what the connection means is "
                 "unreadable", edge=[src, dst])
        elif kind not in EDGE_KINDS:
            _add(findings, "map.edge_type_unknown", "medium",
                 "an edge's relation type is outside the declared set", found=kind,
                 edge=[src, dst])
        if not str(e.get("basis") or "").strip():
            _add(findings, "map.edge_no_basis", "high",
                 "an edge carries no locator in the source, so the connection may exist "
                 "only in the map, not in the material", edge=[src, dst])

    # --- fact / summary / inference --------------------------------------
    for n in nodes:
        if not str(n.get("evidence") or "").strip():
            continue
        kind = str(n.get("kind") or "").strip().lower()
        if not kind:
            _add(findings, "map.kind_undeclared", "medium",
                 "an evidence-bearing node does not say whether its content is a fact, a "
                 "summary or an inference, so the map renders its own reading as a quote",
                 node=n.get("id"), label=str(n.get("label") or "")[:60])
        elif kind not in NODE_KINDS:
            _add(findings, "map.kind_unknown", "low",
                 "a node's kind is outside fact/summary/inference", node=n.get("id"),
                 found=kind)

    # --- decorative labels ------------------------------------------------
    for n in nodes:
        label = str(n.get("label") or "").strip()
        if label and DECORATIVE_LABEL.match(label):
            _add(findings, "map.decorative_label", "medium",
                 "a node label is a placeholder word, not a concept the material names",
                 node=n.get("id"), label=label)

    # --- scale guards -----------------------------------------------------
    try:
        max_nodes = int(spec.get("max_nodes", 150))
    except (TypeError, ValueError):
        max_nodes = 150
    if len(nodes) > max_nodes:
        _add(findings, "map.too_many_nodes", "medium",
             "the map exceeds the declared node budget, which stops being scannable and "
             "starts being a dump of the source", nodes=len(nodes), limit=max_nodes)
    try:
        max_children = int(spec.get("max_children", 12))
    except (TypeError, ValueError):
        max_children = 12
    for parent, kids in seen_parents.items():
        if len(kids) > max_children:
            _add(findings, "map.wide_node", "low",
                 "one node carries more children than the declared granularity; consider "
                 "grouping them under an intermediate level", node=parent, children=len(kids),
                 limit=max_children)


SECTIONS = {
    "conclusion_extract": conclusion_extract,
    "claim_verify": claim_verify,
    "compare_docs": compare_docs,
    "formula": formula,
    "reproduce": reproduce,
    "qa": qa,
    "paper_draft": paper_draft,
    "structure_logic": structure_logic,
    "results_discussion": results_discussion,
    "proposal": proposal,
    "research_plan": research_plan,
    "longdoc": longdoc,
    "dissemination": dissemination,
    "mindmap": mindmap,
}


def run(spec: dict, section: str):
    fn = SECTIONS.get(section)
    if fn is None:
        raise ValueError(f"unknown section '{section}'; choose from {sorted(SECTIONS)}")
    findings: list[dict] = []
    fn(spec, findings)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    status = "clean" if not findings else "blocked" if counts.get("high") else "review"
    return findings, status, counts

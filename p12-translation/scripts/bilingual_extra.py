"""Conservative bilingual alignment and identity checks (standard library only).

These checks supplement, never replace, the fluent translation written by the
model. They are deliberately structural: no claim that fluency can be scored by
regex. Persistent-citation parsing follows the public Manubot @prefix:accession
model; bare DOI URLs and @doi keys are recognized as the same identity.
"""
from __future__ import annotations

from collections import Counter
import re

import guard as G

_MATH_PATTERNS = (
    re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", re.S),
    re.compile(r"\\\[(.*?)\\\]", re.S),
    re.compile(r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?)\}(.*?)\\end\{\1\}", re.S),
)
_DOI = re.compile(r"(?<![\w.])10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_PID_KEY = re.compile(
    r"(?<![\w@])@(doi|arxiv|pubmed|pmid|pmc|isbn|issn|handle|biorxiv|medrxiv|"
    r"https?|url):([^\s;,\]\}]+)", re.I)
_ALIAS = re.compile(r"(?<![\w@])@([A-Za-z_][A-Za-z0-9_.:-]*)(?=[\s;\],])")
_NEG = re.compile(
    r"\b(?:not|no|never|without|none|neither|nor|cannot|can't|doesn't|does not|"
    r"isn't|is not|aren't|are not|was not|were not)\b"
    r"|并非|没有|不(?!超过|少于|仅|只|但|同|足|错)|无(?!论|限)|未(?!来)", re.I)
_EPISTEMIC = re.compile(
    r"\b(?:may|might|could|possibly|likely|appears?|seems?|suggests?|indicates?)\b"
    r"|可能|也许|似乎|推测|倾向于|提示|表明", re.I)


def negation_count(text: str) -> int:
    """Count actual negative operators, excluding 非 in 除非 and 未 in 未来."""
    return sum(1 for _ in _NEG.finditer(text or ""))
# Presence is compared per group, not the number of English/Chinese function
# words. Every group has an explicit scope-changing meaning in either language.
_LIMITERS = {
    "only": re.compile(r"\b(?:only|solely|just)\b|仅(?:仅)?|只有|只是", re.I),
    "lower_bound": re.compile(r"\b(?:at least|no less than|minimum of)\b|至少|不少于|最低", re.I),
    "upper_bound": re.compile(r"\b(?:at most|no more than|up to|maximum of)\b|至多|最多|不超过|上限", re.I),
    "condition": re.compile(r"\b(?:if|provided that|conditional on|subject to)\b|如果|若|在.+条件下|前提是", re.I),
    "exception": re.compile(r"\b(?:unless|except(?: for)?|other than)\b|除非|除外|除了", re.I),
    "approximation": re.compile(r"\b(?:approximately|about|around|roughly|circa|ca\.)\b|约|大约|近|左右|上下", re.I),
}


def _contains(pattern, text: str) -> bool:
    return bool(pattern.search(G.normalise(text or "")))


def _normal_form(text: str) -> str:
    text = G.normalise(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normal_math(text: str) -> str:
    text = _normal_form(text)
    return re.sub(r"\\(left|right|displaystyle|!|,|;|:)", "", text)


def extract_math(text: str) -> list[str]:
    text = text or ""
    out = []
    for pattern in _MATH_PATTERNS:
        for match in pattern.finditer(text):
            body = match.group(match.lastindex or 1)
            if pattern is _MATH_PATTERNS[-1]:
                body = match.group(2)
            body = normal_math(body)
            if body:
                out.append(body)
    return out


def persistent_citations(text: str) -> list[str]:
    """Canonical citation identities, preserving multiplicity within a cluster.

    PID spans are claimed first so the DOI in ``@doi:...`` is not counted twice.
    A DOI resolver URL has the same DOI identity rather than becoming a new URL source.
    """
    text = G.normalise(text or "")
    found = []
    occupied = []
    for match in _PID_KEY.finditer(text):
        prefix = match.group(1).lower()
        accession = match.group(2).rstrip(".;)]}")
        occupied.append(match.span())
        doi = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", accession, re.I)
        if prefix == "doi" or (doi and "doi.org/" in accession.lower()):
            value = doi.group(0).rstrip(".;)]}") if doi else accession
            found.append("doi:" + value.lower())
        elif prefix in ("http", "https", "url"):
            found.append("url:" + accession)
        else:
            found.append(prefix + ":" + accession.lower())
    for match in _DOI.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        value = match.group(0).rstrip(".;,;)]}")
        found.append("doi:" + value.lower())
    # A bare @accession alias is meaningful only in a bracketed citation cluster;
    # email addresses and social-media handles are not treated as references.
    for bracket in re.finditer(r"\[[^\]]+\]", text):
        for match in _ALIAS.finditer(bracket.group(0)):
            alias = match.group(1)
            if ":" not in alias:
                found.append("alias:" + alias)
    return found


def extract_xrefs(text: str) -> list[str]:
    """Language-neutral figure/table/equation/section identities.

    G.extract_xrefs first finds the actual spans in either language; this layer
    compares their scientific identity, not whether the translator used Fig. or 图.
    """
    out = []
    for raw in G.extract_xrefs(text or ""):
        token = G.normalise(raw).strip().lower()
        token = re.sub(r"\s+", "", token)
        token = token.replace("supplementary", "supp.")
        replacements = (
            ("figures", "fig"), ("figure", "fig"), ("fig.", "fig"), ("fig", "fig"),
            ("tables", "tab"), ("table", "tab"), ("tab.", "tab"), ("tab", "tab"),
            ("equations", "eq"), ("equation", "eq"), ("eq.", "eq"), ("eq", "eq"),
            ("sections", "sec"), ("section", "sec"), ("sec.", "sec"),
        )
        # Longest English prefix first; each replacement returns immediately so
        # `figure` cannot become `fig.ure` through repeated substitutions.
        kind = None
        for prefix, name in replacements:
            if token.startswith(prefix):
                kind = name
                token = token[len(prefix):]
                break
        if kind is None:
            for prefix, name in (("图", "fig"), ("表", "tab"), ("公式", "eq"),
                                 ("式", "eq"), ("章节", "sec")):
                if token.startswith(prefix):
                    kind = name
                    token = token[len(prefix):]
                    break
        token = token.lstrip(".:")
        out.append((kind or "xref", token))
    return out


_MAGNITUDES = {"万": 1e4, "亿": 1e8, "thousand": 1e3, "million": 1e6, "billion": 1e9}
_NUMBER_SCALE = re.compile(
    r"^\s*([-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*"
    r"(万|亿|thousand|million|billion)?\s*$", re.I)


def _number_and_scale(value):
    if not isinstance(value, str):
        return None
    match = _NUMBER_SCALE.fullmatch(G.normalise(value).strip())
    if not match:
        return None
    try:
        coefficient = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    scale = _MAGNITUDES.get((match.group(2) or "").lower(), 1.0)
    return coefficient, coefficient * scale, scale


def conversion_records(spec: dict, add) -> list[dict]:
    """Validate declared arithmetic and return records usable for exact diffs."""
    if not spec.get("conversions"):
        return []
    raw = spec.get("conversions")
    if not isinstance(raw, list):
        add("xlate.conversion_malformed", "medium",
            "conversions must be a list of {from,to,factor?} objects")
        return []
    valid = []
    for index, record in enumerate(raw):
        if not isinstance(record, dict):
            add("xlate.conversion_malformed", "medium",
                "a conversion entry is not an object", index=index)
            continue
        source = _number_and_scale(record.get("from"))
        target = _number_and_scale(record.get("to"))
        if not source or not target:
            add("xlate.conversion_malformed", "medium",
                "conversion from/to must be an explicit number, optionally with 万/亿/"
                "thousand/million/billion", index=index)
            continue
        if abs(source[1] - target[1]) > max(1e-9, abs(source[1]) * 1e-9):
            add("xlate.conversion_arithmetic_mismatch", "high",
                "declared conversion endpoints represent different actual quantities",
                index=index, source_actual=source[1], target_actual=target[1])
            continue
        factor = record.get("factor")
        if factor is not None:
            try:
                numeric_factor = float(str(factor).strip())
            except (ValueError, TypeError):
                numeric_factor = -1.0
            if numeric_factor <= 0 or numeric_factor not in (source[2], target[2]):
                add("xlate.conversion_factor_mismatch", "medium",
                    "factor must equal the source or target magnitude scale; endpoint "
                    "arithmetic is the primary check", index=index, factor=str(factor),
                    accepted=[source[2], target[2]])
        valid.append({"from_coefficient": source[0], "to_coefficient": target[0],
                      "factor": source[2] if factor is None else factor,
                      "source_actual": source[1], "target_actual": target[1]})
    return valid


def conversion_allowed(records: list[dict], source: float, target: float) -> bool:
    """True only when the exact dropped/added coefficients have a valid record."""
    close = lambda a, b: abs(a - b) <= max(1e-9, abs(a) * 1e-9)
    return any(close(record["from_coefficient"], source)
               and close(record["to_coefficient"], target) for record in records)


def _inventory_diff(source: str, target: str, extractor):
    src, tgt = Counter(extractor(source)), Counter(extractor(target))
    return list((src - tgt).elements()), list((tgt - src).elements())


def _audit_alignment(spec: dict, segments: list[dict], add) -> None:
    source = spec.get("source_text")
    if spec.get("output_mode") not in ("bilingual", "tracked") or not segments:
        return
    if not isinstance(source, str) or not source.strip():
        return
    canonical_source = _normal_form(source)
    positions = []
    missing = []
    duplicates = []
    occurrence_index = {}
    for index, segment in enumerate(segments):
        chunk = _normal_form(str(segment.get("source") or ""))
        if not chunk:
            continue
        # Repeated source paragraphs are legitimate: pair them with successive
        # occurrences instead of calling every repeat a fabricated duplicate.
        occurrence = occurrence_index.get(chunk, 0)
        occurrence_index[chunk] = occurrence + 1
        pos, cursor = -1, 0
        for _ in range(occurrence + 1):
            pos = canonical_source.find(chunk, cursor)
            if pos < 0:
                break
            cursor = pos + len(chunk)
        sid = str(segment.get("id") or index)
        if pos < 0:
            if canonical_source.find(chunk) >= 0:
                duplicates.append(sid)
            else:
                missing.append(sid)
        else:
            positions.append((sid, pos, index))
    if duplicates:
        add("xlate.segment_duplicate_source", "high",
            "multiple pairs claim more occurrences of one source span than source_text contains",
            segment_ids=duplicates[:10], count=len(duplicates))
    if missing:
        add("xlate.segment_source_mismatch", "high",
            "a segment's declared source is not a contiguous span of the supplied source_text; "
            "the pair cannot be traced and may duplicate or rewrite the source",
            segment_ids=missing[:10], count=len(missing))
    if [x[1] for x in positions] != sorted(x[1] for x in positions):
        add("xlate.segment_order_changed", "high",
            "segment offsets are not monotonically increasing in source_text, so bilingual "
            "paragraph/sentence order changed", order=[x[0] for x in positions])

def _audit_segment_boundaries(segments: list[dict], add) -> None:
    for index, segment in enumerate(segments):
        src, tgt = str(segment.get("source") or ""), str(segment.get("target") or "")
        if not src.strip() or not tgt.strip():
            continue
        sid = str(segment.get("id") or index)
        source_neg, target_neg = negation_count(src), negation_count(tgt)
        if source_neg != target_neg and (source_neg or target_neg):
            add("xlate.segment_negation_changed", "high",
                "negation count changed inside this aligned segment; the document-level count "
                "can hide a moved or inverted negation", segment_id=sid,
                source_count=source_neg, target_count=target_neg)
        for name, pattern in _LIMITERS.items():
            s_hit, t_hit = _contains(pattern, src), _contains(pattern, tgt)
            if s_hit != t_hit:
                add("xlate.segment_limiter_changed", "high",
                    "a restrictive, conditional or approximate qualifier was added or lost in "
                    "this aligned segment", segment_id=sid, qualifier=name,
                    source_present=s_hit, target_present=t_hit)
        # Modal/epistemic presence is distinct from approximate quantity: 约 is
        # not proof that a source may/suggest was retained in every clause.
        s_hedge, t_hedge = bool(_EPISTEMIC.search(src)), bool(_EPISTEMIC.search(tgt))
        if s_hedge != t_hedge:
            add("xlate.segment_hedge_changed", "high",
                "epistemic qualification is present on only one side of this aligned pair",
                segment_id=sid, source_hedged=s_hedge, target_hedged=t_hedge)


def _audit_ambiguities(spec: dict, segments: list[dict], add) -> None:
    if "ambiguities" not in spec:
        return
    registry = spec.get("ambiguities")
    if not isinstance(registry, list):
        add("xlate.ambiguity_registry_malformed", "medium",
            "ambiguities must be a list of {segment, issue, status, resolution} objects")
        return
    ids = {str(s.get("id") or "") for s in segments if s.get("id")}
    for index, item in enumerate(registry):
        if not isinstance(item, dict):
            add("xlate.ambiguity_entry_malformed", "medium",
                "an ambiguity record is not an object", index=index)
            continue
        sid = str(item.get("segment") or "")
        issue = str(item.get("issue") or "").strip()
        status = str(item.get("status") or "resolved").strip().lower()
        resolution = str(item.get("resolution") or "").strip()
        if ids and sid not in ids:
            add("xlate.ambiguity_orphaned", "medium",
                "an ambiguity record points at an unknown segment id", segment_id=sid, index=index)
        if not issue:
            add("xlate.ambiguity_unspecified", "medium",
                "a back-check record does not identify the ambiguity to review", index=index)
        if status in ("open", "pending", "human_review") and not resolution:
            # Pending is an honest terminal state; do not mutate the input spec or
            # silently turn the item into a resolved editorial claim.
            resolution = "human confirmation is still required"
        if not resolution:
            add("xlate.ambiguity_unresolved", "high",
                "a declared ambiguity has neither a resolution nor an explicit open/human_review status",
                segment_id=sid, index=index)


def audit(spec: dict, source: str, target: str, segments: list[dict], add) -> None:
    """Run invariant and source-anchored checks. All inputs other than text are opt-in."""
    if source.strip() or target.strip():
        for label, extractor, missing_rule, added_rule, human in (
            ("math", extract_math, "xlate.formula_missing", "xlate.formula_added",
             "a formula or mathematical expression"),
            ("persistent_citation", persistent_citations,
             "xlate.citation_identity_missing", "xlate.citation_identity_added",
             "a DOI/arXiv/PubMed/Manubot citation identity"),
        ):
            missing, added = _inventory_diff(source, target, extractor)
            if missing:
                add(missing_rule, "high", f"target drops {human}",
                    invariant=label, dropped=missing[:10], count=len(missing))
            if added:
                add(added_rule, "high", f"target introduces {human} absent from the source",
                    invariant=label, added=added[:10], count=len(added))
    _audit_alignment(spec, segments, add)
    if spec.get("output_mode") in ("bilingual", "tracked"):
        _audit_segment_boundaries(segments, add)
    _audit_ambiguities(spec, segments, add)


def evidence(source: str, target: str) -> list[dict]:
    out = []
    for kind, extractor in (("formula", extract_math), ("persistent_citation", persistent_citations)):
        src, tgt = Counter(extractor(source)), Counter(extractor(target))
        for key in sorted(set(src) | set(tgt)):
            verdict = "match" if src.get(key) and tgt.get(key) else "dropped" if src.get(key) else "added"
            out.append({"kind": kind, "value": key, "source_count": src.get(key, 0),
                        "target_count": tgt.get(key, 0), "verdict": verdict})
    return out


def open_questions(spec: dict) -> list[dict]:
    out = []
    registry = spec.get("ambiguities")
    if isinstance(registry, list):
        for index, item in enumerate(registry):
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").lower()
            if status in ("open", "pending", "human_review"):
                out.append({"type": "human_review", "kind": "ambiguity_backcheck",
                            "segment": str(item.get("segment") or ""),
                            "issue": str(item.get("issue") or ""), "index": index})
    # Explicit disclosure that naturalness is editorial evidence, never a regex score.
    review = spec.get("naturalness_review")
    if isinstance(review, dict):
        spans = review.get("literal_spans")
        spans = spans if isinstance(spans, list) else []
        for span in spans:
            if isinstance(span, dict) and str(span.get("status") or "") in ("open", "human_review"): 
                out.append({"type": "human_review", "kind": "naturalness",
                            "segment": str(span.get("segment") or ""),
                            "issue": "literal/awkward span needs editorial confirmation"})
    return out

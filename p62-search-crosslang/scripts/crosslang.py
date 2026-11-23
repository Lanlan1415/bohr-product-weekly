"""Controlled multilingual query generation, original-text evidence and work-level recall."""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import case_common as C

SCHEMA_VERSION = "search-crosslang/v2"
LANG_NAMES = {"zh": "Chinese", "en": "English", "pt": "Portuguese", "ja": "Japanese",
              "de": "German", "fr": "French", "es": "Spanish", "ko": "Korean", "ru": "Russian"}
LANG_ALIASES = {"english": "en", "portuguese": "pt", "chinese": "zh", "japanese": "ja",
                "german": "de", "french": "fr", "spanish": "es", "korean": "ko",
                "英文": "en", "葡文": "pt", "葡萄牙文": "pt", "中文": "zh", "日文": "ja"}
PT_STOP = {"de", "da", "do", "das", "dos", "uma", "um", "para", "com", "em", "os", "as", "por", "que"}
EN_STOP = C.STOP | {"of", "in", "on", "to", "a", "an", "by", "is", "be", "this", "these", "those"}
PRF_STOP = EN_STOP | PT_STOP | {"sobre", "entre", "ainda", "como", "mais", "their", "there", "which"}


def _lang(value: Any) -> str:
    text = C.as_text(value).strip().lower().replace("_", "-")
    if not text:
        return "und"
    text = LANG_ALIASES.get(text, text)
    return text.split("-")[0] if text.split("-")[0] in LANG_NAMES else text


def detect_language(doc: dict[str, Any]) -> dict[str, Any]:
    declared = _lang(doc["metadata"].get("language"))
    text = _scientific_text(doc)
    has_han = bool(C.CJK_RE.search(text))
    has_kana = bool(re.search(r"[\u3040-\u30ff]", text))
    has_hangul = bool(re.search(r"[\uac00-\ud7af]", text))
    has_cyrillic = bool(re.search(r"[\u0400-\u04ff]", text))
    inferred, confidence, evidence = "und", "low", "Latin script alone cannot distinguish English from Portuguese"
    if has_kana:
        inferred, confidence, evidence = "ja", "script", "Hiragana/Katakana present"
    elif has_han:
        inferred, confidence, evidence = "zh", "script_with_cjk_caveat", "Han present without kana; Chinese/Japanese still requires metadata confirmation"
    elif has_hangul:
        inferred, confidence, evidence = "ko", "script", "Hangul present"
    elif has_cyrillic:
        inferred, confidence, evidence = "und", "script_only", "Cyrillic script does not distinguish Russian/Ukrainian/etc."
    else:
        latin = re.findall(r"(?<![\w])[A-Za-zÀ-ÖØ-öø-ÿ]+(?![\w])", text.casefold())
        en_score = sum(word in EN_STOP for word in latin)
        pt_score = sum(word in PT_STOP for word in latin)
        if len(latin) >= 8 and abs(en_score - pt_score) >= 3 and max(en_score, pt_score) >= 3:
            inferred = "en" if en_score > pt_score else "pt"
            confidence, evidence = "stopword_clue", f"English score={en_score}; Portuguese score={pt_score}"
    final = declared if declared != "und" else inferred
    conflict = declared == "en" and (has_han or has_kana or has_hangul) and not re.search(r"[A-Za-z]", text)
    return {"declared": None if declared == "und" else declared, "inferred": inferred,
            "routed_language": final, "confidence": "declared_metadata" if declared != "und" else confidence,
            "evidence": evidence, "script_metadata_conflict": conflict, "requires_review": declared == "und" or conflict}


def tokenize_with_offsets(text: str) -> list[dict[str, Any]]:
    """Real surface tokens for PRF: Latin stems are NOT guessed; CJK uses measured bigrams."""
    tokens: list[dict[str, Any]] = []
    covered: list[tuple[int, int]] = []
    for match in re.finditer(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", text or "", re.UNICODE):
        value = match.group(0)
        if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", value):
            tokens.append({"token": value.casefold(), "surface": value, "start": match.start(), "end": match.end(),
                           "kind": "latin_word_boundary"})
            covered.append((match.start(), match.end()))
        elif C.CJK_RE.search(value) or re.fullmatch(r"[\u3040-\u30ff]+", value):
            # Han runs and kana are emitted by dedicated measured-span scanners below.
            continue
        else:
            tokens.append({"token": value.casefold(), "surface": value, "start": match.start(), "end": match.end(),
                           "kind": "script_word"})
            covered.append((match.start(), match.end()))
    for match in re.finditer(r"[\u3040-\u30ff]+", text or ""):
        value = match.group(0)
        tokens.append({"token": value.casefold(), "surface": value, "start": match.start(), "end": match.end(),
                       "kind": "japanese_kana_run"})
    for match in C.CJK_RE.finditer(text or ""):
        run = match.group(0)
        if len(run) == 1:
            tokens.append({"token": run, "surface": run, "start": match.start(), "end": match.end(), "kind": "cjk_unigram"})
        else:
            for i in range(len(run) - 1):
                tokens.append({"token": run[i:i + 2], "surface": run[i:i + 2],
                               "start": match.start() + i, "end": match.start() + i + 2, "kind": "cjk_bigram_measured_span"})
    tokens.sort(key=lambda x: (x["start"], x["end"], x["token"]))
    return tokens


def _term_items(value: Any, provenance: str, kind: str = "variant") -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else [value]
    out = []
    for item in rows:
        if isinstance(item, str):
            if item.strip():
                out.append({"term": item.strip(), "kind": kind, "provenance": provenance})
        elif isinstance(item, dict):
            term = C.first(item, "term", "text", "label", "value", "name")
            if not term:
                continue
            out.append({"term": C.as_text(term), "kind": C.first(item, "kind", "type") or kind,
                        "provenance": C.first(item, "provenance", "source", "reference") or provenance,
                        "translation_service": C.first(item, "translation_service", "service"),
                        "translation_version": C.first(item, "translation_version", "service_version")})
    return out


def _concept_terms(entry: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    terms_obj = C.first(entry, "terms", "translations", "languages", "language_terms") or {}
    values = []
    if isinstance(terms_obj, dict):
        values = terms_obj.get(lang, [])
        if not values:
            values = terms_obj.get(LANG_NAMES.get(lang, ""), [])
    if not values:
        values = entry.get(lang, entry.get(LANG_NAMES.get(lang, ""), []))
    rows = _term_items(values, C.first(entry, "provenance", "source", "reference") or "caller_supplied_term_table")
    for key in ("synonyms", "spelling_variants", "misspellings", "abbreviations", "transliterations",
                "local_names", "controlled_terms", "controlled_vocabulary"):
        extras = entry.get(key)
        if isinstance(extras, dict):
            rows.extend(_term_items(extras.get(lang, extras.get(LANG_NAMES.get(lang, ""), [])),
                                    C.first(entry, "provenance", "source") or "term_table", key))
    for item in rows:
        item.setdefault("translation_service", C.first(entry, "translation_service", "service"))
        item.setdefault("translation_version", C.first(entry, "translation_version", "service_version"))
    unique = {}
    for item in rows:
        if item.get("term"):
            unique.setdefault(item["term"].casefold(), item)
    return list(unique.values())


def _concepts(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw = C.first(spec, "concepts", "term_table", "terminology", "concept_map") or []
    if isinstance(raw, dict):
        if any(k in raw for k in ("terms", "translations", "languages", "concept", "id")):
            raw = [raw]
        elif all(_lang(k) in LANG_NAMES and not isinstance(v, dict) for k, v in raw.items()):
            raw = [{"id": "concept-01", "terms": raw}]
        else:
            raw = [dict(value, id=key) if isinstance(value, dict) else {"id": key, "terms": value}
                   for key, value in raw.items()]
    if isinstance(raw, str):
        raw = [{"id": "concept-01", "terms": {"und": [raw]}}]
    concepts = []
    if not isinstance(raw, list):
        return concepts
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            entry = {"terms": {"und": [entry]}}
        if not isinstance(entry, dict):
            continue
        concept_id = C.as_text(C.first(entry, "id", "concept_id", "name") or f"concept-{i + 1:02d}")
        concepts.append({"id": concept_id, "label": C.first(entry, "concept", "label", "name") or concept_id,
                         "source": C.first(entry, "source", "reference", "provenance"),
                         "translation_service": C.first(entry, "translation_service", "service"),
                         "translation_version": C.first(entry, "translation_version", "service_version"),
                         "license": C.first(entry, "license", "licence"), "original": entry})
    if not concepts:
        raise C.MaterialError("crosslang.no_concepts", "no controlled multilingual concept table was supplied")
    return concepts


def _targets(spec: dict[str, Any], concepts: list[dict[str, Any]]) -> list[str]:
    raw = C.first(spec, "target_languages", "query_languages", "languages")
    if isinstance(raw, str):
        raw = re.split(r"[,，;； ]+", raw)
    if not isinstance(raw, list) or not raw:
        found = set()
        for concept in concepts:
            terms = C.first(concept["original"], "terms", "translations", "languages") or {}
            if isinstance(terms, dict):
                found.update(_lang(k) for k in terms)
        raw = sorted(found - {"und"}) if found else ["und"]
    return list(dict.fromkeys(_lang(x) for x in raw if _lang(x)))


def _expression(groups: list[list[dict[str, Any]]]) -> str:
    parts = []
    for variants in groups:
        terms = []
        for item in variants:
            term = item["term"].replace('"', '\\"')
            terms.append(f'"{term}"' if re.search(r"\s", term) else term)
        parts.append("(" + " OR ".join(terms) + ")")
    return " AND ".join(parts)


def _queries(spec: dict[str, Any], concepts: list[dict[str, Any]], targets: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    source = _lang(C.first(spec, "source_language", "query_language") or "und")
    rows, term_ledger, omissions = [], [], []
    query_languages = list(dict.fromkeys(targets + ([source] if source != "und" and source not in targets else [])))
    for lang in query_languages:
        combined_groups = []
        for concept in concepts:
            variants = _concept_terms(concept["original"], lang)
            term_ledger.append({"concept_id": concept["id"], "language": lang,
                                "terms": variants, "source": concept["source"],
                                "translation_service": concept["translation_service"],
                                "translation_version": concept["translation_version"], "license": concept["license"]})
            if not variants:
                omissions.append({"concept_id": concept["id"], "language": lang,
                                  "rule": "crosslang.term_translation_missing",
                                  "message": "No validated term was supplied; no machine translation was fabricated."})
                continue
            combined_groups.append(variants)
            rows.append({"query_id": f"{lang}-{concept['id']}", "language": lang, "kind": "concept",
                         "concept_ids": [concept["id"]], "groups": [variants], "expression": _expression([variants]),
                         "translation_provenance": concept["translation_service"],
                         "translation_version": concept["translation_version"]})
        if len(combined_groups) == len(concepts) and combined_groups:
            rows.append({"query_id": f"{lang}-combined", "language": lang, "kind": "combined",
                         "concept_ids": [c["id"] for c in concepts], "groups": combined_groups,
                         "expression": _expression(combined_groups), "translation_provenance": "declared per concept",
                         "translation_version": "declared per concept"})
        else:
            omissions.append({"language": lang, "rule": "crosslang.language_query_incomplete",
                              "message": "Combined query was not generated because required concept groups are missing."})
    # Baseline is source-language-only and frozen before multilingual expansion.
    baseline = [copy.deepcopy(q) for q in rows if q["language"] == source]
    for q in baseline:
        q["query_id"] = "baseline-" + q["query_id"]
        q["kind"] = "baseline_" + q["kind"]
    return baseline + rows, term_ledger, omissions


def _all_identifiers(doc: dict[str, Any]) -> set[str]:
    return {C.as_text(x).casefold() for x in doc["identifiers"] if C.as_text(x)} | {doc["doc_id"].casefold()}


def _relation_ids(doc: dict[str, Any]) -> set[str]:
    raw = doc["original"]
    out = set()
    def walk(value):
        if isinstance(value, str):
            out.add(C.normalize_doi(value).casefold())
            out.add(value.casefold())
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if any(x in key.lower() for x in ("version", "preprint", "translation", "work", "study", "doi", "id")):
                    walk(item)
    for key in ("work_id", "study_id", "version_of", "translation_of", "trans_of", "relation", "relation_type"):
        walk(raw.get(key))
    out.discard("")
    return out


def _version_kind(doc: dict[str, Any]) -> str:
    raw = doc["original"]
    explicit = C.as_text(C.first(raw, "version_kind", "text_origin", "translation_status", "version")).lower()
    if doc["abstract_only"] or "abstract_only" in explicit or "abstract-only" in explicit:
        return "abstract_only"
    if C.first(raw, "translation_of", "trans_of") or "translation" in explicit or "translated" in explicit:
        if "machine" in explicit or "mt_" in explicit:
            return "machine_translation_view"
        if "publisher" in explicit or "full" in explicit:
            return "publisher_full_translation"
        return "translation_view"
    return "original_or_supplied_view"


SEARCH_METADATA_FIELDS = {"id", "doc_id", "doi", "DOI", "pmid", "PMID", "source", "database",
                          "language", "lang", "body_language", "content_language", "version", "version_kind",
                          "work_id", "study_id", "journal", "container-title", "authorString"}


def _scientific_text(doc: dict[str, Any]) -> str:
    return "\n".join(u["text"] for u in doc["units"] if u["field"] not in SEARCH_METADATA_FIELDS)


def _scientific_evidence(doc: dict[str, Any], terms: list[str], limit: int = 20) -> list[dict[str, Any]]:
    reduced = dict(doc)
    reduced["units"] = [u for u in doc["units"] if u["field"] not in SEARCH_METADATA_FIELDS]
    return C.evidence_for(reduced, terms, limit=limit)


def _content_fingerprint(doc: dict[str, Any]) -> str:
    return C.fingerprint(_scientific_text(doc))


def _cluster(docs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    views, duplicates, findings = [], [], []
    seen_exact = set()
    seen_versions: dict[tuple[str, str, str], dict[str, Any]] = {}
    for doc in docs:
        lang = detect_language(doc)
        doc["language_analysis"] = lang
        doc["version_kind"] = _version_kind(doc)
        if lang["requires_review"]:
            findings.append({"rule": "crosslang.language_uncertain" if not lang["script_metadata_conflict"] else "crosslang.language_conflict",
                              "severity": "medium", "doc_id": doc["doc_id"], "language_analysis": lang})
        identity = doc.get("work_id") or doc.get("doi") or doc["doc_id"]
        exact_key = (C.as_text(identity).casefold(), lang["routed_language"], doc["version_kind"], _content_fingerprint(doc))
        if exact_key in seen_exact:
            duplicates.append({"duplicate_doc_id": doc["doc_id"], "reason": "same work/language/version and exact supplied text",
                               "counted_as_new_view": False})
            continue
        seen_exact.add(exact_key)
        variant_key = (C.as_text(identity).casefold(), lang["routed_language"], doc["version_kind"])
        if variant_key in seen_versions:
            previous = seen_versions[variant_key]
            findings.append({"rule": "crosslang.version_conflict", "severity": "medium",
                             "doc_ids": [previous["doc_id"], doc["doc_id"]],
                             "language": lang["routed_language"], "version_kind": doc["version_kind"],
                             "message": "Same work/language/version label but substantive supplied text differs; both views retained for review."})
        else:
            seen_versions[variant_key] = doc
        views.append(doc)
    lookup = {}
    for doc in views:
        for identifier in _all_identifiers(doc):
            lookup[identifier] = doc
        if doc.get("doi"):
            lookup[doc["doi"].casefold()] = doc
        if doc.get("work_id"):
            lookup[doc["work_id"].casefold()] = doc
    groups: dict[str, dict[str, Any]] = {}
    for doc in views:
        explicit_work = C.as_text(doc.get("work_id")).casefold()
        key = "work:" + explicit_work if explicit_work else "doi:" + doc["doi"] if doc.get("doi") else ""
        if not key:
            relations = _relation_ids(doc)
            linked = next((lookup[x] for x in sorted(relations) if x in lookup and lookup[x] is not doc), None)
            key = "work:" + C.as_text(linked.get("work_id")).casefold() if linked and linked.get("work_id") else \
                  "doi:" + linked["doi"] if linked and linked.get("doi") else "record:" + doc["doc_id"].casefold()
        # Explicit work ids unify all publication-language views but not records lacking any work relation.
        if key not in groups:
            groups[key] = {"work_id": key, "views": [], "identifiers": set(), "titles": []}
        groups[key]["views"].append(doc)
        groups[key]["identifiers"].update(_all_identifiers(doc))
        if doc["title"]:
            groups[key]["titles"].append(doc["normalized_title"])
    clusters = []
    for group in groups.values():
        group["identifiers"] = sorted(group["identifiers"])
        group["languages"] = sorted({v["language_analysis"]["routed_language"] for v in group["views"]})
        group["metadata"] = [v["metadata"] for v in group["views"]]
        group["sources"] = [v["source"] for v in group["views"]]
        clusters.append(group)
    return clusters, duplicates, findings


def _docs_for_language(clusters: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    docs = [v for c in clusters for v in c["views"]]
    if lang == "und":
        return docs
    routed = [v for v in docs if v["language_analysis"]["routed_language"] == lang]
    uncertain = [v for v in docs if v["language_analysis"]["routed_language"] == "und"]
    return routed + [v for v in uncertain if v not in routed]


def _match_query(query: dict[str, Any], clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for doc in _docs_for_language(clusters, query["language"]):
        scientific_text = _scientific_text(doc)
        group_matches = []
        for variants in query["groups"]:
            terms = [v["term"] for v in variants]
            matched = [term for term in terms if C.term_occurrences(scientific_text, term)]
            group_matches.append({"concept_terms": terms, "matched_terms": matched,
                                  "matched": bool(matched)})
        if not all(m["matched"] for m in group_matches):
            continue
        matched_terms = sorted({t for m in group_matches for t in m["matched_terms"]})
        evidence = _scientific_evidence(doc, matched_terms, limit=20)
        for ev in evidence:
            ev["text_origin"] = doc["version_kind"]
            ev["body_language"] = doc["language_analysis"]["routed_language"]
            ev["is_machine_translated_quote"] = doc["version_kind"] == "machine_translation_view"
            ev["quotation_role"] = ("translation_version_evidence_not_original_quotation"
                                      if doc["version_kind"] in {"publisher_full_translation", "translation_view", "machine_translation_view"}
                                      else "supplied_original_or_abstract_evidence_origin_as_declared")
        hits.append({"doc_id": doc["doc_id"], "query_id": query["query_id"], "language": query["language"],
                     "matched_terms": matched_terms, "concept_groups": group_matches,
                     "match_strength": len(matched_terms), "evidence": evidence,
                     "routing_basis": doc["language_analysis"], "version_kind": doc["version_kind"],
                     "source": doc["source"], "candidate_relevance": "lexical_match_not_scientific_adjudication"})
    hits.sort(key=lambda h: (-h["match_strength"], h["doc_id"]))
    for rank, hit in enumerate(hits, 1):
        hit["rank"] = rank
    return hits


def _cluster_for_doc(clusters: list[dict[str, Any]], doc_id: str) -> dict[str, Any] | None:
    return next((c for c in clusters if any(v["doc_id"] == doc_id for v in c["views"])), None)


def _known_refs(spec: dict[str, Any], case_dir: Path) -> list[dict[str, Any]]:
    value, source = C.load_value(spec, ("reference_set", "known_relevant", "known_relevant_set", "references", "qrels"), case_dir)
    if value is None:
        return []
    if isinstance(value, dict) and not any(k in value for k in ("references", "reference_set", "known_relevant", "items", "results", "message")):
        value = [dict(v, id=k) if isinstance(v, dict) else {"id": k, "work_id": v} for k, v in value.items()]
    rows = C.records_from_payload(value, source or "inline")
    refs, _ = C.normalize_documents(rows, [source or "inline"] * len(rows))
    unique = {}
    for ref in refs:
        raw = ref["original"]
        ref_id = C.as_text(C.first(raw, "ref_id", "reference_id", "id", "work_id", "doc_id") or ref["doc_id"])
        ref["ref_id"] = ref_id
        key = (ref.get("work_id") or ref.get("doi") or ref_id).casefold()
        unique.setdefault(key, ref)
    return list(unique.values())


def _covered_refs(refs: list[dict[str, Any]], ranked_hits: list[dict[str, Any]], clusters: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_ref = {}
    for ref in refs:
        ref_ids = {ref["ref_id"].casefold(), *_all_identifiers(ref)}
        if ref.get("work_id"):
            ref_ids.add(("work:" + ref["work_id"].casefold()))
        if ref.get("doi"):
            ref_ids.add(("doi:" + ref["doi"]))
        found = set()
        for hit in ranked_hits:
            cluster = _cluster_for_doc(clusters, hit["doc_id"])
            if not cluster:
                continue
            cluster_ids = {cluster["work_id"].casefold(), *cluster["identifiers"]}
            if ref_ids & cluster_ids:
                found.add(cluster["work_id"])
        if not found:
            # Exact title/author/year fallback only; translation titles are never guessed into one work.
            ref_title = ref["normalized_title"]
            for hit in ranked_hits:
                cluster = _cluster_for_doc(clusters, hit["doc_id"])
                if not cluster or not ref_title:
                    continue
                for view in cluster["views"]:
                    if view["normalized_title"] == ref_title and (not ref["year"] or ref["year"] == view["year"]) \
                            and (not ref["first_author"] or ref["first_author"] == view["first_author"]):
                        found.add(cluster["work_id"])
                        break
        by_ref[ref["ref_id"]] = sorted(found)
    return by_ref


def _recall(refs: list[dict[str, Any]], coverage: dict[str, list[str]]) -> dict[str, Any]:
    covered = sorted(ref for ref, works in coverage.items() if works)
    return {"scope": "known_relevant_works_not_views", "known_relevant_works": len(refs),
            "covered_works": len(covered), "covered_ref_ids": covered,
            "known_set_recall": len(covered) / len(refs) if refs else None,
            "missed_ref_ids": sorted(set(coverage) - set(covered)), "absolute_crosslingual_recall": None,
            "note": "Translations/views never enlarge the denominator or numerator. Global multilingual recall is unknown."}


def _ranking(clusters: list[dict[str, Any]], query_results: list[dict[str, Any]], accepted_prf_results=None) -> list[dict[str, Any]]:
    accepted_prf_results = accepted_prf_results or []
    standard_scores: dict[str, float] = {}
    evidence_map: dict[str, list[dict[str, Any]]] = {}
    for result in query_results:
        for hit in result["hits"]:
            score = 1.0 / (60 + hit["rank"])
            standard_scores[hit["doc_id"]] = standard_scores.get(hit["doc_id"], 0.0) + score
            evidence_map.setdefault(hit["doc_id"], []).append({"query_id": result["query_id"], "rank": hit["rank"],
                                                                 "language": result["language"],
                                                                 "matched_terms": hit["matched_terms"]})
    for result in accepted_prf_results:
        for hit in result["hits"]:
            standard_scores[hit["doc_id"]] = standard_scores.get(hit["doc_id"], 0.0) + 0.5 / (60 + hit["rank"])
    rows = []
    for cluster in clusters:
        hits = [(doc, standard_scores[doc["doc_id"]]) for doc in cluster["views"] if doc["doc_id"] in standard_scores]
        if not hits:
            continue
        best_doc, best_view_score = max(hits, key=lambda x: (x[1], x[0]["doc_id"]))
        # Max across versions prevents a work with more translation views from dominating by count.
        score = best_view_score
        rows.append({"work_id": cluster["work_id"], "score": score, "best_original_view_id": best_doc["doc_id"],
                     "languages": sorted({d["language_analysis"]["routed_language"] for d, _ in hits}),
                     "retrieved_view_ids": [d["doc_id"] for d, _ in hits],
                     "view_count_retrieved": len(hits),
                     "query_ranks": evidence_map.get(best_doc["doc_id"], []),
                     "original_evidence": best_doc.get("_all_evidence", []),
                     "relevance": "known_reference_alignment_or_lexical_candidate"})
    rows.sort(key=lambda r: (-r["score"], r["work_id"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def _prf(spec: dict[str, Any], clusters: list[dict[str, Any]], expanded_results: list[dict[str, Any]], targets: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = C.first(spec, "pseudo_relevance_feedback", "prf", "feedback") or {}
    if config is True:
        config = {"enabled": True}
    if not isinstance(config, dict) or not config.get("enabled"):
        return [], []
    try:
        fb_docs = max(1, min(10, int(config.get("fb_docs", 3))))
    except (TypeError, ValueError):
        fb_docs = 3
    try:
        fb_terms = max(1, min(20, int(config.get("fb_terms", 5))))
    except (TypeError, ValueError):
        fb_terms = 5
    try:
        min_df = max(1, int(config.get("min_document_frequency", 2)))
    except (TypeError, ValueError):
        min_df = 2
    accepted = config.get("accept_prf") is True
    runs, accepted_results = [], []
    by_lang_combined = {r["language"]: r for r in expanded_results if r["kind"] == "combined"}
    for lang in targets:
        initial = by_lang_combined.get(lang)
        if not initial or not initial["hits"]:
            runs.append({"language": lang, "status": "no_initial_relevant_feedback_documents", "terms": [], "accepted": accepted})
            continue
        feedback_hits = initial["hits"][:fb_docs]
        feedback_docs = [_cluster_for_doc(clusters, h["doc_id"]) for h in feedback_hits]
        documents = [next(v for c in feedback_docs if c for v in c["views"] if v["doc_id"] == h["doc_id"])
                     for c, h in zip(feedback_docs, feedback_hits)]
        document_frequency: dict[str, int] = {}
        surfaces: dict[str, str] = {}
        for doc in documents:
            tokens = tokenize_with_offsets(_scientific_text(doc))
            present = {}
            for token in tokens:
                value = token["token"]
                if len(value) < 3 or value in PRF_STOP or value.isdigit() or value.startswith("10."):
                    continue
                present.setdefault(value, token)
                surfaces.setdefault(value, token["surface"])
            for value in present:
                document_frequency[value] = document_frequency.get(value, 0) + 1
        original_terms = {term.casefold() for group in initial["groups"] for item in group for term in [item["term"]]}
        selected = sorted(((token, df) for token, df in document_frequency.items()
                           if df >= min_df and token not in original_terms),
                          key=lambda x: (-x[1], x[0]))[:fb_terms]
        prf_variants = [{"term": surfaces[token], "kind": "unverified_pseudo_relevance_feedback",
                         "provenance": f"top-{len(feedback_hits)} initial original-language hits",
                         "document_frequency": df} for token, df in selected]
        if not prf_variants:
            runs.append({"language": lang, "source_query_id": initial["query_id"],
                         "feedback_document_ids": [h["doc_id"] for h in feedback_hits], "min_document_frequency": min_df,
                         "terms": [], "status": "no_safe_expansion_terms", "accepted": accepted})
            continue
        # PRF can only alter ranking by default. Optional recall candidates retain at least one original concept group.
        groups = initial["groups"]
        expression = initial["expression"] + " AND (" + " OR ".join(v["term"] for v in prf_variants) + ") [PRF optional ranking terms]"
        prf_query = {"query_id": "prf-" + initial["query_id"], "language": lang, "kind": "prf",
                     "concept_ids": initial["concept_ids"], "groups": groups, "expression": expression}
        candidate_hits = []
        for hit in _match_query(prf_query, clusters):
            doc = next(v for c in clusters for v in c["views"] if v["doc_id"] == hit["doc_id"])
            extra = [v["term"] for v in prf_variants if C.term_occurrences(_scientific_text(doc), v["term"])]
            if not extra:
                continue
            hit["prf_matched_terms"] = extra
            hit["prf_evidence"] = _scientific_evidence(doc, extra, limit=10)
            hit["match_strength"] += len(extra)
            candidate_hits.append(hit)
        candidate_hits.sort(key=lambda h: (-h["match_strength"], h["doc_id"]))
        for rank, hit in enumerate(candidate_hits, 1):
            hit["rank"] = rank
        prf_result = {"query_id": prf_query["query_id"], "language": lang, "kind": "prf",
                      "groups": groups, "expression": expression, "hits": candidate_hits,
                      "accepted_into_main_recall": accepted}
        runs.append({"language": lang, "source_query_id": initial["query_id"],
                     "feedback_document_ids": [h["doc_id"] for h in feedback_hits],
                     "fb_docs": fb_docs, "fb_terms": fb_terms, "original_query_weight": 0.5,
                     "min_document_frequency": min_df, "terms": prf_variants,
                     "candidate_doc_ids": [h["doc_id"] for h in candidate_hits],
                     "candidate_ranking": [{"doc_id": h["doc_id"], "rank": h["rank"],
                                            "match_strength": h["match_strength"],
                                            "prf_matched_terms": h["prf_matched_terms"]} for h in candidate_hits],
                     "validation_status": "unverified_original_text_terms_not_concept_translations",
                     "accepted": accepted,
                     "note": "PRF never substitutes for a validated concept translation and never becomes original quotation by generation."})
        if accepted:
            accepted_results.append(prf_result)
    return runs, accepted_results


def analyze(spec: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    raw_docs, sources = C.load_document_records(spec, case_dir, keys=("documents", "views", "studies", "corpus", "records", "candidates"))
    docs, omissions = C.normalize_documents(raw_docs, sources)
    if not docs:
        raise C.MaterialError("crosslang.no_documents", "no multilingual document views could be normalized")
    concepts = _concepts(spec)
    targets = _targets(spec, concepts)
    queries, term_ledger, query_omissions = _queries(spec, concepts, targets)
    clusters, exact_duplicates, language_findings = _cluster(docs)
    query_results = []
    for query in queries:
        hits = _match_query(query, clusters)
        query_results.append({k: query[k] for k in ("query_id", "language", "kind", "concept_ids", "groups", "expression")} | {"hits": hits, "empty": not hits})
    baseline_results = [r for r in query_results if r["kind"].startswith("baseline_")]
    expanded_results = [r for r in query_results if not r["kind"].startswith("baseline_")]
    # Preserve every original hit's evidence before cross-query work ranking.
    for cluster in clusters:
        for view in cluster["views"]:
            evidence = [hit["evidence"] for result in query_results for hit in result["hits"] if hit["doc_id"] == view["doc_id"]]
            flat = [item for group in evidence for item in group]
            view["_all_evidence"] = flat
    refs = _known_refs(spec, case_dir)
    baseline_coverage = _covered_refs(refs, [h for r in baseline_results for h in r["hits"]], clusters)
    expanded_coverage = _covered_refs(refs, [h for r in baseline_results + expanded_results for h in r["hits"]], clusters)
    before = _recall(refs, baseline_coverage)
    after = _recall(refs, expanded_coverage)
    prf_runs, accepted_prf = _prf(spec, clusters, expanded_results, targets)
    ranked = _ranking(clusters, expanded_results, accepted_prf)
    all_expanded_hits = [h for r in expanded_results for h in r["hits"]]
    language_summary = []
    for lang in targets:
        language_queries = [r for r in expanded_results if r["language"] == lang]
        hits = [h for r in language_queries for h in r["hits"]]
        known = _covered_refs(refs, hits, clusters)
        language_summary.append({"language": lang, "queries_executed": len(language_queries),
                                 "view_hits_before_work_dedup": len({h["doc_id"] for h in hits}),
                                 "work_hits_after_dedup": len({_cluster_for_doc(clusters, h["doc_id"])["work_id"] for h in hits if _cluster_for_doc(clusters, h["doc_id"])}),
                                 "known_ref_ids_covered": sorted(ref for ref, works in known.items() if works),
                                 "empty_query_ids": [r["query_id"] for r in language_queries if not r["hits"]]})
    before_set = set(before["covered_ref_ids"])
    after_set = set(after["covered_ref_ids"])
    source_language = _lang(C.first(spec, "source_language", "query_language") or "und")
    gains = sorted(after_set - before_set)
    if source_language == "und":
        before["known_set_recall"] = None
        before["note"] = "Source language is undefined; a source-only baseline and gain cannot be calculated."
        gains = []
    comparison = {"source_language": source_language,
                  "before": before, "after": after, "newly_covered_ref_ids": gains,
                  "marginal_gain": None if source_language == "und" else len(gains), "remaining_missed_ref_ids": after["missed_ref_ids"],
                  "work_counting_rule": "Exact duplicate exports are ignored; original, translation and abstract-only views remain visible but share one work recall unit."}
    findings = list(language_findings)
    findings.extend({"rule": o["rule"], "severity": "medium", "details": o} for o in query_omissions)
    if omissions:
        findings.append({"rule": "crosslang.records_omitted", "severity": "medium", "entries": omissions})
    if exact_duplicates:
        findings.append({"rule": "crosslang.exact_duplicate_views", "severity": "low", "entries": exact_duplicates})
    empty_languages = [x["language"] for x in language_summary if x["work_hits_after_dedup"] == 0]
    if empty_languages:
        findings.append({"rule": "crosslang.language_has_no_results", "severity": "medium", "languages": empty_languages,
                         "message": "Declared query languages without hits remain explicit; no results are translated into existence."})
    declared_translation_states = [C.first(spec, "translation_service_status", "translation_status")] + [
        C.first(c["original"], "translation_service_status", "translation_status") for c in concepts]
    if any(re.search(r"fail|error|unavailable|quota|limit|timeout|失败|不可用|限额", C.as_text(x), re.I) for x in declared_translation_states if x):
        findings.append({"rule": "crosslang.translation_service_unavailable", "severity": "medium",
                         "message": "A declared translation service failed or was unavailable. Existing verified terms were still used; no replacement translations were fabricated."})
    if comparison["source_language"] == "und":
        findings.append({"rule": "crosslang.source_language_unknown", "severity": "medium",
                         "message": "Source language was not declared; baseline-only recall is not inferred from an arbitrary language."})
    if not refs:
        findings.append({"rule": "crosslang.known_set_missing", "severity": "medium",
                         "message": "Only lexical candidate ranking is available; multilingual recall cannot be measured."})
    status = "review" if any(f["severity"] in {"high", "medium"} for f in findings) else "clean"
    candidates = []
    for cluster in clusters:
        candidates.append({"work_id": cluster["work_id"], "languages": cluster["languages"],
                           "metadata": cluster["metadata"], "sources": cluster["sources"],
                           "views": [{"doc_id": v["doc_id"], "language": v["language_analysis"],
                                      "version_kind": v["version_kind"], "full_text_available": v["full_text_available"],
                                      "abstract_only": v["abstract_only"], "source": v["source"]} for v in cluster["views"]],
                           "identifiers": cluster["identifiers"]})
    evidence_ledger = [{"query_id": result["query_id"], "language": result["language"], "doc_id": hit["doc_id"],
                        "matched_terms": hit["matched_terms"], "evidence": hit["evidence"]}
                       for result in expanded_results for hit in result["hits"]]
    missing_terms = []
    for item in term_ledger:
        if not item["terms"]:
            missing_terms.append({"concept_id": item["concept_id"], "language": item["language"]})
    return {
        "schema_version": SCHEMA_VERSION, "status": status,
        "source_language": comparison["source_language"], "target_languages": targets,
        "input_fingerprint": C.fingerprint(spec), "concept_alignment": term_ledger,
        "multilingual_queries": [{k: v for k, v in r.items() if k != "hits"} | {"hit_count": len(r["hits"]), "empty": r["empty"]} for r in expanded_results],
        "query_results": expanded_results, "baseline_queries": baseline_results,
        "cross_language_ranking": ranked, "ranked_results": ranked,
        "candidate_set": candidates, "documents_indexed": len(docs),
        "unique_input_views_after_exact_dedup": sum(len(c["views"]) for c in clusters),
        "unique_candidate_works": len(clusters), "exact_duplicate_views": exact_duplicates,
        "language_summary": language_summary, "known_set_evaluation": comparison,
        "crosslingual_recall_gain": comparison, "feedback_runs": prf_runs,
        "accepted_prf_query_count": len(accepted_prf),
        "evidence_ledger": evidence_ledger,
        "quotation_policy": "Every quote is sliced from the supplied text of that language/version view. Publisher or machine translations have quotation_role=translation_version_evidence_not_original_quotation. Derived queries, back-translations and PRF terms are labeled generation metadata and can never become original-language quotations.",
        "findings": findings, "limits": ["Local supplied snapshots only; no live remote, unseen-language or new-study claim.",
                                                "Terms absent from the concept table are not machine-fabricated. Lexical hits require relevance review.",
                                                "PRF is isolated from main recall unless accept_prf=true and added weight is then recorded separately."],
        "uncertainty": (["Some languages have no validated query term or no result; do not infer absence of the literature."] if empty_languages or missing_terms else [])
                       + ["Language classification uses declared metadata first; script-only inference remains uncertain, especially for Latin-script languages and CJK without kana."],
        "sources": [v["source"] | {"doc_id": v["doc_id"], "language": v["language_analysis"],
                                   "version_kind": v["version_kind"]} for c in clusters for v in c["views"]],
        "change_records": [{"operation": "freeze_concept_alignment", "concepts": len(concepts), "targets": targets},
                           {"operation": "generate_per_language_queries", "queries": len(expanded_results)},
                           {"operation": "deduplicate_exact_views", "duplicates": len(exact_duplicates),
                            "unique_views": sum(len(c["views"]) for c in clusters), "unique_works": len(clusters)},
                           {"operation": "run_pseudo_relevance_feedback", "enabled": bool(prf_runs),
                            "accepted_into_main_recall": len(accepted_prf)}],
        "omissions": omissions,
        "independent_recompute": {"reference_n": len(refs), "baseline_covered_n": before["covered_works"],
                                  "expanded_covered_n": after["covered_works"],
                                  "gain_recount": None if source_language == "und" else len(after_set - before_set),
                                  "unique_works_recount": len(clusters),
                                  "unique_views_recount": sum(len(c["views"]) for c in clusters)},
    }


def attach_rubric(result: dict[str, Any]) -> dict[str, Any]:
    result["检索结果"] = {"候选文献": result["candidate_set"], "排序/筛选结果": result["ranked_results"],
                         "逐语种结果": result["language_summary"], "元数据": [c["metadata"] for c in result["candidate_set"]],
                         "来源定位": result["sources"], "跨语种召回增益": result["crosslingual_recall_gain"],
                         "遗漏说明": result["known_set_evaluation"]["after"]["missed_ref_ids"]}
    result["证据记录"] = {"概念与术语对齐": result["concept_alignment"], "逐语种查询": result["multilingual_queries"],
                         "原文证据": result["evidence_ledger"], "引文边界": result["quotation_policy"],
                         "伪相关反馈": result["feedback_runs"], "复算入口": result["independent_recompute"]}
    result["状态说明"] = C.status_block(
        result["status"], [x["language"] for x in result["language_summary"] if x["work_hits_after_dedup"]],
        [x for x in result["language_summary"] if not x["work_hits_after_dedup"]],
        [q["query_id"] for q in result["multilingual_queries"] if q["empty"]],
        [f for f in result["findings"] if "conflict" in f["rule"]],
        result["omissions"] + result["exact_duplicate_views"], result["uncertainty"])
    result["运行状态"] = result["status"]
    return result

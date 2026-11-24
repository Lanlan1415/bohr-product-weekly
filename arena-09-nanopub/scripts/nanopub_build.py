"""Build deterministic local Nanopublications from agent-read SPOQ assertions.

No network, DOI/ORCID, publication timestamp or licence is minted. The agent
extracts minimal assertions and evidence; this tool performs syntax-safe RDF
serialization, exact evidence-offset binding, contract echo and graph checks.

  python nanopub_build.py --case /input/case.json --draft /app/work/assertions.json \
      --source /app/work/source.txt --out /app/output

Exit: 0 success, 3 partial (valid RDF + named gaps), 5 refused/failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

# Direct `-I script/path.py` execution has no cwd/script imports by design.
sys.path.insert(0, str(Path(__file__).resolve().parent))

NP = "http://www.nanopub.org/nschema#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
DCT = "http://purl.org/dc/terms/"
PROV = "http://www.w3.org/ns/prov#"
PAV = "http://purl.org/pav/"
XSD = "http://www.w3.org/2001/XMLSchema#"
EX = "urn:nanopub:local:vocab:"
TOOL = "urn:nanopub:local:tool:authoring-nanopublications-v3"
SCHEMA = "authoring-nanopublications/v3"
QUOTE_CODES = {
    "missing": "evidence.missing",
    "not_checked": "evidence.not_checked",
    "not_found": "evidence.not_found",
    "multiple_matches_unresolved": "evidence.multiple_matches_unresolved",
}


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _iri(value):
    value = str(value or "").strip()
    if not value or re.search(r"[\s<>\"{}|\\^`]", value) or not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
        raise ValueError("invalid absolute IRI: %r" % value[:80])
    return "<%s>" % value


def _literal(value, datatype=None, language=None):
    text = str(value)
    escaped = (text.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    suffix = ""
    if language:
        if not re.match(r"^[A-Za-z]+(?:-[A-Za-z0-9]+)*$", language):
            raise ValueError("invalid RDF language tag")
        suffix = "@" + language
    elif datatype:
        suffix = "^^" + _iri(datatype)
    return '"%s"%s' % (escaped, suffix)


def _local(prefix, *values):
    return "urn:nanopub:local:%s:%s" % (prefix, _hash(values))


def _identifier_iri(identifier):
    """Resolve only identifiers supplied by the input; never invent one."""
    value = str(identifier or "").strip()
    if re.match(r"^https?://\S+$", value) or value.startswith("urn:"):
        return value
    doi = value[4:] if value.lower().startswith("doi:") else value
    if re.match(r"^10\.\d{4,9}/\S+$", doi):
        return "https://doi.org/" + doi
    if re.match(r"^\d{7,8}$", value):
        return "https://pubmed.ncbi.nlm.nih.gov/%s/" % value
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", value):
        return "https://arxiv.org/abs/" + value
    orcid = value[6:] if value.lower().startswith("orcid:") else value
    if re.match(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dXx]$", orcid):
        return "https://orcid.org/" + orcid.upper()
    return None


def _resource(value, prefix="entity"):
    """Return (absolute_iri, optional_label). Strings are labels, not guessed IRIs."""
    if isinstance(value, dict) and value.get("iri"):
        return str(value["iri"]), value.get("label")
    text = str(value.get("label") if isinstance(value, dict) else value or "").strip()
    if not text:
        raise ValueError("empty RDF resource")
    if re.match(r"^https?://\S+$", text) or text.startswith("urn:"):
        return text, None
    if prefix in ("predicate", "qualifier-predicate"):
        # Controlled local vocabulary: the same relation spelling has one stable,
        # inspectable IRI instead of an opaque per-assertion hash. Never claims a
        # domain ontology or registered external identifier.
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-.") or "relation-" + _hash(text)
        return EX + slug, text
    return _local(prefix, text), text


def _object(value):
    if isinstance(value, dict):
        if value.get("iri"):
            return _iri(value["iri"])
        val = value.get("value", value.get("label"))
        if val is None:
            raise ValueError("RDF object has neither iri nor value")
        datatype = value.get("datatype")
        if datatype and not datatype.startswith(("http://", "https://", "urn:")):
            prefixed = {"decimal": XSD + "decimal", "integer": XSD + "integer",
                        "date": XSD + "date", "dateTime": XSD + "dateTime",
                        "gYear": XSD + "gYear"}.get(datatype)
            datatype = prefixed or datatype
        if datatype is None and isinstance(val, bool):
            datatype = XSD + "boolean"
        elif datatype is None and isinstance(val, int):
            datatype = XSD + "integer"
        elif datatype is None and isinstance(val, float):
            datatype = XSD + "decimal"
        return _literal(str(val).lower() if isinstance(val, bool) else val, datatype, value.get("language") or value.get("lang"))
    if isinstance(value, bool):
        return _literal(str(value).lower(), XSD + "boolean")
    if isinstance(value, int):
        return _literal(value, XSD + "integer")
    if isinstance(value, float):
        return _literal(value, XSD + "decimal")
    return _literal(value if value is not None else "")


def _triples(graph, triples):
    return graph + " {\n" + "".join("  %s %s %s .\n" % triple for triple in triples) + "}\n"


def _qualifier_text(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _date_term(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            dt.date.fromisoformat(text)
            return _literal(text, XSD + "date")
        dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return _literal(text, XSD + "dateTime")
    except ValueError:
        return None


def _read_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _quote_status(assertion, source_text):
    quote = ((assertion.get("evidence") or {}).get("quote") if isinstance(assertion.get("evidence"), dict) else None)
    if not isinstance(quote, str) or not quote:
        return {"status": "missing", "quote": quote}
    if source_text is None:
        return {"status": "not_checked", "quote": quote}
    hits = [m.start() for m in re.finditer(re.escape(quote), source_text)]
    if len(hits) == 1:
        return {"status": "exact_unique", "quote": quote,
                "char_start": hits[0], "char_end": hits[0] + len(quote)}
    if len(hits) > 1:
        return {"status": "multiple_matches_unresolved", "quote": quote, "count": len(hits)}
    return {"status": "not_found", "quote": quote}


def _source_record(assertion, draft):
    source = draft.get("source_metadata") if isinstance(draft.get("source_metadata"), dict) else {}
    own = assertion.get("source_metadata") if isinstance(assertion.get("source_metadata"), dict) else {}
    merged = dict(source); merged.update(own)
    return merged


def _one(assertion, index, case, draft, source_text):
    errors, warnings = [], []
    if not isinstance(assertion, dict):
        return None, [{"id": "assertion-%03d" % index, "code": "assertion.not_object",
                       "message": "assertion must be an object"}]
    aid = str(assertion.get("id") or "assertion-%03d" % index)
    needed = [k for k in ("subject", "predicate", "object") if not assertion.get(k)]
    if needed:
        return None, [{"id": aid, "code": "assertion.incomplete_spo",
                       "message": "missing " + ",".join(needed)}]
    try:
        subject, slabel = _resource(assertion["subject"], "subject")
        predicate, plabel = _resource(assertion["predicate"], "predicate")
        st, pr, ob = _iri(subject), _iri(predicate), _object(assertion["object"])
    except (TypeError, ValueError) as exc:
        return None, [{"id": aid, "code": "assertion.invalid_rdf_term", "message": str(exc)[:200]}]
    raw_id = assertion.get("np_uri") or assertion.get("uri")
    if raw_id is not None:
        try:
            _iri(raw_id)
            base = str(raw_id) + ("#" if not str(raw_id).endswith(("/", "#")) else "")
        except ValueError:
            return None, [{"id": aid, "code": "assertion.invalid_supplied_uri",
                           "message": "supplied nanopub URI is invalid; no replacement remote ID was minted"}]
    else:
        seed = [case.get("case_id"), aid, subject, predicate, assertion["object"]]
        base = _local("nanopub", seed) + ":"
    root = str(raw_id) if raw_id is not None else base + "this"
    head, ag, pg, ig = base + "Head", base + "assertion", base + "provenance", base + "pubInfo"
    statement = base + "statement"
    evidence = assertion.get("evidence") if isinstance(assertion.get("evidence"), dict) else {}
    binding = _quote_status(assertion, source_text)
    source = _source_record(assertion, draft)
    source_iri = _identifier_iri(source.get("identifier") or source.get("doi") or source.get("url"))
    condition = assertion.get("condition_scope", assertion.get("conditionScope"))
    if condition in (None, "", []):
        warnings.append({"id": aid, "code": "assertion.condition_unreported",
                         "message": "condition/scope was not declared; no universal scope was invented"})
    if binding["status"] != "exact_unique":
        warnings.append({"id": aid, "code": QUOTE_CODES[binding["status"]],
                         "message": "exact unique source quote was not verified"})
    locator = evidence.get("locator") or evidence.get("anchor")
    if not locator:
        warnings.append({"id": aid, "code": "evidence.locator_missing",
                         "message": "no page/paragraph/figure/table locator supplied"})
    if not source.get("identifier") and not source.get("doi") and not source.get("url") and not source.get("material_file"):
        warnings.append({"id": aid, "code": "source.identifier_unreported",
                         "message": "no DOI/URL/identifier/material_file supplied; no DOI was minted"})
    if not source.get("title"):
        warnings.append({"id": aid, "code": "source.title_unreported", "message": "source title not supplied"})
    pub = draft.get("publication_info") if isinstance(draft.get("publication_info"), dict) else {}
    own_pub = assertion.get("publication_info") if isinstance(assertion.get("publication_info"), dict) else {}
    pub = {**pub, **own_pub}
    created_term = _date_term(pub.get("created"))
    if created_term is None:
        warnings.append({"id": aid, "code": "pubinfo.created_unreported_or_invalid",
                         "message": "no valid actual creation date supplied; no wall-clock date was invented"})
    license_value = pub.get("license")
    if not license_value:
        warnings.append({"id": aid, "code": "pubinfo.license_unreported",
                         "message": "licence not supplied; source-article rights were not assumed to cover the nanopub"})

    assertion_triples = [(st, pr, ob), (_iri(statement), _iri(RDF + "type"), _iri(EX + "AtomicAssertion")),
                         (_iri(statement), _iri(RDF + "subject"), st),
                         (_iri(statement), _iri(RDF + "predicate"), pr),
                         (_iri(statement), _iri(RDF + "object"), ob)]
    statement_text = assertion.get("statement") or assertion.get("text")
    if statement_text:
        assertion_triples.append((_iri(statement), _iri(DCT + "description"), _literal(statement_text)))
    if slabel:
        assertion_triples.append((st, _iri(RDFS + "label"), _literal(slabel)))
    if plabel:
        assertion_triples.append((pr, _iri(RDFS + "label"), _literal(plabel)))
    if condition not in (None, "", []):
        assertion_triples.append((_iri(statement), _iri(EX + "conditionScope"), _literal(_qualifier_text(condition))))
    qualifiers = assertion.get("qualifiers", assertion.get("qualifier")) or []
    if isinstance(qualifiers, str):
        qualifiers = [qualifiers]
    if not isinstance(qualifiers, list):
        qualifiers = [qualifiers]
    for qi, qual in enumerate(qualifiers):
        qnode = base + "qualifier-" + str(qi + 1)
        assertion_triples.append((_iri(statement), _iri(EX + "hasQualifier"), _iri(qnode)))
        if isinstance(qual, dict) and qual.get("predicate"):
            qp, qplabel = _resource(qual["predicate"], "qualifier-predicate")
            qvalue = qual.get("value", qual.get("object"))
            assertion_triples.extend([(_iri(qnode), _iri(RDF + "predicate"), _iri(qp)),
                                      (_iri(qnode), _iri(RDF + "object"), _object(qvalue))])
            if qplabel:
                assertion_triples.append((_iri(qp), _iri(RDFS + "label"), _literal(qplabel)))
        else:
            assertion_triples.append((_iri(qnode), _iri(DCT + "description"), _literal(_qualifier_text(qual))))

    provenance_triples = []
    source_node = _iri(source_iri) if source_iri else None
    if source_node:
        provenance_triples.append((_iri(ag), _iri(PROV + "wasDerivedFrom"), source_node))
        provenance_triples.append((_iri(statement), _iri(PROV + "wasDerivedFrom"), source_node))
    else:
        missing = source.get("identifier") or source.get("doi") or source.get("material_file") or "unreported"
        provenance_triples.append((_iri(ag), _iri(EX + "sourceIdentifierOrStatus"), _literal(missing)))
    for key, pred in (("title", DCT + "title"), ("year", DCT + "issued"), ("version", DCT + "hasVersion"),
                      ("material_file", EX + "sourceFile"), ("identifier", DCT + "identifier"), ("doi", DCT + "identifier")):
        if source.get(key) not in (None, ""):
            # The DOI URI links above; the original string remains for exact audit.
            datatype = XSD + "gYear" if key == "year" and re.match(r"^\d{4}$", str(source[key])) else None
            target = source_node or _iri(ag)
            provenance_triples.append((target, _iri(pred), _literal(source[key], datatype)))
    authors = source.get("authors") or ([source.get("author")] if source.get("author") else [])
    if isinstance(authors, str):
        authors = [authors]
    for author in authors if isinstance(authors, list) else []:
        if isinstance(author, dict):
            author_iri = _identifier_iri(author.get("orcid"))
            if author_iri:
                provenance_triples.append((_iri(ag), _iri(PROV + "wasAttributedTo"), _iri(author_iri)))
            if author.get("name"):
                provenance_triples.append((_iri(ag), _iri(EX + "sourceAuthor"), _literal(author["name"])))
        else:
            provenance_triples.append((_iri(ag), _iri(EX + "sourceAuthor"), _literal(author)))
    if not locator:
        locator = "unreported"
    if binding.get("quote"):
        provenance_triples.append((_iri(ag), _iri(EX + "evidenceQuote"), _literal(binding["quote"])))
    provenance_triples.extend([
        (_iri(ag), _iri(EX + "hasEvidenceAnchor"), _literal(_qualifier_text(locator))),
        (_iri(ag), _iri(EX + "evidenceType"), _iri(EX + re.sub(r"[^A-Za-z0-9]+", "", str(assertion.get("evidence_type") or evidence.get("strength") or "Unspecified")))),
        (_iri(ag), _iri(EX + "evidenceForm"), _iri(EX + re.sub(r"[^A-Za-z0-9]+", "", str(assertion.get("evidence_form") or evidence.get("form") or "Unspecified")))),
        (_iri(ag), _iri(EX + "quoteVerification"), _literal(binding["status"]))])
    if binding.get("char_start") is not None:
        provenance_triples.extend([(_iri(ag), _iri(EX + "evidenceCharStart"), _literal(binding["char_start"], XSD + "integer")),
                                   (_iri(ag), _iri(EX + "evidenceCharEnd"), _literal(binding["char_end"], XSD + "integer"))])
    if condition not in (None, "", []):
        provenance_triples.append((_iri(ag), _iri(EX + "conditionScope"), _literal(_qualifier_text(condition))))

    confidence = assertion.get("confidence") if isinstance(assertion.get("confidence"), dict) else {"level": assertion.get("confidence")}
    level = str(confidence.get("level") or "low").lower()
    if level not in ("high", "medium", "low"):
        level = "low"
        warnings.append({"id": aid, "code": "assertion.invalid_confidence", "message": "unknown confidence mapped to low"})
    basis = confidence.get("basis") or assertion.get("confidence_basis") or "no explicit basis supplied"
    pubinfo_triples = [
        (_iri(root), _iri(PAV + "createdWith"), _iri(TOOL)),
        (_iri(root), _iri(EX + "confidence"), _iri(EX + level.capitalize())),
        (_iri(root), _iri(EX + "confidenceBasis"), _literal(basis)),
        (_iri(root), _iri(DCT + "identifier"), _literal(case.get("case_id", "UNKNOWN"))),
        (_iri(root), _iri(EX + "publicationStatus"), _literal("local-serialization-not-publication")),
        (_iri(root), _iri(EX + "identifierScope"), _literal(
            "caller-supplied identifier retained verbatim; registration/publication not inferred" if raw_id is not None
            else "deterministic local identifier; not a registered/trusty nanopublication URI"))]
    creator = pub.get("created_by_or_iri") or pub.get("orcid")
    creator_iri = _identifier_iri(creator)
    if creator_iri:
        pubinfo_triples.append((_iri(root), _iri(PAV + "createdBy"), _iri(creator_iri)))
    else:
        pubinfo_triples.append((_iri(root), _iri(PAV + "createdBy"), _literal(pub.get("agent") or "Local literature-reading agent; ORCID unreported")))
    if created_term:
        pubinfo_triples.append((_iri(root), _iri(DCT + "created"), created_term))
    else:
        pubinfo_triples.append((_iri(root), _iri(EX + "createdDateStatus"), _literal("unreported")))
    if license_value:
        license_iri = license_value if re.match(r"^https?://\S+$", str(license_value)) else None
        pubinfo_triples.append((_iri(root), _iri(DCT + "license"), _iri(license_iri) if license_iri else _literal(license_value)))
    else:
        pubinfo_triples.append((_iri(root), _iri(EX + "licenseStatus"), _literal("unreported")))
    head_triples = [(_iri(root), _iri(RDF + "type"), _iri(NP + "Nanopublication")),
                    (_iri(root), _iri(NP + "hasAssertion"), _iri(ag)),
                    (_iri(root), _iri(NP + "hasProvenance"), _iri(pg)),
                    (_iri(root), _iri(NP + "hasPublicationInfo"), _iri(ig))]
    prefixes = "@prefix np: <%s> .\n@prefix local: <%s> .\n\n" % (NP, base)
    trig = (prefixes + _triples("local:Head", head_triples) + "\n" +
            _triples("local:assertion", assertion_triples) + "\n" +
            _triples("local:provenance", provenance_triples) + "\n" +
            _triples("local:pubInfo", pubinfo_triples))
    record = {"id": aid, "uri": root, "local_unpublished": raw_id is None,
              "statement": statement_text, "subject": subject, "predicate": predicate,
              "object": assertion["object"], "condition_scope": condition,
              "evidence": {**evidence, "quote_verification": binding},
              "source_metadata": source, "confidence": {"level": level, "basis": basis},
              "graph_links": {"head": head, "assertion": ag, "provenance": pg, "pubInfo": ig}}
    return {"trig": trig, "record": record, "warnings": warnings}, []


def _escape_md(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _tables(records):
    atm = ["# Assertion register", "", "Built from the supplied draft; rows are case-derived, not prepared answers.", "",
           "| id | statement | subject | predicate | object | condition scope | confidence | basis |",
           "|-|-|-|-|-|-|-|-|"]
    evm = ["# Evidence map", "", "| id | quote | quote verification | locator | source metadata | computed char offsets |",
           "|-|-|-|-|-|-|"]
    for r in records:
        atm.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            _escape_md(r["id"]), _escape_md(r.get("statement")), _escape_md(r.get("subject")),
            _escape_md(r.get("predicate")), _escape_md(json.dumps(r.get("object"), ensure_ascii=False)),
            _escape_md(r.get("condition_scope")), _escape_md(r["confidence"]["level"]),
            _escape_md(r["confidence"]["basis"])))
        bind = r["evidence"].get("quote_verification") or {}
        evm.append("| %s | %s | %s | %s | %s | %s |" % (
            _escape_md(r["id"]), _escape_md(bind.get("quote")), _escape_md(bind.get("status")),
            _escape_md(_qualifier_text(r["evidence"].get("locator") or r["evidence"].get("anchor"))),
            _escape_md(json.dumps(r.get("source_metadata"), ensure_ascii=False, sort_keys=True)),
            _escape_md("%s-%s" % (bind.get("char_start"), bind.get("char_end")))))
    return "\n".join(atm) + "\n", "\n".join(evm) + "\n"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    if isinstance(text, bytes):
        temp.write_bytes(text)
    else:
        temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def build(case_path, draft_path, out_dir, source_path=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    case, draft = {}, {}
    result = {"schema_version": SCHEMA, "case_id": "UNKNOWN", "status": "failed",
              "nanopub_file": None, "nanopubs": [], "assertion_count": 0,
              "sources": [], "uncertainty": [], "change_log": [], "skipped_reason": []}
    try:
        case = _read_json(case_path)
        if not isinstance(case, dict):
            raise ValueError("case is not a JSON object")
        result["case_id"] = case.get("case_id", "UNKNOWN")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result["uncertainty"].append("case unreadable: %s" % str(exc)[:200])
        result["refusal"] = {"code": "nanopub.case_unreadable", "message": result["uncertainty"][-1]}
        _write(out / "result.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result, 5
    try:
        draft = _read_json(draft_path)
        if isinstance(draft, list):
            draft = {"assertions": draft}
        if not isinstance(draft, dict):
            raise ValueError("draft is not an object or assertion list")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result["uncertainty"].append("draft unreadable: %s" % str(exc)[:200])
        result["refusal"] = {"code": "nanopub.draft_unreadable", "message": result["uncertainty"][-1]}
        _echo_contract(result, case)
        _write(out / "result.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result, 5
    source_text = None
    if source_path:
        try:
            source_text = Path(source_path).read_text(encoding="utf-8-sig")
            result["sources"].append({"kind": "verbatim_evidence_text", "path": str(source_path)})
        except (OSError, UnicodeDecodeError) as exc:
            result["uncertainty"].append("evidence source unreadable; quotes were not verified: %s" % str(exc)[:160])
    assertions = draft.get("assertions", draft.get("nanopubs"))
    if not isinstance(assertions, list):
        assertions = []
    trigs, records, errors, warnings = [], [], [], []
    seen = set()
    for index, assertion in enumerate(assertions, 1):
        built, errs = _one(assertion, index, case, draft, source_text)
        if errs:
            errors.extend(errs)
            continue
        record = built["record"]
        if record["id"] in seen:
            errors.append({"id": record["id"], "code": "assertion.duplicate_id",
                           "message": "duplicate id refused rather than silently reminted"})
            continue
        seen.add(record["id"])
        trigs.append(built["trig"]); records.append(record); warnings.extend(built["warnings"])
    result["skipped_reason"].extend(errors)
    result["uncertainty"].extend(w["message"] + " [" + w["id"] + "]" for w in warnings)
    result["nanopubs"] = records; result["assertion_count"] = len(records)
    result["sources"].extend(r["source_metadata"] for r in records if r.get("source_metadata"))
    if records:
        rdf_path = out / "nanopubs.trig"
        _write(rdf_path, "\n".join(trigs))
        assertion_text, evidence_text = _tables(records)
        _write(out / "assertion_table.md", assertion_text)
        _write(out / "evidence_map.md", evidence_text)
        result.update({"nanopub_file": "nanopubs.trig", "assertion_table_file": "assertion_table.md",
                       "evidence_map_file": "evidence_map.md"})
        import nanopub_check as NC
        fails, std_warnings, infos = NC.check_file(str(rdf_path))
        import rdf_validate as RV
        independent = RV.validate(rdf_path)
        independent["file"] = "nanopubs.trig"  # no output-directory entropy in result bytes
        report = {"stdlib": {"fails": fails, "warnings": std_warnings, "passed_checks": infos},
                  "rdflib": independent, "valid": not fails and not independent["errors"],
                  "graph_count": len(records) * 4, "nanopub_count": len(records)}
        result["rdf_validation"] = report
        _write(out / "rdf_validation.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        if fails or independent["errors"]:
            result["uncertainty"].append("RDF serialization or graph integrity failed validation")
        elif independent["parser"] == "unavailable":
            result["change_log"].append("stdlib TriG/graph checks passed; RDFLib unavailable, so no independent parser result is claimed")
        result["rdf_sha256"] = hashlib.sha256(rdf_path.read_bytes()).hexdigest()
    else:
        errors = errors or [{"code": "nanopub.no_assertions", "message": "no valid assertion was supplied"}]
        result["refusal"] = {"code": "nanopub.no_valid_assertion", "message": "no serializable SPO assertion with provenance was produced"}
        result["uncertainty"].append(result["refusal"]["message"])
        _tables_text = "# Assertion register\n\nNo valid assertion was serializable; inspect skipped_reason.\n"
        _write(out / "assertion_table.md", _tables_text)
        _write(out / "evidence_map.md", "# Evidence map\n\nNo evidence was serialized.\n")
    result["change_log"] = ["normalized %d assertion(s) and wrote four linked graphs per assertion" % len(records),
                            "preserved supplied identifiers; generated only deterministic local URNs where absent",
                            "ran stdlib structural check and optional RDFLib Dataset graph-integrity check"]
    if records and result.get("rdf_validation", {}).get("rdflib", {}).get("parser") == "unavailable":
        result["change_log"].append("no RDFLib was installed; only stdlib check results are reported in rdf_validation")
    result["status"] = "partial" if records and (errors or warnings or result["uncertainty"]) else ("success" if records else "failed")
    _echo_contract(result, case)
    if result["status"] != "failed" and any(result.get(k) is None for k in (case.get("output_contract") or {})):
        result["status"] = "partial"
    if result["status"] == "partial":
        for w in warnings:
            result["skipped_reason"].append({"stage": "metadata_or_evidence", **w})
    _write(out / "result.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result, {"success": 0, "partial": 3, "failed": 5}[result["status"]]


def _echo_contract(result, case):
    contract = case.get("output_contract")
    if contract is None:
        return
    fields = list(contract) if isinstance(contract, dict) else contract if isinstance(contract, list) else [contract]
    bulky = {"output_contract", "assertions", "nanopubs", "source_metadata", "publication_info"}
    for item in fields:
        key = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        if not key or key in result:
            continue
        if key in case and key not in bulky:
            result[key] = case[key]
        else:
            result[key] = None
            result["uncertainty"].append("output_contract field '%s' was not derivable" % key)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--source")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    result, code = build(args.case, args.draft, args.out, args.source)
    print(json.dumps({"status": result["status"], "case_id": result["case_id"],
                      "assertions": result.get("assertion_count"),
                      "nanopub_file": result.get("nanopub_file"),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

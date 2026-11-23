"""Source-bound academic norms and compliance audit with an explicit coverage matrix.

  python compliancecheck.py --case /input/case.json --out /app/output
  python compliancecheck.py --case /input/case.json --material /app/work/paper.txt \
      --out /app/output

A missing statement is a reporting gap, not an accusation of misconduct.  Text
reuse, redundant publication and image/data integrity findings require supplied
comparison evidence.  Journal checks are run only against supplied requirements.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_common as C  # noqa: E402

ALIASES = {"审查报告": "audit_report", "依据与边界": "evidence_bounds", "结果状态": "result_state",
           "review_report": "audit_report", "evidence_and_boundaries": "evidence_bounds",
           "result_status": "result_state", "compliance_results": "compliance_matrix"}
FACETS = ("text_reuse", "data_image_integrity", "authorship", "conflicts_of_interest",
          "ethics_approval", "informed_consent", "data_availability", "code_availability",
          "duplicate_publication", "ai_use_disclosure", "citation_integrity", "privacy",
          "copyright_license", "journal_requirements")
DECLARATION_PATTERNS = {
    "authorship": r"author\s+contributions?|contributorship|CRediT|作者贡献|署名|贡献声明",
    "conflicts_of_interest": r"conflicts?\s+of\s+interest|competing\s+interests?|利益冲突|竞争性利益",
    "ethics_approval": r"ethics\s+(?:committee|approval|review)|institutional\s+review\s+board|\bIRB\b|approved\s+by.{0,60}(?:ethics|institutional)|伦理委员会|伦理审批|伦理审查|批准编号",
    "informed_consent": r"informed\s+consent|consent\s+(?:was\s+)?(?:obtained|waived)|知情同意|豁免知情同意",
    "data_availability": r"data\s+availability|availability\s+of\s+(?:the\s+)?data|data\s+(?:are|is)\s+available|数据可用性|数据可(?:用|获取|公开)",
    "code_availability": r"code\s+availability|availability\s+of\s+(?:the\s+)?code|source\s+code\s+(?:is|are)\s+available|代码可用性|代码(?:公开|可获取)",
    "ai_use_disclosure": r"AI\s+use\s+disclosure|artificial\s+intelligence\s+disclosure|during\s+the\s+preparation.{0,100}(?:AI|artificial\s+intelligence|ChatGPT|GPT[- ]?\d|language\s+model)|(?:we\s+(?:acknowledge|declare)|the\s+authors\s+(?:acknowledge|declare)).{0,60}(?:AI|artificial\s+intelligence|ChatGPT|GPT[- ]?\d|language\s+model)|人工智能使用声明|生成式人工智能使用.{0,20}声明",
    "funding": r"funding|financial\s+support|grant\s+(?:number|no\.)|基金|资助",
}


def spans_matching(doc: C.Document, pattern: str, include_references: bool = False) -> list[dict]:
    rx = re.compile(pattern, re.I | re.S)
    return [s for s in doc.spans if s["kind"] != "heading" and rx.search(s["text"])
            and (include_references or not re.search(r"references|bibliography|参考文献", s["section"], re.I))]


def declaration(doc: C.Document, name: str) -> dict:
    # Declarations commonly appear after the bibliography; do not mistake that
    # end-matter position for a reference title and silently drop the statement.
    spans = spans_matching(doc, DECLARATION_PATTERNS[name], include_references=True)
    return {"reported": bool(spans), "evidence": [doc.evidence(s) for s in spans[:3]],
            "search_scope": {"manuscript_sha256": doc.sha256, "sentences": len(doc.spans),
                             "pattern": DECLARATION_PATTERNS[name]}}


def _subject_mode(case: dict, doc: C.Document) -> tuple[str, list[dict]]:
    structured = case.get("subjects") or case.get("study_subjects")
    if isinstance(structured, str) and structured.strip():
        mode = structured.lower()
        spans = spans_matching(doc, r"human|participant|patient|animal|mice|mouse|rat|受试|患者|动物|小鼠|大鼠")
        return mode, spans[:2]
    methods = [s for s in doc.spans if re.search(r"method|方法|experiment|实验", s["section"], re.I)
               and s["kind"] != "heading"]
    human_rx = r"\b(?:we\s+(?:recruited|enrolled|interviewed|surveyed)|participants?|patients?|human\s+subjects?|volunteers?|respondents?|clinical\s+trial)\b|我们(?:招募|纳入|调查)|受试者|患者|志愿者|人体试验"
    animal_rx = r"\b(?:mice|mouse|rats?|zebrafish|animals?|murine)\b|小鼠|大鼠|斑马鱼|动物实验"
    human = [s for s in methods if re.search(human_rx, s["text"], re.I)]
    animal = [s for s in methods if re.search(animal_rx, s["text"], re.I)]
    if human:
        return "human", human[:2]
    if animal:
        return "animal", animal[:2]
    return "none_detected", []


def _original_data(doc: C.Document) -> tuple[bool, list[dict]]:
    spans = spans_matching(doc, r"\bwe\s+(?:collected|measured|generated|recruited|enrolled|performed|conducted)\b|\bour\s+(?:dataset|samples?|measurements?|experiments?)\b|我们(?:采集|测量|生成|开展|实验)|本研究(?:数据|样本)")
    return bool(spans), spans[:2]


def _code_used(doc: C.Document) -> tuple[bool, list[dict]]:
    spans = spans_matching(doc, r"\bwe\s+(?:implemented|developed|wrote)\b.{0,80}\b(?:code|software|algorithm|pipeline)\b|\bour\s+(?:code|software|script)\b|我们(?:编写|开发|实现).{0,40}(?:代码|软件|算法|流程)")
    return bool(spans), spans[:2]


def _ai_used(doc: C.Document) -> tuple[bool, list[dict]]:
    spans = spans_matching(doc, r"\bwe\s+used\s+(?:ChatGPT|GPT[- ]?\d|a\s+large\s+language\s+model|generative\s+AI)\b|\bAI[- ]assisted\s+(?:writing|editing|analysis|coding)\b|使用(?:生成式)?人工智能.{0,50}(?:撰写|润色|分析|编码)|我们使用\s*(?:ChatGPT|GPT|大语言模型)", include_references=True)
    return bool(spans), spans[:2]


def absence_finding(rule: str, category: str, severity: str, doc: C.Document,
                    triggers: list[dict], basis: str, fix: str, facet: str,
                    guideline: dict | None = None) -> dict:
    nearest = triggers[0] if triggers else next((s for s in reversed(doc.spans)
                                                if s["kind"] != "heading" and not re.search(r"references|参考文献", s["section"], re.I)),
                                               doc.spans[0] if doc.spans else None)
    evidence = doc.evidence(nearest) if nearest else None
    finding = {"rule": rule, "category": category, "severity": severity, "facet": facet,
               "kind": "reporting_gap", "verdict": "not_reported_not_misconduct",
               "location": (f"whole supplied manuscript sha256:{doc.sha256[:12]}; nearest: {doc.locator(nearest)}" if nearest else None),
               "excerpt": nearest["text"] if nearest else None, "trigger_evidence": [doc.evidence(s) for s in triggers],
               "search_scope": {"manuscript_sha256": doc.sha256, "sentences": len(doc.spans), "references_excluded": True},
               "evidence_at_nearest_location": evidence, "basis": basis, "fix": fix}
    if guideline:
        finding["guideline"] = guideline
    return finding


def _author_name(value: Any) -> str:
    if isinstance(value, str):
        return C.normalise_space(value).casefold()
    if isinstance(value, dict):
        name = value.get("name") or " ".join(str(value.get(k) or "") for k in ("given", "family"))
        return C.normalise_space(name).casefold()
    return ""


def authorship_checks(case: dict, doc: C.Document, declarations: dict) -> list[dict]:
    findings = []
    authors = case.get("authors") or case.get("author_list") or []
    contributions = case.get("author_contributions") or case.get("contributions") or {}
    names = {_author_name(a) for a in authors if _author_name(a)} if isinstance(authors, list) else set()
    contributed = set()
    if isinstance(contributions, dict):
        contributed = {_author_name(k) for k in contributions if _author_name(k)}
    elif isinstance(contributions, list):
        contributed = {_author_name(x.get("author") or x.get("name")) for x in contributions
                       if isinstance(x, dict) and _author_name(x.get("author") or x.get("name"))}
    if names and contributed:
        for name in sorted(names - contributed):
            findings.append(absence_finding("compliance.author_contribution_not_mapped", "署名与贡献", "medium", doc, [],
                                            f"Structured author '{name}' has no corresponding contribution record; this is a mapping gap, not a guest-authorship verdict.",
                                            "Add that author's actual CRediT roles or correct the author/contributor identifier.", "authorship"))
        for name in sorted(contributed - names):
            findings.append(absence_finding("compliance.contributor_not_in_author_list", "署名与贡献", "medium", doc, [],
                                            f"Contributor '{name}' is absent from the supplied author list; identity needs reconciliation.",
                                            "Reconcile the contributor identifier with the author list; do not infer gift or ghost authorship automatically.", "authorship"))
    return findings


def _comparison_documents(case: dict) -> list[dict]:
    records = []
    for key in ("comparison_corpus", "related_publications", "prior_publications", "published_versions"):
        value = case.get(key)
        entries = value.values() if isinstance(value, dict) else value
        if isinstance(entries, (list, tuple)):
            for pos, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                text = next((entry.get(k) for k in ("text", "full_text", "abstract", "content")
                             if isinstance(entry.get(k), str) and entry.get(k).strip()), None)
                if text:
                    records.append({**entry, "name": str(entry.get("name") or entry.get("title") or f"comparison-{pos+1}"),
                                    "text": text, "sha256": C.sha256_text(text)})
    return records


def word_shingles(text: str, size: int = 12) -> dict[tuple[str, ...], int]:
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", text)]
    return {tuple(words[i:i+size]): i for i in range(max(0, len(words)-size+1))}


def reuse_checks(case: dict, doc: C.Document) -> tuple[list[dict], list[dict], list[str]]:
    comparisons = _comparison_documents(case)
    findings, checks, passed = [], [], []
    for source in comparisons:
        other = C.Document(source["text"], source["name"])
        for span in doc.spans:
            if span["kind"] == "heading" or re.search(r"references|bibliography|参考文献", span["section"], re.I):
                continue
            shingles = word_shingles(span["text"])
            if not shingles:
                continue
            best = None
            common = []
            for candidate in other.spans:
                shared = list(set(shingles) & set(word_shingles(candidate["text"])))
                if len(shared) > len(common):
                    best, common = candidate, shared
            if not best or not common:
                continue
            following = doc.text[span["end"]:span["end"] + 24]
            attributed = bool(re.search(r"\[[0-9,; \-–]+\]|\([^)]*(?:19|20)\d{2}[^)]*\)|[\"“”]", span["text"])
                              or re.match(r"\s*(?:\[[0-9,; \-–]+\]|\([^)]*(?:19|20)\d{2}[^)]*\))", following))
            check = {"source": source["name"], "manuscript_quote": span["text"], "manuscript_locator": doc.locator(span),
                     "comparison_quote": best["text"], "comparison_locator": other.locator(best),
                     "shared_12word_shingles": len(common), "attributed_or_quoted": attributed,
                     "verdict": "attributed_overlap" if attributed else "possible_unattributed_text_reuse"}
            checks.append(check)
            if attributed:
                passed.append("attributed_text_overlap:" + span["id"])
            else:
                findings.append({"rule": "integrity.possible_unattributed_text_reuse", "category": "学术诚信/文本复用",
                                 "severity": "medium", "facet": "text_reuse", "kind": "integrity_signal",
                                 "verdict": "possible_reuse_not_plagiarism_verdict", "location": doc.locator(span),
                                 "excerpt": span["text"], "evidence_quote": best["text"],
                                 "evidence_locator": source["name"] + ": " + other.locator(best),
                                 "basis": f"At least one exact 12-word sequence is shared with the supplied comparison document ({len(common)} shingles); quotation/attribution was not detected in the manuscript sentence.",
                                 "fix": "Check the comparison source. Quote and cite legitimate reuse, rewrite in original wording with attribution, or document why the overlap is standard wording; do not label intent automatically."})
    return findings, checks, passed


def duplicate_publication_checks(case: dict, doc: C.Document) -> tuple[list[dict], list[dict]]:
    findings, checks = [], []
    title = str(case.get("title") or case.get("manuscript_title") or "")
    if not title:
        title = next((line.strip() for line in doc.text.splitlines() if line.strip()), "")
        if len(title) > 240:
            title = next((s["text"] for s in doc.spans if s["kind"] == "heading"), "")
    disclosed = bool(case.get("related_publication_disclosed") or case.get("duplicate_publication_disclosed"))
    for source in _comparison_documents(case):
        other_title = str(source.get("title") or source.get("name") or "")
        title_score = C.f1(title, other_title) if title and other_title else 0.0
        manuscript_abstract = " ".join(s["text"] for s in doc.section_spans(r"abstract|摘要"))
        other_abstract = str(source.get("abstract") or source.get("text") or "")
        text_score = C.f1(manuscript_abstract, other_abstract) if manuscript_abstract and other_abstract else 0.0
        check = {"comparison": source["name"], "title_similarity": round(title_score, 4),
                 "abstract_similarity": round(text_score, 4), "disclosed": disclosed,
                 "status": "undetermined"}
        if (title_score >= 0.78 or text_score >= 0.68) and not disclosed:
            check["status"] = "possible_redundant_publication"
            findings.append({"rule": "integrity.possible_redundant_publication", "category": "重复发表", "severity": "high",
                             "facet": "duplicate_publication", "kind": "integrity_signal",
                             "verdict": "possible_overlap_not_redundancy_verdict", "location": "title/abstract",
                             "excerpt": manuscript_abstract[:600] or title, "evidence_quote": other_abstract[:600] or other_title,
                             "evidence_locator": source["name"], "basis": f"High title/abstract overlap with supplied prior publication (title={title_score:.2f}, abstract={text_score:.2f}) and no disclosure flag.",
                             "fix": "Compare hypotheses, datasets and results across both versions; disclose and cite related publications and explain the distinct contribution before determining redundancy."})
        elif disclosed:
            check["status"] = "disclosed_for_human_review"
    return findings, checks


def image_integrity_checks(case: dict, doc: C.Document) -> list[dict]:
    images = case.get("images") or case.get("figures") or []
    if not isinstance(images, list):
        return []
    by_hash: dict[str, list[dict]] = {}
    for pos, image in enumerate(images):
        if not isinstance(image, dict):
            continue
        digest = str(image.get("sha256") or image.get("hash") or "").lower()
        if digest:
            by_hash.setdefault(digest, []).append({**image, "_pos": pos})
    findings = []
    for digest, entries in sorted(by_hash.items()):
        if len(entries) < 2:
            continue
        undeclared = [x for x in entries if not (x.get("reuse_declared") or x.get("declared_reuse") or x.get("same_image_disclosed"))]
        if len(undeclared) < 2:
            continue
        ids = [str(x.get("id") or x.get("name") or x["_pos"] + 1) for x in undeclared]
        findings.append({"rule": "integrity.identical_image_reuse_undeclared", "category": "图像与数据诚信", "severity": "high",
                         "facet": "data_image_integrity", "kind": "integrity_signal", "verdict": "requires_investigation_not_falsification_verdict",
                         "location": ", ".join(ids), "excerpt": f"identical supplied image hash {digest}",
                         "basis": "Distinct supplied figure records have byte-identical hashes and no reuse disclosure. Legitimate reuse remains possible.",
                         "fix": "Inspect the original images and captions; disclose legitimate reuse or replace incorrect panels. Do not infer manipulation from the hash alone."})
    return findings


def citation_integrity_checks(case: dict, doc: C.Document) -> tuple[list[dict], list[str]]:
    findings, passed = [], []
    refs = case.get("references") or []
    if isinstance(refs, list):
        for pos, ref in enumerate(refs):
            if isinstance(ref, dict) and ref.get("retracted"):
                findings.append({"rule": "compliance.retracted_source_used", "category": "引用规范", "severity": "high",
                                 "facet": "citation_integrity", "kind": "verified_metadata_signal", "verdict": "retracted_source_recorded",
                                 "location": str(ref.get("locator") or ref.get("key") or pos + 1),
                                 "excerpt": str(ref.get("raw") or ref.get("title") or ref.get("key") or "reference entry"),
                                 "basis": str(ref.get("retraction_notice") or "The supplied reference record explicitly marks this source retracted."),
                                 "fix": "Read the retraction notice, remove reliance on the retracted claim or explicitly discuss why it is cited as retracted."})
            elif isinstance(ref, dict):
                passed.append("reference_screened:" + str(ref.get("key") or pos + 1))
    return findings, passed


def privacy_checks(doc: C.Document) -> list[dict]:
    findings = []
    sensitive = spans_matching(doc, r"\b(?:MRN|medical\s+record\s+number|patient\s+ID|social\s+security\s+number|passport\s+number)\s*[:=#-]?\s*[A-Z0-9-]{4,}\b|(?:身份证号|病历号|住院号|电话号码)\s*[:：]?\s*[0-9Xx-]{5,}", include_references=True)
    for span in sensitive:
        if re.search(r"author|correspondence|affiliation", span["section"], re.I):
            continue
        findings.append({"rule": "privacy.direct_identifier_exposed", "category": "隐私与数据合规", "severity": "high",
                         "facet": "privacy", "kind": "verified_text_signal", "verdict": "identifier_pattern_present",
                         "location": doc.locator(span), "excerpt": span["text"],
                         "basis": "A direct-identifier label and value occur in the supplied scientific text.",
                         "fix": "Remove or pseudonymise the identifier, verify that re-identification risk is controlled, and document the applicable authorisation/ethics basis."})
    return findings


def copyright_checks(doc: C.Document) -> list[dict]:
    findings = []
    third_party = spans_matching(doc, r"\b(?:reproduced|adapted|republished|taken)\s+from\b|转载自|改编自|复制自", include_references=True)
    permission = spans_matching(doc, r"\b(?:with\s+permission|permission\s+(?:was\s+)?obtained|licensed\s+under|CC\s*BY|Creative\s+Commons|copyright\s+permission)\b|已获得授权|许可协议|知识共享|版权许可", include_references=True)
    for span in third_party:
        # PDF sentence splitting often separates 'et al.' from the licence sentence;
        # same-paragraph or immediately following permission text belongs to the item.
        if any(p["start"] == span["start"] or (p["paragraph"] == span["paragraph"] and abs(p["start"] - span["end"]) < 400) for p in permission):
            continue
        nearby = doc.text[span["start"]:min(len(doc.text), span["end"] + 400)]
        if re.search(r"with\s+permission|permission\s+(?:was\s+)?obtained|licensed\s+under|CC\s*BY|已获得授权|许可协议", nearby, re.I):
            continue
        if permission and any(re.search(r"all\s+(?:figures|tables)|所有(?:图|表)|throughout", p["text"], re.I) for p in permission):
            continue
        findings.append({"rule": "copyright.reuse_permission_not_reported", "category": "版权与许可", "severity": "medium",
                         "facet": "copyright_license", "kind": "reporting_gap", "verdict": "permission_not_reported_not_infringement_verdict",
                         "location": doc.locator(span), "excerpt": span["text"],
                         "basis": "Third-party reuse is stated, but no item-specific permission/licence statement was located in the supplied text.",
                         "fix": "Add the source, licence/permission identifier and required attribution, or replace the material; verify licence compatibility rather than assuming infringement."})
    return findings


def guideline_requirements(case: dict) -> tuple[list[dict], dict]:
    value = case.get("journal_requirements") or case.get("author_guidelines") or case.get("target_guidelines")
    if isinstance(value, dict):
        return [value], {"version": value.get("version") or value.get("date"),
                         "locator": value.get("url") or value.get("locator") or value.get("source")}
    if isinstance(value, list):
        records = [x for x in value if isinstance(x, dict)]
        return records, {"version": next((x.get("version") or x.get("date") for x in records if x.get("version") or x.get("date")), None),
                         "locator": next((x.get("url") or x.get("locator") or x.get("source") for x in records if x.get("url") or x.get("locator") or x.get("source")), None)}
    return [], {}


def guideline_checks(case: dict, doc: C.Document, declarations: dict) -> tuple[list[dict], list[dict], list[str]]:
    records, provenance = guideline_requirements(case)
    findings, checks, pending = [], [], []
    if records and not provenance.get("version"):
        pending.append("Supplied journal guideline has no version/date; requirement conclusions apply only to the supplied text snapshot.")
    for record in records:
        required_sections = record.get("required_sections") or record.get("sections") or []
        if isinstance(required_sections, list):
            for section in required_sections:
                name = str(section)
                found = any(name.casefold() in str(s["section"]).casefold() for s in doc.spans if s["kind"] == "heading")
                checks.append({"requirement": "section", "name": name, "status": "present" if found else "missing",
                               "guideline": provenance})
                if not found:
                    findings.append(absence_finding("journal.required_section_missing", "投稿要求", "medium", doc, [],
                                                    f"Required section '{name}' was not located among supplied headings; requirement={provenance}.",
                                                    f"Add a clearly labelled '{name}' section or document an applicable guideline exception.", "journal_requirements", provenance))
        required_declarations = record.get("required_declarations") or []
        if isinstance(required_declarations, list):
            for req in required_declarations:
                key = str(req)
                canonical = {"coi": "conflicts_of_interest", "competing_interests": "conflicts_of_interest",
                             "ethics": "ethics_approval", "consent": "informed_consent",
                             "data": "data_availability", "code": "code_availability",
                             "author_contributions": "authorship", "ai": "ai_use_disclosure"}.get(key, key)
                reported = declarations.get(canonical, {}).get("reported", False)
                checks.append({"requirement": "declaration", "name": key, "status": "present" if reported else "missing",
                               "guideline": provenance})
                if not reported:
                    findings.append(absence_finding("journal.required_declaration_missing", "投稿要求", "medium", doc, [],
                                                    f"The supplied guideline explicitly requires '{key}', but its declaration was not located; requirement={provenance}.",
                                                    f"Add an honest '{key}' declaration, including not-applicable reasoning where permitted.", "journal_requirements", provenance))
        try:
            limit = int(record.get("word_limit")) if record.get("word_limit") is not None else None
        except (TypeError, ValueError):
            limit = None
            pending.append("Journal word_limit was not a readable integer and was not enforced.")
        if limit is not None:
            body = " ".join(s["text"] for s in doc.spans if not re.search(r"references|参考文献", s["section"], re.I))
            words = len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?|[\u3400-\u9fff]", body))
            checks.append({"requirement": "word_limit", "limit": limit, "observed": words,
                           "status": "exceeded" if words > limit else "within_limit", "guideline": provenance})
            if words > limit:
                nearest = doc.spans[0] if doc.spans else None
                findings.append({"rule": "journal.word_limit_exceeded", "category": "投稿要求", "severity": "medium",
                                 "facet": "journal_requirements", "kind": "guideline_mismatch", "verdict": "verified_requirement_mismatch",
                                 "location": doc.locator(nearest) if nearest else "whole manuscript", "excerpt": f"observed {words} words/CJK characters; supplied limit {limit}",
                                 "basis": f"Deterministic count exceeds supplied guideline limit; guideline={provenance}.",
                                 "fix": "Reduce the counted manuscript text to the guideline limit or document an applicable exception.", "guideline": provenance})
    return findings, checks, pending


def audit(case: dict, materials: list[dict], material_errors: list[str]) -> dict:
    primary = materials[0]
    doc = C.Document(primary["text"], primary["name"])
    declarations = {name: declaration(doc, name) for name in DECLARATION_PATTERNS}
    findings: list[dict] = []
    passed: list[str] = []
    pending: list[str] = list(material_errors)
    full_manuscript = len(doc.text) >= 800 and any(re.search(r"method|方法", s["section"], re.I) for s in doc.spans)
    subject_mode, subject_spans = _subject_mode(case, doc)
    data_used, data_spans = _original_data(doc)
    code_used, code_spans = _code_used(doc)
    ai_used, ai_spans = _ai_used(doc)

    if full_manuscript and not declarations["conflicts_of_interest"]["reported"]:
        findings.append(absence_finding("compliance.coi_not_reported", "利益冲突", "medium", doc, [],
                                        "No conflict/competing-interest declaration was located in the complete supplied manuscript. This does not establish an undisclosed conflict.",
                                        "Add an explicit conflict-of-interest declaration (including 'none declared' when true), following the target guideline.", "conflicts_of_interest"))
    if subject_mode != "none_detected" and subject_mode not in {"none", "not_applicable", "n/a", "无"}:
        if not declarations["ethics_approval"]["reported"]:
            findings.append(absence_finding("compliance.ethics_approval_not_reported", "伦理审查", "high", doc, subject_spans,
                                            f"The methods indicate {subject_mode} subjects, but no ethics approval/review statement was located. Approval status remains undetermined.",
                                            "Supply the committee, approval/waiver status and protocol identifier, or mark the facet not applicable with a sourced justification.", "ethics_approval"))
        elif not re.search(r"(?:protocol|approval|ethics|IRB|批件|批准).{0,50}(?:no\.?|number|#|编号|第.{0,12}号)|\b[A-Z]{2,}[- ]?\d{2,}\b", " ".join(e["quote"] for d in [declarations["ethics_approval"]] for e in d["evidence"]), re.I):
            findings.append({"rule": "compliance.ethics_identifier_not_reported", "category": "伦理审查", "severity": "medium",
                             "facet": "ethics_approval", "kind": "reporting_gap", "verdict": "identifier_not_reported",
                             "location": declarations["ethics_approval"]["evidence"][0]["locator"],
                             "excerpt": declarations["ethics_approval"]["evidence"][0]["quote"],
                             "basis": "An ethics statement exists but no protocol/approval identifier was detected; validity is not denied.",
                             "fix": "Add the protocol/approval or waiver identifier and committee scope, or explain why no identifier was issued."})
        if subject_mode == "human" and not declarations["informed_consent"]["reported"]:
            findings.append(absence_finding("compliance.informed_consent_not_reported", "伦理审查/知情同意", "high", doc, subject_spans,
                                            "Human-subject methods were found but no informed-consent or consent-waiver statement was located.",
                                            "Report consent acquisition or the ethics-approved waiver and its scope; do not infer that consent was absent.", "informed_consent"))
    if data_used and not declarations["data_availability"]["reported"]:
        findings.append(absence_finding("compliance.data_availability_not_reported", "数据可用性", "medium", doc, data_spans,
                                        "Original data generation/collection is described but no data-availability statement was located.",
                                        "Add a repository/accession or a specific lawful/ethical access restriction and contact route; do not invent a URL.", "data_availability"))
    if code_used and not declarations["code_availability"]["reported"]:
        findings.append(absence_finding("compliance.code_availability_not_reported", "代码可用性", "medium", doc, code_spans,
                                        "Study code/software development is described but no code-availability statement was located.",
                                        "Provide the exact repository/version or an honest availability restriction; cite a versioned archive when possible.", "code_availability"))
    if ai_used and not declarations["ai_use_disclosure"]["reported"]:
        findings.append(absence_finding("compliance.ai_use_disclosure_not_reported", "AI 使用披露", "medium", doc, ai_spans,
                                        "AI-assisted manuscript/analysis work is stated, but a distinct preparation/use disclosure was not located. This is a reporting gap, not proof of undisclosed use.",
                                        "Name the tool/version, task, extent and human verification in an AI-use statement, following the supplied target policy.", "ai_use_disclosure"))

    findings.extend(authorship_checks(case, doc, declarations))
    findings.extend(image_integrity_checks(case, doc))
    findings.extend(privacy_checks(doc))
    findings.extend(copyright_checks(doc))
    citation_findings, citation_passed = citation_integrity_checks(case, doc)
    findings.extend(citation_findings)
    passed.extend(citation_passed)
    reuse_findings, reuse_results, reuse_passed = reuse_checks(case, doc)
    findings.extend(reuse_findings)
    passed.extend(reuse_passed)
    duplicate_findings, duplicate_results = duplicate_publication_checks(case, doc)
    findings.extend(duplicate_findings)
    guideline_findings, guideline_results, guideline_pending = guideline_checks(case, doc, declarations)
    findings.extend(guideline_findings)
    pending.extend(guideline_pending)

    for name, record in declarations.items():
        if record["reported"] and name in FACETS:
            passed.append(name)
    comparisons = _comparison_documents(case)
    coverage = {}
    for facet in FACETS:
        related = [f for f in findings if f.get("facet") == facet]
        coverage[facet] = {"status": "problem" if related else "checked",
                           "finding_ids": [], "evidence": []}
    coverage["text_reuse"].update({"status": "problem" if reuse_findings else ("checked" if comparisons else "not_checked"),
                                   "reason": None if comparisons else "no supplied comparison corpus; plagiarism cannot be determined"})
    coverage["duplicate_publication"].update({"status": "problem" if duplicate_findings else ("checked" if comparisons else "not_checked"),
                                               "reason": None if comparisons else "no supplied prior-publication corpus"})
    if not (case.get("images") or case.get("figures") or case.get("data_integrity")):
        coverage["data_image_integrity"].update({"status": "not_checked", "reason": "no original image/data integrity evidence supplied; fabrication/falsification cannot be inferred from prose"})
    if subject_mode in {"none_detected", "none", "not_applicable", "n/a", "无"}:
        coverage["ethics_approval"].update({"status": "not_applicable", "reason": "no human/animal subject methods detected in supplied text"})
        coverage["informed_consent"].update({"status": "not_applicable", "reason": "no human-subject methods detected"})
    if not data_used:
        coverage["data_availability"].update({"status": "not_applicable", "reason": "no original data generation detected"})
    if not code_used:
        coverage["code_availability"].update({"status": "not_applicable", "reason": "no study code development detected"})
    if not ai_used:
        coverage["ai_use_disclosure"].update({"status": "not_applicable_unless_policy_requires", "reason": "no AI-assisted manuscript/analysis use detected; AI as research subject alone is not use"})
    if not guideline_requirements(case)[0]:
        coverage["journal_requirements"].update({"status": "not_checked", "reason": "no target guideline supplied; no requirements were invented"})

    findings = C.finalise_findings(findings)
    for finding in findings:
        facet = finding.get("facet")
        if facet in coverage:
            coverage[facet]["finding_ids"].append(finding["id"])
            if finding.get("excerpt"):
                coverage[facet]["evidence"].append({"quote": finding.get("excerpt"), "locator": finding.get("location")})
    counts = C.severity_counts(findings)
    not_checked = [f"{facet}: {record.get('reason')}" for facet, record in coverage.items() if record["status"] == "not_checked"]
    limits = ["Absence findings mean 'not reported in the supplied version', not proof of misconduct or absence of approval.",
              "Plagiarism, fabrication, falsification and redundant publication require external/original evidence; overlap and identical hashes are investigation signals only.",
              "Authorship roles, funding truth, licence validity and ethics approval authenticity require human/source-document verification.",
              "No journal clause or AI policy is assumed when a target guideline is absent."]
    status = "blocked" if counts.get("high") else ("review" if findings or material_errors else "clean")
    evidence_bounds = {"manuscript_quotes": [{"finding_id": f["id"], "quote": f.get("excerpt"), "locator": f.get("location")}
                                             for f in findings if f.get("excerpt")],
                       "declarations": declarations, "comparison_evidence": reuse_results + duplicate_results,
                       "pending_review": pending, "coverage_matrix": coverage}
    result = {"schema_version": C.SCHEMA_VERSION, "status": status, "ok": True,
              "audit_report": findings, "findings": findings, "compliance_matrix": coverage,
              "declarations": declarations, "text_reuse_checks": reuse_results,
              "duplicate_publication_checks": duplicate_results, "guideline_checks": guideline_results,
              "evidence_bounds": evidence_bounds, "uncertainty": pending,
              "result_state": C.result_state(findings, sorted(set(passed)), pending, not_checked),
              "severity_counts": counts,
              "sources": [{k: v for k, v in m.items() if k != "text"} for m in materials],
              "checked": {"manuscript_sha256": doc.sha256, "manuscript_chars": len(doc.text),
                          "sentences": len(doc.spans), "full_manuscript": full_manuscript,
                          "subject_mode": subject_mode, "original_data_detected": data_used,
                          "study_code_detected": code_used, "ai_assistance_detected": ai_used,
                          "facets": coverage},
              "limits": limits,
              "change_records": [{"stage": "declarations", "action": "locate explicit declaration evidence and search scope"},
                                 {"stage": "risk_rules", "action": "bind each finding to quote, locator, severity and coverage facet"},
                                 {"stage": "coverage", "action": "separate checked/problem/not_applicable/not_checked",
                                  "values_fabricated": False}]}
    return result


def run(case_path: str | Path, out_dir: str | Path, materials: list[str] | None = None) -> dict:
    case, error = C.read_json(case_path)
    if error:
        return C.refused({}, out_dir, "compliance.case_unreadable", error, ALIASES)
    if not isinstance(case, dict):
        return C.refused({}, out_dir, "compliance.case_not_object", "case.json must be a JSON object", ALIASES)
    records, errors = C.material_records(case, case_path, materials)
    if not records:
        detail = "no readable manuscript/full text was supplied" + (("; " + "; ".join(errors)) if errors else "")
        return C.refused(case, out_dir, "compliance.no_manuscript", detail, ALIASES)
    try:
        result = C.complete_contract(audit(case, records, errors), case, ALIASES)
        C.write_artifacts(out_dir, result)
        return result
    except Exception as exc:
        return C.refused(case, out_dir, "compliance.internal_error",
                         f"compliance audit could not complete: {type(exc).__name__}: {exc}", ALIASES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compliancecheck", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True)
    parser.add_argument("--material", action="append", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.case, args.out, args.material)
    except Exception as exc:
        result = C.refused({}, args.out, "compliance.runner_error", f"runner refused: {type(exc).__name__}: {exc}", ALIASES)
    print(C.summary_for_stdout(result))
    return C.EXIT_CODES.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())

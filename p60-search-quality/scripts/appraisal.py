"""Deterministic, source-bound research-quality appraisal.

The engine deliberately separates *reported evidence* from *reviewer judgement*.
A lexical match is only an observation: low risk requires every declared evidence
group, contradictory evidence raises a concern, and missing evidence remains
insufficient.  No journal prestige, peer-review, full-text or causal claim is
inferred.  Quotes are exact slices of a supplied text unit or exact structured
field values, with source paths/pages retained.

Public API: appraise(spec) -> result dict.  The CLI adds file loading and Harbor
contract completion.  Standard library only and no wall-clock fields, so equal
inputs produce byte-identical JSON.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = "research-quality/v2"
RUBRIC_VERSION = "source-bound-quality-rubric/2.0"
JUDGEMENTS = {"low", "some_concerns", "high", "insufficient", "not_applicable"}
BULKY = {
    "documents", "studies", "records", "corpus", "text", "full_text", "abstract",
    "sections", "pages", "tables", "materials", "files", "output_contract", "spec",
    "review_decisions", "reference_graph", "search_history", "iterations",
}

DESIGN_PATTERNS = [
    ("randomized_trial", r"\brandomi[sz]ed\s+(?:controlled\s+)?trial\b|\bRCT\b|\brandomly\s+(?:assigned|allocated)\b"),
    ("nonrandomized_intervention", r"\bnon[- ]?randomi[sz]ed\s+(?:intervention|trial|study)\b|\bquasi[- ]experimental\b"),
    ("cohort", r"\b(?:prospective|retrospective)?\s*cohort\s+study\b|\blongitudinal\s+cohort\b"),
    ("case_control", r"\bcase[- ]control\s+study\b"),
    ("cross_sectional", r"\bcross[- ]sectional\s+(?:study|survey)\b"),
    ("systematic_review", r"\bsystematic\s+review\b|\bmeta[- ]analysis\b|\bPRISMA\b"),
    ("diagnostic_accuracy", r"\bdiagnostic\s+accuracy\s+study\b|\breference\s+standard\b.*\bindex\s+test\b"),
    ("qualitative", r"\bqualitative\s+(?:study|interviews?|research)\b|\bgrounded\s+theory\b|\bthematic\s+analysis\b"),
    ("computational", r"\b(?:in silico|computational)\s+study\b|\bmachine[- ]learning\s+model\b|\bdeep[- ]learning\s+model\b"),
    ("protocol", r"\bstudy\s+protocol\b|\btrial\s+protocol\b"),
]

MISSING = re.compile(r"\b(?:not|was not|were not|wasn't|weren't)\s+(?:reported|described|specified|assessed|available)\b|\bunreported\b|\bunclear\b|未报告|未说明|不清楚", re.I)
NEGATIVE = re.compile(r"\b(?:no|not|without|non[- ]?)\s+(?:\w+[- ]?){0,2}$", re.I)

# Each group is necessary before the engine may say "low".  These are reporting
# and risk-of-bias aids, not claims that a keyword proves methodological rigour.
RULES: dict[str, dict[str, Any]] = {
    "design_identification": {"label": "研究设计与问题匹配", "category": "研究设计", "groups": {}},
    "random_sequence": {"label": "随机序列生成", "category": "偏倚风险", "groups": {
        "sequence": [r"\brandom\s+(?:sequence|number generator)\b", r"\bcomputer[- ]generated\s+random\b", r"\brandomi[sz]ation\s+(?:was|is)\s+generated\b"]},
        "concerns": [r"\balternat(?:e|ing)\s+allocation\b", r"\ballocated\s+by\s+(?:date of birth|record number)\b"]},
    "allocation_concealment": {"label": "分配隐藏", "category": "偏倚风险", "groups": {
        "concealment": [r"\ballocation\s+conceal", r"\bsequentially\s+numbered\s+opaque\s+sealed\s+envelopes?\b", r"\bcentral\s+randomi[sz]ation\b"]},
        "concerns": [r"\bopen\s+allocation\b", r"\ballocation\s+(?:was\s+)?not\s+concealed\b"]},
    "blinding": {"label": "盲法与结局测量", "category": "偏倚风险", "groups": {
        "blinding": [r"\b(?:participants?|personnel|outcome\s+assessors?)\s+(?:were|was)\s+blinded\b", r"\bdouble[- ]blind\b", r"\bmasked\s+outcome\s+assessment\b"]},
        "concerns": [r"\bopen[- ]label\b", r"\bno\s+blinding\b", r"\bunblinded\b"]},
    "sample_data": {"label": "样本、抽样与数据充分性", "category": "证据充分性", "groups": {
        "sample": [r"\b(?:n\s*=|sample\s+size\s+(?:was|of)|enrolled\s+\d+|included\s+\d+\s+(?:participants?|patients?|samples?))\b", r"\b\d+\s+(?:participants?|patients?)\s+were\s+(?:enrolled|randomi[sz]ed|included)\b", r"样本量\s*(?:为|=|:|：)\s*\d+"],
        "sampling": [r"\b(?:consecutive|random|stratified|purposive)\s+sampling\b", r"\binclusion\s+and\s+exclusion\s+criteria\b", r"\beligibility\s+criteria\b", r"纳入(?:和|与)排除标准"],
        "precision": [r"\b(?:a\s+priori\s+)?power\s+(?:calculation|analysis)\b", r"\bsample[- ]size\s+calculation\b", r"\bprecision[- ]based\s+sample\b"]},
        "concerns": [r"\bconvenience\s+sample\b", r"\bpost[- ]hoc\s+power\b"]},
    "outcomes_measurement": {"label": "测量、结局与随访", "category": "证据充分性", "groups": {
        "outcome": [r"\bprimary\s+outcome\b", r"\bpre[- ]specified\s+outcome\b", r"\bendpoint\s+(?:was|is)\b", r"主要结局"],
        "measurement": [r"\bvalidat(?:ed|ion)\b", r"\breliab(?:le|ility)\b", r"\bobjective\s+(?:measure|outcome)\b", r"\bcalibrat(?:ed|ion)\b", r"\binter[- ]rater\b"],
        "timing": [r"\bfollow[- ]up\s+(?:at|for|period)\b", r"\bat\s+\d+\s+(?:weeks?|months?|years?)\b", r"\bmeasurement\s+time\s*points?\b"]},
        "concerns": [r"\bunvalidat(?:ed|ed)\s+(?:scale|instrument|measure)\b", r"\boutcome\s+(?:was\s+)?changed\s+after\b"]},
    "methods_transparency": {"label": "方法透明度", "category": "报告完整性", "groups": {
        "procedure": [r"\bmethods?\s*:", r"\bparticipants?\s+were\s+(?:recruited|assigned)\b", r"\bprocedure\s+(?:was|is)\b", r"\bwe\s+(?:used|performed|measured)\b", r"方法\s*[:：]"],
        "materials_protocol": [r"\bprotocol\b", r"\bmaterials?\b", r"\breagent\b", r"\binstrument\s+model\b", r"\bsoftware\s+version\b"]},
        "concerns": []},
    "confounding": {"label": "混杂控制", "category": "偏倚风险", "groups": {
        "control": [r"\bpropensity[- ]score\b", r"\bmultivari(?:able|ate)\s+(?:regression|adjustment)\b", r"\badjusted\s+for\s+(?:age|sex|confounders?|baseline)\b", r"\bdirected\s+acyclic\s+graph\b", r"\bconfounders?\s+were\s+(?:selected|adjusted)\b"]},
        "concerns": [r"\bunadjusted\s+(?:analysis|estimate)\b", r"\bresidual\s+confounding\s+(?:remains|is likely)\b", r"\bno\s+adjustment\s+for\s+confound"]},
    "selection_bias": {"label": "研究对象选择", "category": "偏倚风险", "groups": {
        "selection": [r"\bconsecutive\s+(?:patients?|participants?|sampling)\b", r"\bpopulation[- ]based\s+(?:sample|cohort)\b", r"\ball\s+eligible\s+participants\b", r"\binception\s+cohort\b"]},
        "concerns": [r"\bself[- ]selected\s+(?:sample|participants?)\b", r"\bvolunteer\s+sample\b", r"\bselected\s+(?:participants?|cases)\s+based\s+on\s+outcome\b"]},
    "comparator": {"label": "对照与比较组", "category": "偏倚风险", "groups": {
        "comparator": [r"\bcontrol\s+group\b", r"\bcomparator\s+group\b", r"\bmatched\s+controls?\b", r"\bactive\s+comparator\b"]},
        "concerns": [r"\bhistorical\s+controls?\s+without\b", r"\bno\s+comparator\b"]},
    "missing_data": {"label": "缺失数据、退出与失访", "category": "偏倚风险", "groups": {
        "reporting": [r"\bmissing\s+data\b", r"\battrition\b", r"\bdrop[- ]?outs?\b", r"\blost\s+to\s+follow[- ]up\b", r"\bcomplete[- ]case\b", r"\bintention[- ]to[- ]treat\b"],
        "handling": [r"\bmultiple\s+imputation\b", r"\bintention[- ]to[- ]treat\b", r"\bsensitivity\s+analysis\s+for\s+missing\b", r"\bno\s+missing\s+(?:outcome\s+)?data\b"]},
        "concerns": [r"\bcomplete[- ]case\s+analysis\s+only\b", r"\bexcluded\s+\d+%\s+of\s+(?:participants?|randomi[sz]ed)\b"]},
    "selective_reporting": {"label": "选择性报告与方案一致性", "category": "偏倚风险", "groups": {
        "protocol": [r"\b(?:NCT\d{8}|ISRCTN\d+|ChiCTR\w+|OSF\s+registration|PROSPERO\s+CRD\w+)\b", r"\bpre[- ]registered\b", r"\bregistered\s+protocol\b"],
        "outcomes": [r"\ball\s+pre[- ]specified\s+outcomes\s+(?:were|are)\s+reported\b", r"\bprotocol[- ]defined\s+outcomes\s+(?:were|are)\s+reported\b", r"\breporting\s+followed\s+the\s+registered\s+protocol\b"]},
        "concerns": [r"\boutcome\s+(?:was\s+)?changed\s+after\b", r"\bpost[- ]hoc\s+outcome\b", r"\bselective(?:ly)?\s+reported\b"]},
    "statistical_analysis": {"label": "统计方法与不确定性", "category": "证据充分性", "groups": {
        "method": [r"\b(?:linear|logistic|Cox|mixed[- ]effects?)\s+regression\b", r"\b(?:t[- ]test|Mann[- ]Whitney|chi[- ]square|ANOVA|Kruskal[- ]Wallis)\b", r"\bstatistical\s+analysis\b", r"\bmeta[- ]analysis\b"],
        "uncertainty": [r"\b95%\s*(?:confidence\s+interval|CI)\b", r"\bconfidence\s+intervals?\b", r"\bstandard\s+(?:error|deviation)\b", r"\bcredible\s+interval\b"],
        "effect": [r"\beffect\s+size\b", r"\bodds\s+ratio\b", r"\brisk\s+ratio\b", r"\bhazard\s+ratio\b", r"\bmean\s+difference\b", r"\bβ\s*="]},
        "concerns": [r"\bonly\s+p[- ]values?\s+(?:are|were)\s+reported\b", r"\bno\s+adjustment\s+for\s+multipl(?:e|icity)\b", r"\bpost[- ]hoc\s+subgroup\s+analysis\b"]},
    "conclusion_consistency": {"label": "结果与结论一致性", "category": "证据充分性", "groups": {
        "results": [r"\bresults?\s*:", r"\bwe\s+(?:found|observed)\b", r"\bthe\s+(?:effect|estimate|odds\s+ratio|hazard\s+ratio)\s+was\b", r"结果\s*[:：]"],
        "conclusion": [r"\bconclusions?\s*:", r"\bwe\s+conclude\b", r"\bin\s+conclusion\b", r"结论\s*[:：]"]},
        "concerns": []},
    "reproducibility": {"label": "可复现性与开放材料", "category": "报告完整性", "groups": {
        "materials": [r"\bdata\s+(?:and\s+code\s+)?availability\b", r"\bcode\s+(?:is|was)\s+available\b", r"\bgithub\.com/[\w./-]+", r"\bzenodo\b", r"\bOSF\b", r"数据可用性"],
        "computational": [r"\bsoftware\s+version\b", r"\bPython\s+\d", r"\bR\s+version\s+\d", r"\brandom\s+seed\b", r"\bhardware\s+(?:was|is)\b", r"\bpackage\s+versions?\b"]},
        "concerns": [r"\bdata\s+available\s+(?:only\s+)?upon\s+request\b", r"\bcode\s+available\s+(?:only\s+)?upon\s+request\b"]},
    "reporting_completeness": {"label": "局限、伦理与利益冲突报告", "category": "报告完整性", "groups": {
        "limitations": [r"\blimitations?\s*:", r"\b(?:this|our)\s+study\s+(?:has|had)\s+(?:several\s+)?limitations\b", r"局限性\s*[:：]"],
        "ethics": [r"\bethics\s+(?:committee|approval)\b", r"\binstitutional\s+review\s+board\b", r"\binformed\s+consent\b", r"\bnot\s+applicable\s+.*ethics\b", r"伦理(?:委员会|审批)"],
        "conflicts": [r"\bconflicts?\s+of\s+interest\b", r"\bcompeting\s+interests?\b", r"\bfunding\s*:", r"\bno\s+funding\b", r"利益冲突"]},
        "concerns": [r"\bundeclared\s+conflicts?\s+of\s+interest\b"]},
    "source_quality": {"label": "来源、版本与出版状态", "category": "来源质量", "groups": {}},
    # Systematic reviews / meta-analyses.
    "review_search": {"label": "综述检索覆盖", "category": "偏倚风险", "groups": {
        "search": [r"\b(?:MEDLINE|PubMed|Embase|Web of Science|Scopus|Cochrane)\b", r"\bsearch\s+strategy\b", r"\bsearch\s+dates?\b"]},
        "concerns": [r"\bsingle\s+database\s+only\b"]},
    "review_selection": {"label": "综述筛选与提取", "category": "偏倚风险", "groups": {
        "dual": [r"\btwo\s+reviewers\s+independently\b", r"\bdual\s+(?:screening|extraction)\b", r"\bdisagreements\s+were\s+resolved\b"]},
        "concerns": [r"\bsingle\s+reviewer\s+(?:screening|extraction)\b"]},
    "publication_bias": {"label": "发表偏倚与异质性", "category": "偏倚风险", "groups": {
        "assessment": [r"\bfunnel\s+plot\b", r"\bEgger(?:'s)?\s+test\b", r"\bpublication\s+bias\s+was\s+assessed\b", r"\bI[²2]\s*=", r"\bheterogeneity\s+was\s+assessed\b"]},
        "concerns": [r"\bsubstantial\s+heterogeneity\b", r"\bpublication\s+bias\s+(?:was\s+)?detected\b"]},
    # Diagnostic studies.
    "reference_standard": {"label": "参考标准", "category": "偏倚风险", "groups": {
        "standard": [r"\breference\s+standard\b", r"\bblinded\s+interpretation\s+of\s+the\s+reference\b"]},
        "concerns": [r"\bincorporation\s+bias\b", r"\bindex\s+test\s+was\s+part\s+of\s+the\s+reference\b"]},
    "patient_flow": {"label": "病例流程与检测间隔", "category": "偏倚风险", "groups": {
        "flow": [r"\ball\s+patients\s+received\s+the\s+reference\s+standard\b", r"\btime\s+interval\s+between\s+index\s+test\b", r"\bpatient\s+flow\b"]},
        "concerns": [r"\bpartial\s+verification\b", r"\bdifferential\s+verification\b"]},
    # Qualitative studies.
    "reflexivity": {"label": "研究者反思性", "category": "偏倚风险", "groups": {
        "reflexivity": [r"\breflexiv(?:ity|e)\b", r"\bresearcher\s+positionality\b", r"\breflexive\s+journal\b"]},
        "concerns": []},
    "qualitative_rigour": {"label": "质性分析严谨性", "category": "证据充分性", "groups": {
        "rigour": [r"\btwo\s+researchers\s+independently\s+coded\b", r"\btriangulation\b", r"\bmember\s+checking\b", r"\bdata\s+saturation\b", r"\baudit\s+trail\b"]},
        "concerns": []},
    # Computational studies.
    "validation_leakage": {"label": "验证设计与数据泄漏", "category": "偏倚风险", "groups": {
        "validation": [r"\bexternal\s+validation\b", r"\bheld[- ]out\s+test\s+set\b", r"\bpatient[- ]level\s+split\b", r"\bnested\s+cross[- ]validation\b", r"\bdata\s+leakage\s+was\s+prevented\b"]},
        "concerns": [r"\brandom\s+row[- ]level\s+split\b", r"\btest\s+set\s+was\s+used\s+for\s+(?:training|tuning|feature\s+selection)\b", r"\bdata\s+leakage\b"]},
    "baselines": {"label": "基线与公平比较", "category": "证据充分性", "groups": {
        "baselines": [r"\bbaselines?\b", r"\bablation\b", r"\bsame\s+(?:training\s+data|compute\s+budget|evaluation\s+protocol)\b"]},
        "concerns": [r"\bno\s+baseline\b", r"\bunfair\s+comparison\b"]},
}

BASE_DOMAINS = ["design_identification", "sample_data", "outcomes_measurement", "methods_transparency",
                "statistical_analysis", "conclusion_consistency", "reproducibility", "reporting_completeness",
                "source_quality", "selective_reporting"]
DESIGN_DOMAINS = {
    "randomized_trial": ["random_sequence", "allocation_concealment", "blinding", "missing_data"],
    "nonrandomized_intervention": ["confounding", "selection_bias", "comparator", "blinding", "missing_data"],
    "cohort": ["confounding", "selection_bias", "comparator", "missing_data"],
    "case_control": ["confounding", "selection_bias", "comparator", "missing_data"],
    "cross_sectional": ["confounding", "selection_bias", "missing_data"],
    "systematic_review": ["review_search", "review_selection", "publication_bias"],
    "diagnostic_accuracy": ["selection_bias", "reference_standard", "patient_flow", "blinding"],
    "qualitative": ["selection_bias", "reflexivity", "qualitative_rigour"],
    "computational": ["validation_leakage", "baselines", "missing_data"],
    "protocol": [],
    "unknown": ["selection_bias", "missing_data"],
}
CORE_BIAS = {"random_sequence", "allocation_concealment", "blinding", "confounding", "selection_bias",
             "comparator", "missing_data", "selective_reporting", "review_search", "review_selection",
             "publication_bias", "reference_standard", "patient_flow", "reflexivity", "validation_leakage"}


def _units(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc.get("units") or []


def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    left_candidates = [text.rfind(mark, 0, start) for mark in ("\n", ". ", "! ", "? ", "。", "！", "？")]
    left = max(left_candidates)
    s = left + (2 if left >= 0 and text[left:left + 2] in (". ", "! ", "? ") else 1) if left >= 0 else 0
    stops = [p for p in (text.find(". ", end), text.find("! ", end), text.find("? ", end),
                         text.find("\n", end), text.find("。", end), text.find("！", end), text.find("？", end)) if p >= 0]
    if not stops:
        e = len(text)
    else:
        e0 = min(stops)
        e = e0 + (1 if text[e0:e0 + 1] in ("。", "！", "？") else 1)
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


def _evidence(doc: dict[str, Any], unit: dict[str, Any], match: re.Match[str], dimension: str,
              kind: str = "reported") -> dict[str, Any]:
    text = unit["text"]
    s, e = _sentence_span(text, match.start(), match.end())
    quote = text[s:e]
    locator = dict(unit.get("locator") or {})
    locator.update({"start": s, "end": e, "quote": quote})
    digest = hashlib.sha256((doc["doc_id"] + "|" + dimension + "|" + kind + "|" + str(locator.get("source_path", ""))
                             + "|" + str(s) + "|" + quote).encode("utf-8")).hexdigest()[:16]
    return {"evidence_id": digest, "dimension": dimension, "kind": kind, "quote": quote,
            "locator": locator, "match": match.group(0),
            "verification": "quote == source_text[start:end] for text units; exact field value for structured units"}


def _find(doc: dict[str, Any], patterns: list[str], dimension: str, kind: str = "reported") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for pattern in patterns:
        rx = re.compile(pattern, re.I)
        for unit in _units(doc):
            for match in rx.finditer(unit.get("text", "")):
                prefix = unit["text"][max(0, match.start() - 28):match.start()]
                if kind == "reported" and NEGATIVE.search(prefix):
                    continue
                loc = unit.get("locator") or {}
                key = (str(loc.get("source_path", "")), match.start(), match.end())
                if key in seen:
                    continue
                seen.add(key)
                found.append(_evidence(doc, unit, match, dimension, kind))
    return found


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, seen = [], set()
    for item in items:
        key = item.get("evidence_id") or (item.get("quote"), json.dumps(item.get("locator"), sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _metadata_evidence(doc: dict[str, Any], fields: list[str], dimension: str) -> list[dict[str, Any]]:
    out = []
    for unit in _units(doc):
        path = str((unit.get("locator") or {}).get("source_path", ""))
        if any(path == f or path.endswith("." + f) for f in fields):
            text = unit.get("text", "")
            if not text:
                continue
            match = re.match(r"[\s\S]*", text)
            out.append(_evidence(doc, unit, match, dimension))
    return out


def identify_design(doc: dict[str, Any]) -> dict[str, Any]:
    explicit = doc.get("metadata", {}).get("design")
    explicit = str(explicit or "").strip()
    candidates = []
    design_doc = dict(doc)
    design_doc["units"] = [u for u in _units(doc)
                           if str((u.get("locator") or {}).get("source_path", "")).split("[")[0]
                           not in {"doi", "DOI", "pmid", "url", "source", "version", "source_version"}]
    for design, pattern in DESIGN_PATTERNS:
        ev = _find(design_doc, [pattern], "design_identification")
        if ev:
            candidates.append((design, ev))
    # A declared structured design is evidence too.  Keep it alongside textual
    # evidence so a metadata/text conflict is visible instead of silently won.
    if explicit:
        normalized = explicit.lower().replace("_", " ").replace("-", " ")
        aliases = {"rct": "randomized_trial", "randomised trial": "randomized_trial",
                   "randomized trial": "randomized_trial", "meta analysis": "systematic_review"}
        explicit_design = aliases.get(normalized)
        if explicit_design is None:
            explicit_design = next((d for d in DESIGN_DOMAINS if d.replace("_", " ") in normalized), None)
        if explicit_design:
            ev = _metadata_evidence(doc, ["design", "study_design", "publication_type", "pubType"], "design_identification")
            for pos, (design, existing) in enumerate(candidates):
                if design == explicit_design:
                    candidates[pos] = (design, _dedupe(existing + ev))
                    break
            else:
                candidates.append((explicit_design, ev))
    if not candidates:
        return {"design": "unknown", "evidence": [], "conflict": False,
                "note": "Study design is not identifiable from supplied evidence; generic bias checks are used."}
    order = [d for d, _ in candidates]
    # Specific diagnostic/systematic labels beat incidental words such as RCT in references.
    chosen = candidates[0]
    for preferred in ("diagnostic_accuracy", "systematic_review", "protocol"):
        if preferred in order:
            chosen = candidates[order.index(preferred)]
            break
    conflict = len({d for d, _ in candidates}) > 1
    return {"design": chosen[0], "evidence": _dedupe([e for _, ev in candidates for e in ev]),
            "conflict": conflict, "alternative_designs": sorted(set(order) - {chosen[0]}),
            "note": "Design label is evidence-anchored; applicability of checklist domains follows this label."}


def _statistical_contradictions(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Only numeric/text contradictions in the SAME sentence are flagged."""
    out = []
    patterns = [r"\bp\s*(?:=|<|>)\s*0?\.\d+\b", r"\bp\s*(?:=|<|>)\s*1\.0+\b"]
    for ev in _find(doc, patterns, "statistical_analysis"):
        quote = ev["quote"]
        pm = re.search(r"\bp\s*(=|<|>)\s*(0?\.\d+|1\.0+)\b", quote, re.I)
        if not pm:
            continue
        op, value = pm.group(1), float(pm.group(2))
        significant = (op == "<" and value >= 0.05) or (op == "=" and value < 0.05) or (op == ">" and value < 0.05)
        if op == ">" and value >= 0.05:
            significant = False
        says_not = bool(re.search(r"\b(?:not|no)\s+(?:statistically\s+)?significant\b|\bnon[- ]significant\b", quote, re.I))
        says_sig = bool(re.search(r"\bstatistically\s+significant\b", quote, re.I)) and not says_not
        if (significant and says_not) or ((not significant) and says_sig and op in ("=", ">")):
            item = dict(ev)
            item["kind"] = "contradiction"
            item["explanation"] = f"p {op} {value:g} conflicts with the significance wording in the same sentence"
            out.append(item)
    return out


def _causal_overreach(doc: dict[str, Any], design: str) -> list[dict[str, Any]]:
    if design in {"randomized_trial", "systematic_review", "unknown", "protocol"}:
        return []
    out = []
    for pattern in (r"\bconclusions?\s*:[^\n.]*\b(?:caused|causes|led to|prevents?|eliminates?)\b",
                    r"\bwe\s+conclude\s+that\s+[^\n.]*\b(?:caused|causes|prevents?|eliminates?)\b"):
        for ev in _find(doc, [pattern], "conclusion_consistency", "contradiction"):
            ev["explanation"] = f"Causal conclusion requires separate justification for design '{design}'"
            out.append(ev)
    return out


def _attrition_concerns(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for ev in _find(doc, [r"\b(?:attrition|drop[- ]?out|lost\s+to\s+follow[- ]up)\s+(?:rate\s+)?(?:was\s+)?(\d+(?:\.\d+)?)\s*%"], "missing_data", "numeric_concern"):
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", ev["quote"])
        if m and float(m.group(1)) > 20:
            ev["explanation"] = "Attrition exceeds the declared 20% review threshold; direction and arm balance still need review"
            out.append(ev)
    return out


def _row(doc: dict[str, Any], domain: str, design_info: dict[str, Any]) -> dict[str, Any]:
    rule = RULES[domain]
    row: dict[str, Any] = {"dimension": domain, "dimension_label": rule["label"],
                           "category": rule["category"], "judgement": "insufficient",
                           "reason": "", "evidence": [], "review_required": True}
    if domain == "design_identification":
        row["evidence"] = design_info["evidence"]
        if design_info["design"] == "unknown":
            row["reason"] = "No explicit design statement was located; checklist selection is uncertain."
        elif design_info.get("conflict"):
            row["judgement"] = "some_concerns"
            row["reason"] = "Multiple design labels occur; alternatives are retained for reviewer adjudication."
        else:
            row["judgement"] = "low"
            row["review_required"] = False
            row["reason"] = "An explicit design statement was located; this supports identification, not adequacy by itself."
        return row
    if domain == "source_quality":
        md = doc.get("metadata", {})
        ev = _metadata_evidence(doc, ["title", "DOI", "doi", "journal", "container-title", "publisher",
                                      "source", "source_type", "version", "publication_status", "retracted"], domain)
        row["evidence"] = ev
        if str(md.get("retracted", "")).lower() in {"true", "yes", "retracted", "1"}:
            row.update(judgement="high", reason="The supplied record declares retraction; do not treat the work as dependable evidence.")
        elif str(md.get("publication_status", "")).lower() == "preprint" or md.get("subtype") == "preprint":
            row.update(judgement="some_concerns", reason="Preprint status is explicit; peer-review and version status are not inferred.")
        elif doc.get("abstract_only"):
            row.update(judgement="insufficient", reason="Only abstract/metadata evidence is available; source identity does not establish full reporting quality.")
        elif md.get("title") and (md.get("doi") or md.get("pmid") or md.get("source")):
            row.update(judgement="low", review_required=False,
                       reason="Title and a persistent/source identifier are present. This is traceability, not a journal-quality score.")
        else:
            row["reason"] = "Title and persistent/source identifiers are incomplete; peer review is unknown unless explicitly stated."
        return row

    evidence, concerns, missing = [], [], []
    for group, patterns in rule.get("groups", {}).items():
        ev = _find(doc, patterns, domain)
        evidence.extend((group, item) for item in ev)
    concern_ev = _find(doc, rule.get("concerns", []), domain, "concern")
    concerns.extend(concern_ev)
    missing_ev = _find(doc, [MISSING.pattern], domain, "absence_statement")
    # Keep only absence statements semantically near a domain keyword, not every
    # unrelated "not reported" sentence in a paper.
    domain_words = {
        "random_sequence": r"random|sequence|allocation", "allocation_concealment": r"allocation|conceal",
        "blinding": r"blind|mask", "sample_data": r"sample|power|sampling", "outcomes_measurement": r"outcome|measure|follow",
        "methods_transparency": r"method|procedure|protocol", "confounding": r"confound|adjust", "selection_bias": r"selection|sampling",
        "comparator": r"control|comparator", "missing_data": r"missing|attrition|drop|follow", "selective_reporting": r"protocol|register|outcome",
        "statistical_analysis": r"statistic|analysis|confidence|p[- ]value", "conclusion_consistency": r"result|conclusion",
        "reproducibility": r"data|code|software|material", "reporting_completeness": r"limitation|ethic|consent|conflict|funding",
        "review_search": r"search|database", "review_selection": r"screen|reviewer|extract", "publication_bias": r"bias|heterogeneity",
        "reference_standard": r"reference|standard", "patient_flow": r"flow|verification|interval", "reflexivity": r"reflex|position",
        "qualitative_rigour": r"coding|saturation|triangulation", "validation_leakage": r"validation|split|leakage", "baselines": r"baseline|ablation",
    }.get(domain, r"$^")
    missing = [e for e in missing_ev if re.search(domain_words, e["quote"], re.I)]
    if domain == "statistical_analysis":
        concerns.extend(_statistical_contradictions(doc))
    if domain == "conclusion_consistency":
        concerns.extend(_causal_overreach(doc, design_info["design"]))
    if domain == "missing_data":
        concerns.extend(_attrition_concerns(doc))

    group_status = {}
    for group in rule.get("groups", {}):
        group_status[group] = any(g == group for g, _ in evidence)
    all_evidence = _dedupe([e for _, e in evidence] + concerns + missing)
    row["evidence"] = all_evidence
    row["evidence_group_coverage"] = group_status
    high = any(e.get("kind") == "contradiction" for e in concerns)
    if high:
        row.update(judgement="high", reason="A direct statistical/design contradiction is anchored below; substantive review is required.")
    elif concerns:
        numeric_high = any(e.get("kind") == "numeric_concern" and "exceeds" in e.get("explanation", "") for e in concerns)
        row.update(judgement="some_concerns", reason=("A declared numeric threshold was crossed; " if numeric_high else "") +
                   "Explicit concern evidence is present; missing evidence is not treated as proof of bias.")
    elif missing or not all(group_status.values()):
        absent = [g for g, ok in group_status.items() if not ok]
        row.update(judgement="insufficient", reason="Evidence is incomplete for required group(s): " + (", ".join(absent) if absent else "unclear report") + ". Abstaining rather than inferring low/high risk.")
    else:
        row.update(judgement="low", review_required=False,
                   reason="All declared evidence groups are present and no concern pattern was located. Human review can still overturn this reporting-based judgement.")
    return row


def _domains_for(design: str) -> list[str]:
    domains = list(BASE_DOMAINS)
    for item in DESIGN_DOMAINS.get(design, DESIGN_DOMAINS["unknown"]):
        if item not in domains:
            domains.append(item)
    # Protocols have no results to appraise yet.
    if design == "protocol":
        for item in ("outcomes_measurement", "statistical_analysis", "conclusion_consistency", "selective_reporting"):
            if item in domains:
                domains.remove(item)
    return domains


def _overall(rows: list[dict[str, Any]], abstract_only: bool, design: str) -> dict[str, Any]:
    applicable = [r for r in rows if r["judgement"] != "not_applicable" and r["dimension"] != "source_quality"]
    if design == "protocol":
        return {"grade": "insufficient", "reason": "A protocol cannot establish outcome, analysis or conclusion quality before results are available.",
                "aggregation": "protocols abstain on study-result quality"}
    if abstract_only:
        return {"grade": "insufficient", "reason": "Abstract-only coverage is insufficient for a full risk-of-bias judgement.",
                "aggregation": "abstract-only forces overall abstention"}
    high = [r["dimension"] for r in applicable if r["judgement"] == "high"]
    some = [r["dimension"] for r in applicable if r["judgement"] == "some_concerns"]
    missing = [r["dimension"] for r in applicable if r["judgement"] == "insufficient"]
    if high:
        grade, reason = "high", "At least one applicable domain has direct high-concern/contradictory evidence: " + ", ".join(high)
    elif some:
        grade, reason = "some_concerns", "At least one domain has explicit concern evidence: " + ", ".join(some)
    elif missing:
        grade, reason = "insufficient", "No direct high/some concern was located, but required evidence is missing: " + ", ".join(missing)
    else:
        grade, reason = "low", "Every applicable domain met the declared reporting-evidence rule; this remains reviewer-assisted, not peer review."
    return {"grade": grade, "reason": reason, "high_domains": high, "concern_domains": some,
            "insufficient_domains": missing,
            "aggregation": "high if any high; else some_concerns if any some; else insufficient if any required domain lacks evidence; low only when all applicable domains are low"}


def _apply_reviews(doc_result: dict[str, Any], decisions: Any) -> list[dict[str, Any]]:
    changes = []
    if not isinstance(decisions, list):
        return changes
    rows = {r["dimension"]: r for r in doc_result["quality_table"]}
    valid_ids = {e["evidence_id"] for r in doc_result["quality_table"] for e in r["evidence"]}
    for i, decision in enumerate(decisions):
        if not isinstance(decision, dict) or decision.get("doc_id") != doc_result["doc_id"]:
            continue
        dim = decision.get("dimension")
        judgement = decision.get("judgement")
        reviewer = str(decision.get("reviewer") or "").strip()
        rationale = str(decision.get("rationale") or "").strip()
        if dim not in rows or judgement not in JUDGEMENTS or not reviewer or not rationale:
            continue
        cited = decision.get("evidence_ids") or []
        if not isinstance(cited, list) or any(x not in valid_ids for x in cited):
            continue
        before = rows[dim]["judgement"]
        rows[dim]["engine_judgement"] = before
        rows[dim]["judgement"] = judgement
        rows[dim]["review_required"] = False
        rows[dim]["review_decision"] = {"reviewer": reviewer, "rationale": rationale, "evidence_ids": cited}
        changes.append({"operation": "manual_review", "doc_id": doc_result["doc_id"], "dimension": dim,
                        "before": before, "after": judgement, "reviewer": reviewer, "rationale": rationale,
                        "decision_index": i})
    doc_result["overall"] = _overall(doc_result["quality_table"], doc_result["coverage"] == "abstract_only",
                                     doc_result["design"]["design"])
    return changes


def appraise_document(doc: dict[str, Any], decisions: Any = None) -> dict[str, Any]:
    design = identify_design(doc)
    domains = _domains_for(design["design"])
    rows = [_row(doc, d, design) for d in domains]
    coverage = "abstract_only" if doc.get("abstract_only") else ("full_text" if doc.get("full_text_available") else "provided_excerpt")
    result = {"doc_id": doc["doc_id"], "metadata": doc.get("metadata", {}), "design": design,
              "coverage": coverage, "quality_table": rows,
              "overall": _overall(rows, doc.get("abstract_only", False), design["design"]),
              "review_queue": [{"dimension": r["dimension"], "reason": r["reason"],
                                "evidence_ids": [e["evidence_id"] for e in r["evidence"]]}
                               for r in rows if r.get("review_required")],
              "source": doc.get("source", {})}
    changes = _apply_reviews(result, decisions)
    if changes:
        result["change_records"] = changes
    return result


def appraise(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("appraisal spec must be an object")
    docs = spec.get("normalized_documents")
    if not isinstance(docs, list) or not docs:
        raise ValueError("no normalized documents were supplied")
    decisions = spec.get("review_decisions") or []
    appraisals = [appraise_document(doc, decisions) for doc in docs]
    findings = []
    for doc, app in zip(docs, appraisals):
        if app["coverage"] != "full_text":
            findings.append({"rule": "quality.full_text_unavailable", "severity": "medium", "doc_id": doc["doc_id"],
                             "coverage": app["coverage"], "message": "Full-text-dependent domains remain insufficient."})
        if app["design"]["design"] == "unknown":
            findings.append({"rule": "quality.design_unknown", "severity": "medium", "doc_id": doc["doc_id"]})
        if app["design"].get("conflict"):
            findings.append({"rule": "quality.design_conflict", "severity": "medium", "doc_id": doc["doc_id"],
                             "alternatives": app["design"].get("alternative_designs", [])})
        if app["overall"]["grade"] != "low":
            findings.append({"rule": "quality.review_required", "severity": "medium", "doc_id": doc["doc_id"],
                             "grade": app["overall"]["grade"], "open_items": len(app["review_queue"])})
        for row in app["quality_table"]:
            if row["judgement"] == "high":
                findings.append({"rule": "quality.domain_high", "severity": "high", "doc_id": doc["doc_id"],
                                 "dimension": row["dimension"]})
    status = "clean" if not any(f["severity"] in {"medium", "high"} for f in findings) else "review"
    rubric = {"version": RUBRIC_VERSION, "judgements": sorted(JUDGEMENTS),
              "domain_definitions": {k: {"label": v["label"], "category": v["category"],
                                           "required_evidence_groups": sorted(v.get("groups", {}))}
                                     for k, v in RULES.items()},
              "design_domain_map": DESIGN_DOMAINS,
              "aggregation": "Domain rules require every evidence group for low; explicit concerns -> some; direct contradictions -> high; missing -> insufficient. Overall uses high > some > insufficient > low and abstract-only abstains.",
              "human_review": "review_decisions require doc_id, dimension, valid judgement, reviewer, rationale and only valid evidence_ids; original engine judgement is retained."}
    return {"schema_version": SCHEMA_VERSION, "status": status, "appraisals": appraisals,
            "findings": findings, "rubric_definition": rubric,
            "uncertainty": [{"doc_id": a["doc_id"], "coverage": a["coverage"],
                             "overall_grade": a["overall"]["grade"], "reason": a["overall"]["reason"]}
                            for a in appraisals],
            "limits": []}

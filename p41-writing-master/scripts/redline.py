"""Sentence-level redline between an original text and an edited one.

Reports only what can be established mechanically: this quantity vanished, that
citation was dropped, this claim got stronger, that term drifted. It does not
say whether the edit is good prose — that is the caller's judgement, and the
report is built so a human can overrule every line.

The alignment is a monotonic DP over sentence pairs scored by string
similarity, which tolerates rewriting (a sentence can be reworded and still
align) without allowing reordering that would fabricate correspondences.
"""

from __future__ import annotations

import difflib
from collections import Counter

import guard as G

GAP = 0.35          # cost of leaving a sentence unpaired
MIN_PAIR = 0.30     # below this similarity, pair as "replaced" rather than "edited"
HEAVY_REWRITE = 1.8  # edited/original length ratio that breaks minimal-edit


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def align(orig: list[str], edited: list[str]) -> list[tuple[int, int]]:
    """Monotonic pairing maximising total similarity.

    Returns (orig_index, edited_index) pairs. Unpaired sentences appear in
    neither index, which is how deletions and insertions are found.
    """
    n, m = len(orig), len(edited)
    if not n or not m:
        return []
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]  # 0=diag 1=up 2=left

    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0]
        back[i][0] = 1
    for j in range(1, m + 1):
        score[0][j] = score[0][j - 1]
        back[0][j] = 2

    sim = [[similarity(orig[i - 1], edited[j - 1]) for j in range(1, m + 1)] for i in range(1, n + 1)]

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = score[i - 1][j - 1] + (sim[i - 1][j - 1] if sim[i - 1][j - 1] >= MIN_PAIR else -GAP)
            up = score[i - 1][j] - GAP
            left = score[i][j - 1] - GAP
            best = max(diag, up, left)
            score[i][j] = best
            back[i][j] = 0 if best == diag else (1 if best == up else 2)

    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        b = back[i][j]
        if b == 0 and sim[i - 1][j - 1] >= MIN_PAIR:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif b == 1:
            i -= 1
        else:
            j -= 1
    return list(reversed(pairs))


def _multiset_delta(before: list, after: list) -> tuple[list, list]:
    cb, ca = Counter(before), Counter(after)
    missing = list((cb - ca).elements())
    added = list((ca - cb).elements())
    return missing, added


def _qkey(q: G.Quantity) -> tuple:
    return (round(q.value, 9), q.unit or "")


def compare_texts(orig_text: str, edited_text: str, glossary: G.Glossary | None = None) -> dict:
    """Full redline report for one pair of texts."""
    orig_sents = G.split_sentences(orig_text)
    new_sents = G.split_sentences(edited_text)
    pairs = align(orig_sents, new_sents)
    paired_o = {i for i, _ in pairs}
    paired_n = {j for _, j in pairs}

    findings: list[dict] = []
    changes: list[dict] = []

    def add(rule: str, severity: str, message: str, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    for i, j in pairs:
        o, n = orig_sents[i], new_sents[j]

        # --- quantities -----------------------------------------------------
        ob = [_qkey(q) for q in G.extract_quantities(o)]
        nb = [_qkey(q) for q in G.extract_quantities(n)]
        missing, added = _multiset_delta(ob, nb)
        if missing:
            add("quantity.dropped", "high",
                f"{len(missing)} quantity value(s) present in the original are absent from the edit",
                sentence_index=j, original=o, edited=n, dropped=[list(x) for x in missing])
        if added:
            add("quantity.introduced", "high",
                f"{len(added)} quantity value(s) appear in the edit that were not in the original",
                sentence_index=j, original=o, edited=n, added=[list(x) for x in added])

        # --- citations ------------------------------------------------------
        oc, nc = G.extract_citations(o), G.extract_citations(n)
        c_missing, c_added = _multiset_delta(oc, nc)
        if c_missing:
            add("citation.dropped", "high",
                "a citation marker present in the original is missing from the edit",
                sentence_index=j, original=o, edited=n, dropped=c_missing)
        if c_added:
            add("citation.introduced", "medium",
                "the edit adds a citation marker that the original did not have",
                sentence_index=j, original=o, edited=n, added=c_added)

        # --- glossary-locked terms: a polish that swaps the locked form is drift ----
        if glossary is not None:
            for concept, entry in glossary.concepts.items():
                pref = str((entry or {}).get("preferred") or "").strip()
                src_form = str((entry or {}).get("source_form") or concept).strip()
                if not pref or not src_form:
                    continue
                abbrev = str((entry or {}).get("abbreviation") or "").strip()
                if src_form and src_form in o:
                    escapes = [pref, abbrev, src_form]
                    if not any(e and e in n for e in escapes if e):
                        add("term.drift", "medium",
                            "a glossary-locked term was present in the original sentence, but "
                            "the edit replaced it with a form the glossary does not allow",
                            sentence_index=j, concept=concept, locked=pref,
                            original=o[:80], edited=n[:80])

        # --- cross references ----------------------------------------------
        o_x, n_x = G.extract_xrefs(o), G.extract_xrefs(n)
        x_missing, x_added = _multiset_delta(o_x, n_x)
        if x_missing:
            add("xref.dropped", "medium",
                "a figure/table/equation reference was lost",
                sentence_index=j, original=o, edited=n, dropped=x_missing)
        if x_added:
            add("xref.introduced", "medium",
                "the edit points at a figure/table/equation the original did not",
                sentence_index=j, original=o, edited=n, added=x_added)

        # --- claim strength -------------------------------------------------
        so, sn = G.claim_strength(o), G.claim_strength(n)
        if sn > so:
            add("claim.strengthened", "high",
                f"claim strength rose from level {so} to {sn}",
                sentence_index=j, original=o, edited=n,
                absolute_terms=G.strengtheners(n))
        elif sn < so:
            add("claim.weakened", "medium",
                f"claim strength fell from level {so} to {sn}",
                sentence_index=j, original=o, edited=n)

        # --- minimal edit ---------------------------------------------------
        if len(o) >= 20:
            ratio = len(n) / len(o)
            if ratio >= HEAVY_REWRITE or ratio <= 1 / HEAVY_REWRITE:
                add("edit.heavy_rewrite", "low",
                    f"length changed by a factor of {ratio:.2f}; minimal-edit principle suggests "
                    "justifying this sentence in the change log",
                    sentence_index=j, original=o, edited=n)

        if o != n:
            changes.append({
                "sentence_index": j,
                "change_type": _change_type(o, n),
                "original": o,
                "edited": n,
                "rule_ids": sorted({f["rule"] for f in findings if f.get("sentence_index") == j}),
            })

    for i, s in enumerate(orig_sents):
        if i not in paired_o:
            add("sentence.removed", "high", "a sentence of the original has no counterpart in the edit",
                sentence_index=None, original=s)
    for j, s in enumerate(new_sents):
        if j not in paired_n:
            add("sentence.added", "medium", "the edit adds a sentence with no counterpart in the original",
                sentence_index=j, edited=s)

    if glossary is not None:
        for f in G.check_terms(edited_text, glossary):
            f["severity"] = "medium"
            findings.append(f)
        for f in G.check_first_mention(edited_text, glossary):
            f["severity"] = "low"
            findings.append(f)

    counts = Counter(f["severity"] for f in findings)
    return {
        "schema_version": "editguard/v1",
        "sentences_original": len(orig_sents),
        "sentences_edited": len(new_sents),
        "sentences_paired": len(pairs),
        "sentence_reordering_detected": _reordered(pairs),
        "findings": findings,
        "severity_counts": dict(counts),
        "changes": changes,
        "status": ("clean" if not findings else
                   "blocking" if counts.get("high") else "review"),
    }


def _change_type(o: str, n: str) -> str:
    """A coarse label for the change log. Deliberately mechanical, not literary."""
    if not any(c.isalnum() for c in n):
        return "deletion"
    if G.extract_quantities(o) != G.extract_quantities(n):
        return "value-edit"
    if len(n) > len(o) * 1.25:
        return "expansion"
    if len(n) < len(o) * 0.75:
        return "condensation"
    return "wording"


def _reordered(pairs: list[tuple[int, int]]) -> bool:
    return any(pairs[k][1] > pairs[k + 1][1] for k in range(len(pairs) - 1))

"""Formula / Greek-letter / script-character fidelity for pdf-parse.

Detects lines that contain mathematical content (Greek, subscripts, superscripts,
common operators) and marks them as formula blocks. Keeps the raw unicode form
verbatim (so Δ, χ, β_0, x² are not silently renamed), records a UTF-8 sha of the
verbatim string, and flags lines whose characters would not round-trip through
cp1252 (lossy for some legacy pipelines) as a finding.
"""
from __future__ import annotations

import hashlib
import re

GREEK = "αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΧΨΩμ"
MATH_CHARS = set(GREEK + "±±×·÷≈≡≠≈≠≤≥∈∉∑∏∫∮∂∇∝∞√∧∨¬∀∃↔→←↑↓")
SUPERSCRIPT = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿⁱᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐⁿᵒʳˢᵗ"
SUBSCRIPT = "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₔ"


def is_formula(text: str) -> bool:
    if not text or len(text.strip()) < 2:
        return False
    greek = sum(1 for ch in text if ch in MATH_CHARS)
    subs = sum(1 for ch in text if ch in SUPERSCRIPT + SUBSCRIPT)
    has_eq = "=" in text or "≈" in text or "≃" in text
    return (greek + subs) > 0 or (has_eq and len(text) < 200)


def mark_formulas(blocks: list[dict]) -> list[dict]:
    """Mark formula blocks and append warnings where round-trip is unsafe."""
    for b in blocks:
        text = b.get("text", "")
        if not text:
            continue
        if is_formula(text):
            b["kind"] = "formula"
            b["formula_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            b["greek_count"] = sum(1 for ch in text if ch in MATH_CHARS)
            try:
                text.encode("cp1252")
            except UnicodeEncodeError:
                b.setdefault("warnings", []).append(
                    "contains characters outside cp1252 (likely math/symbols) — preserve UTF-8")
    return blocks


def count_by_kind(blocks: list[dict]) -> dict:
    kinds: dict[str, int] = {}
    for b in blocks:
        k = b.get("kind", "paragraph")
        kinds[k] = kinds.get(k, 0) + 1
    return kinds

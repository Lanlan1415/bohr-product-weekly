"""Verbatim Unicode formula and sub/superscript extraction (no invented LaTeX)."""
from __future__ import annotations

import hashlib
import re
from typing import Any

GREEK = "αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΧΨΩμ"
MATH_CHARS = set(GREEK + "±×·÷≈≡≠≤≥∈∉∑∏∫∮∂∇∝∞√∧∨¬∀∃↔→←↑↓")
SUPERSCRIPT = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿⁱᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐⁿᵒʳˢᵗ"
SUBSCRIPT = "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₔ"
SKIP = {"title", "authors", "authors_candidate", "affiliation", "heading", "header_footer",
        "figure_caption", "table_caption", "reference", "footnote", "figure", "scanned_page"}


def is_formula(text: str) -> bool:
    value = text.strip()
    if len(value) < 2:
        return False
    symbol_count = sum(ch in MATH_CHARS or ch in SUPERSCRIPT + SUBSCRIPT for ch in value)
    has_eq = bool(re.search(r"[=≈≡≠≤≥]", value))
    equation_number = bool(re.search(r"\((?:\d+|[A-Z]\d+)\)\s*$", value))
    variable_equation = bool(re.search(r"\b[A-Za-zΑ-Ωα-ω](?:[_^][A-Za-z0-9{}]+)?\s*[=≈≡]", value))
    return (has_eq and (symbol_count > 0 or variable_equation) and len(value) < 600) or \
        (equation_number and (symbol_count > 0 or has_eq)) or \
        (symbol_count >= 2 and has_eq)


def _script_spans(block: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for line in block.get("lines", []) or []:
        for span in line.get("spans", []) or []:
            text = span.get("text", "")
            flag_script = bool(int(span.get("flags", 0)) & 1)
            unicode_script = any(ch in SUPERSCRIPT + SUBSCRIPT for ch in text)
            if flag_script or unicode_script:
                out.append({"text": text, "bbox": span.get("bbox"), "size": span.get("size"),
                            "font": span.get("font"), "flags": span.get("flags"),
                            "basis": "pymupdf-superscript-flag" if flag_script else "unicode-script-codepoint"})
    return out


def mark_formulas(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for b in blocks:
        if not b.get("text") or b.get("kind") in SKIP:
            continue
        scripts = _script_spans(b)
        if scripts:
            b["script_spans"] = scripts
        if is_formula(b["text"]):
            b["kind"] = "formula"
            b["include_in_body"] = True
            b["formula_sha256"] = hashlib.sha256(b["text"].encode("utf-8")).hexdigest()
            number = re.search(r"\((\d+|[A-Z]\d+)\)\s*$", b["text"])
            b["equation_number"] = number.group(1) if number else None
            b["formula_representation"] = "verbatim_unicode"
    return blocks


def extract_formulas(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formulas = []
    for b in blocks:
        if b.get("kind") != "formula":
            continue
        text = b.get("text", "")
        formulas.append({"formula_id": b["block_id"] + "-formula", "text": text,
                         "equation_number": b.get("equation_number"), "locator": b["locator"],
                         "symbols": sorted({ch for ch in text if ch in MATH_CHARS or ch in SUPERSCRIPT + SUBSCRIPT}),
                         "script_spans": b.get("script_spans", []),
                         "unicode_sha256": b.get("formula_sha256"),
                         "latex": None, "structure_status": "verbatim_only_no_latex_inference"})
    return formulas


def count_by_kind(blocks: list[dict[str, Any]]) -> dict[str, int]:
    kinds: dict[str, int] = {}
    for b in blocks:
        k = b.get("kind", "paragraph")
        kinds[k] = kinds.get(k, 0) + 1
    return dict(sorted(kinds.items()))

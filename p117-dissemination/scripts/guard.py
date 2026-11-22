"""Invariant checking for an edited academic text.

The point of this module is narrow and deliberate: it does not know how to
improve prose. It knows how to prove that an edit did not quietly damage the
things a reader relies on — numbers, units, citations, cross-references, hedge
strength, and terminology.

A language model can rewrite a paragraph. It cannot reliably tell you that it
turned "may indicate" into "demonstrates", or that it dropped the one citation
supporting the claim. That is the failure this module exists to catch, and it is
the thing a base agent has no way to check about its own output.

All checks are deterministic and every finding carries the original span, the
edited span and a rule id, so a human can overrule any of them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------

# Chinese and Western sentence terminators. Kept as a character class so a
# mixed-language paragraph splits consistently.
_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*|(?<=[.])\s+(?=[A-Z(\[])")


def normalise(text: str) -> str:
    """NFKC so full-width digits and punctuation compare equal to ASCII."""
    return unicodedata.normalize("NFKC", text)


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(normalise(text)) if p and p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def split_clauses(sentence: str) -> list[str]:
    """Split at commas so a finding can point at the clause, not the sentence."""
    return [c.strip() for c in re.split(r"[,，;；]", sentence) if c.strip()]


# ---------------------------------------------------------------------------
# Numbers, units
# ---------------------------------------------------------------------------

# Units seen in the physics/chemistry/biology literature these tasks draw from.
# Matched longest-first so "mM" wins over "m" and "kPa" over "Pa".
UNITS = [
    "mol/L", "mmol/L", "µmol/L", "μmol/L", "nmol/L", "pmol/L",
    "kPa", "MPa", "GPa", "Pa", "mbar", "bar", "atm", "Torr",
    "keV", "MeV", "GeV", "TeV", "eV", "mV", "kV", "µV", "μV", "V",
    "kHz", "MHz", "GHz", "Hz",
    "mA", "µA", "μA", "nA", "pA", "A",
    "kΩ", "MΩ", "Ω",
    "ms", "µs", "μs", "ns", "ps", "fs", "s", "min", "h", "d",
    "km", "cm", "mm", "µm", "μm", "nm", "pm", "m",
    "kg", "mg", "µg", "μg", "ng", "pg", "g",
    "mL", "µL", "μL", "nL", "L",
    "K", "°C", "C", "°",
    "nM", "µM", "μM", "mM", "pM", "fM", "M",
    "%", "wt%", "vol%", "ppm", "ppb",
    "kN", "mN", "N", "kJ", "MJ", "J", "cal", "kcal",
    "Da", "kDa", "bp", "kb", "nt",
    # Time and period words in both languages: a translation that renders "12 h"
    # as "12 小时" must not read as dropping its unit. Both spellings extract,
    # and the translation invariant canonicalises them before comparing.
    "week", "weeks", "day", "days", "hour", "hours", "month", "months",
    "year", "years", "minute", "minutes", "second", "seconds",
    "周", "天", "日", "小时", "分钟", "秒", "月", "个月", "年",
]
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))

# A number: optional sign, digits, optional decimal, optional exponent.
_NUM = r"[-−–+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# Numeric citation markers are handled separately, so they are excluded here.
_CITE_NUM = re.compile(r"\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]")

# A trailing \b is wrong next to CJK text: "3倍" has no word boundary between the
# digit and the character, and "°C下" has none after the C. Both then either fail to
# match at all or match a shorter unit ("°" instead of "°C"). ASCII-only lookaheads
# keep the guard against "12.4mVx" without breaking Chinese sources.
_NUM_UNIT = re.compile(
    rf"(?<![A-Za-z0-9.])(?:(?P<num>{_NUM})\s*(?P<unit>{_UNIT_ALT})(?![A-Za-z])|(?P<num2>{_NUM})(?![0-9]))")


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str | None
    raw: str

    def key(self) -> tuple:
        return (round(self.value, 9), self.unit)


def _to_float(s: str) -> float | None:
    t = s.replace("−", "-").replace("–", "-").replace("+", "", 1) if s.startswith("+") else s
    t = t.replace("−", "-").replace("–", "-")
    try:
        return float(t)
    except ValueError:
        return None


def extract_quantities(text: str) -> list[Quantity]:
    """All numbers, with a unit when one is attached.

    Numeric citations are removed first: `[12]` is a pointer, not a measurement,
    and treating it as a quantity produces nonsense findings.
    """
    cleaned = normalise(text)
    cleaned = _CITE_NUM.sub(" ", cleaned)
    out: list[Quantity] = []
    for m in _NUM_UNIT.finditer(cleaned):
        raw = m.group(0)
        if m.group("num") is not None:
            v = _to_float(m.group("num"))
            if v is None:
                continue
            out.append(Quantity(v, m.group("unit"), raw.strip()))
        else:
            v = _to_float(m.group("num2"))
            if v is None:
                continue
            out.append(Quantity(v, None, raw.strip()))
    return out


# ---------------------------------------------------------------------------
# Citations and cross-references
# ---------------------------------------------------------------------------

_NUMERIC_CITE = re.compile(r"\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]")
_AUTHOR_YEAR = re.compile(
    r"\((?:[A-Z][A-Za-z'\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'\-]+)?(?:\s+et\s+al\.?)?"
    r"(?:,\s*\d{4}[a-z]?)(?:\s*[;,]\s*\d{4}[a-z]?)*)\)"
)
# In-text author-year without parentheses, e.g. "Smith et al. (2020)".
_AUTHOR_YEAR_INLINE = re.compile(
    r"[A-Z][A-Za-z'\-]+\s+et\s+al\.?\s*\((\d{4}[a-z]?)\)"
)
_XREF = re.compile(
    r"\b(?:Fig(?:ure)?s?\.?|Tab(?:le)?s?\.?|Eq(?:uation)?s?\.?|Section|Sec\.|"
    r"Supplementary\s+(?:Fig(?:ure)?|Tab(?:le)|Sec(?:tion)))\s*"
    r"(?:S?\d+[A-Za-z]?|[IVX]+)\b"
    r"|(?:图|表|式|公式|章节)\s*S?\d+(?:\.\d+)?",
    re.IGNORECASE,
)


def extract_citations(text: str) -> list[str]:
    """Citation markers as written, normalised for whitespace only."""
    t = normalise(text)
    found = _NUMERIC_CITE.findall(t)
    found += ["(" + m + ")" for m in _AUTHOR_YEAR.findall(t)]
    found += [f"({m})" for m in _AUTHOR_YEAR_INLINE.findall(t)]
    return [re.sub(r"\s+", "", f) for f in found]


def extract_xrefs(text: str) -> list[str]:
    t = normalise(text)
    return [re.sub(r"\s+", " ", m.group(0)).lower() for m in _XREF.finditer(t)]


# ---------------------------------------------------------------------------
# Hedge strength
# ---------------------------------------------------------------------------

# Ordered from weakest to most absolute. The number is the *strength of the
# claim*, so raising it in an edit means the claim got stronger.
HEDGE_LEVELS: list[tuple[int, tuple[str, ...]]] = [
    (1, ("might", "could", "possibly", "conceivably", "或许", "也许", "可能仅")),
    (2, ("may", "appears", "appear", "seems", "seem", "unclear", "uncertain",
         "roughly", "approximately", "about", "consistent with", "likely",
         "可能", "似乎", "大致", "约", "推测", "倾向于")),
    (3, ("suggests", "suggest", "indicates", "indicate", "points to",
         "is consistent", "appears to indicate", "表明", "提示", "支持")),
    (4, ("demonstrates", "demonstrate", "shows", "show", "confirms", "confirm",
         "establishes", "establish", "we find", "reveals", "证明", "证实", "显示")),
    (5, ("proves", "prove", "clearly", "undoubtedly", "always", "never", "must",
         "definitively", "conclusively", "必然", "总是", "无疑", "显然", "绝对")),
]
_HEDGE_LOOKUP: list[tuple[int, str]] = [
    (lvl, term) for lvl, terms in HEDGE_LEVELS for term in terms
]
_HEDGE_LOOKUP.sort(key=lambda t: len(t[1]), reverse=True)


def find_hedges(text: str) -> list[dict]:
    """Every hedge/booster term with its claim-strength level."""
    t = normalise(text).lower()
    out: list[dict] = []
    for level, term in _HEDGE_LOOKUP:
        for m in re.finditer(rf"(?<![a-z]){re.escape(term)}(?![a-z])", t):
            out.append({"term": term, "level": level, "start": m.start(), "end": m.end()})
    return out


def claim_strength(sentence: str) -> int:
    """The strongest claim term in a sentence; 0 when it asserts without hedging."""
    hs = find_hedges(sentence)
    return max((h["level"] for h in hs), default=0)


def strengtheners(sentence: str) -> list[str]:
    """Absolute-language terms, which are the usual way a claim gets over-claimed."""
    return sorted({h["term"] for h in find_hedges(sentence) if h["level"] >= 5})


# ---------------------------------------------------------------------------
# Terminology consistency
# ---------------------------------------------------------------------------

@dataclass
class Glossary:
    """A concept maps to exactly one preferred form; variants are violations."""
    concepts: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Glossary":
        return cls(concepts={k: v for k, v in (data or {}).items()})

    def preferred(self, concept: str) -> str | None:
        c = self.concepts.get(concept)
        return c.get("preferred") if c else None

    def variants(self, concept: str) -> list[str]:
        c = self.concepts.get(concept) or {}
        return list(c.get("variants") or [])

    def first_mention(self, concept: str) -> str | None:
        c = self.concepts.get(concept) or {}
        return c.get("abbreviation")


def load_glossary(path) -> Glossary:
    """Read a glossary JSON. Refuses to guess at a malformed file."""
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("glossary must be an object of concept -> {preferred, variants, abbreviation}")
    return Glossary.from_dict(data)


def check_terms(text: str, glossary: Glossary) -> list[dict]:
    """Report every use of a non-preferred variant, with its position."""
    t = normalise(text)
    findings = []
    for concept, spec in glossary.concepts.items():
        pref = spec.get("preferred")
        variants = spec.get("variants")
        for variant in (variants if isinstance(variants, (list, tuple)) else []):
            for m in re.finditer(re.escape(variant), t):
                # A variant that is a substring of the preferred form is not a
                # violation (e.g. "diffraction" inside "X-ray diffraction").
                if pref and variant in pref:
                    continue
                findings.append({
                    "rule": "terminology.variant",
                    "concept": concept,
                    "found": variant,
                    "preferred": pref,
                    "start": m.start(),
                    "end": m.end(),
                    "context": t[max(0, m.start() - 40):m.end() + 40].replace("\n", " "),
                })
    return findings


def check_first_mention(text: str, glossary: Glossary) -> list[dict]:
    """An abbreviation must be introduced in full the first time it is used."""
    t = normalise(text)
    findings = []
    for concept, spec in glossary.concepts.items():
        abbr = spec.get("abbreviation")
        if not abbr:
            continue
        first_abbr = t.find(abbr)
        if first_abbr < 0:
            continue
        pref = spec.get("preferred") or ""
        # Accept either the expanded form before it, or an explicit "Full Name (ABBR)".
        window = t[max(0, first_abbr - max(len(pref) + 40, 80)):first_abbr]
        if pref and pref.lower() not in window.lower():
            findings.append({
                "rule": "terminology.abbreviation_not_introduced",
                "concept": concept,
                "abbreviation": abbr,
                "preferred": pref,
                "start": first_abbr,
                "context": t[max(0, first_abbr - 60):first_abbr + 60].replace("\n", " "),
            })
    return findings

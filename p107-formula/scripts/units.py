"""Unit handling for extracted measurements.

Every rule here exists because a silently converted unit is a wrong number that
nobody catches. So:

  - a conversion records original value, original unit, target unit and factor
  - an unknown unit is never guessed at; it is reported by name
  - prefixes are parsed, not assumed (``mM`` is milli-molar, ``m`` is metre)
  - ranges and "not reported" are first-class, not zero and not a single number

Resolution has three layers, and the layering is what keeps it terminating:

  parse_simple    one token, no recursion          mg, mM, mol, J
  parse_compound  splits on / and * then recurses  mol/L, mg*kg, W/m2
  parse_unit      public entry point: compound     (which itself tries simple first)

Dimensions use 7 base exponents, enough to reject ``mg`` -> ``mm`` without a full
dimensional-analysis library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DIM_NAMES = ("mass", "length", "time", "current", "temperature", "amount", "luminous")
ZERO_DIM = (0, 0, 0, 0, 0, 0, 0)

PREFIXES = [
    ("da", 1e1), ("Y", 1e24), ("Z", 1e21), ("E", 1e18), ("P", 1e15), ("T", 1e12),
    ("G", 1e9), ("M", 1e6), ("k", 1e3), ("h", 1e2), ("d", 1e-1), ("c", 1e-2),
    ("m", 1e-3), ("u", 1e-6), ("\u00b5", 1e-6), ("\u03bc", 1e-6),
    ("n", 1e-9), ("p", 1e-12), ("f", 1e-15), ("a", 1e-18),
]

# name -> (dimension vector, factor to SI base). Base mass is kg, so gram is 1e-3.
_UNITS = {
    "g":   ((1, 0, 0, 0, 0, 0, 0), 1e-3),
    "m":   ((0, 1, 0, 0, 0, 0, 0), 1.0),
    "s":   ((0, 0, 1, 0, 0, 0, 0), 1.0),
    "A":   ((0, 0, 0, 1, 0, 0, 0), 1.0),
    "K":   ((0, 0, 0, 0, 1, 0, 0), 1.0),
    "mol": ((0, 0, 0, 0, 0, 1, 0), 1.0),
    "cd":  ((0, 0, 0, 0, 0, 0, 1), 1.0),
    "L":   ((0, 3, 0, 0, 0, 0, 0), 1e-3),
    # Molar is amount concentration, not mass concentration: mol/m^3, so the
    # dimension vector must carry amount=1 and mass=0. Defining it as mass/volume
    # makes mol/L and mM look like different quantities, which they are not.
    "M":   ((0, -3, 0, 0, 0, 1, 0), 1e3),
    "Hz":  ((0, 0, -1, 0, 0, 0, 0), 1.0),
    "N":   ((1, 1, -2, 0, 0, 0, 0), 1.0),
    "Pa":  ((1, -1, -2, 0, 0, 0, 0), 1.0),
    "J":   ((1, 2, -2, 0, 0, 0, 0), 1.0),
    "W":   ((1, 2, -3, 0, 0, 0, 0), 1.0),
    "V":   ((1, 2, -3, -1, 0, 0, 0), 1.0),
    "C":   ((0, 0, 1, 1, 0, 0, 0), 1.0),
    "ohm": ((1, 2, -3, -2, 0, 0, 0), 1.0),
    "bar": ((1, -1, -2, 0, 0, 0, 0), 1e5),
    "atm": ((1, -1, -2, 0, 0, 0, 0), 101325.0),
    "Torr": ((1, -1, -2, 0, 0, 0, 0), 101325.0 / 760),
    "eV":  ((1, 2, -2, 0, 0, 0, 0), 1.602176634e-19),
    "Da":  ((1, 0, 0, 0, 0, 0, 0), 1.66053906660e-27),
}

SPECIAL = {"degC": "temperature_offset", "deg": "angle", "%": "fraction", "ppm": "fraction_1e6"}


@dataclass(frozen=True)
class Unit:
    raw: str
    factor: float
    dimension: tuple
    kind: str = "compound"


def parse_simple(token: str) -> Unit | None:
    """One unit token, prefixed or not. Never recurses."""
    t = (token or "").strip()
    if not t:
        return None
    if t in SPECIAL:
        return Unit(raw=t, factor=1.0, dimension=ZERO_DIM, kind=SPECIAL[t])
    if t in _UNITS:
        dim, f = _UNITS[t]
        return Unit(raw=t, factor=f, dimension=dim, kind="simple")
    for p, mult in PREFIXES:
        rest = t[len(p):]
        if t.startswith(p) and rest in _UNITS:
            dim, f = _UNITS[rest]
            return Unit(raw=t, factor=mult * f, dimension=dim, kind="prefixed")
    return None


def _combine(a: tuple, b: tuple, sign: int = 1) -> tuple:
    return tuple(x + sign * y for x, y in zip(a, b))


def parse_compound(text: str, depth: int = 0) -> Unit | None:
    """Compound units. Calls parse_simple and itself only, with a depth bound."""
    if depth > 4:
        return None
    t = (text or "").strip().replace("\u00b7", "*").replace("\u22c5", "*").replace(" ", "")
    if not t:
        return None

    simple = parse_simple(t)
    if simple is not None:
        return simple

    # Both common scientific forms (m2, s-2) and LaTeX-like powers (m^2, s^{-2}) are
    # accepted.  Exponents are integers by design; ambiguity about a fractional physical
    # unit stays unresolved rather than silently rounding it.
    power = (re.fullmatch(r"([A-Za-zµμ]+)\^(?:\{)?([+-]?\d+)\}?", t)
             or re.fullmatch(r"([A-Za-zµμ]+?)([+-]?\d+)", t))
    if power:
        base = parse_simple(power.group(1))
        exponent = int(power.group(2))
        if base is not None and abs(exponent) <= 100:
            return Unit(raw=t, factor=base.factor ** exponent,
                        dimension=tuple(x * exponent for x in base.dimension), kind="power")

    if "/" in t:
        parts = t.split("/")
        if len(parts) != 2:
            return None
        num = parse_compound(parts[0], depth + 1)
        den = parse_compound(parts[1], depth + 1)
        if num is None or den is None:
            return None
        return Unit(raw=t, factor=num.factor / den.factor,
                    dimension=_combine(num.dimension, den.dimension, -1), kind="ratio")

    if "*" in t:
        tokens = [x for x in t.split("*") if x]
        if len(tokens) < 2:
            return None
        dim, factor = ZERO_DIM, 1.0
        for tok in tokens:
            got = parse_compound(tok, depth + 1)
            if got is None:
                return None
            dim, factor = _combine(dim, got.dimension), factor * got.factor
        return Unit(raw=t, factor=factor, dimension=dim, kind="product")

    return None


def parse_unit(text: str) -> Unit | None:
    """Public resolver. None means unrecognised and must be reported as such."""
    return parse_compound(text)


def convert(value: float, src: str, dst: str) -> dict:
    """Convert between units of the same dimension, or refuse with a reason."""
    if (src or "").strip() == (dst or "").strip():
        return {"ok": True, "value": value, "src": src, "dst": dst, "factor": 1.0}

    us, ud = parse_unit(src), parse_unit(dst)
    if us is None:
        return {"ok": False, "kind": "unknown_unit", "reason": f"unknown source unit '{src}'"}
    if ud is None:
        return {"ok": False, "kind": "unknown_unit", "reason": f"unknown target unit '{dst}'"}
    if us.dimension != ud.dimension:
        return {"ok": False, "kind": "dimension_mismatch",
                "reason": f"'{src}' and '{dst}' are not the same kind of quantity",
                "src_dimension": {k: v for k, v in zip(DIM_NAMES, us.dimension) if v},
                "dst_dimension": {k: v for k, v in zip(DIM_NAMES, ud.dimension) if v}}
    if us.kind in SPECIAL.values() or ud.kind in SPECIAL.values():
        return {"ok": False, "kind": "special_unit",
                "reason": f"'{src}' -> '{dst}' is not a multiplicative conversion"}

    factor = us.factor / ud.factor
    out = value * factor
    return {"ok": True, "value": out, "src": src, "dst": dst, "factor": factor,
            "formula": f"{value:g} {src} x {factor:g} = {out:g} {dst}"}


# --- measurement parsing ----------------------------------------------------

RANGE = re.compile(
    r"^\s*(?P<a>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?:-|\u2013|\u2014|to|~)\s*"
    r"(?P<b>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?P<u>[^\s]+)?\s*$")
PLUSMINUS = re.compile(
    r"^\s*(?P<v>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?:\u00b1|\+/-|\+-)\s*"
    r"(?P<e>\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?P<u>[^\s]+)?\s*$")
SINGLE = re.compile(
    r"^\s*(?P<v>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?P<u>[^\s]+)?\s*$")
NOT_REPORTED = re.compile(
    r"^\s*(n\.?r\.?|not\s+(?:reported|stated|given)|n/?a|--?|\u2014|"
    r"\u672a\u62a5\u544a|\u672a\u7ed9\u51fa|\u4e0d\u8be6)\s*$", re.IGNORECASE)


def parse_measurement(text: str) -> dict:
    """Parse a value into a typed measurement.

    `kind` is single, plus_minus, range, not_reported or unparsed. Hedging such as
    "about 5 mM" stays `unparsed` on purpose: turning it into 5 discards the hedge,
    and the hedge is part of the claim.
    """
    t = (text or "").strip()
    if NOT_REPORTED.match(t):
        return {"kind": "not_reported", "raw": t}
    m = PLUSMINUS.match(t)
    if m:
        return {"kind": "plus_minus", "value": float(m.group("v")), "error": float(m.group("e")),
                "unit": m.group("u") or "", "raw": t}
    m = RANGE.match(t)
    if m:
        return {"kind": "range", "low": float(m.group("a")), "high": float(m.group("b")),
                "unit": m.group("u") or "", "raw": t}
    m = SINGLE.match(t)
    if m:
        return {"kind": "single", "value": float(m.group("v")), "unit": m.group("u") or "",
                "raw": t}
    return {"kind": "unparsed", "raw": t}

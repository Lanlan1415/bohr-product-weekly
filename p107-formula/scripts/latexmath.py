"""Small, bounded LaTeX/MathML parser and real numeric/dimensional checks.

This intentionally separates syntax conversion from evaluation, following the
parse-tree/semantics split used by latex2sympy (OrangeX4/latex2sympy).  It is not
an arbitrary Python evaluator and never silently returns zero for unsupported
mathematics.  Optional SymPy use is deliberately NOT required: the checks below
work in the standard library.  Matrices and piecewise values cannot be assigned
one scalar here; they return an explicit ``undetermined`` outcome.
"""
from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units as U


class MathUndetermined(ValueError):
    """The available material cannot support a mathematical determination."""


GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ",
    "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
GREEK_REVERSE = {v: k for k, v in GREEK.items()}


def canonical_symbol(name: str) -> str:
    """One identity for `λ_1`, `\\lambda_1` and `lambda_1`, preserving the full index."""
    raw = str(name or "").strip().lstrip("\\")
    base, sep, suffix = raw.partition("_")
    return GREEK.get(base, base) + sep + suffix


OPERATORS = {"cdot": "*", "times": "*", "div": "/", "+": "+", "-": "-", "=": "=",
             "lt": "<", "gt": ">", "leq": "≤", "geq": "≥", "neq": "≠",
             "le": "≤", "ge": "≥", "pm": "±", "infty": "∞", "rightarrow": "→",
             "to": "→", "partial": "∂", "prime": "′"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].strip().lower()


def _mathml_sequence(parent: ET.Element) -> str:
    """Join MathML siblings without fusing adjacent identifier tokens."""
    out = []
    previous = None
    for child in parent:
        text = mathml_latex(child)
        if previous is not None and _local(previous.tag) == _local(child.tag) == "mi":
            a = "".join(previous.itertext()).strip()
            b = "".join(child.itertext()).strip()
            if len(a) == len(b) == 1:
                out.append(" ")
        out.append(text)
        if child.tail:
            out.append(child.tail)
        previous = child
    return "".join(out)


def mathml_latex(node: ET.Element) -> str:
    """Recursively preserve fraction/script/Greek nesting from publisher MathML.

    The routine does not solve, simplify or reorder a formula.  An unsupported
    semantic element is retained as a ``\text{element:...}`` marker rather than
    disappearing silently; a reviewer can then resolve that marked uncertainty.
    """
    t = _local(node.tag)
    raw = (node.text or "")
    kids = list(node)
    if t in {"math", "mrow", "semantics", "mstyle", "mpadded", "merror"}:
        body = _mathml_sequence(node)
        if t == "mrow":
            return "{" + body + "}" if len(kids) > 1 else body
        if t == "math" and len(kids) > 1:
            return "{" + body + "}"
        return body
    if t == "annotation":
        return ""             # alternate presentation, not a second equation
    if t in {"mi", "mn", "mtext"}:
        text = " ".join(raw.split())
        if t == "mi":
            text = GREEK_REVERSE.get(text, "")
            text = "\\" + text + " " if text else " ".join(raw.split())
            return text
        return "\\text{" + text.replace("{", "(").replace("}", ")") + "}" if t == "mtext" else text
    if t == "mo":
        s = "".join(node.itertext()).strip()
        return OPERATORS.get(s, s)
    if t == "mspace":
        return " "
    if t == "mfrac" and len(kids) >= 2:
        return "\\frac{" + mathml_latex(kids[0]) + "}{" + mathml_latex(kids[1]) + "}"
    if t in {"msub", "msup", "msubsup"} and len(kids) >= 2:
        base = mathml_latex(kids[0])
        sub = mathml_latex(kids[1])
        sup = mathml_latex(kids[2]) if len(kids) > 2 else None
        out = base + ("_{" + sub + "}" if t != "msup" else "^{" + sub + "}")
        if sup is not None:
            out += "^{" + sup + "}"
        return out
    if t == "msqrt":
        return "\\sqrt{" + "".join(mathml_latex(c) for c in kids) + "}"
    if t == "mroot" and len(kids) >= 2:
        return "\\sqrt[" + mathml_latex(kids[1]) + "]{" + mathml_latex(kids[0]) + "}"
    if t == "mfenced":
        left = node.attrib.get("open", "(")
        right = node.attrib.get("close", ")")
        sep = node.attrib.get("separators", ",")
        return "\\left" + left + (sep[0] if sep else "").join(
            mathml_latex(c) for c in kids) + "\\right" + right
    if t in {"munder", "mover", "munderover"}:
        return "".join(mathml_latex(c) for c in kids)
    if t == "mtable":
        rows = []
        for row in kids:
            if _local(row.tag) == "mtr":
                cells = [mathml_latex(c) for c in row if _local(c.tag) == "mtd"]
                rows.append(" & ".join(cells))
        attrs = node.attrib.get("columnalign", "")
        env = "pmatrix" if attrs or rows else "matrix"
        return "\\begin{" + env + "}" + " \\\\ ".join(rows) + "\\end{" + env + "}"
    if t in {"mtr"}:
        return " & ".join(mathml_latex(c) for c in kids if _local(c.tag) == "mtd")
    if t == "mtd":
        return "".join(mathml_latex(c) for c in kids) + raw
    # No silent data loss: include the visible source AND name its construct.
    visible = "".join(node.itertext()).strip().replace("{", "(").replace("}", ")")
    return "\\text{unsupported-" + t + ":" + visible + "}"


def catalog_mathml(xml_text: str) -> list[dict]:
    """Return actual ``math`` elements with source and human-readable number locators."""
    root = ET.fromstring(xml_text)
    found = []
    seen = set()
    for pos, node in enumerate(root.iter()):
        if _local(node.tag) != "math":
            continue
        src = (node.attrib.get("id") or node.attrib.get("source-id") or
               node.attrib.get("data-source-id") or node.attrib.get("data-id"))
        key = id(node)
        if key in seen:
            continue
        seen.add(key)
        latex_node = deepcopy(node)
        number = (node.attrib.get("number") or node.attrib.get("equation-number") or
                  node.attrib.get("data-formula-number"))
        for child in list(latex_node):
            if _local(child.tag) == "mtext" and re.fullmatch(
                    r"\s*\(\s*\d+(?:[.-]\d+)*[a-z]?\s*\)\s*", "".join(child.itertext())):
                number = number or "".join(child.itertext()).strip().strip("() ")
                latex_node.remove(child)
        latex = mathml_latex(latex_node)
        # Fix common publisher shape where (1) is an mtext sibling at the end.
        mn = re.findall(r"\((\d+(?:[.-]\d+)*(?:[a-z])?)\)", "".join(node.itertext()))
        if not number and mn:
            number = mn[-1]
        if not src:
            src = "math:%d" % (pos + 1)
        found.append({"source_id": src, "number": str(number) if number else None,
                      "latex": latex, "display": node.attrib.get("display")})
    return found


# --- A small expression parser ------------------------------------------------

class _Lexer:
    def __init__(self, text: str):
        self.s = text or ""
        self.i = 0
        self.tokens = []
        self.unsupported = []
        self._lex()
        self.tokens.append(("end", ""))

    def _lex(self):
        s = self.s
        while self.i < len(s):
            if len(self.tokens) > 4096 or self.i > 65536:
                raise MathUndetermined("expression exceeds the bounded parser budget")
            c = s[self.i]
            if c.isspace() or c in "$":
                self.i += 1
                continue
            if s.startswith("\\left", self.i) or s.startswith("\\right", self.i):
                self.i += 5 if s.startswith("\\left", self.i) else 6
                continue
            if c == "\\":
                if self.i + 1 < len(s) and not s[self.i + 1].isalpha():
                    self.i += 2
                    continue
                m = re.match(r"\\([A-Za-z]+)", s[self.i:])
                if not m:
                    raise MathUndetermined("unrecognised LaTeX command at %d" % self.i)
                cmd = m.group(1)
                self.i += len(m.group(0))
                if cmd in ("frac", "dfrac", "tfrac"):
                    self.tokens.append(("frac", "\\frac"))
                elif cmd == "sqrt":
                    self.tokens.append(("sqrt", cmd))
                elif cmd in ("exp", "ln", "log", "sin", "cos", "tan"):
                    self.tokens.append(("function", cmd))
                elif cmd in GREEK:
                    self.tokens.append(("name", GREEK[cmd]))
                elif cmd in OPERATORS:
                    self.tokens.append((OPERATORS[cmd], OPERATORS[cmd]))
                elif cmd in ("mathrm", "mathbf", "mathit", "mathcal", "operatorname", "text"):
                    # Group contents are still parsed as names/prose; text-only groups are
                    # explicitly left unresolved rather than accidentally evaluated as maths.
                    self.unsupported.append(cmd)
                else:
                    self.tokens.append(("unsupported", cmd))
                continue
            m = re.match(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", s[self.i:])
            if m and c.isdigit() or m and c == ".":
                self.tokens.append(("number", m.group(0)))
                self.i += len(m.group(0))
                continue
            if c.isalpha() or c in GREEK_REVERSE:
                m = re.match(r"[A-Za-z]+", s[self.i:])
                word = m.group(0) if m else c
                self.tokens.append(("name", canonical_symbol(GREEK.get(word, word))))
                self.i += len(word)
                continue
            if c in "()[]{}+-*/^_=<>":
                self.tokens.append((c, c))
                self.i += 1
                continue
            if c == "%":
                # Conventional percentage notation is a number suffix, not modulo.
                self.tokens.append(("%", c))
                self.i += 1
                continue
            self.tokens.append(("unsupported", c))
            self.i += 1

    def peek(self):
        return self.tokens[0]

    def pop(self):
        v = self.tokens.pop(0)
        return v


class _Parser:
    def __init__(self, text: str):
        self.lex = _Lexer(text)
        self.depth = 0

    def parse(self, want_relation=True):
        node = self.relation() if want_relation else self.expr()
        if self.lex.peek()[0] not in {"end", "}", ")"}:
            kind, val = self.lex.peek()
            raise MathUndetermined("unparsed token %r (%s)" % (val, kind))
        return node

    def relation(self):
        lhs = self.expr()
        if self.lex.peek()[0] == "=":
            self.lex.pop()
            return {"kind": "relation", "left": lhs, "right": self.expr(), "operator": "="}
        return lhs

    def expr(self):
        self.depth += 1
        if self.depth > 100:
            raise MathUndetermined("expression nesting exceeds 100")
        node = self.term()
        while self.lex.peek()[0] in {"+", "-"}:
            op = self.lex.pop()[0]
            node = {"kind": "binary", "op": op, "args": [node, self.term()]}
        self.depth -= 1
        return node

    def term(self):
        node = self.power()
        while True:
            kind, val = self.lex.peek()
            if kind in {"*", "/"}:
                self.lex.pop()
                node = {"kind": "binary", "op": kind, "args": [node, self.power()]}
            elif kind in {"number", "name", "(", "{", "frac", "sqrt", "function"}:
                # Juxtaposition is multiplication, e.g. h c.  A function call is parsed in
                # unary(), so exp(x) is not silently converted to exp*x.
                node = {"kind": "binary", "op": "*", "args": [node, self.power()]}
            else:
                break
        return node

    def power(self):
        node = self.unary()
        if self.lex.peek()[0] == "^":
            self.lex.pop()
            node = {"kind": "power", "args": [node, self.power()]}
        return node

    def unary(self):
        if self.lex.peek()[0] in {"+", "-"}:
            op = self.lex.pop()[0]
            node = self.unary()
            return node if op == "+" else {"kind": "neg", "args": [node]}
        return self.atom()

    def _group_text(self, closing="}"):
        # Scripts are names, not evaluated equations.  Keep arbitrary braces intact as a
        # semantic part of the identifier (k_B and x_{i+1} remain distinct symbols).
        self.depth += 1
        if self.depth > 100:
            raise MathUndetermined("script nesting exceeds 100")
        out = []
        while self.lex.peek()[0] not in {closing, "end"}:
            k, v = self.lex.pop()
            out.append(str(v))
        if self.lex.peek()[0] != closing:
            raise MathUndetermined("unclosed script/group")
        self.lex.pop()
        self.depth -= 1
        return "".join(out)

    def atom(self):
        kind, val = self.lex.pop()
        if kind == "number":
            node = {"kind": "number", "value": float(val)}
        elif kind == "name":
            name = val
            if self.lex.peek()[0] == "_":
                self.lex.pop()
                k, v = self.lex.pop()
                if k == "{":
                    sub = self._group_text()
                elif k in {"name", "number"}:
                    sub = v
                else:
                    raise MathUndetermined("invalid subscript on " + name)
                name += "_" + sub
            node = {"kind": "symbol", "name": name}
        elif kind in {"(", "{"}:
            node = self.relation()
            if self.lex.peek()[0] not in {")", "}"}:
                raise MathUndetermined("unclosed parenthesis/group")
            self.lex.pop()
        elif kind == "(":
            raise MathUndetermined("invalid parenthesis")
        elif kind == "frac":
            a, b = self._argument(), self._argument()
            node = {"kind": "binary", "op": "/", "args": [a, b]}
        elif kind == "sqrt":
            degree = None
            if self.lex.peek()[0] == "[":
                self.lex.pop()
                degree = self.expr()
                if self.lex.peek()[0] != "]":
                    raise MathUndetermined("unclosed root index")
                self.lex.pop()
            base = self._argument()
            if degree is None:
                node = {"kind": "function", "name": "sqrt", "args": [base]}
            else:
                node = {"kind": "power", "args": [base, {"kind": "binary", "op": "/",
                        "args": [{"kind": "number", "value": 1.0}, degree]}]}
        elif kind == "function":
            args = [self._argument()]
            node = {"kind": "function", "name": val, "args": args}
        else:
            raise MathUndetermined("unsupported construct %r (%s)" % (val, kind))
        while self.lex.peek()[0] == "%":
            self.lex.pop()
            node = {"kind": "binary", "op": "/", "args": [node, {"kind": "number", "value": 100.0}]}
        return node

    def _argument(self):
        if self.lex.peek()[0] == "{":
            self.lex.pop()
            node = self.relation()
            if self.lex.peek()[0] != "}":
                raise MathUndetermined("unclosed command argument")
            self.lex.pop()
            return node
        return self.atom()


def parse_latex(expression: str):
    if not str(expression or "").strip():
        raise MathUndetermined("no expression was supplied")
    return _Parser(str(expression)).parse()


def _side(node):
    return node["right"] if node.get("kind") == "relation" else node


def _split(node):
    if node.get("kind") == "relation":
        return node["left"], node["right"]
    raise MathUndetermined("this expression has no top-level equation")


def symbols(expression_or_node) -> set[str]:
    tree = parse_latex(expression_or_node) if isinstance(expression_or_node, str) else expression_or_node
    out = set()

    def walk(n):
        k = n.get("kind")
        if k == "symbol":
            out.add(n["name"])
        elif k == "relation":
            walk(n["left"]); walk(n["right"])
        for a in n.get("args", []):
            walk(a)
    walk(tree)
    return out


def _lookup(name: str, env: dict):
    canonical = canonical_symbol(name)
    matches = [(key, value) for key, value in env.items() if canonical_symbol(key) == canonical]
    if not matches:
        raise MathUndetermined("no numeric value for symbol %s" % name)
    values = {repr(value) for _, value in matches}
    if len(values) > 1:
        raise MathUndetermined("ambiguous values for aliased symbol %s" % name)
    return matches[0][1]


def _eval(node, env: dict):
    k = node["kind"]
    if k == "number":
        return node["value"]
    if k == "symbol":
        value = _lookup(node["name"], env)
        try:
            if isinstance(value, dict) and "value" in value:
                value = value["value"]
            out = float(value)
        except (TypeError, ValueError) as exc:
            raise MathUndetermined("value for %s is not numeric" % node["name"]) from exc
        if not math.isfinite(out):
            raise MathUndetermined("non-finite value for %s" % node["name"])
        return out
    if k == "neg":
        return -_eval(node["args"][0], env)
    if k == "relation":
        raise MathUndetermined("an equation has two sides; evaluate each separately")
    if k == "function":
        v = _eval(node["args"][0], env)
        funcs = {"sqrt": math.sqrt, "exp": math.exp, "ln": math.log, "log": math.log10,
                 "sin": math.sin, "cos": math.cos, "tan": math.tan}
        try:
            return funcs[node["name"]](v)
        except (ValueError, OverflowError) as exc:
            raise MathUndetermined("function %s is undefined here: %s" % (node["name"], exc)) from exc
    if k == "power":
        a, b = (_eval(x, env) for x in node["args"])
        try:
            out = a ** b
        except (ValueError, OverflowError, ZeroDivisionError) as exc:
            raise MathUndetermined("power is undefined here: %s" % exc) from exc
        if isinstance(out, complex) or not math.isfinite(out):
            raise MathUndetermined("non-real or non-finite power result")
        return out
    a, b = (_eval(x, env) for x in node["args"])
    try:
        if node["op"] == "+": return a + b
        if node["op"] == "-": return a - b
        if node["op"] == "*": return a * b
        if node["op"] == "/": return a / b
    except (ZeroDivisionError, OverflowError) as exc:
        raise MathUndetermined("arithmetic is undefined here: %s" % exc) from exc
    raise MathUndetermined("unknown expression operator")


def evaluate(expression_or_node, values: dict) -> float:
    tree = parse_latex(expression_or_node) if isinstance(expression_or_node, str) else expression_or_node
    return _finite_value(_eval(_side(tree), values), "evaluated result")


def _finite_value(value, label="numeric value"):
    value = float(value)
    if not math.isfinite(value):
        raise MathUndetermined(label + " is not finite")
    return value


def _unit_value(raw, target=None):
    """Return the raw declared value in the variable's declared target unit.

    Compatibility: numeric inputs remain numbers even if the formula declares no units.
    Measurements are only converted where both units are known;摄氏度 etc. are rejected
    by Unit conversion rather than silently treated as degrees Kelvin.
    """
    if isinstance(raw, bool):
        raise MathUndetermined("a boolean is not a numeric measurement")
    if isinstance(raw, (int, float)):
        return _finite_value(raw)
    if isinstance(raw, dict):
        value, unit = raw.get("value"), str(raw.get("unit") or "")
    elif isinstance(raw, str):
        m = U.parse_measurement(raw)
        if m.get("kind") != "single":
            raise MathUndetermined("only one exact measurement can be substituted; got %r" % raw)
        value, unit = m.get("value"), str(m.get("unit") or "")
    else:
        raise MathUndetermined("malformed measurement of type %s" % type(raw).__name__)
    if unit:
        if not target:
            parsed = U.parse_unit(unit)
            if parsed is None:
                raise MathUndetermined("unknown input unit %s" % unit)
            return _finite_value(float(value) * parsed.factor, "scaled input")
        converted = U.convert(float(value), unit, target)
        if not converted.get("ok"):
            raise MathUndetermined(converted.get("reason", "unit conversion failed"))
        return _finite_value(converted["value"], "converted input")
    # Unitless explicit zero/value is meaningful when no unit was declared; otherwise it is
    # ambiguous whether the author intended a raw coefficient or a physical measurement.
    if target:
        raise MathUndetermined("input lacks the variable's declared unit %s" % target)
    return _finite_value(value, "input measurement")


def normalized_inputs(formula: dict, inputs: dict) -> dict:
    units = {}
    for variable in formula.get("variables") or []:
        if not isinstance(variable, dict):
            continue
        key = canonical_symbol(str(variable.get("name") or "").strip())
        if not key:
            continue
        unit = str(variable.get("unit") or "").strip()
        if key in units and units[key] != unit:
            raise MathUndetermined("aliased variable %s has conflicting declared units" % key)
        units[key] = unit
    out = {}
    for key, val in inputs.items():
        canonical = canonical_symbol(str(key))
        target = units.get(canonical) or None
        value = _unit_value(val, target)
        if canonical in out and repr(out[canonical]) != repr(value):
            raise MathUndetermined("aliased numeric inputs disagree for %s" % canonical)
        out[canonical] = value
    return out


def _dimension(node, units_by_symbol: dict):
    k = node["kind"]
    if k == "number":
        return U.ZERO_DIM
    if k == "symbol":
        name = node["name"]
        unit = units_by_symbol.get(canonical_symbol(name))
        if not unit:
            raise MathUndetermined("no declared unit for %s" % name)
        parsed = U.parse_unit(unit)
        if parsed is None or parsed.kind in U.SPECIAL.values():
            raise MathUndetermined("unit %s of %s is not in the dimensional model" % (unit, name))
        return parsed.dimension
    if k == "relation":
        raise MathUndetermined("evaluate dimensions by equation side, not the whole equation")
    if k == "neg":
        return _dimension(node["args"][0], units_by_symbol)
    if k == "function":
        d = _dimension(node["args"][0], units_by_symbol)
        if d != U.ZERO_DIM:
            raise MathUndetermined("function %s needs a dimensionless argument" % node["name"])
        return d
    if k == "power":
        base, exponent = node["args"]
        if exponent.get("kind") != "number" or not float(exponent["value"]).is_integer():
            raise MathUndetermined("only integer powers are used for dimensional inference")
        count = int(exponent["value"])
        if abs(count) > 100:
            raise MathUndetermined("dimensional exponent exceeds 100")
        return tuple(count * a for a in _dimension(base, units_by_symbol))
    left, right = (_dimension(x, units_by_symbol) for x in node["args"])
    if node["op"] in {"+", "-"}:
        if left != right:
            raise MathUndetermined("addition/subtraction combines different dimensions")
        return left
    factor = 1 if node["op"] == "*" else -1 if node["op"] == "/" else None
    if factor is None:
        raise MathUndetermined("unknown dimensional operator")
    return tuple(a + factor * b for a, b in zip(left, right))


def dimensional_check(formula: dict) -> dict:
    try:
        tree = parse_latex(str(formula.get("latex") or ""))
        lhs, rhs = _split(tree)
        ubs = {}
        for variable in formula.get("variables") or []:
            if not isinstance(variable, dict):
                continue
            key = canonical_symbol(str(variable.get("name") or "").strip())
            if key:
                unit = str(variable.get("unit") or "").strip()
                if key in ubs and ubs[key] != unit:
                    raise MathUndetermined("aliased variable %s has conflicting units" % key)
                ubs[key] = unit
        dl, dr = _dimension(lhs, ubs), _dimension(rhs, ubs)
        declared_l, declared_r = formula.get("lhs_unit"), formula.get("rhs_unit")
        if declared_l:
            ul = U.parse_unit(str(declared_l))
            if ul is None:
                raise MathUndetermined("unknown declared lhs unit %s" % declared_l)
            if ul.dimension != dl:
                return {"status": "mismatch", "side": "lhs", "declared": ul.dimension, "derived": dl}
        if declared_r:
            ur = U.parse_unit(str(declared_r))
            if ur is None:
                raise MathUndetermined("unknown declared rhs unit %s" % declared_r)
            if ur.dimension != dr:
                return {"status": "mismatch", "side": "rhs", "declared": ur.dimension, "derived": dr}
        return {"status": "match" if dl == dr else "mismatch", "lhs": dl, "rhs": dr,
                "detail": "derived from declared variable units; no units were invented"}
    except (MathUndetermined, TypeError, KeyError, ValueError) as exc:
        return {"status": "undetermined", "reason": str(exc)[:240]}


def numeric_check(formula: dict) -> dict:
    """Really substitute measurements and compare.  Never turn failure into zero."""
    num = formula.get("numeric")
    if not isinstance(num, dict):
        return {"status": "not_requested"}
    expression = str(num.get("expression") or "")
    if not expression:
        expression = str(formula.get("latex") or "")
    if num.get("expected") in (None, ""):
        return {"status": "incomplete", "reason": "expected is missing"}
    try:
        tree = parse_latex(expression)
        values = normalized_inputs(formula, num.get("inputs") or {})
        computed = evaluate(tree, values)
        expected_raw = num["expected"]
        expected = _unit_value(expected_raw, str(formula.get("lhs_unit") or "") or None)
        tolerance = num.get("tolerance", 1e-9)
        if isinstance(tolerance, dict):
            abs_tol = float(tolerance.get("abs", 0.0))
            rel_tol = float(tolerance.get("rel", 0.0))
        else:
            abs_tol, rel_tol = float(tolerance), 0.0
        if abs_tol < 0 or rel_tol < 0 or not math.isfinite(abs_tol + rel_tol):
            raise MathUndetermined("tolerance must be finite and non-negative")
        delta = computed - expected
        bound = abs_tol + rel_tol * abs(expected)
        bound = _finite_value(bound, "tolerance bound")
        return {"status": "match" if abs(delta) <= bound else "mismatch",
                "computed": computed, "expected": expected, "absolute_delta": delta,
                "tolerance": {"abs": abs_tol, "rel": rel_tol}, "bound": bound,
                "expression_latex": expression, "input_units_normalised": True}
    except (MathUndetermined, TypeError, ValueError, KeyError) as exc:
        return {"status": "undetermined", "reason": str(exc)[:240]}


def derivation_check(formula: dict) -> list[dict]:
    """Evaluate declared from/to steps; identify the exact failing step or undetermined cause."""
    num = formula.get("numeric") if isinstance(formula.get("numeric"), dict) else {}
    requested = formula.get("verify_steps") is True
    out = []
    for idx, step in enumerate(formula.get("steps") or []):
        if not isinstance(step, dict) or not (requested or step.get("check") is True):
            continue
        record = {"step": idx, "from": step.get("from"), "to": step.get("to")}
        try:
            if not step.get("from") or not step.get("to"):
                raise MathUndetermined("both from and to are required")
            values = normalized_inputs(formula, num.get("inputs") or {})
            a, b = evaluate(str(step["from"]), values), evaluate(str(step["to"]), values)
            tol = num.get("tolerance", 1e-9)
            if isinstance(tol, dict):
                bound = float(tol.get("abs", 0)) + float(tol.get("rel", 0)) * max(abs(a), abs(b))
            else:
                bound = float(tol)
            record.update({"status": "match" if math.isclose(a, b, rel_tol=0.0, abs_tol=bound) else "mismatch",
                           "from_value": a, "to_value": b, "absolute_delta": a - b, "bound": bound})
        except (MathUndetermined, ValueError, TypeError) as exc:
            record.update({"status": "undetermined", "reason": str(exc)[:240]})
        out.append(record)
    return out


def round_trip_mathml(xml_text: str) -> dict:
    """Independent, deterministic parser check with no loaded per-case answer fixture."""
    found = catalog_mathml(xml_text)
    for entry in found:
        entry["parse"] = {}
        try:
            entry["symbols"] = sorted(symbols(entry["latex"]))
            entry["parse"] = {"status": "parsed"}
        except MathUndetermined as exc:
            entry["parse"] = {"status": "undetermined", "reason": str(exc)}
    return {"formulas": found, "count": len(found)}

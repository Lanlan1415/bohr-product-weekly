"""Audit for a graphical abstract.

A graphical abstract is not a decoration on the paper; it is a three-part claim
(what was asked, what was done, what was found) compressed into one panel that
readers will see before the paper. So the audit checks the things a reader would
otherwise have to take on trust:

  does it actually state all three parts
  is every number in it present in the source
  is every panel traceable to the material, readable in the intended order,
  and inside the publisher's limits

The second rule is the one that earns its keep. A graphical abstract is where a
number is most likely to be invented or rounded into something more striking than
the data, and it is the least likely place anyone will check against the table.

Malformed input is handled defensively: a field whose type is wrong is treated as
absent (and its absence reported by the rule that checks for it) rather than as a
crash, because a case with one mistyped field still deserves a structured result.
"""

from __future__ import annotations

import re

NUMBER_RE = re.compile(r"[-−–+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

DEFAULT_MAX_WORDS = 60
DEFAULT_TAKEAWAY_KEYS = ("problem", "method", "finding")

# The renderer's default colour when a node declares none; used here so the
# legend audit counts the same colours the drawn figure will actually carry.
DEFAULT_COLOUR = "#56B4E9"


def _numbers_in(text: str) -> set[str]:
    return {m.group(0).replace("−", "-").replace("–", "-") for m in NUMBER_RE.finditer(text)}


def _normalise_num(s: str) -> str:
    """Compare numbers by value, so '5.0' and '5' are the same figure."""
    try:
        v = float(s)
        return f"{v:.10g}"
    except (ValueError, TypeError):
        return str(s)


def _is_seq(v) -> bool:
    return isinstance(v, (list, tuple))


def _two_numbers(v) -> list[float] | None:
    """A two-element numeric pair, or None when the field is malformed."""
    if _is_seq(v) and len(v) == 2:
        try:
            return [float(v[0]), float(v[1])]
        except (TypeError, ValueError):
            return None
    return None


def audit_graphical_abstract(spec: dict, source_values=None) -> dict:
    findings: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    labels = [str(n.get("label", "")) for n in nodes]
    caption = spec.get("caption") if isinstance(spec.get("caption"), str) else ""

    # --- 1. the three-part claim ------------------------------------------
    takeaways = spec.get("takeaways")
    if not isinstance(takeaways, dict):
        # A malformed declaration (a list, a string, a number) declares nothing:
        # the honest reading is "not declared", and the finding says why.
        if takeaways is not None:
            add("ga.missing_takeaway", "high",
                "the takeaways declaration is not an object, so the three-part claim is "
                "not declared", found_type=type(takeaways).__name__)
            takeaways = {}
        else:
            takeaways = {}
    missing = []
    for key in DEFAULT_TAKEAWAY_KEYS:
        want = takeaways.get(key)
        if not want:
            missing.append(key)
            continue
        # Accept a declared panel/node id or the literal text, since either way of
        # pointing at the content is a legitimate authoring choice.
        if str(want) not in labels and not any(str(want) in l for l in labels) \
                and str(want) not in {n.get("id") for n in nodes}:
            add("ga.takeaway_not_placed", "high",
                f"the declared '{key}' takeaway does not appear in any label",
                takeaway=key, declared=str(want))
    if missing:
        add("ga.missing_takeaway", "high",
            "the graphical abstract does not declare all three of problem, method and finding, "
            "so a reader cannot recover the paper's claim from it", missing=missing)

    # --- 1b. every panel must carry readable text --------------------------
    empty = [n.get("id") for n in nodes if not str(n.get("label") or "").strip()]
    if empty:
        add("ga.empty_label", "medium",
            "a panel carries no label text, so it cannot state its takeaway and a reader "
            "cannot tell what the box asserts", nodes=empty[:8], count=len(empty))

    # --- 2. numbers must come from the source -----------------------------
    if source_values is not None and not _is_seq(source_values):
        add("ga.source_values_invalid", "medium",
            "the declared source values are not a list, so the numbers in the abstract "
            "could not be checked against the paper", found_type=type(source_values).__name__)
    elif source_values is not None:
        allowed = {_normalise_num(v) for v in source_values}
        texts = [(l, "label") for l in labels]
        if caption:
            texts.append((caption, "caption"))
        for text, where in texts:
            for num in _numbers_in(text):
                if _normalise_num(num) not in allowed:
                    add("ga.value_not_in_source", "high",
                        "a number drawn in the abstract does not appear in the source values, "
                        "so the figure states a result the data does not contain",
                        number=num, text=text[:60], where=where)
    else:
        add("ga.source_values_unavailable", "medium",
            "no source values were supplied, so the numbers in the abstract could not be checked")

    # --- 3. reading order -------------------------------------------------
    order = spec.get("reading_order")
    node_ids = {n.get("id") for n in nodes}
    if _is_seq(order):
        seq_str = [str(x) for x in order]
        unknown = [x for x in seq_str if x not in node_ids]
        if unknown:
            add("ga.reading_order_unknown_node", "medium",
                "the declared reading order names panels that are not on the canvas, so the "
                "intended sequence cannot be followed", unknown=unknown[:8])
        idx = {nid: i for i, nid in enumerate(seq_str)}
        placed = [n["id"] for n in nodes if n["id"] in idx]
        # Compare the declared order against the left-to-right / top-to-bottom
        # position the layout produced, via the layer field when present.
        placed_seq = sorted(placed, key=lambda nid: idx[nid])
        layers = [next((n.get("layer", 0) for n in nodes if n["id"] == nid), 0)
                  for nid in placed_seq]
        if layers != sorted(layers):
            add("ga.reading_order", "medium",
                "declared reading order does not follow the drawn layout, so a reader will "
                "follow the figure in a different sequence than intended", sequence=placed_seq,
                layers=layers)
    # A malformed order (a bare string, a number) is treated as undeclared: the
    # layout check cannot compare against something that is not a list.

    # --- 4. the flow must exist ------------------------------------------
    if takeaways and len(takeaways) >= 2:
        want_ids = [str(takeaways.get(k)) for k in DEFAULT_TAKEAWAY_KEYS if takeaways.get(k)]
        present = [w for w in want_ids if w in node_ids]
        if len(present) >= 2:
            pairs = {(e.get("from"), e.get("to")) for e in edges}
            linked = any((present[i], present[i + 1]) in pairs for i in range(len(present) - 1))
            if not linked:
                add("ga.takeaway_panels_unlinked", "medium",
                    "the takeaway panels are not connected, so the abstract does not read as a "
                    "progression from question to finding")

    # --- 4b. colour coding needs a legend ----------------------------------
    # A graphical abstract encodes meaning in colour (problem / method / finding are
    # often told apart by colour alone); a figure that draws two or more colours and
    # declares no legend leaves the coding unexplained. Opt out with legend_exempt
    # for figures whose colours are purely decorative.
    legend = spec.get("legend")
    colours = {str(n.get("color") or DEFAULT_COLOUR).lower() for n in nodes}
    legend_ok = _is_seq(legend) and any(str(x).strip() for x in legend)
    if len(colours) >= 2 and not legend_ok and not spec.get("legend_exempt"):
        add("ga.legend_not_declared", "medium",
            "the abstract draws two or more colours but declares no legend, so the colour "
            "coding is unexplained for a reader (and for grey-scale printing)",
            colours=sorted(colours)[:6])

    # --- 5. publisher word limit ------------------------------------------
    max_words_raw = spec.get("max_words", DEFAULT_MAX_WORDS)
    try:
        max_words = int(max_words_raw)
    except (TypeError, ValueError):
        max_words = DEFAULT_MAX_WORDS
    total_words = sum(len(l.split()) for l in labels) + len(caption.split())
    if total_words > max_words:
        add("ga.text_too_long", "medium",
            "the abstract carries more text than the declared limit, so it will be shrunk or "
            "truncated by the publisher", words=total_words, limit=max_words)

    # --- 6. physical size -------------------------------------------------
    dims = _two_numbers(spec.get("canvas_mm"))
    lim = _two_numbers(spec.get("size_limit_mm"))
    if dims and lim:
        w_ok = dims[0] <= lim[0]
        h_ok = dims[1] <= lim[1]
        if not (w_ok and h_ok):
            add("ga.size_out_of_spec", "medium",
                "the canvas exceeds the publisher's stated maximum",
                canvas_mm=spec.get("canvas_mm"), size_limit_mm=spec.get("size_limit_mm"))

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "graphical-abstract/v1",
        "findings": findings,
        "severity_counts": counts,
        "checked": {"nodes": len(nodes), "edges": len(edges), "words": total_words,
                    "takeaways_declared": sorted(k for k in DEFAULT_TAKEAWAY_KEYS
                                                 if takeaways.get(k)),
                    "colours": len(colours), "legend_declared": bool(legend_ok)},
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
    }

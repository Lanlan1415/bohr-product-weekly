"""Provenance checks shared by the diagram skills.

Three questions, the same three for any figure whose parts come from a described
experiment:

  does every drawn entity name the material item that calls for it
  is every drawn connection stated by the source
  does every material in the list actually appear

They live here rather than in one skill because apparatus diagrams, mechanism
diagrams and graphical abstracts all get the same deduction for the same fault: a
figure that looks complete while containing a part nobody can find in the methods.

A rule only fires when the case supplies the corresponding source list. Without it the
audit cannot tell a fabricated component from an unwitnessed one, and saying nothing is
more honest than guessing.
"""

from __future__ import annotations


def _add(findings, rule, severity, message, **extra):
    findings.append({"rule": rule, "severity": severity, "message": message, **extra})


def audit_provenance(spec: dict, nodes: list[dict] | None = None,
                     edges: list[dict] | None = None,
                     expect_connections: bool = True) -> dict:
    """Return findings plus a coverage summary, or checked=False when no source list."""
    nodes = nodes if nodes is not None else (spec.get("nodes") or [])
    edges = edges if edges is not None else (spec.get("edges") or [])
    findings: list[dict] = []

    materials = spec.get("materials")
    if not materials:
        return {"findings": findings, "checked": False,
                "reason": "no material list supplied, so provenance was not checked",
                "coverage": None}

    known = {str(m.get("id") or m): m for m in materials}

    for n in nodes:
        ev = str(n.get("evidence") or "").strip()
        label = str(n.get("label") or "")[:40]
        if not ev:
            _add(findings, "trace.entity_untraceable", "high",
                 "a drawn entity carries no reference to the material that calls for it, so a "
                 "reader cannot tell whether it belongs in the figure",
                 node=n["id"], label=label)
        elif ev not in known:
            _add(findings, "trace.evidence_not_in_materials", "high",
                 "an entity points at a material item that does not exist",
                 node=n["id"], evidence=ev)

    drawn = {str(n.get("evidence") or "").strip() for n in nodes}
    unused = sorted(set(known) - drawn)
    if unused:
        _add(findings, "trace.material_not_drawn", "medium",
             "a material the source requires never appears in the figure, so the drawing does "
             "not show the full setup", unused=unused[:10], count=len(unused))

    declared = {(str(c.get("from")), str(c.get("to"))) for c in (spec.get("connections") or [])}
    if declared:
        for e in edges:
            if (str(e.get("from")), str(e.get("to"))) not in declared:
                _add(findings, "trace.edge_not_in_source", "high",
                     "a connection is drawn that the source material does not state",
                     edge=[e.get("from"), e.get("to")])
        used = {(str(e.get("from")), str(e.get("to"))) for e in edges}
        absent = sorted(declared - used)
        if absent:
            _add(findings, "trace.connection_not_drawn", "medium",
                 "a connection the source states is missing from the figure",
                 missing=[list(p) for p in absent[:10]], count=len(absent))
    elif expect_connections:
        # Not every figure type has a wiring list. A graphical abstract expresses its
        # progression through reading order rather than through stated connections, so
        # the caller says which it is instead of the rule guessing.
        _add(findings, "trace.no_connection_list", "low",
             "the case declares materials but no connection list, so drawn connections could "
             "not be checked against the source")

    return {
        "findings": findings,
        "checked": True,
        "coverage": {
            "materials_declared": len(known),
            "materials_drawn": len(drawn & set(known)),
            "entities": len(nodes),
            "entities_traced": sum(1 for n in nodes if str(n.get("evidence") or "").strip() in known),
            "connections_declared": len(declared),
            "connections_drawn": len({(str(e.get("from")), str(e.get("to"))) for e in edges} & declared)
            if declared else None,
        },
    }


def check_numbering(spec: dict, nodes: list[dict] | None = None) -> list[dict]:
    """Step numbers must follow the order the source text presents them in.

    A route whose numbering disagrees with the prose is the failure "步骤编号与正文顺序
    错位": the figure is internally consistent and still tells a different story from
    the text.
    """
    nodes = nodes if nodes is not None else (spec.get("nodes") or [])
    order = spec.get("step_order")
    if not order:
        return []
    seq = [str(x) for x in order]
    findings: list[dict] = []
    for n in nodes:
        st = n.get("stage")
        if st is None or str(n["id"]) not in seq:
            continue
        pos = seq.index(str(n["id"])) + 1
        if int(st) != pos:
            _add(findings, "route.numbering_vs_text", "medium",
                 "a step's number disagrees with the order the text presents it in",
                 node=n["id"], stage=int(st), text_position=pos)
    return findings


def check_deterministic(spec: dict, render_fn, tmp_dir=None) -> dict:
    """Render twice and compare the structural fingerprint.

    The third judging criterion for these figures is that a reader can re-run the skill
    and get the same figure, so this is measured rather than assumed.
    """
    import re
    import tempfile
    from pathlib import Path

    def signature(svg_path) -> tuple:
        txt = Path(svg_path).read_text(encoding="utf-8", errors="replace")
        text = sorted(re.findall(r">([^<>]{1,200})</text>", txt))
        geom = sorted(re.findall(r'\bd="([^"]+)"', txt))
        trans = sorted(re.findall(r'<(?:rect|path|g)[^>]*?transform="([^"]*)"', txt))
        return (tuple(text), tuple(geom), tuple(trans))

    # Probe renders go to the system temp directory, never to the output directory:
    # the caller's out_dir is a deliverable, and two scratch renders per run would
    # leave det1_*/det2_* folders in it.
    sigs = []
    for run in (1, 2):
        d = Path(tempfile.mkdtemp(prefix=f"deckprobe{run}_"))
        built = render_fn(spec, d / "figure")
        sigs.append(signature(built["svg"]))
        try:
            import matplotlib.pyplot as plt
            plt.close(built["fig"])
        except Exception:
            pass
    same = sigs[0] == sigs[1]
    return {"deterministic": same,
            "detail": {} if same else {"text_differs": sigs[0][0] != sigs[1][0],
                                       "geometry_differs": sigs[0][1] != sigs[1][1],
                                       "transform_differs": sigs[0][2] != sigs[1][2]},
            "note": "two renders of the same spec, compared on text and geometry only"}

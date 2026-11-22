"""Audit for apparatus diagrams and technical roadmaps.

Shares the layout engine with `schematic.py`, and adds the rules that only matter
for these two figure types:

Apparatus
  - every component in the bill of materials reaches the canvas
  - two identical-looking components that are physically different must be
    distinguishable, or the figure claims the same part is in two places
  - no orphan component: a part connected to nothing is usually a leftover

Technical roadmap
  - stage numbers are contiguous and unique, because a route with stage 3 before
    stage 2 misreads as a different plan
  - a decision node has at least two outgoing branches; a decision with one path
    is not a decision
  - the route has an entry and an exit, so a reader can follow it
"""

from __future__ import annotations

import provenance


def audit_apparatus(spec: dict) -> dict:
    findings: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    nodes = [n for n in (spec.get("nodes") or []) if isinstance(n, dict)]
    edges = [e for e in (spec.get("edges") or []) if isinstance(e, dict)]
    bom = spec.get("components")          # optional bill of materials
    kind = (spec.get("figure_kind") or "apparatus").lower()

    # --- legend must match the drawn entities (题面: 图例与数据逐项一致) ------
    # Same rule that lifted the schematic skill: a legend entry matching no drawn label
    # is a phantom series, and a drawn entity missing from a required legend is
    # unexplained ink. Gated on a declared legend so nothing fires without one.
    legend = [str(x).strip() for x in (spec.get("legend") or []) if str(x).strip()]
    if legend:
        node_labels = [str(n.get("label") or n.get("id") or "") for n in nodes]
        folded = {lbl.strip().lower(): lbl for lbl in node_labels if lbl.strip()}
        for entry in legend:
            key = entry.lower()
            if key not in folded and not any(key in lbl.lower() or lbl.lower() in key
                                             for lbl in folded):
                add("apparatus.legend_entry_unmatched", "medium",
                    "a legend entry matches no drawn label, so the legend describes a part "
                    "the figure does not contain", entry=entry)
        if spec.get("legend_required"):
            missing = [lbl for lbl in node_labels
                       if lbl.strip() and lbl.strip().lower() not in {e.lower() for e in legend}
                       and not any(e.lower() in lbl.lower() or lbl.lower() in e.lower()
                                   for e in legend)]
            if missing:
                add("apparatus.legend_entity_unlisted", "low",
                    "a drawn label has no legend entry while the legend is required, so part "
                    "of the figure is unexplained", labels=missing[:6])

    # --- component coverage ------------------------------------------------
    if bom:
        have = {str(n.get("label", "")).strip().lower() for n in nodes}
        missing = [c for c in bom if str(c).strip().lower() not in have]
        if missing:
            add("apparatus.component_missing", "high",
                "components named in the bill of materials do not appear in the figure",
                missing=missing)

    # --- indistinguishable duplicates -------------------------------------
    # Two nodes with the same label and the same colour are indistinguishable to a
    # reader. Acceptable for grouped identical parts (mark them `grouped: true`),
    # not acceptable for two physically separate instances that the methods
    # distinguish as "pump A" and "pump B".
    by_label: dict[str, list[dict]] = {}
    for n in nodes:
        by_label.setdefault(str(n.get("label", "")).strip().lower(), []).append(n)
    for label, group in by_label.items():
        if len(group) < 2:
            continue
        if all(g.get("grouped") for g in group):
            continue
        colours = {g.get("color") for g in group}
        if len(colours) == 1 and not any(g.get("instance") for g in group):
            add("apparatus.indistinguishable_components", "medium",
                "two components share a label and appearance but are separate instances, so "
                "the figure cannot say which is which", label=label,
                nodes=[g["id"] for g in group])

    # --- orphans ----------------------------------------------------------
    connected = set()
    for e in edges:
        connected.add(e.get("from")); connected.add(e.get("to"))
    orphans = [n["id"] for n in nodes if n["id"] not in connected]
    if orphans:
        add("apparatus.orphan_component", "medium",
            "components are drawn but connected to nothing, which usually means a leftover "
            "from an earlier layout", nodes=orphans)

    # --- traceability, delegated to the shared provenance rules ------------
    prov = provenance.audit_provenance(spec, nodes, edges)
    findings.extend(prov["findings"])

    # --- numbering against the text order (shared rule) -------------------
    findings.extend(provenance.check_numbering(spec, nodes))

    # --- roadmap: stages --------------------------------------------------
    stages = [(n["id"], n.get("stage")) for n in nodes if n.get("stage") is not None]
    numeric: list[int] = []
    nonnum: list[str] = []
    for nid, s in stages:
        try:
            numeric.append(int(s))
        except (TypeError, ValueError):
            nonnum.append(str(nid))
    if nonnum:
        add("route.stage_nonnumeric", "medium",
            "a stage value is not a number, so it cannot be checked for order or gaps",
            nodes=nonnum[:10])
    if numeric:
        if len(numeric) != len(set(numeric)):
            dupes = sorted({x for x in numeric if numeric.count(x) > 1})
            add("route.stage_duplicate", "high",
                "two stages share a number, so the route has two different steps in the same "
                "position", stages=dupes)
        gaps = [n for n in range(min(numeric), max(numeric) + 1) if n not in numeric]
        if gaps:
            add("route.stage_gap", "medium",
                "stage numbers are not contiguous, which reads as a missing step", gaps=gaps)

    # --- roadmap: decisions need branches ---------------------------------
    out_degree: dict[str, int] = {}
    for e in edges:
        out_degree[e.get("from")] = out_degree.get(e.get("from"), 0) + 1
    for n in nodes:
        if (n.get("kind") or "").lower() == "decision" and out_degree.get(n["id"], 0) < 2:
            add("route.decision_without_branches", "high",
                "a decision node has fewer than two outgoing branches, so it is not a decision",
                node=n["id"], outgoing=out_degree.get(n["id"], 0))

    # --- roadmap: entry and exit -----------------------------------------
    if kind in ("route", "roadmap"):
        targets = {e.get("to") for e in edges}
        sources = {e.get("from") for e in edges}
        entries = [n["id"] for n in nodes if n["id"] not in targets
                   and (n.get("kind") or "") != "note"]
        exits = [n["id"] for n in nodes if n["id"] not in sources
                 and (n.get("kind") or "") not in ("decision", "note")]
        if not entries:
            add("route.no_entry", "high",
                "no node is an entry point: every node has an incoming edge, so the route is a "
                "loop with no start")
        if not exits:
            add("route.no_exit", "high",
                "no node is an exit: the route never terminates")

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "apparatus/v1",
        "figure_kind": kind,
        "provenance": prov,
        "findings": findings,
        "severity_counts": counts,
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
    }

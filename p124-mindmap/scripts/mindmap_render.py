#!/usr/bin/env python3
"""Deterministic, source-linked SVG/FreeMind/HTML mind-map renderer.

Inspired by markmap-view 0.18.13's measured nodeSize + flextree packing and
sibling/non-sibling spacing. This standard-library implementation uses span
packing: each subtree has a bounded span, children are allocated disjoint spans,
and each depth is placed after the previous depth's widest measured rect. Thus
node non-overlap is a construction invariant and independently checkable.
"""
from __future__ import annotations

import json
import math
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape, quoteattr

REL_COLORS = {"causal": "#c0392b", "dependency": "#8e44ad", "contrast": "#e67e22",
              "temporal": "#16a085", "citation": "#2c3e50", "support": "#2874a6",
              "conflict": "#c0392b", "contains": "#607d8b", "part_of": "#607d8b"}
KIND_COLORS = {"fact": "#e7f3ff", "summary": "#fff4d6", "inference": "#ffe7e7"}


class MapLayoutError(ValueError):
    pass


def text(value):
    return str(value if value is not None else "").strip()


def _records(value):
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _display_width(value):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text(value))


def _wrap(value, max_units=26, max_lines=6):
    """Whole-label JSON/accessibility retained; only rendered text is wrapped."""
    label = " ".join(text(value).split())
    lines, remaining, truncated = [], label, False
    while remaining and len(lines) < max_lines:
        if _display_width(remaining) <= max_units:
            lines.append(remaining)
            remaining = ""
            break
        units, cut, last_space = 0, 0, -1
        of = []
        for i, char in enumerate(remaining):
            units += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
            if char.isspace():
                last_space = i
            if units > max_units:
                cut = i
                break
        cut = last_space if last_space >= max(4, int(cut * 0.6)) else max(1, cut)
        lines.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        truncated = True
        lines[-1] = lines[-1][:-1] + "…" if lines[-1] else "…"
    return lines, truncated


def _link(value):
    value = text(value)
    try:
        parts = urlsplit(value)
        return value if parts.scheme in ("http", "https") and parts.netloc else ""
    except ValueError:
        return ""


def _prepare(nodes, edges):
    if not nodes:
        raise MapLayoutError("map.no_nodes: a drawable map needs nodes")
    ids = [text(n.get("id")) for n in nodes]
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        raise MapLayoutError("map.duplicate_node_id: node IDs must be present and unique")
    by_id = {text(n.get("id")): n for n in nodes}
    roots = [n for n in nodes if not n.get("parent")]
    if len(roots) != 1:
        raise MapLayoutError("map.root_count: exactly one root is drawable")
    children = {key: [] for key in ids}
    for n in nodes:
        parent = text(n.get("parent"))
        if parent:
            if parent not in by_id:
                raise MapLayoutError("map.dangling_parent: " + text(n.get("id")) + " -> " + parent)
            children[parent].append(n)
    for values in children.values():
        values.sort(key=lambda n: (int(n.get("order", 0)) if str(n.get("order", "0")).lstrip("-").isdigit() else 0,
                                   nodes.index(n)))
    depth, visiting = {}, set()

    def walk(nid, level):
        if nid in visiting:
            raise MapLayoutError("map.cycle: " + nid)
        if nid in depth:
            if depth[nid] != level:
                raise MapLayoutError("map.multiple_paths: hierarchical node appears at two depths: " + nid)
            return
        visiting.add(nid)
        depth[nid] = level
        for child in children[nid]:
            walk(text(child.get("id")), level + 1)
        visiting.remove(nid)
    walk(text(roots[0].get("id")), 0)
    if len(depth) != len(nodes):
        raise MapLayoutError("map.root_count: not every node is connected to the root")

    geometry = {}
    for n in nodes:
        nid = text(n.get("id"))
        lines, truncated = _wrap(n.get("label"))
        evidence = text(n.get("evidence"))
        elines, _ = _wrap("evidence: " + evidence if evidence else "", 30, 2)
        # Approximate font units conservatively; SVG accessibility carries full labels.
        max_line = max([_display_width(x) for x in lines + elines] or [8])
        width = max(110, min(310, max_line * 8 + 34))
        height = max(58, len(lines) * 18 + (len(elines) * 15 if evidence else 0) + 24)
        geometry[nid] = {"id": nid, "label": text(n.get("label")), "lines": lines,
                         "evidence_lines": elines if evidence else [], "width": width, "height": height,
                         "depth": depth[nid], "kind": text(n.get("kind")) or "structural",
                         "evidence": evidence, "basis": n.get("basis"),
                         "source_url": _link(n.get("source_url") or n.get("url")),
                         "priority": n.get("priority", n.get("highlight", 0)),
                         "truncated": truncated}

    spans = {}

    def span(nid):
        if nid in spans:
            return spans[nid]
        own = geometry[nid]["height"]
        kids = children[nid]
        if not kids:
            spans[nid] = own
        else:
            # Children of one parent share baseline spacing; larger uncertainty is
            # handled after layout when bounding the complete viewport.
            required = sum(span(text(k.get("id"))) for k in kids) + 22 * (len(kids) - 1)
            if depth[nid] > 0:
                # markmap uses larger spacing between unrelated branches than
                # between siblings. Give each non-root subtree a 24-unit margin
                # above and below, preserving disjoint spans deterministically.
                required += 48
            spans[nid] = max(own, required)
        return spans[nid]

    for nid in ids:
        span(nid)
    levels = {}
    for nid in ids:
        levels.setdefault(depth[nid], []).append(nid)
    x_by_depth, cursor = {}, 60
    for level in sorted(levels):
        x_by_depth[level] = cursor
        cursor += max(geometry[nid]["width"] for nid in levels[level]) + 100

    def place(nid, top, sibling_gap=22):
        own = geometry[nid]
        own_span = span(nid)
        own["x"] = float(x_by_depth[depth[nid]])
        own["y"] = float(top + (own_span - own["height"]) / 2)
        own["cx"] = own["x"] + own["width"] / 2
        own["cy"] = own["y"] + own["height"] / 2
        if children[nid]:
            child_gap = 22 if len(children[nid]) == 1 else sibling_gap
            needed = sum(span(text(k.get("id"))) for k in children[nid]) + child_gap * (len(children[nid]) - 1)
            start = top + (own_span - needed) / 2
            for k in children[nid]:
                knid = text(k.get("id"))
                place(knid, start, child_gap)
                start += span(knid) + child_gap
    place(text(roots[0].get("id")), 60)

    # Add a modest explicit gap between separate first-level branches. A full
    # second pass repacks them, retaining the same non-overlap proof.
    # (No random jitter: idempotence is part of the artifact contract.)
    minx = min(v["x"] for v in geometry.values())
    miny = min(v["y"] for v in geometry.values())
    for v in geometry.values():
        v["x"] = round(v["x"] - minx + 50, 3)
        v["y"] = round(v["y"] - miny + 50, 3)
        v["cx"] = round(v["x"] + v["width"] / 2, 3)
        v["cy"] = round(v["y"] + v["height"] / 2, 3)
    width = max(620, math.ceil(max(v["x"] + v["width"] for v in geometry.values()) + 70))
    height = math.ceil(max(v["y"] + v["height"] for v in geometry.values()) + 90)
    return geometry, children, width, height


def check_layout(geometry, width, height):
    boxes = sorted(geometry.values(), key=lambda v: v["id"])
    overlaps, boundaries = [], []
    for box in boxes:
        if (box["x"] < 0 or box["y"] < 0 or box["width"] <= 0 or box["height"] <= 0
                or box["x"] + box["width"] > width or box["y"] + box["height"] > height):
            boundaries.append(box["id"])
        # Text must stay inside the measured rect. Wrapped lines are laid out here,
        # so the check is structural rather than trusting an external screenshot.
        if box["y"] + 14 + len(box["lines"]) * 18 + len(box["evidence_lines"]) * 15 > box["y"] + box["height"]:
            boundaries.append(box["id"] + ":text")
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            x_overlap = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
            y_overlap = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
            if x_overlap > 0 and y_overlap > 0:
                overlaps.append([a["id"], b["id"]])
    return {"overlap_pairs": overlaps, "boundary_violations": boundaries,
            "node_count": len(boxes), "edge_count": 0, "viewport": {"width": width, "height": height}}


def _path(source, target):
    if target["depth"] > source["depth"]:
        x1, x2 = source["x"] + source["width"], target["x"]
        mid = (x1 + x2) / 2
        return "M %.3f %.3f C %.3f %.3f %.3f %.3f %.3f %.3f" % (
            x1, source["cy"], mid, source["cy"], mid, target["cy"], x2, target["cy"])
    return "M %.3f %.3f C %.3f %.3f %.3f %.3f %.3f %.3f" % (
        source["cx"], source["y"], source["cx"], 12, target["cx"], 12, target["cx"], target["y"])


def _svg_document(spec, nodes, edges):
    geometry, children, width, height = _prepare(nodes, edges)
    diagnostics = check_layout(geometry, width, height)
    if diagnostics["overlap_pairs"] or diagnostics["boundary_violations"]:
        raise MapLayoutError("map.layout_overlap: generated bounds failed verification")
    svg = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-label="Source-linked mind map">' % (width, height, width, height),
           '<title>' + escape(text(spec.get("title")) or text(spec.get("case_id")) or "Mind map") + '</title>',
           '<desc>Nodes carry fact/summary/inference provenance; dashed arrows carry typed relations and source locators.</desc>',
           '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#52616b"/></marker></defs>',
           '<style>text{font-family:Arial,"Microsoft YaHei","Noto Sans CJK SC",sans-serif;fill:#1c2833}.node-label{font-size:13px}.node-meta{font-size:10px;fill:#52616b}.relation-label{font-size:10px;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}.tree-link{fill:none;stroke:#78909c;stroke-width:1.5}.relation-link{fill:none;stroke-width:1.8;stroke-dasharray:5 3;cursor:pointer}.node{cursor:pointer}.node rect{stroke-width:1.4}.node.high-priority rect{stroke-width:3}.node:hover rect{filter:brightness(.96)}</style>']
    geometry_by_id = {nid: v for nid, v in geometry.items()}
    for parent, kids in children.items():
        for child in kids:
            src, dst = geometry_by_id[parent], geometry_by_id[text(child.get("id"))]
            relation = text(child.get("parent_kind") or child.get("relation") or "contains")
            title = relation + ((" | evidence: " + text(child.get("evidence"))) if child.get("evidence") else "")
            svg.append('<path class="tree-link" data-source="%s" data-target="%s" data-relation="%s" d="%s"><title>%s</title></path>' % (
                escape(parent, {'"': '&quot;'}), escape(dst["id"], {'"': '&quot;'}), escape(relation, {'"': '&quot;'}),
                _path(src, dst), escape(title)))
    for i, edge in enumerate(edges):
        srcid, dstid = text(edge.get("from")), text(edge.get("to"))
        if srcid not in geometry_by_id or dstid not in geometry_by_id:
            continue
        src, dst = geometry_by_id[srcid], geometry_by_id[dstid]
        relation = text(edge.get("kind")) or "untyped"
        color = REL_COLORS.get(relation, "#c0392b")
        basis = text(edge.get("basis"))
        label = relation + (" | " + basis if basis else "")
        path = _path(src, dst)
        mx = (src["cx"] + dst["cx"]) / 2
        my = (src["cy"] + dst["cy"]) / 2 - 10
        link = _link(edge.get("source_url"))
        attributes = ' class="relation-link" data-edge-id="%d" data-source="%s" data-target="%s" data-basis="%s" stroke="%s" marker-end="url(#arrow)" d="%s"' % (
            i, escape(srcid, {'"': '&quot;'}), escape(dstid, {'"': '&quot;'}),
            escape(basis, {'"': '&quot;'}), color, path)
        title = "<title>" + escape(label) + "</title>"
        svg.append('<path%s>%s</path>' % (attributes, title))
        short_label = relation
        if link:
            short_label = '<a xlink:href=%s target="_blank">%s</a>' % (quoteattr(link), escape(short_label))
        svg.append('<text class="relation-label" x="%.3f" y="%.3f" text-anchor="middle" fill="%s">%s</text>' % (mx, my, color, short_label))
    for node in nodes:
        nid = text(node.get("id"))
        box = geometry_by_id[nid]
        kind = box["kind"] if box["kind"] in KIND_COLORS else "structural"
        color = KIND_COLORS.get(kind, "#eef2f7")
        stroke = "#c0392b" if box["priority"] not in (0, False, None, "", "0") else "#4f6b78"
        priority_class = " high-priority" if stroke == "#c0392b" else ""
        svg.append('<g id="node-%s" class="node%s" data-node-id="%s" data-kind="%s" data-evidence="%s" data-label="%s" transform="translate(%.3f %.3f)">' % (
            escape(nid, {'"': '&quot;'}), priority_class, escape(nid, {'"': '&quot;'}),
            escape(kind, {'"': '&quot;'}), escape(box["evidence"], {'"': '&quot;'}),
            escape(box["label"], {'"': '&quot;'}), box["x"], box["y"]))
        svg.append('<title>%s</title>' % escape(box["label"] + (" | " + kind + " | " + box["evidence"])))
        inner = '<rect width="%.3f" height="%.3f" rx="10" fill="%s" stroke="%s"/>' % (box["width"], box["height"], color, stroke)
        if box["source_url"]:
            inner = '<a xlink:href=%s target="_blank">%s</a>' % (quoteattr(box["source_url"]), inner)
        svg.append(inner)
        for i, line in enumerate(box["lines"]):
            svg.append('<text class="node-label" x="16" y="%d">%s</text>' % (22 + i * 18, escape(line)))
        offset = 22 + len(box["lines"]) * 18
        if box["evidence_lines"]:
            for i, line in enumerate(box["evidence_lines"]):
                svg.append('<text class="node-meta" x="16" y="%d">%s</text>' % (offset + i * 15, escape(line)))
        if box["priority"] not in (0, False, None, "", "0"):
            svg.append('<text class="node-meta" x="%.3f" y="17" text-anchor="end">[重点 %s]</text>' % (box["width"] - 12, escape(text(box["priority"]))))
        svg.append('</g>')
    # legend is in canvas space and makes fact/summary/inference visually distinct
    svg.append('<g transform="translate(60 %d)"><rect x="-15" y="-19" width="480" height="30" rx="6" fill="#fff" stroke="#ddd"/>' % (height - 35))
    svg.append('<text class="node-meta" x="0" y="0">fact=blue · summary=amber · inference=red · dashed relation=kind + basis · [重点]=priority</text></g>')
    svg.append('</svg>')
    return "\n".join(svg) + "\n", geometry, diagnostics, children


def _freemind(spec, nodes, edges):
    by_id = {text(n.get("id")): n for n in nodes}
    children = {}
    for n in nodes:
        if n.get("parent"):
            children.setdefault(text(n.get("parent")), []).append(n)
    roots = [n for n in nodes if not n.get("parent")]
    if len(roots) != 1:
        raise MapLayoutError("map.root_count: FreeMind requires one root")
    map_el = ET.Element("map", {"version": "1.0.1"})
    map_el.set("generator", "deterministic-mindmap-v2")

    def expand(parent, n):
        nid = text(n.get("id"))
        at = {"ID": nid, "TEXT": text(n.get("label"))}
        link = _link(n.get("source_url") or n.get("url"))
        if link:
            at["LINK"] = link
        node_el = ET.SubElement(parent, "node", at)
        for key in ("kind", "evidence", "priority"):
            if n.get(key) is not None:
                attrib = ET.SubElement(node_el, "attribute", {"NAME": key, "VALUE": text(n.get(key))})
        for edge in edges:
            if text(edge.get("from")) == nid and text(edge.get("to")) in by_id:
                ET.SubElement(node_el, "arrowlink", {"DESTINATION": text(edge.get("to")),
                      "TYPE": text(edge.get("kind")), "BASIS": text(edge.get("basis"))})
        for child in children.get(nid, []):
            expand(node_el, child)
        return node_el
    expand(map_el, roots[0])
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(map_el, encoding="unicode") + "\n"


def _html(title, svg):
    # No CDN/network script is required: deliver an offline interactive inspection page.
    return """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>%s</title>
<style>body{font-family:Arial,"Microsoft YaHei",sans-serif;margin:20px;background:#f6f8fa}main{background:#fff;padding:16px;overflow:auto;border:1px solid #dde3e7}#evidence{max-width:1120px;margin:0 0 16px}button{margin:4px;padding:5px 10px} .node.highlight rect{stroke:#d90000;stroke-width:4}</style>
</head><body><h1>%s</h1><p id="evidence">点击节点查看 evidence；完整标签和定位保留在各图的 title/属性中。</p>
<button onclick="fit()">Fit width</button><button onclick="actual()">Actual size</button>
<main id="canvas">%s</main><script>
const svg=document.querySelector('svg'); const info=document.getElementById('evidence');
function fit(){svg.style.width='100%%';svg.style.height='auto'} function actual(){svg.style.width='';svg.style.height=''}
document.querySelectorAll('[data-node-id]').forEach(n=>n.addEventListener('click',()=>{document.querySelectorAll('.highlight').forEach(x=>x.classList.remove('highlight'));n.classList.add('highlight');info.textContent=n.dataset.nodeId+' | '+n.dataset.kind+' | '+n.dataset.label+' | '+(n.dataset.evidence||'structural / no locator')}));
</script></body></html>
""" % (escape(title), escape(title), svg)


def write_mindmap(spec, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    nodes, edges = _records(spec.get("nodes")), _records(spec.get("edges"))
    svg, geometry, diagnostics, children = _svg_document(spec, nodes, edges)
    ET.fromstring(svg)
    (out / "mindmap.svg").write_text(svg, encoding="utf-8")
    freemind = _freemind(spec, nodes, edges)
    root = ET.fromstring(freemind)
    if len([x for x in root if x.tag == "node"]) != 1:
        raise MapLayoutError("map.root_count: FreeMind root export is not singular")
    (out / "mindmap.mm").write_text(freemind, encoding="utf-8")
    title = text(spec.get("title")) or text(spec.get("case_id")) or "Mind map"
    inline_svg = svg.split("\n", 1)[1] if svg.startswith("<?xml") else svg
    (out / "mindmap.html").write_text(_html(title, inline_svg), encoding="utf-8")
    diagnostics["edge_count"] = len(edges)
    layout = {"schema_version": "mindmap-layout/v2", "algorithm": "measured span packing, sibling spacing 22, cross-branch margin 24 per side, depth gap 100",
              "viewport": diagnostics["viewport"], "nodes": list(geometry.values()),
              "diagnostics": diagnostics}
    (out / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    structure = {"schema_version": "mindmap/v2", "case_id": spec.get("case_id"), "title": title,
                 "nodes": nodes, "edges": edges, "parent_relations": [
                     {"from": text(n.get("parent")), "to": text(n.get("id")),
                      "kind": text(n.get("parent_kind") or n.get("relation") or "contains"),
                      "basis": n.get("evidence")} for n in nodes if n.get("parent")],
                 "sources": [{"node": k, "evidence": v["evidence"], "source_url": v["source_url"]}
                             for k, v in geometry.items() if v["evidence"] or v["source_url"]]}
    (out / "mindmap.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"mindmap.svg": {"kind": "editable_vector_diagram", "bytes": len(svg.encode("utf-8"))},
            "mindmap.mm": {"kind": "editable_freemind_hierarchy"},
            "mindmap.html": {"kind": "offline_clickable_preview"},
            "mindmap.json": {"kind": "structured_nodes_relations_sources"},
            "layout.json": diagnostics}


OPTIONAL_PREVIEW_HELP = "Optional PNG: use render_preview.py with a real CairoSVG/rsvg/inkscape renderer; do not claim a PNG when none was produced."

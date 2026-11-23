"""Render a schematic diagram from a declarative spec, then audit the result.

Two separate jobs, deliberately kept apart:

  render  — spec (nodes, edges, groups) -> matplotlib Figure -> SVG + PNG
  audit   — Figure + spec -> findings

The audit is the part that matters. A drawing can look finished and still be
wrong: a label overlaps its neighbour, an arrow points backwards, an entity the
source text described never made it onto the canvas, the export is a raster when
it had to be an editable vector. None of that is visible in the PNG at a glance,
and a base agent cannot check it about its own output.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

# Okabe-Ito: distinguishable under the common forms of colour-vision deficiency.
# Anything outside this set is reported, because a figure whose meaning depends on
# telling red from green is unreadable for ~8% of male readers.
OKABE_ITO = {
    "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442",
    "blue": "#0072B2", "vermillion": "#D55E00", "purple": "#CC79A7", "grey": "#999999",
    "black": "#000000",
}
_SAFE_HEX = {v.lower() for v in OKABE_ITO.values()}

EDGE_STYLES = {
    "activate": dict(arrowstyle="-|>", color="#0072B2"),
    "inhibit": dict(arrowstyle="-[", color="#D55E00"),
    "flow": dict(arrowstyle="-|>", color="#555555"),
    "bind": dict(arrowstyle="-", color="#009E73", linestyle="--"),
}

# Apparatus-specific channels: these describe what moves, not just that an arrow exists.
FLOW_KIND_STYLES = {
    "material": dict(color="#555555", linestyle="-"),
    "energy": dict(color="#E69F00", linestyle="-"),
    "information": dict(color="#0072B2", linestyle="--"),
    "waste": dict(color="#D55E00", linestyle=":"),
}
FLOW_KIND_LEGEND = {
    "material": "material flow / 物料流：灰色实线",
    "energy": "energy flow / 能量流：橙色实线",
    "information": "information flow / 信息流：蓝色虚线",
    "waste": "waste outlet / 废物流：红色点线",
}
EDGE_TYPE_LEGEND = {
    "flow": "directed connection / 有向连接",
    "activate": "activate / 推进：蓝色箭头",
    "inhibit": "inhibit / 阻止：红色 T 端",
    "bind": "association / 关联：绿色虚线",
}


def _text_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value if str(x).strip()]
    return []


def _valid_nodes(raw) -> tuple[list[dict], list]:
    if not isinstance(raw, list):
        return [], [raw]
    valid, bad, seen = [], [], set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) \
                or not item["id"].strip() or item["id"] in seen:
            bad.append(item if not isinstance(item, dict) else item.get("id"))
            continue
        seen.add(item["id"])
        valid.append(item)
    return valid, bad


def _valid_edges(raw) -> tuple[list[dict], list]:
    if not isinstance(raw, list):
        return [], [raw]
    valid, bad = [], []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("from"), str) \
                or not isinstance(item.get("to"), str):
            bad.append(item)
        else:
            valid.append(item)
    return valid, bad


def _layers(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """Longest-path layering, so arrows point forward and cycles are surfaced.

    Nodes may declare `layer` explicitly; the rest are placed after their
    parents. A cycle would otherwise recurse forever, so depth is capped and the
    back-edges are reported by the audit rather than silently mangled.
    """
    decl = {n["id"]: n.get("layer") for n in nodes}
    parents: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        if e["to"] in parents and e["from"] in parents:
            parents[e["to"]].append(e["from"])

    depth: dict[str, int] = {}

    def resolve(nid: str, seen: frozenset[str] = frozenset()) -> int:
        if nid in depth:
            return depth[nid]
        if decl.get(nid) is not None:
            depth[nid] = int(decl[nid])
            return depth[nid]
        if nid in seen or len(seen) > 64:
            return 0
        ps = parents.get(nid) or []
        d = 0 if not ps else 1 + max(resolve(p, seen | {nid}) for p in ps)
        depth[nid] = d
        return d

    for n in nodes:
        resolve(n["id"])
    return depth


def render(spec: dict, out_stem: Path, dpi: int = 300, fonttype: str = "none") -> dict:
    """Write editable SVG, 300-dpi PNG and embedded-font PDF from one spec."""
    matplotlib.rcParams["svg.fonttype"] = fonttype
    matplotlib.rcParams["pdf.fonttype"] = 42

    # Pick a font that can draw the labels before drawing anything: matplotlib's
    # default has no CJK glyphs, so a Chinese label silently becomes empty boxes.
    import fontsel
    font = fontsel.resolve(fontsel.labels_text(spec))
    if font.path:
        try:
            from matplotlib import font_manager
            font_manager.fontManager.addfont(font.path)
            matplotlib.rcParams["font.family"] = [font.family]
        except Exception:
            pass

    nodes, malformed_nodes = _valid_nodes(spec.get("nodes") or [])
    edges, malformed_edges = _valid_edges(spec.get("edges") or [])
    if not nodes:
        raise ValueError("spec has no drawable nodes")
    node_ids = {n["id"] for n in nodes}
    dangling = [e for e in edges if e["from"] not in node_ids or e["to"] not in node_ids]
    edges = [e for e in edges if e["from"] in node_ids and e["to"] in node_ids]

    depth = _layers(nodes, edges)
    by_layer: dict[int, list[dict]] = {}
    for n in nodes:
        by_layer.setdefault(depth[n["id"]], []).append(n)

    dx, dy = 2.6, 1.5
    bw, bh = 1.7, 0.85
    pos: dict[str, tuple[float, float]] = {}
    for layer, group in by_layer.items():
        span = (len(group) - 1) * dy
        for k, n in enumerate(group):
            pos[n["id"]] = (layer * dx, span / 2 - k * dy)

    n_layers = max(by_layer) + 1
    n_rows = max(len(g) for g in by_layer.values())
    # A journal slot is a fixed physical width, so the canvas is a constraint and
    # not something to grow until everything fits. When `canvas_mm` is given the
    # figure is that size and the audit can legitimately find collisions.
    if spec.get("canvas_mm"):
        w_mm, h_mm = spec["canvas_mm"]
        fig_w, fig_h = w_mm / 25.4, h_mm / 25.4
    else:
        fig_w = max(4.0, n_layers * dx + 1.2)
        fig_h = max(3.0, n_rows * dy + 0.9)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(-1.0, (n_layers - 1) * dx + 1.0)
    ax.set_ylim(-n_rows * dy / 2 - 0.6, n_rows * dy / 2 + 0.6)
    ax.axis("off")

    fs = spec.get("font_size", 9)
    artists = []
    for n in nodes:
        x, y = pos[n["id"]]
        colour = n.get("color") or OKABE_ITO["sky"]
        box = FancyBboxPatch((x - bw / 2, y - bh / 2), bw, bh,
                             boxstyle="round,pad=0.03,rounding_size=0.08",
                             linewidth=1.2, edgecolor="#333333",
                             facecolor=colour, alpha=0.95, zorder=2)
        ax.add_patch(box)
        # Gene symbols must be italic and protein names roman; the style is taken
        # from the node so the nomenclature audit can verify it survived export.
        # An explicit italic wins over the kind-derived default: silently
        # overriding the caller's instruction would make the resulting
        # convention breach invisible to the nomenclature audit.
        if n.get("italic") is not None:
            style = "italic" if n["italic"] else "normal"
        else:
            style = "italic" if n.get("kind") == "gene" else "normal"
        t = ax.text(x, y, n.get("label", n["id"]), ha="center", va="center",
                    fontsize=fs, zorder=3, wrap=False, style=style)
        artists.append({"node": n["id"], "text": t, "patch": box, "bbox_xy": (x, y)})
        n["_xy"] = (x, y)
        n["_colour"] = colour

    drawn_edges = []
    for e in edges:
        if e["from"] not in pos or e["to"] not in pos:
            continue
        st = EDGE_STYLES.get(e.get("type", "flow"), EDGE_STYLES["flow"])
        a = FancyArrowPatch(pos[e["from"]], pos[e["to"]],
                            connectionstyle="arc3,rad=0.0",
                            mutation_scale=12, linewidth=1.4, zorder=1,
                            shrinkA=26, shrinkB=26,
                            **{k: v for k, v in st.items() if k in ("arrowstyle", "color", "linestyle")})
        ax.add_patch(a)
        drawn_edges.append(a)

    fig.tight_layout(pad=0.2)

    out_stem.parent.mkdir(parents=True, exist_ok=True)
    svg = out_stem.with_suffix(".svg")
    png = out_stem.with_suffix(".png")
    fig.savefig(svg, format="svg")                      # live text, editable
    fig.savefig(png, format="png", dpi=dpi)

    return {"fig": fig, "ax": ax, "artists": artists, "edges_drawn": drawn_edges,
            "pos": pos, "svg": svg, "png": png, "dpi": dpi, "font_size": fs,
            "n_layers": n_layers, "layout_depth": depth, "font": font}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def _overlap(a, b, tol: float = 1.0) -> bool:
    return not (a.x1 - tol <= b.x0 or b.x1 - tol <= a.x0
                or a.y1 - tol <= b.y0 or b.y1 - tol <= a.y0)


def audit(spec: dict, built: dict) -> dict:
    """Check the rendered figure against the spec and against drawing hygiene."""
    import numpy as np

    fig, ax = built["fig"], built["ax"]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    findings: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    texts = [a["text"] for a in built["artists"]]

    # 1. every node must carry its label as live text
    for a in built["artists"]:
        node = next(n for n in spec["nodes"] if n["id"] == a["node"])
        want = node.get("label", node["id"])
        if a["text"].get_text() != want:
            add("label.mismatch", "high", "node label differs from the spec",
                node=a["node"], spec_label=want, drawn=a["text"].get_text())

    # 2. overlapping labels — the classic "looks fine until you print it" defect
    boxes = [(a["node"], a["text"].get_window_extent(renderer)) for a in built["artists"]]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _overlap(boxes[i][1], boxes[j][1]):
                add("label.overlap", "high", "two node labels overlap on the canvas",
                    nodes=[boxes[i][0], boxes[j][0]])

    # 3. labels must sit inside the canvas
    canvas = fig.bbox
    for nid, bb in boxes:
        if bb.x0 < canvas.x0 - 1 or bb.x1 > canvas.x1 + 1 or bb.y0 < canvas.y0 - 1 or bb.y1 > canvas.y1 + 1:
            add("label.outside_canvas", "high", "a label is clipped by the figure edge", node=nid)

    # 3b. labels must fit inside their own shape. A label wider than its box
    # reads as belonging to whatever is next to it, which is worse than no label.
    for a in built["artists"]:
        tb = a["text"].get_window_extent(renderer)
        pb = a["patch"].get_window_extent(renderer)
        if tb.width > pb.width + 1.0 or tb.height > pb.height + 1.0:
            add("label.wider_than_box", "medium",
                "label overflows the shape it belongs to",
                node=a["node"],
                label_px=[round(tb.width, 1), round(tb.height, 1)],
                box_px=[round(pb.width, 1), round(pb.height, 1)])

    # 4. legibility floor
    need = spec.get("min_font_pt", 6.0)
    for a in built["artists"]:
        size = a["text"].get_fontsize()
        if size < need:
            add("font.too_small", "medium",
                f"font size {size} pt is below the legibility floor {need} pt", node=a["node"])

    # 5. edges: count and direction
    want_edges = [e for e in spec.get("edges") or []
                  if e["from"] in built["pos"] and e["to"] in built["pos"]]
    if len(built["edges_drawn"]) != len(want_edges):
        add("edge.count_mismatch", "high", "number of drawn connectors differs from the spec",
            spec=len(want_edges), drawn=len(built["edges_drawn"]))

    node_ids = {n["id"]: n for n in spec["nodes"]}
    for e in want_edges:
        sx, sy = built["pos"][e["from"]]
        tx, ty = built["pos"][e["to"]]
        if node_ids[e["to"]].get("_colour") == node_ids[e["from"]].get("_colour") \
                and node_ids[e["to"]].get("label") == node_ids[e["from"]].get("label"):
            add("entity.duplicate", "medium",
                "two nodes share both label and colour, so the figure cannot distinguish them",
                nodes=[e["from"], e["to"]])
        if (tx, ty) == (sx, sy):
            add("edge.zero_length", "high", "two connected nodes were placed at the same point",
                edge=[e["from"], e["to"]])

    # 6. back-edges: a longer path that a reader would misread as forward flow
    depth = built["layout_depth"]
    for e in want_edges:
        if depth.get(e["to"], 0) <= depth.get(e["from"], 0) and e.get("type", "flow") == "flow":
            add("edge.backward_flow", "medium",
                "a flow arrow points to a node at the same or an earlier layer",
                edge=[e["from"], e["to"]], layers=[depth.get(e["from"]), depth.get(e["to"])])

    # 6b. every character in every label must have a glyph in the chosen font.
    # This is the "中文变成方框" failure: the file is valid, the labels are unreadable.
    font = built.get("font")
    if font is not None:
        if font.path is None:
            add("export.no_font", "high",
                "no font file could be resolved, so labels may render as blank boxes",
                family=font.family)
        elif font.missing:
            add("export.missing_glyphs", "high",
                "characters in the labels have no glyph in the font that was used, so they "
                "render as empty boxes", characters="".join(font.missing)[:40],
                count=len(font.missing), font=font.family)

    # 7. colour-vision safety
    for n in spec["nodes"]:
        c = (n.get("color") or OKABE_ITO["sky"]).lower()
        if c not in _SAFE_HEX:
            add("colour.not_cb_safe", "low",
                "colour is outside the Okabe-Ito colour-blind-safe palette",
                node=n["id"], colour=c)

    # 7b. legend must match the drawn entities (题面: 图例与数据逐项一致)
    # Declared legend entries that match no drawn label are phantom series, and a drawn
    # entity missing from a required legend is unexplained ink. Both are gated: without
    # a declared legend nothing fires, and legend_required gates the second direction.
    legend = [str(x).strip() for x in (spec.get("legend") or []) if str(x).strip()]
    if legend:
        node_labels = [str(n.get("label") or n.get("id") or "") for n in spec["nodes"]]
        folded = {lbl.strip().lower(): lbl for lbl in node_labels if lbl.strip()}
        for entry in legend:
            key = entry.lower()
            if key not in folded and not any(key in lbl.lower() or lbl.lower() in key
                                             for lbl in folded):
                add("legend.entry_unmatched", "medium",
                    "a legend entry matches no drawn label, so the legend describes a series "
                    "the figure does not contain", entry=entry)
        if spec.get("legend_required"):
            missing = [lbl for lbl in node_labels
                       if lbl.strip() and lbl.strip().lower() not in {e.lower() for e in legend}
                       and not any(e.lower() in lbl.lower() or lbl.lower() in e.lower()
                                   for e in legend)]
            if missing:
                add("legend.entity_unlisted", "low",
                    "a drawn label has no legend entry while the legend is required, so part "
                    "of the figure is unexplained", labels=missing[:6])

    # 8. export hygiene: what a journal will ask for
    svg_text = built["svg"].read_text(encoding="utf-8", errors="replace")
    if "<text" not in svg_text:
        add("export.no_live_text", "high",
            "the SVG contains no <text> elements, so labels are paths and cannot be edited")
    if "<image" in svg_text:
        add("export.embedded_raster", "medium",
            "the SVG embeds a raster image; it will not scale cleanly for print")
    if built["dpi"] < 300:
        add("export.low_dpi", "medium",
            f"preview rendered at {built['dpi']} dpi; journals normally require 300 or more")
    for fam in ("font-family",):
        if fam not in svg_text:
            add("export.no_font_family", "low",
                "the SVG does not declare a font-family, so substitution may change metrics")

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "figureaudit/v1",
        "status": ("clean" if not findings else
                   "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "checked": {
            "nodes": len(spec.get("nodes") or []),
            "edges": len(want_edges),
            "labels_overlapping": sum(1 for f in findings if f["rule"] == "label.overlap"),
            "dpi": built["dpi"],
            "artifacts": {"svg": str(built["svg"]), "png": str(built["png"])},
        },
    }


def coverage(spec: dict, checklist: dict) -> dict:
    """Compare the spec against the entities/relations extracted from the source.

    This is the check that separates "I drew a plausible diagram" from "the
    diagram contains what the paper described". Both lists are the caller's, so
    a mismatch is a real omission rather than a rendering artefact.
    """
    want_nodes = {e["id"] for e in (checklist.get("entities") or [])}
    want_edges = {(e["from"], e["to"]) for e in (checklist.get("relations") or [])}
    have_nodes = {n["id"] for n in (spec.get("nodes") or [])}
    have_edges = {(e["from"], e["to"]) for e in (spec.get("edges") or [])}

    missing_nodes = sorted(want_nodes - have_nodes)
    extra_nodes = sorted(have_nodes - want_nodes) if want_nodes else []
    missing_edges = sorted(want_edges - have_edges)
    # An edge whose endpoints are missing is already implied by missing_nodes,
    # so it is reported once, not twice.
    missing_edges = [e for e in missing_edges if e[0] in have_nodes and e[1] in have_nodes]

    return {
        "entities_expected": len(want_nodes),
        "entities_present": len(want_nodes & have_nodes),
        "relations_expected": len(want_edges),
        "relations_present": len(want_edges & have_edges),
        "missing_entities": missing_nodes,
        "missing_relations": [list(e) for e in missing_edges],
        "entities_not_in_source": extra_nodes,
        "complete": not missing_nodes and not missing_edges,
    }


def build_and_audit(spec_path: Path, out_dir: Path, checklist_path: Path | None = None) -> dict:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    built = render(spec, out_dir / "figure")
    result = audit(spec, built)

    # Provenance, determinism and font reporting live here rather than in each skill's
    # wrapper: a per-package patch is lost the moment the shared module is re-copied, and
    # that had already happened twice. One implementation, no patch to forget.
    import provenance as _prov
    prov = _prov.audit_provenance(spec, expect_connections=spec.get("expect_connections", True))
    result["findings"].extend(prov["findings"])
    result["findings"].extend(_prov.check_numbering(spec))
    det = _prov.check_deterministic(spec, render)
    result["reproducibility"] = det
    result["provenance"] = prov
    result["font"] = {"family": built["font"].family,
                      "missing_glyphs": "".join(built["font"].missing)}
    if not det["deterministic"]:
        result["findings"].append({
            "rule": "repro.nondeterministic", "severity": "high",
            "message": "rendering the same spec twice produced different output, so the figure "
                       "cannot be reproduced by a reader", "detail": det["detail"]})
    counts = {}
    for f in result["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    result["severity_counts"] = counts
    result["status"] = ("clean" if not result["findings"]
                        else "blocked" if counts.get("high") else "review")

    if checklist_path is not None and Path(checklist_path).exists():
        cov = coverage(spec, json.loads(Path(checklist_path).read_text(encoding="utf-8")))
        result["coverage"] = cov
        if cov["missing_entities"] or cov["missing_relations"]:
            result["findings"].append({
                "rule": "coverage.incomplete", "severity": "high",
                "message": "the figure does not contain every entity/relation the source states",
                "missing_entities": cov["missing_entities"],
                "missing_relations": cov["missing_relations"],
            })
            result["status"] = "blocked"

    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    plt.close(built["fig"])
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Lives here so every copy of this module has one."""
    import argparse

    ap = argparse.ArgumentParser(prog="schematic", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, help="spec.json describing nodes and edges")
    ap.add_argument("--checklist", help="checklist.json extracted from the source material")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)

    result = build_and_audit(Path(a.spec), Path(a.out),
                             Path(a.checklist) if a.checklist else None)
    print(json.dumps({"status": result["status"],
                      "findings": [f["rule"] for f in result["findings"]],
                      "font": result.get("font", {}).get("family"),
                      "missing_glyphs": result.get("font", {}).get("missing_glyphs"),
                      "deterministic": result.get("reproducibility", {}).get("deterministic"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4}.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

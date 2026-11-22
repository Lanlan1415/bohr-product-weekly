"""Render a schematic diagram from a declarative spec, then audit the result.

Two separate jobs, deliberately kept apart:

  render  — spec (nodes, edges, compartments) -> matplotlib Figure -> SVG + PNG + PDF
  audit   — Figure + spec -> findings

The audit is the part that matters. A drawing can look finished and still be
wrong: a label overlaps its neighbour, an arrow points backwards, an entity the
source text described never made it onto the canvas, the export is a raster when
it had to be an editable vector. None of that is visible in the PNG at a glance,
and a base agent cannot check it about its own output.

Defect handling policy: one malformed entry (a bare string in the node list, an
edge naming a node that does not exist) must not kill the whole case. Such
entries are skipped and reported (`node.malformed`, `edge.malformed`,
`edge.dangling`) so the rest of the figure still renders; refusal is reserved
for specs from which nothing at all can be drawn.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

# Okabe-Ito: distinguishable under the common forms of colour-vision deficiency.
# Anything outside this set is reported, because a figure whose meaning depends on
# telling red from green is unreadable for ~8% of male readers.
def _records(value):
    """Dict entries of a spec list; malformed entries degrade to skipped."""
    for item in value or []:
        if isinstance(item, dict):
            yield item


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

# Evidence strength on a relation (题面: "并标注证据强度或不确定性"). Declared
# levels only; anything else is reported rather than guessed. Rendering maps the
# level onto the line style so the uncertainty is visible on the canvas itself.
CONFIDENCE_LEVELS = ("confirmed", "predicted", "hypothetical")
_CONFIDENCE_DASH = {"confirmed": None, "predicted": "--", "hypothetical": ":"}

COMPARTMENT_DEFAULT_COLOR = "#EDEDED"


def _valid_nodes(raw: list) -> tuple[list[dict], list]:
    """Split the node list into drawable dicts and malformed leftovers."""
    valid, bad = [], []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) \
                or not item["id"].strip():
            bad.append(item if not isinstance(item, dict) else item.get("id"))
            continue
        if item["id"] in seen:
            bad.append(item["id"])
            continue
        seen.add(item["id"])
        valid.append(item)
    return valid, bad


def _valid_edges(raw: list) -> tuple[list[dict], list]:
    valid, bad = [], []
    for item in raw or []:
        if not isinstance(item, dict) or not isinstance(item.get("from"), str) \
                or not isinstance(item.get("to"), str):
            bad.append(item)
            continue
        valid.append(item)
    return valid, bad


def _compartments(spec: dict) -> tuple[dict[str, dict], list]:
    """Declared compartment bands: id -> {label, layers, color}, plus bad entries."""
    out: dict[str, dict] = {}
    bad: list = []
    for c in spec.get("compartments") or []:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"].strip():
            bad.append(c)
            continue
        layers = c.get("layers")
        layers = [int(x) for x in layers if isinstance(x, (int, float))] \
            if isinstance(layers, (list, tuple)) else []
        out[c["id"]] = {"label": str(c.get("label") or c["id"]),
                        "layers": sorted(layers),
                        "color": c.get("color") or COMPARTMENT_DEFAULT_COLOR}
    return out, bad


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
    """Draw the diagram and write `<stem>.svg` (editable), `<stem>.png`, `<stem>.pdf`.

    `fonttype` defaults to "none" so labels stay live <text> with a declared
    font-family. matplotlib's own default is "path", which converts text to
    outlines and silently destroys editability — the audit flags that, and the
    benchmark injects it to prove the flag works. The PDF is written with
    `pdf.fonttype 42` so TrueType glyphs are embedded (字体嵌入): the file carries
    its own glyphs instead of depending on the reader's fonts.
    """
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

    raw_nodes = spec.get("nodes") or []
    raw_edges = spec.get("edges") or []
    nodes, malformed_nodes = _valid_nodes(raw_nodes)
    edges, malformed_edges = _valid_edges(raw_edges)
    if not nodes:
        raise ValueError("spec has no drawable nodes (every entry is malformed or the list is empty)")

    node_ids = {n["id"] for n in nodes}
    dangling = [e for e in edges if e["from"] not in node_ids or e["to"] not in node_ids]
    edges = [e for e in edges if e["from"] in node_ids and e["to"] in node_ids]

    compartments, malformed_compartments = _compartments(spec)

    depth = _layers(nodes, edges)

    # Compartment constraint layout (题面创新点: 区室与跨膜位置约束布局). A node
    # that declares a compartment but no explicit layer is placed inside that
    # compartment's band — the declared biology constrains the geometry instead
    # of the other way round. An explicit `layer` always wins, and a contradiction
    # between the two is exactly what the audit reports.
    comp_of: dict[str, str] = {}
    for n in nodes:
        c = n.get("compartment")
        if isinstance(c, str) and c in compartments and n.get("layer") is None:
            layers = compartments[c]["layers"]
            if layers:
                depth[n["id"]] = int(layers[0])
        if isinstance(c, str):
            comp_of[n["id"]] = c

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
    canvas = spec.get("canvas_mm")
    if (isinstance(canvas, (list, tuple)) and len(canvas) == 2
            and all(isinstance(v, (int, float)) for v in canvas)):
        w_mm, h_mm = canvas
        if w_mm <= 0 or h_mm <= 0:
            raise ValueError(f"canvas_mm must be positive, got {canvas}")
        fig_w, fig_h = w_mm / 25.4, h_mm / 25.4
    else:
        fig_w = max(4.0, n_layers * dx + 1.2)
        fig_h = max(3.0, n_rows * dy + 0.9)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(-1.0, (n_layers - 1) * dx + 1.0)
    ax.set_ylim(-n_rows * dy / 2 - 0.6, n_rows * dy / 2 + 0.6)
    ax.axis("off")

    fs = spec.get("font_size", 9)

    # Compartment bands first, so boxes and arrows layer on top of them. A band
    # is drawn only where its layers hold nodes; an empty band claims space for
    # biology the figure does not show.
    layer_ys: dict[int, list[float]] = {}
    for nid, (x, y) in pos.items():
        layer_ys.setdefault(depth[nid], []).append(y)
    xlim = ax.get_xlim()
    for cid, comp in compartments.items():
        ys = [y for L in comp["layers"] for y in layer_ys.get(L, [])]
        if not ys:
            continue
        top, bot = max(ys) + bh / 2 + 0.18, min(ys) - bh / 2 - 0.18
        ax.add_patch(Rectangle((xlim[0] + 0.02, bot), xlim[1] - xlim[0] - 0.04,
                               top - bot, facecolor=comp["color"],
                               edgecolor="#BBBBBB", linewidth=0.8, alpha=0.6, zorder=0))
        ax.text(xlim[0] + 0.12, top - 0.06, comp["label"], ha="left", va="top",
                fontsize=max(fs - 2.0, 4.5), color="#555555", zorder=1)

    artists = []
    for n in nodes:
        x, y = pos[n["id"]]
        colour = n.get("color") or OKABE_ITO["sky"]
        # Node size encodes a datum (题面: 节点大小编码数据). Area-proportional
        # scaling keeps the mapping readable; non-positive sizes are reported.
        size = n.get("size", 1.0)
        s = size ** 0.5 if isinstance(size, (int, float)) and size > 0 else 1.0
        bw_i, bh_i = bw * s, bh * s
        box = FancyBboxPatch((x - bw_i / 2, y - bh_i / 2), bw_i, bh_i,
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
        st = dict(EDGE_STYLES.get(e.get("type", "flow"), EDGE_STYLES["flow"]))
        conf = str(e.get("confidence") or "").lower()
        dash = _CONFIDENCE_DASH.get(conf)
        if dash and e.get("type", "flow") != "bind":
            st["linestyle"] = dash
        elif dash == ":" and e.get("type", "flow") == "bind":
            st["linestyle"] = ":"
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
    pdf = out_stem.with_suffix(".pdf")
    fig.savefig(svg, format="svg")                      # live text, editable
    fig.savefig(png, format="png", dpi=dpi)
    fig.savefig(pdf, format="pdf")                      # embedded TrueType (type 42)

    return {"fig": fig, "ax": ax, "artists": artists, "edges_drawn": drawn_edges,
            "pos": pos, "svg": svg, "png": png, "pdf": pdf, "dpi": dpi,
            "font_size": fs, "n_layers": n_layers, "layout_depth": depth,
            "font": font, "nodes_valid": nodes, "malformed_nodes": malformed_nodes,
            "malformed_edges": malformed_edges, "dangling_edges": dangling,
            "malformed_compartments": malformed_compartments,
            "compartments": compartments, "compartment_of": comp_of}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def _overlap(a, b, tol: float = 1.0) -> bool:
    return not (a.x1 - tol <= b.x0 or b.x1 - tol <= a.x0
                or a.y1 - tol <= b.y0 or b.y1 - tol <= a.y0)


def audit(spec: dict, built: dict) -> dict:
    """Check the rendered figure against the spec and against drawing hygiene."""
    fig, ax = built["fig"], built["ax"]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    findings: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    nodes = built["nodes_valid"]
    texts = [a["text"] for a in built["artists"]]

    # 0. malformed spec entries were skipped, not drawn — say so explicitly so a
    #    silent partial figure cannot pass as complete.
    if built["malformed_nodes"]:
        add("node.malformed", "medium",
            "node entries were skipped because they are not objects with a string id",
            count=len(built["malformed_nodes"]))
    if built["malformed_edges"]:
        add("edge.malformed", "medium",
            "edge entries were skipped because they lack a string from/to pair",
            count=len(built["malformed_edges"]))
    if built["malformed_compartments"]:
        add("compart.malformed", "medium",
            "compartment entries were skipped because they lack an id",
            count=len(built["malformed_compartments"]))
    for e in built["dangling_edges"]:
        add("edge.dangling", "medium",
            "a connection names a node the figure does not declare, so it is drawn "
            "as neither arrow nor endpoint (断头箭头)",
            edge=[e.get("from"), e.get("to")])

    # 1. every node must carry its label as live text
    for a in built["artists"]:
        node = next(n for n in nodes if n["id"] == a["node"])
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
    try:
        need = float(spec.get("min_font_pt") or 6.0)
    except (TypeError, ValueError):
        need = 6.0  # a non-numeric floor falls back to the default legibility floor
    for a in built["artists"]:
        size = a["text"].get_fontsize()
        if size < need:
            add("font.too_small", "medium",
                f"font size {size} pt is below the legibility floor {need} pt", node=a["node"])

    # 5. edges: count and direction
    want_edges = [e for e in (spec.get("edges") or [])
                  if isinstance(e, dict) and e.get("from") in built["pos"]
                  and e.get("to") in built["pos"]]
    if len(built["edges_drawn"]) != len(want_edges):
        add("edge.count_mismatch", "high", "number of drawn connectors differs from the spec",
            spec=len(want_edges), drawn=len(built["edges_drawn"]))

    node_ids = {n["id"]: n for n in nodes}
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
        etype = e.get("type", "flow")
        back = depth.get(e["to"], 0) <= depth.get(e["from"], 0)
        if back and etype == "flow" and not e.get("recycle"):
            # A declared `recycle: true` is an explicit return line (回流/反馈环),
            # drawn as designed; anything else pointing backwards misreads.
            add("edge.backward_flow", "medium",
                "a flow arrow points to a node at the same or an earlier layer without a "
                "recycle declaration",
                edge=[e["from"], e["to"]], layers=[depth.get(e["from"]), depth.get(e["to"])])
        if back and etype in ("activate", "inhibit") and not e.get("feedback"):
            add("edge.feedback_unlabeled", "medium",
                "an activate/inhibit arrow runs against the layer order: that is a feedback "
                "loop, and it must be marked `feedback: true` so the reader can tell the "
                "loop from a layout mistake (反馈环走向)",
                edge=[e["from"], e["to"]], layers=[depth.get(e["from"]), depth.get(e["to"])])

    # 6b. evidence strength on relations (题面: 标注证据强度或不确定性)
    if spec.get("confidence_required"):
        for e in want_edges:
            conf = e.get("confidence")
            if conf is None or not str(conf).strip():
                add("edge.confidence_missing", "medium",
                    "the spec requires evidence strength on every relation, but this edge "
                    "carries none (confirmed/predicted/hypothetical)",
                    edge=[e.get("from"), e.get("to")])
            elif str(conf).strip().lower() not in CONFIDENCE_LEVELS:
                add("edge.confidence_unknown", "medium",
                    "the evidence strength is not a declared level, so the figure asserts an "
                    "uncertainty class nobody defined",
                    edge=[e.get("from"), e.get("to")], value=str(conf))

    # 6c. compartment consistency (区室与跨膜位置): a node may declare which band
    # it belongs to; the band may constrain its layer. An explicit layer that
    # contradicts the declared band puts a membrane receptor in the cytosol.
    compartments = built["compartments"]
    raw_layer = {n["id"]: n.get("layer") for n in nodes}
    for n in nodes:
        c = n.get("compartment")
        if not isinstance(c, str) or not c.strip():
            continue
        if c not in compartments:
            add("compartment.undeclared", "medium",
                "a node names a compartment the spec never declares, so no band can hold it",
                node=n["id"], compartment=c)
        elif compartments[c]["layers"] and raw_layer[n["id"]] is not None \
                and int(raw_layer[n["id"]]) not in compartments[c]["layers"]:
            add("compartment.mismatch", "high",
                "a node's declared layer places it outside the compartment it claims — "
                "the drawing puts the entity in the wrong subcellular location",
                node=n["id"], compartment=c,
                layer=raw_layer[n["id"]], band_layers=compartments[c]["layers"])

    # 6d. node size is a data channel; a non-positive or non-numeric size is noise
    sizes_seen = set()
    for n in nodes:
        s = n.get("size")
        if s is None:
            continue
        if not isinstance(s, (int, float)) or isinstance(s, bool) or s <= 0:
            add("size.not_positive", "medium",
                "node size must be a positive number: it encodes a datum, and this one "
                "cannot be drawn to scale", node=n["id"], size=s)
        else:
            sizes_seen.add(round(float(s), 6))
    if len(sizes_seen) > 1 and spec.get("legend_required"):
        legend_txt = " ".join(str(x) for x in (spec.get("legend") or [])
                              + list(spec.get("legend_notes") or [])).lower()
        if not any(w in legend_txt for w in ("size", "大小", "尺度", "直径", "表达")):
            add("legend.size_unexplained", "low",
                "node sizes vary but the required legend explains no size mapping, so the "
                "size channel carries unexplained data",
                sizes=sorted(sizes_seen)[:6])

    # 6e. every character in every label must have a glyph in the chosen font.
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
    for n in nodes:
        c = (n.get("color") or OKABE_ITO["sky"]).lower()
        if c not in _SAFE_HEX:
            add("colour.not_cb_safe", "low",
                "colour is outside the Okabe-Ito colour-blind-safe palette",
                node=n["id"], colour=c)

    # 7b. legend must match the drawn entities (题面: 图例与数据逐项一致)
    # Declared legend entries that match no drawn label are phantom series, and a drawn
    # entity missing from a required legend is unexplained ink. Both are gated: without
    # a declared legend nothing fires, and legend_required gates the second direction.
    # `legend_notes` carries mapping explanations ("节点大小 = 表达量") — notes about
    # encodings rather than series, so they are exempt from label matching.
    legend = [str(x).strip() for x in (spec.get("legend") or []) if str(x).strip()]
    legend_notes = [str(x).strip() for x in (spec.get("legend_notes") or []) if str(x).strip()]
    if legend:
        node_labels = [str(n.get("label") or n.get("id") or "") for n in nodes]
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
            "nodes": len(nodes),
            "edges": len(want_edges),
            "labels_overlapping": sum(1 for f in findings if f["rule"] == "label.overlap"),
            "dpi": built["dpi"],
            "malformed_nodes": len(built["malformed_nodes"]),
            "malformed_edges": len(built["malformed_edges"]),
            "compartments": sorted(built["compartments"]),
            "artifacts": {"svg": str(built["svg"]), "png": str(built["png"]),
                          "pdf": str(built["pdf"])},
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
        try:
            cov = coverage(spec, json.loads(Path(checklist_path).read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            cov = None
            result["findings"].append({
                "rule": "checklist.unreadable", "severity": "medium",
                "message": "the checklist file is not readable JSON, so source coverage could "
                           "not be audited against it"})
        result["coverage"] = cov
        if cov and (cov["missing_entities"] or cov["missing_relations"]):
            result["findings"].append({
                "rule": "coverage.incomplete", "severity": "high",
                "message": "the figure does not contain every entity/relation the source states",
                "missing_entities": cov["missing_entities"],
                "missing_relations": cov["missing_relations"]})
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
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())

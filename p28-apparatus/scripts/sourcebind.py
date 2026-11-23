"""Source-bound scientific SVG generation and structure-preserving SVG edits.

Primary runtime entry for the graphics packages.  Unlike the legacy audit-only
wrapper, this command always builds the requested drawing from the source-bound
spec before reporting checks:

  python sourcebind.py --mode schematic --spec spec.json --case case.json --out out
  python sourcebind.py --mode pathway --spec spec.json --case case.json --out out
  python sourcebind.py --mode apparatus --spec spec.json --case case.json --out out
  python sourcebind.py --edit-svg old.svg --edits edits.json --case case.json --out out

Generation writes figure.svg (live text + semantic groups/ports), figure.png
(300 dpi), figure.pdf (vector TrueType), mapping.json, spec.json and result.json.
PNG/PDF require matplotlib.  If it is unavailable the editable SVG and mapping
are still delivered with status=review and export.unavailable, never a fabricated
success.  SVG editing preserves unrelated XML elements and records structural
before/after counts.  Visual inspection is not claimed; the automated checks are
XML, coordinates, boxes, labels, connector semantics and magic-byte validation.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import struct
import sys
import unicodedata
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

# Runtime/bench imports must not leave binary .pyc artifacts in a text-only Skill.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from case_contract import apply_contract, embedded_spec  # noqa: E402

VERSION = "sourcebind/v1"
SVG_NS = "http://www.w3.org/2000/svg"
PALETTE = ["#56B4E9", "#009E73", "#E69F00", "#CC79A7", "#0072B2",
           "#D55E00", "#F0E442", "#999999"]
SAFE_COLOURS = {c.lower() for c in PALETTE} | {"#000000"}
TYPE_ALIASES = {
    "activate": "activate", "activation": "activate", "promote": "activate",
    "induce": "activate", "upregulate": "activate", "激活": "activate", "促进": "activate",
    "inhibit": "inhibit", "inhibition": "inhibit", "suppress": "inhibit",
    "repress": "inhibit", "block": "inhibit", "抑制": "inhibit", "阻止": "inhibit",
    "bind": "bind", "binding": "bind", "associate": "bind", "结合": "bind", "关联": "bind",
    "flow": "flow", "流向": "flow", "连接": "flow",
    "phosphorylate": "phosphorylate", "phosphorylation": "phosphorylate", "磷酸化": "phosphorylate",
    "ubiquitinate": "ubiquitinate", "ubiquitination": "ubiquitinate", "泛素化": "ubiquitinate",
    "recruit": "recruit", "recruitment": "recruit", "募集": "recruit",
    "transport": "transport", "translocate": "transport", "translocation": "transport",
    "转运": "transport", "易位": "transport",
}
TYPE_LABELS = {
    "activate": "activate / 激活: blue arrow", "inhibit": "inhibit / 抑制: red T bar",
    "bind": "bind / 结合: green circle, no direction", "flow": "flow / 流向: grey arrow",
    "phosphorylate": "phosphorylate / 磷酸化: purple arrow + P",
    "ubiquitinate": "ubiquitinate / 泛素化: orange arrow + Ub",
    "recruit": "recruit / 募集: green arrow + recruit",
    "transport": "transport / 转运: sky arrow + transport",
}
TYPE_COLOURS = {"activate": "#0072B2", "inhibit": "#D55E00", "bind": "#009E73",
                "flow": "#666666", "phosphorylate": "#CC79A7", "ubiquitinate": "#E69F00",
                "recruit": "#009E73", "transport": "#56B4E9"}
EDGE_SHORT = {"phosphorylate": "P", "ubiquitinate": "Ub", "recruit": "recruit",
              "transport": "transport"}
FLOW_LABELS = {"material": "material / 物料: grey solid", "energy": "energy / 能量: orange solid",
               "information": "information / 信息: blue dashed", "waste": "waste / 废料: red dotted"}
FLOW_COLOURS = {"material": "#666666", "energy": "#E69F00", "information": "#0072B2",
                "waste": "#D55E00"}
FLOW_DASH = {"material": None, "energy": None, "information": "8,5", "waste": "2,5"}
CONFIDENCE_DASH = {"confirmed": None, "predicted": "8,5", "hypothetical": "2,5"}


class SpecError(ValueError):
    pass


def finding(rule: str, severity: str, message: str, **extra) -> dict:
    return {"rule": rule, "severity": severity, "message": message, **extra}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_json(path: Path) -> object:
    def reject_nonfinite(token):
        raise ValueError(f"non-standard/non-finite JSON number {token} is refused")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SpecError(f"unreadable JSON {path}: {exc}") from exc


def read_object(path: Path | None, label: str, required: bool = False) -> dict:
    if path is None:
        if required:
            raise SpecError(f"{label} is required")
        return {}
    value = read_json(Path(path))
    if not isinstance(value, dict):
        raise SpecError(f"{label} must be a JSON object, got {type(value).__name__}")
    return value


def fnum(value, digits=3):
    value = float(value)
    if not math.isfinite(value):
        raise SpecError("non-finite geometry")
    return round(value, digits)


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def canonical_type(value) -> str:
    return TYPE_ALIASES.get(str(value or "flow").strip().lower(), str(value or "flow").strip().lower())


def value_text(node: dict) -> str:
    if node.get("value") is None:
        return ""
    unit = str(node.get("unit") or "").strip()
    return f"{node['value']}{(' ' + unit) if unit else ''}"


def display_text(node: dict) -> str:
    label = str(node.get("label") or node["id"])
    extra = value_text(node)
    return label + (("\n" + extra) if extra else "")


def text_width(text: str, font_px: float) -> float:
    units = 0.0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            units += 1.0
        elif ch.isspace():
            units += 0.33
        elif ch in "iljIt.,:;'|!":
            units += 0.32
        elif ch in "MW@#%":
            units += 0.90
        else:
            units += 0.58
    return units * font_px


def wrap_text(text: str, max_px: float, font_px: float) -> list[str]:
    """Glyph-aware deterministic wrapping; no text is discarded or resized."""
    out: list[str] = []
    for original in str(text).split("\n"):
        if original == "":
            out.append("")
            continue
        line = ""
        for ch in original:
            candidate = line + ch
            if line and text_width(candidate, font_px) > max_px:
                out.append(line.rstrip())
                line = ch.lstrip() if ch.isspace() else ch
            else:
                line = candidate
        out.append(line.rstrip())
    return out or [""]


def normalise_spec(raw: dict, mode: str) -> tuple[dict, list[dict], list[str]]:
    findings: list[dict] = []
    limits: list[str] = []
    spec = deepcopy(raw)
    raw_nodes = spec.get("nodes")
    if not isinstance(raw_nodes, list):
        raise SpecError("spec.nodes must be a non-empty list")
    nodes, seen = [], set()
    for i, item in enumerate(raw_nodes):
        if not isinstance(item, dict) or not isinstance(item.get("id"), (str, int)) \
                or not str(item.get("id")).strip():
            findings.append(finding("node.malformed", "medium", "node without a string id was skipped", index=i))
            continue
        n = deepcopy(item)
        n["id"] = str(n["id"])
        if n["id"] in seen:
            findings.append(finding("node.duplicate_id", "high", "duplicate node id was skipped", node=n["id"], index=i))
            continue
        seen.add(n["id"])
        n["label"] = str(n.get("label") or n["id"])
        if "stage" in n and "layer" not in n:
            try:
                stage = float(n["stage"])
                if not math.isfinite(stage) or stage < 0:
                    raise ValueError
                n["layer"] = int(stage)
            except (TypeError, ValueError, OverflowError):
                findings.append(finding("route.stage_nonnumeric", "medium", "stage is not a non-negative number", node=n["id"]))
        if "layer" in n:
            layer = n["layer"]
            if not isinstance(layer, (int, float)) or isinstance(layer, bool) \
                    or not math.isfinite(layer) or layer < 0 or int(layer) != layer:
                raise SpecError(f"node {n['id']} layer must be a non-negative integer")
            n["layer"] = int(layer)
        nodes.append(n)
    if not nodes:
        raise SpecError("no drawable nodes after validation")
    spec["nodes"] = nodes
    ids = set(seen)
    raw_edges = spec.get("edges") or []
    if not isinstance(raw_edges, list):
        raise SpecError("spec.edges must be a list when supplied")
    edges = []
    for i, item in enumerate(raw_edges):
        if not isinstance(item, dict) or not isinstance(item.get("from"), (str, int)) \
                or not isinstance(item.get("to"), (str, int)):
            findings.append(finding("edge.malformed", "medium", "edge without from/to was skipped", index=i))
            continue
        e = deepcopy(item)
        e["from"], e["to"] = str(e["from"]), str(e["to"])
        e["id"] = str(e.get("id") or f"e{i + 1}")
        e["declared_type"] = str(e.get("type") or "flow")
        e["type"] = canonical_type(e["declared_type"])
        if e["type"] not in TYPE_LABELS:
            findings.append(finding("edge.type_unknown", "high", "unsupported relation is drawn with an explicit unresolved marker, not silently as flow", edge=[e["from"], e["to"]], found=e["declared_type"]))
        if e["from"] not in ids or e["to"] not in ids:
            findings.append(finding("edge.dangling", "high", "edge names an undeclared endpoint and was not drawn", edge=[e["from"], e["to"]]))
            continue
        if e.get("confidence") is not None and str(e["confidence"]) not in CONFIDENCE_DASH:
            findings.append(finding("edge.confidence_unknown", "medium", "unknown evidence strength", edge=[e["from"], e["to"]], confidence=str(e["confidence"])))
        if spec.get("confidence_required") and not e.get("confidence"):
            findings.append(finding("edge.confidence_missing", "medium", "evidence strength is required but not declared", edge=[e["from"], e["to"]]))
        if mode == "apparatus" and e.get("type") == "flow":
            fk = str(e.get("flow_kind") or "material").lower()
            e["flow_kind"] = fk
            if fk not in FLOW_LABELS:
                findings.append(finding("flow.kind_unknown", "high", "material/energy/information/waste channel is unknown", edge=[e["from"], e["to"]], found=fk))
        edges.append(e)
    spec["edges"] = edges
    requested_kind = str(raw.get("figure_kind") or mode).lower()
    # Apparatus is the renderer family; a technical route is a semantic subtype
    # whose entry/exit constraints must not be lost during normalisation.
    spec["figure_kind"] = "route" if mode == "apparatus" and requested_kind in ("route", "roadmap", "technical_route", "technical-roadmap", "technical-route") else mode
    categories = spec.get("categories")
    cat_map = categories if isinstance(categories, dict) else {}
    cat_list = categories if isinstance(categories, list) else None
    by_category: dict[str, set] = {}
    for n in nodes:
        category = n.get("category")
        if category is None:
            continue
        if cat_map and category not in cat_map:
            findings.append(finding("colour.category_unknown", "medium", "node category is missing from the declared colour mapping", node=n["id"], category=str(category)))
        if cat_list is not None and category not in cat_list:
            findings.append(finding("colour.category_unknown", "medium", "node category is missing from the declared category list", node=n["id"], category=str(category)))
        if cat_map and category in cat_map and n.get("color") and str(n["color"]).lower() != str(cat_map[category]).lower():
            findings.append(finding("colour.category_mismatch", "medium", "node colour contradicts its declared category colour", node=n["id"], category=str(category)))
        if n.get("color"):
            by_category.setdefault(str(category), set()).add(str(n["color"]).lower())
    for category, colours in by_category.items():
        if len(colours) > 1:
            findings.append(finding("colour.category_mismatch", "medium", "one category maps to multiple node colours", category=category, colours=sorted(colours)))
    legend_values = spec.get("legend") or []
    if isinstance(legend_values, str):
        legend_values = [legend_values]
    labels = [n["label"] for n in nodes]
    if isinstance(legend_values, list):
        for entry in legend_values:
            text = str(entry).strip()
            if text and not any(text.lower() in label.lower() or label.lower() in text.lower() for label in labels):
                findings.append(finding("legend.entry_unmatched", "medium", "legend entry matches no drawn entity", entry=text))
        if spec.get("legend_required"):
            for label in labels:
                if not any(str(entry).lower() in label.lower() or label.lower() in str(entry).lower() for entry in legend_values):
                    findings.append(finding("legend.entity_unlisted", "low", "drawn entity is absent from a required legend", label=label))
        size_channels = {json.dumps(n.get("size", 1.0), sort_keys=True, default=str) for n in nodes}
        if spec.get("legend_required") and len(size_channels) > 1:
            explanations = " ".join(str(x) for x in list(legend_values) + list(spec.get("legend_notes") or []))
            if not re.search(r"size|面积|大小|表达量|面积正比", explanations, flags=re.I):
                findings.append(finding("legend.size_unexplained", "low", "node sizes vary but no size/data mapping is explained"))
    if not spec.get("canvas_mm"):
        limits.append("canvas_mm was not supplied; a deterministic geometry-derived canvas was used")
    if not spec.get("font_size"):
        limits.append("font_size was not supplied; 9pt was used")
    return spec, findings, limits


def layers_for(spec: dict) -> dict[str, int]:
    nodes, edges = spec["nodes"], spec["edges"]
    explicit = {n["id"]: n.get("layer") for n in nodes}
    parents = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("feedback") or e.get("recycle"):
            continue
        parents[e["to"]].append(e["from"])
    depth: dict[str, int] = {}

    def resolve(nid: str, seen=frozenset()) -> int:
        if nid in depth:
            return depth[nid]
        if explicit.get(nid) is not None:
            depth[nid] = int(explicit[nid])
            return depth[nid]
        if nid in seen or len(seen) > len(nodes):
            return 0
        ps = parents.get(nid) or []
        value = 0 if not ps else 1 + max(resolve(p, seen | {nid}) for p in ps)
        depth[nid] = value
        return value

    for n in nodes:
        resolve(n["id"])
    # Declared biological bands constrain otherwise unconstrained nodes.
    comps = spec.get("compartments") or []
    if isinstance(comps, list):
        by_comp = {str(c.get("id")): c for c in comps if isinstance(c, dict) and c.get("id") is not None}
        for n in nodes:
            cid = n.get("compartment")
            if n.get("layer") is None and cid in by_comp:
                ls = by_comp[cid].get("layers") or []
                valid = [int(x) for x in ls if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 and int(x) == x]
                if valid:
                    depth[n["id"]] = min(valid)
    return depth


def _canvas(spec: dict) -> tuple[float | None, float | None, float | None, float | None]:
    canvas = spec.get("canvas_mm")
    if canvas is None:
        return None, None, None, None
    if not isinstance(canvas, (list, tuple)) or len(canvas) != 2:
        raise SpecError("canvas_mm must be [width_mm,height_mm]")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in canvas):
        raise SpecError("canvas_mm entries must be finite positive numbers")
    w_mm, h_mm = float(canvas[0]), float(canvas[1])
    if w_mm > 2000 or h_mm > 2000:
        raise SpecError("canvas_mm exceeds the 2000 mm safety limit")
    return w_mm * 96 / 25.4, h_mm * 96 / 25.4, w_mm, h_mm


def make_layout(spec: dict, mode: str) -> tuple[dict, list[dict]]:
    findings: list[dict] = []
    nodes, edges = spec["nodes"], spec["edges"]
    depth = layers_for(spec)
    font_pt = spec.get("font_size", 9)
    if not isinstance(font_pt, (int, float)) or isinstance(font_pt, bool) \
            or not math.isfinite(font_pt) or font_pt <= 0:
        raise SpecError("font_size must be a positive finite number")
    font_px = float(font_pt) * 96 / 72
    fixed_w, fixed_h, w_mm, h_mm = _canvas(spec)
    groups: dict[int, list[dict]] = {}
    for n in nodes:
        groups.setdefault(depth[n["id"]], []).append(n)
    layer_ids = sorted(groups)
    ncols = len(layer_ids)
    gap_x = 86.0
    if fixed_w:
        gap_x = max(34.0, min(86.0, fixed_w / max(8 * ncols, 1)))
    max_node_w = 230.0
    if fixed_w:
        max_node_w = min(230.0, max(68.0, (fixed_w - 56 - gap_x * (ncols - 1)) / ncols))
    sizes: dict[str, list[float]] = {}
    wrapped: dict[str, list[str]] = {}
    col_width: dict[int, float] = {}
    for layer, group in groups.items():
        widest = 0.0
        for n in group:
            scale = 1.0
            value = n.get("size", 1.0)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                findings.append(finding("size.not_positive", "medium", "node size is not a positive finite number; visual scale fallback used", node=n["id"]))
            else:
                scale = math.sqrt(value)
            content = display_text(n)
            if mode == "apparatus" and n.get("stage") is not None:
                try:
                    numeric_stage = float(n["stage"])
                    stage_label = f"{int(numeric_stage):02d}" if numeric_stage.is_integer() else str(n["stage"])
                except (TypeError, ValueError, OverflowError):
                    stage_label = str(n["stage"])
                content = f"S{stage_label} | {content}"
            lines = wrap_text(content, max(32.0, max_node_w - 28), font_px)
            text_w = max(text_width(x, font_px) for x in lines)
            base_w = max(92.0, min(max_node_w, text_w + 28))
            h = max(58.0, len(lines) * font_px * 1.36 + 26) * scale
            # Area proportional to size means both linear dimensions scale by
            # sqrt(size) exactly once; the previous draft scaled width twice.
            w = max(64.0, base_w * scale)
            if mode == "apparatus" and str(n.get("part_kind") or n.get("kind") or "").lower() in ("pump", "detector", "sensor"):
                # A circle computed from min(w,h) cannot contain its own longer
                # stage+instrument label.  Give circular devices a square bbox.
                w = h = max(w, h)
            sizes[n["id"]] = [w, h]
            wrapped[n["id"]] = lines
            widest = max(widest, w)
        col_width[layer] = max(82.0, widest)
    auto_w = 56 + sum(col_width[x] for x in layer_ids) + gap_x * (ncols - 1)
    width = fixed_w or max(620.0, auto_w)
    used_types = list(dict.fromkeys(e["type"] for e in edges))
    legend: list[dict] = []
    for value in spec.get("legend") or []:
        legend.append({"text": str(value), "kind": "declared"})
    for value in spec.get("legend_notes") or []:
        legend.append({"text": str(value), "kind": "note"})
    for typ in used_types:
        legend.append({"text": TYPE_LABELS.get(typ, f"UNRESOLVED RELATION / 未定义关系: {typ}"), "kind": "relation", "relation": typ})
    if mode == "apparatus":
        for kind in dict.fromkeys(e.get("flow_kind") for e in edges if e.get("type") == "flow"):
            legend.append({"text": FLOW_LABELS.get(kind, f"UNRESOLVED FLOW: {kind}"), "kind": "flow", "flow_kind": kind})
        if any(e.get("recycle") for e in edges):
            legend.append({"text": "recycle / 回流: explicitly labelled backward connection", "kind": "note"})
        if any(n.get("milestone") for n in nodes):
            legend.append({"text": "milestone / 里程碑: blue outline (source-declared only)", "kind": "note"})
    if any(e.get("feedback") for e in edges):
        legend.append({"text": "feedback / 反馈: explicitly labelled backward regulation", "kind": "note"})
    if any(e.get("confidence") for e in edges):
        legend.append({"text": "evidence: confirmed solid / predicted dashed / hypothetical dotted", "kind": "note"})
    categories = spec.get("categories") if isinstance(spec.get("categories"), dict) else {}
    for cat, colour in categories.items():
        legend.append({"text": f"{cat}: {colour}", "kind": "category", "colour": str(colour)})
    wrapped_legend = []
    for entry in legend:
        lines = wrap_text(entry["text"], max(80.0, width - 100), max(10.0, font_px - 2))
        wrapped_legend.append((entry, lines))
    legend_h = (sum(len(lines) for _, lines in wrapped_legend) * max(18.0, font_px * 1.45)
                + (22 if legend else 0))
    loop_count = sum(bool(e.get("feedback") or e.get("recycle")) for e in edges)
    bypass_candidates = sum(not (e.get("feedback") or e.get("recycle"))
                            and abs(depth[e["to"]] - depth[e["from"]]) > 1 for e in edges)
    loop_count += bypass_candidates
    title_h = (44 if spec.get("title") else 20) + ((min(loop_count, 6) + 1) * 28 + 30 if loop_count else 0)
    stack_heights = {layer: sum(sizes[n["id"]][1] for n in group) + 32 * (len(group) - 1)
                     for layer, group in groups.items()}
    main_h = max(stack_heights.values()) + 50
    auto_h = title_h + main_h + legend_h + 30
    height = fixed_h or max(360.0, auto_h)
    if width > 12000 or height > 12000:
        raise SpecError("required canvas exceeds the 12000px rendering safety limit")
    usable_h = height - title_h - legend_h - 30
    x = 28.0
    pos: dict[str, list[float]] = {}
    columns: dict[int, list[float]] = {}
    for layer in layer_ids:
        group = groups[layer]
        cw = col_width[layer]
        centre_x = x + cw / 2
        total = stack_heights[layer]
        gap_y = 32.0
        if usable_h - 50 < total and len(group) > 1:
            gap_y = max(12.0, (usable_h - 50 - sum(sizes[n["id"]][1] for n in group)) / (len(group) - 1))
            total = sum(sizes[n["id"]][1] for n in group) + gap_y * (len(group) - 1)
        y = title_h + max(18.0, (usable_h - total) / 2)
        columns[layer] = [x, title_h, x + cw, title_h + usable_h]
        for n in group:
            w, h = sizes[n["id"]]
            if isinstance(n.get("x"), (int, float)) and math.isfinite(n["x"]):
                centre_x_n = float(n["x"])
            else:
                centre_x_n = centre_x
            if isinstance(n.get("y"), (int, float)) and math.isfinite(n["y"]):
                centre_y = float(n["y"])
            else:
                centre_y = y + h / 2
            pos[n["id"]] = [centre_x_n, centre_y]
            y += h + gap_y
        x += cw + gap_x
    layout = {"width": fnum(width), "height": fnum(height), "width_mm": fnum(w_mm) if w_mm else None,
              "height_mm": fnum(h_mm) if h_mm else None, "font_pt": float(font_pt), "font_px": fnum(font_px),
              "depth": depth, "positions": pos, "sizes": sizes, "wrapped": wrapped,
              "columns": columns, "usable_h": fnum(usable_h), "title_h": title_h,
              "legend": wrapped_legend, "legend_h": fnum(legend_h), "mode": mode}
    # Deterministic d3-inspired rectangular collision relaxation (fixed seeds are
    # irrelevant: there is no random source).  Automatic columns are already
    # disjoint; this resolves user-position overlaps without changing layer x.
    for _ in range(80):
        moved = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                aid, bid = a["id"], b["id"]
                ax, ay = pos[aid]; bx, by = pos[bid]
                aw, ah = sizes[aid]; bw, bh = sizes[bid]
                ox = (aw + bw) / 2 + 8 - abs(ax - bx)
                oy = (ah + bh) / 2 + 8 - abs(ay - by)
                if ox <= 0 or oy <= 0:
                    continue
                # Preserve topological columns when possible; move vertically.
                if oy <= ox or depth[aid] == depth[bid]:
                    sign = -1 if ay <= by else 1
                    pos[aid][1] -= sign * oy / 2
                    pos[bid][1] += sign * oy / 2
                else:
                    sign = -1 if ax <= bx else 1
                    pos[aid][0] -= sign * ox / 2
                    pos[bid][0] += sign * ox / 2
                moved = True
        if not moved:
            break
    else:
        findings.append(finding("layout.relaxation_unresolved", "high", "80 deterministic collision-relaxation passes did not separate all nodes"))
    return layout, findings


def node_colour(spec: dict, node: dict, index: int) -> str:
    cats = spec.get("categories") if isinstance(spec.get("categories"), dict) else {}
    return str(node.get("color") or cats.get(node.get("category")) or PALETTE[index % len(PALETTE)])


def ports_for(edge: dict, layout: dict) -> tuple[list[float], list[float], list[dict]]:
    pos, sizes = layout["positions"], layout["sizes"]
    sx, sy = pos[edge["from"]]; tx, ty = pos[edge["to"]]
    vx, vy = tx - sx, ty - sy
    if vx == 0 and vy == 0:
        return [fnum(sx), fnum(sy)], [fnum(tx), fnum(ty)], []
    named = [(edge.get("from_port") or edge.get("from_anchor"), True),
             (edge.get("to_port") or edge.get("to_anchor"), False)]
    points = []
    for (port, is_source), (cx, cy), nid in zip(named, ((sx, sy), (tx, ty)), (edge["from"], edge["to"])):
        w, h = sizes[nid]
        aliases = {"start": "W" if is_source else "E", "end": "E" if is_source else "W",
                   "out": "E" if is_source else "W", "in": "W" if is_source else "E",
                   "left": "W", "right": "E", "top": "N", "bottom": "S"}
        p = aliases.get(str(port or "").lower(), str(port or "").upper())
        manual = p in ("N", "E", "S", "W")
        if manual:
            point = [cx, cy - h / 2] if p == "N" else [cx + w / 2, cy] if p == "E" \
                else [cx, cy + h / 2] if p == "S" else [cx - w / 2, cy]
        else:
            sign = 1 if is_source else -1
            local_vx, local_vy = sign * vx, sign * vy
            tx_edge = w / 2 / abs(local_vx) if local_vx else float("inf")
            ty_edge = h / 2 / abs(local_vy) if local_vy else float("inf")
            distance = min(tx_edge, ty_edge)
            point = [cx + local_vx * distance, cy + local_vy * distance]
        points.append([fnum(point[0]), fnum(point[1])])
    return points[0], points[1], [{"node": nid, "port": str(port)} for (port, _), nid in zip(named, (edge["from"], edge["to"])) if port]


def connector_route(edge: dict, start: list[float], end: list[float], declared_ports: list[dict],
                    node_records: list[dict], lane: int = 0) -> tuple[list[float], list[float], dict, list[float]]:
    """Route loops and entity-crossing direct links above unrelated actors."""
    is_loop = bool(edge.get("feedback") or edge.get("recycle"))
    crossed = [n["id"] for n in node_records if n["id"] not in (edge["from"], edge["to"])
               and segment_hits_box(start[0], start[1], end[0], end[1], n["bbox"])]
    if not is_loop and not crossed:
        return start, end, {"kind": "line", "d": f'M {start[0]} {start[1]} L {end[0]} {end[1]}'}, [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2 - 11]
    by_id = {n["id"]: n for n in node_records}
    if not declared_ports:
        # Attach to the top anchors; this replaces the center-to-center ray that
        # previously crossed intermediate nodes on a backward or bypass edge.
        start = [by_id[edge["from"]]["center"][0], by_id[edge["from"]]["bbox"][1]]
        end = [by_id[edge["to"]]["center"][0], by_id[edge["to"]]["bbox"][1]]
    top = min(n["bbox"][1] for n in node_records)
    # Keep label glyphs and the final tangent inside the reserved corridor; a
    # control_y below ~30 clipped "回流" at the upper canvas edge in visual smoke.
    control_y = max(34.0, top - max(72.0, min(170.0, abs(end[0] - start[0]) * .22)) - 22 * lane)
    control_y = fnum(control_y)
    route = {"kind": "feedback_arc", "control_y": control_y, "lane": lane,
             "reason": "feedback/recycle" if is_loop else "unrelated-node-bypass",
             "crossed_nodes_avoided": crossed,
             "d": f'M {start[0]} {start[1]} C {start[0]} {control_y} {end[0]} {control_y} {end[0]} {end[1]}'}
    return start, end, route, [(start[0] + end[0]) / 2, control_y - 8]


def semantic_records(spec: dict, layout: dict) -> tuple[list[dict], list[dict]]:
    nodes = []
    for i, n in enumerate(spec["nodes"]):
        x, y = layout["positions"][n["id"]]; w, h = layout["sizes"][n["id"]]
        nodes.append({"id": n["id"], "label": n["label"], "value": n.get("value"), "unit": n.get("unit"),
                      "kind": n.get("kind"), "category": n.get("category"), "evidence": n.get("evidence"),
                      "size": n.get("size", 1.0), "stage": n.get("stage"), "milestone": n.get("milestone"),
                      "role": n.get("role"), "compartment": n.get("compartment"), "layer": layout["depth"][n["id"]],
                      "colour": node_colour(spec, n, i), "center": [fnum(x), fnum(y)],
                      "bbox": [fnum(x - w / 2), fnum(y - h / 2), fnum(x + w / 2), fnum(y + h / 2)],
                      "lines": layout["wrapped"][n["id"]]})
    edges = []
    lane = 0
    for e in spec["edges"]:
        start, end, declared_ports = ports_for(e, layout)
        is_loop = bool(e.get("feedback") or e.get("recycle"))
        start, end, route, label_pos = connector_route(e, start, end, declared_ports, nodes, lane)
        if route["kind"] == "feedback_arc":
            lane += 1
        rec = {"id": e["id"], "from": e["from"], "to": e["to"], "type": e["type"],
               "declared_type": e["declared_type"], "flow_kind": e.get("flow_kind"),
               "confidence": e.get("confidence"), "feedback": bool(e.get("feedback")),
               "recycle": bool(e.get("recycle")), "source": e.get("source"), "start": start, "end": end,
               "declared_ports": declared_ports, "route": route, "label_pos": [fnum(label_pos[0]), fnum(label_pos[1])],
               "label": str(e.get("label") or EDGE_SHORT.get(e["type"], ""))}
        edges.append(rec)
    return nodes, edges


def marker_defs(types: list[str]) -> str:
    out = ["<defs>"]
    for typ in dict.fromkeys(types):
        colour = TYPE_COLOURS.get(typ, "#666666")
        if typ == "inhibit":
            body = f'<path d="M 9 0 L 9 12" stroke="{colour}" stroke-width="2.4"/>'
        elif typ == "bind":
            body = f'<circle cx="6" cy="6" r="3.2" fill="{colour}"/>'
        elif typ not in TYPE_LABELS:
            body = '<path d="M6 0 L12 6 L6 12 L0 6 Z" fill="#ffffff" stroke="#D55E00" stroke-width="2"/>'
        else:
            body = f'<path d="M0 0 L12 6 L0 12 Z" fill="{colour}"/>'
        out.append(f'<marker id="arrow-{esc(typ)}" markerWidth="14" markerHeight="14" refX="11" refY="6" orient="auto" markerUnits="userSpaceOnUse">{body}</marker>')
    out.append("</defs>")
    return "".join(out)


def svg_node_shape(n: dict, rec: dict) -> str:
    x0, y0, x1, y1 = rec["bbox"]; cx, cy = rec["center"]
    w, h = x1 - x0, y1 - y0
    kind = str(n.get("part_kind") or n.get("kind") or "").lower()
    common = f'fill="{esc(rec["colour"])}" fill-opacity="0.82" stroke="#263238" stroke-width="1.6"'
    if n.get("milestone"):
        common = f'fill="{esc(rec["colour"])}" fill-opacity="0.82" stroke="#0072B2" stroke-width="3.0"'
    if kind == "pump":
        r = min(w, h) / 2 - 3
        ty = cy - r * .45
        tri = f'{fnum(cx - r * .35)},{fnum(ty - r * .30)} {fnum(cx + r * .45)},{fnum(ty)} {fnum(cx - r * .35)},{fnum(ty + r * .30)}'
        return f'<circle cx="{cx}" cy="{cy}" r="{fnum(r)}" {common}/><polygon points="{tri}" fill="#263238"/>'
    if kind == "valve":
        points = f'{x0},{cy - h * .25} {cx},{cy} {x0},{cy + h * .25} {x0},{cy - h * .25} {x1},{cy - h * .25} {x1},{cy + h * .25} {cx},{cy}'
        return f'<polyline points="{points}" fill="{esc(rec["colour"])}" fill-opacity="0.82" stroke="#263238" stroke-width="1.6"/>'
    if kind in ("sensor", "detector"):
        r = min(w, h) / 2 - 3
        return f'<circle cx="{cx}" cy="{cy}" r="{fnum(r)}" {common}/><line x1="{fnum(cx - r * .7)}" y1="{fnum(cy - r * .7)}" x2="{fnum(cx + r * .7)}" y2="{fnum(cy + r * .7)}" stroke="#263238"/>'
    if kind in ("source", "sink"):
        pts = f'{cx},{y0} {x1},{cy} {cx},{y1} {x0},{cy}'
        return f'<polygon points="{pts}" {common}/>'
    if kind == "vessel":
        return f'<rect x="{x0}" y="{y0}" width="{fnum(w)}" height="{fnum(h)}" rx="{fnum(w / 2)}" {common}/><path d="M {x0} {fnum(cy - h * .18)} L {x1} {fnum(cy - h * .18)}" stroke="#263238" stroke-width="1"/>'
    shape = f'<rect id="node-{esc(n["id"])}-box" x="{x0}" y="{y0}" width="{fnum(w)}" height="{fnum(h)}" rx="{10 if kind != "complex" else 2}" {common}/>'
    if kind == "complex":
        shape += f'<rect x="{fnum(x0 + 5)}" y="{fnum(y0 + 5)}" width="{fnum(max(1, w - 10))}" height="{fnum(max(1, h - 10))}" rx="2" fill="none" stroke="#263238" stroke-width="0.8"/>'
    if kind == "receptor":
        shape += f'<line x1="{fnum(cx)}" y1="{y0}" x2="{fnum(cx)}" y2="{y1}" stroke="#263238" stroke-width="0.8"/>'
    return shape


def build_svg(spec: dict, layout: dict, nodes: list[dict], edges: list[dict], spec_sha: str) -> str:
    W, H = layout["width"], layout["height"]
    physical = ""
    if layout.get("width_mm"):
        physical = f'width="{layout["width_mm"]}mm" height="{layout["height_mm"]}mm"'
    else:
        physical = f'width="{W}" height="{H}"'
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="{SVG_NS}" {physical} viewBox="0 0 {W} {H}" role="img" aria-labelledby="figure-title">',
           f'<title id="figure-title">{esc(spec.get("title") or spec.get("figure_kind") or "Scientific figure")}</title>',
           f'<metadata data-engine="{VERSION}" data-spec-sha256="{spec_sha}">Source-bound deterministic scientific figure; live editable text.</metadata>',
           marker_defs([e["type"] for e in edges]),
           '<rect id="canvas-background" x="0" y="0" width="100%" height="100%" fill="white"/>']
    out.append('<g id="layer-compartments">')
    comps = spec.get("compartments") or []
    if isinstance(comps, list):
        for comp in comps:
            if not isinstance(comp, dict) or comp.get("id") is None:
                continue
            layers = comp.get("layers") or []
            members = [r for r in nodes if r.get("compartment") == comp.get("id") or r["layer"] in layers and any(n["id"] == r["id"] and n.get("compartment") == comp.get("id") for n in spec["nodes"])]
            if not members:
                continue
            x0 = min(r["bbox"][0] for r in members) - 12; y0 = min(r["bbox"][1] for r in members) - 30
            x1 = max(r["bbox"][2] for r in members) + 12; y1 = max(r["bbox"][3] for r in members) + 12
            out.append(f'<g id="compartment-{esc(comp["id"])}" data-compartment-id="{esc(comp["id"])}" data-layers="{esc(layers)}"><rect x="{fnum(x0)}" y="{fnum(y0)}" width="{fnum(x1 - x0)}" height="{fnum(y1 - y0)}" rx="8" fill="{esc(comp.get("color") or "#EDEDED")}" fill-opacity="0.45" stroke="#999999" stroke-dasharray="4,3"/><text x="{fnum(x0 + 6)}" y="{fnum(y0 + 18)}" font-size="13" font-family="Arial,sans-serif" fill="#444444">{esc(comp.get("label") or comp["id"])}</text></g>')
    out.append('</g><g id="layer-nodes">')
    for n, rec in zip(spec["nodes"], nodes):
        attrs = [f'data-node-id="{esc(n["id"])}"', f'data-evidence="{esc(n.get("evidence") or "")}"',
                 f'data-kind="{esc(n.get("kind") or n.get("part_kind") or "node")}"',
                 f'data-layer="{rec["layer"]}"', f'data-compartment="{esc(n.get("compartment") or "")}"',
                 f'data-value-text="{esc(value_text(n))}"', f'data-label-lines="{len(rec["lines"])}"',
                 f'data-bbox="{esc(rec["bbox"])}"']
        out.append(f'<g id="node-{esc(n["id"])}" {" ".join(attrs)}>')
        out.append(svg_node_shape(n, rec))
        cx, cy = rec["center"]; lines = rec["lines"]
        line_pitch = layout["font_px"] * 1.28
        start_y = cy - (len(lines) - 1) * line_pitch / 2 + layout["font_px"] * .35
        italic = n.get("italic") if n.get("italic") is not None else n.get("kind") == "gene"
        spans = ''.join(f'<tspan x="{cx}" y="{fnum(start_y + i * line_pitch)}">{esc(line)}</tspan>' for i, line in enumerate(lines))
        out.append(f'<text id="node-{esc(n["id"])}-label" text-anchor="middle" font-size="{layout["font_px"]}" font-family="Arial,sans-serif" font-style="{"italic" if italic else "normal"}" fill="#17202A">{spans}</text></g>')
    out.append('</g><g id="layer-edges">')
    for e in edges:
        colour = FLOW_COLOURS.get(e.get("flow_kind"), TYPE_COLOURS.get(e["type"], "#666666"))
        dash = CONFIDENCE_DASH.get(str(e.get("confidence") or ""))
        if dash is None:
            dash = FLOW_DASH.get(e.get("flow_kind"))
        if e["type"] == "bind" and dash is None:
            dash = "7,4"
        marker = f' marker-end="url(#arrow-{esc(e["type"])})"'
        attrs = f'id="edge-{esc(e["id"])}" data-edge-id="{esc(e["id"])}" data-from="{esc(e["from"])}" data-to="{esc(e["to"])}" data-type="{esc(e["type"])}" data-flow-kind="{esc(e.get("flow_kind") or "")}" data-feedback="{str(e["feedback"]).lower()}" data-recycle="{str(e["recycle"]).lower()}" data-source="{esc(e.get("source") or "")}"'
        style = f'stroke="{colour}" stroke-width="2" fill="none"{(" stroke-dasharray=" + chr(34) + dash + chr(34)) if dash else ""}{marker}'
        if e["route"]["kind"] == "feedback_arc":
            geometry = f'<path d="{esc(e["route"]["d"])}" {style}/>'
        else:
            x1, y1 = e["start"]; x2, y2 = e["end"]
            geometry = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {style}/>'
        out.append(f'<g {attrs}>{geometry}')
        if e["label"]:
            mx, my = e["label_pos"]
            out.append(f'<text id="edge-{esc(e["id"])}-label" x="{fnum(mx)}" y="{fnum(my)}" text-anchor="middle" font-size="{fnum(max(10, layout["font_px"] - 1))}" font-family="Arial,sans-serif" fill="{colour}"><![CDATA[{e["label"].replace("]]>", "]]]]><![CDATA[>")}]]></text>')
        out.append('</g>')
    out.append('</g><g id="layer-legend">')
    ly = layout["title_h"] + layout["usable_h"] + 24
    for i, (entry, lines) in enumerate(layout["legend"]):
        typ = entry.get("relation")
        flow_kind = entry.get("flow_kind")
        colour = FLOW_COLOURS.get(flow_kind, TYPE_COLOURS.get(typ, entry.get("colour", "#666666"))) if entry["kind"] == "flow" else TYPE_COLOURS.get(typ, entry.get("colour", "#666666"))
        out.append(f'<g id="legend-item-{i + 1}" data-legend-kind="{esc(entry["kind"])}">')
        if entry["kind"] == "category":
            out.append(f'<rect x="28" y="{fnum(ly - 10)}" width="16" height="12" fill="{colour}" stroke="#333333"/>')
        elif entry["kind"] in ("relation", "flow"):
            dash = FLOW_DASH.get(flow_kind) if entry["kind"] == "flow" else "7,4" if typ == "bind" else None
            marker = f' marker-end="url(#arrow-{esc(typ)})"' if typ else ""
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            out.append(f'<line x1="28" y1="{fnum(ly - 4)}" x2="48" y2="{fnum(ly - 4)}" stroke="{colour}" stroke-width="2"{dash_attr}{marker}/>')
        for j, line in enumerate(lines):
            out.append(f'<text x="56" y="{fnum(ly + j * max(18, layout["font_px"] * 1.45))}" font-size="{fnum(max(10, layout["font_px"] - 2))}" font-family="Arial,sans-serif" fill="#333333">{esc(line)}</text>')
        ly += len(lines) * max(18, layout["font_px"] * 1.45)
        out.append('</g>')
    out.append('</g>')
    if spec.get("title"):
        out.append(f'<text id="figure-main-title" x="28" y="30" font-size="{fnum(layout["font_pt"] + 3)}" font-weight="bold" font-family="Arial,sans-serif" fill="#17202A">{esc(spec["title"])}</text>')
    out.append('</svg>\n')
    return '\n'.join(x for x in out if x)


def provenance_audit(spec: dict, edges: list[dict]) -> tuple[list[dict], list[dict], dict]:
    findings: list[dict] = []
    sources: list[dict] = []
    materials = spec.get("materials") or []
    if not isinstance(materials, list):
        findings.append(finding("trace.materials_malformed", "high", "materials is not a list; source tracing is blocked"))
        materials = []
    mats = {str(m.get("id")): m for m in materials if isinstance(m, dict) and m.get("id") is not None}
    for mid, mat in mats.items():
        locator = str(mat.get("source") or mat.get("quote") or "")
        sources.append({"element": None, "material": mid, "locator": locator,
                        "source_version": str(mat.get("version") or spec.get("source_version") or "not supplied")})
        if not locator:
            findings.append(finding("trace.material_no_source", "medium", "material has no source locator or exact quote", material=mid))
    drawn_nodes = set()
    for n in spec["nodes"]:
        ev = str(n.get("evidence") or "")
        drawn_nodes.add(ev)
        if not mats:
            findings.append(finding("trace.no_material_list", "high", "no source material list: entity traceability cannot be established", node=n["id"]))
        elif not ev:
            findings.append(finding("trace.entity_untraceable", "high", "node has no material evidence id", node=n["id"]))
        elif ev not in mats:
            findings.append(finding("trace.evidence_not_in_materials", "high", "node evidence id is absent from materials", node=n["id"], evidence=ev))
        else:
            sources.append({"element": f'node:{n["id"]}', "material": ev,
                            "locator": str(mats[ev].get("source") or mats[ev].get("quote") or ""),
                            "source_version": str(mats[ev].get("version") or spec.get("source_version") or "not supplied")})
    for mid in mats:
        if mid not in drawn_nodes:
            findings.append(finding("trace.material_not_drawn", "medium", "source material has no corresponding node", material=mid))
    connections = spec.get("connections") or []
    if not isinstance(connections, list):
        findings.append(finding("trace.connections_malformed", "high", "connections is not a list; relation tracing is blocked"))
        connections = []
    have = {(e["from"], e["to"], e["type"]) for e in edges}
    pair_have = {(a, b) for a, b, _ in have}
    declared_pairs = set()
    for i, c in enumerate(connections):
        if not isinstance(c, dict):
            findings.append(finding("trace.connection_malformed", "medium", "non-object connection skipped", index=i))
            continue
        a, b = str(c.get("from") or ""), str(c.get("to") or "")
        if not a or not b:
            findings.append(finding("trace.connection_malformed", "medium", "connection lacks from/to", index=i))
            continue
        typed = c.get("type") is not None or c.get("kind") is not None
        typ = canonical_type(c.get("type") or c.get("kind") or "flow")
        declared_pairs.add((a, b))
        loc = str(c.get("source") or c.get("quote") or "")
        sources.append({"element": f"edge:{a}->{b}", "material": None, "locator": loc,
                        "source_version": str(c.get("version") or spec.get("source_version") or "not supplied")})
        if not loc:
            findings.append(finding("trace.connection_no_source", "medium", "connection has no source locator or quote", edge=[a, b]))
        if (typed and (a, b, typ) not in have) or (not typed and (a, b) not in pair_have):
            if typed and (a, b) in pair_have:
                findings.append(finding("trace.relation_type_mismatch", "high", "drawn relation type differs from the source connection", edge=[a, b], source_type=typ))
            else:
                findings.append(finding("trace.connection_not_drawn", "high", "source-stated connection is missing from the drawing", edge=[a, b], source_type=typ))
    if not connections:
        findings.append(finding("trace.no_connection_list", "high", "no source connection list: arrows cannot be verified") if edges else finding("trace.no_connection_list", "low", "no source connection list supplied"))
    for e in edges:
        if (e["from"], e["to"]) not in declared_pairs:
            findings.append(finding("trace.edge_not_in_source", "high", "drawn edge is absent from source connection list", edge=[e["from"], e["to"]]))
    stats = {"checked": bool(mats), "materials": len(mats), "connections": len(connections),
             "nodes_traced": sum(1 for n in spec["nodes"] if str(n.get("evidence") or "") in mats),
             "edges_source_bound": sum(1 for e in edges if (e["from"], e["to"]) in declared_pairs)}
    return findings, sources, stats


def boxes_overlap(a, b, padding=0.0) -> bool:
    return not (a[2] + padding <= b[0] or b[2] + padding <= a[0]
                or a[3] + padding <= b[1] or b[3] + padding <= a[1])


def segment_hits_box(x1, y1, x2, y2, box) -> bool:
    """Liang–Barsky segment/rectangle intersection used for unrelated-node routing."""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - box[0]), (dx, box[2] - x1),
                 (-dy, y1 - box[1]), (dy, box[3] - y1)):
        if p == 0:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


def structure_audit(spec: dict, layout: dict, nodes: list[dict], edges: list[dict], svg_path: Path) -> tuple[list[dict], dict]:
    findings: list[dict] = []
    try:
        root = ET.parse(svg_path).getroot()
    except (ET.ParseError, OSError) as exc:
        return [finding("export.svg_unreadable", "high", f"written SVG cannot be parsed: {exc}")], {"xml_parsed": False}
    all_ids = [el.get("id") for el in root.iter() if el.get("id")]
    duplicates = sorted({x for x in all_ids if all_ids.count(x) > 1})
    if duplicates:
        findings.append(finding("export.duplicate_svg_ids", "high", "duplicate SVG ids break element addressability", ids=duplicates[:20]))
    W, H = layout["width"], layout["height"]
    by_id = {el.get("id"): el for el in root.iter() if el.get("id")}
    for rec in nodes:
        gid = f'node-{rec["id"]}'
        group = by_id.get(gid)
        if group is None:
            findings.append(finding("svg.node_missing", "high", "semantic node group missing after serialization", node=rec["id"]))
            continue
        texts = [''.join(el.itertext()) for el in group.iter() if el.tag == f'{{{SVG_NS}}}text']
        own = ''.join(texts)
        for line in rec["lines"]:
            if line not in own:
                findings.append(finding("label.mismatch", "high", "node text/number/unit missing from SVG", node=rec["id"], expected=line))
        x0, y0, x1, y1 = rec["bbox"]
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            findings.append(finding("label.outside_canvas", "high", "node box or label extent leaves the canvas", node=rec["id"], bbox=rec["bbox"], canvas=[W, H]))
        colour = str(rec["colour"]).lower()
        if colour not in SAFE_COLOURS:
            findings.append(finding("colour.not_cb_safe", "low", "node colour is outside the Okabe-Ito palette", node=rec["id"], colour=colour))
        if rec.get("compartment"):
            comps = spec.get("compartments") or []
            match = [c for c in comps if isinstance(c, dict) and str(c.get("id")) == str(rec["compartment"])]
            if not match:
                findings.append(finding("compartment.undeclared", "medium", "node compartment was never declared", node=rec["id"], compartment=rec["compartment"]))
            elif match[0].get("layers") and rec["layer"] not in match[0]["layers"]:
                findings.append(finding("compartment.mismatch", "high", "node layer contradicts its declared biological compartment", node=rec["id"], compartment=rec["compartment"], layer=rec["layer"]))
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if boxes_overlap(a["bbox"], b["bbox"]):
                findings.append(finding("layout.node_overlap", "high", "node bounding boxes overlap after layout relaxation", nodes=[a["id"], b["id"]]))
    node_by_id = {r["id"]: r for r in nodes}
    for e in edges:
        group = by_id.get(f'edge-{e["id"]}')
        if group is None:
            findings.append(finding("svg.edge_missing", "high", "semantic connector group missing", edge=e["id"]))
            continue
        route_kind = e.get("route", {}).get("kind", "line")
        expected_tag = "path" if route_kind == "feedback_arc" else "line"
        geometries = [el for el in group.iter() if el.tag == f'{{{SVG_NS}}}{expected_tag}'
                      and (expected_tag == "line" or el.get("d") is not None)]
        if len(geometries) != 1:
            findings.append(finding("svg.connector_missing", "high", "connector does not contain exactly one expected geometry primitive", edge=e["id"], expected=expected_tag))
            continue
        geometry = geometries[0]
        if route_kind == "feedback_arc":
            actual_path = geometry.get("d")
            if actual_path != e["route"]["d"]:
                findings.append(finding("edge.geometry_mismatch", "high", "serialized feedback path differs from the non-crossing route", edge=e["id"], expected=e["route"]["d"], actual=actual_path))
            if not 0 <= e["route"].get("control_y", -1) <= H:
                findings.append(finding("edge.route_outside_canvas", "high", "feedback control corridor leaves the canvas", edge=e["id"]))
        else:
            actual = [fnum(float(geometry.get(k))) for k in ("x1", "y1", "x2", "y2")]
            expected = e["start"] + e["end"]
            if any(abs(a - b) > .02 for a, b in zip(actual, expected)):
                findings.append(finding("edge.geometry_mismatch", "high", "serialized connector ports differ from computed source/target anchors", edge=e["id"], expected=expected, actual=actual))
            for other in nodes:
                if other["id"] in (e["from"], e["to"]):
                    continue
                if segment_hits_box(e["start"][0], e["start"][1], e["end"][0], e["end"][1], other["bbox"]):
                    findings.append(finding("edge.crosses_unrelated_node", "high", "direct connector crosses a third-party scientific entity instead of routing around it", edge=e["id"], crossed_node=other["id"]))
        if group.get("data-from") != e["from"] or group.get("data-to") != e["to"] or group.get("data-type") != e["type"]:
            findings.append(finding("edge.semantics_mismatch", "high", "connector from/to/type attributes changed", edge=e["id"]))
        sx, sy = e["start"]; tx, ty = e["end"]
        if math.hypot(tx - sx, ty - sy) < 1:
            findings.append(finding("edge.zero_length", "high", "connector has zero visual length", edge=e["id"]))
        src_layer = node_by_id[e["from"]]["layer"]; dst_layer = node_by_id[e["to"]]["layer"]
        backwards = dst_layer <= src_layer
        if backwards and e["type"] in ("activate", "inhibit") and not e["feedback"]:
            findings.append(finding("edge.feedback_unlabeled", "medium", "backward regulation must be explicitly marked feedback=true", edge=e["id"]))
        if backwards and e["type"] == "flow" and not e["recycle"]:
            findings.append(finding("edge.backward_flow", "medium", "backward material/route flow must be explicitly marked recycle=true or feedback=true", edge=e["id"]))
        marker = geometry.get("marker-end") or ""
        if marker != f'url(#arrow-{e["type"]})':
            findings.append(finding("edge.arrowhead_mismatch", "high", "arrowhead no longer encodes the declared biological/relation type", edge=e["id"], marker=marker))
    checks = {"xml_parsed": True, "svg_ids": len(all_ids), "semantic_nodes": len(nodes),
              "semantic_edges": len(edges), "node_overlaps": sum(f["rule"] == "layout.node_overlap" for f in findings),
              "ports_checked": len(edges) * 2, "labels_checked": sum(len(r["lines"]) for r in nodes),
              "feedback_arcs": sum(bool(e.get("feedback") or e.get("recycle")) for e in edges),
              "bypass_arcs": sum(e.get("route", {}).get("reason") == "unrelated-node-bypass" for e in edges),
              "crossings": sum(f["rule"] == "edge.crosses_unrelated_node" for f in findings),
              "visual_inspection": "not performed; XML/geometry/magic-byte checks only"}
    return findings, checks


def _png_size_dpi(path: Path) -> tuple[int | None, float | None]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
        return None, None
    width = struct.unpack(">I", data[16:20])[0]
    dpi = None
    offset = 8
    while offset + 12 <= len(data):
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        if kind == b"pHYs" and len(payload) == 9 and payload[8] == 1:
            dpi = struct.unpack(">I", payload[:4])[0] * .0254
            break
        offset += size + 12
    return width, dpi


def _mpl_polygon(ax, points, **kwargs):
    from matplotlib.patches import Polygon
    kwargs.setdefault("closed", True)
    patch = Polygon(points, **kwargs)
    ax.add_patch(patch)
    return patch


def export_previews(spec: dict, layout: dict, nodes: list[dict], edges: list[dict], out_dir: Path,
                    font_family: str | None = None) -> tuple[list[dict], list[dict]]:
    """Redraw exactly the mapping geometry with matplotlib to real PNG and PDF."""
    findings: list[dict] = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
        import fontsel
    except Exception as exc:
        return [], [finding("export.unavailable", "medium", "matplotlib unavailable; editable SVG retained but PNG/PDF were not generated", detail=f"{type(exc).__name__}: {exc}")]
    matplotlib.rcParams["pdf.fonttype"] = 42
    if font_family:
        matplotlib.rcParams["font.family"] = [font_family]
    text_for_font = "\n".join([r["label"] for r in nodes] + [e["label"] for e in edges]
                              + [line for entry, lines in layout["legend"] for line in lines])
    resolved = fontsel.resolve(text_for_font)
    if resolved.path:
        try:
            from matplotlib import font_manager
            font_manager.fontManager.addfont(resolved.path)
            matplotlib.rcParams["font.family"] = [resolved.family]
        except Exception:
            pass
    W, H = layout["width"], layout["height"]
    fig, ax = plt.subplots(figsize=(W / 96, H / 96), dpi=96)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    from matplotlib.patches import FancyArrowPatch
    # Compartment backgrounds are part of the same semantic mapping, not SVG-only
    # decoration.  Draw them before connectors/nodes so the PDF/PNG preview agrees.
    for comp in spec.get("compartments") or []:
        if not isinstance(comp, dict) or comp.get("id") is None:
            continue
        layers = comp.get("layers") or []
        members = [r for r in nodes if r.get("compartment") == comp.get("id") or r["layer"] in layers and any(n["id"] == r["id"] and n.get("compartment") == comp.get("id") for n in spec["nodes"])]
        if not members:
            continue
        x0 = min(r["bbox"][0] for r in members) - 12; y0 = min(r["bbox"][1] for r in members) - 30
        x1 = max(r["bbox"][2] for r in members) + 12; y1 = max(r["bbox"][3] for r in members) + 12
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=str(comp.get("color") or "#EDEDED"), edgecolor="#999999", linewidth=.8, linestyle="--", alpha=.45, zorder=0))
        ax.text(x0 + 6, y0 + 18, str(comp.get("label") or comp["id"]), ha="left", va="baseline", fontsize=8, color="#444444", zorder=1)
    for e in edges:
        colour = FLOW_COLOURS.get(e.get("flow_kind"), TYPE_COLOURS.get(e["type"], "#666666"))
        style = "-[" if e["type"] == "inhibit" else "-" if e["type"] == "bind" else "-|>" if e["type"] in TYPE_LABELS else "-"
        dash = CONFIDENCE_DASH.get(str(e.get("confidence") or "")) or FLOW_DASH.get(e.get("flow_kind"))
        if e["type"] == "bind" and not dash:
            dash = "7,4"
        linestyle = "--" if dash and "," in dash and dash.startswith("8") else ":" if dash else "-"
        if e.get("route", {}).get("kind") == "feedback_arc":
            from matplotlib.path import Path as MplPath
            from matplotlib.patches import PathPatch
            sx, sy = e["start"]; ex, ey = e["end"]; cy = e["route"]["control_y"]
            curve = MplPath([(sx, sy), (sx, cy), (ex, cy), (ex, ey)],
                            [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4])
            ax.add_patch(PathPatch(curve, facecolor="none", edgecolor=colour,
                                   linewidth=1.5, linestyle=linestyle, zorder=3))
            # Match SVG's final tangent and marker exactly at the target anchor.
            pre_y = ey - 12 if ey > cy else ey + 12
            arrow = FancyArrowPatch((ex, pre_y), (ex, ey), arrowstyle=style,
                                    mutation_scale=13, linewidth=1.5, color=colour,
                                    linestyle=linestyle, shrinkA=0, shrinkB=0, zorder=3)
        else:
            arrow = FancyArrowPatch(tuple(e["start"]), tuple(e["end"]), arrowstyle=style,
                                    mutation_scale=13, linewidth=1.5, color=colour,
                                    linestyle=linestyle, shrinkA=0, shrinkB=0, zorder=3)
        ax.add_patch(arrow)
        if e["type"] == "bind":
            ax.add_patch(Circle(tuple(e["end"]), 3.6, facecolor=colour, edgecolor=colour, zorder=4))
        elif e["type"] not in TYPE_LABELS:
            ex, ey = e["end"]
            _mpl_polygon(ax, [(ex, ey - 6), (ex + 6, ey), (ex, ey + 6), (ex - 6, ey)], facecolor="white", edgecolor="#D55E00", linewidth=1.5, zorder=4)
        if e["label"]:
            ax.text(e["label_pos"][0], e["label_pos"][1], e["label"], ha="center", va="center",
                    fontsize=max(7, layout["font_pt"] - 1), color=colour, zorder=4)
    for n, rec in zip(spec["nodes"], nodes):
        x0, y0, x1, y1 = rec["bbox"]; cx, cy = rec["center"]
        w, h = x1 - x0, y1 - y0
        kind = str(n.get("part_kind") or n.get("kind") or "").lower()
        fc, ec = rec["colour"], "#0072B2" if n.get("milestone") else "#263238"
        if kind in ("pump", "sensor", "detector"):
            ax.add_patch(Circle((cx, cy), min(w, h) / 2 - 3, facecolor=fc, edgecolor=ec, alpha=.82, linewidth=1.2, zorder=2))
            if kind == "pump":
                r = min(w, h) / 2 - 3
                ty = cy - r * .45
                _mpl_polygon(ax, [(cx - r * .35, ty - r * .30), (cx + r * .45, ty), (cx - r * .35, ty + r * .30)], facecolor=ec, edgecolor=ec, zorder=2)
        elif kind == "valve":
            _mpl_polygon(ax, [(x0, cy - h * .25), (cx, cy), (x0, cy + h * .25)], facecolor=fc, edgecolor=ec, alpha=.82, zorder=2)
            _mpl_polygon(ax, [(x1, cy - h * .25), (cx, cy), (x1, cy + h * .25)], facecolor=fc, edgecolor=ec, alpha=.82, zorder=2)
        elif kind in ("source", "sink"):
            _mpl_polygon(ax, [(cx, y0), (x1, cy), (cx, y1), (x0, cy)], facecolor=fc, edgecolor=ec, alpha=.82, zorder=2)
        else:
            ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle=f"round,pad=0,rounding_size={min(10, h / 3) if kind != 'complex' else 2}", facecolor=fc, edgecolor=ec, alpha=.82, linewidth=1.2, zorder=2))
            if kind == "complex":
                ax.add_patch(Rectangle((x0 + 5, y0 + 5), max(1, w - 10), max(1, h - 10), facecolor="none", edgecolor=ec, linewidth=.8, zorder=2))
            if kind == "receptor":
                ax.plot([cx, cx], [y0, y1], color=ec, linewidth=.8, zorder=2)
        italic = n.get("italic") if n.get("italic") is not None else n.get("kind") == "gene"
        ax.text(cx, cy, "\n".join(rec["lines"]), ha="center", va="center", multialignment="center",
                fontsize=layout["font_pt"], style="italic" if italic else "normal", color="#17202A", zorder=4)
    ly = layout["title_h"] + layout["usable_h"] + 24
    for entry, lines in layout["legend"]:
        typ = entry.get("relation")
        flow_kind = entry.get("flow_kind")
        colour = FLOW_COLOURS.get(flow_kind, TYPE_COLOURS.get(typ, entry.get("colour", "#666666"))) if entry["kind"] == "flow" else TYPE_COLOURS.get(typ, entry.get("colour", "#666666"))
        if entry["kind"] == "category":
            ax.add_patch(Rectangle((28, ly - 10), 16, 12, facecolor=colour, edgecolor="#333333", linewidth=.6, clip_on=False))
        elif entry["kind"] in ("relation", "flow"):
            dash = FLOW_DASH.get(flow_kind) if entry["kind"] == "flow" else "7,4" if typ == "bind" else None
            legend_linestyle = "--" if dash and dash.startswith("8") or typ == "bind" else ":" if dash else "-"
            ax.plot([28, 48], [ly - 4, ly - 4], color=colour, linewidth=1.4, linestyle=legend_linestyle, clip_on=False)
            if typ == "bind":
                ax.add_patch(Circle((48, ly - 4), 3, facecolor=colour, edgecolor=colour, clip_on=False))
            elif typ == "inhibit":
                ax.plot([48, 48], [ly - 10, ly + 2], color=colour, linewidth=1.4, clip_on=False)
            elif typ:
                _mpl_polygon(ax, [(46, ly - 8), (52, ly - 4), (46, ly)], facecolor=colour, edgecolor=colour, clip_on=False)
        ax.text(56, ly, "\n".join(lines), ha="left", va="baseline", fontsize=max(6, layout["font_pt"] - 2), color="#333333", linespacing=1.25)
        ly += len(lines) * max(18, layout["font_px"] * 1.45)
    if spec.get("title"):
        ax.text(28, 30, str(spec["title"]), ha="left", va="baseline", fontsize=layout["font_pt"] + 3, fontweight="bold", color="#17202A")
    png, pdf = out_dir / "figure.png", out_dir / "figure.pdf"
    try:
        fig.savefig(png, dpi=300, facecolor="white", metadata={"Software": VERSION})
        # Stable metadata makes the complete result (which includes artifact
        # hashes) idempotent; no wall-clock timestamp enters the deliverable.
        fig.savefig(pdf, format="pdf", facecolor="white",
                    metadata={"CreationDate": None, "Title": str(spec.get("title") or "Scientific figure"),
                              "Creator": VERSION, "Producer": "Matplotlib"})
    except Exception as exc:
        plt.close(fig)
        return [], [finding("export.unavailable", "medium", "PNG/PDF rendering failed; editable SVG retained", detail=f"{type(exc).__name__}: {exc}")]
    plt.close(fig)
    descriptors = []
    width, actual_dpi = _png_size_dpi(png)
    descriptors.append({"path": str(png), "format": "png", "bytes": png.stat().st_size,
                        "magic_ok": png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
                        "sha256": sha_bytes(png.read_bytes()), "width_px": width,
                        "dpi": fnum(actual_dpi, 2) if actual_dpi else None})
    if actual_dpi is not None and actual_dpi < 299:
        findings.append(finding("export.low_dpi", "medium", "PNG pHYs metadata is below 300 dpi", dpi=actual_dpi))
    pdf_bytes = pdf.read_bytes()
    descriptors.append({"path": str(pdf), "format": "pdf", "bytes": len(pdf_bytes),
                        "magic_ok": pdf_bytes.startswith(b"%PDF"), "sha256": sha_bytes(pdf_bytes),
                        "vector_text": True, "font_embedded": b"/FontFile" in pdf_bytes,
                        "font_embedding_check": "PDF /FontFile marker present" if b"/FontFile" in pdf_bytes else "not detected"})
    if not pdf_bytes.startswith(b"%PDF"):
        findings.append(finding("export.pdf_invalid", "high", "PDF magic header is missing"))
    if resolved.missing:
        findings.append(finding("export.missing_glyphs", "high", "resolved font lacks characters used by the figure", characters="".join(resolved.missing)[:60], font=resolved.family))
    return descriptors, findings


def choose_font(spec: dict) -> tuple[str | None, list[dict]]:
    try:
        import fontsel
        report = fontsel.resolve(fontsel.labels_text(spec))
        findings = []
        if report.path is None:
            findings.append(finding("export.no_font", "high", "no font file could be resolved for live text", family=report.family))
        elif report.missing:
            findings.append(finding("export.missing_glyphs", "high", "resolved font lacks figure characters", characters="".join(report.missing)[:60], family=report.family))
        return report.family, findings
    except Exception as exc:
        return None, [finding("export.font_check_unavailable", "medium", "font coverage could not be checked because matplotlib/fonttools is unavailable", detail=type(exc).__name__)]


def source_file_records(spec: dict) -> list[dict]:
    records = []
    for item in spec.get("source_files") or []:
        if isinstance(item, str):
            path = Path(item); role = "source"; locator = item
        elif isinstance(item, dict) and item.get("path"):
            path = Path(str(item["path"])); role = str(item.get("role") or "source"); locator = str(item.get("source") or item["path"])
        else:
            continue
        rec = {"path": str(path), "role": role, "locator": locator}
        try:
            rec["version_sha256"] = sha_bytes(path.read_bytes())
            rec["bytes"] = path.stat().st_size
        except OSError as exc:
            rec["read_error"] = type(exc).__name__
        records.append(rec)
    return records


def merge_meta(result: dict, meta_path: Path | None) -> None:
    if meta_path is None:
        return
    try:
        meta = read_object(meta_path, "meta", required=True)
    except SpecError as exc:
        result["findings"].append(finding("meta.unreadable", "medium", str(exc)))
        result.setdefault("limits", []).append("meta file was not merged because it was unreadable")
        return
    for key in ("sources", "uncertainty", "limits"):
        value = meta.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            result.setdefault(key, []).extend(value)
        else:
            result.setdefault(key, []).append(value)


def edit_svg_document(source: Path, edits: list, destination: Path) -> tuple[dict, list[dict]]:
    """Apply addressed text/fill/marker edits while retaining unrelated XML."""
    findings: list[dict] = []
    try:
        original_bytes = source.read_bytes()
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.fromstring(original_bytes, parser=parser)
    except (OSError, ET.ParseError) as exc:
        raise SpecError(f"source SVG cannot be edited: {exc}") from exc
    ET.register_namespace("", SVG_NS)
    before = {"elements": sum(1 for _ in root.iter()), "text": sum(1 for e in root.iter() if e.tag == f'{{{SVG_NS}}}text')}
    def body_counts():
        defs = [d for d in root.iter() if d.tag == f'{{{SVG_NS}}}defs']
        excluded = {id(x) for d in defs for x in d.iter()}
        body = [e for e in root.iter() if id(e) not in excluded]
        return {"elements": len(body), "text": sum(e.tag == f'{{{SVG_NS}}}text' for e in body)}
    body_before = body_counts()
    by_id = {e.get("id"): e for e in root.iter() if e.get("id")}
    records = []
    if not isinstance(edits, list):
        raise SpecError("edits JSON must be a list of edit objects")
    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise SpecError(f"edit {i} is not an object")
        target = str(edit.get("target_id") or edit.get("node_id") or "")
        op = str(edit.get("op") or "rename")
        candidates = [target, f"node-{target}", f"node-{target}-label", f"edge-{target}", f"edge-{target}-label"]
        element = next((by_id[x] for x in candidates if x in by_id), None)
        if element is None:
            raise SpecError(f"edit {i}: target_id {target!r} not found; no approximate/fuzzy edit is allowed")
        if op in ("rename", "set_text"):
            label = edit.get("new_label", edit.get("text"))
            if not isinstance(label, (str, int, float)):
                raise SpecError(f"edit {i}: new_label is required")
            text_el = element if element.tag == f'{{{SVG_NS}}}text' else next((e for e in element.iter() if e.tag == f'{{{SVG_NS}}}text'), None)
            if text_el is None:
                raise SpecError(f"edit {i}: target has no live text element")
            tspans = [e for e in text_el.iter() if e.tag == f'{{{SVG_NS}}}tspan']
            if tspans:
                value = element.get("data-value-text") or ""
                has_value_line = bool(value and len(tspans) > 1 and ''.join(tspans[-1].itertext()) == value)
                label_lines = tspans[:-1] if has_value_line else tspans
                label_lines[0].text = str(label)
                for extra in label_lines[1:]:
                    extra.text = ""
                # The separately declared value+unit tspan is unrelated content
                # and deliberately survives a label-only edit.
            else:
                text_el.text = str(label)
        elif op in ("recolour", "set_color"):
            colour = str(edit.get("color") or edit.get("colour") or "")
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour):
                raise SpecError(f"edit {i}: color must be #RRGGBB")
            if colour.lower() not in SAFE_COLOURS:
                findings.append(finding("colour.not_cb_safe", "low", "edited colour is outside Okabe-Ito", target_id=target, colour=colour))
            shapes = [element] if element.tag.split('}')[-1] in ("rect", "circle", "polygon", "polyline", "path") else [e for e in element.iter() if e.tag.split('}')[-1] in ("rect", "circle", "polygon", "polyline", "path")]
            if not shapes:
                raise SpecError(f"edit {i}: no shape to recolour")
            for shape in shapes:
                shape.set("fill", colour)
        elif op == "set_relation_type":
            new_type = canonical_type(edit.get("new_type"))
            if new_type not in TYPE_LABELS or element.get("data-type") is None:
                raise SpecError(f"edit {i}: a declared relation edge and supported new_type are required")
            old_type = element.get("data-type")
            element.set("data-type", new_type)
            for line in element.iter(f'{{{SVG_NS}}}line'):
                line.set("marker-end", f"url(#arrow-{new_type})")
                line.set("stroke", TYPE_COLOURS[new_type])
            # Define the newly used marker if it was not present in the source.
            marker_id = f"arrow-{new_type}"
            defs = next((e for e in root.iter() if e.tag == f'{{{SVG_NS}}}defs'), None)
            if defs is None:
                defs = ET.Element(f'{{{SVG_NS}}}defs'); root.insert(1, defs)
            if not any(e.get("id") == marker_id for e in defs):
                colour = TYPE_COLOURS[new_type]
                marker = ET.SubElement(defs, f'{{{SVG_NS}}}marker', {"id": marker_id, "markerWidth": "14", "markerHeight": "14", "refX": "11", "refY": "6", "orient": "auto", "markerUnits": "userSpaceOnUse"})
                if new_type == "inhibit":
                    ET.SubElement(marker, f'{{{SVG_NS}}}path', {"d": "M 9 0 L 9 12", "stroke": colour, "stroke-width": "2.4"})
                elif new_type == "bind":
                    ET.SubElement(marker, f'{{{SVG_NS}}}circle', {"cx": "6", "cy": "6", "r": "3.2", "fill": colour})
                else:
                    ET.SubElement(marker, f'{{{SVG_NS}}}path', {"d": "M0 0 L12 6 L0 12 Z", "fill": colour})
        else:
            raise SpecError(f"edit {i}: unsupported op {op}")
        records.append({"sequence": i + 1, "op": op, "target_id": target, "new_label": edit.get("new_label"), "color": edit.get("color") or edit.get("colour"), "new_type": edit.get("new_type")})
    after = {"elements": sum(1 for _ in root.iter()), "text": sum(1 for e in root.iter() if e.tag == f'{{{SVG_NS}}}text')}
    body_after = body_counts()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    # Ensure no unrelated elements disappeared and all addressed edits left XML valid.
    ET.parse(destination)
    report = {"source_svg": str(source), "edited_svg": str(destination),
              "source_sha256": sha_bytes(original_bytes), "edited_sha256": sha_bytes(destination.read_bytes()),
              "before": before, "after": after, "body_before": body_before, "body_after": body_after,
              "unrelated_elements_preserved": body_before == body_after,
              "change_records": records}
    if body_before != body_after:
        findings.append(finding("edit.structure_changed", "medium", "edit added or removed non-defs XML elements; review change records"))
    return report, findings


def write_refusal(out_dir: Path, message: str, case: dict | None = None,
                  spec: dict | None = None, code="audit.no_render") -> dict:
    result = {"schema_version": VERSION, "status": "undetermined", "reason": code,
              "findings": [finding(code, "high", message)],
              "severity_counts": {"high": 1}, "exports": [], "sources": [],
              "uncertainty": [message], "limits": ["the case could not be run as declared"],
              "visual_inspection": "not performed"}
    result = apply_contract(result, spec, case)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def generate(spec_path: Path, out_dir: Path, mode: str, case_path: Path | None,
             meta_path: Path | None, checklist_path: Path | None) -> dict:
    case = read_object(case_path, "case", required=True) if case_path else {}
    raw = read_object(spec_path, "spec", required=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    spec, findings, limits = normalise_spec(raw, mode)
    layout, layout_findings = make_layout(spec, mode)
    findings.extend(layout_findings)
    spec_sha = sha_bytes(canonical_bytes(raw))
    nodes, edges = semantic_records(spec, layout)
    svg_text = build_svg(spec, layout, nodes, edges, spec_sha)
    # Pure function serialization is repeated as a deterministic generation check.
    repeat_layout, _ = make_layout(spec, mode)
    repeat_nodes, repeat_edges = semantic_records(spec, repeat_layout)
    svg_repeat = build_svg(spec, repeat_layout, repeat_nodes, repeat_edges, spec_sha)
    if svg_text != svg_repeat:
        findings.append(finding("repro.nondeterministic", "high", "two independent SVG serializations differ"))
    svg_path = out_dir / "figure.svg"
    svg_path.write_text(svg_text, encoding="utf-8")
    (out_dir / "spec.json").write_text(json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    structural, checks = structure_audit(spec, layout, nodes, edges, svg_path)
    findings.extend(structural)
    prov_findings, sources, prov = provenance_audit(spec, edges)
    findings.extend(prov_findings)
    if checklist_path:
        try:
            checklist = read_object(checklist_path, "checklist", required=True)
            expected_nodes = {str(e.get("id")) for e in checklist.get("entities") or [] if isinstance(e, dict)}
            expected_edges = {(str(e.get("from")), str(e.get("to"))) for e in checklist.get("relations") or [] if isinstance(e, dict)}
            have_nodes = {r["id"] for r in nodes}; have_edges = {(e["from"], e["to"]) for e in edges}
            missing_n = sorted(expected_nodes - have_nodes); missing_e = sorted(expected_edges - have_edges)
            if missing_n or missing_e:
                findings.append(finding("coverage.incomplete", "high", "figure omits checklist entities or relations", missing_entities=missing_n, missing_relations=[list(x) for x in missing_e]))
            checks["coverage"] = {"expected_entities": len(expected_nodes), "present_entities": len(expected_nodes & have_nodes), "expected_relations": len(expected_edges), "present_relations": len(expected_edges & have_edges)}
        except SpecError as exc:
            findings.append(finding("checklist.unreadable", "medium", str(exc)))
    family_audits = {}
    if mode == "pathway":
        try:
            import nomenclature
            nom = nomenclature.audit_nomenclature(spec, svg_path, spec["nodes"])
            findings.extend(nom["findings"]); family_audits["nomenclature"] = {"status": nom["status"], "fonts_checked": nom["fonts_checked"], "species": nom["species"]}
        except ImportError:
            limits.append("optional nomenclature.py not present; registry/style audit not executed")
    if mode == "apparatus":
        try:
            import apparatus
            struct = apparatus.audit_apparatus(spec)
            findings.extend(struct["findings"]); family_audits["apparatus"] = {"status": struct["status"], "figure_kind": struct["figure_kind"]}
        except ImportError:
            limits.append("optional apparatus.py not present; BOM/route audit not executed")
    font_family, font_findings = choose_font(spec)
    findings.extend(font_findings)
    exports, export_findings = export_previews(spec, layout, nodes, edges, out_dir, font_family)
    findings.extend(export_findings)
    if not exports:
        limits.append("PNG/PDF are unavailable; the result is partial despite a valid editable SVG")
    svg_desc = {"path": str(svg_path), "format": "svg", "bytes": svg_path.stat().st_size,
                "magic_ok": True, "sha256": sha_bytes(svg_path.read_bytes()), "live_text": True,
                "semantic_layers": ["compartments", "nodes", "edges", "legend"]}
    exports = [svg_desc] + exports
    mapping = {"schema_version": VERSION, "case_id": case.get("case_id", raw.get("case_id")), "mode": mode,
               "spec_sha256": spec_sha, "svg_sha256": svg_desc["sha256"], "canvas": {k: layout[k] for k in ("width", "height", "width_mm", "height_mm")},
               "nodes": nodes, "edges": edges,
               "legend": [{"text": entry["text"], "kind": entry["kind"], "lines": lines} for entry, lines in layout["legend"]],
               "checks": checks}
    (out_dir / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    for item in exports:
        if not item.get("magic_ok", False):
            findings.append(finding("export.magic_invalid", "high", "export magic signature mismatch", path=item["path"]))
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    status = "clean" if not findings else "blocked" if counts.get("high") else "review"
    figure = {"svg": str(svg_path), "png": str(out_dir / "figure.png") if (out_dir / "figure.png").exists() else None,
              "pdf": str(out_dir / "figure.pdf") if (out_dir / "figure.pdf").exists() else None,
              "spec": str(out_dir / "spec.json"), "mapping": str(out_dir / "mapping.json")}
    result = {"case_id": case.get("case_id", raw.get("case_id")), "schema_version": VERSION,
              "status": status, "partial": status != "clean", "figure_kind": spec["figure_kind"], "renderer_mode": mode,
              "input": {"spec_path": str(spec_path), "spec_sha256": spec_sha,
                        "case_path": str(case_path) if case_path else None},
              "figure": figure, "source": str(svg_path), "editable_source": str(svg_path),
              "exports": exports, "export": {"formats": [x["format"] for x in exports],
                      "dpi": 300 if any(x["format"] == "png" for x in exports) else None,
                      "canvas_mm": raw.get("canvas_mm"), "live_text": True,
                      "font_family": font_family, "visual_inspection": checks["visual_inspection"]},
              "findings": findings, "severity_counts": counts, "checked": checks,
              "visual_check": checks["visual_inspection"],
              "provenance": prov, "sources": sources + source_file_records(raw),
              "uncertainty": list(limits), "limits": list(limits),
              "reproducibility": {"deterministic": not any(f["rule"] == "repro.nondeterministic" for f in findings), "comparison": "two pure SVG serializations plus semantic map; image/PDF timestamps not compared"},
              "change_records": [{"sequence": 1, "action": "source-bound generate", "input_sha256": spec_sha, "engine": VERSION, "outputs": ["figure.svg", "mapping.json", "spec.json"] + [Path(x["path"]).name for x in exports if x["format"] != "svg"]}],
              "audits": family_audits}
    merge_meta(result, meta_path)
    counts = {}
    for f in result["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    result["severity_counts"] = counts
    result["status"] = "clean" if not result["findings"] else "blocked" if counts.get("high") else "review"
    result["partial"] = result["status"] != "clean"
    derived = {"figure_svg": figure["svg"], "figure_png": figure["png"], "figure_pdf": figure["pdf"],
               "editable_svg": figure["svg"], "source_file": figure["svg"],
               "preview": figure["png"], "preview_png": figure["png"], "preview_pdf": figure["pdf"],
               "pdf": figure["pdf"], "export_pdf": figure["pdf"], "font_report": result["export"],
               "export_check": result["export"], "mapping": mapping, "mapping_json": figure["mapping"],
               "figure_audit": {"findings": findings, "checked": checks}, "ledger": {"nodes": nodes, "edges": edges}}
    result = apply_contract(result, raw, case, derived)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def run_edit(source_path: Path, edits_path: Path, out_dir: Path, case_path: Path | None,
             spec_path: Path | None) -> dict:
    case = read_object(case_path, "case", required=True) if case_path else {}
    raw = read_object(spec_path, "spec") if spec_path else {}
    edits = read_json(edits_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    report, findings = edit_svg_document(source_path, edits, out_dir / "figure.svg")
    limits = ["SVG editing preserves unrelated XML; PNG/PDF re-rendering of arbitrary third-party SVG is not available without a compatible SVG renderer"]
    if spec_path:
        # A caller may provide the updated spec for reproducible preview export.  The
        # preserved SVG remains primary; regenerated files are explicitly named.
        preview_dir = out_dir / "preview_from_spec"
        preview_dir.mkdir(parents=True, exist_ok=True)
        try:
            spec, more_findings, more_limits = normalise_spec(raw, str(raw.get("figure_kind") or "schematic"))
            layout, lf = make_layout(spec, spec["figure_kind"]); findings.extend(more_findings + lf)
            nodes, edges = semantic_records(spec, layout)
            preview_exports, ef = export_previews(spec, layout, nodes, edges, preview_dir)
            findings.extend(ef)
            report["preview_from_spec"] = [x["path"] for x in preview_exports]
        except SpecError as exc:
            findings.append(finding("edit.preview_spec_invalid", "medium", str(exc)))
    counts = {"high": sum(f["severity"] == "high" for f in findings),
              "medium": sum(f["severity"] == "medium" for f in findings),
              "low": sum(f["severity"] == "low" for f in findings)}
    counts = {k: v for k, v in counts.items() if v}
    status = "blocked" if counts.get("high") else "review"
    result = {"case_id": case.get("case_id", raw.get("case_id")), "schema_version": VERSION,
              "status": status, "partial": True, "figure_kind": "source-preserving-edit",
              "editable_source": str(out_dir / "figure.svg"), "source": str(out_dir / "figure.svg"),
              "figure": {"svg": str(out_dir / "figure.svg"), "png": None, "pdf": None},
              "exports": [{"path": str(out_dir / "figure.svg"), "format": "svg", "bytes": (out_dir / "figure.svg").stat().st_size,
                           "magic_ok": True, "live_text": True, "sha256": report["edited_sha256"]}],
              "edit": report, "change_records": report["change_records"], "findings": findings,
              "severity_counts": counts, "sources": [], "uncertainty": limits, "limits": limits,
              "checked": {"xml_parsed": True, "unrelated_elements_preserved": report["unrelated_elements_preserved"],
                          "visual_inspection": "not performed; structural XML diff only"}}
    derived = {"figure_svg": result["figure"]["svg"], "editable_svg": result["figure"]["svg"],
               "editable_source": result["editable_source"], "source_file": result["source"],
               "figure_png": None, "figure_pdf": None, "exports": result["exports"],
               "visual_check": result["checked"]["visual_inspection"]}
    result = apply_contract(result, raw, case, derived)
    (out_dir / "mapping.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sourcebind", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("schematic", "pathway", "apparatus"), default="schematic")
    ap.add_argument("--spec", help="source-bound spec; optional only when case embeds spec.nodes")
    ap.add_argument("--case", help="original /input/case.json for case_id/output_contract")
    ap.add_argument("--case-id", help="explicit case id when no --case is supplied")
    ap.add_argument("--meta", help="optional sources/uncertainty/limits JSON")
    ap.add_argument("--checklist", help="optional source entity/relation checklist")
    ap.add_argument("--edit-svg", help="existing SVG to edit while preserving unrelated XML")
    ap.add_argument("--edits", help="JSON list of rename/recolour/set_relation_type edits")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    case_for_refusal = None
    spec_for_refusal = None
    try:
        # Parse and retain valid declarations up front so every later refusal can
        # still echo them.  A malformed case/spec itself honestly has no object
        # to echo; no placeholder structure is fabricated in its place.
        if args.case:
            case_for_refusal = read_object(Path(args.case), "case", required=True)
        if args.spec:
            spec_for_refusal = read_object(Path(args.spec), "spec", required=True)
        if args.edit_svg or args.edits:
            if not args.edit_svg or not args.edits:
                raise SpecError("--edit-svg and --edits must be supplied together")
            result = run_edit(Path(args.edit_svg), Path(args.edits), out,
                              Path(args.case) if args.case else None,
                              Path(args.spec) if args.spec else None)
        else:
            spec_path = Path(args.spec) if args.spec else None
            if spec_path is None:
                case = read_object(Path(args.case), "case", required=True)
                embedded = embedded_spec(case)
                if embedded is None:
                    raise SpecError("no drawing spec supplied and case has no explicit spec.nodes; extract the actual source material first")
                spec_path = out / "input_spec.json"
                out.mkdir(parents=True, exist_ok=True)
                spec_path.write_text(json.dumps(embedded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if args.case_id and not args.case:
                case_for_refusal = {"case_id": args.case_id}
                # Use a temporary carrier without changing the original spec.
                raw = read_object(spec_path, "spec", required=True)
                # Explicit CLI identity has priority over an example/spec default.
                raw["case_id"] = args.case_id
                carrier = out / "input_spec_with_case_id.json"
                out.mkdir(parents=True, exist_ok=True)
                carrier.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                spec_path = carrier
            result = generate(spec_path, out, args.mode,
                              Path(args.case) if args.case else None,
                              Path(args.meta) if args.meta else None,
                              Path(args.checklist) if args.checklist else None)
    except Exception as exc:
        # The CLI boundary must always leave a structured outcome, including for
        # wrong-typed nested declarations that survive initial JSON parsing.
        try:
            result = write_refusal(out, str(exc), case_for_refusal, spec_for_refusal)
        except OSError as write_exc:
            print(json.dumps({"status": "undetermined", "reason": "output_unwritable", "error": str(write_exc)}, ensure_ascii=False))
            return 5
    print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                      "findings": [f["rule"] for f in result.get("findings", [])],
                      "artifacts": result.get("figure", {}),
                      "wrote": str(out / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result["status"], 5)


if __name__ == "__main__":
    raise SystemExit(main())

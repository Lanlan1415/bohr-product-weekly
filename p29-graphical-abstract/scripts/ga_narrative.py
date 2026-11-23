"""Four-stage, source-bound graphical-abstract renderer.

SiliCoDraw's useful pattern is deliberately preserved: editable structured input,
numbered panels, connectors and a chart made from typed values.  Unlike an icon
collage, the renderer does not invent biological objects: only declarative roles,
source text and source numbers become marks.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

import fontsel
import schematic

ROLE_NAMES = {"problem": "INPUT / QUESTION", "method": "METHOD",
              "finding": "RESULT / MECHANISM", "conclusion": "CONCLUSION"}
ROLE_COLOURS = {"problem": "#D55E00", "method": "#0072B2",
                "finding": "#009E73", "conclusion": "#CC79A7"}


def _role(spec: dict, node: dict) -> str:
    declared = str(node.get("visual_role") or "").strip()
    if declared in ROLE_NAMES:
        return declared
    takeaways = spec.get("takeaways") or {}
    if not isinstance(takeaways, dict):
        takeaways = {}
    for role, node_id in takeaways.items():
        if node_id == node.get("id") and role in ROLE_NAMES:
            return role
    return "finding" if node.get("visual_data") else "method"


def _wrap(text: str, latin: int = 18, cjk: int = 10) -> str:
    text = str(text or "")
    width = cjk if re.search(r"[\u3400-\u9fff]", text) else latin
    return textwrap.fill(" ".join(text.split()), width=width,
                         break_long_words=True, break_on_hyphens=False)


def _stable_svg(path: Path, title: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"<svg\b[^>]*>", text, flags=re.S)
    if match:
        opening = match.group(0)
        if "role=" not in opening:
            opening = opening[:-1] + ' role="img">'
        text = (text[:match.start()] + opening
                + f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
                + text[match.end():])
    generated = []
    for found in re.finditer(r'\bid="([mph][0-9a-f]{10})"', text):
        if found.group(1) not in generated:
            generated.append(found.group(1))
    for index, old in enumerate(generated, 1):
        new = f"ga_def_{index:04d}"
        text = re.sub(rf'\bid="{re.escape(old)}"', f'id="{new}"', text)
        text = text.replace(f"#{old}", f"#{new}")
    path.write_text(text, encoding="utf-8")


def render(spec: dict, out_stem: Path, dpi: int = 300, fonttype: str = "none") -> dict:
    matplotlib.rcParams["svg.fonttype"] = fonttype
    matplotlib.rcParams["pdf.fonttype"] = 42
    font = fontsel.resolve(fontsel.labels_text(spec))
    if font.path:
        try:
            from matplotlib import font_manager
            font_manager.fontManager.addfont(font.path)
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["font.sans-serif"] = [font.family, "DejaVu Sans"]
        except Exception:
            pass

    nodes, edges = spec.get("nodes") or [], spec.get("edges") or []
    if not isinstance(nodes, list) or not nodes or any(not isinstance(n, dict) or not n.get("id") for n in nodes):
        raise ValueError("narrative spec requires non-empty nodes[] objects with ids")
    if not isinstance(edges, list) or any(not isinstance(e, dict) for e in edges):
        raise ValueError("edges must be an array of objects")
    nodes = sorted(nodes, key=lambda n: (int(n.get("layer", 0)), str(n.get("id"))))
    if len(nodes) > 5:
        raise ValueError("single-message graphical abstracts are limited to five narrative panels")
    dims = spec.get("canvas_mm") or [180, 90]
    if not isinstance(dims, (list, tuple)) or len(dims) != 2:
        raise ValueError("canvas_mm must have two dimensions")
    fig_w, fig_h = float(dims[0]) / 25.4, float(dims[1]) / 25.4
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    artists, aux, visual_marks = [], [], []

    def auxiliary(identifier: str, text, **kwargs):
        item = ax.text(s=str(text), **kwargs)
        aux.append({"id": identifier, "text": item})
        return item

    core = spec.get("core_message")
    if isinstance(core, dict):
        core_text = str(core.get("text") or "")
    else:
        core_text = str(core or spec.get("title") or "")
    if core_text:
        auxiliary("core_message", _wrap(core_text, latin=80, cjk=42), x=8, y=8.12,
                  ha="center", va="center", fontsize=10.2, fontweight="bold", color="#172B3A")
    ax.plot([0.55, 15.45], [7.52, 7.52], color="#CBD5E1", linewidth=0.9)

    count = len(nodes)
    spacing = 16.0 / count
    bw = min(3.25, spacing * 0.81)
    centres = [spacing * (index + 0.5) for index in range(count)]
    pos = {node["id"]: (centres[index], 4.55) for index, node in enumerate(nodes)}
    layout_depth = {node["id"]: int(node.get("layer", index)) for index, node in enumerate(nodes)}
    body_fs = float(spec.get("font_size", 8.4))

    for index, node in enumerate(nodes):
        x = centres[index]
        role = _role(spec, node)
        colour = str(node.get("color") or ROLE_COLOURS[role])
        node["_xy"] = pos[node["id"]]
        node["_colour"] = colour
        box = FancyBboxPatch((x - bw / 2, 2.12), bw, 4.78,
                             boxstyle="round,pad=0.03,rounding_size=0.10",
                             linewidth=1.45 if role == "conclusion" else 1.05,
                             edgecolor=colour, facecolor="#FFFFFF", zorder=2)
        ax.add_patch(box)
        ax.add_patch(Rectangle((x - bw / 2, 6.30), bw, 0.60, facecolor=colour,
                               edgecolor="none", alpha=0.16, zorder=2))
        auxiliary(f"role:{node['id']}", ROLE_NAMES[role], x=x, y=6.58,
                  ha="center", va="center", fontsize=6.6, fontweight="bold", color=colour, zorder=3)
        text = ax.text(x, 5.90, _wrap(node.get("label", node["id"])), ha="center", va="center",
                       fontsize=body_fs, zorder=4, color="#172B3A",
                       fontweight="bold" if role in ("finding", "conclusion") else "normal",
                       style="italic" if node.get("italic") or node.get("kind") == "gene" else "normal")
        artists.append({"node": node["id"], "text": text, "patch": box, "bbox_xy": pos[node["id"]]})

        if role == "problem":
            ax.add_patch(Circle((x, 3.93), 0.64, facecolor="#F8FAFC", edgecolor=colour,
                                linewidth=1.5, zorder=3))
            for offset in (-0.24, 0.0, 0.24):
                ax.plot([x - 0.34, x + 0.34], [3.93 + offset, 3.93 + offset],
                        color=colour, linewidth=1.0, zorder=4)
            auxiliary(f"input_note:{node['id']}", str(node.get("visual_caption") or "Source observation"),
                      x=x, y=2.73, ha="center", va="center", fontsize=6.4, color="#475569")
        elif role == "method":
            steps = node.get("steps") if isinstance(node.get("steps"), list) else []
            if steps:
                for step_index, step in enumerate(steps[:3]):
                    sy = 4.92 - step_index * 0.94
                    ax.add_patch(FancyBboxPatch((x - 1.15, sy - 0.30), 2.30, 0.60,
                                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                                facecolor="#EFF6FF", edgecolor=colour, linewidth=0.65))
                    auxiliary(f"method_step:{node['id']}:{step_index}", _wrap(step, latin=24, cjk=12),
                              x=x, y=sy, ha="center", va="center", fontsize=6.2, color="#172B3A")
                    if step_index:
                        ax.plot([x, x], [sy + 0.34, sy + 0.62], color=colour, linewidth=1.0)
            else:
                for offset in (-0.60, 0.0, 0.60):
                    ax.add_patch(FancyBboxPatch((x + offset - 0.22, 3.72), 0.44, 0.44,
                                                boxstyle="round,pad=0.02,rounding_size=0.04",
                                                facecolor="#EFF6FF", edgecolor=colour, linewidth=0.8))
                ax.plot([x - 0.90, x + 0.90], [3.36, 3.36], color=colour, linewidth=1.2)

        if node.get("visual_data"):
            data = node["visual_data"]
            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list) or not items:
                raise ValueError(f"node {node['id']} visual_data.items must be a non-empty list")
            unit = str(data.get("unit") or "")
            auxiliary(f"result_unit:{node['id']}", unit, x=x, y=5.12,
                      ha="center", va="center", fontsize=6.5, color="#475569")
            max_value = max([abs(float(item["value"])) for item in items]
                            + [abs(float(item["upper"])) for item in items if item.get("upper") is not None]
                            + [1e-12]) * 1.12
            baseline = 2.98
            ax.plot([x - 1.30, x + 1.30], [baseline, baseline], color="#475569", linewidth=0.75)
            gap = 2.45 / len(items)
            zero_values = [float(item["value"]) for item in items]
            for item_index, (item, value) in enumerate(zip(items, zero_values)):
                bx = x - 1.225 + gap * (item_index + 0.5)
                bar_width = min(0.52, gap * 0.62)
                height = value / max_value * 1.66
                bar = Rectangle((bx - bar_width / 2, baseline), bar_width, height,
                                facecolor=colour, edgecolor="#263238", linewidth=0.55,
                                hatch=["", "//", "..", "xx"][item_index % 4], zorder=3)
                ax.add_patch(bar)
                label_extent = float(item.get("upper", value)) if height >= 0 else float(item.get("lower", value))
                label_y = baseline + label_extent / max_value * 1.66 + (0.16 if height >= 0 else -0.16)
                auxiliary(f"result_value:{node['id']}:{item_index}", f"{value:g}",
                          x=bx, y=label_y, ha="center", va="bottom" if height >= 0 else "top",
                          fontsize=6.4, color="#172B3A")
                auxiliary(f"result_label:{node['id']}:{item_index}", _wrap(item.get("label") or item.get("id") or "", latin=11, cjk=6),
                          x=bx, y=2.66, ha="center", va="center", fontsize=6.1, color="#334155")
                lower, upper = item.get("lower"), item.get("upper")
                if lower is not None and upper is not None:
                    lo_y = baseline + float(lower) / max_value * 1.66
                    hi_y = baseline + float(upper) / max_value * 1.66
                    ax.plot([bx, bx], [lo_y, hi_y], color="#172B3A", linewidth=0.85, zorder=4)
                    ax.plot([bx - 0.12, bx + 0.12], [lo_y, lo_y], color="#172B3A", linewidth=0.75)
                    ax.plot([bx - 0.12, bx + 0.12], [hi_y, hi_y], color="#172B3A", linewidth=0.75)
                rendered = (bar.get_y() + bar.get_height() - baseline) * max_value / 1.66
                visual_marks.append({"node": node["id"], "item": item_index,
                                     "label": item.get("label") or item.get("id"),
                                     "evidence": item.get("evidence") or node.get("evidence"),
                                     "source_value": value, "rendered_value": rendered,
                                     "baseline_value": 0, "unit": unit,
                                     "lower": lower, "upper": upper,
                                     "geometry": {"x": bx, "y": baseline, "height": height}})
            note = data.get("n_caption") or (f"n = {data['n']}" if data.get("n") is not None else "")
            if data.get("uncertainty"):
                note = (note + " | " if note else "") + str(data["uncertainty"])
            if note:
                auxiliary(f"result_n:{node['id']}", note,
                                        x=x, y=2.28, ha="center", va="center", fontsize=6.1, color="#475569")
                # Keep one concise line between group labels and the card edge;
                # longer scope belongs in caption, never a two-word-per-line stack.
                aux[-1]["patch"] = box
        elif role == "conclusion":
            ax.add_patch(Circle((x, 3.82), 0.72, facecolor="#FDF2F8", edgecolor=colour,
                                linewidth=1.5, zorder=3))
            ax.add_patch(FancyArrowPatch((x - 0.34, 3.82), (x + 0.38, 3.82),
                                         arrowstyle="-|>", mutation_scale=15,
                                         linewidth=1.4, color=colour, zorder=4))

    drawn_edges = []
    for edge in edges:
        if edge.get("from") not in pos or edge.get("to") not in pos:
            continue
        start, end = pos[edge["from"]], pos[edge["to"]]
        arrow = FancyArrowPatch((start[0] + bw / 2, 4.55), (end[0] - bw / 2, 4.55),
                                arrowstyle="-|>" if edge.get("type") != "inhibit" else "-[",
                                mutation_scale=15, linewidth=1.6, color="#334155",
                                shrinkA=3, shrinkB=3, zorder=1)
        ax.add_patch(arrow)
        drawn_edges.append(arrow)
        if edge.get("label"):
            auxiliary(f"edge:{edge['from']}:{edge['to']}", str(edge["label"]),
                      x=(start[0] + end[0]) / 2, y=4.83, ha="center", va="bottom",
                      fontsize=6.2, color="#334155")

    limitations = spec.get("limitations") if isinstance(spec.get("limitations"), list) else []
    limit_texts = [str(item.get("text") or "") if isinstance(item, dict) else str(item) for item in limitations]
    if any(text.strip() for text in limit_texts):
        ax.add_patch(FancyBboxPatch((0.62, 0.46), 14.76, 1.10,
                                    boxstyle="round,pad=0.02,rounding_size=0.08",
                                    facecolor="#F8FAFC", edgecolor="#94A3B8", linewidth=0.7))
        auxiliary("limitations", "Scope / limitation: " + "; ".join(text for text in limit_texts if text.strip()),
                  x=8, y=1.01, ha="center", va="center", fontsize=6.6, color="#475569")

    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    svg, png, pdf = out_stem.with_suffix(".svg"), out_stem.with_suffix(".png"), out_stem.with_suffix(".pdf")
    fig.savefig(svg, format="svg", metadata={"Date": None})
    fig.savefig(png, format="png", dpi=dpi, metadata={"Software": "ga-narrative/v2"})
    fig.savefig(pdf, format="pdf", metadata={"CreationDate": None})
    description = (core_text + ". Reading order: " + ", ".join(str(x) for x in spec.get("reading_order") or [])
                   + ". Every result value and limitation is bound to declared evidence.")
    _stable_svg(svg, core_text or "Graphical abstract", description)
    caption = str(spec.get("caption") or "").strip()
    if limit_texts:
        caption = (caption + " " if caption else "") + "Scope/limitations: " + "; ".join(limit_texts)
    (out_stem.parent / "caption.txt").write_text(caption + "\n", encoding="utf-8")

    return {"fig": fig, "ax": ax, "artists": artists, "aux_artists": aux,
            "edges_drawn": drawn_edges, "pos": pos, "svg": svg, "png": png, "pdf": pdf,
            "dpi": dpi, "font_size": body_fs, "n_layers": count,
            "layout_depth": layout_depth, "font": font, "visual_marks": visual_marks,
            "description": description}


# Retain the same collision/export audit contract as the established schematic
# renderer instead of maintaining a second, weaker implementation.
audit = schematic.audit

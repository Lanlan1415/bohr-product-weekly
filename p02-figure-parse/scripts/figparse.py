"""figparse — turn a scientific figure into structured, evidence-backed data.

Two entry points:

  python scripts/figparse.py calibrate --image FIG.png --out calib.json
      Detect panels, frames and tick pixel positions. Prints the tick
      positions the caller must label (by OCR) to finish calibration.

  python scripts/figparse.py run --case /input/case.json --out /app/output
      Full pass. Reads the tick labels recorded in the case file, calibrates,
      digitises every series, and writes result.json.

The tool never invents a tick value. If labels are missing it degrades to
`status: partial` and reports readings in axis fractions, which are honest but
not in physical units.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate as C  # noqa: E402
import digitize as D  # noqa: E402
import scientific as S  # noqa: E402

SCHEMA_VERSION = "figparse/v2"


def _write_json(path: Path, payload: dict) -> None:
    """Atomic, deterministic UTF-8 JSON output with stable key order retained."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _status_exit(status: str) -> int:
    return {"success": 0, "partial": 3, "undetermined": 5}.get(status, 5)


def _load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def cmd_calibrate(args: argparse.Namespace) -> int:
    report = {"schema_version": SCHEMA_VERSION, "image": str(args.image),
              "status": "undetermined", "panels": [], "limits": []}
    try:
        rgb = _load_rgb(Path(args.image))
        mask = C.dark_ink_mask(rgb)   # axis furniture only: bars must not read as spines
        panels = C.find_panels(mask)
        for p in panels:
            x0, y0, x1, y1 = p["bbox_px"]["x0"], p["bbox_px"]["y0"], p["bbox_px"]["x1"], p["bbox_px"]["y1"]
            sub = mask[y0:y1, x0:x1]
            frame = C.find_frame(sub)
            entry = {"panel_id": p["panel_id"], "bbox_px": p["bbox_px"], "frame_px": frame}
            if frame:
                entry["x_tick_px"] = [x0 + t for t in C.find_ticks(sub, frame, "x")]
                entry["y_tick_px"] = [y0 + t for t in C.find_ticks(sub, frame, "y")]
                entry["next_step"] = (
                    "OCR the tick labels at these pixel positions, then pass the values "
                    "as x_tick_values / y_tick_values to `figparse run`."
                )
            report["panels"].append(entry)
        report["status"] = ("success" if panels and all(p.get("frame_px") for p in report["panels"])
                            else "partial" if panels else "undetermined")
        if not panels:
            report["limits"].append("no detectable panel; OCR/calibration was not invented")
    except (OSError, ValueError, TypeError) as exc:
        report["limits"].append("image could not be read: %s" % str(exc)[:200])

    if args.out:
        _write_json(Path(args.out), report)
        print(json.dumps({"ok": report["status"] != "undetermined", "status": report["status"],
                          "wrote": args.out, "panels": len(report["panels"])}))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return _status_exit(report["status"])


def _axis_reading(panel_mask, frame, spec: dict, axis: str) -> dict:
    """Calibrate one axis, trying sources in order of how much they can prove.

    The ladder exists because requiring every tick label is brittle: a single
    unreadable or spurious tick used to fail the whole axis and push the panel
    to `axis_fraction`. Each step down the ladder is weaker but still
    verifiable, and every result names the `source` it came from so a reviewer
    knows how much to trust it.

    1. tick positions + supplied values   -- residual proves the axis model
    2. same, with nulls for unread ticks  -- residual still proves it
    3. frame edges + declared axis limits -- no residual, stated as a caveat
    4. nothing                            -- axis_fraction, status partial
    """
    # Tick pixels and tick values are paired in reading order (left->right for
    # x, top->bottom for y). Fitting in that same raw pixel frame keeps the
    # pairing unambiguous: a y axis then simply gets a negative slope, because
    # image rows grow downward while the data axis grows upward. Digitisation
    # applies the fit to raw pixel coordinates too, so the two cannot disagree.
    px = C.find_ticks(panel_mask, frame, axis)
    raw = spec.get(f"{axis}_tick_values") or []
    scale = spec.get("x_scale" if axis == "x" else "y_scale", "auto")
    unit = spec.get(f"{axis}_unit")

    def _finish(fit: dict) -> dict:
        fit["unit"] = unit
        if axis == "y" and fit.get("ok"):
            # Convention: y_tick_values are listed in reading order (top ->
            # bottom), so a normal y axis fits with a negative slope. A positive
            # slope means either a genuinely inverted axis or values listed
            # bottom-up — either way a reviewer must see it, so it is recorded
            # rather than silently accepted.
            fit["values_increase_downward"] = fit["slope"] > 0
        return fit

    # --- 1 & 2: paired tick values, tolerating nulls for unread labels -------
    skipped: list[str] = []
    if raw and len(px) == len(raw):
        parsed = []
        for p, v in zip(px, raw):
            if v is None:
                continue
            try:
                parsed.append((p, float(v)))
            except (TypeError, ValueError):
                # A tick label that parses to no number is unread input: skip it and
                # say so, rather than crashing the digitisation.
                skipped.append(str(v)[:40])
        pairs = parsed
        if len(pairs) >= 2:
            fit = C.fit_axis([p for p, _ in pairs], [v for _, v in pairs], scale=scale)
            # A y axis normally has values decreasing down the page. If the fit
            # comes out the other way round, the overwhelmingly likely cause is
            # that the values were listed bottom-up rather than that the plot
            # has a genuinely inverted axis. Correct it, and say that we did —
            # reporting success while knowingly mirrored is the worst option.
            if (axis == "y" and fit.get("ok") and fit["slope"] > 0
                    and not spec.get("y_axis_inverted")):
                flipped = [(p, v) for p, v in reversed(pairs)]
                alt = C.fit_axis([p for p, _ in flipped], [v for _, v in flipped], scale=scale)
                if alt.get("ok"):
                    alt["orientation_corrected"] = True
                    alt["orientation_note"] = (
                        "supplied y_tick_values fitted with values increasing downward; "
                        "treated as a bottom-to-top list and reversed. Set "
                        "y_axis_inverted: true if this axis really is inverted."
                    )
                    fit = alt
            if fit.get("ok"):
                fit["label_source"] = "case_file"
                fit["source"] = "tick_labels"
                fit["ticks_paired"] = len(pairs)
                fit["ticks_detected"] = len(px)
                if skipped:
                    fit["skipped_labels"] = skipped
                fit["ticks_unread"] = len(px) - len(pairs)
                return _finish(fit)
        # Note: one label is deliberately not enough. A slope needs either two
        # labelled ticks or a declared limit; one label plus the pixel pitch
        # leaves the step size unknown, and assuming step=1 would silently
        # rescale the whole axis.

    # --- 3: frame edges plus declared limits --------------------------------
    limits = spec.get(f"{axis}_axis_limits")
    if isinstance(limits, (list, tuple)) and len(limits) == 2 and all(v is not None for v in limits):
        if axis == "x":
            fit = C.fit_from_limits(frame["left"], frame["right"], limits, scale=scale)
        else:
            # Frame top is the larger value on a normal y axis.
            fit = C.fit_from_limits(frame["top"], frame["bottom"], (limits[1], limits[0]), scale=scale)
        if fit.get("ok"):
            fit["unit"] = unit
            fit["label_source"] = "case_file"
            return _finish(fit)

    return {
        "ok": False,
        "reason": (
            f"no usable calibration for the {axis} axis: {len(px)} tick marks detected, "
            f"{len(raw)} tick values supplied. Supply one value per detected tick (null "
            f"where a label is unreadable), or give {axis}_axis_limits."
        ),
        "tick_px": px,
        "tick_values_supplied": len(raw),
        "unit": unit,
        "label_source": "missing",
        "source": "none",
    }


def _bar_series(i: int, col: dict, bars_info: dict, frame: dict, fx: dict, fy: dict,
                ink: "np.ndarray", x0: int, y0: int) -> dict:
    """One hue detected as solid bars: per-bar values, plus the marks above them.

    Each bar reports its top, the shared baseline and — when both axes are
    calibrated — the height top-minus-baseline, so a zero-based chart and an
    offset one can both be read without the tool assuming which is meant.
    Everything carries a `reading_tier`: `calibrated_digitised` when both axes
    fitted, `axis_fraction` when they did not.
    """
    cal_ok = bool(fx.get("ok") and fy.get("ok"))
    bl_px = bars_info["baseline_px"]
    rows = []
    for b in bars_info["bars"]:
        cx = (b["x0_px"] + b["x1_px"]) / 2.0
        if cal_ok:
            xv = float(C.px_to_value(cx, fx))
            top_v = float(C.px_to_value(b["top_px"], fy))
            base_v = float(C.px_to_value(b["bottom_px"], fy))
        else:
            xv = (cx - frame["left"]) / max(frame["right"] - frame["left"], 1)
            top_v = (frame["bottom"] - b["top_px"]) / max(frame["bottom"] - frame["top"], 1)
            base_v = (frame["bottom"] - b["bottom_px"]) / max(frame["bottom"] - frame["top"], 1)
        rows.append({
            "x_center": round(xv, 6),
            "top_value": round(top_v, 6),
            "baseline_value": round(base_v, 6),
            "height_value": round(top_v - base_v, 6) if cal_ok else None,
            "top_px": b["top_px"], "x_center_px": round(cx, 4),
            "width_px": b["width_px"],
        })

    ann = D.find_annotations_above(ink, frame, bars_info["bars"])
    err_rows = []
    if cal_ok:
        for e in ann["error_bar_candidates"]:
            err_rows.append({
                "x": round(float(C.px_to_value(e["x_px"], fx)), 6),
                "center_y": round(float(C.px_to_value(e["y_px"], fy)), 6),
                "height_value": round(abs(e["height_px"] * fy["slope"]), 6),
                "kind": e["kind"],
            })

    # A bar chart drawn from zero should put the shared baseline at 0; if the
    # calibration disagrees, say so instead of quietly rebasing.
    baseline_note = None
    if cal_ok:
        base_v = rows[0]["baseline_value"] if rows else None
        if base_v is not None and abs(base_v) > 2 * float(abs(fy["slope"])):
            baseline_note = (
                f"the shared baseline reads as {base_v}, not 0: the chart may be drawn with "
                "an offset, a broken axis, or the calibration is off — check against the figure"
            )

    return {
        "series_index": i,
        "chart_type": "bar",
        "reading_tier": "calibrated_digitised" if cal_ok else "axis_fraction",
        "appearance": {"hue_bin": col["hue_bin"],
                       "median_hue_deg": round(col["median_hue"], 1),
                       "pixels": col["pixels"]},
        "n_bars": len(rows),
        "baseline_value": round(float(C.px_to_value(bl_px, fy)), 6) if cal_ok else None,
        "baseline_note": baseline_note,
        "bars": rows,
        "annotations": {
            "error_bar_candidates": err_rows,
            "marker_candidates": ann["marker_candidates"],
            "note": ("ink marks just above the bar tops: tall thin strokes read as error-bar "
                     "candidates, compact blobs as significance markers. Candidates only — a "
                     "reviewer confirms them against the figure"),
        } if (ann["error_bar_candidates"] or ann["marker_candidates"]) else {
            "error_bar_candidates": [], "marker_candidates": [],
            "note": "no marks detected above the bar tops"},
        "evidence": {
            "read_by": "solid-column detector: flat tops on a shared baseline inside the frame",
            "baseline_px": bl_px,
            "frame_px": {k: frame[k] for k in ("left", "top", "right", "bottom")},
            "panel_origin_px": [x0, y0],
        },
    }


def _digitise_panel(rgb, panel, spec) -> dict:
    x0, y0 = panel["bbox_px"]["x0"], panel["bbox_px"]["y0"]
    x1, y1 = panel["bbox_px"]["x1"], panel["bbox_px"]["y1"]
    sub_rgb = rgb[y0:y1, x0:x1]
    # Axis furniture (frame, ticks) is near-black; data ink is saturated. Frame
    # and tick search run on the dark subset so solid bars never read as spines.
    axis_mask = C.dark_ink_mask(sub_rgb)
    full_mask = C.ink_mask(C.load_gray(sub_rgb))

    frame = C.find_frame(axis_mask)
    out = {"panel_id": panel["panel_id"], "bbox_px": panel["bbox_px"], "frame_px": frame,
           "series": [], "status": "undetermined", "notes": []}
    if frame is None:
        out["notes"].append(
            "No axis frame found in this panel. It is likely an image/gel/micrograph panel "
            "or the axes are unlabelled; digitisation by pixel-to-data calibration does not apply."
        )
        return out

    fx = _axis_reading(axis_mask, frame, spec, "x")
    fy = _axis_reading(axis_mask, frame, spec, "y")
    out["calibration"] = {"x": fx, "y": fy}

    if not (fx.get("ok") and fy.get("ok")):
        out["status"] = "partial"
        out["notes"].append(
            "Calibration incomplete, so readings are reported as axis fractions "
            "(0 = frame left/bottom, 1 = frame right/top) instead of physical values."
        )

    colors = D.find_series_colors(sub_rgb, frame)
    if fy.get("values_increase_downward"):
        out["notes"].append(
            "y calibration has values increasing downward. If this figure's y axis is "
            "ordinary, the y_tick_values were listed bottom-to-top instead of top-to-bottom; "
            "re-run with the values reversed to confirm."
        )
    for i, col in enumerate(colors):
        m = D.series_mask(sub_rgb, frame, col["hue_bin"])

        # --- statistical charts: solid bars -------------------------------
        # A bar read through the curve path would come out as a horizontal line
        # through its middle, which is not a reading, it is an artefact. When
        # this colour forms flat-topped columns on a shared baseline, report
        # the bars themselves and skip the per-column trace.
        bars_info = D.detect_bars(m, frame)
        if bars_info:
            out["series"].append(_bar_series(
                i, col, bars_info, frame, fx, fy, full_mask, x0, y0))
            continue

        pts = D.extract_points(m, frame, n_markers=spec.get("n_markers", 0))
        if len(pts) < 3:
            continue
        pts = D.thin_curve(pts, spec.get("every", 1))

        xs_px = np.array([p["x_px"] for p in pts])
        ys_px = np.array([p["y_px"] for p in pts])

        if fx.get("ok") and fy.get("ok"):
            xs = C.px_to_value(xs_px, fx)
            ys = C.px_to_value(ys_px, fy)
            unit_x, unit_y = fx.get("unit"), fy.get("unit")
        else:
            xs = (xs_px - frame["left"]) / max(frame["right"] - frame["left"], 1)
            ys = (frame["bottom"] - ys_px) / max(frame["bottom"] - frame["top"], 1)
            unit_x = unit_y = "axis_fraction"

        thick = np.array([p.get("thickness_px", 1) for p in pts], dtype=float)
        # A stroked line is several pixels wide; its centre is only known to
        # about half the stroke, so convert that stroke width into data units
        # and report it as the per-point reading uncertainty.
        # On a log axis the same pixel error is multiplicative: half a stroke
        # becomes a constant *factor*, not a constant offset. Reporting a linear
        # bar there would understate the error at the top of the axis and
        # overstate it at the bottom.
        median_thickness = float(np.median(thick))
        half_thick = float(median_thickness / 2.0)
        if fy.get("ok") and fy.get("scale") == "log":
            factor = float(10 ** (half_thick * abs(fy["slope"])))
            y_unc = None
            y_unc_rel = round(factor - 1.0, 6)
            unc_basis = ("log axis: half the median stroke thickness converted to a "
                         "multiplicative factor; y_uncertainty_relative is the fractional "
                         "error, applied as y * (1 +/- that)")
        elif fy.get("ok"):
            y_unc = float(half_thick * abs(fy["slope"]))
            y_unc_rel = None
            unc_basis = ("half the median stroke thickness in pixels, converted through the "
                         "fitted y axis; it measures reading precision, not accuracy against "
                         "the underlying data")
        else:
            y_unc = float(half_thick / max(frame["bottom"] - frame["top"], 1))
            y_unc_rel = None
            unc_basis = "axis fraction, from half the median stroke thickness"

        # Error bars are reported as candidates, never asserted as measured
        # data: a steep line can mimic them, so the caller is told what they are.
        bars = D.find_error_bars(m, frame)
        if bars and fy.get("ok"):
            bars = [{"x_px": b["x_px"], "y_px": round(b["y_px"], 2),
                     "x": round(float(C.px_to_value(b["x_px"], fx)), 6) if fx.get("ok") else None,
                     "y": round(float(C.px_to_value(b["y_px"], fy)), 6),
                     "y_err": round(abs(b["half_length_px"] * fy["slope"]), 6),
                     "half_length_px": round(b["half_length_px"], 2)} for b in bars]
        else:
            bars = []

        out["series"].append({
            "series_index": i,
            "chart_type": "curve",
            "reading_tier": "calibrated_digitised" if (fx.get("ok") and fy.get("ok")) else "axis_fraction",
            "appearance": {"hue_bin": col["hue_bin"], "median_hue_deg": round(col["median_hue"], 1),
                           "pixels": col["pixels"]},
            "n_points": int(len(xs)),
            "x": [round(float(v), 6) for v in xs],
            "y": [round(float(v), 6) for v in ys],
            "x_unit": unit_x,
            "y_unit": unit_y,
            "y_uncertainty": None if y_unc is None else round(y_unc, 6),
            "y_uncertainty_relative": y_unc_rel,
            "uncertainty_basis": unc_basis,
            "median_stroke_thickness_px": round(median_thickness, 4),
            "error_bar_candidates": bars,
            "error_bar_note": (
                "tall isolated vertical strokes, reported as candidates: an error bar and a "
                "steep line segment look alike, so a reviewer must confirm against the figure"
            ) if bars else "none detected",
            "features": _features(xs, ys, y_unc if y_unc is not None else float(np.median(np.abs(ys)) * (y_unc_rel or 0.0))),
            "evidence": {
                "read_by": "colour-mask column sampling inside the detected frame",
                "frame_px": {k: frame[k] for k in ("left", "top", "right", "bottom")},
                "panel_origin_px": [x0, y0],
                "points_px": [[round(float(p["x_px"]), 4), round(float(p["y_px"]), 4)] for p in pts],
            },
        })

    out["status"] = "success" if (out["series"] and fx.get("ok") and fy.get("ok")) else "partial"
    if not out["series"]:
        out["notes"].append("No saturated data series found inside the frame.")
    return out


def _features(xs: np.ndarray, ys: np.ndarray, y_unc: float) -> dict:
    """Summary descriptors that are true by construction from the digitised trace.

    Kept deliberately small: only quantities that a reader could verify by eye
    on the figure. Anything requiring a model assumption (fit parameters,
    derivative sign at a point) is left to the caller.
    """
    if xs.size < 2:
        return {}
    i_max, i_min = int(np.argmax(ys)), int(np.argmin(ys))
    d = np.diff(ys)
    # Count direction changes on a lightly smoothed trace. On raw pixel data
    # the stroke jitter flips the sign of the difference almost every column,
    # so the raw count measures noise, not shape.
    w = max(3, (ys.size // 60) * 2 + 1)
    w = min(w, ys.size if ys.size % 2 else ys.size - 1)
    smooth = np.convolve(ys, np.ones(w) / w, mode="valid") if w >= 3 else ys
    ds = np.diff(smooth)
    flips = int(np.sum(np.sign(ds[1:]) != np.sign(ds[:-1]))) if ds.size > 1 else 0
    # Net change across the whole trace, not the mean step: a monotone ramp has
    # a tiny mean step and a large net change, and "flat" would be wrong.
    net = float(ys[-1] - ys[0])
    return {
        "x_range": [round(float(xs.min()), 6), round(float(xs.max()), 6)],
        "y_max": round(float(ys[i_max]), 6),
        "y_max_at_x": round(float(xs[i_max]), 6),
        "y_min": round(float(ys[i_min]), 6),
        "y_min_at_x": round(float(xs[i_min]), 6),
        "y_span": round(float(ys.max() - ys.min()), 6),
        "direction_changes": flips,
        "direction_changes_basis": f"sign changes of the trace smoothed over {w} points",
        "trend": ("increasing" if net > 2 * y_unc else
                  "decreasing" if net < -2 * y_unc else "flat"),
        "trend_net_change": round(net, 6),
        "trend_basis": "net change from first to last point, compared against 2 x y_uncertainty",
    }


def _load_case(case_path: Path):
    try:
        case = json.loads(case_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "case.json could not be read as a JSON object: %s" % str(exc)[:200]
    if not isinstance(case, dict):
        return None, "case.json is not a JSON object"
    return case, None


def _echo_contract(result, case):
    """All declared fields survive; readable supplied values pass through untouched."""
    contract = case.get("output_contract")
    if contract is None:
        return
    if not isinstance(contract, dict):
        result["limits"].append("output_contract is not an object; no field names inferred")
        return
    bulky = {"output_contract", "images", "figures", "tables", "text_claims", "caption_claims"}
    for key in contract:
        if key in result:
            continue
        if key in case and key not in bulky:
            result[key] = case[key]
        else:
            result[key] = None
            result["limits"].append("output_contract field '%s' was not derivable by figparse" % key)


def _ingest_tables(case, case_path, result):
    raw_tables = case.get("tables") or []
    if isinstance(raw_tables, (str, dict)):
        raw_tables = [raw_tables]
    if not isinstance(raw_tables, list):
        result["limits"].append("tables is not a path/list; table ingestion skipped")
        return
    import tables as T
    for raw in raw_tables:
        item = raw if isinstance(raw, dict) else {"path": raw}
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            result["limits"].append("a table entry was not a usable path: %r" % (raw,))
            continue
        p = Path(item["path"])
        if not p.is_absolute():
            p = case_path.parent / p
        try:
            parsed = T.parse_table(p)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            parsed = {"path": str(p), "ok": False,
                      "reason": "table could not be parsed without guessing: %s" % str(exc)[:160]}
        if item.get("locator") is not None:
            parsed["locator"] = item["locator"]
        if item.get("caption") is not None:
            parsed["caption"] = item["caption"]
        result["tables"].append(parsed)
        if not parsed.get("ok"):
            result["limits"].append("table not parsed: %s (%s)" % (p, parsed.get("reason")))


def cmd_run(args: argparse.Namespace) -> int:
    case_path = Path(args.case)
    out_dir = Path(args.out)
    case, error = _load_case(case_path)
    if error:
        result = {"schema_version": SCHEMA_VERSION, "case_id": "UNKNOWN", "status": "undetermined",
                  "panels": [], "tables": [], "readings": [], "figure_metadata": [],
                  "limits": [error], "refusal": {"code": "figparse.case_unreadable", "message": error}}
        _write_json(out_dir / "result.json", result)
        print(json.dumps({"ok": False, "status": "undetermined", "wrote": str(out_dir / "result.json")}, ensure_ascii=False))
        return 5

    case_id = case.get("case_id") or case.get("id") or "UNKNOWN"
    images = case.get("images") or case.get("figures") or []
    if isinstance(images, str):
        images = [images]
    if not isinstance(images, list):
        images = []
    result = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "status": "undetermined",
        "panels": [], "tables": [], "readings": [], "figure_metadata": [],
        "uncertainty": [], "limits": [],
        "provenance": {"tool": "figparse", "schema_version": SCHEMA_VERSION,
                       "case_file": str(case_path), "images_seen": len(images)},
        "method": {"curve": "colour-mask column sampling; geometry and caller-read tick labels",
                   "bar": "flat-top/shared-baseline detector",
                   "uncertainty": "both pixel endpoints mapped through each calibrated axis; not a statistical CI",
                   "reference_design": "DePlot-style image-to-table objective with explicit coordinate calibration and rejection instead of free-form numeric generation"},
    }

    normalized_specs = []
    for raw_spec in images:
        spec = {"path": raw_spec} if isinstance(raw_spec, str) else dict(raw_spec) if isinstance(raw_spec, dict) else None
        if spec is None:
            result["limits"].append("an image entry was neither a path nor an object: %r" % (raw_spec,))
            continue
        raw_path = spec.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            result["limits"].append("an image entry has no usable path")
            continue
        p = Path(raw_path)
        if not p.is_absolute():
            p = (case_path.parent / p).resolve()
        spec["resolved_path"] = str(p)
        normalized_specs.append(spec)
        if not p.exists():
            result["limits"].append("image not found: %s" % p)
            continue
        try:
            rgb = _load_rgb(p)
            mask = C.ink_mask(C.load_gray(rgb))
            panels = C.find_panels(mask)
            if not panels:
                result["limits"].append("no readable panel detected in %s" % p)
            for panel in panels:
                entry = _digitise_panel(rgb, panel, spec)
                entry["image"] = str(p)
                result["panels"].append(entry)
        except (OSError, ValueError, TypeError) as exc:
            result["limits"].append("image processing refused for %s: %s" % (p, str(exc)[:160]))

    _ingest_tables(case, case_path, result)
    S.bind_context({"images": normalized_specs}, result)
    result["readings"] = S.attach_intervals(result)
    result["claim_alignment"] = S.align_claims(case, result)
    result["sources"] = ([{"kind": "image", "path": p.get("resolved_path"),
                           "caption_locator": p.get("caption_locator")} for p in normalized_specs] +
                         [{"kind": "table", "path": t.get("path"), "ok": t.get("ok")}
                          for t in result["tables"]])
    got = [p for p in result["panels"] if p.get("series")]
    table_ok = bool(result["tables"]) and all(t.get("ok") for t in result["tables"])
    inconsistent = [a for a in result["claim_alignment"] if a.get("status") == "inconsistent"]
    unresolved = [a for a in result["claim_alignment"] if a.get("status") == "unresolved"]
    if got and all(p["status"] == "success" for p in got) and not result["limits"] and not inconsistent and not unresolved:
        result["status"] = "success"
    elif got or table_ok:
        result["status"] = "partial"
        if not all(p["status"] == "success" for p in got):
            result["limits"].append("some panels are uncalibrated or contain no digitizable series")
    else:
        result["status"] = "undetermined"
        result["limits"].append("no panel produced a digitizable series and no table was parsed")
        result["refusal"] = {"code": "figparse.no_readable_data",
                             "message": "no physical/axis-fraction data or usable original table was derived"}
    if inconsistent:
        result["limits"].append("%d declared text/caption numeric claim(s) conflict with the linked raster interval" % len(inconsistent))
    if unresolved:
        result["limits"].append("%d declared text/caption claim(s) could not be linked" % len(unresolved))
    if result["status"] != "success":
        result["uncertainty"].append({"type": "reading_completeness", "status": result["status"],
                                      "impact": "do not present missing/calibration/context gaps as recovered science"})
    for panel in result["panels"]:
        for series in panel.get("series", []):
            if series.get("value_status") == "estimated_from_raster_not_exact":
                result["uncertainty"].append({"type": "raster_estimate", "panel_id": panel.get("panel_id"),
                                              "series_index": series.get("series_index"),
                                              "basis": series.get("uncertainty_note")})
    _echo_contract(result, case)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "result.json", result)
    if result["readings"]:
        S.write_readings_csv(result["readings"], out_dir / "digitized.csv")
    print(json.dumps({"ok": result["status"] != "undetermined", "status": result["status"],
                      "panels": len(result["panels"]), "tables": len(result["tables"]),
                      "readings": len(result["readings"]),
                      "wrote": str(out_dir / "result.json")}, ensure_ascii=False))
    return _status_exit(result["status"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="figparse", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("calibrate", help="detect panels/frames/ticks; print tick pixel positions")
    c.add_argument("--image", required=True)
    c.add_argument("--out")
    c.set_defaults(func=cmd_calibrate)

    r = sub.add_parser("run", help="calibrate, digitise, and write result.json")
    r.add_argument("--case", required=True)
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_run)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
